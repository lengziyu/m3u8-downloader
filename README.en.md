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
git tag v1.0.8
git push github v1.0.8
```
