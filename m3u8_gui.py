#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import os
import queue
import re
import shutil
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
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRectF,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
APP_DISPLAY_NAME = "M3U8-Downloader"
GITHUB_REPO = os.environ.get("M3U8_DOWNLOADER_GITHUB_REPO", "lengziyu/m3u8-downloader")


def normalize_version_text(text: str) -> str:
    value = (text or "").strip()
    if value.lower().startswith("v"):
        value = value[1:]
    return value or "1.0.0"


def read_local_version_file() -> str | None:
    version_file = Path(__file__).resolve().parent / "VERSION"
    if not version_file.exists():
        return None
    try:
        for line in version_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                return normalize_version_text(line)
    except Exception:
        return None
    return None


APP_VERSION = normalize_version_text(
    os.environ.get("M3U8_DOWNLOADER_APP_VERSION", "") or (read_local_version_file() or "1.0.0")
)

LANG_ORDER = ["zh", "en", "ja"]
LANG_LABEL = {"zh": "中", "en": "EN", "ja": "日"}
I18N = {
    "zh": {
        "settings_toggle": "⚙ 设置",
        "settings_title": "下载设置",
        "output_dir": "下载目录",
        "choose_dir": "选择目录",
        "jobs": "并发",
        "retries": "重试",
        "title_sub": "支持 Windows 10/11、macOS；批量下载为 MP4；失败任务自动导出",
        "input_title": "M3U8 链接输入",
        "single_hint": "逐条输入：每个输入框一个链接，填完会自动新增下一行",
        "single_remove": "删除",
        "batch_hint": "批量文本：支持多行，也支持一行用 | 分隔多个链接",
        "batch_clear": "清空",
        "tab_single": "逐条输入",
        "tab_batch": "批量文本",
        "start": "开始下载",
        "add_more": "继续添加",
        "summary_wait": "等待开始",
        "task_progress": "任务进度",
        "pause_all": "暂停全部",
        "resume_all": "继续全部",
        "clear_tasks": "清空任务",
        "col_idx": "序号",
        "col_name": "输出文件",
        "col_status": "状态",
        "col_progress": "进度",
        "col_detail": "详情",
        "col_actions": "操作",
        "version_checking": "⟳ 检查中... v{version}",
        "version_plain": "⟳ v{version}",
        "dlg_version": "版本检测",
        "version_repo_missing": "未配置 GitHub 仓库。请设置 m3u8_gui.py 中的 GITHUB_REPO，或设置环境变量 M3U8_DOWNLOADER_GITHUB_REPO=owner/repo。",
        "version_latest": "已是最新版本。\n当前版本：v{current}\n最新版本：{latest}",
        "dlg_new_version": "发现新版本",
        "version_update": "当前版本：v{current}\n最新版本：{latest}\n\n是否前往 Releases 下载更新？",
        "version_failed": "无法检测更新：{err}",
        "settings_collapse": "收起设置",
        "settings_expand": "展开设置",
        "status_waiting": "准备中",
        "status_downloading": "正在下载",
        "status_done": "已完成",
        "status_skipped": "已跳过",
        "status_paused": "已暂停",
        "status_deleted": "已删除",
        "status_failed": "下载失败",
        "row_pause": "暂停",
        "row_resume": "继续",
        "row_delete": "删除",
        "select_output_dir": "选择下载目录",
        "dlg_confirm_delete": "确认删除",
        "dlg_confirm_delete_running": "确定删除这个任务吗？运行中的任务会立即中断。",
        "dlg_confirm_delete_row": "确定从列表中移除这个任务吗？",
        "dlg_confirm_clear": "确认清空任务",
        "dlg_confirm_clear_running": "确定清空所有任务吗？正在下载的任务会被中断。",
        "dlg_confirm_clear_idle": "确定清空任务列表吗？",
        "summary_clear_requested": "已请求清空任务，等待当前线程退出...",
        "summary_cleared": "任务列表已清空",
        "tip": "提示",
        "tip_need_url": "请输入至少一个 m3u8 链接。",
        "tip_need_dir": "请先选择下载目录。",
        "tip_no_running": "当前没有运行中的任务，请使用“开始下载”。",
        "tip_need_more": "请输入要继续添加的链接。",
        "tip_no_new": "没有可添加的新任务（可能都重复或格式无效）。",
        "ffmpeg_missing": "ffmpeg 未找到",
        "summary_added": "已新增 {count} 个任务",
        "summary_preparing": "任务 {count} 条，准备开始...",
        "progress_loading": "加载中...",
        "progress_paused": "暂停",
        "progress_deleted": "已删",
        "progress_failed": "失败",
        "summary_done": "完成：成功 {success} | 跳过 {skipped} | 失败 {failed}",
        "summary_done_file": " | 失败清单：{file}",
        "dlg_batch_done": "任务完成",
        "dlg_batch_done_fail": "成功 {success}，跳过 {skipped}，失败 {failed}。\n失败清单已导出：\n{file}",
        "dlg_batch_done_ok": "全部完成。成功 {success}，跳过 {skipped}。",
        "single_placeholder": "https://example.com/video.m3u8",
        "batch_placeholder": "示例:\nhttps://example.com/episode01.m3u8\n日本語字幕|https://example.com/episode02.m3u8\nhttps://example.com/episode03.m3u8#日文\n\n或一行：\nhttps://a.m3u8|https://b.m3u8|https://c.m3u8",
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
    },
    "en": {
        "settings_toggle": "⚙ Settings",
        "settings_title": "Download Settings",
        "output_dir": "Output Folder",
        "choose_dir": "Choose Folder",
        "jobs": "Concurrency",
        "retries": "Retries",
        "title_sub": "Windows 10/11 & macOS; batch M3U8 to MP4; failed tasks auto-export",
        "input_title": "M3U8 Input",
        "single_hint": "Single mode: one URL per line edit; a new line is auto-created after input.",
        "single_remove": "Delete",
        "batch_hint": "Batch text: supports multiple lines, or single line separated by |.",
        "batch_clear": "Clear",
        "tab_single": "Single",
        "tab_batch": "Batch",
        "start": "Start Download",
        "add_more": "Add More",
        "summary_wait": "Waiting to start",
        "task_progress": "Task Progress",
        "pause_all": "Pause All",
        "resume_all": "Resume All",
        "clear_tasks": "Clear Tasks",
        "col_idx": "#",
        "col_name": "Output File",
        "col_status": "Status",
        "col_progress": "Progress",
        "col_detail": "Detail",
        "col_actions": "Action",
        "version_checking": "⟳ Checking... v{version}",
        "version_plain": "⟳ v{version}",
        "dlg_version": "Version Check",
        "version_repo_missing": "GitHub repo is not configured. Set GITHUB_REPO in m3u8_gui.py or M3U8_DOWNLOADER_GITHUB_REPO=owner/repo.",
        "version_latest": "You are up to date.\nCurrent: v{current}\nLatest: {latest}",
        "dlg_new_version": "Update Available",
        "version_update": "Current: v{current}\nLatest: {latest}\n\nOpen Releases page now?",
        "version_failed": "Update check failed: {err}",
        "settings_collapse": "Collapse settings",
        "settings_expand": "Expand settings",
        "status_waiting": "Waiting",
        "status_downloading": "Downloading",
        "status_done": "Done",
        "status_skipped": "Skipped",
        "status_paused": "Paused",
        "status_deleted": "Deleted",
        "status_failed": "Failed",
        "row_pause": "Pause",
        "row_resume": "Resume",
        "row_delete": "Delete",
        "select_output_dir": "Select Download Folder",
        "dlg_confirm_delete": "Confirm Delete",
        "dlg_confirm_delete_running": "Delete this task? Running task will stop immediately.",
        "dlg_confirm_delete_row": "Remove this task from the list?",
        "dlg_confirm_clear": "Confirm Clear",
        "dlg_confirm_clear_running": "Clear all tasks? Running tasks will be stopped.",
        "dlg_confirm_clear_idle": "Clear task list?",
        "summary_clear_requested": "Clear requested. Waiting for running workers to stop...",
        "summary_cleared": "Task list cleared",
        "tip": "Notice",
        "tip_need_url": "Please input at least one m3u8 URL.",
        "tip_need_dir": "Please choose output folder first.",
        "tip_no_running": "No running task. Click Start Download first.",
        "tip_need_more": "Please input URLs to add.",
        "tip_no_new": "No new task to add (duplicate or invalid).",
        "ffmpeg_missing": "ffmpeg not found",
        "summary_added": "{count} new task(s) added",
        "summary_preparing": "{count} task(s), preparing...",
        "progress_loading": "Loading...",
        "progress_paused": "Paused",
        "progress_deleted": "Deleted",
        "progress_failed": "Failed",
        "summary_done": "Done: success {success} | skipped {skipped} | failed {failed}",
        "summary_done_file": " | failed list: {file}",
        "dlg_batch_done": "Batch Completed",
        "dlg_batch_done_fail": "Success {success}, skipped {skipped}, failed {failed}.\nFailed list exported:\n{file}",
        "dlg_batch_done_ok": "All done. Success {success}, skipped {skipped}.",
        "single_placeholder": "https://example.com/video.m3u8",
        "batch_placeholder": "Examples:\nhttps://example.com/episode01.m3u8\nEnglish_sub|https://example.com/episode02.m3u8\nhttps://example.com/episode03.m3u8#JP\n\nOr one line:\nhttps://a.m3u8|https://b.m3u8|https://c.m3u8",
        "detail_wait_dispatch": "Queued",
        "detail_retry_wait": "Waiting before retry",
        "detail_validating": "Validating output",
        "detail_copy_fallback": "Copy failed, transcoding",
        "detail_copy_invalid_fix": "Copy completed but invalid output, repairing with transcode",
        "detail_finished": "Downloaded",
        "detail_skipped": "Output already exists",
        "detail_paused": "Paused",
        "detail_deleted": "Deleted",
        "detail_interrupted": "Interrupted",
        "detail_copy_transcoded": "Copy failed, auto transcoded",
        "detail_copy_fixed": "Invalid copy output fixed by transcode",
        "detail_unknown_err": "Unknown error",
        "detail_downloading_try": "Downloading (attempt {attempt}/{total})",
        "lang_tip": "Switch language",
    },
    "ja": {
        "settings_toggle": "⚙ 設定",
        "settings_title": "ダウンロード設定",
        "output_dir": "保存先フォルダ",
        "choose_dir": "フォルダ選択",
        "jobs": "並列数",
        "retries": "リトライ",
        "title_sub": "Windows 10/11・macOS 対応、M3U8 を MP4 に一括保存、失敗タスクを自動出力",
        "input_title": "M3U8 入力",
        "single_hint": "1件入力: 1行に1リンク。入力すると次の行が自動追加されます。",
        "single_remove": "削除",
        "batch_hint": "一括入力: 複数行、または 1 行を | 区切りで入力できます。",
        "batch_clear": "クリア",
        "tab_single": "1件入力",
        "tab_batch": "一括入力",
        "start": "ダウンロード開始",
        "add_more": "追加",
        "summary_wait": "開始待機中",
        "task_progress": "タスク進捗",
        "pause_all": "すべて一時停止",
        "resume_all": "すべて再開",
        "clear_tasks": "タスククリア",
        "col_idx": "番号",
        "col_name": "出力ファイル",
        "col_status": "状態",
        "col_progress": "進捗",
        "col_detail": "詳細",
        "col_actions": "操作",
        "version_checking": "⟳ 確認中... v{version}",
        "version_plain": "⟳ v{version}",
        "dlg_version": "バージョン確認",
        "version_repo_missing": "GitHub リポジトリが未設定です。m3u8_gui.py の GITHUB_REPO または M3U8_DOWNLOADER_GITHUB_REPO=owner/repo を設定してください。",
        "version_latest": "最新バージョンです。\n現在: v{current}\n最新: {latest}",
        "dlg_new_version": "新しいバージョン",
        "version_update": "現在: v{current}\n最新: {latest}\n\nReleases ページを開きますか？",
        "version_failed": "更新確認に失敗しました: {err}",
        "settings_collapse": "設定を折りたたむ",
        "settings_expand": "設定を展開",
        "status_waiting": "待機中",
        "status_downloading": "ダウンロード中",
        "status_done": "完了",
        "status_skipped": "スキップ",
        "status_paused": "一時停止",
        "status_deleted": "削除済み",
        "status_failed": "失敗",
        "row_pause": "停止",
        "row_resume": "再開",
        "row_delete": "削除",
        "select_output_dir": "保存先フォルダを選択",
        "dlg_confirm_delete": "削除確認",
        "dlg_confirm_delete_running": "このタスクを削除しますか？実行中の場合は中断されます。",
        "dlg_confirm_delete_row": "このタスクを一覧から削除しますか？",
        "dlg_confirm_clear": "クリア確認",
        "dlg_confirm_clear_running": "すべてのタスクをクリアしますか？実行中タスクは中断されます。",
        "dlg_confirm_clear_idle": "タスクリストをクリアしますか？",
        "summary_clear_requested": "クリア要求を送信しました。実行中タスクの終了を待っています...",
        "summary_cleared": "タスクリストをクリアしました",
        "tip": "ヒント",
        "tip_need_url": "少なくとも1つの m3u8 リンクを入力してください。",
        "tip_need_dir": "先に保存先フォルダを選択してください。",
        "tip_no_running": "実行中タスクがありません。先に開始してください。",
        "tip_need_more": "追加するリンクを入力してください。",
        "tip_no_new": "追加できる新規タスクがありません（重複/無効）。",
        "ffmpeg_missing": "ffmpeg が見つかりません",
        "summary_added": "{count} 件を追加しました",
        "summary_preparing": "{count} 件のタスクを準備中...",
        "progress_loading": "読み込み中...",
        "progress_paused": "停止",
        "progress_deleted": "削除",
        "progress_failed": "失敗",
        "summary_done": "完了: 成功 {success} | スキップ {skipped} | 失敗 {failed}",
        "summary_done_file": " | 失敗リスト: {file}",
        "dlg_batch_done": "タスク完了",
        "dlg_batch_done_fail": "成功 {success}、スキップ {skipped}、失敗 {failed}。\n失敗リストを出力しました:\n{file}",
        "dlg_batch_done_ok": "すべて完了。成功 {success}、スキップ {skipped}。",
        "single_placeholder": "https://example.com/video.m3u8",
        "batch_placeholder": "例:\nhttps://example.com/episode01.m3u8\n日本語字幕|https://example.com/episode02.m3u8\nhttps://example.com/episode03.m3u8#JP\n\nまたは1行:\nhttps://a.m3u8|https://b.m3u8|https://c.m3u8",
        "detail_wait_dispatch": "待機中",
        "detail_retry_wait": "再試行まで待機",
        "detail_validating": "ファイル検証中",
        "detail_copy_fallback": "copy 失敗、再エンコード中",
        "detail_copy_invalid_fix": "copy 成功だが異常、再エンコードで修復中",
        "detail_finished": "完了",
        "detail_skipped": "既に同名ファイルがあります",
        "detail_paused": "一時停止",
        "detail_deleted": "削除済み",
        "detail_interrupted": "中断されました",
        "detail_copy_transcoded": "copy 失敗、再エンコードで完了",
        "detail_copy_fixed": "copy 異常を再エンコードで修復",
        "detail_unknown_err": "不明なエラー",
        "detail_downloading_try": "ダウンロード中（{attempt}/{total} 回目）",
        "lang_tip": "言語切替",
    },
}


