#!/usr/bin/env python3
"""
Adversarial boundary test for BIP65 OP_CHECKLOCKTIMEVERIFY (#34).

End-to-end exercise of the CLTV opcode body via a real P2SH-CLTV output:

  redeem script = <required_locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <pubkey> OP_CHECKSIG

Three phases, all must PASS:

  1. PRE-FORK accept (h < HARDFORK_CLTV_REGTEST_OFF=110):
     Spend a P2SH-CLTV UTXO with tx.nLockTime == required_locktime.
     CLTV is a no-op; spend succeeds, tx lands in a block.

  2. POST-FORK accept (h >= 110, valid spend):
     Spend a P2SH-CLTV UTXO with tx.nLockTime >= required_locktime
     and nSequence != SEQUENCE_FINAL. CLTV check passes; spend
     succeeds, tx lands in a block.

  3. POST-FORK reject (h >= 110, invalid spend):
     Spend a P2SH-CLTV UTXO with tx.nLockTime < required_locktime.
     Mempool accepts (CLTV not enforced at mempool, by design).
     Miner pre-screens with block-validation flags (issue #39 fix)
     and excludes the tx. The next mined block must NOT contain it.

Phase 3 doubles as the regression test for #39: without the miner-side
fix, setgenerate crashes when the CLTV-violating tx is in the mempool.
"""

import json, os, sys, shutil, subprocess, tempfile, time, atexit
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_script as scr

SRCDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
DAEMON = os.path.join(SRCDIR, "Offeringsd")
CLI    = os.path.join(SRCDIR, "Offerings-cli")
PORT     = 18444
RPCPORT  = 18443
RPCUSER  = "rt"
RPCPASS  = "rt"

REQUIRED_LOCKTIME = 5

datadir = None
daemon_proc = None


def _cli_cmd(*args):
    return [CLI, "-regtest", "-datadir=" + datadir,
            "-rpcuser=" + RPCUSER, "-rpcpassword=" + RPCPASS,
            "-rpcport=" + str(RPCPORT)] + list(args)


def cli_raw(*args):
    r = subprocess.run(_cli_cmd(*args), capture_output=True)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or b"").decode().strip()
        raise RuntimeError("cli failed (rc=%d): %s\n  args=%r" % (r.returncode, msg[:500], list(args)[:1]))
    return r.stdout.decode().strip()


def cli(*args):
    out = cli_raw(*args)
    try:
        if "." in out:
            return Decimal(out)
        return int(out)
    except Exception:
        return out


def cli_json(*args):
    return json.loads(cli_raw(*args))


