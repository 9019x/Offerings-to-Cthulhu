#!/usr/bin/env python3
"""
Adversarial boundary test for BIP66 strict-DER (#33).

Hand-builds a block via `submitblock` that contains a non-strict-DER
signature, bypassing the mempool's STRICTENC enforcement to exercise
block-validation's own strict-DER gate added by commit 3928065.

# Three phases

PHASE A — primitive self-test (sanity).
    Hand-build a fully valid block (just a coinbase) with merkle_root +
    block_header_serialize + Quark9 PoW + submitblock. Tip must advance.
    Proves the lib_script.py block primitives are correct end-to-end.

PHASE B — POST-FORK adversarial (the real test).
    At h >= 110 (post-fork), build a block with a non-strict-DER spend
    (excessive R-padding, the "R value excessively padded" rule in
    src/script.cpp::IsCanonicalSignature). submitblock; verify the tip
    does NOT advance and the daemon's debug.log shows the
    Non-canonical-signature rejection. This proves the DERSIG flag is
    wired into ConnectBlock and IsCanonicalSignature fires post-fork.

# Why there is no PHASE C (pre-fork accept)

The literal scenario "pre-fork: block-validation passes the bad sig"
cannot be exercised on this binary. Empirical finding:

    OFF v0.13.x links statically against OpenSSL 1.0.2u. That OpenSSL
    build's ECDSA_verify() is itself strict about DER encoding — every
    BIP66-violating munge we tested (excessive R-padding, excessive
    S-padding, multi-byte length encoding of any TLV, invalid hashtype)
    is rejected by ECDSA_verify BEFORE IsCanonicalSignature is consulted
    on the no-STRICTENC fallback path (main.cpp:1958 retry-without-
    STRICTENC).

    Concretely: at h < 110, ConnectBlock correctly omits DERSIG /
    STRICTENC from `flags`. IsCanonicalSignature short-circuits
    (returns true). CheckSig then calls pubkey.Verify -> ECDSA_verify,
    which rejects the malformed sig. Block rejected — but for the
    "wrong" reason. The patch under test (#33) is NOT exercised pre-fork
    because OpenSSL 1.0.2u is already strict enough.

    This is consistent with the historical BIP66 motivation: the bug
    existed because *some* OpenSSL builds on *some* platforms were
    permissive. On strict builds the gate is belt-and-suspenders.

    A "true" pre-fork accept could only be observed by linking the
    daemon against a permissive crypto backend, or by patching
    pubkey.Verify to skip ECDSA when DERSIG is unset. Neither is
    appropriate for a qa test of the consensus-rule wiring.

# What this test does prove

  1. The block-construction primitives (merkle_root, header,
     Quark9 PoW, block_serialize) are byte-correct against a live OFF
     daemon (Phase A).
  2. At h >= 110 (post-fork), the bad-sig block is rejected. The
     specific rejection reason in debug.log is the IsCanonicalSignature
     parser's "Non-canonical signature: R value excessively padded"
     — proving the DERSIG flag IS being set by the patched
     ConnectBlock branch at line main.cpp:2151-2153 (#33).
  3. The mempool sanity check (bonus): the same bad-sig tx is
     independently rejected by `sendrawtransaction` via mempool's
     long-standing STRICTENC enforcement.

Together with the existing smoke test dersig_block_validation.py, this
brings adversarial coverage to the BIP66 patch about as far as the
OpenSSL backend allows.

Self-contained: no dependency on qa/rpc-tests/util.py. Mirrors the
scaffolding pattern of cltv_boundary.py.
"""

import atexit
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
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

# Fork heights (mirror src/pow.h):
#   HARDFORK_DERSIG_REGTEST_OFF = 110
DERSIG_REGTEST_FORK = 110

datadir = None
daemon_proc = None


# =====================================================================
# CLI scaffolding (lifted directly from cltv_boundary.py)
# =====================================================================

