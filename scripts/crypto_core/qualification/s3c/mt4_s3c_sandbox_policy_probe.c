/*
 * MT4-S3C P0 CANONICAL SANDBOX POLICY PROBE.  Qualification infrastructure only.
 *
 * ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 13, 15.2.
 * BUNDLE ENTRY 11 of the exact 16-entry qualification source bundle (V9 SECTION 8).
 *
 * WHAT THIS PROGRAM PROVES.  It proves that the CANONICAL SOURCE (bundle entry 10) has the intended
 * semantics and reports, as data, exactly two things the Python policy qualifier (bundle entry 12)
 * cannot obtain for itself without asserting platform values from memory:
 *
 *   1. the pinned UAPI numeric values behind every macro name the canonical source uses;
 *   2. the exact bytes the canonical source COMPILED to, for both programs.
 *
 * WHAT THIS PROGRAM EXPLICITLY DOES NOT PROVE (V9 15.1).  It says NOTHING about the bytes the
 * CANDIDATE installed.  The candidate-side claim is a different claim, proved by legs L0, L1 and L2
 * of V9 SECTION 15.2 through the trusted observer, and this probe is never a substitute for any of
 * them.  A run in which the probe passes and the candidate installed something else must still FAIL
 * at INTERNAL_FILTER_EQUIVALENCE (permanent test PT-141).
 *
 * IT INSTALLS NOTHING.  The probe never calls seccomp, never calls prctl, never forks, never execs
 * and never opens a file.  It reads two const objects and writes JSON to standard output.  Running
 * it changes no process state at all.
 *
 * NO VALUE IS ASSERTED FROM MEMORY.  Every numeric value below is emitted from its pinned UAPI
 * macro.  The probe does not compare any of them against a literal; the RELATIONS the canonical
 * structure depends upon are proven by the qualifier from the emitted values.
 */

#include <asm/unistd.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/prctl.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/*
 * The authorized S3C P0 path set contains no header file, so the four canonical objects defined by
 * bundle entry 10 are declared here exactly as they are defined there.  A permanent source-shape
 * test asserts that these declarations and those definitions agree.
 */
extern const struct sock_filter mt4_s3c_outer_filter_program[];
extern const struct sock_fprog mt4_s3c_outer_filter_fprog;
extern const struct sock_filter mt4_s3c_internal_filter_program[];
extern const struct sock_fprog mt4_s3c_internal_filter_fprog;

#define MT4_S3C_PROBE_SCHEMA "mt4-s3c-canonical-policy-probe.v1"
#define MT4_S3C_PROBE_PLATFORM "LINUX_X86_64"
#define MT4_S3C_PROBE_MAX_INSTRUCTIONS 512
#define MT4_S3C_PROBE_ARG_WORDS 6

/* Exit statuses.  A probe failure is an infrastructure failure and never a crypto verdict. */
#define MT4_S3C_PROBE_OK 0
#define MT4_S3C_PROBE_STRUCTURE_INVALID 2
#define MT4_S3C_PROBE_WRITE_FAILED 3

static const char mt4_s3c_probe_hex_digits[] = "0123456789abcdef";

/*
 * Emit one sock_filter array as the canonical byte string of V9 13.2: for each instruction, u16
 * code little-endian, u8 jt, u8 jf, u32 k little-endian, concatenated in index order.  The bytes
 * are read from the exact in-image object, so the hashed form and the loaded form cannot diverge.
 */
static int mt4_s3c_probe_emit_program_hex(const struct sock_filter *program, unsigned int count)
{
    unsigned int index;

    for (index = 0; index < count; index++) {
        unsigned char encoded[8];
        unsigned int byte;

        encoded[0] = (unsigned char)(program[index].code & 0xffu);
        encoded[1] = (unsigned char)((program[index].code >> 8) & 0xffu);
        encoded[2] = (unsigned char)program[index].jt;
        encoded[3] = (unsigned char)program[index].jf;
        encoded[4] = (unsigned char)(program[index].k & 0xffu);
        encoded[5] = (unsigned char)((program[index].k >> 8) & 0xffu);
        encoded[6] = (unsigned char)((program[index].k >> 16) & 0xffu);
        encoded[7] = (unsigned char)((program[index].k >> 24) & 0xffu);

        for (byte = 0; byte < sizeof(encoded); byte++) {
            if (fputc(mt4_s3c_probe_hex_digits[(encoded[byte] >> 4) & 0x0fu], stdout) == EOF) {
                return MT4_S3C_PROBE_WRITE_FAILED;
            }
            if (fputc(mt4_s3c_probe_hex_digits[encoded[byte] & 0x0fu], stdout) == EOF) {
                return MT4_S3C_PROBE_WRITE_FAILED;
            }
        }
    }
    return MT4_S3C_PROBE_OK;
}

