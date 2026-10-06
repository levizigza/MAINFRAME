"""Supported ingest formats and file loading with encoding detection."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".jsonl", ".json", ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def detect_encoding(raw: bytes) -> str:
    """Prefer utf-8; fall back to utf-8-sig / cp1252 / latin-1 without inventing content."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def ingest_file(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "error": "file_not_found", "path": str(path)}
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return {
            "ok": False,
            "error": "unsupported_format",
            "path": str(path),
            "suffix": suffix,
            "supported": sorted(SUPPORTED_SUFFIXES),
        }

    kind = "text"
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        kind = "image"
    elif suffix in {".csv", ".tsv"}:
        kind = "table"
    elif suffix in {".json", ".jsonl"}:
        kind = "json"

    raw = path.read_bytes()
    encoding = None
    text = None
    if kind != "image":
        encoding = detect_encoding(raw)
        text = raw.decode(encoding)

    return {
        "ok": True,
        "path": str(path),
        "name": path.name,
        "suffix": suffix,
        "kind": kind,
        "encoding": encoding,
        "bytes": len(raw),
        "text": text,
        "raw_sha256": __import__("hashlib").sha256(raw).hexdigest(),
        "provenance": {"source_file": path.name, "kind": kind},
    }


def parse_table_text(text: str, *, delimiter: str | None = None) -> list[dict[str, Any]]:
    """Parse CSV/TSV into row dicts with row numbers (1-based data rows)."""
    sample = text[:4096]
    if delimiter is None:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = "\t" if "\t" in sample.splitlines()[0:1][0] else ","

    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    rows: list[dict[str, Any]] = []
    for i, row in enumerate(reader, start=2):  # header is line 1
        # Normalize keys
        clean = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
        rows.append({"_row": i, **clean})
    return rows


def parse_json_records(text: str, *, suffix: str) -> list[dict[str, Any]]:
    if suffix == ".jsonl":
        out = []
        for i, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                out.append({"_row": i, "_parse_error": str(exc), "_raw": line[:200]})
                continue
            if isinstance(obj, dict):
                out.append({"_row": i, **obj})
            else:
                out.append({"_row": i, "value": obj})
        return out
    data = json.loads(text)
    if isinstance(data, list):
        return [{"_row": i + 1, **(r if isinstance(r, dict) else {"value": r})} for i, r in enumerate(data)]
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [
            {"_row": i + 1, **(r if isinstance(r, dict) else {"value": r})}
            for i, r in enumerate(data["records"])
        ]
    if isinstance(data, dict):
        return [{"_row": 1, **data}]
    return [{"_row": 1, "value": data}]
