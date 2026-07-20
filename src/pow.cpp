// Copyright (c) 2026 The Offerings developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
#include "pow.h"

#include "bignum.h"
#include "chainparams.h"
#include "main.h"
#include "core.h"
#include "util.h"

// LWMA-3 (Zawy Linear Weighted Moving Average, rev 3) — block-by-block
// retarget on a 60-block window. Faster and more attack-resistant than
// OFF's legacy Litecoin-style ±10%/+50%-clamped 20-block retarget against
// bursty rented-hash. Ported from dobbscoin-lwma3-testnet/src/pow.cpp:573
// (Bitcoin Core 0.10 era, arith_uint256 idiom) into OFF's pre-0.10 CBigNum
// idiom.
//
// Parameters tuned for OFF (T=60s, N=60 → 60-min window):
//   k = N*(N+1)*T / 2 = 60 * 61 * 60 / 2 = 109,800
//   solvetime clamp: ±6T = ±360s (caps timestamp-attack influence)
//   weightedTime floor: k/3 (caps diff drop at ~3× per cycle)
//
// Companion defense: MAX_REORG_DEPTH check in main.cpp::ActivateBestChain
// rejects reorganizations deeper than 100 blocks past the active tip,
// gated on the same fork height.

unsigned int GetNextWorkRequired_LWMA3(const CBlockIndex* pindexLast,
                                       const CBlockHeader *pblock)
{
    enum { N = 60 };
    const int64_t T = 60;                              // OFF target spacing
    const int64_t k = (int64_t(N) * (N + 1) * T) / 2;  // = 109800
    const CBigNum bnPowLimit = Params().ProofOfWorkLimit();

    if (pindexLast == NULL)
        return bnPowLimit.GetCompact();

    // Bootstrap window: until N blocks past the fork height, reuse the
    // previous block's bits. First N post-fork blocks inherit the legacy
    // retarget's last value, then LWMA-3 takes over cleanly.
    if (pindexLast->nHeight + 1 < LWMA3ForkHeight() + N)
        return pindexLast->nBits;

    // Walk back N+1 indices (need N solvetimes).
    const CBlockIndex *blocks[N + 1];
    blocks[N] = pindexLast;
    for (int i = N - 1; i >= 0; --i)
        blocks[i] = blocks[i + 1]->pprev;

    CBigNum sumTarget = 0;
    int64_t weightedTime = 0;
    int64_t previousTime = blocks[0]->GetBlockTime();

    for (int64_t i = 1; i <= N; ++i) {
        int64_t thisTime = blocks[i]->GetBlockTime();
        int64_t solvetime = thisTime - previousTime;
        // Clamp solvetimes to ±6T so a single bogus timestamp can't
        // dominate the average. Negative is allowed (MTP semantics) but
        // capped symmetrically.
        if (solvetime >  6 * T) solvetime =  6 * T;
        if (solvetime < -6 * T) solvetime = -6 * T;
        previousTime = thisTime;

        weightedTime += solvetime * i;                 // weight = position i

        CBigNum target;
        target.SetCompact(blocks[i]->nBits);
        sumTarget += target / CBigNum(N * k);          // divide-before-add
    }

    // Floor the weighted sum at k/3 so an extreme inbound burst can't
    // push next-target below ~1/3 of average — i.e. diff can at most ~3×
    // per cycle. This is the rented-hash defense on the way up.
    if (weightedTime < k / 3) weightedTime = k / 3;

    CBigNum nextTarget = sumTarget * CBigNum(weightedTime);
    if (nextTarget > bnPowLimit) nextTarget = bnPowLimit;

    LogPrint("pow", "GetNextWorkRequired LWMA3 RETARGET  N=%d T=%d weightedTime=%d k=%d\n",
             (int)N, (int)T, (int)weightedTime, (int)k);
    LogPrint("pow", "Before: %08x  %s\n", pindexLast->nBits,
             CBigNum().SetCompact(pindexLast->nBits).getuint256().ToString().c_str());
    LogPrint("pow", "After:  %08x  %s\n", nextTarget.GetCompact(),
             nextTarget.getuint256().ToString().c_str());
    return nextTarget.GetCompact();
}

int64_t LWMA3ForkHeight()
{
    return TestNet() ? HARDFORK_LWMA3_TESTNET_OFF
                     : HARDFORK_LWMA3_MAIN_OFF;
}

// Dispatcher: route to LWMA-3 once the fork activates, otherwise legacy.
// Called from main.cpp wherever GetNextWorkRequired() was called before.
unsigned int GetNextWorkRequired(const CBlockIndex* pindexLast,
                                 const CBlockHeader *pblock)
{
    if (pindexLast == NULL)
        return Params().ProofOfWorkLimit().GetCompact();

    if (pindexLast->nHeight + 1 >= LWMA3ForkHeight())
        return GetNextWorkRequired_LWMA3(pindexLast, pblock);

    return GetNextWorkRequired_Legacy(pindexLast, pblock);
}


int EmergencyDiffForkHeight()
{
    return TestNet() ? HARDFORK_EMERGENCY_DIFF_TESTNET_OFF
                                               : HARDFORK_EMERGENCY_DIFF_MAIN_OFF;
}

bool IsEmergencyDifficultyBlock(const CBlockHeader& block, const CBlockIndex* pindexPrev)
{
    if (pindexPrev == NULL)
        return false;

    const int64_t nHeight = pindexPrev->nHeight + 1;

    // (a) Activation gate.
    if (nHeight < EmergencyDiffForkHeight())
        return false;

    // (b) Hard-skip the Conclave signed-mining window. Descent + Codex blocks
    // stay pool-only even under hashrate stall — the chain would rather wait
    // than let an outsider land a min-diff ceremony block.
    if (nHeight >= Params().SignedWindowStart() && nHeight <= Params().OpenMiningHeight())
        return false;

    // (c) Strict-greater gap. Equality at exactly 1h is not enough.
    const int64_t gap = (int64_t)block.nTime - (int64_t)pindexPrev->nTime;
    if (gap <= EMERGENCY_DIFFICULTY_GAP)
        return false;

    // (d) Min-difficulty only. Better-than-powLimit must publish at that target.
    CBigNum bnTarget;
    bnTarget.SetCompact(block.nBits);
    if (bnTarget != Params().ProofOfWorkLimit())
        return false;

    return true;
}
