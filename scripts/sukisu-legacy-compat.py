#!/usr/bin/env python3
"""Narrow fixes for SukiSU builtin on the backported cepheus 4.14 tree."""

import re
import sys
from pathlib import Path


def replace(path, old, new):
    text = path.read_text()
    if new in text:
        return
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected compatibility patch anchor missing")
    path.write_text(text.replace(old, new))


def main():
    kernel = Path(sys.argv[1])
    ksu = kernel / "drivers/kernelsu"
    if not re.search(r"struct avtab_node\s*\*\*htable;",
                     (kernel / "security/selinux/ss/avtab.h").read_text()):
        raise SystemExit("cepheus avtab must use backported pointer-array htable")

    replace(ksu / "kernel_includes.h",
            "#endif // __KSU_H_KERNEL_INCLUDES",
            "#ifndef fallthrough\n"
            "#define fallthrough __attribute__((__fallthrough__))\n"
            "#endif\n\n#endif // __KSU_H_KERNEL_INCLUDES")

    path = ksu / "runtime/ksud.c"
    text = path.read_text()
    for function in ("ksu_selinux_hide_handle_post_fs_data",
                     "ksu_selinux_hide_handle_second_stage"):
        # selinux_hide.c is already compiled only on 5.10+, match that guard.
        pattern = rf"(?m)^([ \t]*){function}\(\);$"
        text, count = re.subn(
            pattern,
            rf"#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"
            rf"\1{function}();\n#endif",
            text,
        )
        if not count:
            raise SystemExit(f"missing SELinux callback anchor: {function}")
    path.write_text(text)

    replace(ksu / "sulog/event.c",
            "#define USER_ARG_NULL user_arg_null_ptr()",
            "#ifdef CONFIG_KSU_SUSFS\n"
            "    #define USER_ARG_NULL user_arg_null_ptr()\n"
            "    #else\n"
            "    #define USER_ARG_NULL (*user_arg_null_ptr())\n"
            "    #endif")

    replace(ksu / "selinux/sepolicy.c",
            "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 1, 0)\n"
            "        for (n = db->te_avtab.htable[i];",
            "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 1, 0) || "
            "defined(KSU_CEPHEUS_AVTAB_POINTER_ARRAY)\n"
            "        for (n = db->te_avtab.htable[i];")
    makefile = ksu / "Makefile"
    text = makefile.read_text()
    if "-DKSU_CEPHEUS_AVTAB_POINTER_ARRAY" not in text:
        makefile.write_text(text + "\nccflags-y += -DKSU_CEPHEUS_AVTAB_POINTER_ARRAY\n")
    # builtin uses CONFIG_KSU for manual hooks but no longer declares this
    # conventional marker. Record the actual selected integration mode so it
    # survives olddefconfig and can be checked in the embedded configuration.
    kconfig = ksu / "Kconfig"
    text = kconfig.read_text()
    if not re.search(r"(?m)^config KSU_MANUAL_HOOK$", text):
        kconfig.write_text(text + "\nconfig KSU_MANUAL_HOOK\n"
                           "\tbool \"KernelSU manual source hooks\"\n"
                           "\tdepends on KSU\n"
                           "\tdefault n\n")
    print("Applied SukiSU builtin compatibility fixes for cepheus 4.14")


if __name__ == "__main__":
    main()
