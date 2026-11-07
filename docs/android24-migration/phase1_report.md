# Phase 1 全貌扫描报告（main @427cd346, Gecko 160, minSdk 26）

> 扫描时间: 2026-11-07 | 方法: rg 限定目录扫描 + git diff 对照 archive-1.1 (@c24727e, minSdk 21, Gecko 140.8)
> 复现: bash scripts/scan1a_api26_calls.sh, scripts/scan1c_archive_ref.sh（输出存于本目录）
> 结论分级:【已验证】= rg/git 实际输出证实;【推断】= 代码语义推理, 未编译验证

## 0. 基线复核（替代交接提示词旧数字）

| 项 | 交接提示词 | 实测 main | 结论 |
|---|---|---|---|
| main SHA | 427cd3466360 | 427cd3466360 ✓ | 一致 |
| archive-1.1 SHA | c24727e30ca5 | c24727e30ca5 ✓ | 一致 |
| minSdk | 26 | 26 (android-sdk.configure:160) ✓ | 一致 |
| AGP | 8.13.2 | **9.4.1** | main 已前进 |
| Kotlin | 2.3.0 | **2.4.21** | main 已前进 |
| coreLibraryDesugaring | 已移除 | 已移除（0 处引用）✓ | 一致 |
| GeckoView VERSION_CODES 档位 | Q15/UDC8/S8/P7/R5/O_MR1_1/BAKLAVA1 | 完全一致 ✓ | 一致 |
| GeckoView N/M/LOLLIPOP 残留 | 0 | 0 ✓ | 一致（低档位被删而非跳过） |
| C++ __ANDROID_API__ (mobile/android 内) | ~14 处 | **0 处** | 其余在未检出目录（widget/android 等），按红线不动 |

archive-1.1 geckoview 低档位分布（65 处总计）: N=14, M=12, N_MR1=4, LOLLIPOP_MR1=1, O=9, Q=7, UDC=7, S=4, P=4, R=3 — 与交接吻合。

## 1. 【核心方法论】API 24 视角的分支还原判定

对 archive-1.1 中被删的 `SDK_INT` 分支逐档分析，**只需还原满足以下条件的分支**：

| 被删判断 | API 24 走哪条路径 | main 现状（上游保留的路径） | 是否需还原 |
|---|---|---|---|
| `>= LOLLIPOP_MR1(22)` | 真 | 真路径 | 否 |
| `>= M(23)` | 真 | 真路径 | 否 |
| `>= N(24)` | 真 | 真路径 | 否 |
| `>= N_MR1(25)` | **假（else）** | 真路径 | **是（3 处）** |
| `>= O(26)` / 无判断直接调用 | **能力不存在** | 直接调用 | **是（逐点处理）** |

推论：GeckoView 65 处低档位分支中，**绝大多数无需还原**（API 24 恰好落在上游保留的真路径上）。真正要做的只有：N_MR1 的 3 处 + API 26+ 无防护调用点。

## 2. 【已验证】P0 运行时崩溃点（API 24 上必然崩溃，必须修）

### GeckoView（org.mozilla.geckoview / org.mozilla.gecko）
| # | 文件 | 问题 | 修法（参照 archive-1.1） |
|---|---|---|---|
| 1 | geckoview/GeckoEditable.java:2112 | `outAttrs.contentMimeTypes` 是 API 25 字段，无判断直接赋值 → NoSuchFieldError | 加回 `SDK_INT >= N_MR1 &&` |
| 2 | geckoview/GeckoView.java | `AndroidAutofillDelegate`（引用 API 26 类 AutofillManager）构造时无条件 new | 加回 `SDK_INT >= 26` 判断 + 空 Delegate fallback |
| 3 | geckoview/CrashHandler.java:396 | framework `context.startForegroundService()`（API 26 方法） | 加 `SDK_INT >= 26` else `startService()` |
| 4 | geckoview/GeckoRuntimeSettings.java:2401 | `String.join(",", …)`（API 26 方法） | TextUtils.join |
| 5 | geckoview/SessionAccessibility.java:810 | 同上 | 同上 |
| 6 | geckoview/WebAuthnUtils.java:239 | 同上 | 同上 |

