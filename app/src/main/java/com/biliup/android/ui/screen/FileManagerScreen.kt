package com.biliup.android.ui.screen

import android.content.Intent
import android.net.Uri
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

data class StrmDir(
    val name: String, val path: String, val fileCount: Int,
    val files: List<FlvFile>, val coverUrl: String = "",
)

data class FlvFile(
    val name: String, val path: String, val size: Long, val lastModified: Long,
)

@Composable
fun FileManagerScreen(
    viewModel: MainViewModel,
    scope: androidx.lifecycle.LifecycleCoroutineScope,
) {
    val downloadDir by viewModel.downloadDir.collectAsState()
    val rooms by viewModel.rooms.collectAsState()
    val ctx = LocalContext.current
    var selDir by remember { mutableStateOf<StrmDir?>(null) }
    var gridView by remember { mutableStateOf(false) }
    var preview by remember { mutableStateOf<FlvFile?>(null) }
    var delDialog by remember { mutableStateOf<FlvFile?>(null) }

    val roomMap = remember(rooms) { rooms.associateBy { it.roomId } }
    val cats = remember(downloadDir, rooms) { scanCats(File(downloadDir), roomMap) }

    // 强制刷新key
    var refresh by remember { mutableIntStateOf(0) }
    val key = "$downloadDir-$refresh"

    if (selDir != null) {
        val d = selDir!!
        Column(Modifier.fillMaxSize()) {
            Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { selDir = null }) { Icon(Icons.Filled.ArrowBack, "返回") }
                Text(d.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, maxLines = 1, modifier = Modifier.weight(1f))
                IconButton(onClick = { gridView = !gridView }) {
                    Icon(if (gridView) Icons.Filled.ViewList else Icons.Filled.GridView, null)
                }
            }

            if (gridView) {
                LazyVerticalGrid(columns = GridCells.Fixed(2), contentPadding = PaddingValues(8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(d.files, key = { it.path }) { f ->
                        Card(Modifier.fillMaxWidth().clickable { preview = f }, shape = RoundedCornerShape(8.dp)) {
                            Column(Modifier.padding(8.dp)) {
                                Box(Modifier.fillMaxWidth().height(90.dp).clip(RoundedCornerShape(6.dp))
                                    .background(MaterialTheme.colorScheme.surfaceVariant),
                                    contentAlignment = Alignment.Center) {
                                    Icon(Icons.Filled.Videocam, null, Modifier.size(32.dp),
                                        tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f))
                                }
                                Spacer(Modifier.height(6.dp))
                                Text(f.name, style = MaterialTheme.typography.labelSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                Text("${fmtSize(f.size)} · ${fmtDate(f.lastModified)}", style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
                            }
                        }
                    }
                }
            } else {
                LazyColumn(contentPadding = PaddingValues(8.dp), key = { key }) {
                    items(d.files, key = { it.path }) { f ->
                        Card(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
                            Row(Modifier.padding(12.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f).clickable { preview = f }) {
                                    Text(f.name, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, maxLines = 1)
                                    Text("${fmtSize(f.size)} · ${fmtDate(f.lastModified)}", style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                                }
                                IconButton(onClick = {
                                    val i = Intent(Intent.ACTION_VIEW).apply {
                                        setDataAndType(Uri.fromFile(File(f.path)), "video/*")
                                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                    }
                                    try { ctx.startActivity(i) } catch (_: Exception) { }
                                }) { Icon(Icons.Filled.OpenInNew, "系统打开", Modifier.size(20.dp)) }
                                IconButton(onClick = { delDialog = f }) {
                                    Icon(Icons.Filled.Delete, "删除", Modifier.size(20.dp), tint = MaterialTheme.colorScheme.error)
                                }
                            }
                        }
                    }
                }
            }
        }
    } else {
        // 一级：按主播分类
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            item {
                Row(Modifier.padding(12.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("录播文件", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text("${cats.size} 个主播", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                }
            }
            if (cats.isEmpty()) {
                item {
                    Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("暂无录播文件", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                            Text("录制完成后会自动出现", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f))
                        }
                    }
                }
            }
            items(cats) { cat ->
                Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp)
                    .clickable { selDir = cat }, shape = RoundedCornerShape(12.dp)) {
                    Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(48.dp).clip(RoundedCornerShape(10.dp))
                            .background(MaterialTheme.colorScheme.primaryContainer),
                            contentAlignment = Alignment.Center) {
                            if (cat.coverUrl.isNotEmpty())
                                AsyncImage("${cat.coverUrl}@100w_100h", null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                            else
                                Text(cat.name.take(2), fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(cat.name, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, maxLines = 1)
                            Text("${cat.fileCount} 个录播文件", style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                        }
                        Icon(Icons.Filled.ChevronRight, null, tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f))
                    }
                }
            }
        }
    }

    if (preview != null) VideoPlayerDialog(preview!!.path, preview!!.name, onDismiss = { preview = null })

    if (delDialog != null) {
        val f = delDialog!!
        AlertDialog(
            onDismissRequest = { delDialog = null },
            title = { Text("确认删除") },
            text = { Text("删除 ${f.name}？不可恢复。") },
            confirmButton = { Button(onClick = {
                File(f.path).delete(); delDialog = null; selDir = null; refresh++
            }, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) { Text("删除") } },
            dismissButton = { TextButton(onClick = { delDialog = null }) { Text("取消") } },
        )
    }
}

fun scanCats(root: File, roomMap: Map<String, MainViewModel.RoomItem>): List<StrmDir> {
    if (!root.exists()) return emptyList()
    return root.listFiles()?.filter { it.isDirectory }?.mapNotNull { dir ->
        val files = mutableListOf<FlvFile>()
        fun scan(f: File) {
            if (f.isDirectory) f.listFiles()?.forEach { scan(it) }
            else if (f.name.endsWith(".flv") || f.name.endsWith(".mp4") || f.name.endsWith(".ts"))
                files.add(FlvFile(f.name, f.absolutePath, f.length(), f.lastModified()))
        }
        scan(dir)
        if (files.isEmpty()) return@mapNotNull null
        files.sortByDescending { it.lastModified }
        val rid = dir.name
        val room = roomMap[rid]
        val name = room?.let { if (it.title.isNotEmpty()) it.title else rid } ?: rid
        val cover = room?.coverUrl ?: ""
        StrmDir(name = name, path = dir.absolutePath, fileCount = files.size, files = files, coverUrl = cover)
    }?.sortedByDescending { it.files.maxOfOrNull { f -> f.lastModified } ?: 0L } ?: emptyList()
}

fun fmtSize(s: Long) = when { s < 1048576 -> "${s / 1024}KB"; else -> "${"%.1f".format(s / 1048576.0)}MB" }
fun fmtDate(ts: Long) = SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()).format(Date(ts))
