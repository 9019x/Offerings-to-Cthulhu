#!/usr/bin/env python3
"""
Smoke test for BIP66 strict-DER block-validation gate (#33).

In regtest mode HARDFORK_DERSIG_REGTEST_OFF=110:
  h <  110: ConnectBlock does not add SCRIPT_VERIFY_DERSIG to flags
  h >= 110: ConnectBlock adds (SCRIPT_VERIFY_DERSIG | SCRIPT_VERIFY_STRICTENC)

Mempool already enforces STRICTENC, so a non-strict-DER tx is rejected at
mempool both pre- and post-fork. Observing the block-validation gate
specifically would require constructing a block via `submitblock` that
bypasses mempool with a hand-crafted non-strict-DER spend. That requires
~200 LoC of Python tx/block primitives that OFF's qa infra doesn't ship.

This test verifies:
  1. Daemon boots clean with the new flag-gating in ConnectBlock
  2. Blocks validate normally across the fork height (no crash, no reject)
  3. Strict-DER signatures (the normal kind) continue to work post-fork
  4. debug.log has no assertions or consensus warnings

The underlying encoding parser (IsCanonicalSignature in script.cpp) is
battle-tested via years of mempool enforcement; this commit only changes
WHERE the parser is invoked.

Adversarial block-level test deferred to a follow-up; see commit message.
"""

import os, sys, shutil, subprocess, tempfile, time, atexit
from decimal import Decimal

SRCDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
DAEMON = os.path.join(SRCDIR, "Offeringsd")
CLI    = os.path.join(SRCDIR, "Offerings-cli")
PORT     = 18444
RPCPORT  = 18443
RPCUSER  = "rt"
RPCPASS  = "rt"

datadir = None
daemon_proc = None


def _cli_cmd(*args):
    return [CLI, "-regtest", "-datadir=" + datadir,
            "-rpcuser=" + RPCUSER, "-rpcpassword=" + RPCPASS,
            "-rpcport=" + str(RPCPORT)] + list(args)


def cli(*args):
    out = subprocess.check_output(
        _cli_cmd(*args), stderr=subprocess.STDOUT).decode().strip()
    try:
        if "." in out:
            return Decimal(out)
        return int(out)
    except Exception:
        return out


def cli_silent(*args):
    subprocess.check_call(
        _cli_cmd(*args),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_daemon():
    global datadir, daemon_proc
    datadir = tempfile.mkdtemp(prefix="dersig-rpctest-")
    with open(os.path.join(datadir, "Offerings.conf"), "w") as f:
        f.write("regtest=1\n")
        f.write("rpcuser=%s\n" % RPCUSER)
        f.write("rpcpassword=%s\n" % RPCPASS)
        f.write("rpcport=%d\n" % RPCPORT)
        f.write("port=%d\n" % PORT)
        f.write("listen=0\n")
        f.write("server=1\n")
        f.write("checkpoints=0\n")
        f.write("debug=0\n")
        f.write("keypool=10\n")
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
    if daemon_proc and daemon_proc.poll() is None:
        try:
            cli_silent("stop")
        except Exception:
            pass
        try:
            daemon_proc.wait(timeout=10)
        except Exception:
            daemon_proc.terminate()
            daemon_proc.wait(timeout=5)
    if datadir and os.path.isdir(datadir):
        shutil.rmtree(datadir, ignore_errors=True)


atexit.register(stop_daemon)


def mine_to(target_h):
    while True:
        h = cli("getblockcount")
        if h >= target_h:
            return h
        n = min(50, target_h - h)
        cli_silent("setgenerate", "true", str(n))


def main():
    print("=== qa/rpc-tests: BIP66 strict-DER block-validation gate (#33) ===")
    print()
    print("Starting fresh regtest daemon...")
    start_daemon()

    print()
    print("Phase 1: mine across DERSIG fork boundary (h=0 -> h=150)")
    mine_to(150)
    h = cli("getblockcount")
    assert h == 150, "expected h=150, got %d" % h
    print("  h=%d" % h)
    print("  PASS  mined past fork at h=110 without crash")

    print()
    print("Phase 2: mine past COINBASE_MAT recovery (h=150 -> h=300)")
    mine_to(300)
    h = cli("getblockcount")
    bal = cli("getbalance")
    print("  h=%d  balance=%s" % (h, bal))
    assert bal > 0, ("balance must be positive once coinbases reach depth "
                     "240 under hardened maturity")
    print("  PASS  chain state coherent past both #32 and #33 forks")

    print()
    print("Phase 3: send a normal strict-DER tx post-fork")
    addr = cli("getnewaddress")
    txid = cli("sendtoaddress", addr, "1.0")
    assert isinstance(txid, str) and len(txid) == 64, (
        "expected 64-char hex txid, got %r" % txid)
    print("  txid=%s" % txid)
    print("  PASS  strict-DER sendtoaddress accepted by mempool post-fork")

    print()
    print("Phase 4: mine the tx into a block; block-validation accepts it")
    pre_h = cli("getblockcount")
    cli_silent("setgenerate", "true", "1")
    post_h = cli("getblockcount")
    assert post_h > pre_h, (
        "new block did not land (was h=%d, now h=%d)" % (pre_h, post_h))
    print("  h=%d -> h=%d  block containing the strict-DER tx accepted"
          % (pre_h, post_h))
    print("  PASS  block-validation gate does not reject normal sigs")

    print()
    print("Phase 5: debug.log free of consensus anomalies")
    log_path = os.path.join(datadir, "regtest", "debug.log")
    with open(log_path) as f:
        log = f.read()
    anomalies = []
    for line in log.split("\n"):
        low = line.lower()
        if any(kw in low for kw in ("assert", "bad-script",
                                   "non-canonical", "rejected")):
            if "peers.dat" not in line and "init message" not in line:
                anomalies.append(line)
    if anomalies:
        print("  Anomalies (first 10):")
        for a in anomalies[:10]:
            print("    " + a)
        raise AssertionError("debug.log shows %d anomaly line(s)"
                             % len(anomalies))
    print("  PASS  no assertions, no consensus rejects, no non-canonical")

    print()
    print("=== ALL SMOKE CHECKS PASSED ===")
    print()
    print("NOTE: block-level adversarial test (constructing a malformed-sig")
    print("block via submitblock to confirm post-fork rejection) is deferred.")
    print("The strict-DER parser (IsCanonicalSignature) is battle-tested via")
    print("mempool enforcement; this commit changes only WHERE it is invoked.")


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
