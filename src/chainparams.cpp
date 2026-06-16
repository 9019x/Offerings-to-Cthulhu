// Copyright (c) 2010 Satoshi Nakamoto
// Copyright (c) 2009-2014 The Bitcoin developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "chainparams.h"

#include "assert.h"
#include "base58.h"
#include "core.h"
#include "protocol.h"
#include "script.h"
#include "util.h"

#include <boost/assign/list_of.hpp>
#include <stdint.h>

using namespace boost::assign;

//
// Main network
//

unsigned int pnSeed[] =
{
    // Fixed-seed fallback for fresh Qt clients on first run with no peers.dat.
    // Each entry is the 4 IP bytes laid out in network-order in host memory
    // then read as a little-endian uint32; memcpy into in_addr.s_addr yields
    // the original A.B.C.D. Verify a new entry with:
    //   python3 -c 'import struct,ipaddress; \
    //     print("0x%08x" % struct.unpack("<I", \
    //     ipaddress.IPv4Address("A.B.C.D").packed)[0])'
    //
    // Inclusion criteria for any addition:
    //   1. IP must accept inbound P2P connections and complete a full
    //      version/verack handshake from outside the cluster. Outbound-only
    //      nodes (CGNAT, NATed home machines) do not belong here.
    //   2. Operator must be known and have explicitly opted in. The seed
    //      list is who a fresh client phones home to on first run; every
    //      operator we list can observe every new wallet's starting IP, so
    //      we don't bake in strangers regardless of how reachable they are.
    0x4a4fc69f,   // 159.198.79.74  — Conclave seed (seed1.23skidoo.info)
    0x06721441,   // 65.20.114.6    — Conclave seed (alternate)
    0xe8d12246,   // 70.34.209.232  — Conclave seed (alternate)
};

static const unsigned int timeMainGenesisBlock = 1379187075;
uint256 hashMainGenesisBlock("0x000006829ac5ad04fb30abfcbf6d927c67c30fc2f198fb0bdce5a0c914b091b5");
static CBigNum bnMainProofOfWorkLimit(~uint256(0) >> 20);

static const int64_t nGenesisBlockRewardCoin = 10000 * COIN;
static const int64_t nBlockRewardStartCoin = 5 * COIN;
static const int64_t nBlockRewardMinimumCoin = .01 * COIN;

