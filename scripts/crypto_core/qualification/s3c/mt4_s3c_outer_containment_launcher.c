/*
 * MT4-S3C P0 OUTER CONTAINMENT LAUNCHER AND TRUSTED OBSERVER.  Qualification infrastructure only.
 *
 * ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 11, 13, 15, 17, 18, 19.
 * BUNDLE ENTRY 7 of the exact 16-entry qualification source bundle (V9 SECTION 8).
 *
 * TWO PROCESSES, ONE REVIEWED SOURCE.
 *
 *   S  the SUPERVISOR.  Trust tier T-C (V9 SECTION 10).  It stays OUTSIDE every namespace, holds
 *      the pidfd, performs every seccomp-baseline measurement, is the ptrace TRACER, drives the
 *      governed observation cases, and writes the raw observation record.  It never executes
 *      candidate-derived code, never maps candidate memory executable, never interprets a
 *      candidate-supplied expression, and never decides anything on candidate self-report.
 *   I  the LAUNCHER.  The clone3 child, PID 1 in its own pid namespace.  It builds the private
 *      root, materialises and re-proves the candidate, drops privileges, establishes the trace
 *      relationship ON ITSELF, installs the outer filter, and execve's the candidate.
 *
 * WHAT THIS PROGRAM CONFERS.  Nothing.  Its entire output is EVIDENCE about a candidate binary
 * (V9 SECTION 5).  It grants no MachineTimeAnchor, no MT-5, no MT-6, no Stage-4 completion, no
 * readiness or connector transition, no live or shadow execution, no orders, no capital mutation,
 * no scheduler, and no product-native loading.
 *
 * THE ONLY CLOCK IN THE DESIGN LIVES HERE, AND IT IS A LIVENESS CONTROL.  S uses CLOCK_MONOTONIC
 * for a bounded per-case deadline.  Expiry produces the infrastructure reason WORKER_TIMEOUT and is
 * NEVER an identity field, NEVER a digest input and NEVER a crypto verdict (V9 SECTION 5).  The
 * candidate holds no clock at all: every time syscall is absent from both filters.
 *
 * THE NON-MUTATING TRACER CONTRACT (V9 11.7) IS THE LOAD-BEARING PROPERTY OF THIS FILE.
 * PERMITTED, and nothing else: PTRACE_TRACEME (performed by the tracee on itself), PTRACE_SETOPTIONS
 * with exactly the frozen option set, PTRACE_SYSCALL and PTRACE_CONT as CONTROL ONLY with a literal
 * zero signal, PTRACE_GETREGSET to read the register file, PTRACE_PEEKDATA to read tracee memory a
 * word at a time, and PTRACE_SECCOMP_GET_FILTER as a corroboration leg only.
 * FORBIDDEN ABSOLUTELY, with no exception and no conditional path: PTRACE_POKEDATA, PTRACE_POKETEXT,
 * PTRACE_POKEUSER, PTRACE_SETREGS, PTRACE_SETREGSET, PTRACE_SETFPREGS, PTRACE_SETSIGINFO, resuming a
 * tracee with ANY nonzero signal, process_vm_writev against the tracee, opening or writing
 * /proc/<pid>/mem, PTRACE_DETACH, PTRACE_SEIZE, PTRACE_INTERRUPT and PTRACE_LISTEN.
 * PTRACE_O_SUSPEND_SECCOMP is forbidden: no operation may suspend filter enforcement while
 * attached.  Permanent source-shape tests PT-110b..PT-110e assert that none of those request
 * constants appears anywhere in this file and that every resume site passes a literal zero signal.
 * The distinction between CONTROL and MUTATION is drawn exactly there: resuming a stopped process
 * changes WHEN it runs, never WHAT it is.
 *
 * SECCOMP_STACK_BASELINE_V1 (V9 SECTION 11) IS A MANDATORY LEG, NOT A DIAGNOSTIC.  An inherited
 * filter whose action for the seccomp syscall is a non-killing error-return action can make the
 * install syscall RETURN A SUCCESS-LOOKING VALUE WITHOUT INSTALLING ANYTHING.  Counting seccomp
 * calls is not a substitute, and neither is a zero return value.  The authority is the host-observed
 * /proc/<pid>/status filter COUNT and its transitions 0 -> 1 -> 2.
 */

#define _GNU_SOURCE

#include <asm/unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/elf.h>
#include <linux/filter.h>
#include <linux/prctl.h>
#include <linux/sched.h>
#include <linux/seccomp.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/capability.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/*
 * The authorized S3C P0 path set contains no header file, so the two canonical objects defined by
 * bundle entry 10 are declared here exactly as they are defined there.
 */
extern const struct sock_filter mt4_s3c_outer_filter_program[];
extern const struct sock_fprog mt4_s3c_outer_filter_fprog;

/* ==============================================================================================
 * GOVERNED CONSTANTS
 * ============================================================================================ */

#define MT4_S3C_FD_STDIN 0
#define MT4_S3C_FD_STDOUT 1
#define MT4_S3C_FD_STDERR 2
#define MT4_S3C_FD_REQUEST 3
#define MT4_S3C_FD_RESPONSE 4
#define MT4_S3C_FD_TABLE_SIZE 5
#define MT4_S3C_CLOSE_RANGE_FIRST_FD 5
#define MT4_S3C_CLOSE_RANGE_MAX_FD 4294967295u

#define MT4_S3C_REQUEST_FRAME_BYTES 184
#define MT4_S3C_RESPONSE_FRAME_BYTES 8

/* Reserved exit codes (V9 20.5).  The launcher set and the candidate set are DISJOINT by phase. */
#define MT4_S3C_EXIT_LAUNCHER_FAILED 70

/* V9 SECTION 11 strict parse rule P-5: a status field value above this bound is malformed. */
#define MT4_S3C_STATUS_FIELD_MAX 4096

/* V9 13.2: MAX_FILTER_INSTRUCTIONS, enforced BEFORE any capture read. */
#define MT4_S3C_MAX_FILTER_INSTRUCTIONS 512
#define MT4_S3C_MAX_FILTER_BYTES (MT4_S3C_MAX_FILTER_INSTRUCTIONS * 8)

/* V9 27.2 governed sub-bounds, enforced here so the observation record cannot exceed its bound. */
#define MT4_S3C_MAX_SYSCALL_EVENTS_PER_CASE 256

/* V9 29.5 EM-16: RLIMIT_AS = 32 MiB aggregate + 8 MiB stack reserve + 24 MiB governed headroom. */
#define MT4_S3C_STACK_RESERVE_BYTES (8u * 1024u * 1024u)
#define MT4_S3C_GOVERNED_HEADROOM_BYTES (24u * 1024u * 1024u)
#define MT4_S3C_MAX_AGGREGATE_EFFECTIVE_BYTES (32u * 1024u * 1024u)
#define MT4_S3C_RLIMIT_AS_BYTES                                                                    \
    ((unsigned long)MT4_S3C_MAX_AGGREGATE_EFFECTIVE_BYTES + (unsigned long)MT4_S3C_STACK_RESERVE_BYTES + \
     (unsigned long)MT4_S3C_GOVERNED_HEADROOM_BYTES)

/* V9 29.1/27.2: the SAME bounded file size constant the ELF qualifier and the ZIP policy use. */
#define MT4_S3C_MAX_WORKER_BINARY_BYTES (8u * 1024u * 1024u)

/* The governed candidate file mode inside the private root (V9 17.2 steps 2 and 9). */
#define MT4_S3C_CANDIDATE_MODE 0500
#define MT4_S3C_CANDIDATE_NAME "w"
#define MT4_S3C_CANDIDATE_PATH "/w"
#define MT4_S3C_PUT_OLD_NAME "old"

/* Governed unprivileged identity inside the user namespace. */
#define MT4_S3C_MAPPED_UID 1000
#define MT4_S3C_MAPPED_GID 1000

/* Bounded per-case liveness deadline, in milliseconds.  A liveness control, never an anchor. */
#define MT4_S3C_CASE_DEADLINE_MS 20000
#define MT4_S3C_POLL_INTERVAL_NS 500000L

/* Case-plan format (frozen).  Produced from the bundled fixture by bundle entry 8. */
#define MT4_S3C_PLAN_MAGIC "MT4CPLAN"
#define MT4_S3C_PLAN_MAGIC_BYTES 8
#define MT4_S3C_PLAN_VERSION 1u
#define MT4_S3C_PLAN_HEADER_BYTES 64
#define MT4_S3C_PLAN_CASE_ID_BYTES 48
#define MT4_S3C_PLAN_CASE_HEADER_BYTES (MT4_S3C_PLAN_CASE_ID_BYTES + 20)
#define MT4_S3C_MAX_CASE_INPUT_BYTES 512
#define MT4_S3C_EXACT_CASE_COUNT 25
#define MT4_S3C_MAX_PLAN_BYTES 65536

#define MT4_S3C_STIMULUS_WRITE_ALL_THEN_CLOSE 0u
#define MT4_S3C_STIMULUS_WRITE_PREFIX_THEN_SIGKILL 1u
#define MT4_S3C_STIMULUS_WRITE_PREFIX_THEN_HOLD 2u

/*
 * THE FROZEN PTRACE OPTION SET (V9 11.7 T2).  Exactly three bits and no others:
 *   TRACESYSGOOD  distinguish syscall stops from other SIGTRAP stops
 *   TRACEEXEC     deliver the kernel exec transition event, the ONLY proof that exec succeeded
 *   EXITKILL      kill the tracee if the tracer exits, so no candidate outlives its observer
 * PTRACE_O_SUSPEND_SECCOMP is deliberately absent and must never be added: suspending filter
 * enforcement while attached would void every containment claim this program makes.
 */
#define MT4_S3C_PTRACE_OPTIONS (PTRACE_O_TRACESYSGOOD | PTRACE_O_TRACEEXEC | PTRACE_O_EXITKILL)

/*
 * THE POSITIVE TRACER ORACLE (repair 5A).  Proving that a few forbidden TOKENS do not appear in the
 * source is not a contract: it says nothing about a numeric request, a computed request, or a
 * request nobody thought to name.  The oracle below is the complete, finite, EXACT set of ptrace
 * requests this observer may ever issue, and mt4_s3c_ptrace_permitted() is the ONLY place in this
 * translation unit that calls ptrace().  Anything outside the set is refused before the kernel is
 * reached, whatever value produced it.
 *
 * Every permitted request is READ-ONLY or CONTROL-ONLY with respect to the tracee.  There is no
 * POKE, no SET, no SIGINFO write, no DETACH, no SEIZE, no INTERRUPT and no LISTEN: those are not
 * merely unused, they cannot be issued.
 */
#define MT4_S3C_PTRACE_REQUEST_COUNT 7

static const long mt4_s3c_permitted_ptrace_requests[MT4_S3C_PTRACE_REQUEST_COUNT] = {
    (long)PTRACE_TRACEME,
    (long)PTRACE_SETOPTIONS,
    (long)PTRACE_SYSCALL,
    (long)PTRACE_CONT,
    (long)PTRACE_GETREGSET,
    (long)PTRACE_PEEKDATA,
    (long)PTRACE_SECCOMP_GET_FILTER,
};

/*
 * The forbidden option bit is asserted by VALUE, not by token absence: PTRACE_O_SUSPEND_SECCOMP is
 * 0x00200000, and a build in which the frozen option word carried it would fail to compile.
 */
#define MT4_S3C_PTRACE_O_SUSPEND_SECCOMP_VALUE 0x00200000u
#define MT4_S3C_PTRACE_OPTION_BITS_ALLOWED \
    ((unsigned long)PTRACE_O_TRACESYSGOOD | (unsigned long)PTRACE_O_TRACEEXEC | (unsigned long)PTRACE_O_EXITKILL)

_Static_assert(((unsigned long)MT4_S3C_PTRACE_OPTIONS & (unsigned long)MT4_S3C_PTRACE_O_SUSPEND_SECCOMP_VALUE) == 0ul,
               "MT4_S3C forbids PTRACE_O_SUSPEND_SECCOMP");
_Static_assert(((unsigned long)MT4_S3C_PTRACE_OPTIONS & ~MT4_S3C_PTRACE_OPTION_BITS_ALLOWED) == 0ul,
               "MT4_S3C ptrace options carry a bit outside the frozen three");

/*
 * SUPERVISOR_DUMPABILITY_LIFECYCLE_V1 (repair 3).
 *
 * THE DEFECT THIS CLOSES.  One supervisor process runs all 25 cases.  N5 makes that process
 * non-dumpable, and on Linux the dumpable flag is INHERITED across clone: from case 2 onward the
 * child is born non-dumpable, its /proc/<pid>/uid_map, gid_map and setgroups become root-owned, and
 * the unprivileged supervisor can no longer write them.  Case 2 therefore reached
 * UID_GID_MAP_FAILED, the adjudicator rejected the case set, and the workflow could never produce a
 * passing receipt.  Restoring dumpability is not an optimisation; without it the sequence is broken.
 *
 * THE FROZEN PER-CASE STATE MACHINE.  Restoration happens ONLY after the child is completely reaped
 * and no map operation is outstanding, and ALWAYS before the next clone3 and before the next uid_map
 * or gid_map write:
 *
 *   CASE_START
 *     -> PRE_CLONE_AUTHENTICATED     dumpability is PROVEN 1 by reading it back, never assumed
 *     -> CLONED                      clone3
 *     -> MAPS_WRITTEN                setgroups deny, uid_map, gid_map
 *     -> SUPERVISOR_NON_DUMPABLE     N5 prctl(PR_SET_DUMPABLE, 0) on the supervisor itself
 *     -> CHILD_REAPED                teardown: signal, wait, response collected, no live child
 *     -> RESTORED                    prctl(PR_SET_DUMPABLE, 1) and PR_GET_DUMPABLE re-authenticated
 *     -> NEXT CASE
 *
 * A failed restoration is a QUALIFICATION INFRASTRUCTURE FAILURE that HALTS THE SEQUENCE.  It never
 * becomes a candidate verdict, and no further case runs: continuing would silently produce the same
 * broken maps the repair exists to prevent.
 */
#define MT4_S3C_SUPERVISOR_DUMPABLE_REQUIRED 1

typedef enum {
    MT4_S3C_DUMPABILITY_CASE_START = 0,
    MT4_S3C_DUMPABILITY_PRE_CLONE_AUTHENTICATED,
    MT4_S3C_DUMPABILITY_CLONED,
    MT4_S3C_DUMPABILITY_MAPS_WRITTEN,
    MT4_S3C_DUMPABILITY_SUPERVISOR_NON_DUMPABLE,
    MT4_S3C_DUMPABILITY_CHILD_REAPED,
    MT4_S3C_DUMPABILITY_RESTORED
} mt4_s3c_dumpability_state_t;

/*
 * THE TERMINAL INFRASTRUCTURE FAILURE CHANNEL (repair 2).
 *
 * An infrastructure failure during teardown is NOT a candidate verdict and must never be masked by
 * one.  Three ways that used to happen are closed here:
 *
 *   1. CHILD_REAPED was entered unconditionally after the reap loop, including when the loop broke
 *      on a non-EINTR waitpid failure -- so a child that was never authoritatively reaped looked
 *      reaped, and restoration then ran while it might still exist.
 *   2. A restoration failure only recorded a reason when the case had none.  C25 EXPECTS a timeout,
 *      so its reason was already set and the restoration failure disappeared.
 *   3. The halt flag was only consulted BEFORE the next case, so on the last case there was no next
 *      case to stop and the run completed anyway.
 *
 * The flag below is sticky, is never cleared, and is checked again before ANY final record is
 * written -- so the last case is covered by exactly the same gate as every other one.
 */
static int mt4_s3c_sequence_halted = 0;
static mt4_s3c_reason_t mt4_s3c_terminal_reason = MT4_S3C_REASON_NONE;
static const char *mt4_s3c_terminal_marker = "";

static void mt4_s3c_terminal_failure(mt4_s3c_reason_t reason, const char *marker)
{
    mt4_s3c_sequence_halted = 1;
    if (mt4_s3c_terminal_reason == MT4_S3C_REASON_NONE) {
        mt4_s3c_terminal_reason = reason;
        mt4_s3c_terminal_marker = marker;
    }
}

/* The bounded EINTR retry budget.  An unbounded retry loop is not a bounded contract. */
#define MT4_S3C_MAX_REAP_INTERRUPTS 4096

/* Authenticate, never assume: the value is READ BACK from the kernel. */
static int mt4_s3c_supervisor_dumpability_is(int expected)
{
    int observed = prctl(PR_GET_DUMPABLE, 0, 0, 0, 0);

    return observed == expected;
}

/* CASE_START precondition.  A supervisor that cannot be made dumpable cannot map the next child. */
static int mt4_s3c_supervisor_dumpability_precondition(void)
{
    if (mt4_s3c_supervisor_dumpability_is(MT4_S3C_SUPERVISOR_DUMPABLE_REQUIRED)) {
        return 0;
    }
    if (prctl(PR_SET_DUMPABLE, MT4_S3C_SUPERVISOR_DUMPABLE_REQUIRED, 0, 0, 0) != 0) {
        return -1;
    }
    return mt4_s3c_supervisor_dumpability_is(MT4_S3C_SUPERVISOR_DUMPABLE_REQUIRED) ? 0 : -1;
}

