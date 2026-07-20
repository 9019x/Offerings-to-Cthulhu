# OFF testnet

The OFF testnet is a separate chain that mirrors mainnet's consensus rules
with three differences:

1. **Earlier fork heights** so post-bipsoft rules activate within minutes
   of genesis instead of weeks.
2. **Lower proof-of-work limit** so a laptop CPU can mine blocks.
3. **No real-value coins.** Testnet coins are toys; the chain may be
   re-genesis'd at any time without notice.

Use it to exercise the `v2.0.x-rc-bipsoft` consensus bundle (#32 + #33 +
#34 + #39) before mainnet activation at h=1,055,555.

## Quick start

```bash
# Clone, build (see doc/build-unix.md for prerequisites)
git clone https://github.com/SubGeniusFinance/Offerings-to-Cthulhu.git
cd Offerings-to-Cthulhu
git checkout feat/v2.0.x-rc-bipsoft   # or whatever rc tag is current
./autogen.sh && ./configure --without-gui --disable-tests --without-miniupnpc
make -j$(nproc) -C src Offeringsd

# Launch in testnet mode
mkdir -p ~/.Offering-testnet
cat > ~/.Offering-testnet/Offerings.conf <<EOF
testnet=1
server=1
rpcuser=$(whoami)
rpcpassword=$(openssl rand -hex 24)
rpcallowip=127.0.0.1
EOF
chmod 600 ~/.Offering-testnet/Offerings.conf
src/Offeringsd -daemon -datadir=~/.Offering-testnet

# Confirm you're peered to the seed
src/Offerings-cli -datadir=~/.Offering-testnet getconnectioncount
src/Offerings-cli -datadir=~/.Offering-testnet getpeerinfo | head -20
```

The DNS seed at `testnet-seed.23skidoo.info:21973` should be auto-discovered
and your node will start syncing the testnet chain.

## Chain parameters

| | Mainnet | Testnet |
|---|---|---|
| genesis hash | `000006829ac5ad04…b091b5` | `6f66b770406b4f72…2fabc9` |
| P2P port | 20000 | 21973 |
| RPC port | 11928 | 18372 |
| net magic | `03 a5 fe dd` | `01 1a 39 f7` |
| datadir | `~/.Offering` | `~/.Offering-testnet` (any `-testnet` daemon under `testnet3/`) |
| address prefix | `Q…` (118) | `Q…` (119) — visually similar but different |
| PoW limit | `~uint256 >> 20` | `~uint256 >> 1` (laptop-mineable) |
| Block target | 60 s | 60 s |

## v2.0.x-rc-bipsoft consensus activation heights

The whole point of the testnet is to test the bipsoft bundle before
mainnet. All three rules activate at **testnet h=100**:

- `HARDFORK_COINBASE_MAT_TESTNET_OFF = 100` (#32): coinbase maturity bumps
  10 → 240 at h=100.
- `HARDFORK_DERSIG_TESTNET_OFF = 100` (#33): BIP66 strict-DER signatures
  enforced at block validation.
- `HARDFORK_CLTV_TESTNET_OFF = 100` (#34): `OP_NOP2` redefined as
  `OP_CHECKLOCKTIMEVERIFY`.

For local boundary testing without the seed, regtest mode runs the same
rules at h=110 — see `qa/rpc-tests/coinbase_maturity.py`,
`qa/rpc-tests/cltv_boundary.py`, and `qa/rpc-tests/dersig_boundary.py`.

## How to mine on testnet

Testnet difficulty starts trivial. CPU mining works:

```bash
src/Offerings-cli -datadir=~/.Offering-testnet setgenerate true 1
# Watch height climb
src/Offerings-cli -datadir=~/.Offering-testnet getblockcount
# Stop
src/Offerings-cli -datadir=~/.Offering-testnet setgenerate false
```

Mining into your wallet builds a testnet balance. Coinbase maturity at
testnet h<100 is 10 blocks (legacy); at h>=100 it's 240 (hardened).
`getbalance` reflects only mature coinbases.

## What to exercise

If you're testing a wallet, exchange integration, or just smoke-checking
the rules:

- **Spend a coinbase across h=100.** Mine to h=99, spend a 10-block-old
  coinbase (legacy maturity allows it). Mine to h=110, observe the wallet
  no longer reports old coinbases as mature (hardened maturity = 240).
- **BIP66 strict-DER.** Any modern wallet (anything using libsecp256k1 or
  OpenSSL ≥ 1.0.2) produces strict-DER signatures, so normal operation
  shouldn't change. If you've written a custom signer, validate against
  testnet — block-validation will reject malformed sigs from h=100
  onward.
- **BIP65 CLTV.** Try a P2SH-CLTV escrow / time-lock pattern.
  `qa/rpc-tests/cltv_boundary.py` shows the construction.

## Caveats

- The testnet chain is **expendable**. We may re-genesis it before
  v2.0.x-rc-bipsoft ships if the chainparams change.
- No faucet at the moment; mine your own coins.
- The seed at `testnet-seed.23skidoo.info` is a single host; if it goes
  down briefly, your node may have nothing else to connect to. A second
  seed can be added once external testers join.
- Testnet has **no Codex inscription**, **no OFFSIG window**, and **no
  Treasury split** — the Restoration fork's mainnet-specific features
  are skipped on the testnet path so the bundle's consensus rules can be
  tested in isolation.

## Reporting issues

Issues at https://github.com/SubGeniusFinance/Offerings-to-Cthulhu/issues
— tag with `testnet` so they're easy to find.

Community chat: https://23skidoo.info/discord
