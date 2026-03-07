# M3U8-Downloader

[中文](README.zh-CN.md) | [English](README.en.md) | [日本語](README.ja.md)

[![Download Latest Release](https://img.shields.io/badge/Download-Latest%20Release-8A5BFF?style=for-the-badge)](https://github.com/lengziyu/m3u8-downloader/releases/latest)

![Main UI](docs/screenshots/main-ui.png)

## 快速说明

- 跨平台桌面客户端：Windows 10/11、macOS
- 批量下载 `m3u8` 并输出 `mp4`
- 支持任务进度、暂停/继续、失败任务导出
- 支持主题切换与中/英/日界面语言切换（默认中文）
- 可与 Chrome 扩展 [`m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension) 联动，将页面中的 `m3u8` 任务直接发送到桌面端

## 文档

- 中文文档: [README.zh-CN.md](README.zh-CN.md)
- English docs: [README.en.md](README.en.md)
- 日本語ドキュメント: [README.ja.md](README.ja.md)

## 下载

- 最新版本（跳转到最新 tag 发布页）: [Releases Latest](https://github.com/lengziyu/m3u8-downloader/releases/latest)

## 扩展联动

配套 Chrome 扩展项目：

- [`lengziyu/m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension)

基本使用顺序：

1. 先启动 `M3U8-Downloader` 桌面客户端。
2. 在 Chrome 中安装并启用 `m3u8-chrome-extension`。
3. 打开支持的页面（当前第一版主要对接 `missav.ws` 详情页）。
4. 在扩展里识别 `playlist.m3u8` 和可选分辨率。
5. 点击加入下载器后，扩展会调用本地接口把任务发到桌面端。

桌面端本地接口：

- `GET http://127.0.0.1:38427/ping`
- `POST http://127.0.0.1:38427/open-window`
- `POST http://127.0.0.1:38427/add-task`

说明：

- 如果扩展提示桌面端离线，请先确认本客户端已经启动。
- 如果需要用浏览器标题作为文件名，扩展应传 `filename_hint` 或 `title` 给 `/add-task`。