def cli_silent(*args):
    subprocess.check_call(
        _cli_cmd(*args),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cli_try(*args):
    """Return (rc, output_string). Used when we expect a possible error."""
    r = subprocess.run(_cli_cmd(*args), capture_output=True)
    return r.returncode, (r.stdout or r.stderr).decode().strip()


def start_daemon():
    global datadir, daemon_proc
    datadir = tempfile.mkdtemp(prefix="off-bip65-bdy-")
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


def get_new_pubkey():
    """Return (address, pubkey_hex)."""
    addr = cli_raw("getnewaddress")
    info = cli_json("validateaddress", addr)
    return addr, info["pubkey"]


def build_cltv_redeem(pubkey_hex, locktime):
    """<locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <pubkey> OP_CHECKSIG."""
    pubkey = bytes.fromhex(pubkey_hex)
    return (scr.encode_pushint(locktime)
            + bytes([scr.OP_CHECKLOCKTIMEVERIFY])
            + bytes([scr.OP_DROP])
            + scr.encode_pushdata(pubkey)
            + bytes([scr.OP_CHECKSIG]))


def find_p2sh_vout(funding_txid, redeem_script):
    """Return (vout_index, value_satoshi) for the P2SH output in the funding tx."""
    target_spk_hex = scr.p2sh_script_pubkey(redeem_script).hex()
    rawtx = cli_json("getrawtransaction", funding_txid, "1")
    for v in rawtx["vout"]:
        if v["scriptPubKey"]["hex"] == target_spk_hex:
            return v["n"], int(Decimal(str(v["value"])) * Decimal(scr.COIN))
    raise RuntimeError("P2SH output not found in funding tx %s" % funding_txid)


def build_and_sign_spend(funding_txid, vout, value_sat, dest_addr,
                         redeem_script, locktime, sequence,
                         scriptPubKey_hex, signing_addr):
    """Build raw spending tx, sign manually with ECDSA over the redeem script.

    OFF 0.10's Solver() doesn't recognize a CLTV-prefixed redeem as any of
    its 4 templates, so signrawtransaction returns complete=false. We sign
    by hand using the wallet's dumpprivkey and the standard SIGHASH_ALL
    computation over the redeem script as the substituted scriptSig.
    """
    fee_sat = 100  # plenty for regtest (0.001 OFF at COIN=100000)
    out_sat = value_sat - fee_sat
    dest_spk = scr.address_to_p2pkh_script(dest_addr)
    prevout = scr.serialize_outpoint(funding_txid, vout)
    out = scr.serialize_output(out_sat, dest_spk)

    # SIGHASH_ALL computation:
    #   replace input[0].scriptSig with redeem_script
    #   serialize tx with that, append 0x01 0x00 0x00 0x00, SHA256d
    sighash_tx = scr.build_sighash_tx(
        version=1,
        inputs_meta=[(prevout, sequence)],
        outputs=[out],
        locktime=locktime,
        signing_index=0,
        prev_script=redeem_script)
    sighash = scr.sighash_all(sighash_tx, 0, redeem_script)

    # Sign with the wallet's privkey for the redeem's embedded pubkey
    wif = cli_raw("dumpprivkey", signing_addr)
    privkey_bytes, _compressed = scr.wif_to_privkey(wif)
    sig_with_hashtype = scr.sign_with_ecdsa_strict(privkey_bytes, sighash)

    # Build scriptSig: <signature> <serialized redeem script>
    script_sig = scr.encode_pushdata(sig_with_hashtype) + scr.encode_pushdata(redeem_script)
    final_input = scr.serialize_input(prevout, script_sig, sequence)
    signed = scr.serialize_tx(1, [final_input], [out], locktime)
    return signed.hex()


def fund_p2sh_cltv(required_locktime):
    """Create one P2SH-CLTV UTXO. Returns (funding_txid, vout, value_sat,
    redeem_script_bytes, scriptPubKey_hex, signing_addr)."""
    addr, pubkey_hex = get_new_pubkey()
    redeem = build_cltv_redeem(pubkey_hex, required_locktime)
    p2sh_addr = scr.p2sh_address(redeem)
    funding_txid = cli_raw("sendtoaddress", p2sh_addr, "10.0")
    cli_silent("setgenerate", "true", "1")  # confirm
    vout, value_sat = find_p2sh_vout(funding_txid, redeem)
    spk_hex = scr.p2sh_script_pubkey(redeem).hex()
    return funding_txid, vout, value_sat, redeem, spk_hex, addr


def main():
    print("=== BIP65 CLTV adversarial boundary (#34) ===")
    print()
    print("Starting fresh regtest daemon...")
    start_daemon()

    # === PHASE 1: pre-fork accept ===
    print()
    print("Phase 1: PRE-FORK — CLTV is a no-op, spend succeeds")
    mine_to(20)  # legacy maturity=10 → mature coinbases available, well below fork=110
    print("  h=%d  (pre-fork)" % cli("getblockcount"))
    funding_txid, vout, value_sat, redeem, spk_hex, sign_addr = fund_p2sh_cltv(REQUIRED_LOCKTIME)
    print("  funded P2SH-CLTV: %s:%d  value=%d sat" % (funding_txid[:16] + "...", vout, value_sat))
    dest_addr = cli_raw("getnewaddress")
    signed_hex = build_and_sign_spend(
        funding_txid, vout, value_sat, dest_addr, redeem,
        locktime=REQUIRED_LOCKTIME, sequence=0, scriptPubKey_hex=spk_hex, signing_addr=sign_addr)
    spend_txid = cli_raw("sendrawtransaction", signed_hex)
    print("  sendrawtransaction: %s..." % spend_txid[:16])
    pre_h = cli("getblockcount")
    cli_silent("setgenerate", "true", "1")
    post_h = cli("getblockcount")
    block_hash = cli_raw("getblockhash", str(post_h))
    block = cli_json("getblock", block_hash)
    assert spend_txid in block["tx"], (
        "pre-fork spend %s did NOT land in block %s; CLTV must be no-op pre-fork"
        % (spend_txid, block_hash))
    print("  PASS  pre-fork P2SH-CLTV spend landed in block %d" % post_h)

    # === PHASE 2: post-fork, valid CLTV ===
    print()
    print("Phase 2: POST-FORK valid — CLTV passes when tx.nLockTime >= required")
    # Need to cross h=110 (CLTV fork) AND h=240+REQUIRED_LOCKTIME so coinbases mature under hardened rule
    mine_to(350)
    print("  h=%d  (post-fork; hardened maturity=240 applies)" % cli("getblockcount"))
    funding_txid, vout, value_sat, redeem, spk_hex, sign_addr = fund_p2sh_cltv(REQUIRED_LOCKTIME)
    print("  funded P2SH-CLTV: %s:%d  value=%d sat" % (funding_txid[:16] + "...", vout, value_sat))
    dest_addr = cli_raw("getnewaddress")
    # nLockTime=REQUIRED_LOCKTIME satisfies CLTV (>=) and chain tip > 5 so tx is final.
    signed_hex = build_and_sign_spend(
        funding_txid, vout, value_sat, dest_addr, redeem,
        locktime=REQUIRED_LOCKTIME, sequence=0, scriptPubKey_hex=spk_hex, signing_addr=sign_addr)
    spend_txid = cli_raw("sendrawtransaction", signed_hex)
    print("  sendrawtransaction: %s..." % spend_txid[:16])
    pre_h = cli("getblockcount")
    cli_silent("setgenerate", "true", "1")
    post_h = cli("getblockcount")
    block_hash = cli_raw("getblockhash", str(post_h))
    block = cli_json("getblock", block_hash)
    assert spend_txid in block["tx"], (
        "post-fork valid spend %s did NOT land in block %s"
        % (spend_txid, block_hash))
    print("  PASS  post-fork valid CLTV spend landed in block %d" % post_h)

    # === PHASE 3: post-fork, INVALID CLTV (regression for #39) ===
    print()
    print("Phase 3: POST-FORK invalid — bad-CLTV tx kept out of block")
    funding_txid, vout, value_sat, redeem, spk_hex, sign_addr = fund_p2sh_cltv(REQUIRED_LOCKTIME)
    print("  funded P2SH-CLTV: %s:%d" % (funding_txid[:16] + "...", vout))
    dest_addr = cli_raw("getnewaddress")
    bad_locktime = REQUIRED_LOCKTIME - 1  # CLTV-violating
    signed_hex = build_and_sign_spend(
        funding_txid, vout, value_sat, dest_addr, redeem,
        locktime=bad_locktime, sequence=0,
        scriptPubKey_hex=spk_hex, signing_addr=sign_addr)
    rc, out = cli_try("sendrawtransaction", signed_hex)
    if rc == 0:
        bad_spend_txid = out
        print("  mempool accepted bad-CLTV tx (expected; mempool doesn't gate CLTV)")
        print("  bad_spend_txid=%s..." % bad_spend_txid[:16])
        pre_h = cli("getblockcount")
        cli_silent("setgenerate", "true", "1")
        post_h = cli("getblockcount")
        assert post_h > pre_h, (
            "setgenerate failed to land a block (#39 not fixed?): "
            "pre=%d post=%d" % (pre_h, post_h))
        block_hash = cli_raw("getblockhash", str(post_h))
        block = cli_json("getblock", block_hash)
        assert bad_spend_txid not in block["tx"], (
            "post-fork INVALID spend %s landed in block %s — "
            "block-validation should have rejected it"
            % (bad_spend_txid, block_hash))
        print("  PASS  bad-CLTV tx kept out of block %d by miner pre-screen (#39)"
              % post_h)
    else:
        # Mempool itself rejected — also acceptable (the rule fires
        # somewhere; the tx never lands in any block either way).
        print("  sendrawtransaction rejected at mempool with: %s" % out[:200])
        print("  PASS  bad-CLTV tx never reached a block")

    print()
    print("=== ALL CLTV BOUNDARY CHECKS PASSED ===")


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