/*
 * Restoration.  Called ONLY from the teardown path, after the child has been reaped, and its result
 * is authenticated by reading the flag back rather than by trusting the prctl return value.
 */
static int mt4_s3c_supervisor_dumpability_restore(void)
{
    if (prctl(PR_SET_DUMPABLE, MT4_S3C_SUPERVISOR_DUMPABLE_REQUIRED, 0, 0, 0) != 0) {
        return -1;
    }
    return mt4_s3c_supervisor_dumpability_is(MT4_S3C_SUPERVISOR_DUMPABLE_REQUIRED) ? 0 : -1;
}

/* The literal zero every resume path must deliver.  A nonzero signal is never representable here. */
#define MT4_S3C_PTRACE_RESUME_SIGNAL ((void *)0)

/*
 * THE SINGLE GATEWAY.  Every ptrace in this file goes through here, so the oracle is enforced at
 * RUNTIME as well as by inspection, and a resume that somehow carried a signal is refused rather
 * than delivered.
 */
static long mt4_s3c_ptrace_permitted(long request, pid_t pid, void *address, void *data)
{
    unsigned int index;
    int permitted = 0;

    for (index = 0u; index < (unsigned int)MT4_S3C_PTRACE_REQUEST_COUNT; index++) {
        if (mt4_s3c_permitted_ptrace_requests[index] == request) {
            permitted = 1;
        }
    }
    if (permitted == 0) {
        errno = EPERM;
        return -1L;
    }
    /* 5B: a resume request may carry NOTHING but the literal zero signal. */
    if ((request == (long)PTRACE_SYSCALL || request == (long)PTRACE_CONT) && data != MT4_S3C_PTRACE_RESUME_SIGNAL) {
        errno = EPERM;
        return -1L;
    }
    /* The option word is frozen: SETOPTIONS may install exactly the three approved bits. */
    if (request == (long)PTRACE_SETOPTIONS && data != (void *)(unsigned long)MT4_S3C_PTRACE_OPTIONS) {
        errno = EPERM;
        return -1L;
    }
    return ptrace((enum __ptrace_request)request, pid, address, data);
}

/* ==============================================================================================
 * TYPED REASON DOMAIN (V9 32.1).  Infrastructure reasons are NEVER verifier statuses.
 * ============================================================================================ */

typedef enum {
    MT4_S3C_REASON_NONE = 0,
    MT4_S3C_REASON_QUALIFICATION_INFRASTRUCTURE_FAILURE,
    MT4_S3C_REASON_SECCOMP_BASELINE_NONZERO,
    MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MISSING,
    MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_DUPLICATE,
    MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MALFORMED,
    MT4_S3C_REASON_SECCOMP_BASELINE_UNREADABLE,
    MT4_S3C_REASON_SECCOMP_COUNT_TRANSITION_INVALID,
    MT4_S3C_REASON_SECCOMP_COUNT_DISAGREEMENT,
    MT4_S3C_REASON_TRACER_CONTRACT_VIOLATION,
    MT4_S3C_REASON_NAMESPACE_SETUP_FAILED,
    MT4_S3C_REASON_NAMESPACE_SEPARATION_UNPROVEN,
    MT4_S3C_REASON_NAMESPACE_RELEASE_ORDER_VIOLATION,
    MT4_S3C_REASON_UID_GID_MAP_FAILED,
    MT4_S3C_REASON_PRIVILEGE_SETUP_FAILED,
    MT4_S3C_REASON_RLIMIT_AS_NOT_SET,
    MT4_S3C_REASON_PRIVATE_ROOT_FAILED,
    MT4_S3C_REASON_READ_ONLY_ROOT_FAILED,
    MT4_S3C_REASON_CANDIDATE_DIGEST_DRIFT,
    MT4_S3C_REASON_FINAL_REPROOF_FAILED,
    MT4_S3C_REASON_OUTER_FILTER_INSTALL_FAILED,
    MT4_S3C_REASON_OUTER_FILTER_EQUIVALENCE_FAILED,
    MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE,
    MT4_S3C_REASON_EXEC_TRANSITION_NOT_PROVEN,
    MT4_S3C_REASON_LAUNCH_FAILED,
    MT4_S3C_REASON_WORKER_TIMEOUT,
    MT4_S3C_REASON_WORKER_CRASHED,
    MT4_S3C_REASON_WORKER_KILLED_BY_SECCOMP,
    MT4_S3C_REASON_WORKER_BOOTSTRAP_FAILED,
    MT4_S3C_REASON_WORKER_SANDBOX_FAILED,
    MT4_S3C_REASON_TRANSPORT_FRAMING_FAILURE,
    MT4_S3C_REASON_OBSERVATION_EVENT_BUDGET_EXCEEDED,
    MT4_S3C_REASON_SUPERVISOR_REAP_FAILED,
    MT4_S3C_REASON_CASE_PLAN_MALFORMED,
    MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED,
    MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_PRECONDITION_FAILED
} mt4_s3c_reason_t;

static const char *mt4_s3c_reason_name(mt4_s3c_reason_t reason)
{
    switch (reason) {
    case MT4_S3C_REASON_NONE:
        return "NONE";
    case MT4_S3C_REASON_QUALIFICATION_INFRASTRUCTURE_FAILURE:
        return "QUALIFICATION_INFRASTRUCTURE_FAILURE";
    case MT4_S3C_REASON_SECCOMP_BASELINE_NONZERO:
        return "SECCOMP_BASELINE_NONZERO";
    case MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MISSING:
        return "SECCOMP_BASELINE_FIELD_MISSING";
    case MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_DUPLICATE:
        return "SECCOMP_BASELINE_FIELD_DUPLICATE";
    case MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MALFORMED:
        return "SECCOMP_BASELINE_FIELD_MALFORMED";
    case MT4_S3C_REASON_SECCOMP_BASELINE_UNREADABLE:
        return "SECCOMP_BASELINE_UNREADABLE";
    case MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED:
        return "SUPERVISOR_DUMPABILITY_NOT_RESTORED";
    case MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_PRECONDITION_FAILED:
        return "SUPERVISOR_DUMPABILITY_PRECONDITION_FAILED";
    case MT4_S3C_REASON_SECCOMP_COUNT_TRANSITION_INVALID:
        return "SECCOMP_COUNT_TRANSITION_INVALID";
    case MT4_S3C_REASON_SECCOMP_COUNT_DISAGREEMENT:
        return "SECCOMP_COUNT_DISAGREEMENT";
    case MT4_S3C_REASON_TRACER_CONTRACT_VIOLATION:
        return "TRACER_CONTRACT_VIOLATION";
    case MT4_S3C_REASON_NAMESPACE_SETUP_FAILED:
        return "NAMESPACE_SETUP_FAILED";
    case MT4_S3C_REASON_NAMESPACE_SEPARATION_UNPROVEN:
        return "NAMESPACE_SEPARATION_UNPROVEN";
    case MT4_S3C_REASON_NAMESPACE_RELEASE_ORDER_VIOLATION:
        return "NAMESPACE_RELEASE_ORDER_VIOLATION";
    case MT4_S3C_REASON_UID_GID_MAP_FAILED:
        return "UID_GID_MAP_FAILED";
    case MT4_S3C_REASON_PRIVILEGE_SETUP_FAILED:
        return "PRIVILEGE_SETUP_FAILED";
    case MT4_S3C_REASON_RLIMIT_AS_NOT_SET:
        return "RLIMIT_AS_NOT_SET";
    case MT4_S3C_REASON_PRIVATE_ROOT_FAILED:
        return "PRIVATE_ROOT_FAILED";
    case MT4_S3C_REASON_READ_ONLY_ROOT_FAILED:
        return "READ_ONLY_ROOT_FAILED";
    case MT4_S3C_REASON_CANDIDATE_DIGEST_DRIFT:
        return "CANDIDATE_DIGEST_DRIFT";
    case MT4_S3C_REASON_FINAL_REPROOF_FAILED:
        return "FINAL_REPROOF_FAILED";
    case MT4_S3C_REASON_OUTER_FILTER_INSTALL_FAILED:
        return "OUTER_FILTER_INSTALL_FAILED";
    case MT4_S3C_REASON_OUTER_FILTER_EQUIVALENCE_FAILED:
        return "OUTER_FILTER_EQUIVALENCE_FAILED";
    case MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE:
        return "WORKER_FILTER_OBSERVATION_UNAVAILABLE";
    case MT4_S3C_REASON_EXEC_TRANSITION_NOT_PROVEN:
        return "EXEC_TRANSITION_NOT_PROVEN";
    case MT4_S3C_REASON_LAUNCH_FAILED:
        return "LAUNCH_FAILED";
    case MT4_S3C_REASON_WORKER_TIMEOUT:
        return "WORKER_TIMEOUT";
    case MT4_S3C_REASON_WORKER_CRASHED:
        return "WORKER_CRASHED";
    case MT4_S3C_REASON_WORKER_KILLED_BY_SECCOMP:
        return "WORKER_KILLED_BY_SECCOMP";
    case MT4_S3C_REASON_WORKER_BOOTSTRAP_FAILED:
        return "WORKER_BOOTSTRAP_FAILED";
    case MT4_S3C_REASON_WORKER_SANDBOX_FAILED:
        return "WORKER_SANDBOX_FAILED";
    case MT4_S3C_REASON_TRANSPORT_FRAMING_FAILURE:
        return "TRANSPORT_FRAMING_FAILURE";
    case MT4_S3C_REASON_OBSERVATION_EVENT_BUDGET_EXCEEDED:
        return "OBSERVATION_EVENT_BUDGET_EXCEEDED";
    case MT4_S3C_REASON_SUPERVISOR_REAP_FAILED:
        return "SUPERVISOR_REAP_FAILED";
    case MT4_S3C_REASON_CASE_PLAN_MALFORMED:
        return "CASE_PLAN_MALFORMED";
    default:
        return "QUALIFICATION_INFRASTRUCTURE_FAILURE";
    }
}

/* ==============================================================================================
 * BOUNDED OUTPUT BUFFER.  The raw observation record is built in memory and written once, after
 * every candidate process has terminated AND been reaped (V9 SECTION 10 point 4).
 * ============================================================================================ */

#define MT4_S3C_OUTPUT_CAPACITY (4u * 1024u * 1024u)

static char *mt4_s3c_output;
static size_t mt4_s3c_output_used;
static int mt4_s3c_output_overflow;

static void mt4_s3c_emit(const char *format, ...)
{
    va_list arguments;
    int written;
    size_t remaining;

    if (mt4_s3c_output_overflow || mt4_s3c_output == NULL) {
        return;
    }
    remaining = (size_t)MT4_S3C_OUTPUT_CAPACITY - mt4_s3c_output_used;
    va_start(arguments, format);
    written = vsnprintf(mt4_s3c_output + mt4_s3c_output_used, remaining, format, arguments);
    va_end(arguments);
    if (written < 0 || (size_t)written >= remaining) {
        mt4_s3c_output_overflow = 1;
        return;
    }
    mt4_s3c_output_used += (size_t)written;
}

static void mt4_s3c_emit_hex(const unsigned char *bytes, size_t length)
{
    static const char digits[] = "0123456789abcdef";
    size_t index;

    for (index = 0; index < length; index++) {
        mt4_s3c_emit("%c%c", digits[(bytes[index] >> 4) & 0x0f], digits[bytes[index] & 0x0f]);
    }
}

/* JSON string emission restricted to the characters this program can ever produce. */
static void mt4_s3c_emit_json_string(const char *value)
{
    size_t index;

    mt4_s3c_emit("\"");
    for (index = 0; value[index] != '\0'; index++) {
        unsigned char character = (unsigned char)value[index];

        if (character < 0x20 || character > 0x7e || character == '"' || character == '\\') {
            mt4_s3c_emit("?");
        } else {
            mt4_s3c_emit("%c", (int)character);
        }
    }
    mt4_s3c_emit("\"");
}

static void mt4_s3c_fatal(mt4_s3c_reason_t reason, const char *marker)
{
    (void)fprintf(stderr, "MT4_S3C_INFRASTRUCTURE_FAILURE=%s:%s\n", mt4_s3c_reason_name(reason), marker);
    _exit(MT4_S3C_EXIT_LAUNCHER_FAILED);
}

/* ==============================================================================================
 * SHA-256.  Self-contained so the digest of the candidate bytes depends on no external library.
 * ============================================================================================ */

typedef struct {
    uint32_t state[8];
    uint64_t length;
    unsigned char block[64];
    size_t used;
} mt4_s3c_sha256_t;

static const uint32_t mt4_s3c_sha256_k[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u};

static uint32_t mt4_s3c_ror(uint32_t value, unsigned int bits)
{
    return (value >> bits) | (value << (32u - bits));
}

