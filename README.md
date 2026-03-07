# M3U8-Downloader

跨平台桌面客户端（Windows 10/11、macOS），用于批量下载 `m3u8` 并输出为 `mp4`。

- UI：紫色主题 + 白色主题（右上角符号切换）
- 下载：多任务并发、任务级进度条、暂停/继续/删除
- 产物：`Windows .exe` / `Windows 安装包` / `macOS .app + .dmg + .pkg`

## 截图

> 你可以把截图放到 `docs/screenshots/main-ui.png`，README 会自动显示。

![Main UI](docs/screenshots/main-ui.png)

## 功能特性

- 批量输入两种模式
  - `逐条输入`：一个输入框一个链接，输入后自动新增下一行
  - `批量文本`：支持多行、单行 `|` 分隔、空格分隔多个链接
- 自定义命名
  - 支持 `文件名|URL`
  - 支持 URL `#` 片段命名（如 `...m3u8#日文`）
- 智能文件名规则（无自定义名时）
  - 优先：`#片段_清晰度`
  - 其次：`source_id_清晰度`
- 任务管理
  - 全部暂停/继续
  - 单任务暂停/继续、删除
  - 清空任务（二次确认）
  - 支持下载中继续追加新任务（自动去重 URL）
- 下载稳定性
  - HLS 容错参数（允许更多分片后缀）
  - 失败自动重试
  - `copy` 失败自动转码兜底
  - 输出文件校验，异常文件自动修复转码
- 结果反馈
  - 表格显示：准备中/正在下载/已暂停/已完成/失败/已删除
  - 进度条带百分比
  - 失败任务自动导出 `failed_tasks_*.txt`
- 版本更新
  - 设置栏底部版本按钮，点击检测 GitHub 最新版本（Release 优先，Tag 回退）

## 环境要求

- Python `3.10+`（建议 `3.11/3.12`）
- `ffmpeg`（必须）
- `ffprobe`（建议）

安装 ffmpeg：

- Windows（任选其一）
  - `winget install "Gyan.FFmpeg"`
  - `choco install ffmpeg -y`
- macOS
  - `brew install ffmpeg`

校验：

```bash
ffmpeg -version
ffprobe -version
```

## 本地运行

```bash
python -m pip install -r requirements.txt
```

- Windows:

```bat
scripts\run_windows.bat
```

- macOS:

```bash
./scripts/run_mac.sh
```

## 使用说明

1. 左侧设置里选择下载目录、并发、重试次数
2. 在输入区粘贴链接（逐条输入或批量文本）
3. 点击 `开始下载`
4. 下载过程中可：`暂停全部`、`清空任务`、单条 `暂停/删除`
5. 需要继续加任务时点击 `继续添加`

## 输入格式

支持以下常见格式：

```text
https://example.com/a.m3u8
https://example.com/b.m3u8#日文
自定义文件名|https://example.com/c.m3u8
https://a.m3u8|https://b.m3u8|https://c.m3u8
https://a.m3u8 https://b.m3u8 https://c.m3u8
```

## 一键构建产物

### 1) 客户端产物（推荐）

- Windows：`dist/M3U8-Downloader.exe`
- macOS：`dist/M3U8-Downloader.app`、`dist/M3U8-Downloader-macOS.dmg`

Windows：

```bat
scripts\build_windows.bat
```

macOS：

```bash
./scripts/build_mac.sh
```

### 2) 标准安装器（安装向导）

- Windows：`dist/M3U8-Downloader-Setup.exe`
- macOS：`dist/M3U8-Downloader-Installer.pkg`、`dist/M3U8-Downloader-Installer.dmg`

Windows：

```bat
scripts\build_windows_installer.bat
```

macOS：

```bash
./scripts/build_mac_installer.sh
```

## GitHub Releases 自动发布

工作流文件：`.github/workflows/release.yml`

触发方式：推送 `v*` 标签，例如：

```bash
git tag v1.0.4
git push github v1.0.4
```

说明：

- workflow 会把 tag 版本同时注入客户端版本号（用于应用内更新检测显示）

默认发布资产：

- `M3U8-Downloader-Setup.exe`
- `M3U8-Downloader.exe`（portable 回退）
- `M3U8-Downloader-Installer.pkg`
- `M3U8-Downloader-Installer.dmg`
- `windows-build.log`（Windows 构建日志）

Release 页面：

- [Releases](https://github.com/lengziyu/m3u8-downloader/releases)

## 更新检测配置

默认仓库已配置：

```python
GITHUB_REPO = "lengziyu/m3u8-downloader"
```

也可用环境变量覆盖：

```bash
M3U8_DOWNLOADER_GITHUB_REPO=owner/repo
```

更新检测策略：

- 先读 `releases/latest`
- 如果仓库暂无 release 或接口受限，则回退读取 `tags`

## 常见问题（FAQ）

### 1. Releases 只有 Source code，没有安装包？

通常是 CI 构建失败或标签未触发。去 `Actions` 看对应 run 日志。

### 2. 需要把 `dist` 提交到 Git 吗？

不需要。安装包应通过 GitHub Releases 上传/发布，`dist` 保持忽略。

### 3. Windows 下载报 `Error number -10054` / 长时间 0%？

多为网络链路问题（CDN、TLS、代理）。可尝试 VPN/TUN、重试、或更稳定网络。

### 4. Windows 打包时弹 ffmpeg 黑窗吗？

当前实现已使用无控制台方式调用，默认不弹 ffmpeg 控制台窗口。

## 项目结构

```text
m3u8_gui.py                     # GUI 主程序
m3u8_batch_downloader.py        # 早期命令行版本
requirements.txt                # 依赖
scripts/run_windows.bat         # Windows 本地运行
scripts/run_mac.sh              # macOS 本地运行
scripts/build_oneclick.py       # 一键构建核心
scripts/build_installer.py      # 安装器构建核心
scripts/build_windows*.bat      # Windows 构建入口
scripts/build_mac*.sh/.command  # macOS 构建入口
.github/workflows/release.yml   # Tag 自动构建并发布 Release
```

## 免责声明

请仅下载你有合法访问权限的内容。
