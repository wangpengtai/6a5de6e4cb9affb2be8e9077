using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace PackingMonitor;

/// <summary>
/// Ollama 本地多模态模型调用封装（默认关闭状态）。
///
/// 协议：Ollama /api/generate 支持多模态，传入 prompt + images(base64) 字段。
/// 我们把监控画面每 N 秒抓一帧（base64 编码后）发到本地 Ollama。
/// 返回的 response 文本显示在 UI 日志 + 写入本地日志文件。
///
/// 所有异常仅记录日志，绝不影响主监控、录像流程。
/// </summary>
public sealed class OllamaAnalyzer : IDisposable
{
    private CancellationTokenSource? _cts;
    private Task? _loopTask;
    private readonly HttpClient _http;
    private string? _logFilePath;
    private bool _disposed;
    private DateTime _nextSchedule = DateTime.MinValue;

    public event EventHandler<string>? Analyzed;

    public bool IsRunning => _loopTask != null && !_loopTask.IsCompleted;

    public OllamaAnalyzer()
    {
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(60) };
    }

    public void Start()
    {
        if (IsRunning) return;
        if (!ConfigManager.Current.Ai.Enabled)
        {
            LogUtil.Info("AI", "AI 模块在配置中处于关闭状态，跳过启动");
            return;
        }

        _logFilePath = Path.Combine(AppContext.BaseDirectory, "logs",
            $"ai-{DateTime.Now:yyyyMMdd}.log");
        try { Directory.CreateDirectory(Path.GetDirectoryName(_logFilePath)!); } catch { }

        _cts = new CancellationTokenSource();
        _loopTask = Task.Run(() => RunLoopAsync(_cts.Token));
    }

    public void Stop()
    {
        try { _cts?.Cancel(); } catch { }
        try { _loopTask?.Wait(2000); } catch { }
        _cts?.Dispose();
        _cts = null;
        _loopTask = null;
    }

    private async Task RunLoopAsync(CancellationToken ct)
    {
        var cfg = ConfigManager.Current.Ai;
        LogUtil.Info("AI", $"AI 已启动 -> {cfg.OllamaUrl}, model={cfg.Model}, interval={cfg.IntervalSeconds}s");

        while (!ct.IsCancellationRequested)
        {
            try
            {
                if (DateTime.Now < _nextSchedule)
                {
                    await Task.Delay(500, ct);
                    continue;
                }

                if (MjpegFrameBus.TryGetLatest(out var jpeg, out var ts))
                {
                    await AnalyzeOneAsync(jpeg!, ts, ct);
                }

                _nextSchedule = DateTime.Now.AddSeconds(Math.Max(1, cfg.IntervalSeconds));
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                LogUtil.Warn("AI", $"AI 循环异常（不影响主程序）: {ex.Message}");
                // 退避 5 秒
                try { await Task.Delay(5000, ct); } catch { }
            }
        }

        LogUtil.Info("AI", "AI 循环退出");
    }

    private async Task AnalyzeOneAsync(byte[] jpeg, DateTime ts, CancellationToken ct)
    {
        var cfg = ConfigManager.Current.Ai;
        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeoutCts.CancelAfter(TimeSpan.FromSeconds(cfg.TimeoutSeconds));

        try
        {
            var prompt = "你是一个电商打包工位监控助手。请用中文简洁描述当前画面正在发生什么（最多 80 字）。如有明显异常（人离开、货物倒塌、火焰等），请以 ⚠ 开头标注。";
            var payload = new
            {
                model = cfg.Model,
                prompt,
                images = new[] { Convert.ToBase64String(jpeg) },
                stream = false
            };
            var json = JsonSerializer.Serialize(payload);

            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            using var resp = await _http.PostAsync(cfg.OllamaUrl, content, timeoutCts.Token);
            var text = await resp.Content.ReadAsStringAsync(timeoutCts.Token);

            if (!resp.IsSuccessStatusCode)
            {
                LogUtil.Warn("AI", $"Ollama 返回 {(int)resp.StatusCode}: {Truncate(text, 200)}");
                return;
            }

            string? reply = ExtractResponseField(text);
            if (string.IsNullOrWhiteSpace(reply)) reply = text;

            var line = $"[{ts:HH:mm:ss}] {reply}";
            LogUtil.Info("AI", line);
            AppendToLog(line);
            try { Analyzed?.Invoke(this, line); } catch { }
        }
        catch (TaskCanceledException) { LogUtil.Warn("AI", "Ollama 请求超时"); }
        catch (HttpRequestException ex) { LogUtil.Warn("AI", $"Ollama 连接失败（监控功能正常）: {ex.Message}"); }
        catch (Exception ex) { LogUtil.Warn("AI", $"Ollama 调用异常: {ex.Message}"); }
    }

    private static string? ExtractResponseField(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("response", out var r))
                return r.GetString();
        }
        catch { }
        return null;
    }

    private void AppendToLog(string line)
    {
        if (string.IsNullOrEmpty(_logFilePath)) return;
        try { File.AppendAllText(_logFilePath, line + Environment.NewLine, Encoding.UTF8); } catch { }
    }

    private static string Truncate(string s, int n) => s.Length <= n ? s : s.Substring(0, n) + "...";

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        Stop();
        try { _http.Dispose(); } catch { }
    }
}

/// <summary>
/// 全局帧总线：拉流模块将最新帧写入，AI 模块按需读取。
/// 两者解耦：拉流不依赖 AI，AI 不阻塞拉流。
/// </summary>
public static class MjpegFrameBus
{
    private static byte[]? _jpeg;
    private static DateTime _ts = DateTime.MinValue;
    private static readonly object _lock = new();

    public static void Publish(byte[] jpeg, DateTime ts)
    {
        lock (_lock) { _jpeg = jpeg; _ts = ts; }
    }

    public static bool TryGetLatest(out byte[]? jpeg, out DateTime ts)
    {
        lock (_lock) { jpeg = _jpeg; ts = _ts; return jpeg != null; }
    }
}