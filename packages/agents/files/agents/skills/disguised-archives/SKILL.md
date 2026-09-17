---
name: disguised-archives
description: Open archives that refuse to extract, especially netdisk releases where a real zip/rar/7z is appended to a small valid .mp4/.png and then renamed to .zip. Covers "Is not archive" and "cannot open the file" errors, and WinZip-AES (method 99) entries that Ark, file-roller and unzip reject.
---

# Disguised archives

Netdisk releases hide the archive: a few MB of genuine video, then the `.zip` bytes, extension renamed to `.zip`. WinRAR tolerates the result, which is why the notes name WinRAR as the only tool; on Linux nothing opens it as-is. Two independent blockers, either one fatal:

- The media prefix shifts every byte position, and these packers wrote the ZIP64 offsets relative to the archive start, ignoring the prefix.
- The outer layer is usually WinZip-AES (method 99), which only 7-Zip and WinRAR decrypt.

Drive both through `scripts/disguised_archive.py` (stdlib only, locates 7-Zip itself):

```bash
uv run --no-project <skill-dir>/scripts/disguised_archive.py analyze FILE
```

## 1. Read the diagnosis

`analyze` prints the leading file type, the offset of the first archive signature, the ZIP64 layout, per-entry encryption, and whether the payload is shorter than the directory declares.

Completion: you can name what the file really is, which blocker stops extraction, and whether the download itself is complete.

## 2. Repair, then extract

```bash
... repair FILE                    # reflink copy + offsets rewritten: instant, no extra space on btrfs/xfs
... repair FILE --strip            # byte-range copy without the prefix: for rar/7z, or foreign filesystems
... verify FILE --password '<password>'   # cheap head check, plus the SHA-256 these packs embed in the archive comment
... extract FILE --password '<password>'  # 7-Zip unpacks, then the script names the next layer
```

Completion: `repair` reports "accepted by 7-Zip", and `verify` reports a hash MATCH — before a multi-GB write is spent. Repair always writes a new file; the download stays untouched.

## 3. The next layer

A nested archive has its own password, which no generic rule predicts: take the candidates from that release's notes, and treat a failure as per-layer, not per-file. Unpack with `unrar x -p'<password>' FILE`; a RAR with encrypted headers answers `Incorrect password` when the guess is wrong, so the error names the layer that needs a different candidate.

## Reference

**Extractors on Linux, measured** against a WinZip-AES-256 zip entry:

| Tool | Result |
|---|---|
| `7z` / `7zz` / `7za` / p7zip (GUI: PeaZip) | decrypts |
| `ark`, `file-roller`, `bsdtar` (libarchive) | `need PK compat. v5.1` |
| `unzip` (Info-ZIP) | exit 81 |
| python `zipfile` | `NotImplementedError` |
| WinRAR | decrypts, but has no Linux build (`unrar` handles RAR only) |

Listing works in most of these; only decryption separates them. So "it opens but extraction fails" and "it does not even open" are different branches: the first is AES, the second is the prefix.

**Manual fallback** without the script:

```bash
python3 -c "print(open('FILE','rb').read(64<<20).find(b'PK\x03\x04'))"   # offset of the real archive start
dd if=FILE of=fixed.zip bs=1M iflag=skip_bytes skip=<that offset>        # strip the prefix -> a standard zip
```

Use `analyze --deep` when no signature shows up in the head: it scans the whole file and lists every hit, including the decoy `Rar!`/`7z` signatures these packs append after the archive end (they are not openable; the trailing bytes are noise). Autodetecting tools get misled by them, so force the handler when in doubt: `7z l -tzip FILE`.

**Why the offsets break**: the packer wrote the archive as if it started at byte 0, then prepended the video. The ZIP64 EOCD offset, the ZIP64 locator offset, and every entry's local-header offset therefore sit `prefix_len` bytes early; a reader that trusts them lands inside encrypted payload and reports the file as not an archive. `repair` rewrites exactly those fields, and only after the local header signature (and name) matches at the target position.

**After editing the script**, `bash scripts/selftest.sh` builds 8 fixtures and runs 18 checks covering both the reflink and strip paths; point `TMPDIR` at a btrfs/xfs directory to include the reflink path.
