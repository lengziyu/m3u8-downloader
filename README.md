# 桃影

[中文](README.zh-CN.md) | [English](README.en.md) | [日本語](README.ja.md)

[![Download Latest Release](https://img.shields.io/badge/Download-Latest%20Release-FF385C?style=for-the-badge)](https://github.com/lengziyu/m3u8-downloader/releases/latest)

`桃影` 是一个简洁的桌面客户端，用来批量下载 `m3u8` 视频、输出为 `mp4`，并在下载后自动校验文件；如果遇到个别元数据异常的视频，也可以直接在客户端里修复。

## 功能

- Windows 10/11、macOS 桌面客户端
- 单条输入与批量输入 `m3u8` 链接
- 下载完成后自动校验，尽量避免生成无法播放的坏文件
- 内置“修复视频”功能，可对异常 MP4 重封装或转码修复
- 左侧菜单式界面：下载、目录、修复视频、设置
- 支持浅色 / 深色主题与中英日界面切换
- 支持与 Chrome 扩展 [`m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension) 联动

## 快速开始

```bash
python -m pip install -r requirements.txt
python m3u8_gui.py
```

Windows 也可以直接使用：

```bat
scripts\run_windows.bat
```

## Chrome 扩展联动

1. 先启动桌面客户端 `桃影`
2. 在 Chrome 中安装并启用 `m3u8-chrome-extension`
3. 打开支持的页面，识别 `playlist.m3u8`
4. 点击扩展中的添加下载，即可把任务发送到桌面客户端

本地接口：

- `GET http://127.0.0.1:38427/ping`
- `POST http://127.0.0.1:38427/open-window`
- `POST http://127.0.0.1:38427/add-task`

## 发布

- 最新版本：[Releases Latest](https://github.com/lengziyu/m3u8-downloader/releases/latest)
