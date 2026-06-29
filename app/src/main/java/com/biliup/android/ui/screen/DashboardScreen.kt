package com.biliup.android.ui.screen

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.biliup.android.viewmodel.MainViewModel
import java.io.File
import kotlinx.coroutines.launch

@Composable
fun DashboardScreen(
    viewModel: MainViewModel,
    scope: androidx.lifecycle.LifecycleCoroutineScope,
) {
    val recordings by viewModel.activeRecordings.collectAsState()
    val logs by viewModel.logs.collectAsState()
    val downloadDir by viewModel.downloadDir.collectAsState()
    val context = LocalContext.current
    var showLog by remember { mutableStateOf(false) }
    var fileLog by remember { mutableStateOf("加载中...") }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // 存储路径
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.7f)),
            ) {
                Row(
                    modifier = Modifier.padding(12.dp).fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.Folder, null, modifier = Modifier.size(18.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = downloadDir,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }

        // 状态卡片
        item {
            StatusCard(
                isRecording = recordings.any { it.isRunning },
                recordingCount = recordings.count { it.isRunning },
                totalRecorded = recordings.size,
            )
        }

        item {
            Text("当前录制", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        }

        if (recordings.isEmpty()) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                ) {
                    Column(modifier = Modifier.padding(24.dp).fillMaxWidth(),
                        horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Outlined.Videocam, null, modifier = Modifier.size(48.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(8.dp))
                        Text("暂无录制任务", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("前往「直播间」添加任务", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f))
                    }
                }
            }
        }

        items(recordings) { task ->
            RecordingCard(task, scope, viewModel, context)
        }

        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("最近日志", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                TextButton(onClick = {
                    scope.launch { fileLog = com.biliup.android.bridge.PythonBridge.getFileLog(200) }; showLog = true
                }) { Text("查看文件日志", style = MaterialTheme.typography.labelSmall) }
            }
        }
        items(logs.takeLast(10).reversed()) { log ->
            Surface(modifier = Modifier.fillMaxWidth(), shape = MaterialTheme.shapes.small,
                color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)) {
                Text(text = log, modifier = Modifier.padding(8.dp), style = MaterialTheme.typography.bodySmall)
            }
        }
    }

    // 文件日志对话框
    if (showLog) {
        val logScroll = rememberScrollState()
        AlertDialog(
            onDismissRequest = { showLog = false },
            title = { Text("录制日志 (biliup.log)") },
            text = {
                Text(text = fileLog, style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.fillMaxWidth().heightIn(max = 400.dp).verticalScroll(logScroll))
            },
            confirmButton = { TextButton(onClick = { showLog = false }) { Text("关闭") } },
        )
    }
}

@Composable
fun StatusCard(isRecording: Boolean, recordingCount: Int, totalRecorded: Int) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (isRecording) MaterialTheme.colorScheme.primaryContainer
            else MaterialTheme.colorScheme.surfaceVariant
        ),
    ) {
        Row(modifier = Modifier.padding(20.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically) {
            StatusItem(
                icon = if (isRecording) Icons.Filled.FiberManualRecord else Icons.Outlined.RadioButtonUnchecked,
                value = if (isRecording) "录制中" else "空闲",
                label = "状态",
                tint = if (isRecording) Color(0xFFFF5252) else MaterialTheme.colorScheme.onSurface,
            )
            StatusItem(Icons.Filled.Videocam, "$recordingCount", "直播中", MaterialTheme.colorScheme.primary)
            StatusItem(Icons.Filled.VideoLibrary, "$totalRecorded", "文件", MaterialTheme.colorScheme.secondary)
        }
    }
}

@Composable
fun StatusItem(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    value: String, label: String, tint: Color,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(icon, null, tint = tint, modifier = Modifier.size(28.dp))
        Spacer(Modifier.height(4.dp))
        Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
    }
}

@Composable
fun RecordingCard(
    task: MainViewModel.RecTask,
    scope: androidx.lifecycle.LifecycleCoroutineScope,
    viewModel: MainViewModel,
    context: android.content.Context,
) {
    var showPlayer by remember { mutableStateOf(false) }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(task.title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    Text("${task.platform} | 房间 ${task.roomId}", style = MaterialTheme.typography.bodySmall)
                    if (task.uname.isNotEmpty())
                        Text(task.uname, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                }
                if (task.isRunning) {
                    FilledTonalButton(onClick = { scope.launch { viewModel.stopRecording(task) } }) {
                        Icon(Icons.Filled.Stop, null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("停止")
                    }
                }
            }

            if (task.isRunning) {
                Spacer(Modifier.height(8.dp))
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                // 指标行
                Row(modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    // 文件持续
                    MetricChip("文件", task.segmentDur, Modifier.weight(1f))
                    // 录制耗时
                    MetricChip("耗时", task.duration, Modifier.weight(1f))
                    // 网速
                    MetricChip("网速", task.speedStr, Modifier.weight(1f))
                    // 速度比
                    val ratioStr = if (task.speedRatio > 0) "%.1fx".format(task.speedRatio) else "—"
                    val ratioColor = when {
                        task.speedRatio >= 0.9f -> MaterialTheme.colorScheme.primary
                        task.speedRatio >= 0.5f -> Color(0xFFFFA726)
                        task.speedRatio > 0f -> MaterialTheme.colorScheme.error
                        else -> MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f)
                    }
                    MetricChip("速度比", ratioStr, Modifier.weight(1f), ratioColor)
                }
            } else if (task.filePath.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    // 播放按钮
                    FilledTonalButton(onClick = { showPlayer = true }) {
                        Icon(Icons.Filled.PlayArrow, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("预览")
                    }
                    // 系统播放器
                    OutlinedButton(onClick = {
                        val f = File(task.filePath)
                        if (!f.exists()) {
                            android.widget.Toast.makeText(context, "文件不存在: ${task.filePath}", android.widget.Toast.LENGTH_LONG).show()
                            return@OutlinedButton
                        }
                        val intent = Intent(Intent.ACTION_VIEW).apply {
                            setDataAndType(Uri.fromFile(f), "video/*")
                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                        }
                        try { context.startActivity(intent) }
                        catch (_: Exception) {
                            android.widget.Toast.makeText(context, "无可用播放器, 路径: ${task.filePath}", android.widget.Toast.LENGTH_LONG).show()
                        }
                    }) {
                        Icon(Icons.Filled.OpenInNew, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("系统播放")
                    }
                }
            }
        }
    }

    // 内置视频预览
    if (showPlayer && task.filePath.isNotEmpty()) {
        VideoPlayerDialog(
            filePath = task.filePath,
            title = task.title,
            onDismiss = { showPlayer = false },
        )
    }
}

@Composable
fun MetricChip(label: String, value: String, modifier: Modifier = Modifier,
               valueColor: Color = MaterialTheme.colorScheme.onSurface) {
    Surface(
        modifier = modifier,
        shape = MaterialTheme.shapes.small,
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.7f),
    ) {
        Column(modifier = Modifier.padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold, color = valueColor)
            Text(label, style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
        }
    }
}
