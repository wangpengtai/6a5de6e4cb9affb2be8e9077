using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace PackingMonitor;

/// <summary>
/// 设置窗体：摄像头、录像、存储、AI 四个分组。
/// 保存到 config.json 后通过 OK 返回，主窗口重启拉流。
/// </summary>
public sealed class SettingsForm : Form
{
    private readonly AppConfig _cfg = ConfigManager.Current;

    private TextBox _txtUrl = null!;
    private NumericUpDown _numTimeout = null!;
    private NumericUpDown _numReconnect = null!;
    private TextBox _txtUserAgent = null!;

    private CheckBox _chkAutoRecord = null!;
    private NumericUpDown _numSegment = null!;
    private NumericUpDown _numFps = null!;

    private TextBox _txtRecDir = null!;
    private TextBox _txtShotDir = null!;
    private NumericUpDown _numMinFree = null!;

    private CheckBox _chkAiEnabled = null!;
    private TextBox _txtOllama = null!;
    private TextBox _txtModel = null!;
    private NumericUpDown _numInterval = null!;
    private NumericUpDown _numAiTimeout = null!;

    public SettingsForm()
    {
        Text = "设置 - 电商打包监控";
        ClientSize = new Size(640, 560);
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        BackColor = Color.White;
        Font = new Font("Segoe UI", 9F);

        var tabs = new TabControl { Dock = DockStyle.Fill, Padding = new Point(12, 6) };

        tabs.TabPages.Add(BuildCameraTab());
        tabs.TabPages.Add(BuildRecordTab());
        tabs.TabPages.Add(BuildStorageTab());
        tabs.TabPages.Add(BuildAiTab());

        Controls.Add(tabs);

        var bottom = new Panel { Dock = DockStyle.Bottom, Height = 48, BackColor = Color.FromArgb(245, 245, 245) };
        var btnOk = new Button
        {
            Text = "保存",
            Size = new Size(90, 32),
            Location = new Point(ClientSize.Width - 200, 8),
            BackColor = Color.FromArgb(60, 130, 200),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            DialogResult = DialogResult.OK
        };
        btnOk.FlatAppearance.BorderSize = 0;
        btnOk.Click += (_, _) => SaveAndClose();

        var btnCancel = new Button
        {
            Text = "取消",
            Size = new Size(90, 32),
            Location = new Point(ClientSize.Width - 100, 8),
            BackColor = Color.FromArgb(180, 180, 180),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            DialogResult = DialogResult.Cancel
        };
        btnCancel.FlatAppearance.BorderSize = 0;

        bottom.Controls.Add(btnOk);
        bottom.Controls.Add(btnCancel);
        Controls.Add(bottom);

        AcceptButton = btnOk;
        CancelButton = btnCancel;

        LoadConfigToUi();
    }

