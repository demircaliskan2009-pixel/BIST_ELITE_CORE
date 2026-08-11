/*
 * MT4-S3A qualification-only narrow C ABI over official supranational/blst v0.3.17.
 *
 * SCOPE.  This translation unit exists solely to QUALIFY a candidate verification boundary in CI.
 * It is not wired into any crypto_core product module, it admits no dependency, it selects no
 * verifier profile, and it promotes no readiness or connector state.  Building it proves that the
 * Quicknet orientation can be verified through stable blst C symbols on Windows x64 and Linux x64;
 * it proves nothing about provider reachability, machine time, timestamp origin or quorum.
 *
 * UPSTREAM.  supranational/blst, release v0.3.17, commit
 * 54e6e55674722fc2797ebb4bbb71b26d881eb4b8, Apache-2.0.  Only the stable blst.h surface is used.
 * blst_aux.h is deliberately NOT included: no experimental interface may carry a load-bearing
 * qualification claim.
 *
 * QUICKNET CONTRACT (fixed at compile time, never caller-selectable):
 *   scheme      bls-unchained-g1-rfc9380
 *   curve       BLS12-381
 *   public key  G2, compressed, exactly 96 bytes
 *   signature   G1, compressed, exactly 48 bytes
 *   message     SHA256(uint64_big_endian(round)), exactly 32 bytes
 *   DST         BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_
 *   augmentation  none
 *
 * DETERMINISM.  The entry point performs no allocation owned across the ABI, exposes no blst
 * object, keeps no mutable global state, and touches no network, clock, environment, filesystem or
 * randomness.  Every path returns an explicit bounded status; no failure can be represented as
 * success, and no upstream BLST_ERROR integer is exposed through this ABI.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "blst.h"

#if defined(_WIN32)
#define MT4_S3A_EXPORT __declspec(dllexport)
#else
#define MT4_S3A_EXPORT __attribute__((visibility("default")))
#endif

/* Exact Quicknet wire sizes.  Nothing else is accepted. */
#define MT4_S3A_PUBLIC_KEY_LEN 96
#define MT4_S3A_SIGNATURE_LEN 48
#define MT4_S3A_MESSAGE_DIGEST_LEN 32

/*
 * Bounded qualification status taxonomy.  This is the ONLY numeric vocabulary crossing the ABI.
 * Upstream BLST_ERROR values are mapped into it and never forwarded.
 */
#define MT4_S3A_OK 0
#define MT4_S3A_NULL_INPUT 1
#define MT4_S3A_BAD_LENGTH 2
#define MT4_S3A_PK_BAD_ENCODING 3
#define MT4_S3A_PK_NON_CANONICAL 4
#define MT4_S3A_PK_INFINITY 5
#define MT4_S3A_PK_NOT_IN_GROUP 6
#define MT4_S3A_SIG_BAD_ENCODING 7
#define MT4_S3A_SIG_NON_CANONICAL 8
#define MT4_S3A_SIG_INFINITY 9
#define MT4_S3A_SIG_NOT_IN_GROUP 10
#define MT4_S3A_VERIFY_FAILED 11

/*
 * Compile-time fixed domain separation tag.  It is a file-scope constant, not a parameter: a caller
 * cannot supply, override or select a DST, a curve, a group orientation, a hash mode or an
 * augmentation through this boundary.
 */
static const byte MT4_S3A_QUICKNET_DST[] = "BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_";
#define MT4_S3A_QUICKNET_DST_LEN (sizeof(MT4_S3A_QUICKNET_DST) - 1)

/*
 * QUALIFICATION SCAFFOLDING -- NOT part of the verification contract.
 *
 * Emits the compressed BLS12-381 G2 generator taken from the stable upstream constant
 * ``BLS12_381_G2``.  Lane A needs a deterministic, offline, licence-clean G2 point that is genuinely
 * in the prime-order subgroup so the G1 signature gate can be reached at all: the verification
 * sequence proves the public key first, so an official G1 low-order vector can only be pushed
 * against the signature gate behind a valid public key.
 *
 * This helper performs NO verification, decodes nothing supplied by a caller, and carries no trust
 * decision.  It exists solely so Lane A never has to embed a point literal or borrow Lane-B
 * production bytes.
 */
