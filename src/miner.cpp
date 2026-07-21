// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2014 The Bitcoin developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "miner.h"

#include "core.h"
#include "main.h"
#include "net.h"
#include "checkpoints.h"
#include "base58.h"
#ifdef ENABLE_WALLET
#include "wallet.h"
#endif
#include <cstring>
#include <algorithm>
#include <fstream>
#include <sstream>
#include <string>
//////////////////////////////////////////////////////////////////////////////
//
// BitcoinMiner
//

int static FormatHashBlocks(void* pbuffer, unsigned int len)
{
    unsigned char* pdata = (unsigned char*)pbuffer;
    unsigned int blocks = 1 + ((len + 8) / 64);
    unsigned char* pend = pdata + 64 * blocks;
    memset(pdata + len, 0, 64 * blocks - len);
    pdata[len] = 0x80;
    unsigned int bits = len * 8;
    pend[-1] = (bits >> 0) & 0xff;
    pend[-2] = (bits >> 8) & 0xff;
    pend[-3] = (bits >> 16) & 0xff;
    pend[-4] = (bits >> 24) & 0xff;
    return blocks;
}

static const unsigned int pSHA256InitState[8] =
{0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};

void SHA256Transform(void* pstate, void* pinput, const void* pinit)
{
    SHA256_CTX ctx;
    unsigned char data[64];

    SHA256_Init(&ctx);

    for (int i = 0; i < 16; i++)
        ((uint32_t*)data)[i] = ByteReverse(((uint32_t*)pinput)[i]);

    for (int i = 0; i < 8; i++)
        ctx.h[i] = ((uint32_t*)pinit)[i];

    SHA256_Update(&ctx, data, sizeof(data));
    for (int i = 0; i < 8; i++)
        ((uint32_t*)pstate)[i] = ctx.h[i];
}

// Some explaining would be appreciated
class COrphan
{
public:
    const CTransaction* ptx;
    set<uint256> setDependsOn;
    double dPriority;
    double dFeePerKb;

    COrphan(const CTransaction* ptxIn)
    {
        ptx = ptxIn;
        dPriority = dFeePerKb = 0;
    }

    void print() const
    {
        LogPrintf("COrphan(hash=%s, dPriority=%.1f, dFeePerKb=%.1f)\n",
               ptx->GetHash().ToString(), dPriority, dFeePerKb);
        BOOST_FOREACH(uint256 hash, setDependsOn)
            LogPrintf("   setDependsOn %s\n", hash.ToString());
    }
};


uint64_t nLastBlockTx = 0;
uint64_t nLastBlockSize = 0;

// We want to sort transactions by priority and fee, so:
typedef boost::tuple<double, double, const CTransaction*> TxPriority;
class TxPriorityCompare
{
    bool byFee;
public:
    TxPriorityCompare(bool _byFee) : byFee(_byFee) { }
    bool operator()(const TxPriority& a, const TxPriority& b)
    {
        if (byFee)
        {
            if (a.get<1>() == b.get<1>())
                return a.get<0>() < b.get<0>();
            return a.get<1>() < b.get<1>();
        }
        else
        {
            if (a.get<0>() == b.get<0>())
                return a.get<1>() < b.get<1>();
            return a.get<0>() < b.get<0>();
        }
    }
};

