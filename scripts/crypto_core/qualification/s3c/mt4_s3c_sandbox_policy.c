/*
 * MT4-S3C P0 CANONICAL SANDBOX POLICY SOURCE.  Qualification infrastructure only.
 *
 * ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 12, 13, 14, 15.5.
 * BUNDLE ENTRY 10 of the exact 16-entry qualification source bundle (V9 SECTION 8).
 *
 * WHAT THIS TRANSLATION UNIT IS.  It is the single canonical definition of BOTH seccomp filter
 * programs used anywhere in S3C P0:
 *
 *   OUTER    installed by the launcher I immediately before the candidate execve.  Closed finite
 *            allowlist of EXACTLY EIGHT syscalls (V9 12.3).  Default SECCOMP_RET_KILL_PROCESS.
 *   INTERNAL installed by the candidate worker itself.  Allowed set exactly {read, write,
 *            exit_group} (V9 15.5).  Default SECCOMP_RET_KILL_PROCESS.
 *
 * WHAT THIS TRANSLATION UNIT IS NOT.  It confers no authority of any kind.  It performs no I/O,
 * holds no clock, reads no environment, and executes nothing.  It is DATA plus a compile-time
 * layout.  A successful build proves nothing about readiness, connectors, machine time, MT-5,
 * MT-6, Stage-4, live or shadow execution, orders, capital, or product-native loading.
 *
 * NO NUMERIC UAPI VALUE IS ASSERTED FROM MEMORY (V9 13.1).  Every audit architecture value, x32
 * marker, syscall number, prctl option, seccomp operation and seccomp return action below comes
 * from the pinned Linux UAPI headers through its macro name.  The only literals are the project's
 * OWN governed constants (the fixed descriptor numbers, the fixed frame lengths, the close_range
 * bounds) and the frozen instruction-layout offsets, which are a property of this architecture
 * rather than of the platform.
 *
 * NO PROJECT HEADER EXISTS.  The authorized S3C P0 path set contains no header file, so every
 * consumer of the four exported objects below declares exactly what it needs with its own extern
 * declaration.  A permanent source-shape test asserts those declarations agree with the
 * definitions here.
 *
 * FREESTANDING SAFE.  This unit is compiled into the freestanding no-libc worker as well as into
 * the hosted launcher and the hosted canonical probe.  It calls no function at all, defines no
 * constructor, allocates nothing, and contains no writable data.
 *
 * WHY BOTH PROGRAMS ARE COMPILE-TIME CONSTANT ARRAYS.  V9 SECTION 29.6 rule Q10 requires the
 * canonical internal sock_fprog object and the sock_filter array it references to each be exactly
 * one strong, hidden, section-defined object at a link-time-fixed address, lying entirely inside a
 * PT_LOAD whose EFFECTIVE page permission has PF_W CLEAR and entirely inside that segment's
 * FILE-BACKED range.  A runtime-constructed array would live in writable memory and could not
 * satisfy Q10, so leg L1 of V9 SECTION 15.2 would be unsound.  A const initialized object also
 * satisfies V9 13.3 E1..E5 by construction: there is exactly ONE definition of each program, it is
 * never rewritten, patched, re-sorted, re-compiled, copied through a transforming function or
 * reconstructed, and the bytes handed to the kernel are the bytes in the image.
 *
 * JUMP DISCIPLINE.  Classic BPF conditional jumps carry unsigned 8-bit jt/jf offsets and can
 * express neither a distance larger than 255 nor any backward distance.  Every conditional below
 * therefore skips exactly one instruction on success, and the instruction it skips is an
 * unconditional BPF_JA whose 32-bit k field carries the exact distance to the failure target.
 * That makes every jump distance representable regardless of program length, makes the emitted
 * layout a pure function of the semantic table, and keeps a SINGLE shared kill instruction at the
 * end of the program which is simultaneously the STEP 4 default action (V9 13.1).
 */

#include <asm/unistd.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/prctl.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdint.h>

/* ---------------------------------------------------------------------------------------------
 * GOVERNED PROJECT CONSTANTS.  These are this architecture's own values, not platform values.
 * ------------------------------------------------------------------------------------------- */

/* The candidate's fixed descriptor table is exactly {0,1,2,3,4} at exec (V9 17.2 step 13). */
#define MT4_S3C_FD_REQUEST 3
#define MT4_S3C_FD_RESPONSE 4

