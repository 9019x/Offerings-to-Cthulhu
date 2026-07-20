// Copyright (c) 2009-2013 The Bitcoin developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_CHECKPOINT_H
#define BITCOIN_CHECKPOINT_H

#include <map>
#include "uint256.h"
#include "util.h"
#include "net.h"

class CBlockIndex;
class uint256;

// ppcoin: synchronized checkpoint
class CUnsignedSyncCheckpoint
{
public:
    int nVersion;
    uint256 hashCheckpoint;      // checkpoint block

    IMPLEMENT_SERIALIZE
    (
        READWRITE(this->nVersion);
        nVersion = this->nVersion;
        READWRITE(hashCheckpoint);
    )

    void SetNull()
    {
        nVersion = 1;
        hashCheckpoint = 0;
    }

    std::string ToString() const
    {
        return strprintf(
                "CSyncCheckpoint(\n"
                "    nVersion       = %d\n"
                "    hashCheckpoint = %s\n"
                ")\n",
            nVersion,
            hashCheckpoint.ToString().c_str());
    }

    void print() const
    {
        LogPrintf("%s", ToString().c_str());
    }
};

class CSyncCheckpoint : public CUnsignedSyncCheckpoint
{
public:
    // Phase-2 ACP master privkey (issue #40): set at daemon start via -checkpointkey=<WIF>.
    // The pubkey is read dynamically from Params().ConclaveKeys()[0] — the pre-#40
    // strMainPubKey / strTestPubKey constants pointed at stale 2014 ppcoin/Peercoin keys
    // and were deleted along with their TestNet() branch in CheckSignature.
    static std::string strMasterPrivKey;

    std::vector<unsigned char> vchMsg;
    std::vector<unsigned char> vchSig;

    CSyncCheckpoint()
    {
        SetNull();
    }

    IMPLEMENT_SERIALIZE
    (
        READWRITE(vchMsg);
        READWRITE(vchSig);
    )

    void SetNull()
    {
        CUnsignedSyncCheckpoint::SetNull();
        vchMsg.clear();
        vchSig.clear();
    }

    bool IsNull() const
    {
        return (hashCheckpoint == 0);
    }

    uint256 GetHash() const
    {
        return Hash(this->vchMsg.begin(), this->vchMsg.end());
    }

    bool RelayTo(CNode* pnode) const
    {
        // returns true if wasn't already sent
        if (pnode->hashCheckpointKnown != hashCheckpoint)
        {
            pnode->hashCheckpointKnown = hashCheckpoint;
            pnode->PushMessage("checkpoint", *this);
            return true;
        }
        return false;
    }

    bool CheckSignature();
    bool ProcessSyncCheckpoint(CNode* pfrom);
};

/** Block-chain checkpoints are compiled-in sanity checks.
 * They are updated every release or three.
 */
namespace Checkpoints
{
    // Returns true if block passes checkpoint checks
    bool CheckBlock(int nHeight, const uint256& hash);

    // Return conservative estimate of total number of blocks, 0 if unknown
    int GetTotalBlocksEstimate();

    // Returns last CBlockIndex* in mapBlockIndex that is a checkpoint
    CBlockIndex* GetLastCheckpoint(const std::map<uint256, CBlockIndex*>& mapBlockIndex);
	
    double GuessVerificationProgress(CBlockIndex *pindex, bool fSigchecks = true);

    extern bool fEnabled;

    // Rolling checkpoint auto-rollforward (issue #6, Phase 1).
    // Activates at HARDFORK_ROLLING_CKPT_<net>_OFF in src/pow.h.
    // See MaybeRollForward() for the per-block hook.
    extern bool fRollingEnabled;

    // Returns the rolling-checkpoint activation height for the active
    // network (mainnet/testnet/regtest). Mirrors LWMA3ForkHeight().
    int GetRollingCheckpointActivationHeight();

    // Load any persisted rolling entries from
    // <datadir>/rolling_checkpoints.dat. Idempotent; safe to call once
    // at startup. Tolerant of a truncated tail record.
    bool LoadRollingCheckpoints();

    // Append a (height, hash) record to <datadir>/rolling_checkpoints.dat.
    // Fixed-width 36-byte records (uint32 LE + uint256 hash).
    bool WriteRollingCheckpoint(int nHeight, const uint256& hash);

    // Per-block entry from ConnectTip. If pindexNew is past activation
    // height + ROLLING_DEPTH, walks back ROLLING_DEPTH and locks the
    // ancestor (height, hash) into the runtime rolling map + disk.
    // No-op below activation height, or when fRollingEnabled is false.
    void MaybeRollForward(const CBlockIndex* pindexNew);

    // Drops oldest rolling entries until size <= ROLLING_KEEP. Static
    // entries are never touched. Called internally on every roll-forward.
    void GCRollingCheckpoints();

    // RPC support — listing, clearing, and the runtime toggle.
    std::map<int, uint256> GetRollingCheckpoints();
    bool ClearRollingCheckpointsBelow(int nBelowHeight);
    void SetRollingEnabled(bool fOn);

    // ppcoin: synchronized checkpoint
    extern uint256 hashSyncCheckpoint;
    extern CSyncCheckpoint checkpointMessage;
    extern uint256 hashInvalidCheckpoint;
    extern CCriticalSection cs_hashSyncCheckpoint;
    extern std::string strCheckpointWarning;
	
    bool WriteSyncCheckpoint(const uint256& hashCheckpoint);
    bool IsSyncCheckpointEnforced();
    bool AcceptPendingSyncCheckpoint();
    uint256 AutoSelectSyncCheckpoint();
    bool CheckSyncCheckpoint(const uint256& hashBlock, const CBlockIndex* pindexPrev);
    bool WantedByPendingSyncCheckpoint(uint256 hashBlock);
    bool ResetSyncCheckpoint();
    void AskForPendingSyncCheckpoint(CNode* pfrom);
    bool CheckCheckpointPubKey();
    bool SetCheckpointPrivKey(std::string strPrivKey);
    bool SendSyncCheckpoint(uint256 hashCheckpoint);
    bool IsMatureSyncCheckpoint();
    bool IsSyncCheckpointTooOld(unsigned int nSeconds);
	
    uint256 WantedByOrphan(const CBlock* pblockOrphan);
	
}

#endif
