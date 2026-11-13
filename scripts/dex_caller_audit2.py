#!/usr/bin/env python3
"""
dex_caller_audit2.py — 单 dex 指令级审计（并行友好版）

用法: python3 dex_caller_audit2.py <apk> <jar> <dex_index> <out.json>
优化: 内联指令循环（无生成器）、局部变量、一次性 tuple 解包。
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

OPLEN = [1] * 256
# 2 units: 22x/21c/21s/21t/22s/22b/23x/20t/31c-switch
for o in [0x02, 0x08, 0x13, 0x15, 0x16, 0x19, 0x1a, 0x1c, 0x1f,
          0x20, 0x22, 0x23, 0x29, 0x2b, 0x2c] + list(range(0x2d, 0x3e)) + \
         list(range(0x44, 0x6e)) + list(range(0x7b, 0x90)) + \
         list(range(0xb0, 0xe3)):
    OPLEN[o] = 2
# 3 units: 32x/31i/31c
for o in [0x03, 0x09, 0x14, 0x17, 0x1b, 0x24, 0x25, 0x26, 0x2a] + \
         list(range(0x6e, 0x73)) + list(range(0x74, 0x79)):
    OPLEN[o] = 3
OPLEN[0x18] = 5  # const-wide 51l
for o in range(0xfa, 0x100):
    OPLEN[o] = 4  # quickened（app dex 不出现，防御）
OPLEN = tuple(OPLEN)

# 快速判断指令是否引用 idx（invoke 0x6e-0x72,0x74-0x78 / field 0x52-0x6d / type 0x1c,1f,20,22,23,24,25)
INVOKE = frozenset(range(0x6e, 0x73)) | frozenset(range(0x74, 0x79))
FIELD = frozenset(range(0x52, 0x6e))
TYPEOP = frozenset((0x1c, 0x1f, 0x20, 0x22, 0x23, 0x24, 0x25))


def scan_dex(buf, jar_methods, jar_fields):
    (str_size, str_off, type_size, type_off, proto_size, proto_off,
     field_size, field_off, meth_size, meth_off,
     cd_size, cd_off) = struct.unpack_from("<12I", buf, 0x38)
    strings = parse_dex_strings(buf, str_size, str_off)
    types = parse_dex_types(buf, type_size, type_off, strings)
    protos = parse_dex_protos(buf, proto_size, proto_off, types)

    mid_class = [None] * meth_size
    mid_name = [None] * meth_size
    mid_key = [None] * meth_size  # "name+proto" jar 匹配键
    mid_fw = [False] * meth_size
    for i in range(meth_size):
        b = meth_off + i * 8
        c, p, n = struct.unpack_from("<HHI", buf, b)
        tc = types[c]
        mid_class[i] = tc
        mid_name[i] = strings[n]
        mid_key[i] = strings[n] + protos[p]
        mid_fw[i] = tc.startswith("Landroid/")
    fid_class = [None] * field_size
    fid_key = [None] * field_size
    fid_fw = [False] * field_size
    for i in range(field_size):
        b = field_off + i * 8
        c, t, n = struct.unpack_from("<HHI", buf, b)
        tc = types[c]
        fid_class[i] = tc
        fid_key[i] = strings[n] + types[t]
        fid_fw[i] = tc.startswith("Landroid/")
    type_fw = [t.startswith("Landroid/") for t in types]

    call_sites = defaultdict(set)
    class_sites = defaultdict(set)
    oplen = OPLEN
    invoke_ops = INVOKE
    field_ops = FIELD
    type_ops = TYPEOP
    jmeth = jar_methods
    jfield = jar_fields
    unpack_from = struct.unpack_from
    mk_call = call_sites  # alias
    n_hit_m = [0]

    for ci in range(cd_size):
        base = cd_off + ci * 32
        class_idx = unpack_from("<I", buf, base)[0]
        cd_off_item = unpack_from("<I", buf, base + 24)[0]
        if not cd_off_item:
            continue
        cls = types[class_idx]
        p = cd_off_item
        sfs, p = read_uleb128(buf, p)
        ifs_, p = read_uleb128(buf, p)
        dms, p = read_uleb128(buf, p)
        vms, p = read_uleb128(buf, p)
        for _ in range(sfs + ifs_):
            _, p = read_uleb128(buf, p)
            _, p = read_uleb128(buf, p)
        midx = 0
        total_m = dms + vms
        for _ in range(total_m):
            d, p = read_uleb128(buf, p)
            midx += d
            _, p = read_uleb128(buf, p)
            code_off, p = read_uleb128(buf, p)
            if not code_off or midx >= meth_size:
                continue
            caller = cls + "#" + mid_name[midx]
            tries = unpack_from("<H", buf, code_off + 6)[0]
            insns_size = unpack_from("<I", buf, code_off + 12)[0]
            insns = unpack_from("<%dH" % insns_size, buf, code_off + 16)
            n = insns_size
            pc = 0
            while pc < n:
                op = insns[pc] & 0xFF
                if op in invoke_ops:
                    if pc + 1 >= n:
                        break
                    idx = insns[pc + 1]
                    if idx >= meth_size:
                        break
                    if mid_fw[idx]:
                        tc = mid_class[idx]
                        avail = jmeth.get(tc)
                        if avail is None:
                            # 类本身不在 API 24：成员调用执行时必触发类加载
                            call_sites["MISSING-CLASS " + tc + "->" + mid_key[idx]].add(caller)
                        elif mid_key[idx] not in avail:
                            call_sites[tc + "->" + mid_key[idx]].add(caller)
                    pc += 3
                elif op in field_ops:
                    if pc + 1 >= n:
                        break
                    idx = insns[pc + 1]
                    if idx >= field_size:
                        break
                    if fid_fw[idx]:
                        tc = fid_class[idx]
                        avail = jfield.get(tc)
                        if avail is None:
                            call_sites["MISSING-CLASS " + tc + "->F:" + fid_key[idx]].add(caller)
                        elif fid_key[idx] not in avail:
                            call_sites[tc + "->F:" + fid_key[idx]].add(caller)
                    pc += 2
                elif op in type_ops:
                    if pc + 1 >= n:
                        break
                    idx = insns[pc + 1]
                    if idx >= type_size:
                        break
                    if type_fw[idx]:
                        t = types[idx]
                        if t not in jmeth:
                            class_sites[t].add(caller)
                    pc += oplen[op]
                elif op == 0x00:
                    if pc + 1 < n:
                        ident = insns[pc + 1]
                        if ident == 0x0100:
                            pc += insns[pc + 2] * 2 + 4
                        elif ident == 0x0200:
                            pc += insns[pc + 2] * 2 + 2
                        elif ident == 0x0300:
                            ew = insns[pc + 2]
                            if pc + 4 < n:
                                sz = insns[pc + 3] | (insns[pc + 4] << 16)
                                pc += (sz * ew + 1) // 2 + 4
                            else:
                                pc += 1
                        else:
                            pc += 1
                    else:
                        pc += 1
                else:
                    pc += oplen[op]
    return call_sites, class_sites


def main():
    apk_path, jar_path, dex_index, out_path = (
        sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4])
    _jm, _jf = load_jar_symbols(jar_path)
    # load_jar_symbols 返回 {cls: {(name, desc)}} 元组集合；转成 name+desc 字符串集合
    jar_methods = {c: {n + d for (n, d) in s} for c, s in _jm.items()}
    jar_fields = {c: {n + d for (n, d) in s} for c, s in _jf.items()}
    # 同时需要保留元组版本用于类存在性检查（jmeth 的 key 集合不受影响）
    print("jar classes:", len(jar_methods), file=sys.stderr)
    zf = zipfile.ZipFile(apk_path)
    dex_names = sorted(n for n in zf.namelist()
                       if n.endswith(".dex") and not n.startswith("assets/"))
    dn = dex_names[dex_index]
    buf = zf.read(dn)
    print("scanning", dn, len(buf), "bytes", file=sys.stderr)
    call_sites, class_sites = scan_dex(buf, jar_methods, jar_fields)
    result = {
        "dex": dn,
        "call_sites": {k: sorted(v) for k, v in sorted(call_sites.items())},
        "class_sites": {k: sorted(v) for k, v in sorted(class_sites.items())},
    }
    with open(out_path, "w") as fp:
        json.dump(result, fp, indent=1)
    print("call symbols: %d, class symbols: %d -> %s"
          % (len(call_sites), len(class_sites), out_path), file=sys.stderr)


if __name__ == "__main__":
    main()