/* Fixed wire frame lengths (V9 20.2 and 20.3).  Nothing variable-length crosses the boundary. */
#define MT4_S3C_REQUEST_FRAME_BYTES 184
#define MT4_S3C_RESPONSE_FRAME_BYTES 8

/* close_range(5, UINT32_MAX, 0) in FD_CLOSURE (V9 12.3 and 14.4). */
#define MT4_S3C_CLOSE_RANGE_FIRST_FD 5
#define MT4_S3C_CLOSE_RANGE_MAX_FD 4294967295u

/* V9 13.2: MAX_FILTER_INSTRUCTIONS, enforced before any capture read. */
#define MT4_S3C_MAX_FILTER_INSTRUCTIONS 512

/*
 * Placement.  ".rodata.mt4_s3c_filter" merges into the read-only data of the final image, so the
 * objects land in a PT_LOAD whose effective page permission has PF_W clear and which is file
 * backed.  Hidden visibility keeps them un-interposable; V9 30 requires hidden visibility on every
 * qualification symbol and forbids exported symbols entirely.
 */
#define MT4_S3C_FILTER_RODATA __attribute__((section(".rodata.mt4_s3c_filter"), visibility("hidden"), used))

/* ---------------------------------------------------------------------------------------------
 * FROZEN INSTRUCTION LAYOUT.
 *
 * Every block length below is a frozen architectural constant.  The Python policy qualifier
 * (bundle entry 12) reproduces exactly these lengths and offsets when it INDEPENDENTLY derives the
 * canonical program from the semantic policy table, and the canonical probe (bundle entry 11)
 * reports the bytes this unit actually compiled to.  A disagreement between the two derivations is
 * OUTER_FILTER_EQUIVALENCE_FAILED or INTERNAL_FILTER_EQUIVALENCE_FAILED; it is never resolved in
 * favour of either side.
 * ------------------------------------------------------------------------------------------- */

#define MT4_S3C_LEN_PROLOGUE 6
#define MT4_S3C_LEN_NR_MATCH 3
#define MT4_S3C_LEN_ARG_EXACT 6
#define MT4_S3C_LEN_ARG_RANGE 8
#define MT4_S3C_LEN_ARG_POINTER 0
#define MT4_S3C_LEN_ARG_UNCONSTRAINED_SCALAR 0
#define MT4_S3C_LEN_ALLOW 1
#define MT4_S3C_LEN_KILL 1

/* Per-entry totals, each the exact sum of its own block lengths. */
#define MT4_S3C_ENTRY_LEN_READ 36
#define MT4_S3C_ENTRY_LEN_WRITE 36
#define MT4_S3C_ENTRY_LEN_CLOSE 114
#define MT4_S3C_ENTRY_LEN_EXECVE 22
#define MT4_S3C_ENTRY_LEN_PRCTL 77
#define MT4_S3C_ENTRY_LEN_EXIT_GROUP 34
#define MT4_S3C_ENTRY_LEN_SECCOMP 34
#define MT4_S3C_ENTRY_LEN_CLOSE_RANGE 40

/* Outer program bases, in the frozen ascending-syscall-number dispatch order. */
#define MT4_S3C_OUTER_BASE_PROLOGUE 0
#define MT4_S3C_OUTER_BASE_READ (MT4_S3C_OUTER_BASE_PROLOGUE + MT4_S3C_LEN_PROLOGUE)
#define MT4_S3C_OUTER_BASE_WRITE (MT4_S3C_OUTER_BASE_READ + MT4_S3C_ENTRY_LEN_READ)
#define MT4_S3C_OUTER_BASE_CLOSE (MT4_S3C_OUTER_BASE_WRITE + MT4_S3C_ENTRY_LEN_WRITE)
#define MT4_S3C_OUTER_BASE_EXECVE (MT4_S3C_OUTER_BASE_CLOSE + MT4_S3C_ENTRY_LEN_CLOSE)
#define MT4_S3C_OUTER_BASE_PRCTL (MT4_S3C_OUTER_BASE_EXECVE + MT4_S3C_ENTRY_LEN_EXECVE)
#define MT4_S3C_OUTER_BASE_EXIT_GROUP (MT4_S3C_OUTER_BASE_PRCTL + MT4_S3C_ENTRY_LEN_PRCTL)
#define MT4_S3C_OUTER_BASE_SECCOMP (MT4_S3C_OUTER_BASE_EXIT_GROUP + MT4_S3C_ENTRY_LEN_EXIT_GROUP)
#define MT4_S3C_OUTER_BASE_CLOSE_RANGE (MT4_S3C_OUTER_BASE_SECCOMP + MT4_S3C_ENTRY_LEN_SECCOMP)
#define MT4_S3C_OUTER_INDEX_KILL (MT4_S3C_OUTER_BASE_CLOSE_RANGE + MT4_S3C_ENTRY_LEN_CLOSE_RANGE)
#define MT4_S3C_OUTER_PROGRAM_LEN (MT4_S3C_OUTER_INDEX_KILL + MT4_S3C_LEN_KILL)

