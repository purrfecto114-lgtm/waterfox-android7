# Waterfox for Android（Android 7.0 / API 24 移植版）

[BrowserWorks/Waterfox-Android](https://github.com/BrowserWorks/Waterfox-Android) 的 fork，
将最低系统要求从 Android 8（minSdk 26）降级到 **Android 7.0（minSdk 24）**，功能零删减。
版本号与上游保持一致（当前 **1.2.11**），基线为上游 `main` @ `427cd346`（Gecko 160）。

> 本仓库的移植代码、CI 工作流与文档由 AI（GLM，Z.ai）生成。

## 下载

从 [Releases](../../releases) 获取 `fenix-waterfox-arm64-v8a-release.apk`（arm64-v8a，Android 7.0+）。
Release 以 **pre-release** 形式发布；上游发新版前，同一版本号会删旧重发、持续迭代修复。

## 构建

`.github/workflows/build-apk.yml`（Actions 页手动触发）：
本仓库的精简树叠加到上游基线全量树上，CI 现场完成 mach/Gradle 编译、签名与发布。

| 输入 | 说明 |
|---|---|
| `stage` | `full` 完整构建；`gradle-only` 复用上次 run 的 buildstate 只重跑打包段 |
| `version` | versionName，与上游对齐（如 `1.2.11`） |
| `tag` | Release tag（如 `android24-v1.0`） |
| `publish` | `true` 时删除旧 Release 并以 pre-release 重建 |

## 移植要点

- minSdk 26 → 24（targetSdk 37 不变），恢复 coreLibraryDesugaring
- 修复 19 处 API 26+ 崩溃点及 1 处 DRM 功能错误；后续又修复 12 处启动路径无防护 API 调用（Android 7 卡 logo 循环）
- AndroidX 零降级；系统级 autofill、PiP 等 API 24 缺失能力优雅降级

## 仓库结构

- `mobile/android/` — GeckoView + android-components + fenix + focus-android 源码（精简树）
- `build/moz.configure/`、`gradle/` — 构建配置（minSdk 全局来源）
- `patches/` — CI 现场应用的本地补丁
- `.overlay-deletions` — 叠加时需从上游基线删除的文件清单
- `docs/android24-migration/` — [移植最终报告](docs/android24-migration/FINAL_REPORT.md)、
  [启动崩溃审计与修复](docs/android24-migration/STARTUP_CRASH_AUDIT.md)、
  [全量迁移补丁](docs/android24-migration/android24-full-migration.patch)

## 许可

沿用上游 Mozilla 公共许可（MPL 2.0 等），见 [LICENSE](LICENSE)。
