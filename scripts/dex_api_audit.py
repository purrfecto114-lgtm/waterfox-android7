#!/usr/bin/env python3
"""
dex_api_audit.py — APK 全量 API 调用审计（对比 API 24 android.jar）

方法：直接解析 APK 内所有 .dex 的 method_ids / field_ids（= 所有被引用的
framework 方法/字段），与 android-24 android.jar 的 stub 类符号集合做差集。
命中 = 运行时 NoSuchMethodError / NoSuchFieldError 点（真实崩溃面）。

不依赖 androguard，纯 stdlib 解析 DEX 与 .class 二进制。
"""
import io
import json
import struct
import sys
import zipfile
from collections import defaultdict


# ---------------------------------------------------------------- DEX 解析

def read_uleb128(buf, off):
    result = 0
    shift = 0
    while True:
        b = buf[off]
        off += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, off


def parse_dex_strings(buf, size, off):
    """返回 string 列表（按 index）"""
    id_offs = struct.unpack_from("<%dI" % size, buf, off)
    strings = []
    for so in id_offs:
        # uleb128 utf16_size + MUTF-8 bytes + NUL
        _, p = read_uleb128(buf, so)
        end = buf.index(b"\x00", p)
        try:
            s = buf[p:end].decode("utf-8")
        except UnicodeDecodeError:
            s = buf[p:end].decode("latin-1")
        strings.append(s)
    return strings


def parse_dex_types(buf, size, off, strings):
    idxs = struct.unpack_from("<%dI" % size, buf, off)
    return [strings[i] for i in idxs]


def parse_dex_protos(buf, size, off, types):
    protos = []
    for i in range(size):
        base = off + i * 12
        # shorty_idx(u4), return_type_idx(u4), parameters_off(u4)
        ret_idx, params_off = struct.unpack_from("<II", buf, base + 4)
        ret = types[ret_idx]
        params = []
        if params_off:
            n = struct.unpack_from("<I", buf, params_off)[0]
            pidx = struct.unpack_from("<%dH" % n, buf, params_off + 4)
            params = [types[j] for j in pidx]
        protos.append("(" + "".join(params) + ")" + ret)
    return protos


def parse_dex_refs(buf):
    """解析一个 dex，返回 (methods, fields) 两个 dict:
       {class_descriptor: {(name, proto/descriptor): True}}"""
    # header offsets
    (str_size, str_off, type_size, type_off, proto_size, proto_off,
     field_size, field_off, meth_size, meth_off) = struct.unpack_from(
        "<10I", buf, 0x38)
    strings = parse_dex_strings(buf, str_size, str_off)
    types = parse_dex_types(buf, type_size, type_off, strings)
    protos = parse_dex_protos(buf, proto_size, proto_off, types)

    methods = defaultdict(set)
    for i in range(meth_size):
        base = meth_off + i * 8
        class_idx, proto_idx, name_idx = struct.unpack_from("<HHI", buf, base)
        cls = types[class_idx]
        methods[cls].add((strings[name_idx], protos[proto_idx]))

    fields = defaultdict(set)
    for i in range(field_size):
        base = field_off + i * 8
        class_idx, type_idx, name_idx = struct.unpack_from("<HHI", buf, base)
        cls = types[class_idx]
        fields[cls].add((strings[name_idx], types[type_idx]))
    return methods, fields


# ------------------------------------------------------- .class (android.jar)

def parse_class_file(buf):
    """返回 (class_descriptor, super_cls, interfaces, methods, fields)"""
    if buf[:4] != b"\xca\xfe\xba\xbe":
        return None
    pos = 8
    cp_count = struct.unpack_from(">H", buf, pos)[0]
    pos += 2
    cp = [None] * cp_count
    i = 1
    while i < cp_count:
        tag = buf[pos]
        pos += 1
        if tag == 1:  # Utf8
            ln = struct.unpack_from(">H", buf, pos)[0]
            pos += 2
            try:
                cp[i] = buf[pos:pos + ln].decode("utf-8")
            except UnicodeDecodeError:
                cp[i] = buf[pos:pos + ln].decode("latin-1")
            pos += ln
        elif tag in (7, 8, 16, 19, 20):  # Class/String/MethodType/Module/Package
            cp[i] = struct.unpack_from(">H", buf, pos)[0]
            pos += 2
        elif tag == 15:  # MethodHandle
            cp[i] = (buf[pos], struct.unpack_from(">H", buf, pos + 1)[0])
            pos += 3
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):  # 4B entries
            cp[i] = struct.unpack_from(">I", buf, pos)[0]
            pos += 4
        elif tag in (5, 6):  # Long/Double 8B, two slots
            pos += 8
            i += 1
        else:
            raise ValueError("cp tag %d @%d" % (tag, pos))
        i += 1

    def u2():
        nonlocal pos
        v = struct.unpack_from(">H", buf, pos)[0]
        pos += 2
        return v

    def skip_attrs():
        nonlocal pos
        n = u2()
        for _ in range(n):
            u2()
            alen = struct.unpack_from(">I", buf, pos)[0]
            pos += 4 + alen

    u2()  # access_flags
    this_class = u2()
    super_class = u2()
    ifc = u2()
    ifaces = [struct.unpack_from(">H", buf, pos + k * 2)[0] for k in range(ifc)]
    pos += ifc * 2

    def read_members():
        members = set()
        count = u2()
        for _ in range(count):
            u2()  # access
            name_i = u2()
            desc_i = u2()
            skip_attrs()
            members.add((cp[name_i], cp[desc_i]))
        return members

    fields = read_members()
    methods = read_members()
    cls_name = cp[cp[this_class]]  # 'android/app/Activity'
    sup = cp[cp[super_class]] if super_class else None
    ifs = [cp[cp[i]] for i in ifaces]
    return "L" + cls_name + ";", ("L" + sup + ";" if sup else None), \
        ["L" + i + ";" for i in ifs], methods, fields