class CMainParams : public CChainParams {
public:
    CMainParams() {
        // The message start string is designed to be unlikely to occur in normal data.
        // The characters are rarely used upper ASCII, not valid as UTF-8, and produce
        // a large 4-byte int at any alignment.
        pchMessageStart[0] = 0x03;
        pchMessageStart[1] = 0xa5;
        pchMessageStart[2] = 0xfe;
        pchMessageStart[3] = 0xdd;
        vAlertPubKey = ParseHex("044b612d1775814a3a07e9ec4209afed2884f6f5ede1d177da30b6b8f3327652b01f67708349a239cb701b226715680e9f31a4d3d0ca803b76f606335077fcd803");
        nDefaultPort = 20000;
        nRPCPort = 11928;
        bnProofOfWorkLimit = bnMainProofOfWorkLimit;
        nSubsidyHalvingInterval = 259200;

        // Build the genesis block. Note that the output of the genesis coinbase cannot
        // be spent as it did not originally exist in the database.
        const char* pszTimestamp = "ph'nglui mglw'nafh Cthulhu R'lyeh wgah'nagl fhtagn";
        CTransaction txNew;
        txNew.vin.resize(1);
        txNew.vout.resize(1);
        txNew.vin[0].scriptSig = CScript() << 486604799 << CBigNum(4) << vector<unsigned char>((const unsigned char*)pszTimestamp, (const unsigned char*)pszTimestamp + strlen(pszTimestamp));
        txNew.vout[0].nValue = nGenesisBlockRewardCoin;
        txNew.vout[0].scriptPubKey = CScript() << ParseHex("04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f") << OP_CHECKSIG;
        genesis.vtx.push_back(txNew);
        genesis.hashPrevBlock = 0;
        genesis.hashMerkleRoot = genesis.BuildMerkleTree();
        genesis.nVersion = 112;
        genesis.nTime    = timeMainGenesisBlock;
        genesis.nBits    = bnMainProofOfWorkLimit.GetCompact();
        genesis.nNonce   = 963992;

        hashGenesisBlock = genesis.GetHash();
        assert(hashGenesisBlock == hashMainGenesisBlock);
        assert(genesis.hashMerkleRoot == uint256("0xb3f4e4e9bbae6f63a0693661c510a33dca69489bfff65a88aaeb85f30d30b485"));

        vSeeds.push_back(CDNSSeedData("seed1.23skidoo.info", "seed1.23skidoo.info"));
        vSeeds.push_back(CDNSSeedData("seed2.23skidoo.info", "seed2.23skidoo.info"));
        vSeeds.push_back(CDNSSeedData("seed3.23skidoo.info", "seed3.23skidoo.info"));
        vSeeds.push_back(CDNSSeedData("seed4.23skidoo.info", "seed4.23skidoo.info"));
        vSeeds.push_back(CDNSSeedData("seed5.23skidoo.info", "seed5.23skidoo.info"));
        vSeeds.push_back(CDNSSeedData("seed6.23skidoo.info", "seed6.23skidoo.info"));
        vSeeds.push_back(CDNSSeedData("seed7.23skidoo.info", "seed7.23skidoo.info"));
        vSeeds.push_back(CDNSSeedData("seed8.23skidoo.info", "seed8.23skidoo.info"));
        vSeeds.push_back(CDNSSeedData("seed9.23skidoo.info", "seed9.23skidoo.info"));
        vSeeds.push_back(CDNSSeedData("seed10.23skidoo.info", "seed10.23skidoo.info"));

        base58Prefixes[PUBKEY_ADDRESS] = list_of(58).convert_to_container<std::vector<unsigned char> >();
        base58Prefixes[SCRIPT_ADDRESS] = list_of(9).convert_to_container<std::vector<unsigned char> >();
        base58Prefixes[SECRET_KEY] = list_of(186).convert_to_container<std::vector<unsigned char> >();
        base58Prefixes[EXT_PUBLIC_KEY] = list_of(0x04)(0x88)(0xB2)(0x1E).convert_to_container<std::vector<unsigned char> >();
        base58Prefixes[EXT_SECRET_KEY] = list_of(0x04)(0x88)(0xAD)(0xE4).convert_to_container<std::vector<unsigned char> >();

        // ===== Restoration Hardfork v2.0.0 — BtcBob / SubGenius.Finance, 2026 =====
        // Fork activates at block 1,000,000. From that height forward:
        //   1) Subsidy locks to 1.5 OFF/block forever (the folklore made real;
        //      the prior `nSubsidy >>= nHeight/259200` curve would have decayed
        //      to the 0.01 OFF floor by ~block 3,113,000).
        //   2) Coinbase MUST contain an output paying exactly 1/8 of subsidy
        //      (0.1875 OFF) to the Conclave Treasury 2-of-3 multisig P2SH.
        //   3) Block 1,000,000 exactly carries an additional 150,000 OFF
        //      Restoration Tithe to the Treasury.
        //   4) Any transaction with an output paying a banned attacker script
        //      is rejected — finishing billotronic's never-shipped 2018
        //      hardfork (BCT #697): "Could easily hardfork and ban the 51'ed
        //      coins. It's a shitty thing to do, but so is 51% attacks."
        //
        // BCT 294383 citations:
        //   #697  billotronic, 2018-09-19  — proposed the burn
        //   #699  vampirus,    2018-11-21  — named the 8 attacker addresses
        //   #702  vampirus,    2018-12-28  — Cryptopia delist for chains with
        //                                     no 51% protection
        nRestorationForkHeight = 1000000;
        nPostForkSubsidy       = 15 * COIN / 10;        // 1.5 OFF
        nTreasuryNum           = 1;
        nTreasuryDen           = 8;
        nRestorationTithe      = 150000 * COIN;

        // Conclave Treasury — 2-of-3 P2SH multisig
        //   P2SH address: 4fZqDjscS9ANR59xNFJxZ2HmrhuDwWUJB4
        //   Redeem H160:  1bb03a89f2c713bd1beed4cd67934dbd6094b686
        //   Keys (any 2 of 3 required to spend):
        //     #1 Treasury Key A (hot, online)    pk 03129479…28b7adcde
        //     #2 Treasury Key B (hot, online)    pk 0244dbe9…578e059
        //     #3 Treasury Key C (cold, offline)  pk 02df218b…b99b2b4c
        scriptTreasury = CScript()
            << OP_HASH160
            << ParseHex("1bb03a89f2c713bd1beed4cd67934dbd6094b686")
            << OP_EQUAL;

        // Banned attacker scripts — BCT #699 (vampirus, 2018-11-21).
        // Each is the P2PKH scriptPubKey of one wallet that received the
        // 533,983-OFF May 2018 counterfeit print on the original chain.
        // Our chainstate (recovered from Wayback, tip block 966,413, June
        // 2015) PREDATES the attack by ~870K blocks — these addresses hold
        // ZERO in our UTXO set. The ban is a policy invariant against any
        // future chain-rewrite or resurrected pre-attack UTXO from re-
        // emerging value at these scripts.
        const char* bannedAddrs[] = {
            "QTLUPH9b4dRQdz9uKB7GreMvHPA8iyDoQY", //  93,036 OFF stolen
            "QeHkx6jFvStkzaVaSTtfPrSAwwrqMgauP8", //  72,856
            "QgynW4zGXyjhG3DQHn9vBuHwNp4c4xqtgM", //  68,372
            "QjfP4o7o2TszP5Ph4TmNVmktzDCjYkq2xj", //  66,770
            "QM8ZeuBDwrhya9BHQfNKifEzfwUhyh7Tji", //  65,388
            "Qb6jxfUmfWHh7XTTRWKBoiZ43sSNTJrw8J", //  60,562
            "QireWv3upmhVuRMcE6u7h81gmhWfiGEyTt", //  54,839
            "QSJU4tDNsZiaNcUuBWYcvjqKWoB8EHDVsT", //  52,160
        };                                       // -------
                                                 // 533,983 OFF total
        for (size_t i = 0; i < sizeof(bannedAddrs)/sizeof(*bannedAddrs); ++i) {
            CBitcoinAddress a(bannedAddrs[i]);
            assert(a.IsValid());
            CScript s; s.SetDestination(a.Get());
            setBannedAttackers.insert(s);
        }

        // ---- Conclave signed-mining window ----
        // From SignedWindowStart through OpenMiningHeight (inclusive), a block is
        // only valid if it carries a signature from one of the Conclave keys below.
        //
        // Window opens at 999,991 — the first Descent verse — so the entire 10-block
        // Descent (999991..1000000) plus the full canon transcription (1000001..1047248,
        // 47,248 chunks) plus ~2.4 days of post-canon buffer are consensus-protected
        // from outsider mining. Window closes at 1,050,666, on the project's xxx,666
        // numerological convention; after that Quark mining is permissionless again.
        // (Changed in v2.0.0-rc2 from previous bounds [1000000 .. 1057329].)
        nSignedWindowStart = 999991;
        nOpenMiningHeight  = 1050666;
        // Conclave keys — any one valid signature lets a block pass CheckConclaveSignature.
        // Three independent signers added 2026-06-03 for redundancy during the
        // Codex window; loss of any two still permits the third to keep the chain alive.
        vConclaveKeys.push_back(ParseHex(
            "0238efde05d567979485df6cd6dcf3af2606348a1e260eedf9a6464df57f46b111")); // Conclave Key #1
        vConclaveKeys.push_back(ParseHex(
            "027d7a1692dfb255925299a6114c3cf4a764aad7360548c60a2348a1d03abd4907")); // Conclave Key #2
        vConclaveKeys.push_back(ParseHex(
            "02a1c992ed9b6dc8ed3646cedc09b6075b13bfc957bb3bc0adf77c50c7e4193dfc")); // Conclave Key #3

        // Convert the pnSeeds array into usable address objects.
        for (unsigned int i = 0; i < ARRAYLEN(pnSeed); i++)
        {
            // It'll only connect to one or two seed nodes because once it connects,
            // it'll get a pile of addresses with newer timestamps.
            // Seed nodes are given a random 'last seen time' of between one and two
            // weeks ago.
            const int64_t nOneWeek = 7*24*60*60;
            struct in_addr ip;
            memcpy(&ip, &pnSeed[i], sizeof(ip));
            CAddress addr(CService(ip, GetDefaultPort()));
            addr.nTime = GetTime() - GetRand(nOneWeek) - nOneWeek;
            vFixedSeeds.push_back(addr);
        }
    }

