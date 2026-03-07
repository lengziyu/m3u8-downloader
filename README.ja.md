# M3U8-Downloader（日本語）

[中文](README.zh-CN.md) | [English](README.en.md)

[最新リリース（Tag）をダウンロード](https://github.com/lengziyu/m3u8-downloader/releases/latest)

## 機能

- Windows 10/11・macOS 対応デスクトップアプリ
- `m3u8` を一括で `mp4` に保存
- 1件入力モード + 一括テキストモード
- 保存先 / 並列数 / リトライ設定
- タスクごとの進捗、停止/再開、削除
- ダウンロード中に新規タスク追加可能
- 失敗タスクを `failed_tasks_*.txt` に自動出力
- 更新チェック（Release 優先、Tag フォールバック）
- UI言語切替：中国語 / 英語 / 日本語（既定：中国語）

## 実行

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

## ビルド

Windows:

```bat
scripts\build_windows.bat
```

macOS:

```bash
./scripts/build_mac.sh
```

インストーラ:

- Windows: `scripts\build_windows_installer.bat`
- macOS: `./scripts/build_mac_installer.sh`

## 自動リリース

`v*` タグを push すると GitHub Actions で自動リリースされます。

```bash
git tag v1.0.8
git push github v1.0.8
```