def load_jar_symbols(jar_path, expand_inheritance=True):
    """解析 jar 并按类层级展开继承方法/字段（stub 类不重复声明父类成员，
    而 dex method_id 的 class 是调用点静态类型，需要继承闭包才能匹配）"""
    raw = {}
    with zipfile.ZipFile(jar_path) as zf:
        for name in zf.namelist():
            if not name.endswith(".class") or name.endswith("module-info.class"):
                continue
            try:
                r = parse_class_file(zf.read(name))
            except Exception as e:
                print("  ! skip %s: %s" % (name, e), file=sys.stderr)
                continue
            if not r:
                continue
            cls, sup, ifs, m, f = r
            raw[cls] = (sup, ifs, m, f)

    if not expand_inheritance:
        methods = defaultdict(set); fields = defaultdict(set)
        for cls, (s, i, m, f) in raw.items():
            methods[cls] |= m; fields[cls] |= f
        return methods, fields

    memo = {}
    def expand(cls):
        if cls in memo:
            return memo[cls]
        memo[cls] = (set(), set())  # 防环
        if cls not in raw:
            return (set(), set())
        sup, ifs, m, f = raw[cls]
        em, ef = set(m), set(f)
        for parent in ([sup] if sup else []) + ifs:
            pm, pf = expand(parent)
            em |= pm
            ef |= pf
        memo[cls] = (em, ef)
        return memo[cls]

    methods = defaultdict(set)
    fields = defaultdict(set)
    for cls in raw:
        em, ef = expand(cls)
        methods[cls] |= em
        fields[cls] |= ef
    return methods, fields


# ------------------------------------------------------------------- main

def main():
    apk_path, jar_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

    print("[1/3] parsing android.jar (API 24) ...")
    jar_methods, jar_fields = load_jar_symbols(jar_path)
    print("      classes: methods=%d fields=%d" % (len(jar_methods), len(jar_fields)))

    print("[2/3] parsing APK dex files ...")
    zf = zipfile.ZipFile(apk_path)
    dex_names = sorted(
        n for n in zf.namelist()
        if n.endswith(".dex") and not n.startswith("assets/")
    )
    print("      dex files:", dex_names)

    # 汇总：symbol -> set(dex_idx)；以及 symbol -> 是否真被引用
    missing_methods = defaultdict(set)  # (cls, name, proto) -> {dex,...}
    missing_fields = defaultdict(set)
    # 反查命中所在 dex，也记录该 dex 是否为 primary
    for di, dn in enumerate(dex_names):
        buf = zf.read(dn)
        m, f = parse_dex_refs(buf)
        for cls, members in m.items():
            if not cls.startswith("Landroid/"):
                continue
            if cls not in jar_methods:
                continue  # 类本身 API24 就没有（类引用是 class_ids，单独风险，后面查）
            avail = jar_methods[cls]
            for (name, proto) in members:
                if (name, proto) not in avail:
                    missing_methods[(cls, name, proto)].add(di)
        for cls, members in f.items():
            if not cls.startswith("Landroid/"):
                continue
            if cls not in jar_fields:
                continue
            avail = jar_fields[cls]
            for (name, desc) in members:
                if (name, desc) not in avail:
                    missing_fields[(cls, name, desc)].add(di)
        print("      %s: refs -> missing m=%d f=%d (cumulative)"
              % (dn, len(missing_methods), len(missing_fields)))

    # 缺失类引用检查（class_defs / type_ids 里的 android 类，运行时 NoClassDefFoundError）
    print("[3/3] checking class references ...")
    missing_classes = defaultdict(set)
    for di, dn in enumerate(dex_names):
        buf = zf.read(dn)
        str_size, str_off, type_size, type_off = struct.unpack_from(
            "<4I", buf, 0x38)
        strings = parse_dex_strings(buf, str_size, str_off)
        types = parse_dex_types(buf, type_size, type_off, strings)
        for t in set(types):
            if t.startswith("Landroid/") and t not in jar_methods:
                missing_classes[t].add(di)

    result = {
        "dex_files": dex_names,
        "missing_methods": {
            "%s->%s%s" % (c, n, p): sorted(v)
            for (c, n, p), v in sorted(missing_methods.items())
        },
        "missing_fields": {
            "%s->%s:%s" % (c, n, d): sorted(v)
            for (c, n, d), v in sorted(missing_fields.items())
        },
        "missing_classes": {
            c: sorted(v) for c, v in sorted(missing_classes.items())
        },
    }
    with open(out_path, "w") as fp:
        json.dump(result, fp, indent=1)

    print()
    print("=== SUMMARY ===")
    print("missing method refs : %d" % len(missing_methods))
    print("missing field refs  : %d" % len(missing_fields))
    print("missing class refs  : %d" % len(missing_classes))
    print("full report -> %s" % out_path)


if __name__ == "__main__":
    main()
