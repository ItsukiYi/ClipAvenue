package com.biliup.android.service

import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.biliup.android.BiliupApp
import com.biliup.android.MainActivity
import com.biliup.android.bridge.PythonBridge
import kotlinx.coroutines.*

/**
 * 前台录制服务 — 只做保活 (通知 + WakeLock)
 * 录制工作流完全由 Python 侧管理
 */
class RecordingService : Service() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var wakeLock: PowerManager.WakeLock? = null
    private var roomTitle: String = ""
    private var taskId: String = ""

    override fun onCreate() {
        super.onCreate()
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "biliup:recording")
            .also { it.acquire(24 * 60 * 60 * 1000L) }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        roomTitle = intent?.getStringExtra(EXTRA_TITLE) ?: "录制中"
        taskId = intent?.getStringExtra(EXTRA_TASK_ID) ?: ""

        startForeground(BiliupApp.NOTIFICATION_RECORDING_ID,
            buildNotification(roomTitle, "准备录制..."))

        // 定期检查录制状态，更新通知
        scope.launch {
            while (isActive) {
                delay(15_000)
                try {
                    val s = PythonBridge.getRecordingStatus(taskId)
                    // 简单解析看是否还在录制
                    if (!s.contains("\"running\": true") && !s.contains("\"running\":true")) {
                        updateNotification(roomTitle, "录制已停止")
                        delay(5000); stopSelf(); break
                    }
                    // 更新通知显示录制时长
                    val dur = extractField(s, "duration_str") ?: extractField(s, "duration") ?: ""
                    if (dur.isNotEmpty()) updateNotification(roomTitle, "录制中 $dur")
                } catch (_: Exception) { break }
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        scope.cancel()
        wakeLock?.let { if (it.isHeld) it.release() }
        super.onDestroy()
    }

    private fun buildNotification(title: String, content: String) =
        NotificationCompat.Builder(this, BiliupApp.CHANNEL_RECORDING)
            .setContentTitle("biliup: $title")
            .setContentText(content)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setOngoing(true)
            .setContentIntent(PendingIntent.getActivity(this, 0,
                Intent(this, MainActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
            .addAction(android.R.drawable.ic_media_pause, "停止",
                PendingIntent.getService(this, 1,
                    Intent(this, RecordingService::class.java).apply { action = ACTION_STOP },
                    PendingIntent.FLAG_IMMUTABLE))
            .build()

    private fun updateNotification(title: String, content: String) {
        (getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager)
            .notify(BiliupApp.NOTIFICATION_RECORDING_ID, buildNotification(title, content))
    }

    private fun extractField(json: String, key: String): String? {
        val m = Regex("\"$key\"\\s*:\\s*\"?([^\",}]+)\"?").find(json) ?: return null
        return m.groupValues.getOrNull(1)?.trim('"')
    }

    companion object {
        const val ACTION_START = "com.biliup.android.START_RECORDING"
        const val ACTION_STOP = "com.biliup.android.STOP_RECORDING"
        const val EXTRA_TITLE = "title"
        const val EXTRA_TASK_ID = "task_id"

        fun start(ctx: Context, title: String, taskId: String) {
            ctx.startForegroundService(Intent(ctx, RecordingService::class.java).apply {
                action = ACTION_START; putExtra(EXTRA_TITLE, title); putExtra(EXTRA_TASK_ID, taskId)
            })
        }
        fun stop(ctx: Context) {
            ctx.startService(Intent(ctx, RecordingService::class.java).apply { action = ACTION_STOP })
        }
    }
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) { /* TODO */ }
    }
}
