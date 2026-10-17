"""Offline adversarial tests. Synthetic image headers are never executed."""

from __future__ import annotations

import ctypes
import hashlib
import os
import struct
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.crypto_core.qualification.c_native_formats import Image, QualificationError, inspect_image
from scripts.crypto_core.qualification.c_native_loader import (
    CandidateLibrary,
    LinuxProtectedObject,
    _linux_baseline,
    host_platform,
)
from scripts.crypto_core.qualification.c_native_windows import WindowsProtectedObject, windows_path
from scripts.crypto_core.qualification.c_rfc3161_probe import (
    REQUIRED_FLAGS,
    Rfc3161QualificationProbe,
    Rfc3161TestResult,
)


def pe_image():
    data = bytearray(2048)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, 0x8664, 1, 0, 0, 0, 240, 0x2022)
    struct.pack_into("<H", data, 152, 0x20B)
    struct.pack_into("<I", data, 260, 16)
    struct.pack_into("<II", data, 264, 0x1000, 128)
    struct.pack_into("<8sIIIIIIHHI", data, 392, b".text\0\0\0", 1536, 0x1000, 1536, 512, 0, 0, 0, 0, 0x60000020)
    struct.pack_into("<IIHHIIIIIII", data, 512, 0, 0, 0, 0, 0, 1, 1, 1, 0x1080, 0x1084, 0x1088)
    struct.pack_into("<IIH", data, 640, 0x1100, 0x1090, 0)
    data[656:665] = b"test_abi\0"
    return bytes(data)


def elf_image():
    data = bytearray(8192)
    data[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHIQQQIHHHHHH", data, 16, 3, 62, 1, 0, 64, 512, 0, 64, 56, 3, 64, 3, 0)
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, 8192, 8192, 4096)
    struct.pack_into("<IIQQQQQQ", data, 120, 2, 4, 4096, 4096, 0, 48, 48, 8)
    struct.pack_into("<IIQQQQQQ", data, 176, 0x6474E551, 6, 0, 0, 0, 0, 0, 16)
    struct.pack_into("<qQqQqQ", data, 4096, 5, 4608, 10, 1, 0, 0)
    struct.pack_into("<IIQQQQIIQQ", data, 576, 0, 6, 2, 4096, 4096, 48, 2, 0, 8, 16)
    struct.pack_into("<IIQQQQIIQQ", data, 640, 0, 3, 2, 4608, 4608, 1, 0, 0, 1, 0)
    return bytes(data)


def mutate(data, offset, fmt, value):
    output = bytearray(data)
    struct.pack_into(fmt, output, offset, value)
    return bytes(output)


def test_pe_and_elf_headers_are_inspected_without_execution():
    assert inspect_image(pe_image(), ("test_abi",)).platform == "windows-x64"
    assert inspect_image(elf_image()).platform == "linux-x64"


@pytest.mark.parametrize("candidate", [b"", b"MZ", b"\x7fELF", None, bytearray(128), b"x" * 128])
def test_modified_or_malformed_binary_rejected(candidate):
    with pytest.raises(QualificationError):
        inspect_image(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        mutate(pe_image(), 132, "<H", 0xAA64),
        mutate(pe_image(), 152, "<H", 0x10B),
        mutate(elf_image(), 18, "<H", 183),
        mutate(elf_image(), 48, "<I", 1),
    ],
    ids=("pe-arm64", "pe-32bit", "elf-arm64", "elf-abi-flags"),
)
def test_wrong_architecture_and_abi_rejected(candidate):
    with pytest.raises(QualificationError, match="ARCH|ABI"):
        inspect_image(candidate)


def test_missing_export_rejected_before_load():
    with pytest.raises(QualificationError, match="MISSING_EXPORT"):
        inspect_image(pe_image(), ("missing",))


@pytest.mark.parametrize("tag", [15, 29, 22, 0x6FFFFEFC, 0x6FFFFEFB, 0x7FFFFFFD, 0x7FFFFFFF])
def test_unsafe_so_search_audit_and_text_relocations_rejected(tag):
    candidate = mutate(elf_image(), 4096, "<q", tag)
    with pytest.raises(QualificationError, match="SEARCH"):
        inspect_image(candidate)