CBlockTemplate* CreateNewBlock(const CScript& scriptPubKeyIn)
{
    // Create new block
    auto_ptr<CBlockTemplate> pblocktemplate(new CBlockTemplate());
    if(!pblocktemplate.get())
        return NULL;
    CBlock *pblock = &pblocktemplate->block; // pointer for convenience

    // Create coinbase tx
    CTransaction txNew;
    txNew.vin.resize(1);
    txNew.vin[0].prevout.SetNull();
    txNew.vout.resize(1);
    txNew.vout[0].scriptPubKey = scriptPubKeyIn;

    // Add our coinbase tx as first transaction
    pblock->vtx.push_back(txNew);
    pblocktemplate->vTxFees.push_back(-1); // updated at end
    pblocktemplate->vTxSigOps.push_back(-1); // updated at end

    // Largest block you're willing to create:
    unsigned int nBlockMaxSize = GetArg("-blockmaxsize", DEFAULT_BLOCK_MAX_SIZE);
    // Limit to betweeen 1K and MAX_BLOCK_SIZE-1K for sanity:
    nBlockMaxSize = std::max((unsigned int)1000, std::min((unsigned int)(MAX_BLOCK_SIZE-1000), nBlockMaxSize));

    // How much of the block should be dedicated to high-priority transactions,
    // included regardless of the fees they pay
    unsigned int nBlockPrioritySize = GetArg("-blockprioritysize", DEFAULT_BLOCK_PRIORITY_SIZE);
    nBlockPrioritySize = std::min(nBlockMaxSize, nBlockPrioritySize);

    // Minimum block size you want to create; block will be filled with free transactions
    // until there are no more or the block reaches this size:
    unsigned int nBlockMinSize = GetArg("-blockminsize", DEFAULT_BLOCK_MIN_SIZE);
    nBlockMinSize = std::min(nBlockMaxSize, nBlockMinSize);

    // Collect memory pool transactions into the block
    int64_t nFees = 0;
    {
        LOCK2(cs_main, mempool.cs);
        CBlockIndex* pindexPrev = chainActive.Tip();
        CCoinsViewCache view(*pcoinsTip, true);

        // Priority order to process transactions
        list<COrphan> vOrphan; // list memory doesn't move
        map<uint256, vector<COrphan*> > mapDependers;
        bool fPrintPriority = GetBoolArg("-printpriority", false);

        // This vector will be sorted into a priority queue:
        vector<TxPriority> vecPriority;
        vecPriority.reserve(mempool.mapTx.size());
        for (map<uint256, CTxMemPoolEntry>::iterator mi = mempool.mapTx.begin();
             mi != mempool.mapTx.end(); ++mi)
        {
            const CTransaction& tx = mi->second.GetTx();
            if (tx.IsCoinBase() || !IsFinalTx(tx, pindexPrev->nHeight + 1))
                continue;

            COrphan* porphan = NULL;
            double dPriority = 0;
            int64_t nTotalIn = 0;
            bool fMissingInputs = false;
            BOOST_FOREACH(const CTxIn& txin, tx.vin)
            {
                // Read prev transaction
                if (!view.HaveCoins(txin.prevout.hash))
                {
                    // This should never happen; all transactions in the memory
                    // pool should connect to either transactions in the chain
                    // or other transactions in the memory pool.
                    if (!mempool.mapTx.count(txin.prevout.hash))
                    {
                        LogPrintf("ERROR: mempool transaction missing input\n");
                        if (fDebug) assert("mempool transaction missing input" == 0);
                        fMissingInputs = true;
                        if (porphan)
                            vOrphan.pop_back();
                        break;
                    }

                    // Has to wait for dependencies
                    if (!porphan)
                    {
                        // Use list for automatic deletion
                        vOrphan.push_back(COrphan(&tx));
                        porphan = &vOrphan.back();
                    }
                    mapDependers[txin.prevout.hash].push_back(porphan);
                    porphan->setDependsOn.insert(txin.prevout.hash);
                    nTotalIn += mempool.mapTx[txin.prevout.hash].GetTx().vout[txin.prevout.n].nValue;
                    continue;
                }
                const CCoins &coins = view.GetCoins(txin.prevout.hash);

                int64_t nValueIn = coins.vout[txin.prevout.n].nValue;
                nTotalIn += nValueIn;

                int nConf = pindexPrev->nHeight - coins.nHeight + 1;

                dPriority += (double)nValueIn * nConf;
            }
            if (fMissingInputs) continue;

            // Priority is sum(valuein * age) / modified_txsize
            unsigned int nTxSize = ::GetSerializeSize(tx, SER_NETWORK, PROTOCOL_VERSION);
            dPriority = tx.ComputePriority(dPriority, nTxSize);

            // This is a more accurate fee-per-kilobyte than is used by the client code, because the
            // client code rounds up the size to the nearest 1K. That's good, because it gives an
            // incentive to create smaller transactions.
            double dFeePerKb =  double(nTotalIn-tx.GetValueOut()) / (double(nTxSize)/1000.0);

            if (porphan)
            {
                porphan->dPriority = dPriority;
                porphan->dFeePerKb = dFeePerKb;
            }
            else
                vecPriority.push_back(TxPriority(dPriority, dFeePerKb, &mi->second.GetTx()));
        }

        // Collect transactions into block
        uint64_t nBlockSize = 1000;
        uint64_t nBlockTx = 0;
        int nBlockSigOps = 100;
        bool fSortedByFee = (nBlockPrioritySize <= 0);

        TxPriorityCompare comparer(fSortedByFee);
        std::make_heap(vecPriority.begin(), vecPriority.end(), comparer);

        // Pre-screen mempool txs with the same flags ConnectBlock will use
        // at this height. Without this, a tx that passes mempool's looser
        // flags (P2SH | STRICTENC) but fails block-validation's stricter
        // flags (post-fork: + DERSIG + CHECKLOCKTIMEVERIFY) is added to
        // the candidate block here, then trips the final ConnectBlock
        // test-pass at the end of this function — which throws and ends
        // the mining attempt. See issue #39.
        const int nNextHeight = pindexPrev->nHeight + 1;
        unsigned int nMinerScriptFlags = SCRIPT_VERIFY_P2SH;
        if (nNextHeight >= GetDersigForkHeight()) {
            nMinerScriptFlags |= SCRIPT_VERIFY_DERSIG | SCRIPT_VERIFY_STRICTENC;
        }
        if (nNextHeight >= GetCLTVForkHeight()) {
            nMinerScriptFlags |= SCRIPT_VERIFY_CHECKLOCKTIMEVERIFY;
        }

        while (!vecPriority.empty())
        {
            // Take highest priority transaction off the priority queue:
            double dPriority = vecPriority.front().get<0>();
            double dFeePerKb = vecPriority.front().get<1>();
            const CTransaction& tx = *(vecPriority.front().get<2>());

            std::pop_heap(vecPriority.begin(), vecPriority.end(), comparer);
            vecPriority.pop_back();

            // Size limits
            unsigned int nTxSize = ::GetSerializeSize(tx, SER_NETWORK, PROTOCOL_VERSION);
            if (nBlockSize + nTxSize >= nBlockMaxSize)
                continue;

            // Legacy limits on sigOps:
            unsigned int nTxSigOps = GetLegacySigOpCount(tx);
            if (nBlockSigOps + nTxSigOps >= MAX_BLOCK_SIGOPS)
                continue;

            // Skip free transactions if we're past the minimum block size:
            if (fSortedByFee && (dFeePerKb < CTransaction::nMinRelayTxFee) && (nBlockSize + nTxSize >= nBlockMinSize))
                continue;

            // Prioritize by fee once past the priority size or we run out of high-priority
            // transactions:
            if (!fSortedByFee &&
                ((nBlockSize + nTxSize >= nBlockPrioritySize) || !AllowFree(dPriority)))
            {
                fSortedByFee = true;
                comparer = TxPriorityCompare(fSortedByFee);
                std::make_heap(vecPriority.begin(), vecPriority.end(), comparer);
            }

            if (!view.HaveInputs(tx))
                continue;

            int64_t nTxFees = view.GetValueIn(tx)-tx.GetValueOut();

            nTxSigOps += GetP2SHSigOpCount(tx, view);
            if (nBlockSigOps + nTxSigOps >= MAX_BLOCK_SIGOPS)
                continue;

            CValidationState state;
            if (!CheckInputs(tx, state, view, true, nMinerScriptFlags))
                continue;

            CTxUndo txundo;
            uint256 hash = tx.GetHash();
            UpdateCoins(tx, state, view, txundo, pindexPrev->nHeight+1, hash);

            // Added
            pblock->vtx.push_back(tx);
            pblocktemplate->vTxFees.push_back(nTxFees);
            pblocktemplate->vTxSigOps.push_back(nTxSigOps);
            nBlockSize += nTxSize;
            ++nBlockTx;
            nBlockSigOps += nTxSigOps;
            nFees += nTxFees;

            if (fPrintPriority)
            {
                LogPrintf("priority %.1f feeperkb %.1f txid %s\n",
                       dPriority, dFeePerKb, tx.GetHash().ToString());
            }

            // Add transactions that depend on this one to the priority queue
            if (mapDependers.count(hash))
            {
                BOOST_FOREACH(COrphan* porphan, mapDependers[hash])
                {
                    if (!porphan->setDependsOn.empty())
                    {
                        porphan->setDependsOn.erase(hash);
                        if (porphan->setDependsOn.empty())
                        {
                            vecPriority.push_back(TxPriority(porphan->dPriority, porphan->dFeePerKb, porphan->ptx));
                            std::push_heap(vecPriority.begin(), vecPriority.end(), comparer);
                        }
                    }
                }
            }
        }

        nLastBlockTx = nBlockTx;
        nLastBlockSize = nBlockSize;
        LogPrintf("CreateNewBlock(): total size %u\n", nBlockSize);

        int nNewHeight = pindexPrev->nHeight + 1;
        if (IsAfterRestorationFork(nNewHeight)) {
            // Restoration Hardfork: 2-output coinbase
            //   vout[0] = miner    (7/8 subsidy + fees)
            //   vout[1] = Treasury (1/8 subsidy + tithe-at-fork-block)
            pblock->vtx[0].vout[0].nValue = GetMinerSubsidy(nNewHeight, nFees);

            CTxOut treasuryOut;
            treasuryOut.nValue       = GetTreasurySubsidy(nNewHeight) + GetTitheAmount(nNewHeight);
            treasuryOut.scriptPubKey = Params().TreasuryScript();
            pblock->vtx[0].vout.push_back(treasuryOut);

            // Reserve a placeholder OP_RETURN output for the Conclave signature;
            // it is filled in by SignBlockIfNeeded() once the merkle is settled.
            if (IsInSignedWindow(nNewHeight)) {
                CTxOut sigOut;
                sigOut.nValue = 0;
                std::vector<unsigned char> placeholder(6 + 72, 0);
                memcpy(&placeholder[0], "OFFSIG", 6);
                sigOut.scriptPubKey = CScript() << OP_RETURN << placeholder;
                pblock->vtx[0].vout.push_back(sigOut);
            }
        } else {
            // Pre-fork: unchanged
            pblock->vtx[0].vout[0].nValue = GetBlockValue(nNewHeight, nFees);
        }
        pblocktemplate->vTxFees[0] = -nFees;

        // Fill in header
        pblock->hashPrevBlock  = pindexPrev->GetBlockHash();
        UpdateTime(*pblock, pindexPrev);
        pblock->nBits          = GetNextWorkRequired(pindexPrev, pblock);
        pblock->nNonce         = 0;
        pblock->vtx[0].vin[0].scriptSig = CScript() << OP_0 << OP_0;
        pblocktemplate->vTxSigOps[0] = GetLegacySigOpCount(pblock->vtx[0]);

        CBlockIndex indexDummy(*pblock);
        indexDummy.pprev = pindexPrev;
        indexDummy.nHeight = pindexPrev->nHeight + 1;
        CCoinsViewCache viewNew(*pcoinsTip, true);
        CValidationState state;
        if (!ConnectBlock(*pblock, state, &indexDummy, viewNew, true))
            throw std::runtime_error("CreateNewBlock() : ConnectBlock failed");
    }

    return pblocktemplate.release();
}

