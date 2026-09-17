#!/usr/bin/env python3
"""Analyse, repair, verify, and extract archives that hide behind a decoy prefix.

Netdisk releases ship the real archive appended to a small but genuine media file
(a few MB of real MP4) and the reader is told to rename the extension. Extracting
then fails for two unrelated reasons:

  1. The prefix shifts every byte position, and the packer wrote the ZIP64
     central-directory offsets relative to the archive start, ignoring it.
     Only tolerant readers (WinRAR) get through.
  2. Outer layers are usually WinZip-AES encrypted (compression method 99),
     which Ark/file-roller/unzip/python reject outright.

Subcommands:

  analyze FILE [--deep]        report container, offsets, encryption, completeness
  repair  FILE [--out PATH]    make it openable: reflink copy + rewrite offsets,
                               or --strip (byte-range copy without the prefix)
  verify  FILE --password PW   decrypt the head (cheap) and compare the archive's
                               embedded SHA-256 (strong) before paying a write
  extract FILE --password PW   unpack with 7-Zip and name the next layer

Stdlib only; call 7-Zip (7z/7zz/7za) for the ZIP64 record work we cannot do alone.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ARCHIVE_SIGNATURES = (
    (b"PK\x03\x04", "zip"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"Rar!\x1a\x07\x01\x00", "rar5"),
    (b"Rar!\x1a\x07\x00", "rar4"),
)

LEADING_KINDS = (
    (b"ftyp", 4, "ISO base media (MP4/MOV) - real video, not an archive"),
    (b"\x89PNG", 0, "PNG image"),
    (b"\xff\xd8\xff", 0, "JPEG image"),
    (b"ID3", 0, "MP3 audio"),
)

HEAD_SCAN = 64 << 20
EOCD_SCAN = (1 << 20) + 65557  # 网盘 packers leave junk after the archive end
SEVEN_ZIP_NAMES = ("7z", "7zz", "7za", "7zr")
COPY_CHUNK = 32 << 20
AES_STRENGTHS = {1: "AES-128", 2: "AES-192", 3: "AES-256"}
HASH_IN_COMMENT = re.compile(rb"SHA-256 Hash of '.*?':\s*([0-9a-fA-F]{64})", re.S)


class LayoutError(Exception):
    """The bytes do not form a ZIP layout we can reason about."""


def seven_zip() -> str:
    for name in SEVEN_ZIP_NAMES:
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("7-Zip not found. Install the '7zip' or 'p7zip' package (7z/7zz/7za).")


def human(n: int) -> str:
    for unit, scale in (("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)):
        if n >= scale:
            return f"{n / scale:.2f} {unit}"
    return f"{n} B"


def read_at(f, offset: int, size: int) -> bytes:
    f.seek(offset)
    return f.read(size)


def first_archive_signature(path: Path, limit: int) -> tuple[int, str] | None:
    with open(path, "rb") as f:
        head = f.read(limit)
    best = None
    for sig, kind in ARCHIVE_SIGNATURES:
        pos = head.find(sig)
        if pos >= 0 and (best is None or pos < best[0]):
            best = (pos, kind)
    return best


def leading_kind(head: bytes) -> str:
    for sig, at, label in LEADING_KINDS:
        if head[at : at + len(sig)] == sig:
            return label
    return "unknown"


def iter_extra(extra: bytes):
    i = 0
    while i + 4 <= len(extra):
        tag, size = struct.unpack_from("<HH", extra, i)
        yield tag, extra[i + 4 : i + 4 + size], i + 4
        i += 4 + size


def decode_name(raw: bytes, flags: int) -> str:
    if flags & 0x800:
        return raw.decode("utf-8", "replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp437", "replace")


def local_header(f, pos: int, expected_name: bytes) -> dict | None:
    """Parse a local file header, accepting it only when the name matches.

    Matching the name is what keeps a stray `PK\\x03\\x04` inside payload bytes
    from being mistaken for the entry's real header.
    """
    hdr = read_at(f, pos, 30)
    if len(hdr) < 30 or hdr[:4] != b"PK\x03\x04":
        return None
    flags, method = struct.unpack_from("<HH", hdr, 6)
    name_len, extra_len = struct.unpack_from("<HH", hdr, 26)
    name = read_at(f, pos + 30, name_len)
    if expected_name and name != expected_name:
        return None
    return {
        "flags": flags,
        "method": method,
        "name_len": name_len,
        "extra_len": extra_len,
        "data_offset": pos + 30 + name_len + extra_len,
    }


class Layout:
    """A ZIP's own bookkeeping, with every offset resolved against the real file."""

    def __init__(self, path: Path):
        self.path = path
        self.size = os.path.getsize(path)
        self.zip64_pos = None
        self.locator_pos = None
        self.eocd_pos = 0
        self.comment = b""
        self.entries: list[dict] = []
        with open(path, "rb") as f:
            self._read_eocd(f)
            self.cd_declared = self._cd_declared
            self.cd_actual = self._cd_actual
            self.shift = self.cd_actual - self.cd_declared
            self._read_entries(f)

    def _read_eocd(self, f) -> None:
        window = min(self.size, EOCD_SCAN)
        f.seek(self.size - window)
        buf = f.read(window)
        probe = len(buf)
        while True:
            i = buf.rfind(b"PK\x05\x06", 0, probe)
            if i < 0:
                raise LayoutError("no end-of-central-directory record found (not a ZIP, or truncated)")
            probe = i
            pos = self.size - window + i
            clen = struct.unpack_from("<H", buf, i + 20)[0]
            if pos + 22 + clen > self.size:
                continue  # comment claims bytes that are not there
            entries, cd_size, cd_off = struct.unpack_from("<HII", buf, i + 10)
            comment = buf[i + 22 : i + 22 + clen]
            self.eocd_pos = pos
            self.comment = comment
            if cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF or entries == 0xFFFF:
                self._read_zip64_eocd(f, pos)
            else:
                self._cd_declared = cd_off
                self._cd_size = cd_size
                # The central directory ends exactly where the EOCD record starts;
                # the archive comment lives inside that record, after its 22 bytes.
                self._cd_actual = pos - cd_size
            return

    def _read_zip64_eocd(self, f, eocd_pos: int) -> None:
        if eocd_pos < 20 or read_at(f, eocd_pos - 20, 4) != b"PK\x06\x07":
            raise LayoutError(
                "EOCD claims ZIP64 but the ZIP64 locator is missing; the archive needs a tolerant reader"
            )
        self.locator_pos = eocd_pos - 20
        declared = struct.unpack("<Q", read_at(f, eocd_pos - 12, 8))[0]
        # The record sits immediately before the locator; its own declared offset
        # is the packer's, which for disguised archives ignores the prefix.
        for cand in (declared, self.locator_pos - 56):
            if 0 <= cand <= self.locator_pos - 56 and read_at(f, cand, 4) == b"PK\x06\x06":
                self.zip64_pos = cand
                break
        if self.zip64_pos is None:
            raise LayoutError("ZIP64 end-of-central-directory record not found where the locator points")
        rec = read_at(f, self.zip64_pos, 56)
        self._cd_size = struct.unpack_from("<Q", rec, 40)[0]
        self._cd_declared = struct.unpack_from("<Q", rec, 48)[0]
        self._cd_actual = self.zip64_pos - self._cd_size
        self.zip64_declared = declared

    def _read_entries(self, f) -> None:
        if read_at(f, self._cd_actual, 4) != b"PK\x01\x02":
            raise LayoutError(
                f"central directory not where the archive says it is (expected PK\\x01\\x02 at {self._cd_actual})"
            )
        pos = self._cd_actual
        cd_end = self._cd_actual + self._cd_size
        while pos + 46 <= cd_end:
            head = read_at(f, pos, 46)
            if head[:4] != b"PK\x01\x02":
                break
            (
                _sig,
                _made,
                _needed,
                flags,
                method,
                _time,
                _date,
                _crc,
                csz,
                usz,
                name_len,
                extra_len,
                comment_len,
                disk,
                _attrs,
                _attrs_ext,
                lho,
            ) = struct.unpack("<IHHHHHHIIIHHHHHII", head)
            name_raw = read_at(f, pos + 46, name_len)
            extra = read_at(f, pos + 46 + name_len, extra_len)
            entry = {
                "name": decode_name(name_raw, flags),
                "name_raw": name_raw,
                "flags": flags,
                "method": method,
                "csz": csz,
                "usz": usz,
                "disk": disk,
                "lho_declared": lho,
                "lho_field_pos": pos + 42,
                "aes": None,
                "zip64": None,
            }
            for tag, body, body_at in iter_extra(extra):
                if tag == 0x0001:
                    entry["zip64"] = (body, pos + 46 + name_len + body_at, usz == 0xFFFFFFFF, csz == 0xFFFFFFFF, lho == 0xFFFFFFFF)
                elif tag == 0x9901 and len(body) >= 7:
                    # version(2), vendor(2), strength(1), real method(2)
                    version = struct.unpack_from("<H", body, 0)[0]
                    entry["aes"] = {
                        "version": version,
                        "vendor": body[2:4].decode("latin1"),
                        "strength": AES_STRENGTHS.get(body[4], f"strength {body[4]}"),
                        "actual_method": struct.unpack_from("<H", body, 5)[0],
                    }
            if entry["zip64"]:
                body, _at, need_usz, need_csz, need_lho = entry["zip64"]
                off = 0
                if need_usz and off + 8 <= len(body):
                    entry["usz"] = struct.unpack_from("<Q", body, off)[0]
                    off += 8
                if need_csz and off + 8 <= len(body):
                    entry["csz"] = struct.unpack_from("<Q", body, off)[0]
                    off += 8
                if need_lho and off + 8 <= len(body):
                    entry["zip64_lho_pos"] = entry["zip64"][1] + off
                    entry["lho_declared"] = struct.unpack_from("<Q", body, off)[0]
            self.entries.append(entry)
            pos += 46 + name_len + extra_len + comment_len
        self._resolve_entries(f)

    def _resolve_entries(self, f) -> None:
        for entry in self.entries:
            entry["local_pos"] = None
            entry["lho_mode"] = None
            candidates = [
                (entry["lho_declared"] + self.shift, "relative"),
                (entry["lho_declared"], "absolute"),
            ]
            for cand, mode in candidates:
                if cand < 0:
                    continue
                parsed = local_header(f, cand, entry["name_raw"])
                if parsed:
                    entry["local_pos"] = cand
                    entry["lho_mode"] = mode
                    entry["local"] = parsed
                    break
            entry["payload_end"] = (
                entry["local"]["data_offset"] + entry["csz"] if entry["local_pos"] is not None else None
            )

    @property
    def encrypted(self) -> bool:
        return any(e["flags"] & 0x1 for e in self.entries)

    def payload_end(self) -> int | None:
        ends = [e["payload_end"] for e in self.entries if e["payload_end"] is not None]
        return max(ends) if ends else None

    def patches(self) -> list[tuple[int, int, int, str]]:
        """(file offset, byte width, new value, label) for every stale offset."""
        out: list[tuple[int, int, int, str]] = []
        with open(self.path, "rb") as f:
            if not self.is_zip64:
                declared = struct.unpack("<I", read_at(f, self.eocd_pos + 16, 4))[0]
                if declared != 0xFFFFFFFF and declared != self.cd_actual:
                    out.append((self.eocd_pos + 16, 4, self.cd_actual, "EOCD central-directory offset"))
            else:
                declared_cd = struct.unpack("<Q", read_at(f, self.zip64_pos + 48, 8))[0]
                if declared_cd != self.cd_actual:
                    out.append((self.zip64_pos + 48, 8, self.cd_actual, "ZIP64 EOCD central-directory offset"))
                declared_z64 = struct.unpack("<Q", read_at(f, self.locator_pos + 8, 8))[0]
                if declared_z64 != self.zip64_pos:
                    out.append((self.locator_pos + 8, 8, self.zip64_pos, "ZIP64 locator record offset"))
        for index, entry in enumerate(self.entries, 1):
            if entry["lho_mode"] != "relative":
                continue
            if "zip64_lho_pos" in entry:
                out.append((entry["zip64_lho_pos"], 8, entry["local_pos"], f"entry {index} local-header offset"))
            else:
                out.append((entry["lho_field_pos"], 4, entry["local_pos"], f"entry {index} local-header offset"))
        return out

    @property
    def is_zip64(self) -> bool:
        return self.zip64_pos is not None