def _cli_cmd(*args):
    return [CLI, "-regtest", "-datadir=" + datadir,
            "-rpcuser=" + RPCUSER, "-rpcpassword=" + RPCPASS,
            "-rpcport=" + str(RPCPORT)] + list(args)


def cli_raw(*args):
    r = subprocess.run(_cli_cmd(*args), capture_output=True)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or b"").decode().strip()
        raise RuntimeError("cli failed (rc=%d): %s\n  args=%r"
                           % (r.returncode, msg[:500], list(args)[:1]))
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
    subprocess.check_call(_cli_cmd(*args),
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)


def cli_try(*args):
    """Return (rc, output_string). Used when we expect a possible error."""
    r = subprocess.run(_cli_cmd(*args), capture_output=True)
    return r.returncode, (r.stdout or r.stderr).decode().strip()


def start_daemon():
    global datadir, daemon_proc
    datadir = tempfile.mkdtemp(prefix="off-bip66-bdy-")
    with open(os.path.join(datadir, "Offerings.conf"), "w") as f:
        f.write("regtest=1\n")
        f.write("rpcuser=%s\n" % RPCUSER)
        f.write("rpcpassword=%s\n" % RPCPASS)
        f.write("rpcport=%d\n" % RPCPORT)
        f.write("port=%d\n" % PORT)
        f.write("listen=0\n")
        f.write("server=1\n")
        f.write("checkpoints=0\n")
        # Need debug=1 to see "Non-canonical signature: ..." messages,
        # which is the evidence Phase B looks for.
        f.write("debug=1\n")
        f.write("keypool=20\n")
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


def tail_debug_log(n=200):
    log_path = os.path.join(datadir, "regtest", "debug.log")
    with open(log_path) as f:
        lines = f.readlines()
    return "".join(lines[-n:])


# =====================================================================
# Signature munging (BIP66 strict-DER violation construction)
# =====================================================================

def munge_excessive_R_padding(sig_with_hashtype):
    """Take a strict-DER sig (last byte is the SIGHASH_ALL byte) and
    inject an excessive 0x00 byte at the start of the R component.

    Strict-DER sig layout (per src/script.cpp::IsCanonicalSignature):

        30 [total_len] 02 [r_len] R... 02 [s_len] S... [hashtype]

    The "R value excessively padded" rule (line ~287) rejects when:
        nLenR > 1 AND R[0] == 0x00 AND !(R[1] & 0x80)

    The python-ecdsa sigencode_der_canonize already produces R values
    with the high bit of R[0] clear (else it would have added a sign
    byte itself), so our inserted 0x00 is guaranteed excessive.

    Returns the munged sig WITH the hashtype byte still appended.
    """
    if len(sig_with_hashtype) < 9:
        raise ValueError("sig too short to be DER: %d bytes" % len(sig_with_hashtype))
    sig = sig_with_hashtype[:-1]      # strip hashtype
    hashtype = sig_with_hashtype[-1:]

    if sig[0] != 0x30:
        raise ValueError("expected DER prefix 0x30, got 0x%02x" % sig[0])
    total_len = sig[1]
    if total_len + 2 != len(sig):
        raise ValueError("bad outer length marker: %d vs %d bytes"
                         % (total_len, len(sig) - 2))
    if sig[2] != 0x02:
        raise ValueError("expected R marker 0x02 at offset 2")
    r_len = sig[3]
    r_start = 4
    r_end = r_start + r_len
    R = sig[r_start:r_end]

    if R and (R[0] & 0x80):
        raise ValueError("R has high bit set; canonical encoder should have "
                         "added a sign byte already — we'd be making it valid")

    rest = sig[r_end:]  # S marker + S + (nothing more)
    if not rest or rest[0] != 0x02:
        raise ValueError("expected S marker 0x02 after R")

    # Build munged R: prepend 0x00
    new_R = b"\x00" + R
    new_r_len = r_len + 1
    if new_r_len > 0xff:
        raise ValueError("munged R too long for 1-byte length marker")

    new_inner = bytes([0x02, new_r_len]) + new_R + rest
    new_total_len = len(new_inner)
    if new_total_len > 0xff:
        raise ValueError("munged sig too long for 1-byte outer length marker")
    munged = bytes([0x30, new_total_len]) + new_inner + hashtype

    if not (9 <= len(munged) <= 73):
        raise ValueError("munged sig out of bounds: %d bytes" % len(munged))
    return munged


