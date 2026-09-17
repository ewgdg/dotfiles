#!/usr/bin/env bash
# Fixture-driven check for disguised_archive.py. Run it after editing the script:
#
#   bash scripts/selftest.sh
#
# Needs 7-Zip and python3. Uses a reflink-capable directory under $HOME when the
# filesystem has one, so the "rewrite offsets in a reflinked copy" path is covered
# as well; otherwise only the strip fallback runs. Point TMPDIR at a btrfs/xfs
# directory (e.g. TMPDIR=$HOME/.cache) to cover the reflink path.
set -euo pipefail

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tool="$skill_dir/scripts/disguised_archive.py"
command -v 7z >/dev/null || { echo "7-Zip is required for the self-test" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"

reflink_dir=""
if cp --reflink=always /etc/hostname "$work/.probe" 2>/dev/null; then
  reflink_dir="$HOME/.cache/disguised-archive-selftest"
  mkdir -p "$reflink_dir"
  echo "reflink available; the offset-rewrite path is tested in $reflink_dir"
else
  echo "no reflink here; only the strip fallback is tested"
fi

pass=0
check() { # check <label> <expected substring> <output file>
  local label="$1" needle="$2" file="$3"
  if grep -qF -- "$needle" "$file"; then
    echo "  ok    $label"
    pass=$((pass + 1))
  else
    echo "  FAIL  $label: expected '$needle' in $file:" >&2
    cat "$file" >&2
    exit 1
  fi
}

# ---------------------------------------------------------------- fixtures
mkdir -p data/sub
echo "hello world" > data/a.txt
head -c 300000 /dev/urandom > data/sub/b.bin
7z a -tzip -bso0 -bsp0 plain.zip ./data >/dev/null
7z a -tzip -psecret -mem=AES256 -bso0 -bsp0 aes.zip ./data >/dev/null
head -c 1048576 /dev/urandom > prefix.bin
printf '\x00\x00\x00\x14ftypisom\x00\x00\x00\x01isom' | dd of=prefix.bin bs=1 seek=0 conv=notrunc status=none
cat prefix.bin plain.zip > disguised.zip
cat prefix.bin aes.zip > disguised_aes.zip

# Hand-built ZIP64 archives whose offsets ignore the prefix, the way the packers
# write them: declared positions are relative to the archive start.
python3 - "$work" <<'PY'
import struct, sys, zlib
from pathlib import Path

work = Path(sys.argv[1])
payload = b"zip64 payload\n" * 100
crc = zlib.crc32(payload)
name = "inner/文件.bin".encode()
data_at = 30 + len(name)
cd_at = data_at + len(payload)
extra = struct.pack("<HHQQ", 0x0001, 16, len(payload), len(payload))
cd_size = 46 + len(name) + len(extra)

local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 45, 0, 0, 0, 0, crc, len(payload), len(payload), len(name), 0) + name + payload
cd = struct.pack(
    "<IHHHHHHIIIHHHHHII", 0x02014B50, 45, 45, 0, 0, 0, 0, crc, 0xFFFFFFFF, 0xFFFFFFFF, len(name), len(extra), 0, 0, 0, 0, 0
) + name + extra
zip64_eocd = struct.pack("<IQHHIIQQQQ", 0x06064B50, 44, 45, 45, 0, 0, 1, 1, cd_size, cd_at)
locator = struct.pack("<IIQI", 0x07064B50, 0, cd_at + cd_size, 1)
eocd = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, 0xFFFFFFFF, 0xFFFFFFFF, 0)
torso = local + cd + zip64_eocd + locator + eocd
prefix = b"\x00\x00\x00\x18ftypisom" + bytes(500)
(work / "zip64_relative.zip").write_bytes(prefix + torso)
# Same archive with 4 KiB cut out of the payload: every recorded offset is now stale.
(work / "zip64_short.zip").write_bytes(prefix + local[: data_at + 100] + local[data_at + 4196 :] + cd + zip64_eocd + locator + eocd)
print(f"built zip64 fixtures: directory at {cd_at}, {cd_size} bytes")
PY

