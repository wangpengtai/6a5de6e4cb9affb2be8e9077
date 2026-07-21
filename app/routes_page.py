# -*- coding: utf-8 -*-
"""页面路由模块 - HTML 页面端点"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    """主页面 - 监控界面"""
    return _render_main_page()


@router.get("/settings", response_class=HTMLResponse)
async def settings():
    """设置页面"""
    return _render_settings_page()


@router.get("/play/{filepath:path}", response_class=HTMLResponse)
async def play(filepath: str):
    """在线播放页面"""
    return _render_play_page(filepath)


def _render_main_page() -> str:
    """渲染主页面 HTML"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>电商打包监控系统</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; background: #1a1a2e; color: #e0e0e0; overflow: hidden; height: 100vh; }

        /* 顶部导航栏 */
        .topbar { background: #0f3460; height: 52px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; border-bottom: 1px solid #1a3a6a; flex-shrink: 0; }
        .topbar-title { font-size: 18px; font-weight: 600; color: #fff; letter-spacing: 1px; }
        .topbar-title span { color: #e94560; margin-right: 8px; }
        .topbar-right { display: flex; align-items: center; gap: 16px; }
        .topbar-time { color: #8899bb; font-size: 13px; }
        .btn-settings { background: none; border: 1px solid #3a5078; color: #aabbcc; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; transition: all .2s; }
        .btn-settings:hover { background: #1a3a6a; color: #fff; border-color: #5577aa; }

        /* 主布局 */
        .main-layout { display: flex; height: calc(100vh - 52px); }

        /* 左侧区域 70% */
        .left-panel { width: 70%; display: flex; flex-direction: column; padding: 12px; gap: 10px; }

        /* 视频区域 */
        .video-wrapper { flex: 1; background: #000; border-radius: 6px; overflow: hidden; position: relative; display: flex; align-items: center; justify-content: center; border: 1px solid #1a2a4a; min-height: 0; }
        .video-wrapper img { width: 100%; height: 100%; object-fit: contain; display: block; }
        .cam-offline { display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; color: #556; z-index: 2; }
        .cam-offline .icon { font-size: 48px; margin-bottom: 12px; }
        .cam-offline .text { font-size: 16px; color: #778; }

        /* 状态栏 */
        .status-bar { display: flex; align-items: center; gap: 24px; padding: 8px 16px; background: #16213e; border-radius: 4px; font-size: 13px; flex-shrink: 0; }
        .status-item { display: flex; align-items: center; gap: 6px; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
        .status-dot.green { background: #4caf50; box-shadow: 0 0 6px #4caf5088; }
        .status-dot.red { background: #f44336; box-shadow: 0 0 6px #f4433688; }
        .status-label { color: #8899bb; }
        .status-val { color: #ddd; }

        /* 操作按钮区 */
        .action-bar { display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap; }
        .btn { padding: 8px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all .2s; display: inline-flex; align-items: center; gap: 6px; }
        .btn:hover { opacity: 0.85; transform: translateY(-1px); }
        .btn-record { background: #e94560; color: #fff; }
        .btn-record.recording { background: #ff1744; animation: recBlink 1s infinite; }
        @keyframes recBlink { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .btn-stop { background: #444; color: #fff; }
        .btn-screenshot { background: #0f3460; color: #fff; }
        .btn-fullscreen { background: #1a3a6a; color: #aabbcc; border: 1px solid #2a4a7a; }
        .btn-fullscreen:hover { background: #2a4a7a; color: #fff; }

        /* 运单绑定区 */
        .waybill-bar { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
        .waybill-bar select { padding: 8px 10px; border-radius: 4px; border: 1px solid #2a3a5a; background: #16213e; color: #ddd; font-size: 13px; width: 100px; }
        .waybill-bar input { flex: 1; padding: 8px 12px; border-radius: 4px; border: 1px solid #2a3a5a; background: #16213e; color: #ddd; font-size: 13px; min-width: 0; }
        .waybill-bar input::placeholder { color: #556; }
        .btn-bind { background: #0f3460; color: #e94560; border: 1px solid #e94560; padding: 8px 18px; border-radius: 4px; cursor: pointer; font-size: 13px; white-space: nowrap; transition: all .2s; }
        .btn-bind:hover { background: #e94560; color: #fff; }

        /* 右侧区域 30% */
        .right-panel { width: 30%; display: flex; flex-direction: column; gap: 10px; padding: 12px 12px 12px 0; min-width: 280px; }

        .panel-card { background: #16213e; border-radius: 6px; display: flex; flex-direction: column; border: 1px solid #1a2a4a; overflow: hidden; }
        .panel-header { padding: 10px 14px; font-size: 14px; font-weight: 600; color: #e94560; border-bottom: 1px solid #1a2a4a; display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
        .panel-body { padding: 10px 14px; flex: 1; overflow-y: auto; min-height: 0; }

        /* 运单检索 */
        .search-row { display: flex; gap: 6px; margin-bottom: 8px; }
        .search-row select { padding: 7px 8px; border-radius: 4px; border: 1px solid #2a3a5a; background: #1a1a2e; color: #ddd; font-size: 12px; width: 80px; }
        .search-row input { flex: 1; padding: 7px 10px; border-radius: 4px; border: 1px solid #2a3a5a; background: #1a1a2e; color: #ddd; font-size: 12px; min-width: 0; }
        .search-row input::placeholder { color: #556; }
        .btn-search { padding: 7px 14px; border: none; border-radius: 4px; background: #e94560; color: #fff; cursor: pointer; font-size: 12px; white-space: nowrap; }
        .btn-search:hover { opacity: 0.85; }
        .file-list { font-size: 12px; }
        .file-item { padding: 6px 8px; border-bottom: 1px solid #1a2a3a; display: flex; justify-content: space-between; align-items: center; }
        .file-item:last-child { border-bottom: none; }
        .file-item-name { color: #bcc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
        .file-item a { color: #e94560; text-decoration: none; font-size: 12px; white-space: nowrap; margin-left: 8px; }
        .file-item a:hover { text-decoration: underline; }

        /* 日志面板 */
        .log-list { font-size: 12px; font-family: "Cascadia Code", "Fira Code", monospace; }
        .log-item { padding: 4px 0; border-bottom: 1px solid #111a2e; line-height: 1.5; }
        .log-item:last-child { border-bottom: none; }
        .log-time { color: #556; margin-right: 6px; }
        .log-ai .log-tag { color: #4caf50; }
        .log-sys .log-tag { color: #42a5f5; }

        /* 滚动条 */
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #2a3a5a; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #3a4a6a; }

        /* 响应式 */
        @media (max-width: 900px) {
            .main-layout { flex-direction: column; }
            .left-panel, .right-panel { width: 100%; }
            .left-panel { height: 55vh; }
            .right-panel { height: 45vh; padding: 0 12px 12px; }
        }
    </style>
</head>
<body>
    <!-- 顶部导航栏 -->
    <div class="topbar">
        <div class="topbar-title"><span>&#9654;</span>电商打包监控系统</div>
        <div class="topbar-right">
            <span class="topbar-time" id="clock"></span>
            <button class="btn-settings" onclick="location.href='/settings'">&#9881; 系统设置</button>
        </div>
    </div>

    <div class="main-layout">
        <!-- 左侧区域 -->
        <div class="left-panel">
            <!-- 视频画面 -->
            <div class="video-wrapper" id="videoWrapper">
                <img id="videoStream" src="/api/stream" alt="实时监控画面">
                <div class="cam-offline" id="camOffline">
                    <div class="icon">&#128247;</div>
                    <div class="text">摄像头连接断开</div>
                </div>
            </div>

            <!-- 状态栏 -->
            <div class="status-bar">
                <div class="status-item">
                    <span class="status-dot red" id="camDot"></span>
                    <span class="status-label">摄像头：</span>
                    <span class="status-val" id="camStatus">未连接</span>
                </div>
                <div class="status-item">
                    <span class="status-label">录像：</span>
                    <span class="status-val" id="recStatus">未录像</span>
                </div>
                <div class="status-item">
                    <span class="status-label">磁盘：</span>
                    <span class="status-val" id="diskStatus">--</span>
                </div>
            </div>

            <!-- 操作按钮 -->
            <div class="action-bar">
                <button class="btn btn-record" id="btnRecord" onclick="toggleRecord()">&#9679; 开始录像</button>
                <button class="btn btn-screenshot" onclick="takeScreenshot()">&#128248; 截图</button>
                <button class="btn btn-fullscreen" onclick="toggleFullscreen()">&#9974; 全屏</button>
            </div>

            <!-- 运单绑定 -->
            <div class="waybill-bar">
                <select id="platform">
                    <option value="douyin">抖音</option>
                    <option value="taobao">淘宝</option>
                    <option value="jd">京东</option>
                    <option value="other">其他</option>
                </select>
                <input type="text" id="waybill" placeholder="输入运单号">
                <button class="btn-bind" onclick="bindWaybill()">绑定</button>
            </div>
        </div>

        <!-- 右侧区域 -->
        <div class="right-panel">
            <!-- 运单检索 -->
            <div class="panel-card" style="flex: 3;">
                <div class="panel-header">&#128269; 运单检索</div>
                <div class="panel-body">
                    <div class="search-row">
                        <select id="fileType" onchange="loadFiles()">
                            <option value="all">全部</option>
                            <option value="record">录像</option>
                            <option value="screenshot">截图</option>
                        </select>
                        <input type="text" id="searchWaybill" placeholder="输入运单号查询">
                        <button class="btn-search" onclick="loadFiles()">查询</button>
                    </div>
                    <div class="file-list" id="fileList"></div>
                </div>
            </div>

            <!-- AI识别日志 -->
            <div class="panel-card" style="flex: 2;">
                <div class="panel-header">&#129302; AI识别日志</div>
                <div class="panel-body">
                    <div class="log-list" id="aiLogList"></div>
                </div>
            </div>

            <!-- 系统运行日志 -->
            <div class="panel-card" style="flex: 2;">
                <div class="panel-header">&#128203; 系统日志</div>
                <div class="panel-body">
                    <div class="log-list" id="sysLogList"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let isRecording = false;
        let ws = null;

        // 时钟
        function updateClock() {
            const now = new Date();
            const str = now.getFullYear() + '-' +
                String(now.getMonth()+1).padStart(2,'0') + '-' +
                String(now.getDate()).padStart(2,'0') + ' ' +
                String(now.getHours()).padStart(2,'0') + ':' +
                String(now.getMinutes()).padStart(2,'0') + ':' +
                String(now.getSeconds()).padStart(2,'0');
            document.getElementById('clock').textContent = str;
        }
        setInterval(updateClock, 1000);
        updateClock();

        // WebSocket
        function connectWS() {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(proto + '//' + location.host + '/api/ws/status');
            ws.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    updateStatus(data);
                } catch(err) {}
            };
            ws.onclose = () => {
                addSysLog('WebSocket 连接断开，3秒后重连...');
                setTimeout(connectWS, 3000);
            };
            ws.onerror = () => {};
        }

        function updateStatus(data) {
            // 摄像头状态
            const dot = document.getElementById('camDot');
            const camSt = document.getElementById('camStatus');
            const offlineDiv = document.getElementById('camOffline');
            const imgEl = document.getElementById('videoStream');
            const connected = data.camera && data.camera.connected;
            dot.className = 'status-dot ' + (connected ? 'green' : 'red');
            camSt.textContent = connected ? '已连接' : '未连接';
            if (connected) {
                offlineDiv.style.display = 'none';
                imgEl.style.display = 'block';
            } else {
                offlineDiv.style.display = 'block';
                imgEl.style.display = 'none';
            }

            // 录像状态
            isRecording = data.recording || false;
            const btn = document.getElementById('btnRecord');
            const recSt = document.getElementById('recStatus');
            if (isRecording) {
                btn.innerHTML = '&#9632; 停止录像';
                btn.className = 'btn btn-record recording';
                recSt.textContent = '录像中';
                recSt.style.color = '#e94560';
            } else {
                btn.innerHTML = '&#9679; 开始录像';
                btn.className = 'btn btn-record';
                recSt.textContent = '未录像';
                recSt.style.color = '';
            }

            // 磁盘
            if (data.disk) {
                document.getElementById('diskStatus').textContent = data.disk.free_mb + ' MB 可用';
            }

            // AI日志
            if (data.ai_log) {
                addAiLog(data.ai_log);
            }
        }

        function nowTime() {
            const d = new Date();
            return String(d.getHours()).padStart(2,'0') + ':' +
                   String(d.getMinutes()).padStart(2,'0') + ':' +
                   String(d.getSeconds()).padStart(2,'0');
        }

        function addAiLog(msg) {
            const list = document.getElementById('aiLogList');
            const div = document.createElement('div');
            div.className = 'log-item log-ai';
            div.innerHTML = '<span class="log-time">' + nowTime() + '</span><span class="log-tag">[AI]</span> ' + escapeHtml(msg);
            list.appendChild(div);
            list.scrollTop = list.scrollHeight;
            while (list.children.length > 100) list.removeChild(list.firstChild);
        }

        function addSysLog(msg) {
            const list = document.getElementById('sysLogList');
            const div = document.createElement('div');
            div.className = 'log-item log-sys';
            div.innerHTML = '<span class="log-time">' + nowTime() + '</span><span class="log-tag">[系统]</span> ' + escapeHtml(msg);
            list.appendChild(div);
            list.scrollTop = list.scrollHeight;
            while (list.children.length > 100) list.removeChild(list.firstChild);
        }

        function escapeHtml(str) {
            const d = document.createElement('div');
            d.textContent = str;
            return d.innerHTML;
        }

        async function toggleRecord() {
            const url = isRecording ? '/api/record/stop' : '/api/record/start';
            addSysLog(isRecording ? '正在停止录像...' : '正在开始录像...');
            await fetch(url, { method: 'POST' });
        }

        async function takeScreenshot() {
            addSysLog('正在截图...');
            await fetch('/api/screenshot', { method: 'POST' });
            addSysLog('截图完成');
            loadFiles();
        }

        async function bindWaybill() {
            const platform = document.getElementById('platform').value;
            const waybill = document.getElementById('waybill').value;
            if (!waybill) { alert('请输入运单号'); return; }
            addSysLog('绑定运单：' + waybill + ' (' + platform + ')');
            await fetch('/api/record/bind', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ platform, waybill })
            });
            addSysLog('运单绑定成功');
            document.getElementById('waybill').value = '';
        }

        async function loadFiles() {
            const type = document.getElementById('fileType').value;
            const resp = await fetch('/api/files?type=' + type);
            const data = await resp.json();
            const list = document.getElementById('fileList');
            if (!data.files || data.files.length === 0) {
                list.innerHTML = '<div style="color:#556;padding:12px;text-align:center;">暂无文件</div>';
                return;
            }
            list.innerHTML = data.files.map(f =>
                '<div class="file-item"><span class="file-item-name">' + escapeHtml(f.name) + '</span><a href="/play/' + f.path + '" target="_blank">播放</a></div>'
            ).join('');
        }

        function toggleFullscreen() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen();
            } else {
                document.exitFullscreen();
            }
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'F11') {
                e.preventDefault();
                toggleFullscreen();
            }
        });

        connectWS();
        loadFiles();
        setInterval(loadFiles, 30000);
        addSysLog('系统启动完成');
    </script>
</body>
</html>"""


def _render_settings_page() -> str:
    """渲染设置页面 HTML"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>系统设置 - 电商打包监控系统</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; background: #1a1a2e; color: #e0e0e0; min-height: 100vh; }

        /* 顶部栏 */
        .topbar { background: #0f3460; height: 52px; display: flex; align-items: center; padding: 0 24px; border-bottom: 1px solid #1a3a6a; gap: 16px; }
        .topbar-title { font-size: 16px; font-weight: 600; color: #fff; }
        .topbar-title span { color: #e94560; margin-right: 8px; }
        .btn-back { background: none; border: 1px solid #3a5078; color: #aabbcc; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; text-decoration: none; transition: all .2s; }
        .btn-back:hover { background: #1a3a6a; color: #fff; border-color: #5577aa; }

        /* Tab 导航 */
        .tab-nav { display: flex; background: #0f3460; padding: 0 24px; border-bottom: 1px solid #1a2a4a; }
        .tab-btn { padding: 12px 24px; background: none; border: none; color: #8899bb; font-size: 14px; cursor: pointer; border-bottom: 2px solid transparent; transition: all .2s; }
        .tab-btn:hover { color: #ddd; }
        .tab-btn.active { color: #e94560; border-bottom-color: #e94560; }

        /* Tab 内容 */
        .tab-content { display: none; padding: 24px; max-width: 680px; }
        .tab-content.active { display: block; }

        /* 表单 */
        .form-card { background: #16213e; border-radius: 6px; padding: 20px; border: 1px solid #1a2a4a; }
        .form-card h3 { font-size: 15px; color: #e94560; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #1a2a4a; }
        .field { margin-bottom: 14px; }
        .field label { display: block; font-size: 13px; color: #8899bb; margin-bottom: 5px; }
        .field input, .field select { width: 100%; padding: 9px 12px; border-radius: 4px; border: 1px solid #2a3a5a; background: #1a1a2e; color: #e0e0e0; font-size: 13px; transition: border .2s; }
        .field input:focus, .field select:focus { outline: none; border-color: #e94560; }
        .field .hint { font-size: 11px; color: #556; margin-top: 3px; }

        /* 底部操作栏 */
        .form-actions { padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
        .btn-save { padding: 10px 32px; border: none; border-radius: 4px; cursor: pointer; background: #e94560; color: #fff; font-size: 14px; font-weight: 500; transition: all .2s; }
        .btn-save:hover { opacity: 0.85; }
        .msg { padding: 8px 14px; border-radius: 4px; font-size: 13px; display: none; }
        .msg.ok { display: block; background: #1b3a1b; color: #4caf50; border: 1px solid #2e5a2e; }
        .msg.err { display: block; background: #3a1b1b; color: #f44336; border: 1px solid #5a2e2e; }

        /* 滚动条 */
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #2a3a5a; border-radius: 3px; }

        @media (max-width: 700px) {
            .tab-content { padding: 16px; }
            .form-card { padding: 14px; }
        }
    </style>
</head>
<body>
    <!-- 顶部栏 -->
    <div class="topbar">
        <div class="topbar-title"><span>&#9881;</span>系统设置</div>
        <a href="/" class="btn-back">&#8592; 返回监控</a>
    </div>

    <!-- Tab 导航 -->
    <div class="tab-nav">
        <button class="tab-btn active" onclick="switchTab('camera')">&#128247; 摄像头配置</button>
        <button class="tab-btn" onclick="switchTab('storage')">&#128190; 存储配置</button>
        <button class="tab-btn" onclick="switchTab('voice')">&#128264; 语音配置</button>
        <button class="tab-btn" onclick="switchTab('ai')">&#129302; AI配置</button>
    </div>

    <!-- 摄像头配置 -->
    <div class="tab-content active" id="tab-camera">
        <div class="form-card">
            <h3>摄像头配置</h3>
            <div class="field">
                <label>摄像头地址（URL）</label>
                <input id="camera_url" placeholder="rtsp://...">
                <div class="hint">支持 RTSP / HTTP 视频流地址</div>
            </div>
            <div class="field">
                <label>重连间隔（毫秒）</label>
                <input id="camera_reconnect" type="number" placeholder="5000">
            </div>
            <div class="field">
                <label>网络超时（毫秒）</label>
                <input id="camera_timeout" type="number" placeholder="10000">
            </div>
        </div>
    </div>

    <!-- 存储配置 -->
    <div class="tab-content" id="tab-storage">
        <div class="form-card">
            <h3>存储配置</h3>
            <div class="field">
                <label>录像保存目录</label>
                <input id="storage_record_dir" placeholder="./recordings">
            </div>
            <div class="field">
                <label>截图保存目录</label>
                <input id="storage_screenshot_dir" placeholder="./screenshots">
            </div>
            <div class="field">
                <label>最小可用空间（MB）</label>
                <input id="storage_min_free" type="number" placeholder="500">
                <div class="hint">低于此值将停止录像并报警</div>
            </div>
            <div class="field">
                <label>录像分段时长（秒）</label>
                <input id="storage_segment" type="number" placeholder="300">
            </div>
            <div class="field">
                <label>录像帧率（FPS）</label>
                <input id="storage_fps" type="number" placeholder="25">
            </div>
        </div>
    </div>

    <!-- 语音配置 -->
    <div class="tab-content" id="tab-voice">
        <div class="form-card">
            <h3>语音配置</h3>
            <div class="field">
                <label>启用语音播报</label>
                <select id="voice_enabled"><option value="true">启用</option><option value="false">禁用</option></select>
            </div>
            <div class="field">
                <label>音量（0-1）</label>
                <input id="voice_volume" type="number" step="0.1" min="0" max="1" placeholder="0.8">
            </div>
            <div class="field">
                <label>语速</label>
                <input id="voice_rate" type="number" placeholder="200">
            </div>
        </div>
    </div>

    <!-- AI配置 -->
    <div class="tab-content" id="tab-ai">
        <div class="form-card">
            <h3>AI识别配置</h3>
            <div class="field">
                <label>启用AI分析</label>
                <select id="ai_enabled"><option value="true">启用</option><option value="false">禁用</option></select>
            </div>
            <div class="field">
                <label>Ollama 服务地址</label>
                <input id="ai_url" placeholder="http://localhost:11434">
            </div>
            <div class="field">
                <label>AI 模型</label>
                <input id="ai_model" placeholder="llava">
            </div>
            <div class="field">
                <label>分析间隔（秒）</label>
                <input id="ai_interval" type="number" placeholder="5">
            </div>
            <div class="field">
                <label>超时时间（秒）</label>
                <input id="ai_timeout" type="number" placeholder="30">
            </div>
        </div>
    </div>

    <!-- 保存按钮 -->
    <div class="form-actions">
        <button class="btn-save" onclick="saveConfig()">&#128190; 保存设置</button>
        <div class="msg" id="msg"></div>
    </div>

    <script>
        function switchTab(name) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.getElementById('tab-' + name).classList.add('active');
            event.target.classList.add('active');
        }

        async function loadConfig() {
            const resp = await fetch('/api/config');
            const cfg = await resp.json();
            document.getElementById('camera_url').value = cfg.camera.url;
            document.getElementById('camera_reconnect').value = cfg.camera.reconnect_interval_ms;
            document.getElementById('camera_timeout').value = cfg.camera.network_timeout_ms;
            document.getElementById('storage_record_dir').value = cfg.storage.record_dir;
            document.getElementById('storage_screenshot_dir').value = cfg.storage.screenshot_dir;
            document.getElementById('storage_min_free').value = cfg.storage.min_free_space_mb;
            document.getElementById('storage_segment').value = cfg.storage.segment_seconds;
            document.getElementById('storage_fps').value = cfg.storage.fps;
            document.getElementById('voice_enabled').value = String(cfg.voice.enabled);
            document.getElementById('voice_volume').value = cfg.voice.volume;
            document.getElementById('voice_rate').value = cfg.voice.rate;
            document.getElementById('ai_enabled').value = String(cfg.ai.enabled);
            document.getElementById('ai_url').value = cfg.ai.ollama_url;
            document.getElementById('ai_model').value = cfg.ai.model;
            document.getElementById('ai_interval').value = cfg.ai.interval_seconds;
            document.getElementById('ai_timeout').value = cfg.ai.timeout_seconds;
        }

        async function saveConfig() {
            const data = {
                camera: {
                    url: document.getElementById('camera_url').value,
                    reconnect_interval_ms: parseInt(document.getElementById('camera_reconnect').value),
                    network_timeout_ms: parseInt(document.getElementById('camera_timeout').value),
                },
                storage: {
                    record_dir: document.getElementById('storage_record_dir').value,
                    screenshot_dir: document.getElementById('storage_screenshot_dir').value,
                    min_free_space_mb: parseInt(document.getElementById('storage_min_free').value),
                    segment_seconds: parseInt(document.getElementById('storage_segment').value),
                    fps: parseInt(document.getElementById('storage_fps').value),
                },
                voice: {
                    enabled: document.getElementById('voice_enabled').value === 'true',
                    volume: parseFloat(document.getElementById('voice_volume').value),
                    rate: parseInt(document.getElementById('voice_rate').value),
                },
                ai: {
                    enabled: document.getElementById('ai_enabled').value === 'true',
                    ollama_url: document.getElementById('ai_url').value,
                    model: document.getElementById('ai_model').value,
                    interval_seconds: parseInt(document.getElementById('ai_interval').value),
                    timeout_seconds: parseInt(document.getElementById('ai_timeout').value),
                },
            };
            const msg = document.getElementById('msg');
            try {
                const resp = await fetch('/api/config', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                if (resp.ok) {
                    msg.className = 'msg ok';
                    msg.textContent = '设置保存成功！';
                } else {
                    msg.className = 'msg err';
                    msg.textContent = '保存失败，请检查输入';
                }
            } catch (e) {
                msg.className = 'msg err';
                msg.textContent = '网络错误：' + e.message;
            }
        }

        loadConfig();
    </script>
</body>
</html>"""


def _render_play_page(filepath: str) -> str:
    """渲染在线播放页面 HTML"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>视频回放 - 电商打包监控系统</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; background: #1a1a2e; color: #e0e0e0; display: flex; flex-direction: column; height: 100vh; }}

        /* 顶部栏 */
        .topbar {{ background: #0f3460; height: 52px; display: flex; align-items: center; padding: 0 24px; border-bottom: 1px solid #1a3a6a; gap: 16px; flex-shrink: 0; }}
        .topbar-title {{ font-size: 16px; font-weight: 600; color: #fff; }}
        .topbar-title span {{ color: #e94560; margin-right: 8px; }}
        .btn-back {{ background: none; border: 1px solid #3a5078; color: #aabbcc; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; text-decoration: none; transition: all .2s; }}
        .btn-back:hover {{ background: #1a3a6a; color: #fff; border-color: #5577aa; }}

        /* 视频区域 */
        .player-wrap {{ flex: 1; display: flex; align-items: center; justify-content: center; padding: 16px; min-height: 0; }}
        video {{ max-width: 100%; max-height: 100%; border-radius: 6px; background: #000; box-shadow: 0 2px 16px rgba(0,0,0,0.5); }}
        .no-support {{ color: #778; font-size: 16px; text-align: center; }}
    </style>
</head>
<body>
    <div class="topbar">
        <div class="topbar-title"><span>&#9654;</span>视频回放</div>
        <a href="/" class="btn-back">&#8592; 返回监控</a>
    </div>
    <div class="player-wrap">
        <video controls autoplay>
            <source src="/api/files/{filepath}" type="video/x-msvideo">
            <p class="no-support">您的浏览器不支持视频播放，请使用 Chrome 或 Edge 浏览器。</p>
        </video>
    </div>
</body>
</html>"""
