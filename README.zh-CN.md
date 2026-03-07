# M3U8-Downloader（中文）

[English](README.en.md) | [日本語](README.ja.md)

[下载最新版本（Tag）](https://github.com/lengziyu/m3u8-downloader/releases/latest)

## 功能

- Windows 10/11、macOS 跨平台 GUI
- m3u8 批量下载为 mp4
- 逐条输入 + 批量文本输入
- 下载目录、并发、重试设置
- 任务级进度、暂停/继续、删除
- 支持下载中继续追加任务
- 失败任务自动导出 `failed_tasks_*.txt`
- 版本检测（Release 优先，Tag 回退）
- 语言切换：中文 / English / 日本語（默认中文）

## 运行

```bash
python -m pip install -r requirements.txt
```

Windows:

```bat
scripts\run_windows.bat
```

macOS:

```bash
./scripts/run_mac.sh
```

## 构建

Windows 一键产物：

```bat
scripts\build_windows.bat
```

macOS 一键产物：

```bash
./scripts/build_mac.sh
```

安装器：

- Windows: `scripts\build_windows_installer.bat`
- macOS: `./scripts/build_mac_installer.sh`

## 自动发布

推送 `v*` 标签会触发 GitHub Actions 自动构建并发布到 Releases。

```bash
git tag v1.0.8
git push github v1.0.8
```