printf 'not an archive at all\n' > notes.txt

# ---------------------------------------------------------------- assertions
echo "analyze"
"$tool" analyze plain.zip > plain.out
check "plain zip needs no repair" "offset shift    none" plain.out
"$tool" analyze disguised.zip > disguised.out
check "disguised zip reports the prefix" "archive found   zip signature at offset 1,048,576" disguised.out
check "disguised zip reports the shift" "offsets ignore the prefix" disguised.out
check "disguised zip payload is complete" "payload check   complete" disguised.out
"$tool" analyze disguised_aes.zip > aes.out
check "aes strength reported" "AES-256 encrypted" aes.out
"$tool" analyze zip64_relative.zip > zip64.out
check "zip64 directory located" "central dir     declared 1,446  actual 1,958" zip64.out
check "zip64 shift detected" "offset shift    512 bytes" zip64.out
"$tool" analyze zip64_short.zip > short.out
check "stale offsets flagged" "no local header at the recorded offset" short.out
"$tool" analyze notes.txt > notes.out || true
check "non-archive reported" "no archive to repair" notes.out

echo "repair"
"$tool" repair disguised.zip --out fixed-default.zip > default.out
check "repair produced an accepted copy" "accepted by" default.out
7z t fixed-default.zip >/dev/null
"$tool" repair disguised.zip --out fixed-strip.zip --strip > strip.out
check "strip mode reported" "stripped" strip.out
7z t fixed-strip.zip >/dev/null
"$tool" repair disguised_aes.zip --out fixed-aes.zip >/dev/null
7z t -psecret fixed-aes.zip >/dev/null
echo "  ok    repaired copies pass 7z t"

if [[ -n "$reflink_dir" ]]; then
  cp disguised.zip zip64_relative.zip "$reflink_dir/"
  "$tool" repair "$reflink_dir/disguised.zip" > "$reflink_dir/patch.out"
  check "reflink path used" "reflink copy" "$reflink_dir/patch.out"
  check "offsets rewritten" "local-header offset" "$reflink_dir/patch.out"
  7z t "$reflink_dir/disguised-fixed.zip" >/dev/null
  "$tool" repair "$reflink_dir/zip64_relative.zip" >/dev/null
  7z t "$reflink_dir/zip64_relative-fixed.zip" >/dev/null
  "$tool" analyze "$reflink_dir/zip64_relative-fixed.zip" > "$reflink_dir/again.out"
  check "repaired archive needs no further repair" "offset shift    none" "$reflink_dir/again.out"
  check "repaired archive is complete" "payload check   complete" "$reflink_dir/again.out"
  echo "  ok    patched copies pass 7z t"
  rm -rf "$reflink_dir"
fi

echo "extract"
rm -rf out && "$tool" extract fixed-aes.zip --password secret -o out > extract.out
cmp data/a.txt out/data/a.txt
cmp data/sub/b.bin out/data/sub/b.bin
echo "  ok    decrypted payload matches the original"
rm -rf out-plain && "$tool" extract fixed-default.zip --password unused -o out-plain >/dev/null 2>&1 || true
cmp data/a.txt out-plain/data/a.txt && cmp data/sub/b.bin out-plain/data/sub/b.bin
echo "  ok    offset-repaired copy extracts byte-identical"
if "$tool" extract fixed-aes.zip --password wrong -o out-bad >/dev/null 2>&1; then
  echo "  FAIL  wrong password was accepted" >&2
  exit 1
fi
echo "  ok    wrong password rejected"

echo "verify"
"$tool" verify fixed-aes.zip --password secret > verify.out
check "verify accepts the right password" "7-Zip accepted the password" verify.out
check "verify reports the decrypted size" "decrypted size  300,012 bytes" verify.out
if "$tool" verify fixed-aes.zip --password wrong > wrong.out 2>&1; then
  echo "  FAIL  verify accepted a wrong password" >&2
  exit 1
fi
check "verify rejects a wrong password" "wrong password" wrong.out

echo "all $pass checks passed"
