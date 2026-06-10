package com.biliup.android.ui.screen

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
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
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item {
                Row(modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("直播间管理", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    FilledTonalButton(onClick = { showAddDialog = true }) {
                        Icon(Icons.Filled.Add, null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("添加")
                    }
                }
            }

            if (rooms.isEmpty()) {
                item {
                    Card(modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                        Column(modifier = Modifier.padding(24.dp).fillMaxWidth(),
                            horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("还没有添加直播间", color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text("点击「添加」输入 B站直播间链接", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f))
                        }
                    }
                }
            }

            items(rooms) { room ->
                RoomCard(room, viewModel, scope)
            }
        }

        FloatingActionButton(
            onClick = { showAddDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
            containerColor = MaterialTheme.colorScheme.primary,
        ) {
            Icon(Icons.Filled.Add, contentDescription = "添加直播间")
        }
    }

    if (showAddDialog) {
        AddRoomDialog(
            onDismiss = { showAddDialog = false },
            onAdd = { url, platform ->
                showAddDialog = false
                scope.launch { viewModel.addRoom(url, platform) }
            },
        )
    }
}

@Composable
fun RoomCard(
    room: MainViewModel.RoomItem,
    viewModel: MainViewModel,
    scope: androidx.lifecycle.LifecycleCoroutineScope,
) {
    var expanded by remember { mutableStateOf(false) }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            // 主行：状态 + 操作
            Row(modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically) {
                // 直播状态指示灯
                Icon(
                    imageVector = Icons.Filled.Circle,
                    contentDescription = null,
                    modifier = Modifier.size(10.dp),
                    tint = when {
                        room.isLive -> androidx.compose.ui.graphics.Color(0xFFEF5350)
                        room.isChecking -> androidx.compose.ui.graphics.Color(0xFFFFC107)
                        else -> androidx.compose.ui.graphics.Color(0xFF9E9E9E)
                    },
                )
                Spacer(Modifier.width(8.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            room.title.ifEmpty { "房间 ${room.roomId}" },
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.weight(1f),
                        )
                        // 自动录制标记
                        if (room.autoRecord) {
                            Text("AUTO", style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary)
                        }
                    }
                    Text("${room.platform} | ${room.uname.ifEmpty { room.roomId }}",
                        style = MaterialTheme.typography.bodySmall)
                }

                // 录制按钮
                if (room.isLive) {
                    Button(onClick = { scope.launch { viewModel.startRecording(room) } }) {
                        Icon(Icons.Filled.FiberManualRecord, null, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("录制")
                    }
                }
            }

            // 展开/收起控制面板
            TextButton(onClick = { expanded = !expanded },
                modifier = Modifier.padding(top = 4.dp)) {
                Text(
                    if (expanded) "收起 ▲" else "更多 ▼",
                    style = MaterialTheme.typography.labelSmall,
                )
            }

            if (expanded) {
                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    // 检测按钮
                    OutlinedButton(
                        onClick = { scope.launch { viewModel.checkRoom(room) } },
                        modifier = Modifier.weight(1f),
                    ) {
                        Icon(Icons.Filled.Refresh, null, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(2.dp))
                        Text("检测", style = MaterialTheme.typography.labelSmall)
                    }

                    // 自动录制开关
                    FilterChip(
                        selected = room.autoRecord,
                        onClick = { viewModel.setRoomAutoRecord(room, !room.autoRecord) },
                        label = { Text("自动录", style = MaterialTheme.typography.labelSmall) },
                        leadingIcon = if (room.autoRecord)
                            { { Icon(Icons.Filled.Check, null, modifier = Modifier.size(14.dp)) } }
                        else null,
                    )

                    // 轮询开关
                    FilterChip(
                        selected = room.isMonitored,
                        onClick = { viewModel.setRoomMonitored(room, !room.isMonitored) },
                        label = { Text("轮询", style = MaterialTheme.typography.labelSmall) },
                        leadingIcon = if (room.isMonitored)
                            { { Icon(Icons.Filled.Wifi, null, modifier = Modifier.size(14.dp)) } }
                        else null,
                    )
                }

                // 画质选择
                Spacer(Modifier.height(8.dp))
                var qnExpanded by remember { mutableStateOf(false) }
                val qnLabel = when (room.qn) {
                    10000 -> "原画"
                    400 -> "蓝光"
                    250 -> "超清"
                    150 -> "高清"
                    80 -> "流畅"
                    else -> "${room.qn}"
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("画质: ", style = MaterialTheme.typography.labelSmall)
                    TextButton(onClick = { qnExpanded = true }) {
                        Text(qnLabel, style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary)
                    }
                }
                if (qnExpanded) {
                    AlertDialog(
                        onDismissRequest = { qnExpanded = false },
                        title = { Text("选择画质") },
                        text = {
                            Column {
                                listOf(10000 to "原画", 400 to "蓝光", 250 to "超清",
                                       150 to "高清", 80 to "流畅").forEach { (qn, name) ->
                                    Row(Modifier.fillMaxWidth().padding(4.dp),
                                        verticalAlignment = Alignment.CenterVertically) {
                                        RadioButton(selected = room.qn == qn,
                                            onClick = { viewModel.setRoomQn(room, qn); qnExpanded = false })
                                        Spacer(Modifier.width(8.dp))
                                        Text(name)
                                    }
                                }
                            }
                        },
                        confirmButton = { TextButton(onClick = { qnExpanded = false }) { Text("关闭") } },
                    )
                }

                // 状态信息
                if (room.isLive) {
                    Spacer(Modifier.height(4.dp))
                    Text("🔴 直播中", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error)
                } else if (room.isChecking) {
                    Spacer(Modifier.height(4.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(modifier = Modifier.size(12.dp), strokeWidth = 1.dp)
                        Spacer(Modifier.width(4.dp))
                        Text("检测中...", style = MaterialTheme.typography.labelSmall)
                    }
                } else {
                    Spacer(Modifier.height(4.dp))
                    Text("未开播", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
                }
            }
        }
    }
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
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    label = { Text("直播间链接或房间号") },
                    placeholder = { Text("https://live.bilibili.com/12345") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("bilibili" to "B站", "douyin" to "抖音").forEach { (key, label) ->
                        FilterChip(
                            selected = platform == key,
                            onClick = { platform = key },
                            label = { Text(label) },
                        )
                    }
                }
            }
        },
        confirmButton = {
            Button(onClick = { onAdd(url, platform) }, enabled = url.isNotBlank()) { Text("添加") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}
