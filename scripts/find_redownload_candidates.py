#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CODE_RE = re.compile(r"([A-Za-z]{2,8}-\d{2,6})")


@dataclass(frozen=True)
class BrowserHistorySource:
    name: str
    root: Path


@dataclass(frozen=True)
class CandidateHit:
    browser: str
    history_file: Path
    url: str
    title: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan broken videos and try to recover likely source pages from local browser history."
    )
    parser.add_argument("dirs", nargs="+", help="Video directories to scan")
    parser.add_argument("--ffprobe", default="ffprobe", help="ffprobe command or full path")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg command or full path")
    parser.add_argument(
        "--include-healthy",
        action="store_true",
        help="Include playable videos too. Default: only output videos that look broken.",
    )
    parser.add_argument(
        "--max-hits",
        type=int,
        default=5,
        help="Maximum browser history matches to keep for each code (default: 5)",
    )
    parser.add_argument(
        "--output",
        default="redownload_candidates.csv",
        help="Output CSV path (default: redownload_candidates.csv)",
    )
    return parser.parse_args()


def browser_history_sources() -> list[BrowserHistorySource]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))
    sources: list[BrowserHistorySource] = []
    for name, root in (
        ("chrome", local / "Google/Chrome/User Data"),
        ("edge", local / "Microsoft/Edge/User Data"),
        ("roxy", roaming / "RoxyBrowser/browser-cache"),
        ("ollama-app", roaming / "ollama app.exe/EBWebView"),
    ):
        if root.exists():
            sources.append(BrowserHistorySource(name=name, root=root))
    return sources


def iter_history_files() -> Iterable[tuple[str, Path]]:
    for source in browser_history_sources():
        for history_path in source.root.rglob("History"):
            yield source.name, history_path


def extract_code(name: str) -> str | None:
    matched = CODE_RE.search(name)
    return matched.group(1).upper() if matched else None


def run_probe(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
    except Exception as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stderr or proc.stdout or "").strip()


def is_broken_video(path: Path, ffprobe: str, ffmpeg: str) -> tuple[bool, str]:
    probe_rc, probe_text = run_probe(
        [ffprobe, "-v", "error", "-show_entries", "format=format_name", "-of", "default=nw=1:nk=1", str(path)]
    )
    if probe_rc != 0:
        return True, probe_text or "ffprobe failed"

    decode_rc, decode_text = run_probe([ffmpeg, "-v", "error", "-ss", "0", "-t", "1.5", "-i", str(path), "-f", "null", "-"])
    if decode_rc != 0:
        return True, decode_text or "decode smoke test failed"
    return False, ""


def history_hits_for_code(code: str, max_hits: int) -> list[CandidateHit]:
    hits: list[CandidateHit] = []
    seen_urls: set[str] = set()
    for browser, history_path in iter_history_files():
        temp_db = Path(tempfile.gettempdir()) / f"codex_history_{browser}_{os.getpid()}_{len(hits)}.db"
        try:
            shutil.copy2(history_path, temp_db)
            conn = sqlite3.connect(temp_db)
            rows = conn.execute(
                """
                select url, title
                from urls
                where url like ? or title like ?
                order by last_visit_time desc
                limit ?
                """,
                (f"%{code}%", f"%{code}%", max_hits),
            ).fetchall()
            conn.close()
        except Exception:
            rows = []
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except Exception:
                pass

        for url, title in rows:
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            hits.append(
                CandidateHit(
                    browser=browser,
                    history_file=history_path,
                    url=str(url),
                    title=str(title or ""),
                )
            )
            if len(hits) >= max_hits:
                return hits
    return hits


def main() -> int:
    args = parse_args()
    rows: list[dict[str, str]] = []
    history_cache: dict[str, list[CandidateHit]] = {}

    for raw_dir in args.dirs:
        target_dir = Path(raw_dir).expanduser()
        if not target_dir.exists():
            print(f"[WARN] missing directory: {target_dir}")
            continue

        for video_path in sorted(target_dir.glob("*.mp4")):
            code = extract_code(video_path.name)
            broken = False
            broken_reason = ""
            if not args.include_healthy:
                broken, broken_reason = is_broken_video(video_path, args.ffprobe, args.ffmpeg)
                if not broken:
                    continue

            if code and code not in history_cache:
                history_cache[code] = history_hits_for_code(code, args.max_hits)

            hits = history_cache.get(code or "", [])
            if not hits:
                rows.append(
                    {
                        "video_path": str(video_path),
                        "file_name": video_path.name,
                        "code": code or "",
                        "broken_reason": broken_reason,
                        "browser": "",
                        "history_file": "",
                        "page_title": "",
                        "page_url": "",
                    }
                )
                continue

            for hit in hits:
                rows.append(
                    {
                        "video_path": str(video_path),
                        "file_name": video_path.name,
                        "code": code or "",
                        "broken_reason": broken_reason,
                        "browser": hit.browser,
                        "history_file": str(hit.history_file),
                        "page_title": hit.title,
                        "page_url": hit.url,
                    }
                )

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "video_path",
                "file_name",
                "code",
                "broken_reason",
                "browser",
                "history_file",
                "page_title",
                "page_url",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
