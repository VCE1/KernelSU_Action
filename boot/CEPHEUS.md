# cepheus / PixelOS 15 source boot

`cepheus-pixelos15.img.gz` is a lossless gzip copy of the existing user-supplied
`/nas/cepheus_kernel/boot.img`. Its decompressed SHA-256 is:

```text
9ceb4c8f56ff0f7ae339ed6d272232fe1074460f36c9af58e5a0da0d329c70f8
```

Header: Android 15.0.0, security patch 2025-01, header version 0, page size 4096,
original partition dump size 134217728 bytes. The command line identifies the
Qualcomm UFS device and `a600000.dwc3` USB controller.

Do NOT use the older generic `boot/boot.img` for cepheus: its header identifies
Android 13 (2023-04), a different SDHCI boot device, and a different USB controller.
It is retained unchanged for provenance.

Workflow `Repack cepheus boot` accepts a successful `Build Kernel` run ID, reuses
that run's artifacts, verifies the embedded root configuration and DTB structure,
and repacks on a GitHub-hosted runner with pinned official `magiskboot`.
It does not compile locally, inject Magisk, change the stock ramdisk, publish a
release, flash a device, or claim an on-device boot/root test.

The included cepheus-only AnyKernel3 script replaces the kernel without the
upstream template's sample tuna ramdisk/fstab edits.
