"""Read/write helpers that preserve CRLF, encoding BOM, and file mode."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FileBytes:
    path: Path
    raw: bytes
    encoding: str  # utf-8 | utf-8-sig | ...
    newline: str  # '\n' | '\r\n' | '' (binary-ish empty)
    mode: int | None
    text: str  # decoded logical text with newlines normalized to \n for editing


def detect_encoding_and_newline(raw: bytes) -> tuple[str, str]:
    encoding = "utf-8"
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    # Prefer CRLF if present (even mixed — preserve dominant)
    if b"\r\n" in raw:
        newline = "\r\n"
    elif b"\n" in raw:
        newline = "\n"
    elif b"\r" in raw:
        newline = "\r"
    else:
        newline = "\n"
    return encoding, newline


def read_preserved(path: Path) -> FileBytes:
    raw = path.read_bytes()
    encoding, newline = detect_encoding_and_newline(raw)
    try:
        mode = path.stat().st_mode
    except OSError:
        mode = None
    # Decode then normalize to \n for editing; original newline restored on write
    text = raw.decode(encoding)
    if encoding == "utf-8-sig":
        # decode already strips BOM from text content in utf-8-sig
        pass
    text_norm = text.replace("\r\n", "\n").replace("\r", "\n")
    return FileBytes(
        path=path, raw=raw, encoding=encoding, newline=newline, mode=mode, text=text_norm
    )


def encode_preserved(text_norm: str, *, encoding: str, newline: str) -> bytes:
    """Re-encode normalized \\n text using original newline style + encoding."""
    if newline == "\r\n":
        body = text_norm.replace("\n", "\r\n")
    elif newline == "\r":
        body = text_norm.replace("\n", "\r")
    else:
        body = text_norm
    return body.encode(encoding)


def write_preserved(path: Path, text_norm: str, meta: FileBytes) -> dict[str, Any]:
    data = encode_preserved(text_norm, encoding=meta.encoding, newline=meta.newline)
    path.write_bytes(data)
    restored_mode = False
    if meta.mode is not None and os.name != "nt":
        try:
            os.chmod(path, stat.S_IMODE(meta.mode))
            restored_mode = True
        except OSError:
            restored_mode = False
    return {
        "encoding": meta.encoding,
        "newline": "crlf" if meta.newline == "\r\n" else ("cr" if meta.newline == "\r" else "lf"),
        "mode_restored": restored_mode,
        "bytes_written": len(data),
    }