### App 层（通知渠道 = API 26 类，全部无防护直接构造）
| # | 模块 | 文件 | 修法 |
|---|---|---|---|
| 7 | AC support/ktx | notification/Notification.kt `ensureNotificationChannelExists` | 加回 `SDK_INT >= O` 包裹（archive 原样） |
| 8 | AC support/ktx | os/Vibrator.kt `vibrateOneShot` | 加回 `>= O ? VibrationEffect : vibrate(ms)`（archive 原样） |
| 9 | AC feature/media | MediaNotificationChannel.kt | 渠道构造加 `>= O` 防护 |
| 10 | AC feature/downloads | DownloadNotification.kt:235,249 | `getNotificationChannel`/构造加防护 |
| 11 | AC feature/webnotifications | WebNotificationFeature.kt:124-132 | 同上（网站通知 API<26 降级为无渠道通知） |
| 12 | AC lib/crash | CrashNotification.kt:115-121 | 同上（崩溃通知在 API<26 不建渠道） |
| 13 | AC feature/pwa | WebAppSiteControlsFeature.kt:138 | framework `Notification.Builder(ctx, id)`(26+) → NotificationCompat.Builder |
| 14 | fenix | components/NotificationManager.kt:51,184-197 | init 渠道创建加防护 |
| 15 | fenix | perf/ProfilerService.kt（4 处） | 同上 |
| 16 | fenix | customtabs/PoweredByNotification.kt（2 处） | 同上 |
| 17 | fenix | onboarding/MarketingNotificationHelper.kt（3 处） | 同上 |
| 18 | fenix | privacyreport/PrivacyReportNotificationHelper.kt（4 处） | 同上 |
| 19 | focus | session/SessionNotificationService.kt:191-211 | 同上 |

**通知调用方自动收敛**（走封装，修 #7/#9 后无需动）：MediaNotification.kt、RecordingDevicesMiddleware.kt、AddonUpdater.kt、AbstractPrivateNotificationService.kt。

## 3. 【已验证】功能正确性问题（不崩溃但行为错）

| 文件 | 问题 | 修法 |
|---|---|---|
| geckoview/media/CodecProxy.java:489 | `setCryptoPatternIfNeeded` 丢了 `supportsCBCS()`（`>= N_MR1`）判断 → API 24 会启用有 bug 的 CBCS DRM 路径（ExoPlayer#4022） | 还原 archive 的 supportsCBCS() 判断 |

## 4. 【已验证】零修改项（重要：与交接提示词预期不同的实测结论）

| 项 | 交接预期 | 实测结论 | 依据 |
|---|---|---|---|
| GeckoMediaDrmBridge V21/V23 拆分 | 重点还原 | **零修改** | main 合并版(806行)语义=V23：最高 API 调用为 `setOnKeyStatusChangeListener`/`queryKeyStatus`（均 API 23）≤ 24 |
| LollipopAsyncCodec/JellyBeanAsyncCodec | 还原 | **零修改** | AsyncCodecImpl=LollipopAsyncCodec 改名；最高调用 `CodecException.getErrorCode()`(API 23)；JellyBean 路径(≤21)API 24 不需要 |
| MediaDrmProxy V21 桥选择 | 还原 | **零修改** | API 24 走 V23 语义=main 现状 |
| CrashedProcessType | 还原 | **不还原** | 调用方(fenix/AC src/main)已 0 引用；API 形态与运行时无关 |
| PermissionPromptResponse/权限 API 签名 | 还原 | **不还原** | 新签名是 Gecko 142 权限系统重构，与 Android API 级别无关，API 24 功能等价 |
| GeckoAppShell/Clipboard/SpeechSynthesis/GeckoSession/FormatParam/BasicSelectionActionDelegate/GeckoDragAndDrop 的 N/M/LOLLIPOP 分支 | 列为移植目标 | **零修改** | API 24 恒走真路径（=main 现状），N=24 恰好满足 |
| AsyncCodecFactory | — | **无需还原** | API 24 >= LOLLIPOP_MR1 走 LollipopAsyncCodec 路径 |
| ShortcutManager | — | **零修改** | 全部经 androidx `ShortcutManagerCompat`（API 19+ 兼容） |
| PictureInPicture | — | **零修改（自动降级）** | `hasSystemFeature(FEATURE_PICTURE_IN_PICTURE)` API 24 返回 false 短路 |
| AC feature/autofill（Android autofill service） | — | **零修改（懒加载）** | manifest service 声明在 API<26 不被系统 bind，类不加载；archive(minSdk 21)同构仅靠 @RequiresApi 注解 |
| ContextCompat.startForegroundService（AC 3 处+GeckoJavaSampler） | — | **零修改** | androidx core 内部已做 < 26 回退 startService |
| GeckoInputConnection.commitContent | N_MR1 目标 | **零修改（可选拿回注解）** | 方法签名类懒加载+系统不调用；archive(minSdk 21) 同构实证 |

