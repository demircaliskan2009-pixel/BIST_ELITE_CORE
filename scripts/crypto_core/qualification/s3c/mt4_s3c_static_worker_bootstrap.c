/*
 * MT4-S3C P0 STATIC WORKER BOOTSTRAP.  Qualification infrastructure only.
 *
 * ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 19.1, 20.5, 20.6.
 * BUNDLE ENTRY 13 of the exact 16-entry qualification source bundle (V9 SECTION 8).
 *
 * WHAT THIS TRANSLATION UNIT IS.  It is the whole of the candidate worker's control flow:
 * PRIVILEGE_LOCK, FD_CLOSURE, the internal seccomp installation, the V5 REQUEST_COMPLETION_POLICY,
 * exactly one 8-byte response write, and exit_group.  It is untrusted by construction (V9 SECTION
 * 10 tier T-D): every artifact it influences is DATA, and nothing it reports about itself is ever
 * believed.
 *
 * FREESTANDING, NO LIBC, NO CRT.  There is no libc, no allocator, no clock, no environment, no
 * filesystem access and no network.  Every syscall goes through a project-owned wrapper in this
 * file, and every one of those wrappers zeroes EVERY argument register the syscall does not
 * consume -- including the sixth -- which is exactly what makes V9 SECTION 14.3's
 * UNUSED_ARGUMENT_ZERO_RULE satisfiable rather than an assumption about the platform ABI.
 *
 * THE WORKER HOLDS NO CLOCK.  Every time syscall is absent from both filters (V9 SECTION 5), so the
 * worker cannot measure, report or depend on time.  A sender that never closes the request pipe
 * leaves the worker blocked and the SUPERVISOR's external deadline fires; that is WORKER_TIMEOUT,
 * a process failure, and never a crypto verdict.
 *
 * NO SECOND COMMAND PARSER EXISTS.  Control flow is straight-line: one request is consumed at most
 * once, there is no read loop around request handling, and the process exits after its single
 * response write.  A second command arrives as trailing data and is rejected BEFORE any
 * cryptographic work (V9 20.6 step 6).
 */

#include <asm/unistd.h>
#include <linux/filter.h>
#include <linux/prctl.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdint.h>

/*
 * The authorized S3C P0 path set contains no header file, so each cross-unit symbol is declared
 * here exactly as it is defined in its own translation unit.  A permanent source-shape test
 * asserts the declarations and the definitions agree.
 */
extern const struct sock_fprog mt4_s3c_internal_filter_fprog;
extern int mt4_s3c_verify_quicknet_request(const uint8_t *public_key,
                                           const uint8_t *signature,
                                           const uint8_t *message_digest);

/* ---------------------------------------------------------------------------------------------
 * GOVERNED PROJECT CONSTANTS (V9 12.3, 17.2, 20.2, 20.3, 20.5).
 * ------------------------------------------------------------------------------------------- */

#define MT4_S3C_FD_REQUEST 3
#define MT4_S3C_FD_RESPONSE 4
#define MT4_S3C_CLOSE_RANGE_FIRST_FD 5
#define MT4_S3C_CLOSE_RANGE_MAX_FD 4294967295u

#define MT4_S3C_REQUEST_FRAME_BYTES 184
#define MT4_S3C_RESPONSE_FRAME_BYTES 8

/* WIRE_REQUEST_LAYOUT offsets (V9 20.2).  Fixed 184 bytes; no field selects behaviour. */
#define MT4_S3C_REQ_OFF_MAGIC 0
#define MT4_S3C_REQ_OFF_VERSION 4
#define MT4_S3C_REQ_OFF_OPCODE 5
#define MT4_S3C_REQ_OFF_RESERVED 6
#define MT4_S3C_REQ_OFF_PUBLIC_KEY 8
#define MT4_S3C_REQ_OFF_SIGNATURE 104
#define MT4_S3C_REQ_OFF_MESSAGE_DIGEST 152

#define MT4_S3C_REQUEST_VERSION 0x01
#define MT4_S3C_REQUEST_OPCODE_VERIFY_QUICKNET_G1 0x01