def test_pe_delayed_dependency_and_forwarder_rejected():
    for candidate in (mutate(pe_image(), 264 + 13 * 8, "<I", 0x1000), mutate(pe_image(), 640, "<I", 0x1040)):
        with pytest.raises(QualificationError, match="IMPORT|FORWARD"):
            inspect_image(candidate)


def test_runtime_dynamic_string_substitution_rejected():
    with pytest.raises(QualificationError, match="BINDING"):
        inspect_image(mutate(elf_image(), 4104, "<Q", 4700))


@pytest.mark.parametrize("digest", ["0" * 64, "not-a-digest", None, True])
def test_wrong_digest_cannot_reach_mapping(digest):
    with pytest.raises(QualificationError, match="DIGEST"):
        CandidateLibrary(pe_image(), digest, ("test_abi",))


def test_third_party_dependency_substitution_rejected():
    with pytest.raises(QualificationError, match="UNQUALIFIED_DEPENDENCY"):
        _linux_baseline(Image("linux-x64", (), ("libcrypto.so.3",)))


def test_untrusted_loader_environment_rejected(monkeypatch):
    monkeypatch.setenv("LD_PRELOAD", "/attacker/injected.so")
    with pytest.raises(QualificationError, match="ENVIRONMENT"):
        _linux_baseline(Image("linux-x64", (), ()))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows protection requires a real Windows kernel")
def test_windows_protected_identity_and_deny_writer(tmp_path):
    payload = b"qualification plain data; never a native image"
    with WindowsProtectedObject(payload, tmp_path) as obj:
        assert obj.digest == hashlib.sha256(payload).hexdigest()
        obj.reprove()
        executable_reader = obj._open(obj.path, 0xA0000000, 1, 3, 0x00200080)
        obj.k.CloseHandle(executable_reader)
        with pytest.raises(QualificationError, match="PROTECTED_OPEN:(5|32)$"):
            obj._open(obj.path, 0x40000000, 7, 3, 0x80)
        assert not obj.k.MoveFileExW(obj.load_path, windows_path(tmp_path / "replaced.dll"), 0)
        assert ctypes.get_last_error() in (5, 32)
        obj.reprove()
    assert not obj.path.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows parent rename requires a real Windows kernel")
def test_windows_parent_and_ancestor_directory_rename_denied(tmp_path):
    outer = tmp_path / "outer"
    root = outer / "root"
    root.mkdir(parents=True)
    with WindowsProtectedObject(b"private stage", root) as obj:
        for source in (obj.directory, root, outer):
            assert not obj.k.MoveFileExW(
                windows_path(source), windows_path(source.with_name(source.name + "-moved")), 0
            )
            assert ctypes.get_last_error() in (5, 32)
        obj.reprove()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DACL race requires a real Windows kernel")
def test_windows_reopen_gap_rejects_writer_and_owner_dacl_override(tmp_path):
    class AttackAtReopen(WindowsProtectedObject):
        attempted = False

        def _open(self, path, access, sharing, creation, flags, sa=None):
            if (
                self.path is not None
                and path == self.path
                and self.file is None
                and creation == 3
                and not self.attempted
            ):
                self.attempted = True
                # There is no held target handle at this exact moment. The DACL,
                # rather than sharing flags, must stop writable/mapped aliases.
                with pytest.raises(QualificationError, match="PROTECTED_OPEN:5$"):
                    super()._open(path, 0x40000000, 7, 3, 0x80)
                attack = self.k.CreateFileW(windows_path(path), 0x000C0000, 7, None, 3, 0x80, None)
                assert attack == ctypes.c_void_p(-1).value
            return super()._open(path, access, sharing, creation, flags, sa)

    with AttackAtReopen(b"held source bytes", tmp_path) as obj:
        assert obj.attempted
        obj.reprove()


@pytest.mark.skipif(sys.platform != "win32", reason="Long Win32 paths require Windows")
def test_windows_long_path_has_same_identity_and_rename_protection(tmp_path):
    root = tmp_path / ("long-path-" + "x" * 140)
    os.mkdir(windows_path(root))
    with WindowsProtectedObject(b"long path snapshot", root) as obj:
        assert len(str(obj.path)) > 260
        obj.reprove()
        assert not obj.k.MoveFileExW(windows_path(obj.directory), windows_path(obj.directory.with_name("renamed")), 0)
        assert ctypes.get_last_error() in (5, 32)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows reparse fixture requires Windows")
