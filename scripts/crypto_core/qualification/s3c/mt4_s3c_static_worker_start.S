/*
 * MT4-S3C P0 STATIC WORKER ENTRY POINT.  Qualification infrastructure only.
 *
 * ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 29.1, 30.
 * BUNDLE ENTRY 14 of the exact 16-entry qualification source bundle (V9 SECTION 8).
 *
 * WHY THIS FILE EXISTS.  V9 SECTION 29.1 requires a PROJECT-OWNED entry point and forbids a libc
 * _start or __libc_start_main chain, forbids PT_INTERP and PT_DYNAMIC, and forbids any
 * self-relocating stub running before the project entry point (which is why the image is ET_EXEC
 * non-PIE rather than static-PIE).  This is that entry point: the first instruction the kernel
 * transfers to after the trusted execve, and the whole of the pre-main runtime.
 *
 * WHAT IT DOES, AND NOTHING ELSE.  It terminates the frame-pointer chain, aligns the stack to the
 * System V AMD64 boundary, and calls the worker bootstrap.  There is no constructor machinery, no
 * TLS setup, no environment parsing, no argument parsing, no atexit registration, and no dynamic
 * loader interaction.  V9 SECTION 30 rule Q9 requires .init_array and .fini_array to be absent or
 * zero-length, which is a property of never creating any.
 *
 * NO NUMERIC VALUE IS ASSERTED FROM MEMORY.  This is a capital-S assembly file, so it is run
 * through the C preprocessor and takes __NR_exit_group from the pinned UAPI headers by name.  The
 * only literal is this project's own reserved exit code.
 *
 * THE UNREACHABLE TAIL.  mt4_s3c_worker_main never returns: every one of its paths ends in
 * exit_group.  The tail below therefore cannot execute.  It exists so that "returned unexpectedly"
 * is a typed, contained bootstrap failure rather than a fall-through into whatever bytes follow.
 * It zeroes EVERY argument register the syscall does not consume, including the sixth, exactly as
 * V9 SECTION 14.3 requires of every project-owned syscall site, so the outer filter's zero-tail
 * rule holds even on this path.
 */

#include <asm/unistd.h>

/* Reserved candidate exit code: WORKER_BOOTSTRAP_FAILED (V9 20.5). */
#define MT4_S3C_EXIT_BOOTSTRAP_FAILED 64

    .section .text.mt4_s3c_start, "ax", @progbits
    .balign 16
    .globl _start
    .hidden _start
    .type _start, @function
_start:
    /* Terminate the frame-pointer chain: there is no caller frame above this one. */
    xorq %rbp, %rbp

    /*
     * The kernel hands over a 16-byte-aligned stack pointing at argc.  Re-align defensively and
     * unconditionally, so the call below leaves rsp congruent to 8 modulo 16 at function entry as
     * the System V AMD64 ABI requires.  Nothing on the incoming stack is read.
     */
    andq $-16, %rsp

    call mt4_s3c_worker_main

    /* Unreachable by contract.  Typed, contained, and zero-tailed. */
    movl $__NR_exit_group, %eax
    movl $MT4_S3C_EXIT_BOOTSTRAP_FAILED, %edi
    xorl %esi, %esi
    xorl %edx, %edx
    xorl %r10d, %r10d
    xorl %r8d, %r8d
    xorl %r9d, %r9d
    syscall

    /*
     * exit_group does not return.  If the kernel somehow delivered control back here, halt rather
     * than execute whatever follows.  In user mode hlt raises SIGSEGV, which the supervisor
     * observes and adjudicates as WORKER_CRASHED -- a process failure, never a crypto verdict.
     */
    hlt

    .size _start, . - _start

/*
 * Mark the stack non-executable.  V9 SECTION 29.1 requires PT_GNU_STACK with the executable flag
 * clear and treats an OMITTED PT_GNU_STACK as FAIL rather than an implicit pass, so this note must
 * be present in every object that contributes to the link.
 */
    .section .note.GNU-stack, "", @progbits