/* Internal program bases.  Same prologue, same three shared entries, same shared kill. */
#define MT4_S3C_INTERNAL_BASE_PROLOGUE 0
#define MT4_S3C_INTERNAL_BASE_READ (MT4_S3C_INTERNAL_BASE_PROLOGUE + MT4_S3C_LEN_PROLOGUE)
#define MT4_S3C_INTERNAL_BASE_WRITE (MT4_S3C_INTERNAL_BASE_READ + MT4_S3C_ENTRY_LEN_READ)
#define MT4_S3C_INTERNAL_BASE_EXIT_GROUP (MT4_S3C_INTERNAL_BASE_WRITE + MT4_S3C_ENTRY_LEN_WRITE)
#define MT4_S3C_INTERNAL_INDEX_KILL (MT4_S3C_INTERNAL_BASE_EXIT_GROUP + MT4_S3C_ENTRY_LEN_EXIT_GROUP)
#define MT4_S3C_INTERNAL_PROGRAM_LEN (MT4_S3C_INTERNAL_INDEX_KILL + MT4_S3C_LEN_KILL)

/* ---------------------------------------------------------------------------------------------
 * FROZEN ORDERING ASSERTIONS.
 *
 * V9 13.1 STEP 3 requires SYSCALL DISPATCH in FROZEN ASCENDING nr_u32 order, because that is what
 * makes the emitted program byte-deterministic given the policy.  This unit lays the entries out
 * in one fixed SOURCE order and asserts the pinned UAPI numbers are strictly ascending in exactly
 * that order.  The ordering RELATION is asserted; no numeric VALUE is asserted anywhere.  If a
 * future pinned UAPI renumbered these syscalls the build FAILS here rather than silently emitting
 * a non-canonical program.
 * ------------------------------------------------------------------------------------------- */

_Static_assert(__NR_read < __NR_write, "MT4_S3C canonical dispatch order: read < write");
_Static_assert(__NR_write < __NR_close, "MT4_S3C canonical dispatch order: write < close");
_Static_assert(__NR_close < __NR_execve, "MT4_S3C canonical dispatch order: close < execve");
_Static_assert(__NR_execve < __NR_prctl, "MT4_S3C canonical dispatch order: execve < prctl");
_Static_assert(__NR_prctl < __NR_exit_group, "MT4_S3C canonical dispatch order: prctl < exit_group");
_Static_assert(__NR_exit_group < __NR_seccomp, "MT4_S3C canonical dispatch order: exit_group < seccomp");
_Static_assert(__NR_seccomp < __NR_close_range, "MT4_S3C canonical dispatch order: seccomp < close_range");

/* ---------------------------------------------------------------------------------------------
 * seccomp_data field offsets, taken from the pinned UAPI struct rather than assumed.
 *
 * V9 13.1 64-BIT ARGUMENT COMPARISON RULE: seccomp_data args are 64-bit and classic BPF is 32-bit,
 * so EVERY argument comparison compares the HIGH word first and requires it to equal 0, then
 * compares the LOW word.  A rule comparing only the low word is a bypass, not a simplification.
 * ------------------------------------------------------------------------------------------- */

#define MT4_S3C_OFF_NR ((uint32_t)offsetof(struct seccomp_data, nr))
#define MT4_S3C_OFF_ARCH ((uint32_t)offsetof(struct seccomp_data, arch))
#define MT4_S3C_OFF_ARG_LO(index) ((uint32_t)(offsetof(struct seccomp_data, args) + ((index) * 8u)))
#define MT4_S3C_OFF_ARG_HI(index) ((uint32_t)(offsetof(struct seccomp_data, args) + ((index) * 8u) + 4u))

