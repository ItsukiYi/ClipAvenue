package com.biliup.android

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import com.biliup.android.bridge.PythonBridge
import com.biliup.android.ui.screen.*
import com.biliup.android.ui.theme.BiliupTheme
import com.biliup.android.viewmodel.MainViewModel
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var viewModel: MainViewModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        viewModel = MainViewModel()
        viewModel.init(this)

        // 显示 Python 初始化状态
        val error = BiliupApp.initError
        if (error != null) {
            Toast.makeText(this, "Python 初始化失败: $error", Toast.LENGTH_LONG).show()
            viewModel.addLog("初始化失败: $error")
        } else {
            viewModel.addLog("Python 引擎已就绪")
        }

        setContent {
            BiliupTheme {
                BiliupMainScreen(viewModel = viewModel, lifecycleScope = lifecycleScope)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        PythonBridge.cleanup()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BiliupMainScreen(
    viewModel: MainViewModel,
    lifecycleScope: androidx.lifecycle.LifecycleCoroutineScope,
) {
    var selectedTab by remember { mutableIntStateOf(0) }

    Scaffold(
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    icon = { if (selectedTab == 0) Icon(Icons.Filled.Dashboard, null) else Icon(Icons.Outlined.Dashboard, null) },
                    label = { Text("仪表盘") },
                    selected = selectedTab == 0,
                    onClick = { selectedTab = 0 },
                )
                NavigationBarItem(
                    icon = { if (selectedTab == 1) Icon(Icons.Filled.Videocam, null) else Icon(Icons.Outlined.Videocam, null) },
                    label = { Text("直播间") },
                    selected = selectedTab == 1,
                    onClick = { selectedTab = 1 },
                )
                NavigationBarItem(
                    icon = { if (selectedTab == 2) Icon(Icons.Filled.VideoLibrary, null) else Icon(Icons.Outlined.VideoLibrary, null) },
                    label = { Text("文件") },
                    selected = selectedTab == 2,
                    onClick = { selectedTab = 2 },
                )
                NavigationBarItem(
                    icon = { if (selectedTab == 3) Icon(Icons.Filled.Settings, null) else Icon(Icons.Outlined.Settings, null) },
                    label = { Text("设置") },
                    selected = selectedTab == 3,
                    onClick = { selectedTab = 3 },
                )
            }
        }
    ) { paddingValues ->
        Box(modifier = Modifier.padding(paddingValues)) {
            when (selectedTab) {
                0 -> DashboardScreen(viewModel, lifecycleScope)
                1 -> RoomListScreen(viewModel, lifecycleScope)
                2 -> FileManagerScreen(viewModel, lifecycleScope)
                3 -> SettingsScreen(viewModel)
            }
        }
    }
}