/* WIRE_RESPONSE_LAYOUT offsets (V9 20.3).  Fixed 8 bytes. */
#define MT4_S3C_RSP_OFF_MAGIC 0
#define MT4_S3C_RSP_OFF_VERSION 4
#define MT4_S3C_RSP_OFF_RESULT_CLASS 5
#define MT4_S3C_RSP_OFF_RESULT_CODE 6
#define MT4_S3C_RSP_OFF_RESERVED 7

#define MT4_S3C_RESPONSE_VERSION 0x01

/*
 * RESULT_CLASS is CLOSED.  0x00 is ILLEGAL AND RESERVED-INVALID ON PURPOSE, so that an all-zero or
 * partially written 8-byte buffer can never be interpreted as "VERIFIER_STATUS / OK" (V9 20.3).
 */
#define MT4_S3C_RESULT_CLASS_VERIFIER_STATUS 0x01
#define MT4_S3C_RESULT_CLASS_REQUEST_PROTOCOL_ERROR 0x02

/* REQUEST_PROTOCOL_ERROR taxonomy, CLOSED AT SIX (V9 20.5). */
#define MT4_S3C_REQERR_WRONG_MAGIC 1
#define MT4_S3C_REQERR_WRONG_VERSION 2
#define MT4_S3C_REQERR_WRONG_OPCODE 3
#define MT4_S3C_REQERR_RESERVED_NONZERO 4
#define MT4_S3C_REQERR_SHORT_FRAME_EOF 5
#define MT4_S3C_REQERR_TRAILING_INPUT 6

/* Reserved candidate exit codes (V9 20.5).  Nothing else is a legal candidate exit code. */
#define MT4_S3C_EXIT_RESPONSE_WRITTEN 0
#define MT4_S3C_EXIT_BOOTSTRAP_FAILED 64
#define MT4_S3C_EXIT_SANDBOX_FAILED 65

/* Governed encoded lengths, transcribed from the S3B verifier profile (V9 SECTION 9 R6). */
#define MT4_S3C_PUBLIC_KEY_ENCODED_LENGTH 96
#define MT4_S3C_SIGNATURE_ENCODED_LENGTH 48
#define MT4_S3C_MESSAGE_LENGTH 32

/* EINTR, taken from the pinned UAPI rather than assumed. */
#include <asm-generic/errno-base.h>

/* ---------------------------------------------------------------------------------------------
 * PROJECT-OWNED FREESTANDING SYSCALL WRAPPERS.
 *
 * Every wrapper loads ALL SIX System V AMD64 syscall argument registers, so an argument the
 * syscall does not consume always carries an explicit zero rather than whatever the register
 * happened to hold.  That is the whole basis of V9 SECTION 14.3: the zero-tail rule is a property
 * of THIS code, not a property the platform provides.
 * ------------------------------------------------------------------------------------------- */

static inline long mt4_s3c_syscall6(long number, long a0, long a1, long a2, long a3, long a4, long a5)
{
    long result;
    register long r10 __asm__("r10") = a3;
    register long r8 __asm__("r8") = a4;
    register long r9 __asm__("r9") = a5;

    __asm__ volatile("syscall"
                     : "=a"(result)
                     : "a"(number), "D"(a0), "S"(a1), "d"(a2), "r"(r10), "r"(r8), "r"(r9)
                     : "rcx", "r11", "memory");
    return result;
}

static inline long mt4_s3c_sys_read(int fd, void *buffer, unsigned long count)
{
    return mt4_s3c_syscall6(__NR_read, (long)fd, (long)buffer, (long)count, 0, 0, 0);
}

static inline long mt4_s3c_sys_write(int fd, const void *buffer, unsigned long count)
{
    return mt4_s3c_syscall6(__NR_write, (long)fd, (long)buffer, (long)count, 0, 0, 0);
}

static inline long mt4_s3c_sys_close(int fd)
{
    return mt4_s3c_syscall6(__NR_close, (long)fd, 0, 0, 0, 0, 0);
}

static inline long mt4_s3c_sys_close_range(unsigned int first, unsigned int last, unsigned int flags)
{
    return mt4_s3c_syscall6(__NR_close_range, (long)first, (long)last, (long)flags, 0, 0, 0);
}

static inline long mt4_s3c_sys_prctl(int option, unsigned long argument)
{
    return mt4_s3c_syscall6(__NR_prctl, (long)option, (long)argument, 0, 0, 0, 0);
}

