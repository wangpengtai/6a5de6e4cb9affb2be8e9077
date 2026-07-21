using System;
using System.Buffers.Binary;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace PackingMonitor;

/// <summary>
/// 极简 AVI MJPEG 录像写入器。
///
/// 直接保存从 MJPEG 流中拿到的 JPEG 字节，不重新编码（零 CPU 损失）。
/// 产物为标准 .avi 文件，Windows Media Player、PotPlayer、VLC 等均可直接播放。
///
/// 视频流：MJPG (Motion JPEG)，每帧一个 00dc chunk
/// 帧率：使用配置中的 fps（仅用于播放器呈现）
///
/// 文件布局：
///   RIFF (size) AVI
///     LIST hdrl
///       avih (Main AVI Header)
///       LIST strl
///         strh (Stream Header, vids MJPG)
///         strf (Stream Format, BITMAPINFOHEADER)
///     LIST movi
///       00dc (frame 1 jpeg bytes)
///       00dc (frame 2 jpeg bytes)
///       ...
///     idx1 (index chunk)
/// </summary>
public sealed class AviMjpegWriter : IDisposable
{
    private readonly FileStream _fs;
    private readonly long _moviStartOffset;     // "movi" 之后（即第一个 00dc 起始）
    private readonly long _riffSizePos;         // RIFF size 字段位置
    private readonly long _hdrlSizePos;         // LIST hdrl size 字段位置
    private readonly long _strlSizePos;         // LIST strl size 字段位置
    private readonly long _moviSizePos;         // LIST movi size 字段位置
    private readonly long _avihTotalFramesPos;  // avih 中 dwTotalFrames 位置
    private readonly long _strhLengthPos;       // strh 中 dwLength 位置
    private readonly List<IndexEntry> _index = new();
    private int _frameCount;
    private bool _disposed;

    private readonly int _width;
    private readonly int _height;
    private readonly int _fps;
    private uint WidthU => (uint)_width;
    private uint HeightU => (uint)_height;
    private uint FpsU => (uint)_fps;

    private struct IndexEntry
    {
        public uint Offset;   // 相对于 movi 起始（不含 'movi' 类型本身）
        public uint Size;
    }

    /// <summary>
    /// 创建分段录像文件
    /// </summary>
    /// <param name="path">输出文件路径（.avi）</param>
    /// <param name="width">视频宽度（首帧决定）</param>
    /// <param name="height">视频高度</param>
    /// <param name="fps">帧率（影响播放器呈现）</param>
    public AviMjpegWriter(string path, int width, int height, int fps)
    {
        _width = width;
        _height = height;
        _fps = Math.Max(1, fps);

        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        _fs = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.Read, 65536);

        // 关键偏移（写入过程中同步记录，避免 Close 阶段重新计算）：
        // 0: RIFF 字符串 (4)
        // 4: RIFF size (4)      <- _riffSizePos
        // 8: "AVI " (4)
        // 12: "LIST" (4)
        // 16: hdrl size (4)     <- _hdrlSizePos
        // 20: "hdrl" (4)
        // 24: "avih" (4)
        // 28: avih size (4) (固定 56)
        // 32: avih data start
        // 32:  dwMicroSecPerFrame (4)
        // 36:  dwMaxBytesPerSec (4)
        // 40:  dwPaddingGranularity (4)
        // 44:  dwFlags (4)
        // 48:  dwTotalFrames (4) <- _avihTotalFramesPos
        // 52:  dwInitialFrames (4)
        // ...
        // 88: "LIST" (4)
        // 92: strl size (4)     <- _strlSizePos
        // 96: "strl" (4)
        // 100: "strh" (4)
        // 104: strh size (4) (固定 56)
        // 108: strh data start
        // 108: fccType (4)
        // 112: fccHandler (4)
        // 116: dwFlags (4)
        // 120: wPriority (2)
        // 122: wLanguage (2)
        // 124: dwInitialFrames (4)
        // 128: dwScale (4)
        // 132: dwRate (4)
        // 136: dwStart (4)
        // 140: dwLength (4)     <- _strhLengthPos
        // 144: dwSuggestedBufferSize (4)
        // ...
        // 164: "strf" (4)
        // 168: strf size (4) (固定 40)
        // 172: BITMAPINFOHEADER (40)
        // 212: "LIST" (4)
        // 216: movi size (4)    <- _moviSizePos
        // 220: "movi" (4)
        // 224: 第一个 00dc (后续每帧)
        _riffSizePos = 4;
        _hdrlSizePos = 16;
        _strlSizePos = 92;
        _avihTotalFramesPos = 48;
        _strhLengthPos = 140;

