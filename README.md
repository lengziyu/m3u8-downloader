# M3U8 Batch Downloader (GUI)

一个支持 **Windows 10/11** 和 **macOS** 的桌面批量下载工具。  
核心能力：批量 `m3u8 -> mp4`、每条任务进度、失败任务自动导出、紫色主题/白色主题切换。

## 功能

- 批量输入多个 m3u8 链接（多行）
- 支持 `文件名|URL` 自定义输出文件名
- 选择下载目录
- 每个链接独立进度条与状态（下载中/重试/完成/失败）
- 失败任务自动导出为 `failed_tasks_时间戳.txt`
- 紫色主题 + 白色主题切换
- 默认 `copy` 模式，失败自动转码兜底

## 界面说明

- 大输入框：粘贴多个 m3u8 地址
- 下载目录：选择目标保存路径
- 并发/重试：控制下载线程和失败重试次数
- 开始下载：启动批量任务
- 任务进度表：按链接显示状态与进度

> 说明：当前版本未提供“分辨率选择”UI（不同站点 master playlist 规则差异较大）。

## 环境要求

- Python 3.10+
- ffmpeg（运行时必须；一键打包会尝试自动捆绑）
- ffprobe（建议，用于更准确进度）

### 安装 ffmpeg

- Windows:
```powershell
winget install "Gyan.FFmpeg"
```

- macOS:
```bash
brew install ffmpeg
```

校验：
```bash
ffmpeg -version
```

## 本地运行

1. 安装依赖
```bash
python3 -m pip install -r requirements.txt
```

2. 启动 GUI
- Windows:
```bat
scripts\run_windows.bat
```
- macOS:
```bash
./scripts/run_mac.sh
```

## 链接输入格式

支持两种格式：

```txt
https://example.com/a.m3u8
my_video_02|https://example.com/b.m3u8
```

## 一键产物（推荐）

统一入口脚本会自动判断系统：
- Windows: 产出 `dist\\M3U8-Downloader.exe`
- macOS: 产出 `dist/M3U8-Downloader.app` 和 `dist/M3U8-Downloader-macOS.dmg`

默认行为：
- 自动安装/更新打包依赖
- 自动创建本地构建虚拟环境 `.build-venv`（避免系统 Python 权限问题）
- 自动尝试将系统 `ffmpeg/ffprobe` 打进客户端（如果本机 PATH 可找到）

### Windows（一键）

```bat
scripts\build_windows.bat
```

### macOS（一键）

```bash
./scripts/build_mac.sh
```

或双击 Finder 中的：

```bash
scripts/build_mac.command
```

## 标准安装器（向导安装）

如果你要“下一步-下一步-选择安装目录”的标准安装体验，用这一组脚本：

- Windows 安装器（Inno Setup 向导）：
```bat
scripts\build_windows_installer.bat
```
产物：
- `dist\\M3U8-Downloader-Setup.exe`

- macOS 安装器（Installer 向导）：
```bash
./scripts/build_mac_installer.sh
```
或双击：
```bash
scripts/build_mac_installer.command
```
产物：
- `dist/M3U8-Downloader-Installer.pkg`
- `dist/M3U8-Downloader-Installer.dmg`

说明：
- Windows 需要预装 Inno Setup 6（含 `iscc` 编译器）。
- macOS 使用系统 `pkgbuild` + `hdiutil`，无需额外安装。

## 版本检测（GitHub Releases）

应用内设置栏底部有版本按钮，点击会检测是否有新版本（使用 GitHub Releases API）。

请先配置仓库（任选一种）：

1. 修改 [m3u8_gui.py](/Users/lens/Documents/web/lengziyu/gitee/m3u8-download/m3u8_gui.py) 中：
- `GITHUB_REPO = "你的GitHub用户名/仓库名"`

2. 或运行时设置环境变量：
```bash
M3U8_DOWNLOADER_GITHUB_REPO=owner/repo
```

然后在设置栏底部点击版本按钮：
- 已最新：弹窗提示“已是最新版本”
- 有新版本：弹窗并可跳转 Releases 下载页面

Releases 当然可以作为下载源，推荐把安装器都放在 Releases 里。

## 手动参数（可选）

底层统一脚本是：

```bash
python3 scripts/build_oneclick.py
```

可选参数：
- `--skip-install`: 跳过依赖安装
- `--no-bundle-ffmpeg`: 不打包 ffmpeg/ffprobe
- `--no-venv`: 不使用 `.build-venv`（默认使用）
- `--index-url <url>`: 指定 pip 源（网络不稳定时建议）
- `--python <path>`: 指定 Python 解释器

网络慢/超时时可用：

```bash
python3 scripts/build_oneclick.py --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

## 项目结构

- `m3u8_gui.py`: 图形界面主程序
- `m3u8_batch_downloader.py`: 原命令行版本
- `requirements.txt`: GUI 依赖
- `scripts/run_windows.bat`: Windows 启动 GUI
- `scripts/run_mac.sh`: macOS 启动 GUI
- `scripts/build_oneclick.py`: 跨平台一键打包核心脚本
- `scripts/build_windows.bat`: Windows 一键打包入口
- `scripts/build_mac.sh`: macOS 一键打包入口
- `scripts/build_mac.command`: macOS 双击打包入口
- `scripts/build_installer.py`: 跨平台标准安装器构建脚本
- `scripts/build_windows_installer.bat`: Windows 安装器构建入口
- `scripts/build_mac_installer.sh`: macOS 安装器构建入口
- `scripts/build_mac_installer.command`: macOS 安装器双击入口
- `.github/workflows/release.yml`: Tag 自动构建并发布 Release

## 发布到 GitHub 注意事项

1. 仓库与版本
- 确认 `GITHUB_REPO` 配置正确。
- 确认 `APP_VERSION` 与你准备发布的版本一致（例如 `1.0.0`）。

2. 产物建议
- Windows：`M3U8-Downloader-Setup.exe`
- macOS：`M3U8-Downloader-Installer.pkg` / `M3U8-Downloader-Installer.dmg`

3. 自动发布
- 本项目已提供 GitHub Actions 工作流：
  - 推送 tag（如 `v1.0.0`）后自动构建并发布 Release 资产。

4. 安全与信任（正式分发建议）
- Windows：建议代码签名证书，减少 SmartScreen 警告。
- macOS：建议 Apple Developer 签名与 notarize，避免“无法验证开发者”提示。

## 注意事项

- 请确保你对目标资源有合法访问权限。
- 某些地址可能需要 `Referer/Cookie`，当前 GUI 未暴露高级请求头配置（可后续扩展）。
- m3u8 进度依赖流信息，有少量源可能显示为不确定进度，完成后会自动置 100%。