static inline long mt4_s3c_sys_seccomp(unsigned int operation, unsigned int flags, const void *args)
{
    return mt4_s3c_syscall6(__NR_seccomp, (long)operation, (long)flags, (long)args, 0, 0, 0);
}

__attribute__((noreturn)) static void mt4_s3c_sys_exit_group(int status)
{
    for (;;) {
        (void)mt4_s3c_syscall6(__NR_exit_group, (long)status, 0, 0, 0, 0, 0);
    }
}

/* ---------------------------------------------------------------------------------------------
 * FREESTANDING STRING PRIMITIVES.
 *
 * The image links no libc, so the primitives the compiler and the pinned blst sources may call are
 * supplied here.  They carry the standard names deliberately: GCC is permitted to emit a call to
 * memcpy or memset for an aggregate copy or initialisation even under -ffreestanding, and an
 * unresolved reference would be a link error under the zero-undefined-symbol policy.  None of them
 * allocates, and none of them touches any state outside the buffers it is given.
 * ------------------------------------------------------------------------------------------- */

void *memcpy(void *destination, const void *source, unsigned long length);
void *memset(void *destination, int value, unsigned long length);
void *memmove(void *destination, const void *source, unsigned long length);
int memcmp(const void *left, const void *right, unsigned long length);

void *memcpy(void *destination, const void *source, unsigned long length)
{
    unsigned char *out = (unsigned char *)destination;
    const unsigned char *in = (const unsigned char *)source;
    unsigned long index;

    for (index = 0; index < length; index++) {
        out[index] = in[index];
    }
    return destination;
}

void *memset(void *destination, int value, unsigned long length)
{
    unsigned char *out = (unsigned char *)destination;
    unsigned long index;

    for (index = 0; index < length; index++) {
        out[index] = (unsigned char)value;
    }
    return destination;
}

void *memmove(void *destination, const void *source, unsigned long length)
{
    unsigned char *out = (unsigned char *)destination;
    const unsigned char *in = (const unsigned char *)source;
    unsigned long index;

    if (out == in || length == 0) {
        return destination;
    }
    if (out < in) {
        for (index = 0; index < length; index++) {
            out[index] = in[index];
        }
    } else {
        for (index = length; index > 0; index--) {
            out[index - 1] = in[index - 1];
        }
    }
    return destination;
}

int memcmp(const void *left, const void *right, unsigned long length)
{
    const unsigned char *a = (const unsigned char *)left;
    const unsigned char *b = (const unsigned char *)right;
    unsigned long index;

    for (index = 0; index < length; index++) {
        if (a[index] != b[index]) {
            return (int)a[index] - (int)b[index];
        }
    }
    return 0;
}

/* ---------------------------------------------------------------------------------------------
 * FIXED IN-IMAGE BUFFERS.
 *
 * V9 SECTION 20.4 REACHABILITY: verifier statuses 1 NULL_INPUT and 2 BAD_LENGTH are STRUCTURALLY
 * UNREACHABLE precisely because these buffers are fixed in-image arrays that are never null and
 * because the frame is fixed-length, so the encoded lengths reaching the verifier are the
 * compile-time constants 96, 48 and 32.  Neither condition can arise from any wire input.  That is
 * a property of these declarations, so they are load-bearing rather than incidental.
 * ------------------------------------------------------------------------------------------- */

static uint8_t mt4_s3c_request_buffer[MT4_S3C_REQUEST_FRAME_BYTES];
static uint8_t mt4_s3c_response_buffer[MT4_S3C_RESPONSE_FRAME_BYTES];
static uint8_t mt4_s3c_trailing_probe_buffer[1];

/* "MT4W" and "MT4R".  Deliberately distinct so an echoed request can never read as a response. */
static const uint8_t mt4_s3c_request_magic[4] = {0x4D, 0x54, 0x34, 0x57};
static const uint8_t mt4_s3c_response_magic[4] = {0x4D, 0x54, 0x34, 0x52};

/* ---------------------------------------------------------------------------------------------
 * RESPONSE EMISSION.
 *
 * ONE canonical 8-byte frame, written for BOTH result classes, followed by a normal exit with
 * status 0.  V9 20.5 states this explicitly and V8 broke it: a request violation emits the typed
 * frame and exits 0; it does NOT emit nothing and it does NOT exit 64.
 * ------------------------------------------------------------------------------------------- */