def describe_head(path: Path, sig: tuple[int, str] | None) -> None:
    print(f"file            {path}")
    print(f"size            {os.path.getsize(path):,} bytes ({human(os.path.getsize(path))})")
    with open(path, "rb") as f:
        print(f"leading bytes   {leading_kind(read_at(f, 0, 16))}")
    if sig:
        print(f"archive found   {sig[1]} signature at offset {sig[0]:,}" + (f" (prefix {human(sig[0])})" if sig[0] else " (starts at byte 0)"))
    else:
        print(f"archive found   nothing in the first {human(HEAD_SCAN)}: truncated download, or the prefix is not media")


def describe_layout(layout: Layout, path: Path, deep_hits: list[tuple[int, str]] | None = None) -> None:
    print(f"central dir     declared {layout.cd_declared:,}  actual {layout.cd_actual:,}")
    if layout.shift:
        print(f"offset shift    {layout.shift:,} bytes ({human(layout.shift)}): offsets ignore the prefix")
    else:
        print("offset shift    none: offsets already match the file")
    print(f"entries         {len(layout.entries)}")
    for index, entry in enumerate(layout.entries, 1):
        marks = []
        if entry["method"] == 99 and entry["aes"]:
            marks.append(f"{entry['aes']['strength']} encrypted")
        elif entry["flags"] & 0x1:
            marks.append("ZipCrypto encrypted")
        if entry["aes"] and entry["aes"]["actual_method"] == 0:
            marks.append("stored")
        if entry["local_pos"] is None:
            marks.append("LOCAL HEADER NOT FOUND")
        print(f"  {index}. {human(entry['usz'])} raw / {human(entry['csz'])} in archive  {' '.join(marks)}")
        print(f"     {entry['name']}")
    end = layout.payload_end()
    if end is not None:
        gap = layout.cd_actual - end
        if gap == 0:
            verdict = "complete: declared payload ends exactly where the directory starts"
        elif 0 < gap <= 64:
            verdict = f"complete: {gap} bytes of data descriptor between payload and directory"
        elif gap > 0:
            verdict = f"SHORT by {gap:,} bytes ({human(gap)}): re-download, do not re-pipe"
        else:
            verdict = f"INCONSISTENT: payload claims {human(-gap)} more than the file holds: re-download"
        print(f"payload check   {verdict}")
    trailing = layout.size - (layout.eocd_pos + 22 + len(layout.comment))
    if trailing:
        print(f"trailing data   {trailing:,} bytes after the archive end (decoys/verification blob; ignore)")
    if deep_hits:
        print("signatures      " + ", ".join(f"{kind}@{off:,}" for off, kind in deep_hits))
    print("verdict         " + verdict_line(layout))