/*
 * Structural self-checks over the canonical source.  These are properties of the ARCHITECTURE, not
 * of the platform, so asserting them here is not a value assertion.  Every one of them fails closed.
 */
static int mt4_s3c_probe_check_structure(const struct sock_filter *program,
                                         const struct sock_fprog *fprog,
                                         unsigned int count)
{
    unsigned int index;

    if (program == NULL || fprog == NULL) {
        return MT4_S3C_PROBE_STRUCTURE_INVALID;
    }
    if (count < 1u || count > (unsigned int)MT4_S3C_PROBE_MAX_INSTRUCTIONS) {
        return MT4_S3C_PROBE_STRUCTURE_INVALID;
    }
    /* The fprog must reference EXACTLY the in-image array, not a copy of it (V9 13.3 E3/E4). */
    if (fprog->filter != program || (unsigned int)fprog->len != count) {
        return MT4_S3C_PROBE_STRUCTURE_INVALID;
    }
    /* The first instruction must load the audit architecture: arch check strictly first (STEP 1). */
    if (program[0].code != (unsigned short)(BPF_LD | BPF_W | BPF_ABS) ||
        program[0].k != (uint32_t)offsetof(struct seccomp_data, arch)) {
        return MT4_S3C_PROBE_STRUCTURE_INVALID;
    }
    /* The last instruction is the single shared kill block and the STEP 4 default action. */
    if (program[count - 1u].code != (unsigned short)(BPF_RET | BPF_K) ||
        program[count - 1u].k != (uint32_t)SECCOMP_RET_KILL_PROCESS) {
        return MT4_S3C_PROBE_STRUCTURE_INVALID;
    }
    for (index = 0; index < count; index++) {
        unsigned short code = program[index].code;

        /* A return action may only ever be ALLOW or KILL_PROCESS.  No third action exists. */
        if (code == (unsigned short)(BPF_RET | BPF_K)) {
            if (program[index].k != (uint32_t)SECCOMP_RET_ALLOW &&
                program[index].k != (uint32_t)SECCOMP_RET_KILL_PROCESS) {
                return MT4_S3C_PROBE_STRUCTURE_INVALID;
            }
            continue;
        }
        /* Every unconditional jump must stay inside the program and must not be backward. */
        if (code == (unsigned short)(BPF_JMP | BPF_JA)) {
            if (program[index].jt != 0 || program[index].jf != 0) {
                return MT4_S3C_PROBE_STRUCTURE_INVALID;
            }
            if ((uint64_t)index + 1u + (uint64_t)program[index].k >= (uint64_t)count) {
                return MT4_S3C_PROBE_STRUCTURE_INVALID;
            }
            continue;
        }
        /* Every conditional must skip exactly one instruction on exactly one side. */
        if (code == (unsigned short)(BPF_JMP | BPF_JEQ | BPF_K) ||
            code == (unsigned short)(BPF_JMP | BPF_JGE | BPF_K) ||
            code == (unsigned short)(BPF_JMP | BPF_JGT | BPF_K)) {
            if ((program[index].jt != 1u || program[index].jf != 0u) &&
                (program[index].jt != 0u || program[index].jf != 1u)) {
                return MT4_S3C_PROBE_STRUCTURE_INVALID;
            }
            if ((uint64_t)index + 2u > (uint64_t)count) {
                return MT4_S3C_PROBE_STRUCTURE_INVALID;
            }
            continue;
        }
        /* The only remaining permitted form is an absolute 32-bit load inside seccomp_data. */
        if (code == (unsigned short)(BPF_LD | BPF_W | BPF_ABS)) {
            if ((uint64_t)program[index].k + 4u > (uint64_t)sizeof(struct seccomp_data)) {
                return MT4_S3C_PROBE_STRUCTURE_INVALID;
            }
            continue;
        }
        return MT4_S3C_PROBE_STRUCTURE_INVALID;
    }
    return MT4_S3C_PROBE_OK;
}

