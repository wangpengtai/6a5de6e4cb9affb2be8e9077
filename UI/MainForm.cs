using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace PackingMonitor;

/// <summary>
/// 主窗口 —— 极简 UI：实时画面 + 录像开关 + 截图 + 设置 四件套
///
/// - PictureBox SizeMode = Zoom，画面等比缩放不变形
/// - 后台线程拉流推帧，UI Timer 按 ~30fps 节拍拉取最新帧（仅保留 1 帧）
/// - F11 切换全屏，Esc 退出全屏
/// - 窗口最小化 / 后台时拉流与录像继续运行
/// </summary>
public sealed class MainForm : Form
{
    private readonly MjpegStreamer _streamer = new();
    private readonly RecordManager _recorder = new();
    private readonly OllamaAnalyzer _analyzer = new();

    private readonly PictureBox _pic = new();
    private readonly Button _btnRecord = new();
    private readonly Button _btnShot = new();
    private readonly Button _btnSettings = new();
    private readonly Label _lblStatus = new();
    private readonly Label _lblRecord = new();
    private readonly Label _lblAi = new();
    private readonly System.Windows.Forms.Timer _renderTimer = new() { Interval = 33 }; // ~30fps
    private readonly System.Windows.Forms.Timer _diskCheckTimer = new() { Interval = 30000 }; // 30s 检查磁盘
    private readonly System.Windows.Forms.Timer _aiHideTimer = new() { Interval = 8000 }; // AI 文本 8s 后隐藏

    private bool _isFullScreen;
    private FormBorderStyle _savedBorder;
    private Size _savedClientSize;
    private Point _savedLocation;
    private bool _isClosing;

    public MainForm()
    {
        Text = "电商打包监控";
        Icon = null;
        ClientSize = new Size(960, 600);
        MinimumSize = new Size(640, 400);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(32, 32, 32);
        KeyPreview = true;
        FormBorderStyle = FormBorderStyle.Sizable;
        DoubleBuffered = true;
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);

        BuildUi();

        _streamer.FrameReceived += OnFrameReceived;
        _streamer.StatusChanged += OnStreamStatus;
        _recorder.SegmentStarted += (_, p) => BeginInvoke(() => _lblRecord.Text = "● REC  " + Path.GetFileName(p));
        _recorder.SegmentClosed += (_, p) => BeginInvoke(() => _lblRecord.Text = "");
        _analyzer.Analyzed += (_, line) => BeginInvoke(() => ShowAiText(line));

        _renderTimer.Tick += (_, _) => RenderLatestFrame();
        _renderTimer.Start();

        _diskCheckTimer.Tick += (_, _) => _recorder.CheckDiskSpace();
        _diskCheckTimer.Start();

        _aiHideTimer.Tick += (_, _) => { _lblAi.Text = ""; _aiHideTimer.Stop(); };

        FormClosing += MainForm_FormClosing;
        Resize += (_, _) => CenterStatusBar();
        Shown += (_, _) =>
        {
            _streamer.Start();
            if (ConfigManager.Current.Record.AutoStart) ToggleRecording();
            if (ConfigManager.Current.Ai.Enabled) _analyzer.Start();
        };

