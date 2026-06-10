package com.biliup.android.ui.screen

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.asImageBitmap
import com.biliup.android.bridge.PythonBridge
import com.biliup.android.viewmodel.MainViewModel
import kotlinx.coroutines.launch
import java.io.File

@Composable
fun SettingsScreen(viewModel: MainViewModel) {
    val scrollState = rememberScrollState()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    // 从 ViewModel 获取实时路径，每次重组都会更新
    val downloadDir by viewModel.downloadDir.collectAsState()

    var isLoggedIn by remember { mutableStateOf(PythonBridge.isLoggedIn()) }
    var uname by remember { mutableStateOf(if (isLoggedIn) {
        try { org.json.JSONObject(PythonBridge.getUserInfo()).optString("uname", "") } catch (_: Exception) { "" }
    } else "") }
    var showQrDialog by remember { mutableStateOf(false) }
    var editDir by remember { mutableStateOf(false) }
    var editDirText by remember { mutableStateOf("") }
    var pickerMsg by remember { mutableStateOf("") }

    // SAF 目录选择器
    val dirPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { uri: Uri? ->
        if (uri != null) {
            // 获取持久化权限
            val flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            try {
                context.contentResolver.takePersistableUriPermission(uri, flags)
            } catch (_: Exception) {}

            // 尝试提取实际路径
            val path = try {
                val docId = android.provider.DocumentsContract.getTreeDocumentId(uri)
                val split = docId.split(":")
                if (split.size >= 2 && split[0] == "primary")
                    "/storage/emulated/0/${split[1]}"
                else if (split.size >= 2)
                    "/storage/${split[0]}/${split[1]}"
                else null
            } catch (_: Exception) { null }

            val finalPath = path ?: uri.toString()
            scope.launch {
                try {
                    PythonBridge.setDownloadDir(finalPath)
                    PythonBridge.dbSetSetting("download_dir", finalPath)
                    PythonBridge.saveWorkDir(context, finalPath)
                    viewModel.updateDownloadDir(finalPath)
                    pickerMsg = "已切换到: $finalPath"
                    Toast.makeText(context, "已切换到: $finalPath", Toast.LENGTH_SHORT).show()
                } catch (e: Exception) {
                    pickerMsg = "切换失败: ${e.message}"
                }
            }
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // ─── B站账号 ────────────────────────────────
        Text("B站账号", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                if (isLoggedIn) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.CheckCircle, null, tint = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Text("已登录: $uname", style = MaterialTheme.typography.titleSmall)
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = {
                        scope.launch { PythonBridge.setCookies("") }
                        PythonBridge.dbSetSetting("bilibili_cookies", "")
                        isLoggedIn = false; uname = ""
                    }) { Text("退出登录") }
                } else {
                    Text("未登录", style = MaterialTheme.typography.titleSmall)
                    Text("扫码登录以使用自动上传功能", style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = { showQrDialog = true }) {
                        Icon(Icons.Filled.QrCode, null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("扫码登录")
                    }
                }
            }
        }

        // ─── 录制设置 ────────────────────────────────
        Text("录制设置", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                // 存储路径
                Text("存储路径", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(4.dp))
                Text(downloadDir, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                Spacer(Modifier.height(8.dp))

                // 三个按钮
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    // 打开目录
                    OutlinedButton(onClick = {
                        var ok = false
                        // 方案1: DocumentsUI (正确路径 primary:Movies/biliup)
                        try {
                            val uri = android.provider.DocumentsContract.buildDocumentUri(
                                "com.android.externalstorage.documents",
                                "primary:Android/data/com.biliup.android/files/biliup"
                            )
                            context.startActivity(Intent(Intent.ACTION_VIEW).apply {
                                setDataAndType(uri, "vnd.android.document/root")
                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                            })
                            ok = true
                        } catch (_: Exception) {}

                        // 方案2: 复制路径
                        if (!ok) {
                            (context.getSystemService(android.content.Context.CLIPBOARD_SERVICE)
                                as android.content.ClipboardManager)
                                .setPrimaryClip(android.content.ClipData.newPlainText("", downloadDir))
                            Toast.makeText(context, "路径已复制:\n$downloadDir", Toast.LENGTH_LONG).show()
                        }
                    }) {
                        Icon(Icons.Filled.FolderOpen, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("打开目录", style = MaterialTheme.typography.labelSmall)
                    }

                    // 选择文件夹
                    OutlinedButton(onClick = {
                        try { dirPicker.launch(null) } catch (_: Exception) {}
                    }) {
                        Icon(Icons.Filled.DriveFolderUpload, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("选择文件夹", style = MaterialTheme.typography.labelSmall)
                    }

                    // 手动输入
                    OutlinedButton(onClick = {
                        editDirText = downloadDir
                        editDir = true
                    }) {
                        Icon(Icons.Filled.Edit, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("手动输入", style = MaterialTheme.typography.labelSmall)
                    }
                }

                if (pickerMsg.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    Text(pickerMsg, style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary)
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                // 轮询间隔
                var pollSec by remember { mutableIntStateOf(60) }
                Row(modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("轮询间隔 (秒)", style = MaterialTheme.typography.bodyMedium)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { pollSec = maxOf(30, pollSec - 10); viewModel.setPollInterval(pollSec) }) {
                            Text("-10")
                        }
                        Text("${pollSec}s", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.primary)
                        TextButton(onClick = { pollSec = minOf(300, pollSec + 10); viewModel.setPollInterval(pollSec) }) {
                            Text("+10")
                        }
                    }
                }
                Text("设太长响应慢，设太短可能被B站风控 (推荐60s)", style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))

                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                SettingRow("分段时长 (分钟)", "60")
                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                var autoUpload by remember { mutableStateOf(true) }
                Row(modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("录制完自动上传")
                    Switch(checked = autoUpload, onCheckedChange = { autoUpload = it })
                }
            }
        }

        // ─── 关于 ────────────────────────────────────
        Text("关于", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                SettingRow("版本", "1.0.0")
                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                SettingRow("Python 引擎", "3.8 (Chaquopy)")
                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                SettingRow("录播存储", downloadDir)
            }
        }
        Spacer(Modifier.height(16.dp))
    }

    // 手动输入路径
    if (editDir) {
        AlertDialog(
            onDismissRequest = { editDir = false },
            title = { Text("修改存储路径") },
            text = {
                Column {
                    Text("输入新路径后点确定，App 会自动测试并切换",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = editDirText,
                        onValueChange = { editDirText = it },
                        label = { Text("路径") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                Button(onClick = {
                    val newPath = editDirText.trim()
                    if (newPath.isNotEmpty()) {
                        scope.launch {
                            try {
                                PythonBridge.setDownloadDir(newPath)
                                PythonBridge.dbSetSetting("download_dir", newPath)
                                PythonBridge.saveWorkDir(context, newPath)
                                viewModel.updateDownloadDir(newPath)
                                Toast.makeText(context, "已切换", Toast.LENGTH_SHORT).show()
                            } catch (e: Exception) {
                                Toast.makeText(context, "切换失败: ${e.message}", Toast.LENGTH_SHORT).show()
                            }
                        }
                    }
                    editDir = false
                }) { Text("确定") }
            },
            dismissButton = { TextButton(onClick = { editDir = false }) { Text("取消") } },
        )
    }

    // 扫码登录
    if (showQrDialog) {
        QrLoginDialog(
            onDismiss = { showQrDialog = false },
            onLoginSuccess = { uid, name ->
                isLoggedIn = true; uname = name
                showQrDialog = false
            },
        )
    }
}

@Composable
fun QrLoginDialog(
    onDismiss: () -> Unit,
    onLoginSuccess: (uid: Int, uname: String) -> Unit,
) {
    var qrUrl by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("正在生成二维码...") }
    var polling by remember { mutableStateOf(false) }
    var qrBitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }

    // 生成二维码
    LaunchedEffect(Unit) {
        try {
            val result = PythonBridge.loginQrGenerate()
            val json = org.json.JSONObject(result)
            if (json.optBoolean("success")) {
                qrUrl = json.optString("url", "")
                status = "请用B站 App 扫描二维码"
                polling = true
                // ZXing 本地生成 QR 码
                qrBitmap = generateQrCode(qrUrl, 200)
            } else {
                status = "生成失败: ${json.optString("message")}"
            }
        } catch (e: Exception) {
            status = "错误: ${e.message}"
        }
    }

    // 轮询扫码
    LaunchedEffect(polling) {
        if (!polling) return@LaunchedEffect
        var attempts = 0
        while (polling && attempts < 90) {
            kotlinx.coroutines.delay(2000)
            attempts++
            try {
                val result = PythonBridge.loginQrPoll()
                val json = org.json.JSONObject(result)
                when (json.optString("status")) {
                    "success" -> {
                        status = "登录成功！"
                        polling = false
                        onLoginSuccess(json.optInt("uid"), json.optString("uname"))
                        return@LaunchedEffect
                    }
                    "scanned" -> status = "已扫码，请在手机上确认"
                    "expired" -> { status = "二维码已过期，请重新生成"; polling = false }
                    "waiting" -> status = "请用B站 App 扫描二维码"
                    else -> status = json.optString("message", "未知状态")
                }
            } catch (_: Exception) {}
        }
    }

    AlertDialog(
        onDismissRequest = { polling = false; onDismiss() },
        title = { Text("B站扫码登录") },
        text = {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                val bmp = qrBitmap
                if (bmp != null) {
                    androidx.compose.foundation.Image(
                        bitmap = bmp.asImageBitmap(),
                        contentDescription = "二维码",
                        modifier = Modifier.size(200.dp),
                    )
                } else {
                    CircularProgressIndicator()
                }
                Spacer(Modifier.height(12.dp))
                Text(status, style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = { TextButton(onClick = { polling = false; onDismiss() }) { Text("关闭") } },
    )
}

fun generateQrCode(text: String, size: Int): android.graphics.Bitmap? {
    return try {
        val hints = hashMapOf<com.google.zxing.EncodeHintType, Any>(
            com.google.zxing.EncodeHintType.MARGIN to 1
        )
        val matrix = com.google.zxing.qrcode.QRCodeWriter().encode(
            text, com.google.zxing.BarcodeFormat.QR_CODE, size, size, hints
        )
        val bmp = android.graphics.Bitmap.createBitmap(size, size, android.graphics.Bitmap.Config.RGB_565)
        for (x in 0 until size) {
            for (y in 0 until size) {
                bmp.setPixel(x, y, if (matrix[x, y]) android.graphics.Color.BLACK else android.graphics.Color.WHITE)
            }
        }
        bmp
    } catch (_: Exception) { null }
}

@Composable
fun SettingRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Text(value, style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
    }
}
