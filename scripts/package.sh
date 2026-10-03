#!/usr/bin/env bash
# Package build output: AnyKernel3 flashable zip and, optionally, a boot image.

set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

KERNEL_DIR=${KERNEL_DIR:?KERNEL_DIR must be set}
WORKSPACE=${WORKSPACE:-$(cd "${KERNEL_DIR}/.." && pwd)}
ARCH=${ARCH:-arm64}
BOOT_OUT="${KERNEL_DIR}/out/arch/${ARCH}/boot"
AK3="${WORKSPACE}/AnyKernel3"

make_anykernel3() {
	group "Building AnyKernel3 package"
	rm -rf "$AK3"

	if is_true "${USE_CUSTOM_ANYKERNEL3:-false}"; then
		local src=${CUSTOM_ANYKERNEL3_SOURCE:?CUSTOM_ANYKERNEL3_SOURCE required}
		case "$src" in
			*.tar.gz | *.tgz)
				fetch "$src" "${WORKSPACE}/ak3.tar.gz"
				extract_archive "${WORKSPACE}/ak3.tar.gz" "$AK3" ;;
			*.zip)
				fetch "$src" "${WORKSPACE}/ak3.zip"
				extract_archive "${WORKSPACE}/ak3.zip" "$AK3" ;;
			*git*)
				retry 3 git clone -q --depth=1 ${CUSTOM_ANYKERNEL3_BRANCH:+-b "$CUSTOM_ANYKERNEL3_BRANCH"} \
					"$src" "$AK3" || die "failed to clone ${src}" ;;
			*)
				fetch "$src" "${WORKSPACE}/ak3.zip"
				extract_archive "${WORKSPACE}/ak3.zip" "$AK3" ;;
		esac
	else
		retry 3 git clone -q --depth=1 https://github.com/osm0sis/AnyKernel3 "$AK3" \
			|| die "failed to clone AnyKernel3"
		# Device checks are meaningless here: we do not know the target's
		# ro.product.device, and the zip is flashed deliberately by its builder.
		sed -i 's/do.devicecheck=1/do.devicecheck=0/g' "${AK3}/anykernel.sh"
		sed -i 's!BLOCK=/dev/block/platform/omap/omap_hsmmc.0/by-name/boot;!BLOCK=auto;!g' "${AK3}/anykernel.sh"
		sed -i 's/IS_SLOT_DEVICE=0;/is_slot_device=auto;/g' "${AK3}/anykernel.sh"
	fi

	if [ "${KERNEL_CONFIG##*/}" = "cepheus_defconfig" ] && ! is_true "${USE_CUSTOM_ANYKERNEL3:-false}"; then
		# The upstream template contains sample tuna ramdisk/fstab modifications.
		# For this profile only replace the kernel and enforce the device check.
		cp "$(dirname "${BASH_SOURCE[0]}")/../boot/anykernel-cepheus.sh" "${AK3}/anykernel.sh"
	fi

	cp "${BOOT_OUT}/${KERNEL_IMAGE_NAME}" "${AK3}/" \
		|| die "kernel image missing at ${BOOT_OUT}/${KERNEL_IMAGE_NAME}"
	if is_true "${CHECK_DTBO_IS_OK:-false}"; then
		cp "${BOOT_OUT}/dtbo.img" "${AK3}/"
	fi
	rm -rf "${AK3}/.git" "${AK3}/.github" "${AK3}/README.md"

	local zipname="AnyKernel3${LOCALVERSION:-}${UPLOADNAME:-}-${DEVICE}-${BUILD_TIME}.zip"
	( cd "$AK3" && zip -r9 "${WORKSPACE}/${zipname}" . )
	cp -f "${WORKSPACE}/${zipname}" "${AK3}/"
	ok "AnyKernel3 package assembled and zipped: ${zipname}"
	endgroup
}