def extract_sig_and_pubkey_from_p2pkh_scriptsig(script_sig):
    """A P2PKH scriptSig is `<sig> <pubkey>`. Parse them out.
    Each item is a single direct push (opcode = length byte)."""
    pos = 0
    sig_len = script_sig[pos]
    if not (1 <= sig_len <= 0x4b):
        raise ValueError("first push opcode 0x%02x outside direct-push range"
                         % sig_len)
    pos += 1
    sig = script_sig[pos:pos + sig_len]
    pos += sig_len
    pk_len = script_sig[pos]
    if not (1 <= pk_len <= 0x4b):
        raise ValueError("second push opcode 0x%02x outside direct-push range"
                         % pk_len)
    pos += 1
    pubkey = script_sig[pos:pos + pk_len]
    pos += pk_len
    if pos != len(script_sig):
        raise ValueError("trailing %d bytes in scriptSig"
                         % (len(script_sig) - pos))
    return sig, pubkey


def repack_scriptsig(sig, pubkey):
    """Build P2PKH scriptSig: <push sig> <push pubkey>."""
    return scr.encode_pushdata(sig) + scr.encode_pushdata(pubkey)


# =====================================================================
# Building a bad-sig spending tx
# =====================================================================

def build_bad_sig_tx(funding_txid, vout, value_sat, dest_addr):
    """Use the wallet to create a normal signed P2PKH spend, then munge
    the sig in the assembled tx bytes.

    Returns (raw_tx_hex, bad_sig_txid_hex_display_order).
    """
    fee_sat = 100
    out_sat = value_sat - fee_sat
    inputs = [{"txid": funding_txid, "vout": vout}]
    outputs = {dest_addr: round(out_sat / scr.COIN, 5)}
    raw_unsigned = cli_raw(
        "createrawtransaction", json.dumps(inputs), json.dumps(outputs))
    signed = cli_json("signrawtransaction", raw_unsigned)
    if not signed.get("complete", False):
        raise RuntimeError("signrawtransaction not complete: %r" % signed)
    signed_hex = signed["hex"]

    dec = cli_json("decoderawtransaction", signed_hex)
    if len(dec["vin"]) != 1:
        raise RuntimeError("expected 1 input, got %d" % len(dec["vin"]))
    orig_script_sig = bytes.fromhex(dec["vin"][0]["scriptSig"]["hex"])
    orig_sig, pubkey = extract_sig_and_pubkey_from_p2pkh_scriptsig(orig_script_sig)
    bad_sig = munge_excessive_R_padding(orig_sig)
    bad_script_sig = repack_scriptsig(bad_sig, pubkey)

    # Re-serialize the tx with the new scriptSig
    tx_bytes = bytes.fromhex(signed_hex)
    pos = 4
    vin_count = tx_bytes[pos]; pos += 1
    assert vin_count == 1
    prevout_bytes = tx_bytes[pos:pos + 36]; pos += 36
    orig_ss_len = tx_bytes[pos]; pos += 1
    assert orig_ss_len == len(orig_script_sig)
    pos += orig_ss_len
    sequence = struct.unpack("<I", tx_bytes[pos:pos + 4])[0]
    pos += 4
    vout_count = tx_bytes[pos]; pos += 1
    outputs_raw = []
    for _ in range(vout_count):
        value = struct.unpack("<Q", tx_bytes[pos:pos + 8])[0]
        pos += 8
        spk_len = tx_bytes[pos]; pos += 1
        spk = tx_bytes[pos:pos + spk_len]; pos += spk_len
        outputs_raw.append(scr.serialize_output(value, spk))
    locktime = struct.unpack("<I", tx_bytes[pos:pos + 4])[0]
    pos += 4
    assert pos == len(tx_bytes)

    new_input = scr.serialize_input(prevout_bytes, bad_script_sig, sequence)
    new_tx = scr.serialize_tx(1, [new_input], outputs_raw, locktime)
    txid_display = scr.tx_hash(new_tx)[::-1].hex()
    return new_tx.hex(), txid_display


