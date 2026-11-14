# 启动崩溃（卡 logo 循环）审计与修复报告

**日期**: 2026-11-13
**对象**: release `android24-v1.0` 中的 `fenix-waterfox-arm64-v8a-release.apk`（v1.0.1 构建）
**现象**: Android 7.0（API 24）真机可安装，但卡启动 logo 反复显示（崩溃循环）
**结论**: 确认 3 个启动路径崩溃点 + 9 个功能路径崩溃点，全部修复（v1.0.2）

---

## 一、审计方法（dex 级全量 API 引用审计）

上游 minSdk=26，lint NewApi 只保证 API 27+ 调用有防护；**API 26 的类/方法/字段
在上游是"免检"的**，降到 API 24 后全部变成潜在崩溃点，且无法靠 lint 复查
（无 SDK 环境）。因此对已发布 APK 做了直接证据级的审计：

1. 下载 release APK，解析其中 3 个 dex 的 `method_ids` / `field_ids` /
   `class_defs`，并**解码全部方法的指令流**（invoke / iget-iput-sget-sput /
   new-instance / const-class / check-cast / instance-of）。
2. 解析 `android-24_r02.zip` 的 `android.jar` 全部 stub 类符号（含
   **继承闭包展开**——stub 类不重复声明父类成员，而 dex 引用的 class 是
   调用点静态类型）。
3. 差分：APK 引用的 `Landroid/**` 符号中，API 24 不存在的 → 带调用方的
   完整命中清单（含"目标类整体不存在"时的成员访问，即 `NoClassDefFoundError`
   型崩溃）。
4. 对每个命中点回源码（slim 树）核对是否已有 `SDK_INT` 防护；androidx /
   compose / media3 的调用者按库自身 minSdk 兼容策略信任；hidden-API
   （如 `Os.setsockoptInt`、`CryptoInfo.getPattern`、
   `ViewConfiguration.getTextCursorBlinkIntervalMillis`）在 Android 7 运行时
   实际存在且无 hidden-API enforcement（Android 9 才引入），不构成崩溃。

审计脚本：`scripts/dex_api_audit.py`、`scripts/dex_caller_audit.py`（本轮会话产物，
随仓库 scripts 目录保存；修复后 APK 复跑该审计可作为回归验证）。

## 二、确证并修复的崩溃点（12 文件）

### 启动路径（卡 logo 的直接原因）

| # | 调用链 | 缺失符号 | 异常 | 修复 |
|---|---|---|---|---|
| 1 | `FenixApplication.onCreate` → `setStartupMetrics`（IO 协程）→ `AutofillUseCases.isEnabled` | `android.view.autofill.AutofillManager`（API 26 类，`::class.java` 类字面量） | `NoClassDefFoundError`，`catch(RuntimeException)` 拦不住 → 进程崩溃 → Activity 重启 → 循环 | `AutofillUseCases` 三方法均加 `>= O` 短路 |
| 2 | `FenixApplication.queueUpdateAutofillServiceState` → `updateAutofillServiceState` | `ComponentName(this, AutofillService::class.java)` 触发类链接，其父链含 `android.service.autofill.AutofillService`（API 26 类） | `NoClassDefFoundError`（类链接期） | 改字符串 `ComponentName`（不加载类）；`Settings.isAutofillSupported` 加 `>= O` 门控，API 24 上组件被 DISABLED，系统 autofill 整体降级（与 1.1.x 行为一致） |
| 3 | `queueMetrics` → `StorageStatsMetrics.report` → `reportSync` | `StorageStatsManager`（API 26 类）+ `ApplicationInfo.storageUuid`（API 26 字段） | `NoClassDefFoundError` / `NoSuchFieldError` | `report()` 加 `>= O` 早退（源码注释本就自认 "API 26+ only"，上游 minSdk=26 无需运行时判断） |

### 功能路径（用户操作触发）

| # | 位置 | 缺失符号 | 触发时机 | 修复 |
|---|---|---|---|---|
| 4 | `WebAppShortcutManager.updateShortcuts` / `findShortcut` | `android.content.pm.ShortcutManager`（**API 25 类**） | PWA 更新/检测 | `>= N_MR1` 短路（P0 扫描只查 26+，API 25 类是当时的盲区） |
| 5 | `PairFragment` 配对成功振动 | `VibrationEffect`（API 26） | FxA 配对扫码 | `>= O` 分支，回退 deprecated `vibrate(ms)` |
| 6 | `Clipboard.getClipboardTimestamp` | `ClipDescription.getTimestamp()`（API 26 方法） | 剪贴板变更（粘贴/复制） | `< O` 返回 0（调用方本就把 0 当"无时间戳"） |
| 7 | `GeckoAppShell.onLocationChanged` | `Location.hasVerticalAccuracy()/getVerticalAccuracyMeters()`（API 26） | 地理定位更新 | `< O` 报 NaN（"未知"） |
| 8 | `SessionAccessibility.populateNodeInfo` | `AccessibilityNodeInfo.setHintText()`（API 26） | 无障碍节点填充（TalkBack 等） | `>= O` 才调用，否则写入 extras 键兜底 |
| 9 | `AutofillUseCases.disable` | `AutofillManager`（API 26 类） | 设置里关闭 autofill | `>= O` 短路 |
| 10 | `GeckoProcessManager.isIsolatedGmpEnabled` | 隔离 GMP 绑定走 `Context.bindIsolatedService`（API 29） | EME/DRM 进程（若启用 isolated GMP） | `&& SDK_INT >= Q` 兜底 |
| 11 | `ApplicationExitInfoMetrics.TRACKED_REASONS` | object 属性初始化（`<clinit>`）读取 `ApplicationExitInfo.REASON_*`（API 30 类） | 当前唯一入口已有 `>= R` 防护（安全），但任何未来路径加载该 object 即崩 | 改 `by lazy`，类加载不再触碰 API 30 类 |
| 12 | `Addon.formatLocalizedDataCollectionPermissions` | `ListFormatter.format(Collection)`（SDK 24 未暴露，运行时 ICU 存在——灰区） | 插件权限列表展示 | 改变参重载 `format(*arr)`（API 24 公开） |