// ---- OFF Chain Codex --------------------------------------------------------
// Embed an ever-evolving transcription into the coinbase scriptSig of every block
// we mine. Pure data (not consensus-validated beyond the 100-byte coinbase cap),
// readable back via getblock. Phase A ("The Library"): transcribe the public-domain
// Lovecraft canon, one ~48-byte fragment per block, looping for now. Phase B
// ("The Dreaming"): once the canon is exhausted, swap CODEX_TEXT for a hash-seeded
// R'lyehian generator so the chain speaks unique incantations forever.
//
// Fragment wire format (single data push): "OFF1" | uint32 LE chunk-index | text.
// Built-in fallback used only if the corpus file is missing.
static const char* CODEX_TEXT =
    "That is not dead which can eternal lie, and with strange aeons even death may die. "
    "Ph'nglui mglw'nafh Cthulhu R'lyeh wgah'nagl fhtagn. "
    "In his house at R'lyeh dead Cthulhu waits dreaming. Ia! Ia! Cthulhu fhtagn!";
static const unsigned int CODEX_ANCHOR        = 1000001;  // canon transcription begins right after the Awakening
static const unsigned int CODEX_DESCENT_START = 999991;   // ten ceremonial verses (999991..1000000) lead in to the Awakening
static const unsigned int CODEX_CHUNK         = 48;       // bytes of text per block