def verdict_line(layout: Layout) -> str:
    problems = []
    if layout.shift:
        problems.append("offsets ignore the prefix, so 7-Zip/Ark/Bandizip refuse it -> run repair")
    missing = sum(1 for e in layout.entries if e["local_pos"] is None)
    if missing:
        problems.append(f"{missing} of {len(layout.entries)} entries have no local header at the recorded offset -> damaged or truncated download")
    if layout.encrypted:
        problems.append("encrypted entry: only 7-Zip or WinRAR can decrypt it (Ark, file-roller, unzip, python zipfile cannot)")
    if layout.payload_end() is not None and layout.cd_actual - layout.payload_end() > 64:
        problems.append("payload shorter than declared -> incomplete download")
    return " ; ".join(problems) if problems else "opens as-is with 7-Zip: 7z x FILE -p<password>"


def deep_scan(path: Path) -> list[tuple[int, str]]:
    hits = []
    overlap = 64
    with open(path, "rb") as f:
        offset = 0
        tail = b""
        while True:
            chunk = f.read(COPY_CHUNK)
            if not chunk:
                break
            buf = tail + chunk
            base = offset - len(tail)
            for sig, kind in ARCHIVE_SIGNATURES:
                start = 0
                while True:
                    i = buf.find(sig, start)
                    if i < 0:
                        break
                    hits.append((base + i, kind))
                    start = i + 1
            tail = chunk[-overlap:]
            offset += len(chunk)
    return sorted(hits)