    // ----- 构建 Tab -----
    private TabPage BuildCameraTab()
    {
        var page = new TabPage("摄像头");
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 5,
            Padding = new Padding(16),
            AutoSize = false
        };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 140));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));

        _txtUrl = new TextBox { Dock = DockStyle.Fill };
        _numTimeout = new NumericUpDown { Minimum = 500, Maximum = 60000, Increment = 500, Width = 160 };
        _numReconnect = new NumericUpDown { Minimum = 200, Maximum = 30000, Increment = 200, Width = 160 };
        _txtUserAgent = new TextBox { Dock = DockStyle.Fill };

        AddRow(layout, "视频流 URL（IP Webcam）", _txtUrl,
            "例：http://192.168.1.100:8080/videofeed");
        AddRow(layout, "断线判定时长（毫秒）", _numTimeout,
            "超过此时间无帧即认为断开，默认 3000");
        AddRow(layout, "重连间隔（毫秒）", _numReconnect,
            "网络断开后每隔多久重连，默认 1000");
        AddRow(layout, "User-Agent", _txtUserAgent, "");

        page.Controls.Add(layout);
        return page;
    }

    private TabPage BuildRecordTab()
    {
        var page = new TabPage("录像");
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 3,
            Padding = new Padding(16)
        };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 140));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));

        _chkAutoRecord = new CheckBox { Text = "程序启动后自动开始录像", AutoSize = true };
        _numSegment = new NumericUpDown { Minimum = 10, Maximum = 7200, Increment = 60, Width = 160 };
        _numFps = new NumericUpDown { Minimum = 1, Maximum = 60, Increment = 1, Width = 160 };

        AddRow(layout, "自动录像", _chkAutoRecord, "启动后立即进入录像状态");
        AddRow(layout, "单段时长（秒）", _numSegment, "默认 600 秒 = 10 分钟");
        AddRow(layout, "帧率（用于播放器呈现）", _numFps, "默认 15");

        page.Controls.Add(layout);
        return page;
    }

    private TabPage BuildStorageTab()
    {
        var page = new TabPage("存储");
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 3,
            Padding = new Padding(16)
        };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 140));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 80));

        _txtRecDir = new TextBox { Dock = DockStyle.Fill };
        _txtShotDir = new TextBox { Dock = DockStyle.Fill };
        _numMinFree = new NumericUpDown { Minimum = 100, Maximum = 1024 * 1024, Increment = 512, Width = 160 };

        var btnRecDir = new Button { Text = "浏览…", Size = new Size(70, 28) };
        btnRecDir.Click += (_, _) => PickDir(_txtRecDir);
        var btnShotDir = new Button { Text = "浏览…", Size = new Size(70, 28) };
        btnShotDir.Click += (_, _) => PickDir(_txtShotDir);

        AddRow3(layout, "录像保存目录", _txtRecDir, btnRecDir, "留空则使用 exe 同目录 record/");
        AddRow3(layout, "截图保存目录", _txtShotDir, btnShotDir, "留空则使用 exe 同目录 screenshots/");
        AddRow(layout, "最小剩余空间(MB)", _numMinFree, "低于此值自动删除最早录像");

        page.Controls.Add(layout);
        return page;
    }

    private TabPage BuildAiTab()
    {
        var page = new TabPage("AI (Ollama)");
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 5,
            Padding = new Padding(16)
        };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 140));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));

        _chkAiEnabled = new CheckBox { Text = "启用 AI 多模态分析（默认关闭）", AutoSize = true };
        _txtOllama = new TextBox { Dock = DockStyle.Fill };
        _txtModel = new TextBox { Dock = DockStyle.Fill };
        _numInterval = new NumericUpDown { Minimum = 1, Maximum = 3600, Increment = 1, Width = 160 };
        _numAiTimeout = new NumericUpDown { Minimum = 1, Maximum = 600, Increment = 5, Width = 160 };

        AddRow(layout, "AI 总开关", _chkAiEnabled, "关闭时不加载任何 AI 资源，不占 CPU/内存");
        AddRow(layout, "Ollama 地址", _txtOllama, "默认 http://127.0.0.1:11434/api/generate");
        AddRow(layout, "多模态模型", _txtModel, "例：llama3.2-vision / llava / minicpm-v");
        AddRow(layout, "画面分析间隔(秒)", _numInterval, "每隔多少秒抓一帧分析");
        AddRow(layout, "请求超时(秒)", _numAiTimeout, "Ollama 不响应时的最长等待");

        page.Controls.Add(layout);
        return page;
    }

    // ---- 工具方法 ----
    private static void AddRow(TableLayoutPanel p, string label, Control c, string help)
    {
        var row = p.RowCount++;
        p.RowStyles.Add(new RowStyle(SizeType.Absolute, 36));
        var lbl = new Label
        {
            Text = string.IsNullOrEmpty(help) ? label : $"{label}\n{help}",
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft,
            AutoSize = false,
            ForeColor = Color.Black
        };
        c.Dock = DockStyle.Fill;
        p.Controls.Add(lbl, 0, row);
        p.Controls.Add(c, 1, row);
    }

    private static void AddRow3(TableLayoutPanel p, string label, Control c, Control c2, string help)
    {
        var row = p.RowCount++;
        p.RowStyles.Add(new RowStyle(SizeType.Absolute, 36));
        var lbl = new Label
        {
            Text = string.IsNullOrEmpty(help) ? label : $"{label}\n{help}",
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft
        };
        var inner = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
        inner.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        inner.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 80));
        c.Dock = DockStyle.Fill;
        c2.Dock = DockStyle.Right;
        inner.Controls.Add(c, 0, 0);
        inner.Controls.Add(c2, 1, 0);
        p.Controls.Add(lbl, 0, row);
        p.Controls.Add(inner, 1, row);
    }

    private static void PickDir(TextBox target)
    {
        using var dlg = new FolderBrowserDialog();
        if (dlg.ShowDialog() == DialogResult.OK) target.Text = dlg.SelectedPath;
    }

    private void LoadConfigToUi()
    {
        _txtUrl.Text = _cfg.Camera.Url;
        _numTimeout.Value = _cfg.Camera.NetworkTimeoutMs;
        _numReconnect.Value = _cfg.Camera.ReconnectIntervalMs;
        _txtUserAgent.Text = _cfg.Camera.UserAgent;

        _chkAutoRecord.Checked = _cfg.Record.AutoStart;
        _numSegment.Value = _cfg.Record.SegmentSeconds;
        _numFps.Value = _cfg.Record.Fps;

        _txtRecDir.Text = _cfg.Storage.RecordDir;
        _txtShotDir.Text = _cfg.Storage.ScreenshotDir;
        _numMinFree.Value = _cfg.Storage.MinFreeSpaceMB;

        _chkAiEnabled.Checked = _cfg.Ai.Enabled;
        _txtOllama.Text = _cfg.Ai.OllamaUrl;
        _txtModel.Text = _cfg.Ai.Model;
        _numInterval.Value = _cfg.Ai.IntervalSeconds;
        _numAiTimeout.Value = _cfg.Ai.TimeoutSeconds;
    }

    private void SaveAndClose()
    {
        _cfg.Camera.Url = _txtUrl.Text.Trim();
        _cfg.Camera.NetworkTimeoutMs = (int)_numTimeout.Value;
        _cfg.Camera.ReconnectIntervalMs = (int)_numReconnect.Value;
        _cfg.Camera.UserAgent = _txtUserAgent.Text.Trim();

        _cfg.Record.AutoStart = _chkAutoRecord.Checked;
        _cfg.Record.SegmentSeconds = (int)_numSegment.Value;
        _cfg.Record.Fps = (int)_numFps.Value;

        _cfg.Storage.RecordDir = _txtRecDir.Text.Trim();
        _cfg.Storage.ScreenshotDir = _txtShotDir.Text.Trim();
        _cfg.Storage.MinFreeSpaceMB = (long)_numMinFree.Value;

        _cfg.Ai.Enabled = _chkAiEnabled.Checked;
        _cfg.Ai.OllamaUrl = _txtOllama.Text.Trim();
        _cfg.Ai.Model = _txtModel.Text.Trim();
        _cfg.Ai.IntervalSeconds = (int)_numInterval.Value;
        _cfg.Ai.TimeoutSeconds = (int)_numAiTimeout.Value;

        ConfigManager.Save(_cfg);
    }
}
