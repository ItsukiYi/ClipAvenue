package com.biliup.android.ui.screen

import android.widget.Toast
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.layout.ContentScale
import coil.compose.AsyncImage
import com.biliup.android.viewmodel.MainViewModel
import kotlinx.coroutines.launch

@Composable
fun RoomListScreen(
    viewModel: MainViewModel,
    scope: androidx.lifecycle.LifecycleCoroutineScope,
) {
    val rooms by viewModel.rooms.collectAsState()
    var showAddDialog by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxSize()) {
        if (rooms.isEmpty()) {
            Column(
                modifier = Modifier.fillMaxSize().padding(32.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Text("📺", style = MaterialTheme.typography.displaySmall,
                    modifier = Modifier.padding(bottom = 12.dp))
                Text("还没有添加直播间", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                Text("点击右下角 + 添加", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f))
                Spacer(Modifier.height(16.dp))
                Button(onClick = { showAddDialog = true }) {
                    Icon(Icons.Filled.Add, null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("添加直播间")
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(rooms) { room -> RoomCard(room, viewModel, scope) }
                item { Spacer(Modifier.height(80.dp)) }
            }

            FloatingActionButton(
                onClick = { showAddDialog = true },
                modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
                containerColor = MaterialTheme.colorScheme.primary,
            ) { Icon(Icons.Filled.Add, "添加") }
        }
    }

    if (showAddDialog) AddRoomDialog(
        onDismiss = { showAddDialog = false },
        onAdd = { url, platform -> showAddDialog = false; scope.launch { viewModel.addRoom(url, platform) } },
    )
}

@Composable
fun RoomCard(
    room: MainViewModel.RoomItem,
    viewModel: MainViewModel,
    scope: androidx.lifecycle.LifecycleCoroutineScope,
) {
    val context = LocalContext.current
    var showEditDialog by remember { mutableStateOf(false) }
    val isThisRoomRecording = viewModel.activeRecordings.collectAsState().value
        .any { it.roomId == room.roomId && it.isRunning }

    // 脉冲动画
    val pulseAlpha by rememberInfiniteTransition(label = "pulse").animateFloat(
        initialValue = 0.4f, targetValue = 0f,
        animationSpec = infiniteRepeatable(tween(1000), RepeatMode.Restart)
    )

    Card(modifier = Modifier.fillMaxWidth()) {
        Box(modifier = Modifier.fillMaxWidth()) {
            // 封面背景
            if (room.coverUrl.isNotEmpty()) {
                AsyncImage(
                    model = "${room.coverUrl}@400w_250h",
                    contentDescription = null,
                    modifier = Modifier.fillMaxWidth().height(120.dp),
                    contentScale = ContentScale.Crop,
                )
                Box(modifier = Modifier.fillMaxWidth().height(120.dp)
                    .background(Color.Black.copy(alpha = 0.45f)))
            }
            Column(modifier = Modifier.padding(12.dp)) {
            // ── 第一行: 头像 + 信息 ──
            Row(verticalAlignment = Alignment.CenterVertically) {
                // 头像 (带开播脉冲环)
                Box(modifier = Modifier.size(44.dp)) {
                    // 头像 — 优先封面URL, 回落首字母
                    val avatarUrl = room.coverUrl.ifEmpty { room.faceUrl }
                    if (avatarUrl.isNotEmpty()) {
                        AsyncImage(
                            model = "$avatarUrl@100w_100h",
                            contentDescription = "头像",
                            modifier = Modifier.fillMaxSize().clip(CircleShape),
                            contentScale = ContentScale.Crop,
                        )
                    } else {
                        Box(
                            modifier = Modifier.fillMaxSize().clip(CircleShape)
                                .background(MaterialTheme.colorScheme.primaryContainer),
                            contentAlignment = Alignment.Center,
                        ) { Text(room.uname.take(1).ifEmpty { room.roomId.take(1) },
                            color = MaterialTheme.colorScheme.primary) }
                    }
                    if (room.isLive) {
                        Box(
                            modifier = Modifier.fillMaxSize()
                                .clip(CircleShape)
                                .border(2.dp, Color.Red.copy(alpha = 1f), CircleShape)
                        )
                        Box(
                            modifier = Modifier.fillMaxSize()
                                .clip(CircleShape)
                                .border(3.dp, Color.Red.copy(alpha = pulseAlpha), CircleShape)
                        )
                    }
                }

                Spacer(Modifier.width(10.dp))

                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        room.title.ifEmpty { "房间 ${room.roomId}" },
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        "${room.platform} · ${room.uname.ifEmpty { room.roomId }}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                    )
                    Text(
                        "https://live.bilibili.com/${room.roomId}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary.copy(alpha = 0.5f),
                        maxLines = 1, overflow = TextOverflow.Ellipsis,
                    )
                }

                // 直播状态指示
                if (room.isLive) {
                    Surface(shape = RoundedCornerShape(4.dp),
                        color = Color.Red.copy(alpha = 0.15f)) {
                        Text(" LIVE ", modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = Color.Red, fontWeight = FontWeight.Bold)
                    }
                }
            }

            Spacer(Modifier.height(10.dp))

            // ── 第二行: 控制按钮 ──
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // 检测
                SmallButton("检测", onClick = { scope.launch { viewModel.checkRoom(room) } })
                // 自动录
                SmallChip("自动录", room.autoRecord,
                    onClick = { viewModel.setRoomAutoRecord(room, !room.autoRecord) })
                // 轮询
                SmallChip("轮询", room.isMonitored,
                    onClick = { viewModel.setRoomMonitored(room, !room.isMonitored) })

                Spacer(Modifier.weight(1f))
                // 编辑
                SmallButton("编辑", onClick = { showEditDialog = true })
            }

            Spacer(Modifier.height(8.dp))

            // ── 第三行: 录制/终止按钮 ──
            Button(
                onClick = {
                    if (isThisRoomRecording) {
                        val task = viewModel.activeRecordings.value.find {
                            it.roomId == room.roomId && it.isRunning
                        }
                        if (task != null) scope.launch { viewModel.stopRecording(task) }
                    } else {
                        if (room.isLive) scope.launch { viewModel.startRecording(room) }
                        else Toast.makeText(context, "主播未开播", Toast.LENGTH_SHORT).show()
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isThisRoomRecording)
                        MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.primary
                ),
            ) {
                Icon(
                    if (isThisRoomRecording) Icons.Filled.Stop else Icons.Filled.FiberManualRecord,
                    null, modifier = Modifier.size(16.dp)
                )
                Spacer(Modifier.width(6.dp))
                Text(if (isThisRoomRecording) "终止录制" else "开始录制")
            }

            // 状态文字
            if (room.isChecking) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(modifier = Modifier.size(12.dp), strokeWidth = 1.dp)
                    Spacer(Modifier.width(6.dp))
                    Text("检测中...", style = MaterialTheme.typography.labelSmall)
                }
            }
        }
        } // Box
    }

    // 编辑对话框
    if (showEditDialog) EditRoomDialog(
        room = room, viewModel = viewModel,
        onDismiss = { showEditDialog = false },
    )
}

