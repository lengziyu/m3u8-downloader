#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import os
import queue
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRectF,
    QSize,
    QStandardPaths,
    QTimer,
    Qt,
    QThread,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
APP_DISPLAY_NAME = "桃影"
APP_RELEASE_NAME = "Taoying"
GITHUB_REPO = os.environ.get("M3U8_DOWNLOADER_GITHUB_REPO", "lengziyu/m3u8-downloader")
DEFAULT_APP_VERSION = "1.1.0"
LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_PORT = 38427
_FFMPEG_OPTION_SUPPORT_CACHE: dict[tuple[str, str], bool] = {}


@dataclass(frozen=True)
class DownloadTask:
    index: int
    url: str
    output_path: Path
    referer: str | None = None
    headers: tuple[str, ...] = ()
    user_agent: str | None = None
    source_page_url: str | None = None


@dataclass(frozen=True)
class DownloadOptions:
    ffmpeg: str
    ffprobe: str | None
    retries: int
    overwrite: bool
    timeout: int
    user_agent: str | None = None
    referer: str | None = None
    headers: list[str] | tuple[str, ...] = ()
    transcode_on_fail: bool = True
    validate_after_copy: bool = True


@dataclass(frozen=True)
class MediaRepairResult:
    status: str
    output_path: Path | None = None
    method: str | None = None
    detail: str | None = None


def normalize_version_text(text: str) -> str:
    value = (text or "").strip()
    if value.lower().startswith("v"):
        value = value[1:]
    return value or "1.0.0"


def _candidate_version_files() -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def push(path: Path) -> None:
        key = str(path)
        if key not in seen:
            seen.add(key)
            candidates.append(path)

    source_root = Path(__file__).resolve().parent
    push(source_root / "VERSION")
    push(Path.cwd() / "VERSION")

    exe_root = Path(sys.executable).resolve().parent
    push(exe_root / "VERSION")
    push(exe_root.parent / "Resources" / "VERSION")

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        push(Path(meipass) / "VERSION")

    return candidates


def read_local_version_file() -> str | None:
    for version_file in _candidate_version_files():
        if not version_file.exists():
            continue
        try:
            for line in version_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    return normalize_version_text(line)
        except Exception:
            continue
    return None


APP_VERSION = normalize_version_text(
    os.environ.get("M3U8_DOWNLOADER_APP_VERSION", "")
    or (read_local_version_file() or DEFAULT_APP_VERSION)
)

LANG_ORDER = ["zh", "en", "ja"]
LANG_LABEL = {"zh": "中文", "en": "English", "ja": "日本語"}
I18N = {
    "zh": {
        "settings_toggle": "设置",
        "settings_title": "下载偏好",
        "output_dir": "下载目录",
        "choose_dir": "选择目录",
        "jobs": "并发任务",
        "retries": "失败重试",
        "timeout": "超时秒数",
        "title_sub": "轻巧的 m3u8 视频下载与修复客户端",
        "input_title": "M3U8 链接输入",
        "single_hint": "逐条输入：每一行只放一个链接，填满后会自动补出下一行。",
        "single_remove": "删除",
        "batch_hint": "批量文本：支持多行输入，也支持一行用 | 分隔多个链接。",
        "batch_clear": "清空",
        "tab_single": "逐条输入",
        "tab_batch": "批量文本",
        "start": "开始下载",
        "add_more": "继续追加",
        "summary_wait": "等待开始下载。",
        "task_progress": "任务进度",
        "pause_all": "暂停全部",
        "resume_all": "继续全部",
        "open_folder": "打开目录",
        "clear_tasks": "清空任务",
        "col_idx": "序号",
        "col_name": "输出文件",
        "col_status": "状态",
        "col_progress": "进度",
        "col_detail": "详情",
        "col_actions": "操作",
        "version_checking": "正在检查更新 v{version}",
        "version_plain": "当前版本 v{version}",
        "dlg_version": "版本信息",
        "version_repo_missing": "还没有配置 GitHub 仓库，请先在环境变量或源码里设置 GITHUB_REPO。",
        "version_latest": "已经是最新版本。\n当前版本：v{current}\n最新版本：{latest}",
        "dlg_new_version": "发现新版本",
        "version_update": "当前版本：v{current}\n最新版本：{latest}\n\n是否打开 Releases 页面下载更新？",
        "version_failed": "检查更新失败：{err}",
        "settings_collapse": "收起设置",
        "settings_expand": "展开设置",
        "status_waiting": "准备中",
        "status_downloading": "下载中",
        "status_done": "已完成",
        "status_skipped": "已跳过",
        "status_paused": "已暂停",
        "status_deleted": "已删除",
        "status_failed": "已失败",
        "row_pause": "暂停",
        "row_resume": "继续",
        "row_play": "播放",
        "row_delete": "删除",
        "select_output_dir": "选择下载目录",
        "dlg_confirm_delete": "确认删除",
        "dlg_confirm_delete_running": "确定删除这个任务吗？正在执行的任务会立即中断。",
        "dlg_confirm_delete_row": "确定只从列表中移除这个任务吗？",
        "dlg_confirm_clear": "确认清空任务",
        "dlg_confirm_clear_running": "确定清空全部任务吗？正在下载的任务会被中断。",
        "dlg_confirm_clear_idle": "确定清空当前任务列表吗？",
        "summary_clear_requested": "已请求清空任务，正在等待当前线程退出。",
        "summary_cleared": "任务列表已清空。",
        "tip": "提示",
        "tip_need_url": "请至少输入一个 m3u8 链接。",
        "tip_need_dir": "请先选择下载目录。",
        "tip_no_running": "当前没有正在运行的任务，请先开始下载。",
        "tip_need_more": "请输入要继续追加的链接。",
        "tip_no_new": "没有可追加的新任务，可能都重复了或者格式无效。",
        "tip_dir_missing": "下载目录不存在。",
        "tip_file_missing": "文件不存在，可能已经被移动或删除。",
        "ffmpeg_missing": "找不到 ffmpeg",
        "summary_added": "已追加 {count} 个新任务。",
        "summary_preparing": "共 {count} 个任务，正在准备下载。",
        "progress_loading": "加载中...",
        "progress_paused": "已暂停",
        "progress_deleted": "已删除",
        "progress_failed": "已失败",
        "summary_done": "完成：成功 {success} | 跳过 {skipped} | 失败 {failed}",
        "summary_done_file": " | 失败清单：{file}",
        "dlg_batch_done": "任务完成",
        "dlg_batch_done_fail": "成功 {success}，跳过 {skipped}，失败 {failed}。\n失败清单已导出：\n{file}",
        "dlg_batch_done_ok": "全部完成。成功 {success}，跳过 {skipped}。",
        "single_placeholder": "https://example.com/video.m3u8",
        "batch_placeholder": "示例：\nhttps://example.com/episode01.m3u8\n渚光希|https://example.com/episode02.m3u8\nhttps://example.com/episode03.m3u8#日文标题\n\n或一行输入：\nhttps://a.m3u8|https://b.m3u8|https://c.m3u8",
        "detail_wait_dispatch": "等待执行",
        "detail_retry_wait": "重试等待中",
        "detail_validating": "校验文件",
        "detail_copy_fallback": "copy 失败，转码中",
        "detail_copy_invalid_fix": "copy 成功但文件异常，转码修复中",
        "detail_finished": "下载完成",
        "detail_skipped": "目标文件已存在",
        "detail_paused": "已暂停",
        "detail_deleted": "已删除",
        "detail_interrupted": "任务已中断",
        "detail_copy_transcoded": "copy 失败，已自动转码",
        "detail_copy_fixed": "copy 文件异常，已自动转码修复",
        "detail_unknown_err": "未知错误",
        "detail_downloading_try": "下载中（尝试 {attempt}/{total}）",
        "lang_tip": "切换语言",
        "sidebar_caption": "功能导航",
        "nav_download": "下载",
        "nav_directory": "目录",
        "nav_repair": "修复视频",
        "nav_settings": "设置",
        "page_badge": "Airy Pink",
        "page_download_title": "视频下载",
        "page_download_sub": "输入单条或批量 m3u8 链接，稳定下载并自动校验输出文件。",
        "page_directory_title": "下载目录",
        "page_directory_sub": "把保存路径单独放出来，方便随时切换和打开。",
        "page_repair_title": "视频修复",
        "page_repair_sub": "对已下载但元数据异常的 MP4 进行重封装或转码修复。",
        "page_settings_title": "偏好设置",
        "page_settings_sub": "主题、语言、并发、重试和超时都集中放在这里。",
        "dir_hint": "当前目录会用于下载输出，也会作为修复视频的默认选择位置。",
        "repair_file_label": "待修复文件",
        "repair_file_hint": "支持多选，也支持每行一个本地视频路径；修复结果会另存，不覆盖原文件。",
        "repair_choose": "选择视频",
        "repair_start": "开始修复",
        "repair_open_output": "打开修复结果",
        "repair_idle": "选择一个或多个 mp4 文件后点击开始修复，修复结果会另存，不覆盖原文件。",
        "repair_placeholder": "K:/video/example.mp4\nK:/video/broken.mp4",
        "repair_processing": "正在修复（{current}/{total}）：{file}",
        "repair_progress": "进度：{current}/{total}",
        "repair_running": "修复中...",
        "repair_stage_scan": "正在探测可恢复流（{current}/{total}）：{file}",
        "repair_stage_remux": "正在尝试封装修复（{current}/{total}）：{file}",
        "repair_stage_verify": "正在校验修复结果（{current}/{total}）：{file}",
        "repair_stage_transcode": "正在尝试转码抢救（{current}/{total}）：{file}",
        "repair_stage_ts_probe": "正在按 TS 残片分析（{current}/{total}）：{file}",
        "repair_stage_ts_remux": "正在按 TS 残片封装修复（{current}/{total}）：{file}",
        "repair_stage_ts_transcode": "正在按 TS 残片转码抢救（{current}/{total}）：{file}",
        "repair_stage_missing": "源文件不存在（{current}/{total}）：{file}",
        "copy_detail": "复制详情",
        "settings_lang": "界面语言",
        "settings_theme": "界面主题",
        "settings_download": "下载调优",
        "settings_version": "版本检查",
        "theme_light": "浅色",
        "theme_dark": "深色",
        "menu_file": "文件",
        "menu_tools": "工具",
        "action_repair_video": "修复视频...",
        "action_exit": "退出",
        "dlg_confirm_exit": "确认退出",
        "dlg_confirm_exit_running": "当前还有下载任务正在运行。现在退出会先尝试停止这些任务，确定继续吗？",
        "summary_exit_stopping": "正在停止下载任务，准备退出...",
        "tip_exit_wait_stop": "仍有任务未能及时停止，请稍后再试。",
        "dlg_select_repair_file": "选择要修复的视频",
        "repair_filter": "视频文件 (*.mp4 *.mkv *.mov *.m4v);;所有文件 (*.*)",
        "tip_repair_missing": "选择的视频文件不存在。",
        "repair_result_healthy": "这个视频看起来是正常的，不需要修复。",
        "repair_result_remux": "修复完成，已生成新的无损重封装文件：\n{file}",
        "repair_result_transcode": "修复完成，已生成新的转码文件：\n{file}",
        "repair_result_failed": "修复失败。",
        "repair_result_failed_detail": "修复失败：{detail}",
        "repair_result_batch": "批量修复完成：成功 {success} / 无需修复 {skipped} / 失败 {failed}",
        "repair_result_batch_detail": "批量修复完成：成功 {success} / 无需修复 {skipped} / 失败 {failed}\n\n{details}",
    },
    "en": {
        "settings_toggle": "Settings",
        "settings_title": "Download Preferences",
        "output_dir": "Download Folder",
        "choose_dir": "Choose Folder",
        "jobs": "Parallel Jobs",
        "retries": "Retries",
        "timeout": "Timeout (sec)",
        "title_sub": "A compact m3u8 downloader and repair client",
        "input_title": "M3U8 Input",
        "single_hint": "Single mode: one link per row. A new row appears automatically when the last one is filled.",
        "single_remove": "Remove",
        "batch_hint": "Batch mode: paste multiple lines, or use | to separate links in a single line.",
        "batch_clear": "Clear",
        "tab_single": "Single",
        "tab_batch": "Batch",
        "start": "Start Download",
        "add_more": "Append More",
        "summary_wait": "Waiting to start.",
        "task_progress": "Task Progress",
        "pause_all": "Pause All",
        "resume_all": "Resume All",
        "open_folder": "Open Folder",
        "clear_tasks": "Clear Tasks",
        "col_idx": "#",
        "col_name": "Output",
        "col_status": "Status",
        "col_progress": "Progress",
        "col_detail": "Detail",
        "col_actions": "Actions",
        "version_checking": "Checking updates v{version}",
        "version_plain": "Current version v{version}",
        "dlg_version": "Version",
        "version_repo_missing": "GitHub repository is not configured yet.",
        "version_latest": "You already have the latest version.\nCurrent: v{current}\nLatest: {latest}",
        "dlg_new_version": "Update Available",
        "version_update": "Current: v{current}\nLatest: {latest}\n\nOpen the Releases page now?",
        "version_failed": "Update check failed: {err}",
        "settings_collapse": "Collapse settings",
        "settings_expand": "Expand settings",
        "status_waiting": "Preparing",
        "status_downloading": "Downloading",
        "status_done": "Done",
        "status_skipped": "Skipped",
        "status_paused": "Paused",
        "status_deleted": "Deleted",
        "status_failed": "Failed",
        "row_pause": "Pause",
        "row_resume": "Resume",
        "row_play": "Play",
        "row_delete": "Delete",
        "select_output_dir": "Choose Download Folder",
        "dlg_confirm_delete": "Confirm Delete",
        "dlg_confirm_delete_running": "Delete this task now? A running task will be interrupted immediately.",
        "dlg_confirm_delete_row": "Remove this task from the list?",
        "dlg_confirm_clear": "Confirm Clear",
        "dlg_confirm_clear_running": "Clear all tasks? Active downloads will be interrupted.",
        "dlg_confirm_clear_idle": "Clear the current task list?",
        "summary_clear_requested": "Clear requested. Waiting for the worker thread to stop.",
        "summary_cleared": "Task list cleared.",
        "tip": "Info",
        "tip_need_url": "Enter at least one m3u8 link.",
        "tip_need_dir": "Choose a download folder first.",
        "tip_no_running": "No task is running right now.",
        "tip_need_more": "Enter links to append.",
        "tip_no_new": "No new task can be appended. They may be duplicates or invalid.",
        "tip_dir_missing": "The download folder does not exist.",
        "tip_file_missing": "The file does not exist. It may have been moved or removed.",
        "ffmpeg_missing": "ffmpeg not found",
        "summary_added": "Added {count} new tasks.",
        "summary_preparing": "Preparing {count} tasks.",
        "progress_loading": "Loading...",
        "progress_paused": "Paused",
        "progress_deleted": "Deleted",
        "progress_failed": "Failed",
        "summary_done": "Done: success {success} | skipped {skipped} | failed {failed}",
        "summary_done_file": " | failures: {file}",
        "dlg_batch_done": "Completed",
        "dlg_batch_done_fail": "Success {success}, skipped {skipped}, failed {failed}.\nFailure list exported to:\n{file}",
        "dlg_batch_done_ok": "All tasks completed. Success {success}, skipped {skipped}.",
        "single_placeholder": "https://example.com/video.m3u8",
        "batch_placeholder": "Example:\nhttps://example.com/episode01.m3u8\nMitsuki Nagisa|https://example.com/episode02.m3u8\nhttps://example.com/episode03.m3u8#Japanese title\n\nOr in one line:\nhttps://a.m3u8|https://b.m3u8|https://c.m3u8",
        "detail_wait_dispatch": "Waiting",
        "detail_retry_wait": "Waiting to retry",
        "detail_validating": "Validating file",
        "detail_copy_fallback": "copy failed, transcoding",
        "detail_copy_invalid_fix": "copy succeeded but file is invalid, repairing by transcode",
        "detail_finished": "Download finished",
        "detail_skipped": "Target file already exists",
        "detail_paused": "Paused",
        "detail_deleted": "Deleted",
        "detail_interrupted": "Interrupted",
        "detail_copy_transcoded": "copy failed, transcoded automatically",
        "detail_copy_fixed": "invalid copy fixed by automatic transcode",
        "detail_unknown_err": "Unknown error",
        "detail_downloading_try": "Downloading (attempt {attempt}/{total})",
        "lang_tip": "Switch language",
        "sidebar_caption": "Navigation",
        "nav_download": "Download",
        "nav_directory": "Directory",
        "nav_repair": "Repair",
        "nav_settings": "Settings",
        "page_badge": "Airy Pink",
        "page_download_title": "Video Download",
        "page_download_sub": "Paste m3u8 links, download reliably, and validate every output file.",
        "page_directory_title": "Download Directory",
        "page_directory_sub": "Keep the save path on its own page so it is always easy to switch and open.",
        "page_repair_title": "Video Repair",
        "page_repair_sub": "Repair downloaded MP4 files with broken metadata through remux or transcode.",
        "page_settings_title": "Preferences",
        "page_settings_sub": "Language, theme, concurrency, retries, and timeout live here.",
        "dir_hint": "This folder is used for downloads and also becomes the default starting location for repair.",
        "repair_file_label": "Source File",
        "repair_file_hint": "Supports multi-select or one local video path per line. Repaired files are saved separately.",
        "repair_choose": "Choose Video",
        "repair_start": "Repair Now",
        "repair_open_output": "Open Repaired File",
        "repair_idle": "Choose one or more mp4 files and start repair. Results are saved as new files.",
        "repair_placeholder": "C:/video/example.mp4\nD:/video/broken.mp4",
        "repair_processing": "Repairing ({current}/{total}): {file}",
        "repair_progress": "Progress: {current}/{total}",
        "repair_running": "Repairing...",
        "repair_stage_scan": "Scanning recoverable streams ({current}/{total}): {file}",
        "repair_stage_remux": "Trying container repair ({current}/{total}): {file}",
        "repair_stage_verify": "Verifying repaired output ({current}/{total}): {file}",
        "repair_stage_transcode": "Trying transcode recovery ({current}/{total}): {file}",
        "repair_stage_ts_probe": "Analyzing as TS fragment ({current}/{total}): {file}",
        "repair_stage_ts_remux": "Trying TS container repair ({current}/{total}): {file}",
        "repair_stage_ts_transcode": "Trying TS transcode recovery ({current}/{total}): {file}",
        "repair_stage_missing": "Source file is missing ({current}/{total}): {file}",
        "copy_detail": "Copy Details",
        "settings_lang": "Language",
        "settings_theme": "Theme",
        "settings_download": "Download Tuning",
        "settings_version": "Version Check",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "menu_file": "File",
        "menu_tools": "Tools",
        "action_repair_video": "Repair Video...",
        "action_exit": "Exit",
        "dlg_confirm_exit": "Confirm Exit",
        "dlg_confirm_exit_running": "There are active downloads. Exit now and stop them first?",
        "summary_exit_stopping": "Stopping downloads before exit...",
        "tip_exit_wait_stop": "Some tasks are still stopping. Please try again in a moment.",
        "dlg_select_repair_file": "Select Video to Repair",
        "repair_filter": "Video Files (*.mp4 *.mkv *.mov *.m4v);;All Files (*.*)",
        "tip_repair_missing": "The selected video file does not exist.",
        "repair_result_healthy": "This video looks healthy and does not need repair.",
        "repair_result_remux": "Repair complete. A new remuxed file was created:\n{file}",
        "repair_result_transcode": "Repair complete. A new transcoded file was created:\n{file}",
        "repair_result_failed": "Repair failed.",
        "repair_result_failed_detail": "Repair failed: {detail}",
        "repair_result_batch": "Batch repair finished: success {success} / no repair needed {skipped} / failed {failed}",
        "repair_result_batch_detail": "Batch repair finished: success {success} / no repair needed {skipped} / failed {failed}\n\n{details}",
    },
    "ja": {
        "settings_toggle": "設定",
        "settings_title": "ダウンロード設定",
        "output_dir": "保存先フォルダー",
        "choose_dir": "フォルダーを選択",
        "jobs": "同時実行数",
        "retries": "再試行回数",
        "timeout": "タイムアウト秒数",
        "title_sub": "軽量な m3u8 ダウンロード・修復クライアント",
        "input_title": "M3U8 入力",
        "single_hint": "単体入力: 1 行に 1 リンク。最後の行が埋まると次の行を自動追加します。",
        "single_remove": "削除",
        "batch_hint": "一括入力: 複数行貼り付け、または 1 行で | 区切りにも対応します。",
        "batch_clear": "クリア",
        "tab_single": "単体入力",
        "tab_batch": "一括入力",
        "start": "ダウンロード開始",
        "add_more": "さらに追加",
        "summary_wait": "開始待ちです。",
        "task_progress": "進捗",
        "pause_all": "すべて一時停止",
        "resume_all": "すべて再開",
        "open_folder": "フォルダーを開く",
        "clear_tasks": "タスクをクリア",
        "col_idx": "番号",
        "col_name": "出力ファイル",
        "col_status": "状態",
        "col_progress": "進捗",
        "col_detail": "詳細",
        "col_actions": "操作",
        "version_checking": "更新確認中 v{version}",
        "version_plain": "現在のバージョン v{version}",
        "dlg_version": "バージョン情報",
        "version_repo_missing": "GitHub リポジトリがまだ設定されていません。",
        "version_latest": "すでに最新です。\n現在: v{current}\n最新: {latest}",
        "dlg_new_version": "新しいバージョンがあります",
        "version_update": "現在: v{current}\n最新: {latest}\n\nReleases ページを開きますか？",
        "version_failed": "更新確認に失敗しました: {err}",
        "settings_collapse": "設定を閉じる",
        "settings_expand": "設定を開く",
        "status_waiting": "準備中",
        "status_downloading": "ダウンロード中",
        "status_done": "完了",
        "status_skipped": "スキップ",
        "status_paused": "一時停止",
        "status_deleted": "削除済み",
        "status_failed": "失敗",
        "row_pause": "停止",
        "row_resume": "再開",
        "row_play": "再生",
        "row_delete": "削除",
        "select_output_dir": "保存先フォルダーを選択",
        "dlg_confirm_delete": "削除確認",
        "dlg_confirm_delete_running": "このタスクを削除しますか？実行中のタスクは中断されます。",
        "dlg_confirm_delete_row": "このタスクを一覧から削除しますか？",
        "dlg_confirm_clear": "クリア確認",
        "dlg_confirm_clear_running": "すべてのタスクをクリアしますか？実行中のダウンロードは中断されます。",
        "dlg_confirm_clear_idle": "現在のタスク一覧をクリアしますか？",
        "summary_clear_requested": "クリアを要求しました。ワーカースレッドの停止を待っています。",
        "summary_cleared": "タスク一覧をクリアしました。",
        "tip": "案内",
        "tip_need_url": "m3u8 リンクを少なくとも 1 つ入力してください。",
        "tip_need_dir": "先に保存先フォルダーを選択してください。",
        "tip_no_running": "現在実行中のタスクはありません。",
        "tip_need_more": "追加するリンクを入力してください。",
        "tip_no_new": "追加できる新しいタスクがありません。重複または無効な可能性があります。",
        "tip_dir_missing": "保存先フォルダーが存在しません。",
        "tip_file_missing": "ファイルが存在しません。移動または削除された可能性があります。",
        "ffmpeg_missing": "ffmpeg が見つかりません",
        "summary_added": "{count} 件のタスクを追加しました。",
        "summary_preparing": "{count} 件のタスクを準備しています。",
        "progress_loading": "読み込み中...",
        "progress_paused": "一時停止",
        "progress_deleted": "削除済み",
        "progress_failed": "失敗",
        "summary_done": "完了: 成功 {success} | スキップ {skipped} | 失敗 {failed}",
        "summary_done_file": " | 失敗一覧: {file}",
        "dlg_batch_done": "完了",
        "dlg_batch_done_fail": "成功 {success}、スキップ {skipped}、失敗 {failed}。\n失敗一覧を出力しました:\n{file}",
        "dlg_batch_done_ok": "すべて完了しました。成功 {success}、スキップ {skipped}。",
        "single_placeholder": "https://example.com/video.m3u8",
        "batch_placeholder": "例:\nhttps://example.com/episode01.m3u8\n渚光希|https://example.com/episode02.m3u8\nhttps://example.com/episode03.m3u8#日本語タイトル\n\nまたは 1 行で:\nhttps://a.m3u8|https://b.m3u8|https://c.m3u8",
        "detail_wait_dispatch": "待機中",
        "detail_retry_wait": "再試行待ち",
        "detail_validating": "ファイルを検証中",
        "detail_copy_fallback": "copy に失敗、再エンコード中",
        "detail_copy_invalid_fix": "copy 成功だが不正なファイルのため修復中",
        "detail_finished": "ダウンロード完了",
        "detail_skipped": "出力ファイルはすでに存在します",
        "detail_paused": "一時停止",
        "detail_deleted": "削除済み",
        "detail_interrupted": "中断されました",
        "detail_copy_transcoded": "copy に失敗したため自動再エンコードしました",
        "detail_copy_fixed": "不正な copy を自動再エンコードで修復しました",
        "detail_unknown_err": "不明なエラー",
        "detail_downloading_try": "ダウンロード中 ({attempt}/{total})",
        "lang_tip": "言語を切り替え",
        "sidebar_caption": "メニュー",
        "nav_download": "ダウンロード",
        "nav_directory": "保存先",
        "nav_repair": "動画修復",
        "nav_settings": "設定",
        "page_badge": "Airy Pink",
        "page_download_title": "動画ダウンロード",
        "page_download_sub": "m3u8 リンクを入力し、安定してダウンロードしながら出力ファイルを検証します。",
        "page_directory_title": "保存先フォルダー",
        "page_directory_sub": "保存先を専用ページに分け、いつでも切り替えや確認をしやすくします。",
        "page_repair_title": "動画修復",
        "page_repair_sub": "メタデータが壊れた MP4 を再 mux または再エンコードで修復します。",
        "page_settings_title": "環境設定",
        "page_settings_sub": "言語、テーマ、同時実行数、再試行回数、タイムアウトをここで調整できます。",
        "dir_hint": "このフォルダーはダウンロード保存先であり、動画修復の初期選択場所にも使われます。",
        "repair_file_label": "修復対象ファイル",
        "repair_file_hint": "複数選択、または 1 行に 1 つずつローカル動画パスを貼り付けられます。結果は別名保存されます。",
        "repair_choose": "動画を選択",
        "repair_start": "修復開始",
        "repair_open_output": "修復結果を開く",
        "repair_idle": "1 つ以上の mp4 ファイルを選択してから修復を開始してください。結果は別名で保存されます。",
        "repair_placeholder": "C:/video/example.mp4\nD:/video/broken.mp4",
        "repair_processing": "修復中 ({current}/{total}): {file}",
        "repair_progress": "進捗: {current}/{total}",
        "repair_running": "修復中...",
        "repair_stage_scan": "復旧可能なストリームを解析中 ({current}/{total}): {file}",
        "repair_stage_remux": "コンテナ修復を試行中 ({current}/{total}): {file}",
        "repair_stage_verify": "修復結果を検証中 ({current}/{total}): {file}",
        "repair_stage_transcode": "再エンコード救済を試行中 ({current}/{total}): {file}",
        "repair_stage_ts_probe": "TS 断片として解析中 ({current}/{total}): {file}",
        "repair_stage_ts_remux": "TS 断片としてコンテナ修復中 ({current}/{total}): {file}",
        "repair_stage_ts_transcode": "TS 断片として再エンコード救済中 ({current}/{total}): {file}",
        "repair_stage_missing": "元ファイルが見つかりません ({current}/{total}): {file}",
        "copy_detail": "詳細をコピー",
        "settings_lang": "表示言語",
        "settings_theme": "テーマ",
        "settings_download": "ダウンロード調整",
        "settings_version": "更新確認",
        "theme_light": "ライト",
        "theme_dark": "ダーク",
        "menu_file": "ファイル",
        "menu_tools": "ツール",
        "action_repair_video": "動画を修復...",
        "action_exit": "終了",
        "dlg_confirm_exit": "終了確認",
        "dlg_confirm_exit_running": "まだダウンロード中のタスクがあります。先に停止して終了しますか？",
        "summary_exit_stopping": "終了前にダウンロードを停止しています...",
        "tip_exit_wait_stop": "まだ停止していないタスクがあります。少し待ってから再試行してください。",
        "dlg_select_repair_file": "修復する動画を選択",
        "repair_filter": "動画ファイル (*.mp4 *.mkv *.mov *.m4v);;すべてのファイル (*.*)",
        "tip_repair_missing": "選択した動画ファイルが存在しません。",
        "repair_result_healthy": "この動画は正常に見えるため、修復は不要です。",
        "repair_result_remux": "修復完了。新しい remux ファイルを作成しました:\n{file}",
        "repair_result_transcode": "修復完了。新しい再エンコードファイルを作成しました:\n{file}",
        "repair_result_failed": "修復に失敗しました。",
        "repair_result_failed_detail": "修復に失敗しました: {detail}",
        "repair_result_batch": "一括修復完了: 成功 {success} / 修復不要 {skipped} / 失敗 {failed}",
        "repair_result_batch_detail": "一括修復完了: 成功 {success} / 修復不要 {skipped} / 失敗 {failed}\n\n{details}",
    },
}

