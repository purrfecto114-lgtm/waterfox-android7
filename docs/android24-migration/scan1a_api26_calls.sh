#!/bin/bash
# Phase 1a: 扫描 main 中 API 26+ 专属调用点（产品代码 src/main 优先）
# 用法: bash scan1a_api26_calls.sh <repo_root> <output_dir>
REPO="${1:-/home/z/my-project/Waterfox-Android}"
OUT="${2:-/home/z/my-project/download/waterfox-android24-migration}"
MA=mobile/android
cd "$REPO" || exit 1
mkdir -p "$OUT"

{
echo "============================================================"
echo " Phase 1a: main (427cd346, Gecko 160) API26+ 专属调用点扫描"
echo " 时间: $(date -u +'%Y-%m-%d %H:%M UTC')  范围: mobile/android 产品代码"
echo "============================================================"

echo
echo "## A. java.time 使用（src/main 产品代码，需 desugaring）"
for mod in fenix/android-components/focus-android; do :; done
echo "--- A1. 按 import java.time. 统计（src/main）---"
rg -c '^import java\.time\.' --glob '*.{kt,java}' \
   $MA/fenix $MA/android-components $MA/focus-android $MA/geckoview/src/main \
   -g '!**/test/**' -g '!**/androidTest/**' 2>/dev/null | sort | head -100
echo "--- A1 计数 ---"
rg -l '^import java\.time\.' --glob '*.{kt,java}' \
   $MA/fenix $MA/android-components $MA/focus-android $MA/geckoview/src/main \
   -g '!**/test/**' -g '!**/androidTest/**' 2>/dev/null | wc -l

echo
echo "--- A2. 全部 java.time 直接 import 明细（含 test 供参考）---"
rg -o '^import java\.time\.[A-Za-z]+' --glob '*.{kt,java}' \
   $MA/fenix $MA/android-components $MA/focus-android $MA/geckoview/src/main 2>/dev/null \
   | sed 's/.*import //' | sort | uniq -c | sort -rn | head -25

echo
echo "## B. NotificationChannel / 通知渠道（API 26+，src/main）"
rg -l 'NotificationChannel|createNotificationChannel|NotificationChannelGroup' \
   --glob '*.{kt,java}' \
   $MA/fenix/app/src/main $MA/android-components/components \
   $MA/focus-android/app/src/main $MA/geckoview/src/main 2>/dev/null | sort

echo
echo "## C. 其他常见 API 26+ 符号（src/main，逐一确认）"
for sym in 'startForegroundService' 'AdaptiveIconDrawable' 'VibrationEffect' \
           'PictureInPictureParams' 'WifiAware' 'isDeviceLocked' ; do
  echo "--- C. $sym ---"
  rg -l "$sym" --glob '*.{kt,java}' \
     $MA/fenix/app/src/main $MA/android-components/components \
     $MA/focus-android/app/src/main $MA/geckoview/src/main 2>/dev/null
done

echo
echo "--- C7. String.join( (API 26+，排除 StringJoiner API24+) ---"
rg -n 'String\.join\(' --glob '*.{kt,java}' \
   $MA/fenix/app/src/main $MA/android-components/components \
   $MA/focus-android/app/src/main $MA/geckoview/src/main 2>/dev/null | head -20

echo
echo "## D. main 中 VERSION_CODES 档位分布（全 mobile/android，src/main）"
echo "--- D1. geckoview/src/main ---"
rg -o 'VERSION_CODES\.[A-Z_0-9]+' --glob '*.{kt,java}' $MA/geckoview/src/main 2>/dev/null \
   | sed 's/.*VERSION_CODES\.//' | sort | uniq -c | sort -rn
echo "--- D2. fenix + AC + focus (src/main) ---"
rg -o 'VERSION_CODES\.[A-Z_0-9]+' --glob '*.{kt,java}' \
   $MA/fenix/app/src/main $MA/android-components/components \
   $MA/focus-android/app/src/main 2>/dev/null \
   | sed 's/.*VERSION_CODES\.//' | sort | uniq -c | sort -rn

echo
echo "## E. SDK_INT 与 N/M/LOLLIPOP 低档位残留（应为 0，验证上游删除）"
rg -n 'SDK_INT\s*[<>=]+\s*2[1-6]\b|VERSION_CODES\.(N\b|M\b|LOLLIPOP|LOLLIPOP_MR1|BASE)' \
   --glob '*.{kt,java}' $MA/geckoview/src/main $MA/fenix/app/src/main \
   $MA/android-components/components $MA/focus-android/app/src/main 2>/dev/null | head -30

echo
echo "## F. C++ 侧 __ANDROID_API__ 宏（mobile/android 内）"
rg -n '__ANDROID_API__' $MA/geckoview $MA/android-components --glob '*.{cpp,h,c,mm}' 2>/dev/null | head -20

echo
echo "## G. coreLibraryDesugaring 现状（应为 0）"
rg -rn 'coreLibraryDesugaring|desugar_jdk_libs|desugar-jdk-libs' \
   gradle/libs.versions.toml $MA/fenix/app/build.gradle.kts \
   $MA/android-components/components/lib/push-firebase 2>/dev/null || echo "(无任何 desugaring 配置 — 已确认移除)"
} | tee "$OUT/phase1a_scan.txt"

echo; echo "输出已保存: $OUT/phase1a_scan.txt"
