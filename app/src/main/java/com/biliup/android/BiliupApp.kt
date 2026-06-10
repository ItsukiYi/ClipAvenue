package com.biliup.android

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.biliup.android.bridge.PythonBridge

class BiliupApp : Application() {

    companion object {
        const val TAG = "biliup"
        const val CHANNEL_RECORDING = "biliup_recording"
        const val CHANNEL_UPLOAD = "biliup_upload"
        const val CHANNEL_ALERTS = "biliup_alerts"
        const val NOTIFICATION_RECORDING_ID = 1001
        const val NOTIFICATION_UPLOAD_ID = 1002

        var initError: String? = null
        var downloadDir: String = "/sdcard/biliup"
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()

        try {
            // 同步启动 Python 解释器
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(this))
                Log.i(TAG, "Python interpreter started")
            }

            // 同步初始化 Python 引擎
            val result = PythonBridge.init(this)
            Log.i(TAG, "Python init: $result")
            val j = org.json.JSONObject(result)
            downloadDir = j.optString("download_dir", downloadDir)
            if (j.optBoolean("success")) {
                initError = null
            } else {
                initError = j.optString("error", "未知错误")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Init failed", e)
            initError = e.message ?: e.toString()
        }
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channels = listOf(
                NotificationChannel(CHANNEL_RECORDING, "录制状态", NotificationManager.IMPORTANCE_LOW)
                    .apply { description = "显示录制进度和状态"; setShowBadge(false) },
                NotificationChannel(CHANNEL_UPLOAD, "上传进度", NotificationManager.IMPORTANCE_LOW)
                    .apply { description = "显示上传进度" },
                NotificationChannel(CHANNEL_ALERTS, "提醒", NotificationManager.IMPORTANCE_DEFAULT)
                    .apply { description = "录制完成、错误等提醒" },
            )
            val manager = getSystemService(NotificationManager::class.java)
            channels.forEach { manager.createNotificationChannel(it) }
        }
    }
}