def cmd_analyze(args) -> int:
    path = Path(args.file)
    sig = first_archive_signature(path, HEAD_SCAN)
    layout = None
    error = None
    try:
        layout = Layout(path)
    except LayoutError as exc:
        error = exc
    describe_head(path, sig)
    if layout:
        describe_layout(layout, path, deep_scan(path) if args.deep else None)
    else:
        print(f"zip layout      {error}")
        if sig:
            print(
                f"verdict         {sig[1]} stores nothing position-dependent, so stripping the {human(sig[0])} "
                "prefix is enough -> run repair"
            )
        else:
            print("verdict         no archive to repair; the download looks incomplete or is not packed this way")
    if args.deep and not sig:
        hits = deep_scan(path)
        print("signatures      " + (", ".join(f"{kind}@{off:,}" for off, kind in hits) or "none"))
    return 0 if sig else 1


def cmd_repair(args) -> int:
    path = Path(args.file)
    out = Path(args.out) if args.out else path.with_name(f"{path.stem}-fixed{path.suffix}")
    if out.exists() and not args.force:
        raise SystemExit(f"{out} exists; pass --force to overwrite")
    layout = None
    try:
        layout = Layout(path)
    except LayoutError as exc:
        print(f"no usable ZIP layout ({exc}); repairing by stripping the prefix instead")
    if layout and not layout.shift and not args.strip:
        print(f"nothing to repair: offsets already match the file")
        print(f"next            {seven_zip()} x '{path}' -p<password>")
        return 0
    if args.strip or layout is None:
        prefix = prefix_length(path)
        if prefix == 0:
            print("no archive signature found; nothing to strip")
            return 1
        strip_copy(path, out, prefix)
        print(f"stripped        {prefix:,} bytes ({human(prefix)}) of prefix -> {out}")
    else:
        if not reflink_copy(path, out):
            prefix = layout.entries[0]["local_pos"] if layout.entries[0]["local_pos"] else 0
            print("reflink unavailable here; falling back to a full-size stripped copy")
            strip_copy(path, out, prefix)
            print(f"stripped        {prefix:,} bytes of prefix -> {out}")
        else:
            print(f"reflink copy    {out} (shares extents with the original; no extra space used)")
            patches = layout.patches()
            with open(out, "r+b") as f:
                for offset, width, value, label in patches:
                    fmt = "<I" if width == 4 else "<Q"
                    f.seek(offset)
                    f.write(struct.pack(fmt, value))
                    print(f"rewrote         {label} -> {value:,}")
            if not patches:
                print("rewrote         nothing (offsets already correct)")
    check = subprocess.run([seven_zip(), "l", str(out)], capture_output=True, text=True)
    if check.returncode != 0:
        print(check.stdout + check.stderr, file=sys.stderr)
        print(f"7-Zip still refuses {out}; keep the original and re-download", file=sys.stderr)
        return 1
    listed = [line for line in check.stdout.splitlines() if line.strip()]
    print("accepted by     7-Zip (" + listed[-1].strip() + ")")
    print(f"next            {seven_zip()} x '{out}' -p<password>")
    return 0


