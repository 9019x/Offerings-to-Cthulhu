"""
Minimal Bitcoin Script primitives for OFF qa tests.

Just enough to:
  - Build redeem scripts byte-by-byte
  - Compute P2SH addresses
  - Round-trip integers as stack push opcodes

Avoids any external dependency. Pure stdlib (hashlib, struct).

Network parameters baked for OFF regtest. If used outside regtest,
pass the right version byte explicitly to p2sh_address().
"""

import hashlib

# Opcodes (subset we actually use)
OP_0 = 0x00
OP_PUSHDATA1 = 0x4c
OP_PUSHDATA2 = 0x4d
OP_PUSHDATA4 = 0x4e
OP_1NEGATE = 0x4f
OP_1 = 0x51
OP_16 = 0x60
OP_NOP = 0x61
OP_NOP2 = 0xb1
OP_CHECKLOCKTIMEVERIFY = OP_NOP2  # BIP65 alias
OP_DROP = 0x75
OP_DUP = 0x76
OP_HASH160 = 0xa9
OP_EQUAL = 0x87
OP_EQUALVERIFY = 0x88
OP_CHECKSIG = 0xac

# OFF regtest base58 script-address prefix (inherited from CTestNetParams)
OFF_REGTEST_P2SH_VERSION = 199
# OFF base units per OFF (src/util.h:38 -- NOT Bitcoin's 1e8)
COIN = 100000


def encode_pushint(n):
    """Encode integer n as a stack push.

    Uses single-opcode shortcuts (OP_0, OP_1NEGATE, OP_1..OP_16) when
    possible; otherwise pushes a signed little-endian byte representation
    using bitcoin's sign-magnitude convention.
    """
    if n == 0:
        return bytes([OP_0])
    if n == -1:
        return bytes([OP_1NEGATE])
    if 1 <= n <= 16:
        return bytes([OP_1 + n - 1])
    neg = n < 0
    n = -n if neg else n
    blob = b""
    while n:
        blob += bytes([n & 0xff])
        n >>= 8
    # Sign convention: top bit of MSB indicates sign. If the encoded
    # value's MSB top bit is already set, we need an extra sign byte.
    if blob[-1] & 0x80:
        blob += bytes([0x80 if neg else 0x00])
    elif neg:
        blob = blob[:-1] + bytes([blob[-1] | 0x80])
    return encode_pushdata(blob)


def encode_pushdata(data):
    """Encode push of raw bytes onto the stack."""
    l = len(data)
    if l < OP_PUSHDATA1:
        return bytes([l]) + data
    elif l <= 0xff:
        return bytes([OP_PUSHDATA1, l]) + data
    elif l <= 0xffff:
        return bytes([OP_PUSHDATA2, l & 0xff, (l >> 8) & 0xff]) + data
    else:
        return bytes([OP_PUSHDATA4]) + l.to_bytes(4, 'little') + data


def _ripemd160(data):
    """RIPEMD160 with OpenSSL-3 legacy-provider fallback.

    Ubuntu 22.04+ ships OpenSSL 3 which moves RIPEMD160 to the legacy
    provider, breaking `hashlib.new('ripemd160')`. Try hashlib first;
    fall back to `openssl dgst -ripemd160 -provider legacy`.
    """
    try:
        r = hashlib.new('ripemd160')
        r.update(data)
        return r.digest()
    except (ValueError, Exception):
        import subprocess
        r = subprocess.run(
            ["openssl", "dgst", "-ripemd160", "-provider", "legacy", "-binary"],
            input=data, capture_output=True, check=True)
        return r.stdout


def hash160(data):
    """RIPEMD160(SHA256(data)) — same as Bitcoin's Hash160."""
    return _ripemd160(hashlib.sha256(data).digest())


def double_sha256(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


# Base58Check encoding
_B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_encode(data):
    n = int.from_bytes(data, 'big')
    out = bytearray()
    while n > 0:
        n, r = divmod(n, 58)
        out.insert(0, _B58_ALPHABET[r])
    for b in data:
        if b == 0:
            out.insert(0, _B58_ALPHABET[0])
        else:
            break
    return out.decode()


def base58_check_encode(version_byte, payload):
    raw = bytes([version_byte]) + payload
    checksum = double_sha256(raw)[:4]
    return _base58_encode(raw + checksum)


def _base58_decode(s):
    n = 0
    for c in s.encode():
        n = n * 58 + _B58_ALPHABET.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, 'big') if n else b""
    leading = 0
    for c in s:
        if c == _B58_ALPHABET[0:1].decode():
            leading += 1
        else:
            break
    return b'\x00' * leading + raw


def base58_check_decode(s):
    """Returns (version_byte, payload). Raises on bad checksum."""
    raw = _base58_decode(s)
    if len(raw) < 5:
        raise ValueError("base58check decoded too short")
    payload, checksum = raw[:-4], raw[-4:]
    if double_sha256(payload)[:4] != checksum:
        raise ValueError("base58check bad checksum")
    return payload[0], payload[1:]


