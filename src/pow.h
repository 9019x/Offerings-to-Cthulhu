// Copyright (c) 2026 The Offerings developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
#ifndef BITCOIN_POW_H
#define BITCOIN_POW_H

#include <stdint.h>

class CBlockIndex;
class CBlockHeader;

// HARD FORK ACTIVATION HEIGHTS — LWMA-3 + MAX_REORG_DEPTH defense
// vs rented-hash drive-by attacks. Companion to the h=976000 hardcoded
// checkpoint (mapCheckpoints) shipped in v2.0.1-Bokrug-checkpoint
// (non-consensus, 2026-05-29) — the checkpoint locks old history, this
// fork hardens the chain going forward.
//
// HARDFORK_LWMA3_MAIN_OFF: pulled in from 990000 → 980000 in rc4
// (2026-05-29) after observing the chain locked at ~20s/block with
// hashrate tracking the legacy +10%/cycle clamp 1:1 — the drive-by-
// miner pattern the LWMA-3 + MAX_REORG_DEPTH defense was built for.
// Block-height activation (not wall-time) so the fork lands
// deterministically regardless of attack-compressed solvetimes.
static const int64_t HARDFORK_LWMA3_MAIN_OFF    = 980000;
static const int64_t HARDFORK_LWMA3_TESTNET_OFF = 100;

// MAX_REORG_DEPTH: chains attempting to reorganize past this many buried
// blocks of the active tip are rejected at consensus. 100 blocks ≈ 100
// minutes at OFF's 60s target — economically infeasible for an attacker
// to mine in secret on a small chain at any plausible hashrate.
static const int MAX_REORG_DEPTH = 100;

// EMERGENCY-DIFFICULTY rule — escape valve against Quark-hashrate departure.
// Companion to LWMA-3: when no block lands for >EMERGENCY_DIFFICULTY_GAP and
// the next block carries nBits == ProofOfWorkLimit (min-diff), the strict
// nBits == GetNextWorkRequired() check at AcceptBlock is relaxed for that
// one block. LWMA-3 then sees the long solvetime in its rolling 60-block
// window and resumes normal retargeting within ~N blocks.
//
// Min-diff-only: a miner who can mine harder than powLimit MUST publish at
// the normally-computed target. Claiming min-difficulty when you don't need
// it is rejected.
//
// Hard-skipped during the Conclave signed-mining window [SignedWindowStart
// .. OpenMiningHeight] — Descent verses, Codex transcription, and post-canon
// buffer stay pool/Conclave-only even under stall. (Belt-and-braces: the
// Conclave signature check rejects outsider blocks at those heights anyway.)
//
// Gap = 1 hour = 60× OFF's target spacing — a 60-block stall is a clear
// stuck condition, not bad luck.
//
// Activation 989,898 — palindromic, ~7 days of pre-Conclave-window runway,
// ~10K blocks before the Restoration fork at 1,000,000.
static const int     HARDFORK_EMERGENCY_DIFF_MAIN_OFF    = 989898;
static const int     HARDFORK_EMERGENCY_DIFF_TESTNET_OFF = 200;
static const int64_t EMERGENCY_DIFFICULTY_GAP            = 60 * 60;  // 3600 s

// COINBASE_MATURITY hardening — bumps coinbase-spend maturity 10 → 240.
// Activates post-OFFSIG-window (window ends 1,050,666), 4,889 blocks past
// freeze-end at h=1,050,667. Bundled with #6 rolling-checkpoints at the
// same height (one upgrade cycle). See issue #32 and #20 (feature-freeze
// policy that anchored the activation slot).
static const int     HARDFORK_COINBASE_MAT_MAIN_OFF      = 1055555;
static const int     HARDFORK_COINBASE_MAT_TESTNET_OFF   = 100;
static const int     HARDFORK_COINBASE_MAT_REGTEST_OFF   = 110;

unsigned int GetNextWorkRequired(const CBlockIndex* pindexLast, const CBlockHeader *pblock);
unsigned int GetNextWorkRequired_Legacy(const CBlockIndex* pindexLast, const CBlockHeader *pblock);
unsigned int GetNextWorkRequired_LWMA3(const CBlockIndex* pindexLast, const CBlockHeader *pblock);
int64_t LWMA3ForkHeight();
int     EmergencyDiffForkHeight();
bool    IsEmergencyDifficultyBlock(const CBlockHeader& block, const CBlockIndex* pindexPrev);

#endif // BITCOIN_POW_H
