/*
 * quark9_cli — minimal Quark Hash9 CLI for qa/rpc-tests.
 *
 * Reads a hex string from argv[1] (no 0x prefix), prints the Quark Hash9
 * of those bytes as 64 hex chars (little-endian byte order, same as the
 * uint256 byte representation OFF's PoW comparison uses internally).
 *
 * Reuses OFF's src/sph_*.h and src/{blake,bmw,groestl,jh,keccak,skein}.c
 * implementations. Replicates src/hashblock.h::Hash9 exactly.
 *
 * Build:
 *   gcc -O2 -I../../../src -o quark9_cli quark9_cli.c \
 *       ../../../src/blake.c ../../../src/bmw.c ../../../src/groestl.c \
 *       ../../../src/jh.c ../../../src/keccak.c ../../../src/skein.c
 *
 * Usage:
 *   ./quark9_cli <hex-string>
 *   -> prints 64-char hex
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "sph_blake.h"
#include "sph_bmw.h"
#include "sph_groestl.h"
#include "sph_jh.h"
#include "sph_keccak.h"
#include "sph_skein.h"

static int hexchar(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int hex_to_bytes(const char *s, unsigned char *out, size_t out_max, size_t *out_len) {
    size_t L = strlen(s);
    if (L % 2 != 0) return -1;
    if (L / 2 > out_max) return -1;
    for (size_t i = 0; i < L; i += 2) {
        int hi = hexchar(s[i]);
        int lo = hexchar(s[i + 1]);
        if (hi < 0 || lo < 0) return -1;
        out[i / 2] = (unsigned char)((hi << 4) | lo);
    }
    *out_len = L / 2;
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: %s <hex>\n", argv[0]);
        return 2;
    }

    unsigned char data[8192];
    size_t data_len = 0;
    if (hex_to_bytes(argv[1], data, sizeof(data), &data_len) != 0) {
        fprintf(stderr, "bad hex input\n");
        return 2;
    }

    /* Per hashblock.h Hash9: mask = 8 as uint512 (LE), pn[0]=8.
     * In raw byte representation that's byte 0 = 0x08, all other bytes = 0.
     * Condition (hash[i] & mask) != 0 ↔ (hash[i].byte[0] & 0x08) != 0.
     * sphlib stores the digest in natural byte order (matching pn[] on LE),
     * so we just check byte 0.
     */

    sph_blake512_context     ctx_blake;
    sph_bmw512_context       ctx_bmw;
    sph_groestl512_context   ctx_groestl;
    sph_jh512_context        ctx_jh;
    sph_keccak512_context    ctx_keccak;
    sph_skein512_context     ctx_skein;

    unsigned char hash[9][64];

    /* round 1: blake */
    sph_blake512_init(&ctx_blake);
    sph_blake512(&ctx_blake, data, data_len);
    sph_blake512_close(&ctx_blake, hash[0]);

    /* round 2: bmw */
    sph_bmw512_init(&ctx_bmw);
    sph_bmw512(&ctx_bmw, hash[0], 64);
    sph_bmw512_close(&ctx_bmw, hash[1]);

    /* round 3: groestl-or-skein on hash[1] */
    if (hash[1][0] & 0x08) {
        sph_groestl512_init(&ctx_groestl);
        sph_groestl512(&ctx_groestl, hash[1], 64);
        sph_groestl512_close(&ctx_groestl, hash[2]);
    } else {
        sph_skein512_init(&ctx_skein);
        sph_skein512(&ctx_skein, hash[1], 64);
        sph_skein512_close(&ctx_skein, hash[2]);
    }

    /* round 4: groestl on hash[2] */
    sph_groestl512_init(&ctx_groestl);
    sph_groestl512(&ctx_groestl, hash[2], 64);
    sph_groestl512_close(&ctx_groestl, hash[3]);

    /* round 5: jh */
    sph_jh512_init(&ctx_jh);
    sph_jh512(&ctx_jh, hash[3], 64);
    sph_jh512_close(&ctx_jh, hash[4]);

    /* round 6: blake-or-bmw on hash[4] */
    if (hash[4][0] & 0x08) {
        sph_blake512_init(&ctx_blake);
        sph_blake512(&ctx_blake, hash[4], 64);
        sph_blake512_close(&ctx_blake, hash[5]);
    } else {
        sph_bmw512_init(&ctx_bmw);
        sph_bmw512(&ctx_bmw, hash[4], 64);
        sph_bmw512_close(&ctx_bmw, hash[5]);
    }

    /* round 7: keccak */
    sph_keccak512_init(&ctx_keccak);
    sph_keccak512(&ctx_keccak, hash[5], 64);
    sph_keccak512_close(&ctx_keccak, hash[6]);

    /* round 8: skein */
    sph_skein512_init(&ctx_skein);
    sph_skein512(&ctx_skein, hash[6], 64);
    sph_skein512_close(&ctx_skein, hash[7]);

    /* round 9: keccak-or-jh on hash[7] */
    if (hash[7][0] & 0x08) {
        sph_keccak512_init(&ctx_keccak);
        sph_keccak512(&ctx_keccak, hash[7], 64);
        sph_keccak512_close(&ctx_keccak, hash[8]);
    } else {
        sph_jh512_init(&ctx_jh);
        sph_jh512(&ctx_jh, hash[7], 64);
        sph_jh512_close(&ctx_jh, hash[8]);
    }

    /* trim256: low 32 bytes (pn[0..7]). On LE that's the first 32 bytes. */
    for (int i = 0; i < 32; i++) {
        printf("%02x", hash[8][i]);
    }
    printf("\n");
    return 0;
}
