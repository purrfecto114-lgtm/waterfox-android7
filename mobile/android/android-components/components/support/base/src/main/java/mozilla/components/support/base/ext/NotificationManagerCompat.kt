/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

package mozilla.components.support.base.ext

import android.os.Build
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationManagerCompat

/**
 * Returns whether notifications are enabled, catches any exception that was thrown from
 * [NotificationManagerCompat.areNotificationsEnabled] and returns false.
 */
@Suppress("TooGenericExceptionCaught")
fun NotificationManagerCompat.areNotificationsEnabledSafe(): Boolean {
    return try {
        areNotificationsEnabled()
    } catch (_: Exception) {
        false
    }
}

/**
 * If the channel does not exist or is null, this returns false. If the channel exists with importance more than
 * [NotificationManagerCompat.IMPORTANCE_NONE] and notifications are enabled for the app, this returns true.
 *
 * On API < 26 (before Android O) notification channels do not exist; the app-level
 * notification setting is the only gate. (Restored for API 24 / Android 7 support
 * so callers do not silently treat notifications as disabled.)
 *
 * @param channelId the id of the notification channel to check.
 * @return true if the channel is enabled, false otherwise.
 */
fun NotificationManagerCompat.isNotificationChannelEnabled(channelId: String): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
        return areNotificationsEnabledSafe()
    }

    val channel = getNotificationChannelSafe(channelId)
    return if (channel == null) {
        false
    } else {
        areNotificationsEnabledSafe() && channel.importance != NotificationManagerCompat.IMPORTANCE_NONE
    }
}

/**
 * Returns the notification channel with the given [channelId], or null if the channel does not exist, catches any
 * exception that was thrown by [NotificationManagerCompat.getNotificationChannelCompat] and returns null.
 *
 * @param channelId the id of the notification channel to check.
 */
@Suppress("TooGenericExceptionCaught")
private fun NotificationManagerCompat.getNotificationChannelSafe(channelId: String): NotificationChannelCompat? {
    return try {
        getNotificationChannelCompat(channelId)
    } catch (_: Exception) {
        null
    }
}