## 三、审计命中但确认安全的类别（无需修改）

- **已有 `SDK_INT` 防护**：ApplicationExitInfoMetrics 调用点（>= R）、
  WebAuthnCredentialManager 全部 credentials API 34 调用（三处 `>= UPSIDE_DOWN_CAKE` 早退）、
  QrFragment（SessionConfiguration >= P / RemoteUserInfo >= R）、IconDiskCache（WEBP >= R）、
  GeckoNetworkManager（isPrivateDnsActive >= P）、HardwareCodecCapabilityUtils（>= Q）、
  GeckoSystemStateListener（getContrast >= 34）、SurfaceViewWrapper（getSurfaceControl >= Q）、
  SetToDefaultPromptRequest / Activity（RoleManager >= Q）、WindowOverlayProtection（< S 早退）、
  InstallSource（getInstallSourceInfo >= R）、gecko IntentUtils（getStorageDirectory >= R）、
  GeckoEditable（TextPaint.underline* 有 >= Q + 反射 fallback）、
  SessionAccessibility 其余新 API（>= 34/36 分支）、ServiceAllocator（bindService(executor) >= Q）、
  PairFragment 之外无 VibrationEffect 直用、ListFormatter 主分支（>= 33）、
  LensCameraActivity（ImageDecoder >= P）、isIpv4OrIpv6（InetAddresses >= Q）
- **androidx / compose / media3 / material 内部调用**：库自带版本防护
  （`Api26Impl/Api28Impl/Api30Impl` 模式、Compat 类、`$$ExternalSyntheticApiModelOutline`）
- **非车机早退**：`CarUxRestrictionsFeature.start()`（`hasSystemFeature` false 直接 return，
  android.car 懒解析，且 catch LinkageError）
- **hidden-API 运行时存在**（Android 9 才有 hidden API enforcement，API 24 无拦截）：
  `Os.setsockoptInt`、`MediaCodec$CryptoInfo.getPattern`、
  `ViewConfiguration.getTextCursorBlinkIntervalMillis`、`VelocityTracker.getAxisVelocity(I)` 等
- **R8 优化副作用**：`ApplicationExitInfo.REASON_*` 常量已被内联（无 sget）；
  审计调用方类名受 R8 水平合并影响是宿主假名，定位以符号反查源码为准
- **继承误报**（stub 类不声明父类成员，已由继承展开消除）：`ImageView.setVisibility`、
  `LayoutParams.width`、`ActivityInfo.applicationInfo/exported` 等
- **manifest 组件**：`AutofillService` 等组件经修复 2 后在 API 24 上被
  `setComponentEnabledSetting(DISABLED)` 禁用（字符串 ComponentName 不加载类），
  系统 autofill 设置页 API 26+ 才存在，用户无从启用，类永不被加载

## 四、验证状态

- 【静态验证】12 处修复全部基于 dex 指令级证据 + 源码逐点核对；修改语法保守
  （分支短路 / 字符串构造 / lazy 化 / 变参重载），无 API 行为变更（>= O 路径语义不变）
- 【待验证】CI 重新构建（stage=full，geckoview Java 有改动需重跑 mach build）；
  修复后 APK 复跑审计脚本应显示全部命中均落入防护分支；Android 7 真机启动验证
- 【真机日志】若仍异常，`adb logcat` 抓取：
  `adb logcat -c && adb shell am start -n net.waterfox.android/org.mozilla.fenix.HomeActivity`
  然后看 `adb logcat -d -b crash` 与 `AndroidRuntime` TAG 的 `FATAL EXCEPTION`

## 五、v1.0.3 构建期修复：委托属性注解目标（Kotlin 编译错误）

首次重构建（run 43465128112）mach build 全部通过，但
`:fenix:compileWaterfoxReleaseKotlin` 报唯一错误（gradle.log:6568）：

> ApplicationExitInfoMetrics.kt:38: error: This annotation is not applicable
> to target 'member property with delegate'

**原因**：修复 11 将 `TRACKED_REASONS` 改为 `by lazy` 委托属性。Kotlin 委托属性
无 backing field，`@RequiresApi` / `@VisibleForTesting` 的适用目标
（field/function/getter…）不含 "member property with delegate"，直接标注即
WRONG_ANNOTATION_TARGET。

**修复**：改用 `@get:` 用点目标（注解作用于 getter，getter 属 function，在适用列表内），
运行时语义完全不变。提交 fc1ab4fc。

## 六、构建结果（run 43483686634，2026-11-14）

- stage=gradle-only：复用 run 43465128112 的 objdir 快照（跳过 80min mach build），
  Kotlin 修复仅涉及 fenix 层，Gecko 编译成果直接可用
- 全 job 通过：build / release 重建 / buildstate 分支快照（42×90MB 分块，3.75GB）
- Release android24-v1.0：pre-release，versionName 1.2.11（versionCode 2026456046），
  APK arm64-v8a 142.5MB + mapping.txt + 补丁与报告资产
- 后续调试迭代：stage=gradle-only 且 buildstate_run_id 留空 → 自动从 buildstate
  分支恢复，免 mach build、免 14 天 artifact 过期限制
