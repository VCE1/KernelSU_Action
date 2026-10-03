#!/usr/bin/env python3
"""Validate the embedded Kconfig and the source/repacked cepheus boot images."""

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

SOURCE_SHA256 = "9ceb4c8f56ff0f7ae339ed6d272232fe1074460f36c9af58e5a0da0d329c70f8"


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def boot(path):
    data = path.read_bytes()
    require(data[:8] == b"ANDROID!", f"{path}: not an Android boot image")
    fields = struct.unpack_from("<10I", data, 8)
    ksize, kaddr, rsize, raddr, ssize, saddr, tags, page, version, osver = fields
    require(version == 0 and page == 4096, f"{path}: unexpected boot format")
    aligned = lambda size: (size + page - 1) // page * page
    ramdisk_offset = page + aligned(ksize)
    require(ramdisk_offset + rsize <= len(data), f"{path}: truncated boot image")
    return data, {
        "kernel_addr": kaddr,
        "ramdisk_addr": raddr,
        "second_size": ssize,
        "second_addr": saddr,
        "tags_addr": tags,
        "page_size": page,
        "header_version": version,
        "os_version": osver,
        "name": data[48:64].hex(),
        "cmdline": (data[64:576] + data[608:1632]).split(b"\0")[0].decode(),
    }, data[page:page + ksize], data[ramdisk_offset:ramdisk_offset + rsize]


def kernel(image, out):
    data = image.read_bytes()
    require(data[:3] == b"\x1f\x8b\x08", "Image.gz-dtb must start with gzip")
    stream = zlib.decompressobj(31)
    raw = stream.decompress(data) + stream.flush()
    require(stream.eof, "truncated compressed kernel")
    dtbs = stream.unused_data
    require(raw[56:60] == b"ARMd", "missing arm64 Image magic")
    require(len(dtbs) > 0, "missing appended device trees")
    pos, count = 0, 0
    while pos < len(dtbs):
        require(len(dtbs) - pos >= 40, "truncated DTB header")
        magic, size = struct.unpack_from(">II", dtbs, pos)
        require(magic == 0xD00DFEED and 40 <= size <= len(dtbs) - pos,
                f"invalid appended DTB at {pos}")
        pos += size
        count += 1
    start = raw.find(b"IKCFG_ST")
    require(start >= 0, "missing embedded kernel configuration")
    cfgstream = zlib.decompressobj(31)
    config = cfgstream.decompress(raw[start + 8:]).decode()
    require(cfgstream.eof and cfgstream.unused_data.startswith(b"IKCFG_ED"),
            "invalid embedded kernel configuration")
    lines = set(config.splitlines())
    for option in (
        "CONFIG_KSU=y",
        "CONFIG_KSU_MANUAL_HOOK=y",
        "CONFIG_KSU_FEATURE_ADBROOT=y",
        "# CONFIG_KSU_SUSFS is not set",
    ):
        require(option in lines, f"missing required configuration: {option}")
    require("CONFIG_KPM=y" not in lines, "KPM should be disabled")
    out.mkdir(parents=True, exist_ok=True)
    (out / "kernel.config").write_text(config)
    report = {
        "image_sha256": sha256(data),
        "kernel_sha256": sha256(raw),
        "dtb_sha256": sha256(dtbs),
        "kernel_bytes": len(raw),
        "dtb_bytes": len(dtbs),
        "dtb_count": count,
        "root_config_verified": True,
    }
    return raw, dtbs, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--boot", type=Path)
    args = parser.parse_args()
    raw, dtbs, report = kernel(args.image, args.output)
    if args.source:
        source, header, _, ramdisk = boot(args.source)
        require(sha256(source) == SOURCE_SHA256, "source boot checksum mismatch")
        require(header["os_version"] >> 25 == 15, "source boot is not Android 15")
        report["source_boot_sha256"] = sha256(source)
        report["boot_header"] = header
        if args.boot:
            packed, packed_header, packed_kernel, packed_ramdisk = boot(args.boot)
            require(header == packed_header, "boot header/command line changed")
            require(ramdisk == packed_ramdisk, "compressed stock ramdisk changed")
            if packed_kernel.startswith(b"\x1f\x8b\x08"):
                stream = zlib.decompressobj(31)
                unpacked = stream.decompress(packed_kernel) + stream.flush()
                packed_kernel = unpacked + stream.unused_data
            require(packed_kernel == raw + dtbs,
                    "repacked kernel/DTBs do not match the Actions image")
            require(len(packed) <= len(source), "image exceeds original partition size")
            report["boot_sha256"] = sha256(packed)
            report["ramdisk_preserved"] = True
            report["boot_header_preserved"] = True
            report["repacked_kernel_verified"] = True
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