MT4_S3A_EXPORT int mt4_s3a_qualification_g2_generator_compressed(uint8_t *out, size_t out_len)
{
    if (out == NULL) {
        return MT4_S3A_NULL_INPUT;
    }
    if (out_len != MT4_S3A_PUBLIC_KEY_LEN) {
        return MT4_S3A_BAD_LENGTH;
    }
    blst_p2_affine_compress(out, &BLS12_381_G2);
    return MT4_S3A_OK;
}

/*
 * Verify one Quicknet beacon signature.
 *
 * Returns exactly one MT4_S3A_* status.  Inputs are read-only and are never retained.
 */
MT4_S3A_EXPORT int mt4_s3a_verify_quicknet_bls(const uint8_t *public_key,
                                               size_t public_key_len,
                                               const uint8_t *signature,
                                               size_t signature_len,
                                               const uint8_t *message_digest,
                                               size_t message_digest_len)
{
    blst_p2_affine public_key_affine;
    blst_p1_affine signature_affine;
    byte public_key_recompressed[MT4_S3A_PUBLIC_KEY_LEN];
    byte signature_recompressed[MT4_S3A_SIGNATURE_LEN];
    BLST_ERROR verify_result;

    /* 1. NULL and exact-length gates run before any cryptographic work. */
    if (public_key == NULL || signature == NULL || message_digest == NULL) {
        return MT4_S3A_NULL_INPUT;
    }
    if (public_key_len != MT4_S3A_PUBLIC_KEY_LEN) {
        return MT4_S3A_BAD_LENGTH;
    }
    if (signature_len != MT4_S3A_SIGNATURE_LEN) {
        return MT4_S3A_BAD_LENGTH;
    }
    if (message_digest_len != MT4_S3A_MESSAGE_DIGEST_LEN) {
        return MT4_S3A_BAD_LENGTH;
    }

    /* 2. Compressed G2 public-key decode. */
    if (blst_p2_uncompress(&public_key_affine, public_key) != BLST_SUCCESS) {
        return MT4_S3A_PK_BAD_ENCODING;
    }

    /* 3. Recompress and byte-compare: proves the caller supplied the canonical wire form. */
    blst_p2_affine_compress(public_key_recompressed, &public_key_affine);
    if (memcmp(public_key_recompressed, public_key, MT4_S3A_PUBLIC_KEY_LEN) != 0) {
        return MT4_S3A_PK_NON_CANONICAL;
    }

    /* 4. Reject the G2 identity. */
    if (blst_p2_affine_is_inf(&public_key_affine)) {
        return MT4_S3A_PK_INFINITY;
    }

    /* 5. Explicit G2 subgroup membership.  Never inferred from a later pairing result. */
    if (!blst_p2_affine_in_g2(&public_key_affine)) {
        return MT4_S3A_PK_NOT_IN_GROUP;
    }

    /* 6. Compressed G1 signature decode. */
    if (blst_p1_uncompress(&signature_affine, signature) != BLST_SUCCESS) {
        return MT4_S3A_SIG_BAD_ENCODING;
    }

    /* 7. Recompress and byte-compare. */
    blst_p1_affine_compress(signature_recompressed, &signature_affine);
    if (memcmp(signature_recompressed, signature, MT4_S3A_SIGNATURE_LEN) != 0) {
        return MT4_S3A_SIG_NON_CANONICAL;
    }

    /* 8. Reject the G1 identity. */
    if (blst_p1_affine_is_inf(&signature_affine)) {
        return MT4_S3A_SIG_INFINITY;
    }

    /* 9. Explicit G1 subgroup membership. */
    if (!blst_p1_affine_in_g1(&signature_affine)) {
        return MT4_S3A_SIG_NOT_IN_GROUP;
    }

    /*
     * 10. Stable core verification: public key in G2, signature in G1, RFC 9380 hash-to-curve
     * (hash_or_encode = true) over the exact 32-byte Quicknet message digest, with the fixed
     * Quicknet DST and no augmentation.
     */
    verify_result = blst_core_verify_pk_in_g2(&public_key_affine,
                                              &signature_affine,
                                              true,
                                              message_digest,
                                              MT4_S3A_MESSAGE_DIGEST_LEN,
                                              MT4_S3A_QUICKNET_DST,
                                              MT4_S3A_QUICKNET_DST_LEN,
                                              NULL,
                                              0);
    if (verify_result != BLST_SUCCESS) {
        return MT4_S3A_VERIFY_FAILED;
    }
    return MT4_S3A_OK;
}
