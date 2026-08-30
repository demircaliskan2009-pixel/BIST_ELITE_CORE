/*
 * MT4-S3C P0 OFFLINE TEST-ONLY VECTOR GENERATOR.  Qualification infrastructure only.
 *
 * ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 8, 21.9, 39.
 * PATH N18.  DELIBERATELY NOT A SOURCE-BUNDLE ENTRY.
 *
 * WHY IT IS NOT IN THE BUNDLE, and the condition under which that exclusion would end.  Generation
 * is frozen as OFFLINE and ONE-TIME, outside the qualification jobs, so it cannot affect run
 * evidence.  The FIXTURE it produces IS bundle entry 16, and the fixture's provenance record binds
 * this generator's source and binary digests.  The exclusion is CONDITIONAL and still live: if any
 * future design makes generation participate in the run, this file MUST enter the bundle.
 *
 * WHAT IT PRODUCES.  The governed TEST-ONLY fixture: for each of the twenty-five cases, the exact
 * input bytes plus the architecture-frozen expected RESULT_CLASS and RESULT_CODE.
 *
 * THE EXPECTED CODES ARE NOT OBSERVED AND ADOPTED -- THEY ARE FROZEN AND PROVEN.  V9 21.9 is
 * explicit: the exact status pinned blst returns for a given malformed input is a property of the
 * pinned LIBRARY, and the architecture does not guess it.  This generator therefore carries the
 * frozen expectation for every case, calls the SAME governed verify contract the worker calls, and
 * REQUIRES the observed status to equal the frozen expectation.  IF PINNED BLST DOES NOT RETURN THE
 * INTENDED CODE, this program FAILS and the correct outcome is UNRESOLVED_P2 returned to the
 * controller.  It is never resolved by relabelling the case, by widening the expected set, or by
 * accepting "any non-zero code" -- and there is no code path here that could do any of those.
 *
 * CONSTRUCTION IS DETERMINISTIC BY DESIGN, NEVER BY BIT-FLIPPING.  Single-bit mutation is
 * explicitly NOT used for any crypto negative, because which status a flipped bit produces is not
 * determinate from the architecture.  Every secret is derived from a fixed input keying material
 * literal, so two runs of this program produce byte-identical output.
 *
 * THE VECTOR IS TEST-ONLY AND MUST NEVER BE RELABELLED (V9 SECTION 39).  It is
 * PROJECT_GENERATED_DETERMINISTIC_TEST_VECTOR.  It must never be labelled official, normative or
 * Quicknet, and must never be reinterpreted as FX-DRAND-QUICKNET.v1 authority.  It sets none of
 * fixture_corpus_admitted, fixture_corpus_loaded, fixture_corpus_verified, proof_verified,
 * randomness_verified, provider_operationally_approved or readiness_promoted.  No production beacon
 * byte is read, embedded or committed anywhere in this file.
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "blst.h"

int mt4_s3c_verify_quicknet_request(const uint8_t *public_key,
                                    const uint8_t *signature,
                                    const uint8_t *message_digest);

#define MT4_S3C_PK_LEN 96
#define MT4_S3C_SIG_LEN 48
#define MT4_S3C_DIGEST_LEN 32
#define MT4_S3C_REQUEST_FRAME_BYTES 184
#define MT4_S3C_MAX_CASE_INPUT_BYTES 512
#define MT4_S3C_CASE_COUNT 25
#define MT4_S3C_PARTIAL_PREFIX_BYTES 100

static const byte MT4_S3C_QUICKNET_DST[] = "BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_";
#define MT4_S3C_QUICKNET_DST_LEN (sizeof(MT4_S3C_QUICKNET_DST) - 1)

/* Frozen TEST-ONLY key material.  Not a beacon key, not a production key, not a secret. */
static const byte MT4_S3C_SIGNER_IKM[32] = "MT4-S3C-TEST-ONLY-VECTOR-V1-IKM!";
static const byte MT4_S3C_OTHER_IKM[32] = "MT4-S3C-TEST-ONLY-VECTOR-V1-IKM2";

/* Frozen TEST-ONLY round numbers.  The message transform is SHA256(uint64_big_endian(round)). */
#define MT4_S3C_SIGNED_ROUND 1u
#define MT4_S3C_OTHER_ROUND 2u