@dataclass(frozen=True)
class DownloadTask:
    index: int
    url: str
    output_path: Path


@dataclass(frozen=True)
class DownloadOptions:
    ffmpeg: str
    ffprobe: str | None
    retries: int
    overwrite: bool
    timeout: int
    user_agent: str | None
    referer: str | None
    headers: list[str]
    transcode_on_fail: bool
    validate_after_copy: bool


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", name).strip().strip(".")
    return cleaned or "video"


def is_probable_url(text: str) -> bool:
    value = text.strip().lower()
    return value.startswith("http://") or value.startswith("https://")


def parse_url_lines(raw_text: str) -> list[tuple[str | None, str]]:
    entries: list[tuple[str | None, str]] = []
    for line in raw_text.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue

        # Allow paste format like "url1|url2|url3"
        if "|" in text:
            parts = [p.strip() for p in text.split("|") if p.strip()]
            if parts and all(is_probable_url(p) for p in parts):
                for p in parts:
                    entries.append((None, p))
                continue

            name, url = text.split("|", 1)
            final_url = url.strip()
            if final_url and is_probable_url(final_url):
                entries.append((name.strip() or None, final_url))
                continue

        # Allow multiple URLs separated by spaces in one line.
        tokens = [t.strip() for t in re.split(r"\s+", text) if t.strip()]
        if len(tokens) > 1 and all(is_probable_url(t) for t in tokens):
            for t in tokens:
                entries.append((None, t))
            continue

        entries.append((None, text))
    return entries


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
            stem = Path(unquote(parsed.path)).stem
            base = sanitize_filename(stem) if stem else f"video_{index:03d}"
    if base.lower().endswith(".mp4"):
        return base
    return f"{base}.mp4"