        // RIFF 头
        WriteAscii(_fs, "RIFF");
        WriteUInt32(_fs, 0); // RIFF size，最后回填
        WriteAscii(_fs, "AVI ");

        // LIST hdrl
        WriteAscii(_fs, "LIST");
        WriteUInt32(_fs, 0); // hdrl size
        WriteAscii(_fs, "hdrl");

        // avih (56 字节)
        WriteAscii(_fs, "avih");
        WriteUInt32(_fs, 56);
        WriteUInt32(_fs, (uint)(1000000 / _fps)); // dwMicroSecPerFrame
        WriteUInt32(_fs, 0);  // dwMaxBytesPerSec
        WriteUInt32(_fs, 0);  // dwPaddingGranularity
        WriteUInt32(_fs, 0x10); // dwFlags: AVIF_HASINDEX
        WriteUInt32(_fs, 0);  // dwTotalFrames (回填)
        WriteUInt32(_fs, 0);  // dwInitialFrames
        WriteUInt32(_fs, 1);  // dwStreams
        WriteUInt32(_fs, 0);  // dwSuggestedBufferSize
        WriteUInt32(_fs, WidthU);  // dwWidth
        WriteUInt32(_fs, HeightU); // dwHeight
        WriteUInt32(_fs, 0); WriteUInt32(_fs, 0); WriteUInt32(_fs, 0); WriteUInt32(_fs, 0); // dwReserved

        // LIST strl
        WriteAscii(_fs, "LIST");
        WriteUInt32(_fs, 0); // strl size
        WriteAscii(_fs, "strl");

        // strh (56 字节)
        WriteAscii(_fs, "strh");
        WriteUInt32(_fs, 56);
        WriteAscii(_fs, "vids");
        WriteAscii(_fs, "MJPG");
        WriteUInt32(_fs, 0);  // dwFlags
        WriteUInt16(_fs, 0);  // wPriority
        WriteUInt16(_fs, 0);  // wLanguage
        WriteUInt32(_fs, 0);  // dwInitialFrames
        WriteUInt32(_fs, 1);  // dwScale
        WriteUInt32(_fs, FpsU); // dwRate
        WriteUInt32(_fs, 0);  // dwStart
        WriteUInt32(_fs, 0);  // dwLength (回填)
        WriteUInt32(_fs, 0);  // dwSuggestedBufferSize
        WriteUInt32(_fs, 0);  // dwQuality
        WriteUInt32(_fs, 0);  // dwSampleSize
        WriteUInt16(_fs, 0);  // rcFrame left
        WriteUInt16(_fs, 0);  // rcFrame top
        WriteUInt16(_fs, (ushort)_width);
        WriteUInt16(_fs, (ushort)_height);

        // strf (BITMAPINFOHEADER, 40 字节)
        WriteAscii(_fs, "strf");
        WriteUInt32(_fs, 40);
        WriteUInt32(_fs, 40); // biSize
        WriteInt32(_fs, _width);
        WriteInt32(_fs, _height);
        WriteUInt16(_fs, 1);  // biPlanes
        WriteUInt16(_fs, 24); // biBitCount
        WriteAscii(_fs, "MJPG"); // biCompression
        WriteUInt32(_fs, WidthU * HeightU * 3); // biSizeImage
        WriteInt32(_fs, 0); WriteInt32(_fs, 0); WriteUInt32(_fs, 0); WriteUInt32(_fs, 0);

        // 修正 strl size = (当前位置 - strl size 字段 - 4)
        var strlEnd = _fs.Position;
        BackPatchUInt32(_strlSizePos, (uint)(strlEnd - _strlSizePos - 4));

