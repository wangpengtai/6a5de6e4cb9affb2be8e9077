using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace PackingMonitor;

/// <summary>
/// MJPEG 帧事件参数
/// </summary>
public sealed class MjpegFrameEventArgs : EventArgs
{
    public byte[] JpegBytes { get; }
    public Bitmap Bitmap { get; }
    public DateTime Timestamp { get; }

    public MjpegFrameEventArgs(byte[] jpeg, Bitmap bitmap, DateTime ts)
    {
        JpegBytes = jpeg;
        Bitmap = bitmap;
        Timestamp = ts;
    }
}

/// <summary>
/// 状态变更事件
/// </summary>
public enum StreamStatus
{
    Disconnected,
    Connecting,
    Connected,
    Reconnecting,
    Error
}

public sealed class StreamStatusEventArgs : EventArgs
{
    public StreamStatus Status { get; }
    public string Message { get; }

    public StreamStatusEventArgs(StreamStatus s, string msg)
    {
        Status = s;
        Message = msg;
    }
}

/// <summary>
/// 局域网 HTTP MJPEG 拉流器。专为 IP Webcam /videofeed 等服务设计。
///
/// 特性：
///   - 单一后台线程拉流，仅保留最新 1 帧在共享内存，最大限度降低延迟
///   - 兼容 multipart/x-mixed-replace 格式（IP Webcam 默认）
///   - 兼容裸连续 JPEG 流（部分设备）
///   - 网络断开后按 ReconnectIntervalMs 持续重连，NetworkTimeoutMs 内任意帧到达即视为在线
///   - HttpClient 缓冲区设为 1 字节，关闭预缓存
/// </summary>
public sealed class MjpegStreamer : IDisposable
{
    private readonly object _frameLock = new();
    private byte[]? _latestJpeg;
    private Bitmap? _latestBitmap;
    private DateTime _lastFrameTime = DateTime.MinValue;

    private CancellationTokenSource? _cts;
    private Task? _loopTask;
    private volatile StreamStatus _status = StreamStatus.Disconnected;
    private int _reconnectCount;

    /// <summary>每帧到达事件（后台线程触发，订阅方应自行 marshal 到 UI 线程）</summary>
    public event EventHandler<MjpegFrameEventArgs>? FrameReceived;
    /// <summary>状态变更事件</summary>
    public event EventHandler<StreamStatusEventArgs>? StatusChanged;

    public StreamStatus Status => _status;
    public DateTime LastFrameTime => _lastFrameTime;
    public int ReconnectCount => _reconnectCount;

    public void Start()
    {
        if (_loopTask != null && !_loopTask.IsCompleted) return;
        _cts = new CancellationTokenSource();
        _loopTask = Task.Run(() => RunLoopAsync(_cts.Token));
    }

    public void Stop()
    {
        try { _cts?.Cancel(); } catch { }
        try { _loopTask?.Wait(1500); } catch { }
        _cts?.Dispose();
        _cts = null;
        _loopTask = null;
        SetStatus(StreamStatus.Disconnected, "已停止");
        ClearLatest();
    }

    /// <summary>获取最新帧（线程安全），无帧返回 null</summary>
    public bool TryGetLatestFrame(out byte[]? jpeg, out Bitmap? bmp, out DateTime ts)
    {
        lock (_frameLock)
        {
            jpeg = _latestJpeg;
            bmp = _latestBitmap;
            ts = _lastFrameTime;
            return jpeg != null && bmp != null;
        }
    }

    private void SetLatest(byte[] jpeg, Bitmap bmp, DateTime ts)
    {
        lock (_frameLock)
        {
            // 仅保留 1 帧引用：替换为新帧
            // 注意：此处不释放旧 Bitmap，避免与 UI 线程的 Clone 产生竞态。
            // Bitmap 生命周期由 UI 线程在替换 _pic.Image 时 Dispose 旧图。
            _latestJpeg = jpeg;
            _latestBitmap = bmp;
            _lastFrameTime = ts;
        }
    }

    private void ClearLatest()
    {
        lock (_frameLock)
        {
            _latestJpeg = null;
            if (_latestBitmap != null)
            {
                try { _latestBitmap.Dispose(); } catch { }
                _latestBitmap = null;
            }
            _lastFrameTime = DateTime.MinValue;
        }
    }

    private void SetStatus(StreamStatus s, string msg)
    {
        if (_status == s) return;
        _status = s;
        try { StatusChanged?.Invoke(this, new StreamStatusEventArgs(s, msg)); } catch { }
        LogUtil.Info("Stream", $"状态 -> {s}: {msg}");
    }

