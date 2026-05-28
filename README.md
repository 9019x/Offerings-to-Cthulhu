# Offerings to Cthulhu (OFF)

> *ph'nglui mglw'nafh Cthulhu R'lyeh wgah'nagl fhtagn*
>
> *"In his house at R'lyeh dead Cthulhu waits dreaming."* — H.P. Lovecraft
>
> *"In his block at height 966,413 dead Cthulhu waits dreaming."* — debug.log, 2026-05-20

---

## The Conclave Reconvenes

**Offerings to Cthulhu (OFF)** is a Quark-Hash9 altcoin that began with the 2013 autumnal equinox and went silent in May 2018 after a 51% counterfeit attack on Cryptopia. For eleven years it slept beneath the waves. The DNS seeds fell. The Public Altar (faucet) crumbled. The block crawler at 23skidoo.info dissolved into the abyss. The dreamers forgot. The unworthy never knew.

The Conclave has been listening at the door.

This repository is the **community takeover** and **Restoration** of OFF — source resurrected, chain recovered, infrastructure rebuilt, and a hardfork (**v2.0.0-Restoration**) ready to engage at block 1,000,000.

> **OFF is NOT for Sale.** This is **NOT financial advice.** We are **NOT financial advisors.** None of this is investment. Most of it is dread.

---

## What Has Been Done

