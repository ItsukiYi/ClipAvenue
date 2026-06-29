package com.biliup.android.ui.screen

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import java.io.File

@Composable
fun VideoPlayerDialog(
    filePath: String,
    title: String,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val file = remember { File(filePath) }
    val exoPlayer = remember {
        ExoPlayer.Builder(context).build().apply { playWhenReady = true }
    }

    DisposableEffect(Unit) {
        if (file.exists()) {
            val uri = Uri.fromFile(file)
            exoPlayer.setMediaItem(MediaItem.fromUri(uri))
            exoPlayer.prepare()
        }
        onDispose { exoPlayer.release() }
    }

    if (!file.exists()) {
        AlertDialog(
            onDismissRequest = onDismiss,
            title = { Text("文件不存在") },
            text = { Text("路径: $filePath\n大小: ${file.length()} bytes") },
            confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
        )
        return
    }

    Dialog(
        onDismissRequest = {
            exoPlayer.stop()
            onDismiss()
        },
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = Color.Black,
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                // 顶部栏
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .statusBarsPadding()
                        .padding(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    IconButton(onClick = {
                        exoPlayer.stop()
                        onDismiss()
                    }) {
                        Icon(Icons.Filled.ArrowBack, "返回", tint = Color.White)
                    }
                    Text(
                        text = title,
                        color = Color.White,
                        style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.weight(1f),
                    )
                }

                // 播放器
                AndroidView(
                    factory = { ctx ->
                        PlayerView(ctx).apply {
                            player = exoPlayer
                            useController = true
                            setKeepContentOnPlayerReset(true)
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .background(Color.Black),
                )
            }
        }
    }
}
