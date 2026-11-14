/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

@file:OptIn(ExperimentalAndroidComponentsApi::class)

package mozilla.components.feature.ipprotection.auth.gpi

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import mozilla.components.ExperimentalAndroidComponentsApi
import mozilla.components.concept.engine.ipprotection.IPProtectionHandler
import mozilla.components.concept.integrity.IntegrityClient
import mozilla.components.feature.ipprotection.auth.IPProtectionAuthProvider
import mozilla.components.support.base.log.logger.Logger

/**
 * [IPProtectionAuthProvider] that wires Google Play Integrity (GPI) warm-up and token retrieval into the IP protection
 * handler.
 *
 * N.B: This is intentionally kept separate from [mozilla.components.feature.ipprotection.IPProtectionFeature] so GPI
 * support can be composed in without affecting the default behavior.
 *
 * @param integrityClient the [IntegrityClient] to supply GPI tokens to the proxy service.
 */
// android24 fork (de-GMS): 参数类型改为 concept IntegrityClient（lib-integrity-googleplay 已移除，
// fenix 侧传入 no-op 实现）；不再需要 forConsumer 遥测包装
class IPProtectionGpiProvider(private val integrityClient: IntegrityClient) : IPProtectionAuthProvider {
    private val logger = Logger("IPP:Gpi")

    override fun configure(handler: IPProtectionHandler, scope: CoroutineScope) {
        handler.setGpiProvider(
            object : IPProtectionHandler.GpiProvider {
                override fun warmUp(onComplete: (Boolean) -> Unit) {
                    scope.launch {
                        onComplete(integrityClient.warmUp())
                    }
                }

                override fun getToken(onComplete: (String?) -> Unit) {
                    scope.launch {
                        val token =
                            integrityClient
                                .request()
                                .onFailure { logger.error("GPI token request failed", it) }
                                .getOrNull()
                                ?.value
                        onComplete(token)
                    }
                }
            }
        )
    }
}
