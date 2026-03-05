#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QBrush
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


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


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", name).strip().strip(".")
    return cleaned or "video"


def parse_url_lines(raw_text: str) -> list[tuple[str | None, str]]:
    entries: list[tuple[str | None, str]] = []
    for line in raw_text.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if "|" in text:
            name, url = text.split("|", 1)
            final_url = url.strip()
            if final_url:
                entries.append((name.strip() or None, final_url))
        else:
            entries.append((None, text))
    return entries


def build_output_name(index: int, url: str, custom_name: str | None) -> str:
    if custom_name:
        base = sanitize_filename(custom_name)
    else:
        parsed = urlparse(url)
        stem = Path(unquote(parsed.path)).stem
        base = sanitize_filename(stem) if stem else f"video_{index:03d}"
    if base.lower().endswith(".mp4"):
        return base
    return f"{base}.mp4"


def build_tasks(entries: list[tuple[str | None, str]], output_dir: Path) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    used_names: set[str] = set()
    for idx, (name, url) in enumerate(entries, start=1):
        candidate = build_output_name(idx, url, name)
        stem = Path(candidate).stem
        final = candidate
        suffix = 1
        while final.lower() in used_names:
            final = f"{stem}_{suffix}.mp4"
            suffix += 1
        used_names.add(final.lower())
        tasks.append(DownloadTask(index=idx, url=url, output_path=output_dir / final))
    return tasks


def _candidate_binary_names(name: str) -> list[str]:
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return [name, f"{name}.exe"]
    return [name]


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
    local = _try_resolve_local_binary(ffmpeg_bin)
    if local:
        return local

    resolved = shutil.which(ffmpeg_bin)
    if resolved:
        return resolved

    raise FileNotFoundError(
        "找不到 ffmpeg。请先安装 ffmpeg 并加入 PATH，"
        "或使用一键打包脚本把 ffmpeg 一起打进客户端。"
    )


def resolve_ffprobe_bin() -> str | None:
    local = _try_resolve_local_binary("ffprobe")
    if local:
        return local
    return shutil.which("ffprobe")


def header_args(user_agent: str | None, referer: str | None, headers: list[str]) -> list[str]:
    args: list[str] = []
    if user_agent:
        args.extend(["-user_agent", user_agent])

    merged_headers: list[str] = []
    if referer:
        merged_headers.append(f"Referer: {referer}")
    merged_headers.extend(headers)

    if merged_headers:
        blob = "".join(f"{h}\r\n" for h in merged_headers)
        args.extend(["-headers", blob])
    return args


def probe_duration_seconds(url: str, options: DownloadOptions) -> float | None:
    if not options.ffprobe:
        return None

    cmd = [
        options.ffprobe,
        "-v",
        "error",
        *header_args(options.user_agent, options.referer, options.headers),
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
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
    )

    error_lines: list[str] = []
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
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
    finally:
        return_code = proc.wait()

    if return_code == 0:
        return True, None

    err = " | ".join(error_lines).strip()
    return False, err or "ffmpeg 执行失败"


