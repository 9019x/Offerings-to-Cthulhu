#!/usr/bin/env python3
"""
Boundary test for rolling-checkpoint Phase 1 (#6).

In regtest mode:
  HARDFORK_ROLLING_CKPT_REGTEST_OFF = 110
  ROLLING_DEPTH                     = 1023
  ROLLING_KEEP                      = 10000

First rolling-checkpoint lock fires at tip >= activation + depth
(110 + 1023 = 1133), locking the ancestor at tip - 1023:
  h=1133 -> lock entry for height 110
  h=1134 -> lock entry for height 111
  ...

The test covers six properties:
  1. Pre-activation tip (h < 1133) -> rolling entries empty regardless
     of how many blocks have been mined.
  2. Cross-activation tip (h >= 1133) -> first entry at height 110.
  3. Continued rolling -> each new block adds one entry at tip - 1023.
  4. Persistence -> entries survive daemon restart (disk round-trip
     through <datadir>/rolling_checkpoints.dat).
  5. Runtime toggle -> setrollingcheckpointsenabled false makes
     MaybeRollForward a no-op; flipping back resumes.
  6. clearrollingcheckpoints RPC -> entries below threshold dropped
     from memory AND disk.
"""

import os, sys, shutil, subprocess, tempfile, time, atexit, json

SRCDIR  = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
DAEMON  = os.path.join(SRCDIR, "Offeringsd")
CLI     = os.path.join(SRCDIR, "Offerings-cli")
PORT    = 18454
RPCPORT = 18453
RPCUSER = "rt"
RPCPASS = "rt"

ACTIVATION = 110
DEPTH      = 1023
FIRST_LOCK_TIP = ACTIVATION + DEPTH   # 1133

datadir = None
daemon_proc = None


def _cli_cmd(*args):
    return [CLI, "-regtest", "-datadir=" + datadir,
            "-rpcuser=" + RPCUSER, "-rpcpassword=" + RPCPASS,
            "-rpcport=" + str(RPCPORT)] + list(args)


def cli(*args):
    out = subprocess.check_output(
        _cli_cmd(*args), stderr=subprocess.STDOUT).decode().strip()
    return out


def cli_int(*args):
    return int(cli(*args))


def cli_json(*args):
    return json.loads(cli(*args))


