package com.biliup.android.ui.screen

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.biliup.android.viewmodel.MainViewModel
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

data class RecordingFile(
    val name: String,
    val path: String,
    val size: Long,
    val lastModified: Long,
)

@Composable
fun FileManagerScreen(
    viewModel: MainViewModel,
    scope: androidx.lifecycle.LifecycleCoroutineScope,
) {
    val context = LocalContext.current
    val downloadDir by viewModel.downloadDir.collectAsState()
    var files by remember { mutableStateOf(scanFiles(downloadDir)) }
    var selectedFile by remember { mutableStateOf<RecordingFile?>(null) }
    var showDeleteDialog by remember { mutableStateOf<RecordingFile?>(null) }

    // 进入页面时自动刷新
    LaunchedEffect(downloadDir) {
        files = scanFiles(downloadDir)
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        // 标题栏
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "录播文件管理器",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                // 刷新按钮
                IconButton(onClick = { files = scanFiles(downloadDir) }) {
                    Icon(Icons.Filled.Refresh, "刷新")
                }
            }
            Spacer(Modifier.height(4.dp))
            Text(
                text = downloadDir,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                "${files.size} 个录播文件",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        if (files.isEmpty()) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp).fillMaxWidth(),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Icon(Icons.Outlined.VideoLibrary, null, modifier = Modifier.size(48.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(8.dp))
                        Text("暂无录播文件", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("录制完成后会自动出现在这里", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f))
                    }
                }
            }
        }

        items(files) { file ->
            FileCard(
                file = file,
                isExpanded = selectedFile == file,
                onPlay = { selectedFile = file },
                onSystemPlay = {
                    val intent = Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(Uri.fromFile(File(file.path)), "video/*")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    try { context.startActivity(intent) } catch (_: Exception) {}
                },
                onDelete = { showDeleteDialog = file },
            )
        }

        item { Spacer(Modifier.height(80.dp)) }
    }

    // 视频预览
    if (selectedFile != null) {
        VideoPlayerDialog(
            filePath = selectedFile!!.path,
            title = selectedFile!!.name,
            onDismiss = { selectedFile = null },
        )
    }

    // 删除确认
    if (showDeleteDialog != null) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = null },
            title = { Text("删除文件") },
            text = { Text("确定要删除 ${showDeleteDialog!!.name} 吗？") },
            confirmButton = {
                Button(
                    onClick = {
                        File(showDeleteDialog!!.path).delete()
                        showDeleteDialog = null
                        files = scanFiles(downloadDir)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                ) { Text("删除") }
            },
            dismissButton = { TextButton(onClick = { showDeleteDialog = null }) { Text("取消") } },
        )
    }
}

@Composable
fun FileCard(
    file: RecordingFile,
    isExpanded: Boolean,
    onPlay: () -> Unit,
    onSystemPlay: () -> Unit,
    onDelete: () -> Unit,
) {
    val dateFormat = remember { SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault()) }
    val sizeStr = when {
        file.size < 1024 -> "${file.size} B"
        file.size < 1048576 -> "${file.size / 1024} KB"
        file.size < 1073741824 -> "${"%.1f".format(file.size / 1048576.0)} MB"
        else -> "${"%.2f".format(file.size / 1073741824.0)} GB"
    }
    val dateStr = dateFormat.format(Date(file.lastModified))

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Outlined.VideoFile, null, tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(32.dp))
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        file.name,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        "$sizeStr · $dateStr",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilledTonalButton(onClick = onPlay) {
                    Icon(Icons.Filled.PlayArrow, null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("预览")
                }
                OutlinedButton(onClick = onSystemPlay) {
                    Icon(Icons.Filled.OpenInNew, null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("系统播放")
                }
                Spacer(Modifier.weight(1f))
                IconButton(onClick = onDelete) {
                    Icon(Icons.Filled.Delete, "删除", tint = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}

fun scanFiles(dir: String): List<RecordingFile> {
    val d = File(dir)
    if (!d.exists() || !d.isDirectory) return emptyList()

    val flvFiles = mutableListOf<RecordingFile>()
    // 递归扫描目录
    fun scan(f: File) {
        if (f.isDirectory) {
            f.listFiles()?.forEach { scan(it) }
        } else if (f.name.endsWith(".flv") || f.name.endsWith(".mp4") || f.name.endsWith(".ts")) {
            flvFiles.add(RecordingFile(
                name = f.name,
                path = f.absolutePath,
                size = f.length(),
                lastModified = f.lastModified(),
            ))
        }
    }
    scan(d)
    // 按时间倒序
    flvFiles.sortByDescending { it.lastModified }
    return flvFiles
}
