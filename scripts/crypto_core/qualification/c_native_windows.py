"""Win32 protected staging for offline native qualification, never admission.

All ancestor directories are held with GENERIC_READ and without delete sharing.
An access-zero metadata handle is insufficient to prevent a directory rename.
The target uses CREATE_NEW, an explicit owner-only DACL, and no write/delete
sharing. Protection remains held for the entire lifetime of the mapped image.
"""

from __future__ import annotations

import ctypes as c
import hashlib
import os
import uuid
from ctypes import wintypes as w
from pathlib import Path

from scripts.crypto_core.qualification.c_native_formats import QualificationError


def windows_path(path):
    """Use one absolute local Win32 namespace, including paths beyond MAX_PATH."""
    text = os.path.abspath(os.fspath(path))
    if text.startswith("\\\\") or ":" in text[2:]:
        raise QualificationError("WINDOWS_LOCAL_PATH_REQUIRED")
    return "\\\\?\\" + text


class SecurityAttributes(c.Structure):
    _fields_ = [("length", w.DWORD), ("descriptor", c.c_void_p), ("inherit", w.BOOL)]


class FileInformation(c.Structure):
    _fields_ = [
        ("attributes", w.DWORD),
        ("created", w.FILETIME),
        ("accessed", w.FILETIME),
        ("written", w.FILETIME),
        ("volume", w.DWORD),
        ("size_hi", w.DWORD),
        ("size_lo", w.DWORD),
        ("links", w.DWORD),
        ("index_hi", w.DWORD),
        ("index_lo", w.DWORD),
    ]


def _apis():
    # Windows resolves these known system DLLs before any candidate is considered.
    k = c.WinDLL("kernel32.dll", use_last_error=True, winmode=0x800)
    k.GetSystemDirectoryW.argtypes, k.GetSystemDirectoryW.restype = [w.LPWSTR, w.UINT], w.UINT
    k.GetModuleFileNameW.argtypes, k.GetModuleFileNameW.restype = [w.HANDLE, w.LPWSTR, w.DWORD], w.DWORD
    system, loaded = c.create_unicode_buffer(32768), c.create_unicode_buffer(32768)
    count = k.GetSystemDirectoryW(system, len(system))
    if not 0 < count < len(system):
        raise QualificationError("WIN32_SYSTEM_DIRECTORY")
    a = c.WinDLL(str(Path(system.value) / "advapi32.dll"), use_last_error=True, winmode=0x800)
    for module, name in ((k, "kernel32.dll"), (a, "advapi32.dll")):
        count = k.GetModuleFileNameW(module._handle, loaded, len(loaded))
        if not 0 < count < len(loaded) or Path(loaded.value).resolve() != (Path(system.value) / name).resolve():
            raise QualificationError("WIN32_API_SUBSTITUTION")
    signatures = {
        "CreateFileW": (
            [w.LPCWSTR, w.DWORD, w.DWORD, c.POINTER(SecurityAttributes), w.DWORD, w.DWORD, w.HANDLE],
            w.HANDLE,
        ),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "CreateDirectoryW": ([w.LPCWSTR, c.POINTER(SecurityAttributes)], w.BOOL),
        "RemoveDirectoryW": ([w.LPCWSTR], w.BOOL),
        "DeleteFileW": ([w.LPCWSTR], w.BOOL),
        "MoveFileExW": ([w.LPCWSTR, w.LPCWSTR, w.DWORD], w.BOOL),
        "GetFileInformationByHandle": ([w.HANDLE, c.POINTER(FileInformation)], w.BOOL),
        "GetFinalPathNameByHandleW": ([w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD], w.DWORD),
        "SetFilePointerEx": ([w.HANDLE, c.c_longlong, c.c_void_p, w.DWORD], w.BOOL),
        "ReadFile": ([w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p], w.BOOL),
        "WriteFile": ([w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p], w.BOOL),
        "FlushFileBuffers": ([w.HANDLE], w.BOOL),
        "GetCurrentProcess": ([], w.HANDLE),
        "LocalFree": ([c.c_void_p], c.c_void_p),
    }
    for name, (args, result) in signatures.items():
        getattr(k, name).argtypes, getattr(k, name).restype = args, result
    a.OpenProcessToken.argtypes, a.OpenProcessToken.restype = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)], w.BOOL
    a.GetTokenInformation.argtypes, a.GetTokenInformation.restype = (
        [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)],
        w.BOOL,
    )
    a.ConvertSidToStringSidW.argtypes, a.ConvertSidToStringSidW.restype = [c.c_void_p, c.POINTER(c.c_void_p)], w.BOOL
    a.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        c.POINTER(c.c_void_p),
        c.c_void_p,
    ]
    a.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    return k, a


def _require(result, reason):
    if not result:
        raise QualificationError(reason + ":" + str(c.get_last_error()))


