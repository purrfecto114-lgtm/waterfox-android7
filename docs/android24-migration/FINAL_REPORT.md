# Waterfox Android 端全量降级迁移（版本 B）—— 最终报告

**分支:** `android24-full-migration`（基线 main @ 427cd34663602950a8d8621a11c7aa273e7a3406, Gecko 160）
**目标:** main 的完整 Android 端（App 层 + GeckoView）运行于 Android 7.0（API 24），不牺牲 1.2.x 功能
**执行:** AI（superpowers 工作流：计划 → 扫描评估 → 分批实施 → 静态验证）
**日期:** 2026-11-07

---

## 一、判定标准四问（交接要求，先回答）

### 1. `min_sdk_version` 最终值？`coreLibraryDesugaring` 是否已恢复？

- **min_sdk_version = "24"**【已验证】`build/moz.configure/android-sdk.configure:160`，
  targetSdk 保持 37 未动。经 `MOZ_ANDROID_MIN_SDK_VERSION` → gradle.py → shared-settings.gradle
  链路分发到 GeckoView / Fenix / AC（分发链路已核验）。
- **coreLibraryDesugaring 已恢复**【已验证配置存在；编译行为未验证】三处与 1.1.x 同构：
  - `gradle/libs.versions.toml`: `desugar-jdk-libs = "2.1.5"`（与 archive-1.1 相同版本；
    其 minCompileSdk 34 ≤ 当前 compileSdk 37，minSdk 21 ≤ 24，与 Kotlin/AGP 无耦合）
  - `fenix/app/build.gradle`: compileOptions + coreLibraryDesugaring
  - `AC push-firebase/build.gradle`: 同上
  - 机制说明【推断，与 1.1.x 同构】：AC 其余模块（awesomebar/prompts/protection-dashboard/support-utils）
    直接使用 java.time 但 AAR 内是 .class，最终由 app 端 R8/D8 全量脱糖兜底——1.1.9 即此结构。

### 2. main 里还有多少处「需要版本判断但判断缺失」的 API 26+ 调用点？

**修复前（本报告 Phase 1 全量扫描）：19 处 P0 崩溃点 + 1 处功能错误 + 1 处静默禁用**，清单：

| 类别 | 数量 | 明细 |
|---|---|---|
| GeckoView API26+ 方法/类无防护 | 4 文件 5 处 | GeckoView.java(autofill delegate)、CrashHandler(startForegroundService)、GeckoRuntimeSettings/SessionAccessibility/WebAuthnUtils(String.join ×3) |
| GeckoView API25 字段无防护 | 1 处 | GeckoEditable(contentMimeTypes) |
| 通知渠道（API 26 类）无防护 | 13 文件 | AC 7（ktx 封装、media、downloads、webnotifications、crash、pwa、base ext）+ fenix 5 + focus 1 |
| 振动 API26+ 无防护 | 1 处 | AC support/ktx Vibrator.kt |
| DRM 功能错误（N_MR1 判断缺失） | 1 处 | CodecProxy.supportsCBCS |
| 渠道检查静默禁用 | 1 处 | support/base isNotificationChannelEnabled（API<26 恒 false → 营销通知静默关闭） |

**修复后（静态复扫）**：以上全部处理完毕。复扫输出：
- `String.join` 在 geckoview src/main = 0 处（已全部 TextUtils.join）
- 无防护 `NotificationChannel(` 构造 = 0 处（全部进入 `SDK_INT >= O` 分支）
- 低档位 VERSION_CODES 恰为本次还原的 3 处 N_MR1
- **剩余风险【未验证】**：lint `NewApi` 级别的深层调用（如 kotlinx/第三方库字节码内的 26+ 调用）
  无法在无 SDK 沙箱中穷尽，需有环境机器跑 `./mach lint` / gradle `lintDebug` 确认。

### 3. 有没有 API 24 上根本不存在该能力的功能？（必须告知，不能默默跳过）

| 功能 | API 24 行为 | 处理方式 |
|---|---|---|
| Android 系统级 Autofill（设置里的自动填充服务） | 系统无此能力（API 26+） | GeckoView autofill delegate 置空（与 1.1.x 行为完全一致）；网页内表单自动填充不受影响 |
| 通知渠道（按渠道开关/设置页） | 概念不存在 | 通知本身全部可用（NotificationCompat）；用户只能整体开关通知，不能按渠道管理 |
| 画中画 PiP | 系统无此能力（API 26+） | `hasSystemFeature` 自动返回 false，无崩溃、自动降级（上游原设计） |
| 隐私报告周报通知 | 通知可发，但无渠道管理 | 已修复 availability 逻辑，API 24 上正常发送（不静默删功能） |
| 营销通知 | 通知可发 | 已修复 isNotificationChannelEnabled 回退，API 24 上正常判定 |

### 4. AndroidX 最终降级了哪几个库、降到什么版本、为什么？

