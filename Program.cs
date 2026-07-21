using System;
using System.IO;
using System.Windows.Forms;

namespace PackingMonitor;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        // 单实例锁，避免重复打开
        using var mutex = new System.Threading.Mutex(true, "PackingMonitor_SingleInstance", out var createdNew);
        if (!createdNew)
        {
            MessageBox.Show("程序已经在运行中，请勿重复打开。", "提示",
                MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
            LogUtil.Error("未捕获异常", "全局未处理异常", e.ExceptionObject as Exception);

        ApplicationConfiguration.Initialize();
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (_, e) =>
            LogUtil.Error("UI 线程异常", "UI 线程未处理异常", e.Exception);

        Application.Run(new MainForm());
    }
}