__attribute__((noreturn)) static void mt4_s3c_emit_response(uint8_t result_class, uint8_t result_code)
{
    unsigned long written = 0;

    mt4_s3c_response_buffer[MT4_S3C_RSP_OFF_MAGIC + 0] = mt4_s3c_response_magic[0];
    mt4_s3c_response_buffer[MT4_S3C_RSP_OFF_MAGIC + 1] = mt4_s3c_response_magic[1];
    mt4_s3c_response_buffer[MT4_S3C_RSP_OFF_MAGIC + 2] = mt4_s3c_response_magic[2];
    mt4_s3c_response_buffer[MT4_S3C_RSP_OFF_MAGIC + 3] = mt4_s3c_response_magic[3];
    mt4_s3c_response_buffer[MT4_S3C_RSP_OFF_VERSION] = MT4_S3C_RESPONSE_VERSION;
    mt4_s3c_response_buffer[MT4_S3C_RSP_OFF_RESULT_CLASS] = result_class;
    mt4_s3c_response_buffer[MT4_S3C_RSP_OFF_RESULT_CODE] = result_code;
    mt4_s3c_response_buffer[MT4_S3C_RSP_OFF_RESERVED] = 0x00;

    while (written < (unsigned long)MT4_S3C_RESPONSE_FRAME_BYTES) {
        long result = mt4_s3c_sys_write(MT4_S3C_FD_RESPONSE,
                                        &mt4_s3c_response_buffer[written],
                                        (unsigned long)MT4_S3C_RESPONSE_FRAME_BYTES - written);
        if (result > 0) {
            written += (unsigned long)result;
            continue;
        }
        if (result == -EINTR) {
            continue;
        }
        /*
         * The response could not be delivered.  There is no second attempt at a different frame and
         * no diagnostic channel: the parent observes a short or absent response and adjudicates
         * WORKER_RESPONSE_PROTOCOL_VIOLATION.  Exiting 0 here would claim a response that does not
         * exist, so the typed bootstrap failure is the honest outcome.
         */
        mt4_s3c_sys_exit_group(MT4_S3C_EXIT_BOOTSTRAP_FAILED);
    }
    mt4_s3c_sys_exit_group(MT4_S3C_EXIT_RESPONSE_WRITTEN);
}

/* ---------------------------------------------------------------------------------------------
 * BOOTSTRAP PHASES
 * ------------------------------------------------------------------------------------------- */

/* State 19 PRIVILEGE_LOCK.  Exactly the two discriminated prctl tuples the outer filter permits. */
static int mt4_s3c_privilege_lock(void)
{
    if (mt4_s3c_sys_prctl(PR_SET_NO_NEW_PRIVS, 1) != 0) {
        return -1;
    }
    /*
     * PR_SET_DUMPABLE 0 happens HERE, before the internal install, and can never be undone: the
     * outer filter denies prctl(PR_SET_DUMPABLE, 1) outright, and after the internal install prctl
     * is not in the allowed set at all.  Moving this after the install is therefore impossible, not
     * merely discouraged (V9 15.3 note b).
     */
    if (mt4_s3c_sys_prctl(PR_SET_DUMPABLE, 0) != 0) {
        return -1;
    }
    return 0;
}

/* State 19 FD_CLOSURE.  The descriptor table becomes exactly {3, 4}. */
static int mt4_s3c_fd_closure(void)
{
    if (mt4_s3c_sys_close(0) != 0) {
        return -1;
    }
    if (mt4_s3c_sys_close(1) != 0) {
        return -1;
    }
    if (mt4_s3c_sys_close(2) != 0) {
        return -1;
    }
    if (mt4_s3c_sys_close_range(MT4_S3C_CLOSE_RANGE_FIRST_FD, MT4_S3C_CLOSE_RANGE_MAX_FD, 0) != 0) {
        return -1;
    }
    return 0;
}

/*
 * State 20 INTERNAL_FILTER_INSTALLED.  Exactly ONE seccomp call, referencing the canonical
 * link-time-fixed sock_fprog object in read-only, file-backed memory (V9 29.6 rule Q10).  The
 * return value is checked, but the AUTHORITATIVE proof that a filter was actually installed is the
 * trusted supervisor's /proc filter-count transition 1 -> 2 (V9 SECTION 11): an inherited
 * error-returning filter could make this call return 0 while installing nothing, and V9 SECTION
 * 11.1 exists precisely because that would otherwise pass.
 */
