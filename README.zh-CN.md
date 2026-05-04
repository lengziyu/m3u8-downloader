# 桃影（中文）

[English](README.en.md) | [日本語](README.ja.md)

[下载最新版本（Tag）](https://github.com/lengziyu/m3u8-downloader/releases/latest)

`桃影` 是一个面向桌面的 `m3u8` 下载与修复客户端，主打简洁界面、稳定下载和坏文件修复。

## 功能

- Windows 10/11、macOS 图形界面
- `m3u8` 批量下载并输出 `mp4`
- 单条输入与批量文本输入
- 下载目录、并发、重试统一管理
- 任务级进度、暂停、继续、删除
- 下载后自动校验，尽量避免无时长、无法播放的异常视频
- 内置视频修复页，可对损坏 MP4 做重封装或转码修复
- 中 / 英 / 日界面切换
- 支持 Chrome 扩展 [`m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension)

## 使用

```bash
python -m pip install -r requirements.txt
python m3u8_gui.py
```

Windows：

```bat
scripts\run_windows.bat
```

## 扩展联动

1. 先启动桌面客户端 `桃影`
2. 安装并启用 Chrome 扩展 `m3u8-chrome-extension`
3. 打开支持页面并识别 `playlist.m3u8`
4. 点击“添加到下载器”后，任务会发送到本地客户端

本地接口：

- `GET http://127.0.0.1:38427/ping`
- `POST http://127.0.0.1:38427/open-window`
- `POST http://127.0.0.1:38427/add-task`
