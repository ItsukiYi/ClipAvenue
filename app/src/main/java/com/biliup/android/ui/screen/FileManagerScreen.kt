package com.biliup.android.ui.screen

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
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
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.biliup.android.viewmodel.MainViewModel
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import kotlin.math.roundToInt

data class StreamerDir(
    val name: String, val path: String, val fileCount: Int,
    val files: List<RecFile>, val coverUrl: String = "",
)

data class RecFile(
    val name: String, val path: String, val size: Long, val lastModified: Long,
)

@Composable
fun FileManagerScreen(
    viewModel: MainViewModel,
    scope: androidx.lifecycle.LifecycleCoroutineScope,
) {
    val downloadDir by viewModel.downloadDir.collectAsState()
    val rooms by viewModel.rooms.collectAsState()
    val context = LocalContext.current
    var selectedDir by remember { mutableStateOf<StreamerDir?>(null) }
    var isGridView by remember { mutableStateOf(false) }
    var previewFile by remember { mutableStateOf<RecFile?>(null) }
    var deleteConfirm by remember { mutableStateOf<RecFile?>(null) }

    // 用房间数据映射目录名
    val roomMap = remember(rooms) { rooms.associateBy { it.roomId } }
    val categories = remember(downloadDir, rooms) { buildCategories(downloadDir, roomMap) }

    if (selectedDir != null) {
        val dir = selectedDir!!
        Column(modifier = Modifier.fillMaxSize()) {
            Row(modifier = Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { selectedDir = null }) { Icon(Icons.Filled.ArrowBack, "返回") }
                Column(modifier = Modifier.weight(1f)) {
                    Text(dir.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text("${dir.fileCount} 个文件", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                }
                IconButton(onClick = { isGridView = !isGridView }) {
                    Icon(if (isGridView) Icons.Filled.List else Icons.Filled.GridView, "切换视图")
                }
            }

            if (isGridView) {
                LazyVerticalGrid(columns = GridCells.Fixed(2), contentPadding = PaddingValues(8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(dir.files) { f -> GridFileCard(f, onClick = { previewFile = f }) }
                }
            } else {
                LazyColumn(contentPadding = PaddingValues(8.dp)) {
                    items(dir.files) { f ->
                        SwipeToReveal(
                            onDelete = { deleteConfirm = f },
                            onOpen = {
                                val i = Intent(Intent.ACTION_VIEW).apply {
                                    setDataAndType(Uri.fromFile(File(f.path)), "video/*")
                                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                                }
                                try { context.startActivity(i) } catch (_: Exception) {
                                    Toast.makeText(context, "无可用播放器", Toast.LENGTH_SHORT).show()
                                }
                            },
                        ) {
                            Card(modifier = Modifier.fillMaxWidth().clickable { previewFile = f }) {
                                Column(modifier = Modifier.padding(12.dp)) {
                                    Text(f.name, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold,
                                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    val sz = when { f.size < 1048576 -> "${f.size / 1024}KB"; else -> "${"%.1f".format(f.size / 1048576.0)}MB" }
                                    val dt = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault()).format(Date(f.lastModified))
                                    Text("$sz · $dt", style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                                }
                            }
                        }
                    }
                }
            }
        }
    } else {
        Column(modifier = Modifier.fillMaxSize()) {
            Row(modifier = Modifier.padding(12.dp).fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically) {
                Text("录播文件", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text("${categories.size} 个主播", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
            }
            if (categories.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("暂无录播文件", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                        Text("录制完成后会自动出现在这里", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f))
                    }
                }
            }
            LazyVerticalGrid(columns = GridCells.Fixed(2), contentPadding = PaddingValues(8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(categories) { cat -> CategoryCard(cat, onClick = { selectedDir = cat }) }
            }
        }
    }

    // 预览
    if (previewFile != null) VideoPlayerDialog(filePath = previewFile!!.path, title = previewFile!!.name,
        onDismiss = { previewFile = null })

    // 删除确认
    if (deleteConfirm != null) {
        val f = deleteConfirm!!
        AlertDialog(
            onDismissRequest = { deleteConfirm = null },
            title = { Text("确认删除") },
            text = { Text("删除 ${f.name}?\n此操作不可恢复。") },
            confirmButton = {
                Button(onClick = {
                    File(f.path).delete()
                    deleteConfirm = null
                    selectedDir = null  // 强制刷新
                }, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) { Text("删除") }
            },
            dismissButton = { TextButton(onClick = { deleteConfirm = null }) { Text("取消") } },
        )
    }
}

@Composable
fun CategoryCard(cat: StreamerDir, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clickable { onClick() }, shape = RoundedCornerShape(12.dp)) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(16.dp)) {
            // 封面或头像占位
            Box(Modifier.size(64.dp).clip(RoundedCornerShape(12.dp))
                .background(MaterialTheme.colorScheme.primaryContainer),
                contentAlignment = Alignment.Center) {
                if (cat.coverUrl.isNotEmpty()) {
                    AsyncImage(model = "${cat.coverUrl}@100w_100h", contentDescription = null,
                        modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                } else {
                    Text(cat.name.take(2), fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(cat.name, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("${cat.fileCount} 个文件", style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
        }
    }
}

@Composable
fun GridFileCard(file: RecFile, onClick: () -> Unit) {
    val sz = when { file.size < 1048576 -> "${file.size / 1024}KB"; else -> "${"%.1f".format(file.size / 1048576.0)}MB" }
    val dt = SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()).format(Date(file.lastModified))
    Card(modifier = Modifier.fillMaxWidth().clickable { onClick() }, shape = RoundedCornerShape(8.dp)) {
        Column(modifier = Modifier.padding(8.dp)) {
            Box(Modifier.fillMaxWidth().height(90.dp).clip(RoundedCornerShape(6.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.PlayArrow, null, modifier = Modifier.size(32.dp),
                    tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f))
            }
            Spacer(Modifier.height(6.dp))
            Text(file.name, style = MaterialTheme.typography.labelSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text("$sz · $dt", style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
        }
    }
}

// 左滑显示删除按钮 (不自动删除)
@Composable
fun SwipeToReveal(
    onDelete: () -> Unit,
    onOpen: () -> Unit,
    content: @Composable () -> Unit,
) {
    var offsetX by remember { mutableFloatStateOf(0f) }
    val deleteWidth = 80.dp
    val deleteWidthPx = with(LocalDensity.current) { deleteWidth.toPx() }
    val bgColor by animateColorAsState(
        if (offsetX < -deleteWidthPx / 2) Color(0xFFFF5252) else Color.Transparent,
        label = "bg"
    )

    Box {
        // 背景：右侧删除按钮
        if (offsetX < -10f) {
            Row(modifier = Modifier.fillMaxSize().padding(end = 8.dp),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = { onDelete(); offsetX = 0f }) {
                    Icon(Icons.Filled.Delete, null, tint = Color.White)
                    Spacer(Modifier.width(4.dp))
                    Text("删除", color = Color.White)
                }
            }
        }

        Box(
            modifier = Modifier
                .offset { IntOffset(offsetX.roundToInt(), 0) }
                .background(bgColor, RoundedCornerShape(8.dp))
                .pointerInput(Unit) {
                    detectHorizontalDragGestures(
                        onDragEnd = {
                            if (offsetX < -deleteWidthPx * 0.6f) offsetX = -deleteWidthPx
                            else offsetX = 0f
                        },
                        onHorizontalDrag = { _, dragAmount ->
                            offsetX = (offsetX + dragAmount).coerceIn(-deleteWidthPx * 1.5f, 0f)
                        },
                    )
                }
        ) {
            content()
        }
    }
}

fun buildCategories(rootDir: String, roomMap: Map<String, MainViewModel.RoomItem>): List<StreamerDir> {
    val root = File(rootDir)
    if (!root.exists()) return emptyList()
    return root.listFiles()?.filter { it.isDirectory }?.mapNotNull { dir ->
        val files = scanFlvFiles(dir)
        if (files.isEmpty()) return@mapNotNull null
        val roomId = dir.name
        val room = roomMap[roomId]
        val name = room?.let { if (it.title.isNotEmpty()) it.title else roomId } ?: roomId
        val cover = room?.coverUrl ?: ""
        StreamerDir(name = name, path = dir.absolutePath, fileCount = files.size, files = files, coverUrl = cover)
    }?.sortedByDescending { it.files.maxOfOrNull { f -> f.lastModified } ?: 0L } ?: emptyList()
}

fun scanFlvFiles(dir: File): List<RecFile> {
    val result = mutableListOf<RecFile>()
    fun scan(f: File) {
        if (f.isDirectory) f.listFiles()?.forEach { scan(it) }
        else if (f.name.endsWith(".flv") || f.name.endsWith(".mp4") || f.name.endsWith(".ts"))
            result.add(RecFile(f.name, f.absolutePath, f.length(), f.lastModified()))
    }
    scan(dir)
    result.sortByDescending { it.lastModified }
    return result
}
