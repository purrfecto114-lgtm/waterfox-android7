#!/bin/bash
# Phase 1c: 对照 archive-1.1 (c24727e, minSdk 21, Gecko 140.8) 的低版本分支分布
# 用法: bash scan1c_archive_ref.sh
REPO="${1:-/home/z/my-project/Waterfox-Android}"
OUT="${2:-/home/z/my-project/download/waterfox-android24-migration}"
cd "$REPO" || exit 1
mkdir -p "$OUT"
ARC=archive-1.1-snapshot

{
echo "============================================================"
echo " Phase 1c: archive-1.1 (c24727e, Gecko 140.8, minSdk 21) 参照物扫描"
echo " 时间: $(date -u +'%Y-%m-%d %H:%M UTC')"
echo "============================================================"

echo
echo "## A. archive-1.1 geckoview/src/main 的 VERSION_CODES 档位分布"
git grep -o 'VERSION_CODES\.[A-Z_0-9]*' $ARC -- mobile/android/geckoview/src/main/java 2>/dev/null \
   | sed 's/.*VERSION_CODES\.//' | sort | uniq -c | sort -rn
echo "--- A2. archive-1.1 geckoview/src/main/java 带版本判断的文件数 ---"
git grep -l 'VERSION_CODES\|SDK_INT' $ARC -- mobile/android/geckoview/src/main/java 2>/dev/null | wc -l
echo "--- A3. archive-1.1 geckoview/src/main/java 中 N/M/LOLLIPOP(含) 到 N 的分支明细 ---"
git grep -n 'VERSION_CODES\.\(N\|M\|LOLLIPOP\|KITKAT\|JELLY\|BASE\)' $ARC -- mobile/android/geckoview/src/main/java 2>/dev/null | head -80

echo
echo "## B. 已被上游删除的关键类在 archive-1.1 中的位置"
echo "--- B1. GeckoMediaDrmBridge* ---"
git ls-tree -r --name-only $ARC -- mobile/android/geckoview/src/main/java | grep -i 'MediaDrm'
echo "--- B2. AsyncCodec* ---"
git ls-tree -r --name-only $ARC -- mobile/android/geckoview/src/main/java | grep -i 'AsyncCodec'
echo "--- B3. main 中的现状 ---"
ls mobile/android/geckoview/src/main/java/org/mozilla/gecko/media/ 2>/dev/null

echo
echo "## C. archive-1.1 的 coreLibraryDesugaring 配置（移植参照）"
echo "--- C1. libs.versions.toml 中 desugar ---"
git show $ARC:gradle/libs.versions.toml | grep -n -i 'desugar'
echo "--- C2. fenix build.gradle.kts 中 desugar ---"
git show $ARC:mobile/android/fenix/app/build.gradle.kts 2>/dev/null | grep -n -i -A2 -B2 'desugar' | head -30
echo "--- C3. push-firebase 中 desugar ---"
git show $ARC:mobile/android/android-components/components/lib/push-firebase/build.gradle.kts 2>/dev/null | grep -n -i -B2 -A2 'desugar' | head -30

echo
echo "## D. archive-1.1 中 App 层 (fenix+AC+focus src/main) 版本判断文件数"
git grep -l 'VERSION_CODES\|SDK_INT' $ARC -- \
  'mobile/android/fenix/app/src/main' \
  'mobile/android/android-components/components' \
  'mobile/android/focus-android/app/src/main' 2>/dev/null | wc -l

echo
echo "## E. archive-1.1 AndroidX 版本（minSdk 24 兼容参照档）"
git show $ARC:gradle/libs.versions.toml | grep -E '^(activity|appcompat|core|lifecycle|compose-bom|navigation|kotlin|android-gradle-plugin|desugar_jdk_libs) *='
} | tee "$OUT/phase1c_scan.txt"

echo; echo "输出已保存: $OUT/phase1c_scan.txt"