_Static_assert(sizeof(((struct seccomp_data *)0)->args[0]) == 8, "MT4_S3C requires 64-bit seccomp_data args");
_Static_assert(sizeof(((struct seccomp_data *)0)->arch) == 4, "MT4_S3C requires a 32-bit seccomp_data arch");
_Static_assert(sizeof(struct sock_filter) == 8, "MT4_S3C canonical cBPF representation requires 8-byte insns");

/* ---------------------------------------------------------------------------------------------
 * INSTRUCTION EMISSION MACROS.  Each takes the ABSOLUTE index of its first instruction so that the
 * unconditional failure jumps can be computed exactly and checked by inspection.
 * ------------------------------------------------------------------------------------------- */

/* Unconditional jump from absolute index `from` to absolute index `target`. */
#define MT4_S3C_JA(from, target) BPF_STMT(BPF_JMP | BPF_JA, (uint32_t)((target) - (from) - 1))

/* MT4_S3C_LEN_PROLOGUE instructions.  STEP 1 arch check first, then STEP 2 x32 rejection. */
#define MT4_S3C_PROLOGUE(base, kill)                                                                   \
    BPF_STMT(BPF_LD | BPF_W | BPF_ABS, MT4_S3C_OFF_ARCH),                                              \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)AUDIT_ARCH_X86_64, 1, 0),                        \
        MT4_S3C_JA((base) + 2, (kill)), BPF_STMT(BPF_LD | BPF_W | BPF_ABS, MT4_S3C_OFF_NR),            \
        BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, (uint32_t)__X32_SYSCALL_BIT, 0, 1),                        \
        MT4_S3C_JA((base) + 5, (kill))

/* MT4_S3C_LEN_NR_MATCH instructions.  Reloads the UNMODIFIED nr field; never a masked value. */
#define MT4_S3C_NR_MATCH(base, number, target)                                                         \
    BPF_STMT(BPF_LD | BPF_W | BPF_ABS, MT4_S3C_OFF_NR),                                                \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)(number), 1, 0), MT4_S3C_JA((base) + 2, (target))

/* MT4_S3C_LEN_ARG_EXACT instructions.  High word must be zero, then the low word must be exact. */
#define MT4_S3C_ARG_EXACT(base, target, index, value)                                                  \
    BPF_STMT(BPF_LD | BPF_W | BPF_ABS, MT4_S3C_OFF_ARG_HI(index)),                                     \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0u, 1, 0), MT4_S3C_JA((base) + 2, (target)),               \
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, MT4_S3C_OFF_ARG_LO(index)),                                 \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)(value), 1, 0), MT4_S3C_JA((base) + 5, (target))

/* MT4_S3C_LEN_ARG_RANGE instructions.  High word zero, then min <= low <= max, inclusive. */
#define MT4_S3C_ARG_RANGE(base, target, index, min_value, max_value)                                   \
    BPF_STMT(BPF_LD | BPF_W | BPF_ABS, MT4_S3C_OFF_ARG_HI(index)),                                     \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0u, 1, 0), MT4_S3C_JA((base) + 2, (target)),               \
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, MT4_S3C_OFF_ARG_LO(index)),                                 \
        BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, (uint32_t)(min_value), 1, 0),                              \
        MT4_S3C_JA((base) + 5, (target)),                                                              \
        BPF_JUMP(BPF_JMP | BPF_JGT | BPF_K, (uint32_t)(max_value), 0, 1),                              \
        MT4_S3C_JA((base) + 7, (target))

/* MT4_S3C_LEN_ALLOW instruction. */
#define MT4_S3C_ALLOW() BPF_STMT(BPF_RET | BPF_K, (uint32_t)SECCOMP_RET_ALLOW)

/* MT4_S3C_LEN_KILL instruction.  The SINGLE shared kill block AND the STEP 4 default action. */
#define MT4_S3C_KILL() BPF_STMT(BPF_RET | BPF_K, (uint32_t)SECCOMP_RET_KILL_PROCESS)

/* ---------------------------------------------------------------------------------------------
 * PER-ENTRY COMPOSITES.  Each expands to exactly its MT4_S3C_ENTRY_LEN_* count.  Every one of the
 * six seccomp_data argument words is classified in every entry: exact, range, unconstrained
 * pointer, unconstrained scalar, or zero-required.  A rule that left an index unclassified would
 * be malformed and is not representable here.
 * ------------------------------------------------------------------------------------------- */