**一个都没降。零降级。**【已验证】
- 实测依据：脚本批量下载 `gradle/libs.versions.toml` 全部 androidx 直接依赖 + compose-bom
  2026.09.00 对齐子库共 **89 个 AAR**，解析各自 AndroidManifest 的 `minSdkVersion`：
  分布 = 14(6) / 19(2) / 21(24) / 23(47) / **24(10)**，**最大值恰好 24**（navigation 2.10.2、
  work 2.12.0、emoji2 1.7.0、benchmark 1.5.0、navigation3 1.2.0——均为 2026-07 后按 AndroidX
  新政 minSdk 23→24 的版本）。
- 背景：AndroidX 官方 minSdk 时间线 19(2023)→21(2024)→23(2025-06)→**24(2026-07)**，
  main 的 2026.09 档依赖恰好落在 24 上。
- 12 个未解析项均为 JAR/构建期插件（annotation、collection、room-compiler 等），无 minSdk 概念。
- 明细数据：`phase3_androidx_minsdk.json`。

---

## 二、完整 diff 摘要（26 文件，+274/−125）

### 构建基础设施（4 文件）
| 文件 | 改动 | 理由 / API 级别 |
|---|---|---|
| `build/moz.configure/android-sdk.configure` | minSdk 26→24 | 全局唯一 minSdk 来源；targetSdk 37 不动 |
| `gradle/libs.versions.toml` | +desugar-jdk-libs 2.1.5（versions + libraries 两段） | java.time 在 API 24 需 desugaring（上游 Bug 1969392 移除后恢复） |
| `mobile/android/fenix/app/build.gradle` | +compileOptions(coreLibraryDesugaringEnabled) +coreLibraryDesugaring 依赖 | 同上；app 是最终打包端，R8/D8 对全依赖树脱糖 |
| `mobile/android/android-components/.../push-firebase/build.gradle` | 同 fenix 两处 | 1.1.x 原有配置原样恢复 |

### GeckoView（8 文件）
| 文件 | 改动 | API 问题 |
|---|---|---|
| `GeckoEditable.java` | contentMimeTypes 加 `>= N_MR1` | API 25 字段，直接赋值必崩（NoSuchFieldError） |
| `GeckoView.java` | autofill delegate 加 `>= 26` 分支 + 空 Delegate | AndroidAutofillDelegate 引用 API 26 类 AutofillManager |
| `CrashHandler.java` | startForegroundService 加 `>= 26` else startService | API 26 方法 |
| `GeckoRuntimeSettings.java` | String.join → TextUtils.join | API 26 方法（DoH 排除域名） |
| `SessionAccessibility.java` | 同上 | API 26 方法（无障碍内容描述） |
| `WebAuthnUtils.java` | 同上 + import | API 26 方法（WebAuthn 日志） |
| `CodecProxy.java` | 还原 supportsCBCS()（`>= N_MR1`） | API 24 CBCS DRM bug 规避（ExoPlayer#4022），功能正确性 |
| `GeckoInputConnection.java` | 恢复 @TargetApi(N_MR1) | lint 语义（运行时懒加载安全，1.1.x 同构实证） |

### Android Components（8 文件）
| 文件 | 改动 | API 问题 |
|---|---|---|
| `support/ktx .../notification/Notification.kt` | ensureNotificationChannelExists 加 `>= O` | 渠道构造（API 26 类）；修复 media/addons/privatemode 全部调用方 |
| `support/ktx .../os/Vibrator.kt` | `>= O ? VibrationEffect : vibrate(ms)` | VibrationEffect API 26 |
| `support/base .../ext/NotificationManagerCompat.kt` | isNotificationChannelEnabled `< O` 回退 app 级检查 | API<26 渠道恒 null 导致营销通知静默关闭 |
| `feature/media MediaNotificationChannel.kt` | 渠道创建/删除加 `>= O` | API 26 |
| `feature/downloads DownloadNotification.kt` | isChannelEnabled/ensureChannelExists 加 `>= O` | getNotificationChannel/构造 均 API 26 |
| `feature/webnotifications WebNotificationFeature.kt` | 渠道创建加 `>= O` | API 26；网站通知 API<26 无渠道但仍可发 |
| `feature/pwa WebAppSiteControlsFeature.kt` | Builder 分支（双参/单参构造）+ setBadgeIconType 防护 + 渠道防护 | 双参 Notification.Builder 与 setBadgeIconType 均 API 26 |
| `lib/crash CrashNotification.kt` | 渠道创建加 `>= O` | API 26 |

### Fenix（6 文件）/ Focus（1 文件）
| 文件 | 改动 | API 问题 |
|---|---|---|
| `fenix components/NotificationManager.kt` | init 渠道创建加 `>= O` | API 26 |
| `fenix perf/ProfilerService.kt` | onCreate 渠道创建加 `>= O` | API 26 |
| `fenix customtabs/PoweredByNotification.kt` | ensureChannelExists 加 `>= O` | API 26 |
| `fenix onboarding/MarketingNotificationHelper.kt` | 渠道 get/create 加 `>= O` | getNotificationChannel + 构造均 API 26 |
| `fenix privacyreport/PrivacyReportNotificationHelper.kt` | 渠道创建加 `>= O`；availability 在 `< O` 只查 app 级开关 | API 26；同时避免周报通知在 API 24 静默停发 |
| `focus session/SessionNotificationService.kt` | 渠道创建加 `>= O` | API 26 |

