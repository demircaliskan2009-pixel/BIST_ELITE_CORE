"""Protected offline candidate loader. No product code imports this module.

Only source-linked, explicitly supplied qualification candidates may be passed.
An expected digest is an input to a test, never an operational admission receipt.
The platform OS loader/system baseline is recorded separately from third-party
dependency admission. Arbitrary third-party dependencies are unsupported.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import platform
import stat
import sys
import threading
from pathlib import Path

from scripts.crypto_core.qualification.c_native_formats import QualificationError, inspect_image
from scripts.crypto_core.qualification.c_native_windows import WindowsProtectedObject

EVIDENCE_CLASS = "CANDIDATE_TEST_EVIDENCE_ONLY"
_LINUX_SYSTEM = frozenset(("libc.so.6", "libdl.so.2", "libpthread.so.0", "ld-linux-x86-64.so.2"))
_WINDOWS_SYSTEM = frozenset(
    ("kernel32.dll", "ntdll.dll", "advapi32.dll", "bcrypt.dll", "ws2_32.dll", "crypt32.dll", "user32.dll")
)


def host_platform():
    if platform.machine().lower() not in ("amd64", "x86_64") or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise QualificationError("HOST_ARCH_UNSUPPORTED")
    if sys.platform == "win32":
        return "windows-x64"
    if sys.platform == "linux":
        return "linux-x64"
    raise QualificationError("HOST_OS_UNSUPPORTED")


class LinuxProtectedObject:
    """Sealed memfd; all writes, growth, truncation and removal of seals denied."""

    def __init__(self, data):
        self.fd = -1
        if sys.platform != "linux" or not hasattr(os, "memfd_create") or type(data) is not bytes:
            raise QualificationError("SEALED_MEMFD_UNAVAILABLE")
        import fcntl

        try:
            self.fd = os.memfd_create("c-qualification", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            remaining = memoryview(data)
            while remaining:
                count = os.write(self.fd, remaining)
                if count <= 0:
                    raise QualificationError("MEMFD_SHORT_WRITE")
                remaining = remaining[count:]
            self.digest = hashlib.sha256(data).hexdigest()
            self.identity = os.fstat(self.fd)
            self.seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
            fcntl.fcntl(self.fd, fcntl.F_ADD_SEALS, self.seals)
            self.path = "/proc/self/fd/" + str(self.fd)
            self.reprove()
        except BaseException:
            self.close()
            raise

    def reprove(self):
        import fcntl

        if self.fd < 0:
            raise QualificationError("OBJECT_CLOSED")
        current = os.fstat(self.fd)
        alias = os.stat(self.path)
        if (current.st_dev, current.st_ino, current.st_size) != (
            self.identity.st_dev,
            self.identity.st_ino,
            self.identity.st_size,
        ) or (alias.st_dev, alias.st_ino) != (current.st_dev, current.st_ino):
            raise QualificationError("MEMFD_IDENTITY")
        if fcntl.fcntl(self.fd, fcntl.F_GET_SEALS) & self.seals != self.seals:
            raise QualificationError("MEMFD_SEALS")
        content = os.pread(self.fd, current.st_size + 1, 0)
        if hashlib.sha256(content).hexdigest() != self.digest:
            raise QualificationError("MEMFD_DIGEST")

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _linux_baseline(image):
    if any(key.startswith("LD_") and value for key, value in os.environ.items()):
        raise QualificationError("UNTRUSTED_LOADER_ENVIRONMENT")
    preload = Path("/etc/ld.so.preload")
    if preload.exists() and preload.read_bytes().strip():
        raise QualificationError("SYSTEM_PRELOAD_UNSUPPORTED")
    if not set(image.dependencies).issubset(_LINUX_SYSTEM):
        raise QualificationError("UNQUALIFIED_DEPENDENCY")
    if os.geteuid() == 0:
        raise QualificationError("UNPRIVILEGED_QUALIFICATION_REQUIRED")
    effective = [
        line.split(":", 1)[1].strip()
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith("CapEff:")
    ]
    if len(effective) != 1 or int(effective[0], 16):
        raise QualificationError("UNPRIVILEGED_QUALIFICATION_REQUIRED")
    # Only already mapped, root-owned, non-user-writable system objects are usable.
    # dlopen therefore does not perform a search for a new dependency.
    paths = {}
    for row in Path("/proc/self/maps").read_text().splitlines():
        parts = row.split(None, 5)
        if len(parts) == 6 and parts[5].startswith("/"):
            path = Path(parts[5])
            if path.name in _LINUX_SYSTEM:
                paths.setdefault(path.name, set()).add(path)
    records = []
    pending = list(image.dependencies)
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        choices = paths.get(name, ())
        if len(choices) != 1:
            raise QualificationError("SYSTEM_DEPENDENCY_NOT_UNIQUELY_MAPPED")
        path = next(iter(choices))
        for parent in (path,) + tuple(path.parents):
            info = parent.stat()
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise QualificationError("MUTABLE_SYSTEM_DEPENDENCY")
        if not stat.S_ISREG(path.stat().st_mode):
            raise QualificationError("SYSTEM_DEPENDENCY_TYPE")
        content = path.read_bytes()
        # Inspect the actual transitive closure. Vendor glibc's IFUNC/interpreter
        # are allowed only in this root-owned, pre-mapped OS baseline.
        dependency_image = inspect_image(content, system_baseline=True)
        if (
            dependency_image.platform != "linux-x64"
            or dependency_image.soname not in ("", name)
            or not set(dependency_image.dependencies).issubset(_LINUX_SYSTEM)
        ):
            raise QualificationError("SYSTEM_DEPENDENCY_CLOSURE")
        records.append({"name": name, "path": str(path), "sha256": hashlib.sha256(content).hexdigest()})
        pending.extend(dependency_image.dependencies)
    return records


def _windows_baseline(image):
    if not set(image.dependencies).issubset(_WINDOWS_SYSTEM):
        raise QualificationError("UNQUALIFIED_DEPENDENCY")
    k = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    k.GetSystemDirectoryW.argtypes, k.GetSystemDirectoryW.restype = [ctypes.c_wchar_p, ctypes.c_uint], ctypes.c_uint
    k.GetModuleHandleW.argtypes, k.GetModuleHandleW.restype = [ctypes.c_wchar_p], ctypes.c_void_p
    k.GetModuleFileNameW.argtypes, k.GetModuleFileNameW.restype = (
        [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint],
        ctypes.c_uint,
    )
    buf = ctypes.create_unicode_buffer(32768)
    n = k.GetSystemDirectoryW(buf, len(buf))
    if not 0 < n < len(buf):
        raise QualificationError("SYSTEM_DIRECTORY")
    directory = Path(buf.value)
    records = []
    for name in image.dependencies:
        expected = directory / name
        handle = k.GetModuleHandleW(name)
        if handle:
            n = k.GetModuleFileNameW(handle, buf, len(buf))
            if not 0 < n < len(buf) or Path(buf.value).resolve() != expected.resolve():
                raise QualificationError("LOADED_DEPENDENCY_SUBSTITUTION")
        records.append(
            {"name": name, "path": str(expected), "sha256": hashlib.sha256(expected.read_bytes()).hexdigest()}
        )
    return records


class CandidateLibrary:
    """A held protected image plus bounded C ABI access; never a promotion API."""

    def __init__(self, data, expected_sha256, required_exports, *, staging_root=None):
        self._lock = threading.RLock()
        self.object, self.library = None, None
        self.evidence_class = EVIDENCE_CLASS
        self.operational_use_approved = False
        self.authorizes_native_load = False
        if (
            type(expected_sha256) is not str
            or len(expected_sha256) != 64
            or any(x not in "0123456789abcdef" for x in expected_sha256)
        ):
            raise QualificationError("EXPECTED_DIGEST")
        if type(data) is not bytes or hashlib.sha256(data).hexdigest() != expected_sha256:
            raise QualificationError("BINARY_DIGEST_MISMATCH")
        if (
            type(required_exports) is not tuple
            or not 1 <= len(required_exports) <= 64
            or any(type(name) is not str or not name.isascii() or not name.isidentifier() for name in required_exports)
        ):
            raise QualificationError("EXPLICIT_C_ABI_EXPORTS_REQUIRED")
        self.required_exports = required_exports
        self.image = inspect_image(data, required_exports)
        if self.image.platform != host_platform():
            raise QualificationError("HOST_IMAGE_MISMATCH")
        try:
            self.baseline = _windows_baseline(self.image) if sys.platform == "win32" else _linux_baseline(self.image)
        except OSError as exc:
            raise QualificationError("DEPENDENCY_PROOF_UNAVAILABLE") from exc
        try:
            if sys.platform == "win32":
                if staging_root is None:
                    raise QualificationError("EXPLICIT_STAGING_ROOT_REQUIRED")
                self.object = WindowsProtectedObject(data, staging_root)
                # SYSTEM32 only: no current directory, PATH, application or user DLL dirs.
                self.library = ctypes.CDLL(self.object.load_path, winmode=0x800)
                k = self.object.k
                k.GetModuleFileNameW.argtypes, k.GetModuleFileNameW.restype = (
                    [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint],
                    ctypes.c_uint,
                )
                buf = ctypes.create_unicode_buffer(32768)
                n = k.GetModuleFileNameW(self.library._handle, buf, len(buf))
                reported_path = buf.value[4:] if buf.value.startswith("\\\\?\\") else buf.value
                if not 0 < n < len(buf) or Path(reported_path) != self.object.path:
                    raise QualificationError("MAPPED_IMAGE_PATH_MISMATCH")
            else:
                self.object = LinuxProtectedObject(data)
                self.library = ctypes.CDLL(self.object.path, mode=os.RTLD_NOW | os.RTLD_LOCAL)
                # Identity of the actual mappings must be the held sealed inode.
                info = os.fstat(self.object.fd)
                matches = [
                    line.split()
                    for line in Path("/proc/self/maps").read_text().splitlines()
                    if "memfd:c-qualification" in line
                ]
                if not any(
                    int(fields[4]) == info.st_ino
                    and int(fields[3].split(":")[0], 16) == os.major(info.st_dev)
                    and int(fields[3].split(":")[1], 16) == os.minor(info.st_dev)
                    for fields in matches
                ):
                    raise QualificationError("MAPPED_IMAGE_IDENTITY_MISMATCH")
            self.object.reprove()
            after = _windows_baseline(self.image) if sys.platform == "win32" else _linux_baseline(self.image)
            if after != self.baseline:
                raise QualificationError("DEPENDENCY_IDENTITY_CHANGED")
            for name in required_exports:
                if not hasattr(self.library, name):
                    raise QualificationError("RUNTIME_EXPORT_MISMATCH")
        except (OSError, AttributeError) as exc:
            self.close()
            raise QualificationError("NATIVE_MAPPING_OR_ABI_REJECTED") from exc
        except BaseException:
            self.close()
            raise

    def call(self, name, argtypes, restype, *args):
        with self._lock:
            return self._call(name, argtypes, restype, *args)

    def _call(self, name, argtypes, restype, *args):
        if self.library is None or name not in self.required_exports:
            raise QualificationError("EXPORT_UNAVAILABLE")
        self.object.reprove()
        function = getattr(self.library, name)
        function.argtypes, function.restype = argtypes, restype
        return function(*args)

    def close(self):
        with self._lock:
            self._close()

    def _close(self):
        if self.library is not None:
            # There must be no escaped callable in use when the context is closed.
            import _ctypes

            if "cqual_cleanup" in self.required_exports:
                cleanup = self.library.cqual_cleanup
                cleanup.argtypes, cleanup.restype = (), None
                cleanup()

            if sys.platform == "win32":
                _ctypes.FreeLibrary(self.library._handle)
            else:
                _ctypes.dlclose(self.library._handle)
            self.library = None
        if self.object is not None:
            self.object.close()
            self.object = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
