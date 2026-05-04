# 桃影（日本語）

[中文](README.zh-CN.md) | [English](README.en.md)

[最新リリース](https://github.com/lengziyu/m3u8-downloader/releases/latest)

`桃影` は、`m3u8` 動画を `mp4` として保存し、ダウンロード後の検証や壊れた動画の修復まで行えるデスクトップクライアントです。

## 機能

- Windows 10/11、macOS 対応
- 単体入力と一括入力の両方に対応
- ダウンロード後に自動検証
- 壊れた MP4 を修復する専用ページ
- 左側メニュー式 UI
- ライト / ダークテーマ
- 中国語 / 英語 / 日本語 UI
- Chrome 拡張 [`m3u8-chrome-extension`](https://github.com/lengziyu/m3u8-chrome-extension) と連携可能

## 使い方

```bash
python -m pip install -r requirements.txt
python m3u8_gui.py
```

Windows:

```bat
scripts\run_windows.bat
```

## 拡張連携

1. 先に `桃影` を起動します
2. `m3u8-chrome-extension` を有効化します
3. 対応ページで `playlist.m3u8` を検出します
4. 拡張からデスクトップクライアントへ送信します
