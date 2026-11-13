#!/usr/bin/env python3
"""
dex_caller_audit.py — 反查缺失 API 符号的调用方

在 dex_api_audit.py 基础上解码每个方法的指令流（invoke / field / 类加载指令），
把「API 24 缺失的符号」映射到「调用者类.方法」，用于甄别：
  - androidx/kotlin 调用（库内部有版本防护，可信）
  - org/mozilla/** 调用（我们自己的源码，必须逐点核查）
"""
import json
import struct
import sys
import zipfile
from collections import defaultdict

from dex_api_audit import (
    parse_dex_strings, parse_dex_types, parse_dex_protos,
    read_uleb128, load_jar_symbols,
)

# Dalvik opcode -> 指令长度（16-bit units），0 = 特殊/payload
OPCODE_LEN = [0] * 256
for _o in [0x01, 0x04, 0x05, 0x06, 0x07 + 100]:  # placeholder
    pass
_std1 = list(range(0x0b, 0x13)) + [0x1d, 0x1e, 0x21, 0x27, 0x28] + \
        list(range(0x3e, 0x44)) + [0x73] + [0x79, 0x7a] + \
        list(range(0x90, 0xb0)) + list(range(0xe3, 0xfa))
_std2 = [0x02, 0x07, 0x08, 0x09, 0x0a, 0x13, 0x15, 0x16, 0x19, 0x1a,
         0x1c, 0x1f, 0x20, 0x22, 0x23, 0x2b, 0x2c] + list(range(0x2d, 0x32)) + \
        list(range(0x32, 0x38)) + list(range(0x44, 0x6e)) + \
        list(range(0x7b, 0x90)) + list(range(0xb0, 0xe3)) + [0xd0 - 0xd0 + 0xd0] + \
        [0xd1, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xdb,
         0xdc, 0xdd, 0xde, 0xdf, 0xe0, 0xe1, 0xe2]
_std3 = [0x03, 0x14, 0x17, 0x1b, 0x24, 0x25, 0x26, 0x29, 0x2a] + \
        list(range(0x38, 0x3e)) + list(range(0x6e, 0x73)) + \
        list(range(0x74, 0x79))
_std5 = [0x18]
for o in _std1:
    OPCODE_LEN[o] = 1
for o in _std2:
    OPCODE_LEN[o] = 2
for o in _std3:
    OPCODE_LEN[o] = 3
for o in _std5:
    OPCODE_LEN[o] = 5
for o in list(range(0xfa, 0x100)):
    OPCODE_LEN[o] = 4  # quickened（app dex 不出现）


def payload_units(insns, pc):
    """pc 指向 ident==0x00 后的 pseudo-op（0x0100/0x0200/0x0300），返回长度"""
    ident = insns[pc]
    if ident == 0x0100:  # packed-switch-payload
        size = insns[pc + 1]
        return size * 2 + 4
    if ident == 0x0200:  # sparse-switch-payload
        size = insns[pc + 1]
        return size * 4 + 2
    if ident == 0x0300:  # fill-array-data-payload
        elem_w = insns[pc + 1]
        size = struct.unpack_from("<I", insns, (pc + 2) * 2)[0]
        return (size * elem_w + 1) // 2 + 4
    return 1


def iter_class_data_methods(buf, class_defs_size, class_defs_off, types):
    """yield (caller_class, method_name, proto, code_off)"""
    for ci in range(class_defs_size):
        base = class_defs_off + ci * 32
        class_idx = struct.unpack_from("<I", buf, base)[0]
        class_data_off = struct.unpack_from("<I", buf, base + 24)[0]
        if not class_data_off:
            continue
        cls = types[class_idx]
        p = class_data_off
        sfs, p = read_uleb128(buf, p)
        ifs, p = read_uleb128(buf, p)
        dms, p = read_uleb128(buf, p)
        vms, p = read_uleb128(buf, p)
        for _ in range(sfs + ifs):  # fields
            _, p = read_uleb128(buf, p)
            _, p = read_uleb128(buf, p)
        midx = 0
        for kind, cnt in (("direct", dms), ("virtual", vms)):
            for _ in range(cnt):
                diff, p = read_uleb128(buf, p)
                _, p = read_uleb128(buf, p)     # access_flags
                code_off, p = read_uleb128(buf, p)
                midx += diff
                # method_ids entry
                mbase = struct.unpack_from("<HHI", buf, 0x58 + 4)[0:0]  # unused
                yield cls, midx, code_off


def get_method_id(buf, idx):
    mids_off = struct.unpack_from("<I", buf, 0x5C)[0]
    base = mids_off + idx * 8
    class_idx, proto_idx, name_idx = struct.unpack_from("<HHI", buf, base)
    return class_idx, proto_idx, name_idx