/*
 * read: arg0 exactly the request descriptor, arg1 an unconstrained pointer, arg2 a bounded length,
 * args 3..5 zero-required.  36 = 3 + 6 + 0 + 8 + 6 + 6 + 6 + 1.
 */
#define MT4_S3C_ENTRY_READ(base, next_entry, kill)                                                                 \
    MT4_S3C_NR_MATCH((base) + 0, __NR_read, (next_entry)),                                                   \
        MT4_S3C_ARG_EXACT((base) + 3, (kill), 0, MT4_S3C_FD_REQUEST),                                  \
        MT4_S3C_ARG_RANGE((base) + 9, (kill), 2, 1, MT4_S3C_REQUEST_FRAME_BYTES),                      \
        MT4_S3C_ARG_EXACT((base) + 17, (kill), 3, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 23, (kill), 4, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 29, (kill), 5, 0), MT4_S3C_ALLOW()

/*
 * write: arg0 exactly the response descriptor, arg1 an unconstrained pointer, arg2 a bounded
 * length, args 3..5 zero-required.  Both RESULT_CLASSes use this one 8-byte write (V9 12.3).
 */
#define MT4_S3C_ENTRY_WRITE(base, next_entry, kill)                                                                \
    MT4_S3C_NR_MATCH((base) + 0, __NR_write, (next_entry)),                                                  \
        MT4_S3C_ARG_EXACT((base) + 3, (kill), 0, MT4_S3C_FD_RESPONSE),                                 \
        MT4_S3C_ARG_RANGE((base) + 9, (kill), 2, 1, MT4_S3C_RESPONSE_FRAME_BYTES),                     \
        MT4_S3C_ARG_EXACT((base) + 17, (kill), 3, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 23, (kill), 4, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 29, (kill), 5, 0), MT4_S3C_ALLOW()

/*
 * close: THREE discriminated exact tuples, one per legal descriptor, so that no rule shape carries
 * an implicit set (V9 14.4).  A failure inside tuple N jumps to the first instruction of tuple
 * N+1; the last tuple's failures jump to the shared kill.  37 = 6*6 + 1 per tuple.
 */
#define MT4_S3C_CLOSE_TUPLE(base, target, fd)                                                          \
    MT4_S3C_ARG_EXACT((base) + 0, (target), 0, (fd)),                                                  \
        MT4_S3C_ARG_EXACT((base) + 6, (target), 1, 0),                                                 \
        MT4_S3C_ARG_EXACT((base) + 12, (target), 2, 0),                                                \
        MT4_S3C_ARG_EXACT((base) + 18, (target), 3, 0),                                                \
        MT4_S3C_ARG_EXACT((base) + 24, (target), 4, 0),                                                \
        MT4_S3C_ARG_EXACT((base) + 30, (target), 5, 0), MT4_S3C_ALLOW()

#define MT4_S3C_ENTRY_CLOSE(base, next_entry, kill)                                                                \
    MT4_S3C_NR_MATCH((base) + 0, __NR_close, (next_entry)),                                                  \
        MT4_S3C_CLOSE_TUPLE((base) + 3, (base) + 40, 0),                                               \
        MT4_S3C_CLOSE_TUPLE((base) + 40, (base) + 77, 1),                                              \
        MT4_S3C_CLOSE_TUPLE((base) + 77, (kill), 2)

/* execve: args 0..2 unconstrained pointers (pathname, argv, envp), args 3..5 zero-required. */
#define MT4_S3C_ENTRY_EXECVE(base, next_entry, kill)                                                               \
    MT4_S3C_NR_MATCH((base) + 0, __NR_execve, (next_entry)),                                                 \
        MT4_S3C_ARG_EXACT((base) + 3, (kill), 3, 0),                                                   \
        MT4_S3C_ARG_EXACT((base) + 9, (kill), 4, 0),                                                   \
        MT4_S3C_ARG_EXACT((base) + 15, (kill), 5, 0), MT4_S3C_ALLOW()

/*
 * prctl: TWO discriminated exact tuples (V9 14.5).  PR_SET_DUMPABLE is accepted ONLY with argument
 * 1 equal to zero, so the candidate may make itself non-dumpable and may never make itself
 * dumpable again.  PR_SET_NO_NEW_PRIVS is accepted ONLY with argument 1 equal to one.  Every other
 * argument in every position, including the sixth word that the five-argument prctl does not
 * consume, must be zero; that sixth word is a property of the project-owned freestanding wrapper
 * (V9 14.3), not an assumption about the platform.
 */