make_boot_image() {
	if [ "${KERNEL_CONFIG##*/}" = "cepheus_defconfig" ] &&
		[ "${KSU_VARIANT:-}" = "sukisu-ultra" ]; then
		make_cepheus_boot
		return
	fi
	is_true "${BUILD_BOOT_IMG:-false}" || return 0
	group "Repacking boot image"

	local tools="${WORKSPACE}/tools"
	[ -x "${tools}/unpack_bootimg.py" ] || [ -f "${tools}/unpack_bootimg.py" ] \
		|| die "mkbootimg tools not found at ${tools}"

	fetch "${SOURCE_BOOT_IMAGE:?SOURCE_BOOT_IMAGE required}" "${WORKSPACE}/boot-source.img"

	cd "$WORKSPACE"
	local fmt
	fmt=$(python3 "${tools}/unpack_bootimg.py" --boot_img boot-source.img --format mkbootimg) \
		|| die "failed to read the source boot image"
	info "source boot image args: ${fmt}"

	python3 "${tools}/unpack_bootimg.py" --boot_img boot-source.img >/dev/null \
		|| die "failed to unpack the source boot image"

	cp "${BOOT_OUT}/${KERNEL_IMAGE_NAME}" "${WORKSPACE}/out/kernel" \
		|| die "could not stage the new kernel into the unpacked ramdisk"

	# shellcheck disable=SC2086
	python3 "${tools}/mkbootimg.py" $fmt -o boot.img || die "mkbootimg failed"
	[ -s "${WORKSPACE}/boot.img" ] || die "boot.img was not produced"

	ok "boot.img built ($(du -h "${WORKSPACE}/boot.img" | cut -f1))"
	export_env MAKE_BOOT_IMAGE_IS_OK true
	endgroup
}

make_cepheus_boot() {
	group "Repacking verified cepheus PixelOS 15 boot on Actions"
	[ "${GITHUB_ACTIONS:-false}" = "true" ] || die "cepheus delivery must be built on GitHub Actions"
	local repo tools delivery
	repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
	tools="${WORKSPACE}/magiskboot-tools"
	delivery="${WORKSPACE}/delivery"
	mkdir -p "$tools" "$delivery"
	python3 "${repo}/scripts/test_verify_cepheus.py"
	fetch "https://github.com/topjohnwu/Magisk/releases/download/v30.7/Magisk-v30.7.apk" "${tools}/Magisk-v30.7.apk"
	echo "e0d32d2123532860f97123d927b1bb86c4e08e6fd8a48bfc6b5bee0afae9ebd5  ${tools}/Magisk-v30.7.apk" | sha256sum -c -
	unzip -p "${tools}/Magisk-v30.7.apk" lib/x86_64/libmagiskboot.so > "${tools}/magiskboot"
	chmod +x "${tools}/magiskboot"
	echo "a18ecbd7981179494b7d281453d6c4e25b5c719e7d2ef7f6eba3c6be3043c58e  ${tools}/magiskboot" | sha256sum -c -
	gzip -dc "${repo}/boot/cepheus-pixelos15.img.gz" > "${WORKSPACE}/cepheus-stock.img"
	MAGISKBOOT="${tools}/magiskboot" bash "${repo}/scripts/repack-cepheus.sh" \
		"${WORKSPACE}/cepheus-stock.img" "${BOOT_OUT}/${KERNEL_IMAGE_NAME}" "$delivery"
	cp "${delivery}/boot-sukisu.img" "${WORKSPACE}/boot.img"
	cp "${BOOT_OUT}/${KERNEL_IMAGE_NAME}" "$delivery/"
	cp "${WORKSPACE}"/AnyKernel3*.zip "$delivery/"
	cp "${KERNEL_DIR}/out/.config" "${delivery}/build.config"
	{
		echo "actions_run=${GITHUB_RUN_ID}"
		echo "workflow_commit=${GITHUB_SHA}"
		echo "kernel_commit=$(git -C "$KERNEL_DIR" rev-parse HEAD)"
		echo "sukisu_commit=$(git -C "${KERNEL_DIR}/drivers/kernelsu" rev-parse HEAD)"
		echo "device_boot_test=not_performed"
	} > "${delivery}/provenance.txt"
	(cd "$delivery" && sha256sum boot-sukisu.img Image.gz-dtb ./*.zip > SHA256SUMS)
	export_env MAKE_BOOT_IMAGE_IS_OK true
	endgroup
}

write_summary() {
	summary ""
	summary "### Build artifacts"
	summary ""
	summary "| Artifact | Size |"
	summary "| --- | --- |"
	local f
	for f in "${BOOT_OUT}/${KERNEL_IMAGE_NAME}" "${BOOT_OUT}/dtbo.img" "${WORKSPACE}/boot.img"; do
		[ -f "$f" ] && summary "| \`$(basename "$f")\` | $(du -h "$f" | cut -f1) |"
	done
	[ -d "$AK3" ] && summary "| \`AnyKernel3\` (flashable zip) | $(du -sh "$AK3" | cut -f1) |"
	summary ""
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
	case "${1:-all}" in
		anykernel3) make_anykernel3 ;;
		bootimg)    make_boot_image ;;
		all)        make_anykernel3; make_boot_image; write_summary ;;
		*) die "unknown package step '$1'" ;;
	esac
fi