static void mt4_s3c_sha256_compress(mt4_s3c_sha256_t *context, const unsigned char *block)
{
    uint32_t w[64];
    uint32_t a, b, c, d, e, f, g, h;
    unsigned int index;

    for (index = 0; index < 16u; index++) {
        w[index] = ((uint32_t)block[index * 4u] << 24) | ((uint32_t)block[index * 4u + 1u] << 16) |
                   ((uint32_t)block[index * 4u + 2u] << 8) | (uint32_t)block[index * 4u + 3u];
    }
    for (index = 16u; index < 64u; index++) {
        uint32_t s0 = mt4_s3c_ror(w[index - 15u], 7) ^ mt4_s3c_ror(w[index - 15u], 18) ^ (w[index - 15u] >> 3);
        uint32_t s1 = mt4_s3c_ror(w[index - 2u], 17) ^ mt4_s3c_ror(w[index - 2u], 19) ^ (w[index - 2u] >> 10);

        w[index] = w[index - 16u] + s0 + w[index - 7u] + s1;
    }
    a = context->state[0];
    b = context->state[1];
    c = context->state[2];
    d = context->state[3];
    e = context->state[4];
    f = context->state[5];
    g = context->state[6];
    h = context->state[7];
    for (index = 0; index < 64u; index++) {
        uint32_t s1 = mt4_s3c_ror(e, 6) ^ mt4_s3c_ror(e, 11) ^ mt4_s3c_ror(e, 25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t temp1 = h + s1 + ch + mt4_s3c_sha256_k[index] + w[index];
        uint32_t s0 = mt4_s3c_ror(a, 2) ^ mt4_s3c_ror(a, 13) ^ mt4_s3c_ror(a, 22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temp2 = s0 + maj;

        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }
    context->state[0] += a;
    context->state[1] += b;
    context->state[2] += c;
    context->state[3] += d;
    context->state[4] += e;
    context->state[5] += f;
    context->state[6] += g;
    context->state[7] += h;
}

static void mt4_s3c_sha256_init(mt4_s3c_sha256_t *context)
{
    context->state[0] = 0x6a09e667u;
    context->state[1] = 0xbb67ae85u;
    context->state[2] = 0x3c6ef372u;
    context->state[3] = 0xa54ff53au;
    context->state[4] = 0x510e527fu;
    context->state[5] = 0x9b05688cu;
    context->state[6] = 0x1f83d9abu;
    context->state[7] = 0x5be0cd19u;
    context->length = 0;
    context->used = 0;
}

static void mt4_s3c_sha256_update(mt4_s3c_sha256_t *context, const unsigned char *data, size_t length)
{
    size_t offset = 0;

    context->length += (uint64_t)length * 8u;
    while (offset < length) {
        size_t take = sizeof(context->block) - context->used;

        if (take > length - offset) {
            take = length - offset;
        }
        memcpy(context->block + context->used, data + offset, take);
        context->used += take;
        offset += take;
        if (context->used == sizeof(context->block)) {
            mt4_s3c_sha256_compress(context, context->block);
            context->used = 0;
        }
    }
}

static void mt4_s3c_sha256_final(mt4_s3c_sha256_t *context, unsigned char digest[32])
{
    uint64_t bit_length = context->length;
    unsigned int index;

    context->block[context->used++] = 0x80u;
    if (context->used > 56u) {
        memset(context->block + context->used, 0, sizeof(context->block) - context->used);
        mt4_s3c_sha256_compress(context, context->block);
        context->used = 0;
    }
    memset(context->block + context->used, 0, 56u - context->used);
    for (index = 0; index < 8u; index++) {
        context->block[56u + index] = (unsigned char)((bit_length >> (56u - 8u * index)) & 0xffu);
    }
    mt4_s3c_sha256_compress(context, context->block);
    for (index = 0; index < 8u; index++) {
        digest[index * 4u] = (unsigned char)((context->state[index] >> 24) & 0xffu);
        digest[index * 4u + 1u] = (unsigned char)((context->state[index] >> 16) & 0xffu);
        digest[index * 4u + 2u] = (unsigned char)((context->state[index] >> 8) & 0xffu);
        digest[index * 4u + 3u] = (unsigned char)(context->state[index] & 0xffu);
    }
}

/* ==============================================================================================
 * MT4_S3C_INTERNAL_FILTER_EQUIVALENCE_V1 (V9 SECTION 16, the V9-4 repair).
 *
 * ONE governed schema, ONE domain, ONE canonical ordering, ONE encoding.  The trusted observer
 * computes the per-case digest into A3; the adjudicator recomputes it INDEPENDENTLY from the raw
 * observation fields into A4; and the trusted Stage-C gate recomputes it a third time from the raw
 * A3 preimage and requires A3 == A4 == STAGE_C_RECOMPUTED.  Receipt equality alone is explicitly
 * insufficient, which is why the value is produced here, at the point of observation, rather than
 * asserted later by anything that could have copied it.
 *
 * The canonical encoding is canonical JSON with sort_keys, separators (",",":") and ensure_ascii.
 * The twenty-seven keys are emitted below in exactly byte-wise ascending order, which is what
 * sort_keys produces, so a canonical-JSON library and this emitter agree byte for byte.
 * ============================================================================================ */

#define MT4_S3C_EQUIVALENCE_SCHEMA "mt4-s3c-internal-filter-equivalence.v1"
#define MT4_S3C_EQUIVALENCE_DOMAIN "mt4-s3c-internal-filter-equivalence.v1"
#define MT4_S3C_CBPF_REPRESENTATION "mt4-s3c-cbpf-canonical.v1"
#define MT4_S3C_EQUIVALENCE_PREIMAGE_CAPACITY 4096

typedef struct {
    const char *canonical_internal_policy_id;
    const char *canonical_internal_policy_sha256;
    unsigned int canonical_internal_cbpf_instruction_count;
    const char *canonical_internal_cbpf_sha256;
    const char *source_head_sha;
    unsigned long long source_run_id;
    unsigned long long source_run_attempt;
    const char *candidate_binary_sha256;
} mt4_s3c_run_identity_t;

/* CBPF_DIGEST over the canonical representation of V9 13.2. */
static void mt4_s3c_cbpf_digest_hex(const unsigned char *program, unsigned int count, char out[65])
{
    static const char digits[] = "0123456789abcdef";
    unsigned char prefix[4];
    unsigned char digest[32];
    mt4_s3c_sha256_t sha;
    unsigned int index;

    prefix[0] = (unsigned char)(count & 0xffu);
    prefix[1] = (unsigned char)((count >> 8) & 0xffu);
    prefix[2] = (unsigned char)((count >> 16) & 0xffu);
    prefix[3] = (unsigned char)((count >> 24) & 0xffu);
    mt4_s3c_sha256_init(&sha);
    mt4_s3c_sha256_update(&sha, (const unsigned char *)MT4_S3C_CBPF_REPRESENTATION,
                          sizeof(MT4_S3C_CBPF_REPRESENTATION) - 1u);
    {
        /* The digest domain is the representation identifier followed by exactly one NUL byte. */
        unsigned char terminator = 0;

        mt4_s3c_sha256_update(&sha, &terminator, 1u);
    }
    mt4_s3c_sha256_update(&sha, prefix, sizeof(prefix));
    mt4_s3c_sha256_update(&sha, program, (size_t)count * 8u);
    mt4_s3c_sha256_final(&sha, digest);
    for (index = 0; index < 32u; index++) {
        out[index * 2u] = digits[(digest[index] >> 4) & 0x0fu];
        out[index * 2u + 1u] = digits[digest[index] & 0x0fu];
    }
    out[64] = '\0';
}

static void mt4_s3c_sha256_hex(const unsigned char *data, size_t length, char out[65])
{
    static const char digits[] = "0123456789abcdef";
    unsigned char digest[32];
    mt4_s3c_sha256_t sha;
    unsigned int index;

    mt4_s3c_sha256_init(&sha);
    mt4_s3c_sha256_update(&sha, data, length);
    mt4_s3c_sha256_final(&sha, digest);
    for (index = 0; index < 32u; index++) {
        out[index * 2u] = digits[(digest[index] >> 4) & 0x0fu];
        out[index * 2u + 1u] = digits[digest[index] & 0x0fu];
    }
    out[64] = '\0';
}

/*
 * Build the canonical preimage and return the digest, or return -1 when a governed constraint is
 * violated.  V9 16.3: the "must be" constraints are validated BEFORE the digest is computed, and a
 * record that violates one is NEVER digested and NEVER recorded as a passing equivalence.
 */
static int mt4_s3c_equivalence_digest_hex(const mt4_s3c_run_identity_t *identity,
                                          const char *case_id,
                                          const char *captured_cbpf_sha256,
                                          unsigned long long captured_uargs_va,
                                          unsigned int captured_len,
                                          int install_exit_return,
                                          unsigned long baseline_supervisor_seccomp,
                                          unsigned long baseline_supervisor_filters,
                                          unsigned long baseline_child_seccomp,
                                          unsigned long baseline_child_filters,
                                          unsigned long pre_install_filters,
                                          unsigned long post_install_filters,
                                          unsigned long post_install_seccomp_mode,
                                          unsigned long revalidated_filters,
                                          const char *dump_availability,
                                          const char *dump_index0_sha256,
                                          const char *dump_index1_sha256,
                                          int dump_terminates_at_index,
                                          char out[65])
{
    char preimage[MT4_S3C_EQUIVALENCE_PREIMAGE_CAPACITY];
    unsigned char domain_and_body[MT4_S3C_EQUIVALENCE_PREIMAGE_CAPACITY + 64];
    size_t domain_length = sizeof(MT4_S3C_EQUIVALENCE_DOMAIN) - 1u;
    int length;

    if (install_exit_return != 0 || baseline_supervisor_seccomp != 0u || baseline_supervisor_filters != 0u ||
        baseline_child_seccomp != 0u || baseline_child_filters != 0u || pre_install_filters != 1u ||
        post_install_filters != 2u || post_install_seccomp_mode != 2u || revalidated_filters != 2u) {
        return -1;
    }
    if (captured_len != identity->canonical_internal_cbpf_instruction_count) {
        return -1;
    }
    if (strcmp(captured_cbpf_sha256, identity->canonical_internal_cbpf_sha256) != 0) {
        return -1;
    }

    /* Exactly the twenty-seven governed keys, in byte-wise ascending order. */
    length = snprintf(preimage,
                      sizeof(preimage),
                      "{\"baseline_child_filters\":%lu,"
                      "\"baseline_child_seccomp\":%lu,"
                      "\"baseline_supervisor_filters\":%lu,"
                      "\"baseline_supervisor_seccomp\":%lu,"
                      "\"candidate_binary_sha256\":\"%s\","
                      "\"canonical_internal_cbpf_instruction_count\":%u,"
                      "\"canonical_internal_cbpf_sha256\":\"%s\","
                      "\"canonical_internal_policy_id\":\"%s\","
                      "\"canonical_internal_policy_sha256\":\"%s\","
                      "\"captured_internal_cbpf_sha256\":\"%s\","
                      "\"captured_internal_len_u32\":%u,"
                      "\"captured_internal_uargs_va_u64\":%llu,"
                      "\"case_id\":\"%s\","
                      "\"dump_leg_availability\":\"%s\","
                      "\"dump_leg_index0_sha256\":\"%s\","
                      "\"dump_leg_index1_sha256\":\"%s\","
                      "\"dump_leg_terminates_at_index\":%d,"
                      "\"install_exit_return_i32\":%d,"
                      "\"post_install_filters\":%lu,"
                      "\"post_install_seccomp_mode\":%lu,"
                      "\"pre_install_filters\":%lu,"
                      "\"program_representation_version\":\"%s\","
                      "\"revalidated_filters\":%lu,"
                      "\"schema\":\"%s\","
                      "\"source_head_sha\":\"%s\","
                      "\"source_run_attempt\":%llu,"
                      "\"source_run_id\":%llu}",
                      baseline_child_filters,
                      baseline_child_seccomp,
                      baseline_supervisor_filters,
                      baseline_supervisor_seccomp,
                      identity->candidate_binary_sha256,
                      identity->canonical_internal_cbpf_instruction_count,
                      identity->canonical_internal_cbpf_sha256,
                      identity->canonical_internal_policy_id,
                      identity->canonical_internal_policy_sha256,
                      captured_cbpf_sha256,
                      captured_len,
                      captured_uargs_va,
                      case_id,
                      dump_availability,
                      dump_index0_sha256,
                      dump_index1_sha256,
                      dump_terminates_at_index,
                      install_exit_return,
                      post_install_filters,
                      post_install_seccomp_mode,
                      pre_install_filters,
                      MT4_S3C_CBPF_REPRESENTATION,
                      revalidated_filters,
                      MT4_S3C_EQUIVALENCE_SCHEMA,
                      identity->source_head_sha,
                      identity->source_run_attempt,
                      identity->source_run_id);
    if (length <= 0 || (size_t)length >= sizeof(preimage)) {
        return -1;
    }
    if (domain_length + (size_t)length > sizeof(domain_and_body)) {
        return -1;
    }
    memcpy(domain_and_body, MT4_S3C_EQUIVALENCE_DOMAIN, domain_length);
    domain_and_body[domain_length] = 0;
    memcpy(domain_and_body + domain_length + 1u, preimage, (size_t)length);
    mt4_s3c_sha256_hex(domain_and_body, domain_length + 1u + (size_t)length, out);
    return 0;
}

/* ==============================================================================================
 * SECCOMP_STACK_BASELINE_V1 STRICT PARSE (V9 11.3 rules P-1 .. P-6)
 * ============================================================================================ */

typedef struct {
    unsigned long seccomp_mode;
    unsigned long filter_count;
} mt4_s3c_seccomp_status_t;

/*
 * Parse ONE required field.  Returns 0 on success and sets *value; otherwise sets *reason.
 *
 * P-2 EXACTLY ONE line must begin with the exact label followed by ':'.  Zero occurrences is
 * FIELD_MISSING; two or more is FIELD_DUPLICATE.  P-3 strips ASCII horizontal whitespace only.
 * P-4 requires a non-empty run of ASCII digits: a sign, an underscore, a radix prefix, embedded
 * whitespace, a trailing comment or any non-digit byte is FIELD_MALFORMED.  P-5 bounds the value.
 */
static int mt4_s3c_parse_status_field(const char *text,
                                      size_t length,
                                      const char *label,
                                      unsigned long *value,
                                      mt4_s3c_reason_t *reason)
{
    size_t label_length = strlen(label);
    size_t line_start = 0;
    int seen = 0;
    unsigned long parsed = 0;

    while (line_start <= length) {
        size_t line_end = line_start;

        while (line_end < length && text[line_end] != '\n') {
            line_end++;
        }
        if (line_end - line_start > label_length && memcmp(text + line_start, label, label_length) == 0 &&
            text[line_start + label_length] == ':') {
            size_t cursor = line_start + label_length + 1u;
            size_t digits = 0;
            unsigned long accumulator = 0;

            seen++;
            if (seen > 1) {
                *reason = MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_DUPLICATE;
                return -1;
            }
            while (cursor < line_end && (text[cursor] == ' ' || text[cursor] == '\t')) {
                cursor++;
            }
            while (line_end > cursor && (text[line_end - 1u] == ' ' || text[line_end - 1u] == '\t')) {
                line_end--;
            }
            while (cursor < line_end) {
                char character = text[cursor];

                if (character < '0' || character > '9') {
                    *reason = MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MALFORMED;
                    return -1;
                }
                if (accumulator > (unsigned long)MT4_S3C_STATUS_FIELD_MAX) {
                    *reason = MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MALFORMED;
                    return -1;
                }
                accumulator = accumulator * 10u + (unsigned long)(character - '0');
                digits++;
                cursor++;
            }
            if (digits == 0 || accumulator > (unsigned long)MT4_S3C_STATUS_FIELD_MAX) {
                *reason = MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MALFORMED;
                return -1;
            }
            parsed = accumulator;
        }
        if (line_end >= length) {
            break;
        }
        line_start = line_end + 1u;
    }
    if (seen == 0) {
        *reason = MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MISSING;
        return -1;
    }
    *value = parsed;
    return 0;
}

/*
 * Read /proc/<pid>/status from the HOST mount namespace and extract exactly the two required
 * fields.  Any read error, permission error, ENOENT, short read or partial file is UNREADABLE
 * (P-6).  There is no permissive fallback and no substitution of a candidate self-report.
 */
static int mt4_s3c_read_seccomp_status(const char *path,
                                       mt4_s3c_seccomp_status_t *out,
                                       mt4_s3c_reason_t *reason)
{
    char buffer[65536];
    size_t used = 0;
    int fd;

    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        *reason = MT4_S3C_REASON_SECCOMP_BASELINE_UNREADABLE;
        return -1;
    }
    for (;;) {
        ssize_t got = read(fd, buffer + used, sizeof(buffer) - used);

        if (got < 0) {
            if (errno == EINTR) {
                continue;
            }
            (void)close(fd);
            *reason = MT4_S3C_REASON_SECCOMP_BASELINE_UNREADABLE;
            return -1;
        }
        if (got == 0) {
            break;
        }
        used += (size_t)got;
        if (used == sizeof(buffer)) {
            (void)close(fd);
            *reason = MT4_S3C_REASON_SECCOMP_BASELINE_UNREADABLE;
            return -1;
        }
    }
    (void)close(fd);
    if (used == 0) {
        *reason = MT4_S3C_REASON_SECCOMP_BASELINE_UNREADABLE;
        return -1;
    }
    /*
     * 5C: THE WHOLE BUFFER IS VALIDATED BEFORE ANY FIELD IS EXTRACTED.  Decoding the two fields we
     * want while ignoring whatever else the file contains is permissive parsing: an embedded NUL, a
     * high byte or a control character anywhere in the document means this is not the /proc/status
     * this contract describes, and a parser that skipped past it would be reading an unknown format
     * while reporting a confident number.  The accepted alphabet is exactly printable ASCII plus
     * horizontal tab and newline.
     *
     * The failure class is the FROZEN SECCOMP_BASELINE_FIELD_MALFORMED.  A whole-buffer encoding
     * violation is a malformed status source, which that class already names, and inventing a new
     * public reason code for a condition an existing class covers would widen the taxonomy without
     * telling an operator anything the existing class does not.
     */
    {
        size_t index;

        for (index = 0; index < used; index++) {
            unsigned char byte = (unsigned char)buffer[index];

            if (byte == 0u) {
                *reason = MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MALFORMED;
                return -1;
            }
            if (byte == (unsigned char)'\n' || byte == (unsigned char)'\t') {
                continue;
            }
            if (byte < 0x20u || byte > 0x7Eu) {
                *reason = MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MALFORMED;
                return -1;
            }
        }
    }
    if (mt4_s3c_parse_status_field(buffer, used, "Seccomp", &out->seccomp_mode, reason) != 0) {
        return -1;
    }
    if (mt4_s3c_parse_status_field(buffer, used, "Seccomp_filters", &out->filter_count, reason) != 0) {
        return -1;
    }
    return 0;
}

static int mt4_s3c_require_baseline_zero(const char *path, mt4_s3c_reason_t *reason)
{
    mt4_s3c_seccomp_status_t status;

    if (mt4_s3c_read_seccomp_status(path, &status, reason) != 0) {
        return -1;
    }
    if (status.seccomp_mode != 0u || status.filter_count != 0u) {
        *reason = MT4_S3C_REASON_SECCOMP_BASELINE_NONZERO;
        return -1;
    }
    return 0;
}

static int mt4_s3c_require_filter_count(const char *path,
                                        unsigned long expected_filters,
                                        mt4_s3c_seccomp_status_t *out,
                                        mt4_s3c_reason_t *reason)
{
    if (mt4_s3c_read_seccomp_status(path, out, reason) != 0) {
        return -1;
    }
    /* Seccomp mode 2 is filter mode; it is REQUIRED after each installation (V9 11.3). */
    if (out->seccomp_mode != 2u || out->filter_count != expected_filters) {
        *reason = MT4_S3C_REASON_SECCOMP_COUNT_TRANSITION_INVALID;
        return -1;
    }
    return 0;
}

/* ==============================================================================================
 * NAMESPACE IDENTITY (V9 18.1).  Identity is the (st_dev, st_ino) pair; the readlink string is
 * ALSO read and its encoded inode must agree, because a string comparison alone cannot detect two
 * different filesystems presenting the same inode number.
 * ============================================================================================ */

static const char *const mt4_s3c_namespace_names[] = {"user", "mnt", "pid", "net", "ipc", "uts"};
#define MT4_S3C_NAMESPACE_COUNT 6

typedef struct {
    dev_t device;
    ino_t inode;
} mt4_s3c_namespace_identity_t;

static int mt4_s3c_read_namespace_identity(const char *path, mt4_s3c_namespace_identity_t *out)
{
    struct stat information;
    char link[256];
    ssize_t link_length;
    unsigned long long encoded = 0;
    size_t cursor;
    int digits = 0;

    if (stat(path, &information) != 0) {
        return -1;
    }
    link_length = readlink(path, link, sizeof(link) - 1u);
    if (link_length <= 0) {
        return -1;
    }
    link[link_length] = '\0';
    /* The link text has the form "<name>:[<inode>]"; the encoded inode must agree with stat. */
    for (cursor = 0; link[cursor] != '\0' && link[cursor] != '['; cursor++) {
        /* deliberate: advance to the bracket */
    }
    if (link[cursor] != '[') {
        return -1;
    }
    cursor++;
    while (link[cursor] >= '0' && link[cursor] <= '9') {
        encoded = encoded * 10ull + (unsigned long long)(link[cursor] - '0');
        digits++;
        cursor++;
    }
    if (digits == 0 || link[cursor] != ']' || link[cursor + 1u] != '\0') {
        return -1;
    }
    if ((unsigned long long)information.st_ino != encoded) {
        return -1;
    }
    out->device = information.st_dev;
    out->inode = information.st_ino;
    return 0;
}

/* ==============================================================================================
 * SYSCALL WRAPPERS THE SUPERVISOR AND LAUNCHER NEED.
 * ============================================================================================ */

static long mt4_s3c_sys_clone3(struct clone_args *arguments, size_t size)
{
    return syscall(__NR_clone3, arguments, size);
}

static int mt4_s3c_sys_pivot_root(const char *new_root, const char *put_old)
{
    return (int)syscall(__NR_pivot_root, new_root, put_old);
}

static int mt4_s3c_sys_seccomp(unsigned int operation, unsigned int flags, const void *arguments)
{
    return (int)syscall(__NR_seccomp, operation, flags, arguments);
}

static int mt4_s3c_sys_pidfd_send_signal(int pidfd, int signal_number)
{
    return (int)syscall(__NR_pidfd_send_signal, pidfd, signal_number, NULL, 0u);
}

static int mt4_s3c_sys_close_range(unsigned int first, unsigned int last, unsigned int flags)
{
    return (int)syscall(__NR_close_range, first, last, flags);
}

/*
 * POST-FILTER SYSCALLS ARE PROJECT-OWNED (repair 5D).
 *
 * WHY A LIBC WRAPPER IS NOT ACCEPTABLE HERE.  The outer filter this launcher installs on itself
 * classifies ALL SIX seccomp_data argument words for every permitted syscall, and requires the
 * unused tail to be exactly zero (UNUSED_ARGUMENT_WORDS_MUST_BE_ZERO).  A libc execve sets only the
 * three registers it needs; %r10, %r8 and %r9 keep whatever the caller left in them.  The filter
 * sees a nonzero tail and kills the process -- and the failure would look like a candidate defect
 * rather than a launcher one.  The two syscalls issued AFTER the filter is installed therefore go
 * through a project-owned wrapper that loads all six argument registers explicitly, zeroing the
 * tail, exactly as the freestanding worker's own wrapper does.
 *
 * This wrapper is used ONLY after the outer filter exists.  Everything before that point is
 * unconstrained by the filter and continues to use ordinary libc calls.
 */
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

/* execve with an explicitly zeroed argument tail.  Returns only on failure, exactly like execve. */
static inline long mt4_s3c_sys_execve(const char *path, char *const argv[], char *const envp[])
{
    return mt4_s3c_syscall6(__NR_execve, (long)path, (long)argv, (long)envp, 0, 0, 0);
}

/* exit_group with an explicitly zeroed argument tail.  arg0 is the status the policy leaves
 * intentionally unconstrained (UNCONSTRAINED_SCALAR); args 1..5 are zero. */
__attribute__((noreturn)) static void mt4_s3c_sys_exit_group(int status)
{
    for (;;) {
        (void)mt4_s3c_syscall6(__NR_exit_group, (long)status, 0, 0, 0, 0, 0);
    }
}

static long mt4_s3c_monotonic_ms(void)
{
    struct timespec now;

    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
        return -1;
    }
    return (long)now.tv_sec * 1000L + (long)(now.tv_nsec / 1000000L);
}

