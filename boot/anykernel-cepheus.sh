# AnyKernel3: kernel-only replacement for Xiaomi Mi 9 / cepheus.
properties() { '
kernel.string=REVUELTO SukiSU-Ultra - cepheus PixelOS 15 (GitHub Actions)
do.devicecheck=1
do.modules=0
do.systemless=1
do.cleanup=1
do.cleanuponabort=0
device.name1=cepheus
supported.versions=15
supported.patchlevels=
supported.vendorpatchlevels=
'; }

BLOCK=/dev/block/bootdevice/by-name/boot;
IS_SLOT_DEVICE=0;
RAMDISK_COMPRESSION=auto;
PATCH_VBMETA_FLAG=auto;

. tools/ak3-core.sh;

# No ramdisk edits, fstab patches, refresh-rate tweaks or Magisk injection.
split_boot;
flash_boot;