def test_windows_reparse_parent_rejected(tmp_path):
    target, alias = tmp_path / "target", tmp_path / "alias"
    target.mkdir()
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip("BLOCKED: real symlink privilege unavailable: " + str(error.winerror))
    with pytest.raises(QualificationError, match="REPARSE"):
        WindowsProtectedObject(b"data", alias)


@pytest.mark.skipif(sys.platform != "win32", reason="Real junction fixture requires Windows")
def test_windows_junction_parent_rejected_with_real_reparse_point(tmp_path):
    target, alias = tmp_path / "junction-target", tmp_path / "junction-alias"
    os.mkdir(windows_path(target))
    os.mkdir(windows_path(alias))
    with WindowsProtectedObject(b"junction fixture setup", tmp_path) as fixture:
        k = fixture.k
        k.DeviceIoControl.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        )
        k.DeviceIoControl.restype = ctypes.c_int
        substitute = "\\??\\" + str(target)
        printable = str(target)
        names = (substitute + "\0" + printable + "\0").encode("utf-16-le")
        payload = (
            struct.pack(
                "<IHHHHHH",
                0xA0000003,
                8 + len(names),
                0,
                0,
                len(substitute) * 2,
                (len(substitute) + 1) * 2,
                len(printable) * 2,
            )
            + names
        )
        buffer, returned = ctypes.create_string_buffer(payload), ctypes.c_uint32()
        handle = fixture._open(alias, 0x40000000, 7, 3, 0x02200000)
        try:
            success = k.DeviceIoControl(handle, 0x000900A4, buffer, len(payload), None, 0, ctypes.byref(returned), None)
            error = ctypes.get_last_error()
        finally:
            k.CloseHandle(handle)
        try:
            if not success:
                pytest.skip("BLOCKED: real junction fixture denied by host: " + str(error))
            with pytest.raises(QualificationError, match="REPARSE"):
                WindowsProtectedObject(b"never staged through a junction", alias)
        finally:
            # Remove the junction object itself, never traverse or recursively delete it.
            os.rmdir(windows_path(alias))


@pytest.mark.skipif(sys.platform != "linux", reason="Linux memfd requires a real Linux kernel")
def test_linux_mutable_object_races_fail_closed():
    import mmap

    with LinuxProtectedObject(b"native candidate snapshot") as obj:
        for length in (0, 4096):
            with pytest.raises(OSError):
                os.ftruncate(obj.fd, length)
        with pytest.raises(OSError):
            os.write(obj.fd, b"replacement")
        with pytest.raises(OSError):
            mmap.mmap(obj.fd, 0, flags=mmap.MAP_SHARED, prot=mmap.PROT_WRITE)
        obj.reprove()


def test_abi_mismatch_rejected_without_crypto_call():
    class WrongAbi:
        def call(self, *_):
            return 0

    with pytest.raises(QualificationError, match="ABI"):
        Rfc3161QualificationProbe(WrongAbi())


def test_signature_disabled_rejected_before_native_call():
    probe = object.__new__(Rfc3161QualificationProbe)
    with pytest.raises(QualificationError, match="SIGNATURE_VERIFICATION_REQUIRED"):
        probe.verify(
            b"req",
            b"resp",
            b"root",
            b"crl",
            b"i" * 32,
            b"n",
            "1.2.3",
            b"s" * 32,
            as_of_us=10,
            max_accuracy_us=10,
            asserted_flags=REQUIRED_FLAGS & ~1,
        )


def test_synthetic_result_never_has_operational_authority():
    result = Rfc3161TestResult("VERIFIED_TEST_ONLY", 1, 1)
    assert not result.machine_time_origin_proven and not result.operational_use_approved and not result.quorum_countable
    # A fabricated/replaced test result has no production consumer or admission API.
    with pytest.raises(ValueError, match="init=False"):
        replace(result, operational_use_approved=True)
    from crypto_core.validation.machine_time_drand_quicknet_verifier_profile import (
        MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_SHA256,
    )

    path = (
        Path(__file__).resolve().parents[3]
        / "src/crypto_core/validation/evidence/mt4_blst_stage_c_admission_evidence_v1.json"
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_SHA256


def test_host_is_derived_from_runtime():
    assert host_platform() in ("windows-x64", "linux-x64")