#define MT4_S3C_PRCTL_TUPLE(base, target, option, value1)                                              \
    MT4_S3C_ARG_EXACT((base) + 0, (target), 0, (option)),                                              \
        MT4_S3C_ARG_EXACT((base) + 6, (target), 1, (value1)),                                          \
        MT4_S3C_ARG_EXACT((base) + 12, (target), 2, 0),                                                \
        MT4_S3C_ARG_EXACT((base) + 18, (target), 3, 0),                                                \
        MT4_S3C_ARG_EXACT((base) + 24, (target), 4, 0),                                                \
        MT4_S3C_ARG_EXACT((base) + 30, (target), 5, 0), MT4_S3C_ALLOW()

#define MT4_S3C_ENTRY_PRCTL(base, next_entry, kill)                                                                \
    MT4_S3C_NR_MATCH((base) + 0, __NR_prctl, (next_entry)),                                                  \
        MT4_S3C_PRCTL_TUPLE((base) + 3, (base) + 40, PR_SET_DUMPABLE, 0),                              \
        MT4_S3C_PRCTL_TUPLE((base) + 40, (kill), PR_SET_NO_NEW_PRIVS, 1)

/*
 * exit_group: argument 0 is an UNCONSTRAINED_SCALAR by deliberate decision (V9 14.4).  Constraining
 * the exit status in classic BPF was considered and REJECTED, because an out-of-taxonomy exit would
 * then be KILLED by seccomp and would present as a containment violation, destroying failure
 * attribution.  The exit-status taxonomy is enforced by the adjudicator over the observed wait
 * status instead, where a violation is correctly typed.  Arguments 1..5 remain zero-required.
 */
#define MT4_S3C_ENTRY_EXIT_GROUP(base, next_entry, kill)                                                           \
    MT4_S3C_NR_MATCH((base) + 0, __NR_exit_group, (next_entry)),                                             \
        MT4_S3C_ARG_EXACT((base) + 3, (kill), 1, 0),                                                   \
        MT4_S3C_ARG_EXACT((base) + 9, (kill), 2, 0),                                                   \
        MT4_S3C_ARG_EXACT((base) + 15, (kill), 3, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 21, (kill), 4, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 27, (kill), 5, 0), MT4_S3C_ALLOW()

/*
 * seccomp: operation exactly SECCOMP_SET_MODE_FILTER, flags exactly zero, argument 2 the
 * unconstrained sock_fprog pointer whose containment is structural (the trusted observer captures
 * it at the syscall-entry stop), arguments 3..5 zero-required.
 */
#define MT4_S3C_ENTRY_SECCOMP(base, next_entry, kill)                                                              \
    MT4_S3C_NR_MATCH((base) + 0, __NR_seccomp, (next_entry)),                                                \
        MT4_S3C_ARG_EXACT((base) + 3, (kill), 0, SECCOMP_SET_MODE_FILTER),                             \
        MT4_S3C_ARG_EXACT((base) + 9, (kill), 1, 0),                                                   \
        MT4_S3C_ARG_EXACT((base) + 15, (kill), 3, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 21, (kill), 4, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 27, (kill), 5, 0), MT4_S3C_ALLOW()

/* close_range: exactly close_range(5, MT4_S3C_CLOSE_RANGE_MAX_FD, 0), args 3..5 zero-required. */
#define MT4_S3C_ENTRY_CLOSE_RANGE(base, next_entry, kill)                                                          \
    MT4_S3C_NR_MATCH((base) + 0, __NR_close_range, (next_entry)),                                            \
        MT4_S3C_ARG_EXACT((base) + 3, (kill), 0, MT4_S3C_CLOSE_RANGE_FIRST_FD),                        \
        MT4_S3C_ARG_EXACT((base) + 9, (kill), 1, MT4_S3C_CLOSE_RANGE_MAX_FD),                          \
        MT4_S3C_ARG_EXACT((base) + 15, (kill), 2, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 21, (kill), 3, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 27, (kill), 4, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 33, (kill), 5, 0), MT4_S3C_ALLOW()

/* ---------------------------------------------------------------------------------------------
 * THE OUTER PROGRAM.  Exactly one definition; never rewritten, patched or reconstructed.
 * ------------------------------------------------------------------------------------------- */