static int mt4_s3c_install_internal_filter(void)
{
    if (mt4_s3c_sys_seccomp(SECCOMP_SET_MODE_FILTER, 0, &mt4_s3c_internal_filter_fprog) != 0) {
        return -1;
    }
    return 0;
}

/* ---------------------------------------------------------------------------------------------
 * V5 REQUEST_COMPLETION_POLICY (V9 20.6).  The seven frozen steps, in order.
 * ------------------------------------------------------------------------------------------- */

/* Steps 1-3.  Returns the number of bytes filled, or a negative value on an unrecoverable error. */
static long mt4_s3c_fill_request(void)
{
    unsigned long filled = 0;

    while (filled < (unsigned long)MT4_S3C_REQUEST_FRAME_BYTES) {
        long result = mt4_s3c_sys_read(MT4_S3C_FD_REQUEST,
                                       &mt4_s3c_request_buffer[filled],
                                       (unsigned long)MT4_S3C_REQUEST_FRAME_BYTES - filled);
        if (result > 0) {
            filled += (unsigned long)result;
            continue;
        }
        if (result == 0) {
            /* Deterministic EOF.  The loop is bounded by the buffer size; it cannot spin. */
            break;
        }
        if (result == -EINTR) {
            continue;
        }
        return -1;
    }
    return (long)filled;
}

/* Steps 4-6.  Exactly ONE bounded trailing probe of exactly one byte. */
static int mt4_s3c_trailing_probe_found_input(void)
{
    for (;;) {
        long result = mt4_s3c_sys_read(MT4_S3C_FD_REQUEST, mt4_s3c_trailing_probe_buffer, 1);

        if (result == 0) {
            return 0;
        }
        if (result > 0) {
            return 1;
        }
        if (result == -EINTR) {
            continue;
        }
        return -1;
    }
}

/*
 * Step 7 and the FROZEN FIELD-VALIDATION ORDER (V9 20.6):
 *   SHORT_FRAME_EOF -> TRAILING_INPUT -> WRONG_MAGIC -> WRONG_VERSION -> WRONG_OPCODE ->
 *   RESERVED_NONZERO -> verify
 * The order is LOAD-BEARING.  An input that is simultaneously over-long AND carries a wrong magic
 * must yield TRAILING_INPUT, not WRONG_MAGIC (case C22); an input that is simultaneously short AND
 * carries a wrong magic must yield SHORT_FRAME_EOF (case C23).  The two conditions are resolved
 * before the field checks are reached at all, which is why the ordering cannot drift.
 */
static int mt4_s3c_validate_fixed_fields(void)
{
    if (memcmp(&mt4_s3c_request_buffer[MT4_S3C_REQ_OFF_MAGIC], mt4_s3c_request_magic, 4) != 0) {
        return MT4_S3C_REQERR_WRONG_MAGIC;
    }
    if (mt4_s3c_request_buffer[MT4_S3C_REQ_OFF_VERSION] != MT4_S3C_REQUEST_VERSION) {
        return MT4_S3C_REQERR_WRONG_VERSION;
    }
    if (mt4_s3c_request_buffer[MT4_S3C_REQ_OFF_OPCODE] != MT4_S3C_REQUEST_OPCODE_VERIFY_QUICKNET_G1) {
        return MT4_S3C_REQERR_WRONG_OPCODE;
    }
    /* A nonzero reserved field is an ERROR and is never silently ignored (V9 20.2). */
    if (mt4_s3c_request_buffer[MT4_S3C_REQ_OFF_RESERVED + 0] != 0x00 ||
        mt4_s3c_request_buffer[MT4_S3C_REQ_OFF_RESERVED + 1] != 0x00) {
        return MT4_S3C_REQERR_RESERVED_NONZERO;
    }
    return 0;
}

/* ---------------------------------------------------------------------------------------------
 * THE WORKER.  Straight-line control flow; every path ends in exit_group.
 * ------------------------------------------------------------------------------------------- */

__attribute__((noreturn)) void mt4_s3c_worker_main(void);

