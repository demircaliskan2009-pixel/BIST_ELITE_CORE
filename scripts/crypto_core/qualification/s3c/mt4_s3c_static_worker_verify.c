/*
 * MT4-S3C P0 STATIC WORKER VERIFICATION CALL.  Qualification infrastructure only.
 *
 * ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 20.4, 30.
 * BUNDLE ENTRY 15 of the exact 16-entry qualification source bundle (V9 SECTION 8).
 *
 * WHAT THIS TRANSLATION UNIT IS.  It is the single bounded BLS verification call the worker makes,
 * reusing the governed verify-call contract of the merged S3A shim BYTE FOR BYTE: the same
 * blst_core_verify_pk_in_g2 call with hash_or_encode true, the exact 32-byte digest, the
 * compile-time file-scope Quicknet DST and no augmentation (V9 SECTION 9 R4, SECTION 30 point 5).
 *
 * NO CRYPTOGRAPHIC PRIMITIVE IS AUTHORED HERE.  The worker links the PINNED blst static library and
 * this project-owned shim logic.  Nothing in this file implements field arithmetic, hashing, curve
 * operations or pairings.
 *
 * NOTHING IS CALLER-SELECTABLE.  The DST, curve, scheme, group orientation, hash mode and
 * augmentation are compile-time file-scope constants.  There is no field in the frozen 184-byte
 * request through which a caller could select cryptographic behaviour, and that is provable by
 * reading the request layout with no build at all (V9 20.2).
 *
 * THE GOVERNED STATUS TAXONOMY IS NEVER COLLAPSED.  This function returns one of the exact 0..11
 * codes governed by src/crypto_core/validation/machine_time_drand_quicknet_verifier_profile.py,
 * whose _verifier_contract_binding() fails closed unless the taxonomy is exactly tuple(range(12)).
 * A boolean is NEVER returned and NEVER persisted as evidence: collapsing the taxonomy destroys the
 * subgroup and encoding causality that S3A's Lane-A matrix exists to prove (V9 20.4).
 *
 * WHY THERE IS NO NULL CHECK AND NO LENGTH CHECK.  Codes 1 NULL_INPUT and 2 BAD_LENGTH are
 * STRUCTURALLY UNREACHABLE through WIRE_PROTOCOL_V1 (V9 20.4): the three pointers this function
 * receives are interior pointers into a fixed in-image array that is never null, and the encoded
 * lengths are the compile-time constants 96, 48 and 32 because the frame is fixed-length.  The
 * checks are omitted BECAUSE the conditions cannot arise, not to save work.  They remain members of
 * the governed taxonomy, which must equal range(12) exactly; a response carrying 1 or 2 is
 * therefore an internal contract break and is adjudicated as WORKER_RESPONSE_PROTOCOL_VIOLATION,
 * never as a crypto result (permanent test PT-421).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "blst.h"

/*
 * The image links no libc, so <string.h> is not included.  memcmp is supplied by the worker
 * bootstrap translation unit (bundle entry 13) and declared here with the identical signature.
 */
int memcmp(const void *left, const void *right, unsigned long length);

/* Exact Quicknet wire sizes, transcribed from the S3B verifier profile (V9 SECTION 9 R6). */
#define MT4_S3C_PUBLIC_KEY_LEN 96
#define MT4_S3C_SIGNATURE_LEN 48
#define MT4_S3C_MESSAGE_DIGEST_LEN 32

/*
 * The governed bounded status taxonomy.  This is the ONLY numeric vocabulary this function returns.
 * Upstream BLST_ERROR values are mapped into it and are NEVER forwarded across the boundary.
 */
#define MT4_S3C_OK 0
#define MT4_S3C_NULL_INPUT 1
#define MT4_S3C_BAD_LENGTH 2
#define MT4_S3C_PK_BAD_ENCODING 3
#define MT4_S3C_PK_NON_CANONICAL 4
#define MT4_S3C_PK_INFINITY 5
#define MT4_S3C_PK_NOT_IN_GROUP 6
#define MT4_S3C_SIG_BAD_ENCODING 7
#define MT4_S3C_SIG_NON_CANONICAL 8
#define MT4_S3C_SIG_INFINITY 9
#define MT4_S3C_SIG_NOT_IN_GROUP 10
#define MT4_S3C_VERIFY_FAILED 11

/*
 * Compile-time fixed domain separation tag.  A file-scope constant, not a parameter: a caller
 * cannot supply, override or select a DST, a curve, a group orientation, a hash mode or an
 * augmentation through this boundary.
 */
static const byte MT4_S3C_QUICKNET_DST[] = "BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_";
#define MT4_S3C_QUICKNET_DST_LEN (sizeof(MT4_S3C_QUICKNET_DST) - 1)

int mt4_s3c_verify_quicknet_request(const uint8_t *public_key,
                                    const uint8_t *signature,
                                    const uint8_t *message_digest);