def get_field_id(buf, idx):
    fids_off = struct.unpack_from("<I", buf, 0x54)[0]
    base = fids_off + idx * 8
    class_idx, type_idx, name_idx = struct.unpack_from("<HHI", buf, base)
    return class_idx, type_idx, name_idx


def scan_code(buf, code_off):
    """yield (kind, idx) for invoke/field/class-loading instructions"""
    if not code_off:
        return
    regs, ins, outs, tries = struct.unpack_from("<HHHH", buf, code_off)
    debug_off, insns_size = struct.unpack_from("<II", buf, code_off + 8)
    insns = struct.unpack_from("<%dH" % insns_size, buf, code_off + 16)
    pc = 0
    n = len(insns)
    while pc < n:
        op = insns[pc] & 0xFF
        ln = OPCODE_LEN[op]
        if op == 0x00:  # nop / payload
            if pc + 1 < n and insns[pc + 1] in (0x0100, 0x0200, 0x0300):
                ln = payload_units(insns, pc + 1)
            else:
                ln = 1
        elif 0x6e <= op <= 0x72 or 0x74 <= op <= 0x78:  # invoke
            yield ("m", insns[pc + 1])
        elif 0x52 <= op <= 0x6d:  # iget/iput/sget/sput
            yield ("f", insns[pc + 1])
        elif op in (0x1c, 0x1f, 0x20, 0x22, 0x23, 0x24, 0x25):  # 类加载/校验
            yield ("t", insns[pc + 1])
        pc += ln


def main():
    apk_path, jar_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    print("[1/3] android.jar (API 24) symbols ...")
    jar_methods, jar_fields = load_jar_symbols(jar_path)

    print("[2/3] scanning APK instruction streams ...")
    zf = zipfile.ZipFile(apk_path)
    dex_names = sorted(n for n in zf.namelist()
                       if n.endswith(".dex") and not n.startswith("assets/"))

    call_sites = defaultdict(set)      # symbol -> {(caller_cls, caller_method)}
    class_sites = defaultdict(set)     # missing class -> {(caller, method)}
    fids_off = mids_off = 0

    for di, dn in enumerate(dex_names):
        buf = zf.read(dn)
        (str_size, str_off, type_size, type_off, proto_size, proto_off,
         field_size, field_off, meth_size, meth_off,
         class_defs_size, class_defs_off) = struct.unpack_from("<12I", buf, 0x38)
        strings = parse_dex_strings(buf, str_size, str_off)
        types = parse_dex_types(buf, type_size, type_off, strings)
        protos = parse_dex_protos(buf, proto_size, proto_off, types)

        # 预构建 method_id/field_id 全表（快）
        mid_tbl = []
        for i in range(meth_size):
            c, p, n = struct.unpack_from("<HHI", buf, meth_off + i * 8)
            mid_tbl.append((types[c], strings[n], protos[p]))
        fid_tbl = []
        for i in range(field_size):
            c, t, n = struct.unpack_from("<HHI", buf, field_off + i * 8)
            fid_tbl.append((types[c], strings[n], types[t]))

        for cls, midx, code_off in iter_class_data_methods(
                buf, class_defs_size, class_defs_off, types):
            tcls, mname, _proto = mid_tbl[midx]
            caller = (tcls, mname)
            for kind, idx in scan_code(buf, code_off):
                if kind == "m":
                    tc, tn, tp = mid_tbl[idx]
                    if tc.startswith("Landroid/") and tc in jar_methods:
                        if (tn, tp) not in jar_methods[tc]:
                            call_sites["%s->%s%s" % (tc, tn, tp)].add(caller)
                elif kind == "f":
                    tc, tn, td = fid_tbl[idx]
                    if tc.startswith("Landroid/") and tc in jar_fields:
                        if (tn, td) not in jar_fields[tc]:
                            call_sites["%s->%s:%s" % (tc, tn, td)].add(caller)
                else:  # class ref
                    t = types[idx]
                    if t.startswith("Landroid/") and t not in jar_methods:
                        class_sites[t].add(caller)
        print("      %s done (calls=%d, classrefs=%d)"
              % (dn, len(call_sites), len(class_sites)))

    print("[3/3] writing report ...")
    def ser(sites):
        out = {}
        for sym, callers in sites.items():
            out[sym] = sorted(
                "%s#%s" % (c[0], c[1]) for c in callers)
        return out

    with open(out_path, "w") as fp:
        json.dump({
            "dex_files": dex_names,
            "call_sites": ser(call_sites),
            "class_sites": ser(class_sites),
        }, fp, indent=1)

    print("call-site symbols: %d" % len(call_sites))
    print("class-ref symbols: %d" % len(class_sites))
    print("report -> %s" % out_path)


if __name__ == "__main__":
    main()