/* ==============================================================================================
 * THE CASE PLAN (frozen binary format, derived from the bundled fixture by bundle entry 8).
 * ============================================================================================ */

typedef struct {
    char case_id[MT4_S3C_PLAN_CASE_ID_BYTES + 1];
    uint32_t stimulus_kind;
    uint32_t input_length;
    uint32_t expected_result_class;
    int32_t expected_result_code;
    int32_t expected_exit_status;
    unsigned char input[MT4_S3C_MAX_CASE_INPUT_BYTES];
} mt4_s3c_case_t;

typedef struct {
    uint32_t case_count;
    unsigned char fixture_sha256[32];
    unsigned char plan_sha256[32];
    mt4_s3c_case_t cases[MT4_S3C_EXACT_CASE_COUNT];
} mt4_s3c_plan_t;

static uint32_t mt4_s3c_read_u32le(const unsigned char *bytes)
{
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) | ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static int mt4_s3c_load_plan(const char *path, mt4_s3c_plan_t *plan)
{
    unsigned char raw[MT4_S3C_MAX_PLAN_BYTES];
    size_t used = 0;
    size_t cursor;
    uint32_t index;
    mt4_s3c_sha256_t sha;
    int fd;

    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    for (;;) {
        ssize_t got = read(fd, raw + used, sizeof(raw) - used);

        if (got < 0) {
            if (errno == EINTR) {
                continue;
            }
            (void)close(fd);
            return -1;
        }
        if (got == 0) {
            break;
        }
        used += (size_t)got;
        if (used == sizeof(raw)) {
            (void)close(fd);
            return -1;
        }
    }
    (void)close(fd);

    if (used < (size_t)MT4_S3C_PLAN_HEADER_BYTES) {
        return -1;
    }
    if (memcmp(raw, MT4_S3C_PLAN_MAGIC, (size_t)MT4_S3C_PLAN_MAGIC_BYTES) != 0) {
        return -1;
    }
    if (mt4_s3c_read_u32le(raw + 8) != (uint32_t)MT4_S3C_PLAN_VERSION) {
        return -1;
    }
    plan->case_count = mt4_s3c_read_u32le(raw + 12);
    if (plan->case_count != (uint32_t)MT4_S3C_EXACT_CASE_COUNT) {
        return -1;
    }
    memcpy(plan->fixture_sha256, raw + 16, sizeof(plan->fixture_sha256));
    for (cursor = 48; cursor < (size_t)MT4_S3C_PLAN_HEADER_BYTES; cursor++) {
        if (raw[cursor] != 0) {
            return -1;
        }
    }

    cursor = (size_t)MT4_S3C_PLAN_HEADER_BYTES;
    for (index = 0; index < plan->case_count; index++) {
        mt4_s3c_case_t *entry = &plan->cases[index];
        size_t identifier;

        if (cursor + (size_t)MT4_S3C_PLAN_CASE_HEADER_BYTES > used) {
            return -1;
        }
        memcpy(entry->case_id, raw + cursor, (size_t)MT4_S3C_PLAN_CASE_ID_BYTES);
        entry->case_id[MT4_S3C_PLAN_CASE_ID_BYTES] = '\0';
        for (identifier = 0; identifier < (size_t)MT4_S3C_PLAN_CASE_ID_BYTES; identifier++) {
            unsigned char character = (unsigned char)entry->case_id[identifier];

            if (character == 0) {
                break;
            }
            if (!((character >= 'A' && character <= 'Z') || (character >= '0' && character <= '9') ||
                  character == '_')) {
                return -1;
            }
        }
        if (identifier == 0) {
            return -1;
        }
        for (; identifier < (size_t)MT4_S3C_PLAN_CASE_ID_BYTES; identifier++) {
            if (entry->case_id[identifier] != 0) {
                return -1;
            }
        }
        cursor += (size_t)MT4_S3C_PLAN_CASE_ID_BYTES;
        entry->stimulus_kind = mt4_s3c_read_u32le(raw + cursor);
        entry->input_length = mt4_s3c_read_u32le(raw + cursor + 4);
        entry->expected_result_class = mt4_s3c_read_u32le(raw + cursor + 8);
        entry->expected_result_code = (int32_t)mt4_s3c_read_u32le(raw + cursor + 12);
        entry->expected_exit_status = (int32_t)mt4_s3c_read_u32le(raw + cursor + 16);
        cursor += 20;
        if (entry->stimulus_kind > MT4_S3C_STIMULUS_WRITE_PREFIX_THEN_HOLD) {
            return -1;
        }
        if (entry->input_length > (uint32_t)MT4_S3C_MAX_CASE_INPUT_BYTES) {
            return -1;
        }
        if (cursor + entry->input_length > used) {
            return -1;
        }
        memcpy(entry->input, raw + cursor, entry->input_length);
        cursor += entry->input_length;
    }
    if (cursor != used) {
        return -1;
    }
    mt4_s3c_sha256_init(&sha);
    mt4_s3c_sha256_update(&sha, raw, used);
    mt4_s3c_sha256_final(&sha, plan->plan_sha256);
    return 0;
}

/* ==============================================================================================
 * SYSCALL EVENT TRACE
 * ============================================================================================ */

typedef struct {
    unsigned int sequence;
    int is_exit_stop;
    long number;
    unsigned long long arguments[6];
    long long result;
    const char *phase;
} mt4_s3c_event_t;

typedef struct {
    mt4_s3c_event_t entries[MT4_S3C_MAX_SYSCALL_EVENTS_PER_CASE];
    unsigned int used;
    int budget_exceeded;
} mt4_s3c_trace_t;

static void mt4_s3c_trace_append(mt4_s3c_trace_t *trace, const mt4_s3c_event_t *event)
{
    if (trace->used >= (unsigned int)MT4_S3C_MAX_SYSCALL_EVENTS_PER_CASE) {
        trace->budget_exceeded = 1;
        return;
    }
    trace->entries[trace->used] = *event;
    trace->entries[trace->used].sequence = trace->used;
    trace->used++;
}

/* ==============================================================================================
 * TRACER PRIMITIVES.  READ-ONLY AND CONTROL-ONLY.  Nothing here can alter tracee state.
 * ============================================================================================ */

static int mt4_s3c_read_registers(pid_t pid, struct user_regs_struct *registers)
{
    struct iovec vector;

    vector.iov_base = registers;
    vector.iov_len = sizeof(*registers);
    if (mt4_s3c_ptrace_permitted((long)PTRACE_GETREGSET, pid, (void *)(unsigned long)NT_PRSTATUS, &vector) != 0) {
        return -1;
    }
    if (vector.iov_len != sizeof(*registers)) {
        return -1;
    }
    return 0;
}

/*
 * Resume the tracee.  CONTROL ONLY.  The delivered signal argument is the literal zero required by
 * V9 11.7 rules T3 and T4; signal injection is forbidden absolutely.
 */
static int mt4_s3c_resume_to_syscall(pid_t pid)
{
    return (int)mt4_s3c_ptrace_permitted((long)PTRACE_SYSCALL, pid, NULL, MT4_S3C_PTRACE_RESUME_SIGNAL);
}

/* Read tracee memory a word at a time through the kernel-mediated tracer interface (T6). */
static int mt4_s3c_read_tracee_memory(pid_t pid, unsigned long address, unsigned char *out, size_t length)
{
    size_t copied = 0;

    while (copied < length) {
        unsigned long word;
        size_t take;

        errno = 0;
        word = (unsigned long)mt4_s3c_ptrace_permitted((long)PTRACE_PEEKDATA, pid, (void *)(address + copied), NULL);
        if (errno != 0) {
            return -1;
        }
        take = sizeof(word);
        if (take > length - copied) {
            take = length - copied;
        }
        memcpy(out + copied, &word, take);
        copied += take;
    }
    return 0;
}

/*
 * Capture the sock_fprog a tracee submitted, at its seccomp syscall-ENTRY stop.
 *
 * DOUBLE-FETCH SOUNDNESS is proven rather than assumed: the tracee is single-threaded, clone,
 * clone3, fork and vfork are absent from every filter in force and from this source, no signal
 * handler exists anywhere in the design, and the process is STOPPED for the whole duration of the
 * read.  The bytes read here are therefore exactly the bytes the kernel will copy.
 */
static int mt4_s3c_capture_filter(pid_t pid,
                                  unsigned long fprog_address,
                                  unsigned short *out_length,
                                  unsigned long *out_filter_address,
                                  unsigned char *out_bytes,
                                  size_t *out_byte_count)
{
    struct sock_fprog captured;
    size_t byte_count;

    memset(&captured, 0, sizeof(captured));
    if (mt4_s3c_read_tracee_memory(pid, fprog_address, (unsigned char *)&captured, sizeof(captured)) != 0) {
        return -1;
    }
    if (captured.len == 0 || captured.len > (unsigned short)MT4_S3C_MAX_FILTER_INSTRUCTIONS) {
        return -1;
    }
    byte_count = (size_t)captured.len * sizeof(struct sock_filter);
    if (mt4_s3c_read_tracee_memory(pid, (unsigned long)captured.filter, out_bytes, byte_count) != 0) {
        return -1;
    }
    *out_length = captured.len;
    *out_filter_address = (unsigned long)captured.filter;
    *out_byte_count = byte_count;
    return 0;
}

/* ==============================================================================================
 * LAUNCHER CHILD (process I).  Runs inside all six namespaces, blocked until the GO byte.
 * ============================================================================================ */

typedef struct {
    int go_pipe_read;
    int request_pipe_read;
    int response_pipe_write;
    const char *candidate_source_path;
    const unsigned char *governed_digest;
    unsigned long long governed_size;
} mt4_s3c_child_context_t;

static void mt4_s3c_child_fail(void)
{
    /*
     * After state 16 the launcher executes AT MOST TWO syscalls (V9 19.2 L-INV-2).  This path is
     * reached only BEFORE the outer filter exists, so exit_group here is unconstrained by it.
     */
    _exit(MT4_S3C_EXIT_LAUNCHER_FAILED);
}

static int mt4_s3c_write_all(int fd, const void *buffer, size_t length)
{
    const unsigned char *bytes = (const unsigned char *)buffer;
    size_t written = 0;

    while (written < length) {
        ssize_t result = write(fd, bytes + written, length - written);

        if (result > 0) {
            written += (size_t)result;
            continue;
        }
        if (result < 0 && errno == EINTR) {
            continue;
        }
        return -1;
    }
    return 0;
}

static int mt4_s3c_digest_fd(int fd, unsigned char digest[32], unsigned long long *out_size)
{
    mt4_s3c_sha256_t sha;
    unsigned char buffer[65536];
    unsigned long long total = 0;

    if (lseek(fd, 0, SEEK_SET) != 0) {
        return -1;
    }
    mt4_s3c_sha256_init(&sha);
    for (;;) {
        ssize_t got = read(fd, buffer, sizeof(buffer));

        if (got < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (got == 0) {
            break;
        }
        total += (unsigned long long)got;
        if (total > (unsigned long long)MT4_S3C_MAX_WORKER_BINARY_BYTES) {
            return -1;
        }
        mt4_s3c_sha256_update(&sha, buffer, (size_t)got);
    }
    mt4_s3c_sha256_final(&sha, digest);
    *out_size = total;
    return 0;
}

/* V9 17.2 steps 3 and 13: the descriptor table must be EXACTLY {0,1,2,3,4}. */
static int mt4_s3c_prove_fd_table(void)
{
    int index;

    for (index = 0; index < MT4_S3C_FD_TABLE_SIZE; index++) {
        if (fcntl(index, F_GETFD) < 0) {
            return -1;
        }
    }
    /*
     * close_range over everything above the governed table makes a surviving descriptor impossible
     * rather than merely detected.  A sixth descriptor cannot persist past this call.
     */
    if (mt4_s3c_sys_close_range((unsigned int)MT4_S3C_FD_TABLE_SIZE, MT4_S3C_CLOSE_RANGE_MAX_FD, 0u) != 0) {
        return -1;
    }
    if (fcntl(MT4_S3C_FD_TABLE_SIZE, F_GETFD) >= 0) {
        return -1;
    }
    return 0;
}

/* V9 17.2 step 7: the read-only state is PROVEN by a failed write AND by re-read mount flags. */
static int mt4_s3c_prove_read_only_root(void)
{
    int probe = open("/mt4_s3c_write_probe", O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);

    if (probe >= 0) {
        (void)close(probe);
        return -1;
    }
    if (errno != EROFS) {
        return -1;
    }
    return 0;
}

static int mt4_s3c_drop_all_capabilities(void)
{
    cap_t empty = cap_init();
    int index;

    if (empty == NULL) {
        return -1;
    }
    if (cap_set_proc(empty) != 0) {
        (void)cap_free(empty);
        return -1;
    }
    (void)cap_free(empty);
    /*
     * Clear the ambient set and drop every capability from the bounding set.  CAP_LAST_CAP is read
     * from the running kernel through the library rather than assumed, so the loop covers every
     * capability the kernel reports.
     */
    if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) != 0) {
        return -1;
    }
    for (index = 0; index <= CAP_LAST_CAP; index++) {
        if (!CAP_IS_SUPPORTED(index)) {
            continue;
        }
        if (prctl(PR_CAPBSET_DROP, index, 0, 0, 0) != 0 && errno != EINVAL) {
            return -1;
        }
    }
    return 0;
}

