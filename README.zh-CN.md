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
- 支持与 Chrome 扩展 [`m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension) 联动添加任务

## 扩展联动使用

配套扩展仓库：

- [`https://github.com/lengziyu/m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension)

使用步骤：

1. 先启动桌面客户端 `M3U8-Downloader`。
2. 安装并启用 Chrome 扩展 `m3u8-chrome-extension`。
3. 打开支持的页面，当前第一版主要对接 `missav.ws` 视频详情页。
4. 扩展识别到 `playlist.m3u8` 后，可在扩展中选择分辨率。
5. 点击“添加到下载器”后，任务会发送到本地客户端队列中。

桌面端提供的本地接口：

- `GET http://127.0.0.1:38427/ping`
- `POST http://127.0.0.1:38427/open-window`
- `POST http://127.0.0.1:38427/add-task`

文件名传递说明：

- 扩展可以传 `filename_hint`，客户端会优先用它作为输出文件名。
- 如果没有 `filename_hint`，客户端会回退使用 `title`。
- 如果扩展提示桌面端不在线，请先确认本软件已经启动。

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
git tag v1.0.11
git push github v1.0.11
```
