#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse


PRINT_LOCK = threading.Lock()
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class DownloadTask:
    index: int
    url: str
    output_path: Path


def safe_print(message: str) -> None:
    with PRINT_LOCK:
        print(message, flush=True)


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", name).strip().strip(".")
    return cleaned or "video"


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


def parse_line(line: str) -> tuple[str | None, str] | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if "|" in text:
        left, right = text.split("|", 1)
        name = left.strip()
        url = right.strip()
        if not url:
            return None
        return (name or None, url)
    return (None, text)


def load_sources(input_file: Path | None, direct_urls: Iterable[str]) -> list[tuple[str | None, str]]:
    items: list[tuple[str | None, str]] = []
    for url in direct_urls:
        stripped = url.strip()
        if stripped:
            items.append((None, stripped))

    if input_file:
        for raw in input_file.read_text(encoding="utf-8").splitlines():
            parsed = parse_line(raw)
            if parsed:
                items.append(parsed)

    if not items:
        raise ValueError("没有可下载的 URL。请通过参数或 --input-file 提供 m3u8 地址。")
    return items


def check_ffmpeg(ffmpeg_bin: str) -> str:
    resolved = shutil.which(ffmpeg_bin)
    if not resolved:
        raise FileNotFoundError(
            f"找不到 ffmpeg：'{ffmpeg_bin}'。请安装 ffmpeg 并确保它在 PATH 里，"
            "或通过 --ffmpeg 指定完整路径。"
        )
    return resolved


def header_args(
    user_agent: str | None, referer: str | None, headers: list[str] | None
) -> list[str]:
    args: list[str] = []
    args.extend(["-user_agent", user_agent or DEFAULT_USER_AGENT])
    merged_headers: list[str] = []
    if referer:
        merged_headers.append(f"Referer: {referer}")
    if headers:
        merged_headers.extend(headers)
    if merged_headers:
        header_blob = "".join(f"{line}\r\n" for line in merged_headers)
        args.extend(["-headers", header_blob])
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


def run_ffmpeg(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, **subprocess_no_window_kwargs())
    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or proc.stdout or "").strip()
    return False, err[-1500:]


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


