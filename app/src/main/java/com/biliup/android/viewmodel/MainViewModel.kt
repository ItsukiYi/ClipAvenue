package com.biliup.android.viewmodel

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.biliup.android.BiliupApp
import com.biliup.android.bridge.PythonBridge
import com.biliup.android.service.RecordingService
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import org.json.JSONArray
import org.json.JSONObject

class MainViewModel : ViewModel() {

    data class RecTask(val taskId: String = "", val roomId: String = "", val platform: String = "bilibili",
                       val title: String = "", val uname: String = "", val isRunning: Boolean = false,
                       val duration: String = "", val segmentDur: String = "",
                       val speedStr: String = "", val speedRatio: Float = 0f,
                       val filePath: String = "", val startTime: Long = 0)

    data class RoomItem(val roomId: String = "", val platform: String = "bilibili",
                        val title: String = "", val uname: String = "",
                        val isLive: Boolean = false, val isChecking: Boolean = false,
                        val autoRecord: Boolean = true, val isMonitored: Boolean = true,
                        val qn: Int = 10000)

    private var _ctx: Context? = null
    private var _polling = false; private var _pollInterval = 60_000L; private var _pollJob: Job? = null
    private var _offlineDetected = mutableMapOf<String, Long>()  // roomId → 首次检测到下播的时间
    private var _startTimes = mutableMapOf<String, Long>()  // taskId → startTime

    private val _tasks = MutableStateFlow<List<RecTask>>(emptyList())
    val activeRecordings: StateFlow<List<RecTask>> = _tasks.asStateFlow()

    private val _rooms = MutableStateFlow<List<RoomItem>>(emptyList())
    val rooms: StateFlow<List<RoomItem>> = _rooms.asStateFlow()

    private val _logs = MutableStateFlow<List<String>>(emptyList())
    val logs: StateFlow<List<String>> = _logs.asStateFlow()

    private val _uploads = MutableStateFlow<List<UploadItem>>(emptyList())
    val uploads: StateFlow<List<UploadItem>> = _uploads.asStateFlow()

    private val _downloadDir = MutableStateFlow(BiliupApp.downloadDir)
    val downloadDir: StateFlow<String> = _downloadDir.asStateFlow()

    data class UploadItem(val taskId: String = "", val title: String = "", val progress: Float = 0f,
                          val status: String = "pending", val statusText: String = "等待上传")

    // ─── 初始化 ────────────────────────────────────────

    fun init(ctx: Context) {
        _ctx = ctx
        _downloadDir.value = BiliupApp.downloadDir
        registerPythonCallback()
        loadSavedRooms()
    }

    /** Java 回调对象 — Python 侧直接调用 onEvent() */
    @Suppress("unused") // Python calls this
    fun onPythonEvent(event: String, data: String) {
        viewModelScope.launch { handlePythonEvent(event, data) }
    }

    /** 注册 Python 事件回调 — 核心：事件驱动 UI 更新 */
    private fun registerPythonCallback() {
        PythonBridge.registerCallback(this)
    }

    private fun handlePythonEvent(event: String, jsonStr: String) {
        try {
            val j = JSONObject(jsonStr)
            when (event) {
                "record" -> handleRecordEvent(j)
                "upload" -> handleUploadEvent(j)
            }
        } catch (_: Exception) {}
    }

    private fun handleRecordEvent(j: JSONObject) {
        val type = j.optString("type", "")
        val tid = j.optString("task_id", "")
        when (type) {
            "started" -> {
                val t = _tasks.value.find { it.taskId == tid } ?: return
                _startTimes[tid] = System.currentTimeMillis()
                updateTask(t.copy(isRunning = true))
                startDurationTimer(tid)
            }
            "segment" -> {
                val fp = j.optString("file", "")
                val t = _tasks.value.find { it.taskId == tid } ?: return
                updateTask(t.copy(filePath = fp))
            }
            "stopped" -> {
                val t = _tasks.value.find { it.taskId == tid } ?: return
                val fp = j.optString("file", t.filePath)
                updateTask(t.copy(isRunning = false, duration = "已停止", filePath = fp))
                RecordingService.stop(_ctx!!)
                _startTimes.remove(tid)
            }
            "reconnecting" -> {
                val retry = j.optInt("retry", 0)
                addLog("[$tid] 重连中 ($retry)")
            }
        }
    }

