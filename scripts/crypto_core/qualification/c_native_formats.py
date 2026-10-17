"""Bounded x64 shared-image inspection, before any candidate code executes.

Qualification only. An inventory is neither provenance nor source/binary admission.
Unsupported ELF/PE features fail closed rather than being silently omitted.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAX_IMAGE = 64 * 1024 * 1024


class QualificationError(ValueError):
    """An explicit qualification rejection, including malformed input."""


@dataclass(frozen=True)
class Image:
    platform: str
    exports: tuple
    dependencies: tuple
    soname: str = ""


def region(data, offset, length):
    if offset < 0 or length < 0 or offset + length > len(data):
        raise QualificationError("IMAGE_BOUNDS")
    return data[offset : offset + length]


def unpack(fmt, data, offset):
    return struct.unpack(fmt, region(data, offset, struct.calcsize(fmt)))


def cstring(data, offset):
    if not 0 <= offset < len(data):
        raise QualificationError("STRING_BOUNDS")
    end = data.find(b"\0", offset, min(len(data), offset + 4096))
    if end < 0:
        raise QualificationError("STRING_TERMINATOR")
    try:
        return data[offset:end].decode("ascii")
    except UnicodeError as exc:
        raise QualificationError("STRING_ENCODING") from exc


def inspect_image(data, required_exports=(), *, system_baseline=False):
    if type(data) is not bytes or not 64 <= len(data) <= MAX_IMAGE:
        raise QualificationError("IMAGE_TYPE_OR_SIZE")
    try:
        image = _elf(data, system_baseline=system_baseline) if data.startswith(b"\x7fELF") else _pe(data)
    except (struct.error, IndexError, OverflowError) as exc:
        raise QualificationError("MALFORMED_IMAGE") from exc
    if not set(required_exports).issubset(image.exports):
        raise QualificationError("MISSING_EXPORT")
    return image


def _elf(data, *, system_baseline=False):
    if data[:7] != b"\x7fELF\x02\x01\x01" or data[7] not in (0, 3) or any(data[8:16]):
        raise QualificationError("ELF_CLASS_ENDIAN_VERSION")
    kind, machine, version = unpack("<HHI", data, 16)
    if (kind, machine, version) != (3, 62, 1):
        raise QualificationError("ELF_ARCH_OR_ABI")
    phoff, shoff = unpack("<QQ", data, 32)
    flags, ehsize, phsize, phnum, shsize, shnum = unpack("<IHHHHH", data, 48)
    if flags:
        raise QualificationError("ELF_ABI_FLAGS")
    if ehsize != 64 or phsize != 56 or shsize != 64 or not 1 <= phnum <= 128 or not 1 <= shnum <= 4096:
        raise QualificationError("ELF_HEADER")
    loads, file_loads, dynamics, stack = [], [], [], []
    for i in range(phnum):
        t, f, off, va, _, filesz, memsz, align = unpack("<IIQQQQQQ", data, phoff + i * 56)
        region(data, off, filesz)
        if filesz > memsz or memsz > MAX_IMAGE * 4:
            raise QualificationError("ELF_SEGMENT_SIZE")
        if t == 1:
            if f & 3 == 3 or align not in (0, 1, 4096, 2097152) or (align > 1 and off % align != va % align):
                raise QualificationError("ELF_WRITABLE_EXECUTABLE_OR_ALIGNMENT")
            loads.append((va, va + memsz))
            file_loads.append((off, va, filesz, f))
        if t == 2:
            dynamics.append((off, filesz, va))
        if t == 3 and not system_baseline:
            raise QualificationError("ELF_INTERPRETER")
        if t == 0x6474E551:
            stack.append(f)
    if len(dynamics) != 1 or not loads or len(stack) != 1 or stack[0] & 1:
        raise QualificationError("ELF_DYNAMIC_OR_STACK")
    ordered = sorted(loads)
    if any(b[0] < a[1] for a, b in zip(ordered, ordered[1:])):
        raise QualificationError("ELF_OVERLAPPING_LOADS")

    def mapped(address, length):
        choices = [
            (off + address - va, f)
            for off, va, size, f in file_loads
            if va <= address and address + length <= va + size
        ]
        if len(choices) != 1:
            raise QualificationError("ELF_RUNTIME_MAPPING")
        return choices[0]

    sections = [unpack("<IIQQQQIIQQ", data, shoff + i * 64) for i in range(shnum)]
    dynamic = []
    off, length, address = dynamics[0]
    if mapped(address, length)[0] != off:
        raise QualificationError("ELF_DYNAMIC_MAPPING")
    if length % 16:
        raise QualificationError("ELF_DYNAMIC_SIZE")
    for i in range(length // 16):
        tag, value = unpack("<qQ", data, off + i * 16)
        if tag == 0:
            break
        # RPATH/RUNPATH, audit/depaudit, filter/auxiliary and text relocation.
        if tag in (15, 29, 22, 0x6FFFFEFA, 0x6FFFFEFC, 0x6FFFFEFB, 0x7FFFFFFD, 0x7FFFFFFF):
            raise QualificationError("UNTRUSTED_SO_SEARCH_OR_FEATURE")
        if tag == 30 and value & 4:
            raise QualificationError("ELF_TEXT_RELOCATION")
        dynamic.append((tag, value))
    else:
        raise QualificationError("ELF_DYNAMIC_TERMINATOR")
    dynsections = [s for s in sections if s[1] == 6 and s[4:6] == (off, length) and s[3] == address]
    if len(dynsections) != 1:
        raise QualificationError("ELF_DYNAMIC_SECTION_BINDING")
    link = dynsections[0][6]
    if link >= shnum or sections[link][1] != 3:
        raise QualificationError("ELF_STRING_TABLE")
    strings = region(data, sections[link][4], sections[link][5])
    if mapped(sections[link][3], len(strings))[0] != sections[link][4]:
        raise QualificationError("ELF_RUNTIME_STRING_MAPPING")
    # Bind the string table used by the runtime dynamic loader, not just section metadata.
    if [(t, v) for t, v in dynamic if t == 5] != [(5, sections[link][3])] or [
        (t, v) for t, v in dynamic if t == 10
    ] != [(10, len(strings))]:
        raise QualificationError("ELF_RUNTIME_STRING_BINDING")
    deps = tuple(cstring(strings, v) for t, v in dynamic if t == 1)
    names = [cstring(strings, v) for t, v in dynamic if t == 14]
    if len(names) > 1 or any("/" in x or "\\" in x or not x for x in deps + tuple(names)):
        raise QualificationError("ELF_DEPENDENCY_NAME")
    exports = []
    for s in sections:
        if s[1] != 11:
            continue
        if s[9] != 24 or s[5] % 24 or s[6] != link:
            raise QualificationError("ELF_SYMBOL_TABLE")
        if (
            [(t, v) for t, v in dynamic if t == 6] != [(6, s[3])]
            or [(t, v) for t, v in dynamic if t == 11] != [(11, 24)]
            or mapped(s[3], s[5])[0] != s[4]
        ):
            raise QualificationError("ELF_RUNTIME_SYMBOL_BINDING")
        for i in range(s[5] // 24):
            name, info, other, index, value, _ = unpack("<IBBHQQ", data, s[4] + i * 24)
            if info & 15 == 10 and not system_baseline:
                raise QualificationError("ELF_IFUNC_UNSUPPORTED")
            if index and info & 15 == 2 and info >> 4 in (1, 2) and other & 3 == 0:
                if not mapped(value, 1)[1] & 1:
                    raise QualificationError("ELF_NON_EXECUTABLE_EXPORT")
                exports.append(cstring(strings, name))
    return Image("linux-x64", tuple(exports), deps, names[0] if names else "")


def _pe(data):
    if data[:2] != b"MZ":
        raise QualificationError("NATIVE_FORMAT")
    pe = unpack("<I", data, 60)[0]
    if region(data, pe, 4) != b"PE\0\0":
        raise QualificationError("PE_SIGNATURE")
    machine, count, _, _, _, size, flags = unpack("<HHIIIHH", data, pe + 4)
    opt = pe + 24
    if machine != 0x8664 or not flags & 0x2000 or unpack("<H", data, opt)[0] != 0x20B:
        raise QualificationError("PE_ARCH_OR_ABI")
    if not 1 <= count <= 96 or size < 240 or unpack("<I", data, opt + 108)[0] != 16:
        raise QualificationError("PE_HEADER")
    sections = []
    for i in range(count):
        _, vs, va, length, off, _, _, _, _, f = unpack("<8sIIIIIIHHI", data, opt + size + i * 40)
        region(data, off, length)
        if f & 0xA0000000 == 0xA0000000:
            raise QualificationError("PE_WRITABLE_EXECUTABLE")
        sections.append((va, max(vs, length), off, length))

    def rva(address, length=1):
        matches = [off + address - va for va, _, off, n in sections if va <= address and address + length <= va + n]
        if len(matches) != 1:
            raise QualificationError("PE_RVA")
        region(data, matches[0], length)
        return matches[0]

    directories = [unpack("<II", data, opt + 112 + i * 8) for i in range(16)]
    if any(directories[i] != (0, 0) for i in (11, 13, 14)):
        raise QualificationError("PE_BOUND_DELAY_OR_MANAGED_IMPORT")
    exports, deps = [], []
    address, length = directories[0]
    if address:
        e = unpack("<IIHHIIIIIII", data, rva(address, 40))
        nfunc, nname, funcs, names, ordinals = e[6:]
        if nname > 65536 or nfunc > 65536:
            raise QualificationError("PE_EXPORT_COUNT")
        for i in range(nname):
            name = unpack("<I", data, rva(names + i * 4, 4))[0]
            ordinal = unpack("<H", data, rva(ordinals + i * 2, 2))[0]
            if ordinal >= nfunc:
                raise QualificationError("PE_EXPORT_ORDINAL")
            function = unpack("<I", data, rva(funcs + ordinal * 4, 4))[0]
            if address <= function < address + length:
                raise QualificationError("PE_FORWARDED_EXPORT_UNSUPPORTED")
            rva(function)
            exports.append(cstring(data, rva(name)))
    address, length = directories[1]
    if address:
        for i in range(min(length // 20, 4096)):
            row = unpack("<IIIII", data, rva(address + i * 20, 20))
            if row == (0, 0, 0, 0, 0):
                break
            name = cstring(data, rva(row[3])).lower()
            if not name.endswith(".dll") or any(x in name for x in ("/", "\\", ":")):
                raise QualificationError("PE_DEPENDENCY_NAME")
            deps.append(name)
        else:
            raise QualificationError("PE_IMPORT_TERMINATOR")
    return Image("windows-x64", tuple(exports), tuple(deps))