int mt4_s3c_verify_quicknet_request(const uint8_t *public_key,
                                    const uint8_t *signature,
                                    const uint8_t *message_digest)
{
    blst_p2_affine public_key_affine;
    blst_p1_affine signature_affine;
    byte public_key_recompressed[MT4_S3C_PUBLIC_KEY_LEN];
    byte signature_recompressed[MT4_S3C_SIGNATURE_LEN];
    BLST_ERROR signature_decode;
    BLST_ERROR verify_result;

    /*
     * 1. Compressed G2 public-key decode.  The G1 asymmetry below is deliberate and repo-verified:
     * pinned src/e2.c contains NO decode-time BLST_POINT_NOT_IN_GROUP return, so every G2 decode
     * failure here really is an encoding or curve failure, and G2 subgroup membership is decided by
     * the explicit gate in step 4.  The G1 mapping is NOT mirrored onto G2.
     */
    if (blst_p2_uncompress(&public_key_affine, public_key) != BLST_SUCCESS) {
        return MT4_S3C_PK_BAD_ENCODING;
    }

    /* 2. Recompress and byte-compare: proves the caller supplied the canonical wire form.
     *
     * STRUCTURALLY UNREACHABLE UNDER PINNED BLST (contract note only -- no behaviour change).
     * pinned src/e2.c clears the encoding bits and then requires each X component to be strictly
     * less than the field modulus, returning BLST_BAD_ENCODING otherwise.  Every non-canonical X is
     * therefore rejected by step 1 above as PK_BAD_ENCODING, and this comparison never observes a
     * decoded-but-non-canonical key.  MT4_S3C_PK_NON_CANONICAL stays in the legal taxonomy and this
     * branch stays exactly as written: the ABI is not renumbered, and the check remains correct for
     * any future library that does decode such a key. */
    blst_p2_affine_compress(public_key_recompressed, &public_key_affine);
    if (memcmp(public_key_recompressed, public_key, MT4_S3C_PUBLIC_KEY_LEN) != 0) {
        return MT4_S3C_PK_NON_CANONICAL;
    }

    /* 3. Reject the G2 identity. */
    if (blst_p2_affine_is_inf(&public_key_affine)) {
        return MT4_S3C_PK_INFINITY;
    }

    /* 4. Explicit G2 subgroup membership.  Never inferred from a later pairing result. */
    if (!blst_p2_affine_in_g2(&public_key_affine)) {
        return MT4_S3C_PK_NOT_IN_GROUP;
    }

    /*
     * 5. Compressed G1 signature decode.  The exact upstream result is captured rather than
     * collapsed, because pinned blst v0.3.17 distinguishes two different failures here.
     *
     * src/e1.c POINTonE1_Uncompress_Z ends with:
     *     return vec_is_zero(out->X, sizeof(out->X)) ? BLST_POINT_NOT_IN_GROUP : BLST_SUCCESS;
     * so the canonical X=0 encoding -- the curve points (0, +/-2) -- reconstructs successfully and
     * is then rejected by the DECODER itself on subgroup grounds.  That is a subgroup verdict, not a
     * malformed encoding, and it keeps its causal meaning across this boundary.
     *
     * Every other decode failure here (bad encoding, not on curve) stays bounded as
     * SIG_BAD_ENCODING.  Raw BLST_ERROR values never cross the boundary.
     */
    signature_decode = blst_p1_uncompress(&signature_affine, signature);
    if (signature_decode == BLST_POINT_NOT_IN_GROUP) {
        return MT4_S3C_SIG_NOT_IN_GROUP;
    }
    if (signature_decode != BLST_SUCCESS) {
        return MT4_S3C_SIG_BAD_ENCODING;
    }

    /* 6. Recompress and byte-compare.
     *
     * As with the G2 path above, MT4_S3C_SIG_NON_CANONICAL is structurally unreachable under pinned
     * blst: src/e1.c requires X < modulus during uncompress, so an out-of-range X is answered as
     * SIG_BAD_ENCODING before this comparison runs.  The branch and the numeric taxonomy are
     * deliberately left unchanged. */
    blst_p1_affine_compress(signature_recompressed, &signature_affine);
    if (memcmp(signature_recompressed, signature, MT4_S3C_SIGNATURE_LEN) != 0) {
        return MT4_S3C_SIG_NON_CANONICAL;
    }

    /* 7. Reject the G1 identity. */
    if (blst_p1_affine_is_inf(&signature_affine)) {
        return MT4_S3C_SIG_INFINITY;
    }

    /* 8. Explicit G1 subgroup membership. */
    if (!blst_p1_affine_in_g1(&signature_affine)) {
        return MT4_S3C_SIG_NOT_IN_GROUP;
    }

    /*
     * 9. Stable core verification: public key in G2, signature in G1, RFC 9380 hash-to-curve
     * (hash_or_encode = true) over the exact 32-byte Quicknet message digest, with the fixed
     * Quicknet DST and no augmentation.
     */
    verify_result = blst_core_verify_pk_in_g2(&public_key_affine,
                                              &signature_affine,
                                              true,
                                              message_digest,
                                              MT4_S3C_MESSAGE_DIGEST_LEN,
                                              MT4_S3C_QUICKNET_DST,
                                              MT4_S3C_QUICKNET_DST_LEN,
                                              NULL,
                                              0);
    if (verify_result != BLST_SUCCESS) {
        return MT4_S3C_VERIFY_FAILED;
    }
    return MT4_S3C_OK;
}

/*
 * The unreachable members of the governed taxonomy are referenced here so that the taxonomy stays
 * complete and a future edit that renumbers a code fails the build.  No code path returns them.
 */
_Static_assert(MT4_S3C_NULL_INPUT == 1 && MT4_S3C_BAD_LENGTH == 2,
               "MT4_S3C taxonomy: 1 and 2 remain governed members even though the wire cannot reach them");
_Static_assert(MT4_S3C_VERIFY_FAILED == 11, "MT4_S3C taxonomy must remain the governed 0..11 range");
_Static_assert(MT4_S3C_QUICKNET_DST_LEN == 43, "MT4_S3C Quicknet DST length is fixed by the governed profile");
