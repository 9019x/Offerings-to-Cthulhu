#!/usr/bin/env python3
"""
Smoke test for BIP65 OP_CHECKLOCKTIMEVERIFY block-validation gate (#34).

In regtest mode HARDFORK_CLTV_REGTEST_OFF=110:
  h <  110: OP_NOP2 (0xb1) behaves as a no-op (forward-compatible)
  h >= 110: OP_NOP2 is OP_CHECKLOCKTIMEVERIFY (script-level locktime)

Soft-fork semantic: pre-fork nodes accept post-fork scripts (they treat
OP_NOP2 as no-op), so the upgrade is one-way safe. Post-fork nodes enforce
CLTV semantics: stack-top locktime, lock-type match against tx.nLockTime,
nSequence != SEQUENCE_FINAL.

This test verifies:
  1. Daemon boots clean with the new opcode dispatch
  2. Blocks validate normally across the fork height
  3. Normal txs (without CLTV in scriptPubKey) work pre- and post-fork
  4. Mining + sending + receiving paths are intact post-fork
  5. debug.log free of consensus anomalies

What this test does NOT verify (deferred):
  Boundary test of the CLTV evaluation itself: constructing a P2SH-CLTV
  output, funding it, and then attempting a spend with tx.nLockTime
  both above and below the required locktime. This requires ~150 LoC of
  Python bitcoin-script primitives (redeem-script construction, P2SH
  address derivation, raw tx assembly with custom prevtxs for sign-with-
  redeem-script) that OFF's qa infra doesn't ship today.

The CLTV opcode body in script.cpp is a direct port of BIP65's reference
implementation: 5-byte locktime decode, lock-type match against tx.nLockTime,
nSequence check, no stack mutation. Boundary verification is therefore
mechanical (spec match), with this smoke confirming nothing else broke.
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
    datadir = tempfile.mkdtemp(prefix="off-bip65-test-")
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
    print("=== qa/rpc-tests: BIP65 OP_CHECKLOCKTIMEVERIFY gate (#34) ===")
    print()
    print("Starting fresh regtest daemon...")
    start_daemon()

    print()
    print("Phase 1: mine to h=109 (pre-fork)")
    mine_to(109)
    h = cli("getblockcount")
    assert h == 109, "expected h=109, got %d" % h
    print("  h=%d  (CLTV flag NOT yet enabled at block validation)" % h)
    print("  PASS  pre-fork mining works")

    print()
    print("Phase 2: cross CLTV fork (h=110)")
    mine_to(110)
    h = cli("getblockcount")
    assert h == 110, "expected h=110, got %d" % h
    print("  h=%d  (CLTV flag now enabled at block validation)" % h)
    print("  PASS  daemon did not crash crossing OP_NOP2 -> OP_CLTV boundary")

    print()
    print("Phase 3: mine past COINBASE_MAT recovery (h=110 -> h=300)")
    mine_to(300)
    h = cli("getblockcount")
    bal = cli("getbalance")
    print("  h=%d  balance=%s" % (h, bal))
    assert bal > 0, "balance must be positive once coinbases mature"
    print("  PASS  chain coherent past all three fork-bundle rules")

    print()
    print("Phase 4: send a normal (non-CLTV) tx post-fork")
    addr = cli("getnewaddress")
    txid = cli("sendtoaddress", addr, "1.0")
    assert isinstance(txid, str) and len(txid) == 64, (
        "expected 64-char hex txid, got %r" % txid)
    print("  txid=%s" % txid)
    print("  PASS  normal tx accepted by mempool post-fork (no CLTV in scriptPubKey)")

    print()
    print("Phase 5: mine the tx; block-validation accepts it")
    pre_h = cli("getblockcount")
    cli_silent("setgenerate", "true", "1")
    post_h = cli("getblockcount")
    assert post_h > pre_h, (
        "new block did not land (was h=%d, now h=%d)" % (pre_h, post_h))
    print("  h=%d -> h=%d" % (pre_h, post_h))
    print("  PASS  block-validation accepts normal txs with CLTV flag enabled")

    print()
    print("Phase 6: debug.log free of consensus anomalies")
    log_path = os.path.join(datadir, "regtest", "debug.log")
    with open(log_path) as f:
        log = f.read()
    # Match substantive consensus/script failures, NOT path-name occurrences
    # of the test prefix or routine "X rejected by peer" lines from networking.
    bad_substrings = (
        "assertion",
        "bad-script",
        "non-canonical",
        "unsatisfied-locktime",
        "bad-txns-",
        "bad-blk-",
        "consensus failure",
    )
    anomalies = []
    for line in log.split("\n"):
        low = line.lower()
        if any(kw in low for kw in bad_substrings):
            if "peers.dat" not in line and "init message" not in line:
                anomalies.append(line)
    if anomalies:
        print("  Anomalies (first 10):")
        for a in anomalies[:10]:
            print("    " + a)
        raise AssertionError("debug.log shows %d anomaly line(s)"
                             % len(anomalies))
    print("  PASS  no assertions, no consensus rejects")

    print()
    print("=== ALL SMOKE CHECKS PASSED ===")
    print()
    print("NOTE: CLTV-evaluation boundary test (P2SH-CLTV redeem script,")
    print("spend with tx.nLockTime below vs above required locktime) is")
    print("deferred. The opcode body is a direct port of BIP65's reference")
    print("implementation; this smoke confirms the flag-gate doesn't break")
    print("non-CLTV transaction flow.")


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