class WindowsProtectedObject:
    """One private staged immutable image; close only after unloading its module."""

    def __init__(self, data, root):
        if os.name != "nt" or type(data) is not bytes:
            raise QualificationError("WINDOWS_OBJECT_INPUT")
        self.k, self.a = _apis()
        self.handles, self.file, self.directory, self.path = [], None, None, None
        self.digest = hashlib.sha256(data).hexdigest()
        self.identity = None
        try:
            root = Path(os.path.abspath(root))
            if str(root).startswith("\\\\") or ":" in str(root)[2:]:
                raise QualificationError("WINDOWS_LOCAL_PATH_REQUIRED")
            for parent in reversed((root,) + tuple(root.parents)):
                h = self._open(parent, 0x80000000, 3, 3, 0x02200000)
                self.handles.append(h)
                self._info(h, directory=True)
            descriptor = self._descriptor()
            sa = SecurityAttributes(c.sizeof(SecurityAttributes), descriptor, False)
            try:
                directory = root / ("c-native-" + uuid.uuid4().hex)
                _require(self.k.CreateDirectoryW(windows_path(directory), c.byref(sa)), "PRIVATE_DIRECTORY")
                self.directory = directory
                h = self._open(directory, 0x80000000, 3, 3, 0x02200000)
                self.handles.append(h)
                self._info(h, directory=True)
                self.path = directory / ("candidate-" + uuid.uuid4().hex + ".dll")
                # A writable creator can remain open; sharing denies every other writer/deleter.
                file_descriptor = self._descriptor(read_only=True)
                file_sa = SecurityAttributes(c.sizeof(SecurityAttributes), file_descriptor, False)
                try:
                    self.file = self._open(self.path, 0xC0000000, 1, 1, 0x00200080, c.byref(file_sa))
                finally:
                    self.k.LocalFree(file_descriptor)
            finally:
                self.k.LocalFree(descriptor)
            written = w.DWORD()
            _require(self.k.WriteFile(self.file, data, len(data), c.byref(written), None), "STAGE_WRITE")
            if written.value != len(data):
                raise QualificationError("STAGE_SHORT_WRITE")
            _require(self.k.FlushFileBuffers(self.file), "STAGE_FLUSH")
            self.identity = self._info(self.file)
            self.k.CloseHandle(self.file)
            self.file = None
            # No writable handle survives into LoadLibraryExW. Reopening is safe only
            # because identity and contents are re-proven before the first native load.
            self.file = self._open(self.path, 0x80000000, 1, 3, 0x00200080)
            self.reprove()
        except BaseException:
            self.close()
            raise

    def _open(self, path, access, sharing, creation, flags, sa=None):
        h = self.k.CreateFileW(windows_path(path), access, sharing, sa, creation, flags, None)
        if h in (None, c.c_void_p(-1).value):
            raise QualificationError("PROTECTED_OPEN:" + str(c.get_last_error()))
        return h

    def _descriptor(self, read_only=False):
        token = w.HANDLE()
        _require(self.a.OpenProcessToken(self.k.GetCurrentProcess(), 8, c.byref(token)), "TOKEN_OPEN")
        try:
            needed = w.DWORD()
            self.a.GetTokenInformation(token, 1, None, 0, c.byref(needed))
            buf = c.create_string_buffer(needed.value)
            _require(self.a.GetTokenInformation(token, 1, buf, len(buf), c.byref(needed)), "TOKEN_USER")
            sid = c.cast(buf, c.POINTER(c.c_void_p))[0]
            text = c.c_void_p()
            _require(self.a.ConvertSidToStringSidW(sid, c.byref(text)), "TOKEN_SID")
            try:
                owner = c.wstring_at(text)
            finally:
                self.k.LocalFree(text)
            descriptor = c.c_void_p()
            # Protected DACL; no inherited ACEs, no Everyone/Users access.
            dacl = "D:P(A;;FA;;;" + owner + ")"
            if read_only:
                # New-file creator receives its requested handle; all subsequent opens
                # get read access only. OWNER RIGHTS removes implicit WRITE_DAC so
                # another process using this user token cannot reopen the write gate.
                dacl = "D:P(D;;WDWO;;;OW)(A;;FRFX;;;" + owner + ")"
            _require(
                self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(dacl, 1, c.byref(descriptor), None),
                "PRIVATE_DACL",
            )
            return descriptor
        finally:
            self.k.CloseHandle(token)

    def _info(self, h, directory=False):
        info = FileInformation()
        _require(self.k.GetFileInformationByHandle(h, c.byref(info)), "FILE_IDENTITY")
        if info.attributes & 0x400 or bool(info.attributes & 0x10) != directory:
            raise QualificationError("REPARSE_OR_OBJECT_TYPE")
        if not directory and info.links != 1:
            raise QualificationError("STAGE_HARDLINK")
        return (
            info.volume,
            info.index_hi,
            info.index_lo,
            info.created.dwHighDateTime,
            info.created.dwLowDateTime,
            info.size_hi,
            info.size_lo,
        )

    def reprove(self):
        if self.file is None:
            raise QualificationError("OBJECT_CLOSED")
        if self._info(self.file) != self.identity:
            raise QualificationError("FILE_IDENTITY_CHANGED")
        # A name-based open compatible with the held writer proves the load path still names it.
        alias = self._open(self.path, 0x80000000, 3, 3, 0x00200080)
        try:
            if self._info(alias) != self.identity:
                raise QualificationError("PATH_SUBSTITUTION")
        finally:
            self.k.CloseHandle(alias)
        _require(self.k.SetFilePointerEx(self.file, 0, None, 0), "FILE_REWIND")
        digest = hashlib.sha256()
        buf, read = c.create_string_buffer(65536), w.DWORD()
        while True:
            _require(self.k.ReadFile(self.file, buf, len(buf), c.byref(read), None), "FILE_HASH_READ")
            if not read.value:
                break
            digest.update(buf.raw[: read.value])
        if digest.hexdigest() != self.digest:
            raise QualificationError("PROTECTED_OBJECT_DIGEST_CHANGED")

    @property
    def load_path(self):
        return windows_path(self.path)

    def close(self):
        if self.file is not None:
            self.k.CloseHandle(self.file)
            self.file = None
        if self.path is not None:
            self.k.DeleteFileW(windows_path(self.path))
        for h in reversed(self.handles):
            self.k.CloseHandle(h)
        self.handles.clear()
        if self.directory is not None:
            self.k.RemoveDirectoryW(windows_path(self.directory))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
