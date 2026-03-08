# M3U8-Downloader (English)

[中文](README.zh-CN.md) | [日本語](README.ja.md)

[Download Latest Release (Tag)](https://github.com/lengziyu/m3u8-downloader/releases/latest)

## Features

- Cross-platform desktop client for Windows 10/11 and macOS
- Batch download `m3u8` to `mp4`
- Single-input mode + batch-text mode
- Output folder / concurrency / retry settings
- Per-task progress, pause/resume, delete
- Add new tasks while downloading
- Auto-export failed tasks to `failed_tasks_*.txt`
- Update check (Release first, Tag fallback)
- UI language switch: Chinese / English / Japanese (default: Chinese)
- Works with the Chrome extension [`m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension)

## Chrome Extension Workflow

Companion extension repository:

- [`https://github.com/lengziyu/m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension)

Basic flow:

1. Launch `M3U8-Downloader` first.
2. Install and enable the Chrome extension `m3u8-chrome-extension`.
3. Open a supported page. The first MVP mainly targets `missav.ws` video detail pages.
4. Let the extension detect `playlist.m3u8` and available resolutions.
5. Click the add button in the extension to send the selected task to the desktop client.

Local desktop API used by the extension:

- `GET http://127.0.0.1:38427/ping`
- `POST http://127.0.0.1:38427/open-window`
- `POST http://127.0.0.1:38427/add-task`

Filename notes:

- The extension can pass `filename_hint`; the desktop client will prefer it as the output name.
- If `filename_hint` is missing, the client falls back to `title`.
- If the extension reports the desktop app as offline, make sure this app is already running.

## Run

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

## Build

Windows build:

```bat
scripts\build_windows.bat
```

macOS build:

```bash
./scripts/build_mac.sh
```

Installer build:

- Windows: `scripts\build_windows_installer.bat`
- macOS: `./scripts/build_mac_installer.sh`

## Auto Release

Push a `v*` tag to trigger GitHub Actions release workflow:

```bash
git tag v1.0.11
git push github v1.0.11
```