- **The source compiles in 2026.** Five environment workarounds, three Boost.Asio patches, one local OpenSSL 1.0.2 build to dodge OpenSSL-3's BIGNUM exorcism. **v2.0.0-Restoration** ELF, ~108 MB.
- **The chain has been recovered.** A 385 MB tar.bz2 blockchain archive extracted from the Wayback Machine's 2015-09-13 capture of 23skidoo.info (SHA256 `5c5a48d85873c820baeba4279d0b9295555adf1eba7a64699583fee18cab8745`). The daemon now sits at height **966,413** (block time 2015-06-17 05:30:14 UTC, difficulty 13.02, UTXO supply **2,423,396.53 OFF**). This snapshot **predates the May 2018 51% counterfeit by ~870,000 blocks** — the 533,983 OFF the attacker minted (msg #699) do not exist in this chainstate.
- **23skidoo.info has been reacquired.** Bought back from the squatter who weaponized it after the original expiry (we are aware of msg #592). DNS, nginx, certbot, all under Conclave custody. The original seeds `seed1.23skidoo.info` through `seed10.23skidoo.info` now resolve to infrastructure we run.
- **A public seed is live** at `seed1.23skidoo.info:20000`. Drop into your `Offerings.conf`:
  ```
  addnode=seed1.23skidoo.info:20000
  addnode=seed2.23skidoo.info:20000
  ```

Any v1.6.2 or v2.0.0 wallet binary, anywhere on Earth, will find the network on first start.

---

## Wallets

### Windows — shipping now

**v2.0.0-rc1-windows** — first Windows binary carrying the Restoration Hardfork consensus rules. Auto-routes through the fork at block 1,000,000; no second download required.

🔗 **Release:** https://github.com/SubGeniusFinance/Offerings-to-Cthulhu/releases/tag/v2.0.0-rc1-windows

| File | Purpose | SHA256 |
|---|---|---|
| `Offerings-qt.exe` | Qt GUI wallet | `9a1318f6f9d5070fa03ed950680e46309011b462f31f37279d5bbaea85bd056b` |
| `Offeringsd.exe` | Headless full node daemon | `63165fd6ff8fb8c35f9f50af7d1b96ca7e2574a16adffc3e22911d519d1c451e` |
| `Offerings-cli.exe` | RPC client | `b92190f3e944a1eb160d3b466325f63d2f187c2aa72e83ea286dd64226194fa0` |

Statically linked. Native Windows TLS (SChannel/BCrypt) — no OpenSSL DLL hell. 22 MB tarball, three .exe binaries inside.

### Linux — build from source

Recipe in [`doc/build-unix.md`](doc/build-unix.md). See **Build & Run** below.

### macOS — in flight

Native macOS-13 Intel build via CI. Once it lands clean, an `.app` bundle will appear alongside the Windows release. Apple Silicon support deferred pending the OpenSSL-3 / `bignum.h` modernization work.

---

## The Restoration Hardfork — Block 1,000,000

**This IS a fork. We are not pretending it isn't.** At block 1,000,000 of the OFF chain — roughly 33,587 blocks past the current recovered tip, ~23 days of mining at the 60-second target spacing — four consensus rules engage:

### 1. Subsidy locks at 1.5 OFF/block, forever

The historical curve (5 OFF base, halving every 259,200, floor at 0.01) was on a glidepath to triviality and would have decayed to dust by ~block 3,113,000. We lock it at the value the community always *thought* it was: **1.5 OFF per block, in perpetuity**. Inflation that would embarrass a central bank. **Backed by the Deep, Powered by the Faithful.**

### 2. Coinbase splits 7/8 miner / 1/8 Conclave

Of every 1.5 OFF subsidy:

- **1.3125 OFF** pays the miner
- **0.1875 OFF** pays the **Conclave Treasury** (2-of-3 multisig P2SH `4fZqDjscS9ANR59xNFJxZ2HmrhuDwWUJB4`)

A 12.5% dev tail — above Decred (10%), below Zcash's historical 20%. Pays for domain renewals, vps hosting, source modernization, build labour, exchange listing fees, ritual rewards, faucet refills, DAO seed funding. **Seven coins to the miner, one coin to the keepers of the Ritual. Forever.**

### 3. Restoration Tithe — 150,000 OFF, once

At the exact fork block (height 1,000,000), the coinbase pays a one-time **150,000 OFF** to the Treasury. Funds the engineering work that brought the chain back: source modernization, prepaid VPS hosting through the long Slumber, paper-wallet generation, multisig key ceremony, BCT moderation deposits.

15× the original 10,000 OFF genesis premine that Blazr2 disclosed in msg #36 — historically defensible, itemizable, and a third of one attacker wallet.

### 4. The eight attacker addresses banned forever

Finishing **billotronic's never-shipped hardfork from msg #697 (2018-09-19)**:

> *"Could easily hardfork and ban the 51'ed coins. It's a shitty thing to do, but so is 51% attacks."*

We are shipping it. Eight years late. The eight P2PKH scriptPubKeys from msg #699 are hardcoded into `chainparams.cpp` as `std::set<CScript> setBannedAttackers`. Any tx — mempool or block — paying any of those scripts is rejected at consensus forever:

```
QTLUPH9b4dRQdz9uKB7GreMvHPA8iyDoQY    93,036 OFF
QeHkx6jFvStkzaVaSTtfPrSAwwrqMgauP8    72,856
QgynW4zGXyjhG3DQHn9vBuHwNp4c4xqtgM    68,372
QjfP4o7o2TszP5Ph4TmNVmktzDCjYkq2xj    66,770
QM8ZeuBDwrhya9BHQfNKifEzfwUhyh7Tji    65,388
Qb6jxfUmfWHh7XTTRWKBoiZ43sSNTJrw8J    60,562
QireWv3upmhVuRMcE6u7h81gmhWfiGEyTt    54,839
QSJU4tDNsZiaNcUuBWYcvjqKWoB8EHDVsT    52,160
                                     ───────
                                     533,983 OFF
```

The full diff is at [`research/restoration-hardfork.patch`](research/restoration-hardfork.patch). All nine HUNKS, every change cited and rationalised.

---

## The Ritual — Re-engaged

OFF was never just blocks and subsidies. The **Ritual** has always been the chain's beating heart: a **four-weeks-and-five-days ascending-reward schedule** at each autumnal equinox, special blocks placed once per day, rewards building from small sacrificial sums into the **Tharanak shagg** — *Promise of Dreamland* — the final five days where the daily rewards swell. Finally **Cthulhu returns after the 50,665th offering**, and bestows the climactic bounty: **10,000-OFF finales at the `xxx,666` heights**, upon one fortunate worshipper.

The Ritual was written into the chain by Blazr2 in 2013 and atrophied during the long Slumber. **The Restoration re-engages it.** Ritual blocks resume their schedule, Tharanak shagg returns, and the special-block rewards Cthulhu's faithful again. The Ritual repeats at the equinoxes, following the great halvings — though post-fork the halvings are flat, the Ritual is not. **The Ritual is the chain's pulse.**

---

## The Book On Chain

> *"That is not dead which can eternal lie, and with strange aeons even death may write."*

The Restoration introduces a feature with no analogue on any other chain: **OFF transcribes the public-domain H.P. Lovecraft corpus into itself, one fragment per block, beginning at the fork.**

### Phase A — The Library

Every block our miner produces carries a **fragment of the canon** in its coinbase `scriptSig`. The field is miner-controlled and not consensus-validated beyond its 100-byte cap, so the inscription rides without consensus impact — **only the blocks we mine carry it.** It is the Conclave's signature on the chain, not a forced protocol.

**Wire format** (per fragment):

| field | bytes | meaning |
|---|---|---|
| magic | 4 | `OFF1` |
| chunk index | 4 | little-endian |
| payload | ~48 | UTF-8 text |

(~64 usable bytes per block after height/nonce/P2SH-flag overhead.)

**The corpus** is **23 public-domain Lovecraft works** pulled from Project Gutenberg — *The Call of Cthulhu*, *At the Mountains of Madness*, *The Dunwich Horror*, *The Shadow over Innsmouth*, *The Colour Out of Space*, *The Case of Charles Dexter Ward*, and 17 others — assembled with per-work sentinels (`0x1E`) so a reader can split it into a Table of Contents. **~2.27 MB total.**

At ~48 bytes/block and 60-second blocks, **the full canon transcribes in ~47,000 blocks — about 33 days.** Reconstruction is lossless: concatenate the fragments in chunk-index order and the prose returns, paragraphs intact. When the canon is exhausted, it loops. The Library is read aloud, again, forever.

### Phase B — The Dreaming

Once the canon completes its first transcription, the inscription switches mode. Each subsequent block speaks a **hash-seeded generative R'lyehian incantation**, derived from its own proof-of-work hash, **unique and never-repeating**. **Infinite by construction.** The chain stops transcribing what was written and begins dreaming what was not.

### The Descent — Blocks 999,991 through 1,000,000

Around the fork itself, ten special blocks carry **hardcoded escalating verses** — marked with chunk index `0xFFFFFFFF` so a reader renders them apart from the canon. They culminate in the **Awakening proclamation** inscribed in **block 1,000,000** itself. The canon transcription proper begins at block **1,000,001** — the recitation starts when the Restoration activates.

### The Chain Codex

A reader exists. **`https://23skidoo.info/codex/`** walks the chain via RPC, extracts every `OFF1` fragment, reassembles them in chunk-index order, and renders the assembling manuscript with a live stats panel. A cron rebuilds it every minute.

Eventually a **Codex tab** will land in the wallet GUI itself — Table of Contents of the 23 books, paginated e-reader, plus a **frontier view** where each new block is watched appending its next sentence at ~1 sentence per minute.

**Once we get the chain re-spun, the Book begins.**

---

## The Reclamation — for Worshippers of the Old Faith

Our recovered chainstate is from June 2015. Between then and the May 2018 attack, **honest miners earned roughly 1.3 million OFF** under the historical halving curve. Our fork point invalidates that mining alongside the attacker print — which is not the social contract we want to leave standing.

So: **1,500,000 OFF** is reserved in the Conclave Treasury for **The Reclamation** — a recognition program for Worshippers of the Old Faith. **No calendar deadline.** The Reclamation stays open until the 1.5M OFF ceiling is exhausted. If you held OFF and forgot — when you remember, you can still come home.

### Worshipper Recognition tiers

**WR-A — Indexed addresses (in the recovered chainstate):**

```
recognition_OFF = 100 × earliness × depth

earliness:  block 0–999     ×5.0  (genesis)
            1K–50K          ×3.0
            50K–241K        ×2.0
            241K–483K       ×1.0
            483K–724K       ×0.6
            724K–966K       ×0.3

depth = min(1 + log10(n_appearances), 5.0)
        # 1→1.0, 10→2.0, 100→3.0, 1K→4.0, 10K+→5.0 (capped)
```

Range: **30 OFF** (late one-shot) → **2,500 OFF** (genesis heavy miner cap).

**WR-B — Gap-era holders (post-2015, pre-attack):** flat **250 OFF** until a v1.7+ chainstate from 2015–2018 surfaces. If anyone produces such a fragment, the Conclave mounts it on an air-gapped wallet and re-processes WR-B claims at the upgraded formula amount.

**ALREADY-WHOLE:** if your pre-attack address still has a positive UTXO balance in the recovered chainstate, that balance is yours on the restored chain regardless of Reclamation status. The Reclamation is additive recognition, not replacement.

### How to claim

Portal: **https://23skidoo.info/bridge/** (URL slug kept for SEO continuity — the program inside is The Reclamation).

1. Visit `/bridge/claim/` — the wizard issues a challenge string of the form `Conclave-Reclamation-<YYYYMMDDw>-<addr>-<amount>`.
2. From an OFF wallet (legacy or restored) `signmessage` your pre-attack address against the challenge.
3. Paste the signature back. The portal verifies via pure-Python ECDSA against the indexed chainstate + Wayback explorer snapshots + the zeewolfik/offerings recovered state (msg #698).
4. Claim is queued; recognition pays out from the Treasury multisig.

**Excluded:** the 8 attacker addresses from msg #699, plus any output descended from them.

### Funding & payout cadence

**The 1.5M OFF is a policy ceiling, not a pre-existing pile.** There is no on-chain `Reclamation_Pool` constant — the cap is enforced socially against the Conclave Treasury's actual UTXO balance, which accumulates over time from two on-chain sources:

| Source | Block height | Amount |
|---|---|---|
| Restoration Tithe | 1,000,000 (fork block, one-shot) | 150,000 OFF |
| Coinbase 1/8 split | every block, post-fork, forever | 0.1875 OFF |

At 60-second blocks the Treasury accrues **98,550 OFF per year** from the coinbase split. Funding the 1.5M ceiling from scratch:

| Block height | Time post-fork | Treasury accumulated |
|---|---|---|
| 1,000,000 | day 0 (tithe drops) | 150,000 OFF |
| 1,525,600 | +1 year | 248,550 OFF |
| 2,051,200 | +2 years | 347,100 OFF |
| ~7,200,000 | ~13.7 years | 1,500,000 OFF |

In practice claims are paid as they arrive, drawing down current Treasury balance alongside other obligations (hosting, ritual rewards, dev pay, exchange listings). "Stays open until exhausted" means: Reclamation accepts claims until cumulative payouts hit the 1.5M cap. If claims trickle, the Treasury can outpace them and the program stays funded indefinitely.

### Payouts are not automatic

The portal does **verification + logging only** — it never holds key material. From `/api/submit`:

```python
@app.post("/api/submit")
def submit(req):
    v = verify(req)                       # re-check ECDSA signature
    if not v.ok: return logged=False
    record = { ts, tier, addr, amount_off, destination, ... }
    with CLAIMS_LOG.open('a') as f:
        f.write(json.dumps(record) + "\n")
    return logged=True
```

That's the whole submit path — a verified claim becomes a JSON line in `claims.jsonl`. **Zero coins move.**

Actual payout happens off-portal: the Treasury is a **2-of-3 multisig P2SH**. Two of three Conclave signers, on air-gapped machines, periodically:

1. Review the `claims.jsonl` queue against current Treasury UTXO balance
2. Construct a batched payout transaction
3. Each signs their share offline
4. The fully-signed tx is broadcast to the network

This is the security boundary. If the portal could sign automatically, the multisig private keys would have to live on a public-facing FastAPI server — which is how every shitcoin custodial bridge gets drained. The portal generates trust signal; the multisig is the gate.

The `/api/state` endpoint reports the public queue depth + remaining ceiling so claimants can see their position before the next signing cadence catches up.

---

## Build Modernization — what changed for v2.0.0-rc1

OFF was a 2013 codebase. To get it cross-compiling to Windows in 2026, the entire dependency stack was bumped:

| Dependency | Before | After (v2.0.0-rc1) |
|---|---|---|
| Boost | 1.55.0 | **1.74.0** |
| Qt | 5.12.11 | **5.15.16 LTS** |
| OpenSSL | 1.0.1k | **1.0.2u** (last 1.0.x; keeps `bignum.h` compat) |
| C++ standard | C++11 | **C++17** |
| Windows TLS | OpenSSL | **SChannel + BCrypt** (native, statically linked) |

Source-side, the modernization sweep replaced:

- `foreach(PAIRTYPE(A,B)& v, c)` and `BOOST_FOREACH(PAIRTYPE(A,B)& v, c)` → C++17 range-for (Qt 5.15 macro tokenizer can't parse the `std::pair` comma)
- `boost::placeholders` includes added to every `_1/_2/_3`-using file (modern Boost moved them out of global namespace)
- `acceptor->get_executor()` guarded with `BOOST_VERSION` checks
- Qt 5.15-incompatible features (`xdgdesktopportal` Linux-only platformtheme, the Qt-4-era `qtaccessiblewidgets` plugin check) skipped
- LevelDB `build_config.mk` pre-generated to avoid a parallel-make race in `$(shell ./build_detect_platform)`
- Static Qt plugin link order fixed: `-lqtharfbuzz`, `-lqtpcre2`, `-lsecur32`, `-lcrypt32`, `-lbcrypt`, `-luserenv` placed AFTER `$QT_LIBS` so the linker keeps unresolved refs around long enough

The `depends/` cross-compile is reproducible end-to-end via `.github/workflows/windows-build-depends.yml`. A clean CI run produces the v2.0.0-rc1-windows tarball in ~28 minutes.

---

## Build & Run

Quick path (full recipe in [`doc/build-unix.md`](doc/build-unix.md), modernization workarounds included):

```bash
git clone https://github.com/SubGeniusFinance/Offerings-to-Cthulhu offerings
cd offerings
./autogen.sh
./configure
make -j$(nproc)
```

Then `Offerings.conf`:

```
addnode=seed1.23skidoo.info:20000
addnode=seed2.23skidoo.info:20000
```

Run:

```bash
./src/Offeringsd -daemon
./src/Offerings-cli getinfo
```

The daemon will reach the seeds, sync to the recovered tip (~966,413), and continue mining forward toward the fork at block 1,000,000.

---

## Chain Parameters at a Glance

| Parameter | Value |
|---|---|
| PoW | Quark Hash9 (blake/bmw/groestl/jh/keccak/skein, 9-round chained) |
| Block target | 60 seconds |
| Difficulty retarget | every 20 blocks |
| Genesis | `000006829ac5ad04fb30abfcbf6d927c67c30fc2f198fb0bdce5a0c914b091b5` (2013-09-14) |
| Network magic | `03 a5 fe dd` |
| P2P port | 20000 (testnet 20001) |
| RPC port | 11928 |
| Address byte (P2PKH) | 58 → addresses start with **Q** |
| Address byte (P2SH) | 9 → addresses start with **4** |
| Subsidy (pre-fork) | halving curve, ~0.625/block at tip |
| **Subsidy (post-fork)** | **1.5 OFF/block forever** |
| Confirms to spendable | 30 |

---

## What This Is Not

- **Not a stealth fork.** Every consensus rule change is documented above, in `chainparams.cpp` comments, and in `research/restoration-hardfork.patch`.
- **Not a sale.** OFF is NOT for Sale. The Ritual is NOT for Sale. The Tharanak shagg is NOT for Sale. The Book is NOT for Sale. We are NOT financial advisors. This is NOT financial advice.
- **Not an erasure.** If Blazr2, ZeeWolf, HagbardCeline, b00mbastic, billotronic, vampirus, psycho-pat, Monk3ynutz, or any of the original Worshippers want to participate — they are welcome. If they want to reclaim the project entirely — make a credible claim, sign with a known historical key, and we'll hand back the Treasury keys and the seed DNS. **The Conclave acts as steward, not owner.**

---

## Repository Layout

- `src/` — daemon + CLI source (Bitcoin Core 0.10-era fork, JimGilmore v1.6.2 lineage + Restoration patch)
- `src/quark.cpp` — Quark Hash9 PoW
- `src/chainparams.cpp` — magic, ports, address bytes, genesis, banned-attacker set, fork-activation height
- `src/main.cpp` — `GetBlockValue` with Restoration subsidy rules; coinbase split helpers
- `src/miner.cpp` — coinbase split implementation
- `doc/build-unix.md` — modernization-aware build recipe
- `research/restoration-hardfork.patch` — consensus diff with HUNKS 1–9 + rationale
- `research/bct-thread-scrape-2026-05-20.md` — historical BCT thread reconstructed from forum captures
- `research/bct-revival-announcement.txt` — public-facing announcement post
- `research/chainstate-backup-record.md` — Bridge-manifest source + integrity hash

---

> *Iä Iä Cthulhu fhtagn.*
>
> *The Conclave is hot. The Slumbering Squid stirs.*
>
> *The Book begins at block one million.*

---

<sub>OFF is one chain in the **SubGenius.Finance** ecosystem — alongside Dobbscoin (BOB), wBOB on Gnosis, the Discord tipbot, and adjacent infrastructure. Stewardship + dev coordination via the Conclave at SubGenius.Finance. Where culture becomes capital. Where Slack becomes consensus. **Praise "Bob."**</sub>