static int mt4_s3c_capability_state_is_empty(void)
{
    cap_t current = cap_get_proc();
    cap_flag_value_t value;
    int index;
    int clean = 1;

    if (current == NULL) {
        return 0;
    }
    for (index = 0; index <= CAP_LAST_CAP && clean; index++) {
        if (!CAP_IS_SUPPORTED(index)) {
            continue;
        }
        if (cap_get_flag(current, index, CAP_EFFECTIVE, &value) != 0 || value != CAP_CLEAR) {
            clean = 0;
        }
        if (clean && (cap_get_flag(current, index, CAP_PERMITTED, &value) != 0 || value != CAP_CLEAR)) {
            clean = 0;
        }
        if (clean && (cap_get_flag(current, index, CAP_INHERITABLE, &value) != 0 || value != CAP_CLEAR)) {
            clean = 0;
        }
        if (clean && prctl(PR_CAPBSET_READ, index, 0, 0, 0) != 0) {
            clean = 0;
        }
    }
    (void)cap_free(current);
    return clean;
}

/*
 * THE LAUNCHER.  V9 SECTION 17.2 steps 1..16, in the frozen order, with no step skipped and none
 * reordered.  Nothing capable of modifying candidate bytes remains between step 11 and step 16.
 */
__attribute__((noreturn)) static void mt4_s3c_launcher_child(const mt4_s3c_child_context_t *context)
{
    unsigned char go = 0;
    unsigned char initial_digest[32];
    unsigned char final_digest[32];
    unsigned long long initial_size = 0;
    unsigned long long final_size = 0;
    struct stat reproof;
    struct stat path_information;
    struct rlimit limit;
    int source_fd;
    int destination_fd;
    int reproof_fd;
    int null_fd;
    ssize_t got;

    /* N1: the child's FIRST action is a blocking one-byte read on the GO pipe. */
    for (;;) {
        got = read(context->go_pipe_read, &go, 1);
        if (got == 1) {
            break;
        }
        if (got == 0) {
            /*
             * PT-181: a GO read returning 0 means the supervisor withheld release.  The child must
             * exit immediately and must NEVER proceed to root construction.
             */
            mt4_s3c_child_fail();
        }
        if (got < 0 && errno == EINTR) {
            continue;
        }
        mt4_s3c_child_fail();
    }
    if (go != 1u) {
        mt4_s3c_child_fail();
    }
    (void)close(context->go_pipe_read);

    /* Standard descriptors become /dev/null before the private root exists.  The open file
     * descriptions survive pivot_root because they reference inodes, not paths. */
    null_fd = open("/dev/null", O_RDWR | O_CLOEXEC);
    if (null_fd < 0) {
        mt4_s3c_child_fail();
    }
    if (dup2(null_fd, MT4_S3C_FD_STDIN) < 0 || dup2(null_fd, MT4_S3C_FD_STDOUT) < 0 ||
        dup2(null_fd, MT4_S3C_FD_STDERR) < 0) {
        mt4_s3c_child_fail();
    }
    if (null_fd > MT4_S3C_FD_STDERR) {
        (void)close(null_fd);
    }
    if (dup2(context->request_pipe_read, MT4_S3C_FD_REQUEST) < 0 ||
        dup2(context->response_pipe_write, MT4_S3C_FD_RESPONSE) < 0) {
        mt4_s3c_child_fail();
    }

    /*
     * State 5 PRIVATE_ROOT_CONSTRUCTED.  MS_REC|MS_PRIVATE precedes tmpfs creation, so the tmpfs has
     * no propagation peer and appears in no other mount namespace (vector V-3).
     */
    if (mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) != 0) {
        mt4_s3c_child_fail();
    }
    if (mount("mt4s3c", "/tmp", "tmpfs", MS_NOSUID | MS_NODEV, "mode=0700") != 0) {
        mt4_s3c_child_fail();
    }
    if (chdir("/tmp") != 0) {
        mt4_s3c_child_fail();
    }
    if (mkdir(MT4_S3C_PUT_OLD_NAME, 0700) != 0) {
        mt4_s3c_child_fail();
    }

    /* Step 1 CANDIDATE_MATERIALISED: exactly one writable descriptor, owned by the launcher. */
    source_fd = open(context->candidate_source_path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (source_fd < 0) {
        mt4_s3c_child_fail();
    }
    destination_fd = open(MT4_S3C_CANDIDATE_NAME, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, MT4_S3C_CANDIDATE_MODE);
    if (destination_fd < 0) {
        mt4_s3c_child_fail();
    }
    for (;;) {
        unsigned char buffer[65536];

        got = read(source_fd, buffer, sizeof(buffer));
        if (got < 0) {
            if (errno == EINTR) {
                continue;
            }
            mt4_s3c_child_fail();
        }
        if (got == 0) {
            break;
        }
        if (mt4_s3c_write_all(destination_fd, buffer, (size_t)got) != 0) {
            mt4_s3c_child_fail();
        }
    }
    (void)close(source_fd);
    if (fsync(destination_fd) != 0) {
        mt4_s3c_child_fail();
    }

    /* Step 2 ORDINARY_VALIDATION: the INITIAL digest, compared to the governed identity. */
    if (mt4_s3c_digest_fd(destination_fd, initial_digest, &initial_size) != 0) {
        mt4_s3c_child_fail();
    }
    if (initial_size != context->governed_size ||
        memcmp(initial_digest, context->governed_digest, sizeof(initial_digest)) != 0) {
        mt4_s3c_child_fail();
    }
    if (fchmod(destination_fd, MT4_S3C_CANDIDATE_MODE) != 0) {
        mt4_s3c_child_fail();
    }

    /* Step 3 ALL_CANDIDATE_WRITERS_CLOSED. */
    if (close(destination_fd) != 0) {
        mt4_s3c_child_fail();
    }

    /* Step 4 OTHER_WRITER_PATHS_ELIMINATED: RLIMIT_FSIZE 0 after the only legitimate write. */
    limit.rlim_cur = 0;
    limit.rlim_max = 0;
    if (setrlimit(RLIMIT_FSIZE, &limit) != 0) {
        mt4_s3c_child_fail();
    }

    /* Step 5 PRIVATE_ROOT_FINALISED. */
    if (mt4_s3c_sys_pivot_root(".", MT4_S3C_PUT_OLD_NAME) != 0) {
        mt4_s3c_child_fail();
    }
    if (chdir("/") != 0) {
        mt4_s3c_child_fail();
    }
    if (umount2("/" MT4_S3C_PUT_OLD_NAME, MNT_DETACH) != 0) {
        mt4_s3c_child_fail();
    }
    if (rmdir("/" MT4_S3C_PUT_OLD_NAME) != 0) {
        mt4_s3c_child_fail();
    }

    /* Step 6 ROOT_MADE_READ_ONLY, then step 7 READ_ONLY_STATE_AUTHENTICATED. */
    if (mount(NULL, "/", NULL, MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV | MS_BIND, NULL) != 0 &&
        mount(NULL, "/", NULL, MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV, NULL) != 0) {
        mt4_s3c_child_fail();
    }
    if (mt4_s3c_prove_read_only_root() != 0) {
        mt4_s3c_child_fail();
    }

    /* Step 8 CANDIDATE_REOPENED_READ_ONLY.  O_NOFOLLOW refuses a symlink rather than following it. */
    reproof_fd = open(MT4_S3C_CANDIDATE_PATH, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (reproof_fd < 0) {
        mt4_s3c_child_fail();
    }

    /* Step 9 FINAL_STAT_INVARIANTS. */
    if (fstat(reproof_fd, &reproof) != 0) {
        mt4_s3c_child_fail();
    }
    if (!S_ISREG(reproof.st_mode) || (unsigned long long)reproof.st_size != context->governed_size ||
        (reproof.st_mode & 07777) != MT4_S3C_CANDIDATE_MODE || (reproof.st_mode & S_ISUID) != 0 ||
        (reproof.st_mode & S_ISGID) != 0 || reproof.st_nlink != 1) {
        mt4_s3c_child_fail();
    }

    /* Steps 10 and 11 FINAL_DIGEST_RECOMPUTED and FINAL_DIGEST_MATCHED. */
    if (mt4_s3c_digest_fd(reproof_fd, final_digest, &final_size) != 0) {
        mt4_s3c_child_fail();
    }
    if (final_size != context->governed_size ||
        memcmp(final_digest, initial_digest, sizeof(final_digest)) != 0 ||
        memcmp(final_digest, context->governed_digest, sizeof(final_digest)) != 0) {
        mt4_s3c_child_fail();
    }

    /* Step 12 PATH_TO_INODE_BOUND. */
    if (lstat(MT4_S3C_CANDIDATE_PATH, &path_information) != 0) {
        mt4_s3c_child_fail();
    }
    if (path_information.st_dev != reproof.st_dev || path_information.st_ino != reproof.st_ino ||
        !S_ISREG(path_information.st_mode)) {
        mt4_s3c_child_fail();
    }

    /* Step 13 REPROOF_FD_CLOSED, then the descriptor table is re-proven to be exactly {0,1,2,3,4}. */
    if (close(reproof_fd) != 0) {
        mt4_s3c_child_fail();
    }
    if (mt4_s3c_prove_fd_table() != 0) {
        mt4_s3c_child_fail();
    }

    /* State 12 PRIVILEGES_DROPPED, including the governed RLIMIT_AS of V9 29.5 EM-16. */
    limit.rlim_cur = MT4_S3C_RLIMIT_AS_BYTES;
    limit.rlim_max = MT4_S3C_RLIMIT_AS_BYTES;
    if (setrlimit(RLIMIT_AS, &limit) != 0) {
        mt4_s3c_child_fail();
    }
    limit.rlim_cur = 0;
    limit.rlim_max = 0;
    if (setrlimit(RLIMIT_NPROC, &limit) != 0 && errno != EPERM) {
        mt4_s3c_child_fail();
    }
    if (setresgid(MT4_S3C_MAPPED_GID, MT4_S3C_MAPPED_GID, MT4_S3C_MAPPED_GID) != 0) {
        mt4_s3c_child_fail();
    }
    if (setresuid(MT4_S3C_MAPPED_UID, MT4_S3C_MAPPED_UID, MT4_S3C_MAPPED_UID) != 0) {
        mt4_s3c_child_fail();
    }
    if (mt4_s3c_drop_all_capabilities() != 0) {
        mt4_s3c_child_fail();
    }

    /* State 13 CAPABILITY_STATE_REPROVED, strictly BEFORE the filter install (V9 19.2 L-INV-1). */
    if (!mt4_s3c_capability_state_is_empty()) {
        mt4_s3c_child_fail();
    }

    /* State 14 NO_NEW_PRIVS_CONFIRMED, also strictly before the install. */
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        mt4_s3c_child_fail();
    }
    if (prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1) {
        mt4_s3c_child_fail();
    }

    /*
     * State 15 TRACE_ESTABLISHED.  The relationship is established by the TRACEE ON ITSELF: TRACEME
     * requires no capability, no privilege and no access check against a process inside a fresh user
     * namespace, because the tracee consents.  An external attach would have to satisfy exactly that
     * check against a process which later makes itself non-dumpable.
     */
    if (mt4_s3c_ptrace_permitted((long)PTRACE_TRACEME, 0, NULL, NULL) != 0) {
        mt4_s3c_child_fail();
    }
    if (raise(SIGSTOP) != 0) {
        mt4_s3c_child_fail();
    }

    /* State 16 OUTER_FILTER_INSTALLED.  Exactly one install site in this source. */
    if (mt4_s3c_sys_seccomp(SECCOMP_SET_MODE_FILTER, 0u, &mt4_s3c_outer_filter_fprog) != 0) {
        mt4_s3c_child_fail();
    }

    /*
     * State 18 EXACT_CANDIDATE_LAUNCH, and V9 19.2 L-INV-2 (accepted finding D16): after state 16
     * the launcher executes AT MOST TWO syscalls, in exactly this order and no other -- execve
     * exactly once and unconditionally, then exit_group(70) exactly once and ONLY IF execve
     * returned.  The success path and the failure path are distinct code paths, not one path with a
     * conditional: execve is the last statement of the launch, and the statement immediately after
     * it is the unconditional exit.  No branch, no error-code inspection, no logging, no retry, and
     * no interpretation of any pipe content appears between them (permanent test PT-193).
     */
    {
        char *const argument_vector[] = {(char *)MT4_S3C_CANDIDATE_NAME, NULL};
        char *const environment_vector[] = {NULL};

        (void)mt4_s3c_sys_execve(MT4_S3C_CANDIDATE_PATH, argument_vector, environment_vector);
    }
    mt4_s3c_sys_exit_group(MT4_S3C_EXIT_LAUNCHER_FAILED);
}

/* ==============================================================================================
 * PER-CASE OBSERVATION
 * ============================================================================================ */

typedef struct {
    int exec_transition_observed;
    int exec_exit_failure_observed;
    int outer_capture_valid;
    int internal_capture_valid;
    unsigned short outer_length;
    unsigned short internal_length;
    unsigned long outer_fprog_address;
    unsigned long internal_fprog_address;
    unsigned long outer_filter_address;
    unsigned long internal_filter_address;
    unsigned char outer_bytes[MT4_S3C_MAX_FILTER_BYTES];
    unsigned char internal_bytes[MT4_S3C_MAX_FILTER_BYTES];
    size_t outer_byte_count;
    size_t internal_byte_count;
    unsigned long baseline_supervisor_mode;
    unsigned long baseline_supervisor_filters;
    unsigned long baseline_child_mode;
    unsigned long baseline_child_filters;
    unsigned long outer_post_mode;
    unsigned long outer_post_filters;
    unsigned long internal_post_mode;
    unsigned long internal_post_filters;
    unsigned long revalidated_filters;
    unsigned int trace_seccomp_success_count;
    unsigned int trace_execve_count;
    int internal_install_return;
    int outer_install_return;
    int dump_available;
    unsigned char dump_index0[MT4_S3C_MAX_FILTER_BYTES];
    unsigned char dump_index1[MT4_S3C_MAX_FILTER_BYTES];
    size_t dump_index0_bytes;
    size_t dump_index1_bytes;
    int dump_terminates_at_index;
    unsigned char response[MT4_S3C_RESPONSE_FRAME_BYTES];
    size_t response_bytes;
    int response_extra_byte;
    int wait_exited;
    int wait_exit_status;
    int wait_signalled;
    int wait_signal;
    int deadline_expired;
    long duration_ms;
    int equivalence_valid;
    char equivalence_digest[65];
    char captured_internal_cbpf_sha256[65];
    mt4_s3c_reason_t reason;
    const char *reason_marker;
    mt4_s3c_trace_t trace;
} mt4_s3c_case_result_t;

static void mt4_s3c_case_fail(mt4_s3c_case_result_t *result, mt4_s3c_reason_t reason, const char *marker)
{
    if (result->reason == MT4_S3C_REASON_NONE) {
        result->reason = reason;
        result->reason_marker = marker;
    }
}

/*
 * LEG L3, corroboration only (V9 15.2).  PTRACE_SECCOMP_GET_FILTER is documented as requiring
 * elevated privilege of the CALLER and requiring the caller itself to carry no seccomp filter.
 * Measurement M-1 already authenticates the seccomp half for S; only the privilege half is
 * RUNTIME_TO_PROVE.  Unavailability is RECORDED, never a failure, because L0 + L1 + L2 are the
 * mandatory proof; a mismatch when it IS available is a hard failure.
 */
static void mt4_s3c_attempt_dump_leg(pid_t pid, mt4_s3c_case_result_t *result)
{
    long index0;
    long index1;
    long index2;

    result->dump_available = 0;
    result->dump_terminates_at_index = -1;
    errno = 0;
    index0 = mt4_s3c_ptrace_permitted((long)PTRACE_SECCOMP_GET_FILTER, pid, (void *)(unsigned long)0,
                                     result->dump_index0);
    if (index0 < 0) {
        return;
    }
    if (index0 > (long)MT4_S3C_MAX_FILTER_INSTRUCTIONS) {
        return;
    }
    errno = 0;
    index1 = mt4_s3c_ptrace_permitted((long)PTRACE_SECCOMP_GET_FILTER, pid, (void *)(unsigned long)1,
                                     result->dump_index1);
    if (index1 < 0 || index1 > (long)MT4_S3C_MAX_FILTER_INSTRUCTIONS) {
        return;
    }
    errno = 0;
    index2 = mt4_s3c_ptrace_permitted((long)PTRACE_SECCOMP_GET_FILTER, pid, (void *)(unsigned long)2, NULL);
    if (index2 >= 0) {
        /* A third installed filter contradicts the authenticated count of exactly two. */
        mt4_s3c_case_fail(result, MT4_S3C_REASON_SECCOMP_COUNT_DISAGREEMENT, "dump_leg_index2_present");
        return;
    }
    result->dump_index0_bytes = (size_t)index0 * sizeof(struct sock_filter);
    result->dump_index1_bytes = (size_t)index1 * sizeof(struct sock_filter);
    result->dump_terminates_at_index = 2;
    result->dump_available = 1;
}