    private fun handleUploadEvent(j: JSONObject) {
        val tid = j.optString("task_id", "")
        val progress = j.optDouble("progress", 0.0).toFloat()
        val status = j.optString("status", "")
        _uploads.value = _uploads.value.map {
            if (it.taskId == tid) it.copy(progress = progress,
                statusText = when (status) { "done" -> "完成"; "uploading" -> "${(progress*100).toInt()}%"; else -> status })
            else it
        }
    }

    private fun startDurationTimer(tid: String) {
        viewModelScope.launch {
            while (_tasks.value.any { it.taskId == tid && it.isRunning }) {
                delay(2000)  // 每2秒刷新指标
                try {
                    val s = org.json.JSONObject(PythonBridge.getRecordingStatus(tid))
                    val dur = s.optString("duration_str", "")
                    val seg = s.optString("segment_str", "")
                    val speed = s.optString("speed_str", "")
                    val ratio = s.optDouble("speed_ratio", 0.0).toFloat()
                    updateTask(_tasks.value.find { it.taskId == tid }?.copy(
                        duration = dur, segmentDur = seg, speedStr = speed, speedRatio = ratio
                    ) ?: return@launch)
                } catch (_: Exception) {}
            }
        }
    }

    private fun updateTask(t: RecTask) { _tasks.value = _tasks.value.map { if (it.taskId == t.taskId) t else it } }
    fun addLog(msg: String) { val ts = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date()); _logs.value = (_logs.value + "[$ts] $msg").takeLast(200) }

    fun updateDownloadDir(dir: String) {
        val old = _downloadDir.value; if (old == dir) return
        viewModelScope.launch {
            try {
                val nd = java.io.File(dir); nd.mkdirs()
                val od = java.io.File(old, "biliup.db"); val ndb = java.io.File(nd, "biliup.db")
                if (od.exists() && !ndb.exists()) { java.io.FileInputStream(od).use { i -> java.io.FileOutputStream(ndb).use { o -> i.copyTo(o) } }; addLog("数据库已迁移") }
                var c = 0; migrateDir(java.io.File(old), nd) { c++ }; if (c > 0) addLog("已迁移 $c 个文件")
            } catch (e: Exception) { addLog("迁移: ${e.message}") }
        }
        _downloadDir.value = dir; BiliupApp.downloadDir = dir
    }

    // ─── 房间 ──────────────────────────────────────────

    fun addRoom(url: String, platform: String) {
        viewModelScope.launch {
            val rid = extractRoomId(url, platform); if (rid.isEmpty()) return@launch
            val room = RoomItem(roomId = rid, platform = platform, isChecking = true)
            _rooms.value = _rooms.value + room; PythonBridge.dbAddRoom(rid, platform); checkRoom(room)
        }
    }

    fun checkRoom(room: RoomItem) {
        viewModelScope.launch {
            updateRoom(room.copy(isChecking = true))
            try {
                val j = JSONObject(PythonBridge.getRoomInfo(room.roomId, room.qn))
                val err = j.optString("error", ""); if (err.isNotEmpty()) addLog("API: $err")
                val title = j.optString("title", ""); val uname = j.optString("uname", "")
                val live = j.optInt("live_status", 0) == 1
                updateRoom(room.copy(title = title.ifEmpty { "房间 ${room.roomId}" }, uname = uname, isLive = live, isChecking = false))
                if (title.isNotEmpty()) PythonBridge.dbUpdateRoom(room.roomId, room.platform, title, uname, if (live) 1 else 0)
                addLog("${room.roomId}: ${if (live) "🔴 直播中" else "未开播"} $title")
                // 检测到开播 + 自动录制 → 立刻开始
                if (live && room.autoRecord && !_tasks.value.any { it.roomId == room.roomId && it.isRunning }) {
                    addLog("🔴 开播: ${title.ifEmpty { room.roomId }} → 自动录制")
                    startRecording(room)
                }
            } catch (e: Exception) { updateRoom(room.copy(isChecking = false)); addLog("检测失败: ${e.message}") }
        }
    }

    private fun updateRoom(r: RoomItem) { _rooms.value = _rooms.value.map { if (it.roomId == r.roomId) r else it } }

    // ─── 轮询 ──────────────────────────────────────────

    fun startPolling() {
        if (_polling) return; _polling = true; _pollJob?.cancel()
        _pollJob = viewModelScope.launch {
            while (_polling) {
                delay((_pollInterval * (0.8 + Math.random() * 0.4)).toLong())
                if (!_polling) break
                for (room in _rooms.value.filter { it.isMonitored }) {
                    if (!_polling) break; delay((500 + Math.random() * 1000).toLong())
                    try {
                        val j = JSONObject(PythonBridge.getRoomInfo(room.roomId, room.qn))
                        val err = j.optString("error", ""); val title = j.optString("title", "")
                        val uname = j.optString("uname", ""); val live = j.optInt("live_status", 0) == 1
                        if (err.contains("412") || err.contains("429")) { delay(30_000); continue }
                        val prev = _rooms.value.find { it.roomId == room.roomId }
                        if (title.isNotEmpty()) PythonBridge.dbUpdateRoom(room.roomId, room.platform, title, uname, if (live) 1 else 0)
                        updateRoom(room.copy(title = title.ifEmpty { room.title }, uname = uname.ifEmpty { room.uname }, isLive = live))
                        if (live && room.autoRecord && (prev == null || !prev.isLive) && !_tasks.value.any { it.roomId == room.roomId && it.isRunning }) {
                            addLog("🔴 开播: ${title.ifEmpty { room.roomId }} → 自动录制"); startRecording(room)
                            _offlineDetected.remove(room.roomId)
                        }
                        // 下播检测: 首次→记录时间, 持续下播60s→停止录制
                        if (!live) {
                            val recording = _tasks.value.find { it.roomId == room.roomId && it.isRunning }
                            if (recording != null) {
                                val firstOff = _offlineDetected[room.roomId]
                                if (firstOff == null) {
                                    _offlineDetected[room.roomId] = System.currentTimeMillis()
                                    addLog("⚪ ${room.roomId}: 疑似下播, 将在60s后确认")
                                } else if (System.currentTimeMillis() - firstOff > 60_000) {
                                    addLog("⚪ ${room.roomId}: 确认下播, 停止录制")
                                    stopRecording(recording)
                                    _offlineDetected.remove(room.roomId)
                                }
                            } else {
                                _offlineDetected.remove(room.roomId)
                            }
                        } else {
                            _offlineDetected.remove(room.roomId)  // 恢复直播, 重置
                        }
                    } catch (_: Exception) {}
                }
            }
        }
    }

    fun stopPolling() { _polling = false; _pollJob?.cancel(); _pollJob = null }
    fun setPollInterval(s: Int) { _pollInterval = s * 1000L; if (_polling) { stopPolling(); startPolling() } }

    private suspend fun initialPoll() {
        addLog("初始轮询...")
        for (room in _rooms.value.filter { it.isMonitored }) {
            delay((500 + Math.random() * 1000).toLong())
            try {
                val j = JSONObject(PythonBridge.getRoomInfo(room.roomId, room.qn))
                val title = j.optString("title", ""); val uname = j.optString("uname", "")
                val live = j.optInt("live_status", 0) == 1
                updateRoom(room.copy(title = title.ifEmpty { room.title }, uname = uname.ifEmpty { room.uname }, isLive = live))
                if (live && room.autoRecord && !_tasks.value.any { it.roomId == room.roomId && it.isRunning }) {
                    addLog("🔴 开播: ${title.ifEmpty { room.roomId }} → 自动录制"); startRecording(room)
                }
                if (!live) {
                    val rec = _tasks.value.find { it.roomId == room.roomId && it.isRunning }
                    if (rec != null) {
                        _offlineDetected[room.roomId] = System.currentTimeMillis()
                        addLog("⚪ ${room.roomId}: 下播中, 等待60s确认")
                    }
                }
            } catch (_: Exception) {}
        }
        addLog("初始轮询完成")
    }
    fun setRoomAutoRecord(room: RoomItem, auto: Boolean) {
        updateRoom(room.copy(autoRecord = auto))
        if (auto && room.isLive && !_tasks.value.any { it.roomId == room.roomId && it.isRunning }) {
            addLog("正在直播 → 立即录制"); viewModelScope.launch { startRecording(room) }
        }
    }
    fun setRoomMonitored(room: RoomItem, m: Boolean) { updateRoom(room.copy(isMonitored = m)) }
    fun setRoomQn(room: RoomItem, qn: Int) { updateRoom(room.copy(qn = qn)); addLog("${room.roomId}: 画质 → $qn") }

    // ─── 录制 (精简: 只管发指令+启动Service保活) ──────

    fun startRecording(room: RoomItem) {
        val ctx = _ctx ?: return
        // 防重复：已有同房间的录制在运行
        if (_tasks.value.any { it.roomId == room.roomId && it.isRunning }) {
            addLog("${room.roomId}: 已在录制中, 跳过")
            return
        }
        viewModelScope.launch {
            val result = JSONObject(PythonBridge.startRecording(room.roomId, room.platform, room.title, room.uname, qn = room.qn))
            if (!result.optBoolean("success")) { addLog("录制启动失败: ${result.optString("error")}"); return@launch }
            val tid = result.optString("task_id", "")
            val task = RecTask(taskId = tid, roomId = room.roomId, platform = room.platform, title = room.title, uname = room.uname, isRunning = true, startTime = System.currentTimeMillis())
            _tasks.value = _tasks.value + task
            _startTimes[tid] = System.currentTimeMillis()
            startDurationTimer(tid)
            RecordingService.start(ctx, room.title.ifEmpty { "房间${room.roomId}" }, tid)
            addLog("录制已启动: ${room.title.ifEmpty { room.roomId }}")
        }
    }

    suspend fun stopRecording(task: RecTask) {
        PythonBridge.stopRecording(task.taskId)
        addLog("停止录制: ${task.title}")
    }

    // ─── 持久化 ────────────────────────────────────────

    private fun loadSavedRooms() {
        viewModelScope.launch {
            try {
                val arr = JSONArray(PythonBridge.dbGetRooms())
                val list = mutableListOf<RoomItem>()
                for (i in 0 until arr.length()) { val o = arr.getJSONObject(i); list.add(RoomItem(roomId = o.optString("room_id", ""), platform = o.optString("platform", "bilibili"), title = o.optString("title", ""), uname = o.optString("uname", ""))) }
                if (list.isNotEmpty()) { _rooms.value = list; addLog("已恢复 ${list.size} 个直播间") }
                startPolling()
                // 启动后立即轮询一次
                delay(1000)
                initialPoll()
            } catch (e: Exception) { addLog("加载失败: ${e.message}") }
        }
    }

    // ─── 上传 ──────────────────────────────────────────

    suspend fun uploadVideo(task: RecTask) { if (task.filePath.isEmpty()) return; val item = UploadItem(taskId = task.taskId, title = task.title, status = "uploading", statusText = "上传中..."); _uploads.value = _uploads.value + item; try { val r = JSONObject(PythonBridge.uploadVideo(task.filePath, task.title, task.platform)); val ok = r.optBoolean("success"); _uploads.value = _uploads.value.map { if (it.taskId == task.taskId) it.copy(status = if (ok) "done" else "failed", progress = 1f, statusText = if (ok) "完成" else r.optString("message", "失败")) else it } } catch (e: Exception) { _uploads.value = _uploads.value.map { if (it.taskId == task.taskId) it.copy(status = "failed", statusText = e.message ?: "异常") else it } } }

    // ─── 工具 ──────────────────────────────────────────

    private fun migrateDir(src: java.io.File, dst: java.io.File, cb: () -> Unit) {
        src.listFiles()?.forEach { f -> if (f.name in listOf(".test", ".writetest")) return@forEach; val d = java.io.File(dst, f.name); if (f.isDirectory) { d.mkdirs(); migrateDir(f, d, cb) } else if (!d.exists()) { try { java.io.FileInputStream(f).use { i -> java.io.FileOutputStream(d).use { o -> i.copyTo(o) } }; cb() } catch (_: Exception) {} } }
    }

    private fun extractRoomId(url: String, platform: String): String {
        if (url.matches(Regex("^\\d+$"))) return url
        for (p in when (platform) { "bilibili" -> listOf(Regex("live\\.bilibili\\.com/(\\d+)"), Regex("b23\\.tv/\\w+")); "douyin" -> listOf(Regex("live\\.douyin\\.com/(\\d+)"), Regex("douyin\\.com/user/(\\w+)")); else -> emptyList() }) { p.find(url)?.let { return it.groupValues.getOrElse(1) { "" } } }
        return url
    }
}
