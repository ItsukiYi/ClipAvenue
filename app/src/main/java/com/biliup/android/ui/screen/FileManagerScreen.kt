package com.biliup.android.ui.screen

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.biliup.android.viewmodel.MainViewModel
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

data class StreamerDir(
    val name: String,
    val path: String,
    val fileCount: Int,
    val files: List<RecordingFile>,
    val coverUrl: String = "",
    val roomId: String = "",
)

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
    val downloadDir by viewModel.downloadDir.collectAsState()
    val context = LocalContext.current
    var selectedDir by remember { mutableStateOf<StreamerDir?>(null) }
    var isGridView by remember { mutableStateOf(false) }
    var previewFile by remember { mutableStateOf<RecordingFile?>(null) }

    val categories = remember(downloadDir) { buildCategories(downloadDir) }

    if (selectedDir != null) {
        // ─── 二级目录 ───
        Column(modifier = Modifier.fillMaxSize()) {
            // 顶部栏
            Row(
                modifier = Modifier.fillMaxWidth().padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = { selectedDir = null }) {
                    Icon(Icons.Filled.ArrowBack, "返回")
                }
                Text(selectedDir!!.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f))
                // 视图切换
                IconButton(onClick = { isGridView = !isGridView }) {
                    Icon(if (isGridView) Icons.Filled.List else Icons.Filled.GridView, "切换视图")
                }
            }

            if (isGridView) {
                LazyVerticalGrid(columns = GridCells.Fixed(2),
                    contentPadding = PaddingValues(8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(selectedDir!!.files) { file -> GridFileCard(file) { previewFile = file } }
                }
            } else {
                LazyColumn(contentPadding = PaddingValues(8.dp)) {
                    items(selectedDir!!.files) { file ->
                        SwipeableFileItem(
                            file = file,
                            onClick = { previewFile = file },
                            onDelete = { File(file.path).delete(); selectedDir = null; selectedDir = buildCategoryFromDir(File(file.path).parentFile) },
                            onOpen = {
                                val intent = Intent(Intent.ACTION_VIEW).apply {
                                    setDataAndType(Uri.fromFile(File(file.path)), "video/*")
                                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                                }
                                try { context.startActivity(intent) }
                                catch (_: Exception) { Toast.makeText(context, "无可用播放器", Toast.LENGTH_SHORT).show() }
                            },
                        )
                    }
                }
            }
        }
    } else {
        // ─── 一级目录: 按主播分类 ───
        Column(modifier = Modifier.fillMaxSize()) {
            Row(modifier = Modifier.padding(12.dp).fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically) {
                Text("录播文件", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text("${categories.size} 个分类", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
            }

            if (categories.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("暂无录播文件", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                }
            }

            LazyVerticalGrid(columns = GridCells.Fixed(2),
                contentPadding = PaddingValues(8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(categories) { cat ->
                    Card(
                        modifier = Modifier.fillMaxWidth().clickable { selectedDir = cat },
                        shape = RoundedCornerShape(12.dp),
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally,
                            modifier = Modifier.padding(16.dp)) {
                            // 圆形头像
                            Box(Modifier.size(64.dp).clip(RoundedCornerShape(12.dp))
                                .background(MaterialTheme.colorScheme.primaryContainer),
                                contentAlignment = Alignment.Center) {
                                Text(cat.name.take(2), fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.primary)
                            }
                            Spacer(Modifier.height(8.dp))
                            Text(cat.name, style = MaterialTheme.typography.titleSmall,
                                maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text("${cat.fileCount} 个文件", style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                        }
                    }
                }
            }
        }
    }

    // 视频预览
    if (previewFile != null) {
        VideoPlayerDialog(
            filePath = previewFile!!.path,
            title = previewFile!!.name,
            onDismiss = { previewFile = null },
        )
    }
}

@Composable
fun GridFileCard(file: RecordingFile, onClick: () -> Unit) {
    val sizeStr = when {
        file.size < 1048576 -> "${file.size / 1024}KB"
        else -> "${"%.1f".format(file.size / 1048576.0)}MB"
    }
    val date = SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()).format(Date(file.lastModified))

    Card(modifier = Modifier.fillMaxWidth().clickable { onClick() },
        shape = RoundedCornerShape(8.dp)) {
        Column(modifier = Modifier.padding(8.dp)) {
            // 缩略图占位
            Box(Modifier.fillMaxWidth().height(90.dp).clip(RoundedCornerShape(6.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.PlayArrow, null, modifier = Modifier.size(32.dp),
                    tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f))
            }
            Spacer(Modifier.height(6.dp))
            Text(file.name, style = MaterialTheme.typography.labelSmall, maxLines = 2,
                overflow = TextOverflow.Ellipsis)
            Text("$sizeStr · $date", style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
        }
    }
}

@Composable
fun SwipeableFileItem(
    file: RecordingFile,
    onClick: () -> Unit,
    onDelete: () -> Unit,
    onOpen: () -> Unit,
) {
    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = {
            if (it == SwipeToDismissBoxValue.EndToStart) { onDelete(); true }
            else if (it == SwipeToDismissBoxValue.StartToEnd) { onOpen(); false }
            else false
        }
    )
    SwipeToDismissBox(
        state = dismissState,
        backgroundContent = {
            Row(Modifier.fillMaxSize().padding(horizontal = 20.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.OpenInNew, "打开", tint = Color.White)
                Icon(Icons.Filled.Delete, "删除", tint = Color(0xFFFF5252))
            }
        },
    ) {
        Card(modifier = Modifier.fillMaxWidth().clickable { onClick() }) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(file.name, style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val sizeStr = when {
                    file.size < 1048576 -> "${file.size / 1024}KB"
                    else -> "${"%.1f".format(file.size / 1048576.0)}MB"
                }
                val date = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault()).format(Date(file.lastModified))
                Text("$sizeStr · $date", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
            }
        }
    }
}

fun buildCategories(rootDir: String): List<StreamerDir> {
    val root = File(rootDir)
    if (!root.exists()) return emptyList()
    return root.listFiles()?.filter { it.isDirectory && it.name != "biliup.db" }?.map { buildCategoryFromDir(it) }
        ?.sortedByDescending { it.files.maxOfOrNull { f -> f.lastModified } ?: 0L }
        ?: emptyList()
}

fun buildCategoryFromDir(dir: File): StreamerDir {
    val flvFiles = mutableListOf<RecordingFile>()
    fun scan(f: File) {
        if (f.isDirectory) f.listFiles()?.forEach { scan(it) }
        else if (f.name.endsWith(".flv") || f.name.endsWith(".mp4") || f.name.endsWith(".ts")) {
            flvFiles.add(RecordingFile(f.name, f.absolutePath, f.length(), f.lastModified()))
        }
    }
    scan(dir)
    flvFiles.sortByDescending { it.lastModified }
    // Extract roomId from path (e.g., "bilibili/12345")
    val parts = dir.absolutePath.split(File.separator)
    val roomId = parts.getOrNull(parts.size - 1) ?: ""
    val platform = parts.getOrNull(parts.size - 2) ?: ""
    return StreamerDir(
        name = dir.name.take(12),
        path = dir.absolutePath,
        fileCount = flvFiles.size,
        files = flvFiles,
        roomId = roomId,
    )
}
