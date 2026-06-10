package com.biliup.android.bridge

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object PythonBridge {

    private val py: Python get() = Python.getInstance()
    private var mainModule: PyObject? = null
    private var initialized = false

    fun init(context: Context, downloadDir: String? = null): String {
        mainModule = py.getModule("main")
        val dir = downloadDir ?: findOrCreateWorkDir(context)
        val result = mainModule!!.callAttr("init_app", dir)
        initialized = true
        return result.toString()
    }

    private fun checkInit() {
        if (!initialized || mainModule == null)
            throw IllegalStateException("Python 引擎未初始化")
    }

    /** 注册 Java 对象作为 Python 事件回调 */
    fun registerCallback(callback: Any) {
        mainModule?.callAttr("register_callback", callback)
    }

    private fun isWritable(dir: java.io.File): Boolean {
        return try {
            dir.mkdirs()
            val t = java.io.File(dir, ".test"); t.createNewFile() || t.exists()
        } catch (_: Exception) { false }
        finally { java.io.File(dir, ".test").delete() }
    }

    fun findOrCreateWorkDir(context: Context): String {
        val prefs = context.getSharedPreferences("biliup_prefs", Context.MODE_PRIVATE)
        // 用户手动设置过的路径（优先，但要可写）
        val saved = prefs.getString("work_dir", null)
        if (saved != null) {
            val d = java.io.File(saved)
            if (d.exists() && isWritable(d)) return saved
        }
        // 默认：app 专属外存目录
        val dir = java.io.File(context.getExternalFilesDir(null), "biliup")
        dir.mkdirs()
        prefs.edit().putString("work_dir", dir.absolutePath).apply()
        return dir.absolutePath
    }

    fun saveWorkDir(context: Context, dir: String) {
        context.getSharedPreferences("biliup_prefs", Context.MODE_PRIVATE).edit().putString("work_dir", dir).apply()
    }

    // ─── 数据库 ────────────────────────────────────────

    suspend fun dbGetRooms(): String = withContext(Dispatchers.IO) { checkInit(); mainModule!!.callAttr("db_get_rooms_json").toString() }
    fun dbAddRoom(roomId: String, platform: String) { try { mainModule?.callAttr("db_add_room", roomId, platform) } catch (_: Exception) {} }
    fun dbUpdateRoom(roomId: String, platform: String, title: String = "", uname: String = "", isLive: Int = 0) { try { mainModule?.callAttr("db_update_room", roomId, platform, title, uname, isLive) } catch (_: Exception) {} }
    fun dbRemoveRoom(roomId: String, platform: String) { try { mainModule?.callAttr("db_remove_room", roomId, platform) } catch (_: Exception) {} }
    suspend fun dbGetSessions(roomId: String = "", platform: String = ""): String = withContext(Dispatchers.IO) { checkInit(); mainModule!!.callAttr("db_get_sessions_json", roomId, platform, 50).toString() }
    suspend fun dbGetFiles(sessionId: Int = 0): String = withContext(Dispatchers.IO) { checkInit(); mainModule!!.callAttr("db_get_files_json", sessionId).toString() }
    suspend fun dbGetStats(): String = withContext(Dispatchers.IO) { checkInit(); mainModule!!.callAttr("db_get_stats_json").toString() }
    fun dbSetSetting(key: String, value: String) { try { mainModule?.callAttr("db_set_setting", key, value) } catch (_: Exception) {} }
    fun saveSetting(key: String, value: String) = dbSetSetting(key, value)

    // ─── B站 ────────────────────────────────────────────

    suspend fun getRoomInfo(roomId: String, qn: Int = 10000): String = withContext(Dispatchers.IO) { checkInit(); mainModule!!.callAttr("bilibili_get_room_info", roomId, qn).toString() }
    suspend fun getStreamUrl(roomId: String, qn: Int = 10000): String = withContext(Dispatchers.IO) { checkInit(); mainModule!!.callAttr("bilibili_get_stream_url", roomId, qn).toString() }

    // ─── 登录 ────────────────────────────────────────────

    suspend fun loginQrGenerate(): String = withContext(Dispatchers.IO) { checkInit(); mainModule!!.callAttr("bilibili_login_qr_generate").toString() }
    suspend fun loginQrPoll(): String = withContext(Dispatchers.IO) { checkInit(); mainModule!!.callAttr("bilibili_login_qr_poll").toString() }
    suspend fun setCookies(c: String) = withContext(Dispatchers.IO) { checkInit(); mainModule!!.callAttr("bilibili_set_cookies", c) }
    fun getCookies(): String = mainModule?.callAttr("bilibili_get_cookies")?.toString() ?: ""
    fun isLoggedIn(): Boolean = mainModule?.callAttr("bilibili_is_logged_in")?.toBoolean() ?: false
    fun getUserInfo(): String = mainModule?.callAttr("bilibili_get_user_info")?.toString() ?: "{}"

    // ─── 录制 (简化: Python做全部工作) ──────────────────

    suspend fun startRecording(roomId: String, platform: String = "bilibili",
                               title: String = "", uname: String = "",
                               segmentTime: Int = 3600, qn: Int = 10000): String = withContext(Dispatchers.IO) {
        checkInit()
        mainModule!!.callAttr("start_recording", roomId, platform, title, uname, segmentTime, qn).toString()
    }

    suspend fun stopRecording(taskId: String): String = withContext(Dispatchers.IO) {
        mainModule!!.callAttr("stop_recording", taskId).toString()
    }

    suspend fun stopAllRecordings(): String = withContext(Dispatchers.IO) {
        mainModule!!.callAttr("stop_all_recordings").toString()
    }

    suspend fun getRecordingStatus(taskId: String = ""): String = withContext(Dispatchers.IO) {
        mainModule!!.callAttr("get_recording_status", taskId).toString()
    }

    // ─── 上传 ────────────────────────────────────────────

    suspend fun uploadVideo(filePath: String, title: String, platform: String = "bilibili",
                            desc: String = "", tags: String = ""): String = withContext(Dispatchers.IO) {
        mainModule!!.callAttr("upload_video", filePath, title, platform, desc, tags).toString()
    }

    fun setDownloadDir(dir: String) { try { mainModule?.callAttr("set_download_dir", dir) } catch (_: Exception) {} }
    suspend fun getFileLog(lines: Int = 100): String = withContext(Dispatchers.IO) {
        mainModule?.callAttr("get_file_log", lines)?.toString() ?: "无法获取日志"
    }

    fun cleanup() { mainModule?.callAttr("cleanup"); mainModule = null }
}