# =====================================================================
# Block construction
# =====================================================================

def build_coinbase_tx(nHeight, value_sat, dest_addr, extra_nonce=0):
    """Build a minimal valid coinbase tx.

    scriptSig is 2..100 bytes per CheckTransaction's coinbase bounds.
    Format: <push height> <push extra-nonce> <push "/QA-DERSIG/">.
    """
    cb_script = (scr.encode_pushint(nHeight)
                 + scr.encode_pushint(extra_nonce)
                 + scr.encode_pushdata(b"/QA-DERSIG/"))
    if not (2 <= len(cb_script) <= 100):
        raise RuntimeError("coinbase script len %d out of [2,100]"
                           % len(cb_script))
    null_prevout = b"\x00" * 32 + (0xffffffff).to_bytes(4, 'little')
    cb_input = scr.serialize_input(null_prevout, cb_script, 0xffffffff)
    dest_spk = scr.address_to_p2pkh_script(dest_addr)
    cb_output = scr.serialize_output(value_sat, dest_spk)
    return scr.serialize_tx(1, [cb_input], [cb_output], 0)


def construct_block(version, prev_hash_display, txs, time, bits):
    """Build a complete block bytes blob.

    prev_hash_display is the display-order hex string from getblockhash.
    txs is a list of raw tx bytes; txs[0] must be the coinbase.
    """
    prev_le = bytes.fromhex(prev_hash_display)[::-1]
    tx_hashes_le = [scr.tx_hash(t) for t in txs]
    mr = scr.merkle_root(tx_hashes_le)
    nonce, header = scr.mine_block_header(
        version, prev_le, mr, time, bits, start_nonce=0)
    return scr.block_serialize(header, txs), nonce


def submit_block(block_bytes):
    """submitblock returns null on accept, a string reason on reject.
    But because of the SUBMITBLOCK_NULL_QUIRK below, we ALSO check the
    chain tip to determine actual acceptance.

    SUBMITBLOCK_NULL_QUIRK: src/rpcmining.cpp::submitblock returns
    Value::null when ProcessBlock returns true. ProcessBlock can return
    true (block accepted into block index) even when ConnectBlock later
    rejects the block during ActivateBestChain. So "submitblock returned
    null" is NECESSARY but not SUFFICIENT for acceptance. The
    authoritative check is whether the chain tip advanced.
    """
    tip_before = cli_raw("getbestblockhash")
    rc, out = cli_try("submitblock", block_bytes.hex())
    tip_after = cli_raw("getbestblockhash")
    advanced = tip_before != tip_after
    return rc, out, advanced, tip_after


# =====================================================================
# Test orchestration
# =====================================================================

def fund_p2pkh_utxo():
    """Send 10 OFF to a fresh wallet address, mine one block to confirm,
    return (funding_txid, vout, value_sat, dest_addr)."""
    addr = cli_raw("getnewaddress")
    funding_txid = cli_raw("sendtoaddress", addr, "10.0")
    cli_silent("setgenerate", "true", "1")
    rawtx = cli_json("getrawtransaction", funding_txid, "1")
    target_spk_hex = scr.address_to_p2pkh_script(addr).hex()
    for v in rawtx["vout"]:
        if v["scriptPubKey"]["hex"] == target_spk_hex:
            vout = v["n"]
            value_sat = int(Decimal(str(v["value"])) * Decimal(scr.COIN))
            return funding_txid, vout, value_sat, addr
    raise RuntimeError("P2PKH output not found in funding tx")


# =====================================================================
# Phase A: primitive self-test
# =====================================================================

