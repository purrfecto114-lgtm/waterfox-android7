# Waterfox-Android — Android 7 (API 24) 全量降级迁移（版本 B / 精简源码树）

> ⚠️ **AI 生成声明**：本仓库的迁移代码、补丁、报告、脚本与 workflow 均由 AI（GLM，Z.ai）生成，
> 属于自动化迁移产物。所有改动仅经静态验证（API 级别论证 + rg/git 复扫），**未经编译与真机验证**。

## 仓库性质

本仓库是 [BrowserWorks/Waterfox-Android](https://github.com/BrowserWorks/Waterfox-Android)（mozilla
monorepo 式，含完整 Gecko 引擎）的 fork，**按精简策略重建为孤儿历史**：不含全内核（约 43 万个
桌面端/引擎文件）的提交历史，仅保留 Android 端迁移所需的源码与配置。与父仓库基线的对应关系由
补丁文件完整保存（见下）。

- **基线**：父仓库 `main` @ `427cd346`（Gecko 160，2026-07-19）
- **迁移结果**：`main` 分支 = 基线 Android 树（6 个 `chore(slim)` 导入提交）+ 5 个迁移提交 + 文档/CI 提交

## 包含 / 删除

| 包含 | 说明 |
|---|---|
| `mobile/android/` | GeckoView + android-components + fenix + focus-android 全部源码与资源 |
| `build/moz.configure/` | minSdk 全局唯一来源（`android-sdk.configure`） |
| `gradle/` | 版本目录（`libs.versions.toml`，含 desugar-jdk-libs 2.1.5）等 |
| `docs/android24-migration/` | 完整报告、扫描脚本、AndroidX 实测数据、独立补丁 |
| `.github/workflows/release.yml` | 手动触发的 release workflow |

| 删除 | 理由 |
|---|---|
| 非 Android 的全部文件（引擎 C++、桌面端、python 构建系统等，约 43 万文件） | Android 端不需要；迁移对引擎源码零改动（已扫描验证） |
| `mobile/android/examples/`、`geckoview_example/` | 演示工程，产品构建不需要 |

**无损性**：迁移的 26 个改动文件 100% 位于 `mobile/android + build/moz.configure + gradle` 内，
本仓库包含迁移全部触及面与 Android 端全部源码；引擎构建使用父仓库基线即可。

## ⚠️ 本树不能独立编译

mozilla 构建系统需要完整树。编译验证方法（在有 Android SDK/NDK 的机器上）：

```bash
git clone https://github.com/BrowserWorks/Waterfox-Android.git
cd Waterfox-Android && git checkout 427cd34663602950a8d8621a11c7aa273e7a3406
git apply android24-full-migration.patch   # docs/android24-migration/ 或 release 资产中获取
./mach build-android && ./mach package-android
./mach android-api-lint                    # NewApi 深层检测
```

## 迁移要点（详见 `docs/android24-migration/FINAL_REPORT.md`）

- `min_sdk_version` 26 → **24**，targetSdk 37 不变，1.2.x 功能零删减
- 恢复 coreLibraryDesugaring（desugar-jdk-libs 2.1.5，与 1.1.x 同构）
- 修复 19 处 API 26+ P0 崩溃点 + 1 处 DRM 功能错误（`CodecProxy.supportsCBCS`）+ 1 处静默禁用
- **AndroidX 零降级**（实测 89 个 AAR 的 minSdkVersion 最大值恰为 24）
- API 24 系统能力缺失（系统级 autofill、PiP、按渠道通知管理）→ 优雅降级，与 1.1.x 行为一致

## 发布

Release workflow 位于 `.github/workflows/release.yml`（`workflow_dispatch` 手动触发），
当前发布：tag `android24-v1.0`（含补丁与报告资产）。
