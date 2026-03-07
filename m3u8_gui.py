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
APP_VERSION = os.environ.get("M3U8_DOWNLOADER_APP_VERSION", "1.0.0").strip()
if APP_VERSION.lower().startswith("v"):
    APP_VERSION = APP_VERSION[1:]
GITHUB_REPO = os.environ.get("M3U8_DOWNLOADER_GITHUB_REPO", "lengziyu/m3u8-downloader")


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
        self._animate_window_enter()

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

        self.settings_toggle_btn = QPushButton("⚙ 设置")
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

        settings_title = QLabel("下载设置")
        settings_title.setObjectName("sectionTitle")
        settings_content_layout.addWidget(settings_title)

        output_label = QLabel("下载目录")
        output_label.setObjectName("fieldLabel")
        self.output_dir_input = QLineEdit(str((Path.cwd() / "downloads").resolve()))
        self.output_dir_input.setObjectName("pathInput")
        browse_btn = QPushButton("选择目录")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self._choose_output_dir)

        settings_content_layout.addWidget(output_label)
        settings_content_layout.addWidget(self.output_dir_input)
        settings_content_layout.addWidget(browse_btn)

        jobs_label = QLabel("并发")
        jobs_label.setObjectName("fieldLabel")
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

        retries_label = QLabel("重试")
        retries_label.setObjectName("fieldLabel")
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

        settings_content_layout.addWidget(jobs_label)
        settings_content_layout.addLayout(jobs_row)
        settings_content_layout.addWidget(retries_label)
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

        title = QLabel(APP_DISPLAY_NAME)
        title.setObjectName("titleLabel")
        subtitle = QLabel("支持 Windows 10/11、macOS；批量下载为 MP4；失败任务自动导出")
        subtitle.setObjectName("subtitleLabel")
        self.theme_btn = QPushButton("◐")
        self.theme_btn.setObjectName("themeIconBtn")
        self.theme_btn.setFixedSize(38, 38)
        self.theme_btn.clicked.connect(self._toggle_theme)

        header_layout.addWidget(title, 0, Qt.AlignVCenter)
        header_layout.addWidget(subtitle, 0, Qt.AlignVCenter)
        header_layout.addStretch(1)
        header_layout.addWidget(self.theme_btn, 0, Qt.AlignRight | Qt.AlignVCenter)

        right_layout.addWidget(header)

        input_card = QFrame()
        input_card.setObjectName("card")
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(20, 18, 20, 18)
        input_layout.setSpacing(10)

        input_title = QLabel("M3U8 链接输入")
        input_title.setObjectName("sectionTitle")

        self.input_tabs = QTabWidget()
        self.input_tabs.setObjectName("inputTabs")
        self.input_tabs.setMinimumHeight(190)

        single_tab = QWidget()
        single_layout = QVBoxLayout(single_tab)
        single_layout.setContentsMargins(6, 8, 6, 6)
        single_layout.setSpacing(8)

        single_hint = QLabel("逐条输入：每个输入框一个链接，填完会自动新增下一行")
        single_hint.setObjectName("inputHintLabel")
        single_layout.addWidget(single_hint)

        self.single_scroll = QScrollArea()
        self.single_scroll.setWidgetResizable(True)
        self.single_scroll.setFrameShape(QFrame.NoFrame)
        self.single_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.single_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.single_container = QWidget()
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

        batch_hint = QLabel("批量文本：支持多行，也支持一行用 | 分隔多个链接")
        batch_hint.setObjectName("inputHintLabel")
        self.url_input = QTextEdit()
        self.url_input.setObjectName("urlInput")
        self.url_input.setPlaceholderText(
            "示例:\n"
            "https://example.com/1.m3u8\n"
            "https://example.com/2.m3u8\n"
            "https://example.com/3.m3u8\n"
            "\n或一行：\n"
            "https://a.m3u8|https://b.m3u8|https://c.m3u8"
        )
        self.url_input.setMinimumHeight(140)
        batch_layout.addWidget(batch_hint)
        batch_layout.addWidget(self.url_input, 1)
        batch_layout.addSpacing(2)

        self.input_tabs.addTab(single_tab, "逐条输入")
        self.input_tabs.addTab(batch_tab, "批量文本")

        input_layout.addWidget(input_title)
        input_layout.addWidget(self.input_tabs)
        right_layout.addWidget(input_card)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.start_btn = QPushButton("开始下载")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setMinimumHeight(48)
        self.start_btn.clicked.connect(self._start_download)

        self.add_more_btn = QPushButton("继续添加")
        self.add_more_btn.setObjectName("tableActionBtn")
        self.add_more_btn.setMinimumHeight(48)
        self.add_more_btn.setEnabled(False)
        self.add_more_btn.clicked.connect(self._append_tasks_while_running)

        self.summary_label = QLabel("等待开始")
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
        table_title = QLabel("任务进度")
        table_title.setObjectName("sectionTitle")
        table_head.addWidget(table_title)
        table_head.addStretch(1)

        self.pause_all_btn = QPushButton("暂停全部")
        self.pause_all_btn.setObjectName("tableActionBtn")
        self.pause_all_btn.setMinimumHeight(36)
        self.pause_all_btn.clicked.connect(self._toggle_pause_all)
        self.pause_all_btn.setEnabled(False)

        self.clear_tasks_btn = QPushButton("清空任务")
        self.clear_tasks_btn.setObjectName("dangerBtn")
        self.clear_tasks_btn.setMinimumHeight(36)
        self.clear_tasks_btn.clicked.connect(self._clear_tasks_confirm)

        table_head.addWidget(self.pause_all_btn)
        table_head.addWidget(self.clear_tasks_btn)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["序号", "输出文件", "状态", "进度", "详情", "操作"])
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

    def _update_version_btn_text(self) -> None:
        if self.settings_panel_expanded:
            if self.update_checking:
                self.version_btn.setText(f"⟳ 检查中... v{APP_VERSION}")
            else:
                self.version_btn.setText(f"⟳ v{APP_VERSION}")
        else:
            self.version_btn.setText("⟳")

    def _check_updates(self) -> None:
        if self.update_checking:
            return
        if not GITHUB_REPO or GITHUB_REPO.startswith("YOUR_GITHUB_OWNER/"):
            QMessageBox.information(
                self,
                "版本检测",
                "未配置 GitHub 仓库。请设置 m3u8_gui.py 中的 GITHUB_REPO，或设置环境变量 "
                "M3U8_DOWNLOADER_GITHUB_REPO=owner/repo。",
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
                "版本检测",
                f"已是最新版本。\n当前版本：v{APP_VERSION}\n最新版本：{latest}",
            )
            return

        if status == "update":
            ret = QMessageBox.question(
                self,
                "发现新版本",
                f"当前版本：v{APP_VERSION}\n最新版本：{latest}\n\n是否前往 Releases 下载更新？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ret == QMessageBox.Yes and release_url:
                webbrowser.open(release_url)
            return

        QMessageBox.warning(self, "版本检测失败", f"无法检测更新：{latest}")

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
        self.settings_toggle_btn.setText("⚙ 设置" if expanded else "⚙")
        self.settings_toggle_btn.setToolTip("收起设置" if expanded else "展开设置")
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
            "选择下载目录",
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
        status_item = QTableWidgetItem("准备中")
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

        pause_btn = QPushButton("暂停")
        pause_btn.setObjectName("rowPauseBtn")
        pause_btn.setMinimumHeight(24)
        pause_btn.setFixedWidth(56)
        pause_btn.clicked.connect(lambda _, idx=task.index: self._on_row_pause_clicked(idx))

        delete_btn = QPushButton("删除")
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
        shown = f"  {text}  " if text == "正在下载" else text
        item.setText(shown)
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
        line.setPlaceholderText("https://example.com/video.m3u8")
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
        btn.setText("继续" if paused else "暂停")
        btn.setEnabled(enabled)

    def _set_pause_btn_visible(self, task_index: int, visible: bool) -> None:
        btn = self.pause_btn_by_index.get(task_index)
        if btn:
            btn.setVisible(visible)

    def _set_delete_btn_enabled(self, task_index: int, enabled: bool) -> None:
        btn = self.delete_btn_by_index.get(task_index)
        if btn:
            btn.setEnabled(enabled)

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
        if not self.worker:
            return
        ret = QMessageBox.question(
            self,
            "确认删除",
            "确定删除这个任务吗？运行中的任务会立即中断。",
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
            self.pause_all_btn.setText("暂停全部")
        else:
            self.worker.apply_command("pause_all")
            self.pause_all_active = True
            self.pause_all_btn.setText("继续全部")

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
                "确认清空任务",
                "确定清空所有任务吗？正在下载的任务会被中断。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            self.worker.apply_command("delete_all")
            self.summary_label.setText("已请求清空任务，等待当前线程退出...")
            return

        if self.table.rowCount() == 0:
            return
        ret = QMessageBox.question(
            self,
            "确认清空任务",
            "确定清空任务列表吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self._clear_table_ui()
            self.summary_label.setText("任务列表已清空")

    def _prepare_tasks(self) -> tuple[list[DownloadTask], DownloadOptions, int, Path] | None:
        raw_entries = self._collect_current_entries()
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
            QMessageBox.information(self, "提示", "当前没有运行中的任务，请使用“开始下载”。")
            return

        raw_entries = self._collect_current_entries()
        if not raw_entries:
            QMessageBox.warning(self, "提示", "请输入要继续添加的链接。")
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
                "提示",
                "没有可添加的新任务（可能都重复或格式无效）。",
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
            self.summary_label.setText(f"已新增 {added} 个任务")

    def _start_download(self) -> None:
        prepared = self._prepare_tasks()
        if not prepared:
            return
        tasks, options, jobs, output_dir = prepared

        self._clear_table_ui()
        self.pause_all_active = False
        self.pause_all_btn.setText("暂停全部")
        self.pause_all_btn.setEnabled(True)
        self.clear_tasks_btn.setEnabled(True)

        for task in tasks:
            self._add_table_row(task)

        self.summary_label.setText(f"任务 {len(tasks)} 条，准备开始...")
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
            if "下载中" in detail:
                self._set_status(
                    row,
                    "正在下载",
                    QColor("#42A5F5") if self.current_theme == "light" else QColor("#9CC8FF"),
                )
            else:
                self._set_status(
                    row,
                    detail,
                    QColor("#42A5F5") if self.current_theme == "light" else QColor("#9CC8FF"),
                )
            if detail_item:
                detail_item.setText(detail)
            self._set_pause_btn_state(task_index, paused=False)
            self._set_pause_btn_visible(task_index, True)
            return

        if status == "progress" and bar:
            if progress < 0:
                if bar.maximum() != 0:
                    bar.setRange(0, 0)
                    bar.setFormat("加载中...")
            else:
                if bar.maximum() == 0:
                    bar.setRange(0, 100)
                bar.setFormat(f"{progress}%")
                self._animate_progress(bar, progress)
            return

        if status == "running":
            self._set_status(row, "准备中", QColor("#3E63DD") if self.current_theme == "light" else QColor("#A7C5FF"))
            self._set_pause_btn_state(task_index, paused=False)
            self._set_pause_btn_visible(task_index, True)
            self._set_delete_btn_enabled(task_index, True)
            if detail_item:
                detail_item.setText(detail)
            return

        if status == "ok":
            self._set_status(row, "已完成", QColor("#1F8F4D") if self.current_theme == "light" else QColor("#86E3A8"))
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_delete_btn_enabled(task_index, False)
            if bar:
                if bar.maximum() == 0:
                    bar.setRange(0, 100)
                bar.setFormat("100%")
                self._animate_progress(bar, 100)
            if detail_item:
                detail_item.setText(detail)
            return

        if status == "skipped":
            self._set_status(row, "已跳过", QColor("#AD6E00") if self.current_theme == "light" else QColor("#FFD287"))
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_delete_btn_enabled(task_index, False)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(100)
                bar.setFormat("100%")
            if detail_item:
                detail_item.setText(detail)
            return

        if status == "paused":
            self._set_status(row, "已暂停", QColor("#A37200") if self.current_theme == "light" else QColor("#FFD287"))
            self._set_pause_btn_state(task_index, paused=True)
            self._set_pause_btn_visible(task_index, True)
            if bar and bar.maximum() == 0:
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat("暂停")
            if detail_item:
                detail_item.setText(detail)
            return

        if status == "deleted":
            self._set_status(row, "已删除", QColor("#C62828") if self.current_theme == "light" else QColor("#FF9A9A"))
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_delete_btn_enabled(task_index, False)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat("已删")
            if detail_item:
                detail_item.setText(detail)
            return

        if status == "failed":
            self._set_status(row, "下载失败", QColor("#C62828") if self.current_theme == "light" else QColor("#FF9A9A"))
            self._set_pause_btn_state(task_index, paused=False, enabled=False)
            self._set_pause_btn_visible(task_index, False)
            self._set_delete_btn_enabled(task_index, False)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat("失败")
            if detail_item:
                detail_item.setText(detail)
            return

    @Slot(int, int, int, str)
    def _on_batch_done(self, success: int, skipped: int, failed: int, failure_file: str) -> None:
        self.pause_all_active = False
        self.pause_all_btn.setText("暂停全部")
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
        self.pause_all_btn.setEnabled(False)
        self.add_more_btn.setEnabled(False)
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
