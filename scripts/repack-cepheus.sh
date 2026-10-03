#!/usr/bin/env bash
# Reuse a verified Actions-built kernel; no local or repeated kernel compilation.
set -euo pipefail

SOURCE=$(realpath "${1:?source boot image required}")
IMAGE=$(realpath "${2:?Image.gz-dtb required}")
OUTPUT=$(realpath -m "${3:?output directory required}")
MAGISKBOOT=$(realpath "${MAGISKBOOT:?magiskboot path required}")
VERIFY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/verify_cepheus.py"

mkdir -p "$OUTPUT"
python3 "$VERIFY" --image "$IMAGE" --source "$SOURCE" --output "$OUTPUT"
TASK_TMP=$(mktemp -d)
trap 'rm -rf "$TASK_TMP"' EXIT
mkdir "$TASK_TMP/source" "$TASK_TMP/new" "$TASK_TMP/verify"

cd "$TASK_TMP/source"
"$MAGISKBOOT" unpack -n -h "$SOURCE"
# Preserve compressed stock ramdisk exactly, including init and SELinux policy.
cp ramdisk.cpio "$TASK_TMP/stock-ramdisk"

cd "$TASK_TMP/new"
# split decompresses Image.gz-dtb into a raw Image and its appended DTBs.
# Copy both separately so the old DTBs cannot be appended a second time.
"$MAGISKBOOT" split "$IMAGE"
cp kernel kernel_dtb "$TASK_TMP/source/"

cd "$TASK_TMP/source"
"$MAGISKBOOT" repack "$SOURCE" "$OUTPUT/boot-sukisu.img"

cd "$TASK_TMP/verify"
"$MAGISKBOOT" unpack -n -h "$OUTPUT/boot-sukisu.img"
cmp ramdisk.cpio "$TASK_TMP/stock-ramdisk"
python3 "$VERIFY" --image "$IMAGE" --source "$SOURCE" \
    --boot "$OUTPUT/boot-sukisu.img" --output "$OUTPUT"