@Composable
fun SmallButton(text: String, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = Modifier.height(30.dp),
        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)) {
        Text(text, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
fun SmallChip(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(
        selected = selected, onClick = onClick,
        modifier = Modifier.height(28.dp),
        label = { Text(label, style = MaterialTheme.typography.labelSmall) },
    )
}

@Composable
fun EditRoomDialog(
    room: MainViewModel.RoomItem,
    viewModel: MainViewModel,
    onDismiss: () -> Unit,
) {
    var title by remember { mutableStateOf(room.title) }
    var url by remember { mutableStateOf(room.roomId) }
    var showDeleteConfirm by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("编辑直播间") },
        text = {
            Column {
                OutlinedTextField(value = title, onValueChange = { title = it },
                    label = { Text("主播备注") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = url, onValueChange = { url = it },
                    label = { Text("直播间 ID/链接") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(12.dp))
                // 画质选择
                Text("画质", style = MaterialTheme.typography.labelMedium)
                Spacer(Modifier.height(4.dp))
                listOf(10000 to "原画", 400 to "蓝光", 250 to "超清", 150 to "高清", 80 to "流畅")
                    .forEach { (qn, name) ->
                        Row(Modifier.fillMaxWidth().padding(2.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = room.qn == qn,
                                onClick = { viewModel.setRoomQn(room, qn) })
                            // Actually just close and use a callback
                            Spacer(Modifier.width(6.dp)); Text(name)
                        }
                    }
                Spacer(Modifier.height(12.dp))
                OutlinedButton(
                    onClick = { showDeleteConfirm = true },
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    modifier = Modifier.fillMaxWidth(),
                ) { Icon(Icons.Filled.Delete, null, modifier = Modifier.size(16.dp)); Spacer(Modifier.width(4.dp)); Text("删除直播间") }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
        dismissButton = null,
    )

    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text("确认删除") },
            text = { Text("删除后录播文件和配置将保留，但不再监测此直播间。") },
            confirmButton = { Button(onClick = { viewModel.deleteRoom(room); onDismiss(); showDeleteConfirm = false },
                colors = ButtonDefaults.buttonColors(
                containerColor = MaterialTheme.colorScheme.error)) { Text("删除") } },
            dismissButton = { TextButton(onClick = { showDeleteConfirm = false }) { Text("取消") } },
        )
    }
}

fun buildFaceUrl(room: MainViewModel.RoomItem): String {
    // 暂时用占位头像 — TODO: 从 API 获取真实头像
    return ""
}

@Composable
fun AddRoomDialog(
    onDismiss: () -> Unit,
    onAdd: (url: String, platform: String) -> Unit,
) {
    var url by remember { mutableStateOf("") }
    var platform by remember { mutableStateOf("bilibili") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("添加直播间") },
        text = {
            Column {
                OutlinedTextField(value = url, onValueChange = { url = it },
                    label = { Text("直播间链接或房间号") },
                    placeholder = { Text("https://live.bilibili.com/12345") },
                    singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("bilibili" to "B站", "douyin" to "抖音").forEach { (k, l) ->
                        FilterChip(selected = platform == k, onClick = { platform = k }, label = { Text(l) })
                    }
                }
            }
        },
        confirmButton = { Button(onClick = { onAdd(url, platform) }, enabled = url.isNotBlank()) { Text("添加") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}