def address_to_p2pkh_script(addr):
    """OFF P2PKH address -> OP_DUP OP_HASH160 <hash160> OP_EQUALVERIFY OP_CHECKSIG."""
    _, h160 = base58_check_decode(addr)
    if len(h160) != 20:
        raise ValueError("expected 20-byte hash160")
    return bytes([OP_DUP, OP_HASH160, 20]) + h160 + bytes([OP_EQUALVERIFY, OP_CHECKSIG])


# Manual signing for P2SH inputs whose redeem script doesn't match any of
# OFF 0.10's Solver() templates (TX_PUBKEY / TX_PUBKEYHASH / TX_MULTISIG /
# TX_NULL_DATA). signrawtransaction would silently return complete=false
# for those; we sign by hand.

def wif_to_privkey(wif_str):
    """Decode WIF -> (32-byte raw private key, compressed_pubkey: bool)."""
    _, payload = base58_check_decode(wif_str)
    if len(payload) == 33 and payload[-1] == 0x01:
        return payload[:32], True
    elif len(payload) == 32:
        return payload, False
    else:
        raise ValueError("unexpected WIF payload length: %d" % len(payload))


def sighash_all(tx_bytes_unsigned, input_index, prev_script_being_signed):
    """Compute SIGHASH_ALL hash for input_index.

    `tx_bytes_unsigned` must be the tx with ALL input scriptSigs empty and
    `prev_script_being_signed` substituted for input_index's scriptSig.
    Caller assembles that tx; this helper just appends the sighash bytes
    and SHA256d's.
    """
    return double_sha256(tx_bytes_unsigned + b"\x01\x00\x00\x00")


def build_sighash_tx(version, inputs_meta, outputs, locktime, signing_index, prev_script):
    """Build the tx-bytes used as input to SIGHASH_ALL computation.

    inputs_meta = [(prevout_bytes, sequence), ...] for each input.
    For input_index == signing_index, scriptSig = prev_script (the redeem
    script for P2SH). For all other inputs, scriptSig = empty.
    """
    serialized_inputs = []
    for i, (prevout_bytes, seq) in enumerate(inputs_meta):
        script_sig = prev_script if i == signing_index else b""
        serialized_inputs.append(serialize_input(prevout_bytes, script_sig, seq))
    return serialize_tx(version, serialized_inputs, outputs, locktime)


def sign_with_ecdsa_strict(privkey_bytes, sighash):
    """Sign a 32-byte hash with secp256k1, return strict-DER+low-S signature
    with SIGHASH_ALL byte appended (ready to push as scriptSig).
    """
    # Imported lazily so lib_script doesn't hard-require the ecdsa pkg.
    import ecdsa
    sk = ecdsa.SigningKey.from_string(privkey_bytes, curve=ecdsa.SECP256k1)
    der = sk.sign_digest(sighash,
                         sigencode=ecdsa.util.sigencode_der_canonize)
    return der + b"\x01"  # SIGHASH_ALL


def p2sh_address(redeem_script, version_byte=OFF_REGTEST_P2SH_VERSION):
    """Base58Check P2SH address for a given redeem script."""
    return base58_check_encode(version_byte, hash160(redeem_script))


def p2sh_script_pubkey(redeem_script):
    """OP_HASH160 <hash160(redeem)> OP_EQUAL."""
    h = hash160(redeem_script)
    return bytes([OP_HASH160, len(h)]) + h + bytes([OP_EQUAL])


# Raw-tx serialization helpers (just enough for spending a single P2SH input)

def _varint(n):
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return b"\xfd" + n.to_bytes(2, 'little')
    elif n <= 0xffffffff:
        return b"\xfe" + n.to_bytes(4, 'little')
    else:
        return b"\xff" + n.to_bytes(8, 'little')


def serialize_outpoint(txid_hex, vout):
    """txid is hex string in display order; serialized little-endian."""
    return bytes.fromhex(txid_hex)[::-1] + vout.to_bytes(4, 'little')


def serialize_input(prevout_bytes, script_sig, sequence):
    return (prevout_bytes
            + _varint(len(script_sig)) + script_sig
            + sequence.to_bytes(4, 'little'))


def serialize_output(value_satoshi, script_pub_key):
    return (value_satoshi.to_bytes(8, 'little')
            + _varint(len(script_pub_key)) + script_pub_key)


def serialize_tx(version, inputs, outputs, locktime):
    """inputs and outputs are pre-serialized bytes."""
    out = version.to_bytes(4, 'little')
    out += _varint(len(inputs))
    for inp in inputs:
        out += inp
    out += _varint(len(outputs))
    for o in outputs:
        out += o
    out += locktime.to_bytes(4, 'little')
    return out