/* The BLS12-381 base field modulus, big-endian.  A format constant of the curve, not a secret. */
static const byte MT4_S3C_FIELD_MODULUS[48] = {
    0x1a, 0x01, 0x11, 0xea, 0x39, 0x7f, 0xe6, 0x9a, 0x4b, 0x1b, 0xa7, 0xb6, 0x43, 0x4b, 0xac, 0xd7,
    0x64, 0x77, 0x4b, 0x84, 0xf3, 0x85, 0x12, 0xbf, 0x67, 0x30, 0xd2, 0xa0, 0xf6, 0xb0, 0xf6, 0x24,
    0x1e, 0xab, 0xff, 0xfe, 0xb1, 0x53, 0xff, 0xff, 0xb9, 0xfe, 0xff, 0xff, 0xff, 0xff, 0xaa, 0xab};

typedef struct {
    const char *case_id;
    const char *construction_intent;
    unsigned int stimulus_kind;
    int expected_result_class;
    int expected_result_code;
    int expected_exit_status;
    unsigned char input[MT4_S3C_MAX_CASE_INPUT_BYTES];
    unsigned int input_length;
} mt4_s3c_case_t;

static mt4_s3c_case_t cases[MT4_S3C_CASE_COUNT];

static void fail(const char *marker, const char *detail)
{
    (void)fprintf(stderr, "MT4_S3C_VECTOR_GENERATION_FAILED=%s:%s\n", marker, detail);
    (void)fprintf(stderr, "MT4_S3C_RESULT=UNRESOLVED_P2\n");
    exit(2);
}

static void message_digest_for_round(uint64_t round, byte out[MT4_S3C_DIGEST_LEN])
{
    byte encoded[8];
    unsigned int index;

    for (index = 0; index < 8u; index++) {
        encoded[index] = (byte)((round >> (56u - 8u * index)) & 0xffu);
    }
    blst_sha256(out, encoded, sizeof(encoded));
}

static void build_frame(unsigned char *frame,
                        const byte public_key[MT4_S3C_PK_LEN],
                        const byte signature[MT4_S3C_SIG_LEN],
                        const byte digest[MT4_S3C_DIGEST_LEN])
{
    memset(frame, 0, MT4_S3C_REQUEST_FRAME_BYTES);
    frame[0] = 0x4D;
    frame[1] = 0x54;
    frame[2] = 0x34;
    frame[3] = 0x57;
    frame[4] = 0x01;
    frame[5] = 0x01;
    frame[6] = 0x00;
    frame[7] = 0x00;
    memcpy(frame + 8, public_key, MT4_S3C_PK_LEN);
    memcpy(frame + 104, signature, MT4_S3C_SIG_LEN);
    memcpy(frame + 152, digest, MT4_S3C_DIGEST_LEN);
}

static void set_case(unsigned int index,
                     const char *case_id,
                     const char *intent,
                     unsigned int stimulus_kind,
                     int expected_class,
                     int expected_code,
                     int expected_exit,
                     const unsigned char *input,
                     unsigned int input_length)
{
    if (index >= (unsigned int)MT4_S3C_CASE_COUNT || input_length > (unsigned int)MT4_S3C_MAX_CASE_INPUT_BYTES) {
        fail("CASE_INDEX", case_id);
    }
    cases[index].case_id = case_id;
    cases[index].construction_intent = intent;
    cases[index].stimulus_kind = stimulus_kind;
    cases[index].expected_result_class = expected_class;
    cases[index].expected_result_code = expected_code;
    cases[index].expected_exit_status = expected_exit;
    cases[index].input_length = input_length;
    if (input_length > 0u) {
        memcpy(cases[index].input, input, input_length);
    }
}

/*
 * Find a VALID encoding of a curve point that lies OUTSIDE the prime-order subgroup, by scanning
 * candidate x-coordinates in a fixed ascending order and taking the first that decodes on-curve but
 * fails the subgroup gate.  The scan order is frozen, so the result is deterministic.
 */