        LogUtil.Init(AppContext.BaseDirectory);
        LogUtil.Info("Main", "程序启动");
    }

    private void BuildUi()
    {
        // 画面区
        _pic.Dock = DockStyle.Fill;
        _pic.BackColor = Color.Black;
        _pic.SizeMode = PictureBoxSizeMode.Zoom;
        Controls.Add(_pic);

        // 底部状态/工具栏
        var bar = new Panel
        {
            Dock = DockStyle.Bottom,
            Height = 44,
            BackColor = Color.FromArgb(48, 48, 48),
            Padding = new Padding(8, 6, 8, 6)
        };
        Controls.Add(bar);

        _btnRecord.Text = "● 开始录像";
        _btnRecord.Size = new Size(110, 32);
        _btnRecord.BackColor = Color.FromArgb(180, 50, 50);
        _btnRecord.ForeColor = Color.White;
        _btnRecord.FlatStyle = FlatStyle.Flat;
        _btnRecord.FlatAppearance.BorderSize = 0;
        _btnRecord.Font = new Font("Segoe UI", 9.5F, FontStyle.Bold);
        _btnRecord.Click += (_, _) => ToggleRecording();

        _btnShot.Text = "📷 截图";
        _btnShot.Size = new Size(100, 32);
        _btnShot.BackColor = Color.FromArgb(70, 130, 180);
        _btnShot.ForeColor = Color.White;
        _btnShot.FlatStyle = FlatStyle.Flat;
        _btnShot.FlatAppearance.BorderSize = 0;
        _btnShot.Font = new Font("Segoe UI", 9.5F, FontStyle.Bold);
        _btnShot.Click += (_, _) => TakeScreenshot();

        _btnSettings.Text = "⚙ 设置";
        _btnSettings.Size = new Size(100, 32);
        _btnSettings.BackColor = Color.FromArgb(90, 90, 90);
        _btnSettings.ForeColor = Color.White;
        _btnSettings.FlatStyle = FlatStyle.Flat;
        _btnSettings.FlatAppearance.BorderSize = 0;
        _btnSettings.Font = new Font("Segoe UI", 9.5F, FontStyle.Bold);
        _btnSettings.Click += (_, _) => OpenSettings();

        _lblRecord.Text = "";
        _lblRecord.AutoSize = true;
        _lblRecord.ForeColor = Color.FromArgb(255, 80, 80);
        _lblRecord.Font = new Font("Consolas", 10F, FontStyle.Bold);

        _lblStatus.Text = "未连接";
        _lblStatus.AutoSize = true;
        _lblStatus.ForeColor = Color.LightGray;
        _lblStatus.Font = new Font("Segoe UI", 9F);

        _lblAi.Text = "";
        _lblAi.AutoSize = true;
        _lblAi.ForeColor = Color.FromArgb(255, 220, 100);
        _lblAi.Font = new Font("Segoe UI", 8.5F, FontStyle.Italic);
        _lblAi.BackColor = Color.FromArgb(20, 20, 20);
        _lblAi.Padding = new Padding(4, 2, 4, 2);

        bar.Controls.Add(_btnRecord);
        bar.Controls.Add(_btnShot);
        bar.Controls.Add(_btnSettings);
        bar.Controls.Add(_lblRecord);
        bar.Controls.Add(_lblStatus);
        bar.Controls.Add(_lblAi);
    }

    private void ShowAiText(string line)
    {
        // 截断过长文本
        if (line.Length > 80) line = line.Substring(0, 80) + "...";
        _lblAi.Text = "🤖 " + line;
        CenterStatusBar();
        _aiHideTimer.Stop();
        _aiHideTimer.Start();
    }

    private void CenterStatusBar()
    {
        if (Controls.Count < 2) return;
        var bar = (Panel)Controls[1];
        if (_btnRecord == null || _btnShot == null || _btnSettings == null) return;
        int y = (bar.Height - _btnRecord.Height) / 2;
        _btnRecord.Location = new Point(8, y);
        _btnShot.Location = new Point(_btnRecord.Right + 8, y);
        _btnSettings.Location = new Point(_btnShot.Right + 8, y);
        _lblRecord.Location = new Point(_btnSettings.Right + 16, y + 6);

        // 状态栏右侧：先放 AI 文本，再放连接状态
        int rightX = bar.Width - 12;
        _lblStatus.Location = new Point(rightX - _lblStatus.Width, y + 8);
        _lblAi.Location = new Point(_lblStatus.Left - _lblAi.Width - 12, y + 6);
    }

    private void OnFrameReceived(object? sender, MjpegFrameEventArgs e)
    {
        // 1) 录像：直接拿 JPEG 字节写入 AVI
        if (_recorder.IsRecording)
        {
            _recorder.WriteFrame(e.JpegBytes);
        }
        // 2) AI：发布到总线
        MjpegFrameBus.Publish(e.JpegBytes, e.Timestamp);
    }

    private void OnStreamStatus(object? sender, StreamStatusEventArgs e)
    {
        BeginInvoke(() =>
        {
            var txt = e.Status switch
            {
                StreamStatus.Connected => "● 在线",
                StreamStatus.Connecting => "○ 正在连接…",
                StreamStatus.Reconnecting => "↻ 重连中",
                StreamStatus.Error => "× 错误",
                _ => "○ 离线"
            };
            _lblStatus.Text = $"{txt}  {e.Message}";
            _lblStatus.ForeColor = e.Status switch
            {
                StreamStatus.Connected => Color.FromArgb(120, 220, 120),
                StreamStatus.Reconnecting => Color.FromArgb(255, 200, 100),
                StreamStatus.Error => Color.FromArgb(255, 100, 100),
                _ => Color.LightGray
            };
        });
    }

    private void RenderLatestFrame()
    {
        if (_isClosing) return;
        if (!_streamer.TryGetLatestFrame(out _, out var bmp, out _)) return;
        if (bmp == null) return;

        // 关键：PictureBox 持有旧 Image，替换前必须 Dispose 旧图，否则内存泄漏
        var old = _pic.Image;
        _pic.Image = (Bitmap)bmp.Clone();
        old?.Dispose();
    }

    private void ToggleRecording()
    {
        if (_recorder.IsRecording)
        {
            _recorder.Stop();
            _btnRecord.Text = "● 开始录像";
            _btnRecord.BackColor = Color.FromArgb(180, 50, 50);
        }
        else
        {
            if (_streamer.TryGetLatestFrame(out var jpeg, out var bmp, out _))
            {
                _recorder.Start(jpeg!, bmp!.Width, bmp.Height);
                _btnRecord.Text = "■ 停止录像";
                _btnRecord.BackColor = Color.FromArgb(60, 60, 60);
            }
            else
            {
                MessageBox.Show("暂无画面，无法开启录像。", "提示",
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }
    }

    private void TakeScreenshot()
    {
        try
        {
            if (!_streamer.TryGetLatestFrame(out var jpeg, out var bmp, out _))
            {
                MessageBox.Show("暂无画面，无法截图。", "提示",
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            var dir = ConfigManager.ResolveDir(ConfigManager.Current.Storage.ScreenshotDir);
            Directory.CreateDirectory(dir);
            var name = $"shot_{DateTime.Now:yyyyMMdd_HHmmss_fff}.jpg";
            var path = Path.Combine(dir, name);
            File.WriteAllBytes(path, jpeg!);
            LogUtil.Info("Shot", $"已保存截图 -> {path}");
        }
        catch (Exception ex)
        {
            LogUtil.Error("Shot", "截图失败", ex);
            MessageBox.Show("截图失败：" + ex.Message, "错误",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void OpenSettings()
    {
        using var frm = new SettingsForm();
        if (frm.ShowDialog(this) == DialogResult.OK)
        {
            // 配置已重载：重启拉流使 URL 生效
            _streamer.Stop();
            _analyzer.Stop();
            _streamer.Start();
            if (ConfigManager.Current.Record.AutoStart && !_recorder.IsRecording)
                ToggleRecording();
            if (ConfigManager.Current.Ai.Enabled) _analyzer.Start();
        }
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData == Keys.F11)
        {
            ToggleFullScreen();
            return true;
        }
        if (keyData == Keys.Escape && _isFullScreen)
        {
            ToggleFullScreen();
            return true;
        }
        if (keyData == Keys.F12)
        {
            TakeScreenshot();
            return true;
        }
        return base.ProcessCmdKey(ref msg, keyData);
    }

    private void ToggleFullScreen()
    {
        if (!_isFullScreen)
        {
            _savedBorder = FormBorderStyle;
            _savedClientSize = ClientSize;
            _savedLocation = Location;
            FormBorderStyle = FormBorderStyle.None;
            WindowState = FormWindowState.Maximized;
            _isFullScreen = true;
        }
        else
        {
            FormBorderStyle = _savedBorder;
            WindowState = FormWindowState.Normal;
            ClientSize = _savedClientSize;
            Location = _savedLocation;
            _isFullScreen = false;
        }
    }

    // 主窗口大小变化（窗口最大化等）时同步状态栏位置
    protected override void OnResize(EventArgs e)
    {
        base.OnResize(e);
        CenterStatusBar();
    }

    private void MainForm_FormClosing(object? sender, FormClosingEventArgs e)
    {
        _isClosing = true;
        _renderTimer.Stop();
        _diskCheckTimer.Stop();
        _aiHideTimer.Stop();
        _streamer.Stop();
        _recorder.Stop();
        _analyzer.Stop();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _streamer.Dispose();
            _recorder.Dispose();
            _analyzer.Dispose();
            _renderTimer.Dispose();
            _diskCheckTimer.Dispose();
            _aiHideTimer.Dispose();
        }
        base.Dispose(disposing);
    }
}