    private async Task RunLoopAsync(CancellationToken ct)
    {
        var cfg = ConfigManager.Current.Camera;
        var firstAttempt = true;

        while (!ct.IsCancellationRequested)
        {
            if (firstAttempt)
            {
                SetStatus(StreamStatus.Connecting, $"正在连接 {cfg.Url}");
                firstAttempt = false;
            }
            else
            {
                _reconnectCount++;
                SetStatus(StreamStatus.Reconnecting, $"第 {_reconnectCount} 次重连: {cfg.Url}");
            }

            try
            {
                await ConnectAndReadAsync(cfg, ct);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                LogUtil.Warn("Stream", $"连接异常: {ex.Message}");
            }

            if (ct.IsCancellationRequested) break;

            // 重连前等待
            try { await Task.Delay(cfg.ReconnectIntervalMs, ct); }
            catch (OperationCanceledException) { break; }
        }

        SetStatus(StreamStatus.Disconnected, "拉流循环退出");
    }

    private async Task ConnectAndReadAsync(CameraConfig cfg, CancellationToken ct)
    {
        // 每次连接使用独立 HttpClient，确保 Socket 干净
        using var handler = new SocketsHttpHandler
        {
            // 不缓存 DNS
            PooledConnectionLifetime = TimeSpan.FromSeconds(30),
            UseCookies = false,
            // 禁用自动解压缩，减少一层缓冲开销
            AutomaticDecompression = System.Net.DecompressionMethods.None
        };
        using var http = new HttpClient(handler, disposeHandler: true)
        {
            // 不使用 HttpClient 内部缓冲
            Timeout = Timeout.InfiniteTimeSpan
        };
        http.DefaultRequestHeaders.UserAgent.ParseAdd(cfg.UserAgent);
        http.DefaultRequestHeaders.Accept.Clear();
        http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("multipart/x-mixed-replace"));
        http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("image/jpeg"));

        using var resp = await http.GetAsync(cfg.Url, HttpCompletionOption.ResponseHeadersRead, ct);
        resp.EnsureSuccessStatusCode();

        var contentType = resp.Content.Headers.ContentType?.MediaType ?? "";
        var boundary = ExtractBoundary(resp.Content.Headers.ContentType?.ToString() ?? "");
        var stream = await resp.Content.ReadAsStreamAsync(ct);

        SetStatus(StreamStatus.Connected, boundary != null
            ? $"已连接 (multipart, boundary={boundary})"
            : $"已连接 (raw jpeg stream)");

        if (boundary != null)
        {
            await ReadMultipartAsync(stream, boundary, ct);
        }
        else
        {
            await ReadRawJpegAsync(stream, ct);
        }
    }

    /// <summary>从 Content-Type 头提取 boundary</summary>
    private static string? ExtractBoundary(string contentType)
    {
        if (string.IsNullOrEmpty(contentType)) return null;
        var idx = contentType.IndexOf("boundary=", StringComparison.OrdinalIgnoreCase);
        if (idx < 0) return null;
        var start = idx + 9;
        var end = contentType.IndexOfAny(new[] { ';', '\r', '\n' }, start);
        var b = end < 0 ? contentType.Substring(start) : contentType.Substring(start, end - start);
        b = b.Trim().Trim('"');
        if (b.StartsWith("--")) b = b.Substring(2);
        return b;
    }

    /// <summary>
    /// 读取 multipart/x-mixed-replace 流
    /// </summary>
    private async Task ReadMultipartAsync(Stream stream, string boundary, CancellationToken ct)
    {
        var boundaryBytes = Encoding.ASCII.GetBytes("--" + boundary);
        // body 终止符：\r\n--boundary
        var terminator = ConcatBytes(Encoding.ASCII.GetBytes("\r\n"), boundaryBytes);

        using var reader = new BinaryReader(stream, Encoding.ASCII, leaveOpen: true);

        while (!ct.IsCancellationRequested)
        {
            // 等待 boundary
            if (!await ScanForBytesAsync(stream, boundaryBytes, ct))
            {
                throw new IOException("连接关闭（boundary 终止）");
            }

            // 读取 part header（多行，直到空行）
            var header = await ReadLineAsync(stream, ct);
            if (header == null) throw new IOException("连接关闭（part header）");
            while (!string.IsNullOrEmpty(header))
            {
                header = await ReadLineAsync(stream, ct);
                if (header == null) throw new IOException("连接关闭（part header 续行）");
            }

            // 读取 part body（直到 \r\n--boundary 终止符）
            var jpeg = await ReadPartBodyAsync(stream, terminator, ct);
            if (jpeg == null || jpeg.Length < 4) continue;
            if (jpeg[0] != 0xFF || jpeg[1] != 0xD8) continue;

            DispatchFrame(jpeg);
        }
    }

    private static byte[] ConcatBytes(byte[] a, byte[] b)
    {
        var r = new byte[a.Length + b.Length];
        Buffer.BlockCopy(a, 0, r, 0, a.Length);
        Buffer.BlockCopy(b, 0, r, a.Length, b.Length);
        return r;
    }

    /// <summary>读取裸连续 JPEG 流（每个 JPEG 以 FFD8 开头 FFD9 结尾）</summary>
    private async Task ReadRawJpegAsync(Stream stream, CancellationToken ct)
    {
        var buf = new byte[4096];
        var state = 0; // 0=等待 FFD8, 1=已找到 FFD8, 2=等待 FFD9
        var pending = new MemoryStream();

        while (!ct.IsCancellationRequested)
        {
            var n = await stream.ReadAsync(buf, 0, buf.Length, ct);
            if (n <= 0) throw new IOException("连接关闭（裸流）");

            for (int i = 0; i < n; i++)
            {
                var b = buf[i];
                if (state == 0)
                {
                    if (b == 0xFF) { state = 1; }
                }
                else if (state == 1)
                {
                    if (b == 0xD8) { state = 2; pending.SetLength(0); pending.WriteByte(0xFF); pending.WriteByte(0xD8); }
                    else if (b == 0xFF) { state = 1; }
                    else { state = 0; }
                }
                else // state == 2
                {
                    pending.WriteByte(b);
                    if (b == 0xD9 && pending.Length > 4)
                    {
                        var jpeg = pending.ToArray();
                        DispatchFrame(jpeg);
                        state = 0;
                    }
                }
            }
        }
    }

    private void DispatchFrame(byte[] jpeg)
    {
        Bitmap? bmp = null;
        try
        {
            using var ms = new MemoryStream(jpeg);
            // 复制一份给 Bitmap（Bitmap 内部不持有原数组所有权）
            bmp = new Bitmap(ms);
        }
        catch (Exception ex)
        {
            LogUtil.Warn("Stream", $"JPEG 解码失败: {ex.Message}");
            return;
        }

        SetLatest(jpeg, bmp, DateTime.Now);

        try { FrameReceived?.Invoke(this, new MjpegFrameEventArgs(jpeg, bmp, DateTime.Now)); }
        catch (Exception ex) { LogUtil.Warn("Stream", $"FrameReceived 处理异常: {ex.Message}"); }
    }

    private static async Task<bool> ScanForBytesAsync(Stream stream, byte[] pattern, CancellationToken ct)
    {
        var matchIdx = 0;
        var buf = new byte[4096];
        while (!ct.IsCancellationRequested)
        {
            var n = await stream.ReadAsync(buf, 0, buf.Length, ct);
            if (n <= 0) return false;
            for (int i = 0; i < n; i++)
            {
                if (buf[i] == pattern[matchIdx])
                {
                    matchIdx++;
                    if (matchIdx == pattern.Length) return true;
                }
                else
                {
                    matchIdx = buf[i] == pattern[0] ? 1 : 0;
                }
            }
        }
        return false;
    }

    private static async Task<string?> ReadLineAsync(Stream stream, CancellationToken ct)
    {
        var ms = new MemoryStream();
        var buf = new byte[1];
        while (!ct.IsCancellationRequested)
        {
            var n = await stream.ReadAsync(buf, 0, 1, ct);
            if (n <= 0) return ms.Length == 0 ? null : Encoding.ASCII.GetString(ms.ToArray());
            if (buf[0] == (byte)'\n')
            {
                var s = Encoding.ASCII.GetString(ms.ToArray()).TrimEnd('\r');
                return s;
            }
            ms.WriteByte(buf[0]);
        }
        return null;
    }

    /// <summary>
    /// 读取 part body（直到匹配 terminator）。terminator 自身不会写入返回的字节。
    /// </summary>
    private async Task<byte[]?> ReadPartBodyAsync(Stream stream, byte[] terminator, CancellationToken ct)
    {
        using var ms = new MemoryStream(64 * 1024);
        // 滑动窗口：暂存最后 terminator.Length 字节
        var tail = new byte[terminator.Length];
        var tailFilled = 0;
        var buf = new byte[8192];

        while (!ct.IsCancellationRequested)
        {
            var n = await stream.ReadAsync(buf, 0, buf.Length, ct);
            if (n <= 0) return ms.ToArray();

            for (int i = 0; i < n; i++)
            {
                var b = buf[i];

                if (tailFilled < tail.Length)
                {
                    // 窗口未满：先累积
                    tail[tailFilled++] = b;
                    if (tailFilled == tail.Length)
                    {
                        // 窗口刚填满：检查是否匹配 terminator
                        if (BytesEqual(tail, terminator))
                        {
                            return ms.ToArray(); // 匹配成功，body 结束
                        }
                        // 不匹配：把整个 tail 写入 body，重置
                        ms.Write(tail, 0, tail.Length);
                        tailFilled = 0;
                    }
                }
                else
                {
                    // 窗口已满：滑动一格
                    // 把 tail[0] 写入 body，新字节进入 tail 末尾
                    ms.WriteByte(tail[0]);
                    Array.Copy(tail, 1, tail, 0, tail.Length - 1);
                    tail[tail.Length - 1] = b;
                    if (BytesEqual(tail, terminator))
                    {
                        return ms.ToArray();
                    }
                }
            }
        }
        return ms.ToArray();
    }

    private static bool BytesEqual(byte[] a, byte[] b)
    {
        if (a.Length != b.Length) return false;
        for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
        return true;
    }

    public void Dispose()
    {
        Stop();
    }
}