// The corpus to transcribe, loaded once from <datadir>/codex_corpus.txt. Records are
// separated by 0x1E ("RS"); each record is a work title, then its body. Readers split
// on 0x1E to build a table of contents. Falls back to CODEX_TEXT if the file is absent.
static const std::string& CodexCorpus()
{
    static std::string corpus;
    static bool loaded = false;
    if (!loaded) {
        loaded = true;
        try {
            boost::filesystem::path p = GetDataDir() / "codex_corpus.txt";
            std::ifstream f(p.string().c_str(), std::ios::binary);
            if (f) {
                std::stringstream ss;
                ss << f.rdbuf();
                corpus = ss.str();
            }
        } catch (...) {}
        if (corpus.empty())
            corpus = CODEX_TEXT;
    }
    return corpus;
}

// The Descent: the ten blocks 999991..1000000 carry a hardcoded invocation, one
// escalating line per block, culminating in the Awakening proclamation permanently
// inscribed in the fork block's coinbase. Marked with index 0xFFFFFFFF so readers
// render them as milestone verses rather than ordinary transcription.
static const unsigned int CODEX_MILESTONE = 0xFFFFFFFFu;
static const unsigned int CODEX_DREAMING  = 0xFFFFFFFEu;  // Phase B marker: post-canon R'lyehian
static const char* DescentLine(unsigned int nHeight)
{
    switch (nHeight) {
        case  999991: return "The angles turn wrong in the deep. He stirs.";
        case  999992: return "Pressure mounts; the black seas blacken further.";
        case  999993: return "The Conclave gathers, candles guttering green.";
        case  999994: return "R'lyeh's drowned spires breach the surface.";
        case  999995: return "That is not dead which can eternal lie,";
        case  999996: return "and with strange aeons even death may die.";
        case  999997: return "The stars come right.";
        case  999998: return "Ph'nglui mglw'nafh Cthulhu R'lyeh wgah'nagl fhtagn.";
        case  999999: return "He dreams no longer.";
        case 1000000: return "IA! IA! CTHULHU FHTAGN! Block 1000000: the Restoration is come.";
    }
    return NULL;
}

static void PushEgg(std::vector<unsigned char>& egg, uint32_t idx, const char* text, size_t n)
{
    const unsigned char magic[4] = { 'O', 'F', 'F', '1' };
    egg.insert(egg.end(), magic, magic + 4);
    egg.push_back((unsigned char)( idx        & 0xff));
    egg.push_back((unsigned char)((idx >> 8)  & 0xff));
    egg.push_back((unsigned char)((idx >> 16) & 0xff));
    egg.push_back((unsigned char)((idx >> 24) & 0xff));
    for (size_t i = 0; i < n; i++)
        egg.push_back((unsigned char)text[i]);
}

