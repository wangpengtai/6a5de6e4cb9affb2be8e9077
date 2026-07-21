using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PackingMonitor;

/// <summary>
/// 外置 JSON 配置。所有运行参数（摄像头地址、录像路径、AI 配置）均通过此文件修改，
/// 无需重新编译。配置文件位于 exe 同目录 config.json。
/// </summary>
public sealed class AppConfig
{
    [JsonPropertyName("camera")]
    public CameraConfig Camera { get; set; } = new();

    [JsonPropertyName("record")]
    public RecordConfig Record { get; set; } = new();

    [JsonPropertyName("storage")]
    public StorageConfig Storage { get; set; } = new();

    [JsonPropertyName("ai")]
    public AiConfig Ai { get; set; } = new();
}

public sealed class CameraConfig
{
    /// <summary>IP Webcam HTTP MJPEG 地址，例 http://192.168.1.100:8080/videofeed</summary>
    [JsonPropertyName("url")]
    public string Url { get; set; } = "http://192.168.1.100:8080/videofeed";

    /// <summary>网络断开后重连间隔（毫秒）</summary>
    [JsonPropertyName("reconnectIntervalMs")]
    public int ReconnectIntervalMs { get; set; } = 1000;

    /// <summary>网络断开多久算作"已断开"，单位毫秒</summary>
    [JsonPropertyName("networkTimeoutMs")]
    public int NetworkTimeoutMs { get; set; } = 3000;

    /// <summary>用户代理字符串，避免被部分摄像头拒绝</summary>
    [JsonPropertyName("userAgent")]
    public string UserAgent { get; set; } = "PackingMonitor/1.0";
}

public sealed class RecordConfig
{
    /// <summary>是否默认开启录像</summary>
    [JsonPropertyName("autoStart")]
    public bool AutoStart { get; set; } = false;

    /// <summary>单段录像时长（秒）</summary>
    [JsonPropertyName("segmentSeconds")]
    public int SegmentSeconds { get; set; } = 600; // 默认 10 分钟

    /// <summary>录像帧率（用于 AVI 头，不影响实际帧间隔）</summary>
    [JsonPropertyName("fps")]
    public int Fps { get; set; } = 15;
}

public sealed class StorageConfig
{
    /// <summary>录像保存目录（绝对路径，留空则使用 exe 同目录 recordings）</summary>
    [JsonPropertyName("recordDir")]
    public string RecordDir { get; set; } = "";

    /// <summary>截图保存目录（绝对路径，留空则使用 exe 同目录 screenshots）</summary>
    [JsonPropertyName("screenshotDir")]
    public string ScreenshotDir { get; set; } = "";

    /// <summary>磁盘剩余空间阈值（MB），低于此值时删除最早录像</summary>
    [JsonPropertyName("minFreeSpaceMB")]
    public long MinFreeSpaceMB { get; set; } = 1024; // 1GB
}

public sealed class AiConfig
{
    /// <summary>AI 总开关（默认关闭，关闭时不加载任何 AI 代码/资源）</summary>
    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; } = false;

    /// <summary>Ollama 本地服务地址，例 http://127.0.0.1:11434/api/generate</summary>
    [JsonPropertyName("ollamaUrl")]
    public string OllamaUrl { get; set; } = "http://127.0.0.1:11434/api/generate";

    /// <summary>多模态模型名称，例 llama3.2-vision、llava、minicpm-v</summary>
    [JsonPropertyName("model")]
    public string Model { get; set; } = "llama3.2-vision";

    /// <summary>画面分析间隔（秒），每隔 N 秒截取一帧分析</summary>
    [JsonPropertyName("intervalSeconds")]
    public int IntervalSeconds { get; set; } = 10;

    /// <summary>请求超时（秒）</summary>
    [JsonPropertyName("timeoutSeconds")]
    public int TimeoutSeconds { get; set; } = 30;
}

/// <summary>
/// 配置读写器。线程安全。文件不存在时自动生成默认值。
/// </summary>
public static class ConfigManager
{
    private static readonly object _lock = new();
    private static AppConfig? _current;
    private static string? _configPath;

    public static string ConfigPath
    {
        get
        {
            if (_configPath == null)
            {
                _configPath = Path.Combine(AppContext.BaseDirectory, "config.json");
            }
            return _configPath;
        }
    }

    public static AppConfig Current
    {
        get
        {
            if (_current == null)
            {
                lock (_lock) { _current ??= Load(); }
            }
            return _current!;
        }
    }

    public static AppConfig Load()
    {
        try
        {
            if (File.Exists(ConfigPath))
            {
                var json = File.ReadAllText(ConfigPath);
                var cfg = JsonSerializer.Deserialize<AppConfig>(json, GetOptions());
                if (cfg != null) return cfg;
            }
        }
        catch (Exception ex)
        {
            LogUtil.Error("Config", $"读取 config.json 失败，使用默认值: {ex.Message}");
        }

        var defaultCfg = new AppConfig();
        Save(defaultCfg);
        return defaultCfg;
    }

    public static void Save(AppConfig cfg)
    {
        try
        {
            var json = JsonSerializer.Serialize(cfg, GetOptions());
            File.WriteAllText(ConfigPath, json);
            _current = cfg;
            LogUtil.Info("Config", $"配置已保存 -> {ConfigPath}");
        }
        catch (Exception ex)
        {
            LogUtil.Error("Config", $"保存 config.json 失败: {ex.Message}");
        }
    }

    public static void Reload()
    {
        lock (_lock) { _current = Load(); }
    }

    private static JsonSerializerOptions GetOptions() => new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never
    };

    /// <summary>解析路径：相对路径视为 exe 同目录</summary>
    public static string ResolveDir(string path)
    {
        if (string.IsNullOrWhiteSpace(path)) return AppContext.BaseDirectory;
        return Path.IsPathRooted(path) ? path : Path.Combine(AppContext.BaseDirectory, path);
    }
}