完整补丁：`android24-full-migration.patch`（840 行，可 `git apply` 复现）。

---

## 三、与交接提示词预期不同的实测结论（重要）

| 交接预期 | 实测结论 | 依据 |
|---|---|---|
| GeckoMediaDrmBridge V21/V23 拆分需还原 | **不需要** | 合并版(806 行)语义=V23：最高 API 调用为 setOnKeyStatusChangeListener/queryKeyStatus（均 API 23 ≤ 24）；V21 路径(≤22) API 24 用不到 |
| LollipopAsyncCodec/JellyBeanAsyncCodec 需还原 | **不需要** | AsyncCodecImpl=LollipopAsyncCodec 改名；最高调用 CodecException.getErrorCode()(API 23)；API 24 ≥ LOLLIPOP_MR1 走此路径 |
| CrashedProcessType 需还原 | **不需要** | fenix/AC 调用方已 0 引用（rg 全量验证）；该 API 形态与 Android API 级别无关 |
| PermissionPromptResponse/权限 API 需还原旧签名 | **不需要** | 新签名(addOptionalPermissions 带 dataCollection)是 Gecko 142 权限系统演进，API 24 功能等价 |
| AndroidX 需逐库降级挡路库 | **零降级** | 89 个 AAR 实测 minSdk ≤ 24（见判定四问 #4） |
| AGP 8.13.2 / Kotlin 2.3.0 | 实际 **AGP 9.4.1 / Kotlin 2.4.21** | main 在交接后又前进；本工作按实测基线执行 |
| archive 低档位分支 65 处需移植 | **实际仅需 3 处** | API 24 恰落在绝大多数被删分支的真路径上（`>=M/23`、`>=N/24`、`>=LOLLIPOP_MR1/22` 均为真）；只有 `>=N_MR1/25`（3 处）与 26+ 调用点需要处理。已抽查 GeckoAppShell/Clipboard 证实上游删除=保留真路径原样 |

**方法论说明**：被删分支的还原判定表——`>=M/23`/`>=N(24)` 在 API 24 为真（走 main 现状路径，零还原）；`>=N_MR1(25)` 为假（else 路径需还原，共 3 处）；API 26+ 无条件调用（能力缺失，逐点处理，共 19 处）。

---

## 四、验证状态分类（诚实声明）

### 【已验证】（rg/git 实际输出，可复现）
- 基线 SHA、minSdk 分发链路、desugaring 配置位置
- 全部 P0 调用点的存在性（修改前）与防护完备性（修改后复扫）
- AndroidX 89 个 AAR 的 minSdkVersion（下载解析 AXML）
- DRM/AsyncCodec/autofill-service 等零修改项的 API 级别论证
- diff 全量 review（26 文件逐一手改，无整文件覆盖）

### 【推断】（代码语义推理，未编译）
- 各防护分支的 Kotlin/Java 语法正确性（人工 review，无编译器验证）
- desugaring 对 AC 模块 java.time 的兜底机制（与 1.1.9 同构）
- TextUtils.join 替换在所有 3 处的类型适配（Iterable/CharSequence 检查过）

### 【未验证】（沙箱无 Android SDK/NDK，无法执行）
- `./mach build-android` / `./mach package-android` 编译
- lint NewApi 全量检测（深层第三方字节码调用）
- API 24 设备/模拟器运行时行为

**有环境机器上的验证命令：**
```bash
git checkout android24-full-migration
./mach build-android          # 编译 GeckoView + Fenix
./mach package-android        # 打包 APK
./mach android-api-lint       # 或 gradle :app:lintDebug（NewApi 检测）
```

---

## 五、已知残余风险（下一步建议）

1. **lint 全量**：跑 `lintDebug` 看 NewApi 报告——尤其 AC 里 1.2.x 新增组件（feature/autofill 服务、glance、ipprotection 等）的字节码级调用。
2. **compose 运行时**：compose ui 1.12.1 minSdk 23 ✓，但 compose 内部对 API 24 的行为差异（如字体回退）需真机回归。
3. **moz.build 层**：minSdk 变化会影响 NDK 编译的 `MOZ_ANDROID_MIN_SDK_VERSION` 传递（geckoview buildConfig），Gecko C++ 侧理论上无需改动（mobile/android 内无 __ANDROID_API__ < 24 的条件编译，已扫描），但需编译确认。
4. **testFixtures/androidTest**：测试代码里还有大量 API 26+ 调用（本次未处理——测试不进 APK；在 API 24 真机跑 instrumentation test 会失败，属预期）。
