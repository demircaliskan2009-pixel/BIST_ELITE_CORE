"""MT4-S3C P0 static ELF qualifier.  Qualification infrastructure only.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 29 and 30.
BUNDLE ENTRY 4 of the exact 16-entry qualification source bundle (V9 SECTION 8).

WHAT THIS MODULE IS.  It is a PURE STATIC PARSE of candidate bytes with ZERO EXECUTION.  It never
runs, maps, loads or links the candidate; it reads the file, parses the ELF structures in
arbitrary-precision integers, and emits the ELF qualification record (artifact class A2).

WHY THE ORACLE IS NEVER THE CANDIDATE.  V9 SECTION 29.5 rule EM-11 exists because V8 required the
observed program-header multiset to equal "a governed expected inventory" without saying where that
inventory came from: if it came from the candidate, the check is vacuous.  Every expectation in this
module is a LITERAL committed in reviewed source, and the trusted surface pins the same literals
independently.  The candidate's own headers and symbol table are compared AGAINST those literals and
can only ever FAIL them, never define them.

FAIL CLOSED, ALWAYS.  Nothing is clamped, wrapped, coerced or truncated.  Every arithmetic
computation is unbounded and range-checked BEFORE use, and every violation is a deterministic
failure with a distinct marker.

SELF-CONTAINED.  This module imports no repository module and contains no dynamic import machinery,
so V9 SECTION 28 rules R2, R5 and leg B hold by construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

# =================================================================================================
# FROZEN IDENTITIES
# =================================================================================================

ELF_RECORD_SCHEMA = "mt4-s3c-elf-qualification-record.v1"
ELF_RECORD_DIGEST_DOMAIN = b"mt4-s3c-elf-qualification-record.v1\x00"
EXPECTED_PHDR_SCHEMA = "mt4-s3c-expected-phdr-inventory.v1"
PLATFORM_ID = "LINUX_X86_64"

# =================================================================================================
# GOVERNED LITERAL CONSTANTS (V9 27.2, 29.1, 29.3, 29.5, 30)
# =================================================================================================

# The SAME constant the ZIP policy enforces as its per-member binary cap, so the archive bound and
# the ELF bound cannot drift apart (V9 27.2).
MAX_WORKER_BINARY_BYTES = 8 * 1024 * 1024

PAGE_SIZE_REQUIRED = 4096
MAX_PHNUM = 16
MAX_SECTION_COUNT = 64

MAX_PT_LOAD_EFFECTIVE_BYTES = 16 * 1024 * 1024
MAX_AGGREGATE_EFFECTIVE_BYTES = 32 * 1024 * 1024
STACK_RESERVE_BYTES = 8 * 1024 * 1024
GOVERNED_HEADROOM_BYTES = 24 * 1024 * 1024
RLIMIT_AS_BYTES = MAX_AGGREGATE_EFFECTIVE_BYTES + STACK_RESERVE_BYTES + GOVERNED_HEADROOM_BYTES

# V9 SECTION 30 rule Q5: the GOVERNED OBJECT SIZE authority is the approved source/build contract
# for bundle entry 2, NOT the candidate symbol table.  This literal is that authority, and the
# trusted surface pins the identical value.
BLST_PLATFORM_CAP_SYMBOL = "__blst_platform_cap"
BLST_PLATFORM_CAP_SIZE_BYTES = 4
BLST_PLATFORM_CAP_VALUE_BYTES = b"\x00\x00\x00\x00"

# V9 SECTION 29.6 rule Q10: the canonical internal filter objects, with their governed sizes.  These
# are properties of the reviewed canonical policy source (bundle entry 10) and of the pinned UAPI
# structure layout, never of the candidate.
INTERNAL_FPROG_SYMBOL = "mt4_s3c_internal_filter_fprog"
INTERNAL_PROGRAM_SYMBOL = "mt4_s3c_internal_filter_program"
INTERNAL_FPROG_SIZE_BYTES = 16
INTERNAL_PROGRAM_INSTRUCTIONS = 113
INTERNAL_PROGRAM_SIZE_BYTES = INTERNAL_PROGRAM_INSTRUCTIONS * 8

ENTRY_SYMBOL = "_start"

# ELF constants, from the ELF64 specification.  These are format constants, not platform values.
ELF_MAGIC = b"\x7fELF"
ELFCLASS64 = 2
ELFDATA2LSB = 1
EV_CURRENT = 1
ET_EXEC = 2
EM_X86_64 = 62

PT_NULL = 0
PT_LOAD = 1
PT_DYNAMIC = 2
PT_INTERP = 3
PT_NOTE = 4
PT_SHLIB = 5
PT_PHDR = 6
PT_TLS = 7
PT_GNU_EH_FRAME = 0x6474E550
PT_GNU_STACK = 0x6474E551
PT_GNU_RELRO = 0x6474E552
PT_GNU_PROPERTY = 0x6474E553

PF_X = 1
PF_W = 2
PF_R = 4

SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_RELA = 4
SHT_DYNAMIC = 6
SHT_NOBITS = 8
SHT_REL = 9
SHT_DYNSYM = 11
SHT_INIT_ARRAY = 14
SHT_FINI_ARRAY = 15

SHN_UNDEF = 0
SHN_COMMON = 0xFFF2
# The reserved range.  SHN_LORESERVE .. SHN_HIRESERVE never denote a real containing section, so a
# governed object whose defining index lands there is not section-defined however it got there.
SHN_LORESERVE = 0xFF00
SHN_HIRESERVE = 0xFFFF

# Section flags and the two section types a governed object may never be declared in.
SHF_ALLOC = 0x2

STT_NOTYPE = 0
STT_OBJECT = 1
STT_FUNC = 2

STB_LOCAL = 0
STB_GLOBAL = 1
STB_WEAK = 2

STV_DEFAULT = 0
STV_INTERNAL = 1
STV_HIDDEN = 2
STV_PROTECTED = 3

_PT_TYPE_NAMES = {
    PT_NULL: "PT_NULL",
    PT_LOAD: "PT_LOAD",
    PT_DYNAMIC: "PT_DYNAMIC",
    PT_INTERP: "PT_INTERP",
    PT_NOTE: "PT_NOTE",
    PT_SHLIB: "PT_SHLIB",
    PT_PHDR: "PT_PHDR",
    PT_TLS: "PT_TLS",
    PT_GNU_EH_FRAME: "PT_GNU_EH_FRAME",
    PT_GNU_STACK: "PT_GNU_STACK",
    PT_GNU_RELRO: "PT_GNU_RELRO",
    PT_GNU_PROPERTY: "PT_GNU_PROPERTY",
}

# =================================================================================================
# EM-11: THE LITERAL, TRUSTED, NON-CANDIDATE-DERIVED EXPECTED PROGRAM-HEADER INVENTORY.
#
# Each entry is (p_type, exact p_flags).  The multiset and the exact flag value of every entry are
# EXACT expectations.  PT_LOAD entries are additionally required to appear in ascending p_vaddr
# order; other types carry no order requirement, and that distinction is stated rather than implied.
#
# WHICH FIELDS ARE EXACT AND WHICH ARE BUILD_DERIVED (V9 29.5 EM-11): p_type, p_flags and p_align
# are EXACT; p_offset, p_vaddr, p_filesz and p_memsz are BUILD_DERIVED and are bounded by EM-1..EM-7
# and EM-15 rather than pinned to a literal, because their exact values are a property of the
# approved build profile.  The build profile itself is pinned by the frozen link flags in the
# reviewed qualification workflow and by the identical literal on the trusted Stage-C surface.
#
# A SUBSET-OF-AN-ALLOWLIST CHECK IS EXPLICITLY REJECTED as insufficient: it cannot detect a MISSING
# expected header.  The comparison below is exact multiset equality.
# =================================================================================================

# THE EXACT ALIGNMENT AUTHORITY (repair 8A).  p_align was DOCUMENTED as exact and then never
# compared, so an image with arbitrary segment alignment satisfied the inventory check.  It is now
# part of the tuple.
#
# WHERE THE VALUES COME FROM, since they must come from a NON-CANDIDATE authority:
#   PT_LOAD 0x1000  -- pinned by the frozen link flags in the reviewed qualification workflow, which
#                      passes -Wl,-z,max-page-size=0x1000.  This is a property of the approved BUILD
#                      CONTRACT, not an assumption about a toolchain default, which is exactly why
#                      the flag is stated in the workflow rather than inferred here.
#   PT_GNU_STACK 0x10 -- the x86_64 psABI stack alignment the marker segment carries.
#
# If the pinned toolchain ever contradicts these values the correct outcome is a CLOSED FAILURE that
# returns to architecture with the observed value.  Widening this tuple to make a build pass would
# destroy the only thing it proves.
PT_LOAD_ALIGN_REQUIRED = 0x1000
PT_GNU_STACK_ALIGN_REQUIRED = 0x10

EXPECTED_PHDR_INVENTORY = (
    (PT_LOAD, PF_R | PF_X, PT_LOAD_ALIGN_REQUIRED),
    (PT_LOAD, PF_R | PF_W, PT_LOAD_ALIGN_REQUIRED),
    (PT_GNU_STACK, PF_R | PF_W, PT_GNU_STACK_ALIGN_REQUIRED),
)

# PT_INTERP and PT_DYNAMIC in the OBSERVED inventory are an immediate FAIL regardless of the
# expected inventory (V9 29.5 EM-11).
ALWAYS_FORBIDDEN_PHDR_TYPES = (PT_INTERP, PT_DYNAMIC, PT_SHLIB, PT_TLS)


class ElfQualificationError(RuntimeError):
    """Any failure to prove a required ELF property.  There is no partial success."""


def _fail(marker, detail=""):
    raise ElfQualificationError(marker if not detail else marker + ": " + detail)


def canonical_phdr_inventory(inventory):
    """The canonical string form every non-candidate authority compares on.

    The alignment is part of the string, so the reviewed source, the qualification workflow and the
    trusted Stage-C surface all have to agree about it, not merely about type and flags.
    """
    return ",".join(
        _PT_TYPE_NAMES.get(kind, "PT_" + str(kind)) + ":" + str(flags) + ":" + hex(align)
        for kind, flags, align in inventory
    )


# =================================================================================================
# PRIMITIVE READERS.  Every field is bounds-checked before it is read.
# =================================================================================================


def _read(data, offset, length):
    if offset < 0 or length < 0 or offset + length > len(data):
        _fail("ELF_RANGE_INVALID", "read beyond the file length")
    return data[offset : offset + length]


def _u16(data, offset):
    return int.from_bytes(_read(data, offset, 2), "little")


def _u32(data, offset):
    return int.from_bytes(_read(data, offset, 4), "little")


def _u64(data, offset):
    return int.from_bytes(_read(data, offset, 8), "little")


# =================================================================================================
# HEADER PARSING
# =================================================================================================


class ProgramHeader:
    __slots__ = ("index", "p_type", "p_flags", "p_offset", "p_vaddr", "p_paddr", "p_filesz", "p_memsz", "p_align")

    def __init__(self, index, data, offset):
        self.index = index
        self.p_type = _u32(data, offset + 0)
        self.p_flags = _u32(data, offset + 4)
        self.p_offset = _u64(data, offset + 8)
        self.p_vaddr = _u64(data, offset + 16)
        self.p_paddr = _u64(data, offset + 24)
        self.p_filesz = _u64(data, offset + 32)
        self.p_memsz = _u64(data, offset + 40)
        self.p_align = _u64(data, offset + 48)

    def type_name(self):
        return _PT_TYPE_NAMES.get(self.p_type, "PT_" + str(self.p_type))


class SectionHeader:
    __slots__ = (
        "index",
        "sh_name",
        "sh_type",
        "sh_flags",
        "sh_addr",
        "sh_offset",
        "sh_size",
        "sh_link",
        "sh_info",
        "sh_addralign",
        "sh_entsize",
        "name",
    )

    def __init__(self, index, data, offset):
        self.index = index
        self.sh_name = _u32(data, offset + 0)
        self.sh_type = _u32(data, offset + 4)
        self.sh_flags = _u64(data, offset + 8)
        self.sh_addr = _u64(data, offset + 16)
        self.sh_offset = _u64(data, offset + 24)
        self.sh_size = _u64(data, offset + 32)
        self.sh_link = _u32(data, offset + 40)
        self.sh_info = _u32(data, offset + 44)
        self.sh_addralign = _u64(data, offset + 48)
        self.sh_entsize = _u64(data, offset + 56)
        self.name = ""


class Symbol:
    __slots__ = ("name", "name_offset", "info", "other", "shndx", "value", "size")

    def __init__(self, name, info, other, shndx, value, size, name_offset=0):
        self.name = name
        self.name_offset = name_offset
        self.info = info
        self.other = other
        self.shndx = shndx
        self.value = value
        self.size = size

    def binding(self):
        return self.info >> 4

    def visibility(self):
        return self.other & 0x03

    def symbol_type(self):
        return self.info & 0x0F


def parse_elf(data):
    """Parse the ELF64 header, program headers and section headers with EM-1..EM-7 enforced."""
    if len(data) < 64:
        _fail("ELF_TRUNCATED", "file shorter than an ELF64 header")
    if len(data) > MAX_WORKER_BINARY_BYTES:
        _fail("ELF_FILE_TOO_LARGE", str(len(data)))
    if _read(data, 0, 4) != ELF_MAGIC:
        _fail("ELF_MAGIC_INVALID")
    if data[4] != ELFCLASS64:
        _fail("ELF_CLASS_INVALID")
    if data[5] != ELFDATA2LSB:
        _fail("ELF_ENDIANNESS_INVALID")
    if data[6] != EV_CURRENT:
        _fail("ELF_VERSION_INVALID")

    e_type = _u16(data, 16)
    e_machine = _u16(data, 18)
    e_version = _u32(data, 20)
    e_entry = _u64(data, 24)
    e_phoff = _u64(data, 32)
    e_shoff = _u64(data, 40)
    e_ehsize = _u16(data, 52)
    e_phentsize = _u16(data, 54)
    e_phnum = _u16(data, 56)
    e_shentsize = _u16(data, 58)
    e_shnum = _u16(data, 60)
    e_shstrndx = _u16(data, 62)

    # ET_EXEC non-PIE.  A static-PIE (ET_DYN) carries a self-relocating stub that runs BEFORE the
    # project entry point, which V9 29.1 forbids outright.
    if e_type != ET_EXEC:
        _fail("ELF_TYPE_NOT_ET_EXEC", str(e_type))
    if e_machine != EM_X86_64:
        _fail("ELF_MACHINE_INVALID", str(e_machine))
    if e_version != EV_CURRENT:
        _fail("ELF_VERSION_INVALID")
    if e_ehsize != 64:
        _fail("ELF_HEADER_SIZE_INVALID", str(e_ehsize))

    # EM-1: table geometry within the ELF64 widths and consistent with the file size.
    if e_phentsize != 56:
        _fail("ELF_PHENTSIZE_INVALID", str(e_phentsize))
    if e_phnum == 0 or e_phnum > MAX_PHNUM:
        _fail("ELF_PHNUM_INVALID", str(e_phnum))
    if e_shentsize != 64:
        _fail("ELF_SHENTSIZE_INVALID", str(e_shentsize))
    if e_shnum == 0 or e_shnum > MAX_SECTION_COUNT:
        _fail("ELF_SHNUM_INVALID", str(e_shnum))

    # EM-7: a header table whose declared extent exceeds the file length is FAIL, not a short read.
    if e_phoff + (e_phnum * e_phentsize) > len(data):
        _fail("ELF_PHDR_TABLE_OUT_OF_RANGE")
    if e_shoff + (e_shnum * e_shentsize) > len(data):
        _fail("ELF_SHDR_TABLE_OUT_OF_RANGE")
    if e_shstrndx >= e_shnum:
        _fail("ELF_SHSTRNDX_INVALID")

    program_headers = [ProgramHeader(index, data, e_phoff + index * e_phentsize) for index in range(e_phnum)]
    section_headers = [SectionHeader(index, data, e_shoff + index * e_shentsize) for index in range(e_shnum)]

    strings = section_headers[e_shstrndx]
    if strings.sh_type != SHT_STRTAB:
        _fail("ELF_SHSTRTAB_INVALID")
    string_blob = _read(data, strings.sh_offset, strings.sh_size)
    for section in section_headers:
        section.name = _read_cstring(string_blob, section.sh_name)

    return {
        "e_entry": e_entry,
        "e_phnum": e_phnum,
        "e_shnum": e_shnum,
        "program_headers": program_headers,
        "section_headers": section_headers,
    }


def _read_cstring(blob, offset):
    if offset >= len(blob):
        _fail("ELF_STRING_OFFSET_INVALID", str(offset))
    end = blob.find(b"\x00", offset)
    if end < 0:
        _fail("ELF_STRING_UNTERMINATED", str(offset))
    return blob[offset:end].decode("ascii", "replace")


# =================================================================================================
# EM-2 .. EM-7 RANGE SAFETY
# =================================================================================================


def check_program_header_ranges(data, program_headers, page_size):
    for header in program_headers:
        for field, value in (
            ("p_offset", header.p_offset),
            ("p_vaddr", header.p_vaddr),
            ("p_paddr", header.p_paddr),
            ("p_filesz", header.p_filesz),
            ("p_memsz", header.p_memsz),
            ("p_align", header.p_align),
        ):
            if value < 0 or value >= 2**64:
                _fail("ELF_RANGE_INVALID", field)
        # EM-3, computed unbounded and never allowed to wrap.
        if header.p_offset + header.p_filesz > len(data):
            _fail("ELF_RANGE_INVALID", "p_offset + p_filesz exceeds the file length")
        # EM-4.
        if header.p_vaddr + header.p_memsz >= 2**64:
            _fail("ELF_RANGE_INVALID", "p_vaddr + p_memsz overflows the address space")
        # EM-5.
        if header.p_filesz > header.p_memsz:
            _fail("ELF_RANGE_INVALID", "p_filesz exceeds p_memsz")
        if header.p_type == PT_LOAD:
            # EM-6: power-of-two alignment at least the page size, and the ELF congruence rule.
            if header.p_align < page_size or (header.p_align & (header.p_align - 1)) != 0:
                _fail("ELF_ALIGN_INVALID", "p_align must be a power of two and at least the page size")
            if (header.p_vaddr - header.p_offset) % header.p_align != 0:
                _fail("ELF_ALIGN_INVALID", "ELF congruence rule violated")


# =================================================================================================
# EM-8 .. EM-10, EM-15: EFFECTIVE PAGE MAPPING
# =================================================================================================


def effective_intervals(program_headers, page_size):
    """Page-round every PT_LOAD into a half-open interval.  Empty when p_memsz is zero."""
    intervals = []
    for header in program_headers:
        if header.p_type != PT_LOAD or header.p_memsz == 0:
            continue
        start = (header.p_vaddr // page_size) * page_size
        end = -(-(header.p_vaddr + header.p_memsz) // page_size) * page_size
        intervals.append((start, end, header))
    return intervals


def check_effective_mapping(program_headers, page_size):
    """EM-8, EM-9 and EM-15.

    WORDING, EXACT (V9 29.4 EM-8, the V9-10 leg C correction): the property proven here is that
    VIRTUAL-PAGE OVERLAP BETWEEN PT_LOAD SEGMENTS, AND THEREFORE EFFECTIVE-PAGE ALIASING WITHIN THE
    FROZEN ELF MAPPING MODEL, IS PROHIBITED.  No claim whatsoever is made about filesystem-level
    aliasing, storage-level aliasing, page-cache sharing between processes, or any mapping created
    after load by a mechanism outside this model.  Those are out of scope for the mapping model and
    are not proven here.
    """
    intervals = effective_intervals(program_headers, page_size)
    aggregate = 0
    for start, end, header in intervals:
        span = end - start
        if span > MAX_PT_LOAD_EFFECTIVE_BYTES:
            _fail("ELF_MEMORY_CEILING_EXCEEDED", "per-segment page-rounded p_memsz")
        aggregate += span
        # EM-9, stated separately from EM-8 so removing EM-8 later cannot silently remove it.
        if (header.p_flags & PF_W) != 0 and (header.p_flags & PF_X) != 0:
            _fail("EFFECTIVE_WX_PAGE", "segment " + str(header.index))
    if aggregate > MAX_AGGREGATE_EFFECTIVE_BYTES:
        _fail("ELF_MEMORY_CEILING_EXCEEDED", "aggregate page-rounded p_memsz")

    for left_index in range(len(intervals)):
        for right_index in range(left_index + 1, len(intervals)):
            a_start, a_end, a_header = intervals[left_index]
            b_start, b_end, b_header = intervals[right_index]
            if a_start < b_end and b_start < a_end:
                _fail("PT_LOAD_EFFECTIVE_PAGE_OVERLAP", str(a_header.index) + "/" + str(b_header.index))
            union_flags = a_header.p_flags | b_header.p_flags
            if (union_flags & PF_W) != 0 and (union_flags & PF_X) != 0 and a_start < b_end and b_start < a_end:
                _fail("EFFECTIVE_WX_PAGE", "union of overlapping segments")
    return aggregate


def check_rlimit_as_relation(aggregate):
    """EM-16.  The relation is checked against the ACTUAL candidate, at qualification time."""
    if aggregate + STACK_RESERVE_BYTES >= RLIMIT_AS_BYTES:
        _fail("RLIMIT_AS_INSUFFICIENT", str(aggregate))
    return RLIMIT_AS_BYTES


# =================================================================================================
# EM-11: EXACT EXPECTED PROGRAM-HEADER INVENTORY
# =================================================================================================


def check_phdr_inventory(program_headers, expected_inventory):
    for header in program_headers:
        if header.p_type in ALWAYS_FORBIDDEN_PHDR_TYPES:
            _fail("DYNAMIC_SURFACE_PRESENT", header.type_name())

    observed = sorted((header.p_type, header.p_flags, header.p_align) for header in program_headers)
    expected = sorted(expected_inventory)
    if observed != expected:
        _fail(
            "PHDR_INVENTORY_MISMATCH",
            canonical_phdr_inventory(observed) + " != " + canonical_phdr_inventory(expected),
        )

    loads = [header for header in program_headers if header.p_type == PT_LOAD]
    addresses = [header.p_vaddr for header in loads]
    if addresses != sorted(addresses):
        _fail("PHDR_INVENTORY_MISMATCH", "PT_LOAD entries are not in ascending p_vaddr order")

    stack = [header for header in program_headers if header.p_type == PT_GNU_STACK]
    # An OMITTED PT_GNU_STACK is FAIL, never an implicit pass (V9 29.1).
    if len(stack) != 1:
        _fail("PT_GNU_STACK_MISSING", str(len(stack)))
    if (stack[0].p_flags & PF_X) != 0:
        _fail("EXECUTABLE_STACK_PRESENT")


# =================================================================================================
# 29.6: CHECKED VA -> FILE OFFSET TRANSLATION WITH COMPLETE FILE-BACKED CONTAINMENT
# =================================================================================================


def translate_symbol(data, program_headers, symbol_va, symbol_size):
    """T-1 .. T-5.  Every step is CHECKED; nothing is assumed and no decoy offset is consulted."""
    if symbol_size <= 0:
        _fail("SYMBOL_SIZE_INVALID", str(symbol_size))
    if symbol_va < 0 or symbol_va >= 2**64:
        _fail("ELF_RANGE_INVALID", "symbol virtual address")
    # T-3 overflow guard, computed unbounded.
    if symbol_va + symbol_size >= 2**64:
        _fail("ELF_RANGE_INVALID", "symbol_va + symbol_size overflows")

    containing = [
        header
        for header in program_headers
        if header.p_type == PT_LOAD and header.p_vaddr <= symbol_va < header.p_vaddr + header.p_memsz
    ]
    if not containing:
        _fail("SYMBOL_NO_CONTAINING_SEGMENT", str(symbol_va))
    if len(containing) > 1:
        _fail("SYMBOL_AMBIGUOUS_CONTAINING_SEGMENT", str(symbol_va))
    segment = containing[0]

    # T-2.
    segment_relative = symbol_va - segment.p_vaddr
    if segment_relative < 0:
        _fail("ELF_RANGE_INVALID", "negative segment-relative offset")

    # T-3: the COMPLETE object range must lie inside the FILE-BACKED range, not merely inside
    # p_memsz.  An object in the p_memsz-beyond-p_filesz tail is BSS/NOBITS-backed, has no bytes in
    # the file, and cannot be verified from the file at all.
    if symbol_va + symbol_size > segment.p_vaddr + segment.p_filesz:
        _fail("SYMBOL_NOT_FILE_BACKED", str(symbol_va))

    # T-4.
    file_offset = segment.p_offset + segment_relative
    if file_offset + symbol_size > len(data):
        _fail("ELF_RANGE_INVALID", "file offset range exceeds the file length")

    # T-5: the bytes are read from THAT offset.  There is no second translation and no alternative
    # offset source; an offset advertised anywhere else in the image is never consulted.
    return segment, file_offset, bytes(_read(data, file_offset, symbol_size))


def require_non_writable_file_backed(segment):
    if (segment.p_flags & PF_W) != 0:
        _fail("FILTER_OBJECT_WRITABLE_PLACEMENT", "segment " + str(segment.index))


# =================================================================================================
# SYMBOL TABLE
# =================================================================================================


def parse_symbols(data, section_headers):
    symbol_tables = [section for section in section_headers if section.sh_type == SHT_SYMTAB]
    if len(symbol_tables) != 1:
        _fail("ELF_SYMTAB_INVALID", str(len(symbol_tables)))
    table = symbol_tables[0]
    if table.sh_entsize != 24:
        _fail("ELF_SYMTAB_INVALID", "entry size")
    if table.sh_link >= len(section_headers):
        _fail("ELF_SYMTAB_INVALID", "string table link")
    strings = section_headers[table.sh_link]
    if strings.sh_type != SHT_STRTAB:
        _fail("ELF_SYMTAB_INVALID", "string table type")
    string_blob = _read(data, strings.sh_offset, strings.sh_size)

    count = table.sh_size // 24
    if table.sh_size % 24 != 0:
        _fail("ELF_SYMTAB_INVALID", "size is not a multiple of the entry size")
    symbols = []
    for index in range(count):
        offset = table.sh_offset + index * 24
        name_offset = _u32(data, offset + 0)
        info = data[offset + 4]
        other = data[offset + 5]
        shndx = _u16(data, offset + 6)
        value = _u64(data, offset + 8)
        size = _u64(data, offset + 16)
        name = _read_cstring(string_blob, name_offset) if name_offset else ""
        symbols.append(Symbol(name, info, other, shndx, value, size, name_offset))
    return symbols


# =================================================================================================
# COMPLETE UNDEFINED-SYMBOL CLOSURE (repair 8B).
#
# Rejecting a handful of NAMED forbidden undefined symbols proves nothing about the one nobody
# thought to name.  The candidate is linked -static -nostdlib -nostartfiles -Wl,-z,defs into a fully
# resolved ET_EXEC, so the approved undefined-symbol inventory is EMPTY.  Any undefined symbol at
# all -- whatever it is called -- means the image is not the closed static object this
# qualification describes.
#
# The empty tuple is the contract, stated explicitly rather than implied by an absent check.
# =================================================================================================

APPROVED_UNDEFINED_SYMBOLS = ()


def check_undefined_symbol_closure(symbols):
    """The final static worker may contain ONLY the approved undefined-symbol inventory.

    EVERY symbol-table ENTRY is examined, by INDEX (repair 9B).  The previous set-of-names form had
    two ways to lose an entry: an anonymous undefined symbol has an empty name and was filtered out
    by the truthiness test, and two undefined entries sharing a name collapsed into one.  A symbol
    table is a LIST, and an undefined entry is undefined whatever it is or is not called, so the
    scan below indexes the list and never builds a name-keyed collection.

    Entry 0 is the reserved null entry, which is STN_UNDEF by definition and is the one entry that
    is not a symbol at all; it is skipped explicitly rather than by accident.
    """
    approved = set(APPROVED_UNDEFINED_SYMBOLS)
    offending = []
    for index, symbol in enumerate(symbols):
        if index == 0:
            # REPAIR 14: the reserved null entry has ONE canonical ELF64 shape and EVERY field of it
            # is checked, st_shndx included.  A null entry whose section index is not SHN_UNDEF is a
            # malformed symbol table, and accepting it would mean the very first entry of the table
            # the closure scan walks was never validated at all.
            if symbol.name_offset != 0:
                _fail("ELF_NULL_SYMBOL_ENTRY_INVALID", "st_name")
            if symbol.info != 0:
                _fail("ELF_NULL_SYMBOL_ENTRY_INVALID", "st_info")
            if symbol.other != 0:
                _fail("ELF_NULL_SYMBOL_ENTRY_INVALID", "st_other")
            if symbol.shndx != SHN_UNDEF:
                _fail("ELF_NULL_SYMBOL_ENTRY_INVALID", "st_shndx")
            if symbol.value != 0:
                _fail("ELF_NULL_SYMBOL_ENTRY_INVALID", "st_value")
            if symbol.size != 0:
                _fail("ELF_NULL_SYMBOL_ENTRY_INVALID", "st_size")
            continue
        if symbol.shndx != SHN_UNDEF:
            continue
        if symbol.name in approved:
            continue
        offending.append(str(index) + ":" + (symbol.name or "<anonymous>"))
    if offending:
        _fail("UNDEFINED_SYMBOL_CLOSURE_VIOLATED", ",".join(offending))
    return [symbol.name for symbol in symbols if symbol.shndx == SHN_UNDEF and symbol.name in approved]


def check_declared_section_containment(symbol, section_headers, program_headers, data, marker):
    """Repair 9A.  SYMBOL RANGE subset-of DECLARED SECTION subset-of APPROVED LOAD MAPPING.

    A virtual address that merely lands inside SOME PT_LOAD proves nothing about which object the
    symbol actually is.  st_shndx NAMES the defining section, and a symbol whose address sits in a
    different section than the one it declares is describing an object that is not there.  The
    three-level containment below is checked in that exact order, so a mismatch is reported at the
    level it actually occurs.
    """
    index = symbol.shndx
    if index == SHN_UNDEF:
        _fail(marker, "SHN_UNDEF")
    if index >= SHN_LORESERVE:
        # SHN_LORESERVE .. SHN_HIRESERVE are reserved; SHN_ABS and SHN_COMMON live in that range and
        # neither denotes a real containing section.
        _fail(marker, "reserved section index " + str(index))
    if index >= len(section_headers):
        _fail(marker, "section index out of range " + str(index))
    section = section_headers[index]

    if section.sh_type == SHT_NULL:
        _fail(marker, "declared section is SHT_NULL")
    if not section.sh_flags & SHF_ALLOC:
        # A non-allocated section is not mapped at run time, so no live object can live in it.
        _fail(marker, "declared section is not SHF_ALLOC")
    if symbol.size <= 0:
        _fail("SYMBOL_SIZE_INVALID", str(symbol.size))
    if symbol.value < section.sh_addr or symbol.value + symbol.size > section.sh_addr + section.sh_size:
        _fail(marker, "symbol range escapes its declared section")

    # A file-backed section must contain the symbol's file bytes as well as its addresses.  SHT_NOBITS
    # occupies no file range at all, which is why a governed object may never be declared in one.
    if section.sh_type == SHT_NOBITS:
        _fail(marker, "declared section is SHT_NOBITS")
    file_start = section.sh_offset + (symbol.value - section.sh_addr)
    if file_start < section.sh_offset or file_start + symbol.size > section.sh_offset + section.sh_size:
        _fail(marker, "symbol bytes escape the declared section file extent")
    if file_start + symbol.size > len(data):
        _fail(marker, "symbol bytes escape the image")

    # And the declared section itself must live inside exactly one approved PT_LOAD mapping.
    containing = [
        header
        for header in program_headers
        if header.p_type == PT_LOAD
        and header.p_vaddr <= section.sh_addr
        and section.sh_addr + section.sh_size <= header.p_vaddr + header.p_filesz
    ]
    if len(containing) != 1:
        _fail(marker, "declared section is not inside exactly one file-backed PT_LOAD")
    segment = containing[0]

    # REPAIR 13: THE FILE OFFSET IS DERIVED TWICE, INDEPENDENTLY, AND THE TWO MUST AGREE.
    #
    # A single derivation cannot see a shift in the field it does not use: adding four to sh_offset
    # moves only the section-derived answer, and adding four to p_offset moves only the
    # segment-derived one.  Requiring equality catches either on its own, and requiring the section
    # to sit at the same relative position in both views catches a shift applied to both.
    segment_derived = segment.p_offset + (symbol.value - segment.p_vaddr)
    if segment_derived != file_start:
        _fail("SYMBOL_FILE_OFFSET_DERIVATION_DISAGREEMENT", str(file_start) + " != " + str(segment_derived))
    if section.sh_offset - segment.p_offset != section.sh_addr - segment.p_vaddr:
        _fail("SYMBOL_FILE_OFFSET_DERIVATION_DISAGREEMENT", "section within mapping")
    if file_start + symbol.size > segment.p_offset + segment.p_filesz:
        _fail(marker, "symbol bytes escape the mapping file extent")
    return section, segment, file_start


def require_single_definition(symbols, name):
    """Q1, Q2, Q6 and Q8 for one governed symbol name.

    Q2 REJECTS STB_WEAK outright, which is the hazard it names: a weak definition is overridable and
    a weak-only definition would let a different object silently win.  SHN_UNDEF and SHN_COMMON are
    rejected by Q6.  The BINDING and VISIBILITY of the governed capability object are checked
    exactly, by the caller, against the frozen authority -- see check_capability_identity.
    """
    matches = [symbol for symbol in symbols if symbol.name == name]
    definitions = [symbol for symbol in matches if symbol.shndx not in (SHN_UNDEF, SHN_COMMON)]
    undefined = [symbol for symbol in matches if symbol.shndx == SHN_UNDEF]
    common = [symbol for symbol in matches if symbol.shndx == SHN_COMMON]

    if common:
        _fail("BLST_CAP_COMMON" if name == BLST_PLATFORM_CAP_SYMBOL else "SYMBOL_COMMON", name)
    if not definitions:
        _fail("BLST_CAP_UNDEFINED" if name == BLST_PLATFORM_CAP_SYMBOL else "SYMBOL_UNDEFINED", name)
    if len(definitions) > 1:
        _fail("BLST_CAP_MULTIPLE" if name == BLST_PLATFORM_CAP_SYMBOL else "SYMBOL_MULTIPLE", name)
    if undefined:
        _fail("SYMBOL_RESIDUAL_UNDEFINED_REFERENCE", name)

    symbol = definitions[0]
    if symbol.binding() == STB_WEAK:
        _fail("BLST_CAP_WEAK" if name == BLST_PLATFORM_CAP_SYMBOL else "SYMBOL_WEAK", name)
    if symbol.binding() not in (STB_GLOBAL, STB_LOCAL):
        _fail("SYMBOL_BINDING_INVALID", name)
    if symbol.visibility() not in (STV_HIDDEN, STV_INTERNAL):
        _fail("BLST_CAP_VISIBILITY" if name == BLST_PLATFORM_CAP_SYMBOL else "SYMBOL_VISIBILITY", name)
    return symbol


# =================================================================================================
# THE EXACT __blst_platform_cap IDENTITY (repair 8C).
#
# The governed authority is EXACT and is asserted here rather than inside the shared helper, so that
# the general rule for internal filter objects is not silently widened by the capability object's
# stricter contract.
#
#   binding    STB_GLOBAL   -- NOT STB_LOCAL.  A lowered binding is not accepted "because a linker
#                              may lower it": the approved contract names the binding the final
#                              image must carry, and an image that does not carry it is not the
#                              approved image.  A pinned-toolchain contradiction here is an
#                              UNRESOLVED finding that returns to architecture with the observed
#                              value, never a widened verifier.
#   visibility STV_HIDDEN   -- NOT STV_INTERNAL, which carries additional reference restrictions and
#                              is a different object contract.
#   type       STT_OBJECT   -- a data object, never a function or a notype placeholder.
#   section    defined      -- a real, in-range, non-reserved section index (see 8D).
# =================================================================================================

BLST_PLATFORM_CAP_BINDING_REQUIRED = STB_GLOBAL
BLST_PLATFORM_CAP_VISIBILITY_REQUIRED = STV_HIDDEN
BLST_PLATFORM_CAP_TYPE_REQUIRED = STT_OBJECT


def check_capability_identity(symbol, section_headers):
    """Q2..Q9 for the governed capability object, at EXACT identity.

    The three-level range containment is proven separately by
    check_declared_section_containment, which the caller runs first; this function owns the
    symbol's IDENTITY, so widening one can never quietly widen the other.
    """
    del section_headers
    if symbol.binding() != BLST_PLATFORM_CAP_BINDING_REQUIRED:
        _fail("BLST_CAP_BINDING", str(symbol.binding()))
    if symbol.visibility() != BLST_PLATFORM_CAP_VISIBILITY_REQUIRED:
        _fail("BLST_CAP_VISIBILITY", str(symbol.visibility()))
    if symbol.symbol_type() != BLST_PLATFORM_CAP_TYPE_REQUIRED:
        _fail("BLST_CAP_TYPE", str(symbol.symbol_type()))
    return symbol


# =================================================================================================
# SECTION POLICY
# =================================================================================================


def check_sections(section_headers):
    """No dynamic surface, no relocation requiring runtime fixup, no constructors."""
    for section in section_headers:
        if section.sh_type in (SHT_DYNAMIC, SHT_DYNSYM):
            _fail("DYNAMIC_SURFACE_PRESENT", section.name or str(section.sh_type))
        if section.name in (".dynamic", ".dynsym", ".dynstr", ".interp", ".gnu.hash", ".hash"):
            _fail("DYNAMIC_SURFACE_PRESENT", section.name)
        if section.sh_type in (SHT_RELA, SHT_REL) and section.sh_size > 0:
            # A static non-PIE image resolves everything at link time; a populated relocation
            # section means a runtime fixup would be required, which V9 29.1 forbids.
            _fail("RUNTIME_RELOCATION_PRESENT", section.name or str(section.sh_type))
        if section.sh_type in (SHT_INIT_ARRAY, SHT_FINI_ARRAY) and section.sh_size > 0:
            _fail("CONSTRUCTOR_PRESENT", section.name or str(section.sh_type))
        if section.name in (".init_array", ".fini_array", ".ctors", ".dtors") and section.sh_size > 0:
            _fail("CONSTRUCTOR_PRESENT", section.name)
        if section.name in (".tdata", ".tbss") and section.sh_size > 0:
            _fail("UNEXPECTED_TLS", section.name)


def scan_for_cpuid(data, program_headers):
    """Q9 corroboration: the two-byte cpuid opcode must not appear in executable, file-backed text.

    HONEST LIMITATION, stated rather than hidden: a byte-level scan cannot distinguish an
    INSTRUCTION from operand or literal bytes that happen to carry the same pair.  The scan is
    therefore a corroboration of the STRUCTURAL property that -D__BLST_NO_CPUID__ removes the only
    upstream translation unit that emits cpuid.  A hit is a HARD FAILURE that returns to the
    controller for investigation; it is never resolved by relaxing the scan, and the absence of a
    hit is never treated as a stronger claim than "the pattern does not occur".
    """
    for header in program_headers:
        if header.p_type != PT_LOAD or (header.p_flags & PF_X) == 0 or header.p_filesz == 0:
            continue
        blob = _read(data, header.p_offset, header.p_filesz)
        if b"\x0f\xa2" in blob:
            _fail("BLST_CPUID_PRESENT", "segment " + str(header.index))


# =================================================================================================
# ENTRY POINT
# =================================================================================================


def check_entry_point(data, program_headers, symbols, e_entry):
    """EM-10 plus the project-owned entry point requirement of V9 29.1."""
    executable = [
        header
        for header in program_headers
        if header.p_type == PT_LOAD
        and (header.p_flags & PF_X) != 0
        and header.p_vaddr <= e_entry < header.p_vaddr + header.p_filesz
    ]
    if len(executable) != 1:
        _fail("ENTRY_POINT_NOT_IN_EXECUTABLE_SEGMENT", str(e_entry))
    entry_symbol = require_single_definition(symbols, ENTRY_SYMBOL)
    if entry_symbol.value != e_entry:
        _fail("ENTRY_POINT_NOT_PROJECT_OWNED", str(e_entry))
    for forbidden in ("__libc_start_main", "__libc_csu_init", "_dl_start", "__libc_init_first"):
        if any(symbol.name == forbidden for symbol in symbols):
            _fail("ENTRY_POINT_NOT_PROJECT_OWNED", forbidden)
    del data
    return executable[0]


# =================================================================================================
# THE QUALIFICATION
# =================================================================================================


def qualify(data, page_size, expected_inventory_text, compile_dependency_digest):
    if page_size != PAGE_SIZE_REQUIRED:
        # The effective-mapping analysis is only sound for the page size actually in use.
        _fail("ENVIRONMENT_PAGE_SIZE_INCOMPATIBLE", str(page_size))
    if expected_inventory_text != canonical_phdr_inventory(EXPECTED_PHDR_INVENTORY):
        # Two independent NON-CANDIDATE authorities must agree: the literal committed in this
        # reviewed source and the literal pinned on the trusted Stage-C surface.
        _fail("PHDR_INVENTORY_AUTHORITY_DISAGREEMENT", expected_inventory_text)

    parsed = parse_elf(data)
    program_headers = parsed["program_headers"]
    section_headers = parsed["section_headers"]

    check_program_header_ranges(data, program_headers, page_size)
    # The effective-mapping analysis runs BEFORE the inventory comparison so that a writable
    # executable page is reported as EFFECTIVE_WX_PAGE -- the precise defect -- rather than being
    # masked by the flag-value mismatch it also happens to produce.  EM-9 is stated separately from
    # EM-8 for the same reason: removing one must never silently remove the other.
    aggregate = check_effective_mapping(program_headers, page_size)
    check_phdr_inventory(program_headers, EXPECTED_PHDR_INVENTORY)
    rlimit_as = check_rlimit_as_relation(aggregate)
    check_sections(section_headers)
    scan_for_cpuid(data, program_headers)

    symbols = parse_symbols(data, section_headers)
    # Repair 8B: the closure runs before any named-symbol rule, so an unrelated undefined symbol is
    # reported as the closure violation it is rather than surviving because nothing asked about it.
    check_undefined_symbol_closure(symbols)
    check_entry_point(data, program_headers, symbols, parsed["e_entry"])

    # SECTION 30 Q1..Q9 for __blst_platform_cap.
    cap_symbol = require_single_definition(symbols, BLST_PLATFORM_CAP_SYMBOL)
    cap_section, cap_load, cap_section_offset = check_declared_section_containment(
        cap_symbol, section_headers, program_headers, data, "BLST_CAP_SECTION_INDEX_INVALID"
    )
    check_capability_identity(cap_symbol, section_headers)
    if cap_symbol.size != BLST_PLATFORM_CAP_SIZE_BYTES:
        _fail("BLST_CAP_SIZE", str(cap_symbol.size) + " != " + str(BLST_PLATFORM_CAP_SIZE_BYTES))
    cap_segment, cap_offset, cap_bytes = translate_symbol(
        data, program_headers, cap_symbol.value, BLST_PLATFORM_CAP_SIZE_BYTES
    )
    if (cap_segment.p_flags & PF_W) != 0:
        _fail("BLST_CAP_WRITABLE", "segment " + str(cap_segment.index))
    if cap_bytes != BLST_PLATFORM_CAP_VALUE_BYTES:
        _fail("BLST_CAP_VALUE", cap_bytes.hex())

    # SECTION 29.6 Q10 for the canonical internal filter objects.
    fprog_symbol = require_single_definition(symbols, INTERNAL_FPROG_SYMBOL)
    fprog_section, fprog_load, fprog_section_offset = check_declared_section_containment(
        fprog_symbol, section_headers, program_headers, data, "FILTER_OBJECT_SECTION_INDEX_INVALID"
    )
    if fprog_symbol.size != INTERNAL_FPROG_SIZE_BYTES:
        _fail("FILTER_OBJECT_SIZE_INVALID", INTERNAL_FPROG_SYMBOL)
    fprog_segment, fprog_offset, fprog_bytes = translate_symbol(
        data, program_headers, fprog_symbol.value, INTERNAL_FPROG_SIZE_BYTES
    )
    require_non_writable_file_backed(fprog_segment)

    program_symbol = require_single_definition(symbols, INTERNAL_PROGRAM_SYMBOL)
    program_section, program_load, program_section_offset = check_declared_section_containment(
        program_symbol, section_headers, program_headers, data, "FILTER_OBJECT_SECTION_INDEX_INVALID"
    )
    if program_symbol.size != INTERNAL_PROGRAM_SIZE_BYTES:
        _fail("FILTER_OBJECT_SIZE_INVALID", INTERNAL_PROGRAM_SYMBOL)
    program_segment, program_offset, program_bytes = translate_symbol(
        data, program_headers, program_symbol.value, INTERNAL_PROGRAM_SIZE_BYTES
    )
    require_non_writable_file_backed(program_segment)

    # The fprog must reference EXACTLY the in-image array, at its link-time-fixed address.  This is
    # what makes leg L1 of V9 15.2 sound: the register-observed uargs address is compared against a
    # value derived from a static parse of the SAME digest-proven bytes.
    declared_length = int.from_bytes(fprog_bytes[0:2], "little")
    declared_filter_va = int.from_bytes(fprog_bytes[8:16], "little")
    if declared_length != INTERNAL_PROGRAM_INSTRUCTIONS:
        _fail("FILTER_OBJECT_LENGTH_INVALID", str(declared_length))
    if declared_filter_va != program_symbol.value:
        _fail("FILTER_OBJECT_POINTER_INVALID", str(declared_filter_va))

    record = {
        "schema": ELF_RECORD_SCHEMA,
        "platform_id": PLATFORM_ID,
        "candidate_binary_sha256": hashlib.sha256(data).hexdigest(),
        "candidate_binary_bytes": len(data),
        # Echoed from the A1 build manifest.  V9 SECTION 7 places this digest on A1, A2 and A4,
        # because it describes how the ARTIFACT was produced rather than the qualification
        # environment, so it rides with the manifest that is already bound to the binary.
        "compile_dependency_inventory_digest_sha256": compile_dependency_digest,
        "page_size": page_size,
        "elf": {
            "type": "ET_EXEC",
            "machine": "EM_X86_64",
            "class": "ELFCLASS64",
            "endianness": "ELFDATA2LSB",
            "entry_va_u64": parsed["e_entry"],
            "entry_symbol": ENTRY_SYMBOL,
            "program_header_count": parsed["e_phnum"],
            "section_header_count": parsed["e_shnum"],
        },
        "expected_phdr_inventory_schema": EXPECTED_PHDR_SCHEMA,
        "expected_phdr_inventory": canonical_phdr_inventory(EXPECTED_PHDR_INVENTORY),
        "observed_phdr_inventory": canonical_phdr_inventory(
            sorted((header.p_type, header.p_flags, header.p_align) for header in program_headers)
        ),
        "program_headers": [
            {
                "index": header.index,
                "type": header.type_name(),
                "flags_u32": header.p_flags,
                "offset_u64": header.p_offset,
                "vaddr_u64": header.p_vaddr,
                "filesz_u64": header.p_filesz,
                "memsz_u64": header.p_memsz,
                "align_u64": header.p_align,
            }
            for header in program_headers
        ],
        # The section table travels with A2 so the trusted surface can see what the producer
        # claims about section geometry; Stage C re-derives the governed parts from the bytes.
        "sections": [
            {
                "index": section.index,
                "name": section.name,
                "type_u32": section.sh_type,
                "flags_u64": section.sh_flags,
                "addr_u64": section.sh_addr,
                "offset_u64": section.sh_offset,
                "size_bytes": section.sh_size,
            }
            for section in section_headers
        ],
        "memory": {
            "aggregate_effective_bytes": aggregate,
            "max_pt_load_effective_bytes": MAX_PT_LOAD_EFFECTIVE_BYTES,
            "max_aggregate_effective_bytes": MAX_AGGREGATE_EFFECTIVE_BYTES,
            "stack_reserve_bytes": STACK_RESERVE_BYTES,
            "governed_headroom_bytes": GOVERNED_HEADROOM_BYTES,
            "rlimit_as_bytes": rlimit_as,
        },
        "blst_platform_cap": {
            "symbol": BLST_PLATFORM_CAP_SYMBOL,
            "governed_size_bytes": BLST_PLATFORM_CAP_SIZE_BYTES,
            "observed_size_bytes": cap_symbol.size,
            "va_u64": cap_symbol.value,
            "file_offset_u64": cap_offset,
            "value_hex": cap_bytes.hex(),
            "segment_flags_u32": cap_segment.p_flags,
            "size_authority": "APPROVED_SOURCE_BUILD_CONTRACT_BUNDLE_ENTRY_2",
            "binding": "STB_GLOBAL",
            "visibility": "STV_HIDDEN",
            "symbol_type": "STT_OBJECT",
            "section_index": cap_symbol.shndx,
            "section_name": cap_section.name,
            "section_addr_u64": cap_section.sh_addr,
            "section_size_bytes": cap_section.sh_size,
            "section_file_offset_u64": cap_section.sh_offset,
            "section_type_u32": cap_section.sh_type,
            "section_flags_u64": cap_section.sh_flags,
            "section_file_offset_of_symbol_u64": cap_section_offset,
            "load_index": cap_load.index,
            "load_vaddr_u64": cap_load.p_vaddr,
            "load_filesz_u64": cap_load.p_filesz,
            "load_memsz_u64": cap_load.p_memsz,
            "load_file_offset_u64": cap_load.p_offset,
            "load_flags_u32": cap_load.p_flags,
        },
        # REPAIR 1A: the COMPLETE authenticated coordinates of both governed filter objects.
        #
        # Stage C must be able to re-establish, and cross-check against one another: the symbol
        # identity, the virtual address, the object size, the DECLARED section index and that
        # section's address, size, type, flags and file range, the file offset the object actually
        # occupies, the PT_LOAD that maps it and that segment's own ranges and flags, and the
        # canonical bytes.  A record that carried only an address and a size would leave the object
        # free to choose its own coordinates.
        "canonical_internal_filter_object": {
            "fprog_symbol": INTERNAL_FPROG_SYMBOL,
            "fprog_va_u64": fprog_symbol.value,
            "fprog_file_offset_u64": fprog_offset,
            "fprog_size_bytes": INTERNAL_FPROG_SIZE_BYTES,
            "fprog_segment_flags_u32": fprog_segment.p_flags,
            "fprog_section_index": fprog_symbol.shndx,
            "fprog_section_name": fprog_section.name,
            "fprog_section_addr_u64": fprog_section.sh_addr,
            "fprog_section_size_bytes": fprog_section.sh_size,
            "fprog_section_file_offset_u64": fprog_section.sh_offset,
            "fprog_section_type_u32": fprog_section.sh_type,
            "fprog_section_flags_u64": fprog_section.sh_flags,
            "fprog_section_file_offset_of_symbol_u64": fprog_section_offset,
            "fprog_load_index": fprog_load.index,
            "fprog_load_vaddr_u64": fprog_load.p_vaddr,
            "fprog_load_filesz_u64": fprog_load.p_filesz,
            "fprog_load_file_offset_u64": fprog_load.p_offset,
            "fprog_load_flags_u32": fprog_load.p_flags,
            "fprog_bytes_sha256": hashlib.sha256(fprog_bytes).hexdigest(),
            "program_symbol": INTERNAL_PROGRAM_SYMBOL,
            "program_va_u64": program_symbol.value,
            "program_file_offset_u64": program_offset,
            "program_size_bytes": INTERNAL_PROGRAM_SIZE_BYTES,
            "program_segment_flags_u32": program_segment.p_flags,
            "program_section_index": program_symbol.shndx,
            "program_section_name": program_section.name,
            "program_section_addr_u64": program_section.sh_addr,
            "program_section_size_bytes": program_section.sh_size,
            "program_section_file_offset_u64": program_section.sh_offset,
            "program_section_type_u32": program_section.sh_type,
            "program_section_flags_u64": program_section.sh_flags,
            "program_section_file_offset_of_symbol_u64": program_section_offset,
            "program_load_index": program_load.index,
            "program_load_vaddr_u64": program_load.p_vaddr,
            "program_load_filesz_u64": program_load.p_filesz,
            "program_load_file_offset_u64": program_load.p_offset,
            "program_load_flags_u32": program_load.p_flags,
            "program_instruction_count": declared_length,
            "program_bytes_sha256": hashlib.sha256(program_bytes).hexdigest(),
        },
        "undefined_symbol_closure": {
            "approved_inventory": list(APPROVED_UNDEFINED_SYMBOLS),
            "observed_inventory": [],
            "symbol_table_entry_count": len(symbols),
        },
        "authority_non_transition": {
            "readiness_transition": "NONE",
            "connector_transition": "NONE",
            "product_native_execution": "NO",
            "machine_time_authority": "NONE",
            "stage4_authority": "NONE",
            "evidence_status": "ADMISSION_EVIDENCE_ONLY",
        },
    }
    record["elf_qualification_digest_sha256"] = hashlib.sha256(
        ELF_RECORD_DIGEST_DOMAIN + canonical_json(record)
    ).hexdigest()
    return record


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
        "utf-8"
    )


# =================================================================================================
# EMIT THE INTERNAL FILTER ADDRESS FOR THE OBSERVER (repair for BUILD_TO_PROVE run 33513591856).
#
# The observer has to read the candidate's internal sock_fprog BEFORE the worker makes itself
# non-dumpable, so it needs that object's link-time address.  The address may only come from THIS
# qualifier's own record for the SAME digest-proven image -- never from the candidate at runtime and
# never as a durable constant, because it belongs to exactly one binary.
#
# Everything asserted here is a precondition of the observation being sound:
#   * the record is this qualifier's schema, and speaks for the governed candidate digest;
#   * both objects carry the canonical symbol names;
#   * both objects live in a NON-WRITABLE load segment, which is what makes the bytes read before
#     the install necessarily the bytes submitted to it.
# Any failure exits non-zero and emits nothing: the observer then has no address and cannot run.
# =================================================================================================

INTERNAL_FPROG_SYMBOL = "mt4_s3c_internal_filter_fprog"
INTERNAL_PROGRAM_SYMBOL = "mt4_s3c_internal_filter_program"


def emit_internal_fprog_va(record_path, expected_candidate_sha256, env_path):
    """Bind the ELF-qualified internal fprog address to one exact candidate and emit it."""
    with open(record_path, "rb") as handle:
        record = json.loads(handle.read().decode("utf-8"))
    if record.get("schema") != ELF_RECORD_SCHEMA:
        _fail("ELF_RECORD_SCHEMA_UNEXPECTED", str(record.get("schema")))
    if record.get("candidate_binary_sha256") != expected_candidate_sha256:
        _fail("ELF_RECORD_CANDIDATE_MISMATCH", str(record.get("candidate_binary_sha256")))
    filter_object = record.get("canonical_internal_filter_object")
    if not isinstance(filter_object, dict):
        _fail("ELF_RECORD_FILTER_OBJECT_MISSING")
    if filter_object.get("fprog_symbol") != INTERNAL_FPROG_SYMBOL:
        _fail("ELF_FPROG_SYMBOL_UNEXPECTED", str(filter_object.get("fprog_symbol")))
    if filter_object.get("program_symbol") != INTERNAL_PROGRAM_SYMBOL:
        _fail("ELF_PROGRAM_SYMBOL_UNEXPECTED", str(filter_object.get("program_symbol")))
    for key in ("fprog_load_flags_u32", "program_load_flags_u32"):
        flags = filter_object.get(key)
        if not isinstance(flags, int) or (flags & PF_W) != 0:
            _fail("ELF_FILTER_MAPPING_IS_WRITABLE", key + "=" + str(flags))
    address = filter_object.get("fprog_va_u64")
    if not isinstance(address, int) or address <= 0:
        _fail("ELF_FPROG_VA_INVALID", str(address))
    program_address = filter_object.get("program_va_u64")
    if not isinstance(program_address, int) or program_address <= 0:
        _fail("ELF_PROGRAM_VA_INVALID", str(program_address))
    with open(env_path, "a", encoding="utf-8") as handle:
        handle.write("S3C_INTERNAL_FPROG_VA=" + str(address) + "\n")
    sys.stdout.write("MT4_S3C_INTERNAL_FPROG_VA=" + str(address) + "\n")
    return 0


def main(argv=None):
    # The emit mode consumes an ALREADY-PRODUCED record and qualifies nothing itself, so it does not
    # take the qualification inputs.  It is handled before the strict parser rather than by making
    # those inputs conditionally optional.
    source = sys.argv[1:] if argv is None else list(argv)
    if "--emit-internal-fprog-va" in source:
        emitter = argparse.ArgumentParser(description="MT4-S3C internal filter address emitter")
        emitter.add_argument("--emit-internal-fprog-va", required=True, help="path to the ELF qualification record")
        emitter.add_argument("--expected-candidate-sha256", required=True, help="the governed candidate digest")
        emitter.add_argument("--emit-env", required=True, help="path of the environment file to append to")
        emitted = emitter.parse_args(source)
        return emit_internal_fprog_va(
            emitted.emit_internal_fprog_va, emitted.expected_candidate_sha256, emitted.emit_env
        )

    parser = argparse.ArgumentParser(description="MT4-S3C static ELF qualifier (zero execution)")
    parser.add_argument("--candidate", required=True, help="absolute path to the candidate binary")
    parser.add_argument(
        "--page-size",
        type=int,
        default=None,
        help="page size; omitted means read it directly from the pinned qualification environment",
    )
    parser.add_argument("--expected-phdr-inventory", required=True, help="the trusted-surface literal inventory")
    parser.add_argument(
        "--compile-dependency-inventory-digest",
        required=True,
        help="the A1 manifest's compile dependency inventory digest, echoed into A2",
    )
    parser.add_argument("--out", required=True, help="absolute path of the ELF qualification record")
    args = parser.parse_args(argv)

    # PAGE_SIZE comes from the PINNED qualification environment at qualification time, never
    # hard-coded and never inferred from the binary.  Reading it here rather than through a shell
    # substitution also keeps the workflow command grammar free of command substitution (V9 28.3).
    page_size = args.page_size if args.page_size is not None else os.sysconf("SC_PAGESIZE")
    with open(args.candidate, "rb") as handle:
        data = handle.read()
    digest = args.compile_dependency_inventory_digest
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        _fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", digest)
    record = qualify(data, page_size, args.expected_phdr_inventory, digest)
    with open(args.out, "wb") as handle:
        handle.write(canonical_json(record))
    sys.stdout.write("MT4_S3C_ELF_QUALIFICATION_DIGEST=" + record["elf_qualification_digest_sha256"] + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