def phase_A_hand_build_valid_block():
    """Hand-build a valid coinbase-only block via lib_script primitives,
    submitblock it, verify the tip advances. Proves the primitives are
    correct end-to-end (merkle root, block header, Quark9 PoW)."""
    print()
    print("Phase A: hand-build a VALID coinbase-only block via lib_script")
    print("         primitives — submitblock; tip must advance.")
    tip_hash = cli_raw("getbestblockhash")
    tip_header = cli_json("getblock", tip_hash, "true")
    new_height = tip_header["height"] + 1
    cb_dest = cli_raw("getnewaddress")
    cb_value = 5 * scr.COIN  # nBlockRewardStartCoin (early-height subsidy)
    coinbase = build_coinbase_tx(new_height, cb_value, cb_dest,
                                 extra_nonce=new_height)
    block_time = max(int(time.time()), tip_header["time"] + 1)
    bits = int(tip_header["bits"], 16)
    block_bytes, nonce = construct_block(
        tip_header["version"], tip_hash, [coinbase], block_time, bits)
    print("  built block:     h=%d nonce=%d bits=%08x size=%d"
          % (new_height, nonce, bits, len(block_bytes)))
    rc, out, advanced, new_tip = submit_block(block_bytes)
    print("  submitblock:     rc=%d out=%r advanced=%s" % (rc, out, advanced))
    if not advanced:
        raise AssertionError(
            "Phase A: hand-built VALID block was REJECTED. "
            "submitblock said: %s\n--- recent debug.log ---\n%s"
            % (out, tail_debug_log(50)))
    print("  PASS  tip advanced to h=%d (hand-built primitives are correct)"
          % cli("getblockcount"))


# =====================================================================
# Phase B: post-fork bad-sig adversarial
# =====================================================================

