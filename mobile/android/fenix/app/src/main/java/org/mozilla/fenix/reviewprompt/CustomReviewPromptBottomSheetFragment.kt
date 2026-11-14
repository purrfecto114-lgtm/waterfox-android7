/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

package org.mozilla.fenix.reviewprompt

import android.app.Dialog
import android.content.ActivityNotFoundException
import android.content.DialogInterface
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.net.toUri
import androidx.fragment.app.Fragment
import androidx.fragment.compose.content
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewModelScope
import com.google.android.material.R as materialR
import com.google.android.material.bottomsheet.BottomSheetDialogFragment
import kotlinx.coroutines.launch
import mozilla.components.lib.state.helpers.StoreProvider.Companion.fragmentStore
import mozilla.components.lib.state.helpers.StoreProvider.Companion.storeProvider
import org.mozilla.fenix.ext.openInNewTab
import org.mozilla.fenix.ext.requireComponents
import org.mozilla.fenix.settings.SupportUtils
import org.mozilla.fenix.reviewprompt.CustomReviewPromptAction.LeaveFeedbackButtonClicked
import org.mozilla.fenix.reviewprompt.CustomReviewPromptAction.NegativePrePromptButtonClicked
import org.mozilla.fenix.reviewprompt.CustomReviewPromptAction.PositivePrePromptButtonClicked
import org.mozilla.fenix.reviewprompt.CustomReviewPromptAction.RateButtonClicked
import org.mozilla.fenix.reviewprompt.ui.CustomReviewPrompt
import org.mozilla.fenix.theme.FirefoxTheme

/** A bottom sheet fragment for displaying [CustomReviewPrompt]. */
class CustomReviewPromptBottomSheetFragment : BottomSheetDialogFragment() {
    private val store by
        fragmentStore(CustomReviewPromptState.PrePrompt) {
            CustomReviewPromptStore(
                initialState = it,
                middleware =
                    listOf(
                        CustomReviewPromptNavigationMiddleware(storeProvider.viewModelScope),
                        CustomReviewPromptTelemetryMiddleware(),
                    ),
            )
        }

    override fun onCreateDialog(savedInstanceState: Bundle?): Dialog {
        return super.onCreateDialog(savedInstanceState).apply {
            setOnShowListener {
                val bottomSheet = findViewById<View?>(materialR.id.design_bottom_sheet)
                bottomSheet?.setBackgroundResource(android.R.color.transparent)
            }
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?,
    ) = content {
        val state by store.stateFlow.collectAsState(initial = CustomReviewPromptState.PrePrompt)

        LaunchedEffect(Unit) {
            store.dispatch(CustomReviewPromptAction.Displayed)
        }

        FirefoxTheme {
            CustomReviewPrompt(
                customReviewPromptState = state,
                onDismissRequest = { dismissAllowingStateLoss() },
                onNegativePrePromptButtonClick = { store.dispatch(NegativePrePromptButtonClicked) },
                onPositivePrePromptButtonClick = { store.dispatch(PositivePrePromptButtonClicked) },
                onRateButtonClick = { store.dispatch(RateButtonClicked) },
                onLeaveFeedbackButtonClick = { store.dispatch(LeaveFeedbackButtonClicked) },
            )
        }
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        viewLifecycleOwner.lifecycleScope.launch {
            store.navigationEvents.collect { event ->
                when (event) {
                    CustomReviewPromptNavigationEvent.Dismiss -> dismissAllowingStateLoss()

                    CustomReviewPromptNavigationEvent.OpenPlayStoreReviewPrompt -> {
                        val activity = activity ?: return@collect
                        // android24 fork (de-GMS): Play In-App Review API 已移除，
                        // 直接打开商店评分页；无 Play 商店（ActivityNotFoundException）时回退网页
                        try {
                            activity.startActivity(Intent(Intent.ACTION_VIEW, SupportUtils.RATE_APP_URL.toUri()))
                        } catch (e: ActivityNotFoundException) {
                            openInNewTab(SupportUtils.FENIX_PLAY_STORE_URL)
                        }
                    }

                    is CustomReviewPromptNavigationEvent.OpenInNewTab -> openInNewTab(event.url)
                }
            }
        }
    }

    override fun onDismiss(dialog: DialogInterface) {
        super.onDismiss(dialog)
        store.dispatch(CustomReviewPromptAction.Dismissed)
    }

    companion object {
        private const val TAG = "CustomReviewPromptBottomSheetFragment"

        /**
         * Shows the custom review prompt, unless it is already shown.
         *
         * @param fragment The [Fragment] whose fragment manager shows the prompt.
         */
        fun showPrompt(fragment: Fragment) {
            if (fragment.parentFragmentManager.findFragmentByTag(TAG) != null) {
                return
            }

            CustomReviewPromptBottomSheetFragment().showNow(fragment.parentFragmentManager, TAG)
        }
    }
}
