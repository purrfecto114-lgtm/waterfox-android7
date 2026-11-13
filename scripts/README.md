# dex 级 API 引用审计脚本（android24 迁移配套）

用法（对任意 APK 与任意 API level 的 android.jar 差分）：

```bash
# 1. 下载平台包（示例 API 24）
curl -fLO https://dl.google.com/android/repository/platform-24_r02.zip
unzip -o platform-24_r02.zip -d p24   # -> p24/android-7.0/android.jar

# 2. 符号清单级审计（不含调用方定位）
python3 scripts/dex_api_audit.py app.apk p24/android-7.0/android.jar out1.json

# 3. 指令级审计（每个缺失符号的调用方；R8 合并宿主名会失真，需结合符号反查源码）
python3 scripts/dex_caller_audit2.py app.apk p24/android-7.0/android.jar 0 out_dex0.json  # 每个 dex 一份
```

背景与结果解读见 `docs/android24-migration/STARTUP_CRASH_AUDIT.md`。