def cli_silent(*args):
    subprocess.check_call(
        _cli_cmd(*args),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write_conf(extra_lines=()):
    with open(os.path.join(datadir, "Offerings.conf"), "w") as f:
        f.write("regtest=1\n")
        f.write("rpcuser=%s\n" % RPCUSER)
        f.write("rpcpassword=%s\n" % RPCPASS)
        f.write("rpcport=%d\n" % RPCPORT)
        f.write("port=%d\n" % PORT)
        f.write("listen=0\n")
        f.write("server=1\n")
        # Note: NOT checkpoints=0 — we want the master Checkpoints flag
        # on so the rolling subsystem activates.
        f.write("debug=0\n")
        f.write("keypool=10\n")
        for line in extra_lines:
            f.write(line + "\n")


def start_daemon(extra_lines=()):
    global daemon_proc
    write_conf(extra_lines)
    daemon_proc = subprocess.Popen(
        [DAEMON, "-datadir=" + datadir],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i in range(60):
        try:
            cli_silent("getblockcount")
            print("  daemon ready (%ds)" % i)
            return
        except subprocess.CalledProcessError:
            time.sleep(1)
    raise RuntimeError("daemon never came up")


def stop_daemon():
    global daemon_proc
    if daemon_proc and daemon_proc.poll() is None:
        try:
            cli_silent("stop")
        except Exception:
            pass
        try:
            daemon_proc.wait(timeout=20)
        except Exception:
            daemon_proc.terminate()
            daemon_proc.wait(timeout=5)
        daemon_proc = None


def cleanup_datadir():
    if datadir and os.path.isdir(datadir):
        shutil.rmtree(datadir, ignore_errors=True)


def atexit_handler():
    stop_daemon()
    cleanup_datadir()


atexit.register(atexit_handler)


def mine_to(target_h):
    while True:
        h = cli_int("getblockcount")
        if h >= target_h:
            return h
        n = min(200, target_h - h)
        cli_silent("setgenerate", "true", str(n))


def main():
    global datadir
    print("=== qa/rpc-tests: rolling checkpoints Phase 1 (#6) ===")
    print()
    datadir = tempfile.mkdtemp(prefix="rollckpt-rpctest-")
    print("Starting fresh regtest daemon... (datadir=%s)" % datadir)
    start_daemon()

    print()
    print("Phase 1: pre-activation tip (h=%d), rolling map must stay empty"
          % (FIRST_LOCK_TIP - 1))
    mine_to(FIRST_LOCK_TIP - 1)
    h = cli_int("getblockcount")
    assert h == FIRST_LOCK_TIP - 1, "expected h=%d, got %d" % (FIRST_LOCK_TIP - 1, h)
    rc = cli_json("getrollingcheckpoints")
    assert rc["enabled"] is True, "expected enabled=true by default"
    assert rc["activation_height"] == ACTIVATION, \
        "expected activation_height=%d, got %d" % (ACTIVATION, rc["activation_height"])
    assert rc["depth"] == DEPTH, "expected depth=%d, got %d" % (DEPTH, rc["depth"])
    assert rc["count"] == 0, "expected 0 entries at h=%d, got %d" % (h, rc["count"])
    assert rc["entries"] == [], "expected empty entries list at h=%d" % h
    print("  h=%d  count=0  PASS" % h)

    print()
    print("Phase 2: cross activation boundary at h=%d, first entry locks at h=%d"
          % (FIRST_LOCK_TIP, ACTIVATION))
    mine_to(FIRST_LOCK_TIP)
    h = cli_int("getblockcount")
    rc = cli_json("getrollingcheckpoints")
    assert rc["count"] == 1, "expected 1 entry at h=%d, got %d" % (h, rc["count"])
    entry = rc["entries"][0]
    assert entry["height"] == ACTIVATION, \
        "expected first locked height=%d, got %d" % (ACTIVATION, entry["height"])
    expected_hash = cli("getblockhash", str(ACTIVATION))
    assert entry["hash"] == expected_hash, \
        "locked hash mismatch: rolling=%s expected=%s" % (entry["hash"], expected_hash)
    print("  h=%d  count=1  locked_h=%d  hash=%s..." % (h, entry["height"], entry["hash"][:16]))
    print("  PASS  first lock at the exact activation block")

    print()
    print("Phase 3: continued rolling, each new tip block adds tip-DEPTH")
    mine_to(FIRST_LOCK_TIP + 5)
    h = cli_int("getblockcount")
    rc = cli_json("getrollingcheckpoints")
    assert rc["count"] == 6, "expected 6 entries at h=%d, got %d" % (h, rc["count"])
    heights = [e["height"] for e in rc["entries"]]
    assert heights == list(range(ACTIVATION, ACTIVATION + 6)), \
        "heights mismatch: %s" % heights
    for e in rc["entries"]:
        assert e["hash"] == cli("getblockhash", str(e["height"])), \
            "hash mismatch at h=%d" % e["height"]
    print("  h=%d  count=6  heights=%d..%d  PASS" % (h, heights[0], heights[-1]))

    print()
    print("Phase 4: persistence across restart — stop, start, verify map reloads")
    locked_before = cli_json("getrollingcheckpoints")["entries"]
    stop_daemon()
    time.sleep(1)
    start_daemon()
    rc = cli_json("getrollingcheckpoints")
    assert rc["count"] == len(locked_before), \
        "post-restart count=%d, expected %d" % (rc["count"], len(locked_before))
    for a, b in zip(rc["entries"], locked_before):
        assert a["height"] == b["height"] and a["hash"] == b["hash"], \
            "post-restart entry mismatch: %s vs %s" % (a, b)
    h = cli_int("getblockcount")
    print("  h=%d  reloaded count=%d  PASS" % (h, rc["count"]))

    print()
    print("Phase 5: runtime toggle — setrollingcheckpointsenabled false stops new locks")
    cli_silent("setrollingcheckpointsenabled", "false")
    count_before = cli_json("getrollingcheckpoints")["count"]
    mine_to(h + 5)
    h2 = cli_int("getblockcount")
    rc = cli_json("getrollingcheckpoints")
    assert rc["enabled"] is False, "toggle did not take effect"
    assert rc["count"] == count_before, \
        "expected count unchanged at %d (toggle off), got %d" \
        % (count_before, rc["count"])
    print("  h=%d  count unchanged at %d while toggled off  PASS" % (h2, count_before))

    cli_silent("setrollingcheckpointsenabled", "true")
    mine_to(h2 + 3)
    h3 = cli_int("getblockcount")
    rc = cli_json("getrollingcheckpoints")
    assert rc["enabled"] is True, "re-enable did not take effect"
    assert rc["count"] >= count_before + 3, \
        "expected count to resume growing after re-enable, got %d (was %d)" \
        % (rc["count"], count_before)
    print("  h=%d  resumed: count=%d  PASS" % (h3, rc["count"]))

    print()
    print("Phase 6: clearrollingcheckpoints below_height drops entries from memory + disk")
    rc_before = cli_json("getrollingcheckpoints")
    threshold = rc_before["entries"][3]["height"]
    cli_silent("clearrollingcheckpoints", str(threshold))
    rc_after = cli_json("getrollingcheckpoints")
    assert all(e["height"] >= threshold for e in rc_after["entries"]), \
        "entries below threshold=%d survived clear" % threshold
    expected_remaining = sum(1 for e in rc_before["entries"] if e["height"] >= threshold)
    assert rc_after["count"] == expected_remaining, \
        "post-clear count=%d, expected %d" % (rc_after["count"], expected_remaining)
    print("  threshold=%d  before=%d  after=%d  PASS"
          % (threshold, rc_before["count"], rc_after["count"]))

    # Verify the disk rewrite by restart-reloading and confirming we get
    # exactly the post-clear set back.
    stop_daemon()
    time.sleep(1)
    start_daemon()
    rc_restart = cli_json("getrollingcheckpoints")
    assert rc_restart["count"] == rc_after["count"], \
        "disk did not match memory after clear+restart"
    for a, b in zip(rc_restart["entries"], rc_after["entries"]):
        assert a["height"] == b["height"] and a["hash"] == b["hash"], \
            "post-clear restart mismatch"
    print("  post-clear restart: count=%d matches disk  PASS" % rc_restart["count"])

    print()
    print("=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except AssertionError as e:
        print()
        print("ASSERTION FAILED:", str(e))
        sys.exit(1)
    except Exception as e:
        import traceback
        print()
        print("EXCEPTION:", str(e))
        traceback.print_exc()
        sys.exit(2)