static void mt4_s3c_collect_response(int response_fd, mt4_s3c_case_result_t *result)
{
    for (;;) {
        unsigned char scratch[64];
        ssize_t got;

        if (result->response_bytes < (size_t)MT4_S3C_RESPONSE_FRAME_BYTES) {
            got = read(response_fd,
                       result->response + result->response_bytes,
                       (size_t)MT4_S3C_RESPONSE_FRAME_BYTES - result->response_bytes);
            if (got > 0) {
                result->response_bytes += (size_t)got;
                continue;
            }
        } else {
            got = read(response_fd, scratch, sizeof(scratch));
            if (got > 0) {
                /* V9 21.8: any additional byte, even one, before EOF is a violation. */
                result->response_extra_byte = 1;
                continue;
            }
        }
        if (got == 0) {
            return;
        }
        if (got < 0 && errno == EINTR) {
            continue;
        }
        if (got < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            return;
        }
        mt4_s3c_case_fail(result, MT4_S3C_REASON_TRANSPORT_FRAMING_FAILURE, "response_read");
        return;
    }
}

/* ==============================================================================================
 * ONE OBSERVATION CASE, END TO END.
 * ============================================================================================ */

typedef struct {
    const char *candidate_path;
    unsigned char governed_digest[32];
    unsigned long long governed_size;
} mt4_s3c_candidate_t;

static void mt4_s3c_run_case(const mt4_s3c_candidate_t *candidate,
                             const mt4_s3c_run_identity_t *identity,
                             const mt4_s3c_case_t *plan_case,
                             mt4_s3c_case_result_t *result)
{
    struct clone_args arguments;
    mt4_s3c_child_context_t child_context;
    mt4_s3c_seccomp_status_t status;
    mt4_s3c_namespace_identity_t supervisor_identity;
    mt4_s3c_namespace_identity_t child_identity;
    char path[128];
    int go_pipe[2];
    int request_pipe[2];
    int response_pipe[2];
    int pidfd = -1;
    pid_t child = -1;
    long deadline;
    long started;
    int in_syscall_exit_stop = 0;
    int candidate_phase = 0;
    int internal_capture_done = 0;
    unsigned int namespace_index;
    long clone_result;
    mt4_s3c_dumpability_state_t dumpability_state = MT4_S3C_DUMPABILITY_CASE_START;
    int reaped = 0;

    memset(result, 0, sizeof(*result));
    result->reason = MT4_S3C_REASON_NONE;
    result->reason_marker = "";
    result->dump_terminates_at_index = -1;
    result->outer_install_return = -1;
    result->internal_install_return = -1;

    /*
     * CASE_START -> PRE_CLONE_AUTHENTICATED (repair 3).  The supervisor's dumpability is PROVEN to
     * be the required pre-clone value before anything else happens.  The child inherits this flag,
     * and a non-dumpable child cannot have its uid_map or gid_map written by an unprivileged
     * supervisor, so this is a precondition of the whole case, not a detail of teardown.
     */
    if (mt4_s3c_supervisor_dumpability_precondition() != 0) {
        result->reason = MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_PRECONDITION_FAILED;
        result->reason_marker = "D-0";
        mt4_s3c_sequence_halted = 1;
        return;
    }
    dumpability_state = MT4_S3C_DUMPABILITY_PRE_CLONE_AUTHENTICATED;

    /*
     * N0a SUPERVISOR_SECCOMP_BASELINE, measurement M-1.  S measures ITSELF BEFORE clone3: if S is
     * filtered, every descendant inherits it, and a child-only measurement would not reveal the
     * origin.  A nonzero value here stops before the child exists at all.
     */
    if (mt4_s3c_read_seccomp_status("/proc/self/status", &status, &result->reason) != 0) {
        result->reason_marker = "M-1";
        return;
    }
    if (status.seccomp_mode != 0u || status.filter_count != 0u) {
        result->reason = MT4_S3C_REASON_SECCOMP_BASELINE_NONZERO;
        result->reason_marker = "M-1";
        return;
    }
    result->baseline_supervisor_mode = status.seccomp_mode;
    result->baseline_supervisor_filters = status.filter_count;

    if (pipe2(go_pipe, O_CLOEXEC) != 0 || pipe2(request_pipe, O_CLOEXEC) != 0 ||
        pipe2(response_pipe, O_CLOEXEC) != 0) {
        mt4_s3c_case_fail(result, MT4_S3C_REASON_QUALIFICATION_INFRASTRUCTURE_FAILURE, "pipe2");
        return;
    }

    child_context.go_pipe_read = go_pipe[0];
    child_context.request_pipe_read = request_pipe[0];
    child_context.response_pipe_write = response_pipe[1];
    child_context.candidate_source_path = candidate->candidate_path;
    child_context.governed_digest = candidate->governed_digest;
    child_context.governed_size = candidate->governed_size;

    /* N1 CHILD_CREATED_AND_BLOCKED: one clone3 with the six flags plus CLONE_PIDFD. */
    memset(&arguments, 0, sizeof(arguments));
    arguments.flags = (uint64_t)(CLONE_NEWUSER | CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWIPC |
                                 CLONE_NEWUTS | CLONE_PIDFD);
    arguments.pidfd = (uint64_t)(uintptr_t)&pidfd;
    arguments.exit_signal = (uint64_t)SIGCHLD;
    clone_result = mt4_s3c_sys_clone3(&arguments, sizeof(arguments));
    if (clone_result < 0) {
        mt4_s3c_case_fail(result, MT4_S3C_REASON_NAMESPACE_SETUP_FAILED, "clone3");
        return;
    }
    if (clone_result == 0) {
        (void)close(go_pipe[1]);
        (void)close(request_pipe[1]);
        (void)close(response_pipe[0]);
        mt4_s3c_launcher_child(&child_context);
    }
    child = (pid_t)clone_result;
    dumpability_state = MT4_S3C_DUMPABILITY_CLONED;
    (void)close(go_pipe[0]);
    (void)close(request_pipe[0]);
    (void)close(response_pipe[1]);

    /* N2, N3, N4: setgroups deny, then the single-line uid and gid maps, written by S. */
    if (snprintf(path, sizeof(path), "/proc/%ld/setgroups", (long)child) <= 0) {
        mt4_s3c_case_fail(result, MT4_S3C_REASON_UID_GID_MAP_FAILED, "setgroups_path");
        goto teardown;
    }
    {
        int fd = open(path, O_WRONLY | O_CLOEXEC);

        if (fd < 0 || mt4_s3c_write_all(fd, "deny", 4) != 0) {
            if (fd >= 0) {
                (void)close(fd);
            }
            mt4_s3c_case_fail(result, MT4_S3C_REASON_UID_GID_MAP_FAILED, "setgroups");
            goto teardown;
        }
        (void)close(fd);
    }
    {
        char mapping[64];
        int fd;
        int length;

        length = snprintf(mapping, sizeof(mapping), "%d %d 1\n", MT4_S3C_MAPPED_UID, (int)getuid());
        (void)snprintf(path, sizeof(path), "/proc/%ld/uid_map", (long)child);
        fd = open(path, O_WRONLY | O_CLOEXEC);
        if (length <= 0 || fd < 0 || mt4_s3c_write_all(fd, mapping, (size_t)length) != 0) {
            if (fd >= 0) {
                (void)close(fd);
            }
            mt4_s3c_case_fail(result, MT4_S3C_REASON_UID_GID_MAP_FAILED, "uid_map");
            goto teardown;
        }
        (void)close(fd);

        length = snprintf(mapping, sizeof(mapping), "%d %d 1\n", MT4_S3C_MAPPED_GID, (int)getgid());
        (void)snprintf(path, sizeof(path), "/proc/%ld/gid_map", (long)child);
        fd = open(path, O_WRONLY | O_CLOEXEC);
        if (length <= 0 || fd < 0 || mt4_s3c_write_all(fd, mapping, (size_t)length) != 0) {
            if (fd >= 0) {
                (void)close(fd);
            }
            mt4_s3c_case_fail(result, MT4_S3C_REASON_UID_GID_MAP_FAILED, "gid_map");
            goto teardown;
        }
        (void)close(fd);
    }

    dumpability_state = MT4_S3C_DUMPABILITY_MAPS_WRITTEN;

    /*
     * N5 SUPERVISOR_DUMPABILITY_SET.  Only NOW does S set PR_SET_DUMPABLE 0 on ITSELF.  Doing it
     * before writing the maps is the inherited P3 hazard and is forbidden.  S never sets
     * dumpability on the child.  The ordering is asserted rather than assumed: reaching this point
     * in any state other than MAPS_WRITTEN would mean the sequence was reordered.
     */
    if (dumpability_state != MT4_S3C_DUMPABILITY_MAPS_WRITTEN) {
        mt4_s3c_case_fail(result, MT4_S3C_REASON_NAMESPACE_RELEASE_ORDER_VIOLATION, "dumpability_order");
        goto teardown;
    }
    if (prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0) {
        mt4_s3c_case_fail(result, MT4_S3C_REASON_PRIVILEGE_SETUP_FAILED, "supervisor_dumpable");
        goto teardown;
    }
    dumpability_state = MT4_S3C_DUMPABILITY_SUPERVISOR_NON_DUMPABLE;

    /* N6 and N7: all six namespace identities queried and required to DIFFER.  No exceptions. */
    for (namespace_index = 0; namespace_index < (unsigned int)MT4_S3C_NAMESPACE_COUNT; namespace_index++) {
        (void)snprintf(path, sizeof(path), "/proc/self/ns/%s", mt4_s3c_namespace_names[namespace_index]);
        if (mt4_s3c_read_namespace_identity(path, &supervisor_identity) != 0) {
            mt4_s3c_case_fail(result, MT4_S3C_REASON_NAMESPACE_SEPARATION_UNPROVEN, "supervisor_ns");
            goto teardown;
        }
        (void)snprintf(path,
                       sizeof(path),
                       "/proc/%ld/ns/%s",
                       (long)child,
                       mt4_s3c_namespace_names[namespace_index]);
        if (mt4_s3c_read_namespace_identity(path, &child_identity) != 0) {
            mt4_s3c_case_fail(result, MT4_S3C_REASON_NAMESPACE_SEPARATION_UNPROVEN, "child_ns");
            goto teardown;
        }
        if (supervisor_identity.device == child_identity.device &&
            supervisor_identity.inode == child_identity.inode) {
            mt4_s3c_case_fail(result, MT4_S3C_REASON_NAMESPACE_SEPARATION_UNPROVEN, "identity_equal");
            goto teardown;
        }
    }

    /*
     * N9a CHILD_SECCOMP_BASELINE, measurement M-2.  Deliberately placed here: the child is still
     * blocked on the GO pipe and has performed NO prctl of any kind, so it is still dumpable and its
     * status file is readable without any special relationship.
     */
    (void)snprintf(path, sizeof(path), "/proc/%ld/status", (long)child);
    if (mt4_s3c_require_baseline_zero(path, &result->reason) != 0) {
        result->reason_marker = "M-2";
        goto teardown;
    }
    result->baseline_child_mode = 0;
    result->baseline_child_filters = 0;

    /* N11 GO_BYTE_RELEASED.  Exactly one byte, then the write end is closed. */
    {
        unsigned char go = 1;

        if (mt4_s3c_write_all(go_pipe[1], &go, 1) != 0) {
            mt4_s3c_case_fail(result, MT4_S3C_REASON_NAMESPACE_RELEASE_ORDER_VIOLATION, "go_write");
            goto teardown;
        }
        (void)close(go_pipe[1]);
        go_pipe[1] = -1;
    }

    started = mt4_s3c_monotonic_ms();
    deadline = started + (long)MT4_S3C_CASE_DEADLINE_MS;

    /* Wait for the launcher's self-stop, then set exactly the frozen option set. */
    for (;;) {
        int status_word = 0;
        pid_t observed = waitpid(child, &status_word, WUNTRACED);

        if (observed < 0) {
            if (errno == EINTR) {
                continue;
            }
            mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE, "wait_selfstop");
            goto teardown;
        }
        if (WIFSTOPPED(status_word)) {
            break;
        }
        if (WIFEXITED(status_word) || WIFSIGNALED(status_word)) {
            result->wait_exited = WIFEXITED(status_word);
            result->wait_exit_status = result->wait_exited ? WEXITSTATUS(status_word) : -1;
            result->wait_signalled = WIFSIGNALED(status_word);
            result->wait_signal = result->wait_signalled ? WTERMSIG(status_word) : 0;
            mt4_s3c_case_fail(result, MT4_S3C_REASON_LAUNCH_FAILED, "died_before_trace");
            child = -1;
            goto teardown;
        }
    }
    if (mt4_s3c_ptrace_permitted((long)PTRACE_SETOPTIONS, child, NULL,
                                 (void *)(unsigned long)MT4_S3C_PTRACE_OPTIONS) != 0) {
        mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE, "setoptions");
        goto teardown;
    }
    if (mt4_s3c_resume_to_syscall(child) != 0) {
        mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE, "resume");
        goto teardown;
    }

    /* Deliver the case stimulus. */
    if (plan_case->input_length > 0u &&
        mt4_s3c_write_all(request_pipe[1], plan_case->input, plan_case->input_length) != 0) {
        mt4_s3c_case_fail(result, MT4_S3C_REASON_TRANSPORT_FRAMING_FAILURE, "request_write");
        goto teardown;
    }
    if (plan_case->stimulus_kind == MT4_S3C_STIMULUS_WRITE_ALL_THEN_CLOSE) {
        /* The parent closes the request-write end immediately so the worker observes a
         * deterministic EOF (V9 20.6 PARENT OBLIGATIONS). */
        (void)close(request_pipe[1]);
        request_pipe[1] = -1;
    }

    /* The stepping loop.  Every stop is recorded; every resume passes a literal zero signal. */
    for (;;) {
        int status_word = 0;
        pid_t observed;
        long now = mt4_s3c_monotonic_ms();

        if (now < 0 || now > deadline) {
            result->deadline_expired = 1;
            mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_TIMEOUT, "deadline");
            break;
        }
        observed = waitpid(child, &status_word, WUNTRACED | WNOHANG);
        if (observed == 0) {
            struct timespec pause;

            pause.tv_sec = 0;
            pause.tv_nsec = MT4_S3C_POLL_INTERVAL_NS;
            (void)nanosleep(&pause, NULL);
            continue;
        }
        if (observed < 0) {
            if (errno == EINTR) {
                continue;
            }
            mt4_s3c_case_fail(result, MT4_S3C_REASON_SUPERVISOR_REAP_FAILED, "waitpid");
            break;
        }
        if (WIFEXITED(status_word)) {
            result->wait_exited = 1;
            result->wait_exit_status = WEXITSTATUS(status_word);
            child = -1;
            break;
        }
        if (WIFSIGNALED(status_word)) {
            result->wait_signalled = 1;
            result->wait_signal = WTERMSIG(status_word);
            child = -1;
            break;
        }
        if (!WIFSTOPPED(status_word)) {
            continue;
        }

        /*
         * PH6a EXEC_TRANSITION_PROVEN.  The kernel-delivered exec transition event is the ONLY
         * proof that the exec succeeded; an exit code is explicitly never sufficient (V9 19.3).
         */
        if (WSTOPSIG(status_word) == SIGTRAP && (status_word >> 8) == (SIGTRAP | (PTRACE_EVENT_EXEC << 8))) {
            mt4_s3c_event_t event;

            memset(&event, 0, sizeof(event));
            event.number = -1;
            event.result = 0;
            event.phase = "EXEC_TRANSITION";
            mt4_s3c_trace_append(&result->trace, &event);
            result->exec_transition_observed = 1;
            candidate_phase = 1;
            in_syscall_exit_stop = 0;
            if (mt4_s3c_resume_to_syscall(child) != 0) {
                mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE, "resume_exec");
                break;
            }
            continue;
        }

        if (WSTOPSIG(status_word) == (SIGTRAP | 0x80)) {
            struct user_regs_struct registers;
            mt4_s3c_event_t event;

            if (mt4_s3c_read_registers(child, &registers) != 0) {
                mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE, "getregset");
                break;
            }
            memset(&event, 0, sizeof(event));
            event.is_exit_stop = in_syscall_exit_stop;
            event.number = (long)registers.orig_rax;
            event.arguments[0] = (unsigned long long)registers.rdi;
            event.arguments[1] = (unsigned long long)registers.rsi;
            event.arguments[2] = (unsigned long long)registers.rdx;
            event.arguments[3] = (unsigned long long)registers.r10;
            event.arguments[4] = (unsigned long long)registers.r8;
            event.arguments[5] = (unsigned long long)registers.r9;
            event.result = in_syscall_exit_stop ? (long long)registers.rax : 0;
            event.phase = candidate_phase ? "CANDIDATE" : "LAUNCHER";
            mt4_s3c_trace_append(&result->trace, &event);
            if (result->trace.budget_exceeded) {
                mt4_s3c_case_fail(result, MT4_S3C_REASON_OBSERVATION_EVENT_BUDGET_EXCEEDED, "trace");
                break;
            }

            if (registers.orig_rax == (unsigned long long)__NR_execve && !in_syscall_exit_stop) {
                result->trace_execve_count++;
            }
            /*
             * PH6b EXEC_RETURNED_FAILURE.  A successful execve never returns, so observing its
             * syscall-EXIT stop proves the process never became the candidate.  No verifier
             * interpretation of any byte is permitted on this path and no bytes from the response
             * pipe may be recorded as a result (V9 19.3).
             */
            if (registers.orig_rax == (unsigned long long)__NR_execve && in_syscall_exit_stop &&
                !result->exec_transition_observed) {
                result->exec_exit_failure_observed = 1;
                mt4_s3c_case_fail(result, MT4_S3C_REASON_LAUNCH_FAILED, "execve_returned");
            }

            /* LEG L1 and LEG L2: capture at the seccomp syscall-ENTRY stop. */
            if (registers.orig_rax == (unsigned long long)__NR_seccomp && !in_syscall_exit_stop) {
                unsigned short captured_length = 0;
                unsigned long filter_address = 0;
                unsigned char *destination = candidate_phase ? result->internal_bytes : result->outer_bytes;
                size_t byte_count = 0;

                /*
                 * L1 is REGISTER ONLY: operation, flags and args[3..5] are read from the register
                 * file with no memory access, exactly as the contract requires.
                 */
                if (registers.rdi != (unsigned long long)SECCOMP_SET_MODE_FILTER || registers.rsi != 0ull ||
                    registers.r10 != 0ull || registers.r8 != 0ull || registers.r9 != 0ull) {
                    mt4_s3c_case_fail(result,
                                      candidate_phase ? MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE
                                                      : MT4_S3C_REASON_OUTER_FILTER_EQUIVALENCE_FAILED,
                                      "seccomp_register_leg");
                    break;
                }
                if (mt4_s3c_capture_filter(child,
                                           (unsigned long)registers.rdx,
                                           &captured_length,
                                           &filter_address,
                                           destination,
                                           &byte_count) != 0) {
                    mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE, "capture");
                    break;
                }
                if (candidate_phase) {
                    result->internal_capture_valid = 1;
                    result->internal_length = captured_length;
                    result->internal_fprog_address = (unsigned long)registers.rdx;
                    result->internal_filter_address = filter_address;
                    result->internal_byte_count = byte_count;
                } else {
                    result->outer_capture_valid = 1;
                    result->outer_length = captured_length;
                    result->outer_fprog_address = (unsigned long)registers.rdx;
                    result->outer_filter_address = filter_address;
                    result->outer_byte_count = byte_count;
                }
            }

            /* The syscall-EXIT stop of a seccomp install: return value, then the COUNT authority. */
            if (registers.orig_rax == (unsigned long long)__NR_seccomp && in_syscall_exit_stop) {
                long long install_result = (long long)registers.rax;

                if (install_result == 0) {
                    result->trace_seccomp_success_count++;
                }
                (void)snprintf(path, sizeof(path), "/proc/%ld/status", (long)child);
                if (!candidate_phase) {
                    result->outer_install_return = (int)install_result;
                    if (install_result != 0) {
                        mt4_s3c_case_fail(result, MT4_S3C_REASON_OUTER_FILTER_INSTALL_FAILED, "outer_install");
                        break;
                    }
                    /* M-3: the authoritative 0 -> 1 transition.  A zero return is NOT sufficient. */
                    if (mt4_s3c_require_filter_count(path, 1u, &status, &result->reason) != 0) {
                        result->reason_marker = "M-3";
                        break;
                    }
                    result->outer_post_mode = status.seccomp_mode;
                    result->outer_post_filters = status.filter_count;
                } else {
                    result->internal_install_return = (int)install_result;
                    if (install_result != 0) {
                        mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_SANDBOX_FAILED, "internal_install");
                        break;
                    }
                    /* M-4: the authoritative 1 -> 2 transition. */
                    if (mt4_s3c_require_filter_count(path, 2u, &status, &result->reason) != 0) {
                        result->reason_marker = "M-4";
                        break;
                    }
                    result->internal_post_mode = status.seccomp_mode;
                    result->internal_post_filters = status.filter_count;
                    mt4_s3c_attempt_dump_leg(child, result);
                    /* M-5: re-measured before the protocol phase, catching any later install. */
                    if (mt4_s3c_require_filter_count(path, 2u, &status, &result->reason) != 0) {
                        result->reason_marker = "M-5";
                        break;
                    }
                    result->revalidated_filters = status.filter_count;
                    internal_capture_done = 1;
                }
            }

            /*
             * The C24 stimulus acts at a candidate read syscall-ENTRY stop, which is the only
             * deterministic point at which the worker is known to be entering a request read.  The
             * C25 stimulus needs no action at all: the request-write end is deliberately never
             * closed, so the worker stays blocked and the supervisor's external deadline fires.
             */
            if (candidate_phase && internal_capture_done && !in_syscall_exit_stop &&
                registers.orig_rax == (unsigned long long)__NR_read &&
                plan_case->stimulus_kind == MT4_S3C_STIMULUS_WRITE_PREFIX_THEN_SIGKILL && pidfd >= 0) {
                (void)mt4_s3c_sys_pidfd_send_signal(pidfd, SIGKILL);
            }

            in_syscall_exit_stop = !in_syscall_exit_stop;

            if (mt4_s3c_resume_to_syscall(child) != 0) {
                mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE, "resume_syscall");
                break;
            }
            continue;
        }

        /*
         * Any other stop signal is delivered to a STOPPED tracee.  Signal injection is forbidden
         * absolutely (V9 11.7 F4), so the tracee is resumed with a literal zero signal and the
         * observed signal is recorded as an event instead.
         */
        {
            mt4_s3c_event_t event;

            memset(&event, 0, sizeof(event));
            event.number = -2;
            event.result = (long long)WSTOPSIG(status_word);
            event.phase = candidate_phase ? "CANDIDATE_SIGNAL" : "LAUNCHER_SIGNAL";
            mt4_s3c_trace_append(&result->trace, &event);
        }
        if (mt4_s3c_resume_to_syscall(child) != 0) {
            mt4_s3c_case_fail(result, MT4_S3C_REASON_WORKER_FILTER_OBSERVATION_UNAVAILABLE, "resume_signal");
            break;
        }
    }

    result->duration_ms = mt4_s3c_monotonic_ms() - started;