    virtual const CBlock& GenesisBlock() const { return genesis; }
    virtual Network NetworkID() const { return CChainParams::MAIN; }

    virtual const vector<CAddress>& FixedSeeds() const {
        return vFixedSeeds;
    }
protected:
    CBlock genesis;
    vector<CAddress> vFixedSeeds;
};
static CMainParams mainParams;


//
// Testnet (v3)
//
class CTestNetParams : public CMainParams {
public:
    CTestNetParams() {
        // The message start string is designed to be unlikely to occur in normal data.
        // The characters are rarely used upper ASCII, not valid as UTF-8, and produce
        // a large 4-byte int at any alignment.
        pchMessageStart[0] = 0x01;
        pchMessageStart[1] = 0x1a;
        pchMessageStart[2] = 0x39;
        pchMessageStart[3] = 0xf7;
        vAlertPubKey = ParseHex("04218bc3f08237baa077cb1b0e5a81695fcf3f5b4e220b4ad274d05a31d762dd4e191efa7b736a24a32d6fd9ac1b5ebb2787c70e9dfad0016a8b32f7bd2520dbd5");
        nDefaultPort = 21973;
        nRPCPort = 18372;
        strDataDir = "testnet3";

        // Testnet uses a more lenient PoW limit than mainnet (>>20 → >>1) so the
        // genesis block can be re-mined with a small nonce and so a laptop CPU
        // can keep up with mining during testing. Real difficulty retargeting
        // (LWMA-3, DigiShield, KGW) still runs once blocks accumulate. See #38.
        bnProofOfWorkLimit = CBigNum(~uint256(0) >> 1);

        // Modified testnet genesis: timestamp re-anchored for a later start,
        // nBits derived from the new PoW limit, nNonce chosen to satisfy
        // CheckProofOfWork() under that limit. See #38.
        genesis.nTime  = 1373481000;
        genesis.nBits  = bnProofOfWorkLimit.GetCompact();
        genesis.nNonce = 0;
        hashGenesisBlock = genesis.GetHash();
        assert(hashGenesisBlock == uint256("0x6f66b770406b4f72c9aae8bd8f60fbc535cc996f683980d2885319ad862fabc9"));

        vFixedSeeds.clear();
        vSeeds.clear();
        vSeeds.push_back(CDNSSeedData("testnet-seed.23skidoo.info",
                                      "testnet-seed.23skidoo.info"));

        base58Prefixes[PUBKEY_ADDRESS] = list_of(119).convert_to_container<std::vector<unsigned char> >();
        base58Prefixes[SCRIPT_ADDRESS] = list_of(199).convert_to_container<std::vector<unsigned char> >();
        base58Prefixes[SECRET_KEY] = list_of(247).convert_to_container<std::vector<unsigned char> >();
        base58Prefixes[EXT_PUBLIC_KEY] = list_of(0x04)(0x35)(0x87)(0xCF).convert_to_container<std::vector<unsigned char> >();
        base58Prefixes[EXT_SECRET_KEY] = list_of(0x04)(0x35)(0x83)(0x94).convert_to_container<std::vector<unsigned char> >();
    }
    virtual Network NetworkID() const { return CChainParams::TESTNET; }
};
static CTestNetParams testNetParams;


