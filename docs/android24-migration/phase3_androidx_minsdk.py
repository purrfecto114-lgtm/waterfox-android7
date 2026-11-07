#!/usr/bin/env python3
"""Phase 3: 从 libs.versions.toml 提取 androidx 依赖, 下载 AAR 实测 minSdkVersion."""
import re, json, sys, zipfile, io, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path("/home/z/my-project/Waterfox-Android")
TOML = REPO / "gradle/libs.versions.toml"
GM = "https://dl.google.com/android/maven2"
NS = "{http://schemas.android.com/apk/res/android}"

text = TOML.read_text()
versions, libraries = {}, {}
section = None
for line in text.splitlines():
    s = line.strip()
    if s.startswith("[") and s.endswith("]"):
        section = s[1:-1]
        continue
    m = re.match(r'^([A-Za-z0-9_.-]+)\s*=\s*"(.*)"$', s)
    if m and section == "versions":
        versions[m.group(1)] = m.group(2)
    m = re.match(r'^([A-Za-z0-9_.-]+)\s*=\s*\{(.*)\}$', s)
    if m and section == "libraries":
        body = m.group(2)
        mod = re.search(r'module\s*=\s*"([^"]+)"', body)  # "group:artifact"
        g = re.search(r'group\s*=\s*"([^"]+)"', body)
        n = re.search(r'name\s*=\s*"([^"]+)"', body)
        v = re.search(r'version\.ref\s*=\s*"([^"]+)"', body)
        vm = re.search(r'version\s*=\s*"([^"]+)"', body)
        if mod:
            gg, _, nn = mod.group(1).partition(":")
            group, artifact = gg, nn
        elif g and n:
            group, artifact = g.group(1), n.group(1)
        else:
            continue
        ver = versions.get(v.group(1)) if v else (vm.group(1) if vm else None)
        libraries[m.group(1)] = (group, artifact, ver)

ax = {k: v for k, v in libraries.items() if v[0].startswith("androidx.")}
print(f"androidx 直接依赖: {len(ax)} 个", file=sys.stderr)

def parse_manifest(axml_bytes):
    """AXML 二进制或纯文本 XML -> minSdkVersion int 或 None."""
    # 先试纯文本
    if axml_bytes[:5] == b"<?xml" or axml_bytes[:9] == b"<manifest":
        root = ET.fromstring(axml_bytes.decode("utf-8", "replace"))
    else:
        from pyaxmlparser import axmlprinter
        pp = axmlprinter.AXMLPrinter(axml_bytes)
        root = ET.fromstring(pp.get_buff().decode("utf-8", "replace"))
    sdk = root.find("uses-sdk")
    if sdk is None:
        return None
    raw = sdk.get(NS + "minSdkVersion", "1")
    return int(raw)

def get_min_sdk(group, artifact, version):
    url = f"{GM}/{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.aar"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "phase3-scan"})
        data = urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:
        return None, f"download-fail: {type(e).__name__}"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            axml = z.read("AndroidManifest.xml")
    except KeyError:
        return None, "no-manifest"
    try:
        return parse_manifest(axml), "ok"
    except Exception as e:
        return None, f"parse-fail: {type(e).__name__}: {str(e)[:80]}"

# compose-bom: POM 提取子库版本
compose_targets = {}
bom_ver = versions.get("compose-bom")
if bom_ver:
    bom_url = f"{GM}/androidx/compose/compose-bom/{bom_ver}/compose-bom-{bom_ver}.pom"
    try:
        req = urllib.request.Request(bom_url, headers={"User-Agent": "phase3-scan"})
        pom = urllib.request.urlopen(req, timeout=60).read().decode()
        for m in re.finditer(r"<artifactId>([\w.-]+)</artifactId>\s*<version>([^<]+)</version>", pom):
            compose_targets[m.group(1)] = m.group(2)
    except Exception as e:
        print(f"BOM 下载失败: {e}", file=sys.stderr)
print(f"compose-bom {bom_ver} 子库: {len(compose_targets)} 个", file=sys.stderr)

results, errors = {}, {}
for alias, (group, artifact, ver) in sorted(ax.items()):
    if not ver:
        continue
    ms, status = get_min_sdk(group, artifact, ver)
    key = f"{group}:{artifact}:{ver}"
    (results if ms is not None else errors)[key] = ms if ms is not None else status

CG = {"ui": "androidx.compose.ui", "ui-text": "androidx.compose.ui", "ui-graphics": "androidx.compose.ui",
      "ui-unit": "androidx.compose.ui", "ui-tooling": "androidx.compose.ui",
      "foundation": "androidx.compose.foundation", "foundation-layout": "androidx.compose.foundation",
      "material3": "androidx.compose.material3", "material": "androidx.compose.material",
      "material-icons-core": "androidx.compose.material", "material-icons-extended": "androidx.compose.material",
      "runtime": "androidx.compose.runtime", "animation": "androidx.compose.animation"}
for art, cver in compose_targets.items():
    if art in CG:
        ms, status = get_min_sdk(CG[art], art, cver)
        key = f"{CG[art]}:{art}:{cver}"
        if ms is None:
            errors[key] = status
        else:
            results[key] = ms

outdir = Path("/home/z/my-project/download/waterfox-android24-migration")
outdir.mkdir(exist_ok=True, parents=True)
(outdir / "phase3_androidx_minsdk.json").write_text(
    json.dumps({"results": {k: v for k, v in results.items()},
                "errors": errors}, indent=2, ensure_ascii=False))

print("\n===== minSdk 实测结果 =====")
over = {k: v for k, v in results.items() if isinstance(v, int) and v > 24}
ok = {k: v for k, v in results.items() if isinstance(v, int) and v <= 24}
print(f"\n[需处理] minSdk > 24: {len(over)} 个")
for k, v in sorted(over.items()):
    print(f"  {v}: {k}")
print(f"\n[无需处理] minSdk <= 24: {len(ok)} 个")
for k, v in sorted(ok.items()):
    print(f"  {v}: {k}")
print(f"\n[解析失败] {len(errors)} 个")
for k, v in sorted(errors.items()):
    print(f"  {v}: {k}")