## 5. 【已验证】API 24 上能力不存在 → 功能降级告知清单

| 功能 | API 24 行为 | 说明 |
|---|---|---|
| Android Autofill（系统级自动填充服务） | 不可用（系统无此能力，API 26+） | GeckoView autofill delegate 置空（与 archive 行为一致）；表单内自动填充不受影响 |
| 通知渠道（channel 分类/设置页） | 概念不存在 | 通知本身正常（NotificationCompat 忽略 channelId）；用户不能按渠道管理通知 |
| 画中画 PiP | 不可用（API 26+） | hasSystemFeature 自动 false，无崩溃 |
| 前台服务类型行为 | startService 回退 | 后台限制更宽松（API 24 无后台执行限制的 26+ 语义） |

## 6. java.time 使用面（desugaring 恢复后全部解决）

- src/main 产品代码 16 文件：AC feature/awesomebar(3)、feature/prompts(1)、feature/protection-dashboard(1)、support/utils(1)、plugins/config(1，构建期 JVM 不需 desugar)；fenix 8
- GeckoView src/main：0 文件（不依赖 desugaring）
- 需启用 coreLibraryDesugaring 的模块：fenix/app、AC feature/awesomebar、feature/prompts、feature/protection-dashboard、support/utils、push-firebase（后者按 archive 原配置恢复）

## 7. 工作量评估（Phase 1 硬性交付）

| 项 | 规模 | 风险 |
|---|---|---|
| Phase 2 基础设施 | 6 个构建文件 | 低；desugar-jdk-libs 2.1.5 需与 Kotlin 2.4.21/AGP 9.4.1 兼容性确认 |
| Phase 3 AndroidX 门槛 | 逐库查 minSdk（约 30 库） | 中；2025-2026 版本库可能有 minSdk>24，需逐个 POM 验证 |
| Phase 4 GeckoView | 6 文件（清单 §2 上半 + §3） | 低-中；均为局部小改，archive 有参照 |
| Phase 4 App 层通知 | 13 文件（清单 §2 下半） | 低-中；模式统一（加 SDK>=O 防护） |
| Phase 5 验证 | 沙箱无 SDK → 静态验证 + 标注未验证 | 编译【未验证】 |

**总体判断：工作量可控，无需停下来调整方案。** 与交接提示词预期的「把 archive-1.1 的 65 处分支 + 211 文件移植回来」相比，实测需改动面收敛到约 25 个代码文件 + 6 个构建文件 —— 因为 API 24 恰好落在绝大多数已删分支的真路径上，真正的缺口集中在 N_MR1(25) / O(26) 两档与通知渠道。

## 8. AndroidX 待查清单（Phase 3 输入）

gradle/libs.versions.toml 全表见 phase3 输出；重点核查（2025-2026 最新版）：
activity 1.13.0 / appcompat 1.8.0 / core 1.19.1 / lifecycle 2.11.0 / compose-bom 2026.09.00 / navigation 2.10.2 / fragment / work / room / datastore / biometric 1.1.0 / browser 1.10.0 等。