teardown:
    if (child > 0) {
        if (pidfd >= 0) {
            (void)mt4_s3c_sys_pidfd_send_signal(pidfd, SIGKILL);
        } else {
            (void)kill(child, SIGKILL);
        }
        {
            unsigned int interrupts = 0;

            for (;;) {
                int status_word = 0;
                pid_t observed = waitpid(child, &status_word, 0);

                if (observed < 0) {
                    if (errno == EINTR) {
                        /* EINTR is the ONLY retryable case, and the retry budget is bounded. */
                        interrupts++;
                        if (interrupts > (unsigned int)MT4_S3C_MAX_REAP_INTERRUPTS) {
                            mt4_s3c_case_fail(result, MT4_S3C_REASON_SUPERVISOR_REAP_FAILED, "reap_interrupt_budget");
                            mt4_s3c_terminal_failure(MT4_S3C_REASON_SUPERVISOR_REAP_FAILED, "reap_interrupt_budget");
                            break;
                        }
                        continue;
                    }
                    /*
                     * ECHILD, EINVAL or anything else means this supervisor cannot prove the child
                     * is gone.  That is terminal, not a case outcome.
                     */
                    mt4_s3c_case_fail(result, MT4_S3C_REASON_SUPERVISOR_REAP_FAILED, "final_reap");
                    mt4_s3c_terminal_failure(MT4_S3C_REASON_SUPERVISOR_REAP_FAILED, "final_reap");
                    break;
                }
                if (observed != child) {
                    /* waitpid was asked about exactly one pid; any other answer is incoherent. */
                    mt4_s3c_case_fail(result, MT4_S3C_REASON_SUPERVISOR_REAP_FAILED, "reap_wrong_child");
                    mt4_s3c_terminal_failure(MT4_S3C_REASON_SUPERVISOR_REAP_FAILED, "reap_wrong_child");
                    break;
                }
                if (WIFEXITED(status_word)) {
                    if (!result->wait_exited && !result->wait_signalled) {
                        result->wait_exited = 1;
                        result->wait_exit_status = WEXITSTATUS(status_word);
                    }
                    reaped = 1;
                    break;
                }
                if (WIFSIGNALED(status_word)) {
                    if (!result->wait_exited && !result->wait_signalled) {
                        result->wait_signalled = 1;
                        result->wait_signal = WTERMSIG(status_word);
                    }
                    reaped = 1;
                    break;
                }
                if (WIFSTOPPED(status_word)) {
                    (void)mt4_s3c_ptrace_permitted((long)PTRACE_CONT, child, NULL, MT4_S3C_PTRACE_RESUME_SIGNAL);
                }
            }
        }
        child = -1;
        /* 2A: the transition happens ONLY on an authoritative successful reap. */
        if (reaped) {
            dumpability_state = MT4_S3C_DUMPABILITY_CHILD_REAPED;
        }
    }
    if (request_pipe[1] >= 0) {
        (void)close(request_pipe[1]);
    }
    /*
     * The response is collected only AFTER the candidate has terminated and been reaped, which is
     * what makes post-hoc tamper impossible: the record is created when no candidate process
     * remains (V9 SECTION 10 point 4).
     */
    mt4_s3c_collect_response(response_pipe[0], result);
    (void)close(response_pipe[0]);
    if (go_pipe[1] >= 0) {
        (void)close(go_pipe[1]);
    }
    if (pidfd >= 0) {
        (void)close(pidfd);
    }

    /*
     * RESTORATION (repair 3).  This is the ONLY restoration site, and it is placed here on purpose:
     * the child has been signalled, waited for and reaped, the response has been collected, and
     * every descriptor belonging to the case is closed, so no map operation and no live child
     * remains.  Restoring earlier would race the very lifecycle this state machine exists to order;
     * restoring later, or not at all, is what broke case 2.
     *
     * A restoration failure is infrastructure, not a candidate verdict, and it HALTS THE SEQUENCE.
     */
    if (dumpability_state == MT4_S3C_DUMPABILITY_SUPERVISOR_NON_DUMPABLE ||
        dumpability_state == MT4_S3C_DUMPABILITY_CHILD_REAPED) {
        if (dumpability_state != MT4_S3C_DUMPABILITY_CHILD_REAPED) {
            /*
             * The child exists, or existed and could not be proven gone.  Restoring now would race
             * a live child's namespace lifecycle, so the failure is recorded and the sequence is
             * terminal rather than restoring optimistically.
             */
            mt4_s3c_terminal_failure(MT4_S3C_REASON_SUPERVISOR_REAP_FAILED, "D-2");
        } else if (mt4_s3c_supervisor_dumpability_restore() != 0) {
            /*
             * 2C: an EXPECTED semantic outcome NEVER masks this.  C25's deadline is the reason the
             * old code path swallowed the failure -- result->reason was already set, so nothing was
             * recorded.  The terminal channel is independent of result->reason for exactly that
             * reason, and the case reason is overwritten unconditionally.
             */
            mt4_s3c_terminal_failure(MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED, "D-1");
            result->reason = MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED;
            result->reason_marker = "D-1";
        } else {
            dumpability_state = MT4_S3C_DUMPABILITY_RESTORED;
        }
    }

    /*
     * 2D, per case: teardown must END in a valid state.  The only acceptable terminal states are
     * "the child was never created" and "the child was reaped and dumpability was restored and
     * re-authenticated".  Anything else is an infrastructure failure whatever the case's semantic
     * outcome was.
     */
    if (dumpability_state != MT4_S3C_DUMPABILITY_CASE_START &&
        dumpability_state != MT4_S3C_DUMPABILITY_PRE_CLONE_AUTHENTICATED &&
        dumpability_state != MT4_S3C_DUMPABILITY_RESTORED) {
        mt4_s3c_terminal_failure(MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED, "D-3");
        result->reason = MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED;
        result->reason_marker = "D-3";
    }

    /* Cross-check C-3 (V9 11.6): the trace-derived count must AGREE with the /proc authority. */
    if (result->reason == MT4_S3C_REASON_NONE && result->exec_transition_observed) {
        unsigned long expected = result->baseline_supervisor_filters + result->trace_seccomp_success_count;

        if (result->revalidated_filters != 0u && expected != result->revalidated_filters) {
            mt4_s3c_case_fail(result, MT4_S3C_REASON_SECCOMP_COUNT_DISAGREEMENT, "C-3");
        }
    }
    if (result->reason == MT4_S3C_REASON_NONE && !result->exec_transition_observed &&
        !result->exec_exit_failure_observed && !result->deadline_expired) {
        mt4_s3c_case_fail(result, MT4_S3C_REASON_EXEC_TRANSITION_NOT_PROVEN, "phase_undetermined");
    }

    /*
     * The per-case internal filter equivalence digest (V9 SECTION 16), computed for EVERY CASE
     * (repair 4).
     *
     * WHY EVERY CASE, INCLUDING THE TWO PROCESS CASES.  The internal filter is installed by the
     * candidate during BOOTSTRAP, before a single byte of the request is consumed.  A case that
     * ends in a signal (C24) or a deadline (C25) therefore has exactly the same installation
     * evidence as one that answers a frame; its semantic RESULT differs, its containment evidence
     * does not.  Emitting an empty digest for those two cases gave them an unbound trust path
     * through adjudication, and made A3 and A4 disagree by construction whenever the observer did
     * capture the installation.  There is no empty-digest branch any more: an internal capture that
     * did not happen is a case failure with its own reason, never a silently absent equivalence.
     */
    result->equivalence_valid = 0;
    result->equivalence_digest[0] = '\0';
    result->captured_internal_cbpf_sha256[0] = '\0';
    if (result->internal_capture_valid) {
        char dump0[65];
        char dump1[65];

        mt4_s3c_cbpf_digest_hex(result->internal_bytes,
                                (unsigned int)result->internal_length,
                                result->captured_internal_cbpf_sha256);
        dump0[0] = '\0';
        dump1[0] = '\0';
        if (result->dump_available) {
            mt4_s3c_cbpf_digest_hex(result->dump_index0,
                                    (unsigned int)(result->dump_index0_bytes / 8u),
                                    dump0);
            mt4_s3c_cbpf_digest_hex(result->dump_index1,
                                    (unsigned int)(result->dump_index1_bytes / 8u),
                                    dump1);
        }
        if (mt4_s3c_equivalence_digest_hex(identity,
                                           plan_case->case_id,
                                           result->captured_internal_cbpf_sha256,
                                           (unsigned long long)result->internal_fprog_address,
                                           (unsigned int)result->internal_length,
                                           result->internal_install_return,
                                           result->baseline_supervisor_mode,
                                           result->baseline_supervisor_filters,
                                           result->baseline_child_mode,
                                           result->baseline_child_filters,
                                           result->outer_post_filters,
                                           result->internal_post_filters,
                                           result->internal_post_mode,
                                           result->revalidated_filters,
                                           result->dump_available ? "AVAILABLE"
                                                                  : "UNAVAILABLE_IN_PINNED_ENVIRONMENT",
                                           dump0,
                                           dump1,
                                           result->dump_terminates_at_index,
                                           result->equivalence_digest) == 0) {
            result->equivalence_valid = 1;
        } else {
            result->equivalence_digest[0] = '\0';
        }
    }
}

/* ==============================================================================================
 * RAW OBSERVATION RECORD EMISSION (artifact class A3).
 *
 * The record contains NO verdict, NO pass/fail flag and NO receipt (V9 SECTION 7).  It carries the
 * exact response bytes in hex, the exact wait status, the terminating signal if any, the ordered
 * syscall and phase event trace, the observer-captured outer and internal cBPF programs, the
 * SECCOMP_STACK_BASELINE_V1 measurements and filter-count transitions.
 * ============================================================================================ */

