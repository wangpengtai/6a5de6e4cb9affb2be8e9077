# 电商打包监控 (PackingMonitor)

基于 PackingMonitor / PackingProof-Desktop 二次开发，面向 Windows 桌面的局域网摄像头监控 + 自动分段录像工具，纯本地运行，不上传任何数据。

## 功能特性

- 局域网 HTTP MJPEG 拉流（适配安卓手机 IP Webcam）
- 超低延迟：1 帧缓冲，画面延迟控制在局域网内最低水平
- 网络断开 3 秒内自动重连，全程无需手动重启
- 自动分段录像（默认 10 分钟/段），文件名 `yyyyMMdd_HHmmss.avi`
- 磁盘剩余空间低于阈值时自动删除最早录像
- 一键截图（时间戳命名，存到独立目录）
- 极简界面：仅 4 个按钮（录像 / 截图 / 设置 / 状态）
- F11 全屏，Esc 退出全屏
- 后台最小化持续拉流录像
- 预留本地 Ollama 多模态 AI 接口（默认关闭，不占资源）

## 运行环境

- Windows 10 / 11 x64
- 局域网 IP Webcam 或其他 HTTP MJPEG 摄像头

无需安装任何运行时、Python、FFmpeg。单文件 exe 直接双击运行。

## 快速开始

1. 启动安卓手机上的 "IP Webcam" App，确保手机和电脑在同一局域网
2. 双击 `PackingMonitor.exe` 运行
3. 点击 ⚙ 设置，把 "视频流 URL" 改为手机 IP Webcam 显示的地址（默认 `http://手机IP:8080/videofeed`）
4. 保存后画面自动开始显示
5. 点击 "● 开始录像" 即开始分段录像

## 配置文件

所有运行参数均在 `config.json` 中，**修改后重启程序生效**：

| 段 | 字段 | 含义 |
|---|---|---|
| camera | url | MJPEG 视频流地址 |
| camera | reconnectIntervalMs | 重连间隔（毫秒） |
| camera | networkTimeoutMs | 断线判定时长（毫秒） |
| record | autoStart | 启动后自动录像 |
| record | segmentSeconds | 单段录像时长（秒） |
| record | fps | 录像帧率（用于播放器呈现） |
| storage | recordDir | 录像保存目录（留空=exe同目录 record/） |
| storage | screenshotDir | 截图保存目录 |
| storage | minFreeSpaceMB | 磁盘剩余空间阈值 |
| ai | enabled | AI 总开关（默认 false） |
| ai | ollamaUrl | Ollama 服务地址 |
| ai | model | 多模态模型名 |
| ai | intervalSeconds | 画面分析间隔 |

## AI 模块（Ollama 预留）

AI 模块**默认完全关闭**，关闭时不加载任何 AI 代码、不占用 CPU/内存。

启用方法：
1. 本地安装并启动 Ollama：https://ollama.com
2. `ollama pull llama3.2-vision` 拉取多模态模型
3. 在设置中勾选 "启用 AI 多模态分析"
4. 确认 Ollama 地址（默认 `http://127.0.0.1:11434/api/generate`）和模型名
5. 保存后 AI 自动按设定间隔抓取画面分析，结果记录到 `logs/ai-*.log` 与状态栏

AI 运行异常**不会**影响监控、录像、画面显示。

## 从源码打包

需要 .NET 8 SDK。

```bat
build.bat
```

产物在 `bin\publish\PackingMonitor.exe`。

## 目录结构

```
PackingMonitor/
├── PackingMonitor.csproj       # .NET 8 WinForms 项目
├── Program.cs                  # 入口 + 单实例锁
├── config.json                 # 外置配置（运行参数）
├── build.bat                   # 一键打包脚本
├── Core/
│   ├── AppConfig.cs            # 配置类 + ConfigManager
│   └── LogUtil.cs              # 日志工具
├── Camera/
│   └── MjpegStreamer.cs        # MJPEG 拉流核心
├── Record/
│   ├── AviMjpegWriter.cs       # AVI MJPEG 录像写入器
│   └── RecordManager.cs        # 分段管理 + 磁盘清理
├── AI/
│   └── OllamaAnalyzer.cs       # Ollama 多模态调用（默认关闭）
└── UI/
    ├── MainForm.cs             # 主窗口
    └── SettingsForm.cs         # 设置窗口
```

## 快捷键

| 键 | 作用 |
|---|---|
| F11 | 切换全屏 |
| Esc | 退出全屏 |
| F12 | 截图 |

## 录像格式

`.avi` MJPEG 视频流（标准 AVI 1.0 容器 + Motion JPEG 编码）。可直接用 Windows Media Player、PotPlayer、VLC 等任意播放器打开。