        // 修正 hdrl size
        var hdrlEnd = _fs.Position;
        BackPatchUInt32(_hdrlSizePos, (uint)(hdrlEnd - _hdrlSizePos - 4));

        // LIST movi
        WriteAscii(_fs, "LIST");
        _moviSizePos = _fs.Position;
        WriteUInt32(_fs, 0);
        WriteAscii(_fs, "movi");

        _moviStartOffset = _fs.Position;
    }

    /// <summary>写入一帧（直接使用 JPEG 字节，零重新编码）</summary>
    public void WriteFrame(byte[] jpegBytes)
    {
        if (_disposed) throw new ObjectDisposedException(nameof(AviMjpegWriter));
        if (jpegBytes == null || jpegBytes.Length == 0) return;

        var offsetInMovi = (uint)(_fs.Position - _moviStartOffset);

        // 00dc chunk
        WriteAscii(_fs, "00dc");
        WriteUInt32(_fs, (uint)jpegBytes.Length);
        _fs.Write(jpegBytes, 0, jpegBytes.Length);
        // RIFF 偶数对齐
        if (jpegBytes.Length % 2 == 1) _fs.WriteByte(0);

        _index.Add(new IndexEntry { Offset = offsetInMovi, Size = (uint)jpegBytes.Length });
        _frameCount++;
    }

    /// <summary>关闭并写回索引、总帧数等元数据</summary>
    public void Close()
    {
        if (_disposed) return;
        _disposed = true;

        var moviContentEnd = _fs.Position; // 最后一个 00dc 之后的位置

        // idx1 chunk（顶级 RIFF 内独立 chunk，不在 movi LIST 内）
        WriteAscii(_fs, "idx1");
        WriteUInt32(_fs, (uint)(_index.Count * 16));
        foreach (var e in _index)
        {
            WriteAscii(_fs, "00dc");
            WriteUInt32(_fs, 0x10); // dwFlags: AVIIF_KEYFRAME
            WriteUInt32(_fs, e.Offset);
            WriteUInt32(_fs, e.Size);
        }

        // 修正 LIST 'movi' size
        // LIST 块 size 字段 = "movi"(4) + 内容字节
        var moviContentBytes = moviContentEnd - _moviStartOffset;
        BackPatchUInt32(_moviSizePos, (uint)(moviContentBytes + 4));

        // 修正 RIFF 整个文件 size（不含 RIFF 头 8 字节）
        BackPatchUInt32(_riffSizePos, (uint)(_fs.Length - 8));

        // 修正 avih 中的 dwTotalFrames
        BackPatchUInt32(_avihTotalFramesPos, (uint)_frameCount);

        // 修正 strh 中的 dwLength
        BackPatchUInt32(_strhLengthPos, (uint)_frameCount);

        _fs.Flush();
        _fs.Close();
    }

    public int FrameCount => _frameCount;

    public void Dispose()
    {
        if (!_disposed) Close();
        try { _fs.Dispose(); } catch { }
    }

    // ---- IO 工具 ----
    private static void WriteAscii(FileStream fs, string s)
    {
        var bytes = Encoding.ASCII.GetBytes(s);
        fs.Write(bytes, 0, bytes.Length);
    }
    private static void WriteUInt32(FileStream fs, uint v)
    {
        Span<byte> buf = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32LittleEndian(buf, v);
        fs.Write(buf);
    }
    private static void WriteUInt32(FileStream fs, int v)
    {
        if (v < 0) v = 0;
        Span<byte> buf = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32LittleEndian(buf, (uint)v);
        fs.Write(buf);
    }
    private static void WriteInt32(FileStream fs, int v)
    {
        Span<byte> buf = stackalloc byte[4];
        BinaryPrimitives.WriteInt32LittleEndian(buf, v);
        fs.Write(buf);
    }
    private static void WriteUInt16(FileStream fs, ushort v)
    {
        Span<byte> buf = stackalloc byte[2];
        BinaryPrimitives.WriteUInt16LittleEndian(buf, v);
        fs.Write(buf);
    }
    private void BackPatchUInt32(long pos, uint v)
    {
        var old = _fs.Position;
        _fs.Position = pos;
        WriteUInt32(_fs, v);
        _fs.Position = old;
    }
}