MT4_S3C_FILTER_RODATA
const struct sock_filter mt4_s3c_outer_filter_program[MT4_S3C_OUTER_PROGRAM_LEN] = {
    MT4_S3C_PROLOGUE(MT4_S3C_OUTER_BASE_PROLOGUE, MT4_S3C_OUTER_INDEX_KILL),
    MT4_S3C_ENTRY_READ(MT4_S3C_OUTER_BASE_READ, MT4_S3C_OUTER_BASE_WRITE, MT4_S3C_OUTER_INDEX_KILL),
    MT4_S3C_ENTRY_WRITE(MT4_S3C_OUTER_BASE_WRITE, MT4_S3C_OUTER_BASE_CLOSE, MT4_S3C_OUTER_INDEX_KILL),
    MT4_S3C_ENTRY_CLOSE(MT4_S3C_OUTER_BASE_CLOSE, MT4_S3C_OUTER_BASE_EXECVE, MT4_S3C_OUTER_INDEX_KILL),
    MT4_S3C_ENTRY_EXECVE(MT4_S3C_OUTER_BASE_EXECVE, MT4_S3C_OUTER_BASE_PRCTL, MT4_S3C_OUTER_INDEX_KILL),
    MT4_S3C_ENTRY_PRCTL(MT4_S3C_OUTER_BASE_PRCTL, MT4_S3C_OUTER_BASE_EXIT_GROUP, MT4_S3C_OUTER_INDEX_KILL),
    MT4_S3C_ENTRY_EXIT_GROUP(MT4_S3C_OUTER_BASE_EXIT_GROUP, MT4_S3C_OUTER_BASE_SECCOMP, MT4_S3C_OUTER_INDEX_KILL),
    MT4_S3C_ENTRY_SECCOMP(MT4_S3C_OUTER_BASE_SECCOMP, MT4_S3C_OUTER_BASE_CLOSE_RANGE, MT4_S3C_OUTER_INDEX_KILL),
    MT4_S3C_ENTRY_CLOSE_RANGE(MT4_S3C_OUTER_BASE_CLOSE_RANGE, MT4_S3C_OUTER_INDEX_KILL,
                              MT4_S3C_OUTER_INDEX_KILL),
    MT4_S3C_KILL(),
};

MT4_S3C_FILTER_RODATA
const struct sock_fprog mt4_s3c_outer_filter_fprog = {
    .len = (unsigned short)MT4_S3C_OUTER_PROGRAM_LEN,
    .filter = (struct sock_filter *)mt4_s3c_outer_filter_program,
};

/* ---------------------------------------------------------------------------------------------
 * THE INTERNAL PROGRAM.  Allowed set exactly {read, write, exit_group}.
 *
 * Effective authority after internal installation is the INTERSECTION of the two filters, because
 * all installed filters participate in every syscall decision and filters can never be
 * uninstalled.  The internal filter can therefore only narrow the outer one, never widen it.
 * ------------------------------------------------------------------------------------------- */

/* ---------------------------------------------------------------------------------------------
 * TEST-ONLY INTERNAL FILTER MUTATION (permanent test PT-141).
 *
 * WHY THIS EXISTS.  PT-141 has to prove that a filter the WORKER ITSELF emits, differing from the
 * canonical one, is rejected by the qualification chain.  Constructing different bytes in Python
 * and handing them to the adjudicator does not prove that: it exercises the consumer against a
 * fabricated input, not the producer's own emission path.  The mutation therefore lives HERE, in
 * the source that actually emits the worker's internal filter.
 *
 * WHY PRODUCTION CANNOT ENABLE IT BY ACCIDENT.  It requires TWO macros to be defined together, one
 * of which spells out that the result is not qualifiable, and defining only the first is a
 * compile-time error rather than a silently mutated filter.  Neither macro appears anywhere in the
 * qualification workflow, and a permanent test asserts that.
 *
 * WHAT IT CHANGES.  Exactly one argument constant in the worker's own read entry: the request
 * descriptor the internal filter permits.  The instruction COUNT is unchanged, so the mutant still
 * builds and still installs -- which is the point.  The bytes differ, so the captured program can
 * no longer equal the canonical one, and the equivalence digest cannot match.  Nothing else moves:
 * the outer filter, the probe, the trusted reference and the receipt framework are untouched.
 * ------------------------------------------------------------------------------------------- */