static int find_off_subgroup_g1(byte out[MT4_S3C_SIG_LEN])
{
    uint32_t candidate;

    for (candidate = 1u; candidate < 4096u; candidate++) {
        blst_p1_affine point;

        memset(out, 0, MT4_S3C_SIG_LEN);
        out[0] = 0x80;
        out[MT4_S3C_SIG_LEN - 4] = (byte)((candidate >> 24) & 0xffu);
        out[MT4_S3C_SIG_LEN - 3] = (byte)((candidate >> 16) & 0xffu);
        out[MT4_S3C_SIG_LEN - 2] = (byte)((candidate >> 8) & 0xffu);
        out[MT4_S3C_SIG_LEN - 1] = (byte)(candidate & 0xffu);
        if (blst_p1_uncompress(&point, out) != BLST_SUCCESS) {
            continue;
        }
        if (blst_p1_affine_is_inf(&point)) {
            continue;
        }
        if (!blst_p1_affine_in_g1(&point)) {
            return 0;
        }
    }
    return -1;
}

static int find_off_subgroup_g2(byte out[MT4_S3C_PK_LEN])
{
    uint32_t candidate;

    for (candidate = 1u; candidate < 4096u; candidate++) {
        blst_p2_affine point;

        memset(out, 0, MT4_S3C_PK_LEN);
        out[0] = 0x80;
        out[MT4_S3C_PK_LEN - 4] = (byte)((candidate >> 24) & 0xffu);
        out[MT4_S3C_PK_LEN - 3] = (byte)((candidate >> 16) & 0xffu);
        out[MT4_S3C_PK_LEN - 2] = (byte)((candidate >> 8) & 0xffu);
        out[MT4_S3C_PK_LEN - 1] = (byte)(candidate & 0xffu);
        if (blst_p2_uncompress(&point, out) != BLST_SUCCESS) {
            continue;
        }
        if (blst_p2_affine_is_inf(&point)) {
            continue;
        }
        if (!blst_p2_affine_in_g2(&point)) {
            return 0;
        }
    }
    return -1;
}

static void emit_hex(FILE *stream, const unsigned char *bytes, unsigned int length)
{
    static const char digits[] = "0123456789abcdef";
    unsigned int index;

    for (index = 0; index < length; index++) {
        (void)fputc(digits[(bytes[index] >> 4) & 0x0f], stream);
        (void)fputc(digits[bytes[index] & 0x0f], stream);
    }
}