def phase_B_bad_sig_postfork():
    """Build a block with a non-strict-DER spend post-fork. Tip must NOT
    advance, and debug.log must show 'Non-canonical signature' — proving
    the patched ConnectBlock at main.cpp:2151-2153 sets DERSIG, and the
    existing IsCanonicalSignature parser rejects the sig at the
    block-validation gate."""
    print()
    print("Phase B: POST-FORK — block with excessive-R-padding sig must")
    print("         be rejected; debug.log must show the BIP66 parser fire.")
    h = cli("getblockcount")
    if h < DERSIG_REGTEST_FORK:
        raise RuntimeError("Phase B requires h>=%d; tip is h=%d"
                           % (DERSIG_REGTEST_FORK, h))
    print("  h=%d  (post-fork, h>=%d)" % (h, DERSIG_REGTEST_FORK))

    # 1. Fund a P2PKH UTXO and build the bad-sig spending tx
    funding_txid, vout, value_sat, _src_addr = fund_p2pkh_utxo()
    print("  funded P2PKH:    %s...:%d  value=%d sat"
          % (funding_txid[:16], vout, value_sat))

    dest_addr = cli_raw("getnewaddress")
    bad_tx_hex, bad_txid = build_bad_sig_tx(
        funding_txid, vout, value_sat, dest_addr)
    print("  bad-sig tx:      %s...  (excessive R-padding)" % bad_txid[:16])

    # 2. Mempool sanity: STRICTENC ALWAYS enforced at mempool (pre OR post
    # fork). Confirms the munge is recognizable as non-strict-DER.
    rc, out = cli_try("sendrawtransaction", bad_tx_hex)
    if rc == 0:
        raise AssertionError(
            "munged tx accepted by mempool — STRICTENC not enforced?\n"
            "  output: %s" % out)
    print("  mempool sanity:  REJECTED — STRICTENC enforced at mempool")

    # 3. Capture debug.log size BEFORE submitting, so we can scan only
    # new lines after.
    log_path = os.path.join(datadir, "regtest", "debug.log")
    log_size_before = os.path.getsize(log_path)

    # 4. Build the block
    tip_hash = cli_raw("getbestblockhash")
    tip_header = cli_json("getblock", tip_hash, "true")
    new_height = tip_header["height"] + 1
    cb_dest = cli_raw("getnewaddress")
    cb_value = 5 * scr.COIN
    coinbase = build_coinbase_tx(new_height, cb_value, cb_dest,
                                 extra_nonce=new_height)
    block_time = max(int(time.time()), tip_header["time"] + 1)
    bits = int(tip_header["bits"], 16)
    bad_tx_bytes = bytes.fromhex(bad_tx_hex)
    block_bytes, nonce = construct_block(
        tip_header["version"], tip_hash,
        [coinbase, bad_tx_bytes], block_time, bits)
    print("  built block:     h=%d nonce=%d bits=%08x size=%d"
          % (new_height, nonce, bits, len(block_bytes)))

    # 5. submitblock
    rc, out, advanced, new_tip = submit_block(block_bytes)
    print("  submitblock:     rc=%d out=%r advanced=%s" % (rc, out, advanced))

    if advanced:
        raise AssertionError(
            "Phase B: post-fork bad-sig block was ACCEPTED — DERSIG gate "
            "FAILED. submitblock=%r tip=%s\n--- recent log ---\n%s"
            % (out, new_tip, tail_debug_log(50)))

    # 6. Check the new debug.log lines for the specific BIP66 parser
    # rejection. This proves IsCanonicalSignature fired — i.e. the
    # DERSIG flag IS being set by ConnectBlock at the fork.
    with open(log_path) as f:
        f.seek(log_size_before)
        new_log = f.read()

    canonical_lines = [
        L for L in new_log.split("\n")
        if "Non-canonical signature" in L]
    if not canonical_lines:
        raise AssertionError(
            "Phase B: block was rejected, but debug.log does NOT contain a "
            "'Non-canonical signature' line — the rejection came from a "
            "different code path. Patch may be ineffective on this build.\n"
            "--- new log lines ---\n%s" % new_log[:3000])
    # Specifically check for our munge variety
    if not any("R value excessively padded" in L for L in canonical_lines):
        print("  WARN  rejected with a Non-canonical reason, but not the")
        print("        specific 'R value excessively padded' we crafted:")
        for L in canonical_lines[:3]:
            print("          " + L.strip())
    else:
        print("  evidence: debug.log shows IsCanonicalSignature fire")
        for L in canonical_lines[:3]:
            print("          " + L.strip())

    print("  PASS  block rejected; BIP66 parser triggered at block-validation")


def main():
    print("=== BIP66 DERSIG adversarial boundary (#33) ===")
    print()
    print("Starting fresh regtest daemon...")
    start_daemon()

    mine_to(20)

    # ---- Phase A: primitive self-test ----
    phase_A_hand_build_valid_block()

    # ---- Phase B: post-fork adversarial ----
    # Need to be PAST h=110 (DERSIG fork) AND past h=350 so that mature
    # coinbases under the hardened maturity=240 (#32) exist for spending.
    mine_to(350)
    phase_B_bad_sig_postfork()

    print()
    print("=== BIP66 DERSIG ADVERSARIAL CHECKS PASSED ===")
    print()
    print("Phase A proved the block-construction primitives in lib_script.py")
    print("(merkle_root, block_header_serialize, quark9_hash, block_serialize)")
    print("agree byte-for-byte with what the OFF daemon accepts.")
    print()
    print("Phase B proved the patched ConnectBlock (commit 3928065, #33)")
    print("DOES set SCRIPT_VERIFY_DERSIG at h>=%d on regtest, and that the"
          % DERSIG_REGTEST_FORK)
    print("existing IsCanonicalSignature parser catches the munged sig at")
    print("block-validation — the smuggle-through-submitblock path is closed.")
    print()
    print("Limitation (documented in the test header): on this OFF build")
    print("(OpenSSL 1.0.2u, strict-ASN.1), ECDSA_verify is already strict")
    print("enough to reject our munges, so a 'pre-fork accept' phase cannot")
    print("be observed. The BIP66 gate is belt-and-suspenders here, against")
    print("future OpenSSL changes or build-host variations.")


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
