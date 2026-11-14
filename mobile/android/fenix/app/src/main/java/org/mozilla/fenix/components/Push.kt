/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

package org.mozilla.fenix.components

import android.content.Context
import mozilla.components.feature.push.AutoPushFeature
import org.mozilla.fenix.perf.lazyMonitored

/**
 * Component group for push services. These components use services that strongly depend on push messaging (e.g.
 * WebPush, SendTab).
 *
 * android24 fork (de-GMS): `lib-push-firebase`（firebase-messaging）依赖已移除，
 * 不存在可用的推送服务实现，[feature] 恒为 null。
 * 与移除前行为完全一致 —— Waterfox 从未配置 Firebase 项目
 * （`pushConfig` 因找不到 `pref_key_push_project_id` 资源恒为 null），
 * 所有调用点均为 `components.push.feature?.let` 的 null 安全形式，自动跳过。
 */
class Push(val context: Context) {
    val feature: AutoPushFeature? by lazyMonitored { null }
}