//
// Regression test
//
class CRegTestParams : public CTestNetParams {
public:
    CRegTestParams() {
        pchMessageStart[0] = 0xfa;
        pchMessageStart[1] = 0xbf;
        pchMessageStart[2] = 0xb5;
        pchMessageStart[3] = 0xda;
        nSubsidyHalvingInterval = 150;
        bnProofOfWorkLimit = CBigNum(~uint256(0) >> 1);
        genesis.nTime = 1296688602;
        genesis.nBits = 0x207fffff;
        genesis.nNonce = 2;
        hashGenesisBlock = genesis.GetHash();
        nDefaultPort = 18444;
        strDataDir = "regtest";
        //assert(hashGenesisBlock == uint256("0x9cc7038a62931521a044f22acd7d9cf3e6f1f35d4e877ffe106b39e946f8000e"));

        vSeeds.clear();  // Regtest mode doesn't have any DNS seeds.
    }

    virtual bool RequireRPCPassword() const { return false; }
    virtual Network NetworkID() const { return CChainParams::REGTEST; }
};
static CRegTestParams regTestParams;

static CChainParams *pCurrentParams = &mainParams;

const CChainParams &Params() {
    return *pCurrentParams;
}

void SelectParams(CChainParams::Network network) {
    switch (network) {
        case CChainParams::MAIN:
            pCurrentParams = &mainParams;
            break;
        case CChainParams::TESTNET:
            pCurrentParams = &testNetParams;
            break;
        case CChainParams::REGTEST:
            pCurrentParams = &regTestParams;
            break;
        default:
            assert(false && "Unimplemented network");
            return;
    }
}

bool SelectParamsFromCommandLine() {
    bool fRegTest = GetBoolArg("-regtest", false);
    bool fTestNet = GetBoolArg("-testnet", false);

    if (fTestNet && fRegTest) {
        return false;
    }

    if (fRegTest) {
        SelectParams(CChainParams::REGTEST);
    } else if (fTestNet) {
        SelectParams(CChainParams::TESTNET);
    } else {
        SelectParams(CChainParams::MAIN);
    }
    return true;
}