for _lang, _extra in {
    "zh": {
        "nav_history": "下载历史",
        "page_history_title": "下载历史",
        "page_history_sub": "这里会长期保存番号、名称、链接和输出文件路径，方便排查坏文件并批量重新下载。",
        "page_settings_sub": "语言、主题、并发、重试、超时都可以在这里调整，下载历史也会保存在软件目录里。",
        "history_filters_title": "历史筛选",
        "history_actions_title": "历史操作",
        "history_code": "番号",
        "history_name": "名称",
        "history_url": "链接",
        "history_status": "状态",
        "history_search": "查询",
        "history_reset": "重置",
        "history_scan": "检查当前结果",
        "history_redownload_selected": "重下选中项",
        "history_redownload_page": "重下本页",
        "history_delete_selected": "删除选中历史",
        "history_page_prev": "上一页",
        "history_page_next": "下一页",
        "history_page_info": "第 {current}/{total} 页",
        "history_summary_empty": "暂无历史记录。",
        "history_summary_page": "共 {total} 条，当前第 {current}/{total_pages} 页。",
        "history_scan_running": "正在检查当前筛选结果，共 {total} 条……",
        "history_scan_progress": "正在检查 {current}/{total}: {name}",
        "history_scan_done": "检查完成：正常 {ok}，损坏 {broken}，文件缺失 {missing}。",
        "history_store_failed": "历史存档初始化失败：{err}",
        "history_no_selection": "请先选中历史记录。",
        "history_confirm_delete": "确认删除历史",
        "history_confirm_delete_selected": "仅删除选中的历史记录，不会删除磁盘里的视频文件，是否继续？",
        "history_redownload_added": "已加入重下队列：{added} 条。",
        "history_redownload_none": "没有可加入的历史记录，可能已经在当前任务里，或链接无效。",
        "history_status_all": "全部",
        "history_status_unknown": "未检查",
        "history_status_ok": "正常",
        "history_status_broken": "损坏",
        "history_status_missing": "文件缺失",
        "history_status_issue": "仅看异常",
        "history_col_id": "ID",
        "history_col_code": "番号",
        "history_col_name": "名称",
        "history_col_status": "状态",
        "history_col_path": "文件路径",
        "history_col_url": "链接",
        "history_col_updated": "更新时间",
    },
    "en": {
        "nav_history": "History",
        "page_history_title": "Download History",
        "page_history_sub": "Save code, name, link, and output path locally so broken videos can be found and queued again.",
        "history_filters_title": "Filters",
        "history_actions_title": "Actions",
        "history_code": "Code",
        "history_name": "Name",
        "history_url": "Link",
        "history_status": "Status",
        "history_search": "Search",
        "history_reset": "Reset",
        "history_scan": "Check Results",
        "history_redownload_selected": "Redownload Selected",
        "history_redownload_page": "Redownload Page",
        "history_delete_selected": "Delete Selected History",
        "history_page_prev": "Prev",
        "history_page_next": "Next",
        "history_page_info": "Page {current}/{total}",
        "history_summary_empty": "No history records yet.",
        "history_summary_page": "{total} records, page {current}/{total_pages}.",
        "history_scan_running": "Checking {total} filtered records...",
        "history_scan_progress": "Checking {current}/{total}: {name}",
        "history_scan_done": "Check complete: ok {ok}, broken {broken}, missing {missing}.",
        "history_store_failed": "Failed to initialize history store: {err}",
        "history_no_selection": "Select at least one history row first.",
        "history_confirm_delete": "Delete History",
        "history_confirm_delete_selected": "Only the selected history rows will be removed. Video files on disk will stay untouched. Continue?",
        "history_redownload_added": "{added} record(s) added back to the download queue.",
        "history_redownload_none": "No history rows could be queued. They may already exist in the current task list, or the links are invalid.",
        "history_status_all": "All",
        "history_status_unknown": "Unknown",
        "history_status_ok": "OK",
        "history_status_broken": "Broken",
        "history_status_missing": "Missing",
        "history_status_issue": "Issues Only",
        "history_col_id": "ID",
        "history_col_code": "Code",
        "history_col_name": "Name",
        "history_col_status": "Status",
        "history_col_path": "File Path",
        "history_col_url": "Link",
        "history_col_updated": "Updated",
    },
    "ja": {
        "nav_history": "履歴",
        "page_history_title": "ダウンロード履歴",
        "page_history_sub": "番号、名前、リンク、保存先をソフト内に残して、壊れた動画の再取得をやりやすくします。",
        "history_filters_title": "絞り込み",
        "history_actions_title": "操作",
        "history_code": "番号",
        "history_name": "名称",
        "history_url": "リンク",
        "history_status": "状態",
        "history_search": "検索",
        "history_reset": "リセット",
        "history_scan": "現在結果を検査",
        "history_redownload_selected": "選択項目を再取得",
        "history_redownload_page": "このページを再取得",
        "history_delete_selected": "選択履歴を削除",
        "history_page_prev": "前へ",
        "history_page_next": "次へ",
        "history_page_info": "{current}/{total} ページ",
        "history_summary_empty": "履歴はまだありません。",
        "history_summary_page": "全 {total} 件、{current}/{total_pages} ページ目です。",
        "history_scan_running": "現在の絞り込み結果 {total} 件を検査中...",
        "history_scan_progress": "{current}/{total} を検査中: {name}",
        "history_scan_done": "検査完了: 正常 {ok}、破損 {broken}、ファイル欠失 {missing}。",
        "history_store_failed": "履歴ストアの初期化に失敗しました: {err}",
        "history_no_selection": "先に履歴行を選択してください。",
        "history_confirm_delete": "履歴削除の確認",
        "history_confirm_delete_selected": "選択した履歴だけを削除します。ディスク上の動画ファイルは削除しません。続行しますか？",
        "history_redownload_added": "{added} 件を再取得キューへ追加しました。",
        "history_redownload_none": "追加できる履歴がありません。すでに現在のタスクにあるか、リンクが無効です。",
        "history_status_all": "すべて",
        "history_status_unknown": "未検査",
        "history_status_ok": "正常",
        "history_status_broken": "破損",
        "history_status_missing": "欠失",
        "history_status_issue": "異常のみ",
        "history_col_id": "ID",
        "history_col_code": "番号",
        "history_col_name": "名称",
        "history_col_status": "状態",
        "history_col_path": "保存先",
        "history_col_url": "リンク",
        "history_col_updated": "更新日時",
    },
}.items():
    I18N.setdefault(_lang, {}).update(_extra)

for _lang, _extra in {
    "zh": {
        "theme_light_tip": "切换到浅色主题",
        "theme_dark_tip": "切换到深色主题",
        "tip_copied_output": "已复制输出文件路径",
    },
    "en": {
        "theme_light_tip": "Switch to the light theme",
        "theme_dark_tip": "Switch to the dark theme",
        "tip_copied_output": "Output path copied",
    },
    "ja": {
        "theme_light_tip": "ライトテーマに切り替え",
        "theme_dark_tip": "ダークテーマに切り替え",
        "tip_copied_output": "出力先パスをコピーしました",
    },
}.items():
    I18N.setdefault(_lang, {}).update(_extra)


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", name).strip().strip(".")
    return cleaned or "video"


VIDEO_CODE_RE = re.compile(r"([A-Za-z]{2,8}-\d{2,6})", re.IGNORECASE)


def app_storage_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def history_db_path() -> Path:
    return app_storage_dir() / "download_history.sqlite3"


def extract_video_code(text: str) -> str:
    source = Path(text or "").stem
    match = VIDEO_CODE_RE.search(source)
    return match.group(1).upper() if match else ""


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    code: str
    name: str
    url: str
    output_path: str
    created_at: str
    updated_at: str


class DownloadHistoryStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS download_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    output_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_download_history_code ON download_history(code)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_download_history_updated ON download_history(updated_at DESC, id DESC)"
            )

    def upsert_entry(self, code: str, name: str, url: str, output_path: str) -> None:
        now = dt.datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO download_history (code, name, url, output_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    code = excluded.code,
                    name = excluded.name,
                    output_path = excluded.output_path,
                    updated_at = excluded.updated_at
                """,
                (code, name, url, output_path, now, now),
            )

    def query_entries(self, code_filter: str = "", name_filter: str = "", url_filter: str = "") -> list[HistoryEntry]:
        clauses: list[str] = []
        params: list[str] = []
        if code_filter.strip():
            clauses.append("LOWER(code) LIKE ?")
            params.append(f"%{code_filter.strip().lower()}%")
        if name_filter.strip():
            clauses.append("LOWER(name) LIKE ?")
            params.append(f"%{name_filter.strip().lower()}%")
        if url_filter.strip():
            clauses.append("LOWER(url) LIKE ?")
            params.append(f"%{url_filter.strip().lower()}%")

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, code, name, url, output_path, created_at, updated_at "
            f"FROM download_history {where_clause} "
            "ORDER BY updated_at DESC, id DESC"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            HistoryEntry(
                id=int(row["id"]),
                code=str(row["code"] or ""),
                name=str(row["name"] or ""),
                url=str(row["url"] or ""),
                output_path=str(row["output_path"] or ""),
                created_at=str(row["created_at"] or ""),
                updated_at=str(row["updated_at"] or ""),
            )
            for row in rows
        ]

    def delete_entries(self, entry_ids: list[int]) -> None:
        if not entry_ids:
            return
        placeholders = ",".join("?" for _ in entry_ids)
        with self._connect() as conn:
            conn.execute(f"DELETE FROM download_history WHERE id IN ({placeholders})", entry_ids)


def is_probable_url(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def build_output_name(index: int, url: str, custom_name: str | None) -> str:
    if custom_name:
        base = sanitize_filename(custom_name)
    else:
        parsed = urlparse(url)
        path_parts = [unquote(p) for p in parsed.path.split("/") if p]
        quality = sanitize_filename(path_parts[-2]) if len(path_parts) >= 2 else ""
        source_id = sanitize_filename(path_parts[-3]) if len(path_parts) >= 3 else ""
        fragment = sanitize_filename(unquote(parsed.fragment)) if parsed.fragment else ""

        if fragment and quality:
            base = f"{fragment}_{quality}"
        elif fragment:
            base = fragment
        elif source_id and quality:
            base = f"{source_id}_{quality}"
        elif source_id:
            base = source_id
        else:
            raw_name = Path(unquote(parsed.path)).stem
            base = sanitize_filename(raw_name) if raw_name else f"video_{index:03d}"

    if not base.lower().endswith(".mp4"):
        return f"{base}.mp4"
    return base


def parse_url_lines(raw_text: str) -> list[tuple[str | None, str]]:
    entries: list[tuple[str | None, str]] = []
    for raw_line in raw_text.splitlines():
        text = raw_line.strip()
        if not text or text.startswith("#"):
            continue

        if "|" not in text:
            if is_probable_url(text):
                entries.append((None, text))
            continue

        parts = [part.strip() for part in text.split("|") if part.strip()]
        if not parts:
            continue

        if len(parts) > 1 and all(is_probable_url(part) for part in parts):
            entries.extend((None, part) for part in parts)
            continue

        last = parts[-1]
        if is_probable_url(last):
            name = "|".join(parts[:-1]).strip() or None
            entries.append((name, last))
            continue

        if is_probable_url(text):
            entries.append((None, text))
    return entries


def create_app_icon(size: int = 256) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    card = QPainterPath()
    card.addRoundedRect(QRectF(6, 6, size - 12, size - 12), 46, 46)
    painter.fillPath(card, QColor("#FF5C7C"))

    glow = QPainterPath()
    glow.addEllipse(QRectF(size * 0.14, size * 0.12, size * 0.72, size * 0.72))
    painter.fillPath(glow, QColor(255, 255, 255, 34))

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    petal_specs = [
        (0.33, 0.28, 0.20, 0.28),
        (0.47, 0.24, 0.20, 0.30),
        (0.56, 0.36, 0.19, 0.26),
        (0.36, 0.40, 0.18, 0.25),
    ]
    for x, y, w, h in petal_specs:
        painter.drawEllipse(QRectF(size * x, size * y, size * w, size * h))

    center = QPainterPath()
    center.addEllipse(QRectF(size * 0.38, size * 0.37, size * 0.24, size * 0.24))
    painter.fillPath(center, QColor("#FF6E8A"))

    play = QPainterPath()
    play.moveTo(size * 0.47, size * 0.42)
    play.lineTo(size * 0.47, size * 0.56)
    play.lineTo(size * 0.58, size * 0.49)
    play.closeSubpath()
    painter.fillPath(play, QColor("#FFFFFF"))

    painter.setPen(QPen(QColor("#FFFFFF"), max(6, size // 34), Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(int(size * 0.30), int(size * 0.78), int(size * 0.70), int(size * 0.78))
    painter.end()
    return QIcon(pix)


def load_brand_logo_pixmap(size: int = 56) -> QPixmap:
    logo_path = Path(__file__).resolve().parent / "assets" / "app_icon.png"
    pix = QPixmap(str(logo_path)) if logo_path.exists() else QPixmap()
    if pix.isNull():
        pix = create_app_icon(size).pixmap(size, size)
    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def create_nav_icon(kind: str, color: QColor, size: int = 18) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    pen = QPen(color, max(1.6, size / 11), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    if kind == "download":
        painter.drawLine(int(size * 0.5), int(size * 0.18), int(size * 0.5), int(size * 0.62))
        painter.drawLine(int(size * 0.34), int(size * 0.48), int(size * 0.5), int(size * 0.66))
        painter.drawLine(int(size * 0.66), int(size * 0.48), int(size * 0.5), int(size * 0.66))
        painter.drawLine(int(size * 0.22), int(size * 0.80), int(size * 0.78), int(size * 0.80))
    elif kind == "directory":
        folder = QPainterPath()
        folder.moveTo(size * 0.14, size * 0.38)
        folder.lineTo(size * 0.34, size * 0.38)
        folder.lineTo(size * 0.41, size * 0.24)
        folder.lineTo(size * 0.83, size * 0.24)
        folder.lineTo(size * 0.83, size * 0.74)
        folder.lineTo(size * 0.14, size * 0.74)
        folder.closeSubpath()
        painter.drawPath(folder)
        painter.drawLine(int(size * 0.14), int(size * 0.42), int(size * 0.83), int(size * 0.42))
    elif kind == "repair":
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(size * 0.16, size * 0.20, size * 0.52, size * 0.58), 3, 3)
        painter.drawPath(frame)
        play = QPainterPath()
        play.moveTo(size * 0.38, size * 0.36)
        play.lineTo(size * 0.38, size * 0.62)
        play.lineTo(size * 0.57, size * 0.49)
        play.closeSubpath()
        painter.fillPath(play, color)
        painter.drawLine(int(size * 0.72), int(size * 0.24), int(size * 0.72), int(size * 0.40))
        painter.drawLine(int(size * 0.64), int(size * 0.32), int(size * 0.80), int(size * 0.32))
        painter.drawLine(int(size * 0.78), int(size * 0.14), int(size * 0.78), int(size * 0.26))
        painter.drawLine(int(size * 0.72), int(size * 0.20), int(size * 0.84), int(size * 0.20))
    elif kind == "history":
        painter.drawRoundedRect(QRectF(size * 0.18, size * 0.20, size * 0.64, size * 0.58), 3, 3)
        painter.drawLine(int(size * 0.30), int(size * 0.38), int(size * 0.70), int(size * 0.38))
        painter.drawLine(int(size * 0.30), int(size * 0.50), int(size * 0.70), int(size * 0.50))
        painter.drawLine(int(size * 0.30), int(size * 0.62), int(size * 0.58), int(size * 0.62))
    else:
        painter.drawEllipse(QRectF(size * 0.30, size * 0.30, size * 0.40, size * 0.40))
        for angle in range(0, 360, 45):
            painter.save()
            painter.translate(size * 0.5, size * 0.5)
            painter.rotate(angle)
            painter.drawLine(int(size * 0.0), int(-size * 0.34), int(size * 0.0), int(-size * 0.20))
            painter.restore()

    painter.end()
    return QIcon(pix)


def create_theme_icon(theme: str, color: QColor, size: int = 18) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, max(1.5, size / 11), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    if theme == "light":
        painter.drawEllipse(QRectF(size * 0.28, size * 0.28, size * 0.44, size * 0.44))
        for angle in range(0, 360, 45):
            painter.save()
            painter.translate(size * 0.5, size * 0.5)
            painter.rotate(angle)
            painter.drawLine(int(size * 0.0), int(-size * 0.42), int(size * 0.0), int(-size * 0.30))
            painter.restore()
    else:
        moon = QPainterPath()
        moon.addEllipse(QRectF(size * 0.24, size * 0.18, size * 0.52, size * 0.60))
        cut = QPainterPath()
        cut.addEllipse(QRectF(size * 0.42, size * 0.14, size * 0.42, size * 0.58))
        moon = moon.subtracted(cut)
        painter.fillPath(moon, color)
        painter.drawPath(moon)

    painter.end()
    return QIcon(pix)


def build_tasks(
    entries: list[tuple[str | None, str]],
    output_dir: Path,
    start_index: int = 1,
    used_names: set[str] | None = None,
) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    local_used = used_names if used_names is not None else set()
    for idx, (name, url) in enumerate(entries, start=start_index):
        candidate = build_output_name(idx, url, name)
        stem = Path(candidate).stem
        final = candidate
        suffix = 1
        while final.lower() in local_used:
            final = f"{stem}_{suffix}.mp4"
            suffix += 1
        local_used.add(final.lower())
        tasks.append(DownloadTask(index=idx, url=url, output_path=output_dir / final))
    return tasks


def build_task(
    *,
    index: int,
    url: str,
    output_dir: Path,
    used_names: set[str],
    custom_name: str | None = None,
    referer: str | None = None,
    headers: list[str] | tuple[str, ...] | None = None,
    user_agent: str | None = None,
    source_page_url: str | None = None,
) -> DownloadTask:
    candidate = build_output_name(index, url, custom_name)
    stem = Path(candidate).stem
    final = candidate
    suffix = 1
    while final.lower() in used_names:
        final = f"{stem}_{suffix}.mp4"
        suffix += 1
    used_names.add(final.lower())
    return DownloadTask(
        index=index,
        url=url,
        output_path=output_dir / final,
        referer=(referer or "").strip() or None,
        headers=tuple(h for h in (headers or []) if h),
        user_agent=(user_agent or "").strip() or None,
        source_page_url=(source_page_url or "").strip() or None,
    )


def parse_version(value: str) -> tuple[int, ...]:
    text = value.strip().lower()
    if text.startswith("v"):
        text = text[1:]
    nums = re.findall(r"\d+", text)
    return tuple(int(n) for n in nums[:4])


def is_newer_version(current: str, latest: str) -> bool:
    cur = parse_version(current)
    lat = parse_version(latest)
    if not cur or not lat:
        return latest.strip() != current.strip()
    length = max(len(cur), len(lat))
    cur_pad = cur + (0,) * (length - len(cur))
    lat_pad = lat + (0,) * (length - len(lat))
    return lat_pad > cur_pad


def _github_json_get(url: str) -> object:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": APP_DISPLAY_NAME,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        # Some local Python environments miss CA bundles.
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            insecure_ctx = ssl.create_default_context()
            insecure_ctx.check_hostname = False
            insecure_ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=12, context=insecure_ctx) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        raise


def fetch_latest_version(repo: str) -> tuple[str, str]:
    releases_url = f"https://github.com/{repo}/releases"

    # Prefer official latest release.
    try:
        payload = _github_json_get(f"https://api.github.com/repos/{repo}/releases/latest")
        if isinstance(payload, dict):
            tag = str(payload.get("tag_name") or payload.get("name") or "").strip()
            html_url = str(payload.get("html_url") or releases_url).strip() or releases_url
            if tag:
                return tag, html_url
    except urllib.error.HTTPError as exc:
        if exc.code not in {403, 404}:
            raise
    except Exception:
        pass

    # Fallback to tags when release is missing or inaccessible.
    payload = _github_json_get(f"https://api.github.com/repos/{repo}/tags?per_page=100")
    if not isinstance(payload, list):
        raise RuntimeError("读取 tag 列表失败。")

    tags = [str(item.get("name") or "").strip() for item in payload if isinstance(item, dict)]
    tags = [tag for tag in tags if tag]
    if not tags:
        raise RuntimeError("未读取到任何 release/tag。")

    valid_semver_tags = [tag for tag in tags if parse_version(tag)]
    latest_tag = max(valid_semver_tags, key=parse_version) if valid_semver_tags else tags[0]
    return latest_tag, releases_url


def _candidate_binary_names(name: str) -> list[str]:
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return [name, f"{name}.exe"]
    return [name]


def _normalize_windows_ffmpeg_candidate(path: str, binary_name: str) -> str:
    p = Path(path)
    lower = str(p).lower().replace("/", "\\")
    if "\\chocolatey\\bin\\" in lower:
        real = p.parent.parent / "lib" / "ffmpeg" / "tools" / "ffmpeg" / "bin" / f"{binary_name}.exe"
        if real.exists():
            return str(real)
    return path


def _binary_is_usable(path: str) -> bool:
    try:
        proc = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=6,
            **subprocess_no_window_kwargs(),
        )
        return proc.returncode == 0
    except Exception:
        return False


def _try_resolve_local_binary(name: str) -> str | None:
    candidates: list[Path] = []
    app_root = Path(__file__).resolve().parent
    exe_root = Path(sys.executable).resolve().parent
    candidates.extend([app_root, exe_root])

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass))

    for root in candidates:
        for binary_name in _candidate_binary_names(name):
            target = (root / binary_name).resolve()
            if target.exists() and os.access(target, os.X_OK):
                return str(target)
    return None


def check_ffmpeg_bin(ffmpeg_bin: str) -> str:
    candidates: list[str] = []
    local = _try_resolve_local_binary(ffmpeg_bin)
    if local:
        candidates.append(local)

    system = shutil.which(ffmpeg_bin)
    if system:
        if os.name == "nt":
            system = _normalize_windows_ffmpeg_candidate(system, "ffmpeg")
        if system not in candidates:
            candidates.append(system)

    for candidate in candidates:
        if _binary_is_usable(candidate):
            return candidate

    raise FileNotFoundError(
        "找不到 ffmpeg。请先安装 ffmpeg 并加入 PATH，"
        "或使用一键打包脚本把 ffmpeg 一起打进客户端。"
    )


def resolve_ffprobe_bin() -> str | None:
    local = _try_resolve_local_binary("ffprobe")
    if local and _binary_is_usable(local):
        return local

    system = shutil.which("ffprobe")
    if system:
        if os.name == "nt":
            system = _normalize_windows_ffmpeg_candidate(system, "ffprobe")
        if _binary_is_usable(system):
            return system
    return None


def header_args(user_agent: str | None, referer: str | None, headers: list[str]) -> list[str]:
    args: list[str] = ["-user_agent", user_agent or DEFAULT_USER_AGENT]

    merged_headers: list[str] = []
    if referer:
        merged_headers.append(f"Referer: {referer}")
    merged_headers.extend(headers)

    if merged_headers:
        blob = "".join(f"{h}\r\n" for h in merged_headers)
        args.extend(["-headers", blob])
    return args


def ffmpeg_supports_option(binary_path: str | None, option_name: str) -> bool:
    if not binary_path:
        return False
    cache_key = (binary_path, option_name)
    cached = _FFMPEG_OPTION_SUPPORT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        proc = subprocess.run(
            [binary_path, "-hide_banner", "-h", "full"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=8,
            **subprocess_no_window_kwargs(),
        )
        output = f"{proc.stdout}\n{proc.stderr}"
        supported = proc.returncode == 0 and option_name in output
    except Exception:
        supported = False

    _FFMPEG_OPTION_SUPPORT_CACHE[cache_key] = supported
    return supported


def task_header_args(task: DownloadTask, options: DownloadOptions) -> list[str]:
    merged_headers = list(options.headers)
    for header in task.headers:
        if header not in merged_headers:
            merged_headers.append(header)
    return header_args(task.user_agent or options.user_agent, task.referer or options.referer, merged_headers)


def normalize_header_lines(raw_headers: object) -> list[str]:
    lines: list[str] = []
    if isinstance(raw_headers, dict):
        for key, value in raw_headers.items():
            if key is None or value is None:
                continue
            name = str(key).strip()
            val = str(value).strip()
            if name and val:
                lines.append(f"{name}: {val}")
        return lines

    if isinstance(raw_headers, list):
        for item in raw_headers:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    lines.append(text)
            elif isinstance(item, dict):
                key = str(item.get("name") or item.get("key") or "").strip()
                val = str(item.get("value") or "").strip()
                if key and val:
                    lines.append(f"{key}: {val}")
        return lines

    if isinstance(raw_headers, str):
        for line in raw_headers.splitlines():
            text = line.strip()
            if text:
                lines.append(text)
    return lines


def build_external_filename_hint(payload: dict[str, object]) -> str | None:
    hint = str(payload.get("filename_hint") or payload.get("name") or "").strip()
    if hint:
        return hint

    title = str(payload.get("title") or "").strip()
    if title:
        return title
    return None


def default_download_dir() -> Path:
    locations = QStandardPaths.standardLocations(QStandardPaths.DownloadLocation)
    if locations:
        base = Path(locations[0]).expanduser()
    else:
        base = Path.home() / "Downloads"
    return (base / APP_DISPLAY_NAME).resolve()


def hls_input_args(binary_path: str | None = None) -> list[str]:
    args = [
        "-protocol_whitelist",
        "file,http,https,tcp,tls,crypto,data",
        "-allowed_extensions",
        "ALL",
        "-extension_picky",
        "0",
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "8",
    ]
    if ffmpeg_supports_option(binary_path, "allowed_segment_extensions"):
        args[4:4] = ["-allowed_segment_extensions", "ALL"]
    return args


def subprocess_no_window_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if flags:
        return {"creationflags": flags}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"startupinfo": startupinfo}


def summarize_process_error(proc: subprocess.CompletedProcess[str]) -> str:
    text = (proc.stderr or proc.stdout or "").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return " | ".join(lines[-3:])[-1500:]


def run_ffmpeg_command(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        errors="replace",
        **subprocess_no_window_kwargs(),
    )
    if proc.returncode == 0:
        return True, ""
    return False, summarize_process_error(proc) or "ffmpeg execution failed"


def normalize_repair_error_detail(detail: str | None) -> str:
    if not detail:
        return "ffmpeg 无法读取这个视频文件，可能文件已损坏或格式并非有效 MP4。"
    lowered_detail = detail.lower()
    if "__mp4_mdat_missing_moov__" in lowered_detail:
        return "检测到该文件只剩 MP4 的 ftyp/mdat 结构，缺少 moov 索引。这通常表示下载中断或文件已被截断，建议回到原始 m3u8 重新下载。"
    if "__mp4_mdat_raw_video_failed__" in lowered_detail:
        return "检测到该文件缺少 moov，已尝试把 mdat 当作原始视频流抢救，但没有得到可播放的结果。文件很可能已经严重损坏，建议重新下载。"
    if "__no_recoverable_stream__" in lowered_detail:
        return "未探测到可恢复的音视频流，当前无法自动修复，建议回到原始 m3u8 重新下载。"
    if "error opening input" in lowered_detail or "invalid data found when processing input" in lowered_detail:
        return "ffmpeg 无法读取该视频文件，文件可能已经严重损坏，当前无法自动修复。"

    raw_parts = [part.strip(" ;|{}") for part in detail.split(";")]
    parts: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        if not part or part in {"|", "{ | }"}:
            continue
        lowered = part.lower()
        if lowered == "ffmpeg execution failed":
            part = "ffmpeg 无法读取该视频流"
            lowered = part.lower()
        if lowered not in seen:
            seen.add(lowered)
            parts.append(part)

    if not parts:
        return "ffmpeg 无法读取这个视频文件，可能文件已损坏或格式并非有效 MP4。"
    return "；".join(parts[:3])


def probe_media_format_name(path: Path, options: DownloadOptions, forced_format: str | None = None) -> str | None:
    if not options.ffprobe:
        return None
    cmd = [options.ffprobe, "-hide_banner", "-v", "error"]
    if forced_format:
        cmd.extend(["-f", forced_format])
    cmd.extend(["-show_entries", "format=format_name", "-of", "default=nw=1:nk=1", str(path)])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
            **subprocess_no_window_kwargs(),
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    value = (proc.stdout or "").strip().splitlines()
    return value[0].strip() if value else None


def inspect_mp4_payload_layout(path: Path) -> dict[str, int | bool | None] | None:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            head = fh.read(256 * 1024)
            if not head:
                return None
            tail = b""
            if size > 1024 * 1024:
                fh.seek(max(0, size - 1024 * 1024))
                tail = fh.read(1024 * 1024)
    except OSError:
        return None

    offset = 0
    has_ftyp = False
    has_moov = False
    has_mdat = False
    mdat_payload_offset: int | None = None
    limit = min(len(head), 256 * 1024)
    while offset + 8 <= limit:
        box_size = int.from_bytes(head[offset : offset + 4], "big")
        box_type = head[offset + 4 : offset + 8]
        header_size = 8
        if box_size == 1:
            if offset + 16 > limit:
                break
            box_size = int.from_bytes(head[offset + 8 : offset + 16], "big")
            header_size = 16
        elif box_size == 0:
            box_size = size - offset
        if box_size < header_size:
            break

        if box_type == b"ftyp":
            has_ftyp = True
        elif box_type == b"moov":
            has_moov = True
        elif box_type == b"mdat":
            has_mdat = True
            mdat_payload_offset = offset + header_size
            if box_size == size - offset:
                break

        if box_size <= 0:
            break
        offset += box_size

    if not has_moov and tail:
        has_moov = b"moov" in tail

    if not has_ftyp and not has_moov and not has_mdat:
        return None
    return {
        "has_ftyp": has_ftyp,
        "has_moov": has_moov,
        "has_mdat": has_mdat,
        "mdat_payload_offset": mdat_payload_offset,
    }


def probe_raw_video_stream_format(
    path: Path,
    options: DownloadOptions,
    skip_initial_bytes: int,
) -> str | None:
    if not options.ffprobe:
        return None
    for forced_format in ("h264", "hevc"):
        cmd = [
            options.ffprobe,
            "-hide_banner",
            "-v",
            "error",
            "-skip_initial_bytes",
            str(skip_initial_bytes),
            "-f",
            forced_format,
            "-show_entries",
            "stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=20,
                **subprocess_no_window_kwargs(),
            )
        except Exception:
            continue
        if proc.returncode != 0:
            continue
        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            continue
        for stream in payload.get("streams") or []:
            if stream.get("codec_type") == "video":
                return forced_format
    return None


def build_sidecar_output_path(path: Path, tag: str) -> Path:
    stem = path.stem or "video"
    suffix = path.suffix or ".mp4"
    candidate = path.with_name(f"{stem}.{tag}{suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{stem}.{tag}.{counter}{suffix}")
        counter += 1
    return candidate


def cleanup_file(path: Path | None) -> None:
    if not path:
        return
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def replace_file_atomic(source_path: Path, final_path: Path) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(source_path), str(final_path))


def probe_duration_seconds(task: DownloadTask, options: DownloadOptions) -> float | None:
    if not options.ffprobe:
        return None

    cmd = [
        options.ffprobe,
        "-v",
        "error",
        *hls_input_args(options.ffprobe),
        *task_header_args(task, options),
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        task.url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
            **subprocess_no_window_kwargs(),
        )
    except Exception:
        return None

    if proc.returncode != 0:
        return None

    out = (proc.stdout or "").strip()
    try:
        dur = float(out)
        return dur if dur > 0 else None
    except ValueError:
        return None


def run_ffmpeg_with_progress(
    task: DownloadTask,
    options: DownloadOptions,
    codec_args: list[str],
    duration: float | None,
    on_progress: Callable[[int], None],
    should_abort: Callable[[], str | None] | None = None,
    output_path: Path | None = None,
) -> tuple[bool, str | None]:
    cmd = [
        options.ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-progress",
        "pipe:1",
        "-y" if options.overwrite else "-n",
    ]

    if options.timeout > 0:
        cmd.extend(["-rw_timeout", str(options.timeout * 1_000_000)])

    cmd.extend(hls_input_args(options.ffmpeg))
    cmd.extend(task_header_args(task, options))
    cmd.extend(["-i", task.url])
    cmd.extend(codec_args)
    cmd.append(str(output_path or task.output_path))

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
        **subprocess_no_window_kwargs(),
    )

    def _reader_thread(stream: object, out_queue: "queue.Queue[str | None]") -> None:
        if stream is None:
            out_queue.put(None)
            return
        for line in stream:
            out_queue.put(line)
        out_queue.put(None)

    out_queue: "queue.Queue[str | None]" = queue.Queue()
    reader = threading.Thread(
        target=_reader_thread, args=(proc.stdout, out_queue), daemon=True
    )
    reader.start()

    stall_timeout = options.timeout if options.timeout > 0 else 30
    last_activity = time.monotonic()
    error_lines: list[str] = []
    while True:
        if should_abort:
            abort_status = should_abort()
            if abort_status:
                proc.kill()
                return False, f"__ABORT__:{abort_status}"
        try:
            raw_line = out_queue.get(timeout=1.0)
        except queue.Empty:
            if proc.poll() is not None:
                break
            if should_abort:
                abort_status = should_abort()
                if abort_status:
                    proc.kill()
                    return False, f"__ABORT__:{abort_status}"
            if time.monotonic() - last_activity > stall_timeout:
                proc.kill()
                return False, f"连接超时（{stall_timeout}s 无响应）"
            continue

        if raw_line is None:
            break

        last_activity = time.monotonic()
        line = raw_line.strip()
        if not line:
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            if key == "out_time_ms":
                if duration and duration > 0:
                    try:
                        current_sec = int(value) / 1_000_000
                        percent = max(0, min(99, int((current_sec / duration) * 100)))
                        on_progress(percent)
                    except ValueError:
                        pass
                else:
                    on_progress(-1)
            elif key == "progress" and value == "end":
                on_progress(100)
        else:
            error_lines.append(line)
            if len(error_lines) > 8:
                error_lines = error_lines[-8:]

    return_code = proc.wait()

    if return_code == 0:
        return True, None

    err = " | ".join(error_lines).strip()
    return False, err or "ffmpeg 执行失败"


def validate_output_media(path: Path, options: DownloadOptions) -> tuple[bool, str | None]:
    if not path.exists():
        return False, "输出文件不存在"
    if path.stat().st_size < 256 * 1024:
        return False, "输出文件过小"

    if options.ffprobe:
        probe_cmd = [
            options.ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
        proc = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            errors="replace",
            **subprocess_no_window_kwargs(),
        )
        if proc.returncode != 0:
            detail = summarize_process_error(proc)
            if detail:
                return False, detail
            return False, "ffprobe 校验失败"
        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            return False, "ffprobe 输出异常"
        streams = payload.get("streams") or []
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        if not video_streams:
            return False, "无视频流"
        duration_text = (payload.get("format") or {}).get("duration")
        try:
            if duration_text is not None and float(duration_text) <= 0.4:
                return False, "时长异常"
        except (TypeError, ValueError):
            pass

    # Decode smoke test: many "can't play mp4" cases are detected here.
    test_cmd = [
        options.ffmpeg,
        "-v",
        "error",
        "-ss",
        "0",
        "-t",
        "1.5",
        "-i",
        str(path),
        "-f",
        "null",
        "-",
    ]
    test_proc = subprocess.run(
        test_cmd,
        capture_output=True,
        text=True,
        errors="replace",
        **subprocess_no_window_kwargs(),
    )
    if test_proc.returncode != 0:
        detail = summarize_process_error(test_proc)
        if detail:
            return False, detail
        return False, "解码测试失败"

    return True, None


def repair_media_file(
    source_path: Path,
    options: DownloadOptions,
    on_stage: Callable[[str], None] | None = None,
) -> MediaRepairResult:
    source = source_path.expanduser().resolve()
    mp4_layout = inspect_mp4_payload_layout(source)

    def emit_stage(stage: str) -> None:
        if on_stage:
            on_stage(stage)

    emit_stage("scan")
    media_ok, media_reason = validate_output_media(source, options)
    if media_ok:
        return MediaRepairResult(status="noop")

    final_output = build_sidecar_output_path(source, "fixed")
    working_output = build_sidecar_output_path(final_output, "working")

    def finish_success(method: str) -> MediaRepairResult:
        replace_file_atomic(working_output, final_output)
        return MediaRepairResult(
            status="ok",
            output_path=final_output,
            method=method,
        )

    cleanup_file(working_output)

    repair_input_args = [
        "-analyzeduration",
        "200M",
        "-probesize",
        "200M",
        "-fflags",
        "+genpts+igndts+discardcorrupt",
        "-err_detect",
        "ignore_err",
    ]

    emit_stage("remux")
    remux_cmd = [
        options.ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *repair_input_args,
        "-i",
        str(source),
        "-map",
        "0",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(working_output),
    ]
    ok, err = run_ffmpeg_command(remux_cmd)
    if ok:
        emit_stage("verify")
        repaired_ok, repaired_reason = validate_output_media(working_output, options)
        if repaired_ok:
            return finish_success("remux")
        err = repaired_reason or "invalid repaired output"
        cleanup_file(working_output)

    emit_stage("transcode")
    transcode_cmd = [
        options.ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *repair_input_args,
        "-i",
        str(source),
        "-map",
        "0:v:0?",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(working_output),
    ]
    ok2, err2 = run_ffmpeg_command(transcode_cmd)
    if ok2:
        emit_stage("verify")
        repaired_ok2, repaired_reason2 = validate_output_media(working_output, options)
        if repaired_ok2:
            return finish_success("transcode")
        err2 = repaired_reason2 or "invalid transcoded output"

    raw_format: str | None = None
    raw_err: str | None = None
    raw_err2: str | None = None
    missing_moov_mdat = bool(
        mp4_layout
        and mp4_layout.get("has_ftyp")
        and mp4_layout.get("has_mdat")
        and not mp4_layout.get("has_moov")
        and isinstance(mp4_layout.get("mdat_payload_offset"), int)
    )
    if missing_moov_mdat:
        skip_initial_bytes = int(mp4_layout["mdat_payload_offset"])
        raw_format = probe_raw_video_stream_format(source, options, skip_initial_bytes)
        if raw_format:
            emit_stage("raw_remux")
            raw_remux_cmd = [
                options.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-skip_initial_bytes",
                str(skip_initial_bytes),
                *repair_input_args,
                "-f",
                raw_format,
                "-i",
                str(source),
                "-map",
                "0:v:0?",
                "-an",
                "-c:v",
                "copy",
                "-movflags",
                "+faststart",
                str(working_output),
            ]
            ok_raw, raw_err = run_ffmpeg_command(raw_remux_cmd)
            if ok_raw:
                emit_stage("verify")
                repaired_ok_raw, repaired_reason_raw = validate_output_media(working_output, options)
                if repaired_ok_raw:
                    return finish_success("remux")
                raw_err = repaired_reason_raw or "invalid raw video remux output"
                cleanup_file(working_output)

            emit_stage("raw_transcode")
            raw_transcode_cmd = [
                options.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-skip_initial_bytes",
                str(skip_initial_bytes),
                *repair_input_args,
                "-f",
                raw_format,
                "-i",
                str(source),
                "-map",
                "0:v:0?",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(working_output),
            ]
            ok_raw2, raw_err2 = run_ffmpeg_command(raw_transcode_cmd)
            if ok_raw2:
                emit_stage("verify")
                repaired_ok_raw2, repaired_reason_raw2 = validate_output_media(working_output, options)
                if repaired_ok_raw2:
                    return finish_success("transcode")
                raw_err2 = repaired_reason_raw2 or "invalid raw video transcode output"
                cleanup_file(working_output)
        else:
            raw_err = "__MP4_MDAT_MISSING_MOOV__"

    emit_stage("ts_probe")
    ts_format = probe_media_format_name(source, options, forced_format="mpegts")
    ts_err: str | None = None
    ts_err2: str | None = None
    if ts_format == "mpegts":
        emit_stage("ts_remux")
        ts_remux_cmd = [
            options.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "mpegts",
            *repair_input_args,
            "-ignore_unknown",
            "-i",
            str(source),
            "-map",
            "0:v?",
            "-map",
            "0:a?",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(working_output),
        ]
        ok3, ts_err = run_ffmpeg_command(ts_remux_cmd)
        if ok3:
            emit_stage("verify")
            repaired_ok3, repaired_reason3 = validate_output_media(working_output, options)
            if repaired_ok3:
                return finish_success("remux")
            ts_err = repaired_reason3 or "invalid ts remux output"
            cleanup_file(working_output)

        emit_stage("ts_transcode")
        ts_transcode_cmd = [
            options.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "mpegts",
            *repair_input_args,
            "-ignore_unknown",
            "-i",
            str(source),
            "-map",
            "0:v?",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(working_output),
        ]
        ok4, ts_err2 = run_ffmpeg_command(ts_transcode_cmd)
        if ok4:
            emit_stage("verify")
            repaired_ok4, repaired_reason4 = validate_output_media(working_output, options)
            if repaired_ok4:
                return finish_success("transcode")
            ts_err2 = repaired_reason4 or "invalid ts transcode output"
            cleanup_file(working_output)

    cleanup_file(working_output)
    detail_parts = [media_reason, err or "remux failed", err2 or "transcode failed"]
    if raw_format:
        detail_parts.extend([raw_err or "raw video remux failed", raw_err2 or "raw video transcode failed"])
    if ts_format == "mpegts":
        detail_parts.extend([ts_err or "ts remux failed", ts_err2 or "ts transcode failed"])
        if any("Output file does not contain any stream" in str(part) for part in detail_parts if part):
            detail = normalize_repair_error_detail("__NO_RECOVERABLE_STREAM__")
            return MediaRepairResult(status="failed", detail=detail)
        if any("Output file does not contain any stream" in str(part) for part in detail_parts if part):
            detail_parts = ["检测到该文件更像 TS 残片，但里面没有可恢复的音视频流，建议重新下载原始 m3u8 后再导出。"]
    if missing_moov_mdat and not raw_format:
        detail_parts.append("__MP4_MDAT_MISSING_MOOV__")
    elif missing_moov_mdat:
        detail_parts.append("__MP4_MDAT_RAW_VIDEO_FAILED__")
    detail = normalize_repair_error_detail("; ".join(part for part in detail_parts if part))
    return MediaRepairResult(status="failed", detail=detail)


def download_single_task(
    task: DownloadTask,
    options: DownloadOptions,
    on_stage: Callable[[str], None],
    on_progress: Callable[[int], None],
    should_abort: Callable[[], str | None] | None = None,
) -> tuple[str, str | None]:
    if task.output_path.exists() and not options.overwrite:
        return "skipped", "目标文件已存在"

    duration = probe_duration_seconds(task, options)
    working_output = build_sidecar_output_path(task.output_path, "downloading")

    def cleanup_partial_output() -> None:
        cleanup_file(working_output)

    def finalize_output() -> tuple[bool, str | None]:
        try:
            replace_file_atomic(working_output, task.output_path)
            return True, None
        except OSError as exc:
            cleanup_partial_output()
            return False, str(exc)

    copy_args = [
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        "-movflags",
        "+faststart",
    ]
    transcode_args = [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-vsync",
        "cfr",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
    ]

    last_error: str | None = None
    total_attempts = options.retries + 1

    for attempt in range(1, total_attempts + 1):
        cleanup_partial_output()
        if should_abort:
            abort_status = should_abort()
            if abort_status:
                cleanup_partial_output()
                return abort_status, "任务已中断"

        on_stage(f"下载中（尝试 {attempt}/{total_attempts}）")
        ok, err = run_ffmpeg_with_progress(
            task,
            options,
            copy_args,
            duration,
            on_progress,
            should_abort,
            output_path=working_output,
        )
        if ok:
            if not options.validate_after_copy:
                finalize_ok, finalize_err = finalize_output()
                if finalize_ok:
                    on_progress(100)
                    return "ok", None
                return "failed", f"写入最终文件失败: {finalize_err or 'unknown'}"

            on_stage("校验文件")
            media_ok, media_reason = validate_output_media(working_output, options)
            if media_ok:
                finalize_ok, finalize_err = finalize_output()
                if finalize_ok:
                    on_progress(100)
                    return "ok", None
                return "failed", f"写入最终文件失败: {finalize_err or 'unknown'}"

            if options.transcode_on_fail:
                on_stage("copy 成功但文件异常，转码修复中")
                cleanup_partial_output()
                ok2, err2 = run_ffmpeg_with_progress(
                    task,
                    options,
                    transcode_args,
                    duration,
                    on_progress,
                    should_abort,
                    output_path=working_output,
                )
                if ok2:
                    on_stage("校验文件")
                    media_ok2, media_reason2 = validate_output_media(working_output, options)
                    if media_ok2:
                        finalize_ok, finalize_err = finalize_output()
                        if finalize_ok:
                            on_progress(100)
                            return "ok", "copy 文件异常，已自动转码修复"
                        return "failed", f"写入最终文件失败: {finalize_err or 'unknown'}"
                    cleanup_partial_output()
                    return "failed", f"转码后校验失败: {media_reason2 or 'unknown'}"
                if err2 and err2.startswith("__ABORT__:"):
                    cleanup_partial_output()
                    return err2.split(":", 1)[1], "任务已中断"
                cleanup_partial_output()
                return "failed", f"copy 成功但文件异常({media_reason or 'unknown'}); 转码失败: {err2 or 'unknown'}"

            cleanup_partial_output()
            return "failed", f"copy 成功但文件异常: {media_reason or 'unknown'}"

        if err and err.startswith("__ABORT__:"):
            cleanup_partial_output()
            return err.split(":", 1)[1], "任务已中断"

        last_error = f"copy 失败: {err or 'unknown'}"

        if options.transcode_on_fail:
            cleanup_partial_output()
            on_stage("copy 失败，转码中")
            ok2, err2 = run_ffmpeg_with_progress(
                task,
                options,
                transcode_args,
                duration,
                on_progress,
                should_abort,
                output_path=working_output,
            )
            if ok2:
                on_stage("校验文件")
                media_ok2, media_reason2 = validate_output_media(working_output, options)
                if media_ok2:
                    finalize_ok, finalize_err = finalize_output()
                    if finalize_ok:
                        on_progress(100)
                        return "ok", "copy 失败，已自动转码"
                    return "failed", f"写入最终文件失败: {finalize_err or 'unknown'}"
                cleanup_partial_output()
                last_error = f"{last_error}; 转码后校验失败: {media_reason2 or 'unknown'}"
            elif err2 and err2.startswith("__ABORT__:"):
                cleanup_partial_output()
                return err2.split(":", 1)[1], "任务已中断"
            else:
                cleanup_partial_output()
                last_error = f"{last_error}; transcode 失败: {err2 or 'unknown'}"

        if attempt < total_attempts:
            on_stage("重试等待中")
            wait_time = min(2 * attempt, 8)
            end_time = time.monotonic() + wait_time
            while time.monotonic() < end_time:
                if should_abort:
                    abort_status = should_abort()
                    if abort_status:
                        cleanup_partial_output()
                        return abort_status, "任务已中断"
                time.sleep(0.2)

    cleanup_partial_output()
    return "failed", last_error


class GlowButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 4)
        self._shadow.setColor(QColor(140, 95, 255, 130))
        self.setGraphicsEffect(self._shadow)

        self._pulse = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._pulse.setStartValue(16)
        self._pulse.setEndValue(32)
        self._pulse.setDuration(900)
        self._pulse.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse.setLoopCount(-1)

    def set_busy(self, busy: bool) -> None:
        if busy:
            if self._pulse.state() != QPropertyAnimation.Running:
                self._pulse.start()
        else:
            self._pulse.stop()
            self._shadow.setBlurRadius(18)


class BatchWorker(QObject):
    task_update = Signal(int, str, int, str)
    batch_done = Signal(int, int, int, str)

    def __init__(self, tasks: list[DownloadTask], options: DownloadOptions, jobs: int, output_dir: Path):
        super().__init__()
        self.tasks = tasks
        self.options = options
        self.jobs = max(1, jobs)
        self.output_dir = output_dir
        self._task_map = {task.index: task for task in tasks}
        self._pending: deque[int] = deque(task.index for task in tasks)
        self._manual_paused: set[int] = set()
        self._deleted: set[int] = set()
        self._done: set[int] = set()
        self._global_paused = False
        self._running_controls: dict[int, tuple[threading.Event, list[str]]] = {}
        self._lock = threading.Lock()

    def apply_command(self, action: str, task_index: int | None = None) -> None:
        with self._lock:
            running = set(self._running_controls.keys())

            if action == "pause_all":
                self._global_paused = True
                for idx, (event, reason) in self._running_controls.items():
                    reason[0] = "paused"
                    event.set()
                return

            if action == "resume_all":
                self._global_paused = False
                return

            if action == "delete_all":
                targets = [idx for idx in self._task_map if idx not in self._done]
                for idx in targets:
                    self._deleted.add(idx)
                    self._manual_paused.discard(idx)
                    if idx in running:
                        event, reason = self._running_controls[idx]
                        reason[0] = "deleted"
                        event.set()
                    else:
                        self._done.add(idx)
                        self.task_update.emit(idx, "deleted", 0, "已删除")
                return

            if task_index is None or task_index not in self._task_map:
                return

            if action == "pause":
                if task_index in self._done or task_index in self._deleted:
                    return
                self._manual_paused.add(task_index)
                if task_index in running:
                    event, reason = self._running_controls[task_index]
                    reason[0] = "paused"
                    event.set()
                else:
                    self.task_update.emit(task_index, "paused", 0, "已暂停")
                return

            if action == "resume":
                if task_index in self._done or task_index in self._deleted:
                    return
                self._manual_paused.discard(task_index)
                self.task_update.emit(task_index, "stage", -2, "等待执行")
                return

            if action == "delete":
                if task_index in self._done:
                    return
                self._deleted.add(task_index)
                self._manual_paused.discard(task_index)
                if task_index in running:
                    event, reason = self._running_controls[task_index]
                    reason[0] = "deleted"
                    event.set()
                else:
                    self._done.add(task_index)
                    self.task_update.emit(task_index, "deleted", 0, "已删除")
                return

    def enqueue_tasks(self, tasks: list[DownloadTask]) -> int:
        added = 0
        with self._lock:
            for task in tasks:
                if task.index in self._task_map:
                    continue
                self.tasks.append(task)
                self._task_map[task.index] = task
                self._pending.append(task.index)
                added += 1
        return added

    @Slot()
    def run(self) -> None:
        success = 0
        skipped = 0
        failed = 0
        deleted = 0
        failures: list[tuple[DownloadTask, str]] = []
        
        def run_one(
            task: DownloadTask, stop_event: threading.Event, stop_reason: list[str]
        ) -> tuple[str, DownloadTask, str | None]:
            self.task_update.emit(task.index, "running", 0, "准备中")

            def stage_cb(stage: str) -> None:
                self.task_update.emit(task.index, "stage", -2, stage)

            def progress_cb(percent: int) -> None:
                self.task_update.emit(task.index, "progress", percent, "")

            def should_abort() -> str | None:
                if stop_event.is_set():
                    return stop_reason[0]
                return None

            status, detail = download_single_task(
                task, self.options, stage_cb, progress_cb, should_abort
            )
            return status, task, detail

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.jobs) as pool:
            running_futures: dict[concurrent.futures.Future[tuple[str, DownloadTask, str | None]], int] = {}

            while True:
                with self._lock:
                    pending_active = [
                        idx for idx in self._pending if idx not in self._done and idx not in self._deleted
                    ]

                    if not self._global_paused:
                        spin = len(self._pending)
                        while spin > 0 and len(running_futures) < self.jobs:
                            spin -= 1
                            if not self._pending:
                                break
                            idx = self._pending.popleft()
                            if idx in self._done or idx in self._deleted:
                                continue
                            if idx in self._manual_paused:
                                self._pending.append(idx)
                                continue
                            task = self._task_map[idx]
                            stop_event = threading.Event()
                            stop_reason = ["paused"]
                            self._running_controls[idx] = (stop_event, stop_reason)
                            fut = pool.submit(run_one, task, stop_event, stop_reason)
                            running_futures[fut] = idx

                if not running_futures and not pending_active:
                    break

                if not running_futures:
                    time.sleep(0.12)
                    continue

                done_set, _ = concurrent.futures.wait(
                    running_futures.keys(),
                    timeout=0.25,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done_set:
                    continue

                for future in done_set:
                    idx = running_futures.pop(future)
                    with self._lock:
                        self._running_controls.pop(idx, None)
                    try:
                        status, task, detail = future.result()
                    except Exception as exc:  # pragma: no cover
                        status = "failed"
                        task = self._task_map[idx]
                        detail = str(exc)

                    with self._lock:
                        if status in {"ok", "skipped", "failed", "deleted"}:
                            self._done.add(task.index)
                        if status == "paused" and task.index not in self._deleted:
                            self._pending.append(task.index)

                    if status == "ok":
                        success += 1
                        self.task_update.emit(task.index, "ok", 100, detail or "下载完成")
                    elif status == "skipped":
                        skipped += 1
                        self.task_update.emit(task.index, "skipped", 100, detail or "已跳过")
                    elif status == "paused":
                        self.task_update.emit(task.index, "paused", 0, detail or "已暂停")
                    elif status == "deleted":
                        deleted += 1
                        self.task_update.emit(task.index, "deleted", 0, detail or "已删除")
                    else:
                        failed += 1
                        failures.append((task, detail or "未知错误"))
                        self.task_update.emit(task.index, "failed", 0, detail or "下载失败")

        failure_file = ""
        if failures:
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            failure_path = self.output_dir / f"failed_tasks_{stamp}.txt"
            lines = [
                "# 下载失败任务",
                "# 格式: 文件名|URL|错误",
                "",
            ]
            for task, reason in failures:
                clean_reason = reason.replace("\n", " ").replace("\r", " ")
                lines.append(f"{task.output_path.name}|{task.url}|{clean_reason}")
            failure_path.write_text("\n".join(lines), encoding="utf-8")
            failure_file = str(failure_path)

        self.batch_done.emit(success, skipped + deleted, failed, failure_file)


class RepairWorker(QObject):
    progress = Signal(int, int, str, str)
    finished = Signal(object)

    def __init__(self, sources: list[Path], options: DownloadOptions):
        super().__init__()
        self.sources = sources
        self.options = options

    @Slot()
    def run(self) -> None:
        results: list[tuple[Path, MediaRepairResult]] = []
        total = len(self.sources)
        for current, source in enumerate(self.sources, start=1):
            def emit_stage(stage: str, current_index: int = current, file_name: str = source.name) -> None:
                self.progress.emit(current_index, total, file_name, stage)

            if not source.exists():
                emit_stage("missing")
                results.append(
                    (
                        source,
                        MediaRepairResult(
                            status="failed",
                            detail="source_missing",
                        ),
                    )
                )
            else:
                results.append((source, repair_media_file(source, self.options, emit_stage)))
            self.progress.emit(current, total, source.name, "done")
        self.finished.emit(results)


class HistoryScanWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)

    def __init__(self, entries: list[HistoryEntry], options: DownloadOptions):
        super().__init__()
        self.entries = entries
        self.options = options

    @Slot()
    def run(self) -> None:
        results: list[tuple[int, str, str]] = []
        total = len(self.entries)
        for current, entry in enumerate(self.entries, start=1):
            self.progress.emit(current, total, entry.name)
            target = Path(entry.output_path)
            if not target.exists():
                results.append((entry.id, "missing", "输出文件不存在"))
                continue
            healthy, detail = validate_output_media(target, self.options)
            results.append((entry.id, "ok" if healthy else "broken", detail or ""))
        self.finished.emit(results)


class HoverAwareTableWidget(QTableWidget):
    hoveredRowChanged = Signal(int, int)

    def __init__(self, rows: int, columns: int, parent: QWidget | None = None):
        super().__init__(rows, columns, parent)
        self._hovered_row = -1
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def hovered_row(self) -> int:
        return self._hovered_row

    def _set_hovered_row(self, row: int) -> None:
        if row == self._hovered_row:
            return
        previous = self._hovered_row
        self._hovered_row = row
        self.viewport().update()
        self.hoveredRowChanged.emit(previous, row)

    def mouseMoveEvent(self, event) -> None:
        index = self.indexAt(event.pos())
        self._set_hovered_row(index.row() if index.isValid() else -1)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_hovered_row(-1)
        super().leaveEvent(event)


class TaskRowHoverDelegate(QStyledItemDelegate):
    def __init__(self, table: HoverAwareTableWidget):
        super().__init__(table)
        self._table = table

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        if index.row() == self._table.hovered_row():
            shifted = QStyleOptionViewItem(option)
            shifted.rect = option.rect.adjusted(4, 0, 0, 0)
            super().paint(painter, shifted, index)
            return
        super().paint(painter, option, index)


class AnimatedProgressBar(QProgressBar):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._busy = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._advance_phase)
        self.setTextVisible(True)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy and not self._timer.isActive():
            self._timer.start()
        elif not busy and self.maximum() != 0 and (self.value() <= 0 or self.value() >= 100):
            self._timer.stop()
        self.update()

    def _advance_phase(self) -> None:
        self._phase = (self._phase + 0.045) % 1.4
        self.update()

    def _theme_is_dark(self) -> bool:
        return self.palette().window().color().lightness() < 128

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2.0
        dark = self._theme_is_dark()
        track = QColor("#2a2a2e") if dark else QColor("#f3f5f7")
        border = QColor("#3a3a42") if dark else QColor("#d8dde3")
        text_color = QColor("#ffffff") if dark else QColor("#344054")

        painter.setPen(QPen(border, 1))
        painter.setBrush(track)
        painter.drawRoundedRect(rect, radius, radius)

        if self.maximum() == 0:
            band_width = rect.width() * 0.28
            start = rect.left() + (rect.width() + band_width) * self._phase - band_width
            moving = QRectF(start, rect.top(), band_width, rect.height())
            gradient = QLinearGradient(moving.topLeft(), moving.topRight())
            gradient.setColorAt(0.0, QColor("#ff5c7a"))
            gradient.setColorAt(0.5, QColor("#ff91a8"))
            gradient.setColorAt(1.0, QColor("#ffd3dc"))
            clip = QPainterPath()
            clip.addRoundedRect(rect.adjusted(1, 1, -1, -1), max(1.0, radius - 1), max(1.0, radius - 1))
            painter.save()
            painter.setClipPath(clip)
            painter.fillRect(moving, gradient)
            painter.restore()
        elif self.maximum() > self.minimum():
            progress = (self.value() - self.minimum()) / (self.maximum() - self.minimum())
            progress = max(0.0, min(1.0, progress))
            fill_width = max(rect.height(), rect.width() * progress)
            filled = QRectF(rect.left(), rect.top(), fill_width, rect.height())
            gradient = QLinearGradient(filled.topLeft(), filled.topRight())
            gradient.setColorAt(0.0, QColor("#ff4d73"))
            gradient.setColorAt(0.55, QColor("#ff6f8d"))
            gradient.setColorAt(1.0, QColor("#ffafbf"))
            clip = QPainterPath()
            clip.addRoundedRect(rect.adjusted(1, 1, -1, -1), max(1.0, radius - 1), max(1.0, radius - 1))
            painter.save()
            painter.setClipPath(clip)
            painter.fillRect(filled, gradient)
            if self._busy and 0 < self.value() < 100:
                shimmer_width = max(rect.width() * 0.18, 22.0)
                shimmer_left = rect.left() + (rect.width() + shimmer_width) * self._phase - shimmer_width
                shimmer = QRectF(shimmer_left, rect.top(), shimmer_width, rect.height())
                shimmer_gradient = QLinearGradient(shimmer.topLeft(), shimmer.topRight())
                shimmer_gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
                shimmer_gradient.setColorAt(0.5, QColor(255, 255, 255, 78))
                shimmer_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.fillRect(shimmer, shimmer_gradient)
            painter.restore()

        if self.isTextVisible():
            painter.setPen(text_color)
            painter.drawText(self.rect(), Qt.AlignCenter, self.text())


@dataclass
class LocalApiRequest:
    path: str
    payload: object
    event: threading.Event
    response: dict[str, object] | None = None


class LocalApiHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_callback: Callable[[str, object], dict[str, object]],
    ) -> None:
        super().__init__(server_address, LocalApiRequestHandler)
        self.request_callback = request_callback


class LocalApiRequestHandler(BaseHTTPRequestHandler):
    server_version = "M3U8DownloaderLocalAPI/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_json_body(self) -> object:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != "/ping":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        callback = getattr(self.server, "request_callback", None)
        if not callable(callback):
            self._send_json(500, {"ok": False, "error": "callback_missing"})
            return
        self._send_json(200, callback(self.path, {}))

    def do_POST(self) -> None:
        if self.path not in {"/add-task", "/add-tasks", "/open-window"}:
            self._send_json(404, {"ok": False, "error": "not_found"})
            return

        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid_json"})
            return
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return

        callback = getattr(self.server, "request_callback", None)
        if not callable(callback):
            self._send_json(500, {"ok": False, "error": "callback_missing"})
            return

        try:
            result = callback(self.path, payload)
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})
            return

        status = 200
        if isinstance(result, dict):
            status = int(result.pop("_http_status", 200))
        self._send_json(status, result if isinstance(result, dict) else {"ok": True})


class LocalApiServer:
    def __init__(
        self,
        host: str,
        port: int,
        request_callback: Callable[[str, object], dict[str, object]],
    ) -> None:
        self.host = host
        self.port = port
        self.request_callback = request_callback
        self.httpd: LocalApiHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.httpd:
            return
        self.httpd = LocalApiHTTPServer((self.host, self.port), self.request_callback)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if not self.httpd:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None
        self.thread = None


class MainWindow(QMainWindow):
    update_check_done = Signal(str, str, str)
    local_api_request = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1240, 830)
        self.setWindowIcon(create_app_icon())

        self.current_theme = "light"
        self.current_lang = "zh"
        self.settings_panel_expanded = True
        self.settings_anim: QParallelAnimationGroup | None = None
        self.worker_thread: QThread | None = None
        self.worker: BatchWorker | None = None
        self.repair_thread: QThread | None = None
        self.repair_worker: RepairWorker | None = None
        self.row_by_index: dict[int, int] = {}
        self.progress_by_index: dict[int, QProgressBar] = {}
        self.progress_wrap_by_index: dict[int, QWidget] = {}
        self.action_wrap_by_index: dict[int, QWidget] = {}
        self.pause_btn_by_index: dict[int, QPushButton] = {}
        self.play_btn_by_index: dict[int, QPushButton] = {}
        self.delete_btn_by_index: dict[int, QPushButton] = {}
        self.task_status_by_index: dict[int, str] = {}
        self.task_url_by_index: dict[int, str] = {}
        self.task_output_path_by_index: dict[int, Path] = {}
        self.resume_progress_floor_by_index: dict[int, int] = {}
        self.single_delete_btns: dict[QLineEdit, QPushButton] = {}
        self.pause_all_active = False
        self.update_checking = False
        self.local_api_server: LocalApiServer | None = None
        self.local_api_error: str | None = None
        self.active_page = "download"
        self.nav_buttons: dict[str, QPushButton] = {}
        self.page_index_map: dict[str, int] = {}
        self.repair_output_paths: list[Path] = []
        self.repair_active_sources: list[Path] = []
        self.repair_completed_count = 0
        self.history_scan_thread: QThread | None = None
        self.history_scan_worker: HistoryScanWorker | None = None
        self.history_entries: list[HistoryEntry] = []
        self.history_filtered_entries: list[HistoryEntry] = []
        self.history_visible_entries: list[HistoryEntry] = []
        self.history_media_status_by_id: dict[int, tuple[str, str]] = {}
        self.history_page = 1
        self.history_page_size = 25
        self.history_store: DownloadHistoryStore | None = None
        self.history_store_error: str | None = None
        try:
            self.history_store = DownloadHistoryStore(history_db_path())
        except Exception as exc:
            self.history_store = None
            self.history_store_error = str(exc)

        self._build_ui()
        self._build_menu_bar()
        self.update_check_done.connect(self._on_update_check_done)
        self.local_api_request.connect(self._handle_local_api_request)
        self._apply_theme(self.current_theme)
        self._refresh_i18n_texts()
        self._animate_window_enter()
        self._start_local_api_server()

    def t(self, key: str, **kwargs: object) -> str:
        lang_pack = I18N.get(self.current_lang, I18N["zh"])
        template = lang_pack.get(key) or I18N["zh"].get(key) or key
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def _start_local_api_server(self) -> None:
        try:
            self.local_api_server = LocalApiServer(
                LOCAL_API_HOST,
                LOCAL_API_PORT,
                self._dispatch_local_api_request,
            )
            self.local_api_server.start()
            self.local_api_error = None
        except Exception as exc:
            self.local_api_server = None
            self.local_api_error = str(exc)

    def _dispatch_local_api_request(self, path: str, payload: object) -> dict[str, object]:
        if path == "/ping":
            running = bool(self.worker and self.worker_thread and self.worker_thread.isRunning())
            return {
                "ok": True,
                "app": APP_DISPLAY_NAME,
                "version": APP_VERSION,
                "api_host": LOCAL_API_HOST,
                "api_port": LOCAL_API_PORT,
                "running": running,
                "task_count": self.table.rowCount(),
            }

        request = LocalApiRequest(path=path, payload=payload, event=threading.Event())
        self.local_api_request.emit(request)
        if not request.event.wait(timeout=10):
            return {"ok": False, "error": "client_timeout"}
        return request.response or {"ok": False, "error": "empty_response"}

    def _resolve_output_dir(self) -> Path:
        out_dir_text = self.output_dir_input.text().strip()
        if not out_dir_text:
            raise ValueError(self.t("tip_need_dir"))
        output_dir = Path(out_dir_text).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _build_default_options(self) -> DownloadOptions:
        ffmpeg = check_ffmpeg_bin("ffmpeg")
        return DownloadOptions(
            ffmpeg=ffmpeg,
            ffprobe=resolve_ffprobe_bin(),
            retries=self.retries_input.value(),
            overwrite=False,
            timeout=self.timeout_input.value(),
            user_agent=None,
            referer=None,
            headers=[],
            transcode_on_fail=True,
            validate_after_copy=True,
        )

    def _focus_main_window(self) -> str:
        action = "focused"
        if not self.isVisible():
            self.show()
            action = "opened"
        elif self.isMinimized():
            self.showNormal()
            action = "opened"

        state = self.windowState()
        if state & Qt.WindowMinimized:
            self.setWindowState((state & ~Qt.WindowMinimized) | Qt.WindowActive)
            action = "opened"

        self.show()
        self.raise_()
        self.activateWindow()

        app = QApplication.instance()
        if app is not None:
            app.processEvents()

        return action

    def _current_used_output_names(self) -> set[str]:
        return {
            self.table.item(r, 1).text().strip().lower()
            for r in range(self.table.rowCount())
            if self.table.item(r, 1)
        }

    def _next_task_index(self) -> int:
        return (max(self.row_by_index.keys()) + 1) if self.row_by_index else 1

    def _start_worker_session(
        self,
        tasks: list[DownloadTask],
        options: DownloadOptions,
        jobs: int,
        output_dir: Path,
        *,
        clear_existing: bool,
    ) -> None:
        if not tasks:
            return

        if clear_existing:
            self._clear_table_ui()

        self.pause_all_active = False
        self.pause_all_btn.setText(self.t("pause_all"))
        self.pause_all_btn.setEnabled(True)
        self.clear_tasks_btn.setEnabled(True)

        for task in tasks:
            self._add_table_row(task)

        self.summary_label.setText(self.t("summary_preparing", count=len(tasks)))
        self.start_btn.setEnabled(False)
        self.add_more_btn.setEnabled(True)

        self.worker = BatchWorker(tasks, options, jobs, output_dir)
        self.worker_thread = QThread(self)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.task_update.connect(self._on_task_update)
        self.worker.batch_done.connect(self._on_batch_done)
        self.worker.batch_done.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._on_worker_finished)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.worker_thread.start()

    def _append_tasks_to_active_worker(self, tasks: list[DownloadTask]) -> int:
        if not tasks or not self.worker:
            return 0
        for task in tasks:
            self._add_table_row(task)
        added = self.worker.enqueue_tasks(tasks)
        if added > 0:
            self.pause_all_btn.setEnabled(True)
            self.add_more_btn.setEnabled(True)
            self.summary_label.setText(self.t("summary_added", count=added))
        return added

    def _build_tasks_from_api_payload(
        self,
        items: list[dict[str, object]],
        output_dir: Path,
        start_index: int,
        used_names: set[str],
    ) -> tuple[list[DownloadTask], int, int]:
        tasks: list[DownloadTask] = []
        duplicate_count = 0
        invalid_count = 0
        existing_urls = {u.strip() for u in self.task_url_by_index.values()}
        next_index = start_index

        for item in items:
            url = str(item.get("m3u8_url") or item.get("url") or "").strip()
            if not is_probable_url(url):
                invalid_count += 1
                continue
            if url in existing_urls:
                duplicate_count += 1
                continue

            task = build_task(
                index=next_index,
                url=url,
                output_dir=output_dir,
                used_names=used_names,
                custom_name=build_external_filename_hint(item),
                referer=str(item.get("referer") or item.get("page_url") or "").strip() or None,
                headers=normalize_header_lines(item.get("headers")),
                user_agent=str(item.get("user_agent") or item.get("ua") or "").strip() or None,
                source_page_url=str(item.get("page_url") or "").strip() or None,
            )
            tasks.append(task)
            existing_urls.add(url)
            next_index += 1

        return tasks, duplicate_count, invalid_count

    def _normalize_api_payload_items(self, path: str, payload: object) -> list[dict[str, object]]:
        if path == "/add-task":
            if not isinstance(payload, dict):
                raise ValueError("payload must be an object")
            return [payload]

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            tasks = payload.get("tasks")
            if isinstance(tasks, list):
                return [item for item in tasks if isinstance(item, dict)]
        raise ValueError("payload must contain tasks")

    @Slot(object)
    def _handle_local_api_request(self, request: object) -> None:
        if not isinstance(request, LocalApiRequest):
            return

        try:
            if request.path == "/open-window":
                action = self._focus_main_window()
                request.response = {
                    "ok": True,
                    "action": action,
                }
                return

            items = self._normalize_api_payload_items(request.path, request.payload)
            if not items:
                request.response = {
                    "ok": False,
                    "error": "empty_tasks",
                    "_http_status": 400,
                }
            else:
                if self.worker and self.worker_thread and self.worker_thread.isRunning():
                    output_dir = self.worker.output_dir
                    jobs = self.worker.jobs
                    options = self.worker.options
                    running = True
                else:
                    output_dir = self._resolve_output_dir()
                    jobs = self.jobs_input.value()
                    options = self._build_default_options()
                    running = False

                tasks, duplicate_count, invalid_count = self._build_tasks_from_api_payload(
                    items,
                    output_dir=output_dir,
                    start_index=self._next_task_index(),
                    used_names=self._current_used_output_names(),
                )

                if not tasks:
                    request.response = {
                        "ok": False,
                        "error": "no_valid_tasks",
                        "duplicate_count": duplicate_count,
                        "invalid_count": invalid_count,
                        "_http_status": 400,
                    }
                else:
                    if running:
                        added_count = self._append_tasks_to_active_worker(tasks)
                    else:
                        self._start_worker_session(
                            tasks,
                            options,
                            jobs,
                            output_dir,
                            clear_existing=False,
                        )
                        added_count = len(tasks)

                    if request.path == "/add-task":
                        request.response = {
                            "ok": True,
                            "task_id": str(tasks[0].index),
                            "message": "Task added",
                        }
                    else:
                        request.response = {
                            "ok": True,
                            "task_ids": [str(task.index) for task in tasks],
                            "added_count": added_count,
                            "message": "Tasks added",
                        }
        except ValueError as exc:
            request.response = {"ok": False, "error": str(exc), "_http_status": 400}
        except Exception as exc:
            request.response = {"ok": False, "error": str(exc), "_http_status": 500}
        finally:
            request.event.set()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("root")
        self.setCentralWidget(root)

        shell = QHBoxLayout(root)
        shell.setContentsMargins(16, 16, 16, 16)
        shell.setSpacing(16)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(216)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(18, 20, 18, 18)
        sidebar_layout.setSpacing(14)

        brand_card = QFrame()
        brand_card.setObjectName("sidebarBrand")
        brand_layout = QHBoxLayout(brand_card)
        brand_layout.setContentsMargins(16, 16, 16, 16)
        brand_layout.setSpacing(12)

        self.brand_mark_label = QLabel("桃")
        self.brand_mark_label.setObjectName("brandLogo")
        self.brand_mark_label.setObjectName("brandLogo")
        self.brand_mark_label.setText("")
        self.brand_mark_label.setFixedSize(56, 56)
        self.brand_mark_label.setPixmap(load_brand_logo_pixmap(56))
        self.brand_mark_label.setAlignment(Qt.AlignCenter)
        brand_text_wrap = QWidget()
        brand_text_layout = QVBoxLayout(brand_text_wrap)
        brand_text_layout.setContentsMargins(0, 0, 0, 0)
        brand_text_layout.setSpacing(4)
        self.brand_name_label = QLabel(APP_DISPLAY_NAME)
        self.brand_name_label.setObjectName("brandName")
        self.brand_subtitle_label = QLabel(APP_RELEASE_NAME)
        self.brand_subtitle_label.setObjectName("brandSub")

        brand_text_layout.addWidget(self.brand_name_label)
        brand_text_layout.addWidget(self.brand_subtitle_label)
        brand_layout.addWidget(self.brand_mark_label, 0, Qt.AlignVCenter)
        brand_layout.addWidget(brand_text_wrap, 1)
        sidebar_layout.addWidget(brand_card)

        self.sidebar_caption_label = QLabel("")
        self.sidebar_caption_label.setObjectName("navCaption")
        sidebar_layout.addWidget(self.sidebar_caption_label)

        self.nav_download_btn = self._create_nav_button("download", "nav_download", "download")
        self.nav_directory_btn = self._create_nav_button("directory", "nav_directory", "directory")
        self.nav_repair_btn = self._create_nav_button("repair", "nav_repair", "repair")
        self.nav_history_btn = self._create_nav_button("history", "nav_history", "history")
        self.nav_settings_btn = self._create_nav_button("settings", "nav_settings", "settings")

        sidebar_layout.addWidget(self.nav_download_btn)
        sidebar_layout.addWidget(self.nav_directory_btn)
        sidebar_layout.addWidget(self.nav_repair_btn)
        sidebar_layout.addWidget(self.nav_history_btn)
        sidebar_layout.addWidget(self.nav_settings_btn)
        sidebar_layout.addStretch(1)

        self.sidebar_version_label = QLabel(f"v{APP_VERSION}")
        self.sidebar_version_label.setObjectName("sideVersion")
        sidebar_layout.addWidget(self.sidebar_version_label, 0, Qt.AlignLeft)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.header_card = QFrame()
        self.header_card.setObjectName("headerCard")
        header_layout = QVBoxLayout(self.header_card)
        header_layout.setContentsMargins(24, 20, 24, 20)
        header_layout.setSpacing(4)

        self.page_badge_label = QLabel("")
        self.page_badge_label.setObjectName("pageBadge")
        self.page_title_label = QLabel("")
        self.page_title_label.setObjectName("pageTitle")
        self.page_subtitle_label = QLabel("")
        self.page_subtitle_label.setObjectName("pageSubtitle")
        self.page_subtitle_label.setWordWrap(True)

        header_layout.addWidget(self.page_badge_label, 0, Qt.AlignLeft)
        header_layout.addWidget(self.page_title_label)
        header_layout.addWidget(self.page_subtitle_label)
        content_layout.addWidget(self.header_card)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("pageStack")
        content_layout.addWidget(self.page_stack, 1)

        download_page = QWidget()
        download_layout = QVBoxLayout(download_page)
        download_layout.setContentsMargins(0, 0, 0, 0)
        download_layout.setSpacing(16)

        input_card = QFrame()
        input_card.setObjectName("card")
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(18, 16, 18, 16)
        input_layout.setSpacing(10)

        self.input_title_label = QLabel("")
        self.input_title_label.setObjectName("sectionTitle")

        self.input_tabs = QTabWidget()
        self.input_tabs.setObjectName("inputTabs")
        self.input_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.input_tabs.currentChanged.connect(self._refresh_input_tabs_height)

        single_tab = QWidget()
        single_layout = QVBoxLayout(single_tab)
        single_layout.setContentsMargins(6, 8, 6, 6)
        single_layout.setSpacing(8)

        self.single_scroll = QScrollArea()
        self.single_scroll.setObjectName("singleScroll")
        self.single_scroll.setWidgetResizable(True)
        self.single_scroll.setFrameShape(QFrame.NoFrame)
        self.single_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.single_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.single_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.single_container = QWidget()
        self.single_container.setObjectName("singleContainer")
        self.single_lines_layout = QVBoxLayout(self.single_container)
        self.single_lines_layout.setContentsMargins(2, 2, 2, 2)
        self.single_lines_layout.setSpacing(8)
        self.single_url_inputs: list[QLineEdit] = []
        self._append_single_input_row()
        self._refresh_single_input_scroll_height()

        self.single_scroll.setWidget(self.single_container)
        single_layout.addWidget(self.single_scroll, 0)

        batch_tab = QWidget()
        batch_layout = QVBoxLayout(batch_tab)
        batch_layout.setContentsMargins(6, 8, 6, 10)
        batch_layout.setSpacing(8)

        batch_head = QHBoxLayout()
        batch_head.setContentsMargins(0, 0, 0, 0)
        batch_head.setSpacing(8)
        self.batch_hint_label = QLabel("")
        self.batch_hint_label.setObjectName("inputHintLabel")
        self.batch_clear_btn = QPushButton("")
        self.batch_clear_btn.setObjectName("miniBtn")
        self.batch_clear_btn.clicked.connect(lambda: self.url_input.clear())
        batch_head.addWidget(self.batch_hint_label, 1)
        batch_head.addWidget(self.batch_clear_btn, 0, Qt.AlignRight)

        self.url_input = QTextEdit()
        self.url_input.setObjectName("urlInput")
        self.url_input.setMinimumHeight(96)
        self.url_input.setMaximumHeight(132)
        batch_layout.addLayout(batch_head)
        batch_layout.addWidget(self.url_input, 1)

        self.input_tabs.addTab(single_tab, "")
        self.input_tabs.addTab(batch_tab, "")
        input_layout.addWidget(self.input_title_label)
        input_layout.addWidget(self.input_tabs)
        self._refresh_input_tabs_height()
        download_layout.addWidget(input_card)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.start_btn = QPushButton("")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setMinimumHeight(44)
        self.start_btn.clicked.connect(self._start_download)

        self.add_more_btn = QPushButton("")
        self.add_more_btn.setObjectName("tableActionBtn")
        self.add_more_btn.setMinimumHeight(44)
        self.add_more_btn.setEnabled(False)
        self.add_more_btn.clicked.connect(self._append_tasks_while_running)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("summaryLabel")
        self.summary_label.setWordWrap(True)

        action_row.addWidget(self.start_btn, 0)
        action_row.addWidget(self.add_more_btn, 0)
        action_row.addWidget(self.summary_label, 1)
        download_layout.addLayout(action_row)

        table_card = QFrame()
        table_card.setObjectName("card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 14, 16, 14)
        table_layout.setSpacing(10)

        table_head = QHBoxLayout()
        table_head.setSpacing(10)
        self.table_title_label = QLabel("")
        self.table_title_label.setObjectName("sectionTitle")
        table_head.addWidget(self.table_title_label)
        table_head.addStretch(1)

        self.pause_all_btn = QPushButton("")
        self.pause_all_btn.setObjectName("tableActionBtn")
        self.pause_all_btn.setMinimumHeight(36)
        self.pause_all_btn.clicked.connect(self._toggle_pause_all)
        self.pause_all_btn.setEnabled(False)

        self.open_folder_btn = QPushButton("")
        self.open_folder_btn.setObjectName("tableActionBtn")
        self.open_folder_btn.setMinimumHeight(36)
        self.open_folder_btn.clicked.connect(self._open_download_folder)

        self.clear_tasks_btn = QPushButton("")
        self.clear_tasks_btn.setObjectName("dangerBtn")
        self.clear_tasks_btn.setMinimumHeight(36)
        self.clear_tasks_btn.clicked.connect(self._clear_tasks_confirm)

        table_head.addWidget(self.pause_all_btn)
        table_head.addWidget(self.open_folder_btn)
        table_head.addWidget(self.clear_tasks_btn)

        self.table = HoverAwareTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "", "", "", "", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setItemDelegate(TaskRowHoverDelegate(self.table))
        self.table.hoveredRowChanged.connect(self._on_task_table_hovered_row_changed)
        self.table.cellClicked.connect(self._on_task_table_cell_clicked)

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.Interactive)
        header_view.setSectionResizeMode(5, QHeaderView.Interactive)
        self.table.setColumnWidth(4, 260)
        self.table.setColumnWidth(5, 208)

        table_layout.addLayout(table_head)
        table_layout.addWidget(self.table)
        download_layout.addWidget(table_card, 1)

        directory_page = QWidget()
        directory_layout = QVBoxLayout(directory_page)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.setSpacing(16)

        directory_card = QFrame()
        directory_card.setObjectName("card")
        directory_card_layout = QVBoxLayout(directory_card)
        directory_card_layout.setContentsMargins(24, 24, 24, 24)
        directory_card_layout.setSpacing(12)

        self.output_label = QLabel("")
        self.output_label.setObjectName("fieldLabel")
        self.output_dir_input = QLineEdit(str(default_download_dir()))
        self.output_dir_input.setObjectName("pathInput")
        self.output_dir_input.setMinimumHeight(44)

        directory_actions = QHBoxLayout()
        directory_actions.setSpacing(10)
        self.browse_btn = QPushButton("")
        self.browse_btn.setObjectName("secondaryBtn")
        self.browse_btn.setMinimumHeight(42)
        self.browse_btn.clicked.connect(self._choose_output_dir)
        self.directory_open_btn = QPushButton("")
        self.directory_open_btn.setObjectName("tableActionBtn")
        self.directory_open_btn.setMinimumHeight(42)
        self.directory_open_btn.clicked.connect(self._open_download_folder)
        directory_actions.addWidget(self.browse_btn)
        directory_actions.addWidget(self.directory_open_btn)
        directory_actions.addStretch(1)

        self.dir_hint_label = QLabel("")
        self.dir_hint_label.setObjectName("hintText")
        self.dir_hint_label.setWordWrap(True)

        directory_card_layout.addWidget(self.output_label)
        directory_card_layout.addWidget(self.output_dir_input)
        directory_card_layout.addLayout(directory_actions)
        directory_card_layout.addWidget(self.dir_hint_label)
        directory_layout.addWidget(directory_card)
        directory_layout.addStretch(1)

        repair_page = QWidget()
        repair_layout = QVBoxLayout(repair_page)
        repair_layout.setContentsMargins(0, 0, 0, 0)
        repair_layout.setSpacing(16)

        repair_card = QFrame()
        repair_card.setObjectName("card")
        repair_card_layout = QVBoxLayout(repair_card)
        repair_card_layout.setContentsMargins(20, 20, 20, 20)
        repair_card_layout.setSpacing(12)

        self.repair_file_label = QLabel("")
        self.repair_file_label.setObjectName("fieldLabel")
        self.repair_hint_label = QLabel("")
        self.repair_hint_label.setObjectName("hintText")
        self.repair_hint_label.setWordWrap(True)
        self.repair_path_input = QTextEdit()
        self.repair_path_input.setObjectName("repairInput")
        self.repair_path_input.setMinimumHeight(96)
        self.repair_path_input.setMaximumHeight(132)

        repair_actions = QHBoxLayout()
        repair_actions.setSpacing(10)
        self.repair_choose_btn = QPushButton("")
        self.repair_choose_btn.setObjectName("secondaryBtn")
        self.repair_choose_btn.setMinimumHeight(42)
        self.repair_choose_btn.clicked.connect(self._choose_repair_files)
        self.repair_start_btn = QPushButton("")
        self.repair_start_btn.setObjectName("primaryBtn")
        self.repair_start_btn.setMinimumHeight(42)
        self.repair_start_btn.clicked.connect(self._run_repair_from_page)
        self.repair_open_btn = QPushButton("")
        self.repair_open_btn.setObjectName("tableActionBtn")
        self.repair_open_btn.setMinimumHeight(42)
        self.repair_open_btn.setEnabled(False)
        self.repair_open_btn.clicked.connect(self._open_repaired_output)
        repair_actions.addWidget(self.repair_choose_btn)
        repair_actions.addWidget(self.repair_start_btn)
        repair_actions.addWidget(self.repair_open_btn)
        repair_actions.addStretch(1)

        self.repair_status_label = QLabel("")
        self.repair_status_label.setObjectName("hintText")
        self.repair_status_label.setWordWrap(True)
        self.repair_progress_label = QLabel("")
        self.repair_progress_label.setObjectName("hintText")
        self.repair_progress_label.setVisible(False)
        self.repair_progress_bar = AnimatedProgressBar()
        self.repair_progress_bar.setRange(0, 100)
        self.repair_progress_bar.setValue(0)
        self.repair_progress_bar.setFormat("%p%")
        self.repair_progress_bar.setVisible(False)

        repair_card_layout.addWidget(self.repair_file_label)
        repair_card_layout.addWidget(self.repair_hint_label)
        repair_card_layout.addWidget(self.repair_path_input)
        repair_card_layout.addLayout(repair_actions)
        repair_card_layout.addWidget(self.repair_progress_label)
        repair_card_layout.addWidget(self.repair_progress_bar)
        repair_card_layout.addWidget(self.repair_status_label)
        repair_layout.addWidget(repair_card)
        repair_layout.addStretch(1)

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(16)

        history_filter_card = QFrame()
        history_filter_card.setObjectName("card")
        history_filter_layout = QVBoxLayout(history_filter_card)
        history_filter_layout.setContentsMargins(20, 18, 20, 18)
        history_filter_layout.setSpacing(12)

        self.history_filters_title_label = QLabel("")
        self.history_filters_title_label.setObjectName("sectionTitle")

        history_filters_grid = QHBoxLayout()
        history_filters_grid.setSpacing(10)

        self.history_code_input = QLineEdit()
        self.history_code_input.setObjectName("pathInput")
        self.history_code_input.setMinimumHeight(42)
        self.history_code_input.returnPressed.connect(lambda: self._refresh_history_view(reset_page=True))

        self.history_name_input = QLineEdit()
        self.history_name_input.setObjectName("pathInput")
        self.history_name_input.setMinimumHeight(42)
        self.history_name_input.returnPressed.connect(lambda: self._refresh_history_view(reset_page=True))

        self.history_url_input = QLineEdit()
        self.history_url_input.setObjectName("pathInput")
        self.history_url_input.setMinimumHeight(42)
        self.history_url_input.returnPressed.connect(lambda: self._refresh_history_view(reset_page=True))

        self.history_status_filter = QComboBox()
        self.history_status_filter.setObjectName("choiceSelect")
        self.history_status_filter.setMinimumHeight(42)
        self.history_status_filter.currentIndexChanged.connect(lambda _=0: self._refresh_history_view(reset_page=True))

        history_filters_grid.addWidget(self.history_code_input, 1)
        history_filters_grid.addWidget(self.history_name_input, 2)
        history_filters_grid.addWidget(self.history_url_input, 3)
        history_filters_grid.addWidget(self.history_status_filter, 1)

        history_filter_actions = QHBoxLayout()
        history_filter_actions.setSpacing(10)
        self.history_search_btn = QPushButton("")
        self.history_search_btn.setObjectName("secondaryBtn")
        self.history_search_btn.setMinimumHeight(40)
        self.history_search_btn.clicked.connect(lambda: self._refresh_history_view(reset_page=True))

        self.history_reset_btn = QPushButton("")
        self.history_reset_btn.setObjectName("tableActionBtn")
        self.history_reset_btn.setMinimumHeight(40)
        self.history_reset_btn.clicked.connect(self._reset_history_filters)

        history_filter_actions.addWidget(self.history_search_btn)
        history_filter_actions.addWidget(self.history_reset_btn)
        history_filter_actions.addStretch(1)

        history_filter_layout.addWidget(self.history_filters_title_label)
        history_filter_layout.addLayout(history_filters_grid)
        history_filter_layout.addLayout(history_filter_actions)
        history_layout.addWidget(history_filter_card)

        history_table_card = QFrame()
        history_table_card.setObjectName("card")
        history_table_layout = QVBoxLayout(history_table_card)
        history_table_layout.setContentsMargins(16, 14, 16, 14)
        history_table_layout.setSpacing(10)

        history_table_head = QHBoxLayout()
        history_table_head.setSpacing(10)
        self.history_actions_title_label = QLabel("")
        self.history_actions_title_label.setObjectName("sectionTitle")
        history_table_head.addWidget(self.history_actions_title_label)
        history_table_head.addStretch(1)

        self.history_scan_btn = QPushButton("")
        self.history_scan_btn.setObjectName("tableActionBtn")
        self.history_scan_btn.setMinimumHeight(36)
        self.history_scan_btn.clicked.connect(self._scan_history_filtered_entries)

        self.history_redownload_selected_btn = QPushButton("")
        self.history_redownload_selected_btn.setObjectName("secondaryBtn")
        self.history_redownload_selected_btn.setMinimumHeight(36)
        self.history_redownload_selected_btn.clicked.connect(self._redownload_selected_history_entries)

        self.history_redownload_page_btn = QPushButton("")
        self.history_redownload_page_btn.setObjectName("tableActionBtn")
        self.history_redownload_page_btn.setMinimumHeight(36)
        self.history_redownload_page_btn.clicked.connect(self._redownload_current_history_page)

        self.history_delete_selected_btn = QPushButton("")
        self.history_delete_selected_btn.setObjectName("dangerBtn")
        self.history_delete_selected_btn.setMinimumHeight(36)
        self.history_delete_selected_btn.clicked.connect(self._delete_selected_history_entries)

        history_table_head.addWidget(self.history_scan_btn)
        history_table_head.addWidget(self.history_redownload_selected_btn)
        history_table_head.addWidget(self.history_redownload_page_btn)
        history_table_head.addWidget(self.history_delete_selected_btn)

        self.history_summary_label = QLabel("")
        self.history_summary_label.setObjectName("summaryLabel")
        self.history_summary_label.setWordWrap(True)

        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(["", "", "", "", "", "", ""])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setFocusPolicy(Qt.StrongFocus)
        self.history_table.setColumnHidden(0, True)

        history_header = self.history_table.horizontalHeader()
        history_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        history_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        history_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        history_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        history_header.setSectionResizeMode(4, QHeaderView.Stretch)
        history_header.setSectionResizeMode(5, QHeaderView.Interactive)
        history_header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.history_table.setColumnWidth(5, 280)

        history_pagination = QHBoxLayout()
        history_pagination.setSpacing(10)
        self.history_prev_btn = QPushButton("")
        self.history_prev_btn.setObjectName("tableActionBtn")
        self.history_prev_btn.setMinimumHeight(34)
        self.history_prev_btn.clicked.connect(self._show_prev_history_page)

        self.history_page_label = QLabel("")
        self.history_page_label.setObjectName("summaryLabel")

        self.history_next_btn = QPushButton("")
        self.history_next_btn.setObjectName("tableActionBtn")
        self.history_next_btn.setMinimumHeight(34)
        self.history_next_btn.clicked.connect(self._show_next_history_page)

        history_pagination.addWidget(self.history_prev_btn)
        history_pagination.addWidget(self.history_page_label)
        history_pagination.addWidget(self.history_next_btn)
        history_pagination.addStretch(1)

        history_table_layout.addLayout(history_table_head)
        history_table_layout.addWidget(self.history_summary_label)
        history_table_layout.addWidget(self.history_table, 1)
        history_table_layout.addLayout(history_pagination)
        history_layout.addWidget(history_table_card, 1)

        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(16)

        interface_card = QFrame()
        interface_card.setObjectName("card")
        interface_layout = QVBoxLayout(interface_card)
        interface_layout.setContentsMargins(24, 24, 24, 24)
        interface_layout.setSpacing(12)

        self.settings_title_label = QLabel("")
        self.settings_title_label.setObjectName("sectionTitle")

        self.lang_label = QLabel("")
        self.lang_label.setObjectName("fieldLabel")
        self.lang_select = QComboBox()
        self.lang_select.setObjectName("choiceSelect")
        self.lang_select.setMinimumHeight(42)
        for code in LANG_ORDER:
            self.lang_select.addItem(LANG_LABEL.get(code, code), code)
        self.lang_select.currentIndexChanged.connect(self._on_language_changed)

        self.theme_label = QLabel("")
        self.theme_label.setObjectName("fieldLabel")
        theme_switch_row = QHBoxLayout()
        theme_switch_row.setContentsMargins(0, 0, 0, 0)
        theme_switch_row.setSpacing(10)
        self.theme_light_btn = QPushButton("")
        self.theme_light_btn.setObjectName("themeOptionBtn")
        self.theme_light_btn.setCheckable(True)
        self.theme_light_btn.setAutoExclusive(True)
        self.theme_light_btn.setMinimumHeight(42)
        self.theme_light_btn.clicked.connect(lambda checked=False: self._on_theme_button_clicked("light"))
        self.theme_dark_btn = QPushButton("")
        self.theme_dark_btn.setObjectName("themeOptionBtn")
        self.theme_dark_btn.setCheckable(True)
        self.theme_dark_btn.setAutoExclusive(True)
        self.theme_dark_btn.setMinimumHeight(42)
        self.theme_dark_btn.clicked.connect(lambda checked=False: self._on_theme_button_clicked("dark"))
        theme_switch_row.addWidget(self.theme_light_btn)
        theme_switch_row.addWidget(self.theme_dark_btn)
        theme_switch_row.addStretch(1)

        interface_layout.addWidget(self.settings_title_label)
        interface_layout.addWidget(self.lang_label)
        interface_layout.addWidget(self.lang_select)
        interface_layout.addWidget(self.theme_label)
        interface_layout.addLayout(theme_switch_row)
        settings_layout.addWidget(interface_card)

        tuning_card = QFrame()
        tuning_card.setObjectName("card")
        tuning_layout = QVBoxLayout(tuning_card)
        tuning_layout.setContentsMargins(24, 24, 24, 24)
        tuning_layout.setSpacing(12)

        self.settings_download_label = QLabel("")
        self.settings_download_label.setObjectName("sectionTitle")

        self.jobs_label = QLabel("")
        self.jobs_label.setObjectName("fieldLabel")
        self.jobs_input = QSpinBox()
        self.jobs_input.setObjectName("spinBox")
        self.jobs_input.setRange(10, 200)
        self.jobs_input.setSingleStep(10)
        self.jobs_input.setValue(20)
        self.jobs_input.setMinimumHeight(42)

        self.retries_label = QLabel("")
        self.retries_label.setObjectName("fieldLabel")
        self.retries_input = QSpinBox()
        self.retries_input.setObjectName("spinBox")
        self.retries_input.setRange(0, 10)
        self.retries_input.setValue(2)
        self.retries_input.setMinimumHeight(42)

        self.timeout_label = QLabel("")
        self.timeout_label.setObjectName("fieldLabel")
        self.timeout_input = QSpinBox()
        self.timeout_input.setObjectName("spinBox")
        self.timeout_input.setRange(30, 600)
        self.timeout_input.setSingleStep(15)
        self.timeout_input.setValue(120)
        self.timeout_input.setSuffix(" s")
        self.timeout_input.setMinimumHeight(42)

        self.settings_version_label = QLabel("")
        self.settings_version_label.setObjectName("fieldLabel")
        self.version_btn = QPushButton("")
        self.version_btn.setObjectName("secondaryBtn")
        self.version_btn.setMinimumHeight(42)
        self.version_btn.clicked.connect(self._check_updates)

        tuning_layout.addWidget(self.settings_download_label)
        tuning_layout.addWidget(self.jobs_label)
        tuning_layout.addWidget(self.jobs_input)
        tuning_layout.addWidget(self.retries_label)
        tuning_layout.addWidget(self.retries_input)
        tuning_layout.addWidget(self.timeout_label)
        tuning_layout.addWidget(self.timeout_input)
        tuning_layout.addWidget(self.settings_version_label)
        tuning_layout.addWidget(self.version_btn)
        settings_layout.addWidget(tuning_card)
        settings_layout.addStretch(1)

        self.page_index_map = {
            "download": self.page_stack.addWidget(download_page),
            "directory": self.page_stack.addWidget(directory_page),
            "repair": self.page_stack.addWidget(repair_page),
            "history": self.page_stack.addWidget(history_page),
            "settings": self.page_stack.addWidget(settings_page),
        }

        shell.addWidget(self.sidebar, 0)
        shell.addWidget(content, 1)

        self._refresh_theme_options()
        self._set_active_page("download")

    def _create_nav_button(self, icon_key: str, text_key: str, page_key: str) -> QPushButton:
        btn = QPushButton("")
        btn.setObjectName("navButton")
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setProperty("icon_key", icon_key)
        btn.setProperty("text_key", text_key)
        btn.setIconSize(QSize(18, 18))
        btn.setMinimumHeight(44)
        btn.clicked.connect(lambda checked=False, key=page_key: self._set_active_page(key))
        self.nav_buttons[page_key] = btn
        return btn

    def _nav_icon_color(self, active: bool) -> QColor:
        if self.current_theme == "dark":
            return QColor("#ff8da4" if active else "#f2edf0")
        return QColor("#ff385c" if active else "#3f3f3f")

    def _refresh_nav_button_icons(self) -> None:
        for key, btn in self.nav_buttons.items():
            icon_key = str(btn.property("icon_key") or "")
            btn.setIcon(create_nav_icon(icon_key, self._nav_icon_color(key == self.active_page)))

    def _build_menu_bar(self) -> None:
        self.file_menu = self.menuBar().addMenu("")
        self.tools_menu = self.menuBar().addMenu("")

        self.repair_video_action = QAction(self)
        self.repair_video_action.triggered.connect(self._repair_video_from_menu)
        self.tools_menu.addAction(self.repair_video_action)

        self.exit_action = QAction(self)
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.exit_action)

    def _animate_window_enter(self) -> None:
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(360)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _animate_theme_switch(self) -> None:
        self.setWindowOpacity(0.95)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setStartValue(0.95)
        anim.setEndValue(1.0)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _on_language_changed(self, index: int) -> None:
        code = self.lang_select.itemData(index)
        if not isinstance(code, str) or code == self.current_lang:
            return
        self.current_lang = code
        self._refresh_i18n_texts()

    def _on_theme_button_clicked(self, theme: str) -> None:
        if not isinstance(theme, str) or theme == self.current_theme:
            return
        self.current_theme = theme
        self._apply_theme(self.current_theme)
        self._refresh_theme_options()
        self._animate_theme_switch()

    def _refresh_theme_options(self) -> None:
        if not hasattr(self, "theme_light_btn"):
            return
        light_active = self.current_theme == "light"
        dark_active = self.current_theme == "dark"
        light_color = QColor("#ff385c" if light_active else "#7f8a98")
        dark_color = QColor("#ff8da4" if dark_active else "#7f8a98")

        self.theme_light_btn.blockSignals(True)
        self.theme_dark_btn.blockSignals(True)
        self.theme_light_btn.setChecked(light_active)
        self.theme_dark_btn.setChecked(dark_active)
        self.theme_light_btn.setIcon(create_theme_icon("light", light_color))
        self.theme_dark_btn.setIcon(create_theme_icon("dark", dark_color))
        self.theme_light_btn.setIconSize(QSize(18, 18))
        self.theme_dark_btn.setIconSize(QSize(18, 18))
        self.theme_light_btn.setText(self.t("theme_light"))
        self.theme_dark_btn.setText(self.t("theme_dark"))
        self.theme_light_btn.setToolTip(self.t("theme_light_tip"))
        self.theme_dark_btn.setToolTip(self.t("theme_dark_tip"))
        self.theme_light_btn.blockSignals(False)
        self.theme_dark_btn.blockSignals(False)

    def _set_active_page(self, page_key: str) -> None:
        index = self.page_index_map.get(page_key)
        if index is None:
            return
        self.active_page = page_key
        self.page_stack.setCurrentIndex(index)
        for key, btn in self.nav_buttons.items():
            btn.setChecked(key == page_key)
        self._refresh_nav_button_icons()
        self._update_page_header()
        if page_key == "history":
            self._refresh_history_view()

    def _update_page_header(self) -> None:
        page_meta = {
            "download": ("page_download_title", "page_download_sub"),
            "directory": ("page_directory_title", "page_directory_sub"),
            "repair": ("page_repair_title", "page_repair_sub"),
            "history": ("page_history_title", "page_history_sub"),
            "settings": ("page_settings_title", "page_settings_sub"),
        }
        title_key, sub_key = page_meta.get(self.active_page, page_meta["download"])
        self.header_card.setVisible(self.active_page != "download")
        self.page_badge_label.setText(self.t("page_badge"))
        self.page_title_label.setText(self.t(title_key))
        self.page_subtitle_label.setText(self.t(sub_key))

    def _refresh_i18n_texts(self) -> None:
        self.brand_name_label.setText(APP_DISPLAY_NAME)
        self.brand_subtitle_label.setText(APP_RELEASE_NAME)
        self.sidebar_caption_label.setText(self.t("sidebar_caption"))
        for btn in self.nav_buttons.values():
            text_key = btn.property("text_key") or ""
            btn.setText(self.t(str(text_key)))
        self._refresh_nav_button_icons()

        self.input_title_label.setText(self.t("input_title"))
        self.batch_hint_label.setText(self.t("batch_hint"))
        self.batch_clear_btn.setText(self.t("batch_clear"))
        self.start_btn.setText(self.t("start"))
        self.add_more_btn.setText(self.t("add_more"))
        self.table_title_label.setText(self.t("task_progress"))
        self.pause_all_btn.setText(self.t("resume_all") if self.pause_all_active else self.t("pause_all"))
        self.open_folder_btn.setText(self.t("open_folder"))
        self.clear_tasks_btn.setText(self.t("clear_tasks"))
        if not self.summary_label.text():
            self.summary_label.setText(self.t("summary_wait"))

        self.input_tabs.setTabText(0, self.t("tab_single"))
        self.input_tabs.setTabText(1, self.t("tab_batch"))
        self.url_input.setPlaceholderText(self.t("batch_placeholder"))
        for line in self.single_url_inputs:
            line.setPlaceholderText(self.t("single_placeholder"))
        for delete_btn in self.single_delete_btns.values():
            delete_btn.setText(self.t("row_delete"))

        self.output_label.setText(self.t("output_dir"))
        self.browse_btn.setText(self.t("choose_dir"))
        self.directory_open_btn.setText(self.t("open_folder"))
        self.dir_hint_label.setText(self.t("dir_hint"))

        self.repair_file_label.setText(self.t("repair_file_label"))
        self.repair_hint_label.setText(self.t("repair_file_hint"))
        self.repair_path_input.setPlaceholderText(self.t("repair_placeholder"))
        self.repair_choose_btn.setText(self.t("repair_choose"))
        self.repair_start_btn.setText(self.t("repair_running") if self.repair_thread else self.t("repair_start"))
        self.repair_open_btn.setText(self.t("repair_open_output"))
        if not self.repair_status_label.text():
            self.repair_status_label.setText(self.t("repair_idle"))
        if self.repair_progress_label.isVisible() and self.repair_active_sources:
            total = len(self.repair_active_sources)
            current = min(self.repair_completed_count, total)
            self.repair_progress_label.setText(self.t("repair_progress", current=current, total=total))

        self.history_filters_title_label.setText(self.t("history_filters_title"))
        self.history_actions_title_label.setText(self.t("history_actions_title"))
        self.history_code_input.setPlaceholderText(self.t("history_code"))
        self.history_name_input.setPlaceholderText(self.t("history_name"))
        self.history_url_input.setPlaceholderText(self.t("history_url"))
        self.history_search_btn.setText(self.t("history_search"))
        self.history_reset_btn.setText(self.t("history_reset"))
        self.history_scan_btn.setText(self.t("history_scan"))
        self.history_redownload_selected_btn.setText(self.t("history_redownload_selected"))
        self.history_redownload_page_btn.setText(self.t("history_redownload_page"))
        self.history_delete_selected_btn.setText(self.t("history_delete_selected"))
        self.history_prev_btn.setText(self.t("history_page_prev"))
        self.history_next_btn.setText(self.t("history_page_next"))
        current_status = self.history_status_filter.currentData() if hasattr(self, "history_status_filter") else "all"
        history_status_items = [
            ("all", self.t("history_status_all")),
            ("unknown", self.t("history_status_unknown")),
            ("ok", self.t("history_status_ok")),
            ("broken", self.t("history_status_broken")),
            ("missing", self.t("history_status_missing")),
            ("issue", self.t("history_status_issue")),
        ]
        self.history_status_filter.blockSignals(True)
        self.history_status_filter.clear()
        for value, label in history_status_items:
            self.history_status_filter.addItem(label, value)
        target_status_index = self.history_status_filter.findData(current_status)
        self.history_status_filter.setCurrentIndex(max(0, target_status_index))
        self.history_status_filter.blockSignals(False)
        self.history_table.setHorizontalHeaderLabels(
            [
                self.t("history_col_id"),
                self.t("history_col_code"),
                self.t("history_col_name"),
                self.t("history_col_status"),
                self.t("history_col_path"),
                self.t("history_col_url"),
                self.t("history_col_updated"),
            ]
        )

        self.settings_title_label.setText(self.t("settings_title"))
        self.lang_label.setText(self.t("settings_lang"))
        self.theme_label.setText(self.t("settings_theme"))
        self.settings_download_label.setText(self.t("settings_download"))
        self.jobs_label.setText(self.t("jobs"))
        self.retries_label.setText(self.t("retries"))
        self.timeout_label.setText(self.t("timeout"))
        self.settings_version_label.setText(self.t("settings_version"))

        self.lang_select.blockSignals(True)
        for code in LANG_ORDER:
            idx = self.lang_select.findData(code)
            if idx >= 0:
                self.lang_select.setItemText(idx, LANG_LABEL.get(code, code))
        target_index = max(0, self.lang_select.findData(self.current_lang))
        self.lang_select.setCurrentIndex(target_index)
        self.lang_select.setToolTip(self.t("lang_tip"))
        self.lang_select.blockSignals(False)
        self._refresh_theme_options()

        self.file_menu.setTitle(self.t("menu_file"))
        self.tools_menu.setTitle(self.t("menu_tools"))
        self.repair_video_action.setText(self.t("action_repair_video"))
        self.exit_action.setText(self.t("action_exit"))

        self.table.setHorizontalHeaderLabels(
            [
                self.t("col_idx"),
                self.t("col_name"),
                self.t("col_status"),
                self.t("col_progress"),
                self.t("col_detail"),
                self.t("col_actions"),
            ]
        )

        for idx, pause_btn in self.pause_btn_by_index.items():
            status = self.task_status_by_index.get(idx, "waiting")
            pause_btn.setText(self.t("row_resume") if status == "paused" else self.t("row_pause"))
        for play_btn in self.play_btn_by_index.values():
            play_btn.setText(self.t("row_play"))
        for delete_btn in self.delete_btn_by_index.values():
            delete_btn.setText(self.t("row_delete"))

        for row in range(self.table.rowCount()):
            idx_item = self.table.item(row, 0)
            if not idx_item:
                continue
            try:
                task_idx = int(idx_item.text())
            except Exception:
                continue
            status_code = self.task_status_by_index.get(task_idx)
            status_item = self.table.item(row, 2)
            if status_code and status_item:
                status_text = {
                    "waiting": self.t("status_waiting"),
                    "running": self.t("status_waiting"),
                    "ok": self.t("status_done"),
                    "skipped": self.t("status_skipped"),
                    "paused": self.t("status_paused"),
                    "deleted": self.t("status_deleted"),
                    "failed": self.t("status_failed"),
                }.get(status_code, status_item.text())
                status_item.setText(status_text)
            detail_item = self.table.item(row, 4)
            if detail_item:
                detail_item.setText(self._localize_detail(detail_item.text()))

        self._update_page_header()
        self._update_version_btn_text()
        self._refresh_history_pagination_label()

    def _localize_detail(self, detail: str) -> str:
        if self.current_lang == "zh" or not detail:
            return detail
        text = detail.strip()
        exact_map = {
            "等待执行": self.t("detail_wait_dispatch"),
            "重试等待中": self.t("detail_retry_wait"),
            "校验文件": self.t("detail_validating"),
            "copy 失败，转码中": self.t("detail_copy_fallback"),
            "copy 成功但文件异常，转码修复中": self.t("detail_copy_invalid_fix"),
            "下载完成": self.t("detail_finished"),
            "目标文件已存在": self.t("detail_skipped"),
            "已暂停": self.t("detail_paused"),
            "已删除": self.t("detail_deleted"),
            "任务已中断": self.t("detail_interrupted"),
            "copy 失败，已自动转码": self.t("detail_copy_transcoded"),
            "copy 文件异常，已自动转码修复": self.t("detail_copy_fixed"),
            "未知错误": self.t("detail_unknown_err"),
        }
        if text in exact_map:
            return exact_map[text]
        m = re.match(r"下载中（尝试\s*(\d+)\s*/\s*(\d+)）", text)
        if m:
            return self.t("detail_downloading_try", attempt=m.group(1), total=m.group(2))
        return text

    def _update_version_btn_text(self) -> None:
        if self.update_checking:
            self.version_btn.setText(self.t("version_checking", version=APP_VERSION))
        else:
            self.version_btn.setText(self.t("version_plain", version=APP_VERSION))

    def _check_updates(self) -> None:
        if self.update_checking:
            return
        if not GITHUB_REPO or GITHUB_REPO.startswith("YOUR_GITHUB_OWNER/"):
            QMessageBox.information(self, self.t("dlg_version"), self.t("version_repo_missing"))
            return

        self.update_checking = True
        self.version_btn.setEnabled(False)
        self._update_version_btn_text()

        def worker() -> None:
            try:
                latest, release_url = fetch_latest_version(GITHUB_REPO)
                if is_newer_version(APP_VERSION, latest):
                    self.update_check_done.emit("update", latest, release_url)
                else:
                    self.update_check_done.emit("latest", latest, release_url)
            except urllib.error.HTTPError as exc:
                self.update_check_done.emit("error", f"HTTP {exc.code}", "")
            except Exception as exc:
                self.update_check_done.emit("error", str(exc), "")

        threading.Thread(target=worker, daemon=True).start()

    @Slot(str, str, str)
    def _on_update_check_done(self, status: str, latest: str, release_url: str) -> None:
        self.update_checking = False
        self.version_btn.setEnabled(True)
        self._update_version_btn_text()

        if status == "latest":
            QMessageBox.information(
                self,
                self.t("dlg_version"),
                self.t("version_latest", current=APP_VERSION, latest=latest),
            )
            return

        if status == "update":
            ret = QMessageBox.question(
                self,
                self.t("dlg_new_version"),
                self.t("version_update", current=APP_VERSION, latest=latest),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ret == QMessageBox.Yes and release_url:
                webbrowser.open(release_url)
            return

        QMessageBox.warning(self, self.t("dlg_version"), self.t("version_failed", err=latest))

    def _apply_theme(self, theme: str) -> None:
        if theme == "dark":
            stylesheet = """
                #root {
                    background: #151515;
                }
                QMenuBar {
                    background: #1a1a1a;
                    color: #f7f2f4;
                    border-bottom: 1px solid #2a2a2a;
                }
                QMenuBar::item:selected {
                    background: #2a2a2a;
                }
                QMenu {
                    background: #202020;
                    color: #f7f2f4;
                    border: 1px solid #343434;
                }
                QMenu::item:selected {
                    background: #ff5d7d;
                }
                QFrame#sidebar {
                    background: #1d1d1f;
                    border: 1px solid #2d2d31;
                    border-radius: 14px;
                }
                QFrame#sidebarBrand {
                    background: #26262a;
                    border: 1px solid #34343a;
                    border-radius: 14px;
                }
                QLabel#brandLogo {
                    min-width: 56px;
                    max-width: 56px;
                    min-height: 56px;
                    max-height: 56px;
                    background: transparent;
                }
                QLabel#brandName {
                    color: #ffffff;
                    font-size: 24px;
                    font-weight: 600;
                }
                QLabel#brandSub {
                    color: #c2b9bd;
                    font-size: 12px;
                }
                QLabel#navCaption, QLabel#sideVersion {
                    color: #a39a9e;
                    font-size: 12px;
                    font-weight: 600;
                    letter-spacing: 0.5px;
                }
                QPushButton#navButton {
                    border: 1px solid transparent;
                    border-radius: 8px;
                    background: transparent;
                    color: #f2edf0;
                    padding: 12px 14px;
                    text-align: left;
                    font-size: 15px;
                    font-weight: 600;
                }
                QPushButton#navButton:hover {
                    background: #27272b;
                }
                QPushButton#navButton:checked {
                    background: #322127;
                    color: #ff8da4;
                    border-color: #4a3037;
                }
                QFrame#headerCard {
                    border-radius: 14px;
                    background: #202022;
                    border: 1px solid #303036;
                }
                QLabel#pageBadge {
                    color: #ffb8c5;
                    background: #322127;
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QLabel#pageTitle {
                    color: #ffffff;
                    font-size: 22px;
                    font-weight: 600;
                }
                QLabel#pageSubtitle {
                    color: #cbc2c6;
                    font-size: 14px;
                }
                QStackedWidget#pageStack {
                    background: transparent;
                }
                QFrame#card {
                    background: #202022;
                    border: 1px solid #303036;
                    border-radius: 14px;
                }
                QLabel#sectionTitle {
                    color: #ffffff;
                    font-size: 18px;
                    font-weight: 600;
                }
                QLabel#fieldLabel {
                    color: #f3eef0;
                    font-size: 14px;
                    font-weight: 600;
                }
                QLabel#inputHintLabel, QLabel#hintText, QLabel#summaryLabel {
                    color: #cbc2c6;
                    font-size: 13px;
                }
                QLineEdit#pathInput, QLineEdit#urlLineInput, QTextEdit#urlInput, QTextEdit#repairInput, QSpinBox#spinBox, QComboBox#choiceSelect {
                    background: #2a2a2e;
                    color: #ffffff;
                    border: 1px solid #3a3a42;
                    border-radius: 8px;
                    padding: 10px 14px;
                    selection-background-color: #ff5d7d;
                }
                QLineEdit#pathInput:focus, QLineEdit#urlLineInput:focus, QTextEdit#urlInput:focus, QTextEdit#repairInput:focus, QSpinBox#spinBox:focus, QComboBox#choiceSelect:focus {
                    border: 2px solid #ff8da4;
                    padding: 9px 13px;
                }
                QTextEdit#urlInput, QTextEdit#repairInput {
                    padding-top: 12px;
                    padding-bottom: 12px;
                }
                QComboBox#choiceSelect::drop-down {
                    border: 0;
                    width: 26px;
                }
                QComboBox#choiceSelect QAbstractItemView {
                    border: 1px solid #3a3a42;
                    background: #222226;
                    color: #ffffff;
                    selection-background-color: #ff5d7d;
                }
                QSpinBox#spinBox {
                    padding-right: 34px;
                }
                QSpinBox#spinBox::up-button, QSpinBox#spinBox::down-button {
                    width: 22px;
                    border-left: 1px solid #3a3a42;
                    background: #313137;
                }
                QSpinBox#spinBox::up-button {
                    subcontrol-origin: border;
                    subcontrol-position: top right;
                    border-top-right-radius: 8px;
                }
                QSpinBox#spinBox::down-button {
                    subcontrol-origin: border;
                    subcontrol-position: bottom right;
                    border-bottom-right-radius: 8px;
                    border-top: 1px solid #3a3a42;
                }
                QSpinBox#spinBox::up-button:hover, QSpinBox#spinBox::down-button:hover {
                    background: #3a3a42;
                }
                QTabWidget#inputTabs::pane {
                    border: 1px solid #34343a;
                    border-radius: 14px;
                    top: -1px;
                }
                QTabWidget#inputTabs QTabBar::tab {
                    background: #2a2a2e;
                    color: #d9d0d3;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    padding: 10px 16px;
                    margin-right: 8px;
                }
                QTabWidget#inputTabs QTabBar::tab:selected {
                    background: #3a272d;
                    color: #ffffff;
                }
                QScrollArea#singleScroll, QWidget#singleContainer {
                    background: transparent;
                    border: 0;
                }
                QPushButton#startBtn, QPushButton#primaryBtn {
                    background: #ff385c;
                    color: white;
                    border: 0;
                    border-radius: 8px;
                    padding: 12px 22px;
                    font-size: 15px;
                    font-weight: 600;
                }
                QPushButton#startBtn:hover, QPushButton#primaryBtn:hover {
                    background: #e00b41;
                }
                QPushButton#startBtn:disabled, QPushButton#primaryBtn:disabled {
                    background: #844350;
                    color: #f7dbe1;
                }
                QPushButton#secondaryBtn, QPushButton#tableActionBtn {
                    background: #2a2a2e;
                    color: #ffffff;
                    border: 1px solid #404048;
                    border-radius: 8px;
                    padding: 10px 16px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton#secondaryBtn:hover, QPushButton#tableActionBtn:hover {
                    background: #333338;
                }
                QPushButton#themeOptionBtn {
                    background: #26262a;
                    color: #f2edf0;
                    border: 1px solid #3c3c42;
                    border-radius: 10px;
                    padding: 10px 14px;
                    font-size: 14px;
                    font-weight: 600;
                    text-align: left;
                }
                QPushButton#themeOptionBtn:hover {
                    background: #2f2f35;
                }
                QPushButton#themeOptionBtn:checked {
                    background: #322127;
                    color: #ffb8c5;
                    border-color: #5a3a43;
                }
                QPushButton#miniBtn {
                    background: #2a2a2e;
                    color: #f7f2f4;
                    border: 1px solid #404048;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton#miniBtn:hover {
                    background: #333338;
                }
                QPushButton#dangerBtn, QPushButton#rowDeleteBtn {
                    background: #3a2428;
                    color: #ffb8c5;
                    border: 1px solid #5a343d;
                    border-radius: 8px;
                    padding: 8px 14px;
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton#dangerBtn:hover, QPushButton#rowDeleteBtn:hover {
                    background: #4a2a31;
                }
                QPushButton#rowPauseBtn, QPushButton#rowPlayBtn {
                    background: #2a2a2e;
                    color: #ffffff;
                    border: 1px solid #404048;
                    border-radius: 8px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton#rowPauseBtn:hover, QPushButton#rowPlayBtn:hover {
                    background: #35353a;
                }
                QTableWidget {
                    background: #1d1d20;
                    color: #ffffff;
                    border: 1px solid #303036;
                    border-radius: 14px;
                    gridline-color: #2a2a2f;
                    alternate-background-color: #232327;
                }
                QTableWidget::item:hover {
                    background: transparent;
                }
                QTableWidget::item:selected {
                    background: rgba(255, 93, 125, 0.18);
                }
                QHeaderView::section {
                    background: #2a2a2e;
                    color: #ffffff;
                    border: 0;
                    padding: 10px 8px;
                    font-weight: 600;
                }
                QProgressBar {
                    background: #2a2a2e;
                    color: #ffffff;
                    border: 1px solid #3a3a42;
                    border-radius: 8px;
                    text-align: center;
                    min-height: 14px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #ff385c, stop:1 #ff9aaa);
                    border-radius: 7px;
                }
            """
        else:
            stylesheet = """
                #root {
                    background: #fbfbfb;
                }
                QMenuBar {
                    background: #ffffff;
                    color: #222222;
                    border-bottom: 1px solid #ebebeb;
                }
                QMenuBar::item:selected {
                    background: #f7f7f7;
                }
                QMenu {
                    background: #ffffff;
                    color: #222222;
                    border: 1px solid #ebebeb;
                }
                QMenu::item:selected {
                    background: #fff1f4;
                }
                QFrame#sidebar {
                    background: #ffffff;
                    border: 1px solid #ebebeb;
                    border-radius: 14px;
                }
                QFrame#sidebarBrand {
                    background: #fff7f8;
                    border: 1px solid #ffe1e7;
                    border-radius: 14px;
                }
                QLabel#brandLogo {
                    min-width: 56px;
                    max-width: 56px;
                    min-height: 56px;
                    max-height: 56px;
                    background: transparent;
                }
                QLabel#brandName {
                    color: #222222;
                    font-size: 24px;
                    font-weight: 600;
                }
                QLabel#brandSub {
                    color: #6a6a6a;
                    font-size: 12px;
                }
                QLabel#navCaption, QLabel#sideVersion {
                    color: #929292;
                    font-size: 12px;
                    font-weight: 600;
                    letter-spacing: 0.5px;
                }
                QPushButton#navButton {
                    border: 1px solid transparent;
                    border-radius: 8px;
                    background: transparent;
                    color: #3f3f3f;
                    padding: 12px 14px;
                    text-align: left;
                    font-size: 15px;
                    font-weight: 600;
                }
                QPushButton#navButton:hover {
                    background: #f7f7f7;
                }
                QPushButton#navButton:checked {
                    background: #fff1f4;
                    color: #ff385c;
                    border-color: #ffd6de;
                }
                QFrame#headerCard {
                    border-radius: 14px;
                    background: #ffffff;
                    border: 1px solid #ebebeb;
                }
                QLabel#pageBadge {
                    color: #ff385c;
                    background: #fff1f4;
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QLabel#pageTitle {
                    color: #222222;
                    font-size: 22px;
                    font-weight: 600;
                }
                QLabel#pageSubtitle {
                    color: #6a6a6a;
                    font-size: 14px;
                }
                QStackedWidget#pageStack {
                    background: transparent;
                }
                QFrame#card {
                    background: #ffffff;
                    border: 1px solid #ebebeb;
                    border-radius: 14px;
                }
                QLabel#sectionTitle {
                    color: #222222;
                    font-size: 18px;
                    font-weight: 600;
                }
                QLabel#fieldLabel {
                    color: #222222;
                    font-size: 14px;
                    font-weight: 600;
                }
                QLabel#inputHintLabel, QLabel#hintText, QLabel#summaryLabel {
                    color: #6a6a6a;
                    font-size: 13px;
                }
                QLineEdit#pathInput, QLineEdit#urlLineInput, QTextEdit#urlInput, QTextEdit#repairInput, QSpinBox#spinBox, QComboBox#choiceSelect {
                    background: #ffffff;
                    color: #222222;
                    border: 1px solid #dddddd;
                    border-radius: 8px;
                    padding: 10px 14px;
                    selection-background-color: #ff5d7d;
                }
                QLineEdit#pathInput:focus, QLineEdit#urlLineInput:focus, QTextEdit#urlInput:focus, QTextEdit#repairInput:focus, QSpinBox#spinBox:focus, QComboBox#choiceSelect:focus {
                    border: 2px solid #222222;
                    padding: 9px 13px;
                }
                QTextEdit#urlInput, QTextEdit#repairInput {
                    padding-top: 12px;
                    padding-bottom: 12px;
                }
                QComboBox#choiceSelect::drop-down {
                    border: 0;
                    width: 26px;
                }
                QComboBox#choiceSelect QAbstractItemView {
                    border: 1px solid #dddddd;
                    background: #ffffff;
                    color: #222222;
                    selection-background-color: #ff5d7d;
                    selection-color: #ffffff;
                }
                QSpinBox#spinBox {
                    padding-right: 34px;
                }
                QSpinBox#spinBox::up-button, QSpinBox#spinBox::down-button {
                    width: 22px;
                    border-left: 1px solid #dddddd;
                    background: #fafafa;
                }
                QSpinBox#spinBox::up-button {
                    subcontrol-origin: border;
                    subcontrol-position: top right;
                    border-top-right-radius: 8px;
                }
                QSpinBox#spinBox::down-button {
                    subcontrol-origin: border;
                    subcontrol-position: bottom right;
                    border-bottom-right-radius: 8px;
                    border-top: 1px solid #dddddd;
                }
                QSpinBox#spinBox::up-button:hover, QSpinBox#spinBox::down-button:hover {
                    background: #f0f2f5;
                }
                QTabWidget#inputTabs::pane {
                    border: 1px solid #ebebeb;
                    border-radius: 14px;
                    top: -1px;
                }
                QTabWidget#inputTabs QTabBar::tab {
                    background: #f7f7f7;
                    color: #6a6a6a;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    padding: 10px 16px;
                    margin-right: 8px;
                }
                QTabWidget#inputTabs QTabBar::tab:selected {
                    background: #fff1f4;
                    color: #222222;
                }
                QScrollArea#singleScroll, QWidget#singleContainer {
                    background: transparent;
                    border: 0;
                }
                QPushButton#startBtn, QPushButton#primaryBtn {
                    background: #ff385c;
                    color: white;
                    border: 0;
                    border-radius: 8px;
                    padding: 12px 22px;
                    font-size: 15px;
                    font-weight: 600;
                }
                QPushButton#startBtn:hover, QPushButton#primaryBtn:hover {
                    background: #e00b41;
                }
                QPushButton#startBtn:disabled, QPushButton#primaryBtn:disabled {
                    background: #ffd1da;
                    color: #ffffff;
                }
                QPushButton#secondaryBtn, QPushButton#tableActionBtn {
                    background: #ffffff;
                    color: #222222;
                    border: 1px solid #dddddd;
                    border-radius: 8px;
                    padding: 10px 16px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton#secondaryBtn:hover, QPushButton#tableActionBtn:hover {
                    background: #f7f7f7;
                }
                QPushButton#themeOptionBtn {
                    background: #ffffff;
                    color: #222222;
                    border: 1px solid #dddddd;
                    border-radius: 10px;
                    padding: 10px 14px;
                    font-size: 14px;
                    font-weight: 600;
                    text-align: left;
                }
                QPushButton#themeOptionBtn:hover {
                    background: #f7f7f7;
                }
                QPushButton#themeOptionBtn:checked {
                    background: #fff1f4;
                    color: #ff385c;
                    border-color: #ffd6de;
                }
                QPushButton#miniBtn {
                    background: #ffffff;
                    color: #222222;
                    border: 1px solid #dddddd;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton#miniBtn:hover {
                    background: #f7f7f7;
                }
                QPushButton#dangerBtn, QPushButton#rowDeleteBtn {
                    background: #fff1f4;
                    color: #c13515;
                    border: 1px solid #ffd6de;
                    border-radius: 8px;
                    padding: 8px 14px;
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton#dangerBtn:hover, QPushButton#rowDeleteBtn:hover {
                    background: #ffe6eb;
                }
                QPushButton#rowPauseBtn, QPushButton#rowPlayBtn {
                    background: #ffffff;
                    color: #222222;
                    border: 1px solid #dddddd;
                    border-radius: 8px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton#rowPauseBtn:hover, QPushButton#rowPlayBtn:hover {
                    background: #f7f7f7;
                }
                QTableWidget {
                    background: #ffffff;
                    color: #222222;
                    border: 1px solid #ebebeb;
                    border-radius: 14px;
                    gridline-color: #f0f0f0;
                    alternate-background-color: #fcfcfc;
                }
                QTableWidget::item:hover {
                    background: transparent;
                }
                QTableWidget::item:selected {
                    background: rgba(255, 93, 125, 0.14);
                }
                QHeaderView::section {
                    background: #f7f7f7;
                    color: #222222;
                    border: 0;
                    padding: 10px 8px;
                    font-weight: 600;
                }
                QProgressBar {
                    background: #f7f7f7;
                    color: #222222;
                    border: 1px solid #ebebeb;
                    border-radius: 8px;
                    text-align: center;
                    min-height: 14px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #ff385c, stop:1 #ff9aaa);
                    border-radius: 7px;
                }
            """

        self.setStyleSheet(stylesheet)
        self._refresh_theme_options()
        self._refresh_nav_button_icons()
        self._update_version_btn_text()

    def _toggle_theme(self) -> None:
        self.current_theme = "dark" if self.current_theme == "light" else "light"
        self._apply_theme(self.current_theme)
        self._animate_theme_switch()

    def _choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.t("select_output_dir"),
            self.output_dir_input.text().strip() or str(Path.cwd()),
        )
        if folder:
            self.output_dir_input.setText(folder)

    def _set_repair_sources(self, paths: list[Path]) -> None:
        self.repair_path_input.setPlainText("\n".join(str(path) for path in paths))
        self.repair_status_label.setText(self.t("repair_idle"))
        self.repair_open_btn.setEnabled(False)
        self.repair_output_paths = []
        self._set_active_page("repair")

    def _collect_repair_sources(self) -> list[Path]:
        raw_text = self.repair_path_input.toPlainText().strip()
        if not raw_text:
            return []

        sources: list[Path] = []
        seen: set[str] = set()
        for raw in re.split(r"[\r\n]+|\s*\|\s*", raw_text):
            text = raw.strip().strip('"')
            if not text:
                continue
            path = Path(text).expanduser().resolve()
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            sources.append(path)
        return sources

    def _choose_repair_files(self) -> bool:
        current_sources = self._collect_repair_sources()
        if current_sources:
            start_dir = str(current_sources[0].parent)
        else:
            start_dir = self.output_dir_input.text().strip() or str(default_download_dir())

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.t("dlg_select_repair_file"),
            start_dir,
            self.t("repair_filter"),
        )
        if not file_paths:
            return False

        self._set_repair_sources([Path(file_path).expanduser().resolve() for file_path in file_paths])
        return True

    def _set_repair_running(self, running: bool) -> None:
        self.repair_start_btn.setEnabled(not running)
        self.repair_start_btn.setText(self.t("repair_running") if running else self.t("repair_start"))
        self.repair_open_btn.setEnabled((not running) and bool(self.repair_output_paths))
        self.repair_progress_label.setHidden(not running)
        self.repair_progress_bar.setHidden(not running)
        if not running:
            self.repair_completed_count = 0
            self.repair_progress_bar.setRange(0, 100)
            self.repair_progress_bar.setValue(0)
            self.repair_progress_bar.setFormat("%p%")
            self.repair_progress_bar.set_busy(False)
            self.repair_progress_label.clear()

    def _start_repair_session(self, sources: list[Path], options: DownloadOptions) -> None:
        if self.repair_thread:
            return
        self.repair_active_sources = sources
        self.repair_output_paths = []
        self.repair_completed_count = 0
        self.repair_status_label.setText(self.t("detail_validating"))
        self.repair_progress_label.setText(self.t("repair_progress", current=0, total=len(sources)))
        self._set_repair_running(True)
        self.repair_progress_bar.setRange(0, 0)
        self.repair_progress_bar.setFormat("")
        self.repair_progress_bar.set_busy(True)

        self.repair_thread = QThread(self)
        self.repair_worker = RepairWorker(sources, options)
        self.repair_worker.moveToThread(self.repair_thread)
        self.repair_thread.started.connect(self.repair_worker.run)
        self.repair_worker.progress.connect(self._on_repair_progress)
        self.repair_worker.finished.connect(self._on_repair_finished)
        self.repair_worker.finished.connect(self.repair_thread.quit)
        self.repair_thread.finished.connect(self._on_repair_thread_finished)
        self.repair_thread.start()

    def _run_repair_from_page(self) -> None:
        if self.repair_thread and self.repair_thread.isRunning():
            return
        sources = self._collect_repair_sources()
        if not sources:
            self._show_copyable_message(QMessageBox.Warning, self.t("tip"), self.t("tip_repair_missing"))
            return

        try:
            options = self._build_default_options()
        except Exception as exc:
            title = self.t("ffmpeg_missing") if isinstance(exc, FileNotFoundError) else self.t("tip")
            self._show_copyable_message(QMessageBox.Critical, title, str(exc))
            return

        self._start_repair_session(sources, options)

    @Slot(int, int, str, str)
    def _on_repair_progress(self, current: int, total: int, file_name: str, stage: str) -> None:
        if stage == "done":
            self.repair_completed_count = current
            self.repair_progress_label.setText(self.t("repair_progress", current=current, total=total))
            self.repair_progress_bar.setRange(0, max(1, total))
            self.repair_progress_bar.setValue(current)
            self.repair_progress_bar.setFormat("%v/%m")
            self.repair_progress_bar.set_busy(current < total)
            self.repair_status_label.setText(
                self.t("repair_processing", current=current, total=total, file=file_name)
            )
            return

        completed = max(0, current - 1)
        self.repair_completed_count = max(self.repair_completed_count, completed)
        self.repair_progress_label.setText(
            self.t("repair_progress", current=self.repair_completed_count, total=total)
        )
        self.repair_progress_bar.setRange(0, 0)
        self.repair_progress_bar.setFormat("")
        self.repair_progress_bar.set_busy(True)

        stage_key = f"repair_stage_{stage}"
        stage_text = I18N.get(self.current_lang, {}).get(stage_key)
        if stage_text:
            self.repair_status_label.setText(
                self.t(stage_key, current=current, total=total, file=file_name)
            )
        else:
            self.repair_status_label.setText(
                self.t("repair_processing", current=current, total=total, file=file_name)
            )

    @Slot(object)
    def _on_repair_finished(self, results: object) -> None:
        if not isinstance(results, list):
            return
        if len(results) == 1:
            source, result = results[0]
            if result.status == "noop":
                self.repair_status_label.setText(self.t("repair_result_healthy"))
                self._show_copyable_message(QMessageBox.Information, self.t("tip"), self.t("repair_result_healthy"))
                return

            if result.status == "ok" and result.output_path:
                self.repair_output_paths = [result.output_path]
                self.repair_open_btn.setEnabled(True)
                if result.method == "transcode":
                    message = self.t("repair_result_transcode", file=str(result.output_path))
                else:
                    message = self.t("repair_result_remux", file=str(result.output_path))
                self.repair_status_label.setText(message)
                self._show_copyable_message(QMessageBox.Information, self.t("tip"), message)
                return

            detail = result.detail or self.t("repair_result_failed")
            if result.detail == "source_missing":
                self.repair_status_label.setText(self.t("tip_repair_missing"))
                self._show_copyable_message(QMessageBox.Warning, self.t("tip"), self.t("tip_repair_missing"))
                return
            detail = normalize_repair_error_detail(detail)
            summary = self.t("repair_result_failed_detail", detail=detail)
            self.repair_status_label.setText(summary)
            self._show_copyable_message(QMessageBox.Warning, self.t("tip"), summary, detail)
            return

        success = 0
        skipped = 0
        failed = 0
        details: list[str] = []
        repaired_outputs: list[Path] = []
        for source, result in results:
            if result.status == "ok" and result.output_path:
                success += 1
                repaired_outputs.append(result.output_path)
                method_key = "repair_result_transcode" if result.method == "transcode" else "repair_result_remux"
                details.append(f"{source.name}: {self.t(method_key, file=str(result.output_path))}")
            elif result.status == "noop":
                skipped += 1
                details.append(f"{source.name}: {self.t('repair_result_healthy')}")
            else:
                failed += 1
                detail_text = self.t("tip_repair_missing") if result.detail == "source_missing" else (
                    normalize_repair_error_detail(result.detail or self.t("repair_result_failed"))
                )
                details.append(
                    f"{source.name}: {self.t('repair_result_failed_detail', detail=detail_text)}"
                )

        self.repair_output_paths = repaired_outputs

        summary = self.t("repair_result_batch", success=success, skipped=skipped, failed=failed)
        detail_text = "\n".join(details[:10])
        if len(details) > 10:
            detail_text += f"\n... {len(details) - 10} more"
        message = self.t(
            "repair_result_batch_detail",
            success=success,
            skipped=skipped,
            failed=failed,
            details=detail_text,
        )
        self.repair_status_label.setText(summary)
        if failed > 0:
            self._show_copyable_message(QMessageBox.Warning, self.t("tip"), summary, message)
        else:
            self._show_copyable_message(QMessageBox.Information, self.t("tip"), message)

    @Slot()
    def _on_repair_thread_finished(self) -> None:
        self.repair_progress_bar.set_busy(False)
        if self.repair_worker:
            self.repair_worker.deleteLater()
            self.repair_worker = None
        if self.repair_thread:
            self.repair_thread.deleteLater()
            self.repair_thread = None
        self._set_repair_running(False)
        self.repair_active_sources = []

    def _open_repaired_output(self) -> None:
        if not self.repair_output_paths:
            QMessageBox.warning(self, self.t("tip"), self.t("tip_file_missing"))
            return
        target = self.repair_output_paths[0]
        if len(self.repair_output_paths) > 1:
            target = target.parent
        self._open_path(target, "tip_file_missing")

    def _repair_video_from_menu(self) -> None:
        self._set_active_page("repair")
        if self._choose_repair_files():
            self._run_repair_from_page()

    def _attempt_stop_worker_for_exit(self) -> bool:
        if not self.worker or not self.worker_thread or not self.worker_thread.isRunning():
            return True

        ret = QMessageBox.question(
            self,
            self.t("dlg_confirm_exit"),
            self.t("dlg_confirm_exit_running"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return False

        self.summary_label.setText(self.t("summary_exit_stopping"))
        self.worker.apply_command("delete_all")

        app = QApplication.instance()
        deadline = time.monotonic() + 8.0
        while self.worker_thread and self.worker_thread.isRunning() and time.monotonic() < deadline:
            if app is not None:
                app.processEvents()
            time.sleep(0.05)

        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.warning(self, self.t("tip"), self.t("tip_exit_wait_stop"))
            return False
        return True

    def _add_table_row(self, task: DownloadTask) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 44)
        self.row_by_index[task.index] = row
        self.task_status_by_index[task.index] = "waiting"
        self.task_url_by_index[task.index] = task.url
        self.task_output_path_by_index[task.index] = task.output_path

        idx_item = QTableWidgetItem(str(task.index))
        name_item = QTableWidgetItem(task.output_path.name)
        status_item = QTableWidgetItem(self.t("status_waiting"))
        detail_item = QTableWidgetItem(task.url)
        idx_item.setTextAlignment(Qt.AlignCenter)
        status_item.setTextAlignment(Qt.AlignCenter)
        name_item.setToolTip(str(task.output_path))

        self.table.setItem(row, 0, idx_item)
        self.table.setItem(row, 1, name_item)
        self.table.setItem(row, 2, status_item)
        self.table.setItem(row, 4, detail_item)

        bar_wrap = QWidget()
        bar_layout = QHBoxLayout(bar_wrap)
        bar_layout.setContentsMargins(8, 0, 8, 0)
        bar_layout.setSpacing(0)

        bar = AnimatedProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFormat("0%")
        bar.setFixedHeight(14)
        bar_layout.addWidget(bar, 1, Qt.AlignVCenter)
        self.table.setCellWidget(row, 3, bar_wrap)
        self.progress_by_index[task.index] = bar
        self.progress_wrap_by_index[task.index] = bar_wrap

        action_wrap = QWidget()
        action_layout = QHBoxLayout(action_wrap)
        action_layout.setContentsMargins(10, 6, 10, 6)
        action_layout.setSpacing(10)

        pause_btn = QPushButton(self.t("row_pause"))
        pause_btn.setObjectName("rowPauseBtn")
        pause_btn.setMinimumHeight(24)
        pause_btn.setFixedWidth(56)
        pause_btn.clicked.connect(lambda _, idx=task.index: self._on_row_pause_clicked(idx))

        play_btn = QPushButton(self.t("row_play"))
        play_btn.setObjectName("rowPlayBtn")
        play_btn.setMinimumHeight(24)
        play_btn.setFixedWidth(56)
        play_btn.setVisible(False)
        play_btn.clicked.connect(lambda _, idx=task.index: self._on_row_play_clicked(idx))

        delete_btn = QPushButton(self.t("row_delete"))
        delete_btn.setObjectName("rowDeleteBtn")
        delete_btn.setMinimumHeight(24)
        delete_btn.setFixedWidth(56)
        delete_btn.clicked.connect(lambda _, idx=task.index: self._on_row_delete_clicked(idx))

        action_layout.addStretch(1)
        action_layout.addWidget(pause_btn)
        action_layout.addWidget(play_btn)
        action_layout.addWidget(delete_btn)
        action_layout.addStretch(1)
        self.table.setCellWidget(row, 5, action_wrap)
        self.action_wrap_by_index[task.index] = action_wrap
        self.pause_btn_by_index[task.index] = pause_btn
        self.play_btn_by_index[task.index] = play_btn
        self.delete_btn_by_index[task.index] = delete_btn

    def _set_status(self, row: int, text: str, color: QColor) -> None:
        item = self.table.item(row, 2)
        if item is None:
            return
        item.setText(text)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QBrush(color))

    def _animate_progress(self, bar: QProgressBar, target: int) -> None:
        anim = QPropertyAnimation(bar, b"value", bar)
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.setDuration(260)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v, b=bar: b.setFormat(f"{int(v)}%"))
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _append_single_input_row(self, text: str = "") -> None:
        row_wrap = QWidget()
        row_layout = QHBoxLayout(row_wrap)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        line = QLineEdit(text)
        line.setObjectName("urlLineInput")
        line.setMinimumHeight(44)
        line.setPlaceholderText(self.t("single_placeholder"))
        line.textChanged.connect(lambda _=None, l=line: self._on_single_input_changed(l))

        delete_btn = QPushButton(self.t("row_delete"))
        delete_btn.setObjectName("miniBtn")
        delete_btn.setFixedSize(52, 32)
        delete_btn.clicked.connect(lambda _, l=line: self._on_single_row_delete_clicked(l))

        row_layout.addWidget(line, 1)
        row_layout.addWidget(delete_btn, 0, Qt.AlignVCenter)
        self.single_lines_layout.addWidget(row_wrap)
        self.single_url_inputs.append(line)
        self.single_delete_btns[line] = delete_btn
        self._refresh_single_input_scroll_height()

    def _refresh_single_input_scroll_height(self) -> None:
        visible_rows = max(1, min(3, len(self.single_url_inputs)))
        row_height = 44
        height = 8 + visible_rows * row_height + (visible_rows - 1) * 8 + 8
        self.single_scroll.setMinimumHeight(height)
        self.single_scroll.setMaximumHeight(height)
        self.single_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if len(self.single_url_inputs) > 3 else Qt.ScrollBarAlwaysOff
        )
        self._refresh_input_tabs_height()

    def _refresh_input_tabs_height(self) -> None:
        if not hasattr(self, "input_tabs"):
            return
        if not hasattr(self, "single_scroll"):
            return
        tab_bar_height = self.input_tabs.tabBar().sizeHint().height() if self.input_tabs.tabBar() else 32
        if self.input_tabs.currentIndex() == 0:
            content_height = self.single_scroll.maximumHeight()
            target_height = tab_bar_height + content_height + 22
        else:
            if not hasattr(self, "url_input"):
                return
            target_height = tab_bar_height + self.url_input.maximumHeight() + 56
        self.input_tabs.setMinimumHeight(target_height)
        self.input_tabs.setMaximumHeight(target_height)

    def _show_copyable_message(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        detail: str | None = None,
    ) -> None:
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        box.setStandardButtons(QMessageBox.Ok)
        if detail and detail != text:
            box.setDetailedText(detail)
            copy_btn = box.addButton(self.t("copy_detail"), QMessageBox.ActionRole)
            copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(detail))
        box.exec()

    def _remove_single_input_row(self, line: QLineEdit) -> None:
        if line in self.single_url_inputs:
            self.single_url_inputs.remove(line)
        self.single_delete_btns.pop(line, None)
        row_wrap = line.parentWidget()
        if row_wrap:
            self.single_lines_layout.removeWidget(row_wrap)
            row_wrap.deleteLater()
        else:
            line.deleteLater()
        self._refresh_single_input_scroll_height()

    def _on_single_input_changed(self, line: QLineEdit) -> None:
        if self.single_url_inputs and line is self.single_url_inputs[-1] and line.text().strip():
            self._append_single_input_row()

        while (
            len(self.single_url_inputs) >= 2
            and not self.single_url_inputs[-1].text().strip()
            and not self.single_url_inputs[-2].text().strip()
        ):
            self._remove_single_input_row(self.single_url_inputs[-1])

    def _on_single_row_delete_clicked(self, line: QLineEdit) -> None:
        if line not in self.single_url_inputs:
            return
        if len(self.single_url_inputs) == 1:
            line.clear()
            return
        self._remove_single_input_row(line)
        if not self.single_url_inputs or self.single_url_inputs[-1].text().strip():
            self._append_single_input_row()

    def _collect_current_entries(self) -> list[tuple[str | None, str]]:
        if self.input_tabs.currentIndex() == 0:
            entries: list[tuple[str | None, str]] = []
            for line in self.single_url_inputs:
                text = line.text().strip()
                if not text:
                    continue
                entries.extend(parse_url_lines(text))
            return entries
        return parse_url_lines(self.url_input.toPlainText())

    def _set_pause_btn_state(self, task_index: int, paused: bool, enabled: bool = True) -> None:
        btn = self.pause_btn_by_index.get(task_index)
        if not btn:
            return
        btn.setText(self.t("row_resume") if paused else self.t("row_pause"))
        btn.setEnabled(enabled)

    def _set_pause_btn_visible(self, task_index: int, visible: bool) -> None:
        btn = self.pause_btn_by_index.get(task_index)
        if btn:
            btn.setVisible(visible)

    def _set_delete_btn_enabled(self, task_index: int, enabled: bool) -> None:
        btn = self.delete_btn_by_index.get(task_index)
        if btn:
            btn.setEnabled(enabled)

    def _set_play_btn_visible(self, task_index: int, visible: bool) -> None:
        btn = self.play_btn_by_index.get(task_index)
        if btn:
            btn.setVisible(visible)

    def _set_play_btn_enabled(self, task_index: int, enabled: bool) -> None:
        btn = self.play_btn_by_index.get(task_index)
        if btn:
            btn.setEnabled(enabled)

    def _set_progress_busy(self, task_index: int, busy: bool) -> None:
        bar = self.progress_by_index.get(task_index)
        if isinstance(bar, AnimatedProgressBar):
            bar.set_busy(busy)

    @Slot(int, int)
    def _on_task_table_hovered_row_changed(self, previous_row: int, current_row: int) -> None:
        self._apply_task_row_hover(previous_row, False)
        self._apply_task_row_hover(current_row, True)

    def _apply_task_row_hover(self, row: int, hovered: bool) -> None:
        if row < 0:
            return
        idx_item = self.table.item(row, 0)
        if not idx_item:
            return
        try:
            task_index = int(idx_item.text())
        except Exception:
            return
        progress_wrap = self.progress_wrap_by_index.get(task_index)
        if progress_wrap and progress_wrap.layout():
            progress_wrap.layout().setContentsMargins(12 if hovered else 8, 0, 4 if hovered else 8, 0)
        action_wrap = self.action_wrap_by_index.get(task_index)
        if action_wrap and action_wrap.layout():
            action_wrap.layout().setContentsMargins(14 if hovered else 10, 6, 6 if hovered else 10, 6)

    @Slot(int, int)
    def _on_task_table_cell_clicked(self, row: int, column: int) -> None:
        if column != 1:
            return
        idx_item = self.table.item(row, 0)
        if not idx_item:
            return
        try:
            task_index = int(idx_item.text())
        except Exception:
            return
        output_path = self.task_output_path_by_index.get(task_index)
        if not output_path:
            return
        QApplication.clipboard().setText(str(output_path))
        QToolTip.showText(QCursor.pos(), self.t("tip_copied_output"), self.table.viewport())

    def _record_history_entry(self, task_index: int) -> None:
        if not self.history_store:
            return
        url = self.task_url_by_index.get(task_index, "").strip()
        output_path = self.task_output_path_by_index.get(task_index)
        if not url or not output_path:
            return
        name = output_path.name
        try:
            self.history_store.upsert_entry(
                code=extract_video_code(name),
                name=name,
                url=url,
                output_path=str(output_path),
            )
        except Exception as exc:
            self.history_store_error = str(exc)
            return
        if self.active_page == "history":
            self._refresh_history_view()

    def _history_entry_status(self, entry: HistoryEntry) -> tuple[str, str]:
        cached = self.history_media_status_by_id.get(entry.id)
        if cached:
            return cached
        target = Path(entry.output_path)
        if not target.exists():
            return "missing", "输出文件不存在"
        return "unknown", ""

    def _history_status_text(self, status: str) -> str:
        return {
            "unknown": self.t("history_status_unknown"),
            "ok": self.t("history_status_ok"),
            "broken": self.t("history_status_broken"),
            "missing": self.t("history_status_missing"),
        }.get(status, status)

    def _history_status_color(self, status: str) -> QColor:
        if status == "ok":
            return QColor("#1F8F4D") if self.current_theme == "light" else QColor("#86E3A8")
        if status == "broken":
            return QColor("#C62828") if self.current_theme == "light" else QColor("#FF9A9A")
        if status == "missing":
            return QColor("#AD6E00") if self.current_theme == "light" else QColor("#FFD287")
        return QColor("#3E63DD") if self.current_theme == "light" else QColor("#A7C5FF")

    def _history_matches_status_filter(self, entry: HistoryEntry, status_filter: str) -> bool:
        status, _ = self._history_entry_status(entry)
        if status_filter == "all":
            return True
        if status_filter == "issue":
            return status in {"broken", "missing"}
        return status == status_filter

    def _refresh_history_pagination_label(self) -> None:
        if not hasattr(self, "history_page_label"):
            return
        total = len(self.history_filtered_entries)
        total_pages = max(1, (total + self.history_page_size - 1) // self.history_page_size) if total else 1
        self.history_page_label.setText(self.t("history_page_info", current=self.history_page, total=total_pages))
        if hasattr(self, "history_prev_btn"):
            self.history_prev_btn.setEnabled(self.history_page > 1)
        if hasattr(self, "history_next_btn"):
            self.history_next_btn.setEnabled(self.history_page < total_pages)

    def _refresh_history_view(self, *, reset_page: bool = False) -> None:
        if not hasattr(self, "history_table"):
            return
        if reset_page:
            self.history_page = 1
        if not self.history_store:
            self.history_entries = []
            self.history_filtered_entries = []
            self.history_visible_entries = []
            self.history_table.setRowCount(0)
            self.history_summary_label.setText(
                self.t("history_store_failed", err=self.history_store_error or "unknown error")
            )
            self._refresh_history_pagination_label()
            return

        try:
            self.history_entries = self.history_store.query_entries(
                code_filter=self.history_code_input.text().strip(),
                name_filter=self.history_name_input.text().strip(),
                url_filter=self.history_url_input.text().strip(),
            )
        except Exception as exc:
            self.history_entries = []
            self.history_filtered_entries = []
            self.history_visible_entries = []
            self.history_summary_label.setText(self.t("history_store_failed", err=str(exc)))
            self.history_table.setRowCount(0)
            self._refresh_history_pagination_label()
            return

        status_filter = str(self.history_status_filter.currentData() or "all")
        self.history_filtered_entries = [
            entry for entry in self.history_entries if self._history_matches_status_filter(entry, status_filter)
        ]

        total = len(self.history_filtered_entries)
        total_pages = max(1, (total + self.history_page_size - 1) // self.history_page_size) if total else 1
        self.history_page = max(1, min(self.history_page, total_pages))
        start = (self.history_page - 1) * self.history_page_size
        end = start + self.history_page_size
        self.history_visible_entries = self.history_filtered_entries[start:end]

        self.history_table.setRowCount(0)
        for entry in self.history_visible_entries:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            status, detail = self._history_entry_status(entry)
            values = [
                str(entry.id),
                entry.code,
                entry.name,
                self._history_status_text(status),
                entry.output_path,
                entry.url,
                entry.updated_at.replace("T", " "),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 3:
                    item.setForeground(QBrush(self._history_status_color(status)))
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 0:
                    item.setData(Qt.UserRole, entry.id)
                if column == 4 and detail:
                    item.setToolTip(detail)
                if column == 5:
                    item.setToolTip(entry.url)
                self.history_table.setItem(row, column, item)

        if total == 0:
            self.history_summary_label.setText(self.t("history_summary_empty"))
        else:
            self.history_summary_label.setText(
                self.t("history_summary_page", total=total, current=self.history_page, total_pages=total_pages)
            )
        self._refresh_history_pagination_label()

    def _reset_history_filters(self) -> None:
        self.history_code_input.clear()
        self.history_name_input.clear()
        self.history_url_input.clear()
        self.history_status_filter.blockSignals(True)
        index = self.history_status_filter.findData("all")
        if index >= 0:
            self.history_status_filter.setCurrentIndex(index)
        self.history_status_filter.blockSignals(False)
        self._refresh_history_view(reset_page=True)

    def _show_prev_history_page(self) -> None:
        if self.history_page <= 1:
            return
        self.history_page -= 1
        self._refresh_history_view()

    def _show_next_history_page(self) -> None:
        total = len(self.history_filtered_entries)
        total_pages = max(1, (total + self.history_page_size - 1) // self.history_page_size) if total else 1
        if self.history_page >= total_pages:
            return
        self.history_page += 1
        self._refresh_history_view()

    def _selected_history_entries(self) -> list[HistoryEntry]:
        if not hasattr(self, "history_table"):
            return []
        selected_rows = self.history_table.selectionModel().selectedRows() if self.history_table.selectionModel() else []
        if not selected_rows:
            return []
        visible_by_id = {entry.id: entry for entry in self.history_visible_entries}
        selected_entries: list[HistoryEntry] = []
        for model_index in selected_rows:
            id_item = self.history_table.item(model_index.row(), 0)
            if not id_item:
                continue
            try:
                entry_id = int(id_item.text())
            except Exception:
                continue
            entry = visible_by_id.get(entry_id)
            if entry:
                selected_entries.append(entry)
        return selected_entries

    def _scan_history_filtered_entries(self) -> None:
        if self.history_scan_thread and self.history_scan_thread.isRunning():
            return
        entries = list(self.history_filtered_entries)
        if not entries:
            QMessageBox.information(self, self.t("tip"), self.t("history_summary_empty"))
            return
        try:
            options = self._build_default_options()
        except Exception as exc:
            title = self.t("ffmpeg_missing") if isinstance(exc, FileNotFoundError) else self.t("tip")
            QMessageBox.critical(self, title, str(exc))
            return

        self.history_scan_btn.setEnabled(False)
        self.history_summary_label.setText(self.t("history_scan_running", total=len(entries)))

        self.history_scan_worker = HistoryScanWorker(entries, options)
        self.history_scan_thread = QThread(self)
        self.history_scan_worker.moveToThread(self.history_scan_thread)
        self.history_scan_thread.started.connect(self.history_scan_worker.run)
        self.history_scan_worker.progress.connect(self._on_history_scan_progress)
        self.history_scan_worker.finished.connect(self._on_history_scan_finished)
        self.history_scan_worker.finished.connect(self.history_scan_thread.quit)
        self.history_scan_thread.finished.connect(self.history_scan_worker.deleteLater)
        self.history_scan_thread.finished.connect(self.history_scan_thread.deleteLater)
        self.history_scan_thread.finished.connect(self._on_history_scan_thread_finished)
        self.history_scan_thread.start()

    @Slot(int, int, str)
    def _on_history_scan_progress(self, current: int, total: int, name: str) -> None:
        self.history_summary_label.setText(self.t("history_scan_progress", current=current, total=total, name=name))

    @Slot(object)
    def _on_history_scan_finished(self, results: object) -> None:
        ok_count = 0
        broken_count = 0
        missing_count = 0
        for entry_id, status, detail in list(results or []):
            self.history_media_status_by_id[int(entry_id)] = (str(status), str(detail or ""))
            if status == "ok":
                ok_count += 1
            elif status == "broken":
                broken_count += 1
            elif status == "missing":
                missing_count += 1
        if broken_count or missing_count:
            self.history_status_filter.blockSignals(True)
            issue_index = self.history_status_filter.findData("issue")
            if issue_index >= 0:
                self.history_status_filter.setCurrentIndex(issue_index)
            self.history_status_filter.blockSignals(False)
        self._refresh_history_view(reset_page=True)
        self.history_summary_label.setText(
            self.t("history_scan_done", ok=ok_count, broken=broken_count, missing=missing_count)
        )

    @Slot()
    def _on_history_scan_thread_finished(self) -> None:
        self.history_scan_btn.setEnabled(True)
        self.history_scan_worker = None
        self.history_scan_thread = None

    def _enqueue_history_entries_for_download(self, entries: list[HistoryEntry]) -> int:
        if not entries:
            QMessageBox.information(self, self.t("tip"), self.t("history_redownload_none"))
            return 0

        try:
            if self.worker and self.worker_thread and self.worker_thread.isRunning():
                output_dir = self.worker.output_dir
                options = self.worker.options
                jobs = self.worker.jobs
                running = True
            else:
                output_dir = self._resolve_output_dir()
                options = self._build_default_options()
                jobs = self.jobs_input.value()
                running = False
        except Exception as exc:
            title = self.t("ffmpeg_missing") if isinstance(exc, FileNotFoundError) else self.t("tip")
            QMessageBox.critical(self, title, str(exc))
            return 0

        existing_urls = {u.strip() for u in self.task_url_by_index.values()}
        used_names = self._current_used_output_names()
        next_index = self._next_task_index()
        tasks: list[DownloadTask] = []

        for entry in entries:
            url = entry.url.strip()
            if not is_probable_url(url) or url in existing_urls:
                continue
            tasks.append(
                build_task(
                    index=next_index,
                    url=url,
                    output_dir=output_dir,
                    used_names=used_names,
                    custom_name=entry.name,
                )
            )
            existing_urls.add(url)
            next_index += 1

        if not tasks:
            QMessageBox.information(self, self.t("tip"), self.t("history_redownload_none"))
            return 0

        if running:
            added = self._append_tasks_to_active_worker(tasks)
        else:
            self._start_worker_session(tasks, options, jobs, output_dir, clear_existing=False)
            added = len(tasks)
        self._set_active_page("download")
        self.summary_label.setText(self.t("history_redownload_added", added=added))
        return added

    def _redownload_selected_history_entries(self) -> None:
        entries = self._selected_history_entries()
        if not entries:
            QMessageBox.information(self, self.t("tip"), self.t("history_no_selection"))
            return
        self._enqueue_history_entries_for_download(entries)

    def _redownload_current_history_page(self) -> None:
        self._enqueue_history_entries_for_download(list(self.history_visible_entries))

    def _delete_selected_history_entries(self) -> None:
        entries = self._selected_history_entries()
        if not entries:
            QMessageBox.information(self, self.t("tip"), self.t("history_no_selection"))
            return
        ret = QMessageBox.question(
            self,
            self.t("history_confirm_delete"),
            self.t("history_confirm_delete_selected"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes or not self.history_store:
            return
        ids = [entry.id for entry in entries]
        try:
            self.history_store.delete_entries(ids)
        except Exception as exc:
            QMessageBox.warning(self, self.t("tip"), self.t("history_store_failed", err=str(exc)))
            return
        for entry_id in ids:
            self.history_media_status_by_id.pop(entry_id, None)
        self._refresh_history_view(reset_page=True)

    def _capture_resume_floor(self, task_index: int) -> None:
        bar = self.progress_by_index.get(task_index)
        if not bar or bar.maximum() == 0:
            return
        current = max(0, min(100, bar.value()))
        if current > 0:
            self.resume_progress_floor_by_index[task_index] = current

    def _remove_task_row(self, task_index: int) -> None:
        row = self.row_by_index.get(task_index)
        if row is None:
            return
        self.table.removeRow(row)
        self.row_by_index.pop(task_index, None)
        self.progress_by_index.pop(task_index, None)
        self.progress_wrap_by_index.pop(task_index, None)
        self.action_wrap_by_index.pop(task_index, None)
        self.pause_btn_by_index.pop(task_index, None)
        self.play_btn_by_index.pop(task_index, None)
        self.delete_btn_by_index.pop(task_index, None)
        self.task_status_by_index.pop(task_index, None)
        self.task_url_by_index.pop(task_index, None)
        self.task_output_path_by_index.pop(task_index, None)
        self.resume_progress_floor_by_index.pop(task_index, None)

        for idx, current_row in list(self.row_by_index.items()):
            if current_row > row:
                self.row_by_index[idx] = current_row - 1
        if self.table.rowCount() == 0 and not self.worker:
            self.summary_label.setText(self.t("summary_wait"))

    def _on_row_pause_clicked(self, task_index: int) -> None:
        if not self.worker:
            return
        status = self.task_status_by_index.get(task_index, "waiting")
        if status in {"deleted", "ok", "failed", "skipped"}:
            return
        if status == "paused":
            self._capture_resume_floor(task_index)
            self.worker.apply_command("resume", task_index)
            self.task_status_by_index[task_index] = "waiting"
            self._set_pause_btn_state(task_index, paused=False)
        else:
            self.worker.apply_command("pause", task_index)
            self.task_status_by_index[task_index] = "paused"
            self._set_pause_btn_state(task_index, paused=True)

    def _on_row_delete_clicked(self, task_index: int) -> None:
        status = self.task_status_by_index.get(task_index, "waiting")
        final_statuses = {"ok", "failed", "skipped", "deleted"}
        if not self.worker or status in final_statuses:
            ret = QMessageBox.question(
                self,
                self.t("dlg_confirm_delete"),
                self.t("dlg_confirm_delete_row"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ret == QMessageBox.Yes:
                self._remove_task_row(task_index)
            return

        ret = QMessageBox.question(
            self,
            self.t("dlg_confirm_delete"),
            self.t("dlg_confirm_delete_running"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self.worker.apply_command("delete", task_index)

    def _open_path(self, path: Path, missing_key: str) -> None:
        target = path.expanduser().resolve()
        if not target.exists():
            QMessageBox.warning(self, self.t("tip"), self.t(missing_key))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _open_download_folder(self) -> None:
        target_text = self.output_dir_input.text().strip()
        if not target_text:
            QMessageBox.warning(self, self.t("tip"), self.t("tip_dir_missing"))
            return
        self._open_path(Path(target_text), "tip_dir_missing")

    def _on_row_play_clicked(self, task_index: int) -> None:
        target = self.task_output_path_by_index.get(task_index)
        if not target:
            QMessageBox.warning(self, self.t("tip"), self.t("tip_file_missing"))
            return
        self._open_path(target, "tip_file_missing")

    def _toggle_pause_all(self) -> None:
        if not self.worker:
            return
        if self.pause_all_active:
            for task_index, status in list(self.task_status_by_index.items()):
                if status == "paused":
                    self._capture_resume_floor(task_index)
            self.worker.apply_command("resume_all")
            self.pause_all_active = False
            self.pause_all_btn.setText(self.t("pause_all"))
        else:
            self.worker.apply_command("pause_all")
            self.pause_all_active = True
            self.pause_all_btn.setText(self.t("resume_all"))

    def _clear_table_ui(self) -> None:
        self.table.setRowCount(0)
        self.row_by_index.clear()
        self.progress_by_index.clear()
        self.progress_wrap_by_index.clear()
        self.action_wrap_by_index.clear()
        self.pause_btn_by_index.clear()
        self.play_btn_by_index.clear()
        self.delete_btn_by_index.clear()
        self.task_status_by_index.clear()
        self.task_url_by_index.clear()
        self.task_output_path_by_index.clear()
        self.resume_progress_floor_by_index.clear()

    def _clear_tasks_confirm(self) -> None:
        if self.worker:
            ret = QMessageBox.question(
                self,
                self.t("dlg_confirm_clear"),
                self.t("dlg_confirm_clear_running"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            self.worker.apply_command("delete_all")
            self.summary_label.setText(self.t("summary_clear_requested"))
            return

        if self.table.rowCount() == 0:
            return
        ret = QMessageBox.question(
            self,
            self.t("dlg_confirm_clear"),
            self.t("dlg_confirm_clear_idle"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self._clear_table_ui()
            self.summary_label.setText(self.t("summary_cleared"))

    def _prepare_tasks(self) -> tuple[list[DownloadTask], DownloadOptions, int, Path] | None:
        raw_entries = self._collect_current_entries()
        if not raw_entries:
            QMessageBox.warning(self, self.t("tip"), self.t("tip_need_url"))
            return None

        try:
            output_dir = self._resolve_output_dir()
            options = self._build_default_options()
        except Exception as exc:
            title = self.t("ffmpeg_missing") if isinstance(exc, FileNotFoundError) else self.t("tip")
            QMessageBox.critical(self, title, str(exc))
            return None

        tasks = build_tasks(raw_entries, output_dir)
        jobs = self.jobs_input.value()
        return tasks, options, jobs, output_dir

    def _append_tasks_while_running(self) -> None:
        if not self.worker or not self.worker_thread or not self.worker_thread.isRunning():
            QMessageBox.information(self, self.t("tip"), self.t("tip_no_running"))
            return

        raw_entries = self._collect_current_entries()
        if not raw_entries:
            QMessageBox.warning(self, self.t("tip"), self.t("tip_need_more"))
            return

        output_dir = self.worker.output_dir

        existing_urls = {u.strip() for u in self.task_url_by_index.values()}
        filtered: list[tuple[str | None, str]] = []
        for name, url in raw_entries:
            final_url = url.strip()
            if not is_probable_url(final_url):
                continue
            if final_url in existing_urls:
                continue
            filtered.append((name, final_url))
            existing_urls.add(final_url)

        if not filtered:
            QMessageBox.information(
                self,
                self.t("tip"),
                self.t("tip_no_new"),
            )
            return

        used_names = {
            self.table.item(r, 1).text().strip().lower()
            for r in range(self.table.rowCount())
            if self.table.item(r, 1)
        }
        start_index = (max(self.row_by_index.keys()) + 1) if self.row_by_index else 1
        new_tasks = build_tasks(
            filtered,
            output_dir=output_dir,
            start_index=start_index,
            used_names=used_names,
        )
        self._append_tasks_to_active_worker(new_tasks)

    def _start_download(self) -> None:
        prepared = self._prepare_tasks()
        if not prepared:
            return
        tasks, options, jobs, output_dir = prepared
        self._start_worker_session(tasks, options, jobs, output_dir, clear_existing=True)

    @Slot(int, str, int, str)
    def _on_task_update(self, task_index: int, status: str, progress: int, detail: str) -> None:
        row = self.row_by_index.get(task_index)
        if row is None:
            return

        self.task_status_by_index[task_index] = status
        bar = self.progress_by_index.get(task_index)
        detail_item = self.table.item(row, 4)

        if status == "stage":
            self._set_progress_busy(task_index, True)
            localized_detail = self._localize_detail(detail)
            if "下载中" in detail:
                self._set_status(
                    row,
                    self.t("status_downloading"),
                    QColor("#42A5F5") if self.current_theme == "light" else QColor("#9CC8FF"),
                )
            else:
                self._set_status(
                    row,
                    localized_detail,
                    QColor("#42A5F5") if self.current_theme == "light" else QColor("#9CC8FF"),
                )
            if detail_item:
                detail_item.setText(localized_detail)
            self._set_pause_btn_state(task_index, paused=False)
            self._set_pause_btn_visible(task_index, True)
            self._set_play_btn_visible(task_index, False)
            return

        if status == "progress" and bar:
            self._set_progress_busy(task_index, True)
            if progress < 0:
                if bar.maximum() != 0:
                    bar.setRange(0, 0)
                    bar.setFormat(self.t("progress_loading"))
            else:
                floor = self.resume_progress_floor_by_index.get(task_index)
                if floor is not None and progress < floor:
                    if bar.maximum() == 0:
                        bar.setRange(0, 100)
                    bar.setValue(floor)
                    bar.setFormat(f"{floor}%")
                    return
                if floor is not None and progress >= floor:
                    self.resume_progress_floor_by_index.pop(task_index, None)
                if bar.maximum() == 0:
                    bar.setRange(0, 100)
                bar.setFormat(f"{progress}%")
                self._animate_progress(bar, progress)
            return

        if status == "running":
            self._set_progress_busy(task_index, True)
            self._set_status(
                row,
                self.t("status_waiting"),
                QColor("#3E63DD") if self.current_theme == "light" else QColor("#A7C5FF"),
            )
            self._set_pause_btn_state(task_index, paused=False)
            self._set_pause_btn_visible(task_index, True)
            self._set_play_btn_visible(task_index, False)
            self._set_delete_btn_enabled(task_index, True)
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

        if status == "ok":
            self.resume_progress_floor_by_index.pop(task_index, None)
            self._record_history_entry(task_index)
            self._set_progress_busy(task_index, False)
            self._set_status(
                row,
                self.t("status_done"),
                QColor("#1F8F4D") if self.current_theme == "light" else QColor("#86E3A8"),
            )
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_play_btn_visible(task_index, True)
            self._set_play_btn_enabled(task_index, self.task_output_path_by_index.get(task_index, Path()).exists())
            self._set_delete_btn_enabled(task_index, True)
            if bar:
                if bar.maximum() == 0:
                    bar.setRange(0, 100)
                bar.setFormat("100%")
                self._animate_progress(bar, 100)
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

        if status == "skipped":
            self.resume_progress_floor_by_index.pop(task_index, None)
            self._record_history_entry(task_index)
            self._set_progress_busy(task_index, False)
            self._set_status(
                row,
                self.t("status_skipped"),
                QColor("#AD6E00") if self.current_theme == "light" else QColor("#FFD287"),
            )
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_play_btn_visible(task_index, True)
            self._set_play_btn_enabled(task_index, self.task_output_path_by_index.get(task_index, Path()).exists())
            self._set_delete_btn_enabled(task_index, True)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(100)
                bar.setFormat("100%")
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

        if status == "paused":
            self._set_progress_busy(task_index, False)
            self._set_status(
                row,
                self.t("status_paused"),
                QColor("#A37200") if self.current_theme == "light" else QColor("#FFD287"),
            )
            self._set_pause_btn_state(task_index, paused=True)
            self._set_pause_btn_visible(task_index, True)
            self._set_play_btn_visible(task_index, False)
            if bar and bar.maximum() == 0:
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat(self.t("progress_paused"))
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

        if status == "deleted":
            self.resume_progress_floor_by_index.pop(task_index, None)
            self._set_progress_busy(task_index, False)
            self._set_status(
                row,
                self.t("status_deleted"),
                QColor("#C62828") if self.current_theme == "light" else QColor("#FF9A9A"),
            )
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_play_btn_visible(task_index, False)
            self._set_delete_btn_enabled(task_index, True)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat(self.t("progress_deleted"))
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

        if status == "failed":
            self.resume_progress_floor_by_index.pop(task_index, None)
            self._record_history_entry(task_index)
            self._set_progress_busy(task_index, False)
            self._set_status(
                row,
                self.t("status_failed"),
                QColor("#C62828") if self.current_theme == "light" else QColor("#FF9A9A"),
            )
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_play_btn_visible(task_index, False)
            self._set_delete_btn_enabled(task_index, True)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat(self.t("progress_failed"))
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

    @Slot(int, int, int, str)
    def _on_batch_done(self, success: int, skipped: int, failed: int, failure_file: str) -> None:
        self.pause_all_active = False
        self.pause_all_btn.setText(self.t("pause_all"))
        text = self.t("summary_done", success=success, skipped=skipped, failed=failed)
        if failure_file:
            text += self.t("summary_done_file", file=failure_file)
        self.summary_label.setText(text)

    @Slot()
    def _on_worker_finished(self) -> None:
        self.start_btn.setEnabled(True)
        self.pause_all_btn.setEnabled(False)
        self.add_more_btn.setEnabled(False)
        self.pause_all_btn.setText(self.t("pause_all"))
        self.worker = None
        self.worker_thread = None

    def closeEvent(self, event: object) -> None:
        ignore = getattr(event, "ignore", None)
        if callable(ignore) and not self._attempt_stop_worker_for_exit():
            ignore()
            return
        if self.history_scan_thread and self.history_scan_thread.isRunning():
            self.history_scan_thread.quit()
            self.history_scan_thread.wait(100)
        if self.local_api_server:
            self.local_api_server.stop()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setWindowIcon(create_app_icon())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
