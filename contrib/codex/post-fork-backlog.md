# OFF — Post-Restoration Update Backlog
# Actioned by the scheduled routine that fires after block 1,000,000.
# BtcBob: add any additional updates below; the routine reads this file.

## Confirmed
1. Backport an `invalidateblock`-style RPC into Offeringsd (enables targeted reorgs).
   - Draft + build only; do NOT reorg the live chain without explicit human confirmation.
2. Deploy the ritual-consensus binary to the relay host (RitualBonus in main.cpp) BEFORE block ~1,270,346
   so the miner host and the relay host do not split. Safe (inert until that height).

## Other updates (BtcBob to specify)
- BCT relay worker — add a session heartbeat. Once every ~30 min, navigate the headless Playwright
  context to `https://bitcointalk.org/` to keep the SMF server-side session warm.
  - File: `chaos:~/relay-worker/worker.js`
  - Why: "stay logged in forever" only sets cookie expiry (years); SMF expires the server-side
    session after hours of idle. Headless profile sits dormant between dispatch jobs and goes
    Guest. Vivaldi avoids this because background browser activity heartbeats the session.
  - Cost: ~20 lines in worker.js + a small extra-detection surface (regular GETs from chaos IP).
  - Test: confirm a freshly-logged-in session survives 24h of idle without re-running login.js.

- `.cast` Discord command — target blocks with on-chain spell inscriptions.
  - Target launch: ahead of the first post-fork Ritual finale at block **1,141,666** (autumnal
    equinox 2026, ~100 days post-Hour). Test against intermediate blocks first.
  - Syntax: `.cast <height> <spell-name|"custom incantation">`
    - Predefined spells generate R'lyehian from the 32-word lexicon (same lexicon as the
      Dreaming phase in `miner.cpp::RlyehianVerse`):
      - `enthrall` — Enthrall Victim, trance/bind incantation (Call of Cthulhu KR#258)
      - `steal-life` — Steal Life, drain-warmth incantation (Masks of Nyarlathotep #637)
      - more to be added; see Lovecraft RPG spell lists for source
  - Pipeline:
    1. Bot stores pending cast in DB keyed by target height
    2. Worker monitors mempool; at T-3 from target, broadcasts an OP_RETURN tx tagged
       `CAST:<height>:<R'lyehian>` from the pool daemon's wallet
    3. (Stretch) coinbase-injection hook on `pool.23skidoo.info` daemon so casts landing on
       pool-found blocks go into the coinbase scriptSig directly (~30% hit rate given the
       current `/P2SH/` solo-miner dominance)
  - eIquidus explorer patch: parse any OP_RETURN starting with `CAST:` and render a "Spells
    cast on this block" panel on the block-view page, regardless of which block the OP_RETURN
    actually landed in. The cast targets the block by metadata, not by inclusion.
  - Scope estimate: 4-6h for OP_RETURN path + bot command. +4-6h for the explorer panel.
    +4-6h for the coinbase-injection hook. Total 12-18h for the full system.
  - Aesthetic note: 999,666 was floated as a first cast target but the chain reached the
    eve-of-Hour before the system could be built. The Conclave told it instead as narrative
    (the binding-mark mention in WHARF #6). Post-fork, the .cast system becomes the real
    mechanism behind that narrative.
- 
