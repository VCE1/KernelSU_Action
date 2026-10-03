#!/usr/bin/env python3
"""Synthetic fixtures only: these tests never compile a kernel."""

import contextlib
import gzip
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verify_cepheus as verify


CONFIG = (
    "CONFIG_KSU=y\nCONFIG_KSU_MANUAL_HOOK=y\nCONFIG_KSU_FEATURE_ADBROOT=y\n"
    "# CONFIG_KSU_SUSFS is not set\n"
)


def image(config=CONFIG):
    raw = bytearray(64)
    raw[56:60] = b"ARMd"
    raw += b"IKCFG_ST" + gzip.compress(config.encode()) + b"IKCFG_ED"
    dtb = struct.pack(">10I", 0xD00DFEED, 40, 0, 0, 0, 17, 16, 0, 0, 0)
    return bytes(raw), dtb, gzip.compress(raw) + dtb


def boot(kernel, ramdisk=b"stock ramdisk", cmdline=b"cepheus"):
    header = bytearray(4096)
    header[:8] = b"ANDROID!"
    struct.pack_into("<10I", header, 8, len(kernel), 32768, len(ramdisk),
                     16777216, 0, 0, 256, 4096, 0, (15 << 25) | (25 << 4) | 1)
    header[64:64 + len(cmdline)] = cmdline
    pad = lambda data: data + bytes((-len(data)) % 4096)
    return bytes(header) + pad(kernel) + pad(ramdisk)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw, self.dtbs, data = image()
        self.image = self.root / "Image.gz-dtb"
        self.image.write_bytes(data)
        self.source = self.root / "source.img"
        self.source.write_bytes(boot(self.raw + self.dtbs))
        self.packed = self.root / "boot-sukisu.img"
        self.packed.write_bytes(self.source.read_bytes())
        self.out = self.root / "out"

    def check(self):
        argv = ["verify", "--image", str(self.image), "--source", str(self.source),
                "--boot", str(self.packed), "--output", str(self.out)]
        with patch.object(sys, "argv", argv), patch.object(
            verify, "SOURCE_SHA256", verify.sha256(self.source.read_bytes())
        ), contextlib.redirect_stdout(io.StringIO()):
            verify.main()

    def test_valid_raw_kernel(self):
        self.check()
        self.assertEqual((self.out / "kernel.config").read_text(), CONFIG)

    def test_valid_gzip_kernel(self):
        self.packed.write_bytes(boot(gzip.compress(self.raw) + self.dtbs))
        self.check()

    def test_missing_root_rejected(self):
        self.image.write_bytes(image(CONFIG.replace("CONFIG_KSU=y\n", ""))[2])
        with self.assertRaisesRegex(SystemExit, "CONFIG_KSU=y"):
            self.check()

    def test_susfs_rejected(self):
        self.image.write_bytes(image(CONFIG.replace(
            "# CONFIG_KSU_SUSFS is not set", "CONFIG_KSU_SUSFS=y"))[2])
        with self.assertRaisesRegex(SystemExit, "CONFIG_KSU_SUSFS"):
            self.check()

    def test_bad_dtb_rejected(self):
        self.image.write_bytes(gzip.compress(self.raw) + bytes(40))
        with self.assertRaisesRegex(SystemExit, "DTB"):
            self.check()

    def test_changed_ramdisk_rejected(self):
        self.packed.write_bytes(boot(self.raw + self.dtbs, ramdisk=b"modified"))
        with self.assertRaisesRegex(SystemExit, "ramdisk changed"):
            self.check()

    def test_changed_cmdline_rejected(self):
        self.packed.write_bytes(boot(self.raw + self.dtbs, cmdline=b"other device"))
        with self.assertRaisesRegex(SystemExit, "command line changed"):
            self.check()

    def test_duplicated_dtbs_rejected(self):
        self.packed.write_bytes(boot(self.raw + self.dtbs + self.dtbs))
        with self.assertRaisesRegex(SystemExit, "kernel/DTBs"):
            self.check()


if __name__ == "__main__":
    unittest.main()