def create_app_icon(size: int = 256) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    card = QPainterPath()
    card.addRoundedRect(QRectF(6, 6, size - 12, size - 12), 46, 46)
    painter.fillPath(card, QColor("#8A5BFF"))

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    shaft_w = size * 0.10
    shaft_h = size * 0.25
    shaft_x = (size - shaft_w) / 2
    shaft_y = size * 0.30
    painter.drawRoundedRect(QRectF(shaft_x, shaft_y, shaft_w, shaft_h), 10, 10)

    arrow = QPainterPath()
    arrow.moveTo(size * 0.34, size * 0.52)
    arrow.lineTo(size * 0.5, size * 0.70)
    arrow.lineTo(size * 0.66, size * 0.52)
    arrow.closeSubpath()
    painter.fillPath(arrow, QColor("#FFFFFF"))

    painter.setPen(QPen(QColor("#FFFFFF"), max(6, size // 28)))
    painter.drawLine(int(size * 0.28), int(size * 0.78), int(size * 0.72), int(size * 0.78))
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


def hls_input_args() -> list[str]:
    return [
        "-protocol_whitelist",
        "file,http,https,tcp,tls,crypto,data",
        "-allowed_extensions",
        "ALL",
        "-allowed_segment_extensions",
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


def subprocess_no_window_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if flags:
        return {"creationflags": flags}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"startupinfo": startupinfo}


def probe_duration_seconds(url: str, options: DownloadOptions) -> float | None:
    if not options.ffprobe:
        return None

    cmd = [
        options.ffprobe,
        "-v",
        "error",
        *hls_input_args(),
        *header_args(options.user_agent, options.referer, options.headers),
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
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

    cmd.extend(hls_input_args())
    cmd.extend(header_args(options.user_agent, options.referer, options.headers))
    cmd.extend(["-i", task.url])
    cmd.extend(codec_args)
    cmd.append(str(task.output_path))

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
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
            **subprocess_no_window_kwargs(),
        )
        if proc.returncode != 0:
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
        **subprocess_no_window_kwargs(),
    )
    if test_proc.returncode != 0:
        return False, "解码测试失败"

    return True, None


def download_single_task(
    task: DownloadTask,
    options: DownloadOptions,
    on_stage: Callable[[str], None],
    on_progress: Callable[[int], None],
    should_abort: Callable[[], str | None] | None = None,
) -> tuple[str, str | None]:
    if task.output_path.exists() and not options.overwrite:
        return "skipped", "目标文件已存在"

    duration = probe_duration_seconds(task.url, options)

    def cleanup_partial_output() -> None:
        try:
            if task.output_path.exists():
                task.output_path.unlink()
        except OSError:
            pass

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
        if should_abort:
            abort_status = should_abort()
            if abort_status:
                cleanup_partial_output()
                return abort_status, "任务已中断"
        on_stage(f"下载中（尝试 {attempt}/{total_attempts}）")
        ok, err = run_ffmpeg_with_progress(
            task, options, copy_args, duration, on_progress, should_abort
        )
        if ok:
            if not options.validate_after_copy:
                on_progress(100)
                return "ok", None

            on_stage("校验文件")
            media_ok, media_reason = validate_output_media(task.output_path, options)
            if media_ok:
                on_progress(100)
                return "ok", None
            if options.transcode_on_fail:
                on_stage("copy 成功但文件异常，转码修复中")
                try:
                    if task.output_path.exists():
                        task.output_path.unlink()
                except OSError:
                    pass
                ok2, err2 = run_ffmpeg_with_progress(
                    task, options, transcode_args, duration, on_progress, should_abort
                )
                if ok2:
                    on_stage("校验文件")
                    media_ok2, media_reason2 = validate_output_media(task.output_path, options)
                    if media_ok2:
                        on_progress(100)
                        return "ok", "copy 文件异常，已自动转码修复"
                    return "failed", f"转码后校验失败: {media_reason2 or 'unknown'}"
                if err2 and err2.startswith("__ABORT__:"):
                    return err2.split(":", 1)[1], "任务已中断"
                return "failed", f"copy 成功但文件异常({media_reason}); 转码失败: {err2 or 'unknown'}"
            return "failed", f"copy 成功但文件异常: {media_reason or 'unknown'}"
        if err and err.startswith("__ABORT__:"):
            cleanup_partial_output()
            return err.split(":", 1)[1], "任务已中断"

        last_error = f"copy 失败: {err or 'unknown'}"

        if options.transcode_on_fail:
            on_stage("copy 失败，转码中")
            ok2, err2 = run_ffmpeg_with_progress(
                task, options, transcode_args, duration, on_progress, should_abort
            )
            if ok2:
                on_progress(100)
                return "ok", "copy 失败，已自动转码"
            if err2 and err2.startswith("__ABORT__:"):
                cleanup_partial_output()
                return err2.split(":", 1)[1], "任务已中断"
            last_error = f"{last_error}; transcode 失败: {err2 or 'unknown'}"

        if attempt < total_attempts:
            on_stage("重试等待中")
            wait_time = min(2 * attempt, 8)
            end_time = time.monotonic() + wait_time
            while time.monotonic() < end_time:
                if should_abort:
                    abort_status = should_abort()
                    if abort_status:
                        return abort_status, "任务已中断"
                time.sleep(0.2)

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


class MainWindow(QMainWindow):
    update_check_done = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1240, 830)
        self.setWindowIcon(create_app_icon())

        self.current_theme = "purple"
        self.current_lang = "zh"
        self.settings_panel_expanded = True
        self.settings_anim: QParallelAnimationGroup | None = None
        self.worker_thread: QThread | None = None
        self.worker: BatchWorker | None = None
        self.row_by_index: dict[int, int] = {}
        self.progress_by_index: dict[int, QProgressBar] = {}
        self.pause_btn_by_index: dict[int, QPushButton] = {}
        self.delete_btn_by_index: dict[int, QPushButton] = {}
        self.task_status_by_index: dict[int, str] = {}
        self.task_url_by_index: dict[int, str] = {}
        self.pause_all_active = False
        self.update_checking = False

        self._build_ui()
        self.update_check_done.connect(self._on_update_check_done)
        self._apply_theme(self.current_theme)
        self._refresh_i18n_texts()
        self._animate_window_enter()

    def t(self, key: str, **kwargs: object) -> str:
        lang_pack = I18N.get(self.current_lang, I18N["zh"])
        template = lang_pack.get(key) or I18N["zh"].get(key) or key
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("root")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(22, 20, 22, 20)
        shell.setSpacing(14)

        self.settings_panel = QFrame()
        self.settings_panel.setObjectName("settingsPanel")
        self.settings_panel.setMinimumWidth(280)
        self.settings_panel.setMaximumWidth(280)
        settings_layout = QVBoxLayout(self.settings_panel)
        settings_layout.setContentsMargins(10, 12, 10, 12)
        settings_layout.setSpacing(10)

        self.settings_toggle_btn = QPushButton("")
        self.settings_toggle_btn.setObjectName("settingsToggleBtn")
        self.settings_toggle_btn.setMinimumHeight(40)
        self.settings_toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.settings_toggle_btn.clicked.connect(self._toggle_settings_panel)
        settings_layout.addWidget(self.settings_toggle_btn, 0, Qt.AlignHCenter)

        self.settings_content = QWidget()
        self.settings_content.setObjectName("settingsContent")
        settings_content_layout = QVBoxLayout(self.settings_content)
        settings_content_layout.setContentsMargins(6, 4, 6, 4)
        settings_content_layout.setSpacing(12)

        self.settings_title_label = QLabel("")
        self.settings_title_label.setObjectName("sectionTitle")
        settings_content_layout.addWidget(self.settings_title_label)

        self.output_label = QLabel("")
        self.output_label.setObjectName("fieldLabel")
        self.output_dir_input = QLineEdit(str((Path.cwd() / "downloads").resolve()))
        self.output_dir_input.setObjectName("pathInput")
        self.browse_btn = QPushButton("")
        self.browse_btn.setObjectName("secondaryBtn")
        self.browse_btn.clicked.connect(self._choose_output_dir)

        settings_content_layout.addWidget(self.output_label)
        settings_content_layout.addWidget(self.output_dir_input)
        settings_content_layout.addWidget(self.browse_btn)

        self.jobs_label = QLabel("")
        self.jobs_label.setObjectName("fieldLabel")
        self.jobs_input = QSpinBox()
        self.jobs_input.setRange(10, 200)
        self.jobs_input.setSingleStep(10)
        self.jobs_input.setValue(20)
        self.jobs_input.setObjectName("spinBox")
        self.jobs_input.setButtonSymbols(QSpinBox.NoButtons)
        self.jobs_input.setAlignment(Qt.AlignCenter)

        self.jobs_minus_btn = QPushButton("−")
        self.jobs_minus_btn.setObjectName("stepBtn")
        self.jobs_minus_btn.setFixedSize(34, 34)
        self.jobs_minus_btn.clicked.connect(
            lambda: self.jobs_input.setValue(
                max(self.jobs_input.minimum(), self.jobs_input.value() - 10)
            )
        )

        self.jobs_plus_btn = QPushButton("+")
        self.jobs_plus_btn.setObjectName("stepBtn")
        self.jobs_plus_btn.setFixedSize(34, 34)
        self.jobs_plus_btn.clicked.connect(
            lambda: self.jobs_input.setValue(
                min(self.jobs_input.maximum(), self.jobs_input.value() + 10)
            )
        )

        jobs_row = QHBoxLayout()
        jobs_row.setSpacing(8)
        jobs_row.addWidget(self.jobs_minus_btn)
        jobs_row.addWidget(self.jobs_input, 1)
        jobs_row.addWidget(self.jobs_plus_btn)

        self.retries_label = QLabel("")
        self.retries_label.setObjectName("fieldLabel")
        self.retries_input = QSpinBox()
        self.retries_input.setRange(0, 10)
        self.retries_input.setValue(2)
        self.retries_input.setObjectName("spinBox")
        self.retries_input.setButtonSymbols(QSpinBox.NoButtons)
        self.retries_input.setAlignment(Qt.AlignCenter)

        self.retries_minus_btn = QPushButton("−")
        self.retries_minus_btn.setObjectName("stepBtn")
        self.retries_minus_btn.setFixedSize(34, 34)
        self.retries_minus_btn.clicked.connect(
            lambda: self.retries_input.setValue(
                max(self.retries_input.minimum(), self.retries_input.value() - 1)
            )
        )

        self.retries_plus_btn = QPushButton("+")
        self.retries_plus_btn.setObjectName("stepBtn")
        self.retries_plus_btn.setFixedSize(34, 34)
        self.retries_plus_btn.clicked.connect(
            lambda: self.retries_input.setValue(
                min(self.retries_input.maximum(), self.retries_input.value() + 1)
            )
        )

        retries_row = QHBoxLayout()
        retries_row.setSpacing(8)
        retries_row.addWidget(self.retries_minus_btn)
        retries_row.addWidget(self.retries_input, 1)
        retries_row.addWidget(self.retries_plus_btn)

        settings_content_layout.addWidget(self.jobs_label)
        settings_content_layout.addLayout(jobs_row)
        settings_content_layout.addWidget(self.retries_label)
        settings_content_layout.addLayout(retries_row)
        settings_content_layout.addStretch(1)
        settings_layout.addWidget(self.settings_content, 1)

        self.version_btn = QPushButton()
        self.version_btn.setObjectName("versionBtn")
        self.version_btn.setMinimumHeight(34)
        self.version_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.version_btn.clicked.connect(self._check_updates)
        settings_layout.addWidget(self.version_btn, 0, Qt.AlignBottom | Qt.AlignHCenter)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 16)
        header_layout.setSpacing(12)

        self.title_label = QLabel(APP_DISPLAY_NAME)
        self.title_label.setObjectName("titleLabel")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("subtitleLabel")
        self.lang_btn = QPushButton("")
        self.lang_btn.setObjectName("themeIconBtn")
        self.lang_btn.setFixedSize(38, 38)
        self.lang_btn.clicked.connect(self._toggle_language)
        self.theme_btn = QPushButton("◐")
        self.theme_btn.setObjectName("themeIconBtn")
        self.theme_btn.setFixedSize(38, 38)
        self.theme_btn.clicked.connect(self._toggle_theme)

        header_layout.addWidget(self.title_label, 0, Qt.AlignVCenter)
        header_layout.addWidget(self.subtitle_label, 0, Qt.AlignVCenter)
        header_layout.addStretch(1)
        header_layout.addWidget(self.lang_btn, 0, Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self.theme_btn, 0, Qt.AlignRight | Qt.AlignVCenter)

        right_layout.addWidget(header)

        input_card = QFrame()
        input_card.setObjectName("card")
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(20, 18, 20, 18)
        input_layout.setSpacing(10)

        self.input_title_label = QLabel("")
        self.input_title_label.setObjectName("sectionTitle")

        self.input_tabs = QTabWidget()
        self.input_tabs.setObjectName("inputTabs")
        self.input_tabs.setMinimumHeight(190)

        single_tab = QWidget()
        single_layout = QVBoxLayout(single_tab)
        single_layout.setContentsMargins(6, 8, 6, 6)
        single_layout.setSpacing(8)

        single_hint_row = QHBoxLayout()
        single_hint_row.setContentsMargins(0, 0, 0, 0)
        single_hint_row.setSpacing(8)
        self.single_hint_label = QLabel("")
        self.single_hint_label.setObjectName("inputHintLabel")
        self.single_remove_btn = QPushButton("")
        self.single_remove_btn.setObjectName("miniBtn")
        self.single_remove_btn.setMinimumHeight(24)
        self.single_remove_btn.clicked.connect(self._on_single_remove_clicked)
        single_hint_row.addWidget(self.single_hint_label, 1)
        single_hint_row.addWidget(self.single_remove_btn, 0, Qt.AlignRight)
        single_layout.addLayout(single_hint_row)

        self.single_scroll = QScrollArea()
        self.single_scroll.setObjectName("singleScroll")
        self.single_scroll.setWidgetResizable(True)
        self.single_scroll.setFrameShape(QFrame.NoFrame)
        self.single_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.single_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.single_container = QWidget()
        self.single_container.setObjectName("singleContainer")
        self.single_lines_layout = QVBoxLayout(self.single_container)
        self.single_lines_layout.setContentsMargins(2, 2, 2, 2)
        self.single_lines_layout.setSpacing(8)
        self.single_url_inputs: list[QLineEdit] = []
        self._append_single_input_row()

        self.single_scroll.setWidget(self.single_container)
        single_layout.addWidget(self.single_scroll, 1)

        batch_tab = QWidget()
        batch_layout = QVBoxLayout(batch_tab)
        batch_layout.setContentsMargins(6, 8, 6, 10)
        batch_layout.setSpacing(8)

        batch_hint_row = QHBoxLayout()
        batch_hint_row.setContentsMargins(0, 0, 0, 0)
        batch_hint_row.setSpacing(8)
        self.batch_hint_label = QLabel("")
        self.batch_hint_label.setObjectName("inputHintLabel")
        self.batch_clear_btn = QPushButton("")
        self.batch_clear_btn.setObjectName("miniBtn")
        self.batch_clear_btn.setMinimumHeight(24)
        self.batch_clear_btn.clicked.connect(lambda: self.url_input.clear())
        batch_hint_row.addWidget(self.batch_hint_label, 1)
        batch_hint_row.addWidget(self.batch_clear_btn, 0, Qt.AlignRight)
        self.url_input = QTextEdit()
        self.url_input.setObjectName("urlInput")
        self.url_input.setMinimumHeight(140)
        batch_layout.addLayout(batch_hint_row)
        batch_layout.addWidget(self.url_input, 1)
        batch_layout.addSpacing(2)

        self.input_tabs.addTab(single_tab, "")
        self.input_tabs.addTab(batch_tab, "")

        input_layout.addWidget(self.input_title_label)
        input_layout.addWidget(self.input_tabs)
        right_layout.addWidget(input_card)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.start_btn = QPushButton("")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setMinimumHeight(48)
        self.start_btn.clicked.connect(self._start_download)

        self.add_more_btn = QPushButton("")
        self.add_more_btn.setObjectName("tableActionBtn")
        self.add_more_btn.setMinimumHeight(48)
        self.add_more_btn.setEnabled(False)
        self.add_more_btn.clicked.connect(self._append_tasks_while_running)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("summaryLabel")

        action_row.addWidget(self.start_btn, 0)
        action_row.addWidget(self.add_more_btn, 0)
        action_row.addWidget(self.summary_label, 1)
        right_layout.addLayout(action_row)

        table_card = QFrame()
        table_card.setObjectName("card")
        table_card.setMinimumHeight(440)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 12, 16, 14)
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

        self.clear_tasks_btn = QPushButton("")
        self.clear_tasks_btn.setObjectName("dangerBtn")
        self.clear_tasks_btn.setMinimumHeight(36)
        self.clear_tasks_btn.clicked.connect(self._clear_tasks_confirm)

        table_head.addWidget(self.pause_all_btn)
        table_head.addWidget(self.clear_tasks_btn)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "", "", "", "", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.Interactive)
        header_view.setSectionResizeMode(5, QHeaderView.Interactive)
        self.table.setColumnWidth(4, 230)
        self.table.setColumnWidth(5, 200)

        table_layout.addLayout(table_head)
        table_layout.addWidget(self.table)
        right_layout.addWidget(table_card, 1)

        shell.addWidget(self.settings_panel, 0)
        shell.addWidget(right, 1)

        self._set_settings_panel_expanded(True, animate=False)

    def _animate_window_enter(self) -> None:
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(420)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _animate_theme_switch(self) -> None:
        self.setWindowOpacity(0.92)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setStartValue(0.92)
        anim.setEndValue(1.0)
        anim.setDuration(280)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _toggle_settings_panel(self) -> None:
        self._set_settings_panel_expanded(not self.settings_panel_expanded, animate=True)

    def _toggle_language(self) -> None:
        cur_idx = LANG_ORDER.index(self.current_lang) if self.current_lang in LANG_ORDER else 0
        self.current_lang = LANG_ORDER[(cur_idx + 1) % len(LANG_ORDER)]
        self._refresh_i18n_texts()

    def _refresh_i18n_texts(self) -> None:
        self.settings_title_label.setText(self.t("settings_title"))
        self.output_label.setText(self.t("output_dir"))
        self.browse_btn.setText(self.t("choose_dir"))
        self.jobs_label.setText(self.t("jobs"))
        self.retries_label.setText(self.t("retries"))
        self.title_label.setText(APP_DISPLAY_NAME)
        self.subtitle_label.setText(self.t("title_sub"))
        self.input_title_label.setText(self.t("input_title"))
        self.single_hint_label.setText(self.t("single_hint"))
        self.batch_hint_label.setText(self.t("batch_hint"))
        self.single_remove_btn.setText(self.t("single_remove"))
        self.batch_clear_btn.setText(self.t("batch_clear"))
        self.start_btn.setText(self.t("start"))
        self.add_more_btn.setText(self.t("add_more"))
        self.table_title_label.setText(self.t("task_progress"))
        self.pause_all_btn.setText(self.t("resume_all") if self.pause_all_active else self.t("pause_all"))
        self.clear_tasks_btn.setText(self.t("clear_tasks"))
        self.summary_label.setText(self.summary_label.text() or self.t("summary_wait"))
        self.input_tabs.setTabText(0, self.t("tab_single"))
        self.input_tabs.setTabText(1, self.t("tab_batch"))
        self.url_input.setPlaceholderText(self.t("batch_placeholder"))
        for line in self.single_url_inputs:
            line.setPlaceholderText(self.t("single_placeholder"))
        self.lang_btn.setText(LANG_LABEL.get(self.current_lang, "中"))
        self.lang_btn.setToolTip(self.t("lang_tip"))

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
            if status == "paused":
                pause_btn.setText(self.t("row_resume"))
            else:
                pause_btn.setText(self.t("row_pause"))
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

        self._set_settings_panel_expanded(self.settings_panel_expanded, animate=False)
        self._update_version_btn_text()

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
        if self.settings_panel_expanded:
            if self.update_checking:
                self.version_btn.setText(self.t("version_checking", version=APP_VERSION))
            else:
                self.version_btn.setText(self.t("version_plain", version=APP_VERSION))
        else:
            self.version_btn.setText("⟳")

    def _check_updates(self) -> None:
        if self.update_checking:
            return
        if not GITHUB_REPO or GITHUB_REPO.startswith("YOUR_GITHUB_OWNER/"):
            QMessageBox.information(
                self,
                self.t("dlg_version"),
                self.t("version_repo_missing"),
            )
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

    def _set_settings_panel_expanded(self, expanded: bool, animate: bool) -> None:
        self.settings_panel_expanded = expanded
        target = 280 if expanded else 72
        current = self.settings_panel.maximumWidth()

        if self.settings_anim:
            try:
                self.settings_anim.stop()
            except RuntimeError:
                pass
            self.settings_anim = None

        if animate:
            group = QParallelAnimationGroup(self)
            for prop in (b"minimumWidth", b"maximumWidth"):
                anim = QPropertyAnimation(self.settings_panel, prop, group)
                anim.setStartValue(current)
                anim.setEndValue(target)
                anim.setDuration(220)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                group.addAnimation(anim)
            group.finished.connect(lambda: setattr(self, "settings_anim", None))
            group.start()
            self.settings_anim = group
        else:
            self.settings_panel.setMinimumWidth(target)
            self.settings_panel.setMaximumWidth(target)

        self.settings_content.setVisible(expanded)
        self.settings_toggle_btn.setText(self.t("settings_toggle") if expanded else "⚙")
        self.settings_toggle_btn.setToolTip(self.t("settings_collapse") if expanded else self.t("settings_expand"))
        self._update_version_btn_text()
        if expanded:
            self.settings_toggle_btn.setMinimumSize(0, 40)
            self.settings_toggle_btn.setMaximumHeight(40)
            self.settings_toggle_btn.setMaximumWidth(16777215)
            self.version_btn.setMinimumSize(0, 34)
            self.version_btn.setMaximumHeight(34)
            self.version_btn.setMaximumWidth(16777215)
            self.settings_toggle_btn.setStyleSheet("")
            self.version_btn.setStyleSheet("")
        else:
            self.settings_toggle_btn.setMinimumSize(40, 40)
            self.settings_toggle_btn.setMaximumSize(40, 40)
            self.version_btn.setMinimumSize(40, 40)
            self.version_btn.setMaximumSize(40, 40)
            self.settings_toggle_btn.setStyleSheet(
                "padding: 0px; text-align: center; font-size: 20px;"
            )
            self.version_btn.setStyleSheet(
                "padding: 0px; text-align: center; font-size: 18px;"
            )

    def _apply_theme(self, theme: str) -> None:
        if theme == "purple":
            stylesheet = """
                #root {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #231338, stop:1 #171025);
                }
                QFrame#headerCard {
                    border-radius: 18px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #7B43FF, stop:1 #A66BFF);
                }
                QFrame#settingsPanel {
                    border-radius: 16px;
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.16);
                }
                QPushButton#settingsToggleBtn {
                    border-radius: 11px;
                    border: 1px solid rgba(255, 255, 255, 0.28);
                    background: rgba(255, 255, 255, 0.14);
                    color: #F4EDFF;
                    padding: 8px 12px;
                    font-size: 16px;
                    font-weight: 700;
                    text-align: left;
                }
                QPushButton#settingsToggleBtn:hover {
                    background: rgba(255, 255, 255, 0.22);
                }
                QPushButton#versionBtn {
                    border-radius: 10px;
                    border: 1px solid rgba(255, 255, 255, 0.24);
                    background: rgba(255, 255, 255, 0.10);
                    color: #EFE6FF;
                    font-size: 15px;
                    font-weight: 700;
                    padding: 7px 10px;
                    text-align: left;
                }
                QPushButton#versionBtn:hover {
                    background: rgba(255, 255, 255, 0.18);
                }
                QPushButton#versionBtn:disabled {
                    color: #BFAEE6;
                }
                QFrame#card {
                    border-radius: 16px;
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                }
                QLabel#titleLabel {
                    color: #FFFFFF;
                    font-size: 26px;
                    font-weight: 700;
                }
                QLabel#subtitleLabel {
                    color: #EFE9FF;
                    font-size: 13px;
                }
                QLabel#inputHintLabel {
                    color: #E7DAFF;
                    font-size: 12px;
                }
                QLabel#sectionTitle {
                    color: #EEE5FF;
                    font-size: 16px;
                    font-weight: 650;
                }
                QLabel#fieldLabel {
                    color: #ECE4FF;
                    font-weight: 600;
                }
                QLabel#summaryLabel {
                    color: #E9DEFF;
                    font-size: 14px;
                    font-weight: 600;
                }
                QTabWidget#inputTabs::pane {
                    border: 1px solid rgba(255, 255, 255, 0.20);
                    border-radius: 10px;
                    top: -1px;
                }
                QTabWidget#inputTabs QTabBar::tab {
                    background: rgba(255, 255, 255, 0.10);
                    color: #EFE6FF;
                    padding: 7px 12px;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    margin-right: 6px;
                }
                QTabWidget#inputTabs QTabBar::tab:selected {
                    background: rgba(156, 108, 255, 0.60);
                }
                QScrollArea#singleScroll, QWidget#singleContainer {
                    background: transparent;
                    border: 0;
                }
                QTextEdit#urlInput, QLineEdit#pathInput, QLineEdit#urlLineInput, QSpinBox#spinBox {
                    border: 1px solid rgba(255, 255, 255, 0.24);
                    border-radius: 10px;
                    background: rgba(255, 255, 255, 0.10);
                    color: #FFFFFF;
                    padding: 10px;
                    selection-background-color: #9E73FF;
                }
                QTextEdit#urlInput {
                    padding-bottom: 14px;
                }
                QSpinBox#spinBox {
                    min-width: 74px;
                    padding: 8px 6px;
                }
                QPushButton#stepBtn {
                    border-radius: 10px;
                    border: 1px solid rgba(255, 255, 255, 0.30);
                    background: rgba(255, 255, 255, 0.12);
                    color: #FFFFFF;
                    font-size: 18px;
                    font-weight: 700;
                }
                QPushButton#stepBtn:hover {
                    background: rgba(255, 255, 255, 0.20);
                }
                QPushButton#secondaryBtn {
                    border-radius: 10px;
                    border: 1px solid rgba(255, 255, 255, 0.24);
                    background: rgba(255, 255, 255, 0.10);
                    color: #F2EBFF;
                    padding: 10px 14px;
                    font-weight: 600;
                }
                QPushButton#secondaryBtn:hover {
                    background: rgba(255, 255, 255, 0.18);
                }
                QPushButton#miniBtn {
                    border-radius: 8px;
                    border: 1px solid rgba(255, 255, 255, 0.24);
                    background: rgba(255, 255, 255, 0.10);
                    color: #F2EBFF;
                    padding: 2px 10px;
                    font-size: 12px;
                    font-weight: 650;
                }
                QPushButton#miniBtn:hover {
                    background: rgba(255, 255, 255, 0.18);
                }
                QPushButton#themeIconBtn {
                    border-radius: 19px;
                    border: 1px solid rgba(255, 255, 255, 0.28);
                    background: rgba(255, 255, 255, 0.18);
                    color: #FFFFFF;
                    font-size: 18px;
                    font-weight: 700;
                }
                QPushButton#themeIconBtn:hover {
                    background: rgba(255, 255, 255, 0.28);
                }
                QPushButton#startBtn {
                    border-radius: 12px;
                    border: 0;
                    background: #9C6BFF;
                    color: #FFFFFF;
                    padding: 12px 26px;
                    font-size: 16px;
                    font-weight: 700;
                }
                QPushButton#startBtn:hover {
                    background: #AE85FF;
                }
                QPushButton#startBtn:disabled {
                    background: #7059A6;
                    color: #D9CFFF;
                }
                QPushButton#tableActionBtn {
                    border-radius: 10px;
                    border: 1px solid rgba(255, 255, 255, 0.26);
                    background: rgba(255, 255, 255, 0.14);
                    color: #F2EBFF;
                    padding: 8px 12px;
                    font-weight: 700;
                }
                QPushButton#tableActionBtn:hover {
                    background: rgba(255, 255, 255, 0.22);
                }
                QPushButton#tableActionBtn:disabled {
                    background: rgba(255, 255, 255, 0.10);
                    color: #B8A7DF;
                }
                QPushButton#dangerBtn {
                    border-radius: 10px;
                    border: 1px solid rgba(255, 132, 145, 0.68);
                    background: rgba(255, 104, 124, 0.24);
                    color: #FFD9DF;
                    padding: 8px 12px;
                    font-weight: 700;
                }
                QPushButton#dangerBtn:hover {
                    background: rgba(255, 104, 124, 0.34);
                }
                QPushButton#rowPauseBtn {
                    border-radius: 8px;
                    border: 1px solid rgba(255, 255, 255, 0.24);
                    background: rgba(255, 255, 255, 0.12);
                    color: #FFFFFF;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: 650;
                }
                QPushButton#rowPauseBtn:hover {
                    background: rgba(255, 255, 255, 0.20);
                }
                QPushButton#rowDeleteBtn {
                    border-radius: 8px;
                    border: 1px solid rgba(255, 132, 145, 0.68);
                    background: rgba(255, 104, 124, 0.22);
                    color: #FFD9DF;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: 650;
                }
                QPushButton#rowDeleteBtn:hover {
                    background: rgba(255, 104, 124, 0.34);
                }
                QTableWidget {
                    border: 1px solid rgba(255, 255, 255, 0.20);
                    border-radius: 12px;
                    background: rgba(255, 255, 255, 0.08);
                    color: #FFFFFF;
                    gridline-color: rgba(255, 255, 255, 0.14);
                    alternate-background-color: rgba(255, 255, 255, 0.06);
                }
                QHeaderView::section {
                    background: rgba(255, 255, 255, 0.16);
                    color: #F1E8FF;
                    border: 0;
                    padding: 8px;
                    font-weight: 700;
                }
                QProgressBar {
                    border: 1px solid rgba(255, 255, 255, 0.24);
                    border-radius: 5px;
                    background: rgba(255, 255, 255, 0.07);
                    text-align: center;
                    color: #FFFFFF;
                    min-width: 200px;
                    min-height: 12px;
                }
                QProgressBar::chunk {
                    border-radius: 4px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #8E5BFF, stop:1 #C37BFF);
                }
            """
            self.theme_btn.setText("☾")
        else:
            stylesheet = """
                #root {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #FDFDFF, stop:1 #EEF1F8);
                }
                QFrame#headerCard {
                    border-radius: 18px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #8D5BFF, stop:1 #B286FF);
                }
                QFrame#settingsPanel {
                    border-radius: 16px;
                    background: #FFFFFF;
                    border: 1px solid #DDE1EB;
                }
                QPushButton#settingsToggleBtn {
                    border-radius: 11px;
                    border: 1px solid #CFD5E3;
                    background: #F8F9FC;
                    color: #253148;
                    padding: 8px 12px;
                    font-size: 16px;
                    font-weight: 700;
                    text-align: left;
                }
                QPushButton#settingsToggleBtn:hover {
                    background: #EEF2FA;
                }
                QPushButton#versionBtn {
                    border-radius: 10px;
                    border: 1px solid #CFD5E3;
                    background: #F8F9FC;
                    color: #2A3346;
                    font-size: 15px;
                    font-weight: 700;
                    padding: 7px 10px;
                    text-align: left;
                }
                QPushButton#versionBtn:hover {
                    background: #EEF2FA;
                }
                QPushButton#versionBtn:disabled {
                    color: #8C99B1;
                }
                QFrame#card {
                    border-radius: 16px;
                    background: #FFFFFF;
                    border: 1px solid #DDE1EB;
                }
                QLabel#titleLabel {
                    color: #FFFFFF;
                    font-size: 26px;
                    font-weight: 700;
                }
                QLabel#subtitleLabel {
                    color: #F4EDFF;
                    font-size: 13px;
                }
                QLabel#inputHintLabel {
                    color: #30384A;
                    font-size: 12px;
                    font-weight: 600;
                }
                QLabel#sectionTitle {
                    color: #1F2430;
                    font-size: 16px;
                    font-weight: 650;
                }
                QLabel#fieldLabel {
                    color: #242A36;
                    font-weight: 600;
                }
                QLabel#summaryLabel {
                    color: #2B3242;
                    font-size: 14px;
                    font-weight: 600;
                }
                QTabWidget#inputTabs::pane {
                    border: 1px solid #D9DFEC;
                    border-radius: 10px;
                    top: -1px;
                }
                QTabWidget#inputTabs QTabBar::tab {
                    background: #F3F6FC;
                    color: #2A3346;
                    padding: 7px 12px;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    margin-right: 6px;
                }
                QTabWidget#inputTabs QTabBar::tab:selected {
                    background: #E5ECFA;
                }
                QScrollArea#singleScroll, QWidget#singleContainer {
                    background: transparent;
                    border: 0;
                }
                QTextEdit#urlInput, QLineEdit#pathInput, QLineEdit#urlLineInput, QSpinBox#spinBox {
                    border: 1px solid #C7B8F2;
                    border-radius: 10px;
                    background: #F2ECFF;
                    color: #251F34;
                    padding: 10px;
                    selection-background-color: #A77BFF;
                }
                QTextEdit#urlInput {
                    padding-bottom: 14px;
                }
                QSpinBox#spinBox {
                    min-width: 74px;
                    padding: 8px 6px;
                }
                QPushButton#stepBtn {
                    border-radius: 10px;
                    border: 1px solid #C7D0E2;
                    background: #EEF2FA;
                    color: #243046;
                    font-size: 18px;
                    font-weight: 700;
                }
                QPushButton#stepBtn:hover {
                    background: #E1E8F6;
                }
                QPushButton#secondaryBtn {
                    border-radius: 10px;
                    border: 1px solid #CFD5E3;
                    background: #F8F9FC;
                    color: #1E2532;
                    padding: 10px 14px;
                    font-weight: 600;
                }
                QPushButton#secondaryBtn:hover {
                    background: #EEF2FA;
                }
                QPushButton#miniBtn {
                    border-radius: 8px;
                    border: 1px solid #CFD5E3;
                    background: #F8F9FC;
                    color: #1E2532;
                    padding: 2px 10px;
                    font-size: 12px;
                    font-weight: 650;
                }
                QPushButton#miniBtn:hover {
                    background: #EEF2FA;
                }
                QPushButton#themeIconBtn {
                    border-radius: 19px;
                    border: 1px solid #C7D0E2;
                    background: #FFFFFF;
                    color: #283347;
                    font-size: 18px;
                    font-weight: 700;
                }
                QPushButton#themeIconBtn:hover {
                    background: #F3F6FC;
                }
                QPushButton#startBtn {
                    border-radius: 12px;
                    border: 0;
                    background: #8A5BFF;
                    color: #FFFFFF;
                    padding: 12px 26px;
                    font-size: 16px;
                    font-weight: 700;
                }
                QPushButton#startBtn:hover {
                    background: #9C71FF;
                }
                QPushButton#startBtn:disabled {
                    background: #AD9BD8;
                    color: #F4EEFF;
                }
                QPushButton#tableActionBtn {
                    border-radius: 10px;
                    border: 1px solid #CAD2E5;
                    background: #F2F5FB;
                    color: #263247;
                    padding: 8px 12px;
                    font-weight: 700;
                }
                QPushButton#tableActionBtn:hover {
                    background: #E8EEF8;
                }
                QPushButton#tableActionBtn:disabled {
                    background: #F7F9FD;
                    color: #96A2BA;
                }
                QPushButton#dangerBtn {
                    border-radius: 10px;
                    border: 1px solid #F1A6B2;
                    background: #FFE7EB;
                    color: #A12C44;
                    padding: 8px 12px;
                    font-weight: 700;
                }
                QPushButton#dangerBtn:hover {
                    background: #FFDCE3;
                }
                QPushButton#rowPauseBtn {
                    border-radius: 8px;
                    border: 1px solid #CAD2E5;
                    background: #F2F5FB;
                    color: #243146;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: 650;
                }
                QPushButton#rowPauseBtn:hover {
                    background: #E8EEF8;
                }
                QPushButton#rowDeleteBtn {
                    border-radius: 8px;
                    border: 1px solid #F1A6B2;
                    background: #FFE7EB;
                    color: #A12C44;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: 650;
                }
                QPushButton#rowDeleteBtn:hover {
                    background: #FFDCE3;
                }
                QTableWidget {
                    border: 1px solid #D9DFEC;
                    border-radius: 12px;
                    background: #FFFFFF;
                    color: #1F2430;
                    gridline-color: #E3E8F4;
                    alternate-background-color: #F8FAFF;
                }
                QHeaderView::section {
                    background: #EFF3FA;
                    color: #2A3343;
                    border: 0;
                    padding: 8px;
                    font-weight: 700;
                }
                QProgressBar {
                    border: 1px solid #CBD4E6;
                    border-radius: 5px;
                    background: #F7F9FD;
                    text-align: center;
                    color: #1F2430;
                    min-width: 200px;
                    min-height: 12px;
                }
                QProgressBar::chunk {
                    border-radius: 4px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #8A5BFF, stop:1 #B27BFF);
                }
            """
            self.theme_btn.setText("☼")

        self.setStyleSheet(stylesheet)
        self._update_version_btn_text()

    def _toggle_theme(self) -> None:
        self.current_theme = "light" if self.current_theme == "purple" else "purple"
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

    def _add_table_row(self, task: DownloadTask) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 44)
        self.row_by_index[task.index] = row
        self.task_status_by_index[task.index] = "waiting"
        self.task_url_by_index[task.index] = task.url

        idx_item = QTableWidgetItem(str(task.index))
        name_item = QTableWidgetItem(task.output_path.name)
        status_item = QTableWidgetItem(self.t("status_waiting"))
        detail_item = QTableWidgetItem(task.url)
        idx_item.setTextAlignment(Qt.AlignCenter)
        status_item.setTextAlignment(Qt.AlignCenter)

        self.table.setItem(row, 0, idx_item)
        self.table.setItem(row, 1, name_item)
        self.table.setItem(row, 2, status_item)
        self.table.setItem(row, 4, detail_item)

        bar_wrap = QWidget()
        bar_layout = QHBoxLayout(bar_wrap)
        bar_layout.setContentsMargins(8, 0, 8, 0)
        bar_layout.setSpacing(0)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFormat("0%")
        bar.setFixedHeight(12)
        bar_layout.addWidget(bar, 1, Qt.AlignVCenter)
        self.table.setCellWidget(row, 3, bar_wrap)
        self.progress_by_index[task.index] = bar

        action_wrap = QWidget()
        action_layout = QHBoxLayout(action_wrap)
        action_layout.setContentsMargins(10, 6, 10, 6)
        action_layout.setSpacing(10)

        pause_btn = QPushButton(self.t("row_pause"))
        pause_btn.setObjectName("rowPauseBtn")
        pause_btn.setMinimumHeight(24)
        pause_btn.setFixedWidth(56)
        pause_btn.clicked.connect(lambda _, idx=task.index: self._on_row_pause_clicked(idx))

        delete_btn = QPushButton(self.t("row_delete"))
        delete_btn.setObjectName("rowDeleteBtn")
        delete_btn.setMinimumHeight(24)
        delete_btn.setFixedWidth(56)
        delete_btn.clicked.connect(lambda _, idx=task.index: self._on_row_delete_clicked(idx))

        action_layout.addStretch(1)
        action_layout.addWidget(pause_btn)
        action_layout.addWidget(delete_btn)
        action_layout.addStretch(1)
        self.table.setCellWidget(row, 5, action_wrap)
        self.pause_btn_by_index[task.index] = pause_btn
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
        line = QLineEdit(text)
        line.setObjectName("urlLineInput")
        line.setPlaceholderText(self.t("single_placeholder"))
        line.textChanged.connect(lambda _=None, l=line: self._on_single_input_changed(l))
        self.single_lines_layout.addWidget(line)
        self.single_url_inputs.append(line)

    def _remove_single_input_row(self, line: QLineEdit) -> None:
        self.single_lines_layout.removeWidget(line)
        if line in self.single_url_inputs:
            self.single_url_inputs.remove(line)
        line.deleteLater()

    def _on_single_input_changed(self, line: QLineEdit) -> None:
        if self.single_url_inputs and line is self.single_url_inputs[-1] and line.text().strip():
            self._append_single_input_row()

        while (
            len(self.single_url_inputs) >= 2
            and not self.single_url_inputs[-1].text().strip()
            and not self.single_url_inputs[-2].text().strip()
        ):
            self._remove_single_input_row(self.single_url_inputs[-1])

    def _on_single_remove_clicked(self) -> None:
        if not self.single_url_inputs:
            self._append_single_input_row()
            return
        if len(self.single_url_inputs) == 1:
            self.single_url_inputs[0].clear()
            return
        if not self.single_url_inputs[-1].text().strip():
            target = self.single_url_inputs[-2]
        else:
            target = self.single_url_inputs[-1]
        self._remove_single_input_row(target)
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

    def _remove_task_row(self, task_index: int) -> None:
        row = self.row_by_index.get(task_index)
        if row is None:
            return
        self.table.removeRow(row)
        self.row_by_index.pop(task_index, None)
        self.progress_by_index.pop(task_index, None)
        self.pause_btn_by_index.pop(task_index, None)
        self.delete_btn_by_index.pop(task_index, None)
        self.task_status_by_index.pop(task_index, None)
        self.task_url_by_index.pop(task_index, None)

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

    def _toggle_pause_all(self) -> None:
        if not self.worker:
            return
        if self.pause_all_active:
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
        self.pause_btn_by_index.clear()
        self.delete_btn_by_index.clear()
        self.task_status_by_index.clear()
        self.task_url_by_index.clear()

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

        out_dir_text = self.output_dir_input.text().strip()
        if not out_dir_text:
            QMessageBox.warning(self, self.t("tip"), self.t("tip_need_dir"))
            return None

        output_dir = Path(out_dir_text).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            ffmpeg = check_ffmpeg_bin("ffmpeg")
        except Exception as exc:
            QMessageBox.critical(self, self.t("ffmpeg_missing"), str(exc))
            return None

        options = DownloadOptions(
            ffmpeg=ffmpeg,
            ffprobe=resolve_ffprobe_bin(),
            retries=self.retries_input.value(),
            overwrite=False,
            timeout=30,
            user_agent=None,
            referer=None,
            headers=[],
            transcode_on_fail=True,
            validate_after_copy=False,
        )

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

        output_dir = Path(self.output_dir_input.text().strip()).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

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
        for task in new_tasks:
            self._add_table_row(task)

        added = self.worker.enqueue_tasks(new_tasks)
        if added > 0:
            self.pause_all_btn.setEnabled(True)
            self.add_more_btn.setEnabled(True)
            self.summary_label.setText(self.t("summary_added", count=added))

    def _start_download(self) -> None:
        prepared = self._prepare_tasks()
        if not prepared:
            return
        tasks, options, jobs, output_dir = prepared

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

    @Slot(int, str, int, str)
    def _on_task_update(self, task_index: int, status: str, progress: int, detail: str) -> None:
        row = self.row_by_index.get(task_index)
        if row is None:
            return

        self.task_status_by_index[task_index] = status
        bar = self.progress_by_index.get(task_index)
        detail_item = self.table.item(row, 4)

        if status == "stage":
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
            return

        if status == "progress" and bar:
            if progress < 0:
                if bar.maximum() != 0:
                    bar.setRange(0, 0)
                    bar.setFormat(self.t("progress_loading"))
            else:
                if bar.maximum() == 0:
                    bar.setRange(0, 100)
                bar.setFormat(f"{progress}%")
                self._animate_progress(bar, progress)
            return

        if status == "running":
            self._set_status(
                row,
                self.t("status_waiting"),
                QColor("#3E63DD") if self.current_theme == "light" else QColor("#A7C5FF"),
            )
            self._set_pause_btn_state(task_index, paused=False)
            self._set_pause_btn_visible(task_index, True)
            self._set_delete_btn_enabled(task_index, True)
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

        if status == "ok":
            self._set_status(
                row,
                self.t("status_done"),
                QColor("#1F8F4D") if self.current_theme == "light" else QColor("#86E3A8"),
            )
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
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
            self._set_status(
                row,
                self.t("status_skipped"),
                QColor("#AD6E00") if self.current_theme == "light" else QColor("#FFD287"),
            )
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_delete_btn_enabled(task_index, True)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(100)
                bar.setFormat("100%")
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

        if status == "paused":
            self._set_status(
                row,
                self.t("status_paused"),
                QColor("#A37200") if self.current_theme == "light" else QColor("#FFD287"),
            )
            self._set_pause_btn_state(task_index, paused=True)
            self._set_pause_btn_visible(task_index, True)
            if bar and bar.maximum() == 0:
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat(self.t("progress_paused"))
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

        if status == "deleted":
            self._set_status(
                row,
                self.t("status_deleted"),
                QColor("#C62828") if self.current_theme == "light" else QColor("#FF9A9A"),
            )
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_delete_btn_enabled(task_index, True)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat(self.t("progress_deleted"))
            if detail_item:
                detail_item.setText(self._localize_detail(detail))
            return

        if status == "failed":
            self._set_status(
                row,
                self.t("status_failed"),
                QColor("#C62828") if self.current_theme == "light" else QColor("#FF9A9A"),
            )
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
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

        if failed > 0:
            QMessageBox.warning(
                self,
                self.t("dlg_batch_done"),
                self.t("dlg_batch_done_fail", success=success, skipped=skipped, failed=failed, file=failure_file),
            )
        else:
            QMessageBox.information(
                self,
                self.t("dlg_batch_done"),
                self.t("dlg_batch_done_ok", success=success, skipped=skipped),
            )

    @Slot()
    def _on_worker_finished(self) -> None:
        self.start_btn.setEnabled(True)
        self.pause_all_btn.setEnabled(False)
        self.add_more_btn.setEnabled(False)
        self.pause_all_btn.setText(self.t("pause_all"))
        self.worker = None
        self.worker_thread = None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setWindowIcon(create_app_icon())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