def validate_output_media(path: Path, ffmpeg: str) -> tuple[bool, str | None]:
    if not path.exists():
        return False, "输出文件不存在"
    if path.stat().st_size < 256 * 1024:
        return False, "输出文件过小"

    test_cmd = [
        ffmpeg,
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
    proc = subprocess.run(
        test_cmd,
        capture_output=True,
        text=True,
        **subprocess_no_window_kwargs(),
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err[-1500:] or "解码测试失败"
    return True, None


def download_one(
    task: DownloadTask,
    ffmpeg: str,
    retries: int,
    overwrite: bool,
    user_agent: str | None,
    referer: str | None,
    headers: list[str] | None,
    transcode_on_fail: bool,
    timeout: int,
    dry_run: bool,
) -> tuple[str, DownloadTask, str | None]:
    if task.output_path.exists() and not overwrite:
        return ("skipped", task, "目标文件已存在")

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

    common = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y" if overwrite else "-n",
    ]
    if timeout > 0:
        common.extend(["-rw_timeout", str(timeout * 1_000_000)])
    common.extend(hls_input_args())
    common.extend(header_args(user_agent, referer, headers))
    common.extend(["-i", task.url])

    copy_cmd = common + [
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        "-movflags",
        "+faststart",
        str(working_output),
    ]
    transcode_cmd = common + [
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
        str(working_output),
    ]

    if dry_run:
        safe_print(f"[DRY-RUN] {task.index:03d}: {' '.join(copy_cmd)}")
        return ("ok", task, None)

    last_error: str | None = None
    for attempt in range(1, retries + 2):
        cleanup_partial_output()
        ok, err = run_ffmpeg(copy_cmd)
        if ok:
            media_ok, media_reason = validate_output_media(working_output, ffmpeg)
            if media_ok:
                finalize_ok, finalize_err = finalize_output()
                if finalize_ok:
                    return ("ok", task, None)
                return ("failed", task, f"写入最终文件失败: {finalize_err or 'unknown error'}")
            last_error = f"copy 成功但文件异常: {media_reason or 'unknown error'}"
            cleanup_partial_output()
        else:
            last_error = f"copy 模式失败: {err or 'unknown error'}"

        if transcode_on_fail:
            cleanup_partial_output()
            ok2, err2 = run_ffmpeg(transcode_cmd)
            if ok2:
                media_ok2, media_reason2 = validate_output_media(working_output, ffmpeg)
                if media_ok2:
                    finalize_ok, finalize_err = finalize_output()
                    if finalize_ok:
                        return ("ok", task, "copy 失败，已自动转码")
                    return ("failed", task, f"写入最终文件失败: {finalize_err or 'unknown error'}")
                cleanup_partial_output()
                last_error = f"{last_error} | 转码后校验失败: {media_reason2 or 'unknown error'}"
            else:
                cleanup_partial_output()
                last_error = f"{last_error} | transcode 失败: {err2 or 'unknown error'}"

        if attempt <= retries:
            time.sleep(min(2 * attempt, 8))

    cleanup_partial_output()
    return ("failed", task, last_error)



def build_tasks(
    sources: list[tuple[str | None, str]],
    output_dir: Path,
    name_prefix: str | None,
) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    used_names: set[str] = set()
    for idx, (custom_name, url) in enumerate(sources, start=1):
        base_name = build_output_name(idx, url, custom_name)
        if name_prefix:
            base_name = f"{sanitize_filename(name_prefix)}_{base_name}"

        stem = Path(base_name).stem
        final_name = base_name
        suffix = 1
        while final_name.lower() in used_names:
            final_name = f"{stem}_{suffix}.mp4"
            suffix += 1
        used_names.add(final_name.lower())
        tasks.append(DownloadTask(index=idx, url=url, output_path=output_dir / final_name))
    return tasks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量下载 m3u8 到 mp4（Windows/macOS 均可）。"
    )
    parser.add_argument("urls", nargs="*", help="直接传入 m3u8 URL（可多个）")
    parser.add_argument(
        "--input-file",
        type=Path,
        help="包含 URL 的文本文件；每行一个 URL，或 `文件名|URL`",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("downloads"),
        help="输出目录（默认：downloads）",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=max(1, min(4, (os.cpu_count() or 4))),
        help="并发数（默认：1~4 之间自动）",
    )
    parser.add_argument("--retries", type=int, default=2, help="失败重试次数（默认：2）")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg 命令或完整路径")
    parser.add_argument("--user-agent", help="请求头 User-Agent")
    parser.add_argument("--referer", help="请求头 Referer")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="自定义请求头，可重复，例如：--header 'Cookie: a=1'",
    )
    parser.add_argument(
        "--name-prefix", help="统一输出文件名前缀，例如 course01"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="网络超时秒数（0 表示不设置 ffmpeg rw_timeout）",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="覆盖已有文件（默认不覆盖）"
    )
    parser.add_argument(
        "--no-transcode-fallback",
        action="store_true",
        help="copy 失败后不自动转码",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印命令，不执行")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ffmpeg = check_ffmpeg(args.ffmpeg)
        sources = load_sources(args.input_file, args.urls)
    except Exception as exc:
        safe_print(f"[ERROR] {exc}")
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(sources, args.output_dir, args.name_prefix)
    transcode_on_fail = not args.no_transcode_fallback

    safe_print(f"ffmpeg: {ffmpeg}")
    safe_print(f"任务数: {len(tasks)} | 并发: {args.jobs} | 输出: {args.output_dir.resolve()}")

    ok_count = 0
    skipped_count = 0
    failed_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [
            pool.submit(
                download_one,
                task=t,
                ffmpeg=ffmpeg,
                retries=max(0, args.retries),
                overwrite=args.overwrite,
                user_agent=args.user_agent,
                referer=args.referer,
                headers=args.header,
                transcode_on_fail=transcode_on_fail,
                timeout=max(0, args.timeout),
                dry_run=args.dry_run,
            )
            for t in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            status, task, detail = future.result()
            if status == "ok":
                ok_count += 1
                tail = f" ({detail})" if detail else ""
                safe_print(f"[OK] {task.index:03d} -> {task.output_path.name}{tail}")
            elif status == "skipped":
                skipped_count += 1
                safe_print(f"[SKIP] {task.index:03d} -> {task.output_path.name}: {detail}")
            else:
                failed_count += 1
                safe_print(f"[FAIL] {task.index:03d} -> {task.output_path.name}: {detail}")

    safe_print(
        f"完成: 成功 {ok_count} | 跳过 {skipped_count} | 失败 {failed_count}"
    )
    return 1 if failed_count else 0


if __name__ == "__main__":
    sys.exit(main())