__attribute__((noreturn)) void mt4_s3c_worker_main(void)
{
    long filled;
    int trailing;
    int field_error;
    int verifier_status;

    if (mt4_s3c_privilege_lock() != 0) {
        mt4_s3c_sys_exit_group(MT4_S3C_EXIT_BOOTSTRAP_FAILED);
    }
    if (mt4_s3c_fd_closure() != 0) {
        mt4_s3c_sys_exit_group(MT4_S3C_EXIT_BOOTSTRAP_FAILED);
    }
    if (mt4_s3c_install_internal_filter() != 0) {
        mt4_s3c_sys_exit_group(MT4_S3C_EXIT_SANDBOX_FAILED);
    }

    filled = mt4_s3c_fill_request();
    if (filled < 0) {
        mt4_s3c_emit_response(MT4_S3C_RESULT_CLASS_REQUEST_PROTOCOL_ERROR, MT4_S3C_REQERR_SHORT_FRAME_EOF);
    }
    if (filled != (long)MT4_S3C_REQUEST_FRAME_BYTES) {
        mt4_s3c_emit_response(MT4_S3C_RESULT_CLASS_REQUEST_PROTOCOL_ERROR, MT4_S3C_REQERR_SHORT_FRAME_EOF);
    }

    trailing = mt4_s3c_trailing_probe_found_input();
    if (trailing != 0) {
        mt4_s3c_emit_response(MT4_S3C_RESULT_CLASS_REQUEST_PROTOCOL_ERROR, MT4_S3C_REQERR_TRAILING_INPUT);
    }

    field_error = mt4_s3c_validate_fixed_fields();
    if (field_error != 0) {
        mt4_s3c_emit_response(MT4_S3C_RESULT_CLASS_REQUEST_PROTOCOL_ERROR, (uint8_t)field_error);
    }

    verifier_status = mt4_s3c_verify_quicknet_request(&mt4_s3c_request_buffer[MT4_S3C_REQ_OFF_PUBLIC_KEY],
                                                      &mt4_s3c_request_buffer[MT4_S3C_REQ_OFF_SIGNATURE],
                                                      &mt4_s3c_request_buffer[MT4_S3C_REQ_OFF_MESSAGE_DIGEST]);
    mt4_s3c_emit_response(MT4_S3C_RESULT_CLASS_VERIFIER_STATUS, (uint8_t)verifier_status);
}

/* ---------------------------------------------------------------------------------------------
 * FROZEN LAYOUT PROOFS.  A wire-layout slip fails the build rather than the qualification run.
 * ------------------------------------------------------------------------------------------- */

_Static_assert(MT4_S3C_REQ_OFF_PUBLIC_KEY + MT4_S3C_PUBLIC_KEY_ENCODED_LENGTH == MT4_S3C_REQ_OFF_SIGNATURE,
               "MT4_S3C request layout: the public key occupies exactly offsets 8..104");
_Static_assert(MT4_S3C_REQ_OFF_SIGNATURE + MT4_S3C_SIGNATURE_ENCODED_LENGTH == MT4_S3C_REQ_OFF_MESSAGE_DIGEST,
               "MT4_S3C request layout: the signature occupies exactly offsets 104..152");
_Static_assert(MT4_S3C_REQ_OFF_MESSAGE_DIGEST + MT4_S3C_MESSAGE_LENGTH == MT4_S3C_REQUEST_FRAME_BYTES,
               "MT4_S3C request layout: the message digest occupies exactly offsets 152..184");
_Static_assert(MT4_S3C_RSP_OFF_RESERVED + 1 == MT4_S3C_RESPONSE_FRAME_BYTES,
               "MT4_S3C response layout: exactly eight bytes with a one-byte reserved tail");
_Static_assert(MT4_S3C_RESULT_CLASS_VERIFIER_STATUS != 0 && MT4_S3C_RESULT_CLASS_REQUEST_PROTOCOL_ERROR != 0,
               "MT4_S3C RESULT_CLASS 0x00 must remain illegal and reserved-invalid");
_Static_assert(sizeof(mt4_s3c_request_buffer) == MT4_S3C_REQUEST_FRAME_BYTES,
               "MT4_S3C request buffer must be exactly the fixed frame");
_Static_assert(sizeof(mt4_s3c_response_buffer) == MT4_S3C_RESPONSE_FRAME_BYTES,
               "MT4_S3C response buffer must be exactly the fixed frame");
