#!/usr/bin/env python3
"""
Boundary test for COINBASE_MATURITY 10 -> 240 height-gated rule (#32).

In regtest mode HARDFORK_COINBASE_MAT_REGTEST_OFF=110:
  h <  110: COINBASE_MATURITY = 10  (legacy)
  h >= 110: COINBASE_MATURITY = 240 (hardened)

The test starts a fresh regtest daemon, mines across the boundary, and
verifies the wallet's getbalance reflects the height-gated maturity rule.
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
    datadir = tempfile.mkdtemp(prefix="cbmat-rpctest-")
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
    """Mine until tip >= target_h. Uses regtest's setgenerate(True, N)
    mine-N-blocks-then-stop semantics."""
    while True:
        h = cli("getblockcount")
        if h >= target_h:
            return h
        n = min(50, target_h - h)
        cli_silent("setgenerate", "true", str(n))


def main():
    print("=== qa/rpc-tests: COINBASE_MATURITY 10 -> 240 boundary ===")
    print()
    print("Starting fresh regtest daemon...")
    start_daemon()

    print()
    print("Phase 1: mine to h=109 (pre-fork)")
    mine_to(109)
    h = cli("getblockcount")
    assert h == 109, "expected h=109, got %d" % h
    bal_pre = cli("getbalance")
    print("  h=%d  balance=%s" % (h, bal_pre))
    assert bal_pre > 0, ("pre-fork balance must be > 0 "
                        "(legacy=10 should mature coinbases at depth>=10)")
    print("  PASS  legacy maturity=10 in effect")

    print()
    print("Phase 2: mine to h=110 (fork activates)")
    mine_to(110)
    h = cli("getblockcount")
    assert h == 110, "expected h=110, got %d" % h
    bal_at_fork = cli("getbalance")
    print("  h=%d  balance=%s" % (h, bal_at_fork))
    assert bal_at_fork == 0, ("post-fork balance must be 0 "
                              "(hardened=240, no coinbase reaches depth 240)")
    print("  PASS  hardened maturity=240 in effect, balance dropped to 0")

    print()
    print("Phase 3: mine to h=240 (no coinbase at depth>=240 yet)")
    mine_to(240)
    h = cli("getblockcount")
    bal_at_240 = cli("getbalance")
    print("  h=%d  balance=%s" % (h, bal_at_240))
    assert bal_at_240 == 0, ("balance must still be 0 at h=240 "
                             "(coinbase from h=1 is at depth 239)")
    print("  PASS  boundary correctly held (depth 239 < 240)")

    print()
    print("Phase 4: mine to h=241 (coinbase from h=1 reaches depth 240)")
    mine_to(241)
    h = cli("getblockcount")
    bal_at_241 = cli("getbalance")
    print("  h=%d  balance=%s" % (h, bal_at_241))
    assert bal_at_241 > 0, ("balance must be > 0 once coinbase from h=1 "
                            "reaches depth 240")
    print("  PASS  recovery: maturity threshold met at depth 240")

    print()
    print("Phase 5: mine 100 more (h=341), balance should keep growing")
    mine_to(341)
    h = cli("getblockcount")
    bal_at_341 = cli("getbalance")
    print("  h=%d  balance=%s" % (h, bal_at_341))
    assert bal_at_341 > bal_at_241, ("balance must grow as more coinbases "
                                     "reach depth 240")
    print("  PASS  monotonic growth post-recovery")

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