// Phase B — The Dreaming. Once the canon is fully transcribed the chain stops
// reciting our books and speaks Cthulhu's own dead tongue: a unique, deterministic
// R'lyehian verse seeded by the block height, so every block is a never-repeating
// incantation that any reader can reproduce. Capped to maxBytes so the coinbase
// stays under the 100-byte limit.
static std::string RlyehianVerse(unsigned int seed, size_t maxBytes)
{
    static const char* L[] = {
        "ph'nglui","mglw'nafh","Cthulhu","R'lyeh","wgah'nagl","fhtagn","ya","nafl",
        "hupadgh","n'gha","k'yarnak","ngah","gof'nn","syha'h","gnaiih","ftaghu",
        "ehye","lloig","ilyaa","ron","throd","uaaah","ooboshu","vulgtlagln",
        "ya-na-kadishtu","ep","goka","ah","ee","nog","kadishtu","ng"
    };
    const size_t N = sizeof(L) / sizeof(L[0]);
    uint32_t s = seed * 2654435761u + 0x9E3779B9u;
    std::string out;
    for (;;) {
        s = s * 1103515245u + 12345u;
        const char* w = L[(s >> 16) % N];
        size_t add = out.empty() ? strlen(w) : strlen(w) + 1;
        if (out.size() + add > maxBytes)
            break;
        if (!out.empty())
            out += ' ';
        out += w;
    }
    if (out.empty())
        out = "fhtagn";
    if (out[0] >= 'a' && out[0] <= 'z')
        out[0] = (char)(out[0] - 'a' + 'A');
    return out;
}

static std::vector<unsigned char> CodexFragment(unsigned int nHeight)
{
    std::vector<unsigned char> egg;
    if (nHeight < CODEX_DESCENT_START)
        return egg;
    const char* descent = DescentLine(nHeight);
    if (descent) {                       // milestone verse
        PushEgg(egg, CODEX_MILESTONE, descent, strlen(descent));
        return egg;
    }
    const std::string& corpus = CodexCorpus();
    size_t corpusLen = corpus.size();
    size_t totalChunks = (corpusLen + CODEX_CHUNK - 1) / CODEX_CHUNK;
    if (totalChunks == 0)
        return egg;
    size_t passIdx = (size_t)(nHeight - CODEX_ANCHOR);
    if (passIdx >= totalChunks) {
        // The canon is read in full; the Dreaming begins. R'lyehian forever.
        std::string verse = RlyehianVerse(nHeight, CODEX_CHUNK);
        PushEgg(egg, CODEX_DREAMING, verse.data(), verse.size());
        return egg;
    }
    uint32_t idx = (uint32_t)passIdx;            // Phase A: single pass, no wrap
    size_t start = (size_t)idx * CODEX_CHUNK;
    size_t n = std::min((size_t)CODEX_CHUNK, corpusLen - start);
    PushEgg(egg, idx, corpus.data() + start, n);
    return egg;
}

void IncrementExtraNonce(CBlock* pblock, CBlockIndex* pindexPrev, unsigned int& nExtraNonce)
{
    // Update nExtraNonce
    static uint256 hashPrevBlock;
    if (hashPrevBlock != pblock->hashPrevBlock)
    {
        nExtraNonce = 0;
        hashPrevBlock = pblock->hashPrevBlock;
    }
    ++nExtraNonce;
    unsigned int nHeight = pindexPrev->nHeight+1; // Height first in coinbase required for block.version=2
    std::vector<unsigned char> codex = CodexFragment(nHeight);
    if (!codex.empty())
        pblock->vtx[0].vin[0].scriptSig = (CScript() << nHeight << CBigNum(nExtraNonce) << codex) + COINBASE_FLAGS;
    else
        pblock->vtx[0].vin[0].scriptSig = (CScript() << nHeight << CBigNum(nExtraNonce)) + COINBASE_FLAGS;
    assert(pblock->vtx[0].vin[0].scriptSig.size() <= 100);

    pblock->hashMerkleRoot = pblock->BuildMerkleTree();
}

// Fill the reserved OFFSIG output with a Conclave signature when mining inside the
// signed window. Returns false if we are in the window but hold no authorized key
// (caller should then not mine this block). Must run AFTER IncrementExtraNonce, as
// it depends on (and rewrites) the merkle root.
// Non-static as of v2.0.0-rc3: also called from rpcmining.cpp::getblocktemplate
// so Miningcore/pool templates carry a valid OFFSIG signature.
bool SignBlockIfNeeded(CBlock* pblock, int nHeight, CWallet* pwallet)
{
    if (!IsInSignedWindow(nHeight))
        return true;

    const std::vector<std::vector<unsigned char> >& keys = Params().ConclaveKeys();
    CKey signingKey;
    bool haveKey = false;
    for (unsigned int i = 0; i < keys.size() && !haveKey; i++) {
        CPubKey pub(keys[i]);
        if (pub.IsValid() && pwallet->GetKey(pub.GetID(), signingKey))
            haveKey = true;
    }
    if (!haveKey)
        return false;

    std::vector<unsigned char> dummy;
    int sigVout = FindOffSigOutput(*pblock, dummy);
    if (sigVout < 0)
        return false;

    uint256 h = OffSigningHash(*pblock, nHeight, sigVout);
    std::vector<unsigned char> vchSig;
    if (!signingKey.Sign(h, vchSig))
        return false;

    std::vector<unsigned char> payload(6, 0);
    memcpy(&payload[0], "OFFSIG", 6);
    payload.insert(payload.end(), vchSig.begin(), vchSig.end());
    pblock->vtx[0].vout[sigVout].scriptPubKey = CScript() << OP_RETURN << payload;
    pblock->hashMerkleRoot = pblock->BuildMerkleTree();
    return true;
}