#ifdef MT4_S3C_TEST_ONLY_INTERNAL_FILTER_MUTANT
#ifndef MT4_S3C_TEST_ONLY_NOT_QUALIFIABLE
#error "MT4_S3C_TEST_ONLY_INTERNAL_FILTER_MUTANT requires MT4_S3C_TEST_ONLY_NOT_QUALIFIABLE"
#endif
/* The mutated worker permits reading a DIFFERENT descriptor than the governed request descriptor. */
#define MT4_S3C_INTERNAL_READ_FD 0
#else
#define MT4_S3C_INTERNAL_READ_FD MT4_S3C_FD_REQUEST
#endif

/*
 * The internal read entry, written out so the mutable descriptor constant is visible at exactly one
 * place.  The shape is identical to MT4_S3C_ENTRY_READ; only the descriptor is parameterised.
 */
#define MT4_S3C_ENTRY_READ_INTERNAL(base, next_entry, kill)                                                        \
    MT4_S3C_NR_MATCH((base) + 0, __NR_read, (next_entry)),                                                   \
        MT4_S3C_ARG_EXACT((base) + 3, (kill), 0, MT4_S3C_INTERNAL_READ_FD),                            \
        MT4_S3C_ARG_RANGE((base) + 9, (kill), 2, 1, MT4_S3C_REQUEST_FRAME_BYTES),                      \
        MT4_S3C_ARG_EXACT((base) + 17, (kill), 3, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 23, (kill), 4, 0),                                                  \
        MT4_S3C_ARG_EXACT((base) + 29, (kill), 5, 0), MT4_S3C_ALLOW()

MT4_S3C_FILTER_RODATA
const struct sock_filter mt4_s3c_internal_filter_program[MT4_S3C_INTERNAL_PROGRAM_LEN] = {
    MT4_S3C_PROLOGUE(MT4_S3C_INTERNAL_BASE_PROLOGUE, MT4_S3C_INTERNAL_INDEX_KILL),
    MT4_S3C_ENTRY_READ_INTERNAL(MT4_S3C_INTERNAL_BASE_READ, MT4_S3C_INTERNAL_BASE_WRITE,
                                MT4_S3C_INTERNAL_INDEX_KILL),
    MT4_S3C_ENTRY_WRITE(MT4_S3C_INTERNAL_BASE_WRITE, MT4_S3C_INTERNAL_BASE_EXIT_GROUP,
                        MT4_S3C_INTERNAL_INDEX_KILL),
    MT4_S3C_ENTRY_EXIT_GROUP(MT4_S3C_INTERNAL_BASE_EXIT_GROUP, MT4_S3C_INTERNAL_INDEX_KILL,
                             MT4_S3C_INTERNAL_INDEX_KILL),
    MT4_S3C_KILL(),
};

MT4_S3C_FILTER_RODATA
const struct sock_fprog mt4_s3c_internal_filter_fprog = {
    .len = (unsigned short)MT4_S3C_INTERNAL_PROGRAM_LEN,
    .filter = (struct sock_filter *)mt4_s3c_internal_filter_program,
};

/* ---------------------------------------------------------------------------------------------
 * FROZEN SIZE PROOFS.  A layout arithmetic slip anywhere above changes an array length and fails
 * the build here rather than emitting a program whose jump targets are wrong.
 * ------------------------------------------------------------------------------------------- */

_Static_assert(sizeof(mt4_s3c_outer_filter_program) / sizeof(struct sock_filter) == MT4_S3C_OUTER_PROGRAM_LEN,
               "MT4_S3C outer program length must equal the frozen layout total");
_Static_assert(sizeof(mt4_s3c_internal_filter_program) / sizeof(struct sock_filter) ==
                   MT4_S3C_INTERNAL_PROGRAM_LEN,
               "MT4_S3C internal program length must equal the frozen layout total");
_Static_assert(MT4_S3C_OUTER_PROGRAM_LEN <= MT4_S3C_MAX_FILTER_INSTRUCTIONS,
               "MT4_S3C outer program must fit the governed instruction bound");
_Static_assert(MT4_S3C_INTERNAL_PROGRAM_LEN <= MT4_S3C_MAX_FILTER_INSTRUCTIONS,
               "MT4_S3C internal program must fit the governed instruction bound");
_Static_assert(MT4_S3C_OUTER_PROGRAM_LEN == 400, "MT4_S3C frozen outer program length");
_Static_assert(MT4_S3C_INTERNAL_PROGRAM_LEN == 113, "MT4_S3C frozen internal program length");