def download_single_task(
    task: DownloadTask,
    options: DownloadOptions,
    on_stage: Callable[[str], None],
    on_progress: Callable[[int], None],
) -> tuple[str, str | None]:
    if task.output_path.exists() and not options.overwrite:
        return "skipped", "目标文件已存在"

    duration = probe_duration_seconds(task.url, options)

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
        on_stage(f"下载中（尝试 {attempt}/{total_attempts}）")
        ok, err = run_ffmpeg_with_progress(task, options, copy_args, duration, on_progress)
        if ok:
            on_progress(100)
            return "ok", None

        last_error = f"copy 失败: {err or 'unknown'}"

        if options.transcode_on_fail:
            on_stage("copy 失败，转码中")
            ok2, err2 = run_ffmpeg_with_progress(
                task, options, transcode_args, duration, on_progress
            )
            if ok2:
                on_progress(100)
                return "ok", "copy 失败，已自动转码"
            last_error = f"{last_error}; transcode 失败: {err2 or 'unknown'}"

        if attempt < total_attempts:
            on_stage("重试等待中")
            time.sleep(min(2 * attempt, 8))

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

    @Slot()
    def run(self) -> None:
        success = 0
        skipped = 0
        failed = 0
        failures: list[tuple[DownloadTask, str]] = []
        lock = threading.Lock()

        def run_one(task: DownloadTask) -> tuple[str, DownloadTask, str | None]:
            self.task_update.emit(task.index, "running", 0, "准备中")

            def stage_cb(stage: str) -> None:
                self.task_update.emit(task.index, "stage", -2, stage)

            def progress_cb(percent: int) -> None:
                self.task_update.emit(task.index, "progress", percent, "")

            status, detail = download_single_task(task, self.options, stage_cb, progress_cb)
            return status, task, detail

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.jobs) as pool:
            future_map = {pool.submit(run_one, task): task for task in self.tasks}
            for future in concurrent.futures.as_completed(future_map):
                status, task, detail = future.result()
                if status == "ok":
                    with lock:
                        success += 1
                    self.task_update.emit(task.index, "ok", 100, detail or "下载完成")
                elif status == "skipped":
                    with lock:
                        skipped += 1
                    self.task_update.emit(task.index, "skipped", 100, detail or "已跳过")
                else:
                    with lock:
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

        self.batch_done.emit(success, skipped, failed, failure_file)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("M3U8 Batch Downloader")
        self.resize(1240, 830)

        self.current_theme = "purple"
        self.worker_thread: QThread | None = None
        self.worker: BatchWorker | None = None
        self.row_by_index: dict[int, int] = {}
        self.progress_by_index: dict[int, QProgressBar] = {}

        self._build_ui()
        self._apply_theme(self.current_theme)
        self._animate_window_enter()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(14)

        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 18)
        header_layout.setSpacing(6)

        title = QLabel("M3U8 批量下载器")
        title.setObjectName("titleLabel")
        subtitle = QLabel("支持 Windows 10/11、macOS；批量下载为 MP4；失败任务自动导出")
        subtitle.setObjectName("subtitleLabel")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        outer.addWidget(header)

        input_card = QFrame()
        input_card.setObjectName("card")
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(20, 18, 20, 18)
        input_layout.setSpacing(10)

        input_title = QLabel("M3U8 链接输入（支持多行；格式可为 文件名|URL）")
        input_title.setObjectName("sectionTitle")

        self.url_input = QTextEdit()
        self.url_input.setObjectName("urlInput")
        self.url_input.setPlaceholderText(
            "示例:\n"
            "episode_01|https://example.com/1.m3u8\n"
            "episode_02|https://example.com/2.m3u8\n"
            "https://example.com/3.m3u8"
        )
        self.url_input.setMinimumHeight(170)

        input_layout.addWidget(input_title)
        input_layout.addWidget(self.url_input)
        outer.addWidget(input_card)

        controls = QFrame()
        controls.setObjectName("card")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(20, 16, 20, 16)
        controls_layout.setSpacing(12)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        output_label = QLabel("下载目录")
        output_label.setObjectName("fieldLabel")
        self.output_dir_input = QLineEdit(str((Path.cwd() / "downloads").resolve()))
        self.output_dir_input.setObjectName("pathInput")
        browse_btn = QPushButton("选择目录")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self._choose_output_dir)

        row1.addWidget(output_label)
        row1.addWidget(self.output_dir_input, 1)
        row1.addWidget(browse_btn)

        row2 = QHBoxLayout()
        row2.setSpacing(10)

        jobs_label = QLabel("并发")
        jobs_label.setObjectName("fieldLabel")
        self.jobs_input = QSpinBox()
        self.jobs_input.setRange(1, 16)
        self.jobs_input.setValue(max(1, min(4, os.cpu_count() or 4)))
        self.jobs_input.setObjectName("spinBox")

        retries_label = QLabel("重试")
        retries_label.setObjectName("fieldLabel")
        self.retries_input = QSpinBox()
        self.retries_input.setRange(0, 10)
        self.retries_input.setValue(2)
        self.retries_input.setObjectName("spinBox")

        self.theme_btn = QPushButton("切换到白色主题")
        self.theme_btn.setObjectName("secondaryBtn")
        self.theme_btn.clicked.connect(self._toggle_theme)

        row2.addWidget(jobs_label)
        row2.addWidget(self.jobs_input)
        row2.addSpacing(8)
        row2.addWidget(retries_label)
        row2.addWidget(self.retries_input)
        row2.addStretch(1)
        row2.addWidget(self.theme_btn)

        controls_layout.addLayout(row1)
        controls_layout.addLayout(row2)
        outer.addWidget(controls)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.start_btn = GlowButton("开始下载")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setMinimumHeight(48)
        self.start_btn.clicked.connect(self._start_download)

        self.summary_label = QLabel("等待开始")
        self.summary_label.setObjectName("summaryLabel")

        action_row.addWidget(self.start_btn, 0)
        action_row.addWidget(self.summary_label, 1)
        outer.addLayout(action_row)

        table_card = QFrame()
        table_card.setObjectName("card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 12, 16, 14)
        table_layout.setSpacing(10)

        table_title = QLabel("任务进度")
        table_title.setObjectName("sectionTitle")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["序号", "输出文件", "状态", "进度", "详情"])
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
        header_view.setSectionResizeMode(4, QHeaderView.Stretch)

        table_layout.addWidget(table_title)
        table_layout.addWidget(self.table)
        outer.addWidget(table_card, 1)

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
                QFrame#card {
                    border-radius: 16px;
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                }
                QLabel#titleLabel {
                    color: #FFFFFF;
                    font-size: 28px;
                    font-weight: 700;
                }
                QLabel#subtitleLabel {
                    color: #EFE9FF;
                    font-size: 14px;
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
                QTextEdit#urlInput, QLineEdit#pathInput, QSpinBox#spinBox {
                    border: 1px solid rgba(255, 255, 255, 0.24);
                    border-radius: 10px;
                    background: rgba(255, 255, 255, 0.10);
                    color: #FFFFFF;
                    padding: 10px;
                    selection-background-color: #9E73FF;
                }
                QSpinBox#spinBox {
                    min-width: 90px;
                    padding-right: 8px;
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
                    border-radius: 8px;
                    background: rgba(255, 255, 255, 0.07);
                    text-align: center;
                    color: #FFFFFF;
                    min-width: 200px;
                    min-height: 18px;
                }
                QProgressBar::chunk {
                    border-radius: 7px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #8E5BFF, stop:1 #C37BFF);
                }
            """
            self.theme_btn.setText("切换到白色主题")
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
                QFrame#card {
                    border-radius: 16px;
                    background: #FFFFFF;
                    border: 1px solid #DDE1EB;
                }
                QLabel#titleLabel {
                    color: #FFFFFF;
                    font-size: 28px;
                    font-weight: 700;
                }
                QLabel#subtitleLabel {
                    color: #F4EDFF;
                    font-size: 14px;
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
                QTextEdit#urlInput, QLineEdit#pathInput, QSpinBox#spinBox {
                    border: 1px solid #CFD5E3;
                    border-radius: 10px;
                    background: #FFFFFF;
                    color: #1F2430;
                    padding: 10px;
                    selection-background-color: #BFA3FF;
                }
                QSpinBox#spinBox {
                    min-width: 90px;
                    padding-right: 8px;
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
                    border-radius: 8px;
                    background: #F7F9FD;
                    text-align: center;
                    color: #1F2430;
                    min-width: 200px;
                    min-height: 18px;
                }
                QProgressBar::chunk {
                    border-radius: 7px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #8A5BFF, stop:1 #B27BFF);
                }
            """
            self.theme_btn.setText("切换到紫色主题")

        self.setStyleSheet(stylesheet)

    def _toggle_theme(self) -> None:
        self.current_theme = "light" if self.current_theme == "purple" else "purple"
        self._apply_theme(self.current_theme)
        self._animate_theme_switch()

    def _choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择下载目录",
            self.output_dir_input.text().strip() or str(Path.cwd()),
        )
        if folder:
            self.output_dir_input.setText(folder)

    def _add_table_row(self, task: DownloadTask) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.row_by_index[task.index] = row

        idx_item = QTableWidgetItem(str(task.index))
        name_item = QTableWidgetItem(task.output_path.name)
        status_item = QTableWidgetItem("等待中")
        detail_item = QTableWidgetItem(task.url)

        self.table.setItem(row, 0, idx_item)
        self.table.setItem(row, 1, name_item)
        self.table.setItem(row, 2, status_item)
        self.table.setItem(row, 4, detail_item)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setFormat("0%")
        self.table.setCellWidget(row, 3, bar)
        self.progress_by_index[task.index] = bar

    def _set_status(self, row: int, text: str, color: QColor) -> None:
        item = self.table.item(row, 2)
        if item is None:
            return
        item.setText(text)
        item.setForeground(QBrush(color))

    def _animate_progress(self, bar: QProgressBar, target: int) -> None:
        anim = QPropertyAnimation(bar, b"value", bar)
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.setDuration(260)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _prepare_tasks(self) -> tuple[list[DownloadTask], DownloadOptions, int, Path] | None:
        raw_entries = parse_url_lines(self.url_input.toPlainText())
        if not raw_entries:
            QMessageBox.warning(self, "提示", "请输入至少一个 m3u8 链接。")
            return None

        out_dir_text = self.output_dir_input.text().strip()
        if not out_dir_text:
            QMessageBox.warning(self, "提示", "请先选择下载目录。")
            return None

        output_dir = Path(out_dir_text).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            ffmpeg = check_ffmpeg_bin("ffmpeg")
        except Exception as exc:
            QMessageBox.critical(self, "ffmpeg 未找到", str(exc))
            return None

        options = DownloadOptions(
            ffmpeg=ffmpeg,
            ffprobe=resolve_ffprobe_bin(),
            retries=self.retries_input.value(),
            overwrite=False,
            timeout=0,
            user_agent=None,
            referer=None,
            headers=[],
            transcode_on_fail=True,
        )

        tasks = build_tasks(raw_entries, output_dir)
        jobs = self.jobs_input.value()
        return tasks, options, jobs, output_dir

    def _start_download(self) -> None:
        prepared = self._prepare_tasks()
        if not prepared:
            return
        tasks, options, jobs, output_dir = prepared

        self.table.setRowCount(0)
        self.row_by_index.clear()
        self.progress_by_index.clear()

        for task in tasks:
            self._add_table_row(task)

        self.summary_label.setText(f"任务 {len(tasks)} 条，准备开始...")
        self.start_btn.setEnabled(False)
        self.start_btn.set_busy(True)

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

        bar = self.progress_by_index.get(task_index)
        detail_item = self.table.item(row, 4)

        if status == "stage":
            self._set_status(row, detail, QColor("#42A5F5") if self.current_theme == "light" else QColor("#9CC8FF"))
            return

        if status == "progress" and bar:
            if progress < 0:
                if bar.maximum() != 0:
                    bar.setRange(0, 0)
                    bar.setFormat("加载中...")
            else:
                if bar.maximum() == 0:
                    bar.setRange(0, 100)
                    bar.setFormat("%p%")
                self._animate_progress(bar, progress)
            return

        if status == "running":
            self._set_status(row, "开始下载", QColor("#3E63DD") if self.current_theme == "light" else QColor("#A7C5FF"))
            if detail_item:
                detail_item.setText(detail)
            return

        if status == "ok":
            self._set_status(row, "已完成", QColor("#1F8F4D") if self.current_theme == "light" else QColor("#86E3A8"))
            if bar:
                if bar.maximum() == 0:
                    bar.setRange(0, 100)
                    bar.setFormat("%p%")
                self._animate_progress(bar, 100)
            if detail_item:
                detail_item.setText(detail)
            return

        if status == "skipped":
            self._set_status(row, "已跳过", QColor("#AD6E00") if self.current_theme == "light" else QColor("#FFD287"))
            if bar:
                bar.setRange(0, 100)
                bar.setValue(100)
                bar.setFormat("100%")
            if detail_item:
                detail_item.setText(detail)
            return

        if status == "failed":
            self._set_status(row, "下载失败", QColor("#C62828") if self.current_theme == "light" else QColor("#FF9A9A"))
            if bar:
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat("失败")
            if detail_item:
                detail_item.setText(detail)
            return

    @Slot(int, int, int, str)
    def _on_batch_done(self, success: int, skipped: int, failed: int, failure_file: str) -> None:
        text = f"完成：成功 {success} | 跳过 {skipped} | 失败 {failed}"
        if failure_file:
            text += f" | 失败清单：{failure_file}"
        self.summary_label.setText(text)

        if failed > 0:
            QMessageBox.warning(
                self,
                "任务完成",
                f"成功 {success}，跳过 {skipped}，失败 {failed}。\n失败清单已导出：\n{failure_file}",
            )
        else:
            QMessageBox.information(
                self,
                "任务完成",
                f"全部完成。成功 {success}，跳过 {skipped}。",
            )

    @Slot()
    def _on_worker_finished(self) -> None:
        self.start_btn.setEnabled(True)
        self.start_btn.set_busy(False)
        self.worker = None
        self.worker_thread = None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("M3U8 Batch Downloader")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
