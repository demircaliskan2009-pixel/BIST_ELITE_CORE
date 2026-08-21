/*
 * MT4-S3C P0 BLST PLATFORM CAPABILITY DEFINITION.  Qualification infrastructure only.
 *
 * ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTION 30.
 * BUNDLE ENTRY 2 of the exact 16-entry qualification source bundle (V9 SECTION 8).
 *
 * PIN: supranational/blst v0.3.17 @ 54e6e55674722fc2797ebb4bbb71b26d881eb4b8.
 *
 * WHY THIS FILE EXISTS.  The worker is built with BOTH -D__BLST_PORTABLE__ and -D__BLST_NO_CPUID__.
 * __BLST_NO_CPUID__ removes cpuid.c from the pinned src/server.c translation unit, and cpuid.c is
 * the only upstream DEFINITION of __blst_platform_cap, while the pinned x86_64 assembly still READS
 * that symbol to select optimised paths.  Combined with the zero-undefined-symbol link policy, a
 * missing capability definition is therefore a BUILD FAILURE rather than a silent fallback to
 * runtime CPUID.  The fail-closed property is STRUCTURAL, not a check somebody remembered to write.
 *
 * WHAT IS PROHIBITED ABSOLUTELY (V9 SECTION 30 point 4): runtime CPUID execution; runtime capability
 * discovery of any kind; an environment-selected backend; a caller-selected backend; any constructor
 * that writes this object; any code path that assigns to it after link time.  Placing the object in
 * read-only data makes the last two structurally impossible rather than merely forbidden: a write
 * would fault, and no constructor exists anywhere in the image.
 *
 * SCOPE HONESTY.  No cryptographic primitive is authored here.  This file defines one zero-valued
 * object and nothing else.  It selects no verifier profile, admits no dependency, and promotes no
 * readiness or connector state.
 *
 * THE GOVERNED OBJECT SIZE, AND WHY THE CANDIDATE CANNOT DEFINE IT.  V9 SECTION 30 rule Q5 requires
 * st_size to equal a GOVERNED OBJECT SIZE whose authority is NAMED and is explicitly NOT the
 * candidate's own symbol table.  That authority is this file -- the approved source/build contract
 * for bundle entry 2 -- whose governed value is committed as the qualification constant
 * MT4_S3C_BLST_PLATFORM_CAP_SIZE_BYTES below, independently frozen as a literal in the ELF
 * qualifier (bundle entry 4), and pinned again on the trusted Stage-C surface.  The ELF qualifier
 * reads the candidate's symbol table and compares it AGAINST that authority; a candidate
 * self-assertion of size can therefore only FAIL the check and can never define it.
 *
 * IF THE PINNED TOOLCHAIN CANNOT SATISFY Q1..Q9 SIMULTANEOUSLY -- strong AND hidden AND
 * non-writable effective page AND file-backed AND the governed size AND the zero value -- the
 * correct outcome is UNRESOLVED_P2 returned to the controller and IMPLEMENTATION STOPS.  No
 * workaround is permitted here, and none exists in this file.
 */

#include <stdint.h>

/*
 * GOVERNED OBJECT SIZE, in bytes.  The pinned x86_64 assembly reads the capability word as a 32-bit
 * quantity, so the governed object is exactly one uint32_t.  This constant is the authority the ELF
 * qualifier compares the candidate symbol table against.
 */
#define MT4_S3C_BLST_PLATFORM_CAP_SIZE_BYTES 4

/* GOVERNED VALUE: the zero capability state.  No specialised path is ever selected. */
#define MT4_S3C_BLST_PLATFORM_CAP_VALUE 0u

/*
 * EXACTLY ONE strong, hidden, section-defined definition, initialised to the zero capability state
 * and placed in read-only data.
 *
 *   used            keeps the definition even though no translation unit in this project reads it;
 *                   the only reader is the pinned upstream assembly.
 *   visibility      hidden, satisfying Q3 and the frozen link policy that forbids exported symbols.
 *   section         a .rodata sub-section, so the object lands in a PT_LOAD whose EFFECTIVE page
 *                   permission has PF_W clear and which is FILE BACKED, satisfying Q7.  A .bss or
 *                   COMMON placement would satisfy neither and is exactly what Q6 rejects.
 *   aligned         the natural alignment of the governed word, so no padding changes st_size.
 */
__attribute__((used, visibility("hidden"), section(".rodata.mt4_s3c_blst_cap"), aligned(4)))
const uint32_t __blst_platform_cap = MT4_S3C_BLST_PLATFORM_CAP_VALUE;

_Static_assert(sizeof(__blst_platform_cap) == MT4_S3C_BLST_PLATFORM_CAP_SIZE_BYTES,
               "MT4_S3C governed __blst_platform_cap object size");
_Static_assert(MT4_S3C_BLST_PLATFORM_CAP_VALUE == 0u,
               "MT4_S3C governed __blst_platform_cap value is the zero capability state");

/*
 * Mark the stack non-executable.  V9 SECTION 29.1 treats an OMITTED PT_GNU_STACK as FAIL rather
 * than an implicit pass, so every object contributing to the link must carry the note.
 */
__asm__(".section .note.GNU-stack,\"\",@progbits");