// v2.0.0: Rebuild the template's coinbase Miningcore-shape so external pools can serve
// it. Replaces vout[0]'s OP_TRUE dummy with the configured pool address, lays a fixed
// 8-byte extranonce placeholder inside scriptSig at a sentinel-marked offset, preserves
// the Codex chunk, and signs OFFSIG. The signature is extranonce-invariant (see
// OffSigningHash) so miners can vary the placeholder freely.
//
// Sentinel = 8 × 0xBB. Vanishingly unlikely to collide with any legitimate byte in
// the serialized coinbase (height varint is small, /P2SH/ + tag are ASCII, codex
// payload is ASCII Lovecraft corpus, all amounts/sequences are bounded). Caller
// reads extranonceOffset and splits serializedCoinbase there.
bool BuildPoolCoinbase(CBlock* pblock, int nHeight, CWallet* pwallet,
                       const std::string& poolAddrStr, const std::string& tag,
                       std::vector<unsigned char>& serializedCoinbase,
                       size_t& extranonceOffset)
{
    if (poolAddrStr.empty() || pblock == NULL || pblock->vtx.empty())
        return false;

    CBitcoinAddress addr(poolAddrStr);
    if (!addr.IsValid())
        return false;
    CScript poolScript;
    poolScript.SetDestination(addr.Get());

    pblock->vtx[0].vout[0].scriptPubKey = poolScript;

    static const unsigned char SENTINEL[8] = {
        0xBB, 0xBB, 0xBB, 0xBB, 0xBB, 0xBB, 0xBB, 0xBB
    };
    std::vector<unsigned char> sentinelVec(SENTINEL, SENTINEL + 8);

    CScript scriptSig;
    scriptSig << nHeight;
    scriptSig << sentinelVec;
    std::vector<unsigned char> codex = CodexFragment(nHeight);
    if (!codex.empty())
        scriptSig << codex;
    if (!tag.empty()) {
        std::vector<unsigned char> tagVec(tag.begin(), tag.end());
        scriptSig << tagVec;
    }
    if (scriptSig.size() > 100)
        return false;

    pblock->vtx[0].vin[0].scriptSig = scriptSig;
    pblock->hashMerkleRoot = pblock->BuildMerkleTree();

    if (!SignBlockIfNeeded(pblock, nHeight, pwallet))
        return false;

    CDataStream ss(SER_NETWORK, PROTOCOL_VERSION);
    ss << pblock->vtx[0];
    serializedCoinbase.assign(ss.begin(), ss.end());

    extranonceOffset = (size_t)-1;
    for (size_t i = 0; i + 8 <= serializedCoinbase.size(); i++) {
        if (memcmp(&serializedCoinbase[i], SENTINEL, 8) == 0) {
            extranonceOffset = i;
            break;
        }
    }
    if (extranonceOffset == (size_t)-1)
        return false;

    return true;
}


void FormatHashBuffers(CBlock* pblock, char* pmidstate, char* pdata, char* phash1)
{
    //
    // Pre-build hash buffers
    //
    struct
    {
        struct unnamed2
        {
            int nVersion;
            uint256 hashPrevBlock;
            uint256 hashMerkleRoot;
            unsigned int nTime;
            unsigned int nBits;
            unsigned int nNonce;
        }
        block;
        unsigned char pchPadding0[64];
        uint256 hash1;
        unsigned char pchPadding1[64];
    }
    tmp;
    memset(&tmp, 0, sizeof(tmp));

    tmp.block.nVersion       = pblock->nVersion;
    tmp.block.hashPrevBlock  = pblock->hashPrevBlock;
    tmp.block.hashMerkleRoot = pblock->hashMerkleRoot;
    tmp.block.nTime          = pblock->nTime;
    tmp.block.nBits          = pblock->nBits;
    tmp.block.nNonce         = pblock->nNonce;

    FormatHashBlocks(&tmp.block, sizeof(tmp.block));
    FormatHashBlocks(&tmp.hash1, sizeof(tmp.hash1));

    // Byte swap all the input buffer
    for (unsigned int i = 0; i < sizeof(tmp)/4; i++)
        ((unsigned int*)&tmp)[i] = ByteReverse(((unsigned int*)&tmp)[i]);

    // Precalc the first half of the first hash, which stays constant
    SHA256Transform(pmidstate, &tmp.block, pSHA256InitState);

    memcpy(pdata, &tmp.block, 128);
    memcpy(phash1, &tmp.hash1, 64);
}

