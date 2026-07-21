using System;
using System.IO;
using System.Linq;
using System.Threading;

namespace PackingMonitor;

/// <summary>
/// 自动分段录像 + 磁盘空间管理
///
/// 工作机制：
///   - 接收 MjpegStreamer 推过来的帧
///   - 写入当前分段文件（按 segmentSeconds 切片）
///   - 文件名格式：yyyyMMdd_HHmmss.avi
///   - 写每帧前检查磁盘剩余空间，低于阈值时按 mtime 升序删除旧文件
/// </summary>
public sealed class RecordManager : IDisposable
{
    private readonly object _lock = new();
    private AviMjpegWriter? _currentWriter;
    private string? _currentFile;
    private DateTime _segmentStartTime;
    private int _width, _height;
    private bool _isRecording;
    private bool _disposed;

    public event EventHandler<string>? SegmentStarted;
    public event EventHandler<string>? SegmentClosed;

    public bool IsRecording => _isRecording;
    public string? CurrentFile => _currentFile;

    /// <summary>开始录像（首帧决定分辨率）</summary>
    public void Start(byte[] firstJpegFrame, int width, int height)
    {
        lock (_lock)
        {
            if (_isRecording) return;
            try
            {
                _width = width;
                _height = height;
                _currentFile = BuildSegmentPath();
                var fps = ConfigManager.Current.Record.Fps;
                _currentWriter = new AviMjpegWriter(_currentFile, _width, _height, fps);
                _segmentStartTime = DateTime.Now;
                _isRecording = true;
                _currentWriter.WriteFrame(firstJpegFrame);
                LogUtil.Info("Record", $"开始分段 -> {_currentFile} ({width}x{height}@{fps}fps)");
                SegmentStarted?.Invoke(this, _currentFile);
            }
            catch (Exception ex)
            {
                LogUtil.Error("Record", $"开启录像失败: {ex.Message}", ex);
                _isRecording = false;
                try { _currentWriter?.Dispose(); } catch { }
                _currentWriter = null;
                _currentFile = null;
            }
        }
    }

    public void Stop()
    {
        lock (_lock)
        {
            if (!_isRecording) return;
            try
            {
                _currentWriter?.Close();
                LogUtil.Info("Record", $"停止录像 -> {_currentFile} (共 {_currentWriter?.FrameCount ?? 0} 帧)");
                var closed = _currentFile;
                SegmentClosed?.Invoke(this, closed ?? "");
            }
            catch (Exception ex)
            {
                LogUtil.Error("Record", $"关闭录像失败: {ex.Message}", ex);
            }
            finally
            {
                _currentWriter?.Dispose();
                _currentWriter = null;
                _currentFile = null;
                _isRecording = false;
            }
        }
    }

    /// <summary>写入一帧。返回 true 表示已写入（含自动切换分段）。</summary>
    public bool WriteFrame(byte[] jpeg)
    {
        if (!_isRecording || jpeg == null || jpeg.Length == 0) return false;

        lock (_lock)
        {
            if (!_isRecording || _currentWriter == null) return false;

            try
            {
                // 检查是否需要切换分段
                var elapsed = (DateTime.Now - _segmentStartTime).TotalSeconds;
                if (elapsed >= ConfigManager.Current.Record.SegmentSeconds)
                {
                    RotateSegmentLocked();
                }

                _currentWriter.WriteFrame(jpeg);
                return true;
            }
            catch (Exception ex)
            {
                LogUtil.Error("Record", $"写入帧失败: {ex.Message}", ex);
                return false;
            }
        }
    }

    /// <summary>写帧后调用：检查磁盘空间，必要时清理旧文件</summary>
    public void CheckDiskSpace()
    {
        if (!_isRecording) return;
        try
        {
            var cfg = ConfigManager.Current.Storage;
            var dir = ConfigManager.ResolveDir(cfg.RecordDir);
            if (!Directory.Exists(dir)) return;

            var drive = new DriveInfo(Path.GetPathRoot(dir) ?? dir);
            if (!drive.IsReady) return;

            var freeMB = drive.AvailableFreeSpace / (1024 * 1024);
            if (freeMB < cfg.MinFreeSpaceMB)
            {
                LogUtil.Warn("Record", $"磁盘剩余 {freeMB}MB < 阈值 {cfg.MinFreeSpaceMB}MB，开始清理旧录像");
                CleanupOldFiles(dir, drive, cfg.MinFreeSpaceMB);
            }
        }
        catch (Exception ex)
        {
            LogUtil.Warn("Record", $"磁盘检查异常: {ex.Message}");
        }
    }

    private void CleanupOldFiles(string dir, DriveInfo drive, long targetFreeMB)
    {
        try
        {
            var files = Directory.EnumerateFiles(dir, "*.avi", SearchOption.TopDirectoryOnly)
                .Select(f => new FileInfo(f))
                .OrderBy(f => f.LastWriteTime)
                .ToList();

            foreach (var f in files)
            {
                if (drive.AvailableFreeSpace / (1024 * 1024) >= targetFreeMB) break;
                try
                {
                    LogUtil.Info("Record", $"删除旧录像: {f.Name} ({f.Length / 1024}KB)");
                    f.Delete();
                }
                catch (Exception ex)
                {
                    LogUtil.Warn("Record", $"删除失败 {f.Name}: {ex.Message}");
                }
            }
        }
        catch (Exception ex)
        {
            LogUtil.Warn("Record", $"清理旧录像异常: {ex.Message}");
        }
    }

    private void RotateSegmentLocked()
    {
        if (_currentWriter == null) return;
        try
        {
            var oldFile = _currentFile;
            _currentWriter.Close();
            LogUtil.Info("Record", $"分段结束 -> {oldFile} (共 {_currentWriter.FrameCount} 帧)");
            SegmentClosed?.Invoke(this, oldFile ?? "");
            _currentWriter.Dispose();
        }
        catch (Exception ex)
        {
            LogUtil.Error("Record", $"分段切换异常: {ex.Message}", ex);
        }

        _currentFile = BuildSegmentPath();
        var fps = ConfigManager.Current.Record.Fps;
        _currentWriter = new AviMjpegWriter(_currentFile, _width, _height, fps);
        _segmentStartTime = DateTime.Now;
        LogUtil.Info("Record", $"开始新分段 -> {_currentFile}");
        SegmentStarted?.Invoke(this, _currentFile);
    }

    private string BuildSegmentPath()
    {
        var dir = ConfigManager.ResolveDir(ConfigManager.Current.Storage.RecordDir);
        Directory.CreateDirectory(dir);
        var name = DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".avi";
        return Path.Combine(dir, name);
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        Stop();
    }
}