int main(int argc, char **argv)
{
    blst_scalar signer_secret;
    blst_scalar other_secret;
    blst_p2 signer_public;
    blst_p2 other_public;
    blst_p1 hashed_message;
    blst_p1 signature_point;
    byte public_key[MT4_S3C_PK_LEN];
    byte other_public_key[MT4_S3C_PK_LEN];
    byte signature[MT4_S3C_SIG_LEN];
    byte signed_digest[MT4_S3C_DIGEST_LEN];
    byte other_digest[MT4_S3C_DIGEST_LEN];
    unsigned char frame[MT4_S3C_REQUEST_FRAME_BYTES];
    unsigned char scratch[MT4_S3C_MAX_CASE_INPUT_BYTES];
    unsigned int index;
    FILE *stream;

    if (argc != 4) {
        (void)fprintf(stderr, "usage: %s <out.json> <generator-source-sha256> <generator-binary-sha256>\n", argv[0]);
        return 2;
    }

    /* --- the frozen deterministic key material and the signed message ------------------------ */
    blst_keygen(&signer_secret, MT4_S3C_SIGNER_IKM, sizeof(MT4_S3C_SIGNER_IKM), NULL, 0);
    blst_keygen(&other_secret, MT4_S3C_OTHER_IKM, sizeof(MT4_S3C_OTHER_IKM), NULL, 0);
    blst_sk_to_pk_in_g2(&signer_public, &signer_secret);
    blst_sk_to_pk_in_g2(&other_public, &other_secret);
    blst_p2_compress(public_key, &signer_public);
    blst_p2_compress(other_public_key, &other_public);

    message_digest_for_round(MT4_S3C_SIGNED_ROUND, signed_digest);
    message_digest_for_round(MT4_S3C_OTHER_ROUND, other_digest);
    blst_hash_to_g1(&hashed_message,
                    signed_digest,
                    MT4_S3C_DIGEST_LEN,
                    MT4_S3C_QUICKNET_DST,
                    MT4_S3C_QUICKNET_DST_LEN,
                    NULL,
                    0);
    blst_sign_pk_in_g2(&signature_point, &hashed_message, &signer_secret);
    blst_p1_compress(signature, &signature_point);

    /* --- C01, C02: the governed positive vector and its byte-identical repeat ---------------- */
    build_frame(frame, public_key, signature, signed_digest);
    set_case(0, "C01_POSITIVE_EXACT_FIXTURE", "GOVERNED_TEST_ONLY_POSITIVE_VECTOR", 0, 1, 0, 0, frame,
             MT4_S3C_REQUEST_FRAME_BYTES);
    set_case(1, "C02_DETERMINISM_EXACT_REPEAT", "BYTE_IDENTICAL_REPEAT_OF_C01", 0, 1, 0, 0, frame,
             MT4_S3C_REQUEST_FRAME_BYTES);

    /* --- C03: a malformed G2 compression flag pattern ---------------------------------------- */
    {
        byte malformed[MT4_S3C_PK_LEN];

        memcpy(malformed, public_key, MT4_S3C_PK_LEN);
        malformed[0] = (byte)(malformed[0] & 0x7fu); /* compression bit cleared */
        build_frame(frame, malformed, signature, signed_digest);
        set_case(2, "C03_PK_BAD_ENCODING", "G2_MALFORMED_COMPRESSION_FLAG_PATTERN", 0, 1, 3, 0, frame,
                 MT4_S3C_REQUEST_FRAME_BYTES);
    }

    /* --- C04: a G2 x-coordinate greater than or equal to the field modulus -------------------- */
    {
        byte noncanonical[MT4_S3C_PK_LEN];

        memset(noncanonical, 0, MT4_S3C_PK_LEN);
        memcpy(noncanonical, MT4_S3C_FIELD_MODULUS, sizeof(MT4_S3C_FIELD_MODULUS));
        noncanonical[0] = (byte)(noncanonical[0] | 0x80u);
        build_frame(frame, noncanonical, signature, signed_digest);
        set_case(3, "C04_PK_FIELD_MODULUS_BAD_ENCODING", "G2_X_COORDINATE_GREATER_OR_EQUAL_FIELD_MODULUS", 0,
                 1, 3, 0, frame,
                 MT4_S3C_REQUEST_FRAME_BYTES);
    }

    /* --- C05: the canonical G2 infinity encoding ---------------------------------------------- */
    {
        byte infinity[MT4_S3C_PK_LEN];

        memset(infinity, 0, MT4_S3C_PK_LEN);
        infinity[0] = 0xc0;
        build_frame(frame, infinity, signature, signed_digest);
        set_case(4, "C05_PK_INFINITY", "G2_CANONICAL_INFINITY_ENCODING", 0, 1, 5, 0, frame,
                 MT4_S3C_REQUEST_FRAME_BYTES);
    }

    /* --- C06: a valid G2 encoding outside the prime-order subgroup ---------------------------- */
    {
        byte off_subgroup[MT4_S3C_PK_LEN];

        if (find_off_subgroup_g2(off_subgroup) != 0) {
            fail("CONSTRUCTION_UNAVAILABLE", "C06_PK_NOT_IN_GROUP");
        }
        build_frame(frame, off_subgroup, signature, signed_digest);
        set_case(5, "C06_PK_NOT_IN_GROUP", "G2_VALID_ENCODING_OUTSIDE_PRIME_ORDER_SUBGROUP", 0, 1, 6, 0, frame,
                 MT4_S3C_REQUEST_FRAME_BYTES);
    }

    /* --- C07..C10: the signature-side constructions -------------------------------------------- */
    {
        byte malformed[MT4_S3C_SIG_LEN];

        memcpy(malformed, signature, MT4_S3C_SIG_LEN);
        malformed[0] = (byte)(malformed[0] & 0x7fu);
        build_frame(frame, public_key, malformed, signed_digest);
        set_case(6, "C07_SIG_BAD_ENCODING", "G1_MALFORMED_COMPRESSION_FLAG_PATTERN", 0, 1, 7, 0, frame,
                 MT4_S3C_REQUEST_FRAME_BYTES);
    }
    {
        byte noncanonical[MT4_S3C_SIG_LEN];

        memcpy(noncanonical, MT4_S3C_FIELD_MODULUS, sizeof(MT4_S3C_FIELD_MODULUS));
        noncanonical[0] = (byte)(noncanonical[0] | 0x80u);
        build_frame(frame, public_key, noncanonical, signed_digest);
        set_case(7, "C08_SIG_FIELD_MODULUS_BAD_ENCODING", "G1_X_COORDINATE_GREATER_OR_EQUAL_FIELD_MODULUS", 0,
                 1, 7, 0, frame,
                 MT4_S3C_REQUEST_FRAME_BYTES);
    }
    {
        byte infinity[MT4_S3C_SIG_LEN];

        memset(infinity, 0, MT4_S3C_SIG_LEN);
        infinity[0] = 0xc0;
        build_frame(frame, public_key, infinity, signed_digest);
        set_case(8, "C09_SIG_INFINITY", "G1_CANONICAL_INFINITY_ENCODING", 0, 1, 9, 0, frame,
                 MT4_S3C_REQUEST_FRAME_BYTES);
    }
    {
        byte off_subgroup[MT4_S3C_SIG_LEN];

        if (find_off_subgroup_g1(off_subgroup) != 0) {
            fail("CONSTRUCTION_UNAVAILABLE", "C10_SIG_NOT_IN_GROUP");
        }
        build_frame(frame, public_key, off_subgroup, signed_digest);
        set_case(9, "C10_SIG_NOT_IN_GROUP", "G1_VALID_ENCODING_OUTSIDE_PRIME_ORDER_SUBGROUP", 0, 1, 10, 0, frame,
                 MT4_S3C_REQUEST_FRAME_BYTES);
    }

    /*
     * C11 and C12 are the two ORTHOGONAL VERIFY_FAILED paths.  C11 proves the message digest is
     * consumed; C12 proves the public key is consumed.  A worker that ignored the public key
     * entirely would still pass C01 and every signature case, which is exactly why both exist.
     */
    build_frame(frame, public_key, signature, other_digest);
    set_case(10, "C11_VERIFY_FAILED_WRONG_DIGEST", "VALID_SIGNATURE_OVER_A_DIFFERENT_MESSAGE_DIGEST", 0, 1, 11, 0,
             frame, MT4_S3C_REQUEST_FRAME_BYTES);
    build_frame(frame, other_public_key, signature, signed_digest);
    set_case(11, "C12_VERIFY_FAILED_WRONG_PUBLIC_KEY", "VALID_IN_SUBGROUP_PUBLIC_KEY_THAT_IS_NOT_THE_SIGNER", 0, 1,
             11, 0, frame, MT4_S3C_REQUEST_FRAME_BYTES);

    /* --- C13..C16: the fixed-field request protocol errors ------------------------------------ */
    build_frame(frame, public_key, signature, signed_digest);
    memcpy(scratch, frame, MT4_S3C_REQUEST_FRAME_BYTES);
    scratch[0] = 0x00;
    set_case(12, "C13_WRONG_MAGIC", "FULL_FRAME_WITH_MAGIC_NOT_MT4W", 0, 2, 1, 0, scratch,
             MT4_S3C_REQUEST_FRAME_BYTES);
    memcpy(scratch, frame, MT4_S3C_REQUEST_FRAME_BYTES);
    scratch[4] = 0x02;
    set_case(13, "C14_WRONG_VERSION", "FULL_FRAME_WITH_VERSION_NOT_ONE", 0, 2, 2, 0, scratch,
             MT4_S3C_REQUEST_FRAME_BYTES);
    memcpy(scratch, frame, MT4_S3C_REQUEST_FRAME_BYTES);
    scratch[5] = 0x02;
    set_case(14, "C15_WRONG_OPCODE", "FULL_FRAME_WITH_OPCODE_NOT_ONE", 0, 2, 3, 0, scratch,
             MT4_S3C_REQUEST_FRAME_BYTES);
    memcpy(scratch, frame, MT4_S3C_REQUEST_FRAME_BYTES);
    scratch[6] = 0x01;
    set_case(15, "C16_RESERVED_NONZERO", "FULL_FRAME_WITH_NONZERO_REQUEST_RESERVED_FIELD", 0, 2, 4, 0, scratch,
             MT4_S3C_REQUEST_FRAME_BYTES);

    /* --- C17..C19: the three distinct SHORT_FRAME_EOF boundary stimuli ------------------------ */
    set_case(16, "C17_SHORT_FRAME_EOF_EMPTY", "ZERO_BYTES_THEN_EOF", 0, 2, 5, 0, frame, 0u);
    set_case(17, "C18_SHORT_FRAME_EOF_PARTIAL_HEADER", "SEVEN_BYTES_THEN_EOF", 0, 2, 5, 0, frame, 7u);
    set_case(18, "C19_SHORT_FRAME_EOF_ONE_SHORT", "ONE_HUNDRED_EIGHTY_THREE_BYTES_THEN_EOF", 0, 2, 5, 0, frame,
             (unsigned int)MT4_S3C_REQUEST_FRAME_BYTES - 1u);

    /* --- C20, C21: the two distinct TRAILING_INPUT boundary stimuli --------------------------- */
    memcpy(scratch, frame, MT4_S3C_REQUEST_FRAME_BYTES);
    scratch[MT4_S3C_REQUEST_FRAME_BYTES] = 0x00;
    set_case(19, "C20_TRAILING_INPUT_ONE_BYTE", "ONE_HUNDRED_EIGHTY_FIVE_BYTES_THEN_EOF", 0, 2, 6, 0, scratch,
             (unsigned int)MT4_S3C_REQUEST_FRAME_BYTES + 1u);
    memcpy(scratch, frame, MT4_S3C_REQUEST_FRAME_BYTES);
    memcpy(scratch + MT4_S3C_REQUEST_FRAME_BYTES, frame, MT4_S3C_REQUEST_FRAME_BYTES);
    set_case(20, "C21_TRAILING_INPUT_SECOND_FRAME", "TWO_COMPLETE_FRAMES_THEN_EOF", 0, 2, 6, 0, scratch,
             (unsigned int)MT4_S3C_REQUEST_FRAME_BYTES * 2u);

    /*
     * C22 and C23 pin the FROZEN FIELD-VALIDATION ORDER.  An input that is simultaneously over-long
     * AND carries a wrong magic must yield TRAILING_INPUT, not WRONG_MAGIC; an input that is
     * simultaneously short AND carries a wrong magic must yield SHORT_FRAME_EOF.  Each expected
     * response is a value V5 already requires for its winning condition, so neither case adds any
     * wire code, offset, length or taxonomy member.
     */
    memcpy(scratch, frame, MT4_S3C_REQUEST_FRAME_BYTES);
    scratch[0] = 0x00;
    scratch[MT4_S3C_REQUEST_FRAME_BYTES] = 0x00;
    set_case(21, "C22_ORDER_TRAILING_BEFORE_MAGIC", "OVER_LONG_INPUT_WHOSE_FIRST_FRAME_CARRIES_A_WRONG_MAGIC", 0, 2,
             6, 0, scratch, (unsigned int)MT4_S3C_REQUEST_FRAME_BYTES + 1u);
    memcpy(scratch, frame, MT4_S3C_REQUEST_FRAME_BYTES);
    scratch[0] = 0x00;
    set_case(22, "C23_ORDER_SHORT_BEFORE_MAGIC", "SHORT_INPUT_THAT_ALSO_CARRIES_A_WRONG_MAGIC", 0, 2, 5, 0, scratch,
             (unsigned int)MT4_S3C_REQUEST_FRAME_BYTES - 1u);

    /* --- C24, C25: the two process stimuli.  No response frame is expected or interpreted ----- */
    set_case(23, "C24_CRASH_MID_REQUEST", "PARTIAL_INPUT_THEN_EXTERNAL_SIGKILL", 1, 0, -1, -1, frame,
             (unsigned int)MT4_S3C_PARTIAL_PREFIX_BYTES);
    set_case(24, "C25_TIMEOUT_WRITER_WITHHOLDS", "PARTIAL_INPUT_WITH_THE_WRITER_HELD_OPEN_PAST_THE_DEADLINE", 2, 0,
             -1, -1, frame, (unsigned int)MT4_S3C_PARTIAL_PREFIX_BYTES);

    /*
     * PROVE the frozen expectations against PINNED BLST for every case that carries a complete
     * frame.  This is the whole point of the generator: it does not learn the expected code, it
     * CONFIRMS it, and it refuses to emit a fixture whose expectations the pinned library
     * contradicts.
     */
    for (index = 0; index < (unsigned int)MT4_S3C_CASE_COUNT; index++) {
        int observed;

        if (cases[index].expected_result_class != 1 ||
            cases[index].input_length < (unsigned int)MT4_S3C_REQUEST_FRAME_BYTES) {
            continue;
        }
        observed = mt4_s3c_verify_quicknet_request(cases[index].input + 8,
                                                   cases[index].input + 104,
                                                   cases[index].input + 152);
        if (observed != cases[index].expected_result_code) {
            (void)fprintf(stderr,
                          "MT4_S3C_EXPECTED=%d MT4_S3C_OBSERVED=%d CASE=%s\n",
                          cases[index].expected_result_code,
                          observed,
                          cases[index].case_id);
            fail("PINNED_BLST_STATUS_DISAGREEMENT", cases[index].case_id);
        }
    }

    /* --- emit the governed fixture ------------------------------------------------------------ */
    stream = fopen(argv[1], "wb");
    if (stream == NULL) {
        fail("OUTPUT", argv[1]);
    }
    (void)fprintf(stream, "{\n");
    (void)fprintf(stream, "  \"schema\": \"mt4-s3c-test-only-vector.v1\",\n");
    (void)fprintf(stream, "  \"vector_authority\": \"PROJECT_GENERATED_DETERMINISTIC_TEST_VECTOR\",\n");
    (void)fprintf(stream, "  \"fixture_material_state\": \"GENERATED_OFFLINE_ONE_TIME\",\n");
    (void)fprintf(stream, "  \"generator_source_sha256\": \"%s\",\n", argv[2]);
    (void)fprintf(stream, "  \"generator_binary_sha256\": \"%s\",\n", argv[3]);
    (void)fprintf(stream, "  \"generation_mode\": \"OFFLINE_ONE_TIME_OUTSIDE_THE_QUALIFICATION_RUN\",\n");
    (void)fprintf(stream, "  \"wire\": {\n");
    (void)fprintf(stream, "    \"request_frame_bytes\": %d,\n", MT4_S3C_REQUEST_FRAME_BYTES);
    (void)fprintf(stream, "    \"response_frame_bytes\": 8\n");
    (void)fprintf(stream, "  },\n");
    (void)fprintf(stream, "  \"cases\": [\n");
    for (index = 0; index < (unsigned int)MT4_S3C_CASE_COUNT; index++) {
        (void)fprintf(stream, "    {\n");
        (void)fprintf(stream, "      \"case_id\": \"%s\",\n", cases[index].case_id);
        (void)fprintf(stream, "      \"construction_intent\": \"%s\",\n", cases[index].construction_intent);
        (void)fprintf(stream, "      \"stimulus_kind\": %u,\n", cases[index].stimulus_kind);
        (void)fprintf(stream, "      \"expected_result_class\": %d,\n", cases[index].expected_result_class);
        (void)fprintf(stream, "      \"expected_result_code\": %d,\n", cases[index].expected_result_code);
        (void)fprintf(stream, "      \"expected_exit_status\": %d,\n", cases[index].expected_exit_status);
        (void)fprintf(stream, "      \"input_hex\": \"");
        emit_hex(stream, cases[index].input, cases[index].input_length);
        (void)fprintf(stream, "\"\n");
        (void)fprintf(stream, "    }%s\n", index + 1u == (unsigned int)MT4_S3C_CASE_COUNT ? "" : ",");
    }
    (void)fprintf(stream, "  ],\n");
    (void)fprintf(stream, "  \"non_claims\": {\n");
    (void)fprintf(stream, "    \"fixture_corpus_admitted\": false,\n");
    (void)fprintf(stream, "    \"fixture_corpus_loaded\": false,\n");
    (void)fprintf(stream, "    \"fixture_corpus_verified\": false,\n");
    (void)fprintf(stream, "    \"proof_verified\": false,\n");
    (void)fprintf(stream, "    \"randomness_verified\": false,\n");
    (void)fprintf(stream, "    \"provider_operationally_approved\": false,\n");
    (void)fprintf(stream, "    \"readiness_promoted\": false,\n");
    (void)fprintf(stream, "    \"is_official_or_normative_vector\": false,\n");
    (void)fprintf(stream, "    \"is_quicknet_beacon_material\": false\n");
    (void)fprintf(stream, "  }\n");
    (void)fprintf(stream, "}\n");
    if (fclose(stream) != 0) {
        fail("OUTPUT", "close");
    }
    (void)fprintf(stderr, "MT4_S3C_VECTOR_GENERATION=OK cases=%d\n", MT4_S3C_CASE_COUNT);
    return 0;
}