#ifdef ENABLE_WALLET
//////////////////////////////////////////////////////////////////////////////
//
// Internal miner
//
double dHashesPerSec = 0.0;
int64_t nHPSTimerStart = 0;

//
// ScanHash scans nonces looking for a hash with at least some zero bits.
// It operates on big endian data.  Caller does the byte reversing.
// All input buffers are 16-byte aligned.  nNonce is usually preserved
// between calls, but periodically or if nNonce is 0xffff0000 or above,
// the block is rebuilt and nNonce starts over at zero.
//
CBlockTemplate* CreateNewBlockWithKey(CReserveKey& reservekey)
{
    // Operator override: if -miningaddress=<Qaddr> is set in offerings.conf,
    // pay the coinbase to that fixed address instead of consuming a wallet
    // keypool entry per block. Lets solo miners consolidate rewards onto a
    // single leaderboard row instead of rotating a fresh address each block.
    // Falls back to the historical CReserveKey path on empty/invalid value.
    std::string strMiningAddress = GetArg("-miningaddress", "");
    if (!strMiningAddress.empty()) {
        CBitcoinAddress addr(strMiningAddress);
        if (addr.IsValid()) {
            CScript scriptPubKey;
            scriptPubKey.SetDestination(addr.Get());
            return CreateNewBlock(scriptPubKey);
        }
        LogPrintf("OfferingsMiner: -miningaddress=%s is not a valid Offerings address; falling back to wallet key\n", strMiningAddress);
    }

    CPubKey pubkey;
    if (!reservekey.GetReservedKey(pubkey))
        return NULL;

    CScript scriptPubKey = CScript() << pubkey << OP_CHECKSIG;
    return CreateNewBlock(scriptPubKey);
}

bool CheckWork(CBlock* pblock, CWallet& wallet, CReserveKey& reservekey)
{
    uint256 hash = pblock->GetHash();
    uint256 hashTarget = CBigNum().SetCompact(pblock->nBits).getuint256();

    if (hash > hashTarget)
        return false;

    //// debug print
    LogPrintf("OfferingsMiner:\n");
    LogPrintf("proof-of-work found  \n  hash: %s  \ntarget: %s\n", hash.GetHex(), hashTarget.GetHex());
    pblock->print();
    LogPrintf("generated %s\n", FormatMoney(pblock->vtx[0].vout[0].nValue));

    // Found a solution
    {
        LOCK(cs_main);
        if (pblock->hashPrevBlock != chainActive.Tip()->GetBlockHash())
            return error("OfferingsMiner : generated block is stale");

        // Remove key from key pool
        reservekey.KeepKey();

        // Track how many getdata requests this block gets
        {
            LOCK(wallet.cs_wallet);
            wallet.mapRequestCount[pblock->GetHash()] = 0;
        }

        // Process this block the same as if we had received it from another node
        CValidationState state;
        if (!ProcessBlock(state, NULL, pblock))
            return error("OfferingsMiner : ProcessBlock, block not accepted");
    }

    return true;
}