def prefix_length(path: Path) -> int:
    sig = first_archive_signature(path, HEAD_SCAN)
    return sig[0] if sig else 0


def reflink_copy(src: Path, dst: Path) -> bool:
    result = subprocess.run(["cp", "--reflink=always", str(src), str(dst)], capture_output=True, text=True)
    if result.returncode == 0:
        return True
    dst.unlink(missing_ok=True)
    return False


class Progress:
    """Throttled progress on stderr: carriage returns on a tty, one line per step in a pipe."""

    def __init__(self, label: str, total: int | None = None):
        self.label = label
        self.total = total
        self.tty = sys.stderr.isatty()
        self.step = (256 << 20) if self.tty else (1 << 30)
        self.last = -1
        self.drew_tty = False

    def update(self, done: int) -> None:
        if done == self.last or (self.last >= 0 and done - self.last < self.step):
            return
        self.last = done
        text = f"{self.label} {human(done)}" + (f" / {human(self.total)}" if self.total else "")
        if self.tty:
            print("\r" + text, end="", file=sys.stderr, flush=True)
            self.drew_tty = True
        else:
            print(text, file=sys.stderr, flush=True)

    def finish(self, done: int) -> None:
        if self.drew_tty:
            print("\r" + " " * 64 + "\r", end="", file=sys.stderr, flush=True)
        elif self.last != done:
            print(f"{self.label} {human(done)} done", file=sys.stderr, flush=True)


def strip_copy(src: Path, dst: Path, prefix: int) -> None:
    total = os.path.getsize(src) - prefix
    progress = Progress("copied", total)
    done = 0
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fin.seek(prefix)
        while True:
            chunk = fin.read(COPY_CHUNK)
            if not chunk:
                break
            fout.write(chunk)
            done += len(chunk)
            progress.update(done)
    progress.finish(done)