static int mt4_s3c_probe_emit_arg_offsets(const char *name, int high_word)
{
    unsigned int index;

    if (printf("\"%s\":[", name) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    for (index = 0; index < (unsigned int)MT4_S3C_PROBE_ARG_WORDS; index++) {
        unsigned long offset = (unsigned long)(offsetof(struct seccomp_data, args) + (index * 8u));

        if (high_word) {
            offset += 4u;
        }
        if (printf("%s%lu", index ? "," : "", offset) < 0) {
            return MT4_S3C_PROBE_WRITE_FAILED;
        }
    }
    if (printf("]") < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    return MT4_S3C_PROBE_OK;
}

int main(void)
{
    const unsigned int outer_count = (unsigned int)mt4_s3c_outer_filter_fprog.len;
    const unsigned int internal_count = (unsigned int)mt4_s3c_internal_filter_fprog.len;
    int status;

    status = mt4_s3c_probe_check_structure(mt4_s3c_outer_filter_program, &mt4_s3c_outer_filter_fprog, outer_count);
    if (status != MT4_S3C_PROBE_OK) {
        (void)fprintf(stderr, "MT4_S3C_PROBE_OUTER_STRUCTURE_INVALID\n");
        return status;
    }
    status = mt4_s3c_probe_check_structure(mt4_s3c_internal_filter_program,
                                           &mt4_s3c_internal_filter_fprog,
                                           internal_count);
    if (status != MT4_S3C_PROBE_OK) {
        (void)fprintf(stderr, "MT4_S3C_PROBE_INTERNAL_STRUCTURE_INVALID\n");
        return status;
    }

    if (printf("{\"schema\":\"%s\",\"platform_id\":\"%s\",\"uapi\":{", MT4_S3C_PROBE_SCHEMA, MT4_S3C_PROBE_PLATFORM) <
        0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"audit_architecture_name\":\"AUDIT_ARCH_X86_64\",") < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"audit_architecture_value_u32\":%lu,", (unsigned long)(uint32_t)AUDIT_ARCH_X86_64) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"x32_syscall_bit_u32\":%lu,", (unsigned long)(uint32_t)__X32_SYSCALL_BIT) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"seccomp_set_mode_filter_u32\":%lu,", (unsigned long)(uint32_t)SECCOMP_SET_MODE_FILTER) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"seccomp_ret_allow_u32\":%lu,", (unsigned long)(uint32_t)SECCOMP_RET_ALLOW) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"seccomp_ret_kill_process_u32\":%lu,", (unsigned long)(uint32_t)SECCOMP_RET_KILL_PROCESS) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"pr_set_dumpable_u32\":%lu,", (unsigned long)(uint32_t)PR_SET_DUMPABLE) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"pr_set_no_new_privs_u32\":%lu,", (unsigned long)(uint32_t)PR_SET_NO_NEW_PRIVS) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"seccomp_data_offset_nr_u32\":%lu,", (unsigned long)offsetof(struct seccomp_data, nr)) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"seccomp_data_offset_arch_u32\":%lu,", (unsigned long)offsetof(struct seccomp_data, arch)) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (mt4_s3c_probe_emit_arg_offsets("seccomp_data_offset_arg_lo_u32", 0) != MT4_S3C_PROBE_OK) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf(",") < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (mt4_s3c_probe_emit_arg_offsets("seccomp_data_offset_arg_hi_u32", 1) != MT4_S3C_PROBE_OK) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf(",\"syscall_nr_u32\":{\"read\":%ld,\"write\":%ld,\"close\":%ld,\"execve\":%ld,"
               "\"prctl\":%ld,\"exit_group\":%ld,\"seccomp\":%ld,\"close_range\":%ld},",
               (long)__NR_read,
               (long)__NR_write,
               (long)__NR_close,
               (long)__NR_execve,
               (long)__NR_prctl,
               (long)__NR_exit_group,
               (long)__NR_seccomp,
               (long)__NR_close_range) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"bpf_opcode_u16\":{\"ld_w_abs\":%u,\"jmp_jeq_k\":%u,\"jmp_jge_k\":%u,"
               "\"jmp_jgt_k\":%u,\"jmp_ja\":%u,\"ret_k\":%u}},",
               (unsigned int)(unsigned short)(BPF_LD | BPF_W | BPF_ABS),
               (unsigned int)(unsigned short)(BPF_JMP | BPF_JEQ | BPF_K),
               (unsigned int)(unsigned short)(BPF_JMP | BPF_JGE | BPF_K),
               (unsigned int)(unsigned short)(BPF_JMP | BPF_JGT | BPF_K),
               (unsigned int)(unsigned short)(BPF_JMP | BPF_JA),
               (unsigned int)(unsigned short)(BPF_RET | BPF_K)) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }

    if (printf("\"programs\":{\"outer\":{\"instruction_count\":%u,\"instruction_bytes_hex\":\"", outer_count) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (mt4_s3c_probe_emit_program_hex(mt4_s3c_outer_filter_program, outer_count) != MT4_S3C_PROBE_OK) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"},\"internal\":{\"instruction_count\":%u,\"instruction_bytes_hex\":\"", internal_count) < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (mt4_s3c_probe_emit_program_hex(mt4_s3c_internal_filter_program, internal_count) != MT4_S3C_PROBE_OK) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (printf("\"}}}\n") < 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    if (fflush(stdout) != 0) {
        return MT4_S3C_PROBE_WRITE_FAILED;
    }
    return MT4_S3C_PROBE_OK;
}