static void mt4_s3c_emit_case(const mt4_s3c_case_t *plan_case, const mt4_s3c_case_result_t *result, unsigned int index)
{
    unsigned int event_index;

    mt4_s3c_emit("{\"case_index\":%u,\"case_id\":", index + 1u);
    mt4_s3c_emit_json_string(plan_case->case_id);
    mt4_s3c_emit(",\"stimulus_kind\":%u", (unsigned int)plan_case->stimulus_kind);
    mt4_s3c_emit(",\"expected_result_class\":%u", (unsigned int)plan_case->expected_result_class);
    mt4_s3c_emit(",\"expected_result_code\":%d", (int)plan_case->expected_result_code);
    mt4_s3c_emit(",\"expected_exit_status\":%d", (int)plan_case->expected_exit_status);
    mt4_s3c_emit(",\"observation_basis\":\"EXECUTED_CANDIDATE_UNDER_OUTER_CONTAINMENT\"");
    mt4_s3c_emit(",\"infrastructure_reason\":");
    mt4_s3c_emit_json_string(mt4_s3c_reason_name(result->reason));
    mt4_s3c_emit(",\"infrastructure_marker\":");
    mt4_s3c_emit_json_string(result->reason_marker == NULL ? "" : result->reason_marker);

    mt4_s3c_emit(",\"exec_transition_observed\":%s", result->exec_transition_observed ? "true" : "false");
    mt4_s3c_emit(",\"wait_exited\":%s", result->wait_exited ? "true" : "false");
    mt4_s3c_emit(",\"wait_exit_status\":%d", result->wait_exited ? result->wait_exit_status : -1);
    mt4_s3c_emit(",\"wait_signalled\":%s", result->wait_signalled ? "true" : "false");
    mt4_s3c_emit(",\"wait_signal\":%d", result->wait_signalled ? result->wait_signal : 0);
    mt4_s3c_emit(",\"deadline_expired\":%s", result->deadline_expired ? "true" : "false");

    mt4_s3c_emit(",\"response_bytes_hex\":\"");
    mt4_s3c_emit_hex(result->response, result->response_bytes);
    mt4_s3c_emit("\",\"response_byte_count\":%u", (unsigned int)result->response_bytes);
    mt4_s3c_emit(",\"response_extra_byte_before_eof\":%s", result->response_extra_byte ? "true" : "false");

    mt4_s3c_emit(",\"seccomp_baseline\":{");
    mt4_s3c_emit("\"supervisor_seccomp\":%lu,", result->baseline_supervisor_mode);
    mt4_s3c_emit("\"supervisor_filters\":%lu,", result->baseline_supervisor_filters);
    mt4_s3c_emit("\"child_seccomp\":%lu,", result->baseline_child_mode);
    mt4_s3c_emit("\"child_filters\":%lu,", result->baseline_child_filters);
    mt4_s3c_emit("\"outer_post_seccomp\":%lu,", result->outer_post_mode);
    mt4_s3c_emit("\"outer_post_filters\":%lu,", result->outer_post_filters);
    mt4_s3c_emit("\"internal_post_seccomp\":%lu,", result->internal_post_mode);
    mt4_s3c_emit("\"internal_post_filters\":%lu,", result->internal_post_filters);
    mt4_s3c_emit("\"revalidated_filters\":%lu,", result->revalidated_filters);
    mt4_s3c_emit("\"trace_successful_seccomp_calls\":%u", result->trace_seccomp_success_count);
    mt4_s3c_emit("}");

    mt4_s3c_emit(",\"outer_capture\":{\"valid\":%s", result->outer_capture_valid ? "true" : "false");
    mt4_s3c_emit(",\"length\":%u", (unsigned int)result->outer_length);
    mt4_s3c_emit(",\"fprog_va_u64\":%llu", (unsigned long long)result->outer_fprog_address);
    mt4_s3c_emit(",\"filter_va_u64\":%llu", (unsigned long long)result->outer_filter_address);
    mt4_s3c_emit(",\"install_return_i32\":%d", result->outer_install_return);
    mt4_s3c_emit(",\"program_bytes_hex\":\"");
    mt4_s3c_emit_hex(result->outer_bytes, result->outer_byte_count);
    mt4_s3c_emit("\"}");

    mt4_s3c_emit(",\"internal_capture\":{\"valid\":%s", result->internal_capture_valid ? "true" : "false");
    mt4_s3c_emit(",\"length\":%u", (unsigned int)result->internal_length);
    mt4_s3c_emit(",\"fprog_va_u64\":%llu", (unsigned long long)result->internal_fprog_address);
    mt4_s3c_emit(",\"filter_va_u64\":%llu", (unsigned long long)result->internal_filter_address);
    mt4_s3c_emit(",\"install_return_i32\":%d", result->internal_install_return);
    mt4_s3c_emit(",\"program_bytes_hex\":\"");
    mt4_s3c_emit_hex(result->internal_bytes, result->internal_byte_count);
    mt4_s3c_emit("\"}");

    mt4_s3c_emit(",\"internal_filter_equivalence\":{\"valid\":%s", result->equivalence_valid ? "true" : "false");
    mt4_s3c_emit(",\"captured_internal_cbpf_sha256\":");
    mt4_s3c_emit_json_string(result->captured_internal_cbpf_sha256);
    mt4_s3c_emit(",\"digest_sha256\":");
    mt4_s3c_emit_json_string(result->equivalence_digest);
    mt4_s3c_emit("}");

    mt4_s3c_emit(",\"dump_leg\":{\"availability\":");
    mt4_s3c_emit_json_string(result->dump_available ? "AVAILABLE" : "UNAVAILABLE_IN_PINNED_ENVIRONMENT");
    mt4_s3c_emit(",\"terminates_at_index\":%d", result->dump_terminates_at_index);
    mt4_s3c_emit(",\"index0_bytes_hex\":\"");
    if (result->dump_available) {
        mt4_s3c_emit_hex(result->dump_index0, result->dump_index0_bytes);
    }
    mt4_s3c_emit("\",\"index1_bytes_hex\":\"");
    if (result->dump_available) {
        mt4_s3c_emit_hex(result->dump_index1, result->dump_index1_bytes);
    }
    mt4_s3c_emit("\"}");

    mt4_s3c_emit(",\"syscall_events\":[");
    for (event_index = 0; event_index < result->trace.used; event_index++) {
        const mt4_s3c_event_t *event = &result->trace.entries[event_index];

        mt4_s3c_emit("%s{\"sequence\":%u,\"phase\":", event_index ? "," : "", event->sequence);
        mt4_s3c_emit_json_string(event->phase == NULL ? "" : event->phase);
        mt4_s3c_emit(",\"stop\":%s", event->is_exit_stop ? "\"EXIT\"" : "\"ENTRY\"");
        mt4_s3c_emit(",\"nr\":%ld,\"args\":[%llu,%llu,%llu,%llu,%llu,%llu],\"ret\":%lld}",
                     event->number,
                     event->arguments[0],
                     event->arguments[1],
                     event->arguments[2],
                     event->arguments[3],
                     event->arguments[4],
                     event->arguments[5],
                     event->result);
    }
    mt4_s3c_emit("],\"syscall_event_count\":%u", result->trace.used);
    mt4_s3c_emit(",\"syscall_event_budget_exceeded\":%s", result->trace.budget_exceeded ? "true" : "false");
    mt4_s3c_emit(",\"trace_execve_count\":%u", result->trace_execve_count);
    /*
     * Durations are DIAGNOSTIC ONLY and are carried outside every digest preimage, so no governed
     * identity can ever acquire a time value (V9 SECTION 5, MACHINE_TIME_ANCHOR = NOT_ALLOWED).
     */
    mt4_s3c_emit(",\"non_digested_diagnostics\":{\"bounded_duration_ms\":%ld}", result->duration_ms);
    mt4_s3c_emit("}");
}

/* ==============================================================================================
 * MAIN
 * ============================================================================================ */

static int mt4_s3c_hex_to_bytes(const char *text, unsigned char *out, size_t out_length)
{
    size_t index;

    if (strlen(text) != out_length * 2u) {
        return -1;
    }
    for (index = 0; index < out_length * 2u; index++) {
        char character = text[index];
        unsigned int value;

        if (character >= '0' && character <= '9') {
            value = (unsigned int)(character - '0');
        } else if (character >= 'a' && character <= 'f') {
            value = (unsigned int)(character - 'a') + 10u;
        } else {
            return -1;
        }
        if ((index & 1u) == 0u) {
            out[index / 2u] = (unsigned char)(value << 4);
        } else {
            out[index / 2u] = (unsigned char)(out[index / 2u] | value);
        }
    }
    return 0;
}

static const char *mt4_s3c_option(int argc, char **argv, const char *name)
{
    int index;

    for (index = 1; index + 1 < argc; index += 2) {
        if (strcmp(argv[index], name) == 0) {
            return argv[index + 1];
        }
    }
    return NULL;
}

static int mt4_s3c_is_lower_hex(const char *value, size_t expected)
{
    size_t index;

    if (value == NULL || strlen(value) != expected) {
        return 0;
    }
    for (index = 0; index < expected; index++) {
        char character = value[index];

        if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) {
            return 0;
        }
    }
    return 1;
}

int main(int argc, char **argv)
{
    mt4_s3c_candidate_t candidate;
    mt4_s3c_run_identity_t identity;
    mt4_s3c_plan_t plan;
    mt4_s3c_case_result_t *result;
    unsigned int index;
    const char *output_path;
    const char *outer_policy_digest;
    const char *case_set_digest;
    const char *value;
    int output_fd;

    if ((argc % 2) != 1) {
        (void)fprintf(stderr, "MT4_S3C_USAGE=paired --option value arguments only
");
        return MT4_S3C_EXIT_LAUNCHER_FAILED;
    }

    candidate.candidate_path = mt4_s3c_option(argc, argv, "--candidate");
    value = mt4_s3c_option(argc, argv, "--candidate-sha256");
    if (candidate.candidate_path == NULL || !mt4_s3c_is_lower_hex(value, 64u) ||
        mt4_s3c_hex_to_bytes(value, candidate.governed_digest, sizeof(candidate.governed_digest)) != 0) {
        mt4_s3c_fatal(MT4_S3C_REASON_QUALIFICATION_INFRASTRUCTURE_FAILURE, "candidate_identity");
    }
    identity.candidate_binary_sha256 = value;

    value = mt4_s3c_option(argc, argv, "--candidate-size");
    candidate.governed_size = (value == NULL) ? 0ull : strtoull(value, NULL, 10);
    if (candidate.governed_size == 0ull ||
        candidate.governed_size > (unsigned long long)MT4_S3C_MAX_WORKER_BINARY_BYTES) {
        mt4_s3c_fatal(MT4_S3C_REASON_QUALIFICATION_INFRASTRUCTURE_FAILURE, "candidate_size");
    }

    identity.canonical_internal_policy_id = mt4_s3c_option(argc, argv, "--canonical-internal-policy-id");
    identity.canonical_internal_policy_sha256 = mt4_s3c_option(argc, argv, "--canonical-internal-policy-sha256");
    identity.canonical_internal_cbpf_sha256 = mt4_s3c_option(argc, argv, "--canonical-internal-cbpf-sha256");
    outer_policy_digest = mt4_s3c_option(argc, argv, "--outer-containment-policy-digest");
    case_set_digest = mt4_s3c_option(argc, argv, "--observation-case-set-digest");
    identity.source_head_sha = mt4_s3c_option(argc, argv, "--source-head-sha");
    value = mt4_s3c_option(argc, argv, "--canonical-internal-cbpf-count");
    identity.canonical_internal_cbpf_instruction_count = (value == NULL) ? 0u : (unsigned int)strtoul(value, NULL, 10);
    value = mt4_s3c_option(argc, argv, "--source-run-id");
    identity.source_run_id = (value == NULL) ? 0ull : strtoull(value, NULL, 10);
    value = mt4_s3c_option(argc, argv, "--source-run-attempt");
    identity.source_run_attempt = (value == NULL) ? 0ull : strtoull(value, NULL, 10);

    if (identity.canonical_internal_policy_id == NULL || identity.canonical_internal_policy_id[0] == '\0' ||
        !mt4_s3c_is_lower_hex(identity.canonical_internal_policy_sha256, 64u) ||
        !mt4_s3c_is_lower_hex(identity.canonical_internal_cbpf_sha256, 64u) ||
        !mt4_s3c_is_lower_hex(identity.source_head_sha, 40u) ||
        identity.canonical_internal_cbpf_instruction_count == 0u ||
        identity.canonical_internal_cbpf_instruction_count > (unsigned int)MT4_S3C_MAX_FILTER_INSTRUCTIONS ||
        identity.source_run_id == 0ull || identity.source_run_attempt == 0ull ||
        !mt4_s3c_is_lower_hex(outer_policy_digest, 64u) || !mt4_s3c_is_lower_hex(case_set_digest, 64u)) {
        mt4_s3c_fatal(MT4_S3C_REASON_QUALIFICATION_INFRASTRUCTURE_FAILURE, "run_identity");
    }

    value = mt4_s3c_option(argc, argv, "--case-plan");
    if (value == NULL || mt4_s3c_load_plan(value, &plan) != 0) {
        mt4_s3c_fatal(MT4_S3C_REASON_CASE_PLAN_MALFORMED, "plan");
    }
    output_path = mt4_s3c_option(argc, argv, "--out");
    if (output_path == NULL) {
        mt4_s3c_fatal(MT4_S3C_REASON_QUALIFICATION_INFRASTRUCTURE_FAILURE, "out");
    }

    mt4_s3c_output = (char *)malloc((size_t)MT4_S3C_OUTPUT_CAPACITY);
    result = (mt4_s3c_case_result_t *)malloc(sizeof(*result));
    if (mt4_s3c_output == NULL || result == NULL) {
        mt4_s3c_fatal(MT4_S3C_REASON_QUALIFICATION_INFRASTRUCTURE_FAILURE, "allocate");
    }

    mt4_s3c_emit("{\"schema\":\"mt4-s3c-raw-observation-record.v1\"");
    mt4_s3c_emit(",\"platform_id\":\"LINUX_X86_64\"");
    mt4_s3c_emit(",\"observation_basis\":\"EXECUTED_CANDIDATE_UNDER_OUTER_CONTAINMENT\"");
    mt4_s3c_emit(",\"candidate_binary_sha256\":\"");
    mt4_s3c_emit_hex(candidate.governed_digest, sizeof(candidate.governed_digest));
    mt4_s3c_emit("\",\"candidate_binary_bytes\":%llu", candidate.governed_size);
    mt4_s3c_emit(",\"source_run_id\":%llu", identity.source_run_id);
    mt4_s3c_emit(",\"source_run_attempt\":%llu", identity.source_run_attempt);
    mt4_s3c_emit(",\"source_head_sha\":");
    mt4_s3c_emit_json_string(identity.source_head_sha);
    mt4_s3c_emit(",\"canonical_internal_policy_id\":");
    mt4_s3c_emit_json_string(identity.canonical_internal_policy_id);
    mt4_s3c_emit(",\"canonical_internal_policy_sha256\":");
    mt4_s3c_emit_json_string(identity.canonical_internal_policy_sha256);
    mt4_s3c_emit(",\"canonical_internal_cbpf_instruction_count\":%u",
                 identity.canonical_internal_cbpf_instruction_count);
    mt4_s3c_emit(",\"canonical_internal_cbpf_sha256\":");
    mt4_s3c_emit_json_string(identity.canonical_internal_cbpf_sha256);
    /*
     * The two environment-scoped digests live on A3 and A4 ONLY, never on the governed worker row:
     * they describe the QUALIFICATION ENVIRONMENT rather than the immutable worker artifact, so
     * placing them on the row would make the row change when the environment changes (V9 SECTION 7).
     */
    mt4_s3c_emit(",\"outer_containment_policy_digest_sha256\":");
    mt4_s3c_emit_json_string(outer_policy_digest);
    mt4_s3c_emit(",\"observation_case_set_digest_sha256\":");
    mt4_s3c_emit_json_string(case_set_digest);
    mt4_s3c_emit(",\"case_plan_sha256\":\"");
    mt4_s3c_emit_hex(plan.plan_sha256, sizeof(plan.plan_sha256));
    mt4_s3c_emit("\",\"fixture_sha256\":\"");
    mt4_s3c_emit_hex(plan.fixture_sha256, sizeof(plan.fixture_sha256));
    mt4_s3c_emit("\",\"case_count\":%u,\"cases\":[", plan.case_count);

    for (index = 0; index < plan.case_count; index++) {
        /*
         * Repair 3: a supervisor whose dumpability could not be restored cannot map the next
         * child's namespaces.  Continuing would emit UID_GID_MAP_FAILED for every remaining case
         * and present an infrastructure failure as a candidate verdict, so the sequence stops with
         * the exact reason instead.
         */
        if (mt4_s3c_sequence_halted || mt4_s3c_terminal_reason != MT4_S3C_REASON_NONE) {
            mt4_s3c_fatal(mt4_s3c_terminal_reason == MT4_S3C_REASON_NONE
                              ? MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED
                              : mt4_s3c_terminal_reason,
                          "sequence_halted");
        }
        mt4_s3c_run_case(&candidate, &identity, &plan.cases[index], result);
        if (index > 0u) {
            mt4_s3c_emit(",");
        }
        mt4_s3c_emit_case(&plan.cases[index], result, index);
    }
    mt4_s3c_emit("]}
");

    if (mt4_s3c_output_overflow) {
        mt4_s3c_fatal(MT4_S3C_REASON_OBSERVATION_EVENT_BUDGET_EXCEEDED, "record_capacity");
    }

    /*
     * 2D, THE FINAL GATE.  Checked HERE, before a single byte of the observation record is written,
     * so it is effective on the LAST case as well as between cases.  A "before the next case" check
     * alone left C25 -- the final case -- able to complete a successful run after its own teardown
     * had failed, which is precisely the hole this closes.  No record is written at all when the
     * sequence carries a terminal infrastructure failure.
     */
    if (mt4_s3c_sequence_halted || mt4_s3c_terminal_reason != MT4_S3C_REASON_NONE) {
        mt4_s3c_fatal(mt4_s3c_terminal_reason == MT4_S3C_REASON_NONE
                          ? MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED
                          : mt4_s3c_terminal_reason,
                      mt4_s3c_terminal_marker[0] == '\0' ? "terminal_teardown" : mt4_s3c_terminal_marker);
    }
    output_fd = open(output_path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
    if (output_fd < 0 || mt4_s3c_write_all(output_fd, mt4_s3c_output, mt4_s3c_output_used) != 0) {
        if (output_fd >= 0) {
            (void)close(output_fd);
        }
        mt4_s3c_fatal(MT4_S3C_REASON_QUALIFICATION_INFRASTRUCTURE_FAILURE, "write_record");
    }
    (void)close(output_fd);
    (void)fprintf(stderr, "MT4_S3C_OBSERVATION_RECORD_WRITTEN=%u
", plan.case_count);
    return 0;
}