def cmd_verify(args) -> int:
    path = Path(args.file)
    password = resolve_password(args.password)
    if not os.path.isfile(path):
        raise SystemExit(f"{path} not found")
    proc = subprocess.Popen(
        [seven_zip(), "x", "-so", "-bd", "-bso0", "-bse0", f"-p{password}", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    digest = hashlib.sha256()
    head = b""
    total = 0
    progress = Progress("read")
    while True:
        chunk = proc.stdout.read(4 << 20)
        if not chunk:
            break
        if len(head) < (4 << 20):
            head += chunk[: (4 << 20) - len(head)]
        digest.update(chunk)
        total += len(chunk)
        progress.update(total)
    returncode = proc.wait()
    progress.finish(total)
    if returncode != 0:
        print(f"password check  7-Zip exited {returncode}: wrong password, or a damaged payload")
        return 2
    print("password check  7-Zip accepted the password (exit 0)")
    inner = next((kind for sig, kind in ARCHIVE_SIGNATURES if head.startswith(sig)), None)
    print(f"payload starts  {inner + ' archive header' if inner else 'not an archive (plain file, or a container 7-Zip splits)'}")
    print(f"decrypted size  {total:,} bytes")
    embedded = HASH_IN_COMMENT.search(layout_comment(path))
    if not embedded:
        print("hash check      no SHA-256 embedded in the archive comment; password check only")
        return 0
    expected = embedded.group(1).decode().lower()
    actual = digest.hexdigest()
    print(f"embedded hash   {expected} (from the archive comment)")
    print(f"decrypted hash  {actual}")
    if actual == expected:
        print("hash check      MATCH: password correct and payload intact")
        return 0
    print("hash check      MISMATCH: wrong password or damaged download")
    return 2


def layout_comment(path: Path) -> bytes:
    try:
        return Layout(path).comment
    except LayoutError:
        return b""


def resolve_password(given: str | None) -> str:
    if given:
        return given
    if sys.stdin.isatty():
        return getpass.getpass("archive password: ")
    raise SystemExit("--password is required in non-interactive runs")


def cmd_extract(args) -> int:
    path = Path(args.file)
    password = resolve_password(args.password)
    try:
        layout = Layout(path)
    except LayoutError as exc:
        raise SystemExit(f"{path} is not extractable yet ({exc}); run: {Path(sys.argv[0]).name} repair '{path}'")
    if layout.shift:
        raise SystemExit(
            f"offsets ignore the {layout.shift:,}-byte prefix, so 7-Zip will refuse this file; run: "
            f"{Path(sys.argv[0]).name} repair '{path}'"
        )
    out_dir = Path(args.out) if args.out else path.parent
    before = {p for p in out_dir.iterdir()} if out_dir.exists() else set()
    command = [seven_zip(), "x", "-y", f"-p{password}", f"-o{out_dir}", str(path)]
    print("$ " + " ".join(command), flush=True)
    result = subprocess.run(command, text=True)
    if result.returncode != 0:
        print(f"7-Zip exited {result.returncode}: wrong password, or the payload is damaged", file=sys.stderr)
        return result.returncode
    for produced in sorted(set(out_dir.iterdir()) - before):
        if produced.is_file():
            print(f"extracted       {produced.name} ({human(produced.stat().st_size)})")
            sig = first_archive_signature(produced, HEAD_SCAN) if produced.stat().st_size else None
            if sig:
                print(f"inner container {sig[1]} -> next layer, its password is often NOT the first one")
                if sig[1].startswith("rar"):
                    print(f"next            unrar x -p'<password>' '{produced}'")
                else:
                    print(f"next            {seven_zip()} x '{produced}' -p<password>")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="report container, offsets, encryption, completeness")
    analyze.add_argument("file")
    analyze.add_argument("--deep", action="store_true", help="scan the whole file for archive signatures (slow on big files)")
    analyze.set_defaults(func=cmd_analyze)

    repair = sub.add_parser("repair", help="produce an archive that standard tools accept")
    repair.add_argument("file")
    repair.add_argument("--out")
    repair.add_argument("--strip", action="store_true", help="copy without the prefix instead of rewriting offsets")
    repair.add_argument("--force", action="store_true")
    repair.set_defaults(func=cmd_repair)

    verify = sub.add_parser("verify", help="check the password against the archive's own hash before extracting")
    verify.add_argument("file")
    verify.add_argument("--password")
    verify.set_defaults(func=cmd_verify)

    extract = sub.add_parser("extract", help="unpack with 7-Zip and name the next layer")
    extract.add_argument("file")
    extract.add_argument("--password")
    extract.add_argument("-o", "--out")
    extract.set_defaults(func=cmd_extract)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
