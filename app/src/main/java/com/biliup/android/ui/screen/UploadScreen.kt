package com.biliup.android.ui.screen

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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.biliup.android.viewmodel.MainViewModel
import kotlinx.coroutines.launch

@Composable
fun UploadScreen(
    viewModel: MainViewModel,
    scope: androidx.lifecycle.LifecycleCoroutineScope,
) {
    val uploads by viewModel.uploads.collectAsState()
    val recordings by viewModel.activeRecordings.collectAsState()

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item {
            Text("上传管理", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        }

        val pending = recordings.filter { !it.isRunning }
        if (pending.isNotEmpty()) {
            item {
                Text("待上传", style = MaterialTheme.typography.titleSmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f))
            }
            items(pending) { task ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Row(modifier = Modifier.padding(16.dp).fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.VideoFile, null, tint = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(task.title, style = MaterialTheme.typography.titleSmall)
                            Text("${task.platform} | ${task.roomId}", style = MaterialTheme.typography.bodySmall)
                            Text(task.duration, style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                        }
                        FilledTonalButton(onClick = {
                            scope.launch { viewModel.uploadVideo(task) }
                        }) {
                            Icon(Icons.Filled.CloudUpload, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("上传")
                        }
                    }
                }
            }
        }

        if (uploads.isNotEmpty()) {
            item {
                Text("上传历史", style = MaterialTheme.typography.titleSmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f))
            }
            items(uploads) { upload ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(upload.title, style = MaterialTheme.typography.titleSmall)
                                Text(upload.statusText, style = MaterialTheme.typography.bodySmall,
                                    color = when (upload.status) {
                                        "done" -> MaterialTheme.colorScheme.primary
                                        "failed" -> MaterialTheme.colorScheme.error
                                        else -> MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                                    })
                            }
                        }
                        if (upload.status == "uploading") {
                            Spacer(Modifier.height(8.dp))
                            LinearProgressIndicator(
                                progress = { upload.progress },
                                modifier = Modifier.fillMaxWidth(),
                            )
                            Spacer(Modifier.height(4.dp))
                            Text("${(upload.progress * 100).toInt()}%", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
        }

        if (pending.isEmpty() && uploads.isEmpty()) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                ) {
                    Column(modifier = Modifier.padding(24.dp).fillMaxWidth(),
                        horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Outlined.CloudUpload, null, modifier = Modifier.size(48.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(8.dp))
                        Text("暂无待上传视频", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("录制完成后会出现在这里", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f))
                    }
                }
            }
        }
    }
}