void static BitcoinMiner(CWallet *pwallet)
{
    LogPrintf("OfferingsMiner started\n");
    SetThreadPriority(THREAD_PRIORITY_LOWEST);
    RenameThread("bitcoin-miner");

    // Each thread has its own key and counter
    CReserveKey reservekey(pwallet);
    unsigned int nExtraNonce = 0;
    
    CBlockIndex* pindexPrev = NULL;
        
    if (Params().NetworkID() == CChainParams::MAIN)
    {
        // Wait for peers, but don't block on tip-not-advancing for the Restoration
        // bootstrap: the chain has been stalled since 2015 and there is no upstream
        // miner to break the deadlock. Once peers are present we proceed; the main
        // loop has its own 5-minute stale-tip timeout to avoid wasting cycles.
        //
        // Testnet and regtest mine without peers — testnet is for development /
        // qa exercising, regtest is single-node by definition. The pre-bipsoft
        // version exempted only regtest; that left a fresh testnet seed node
        // unable to mine its own first block. See #38.
        pindexPrev = chainActive.Tip();
        while (vNodes.empty())
        {
            MilliSleep(1000);
            boost::this_thread::interruption_point();
        }
    }

    try { while (true) {

        if (Params().NetworkID() == CChainParams::MAIN)
        {
            // Restoration bootstrap: the original guard waited on
            // IsInitialBlockDownload() and a 5-minute fresh-tip window. Both are wrong
            // for a chain dead since 2015 sitting BELOW its own hardcoded checkpoint
            // (984023), where IBD never clears and no surviving peer can serve the
            // missing blocks. We only pause while peers feed us a strictly newer tip.
            // Same testnet/regtest exemption as the initial peer-wait above (#38).
            while ( vNodes.empty() ||
                    (pindexPrev != chainActive.Tip()) )
            {
                pindexPrev = chainActive.Tip();
                MilliSleep(1000);
                boost::this_thread::interruption_point();
            }
        }
                
        //
        // Create new block
        //
        unsigned int nTransactionsUpdatedLast = mempool.GetTransactionsUpdated();
        { LOCK(cs_main); pindexPrev = chainActive.Tip(); }

        auto_ptr<CBlockTemplate> pblocktemplate(CreateNewBlockWithKey(reservekey));
        if (!pblocktemplate.get())
            return;
        CBlock *pblock = &pblocktemplate->block;
        IncrementExtraNonce(pblock, pindexPrev, nExtraNonce);
        if (!SignBlockIfNeeded(pblock, pindexPrev->nHeight + 1, pwallet)) {
            LogPrintf("OfferingsMiner: in Conclave signed window but no authorized key (wallet locked?); pausing\n");
            MilliSleep(5000);
            continue;
        }

        LogPrintf("Running OfferingsMiner with %u transactions in block (%u bytes)\n", pblock->vtx.size(),
               ::GetSerializeSize(*pblock, SER_NETWORK, PROTOCOL_VERSION));

        //
        // Search
        //
        uint256 hash;
        uint256 hashTarget = CBigNum().SetCompact(pblock->nBits).getuint256();
        int64_t nStart = GetTime();
        while (true)
        {

            hash = pblock->GetHash();
            
            // Check if something found
            if (hash <= hashTarget)
            {
                // Found a solution
                SetThreadPriority(THREAD_PRIORITY_NORMAL);
                CheckWork(pblock, *pwallet, reservekey);
                SetThreadPriority(THREAD_PRIORITY_LOWEST);

                // In regression test mode, stop mining after a block is found. This
                // allows developers to controllably generate a block on demand.
                if (Params().NetworkID() == CChainParams::REGTEST)
                    throw boost::thread_interrupted();

                break;
            }
            ++pblock->nNonce;

            // Meter hashes/sec
            static int64_t nHashCounter;
            if (nHPSTimerStart == 0)
            {
                nHPSTimerStart = GetTimeMillis();
                nHashCounter = 0;
            }
            else
                nHashCounter += 1;
            if (GetTimeMillis() - nHPSTimerStart > 4000)
            {
                static CCriticalSection cs;
                {
                    LOCK(cs);
                    if (GetTimeMillis() - nHPSTimerStart > 4000)
                    {
                        dHashesPerSec = 1000.0 * nHashCounter / (GetTimeMillis() - nHPSTimerStart);
                        nHPSTimerStart = GetTimeMillis();
                        nHashCounter = 0;
                        static int64_t nLogTime;
                        if (GetTime() - nLogTime > 30 * 60)
                        {
                            nLogTime = GetTime();
                            LogPrintf("hashmeter %6.0f khash/s\n", dHashesPerSec/1000.0);
                        }
                    }
                }
            }

            // Check for stop or if block needs to be rebuilt
            boost::this_thread::interruption_point();
            if (vNodes.empty() && Params().NetworkID() != CChainParams::REGTEST)
                break;
            if (pblock->nNonce >= 0xffff0000)
                break;
            if (mempool.GetTransactionsUpdated() != nTransactionsUpdatedLast && GetTime() - nStart > 60)
                break;
            // Detect a tip change so we abandon stale work — but NEVER read
            // chainActive unlocked. The connection thread reallocates chainActive's
            // internal vector under cs_main when a block connects; an unlocked read
            // here races and segfaults (CChain::Tip()). TRY_LOCK keeps the miner
            // non-blocking: if the connection thread holds cs_main we simply skip
            // this check for one iteration instead of reading freed memory.
            {
                bool fTipChanged = false;
                {
                    TRY_LOCK(cs_main, lockMain);
                    if (lockMain)
                        fTipChanged = (pindexPrev != chainActive.Tip());
                }
                if (fTipChanged)
                    break;
            }

            // Update nTime every few seconds
            UpdateTime(*pblock, pindexPrev);
            // nBlockTime = ByteReverse(pblock->nTime);
            if (TestNet())
            {
                // Changing pblock->nTime can change work required on testnet:
                // nBlockBits = ByteReverse(pblock->nBits);
                hashTarget = CBigNum().SetCompact(pblock->nBits).getuint256();
            }
        }
    } }
    catch (boost::thread_interrupted)
    {
        LogPrintf("OfferingsMiner terminated\n");
        throw;
    }
}

void GenerateBitcoins(bool fGenerate, CWallet* pwallet, int nThreads)
{
    static boost::thread_group* minerThreads = NULL;

    if (nThreads < 0) {
        if (Params().NetworkID() == CChainParams::REGTEST)
            nThreads = 1;
        else
            nThreads = boost::thread::hardware_concurrency();
    }

    if (minerThreads != NULL)
    {
        minerThreads->interrupt_all();
        delete minerThreads;
        minerThreads = NULL;
    }

    if (nThreads == 0 || !fGenerate)
        return;

    minerThreads = new boost::thread_group();
    for (int i = 0; i < nThreads; i++)
        minerThreads->create_thread(boost::bind(&BitcoinMiner, pwallet));
}

#endif

