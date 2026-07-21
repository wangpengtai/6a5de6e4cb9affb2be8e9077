using System;
using System.IO;
using System.Text;

namespace PackingMonitor;

/// <summary>
/// 简易日志工具：本地文件 + 控制台双通道。AI 模块、摄像头模块、录像模块统一调用。
/// 日志文件：exe 同目录 logs/yyyy-MM-dd.log
/// </summary>
internal static class LogUtil
{
    private static readonly object _lock = new();
    private static string? _logDir;

    public static void Init(string baseDir)
    {
        _logDir = Path.Combine(baseDir, "logs");
        try { Directory.CreateDirectory(_logDir); } catch { /* ignore */ }
    }

    private static string GetLogFile()
    {
        if (string.IsNullOrEmpty(_logDir))
            _logDir = Path.Combine(AppContext.BaseDirectory, "logs");
        try { Directory.CreateDirectory(_logDir); } catch { }
        return Path.Combine(_logDir, DateTime.Now.ToString("yyyy-MM-dd") + ".log");
    }

    public static void Info(string tag, string msg)
        => Write("INFO", tag, msg, null);

    public static void Warn(string tag, string msg, Exception? ex = null)
        => Write("WARN", tag, msg, ex);

    public static void Error(string tag, string msg, Exception? ex = null)
        => Write("ERROR", tag, msg, ex);

    private static void Write(string level, string tag, string msg, Exception? ex)
    {
        var line = $"[{DateTime.Now:HH:mm:ss.fff}] [{level}] [{tag}] {msg}";
        if (ex != null) line += Environment.NewLine + ex;

        try
        {
            lock (_lock)
            {
                File.AppendAllText(GetLogFile(), line + Environment.NewLine, Encoding.UTF8);
            }
        }
        catch { /* ignore disk error */ }

        Console.WriteLine(line);
    }
}
