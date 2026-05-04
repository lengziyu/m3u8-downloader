# Taoying (English)

[中文](README.zh-CN.md) | [日本語](README.ja.md)

[Download Latest Release](https://github.com/lengziyu/m3u8-downloader/releases/latest)

`Taoying` is a compact desktop client for downloading `m3u8` videos to `mp4`, validating outputs after download, and repairing broken video files when needed.

## Features

- Desktop client for Windows 10/11 and macOS
- Single-link and batch `m3u8` input
- Post-download validation to avoid broken MP4 files
- Built-in video repair page for remux/transcode recovery
- Sidebar layout with Download, Directory, Repair, and Settings pages
- Light/dark theme and Chinese / English / Japanese UI
- Works with the Chrome extension [`m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension)

## Quick Start

```bash
python -m pip install -r requirements.txt
python m3u8_gui.py
```

On Windows:

```bat
scripts\run_windows.bat
```

## Chrome Extension Flow

1. Launch `Taoying` first
2. Install and enable `m3u8-chrome-extension`
3. Detect a supported `playlist.m3u8`
4. Send the task to the desktop client from the extension
