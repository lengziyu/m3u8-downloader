#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


APP_NAME = "M3U8-Downloader"
ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
DEFAULT_VENV_DIR = ROOT / ".build-venv"
PIP_TRUSTED_HOSTS = ["pypi.org", "files.pythonhosted.org", "pypi.python.org"]
PIP_INSTALL_FLAGS = ["--default-timeout", "120", "--retries", "10"]


def run_cmd(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True, env=env)


def add_binary_args(binary_path: str) -> list[str]:
    sep = ";" if os.name == "nt" else ":"
    return ["--add-binary", f"{binary_path}{sep}."]


def resolve_system_binaries() -> tuple[str | None, str | None]:
    return shutil.which("ffmpeg"), shutil.which("ffprobe")


def _build_trusted_hosts(index_url: str | None) -> list[str]:
    hosts = list(PIP_TRUSTED_HOSTS)
    if index_url:
        host = urlparse(index_url).hostname
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def pip_install(
    python_bin: str,
    args: list[str],
    index_url: str | None,
    fail_ok: bool = False,
) -> None:
    base = [python_bin, "-m", "pip", "install", *PIP_INSTALL_FLAGS, *args]
    if index_url:
        base.extend(["--index-url", index_url])
    try:
        run_cmd(base)
    except subprocess.CalledProcessError:
        print("pip install failed; retrying with trusted-host options...")
        trusted: list[str] = []
        for host in _build_trusted_hosts(index_url):
            trusted.extend(["--trusted-host", host])
        try:
            run_cmd(base + trusted)
        except subprocess.CalledProcessError:
            if fail_ok:
                print("pip optional step failed, continuing...")
                return
            raise


def install_deps(python_bin: str, index_url: str | None) -> None:
    pip_install(python_bin, ["--upgrade", "pip"], index_url, fail_ok=True)
    pip_install(python_bin, ["-r", "requirements.txt", "pyinstaller"], index_url)


def build_app(
    python_bin: str,
    bundle_ffmpeg: bool,
    app_version: str,
) -> tuple[Path, str]:
    system_name = platform.system().lower()
    is_windows = system_name == "windows"
    is_macos = system_name == "darwin"

    cmd = [
        python_bin,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
    ]

    if is_windows:
        cmd.append("--onefile")

    ffmpeg, ffprobe = resolve_system_binaries()
    bundled_items: list[str] = []
    if bundle_ffmpeg:
        if ffmpeg:
            cmd.extend(add_binary_args(ffmpeg))
            bundled_items.append(f"ffmpeg={ffmpeg}")
        if ffprobe:
            cmd.extend(add_binary_args(ffprobe))
            bundled_items.append(f"ffprobe={ffprobe}")

    cmd.append("m3u8_gui.py")

    build_env = os.environ.copy()
    version_text = app_version.strip() or "1.0.0"
    if version_text.lower().startswith("v"):
        version_text = version_text[1:]
    build_env["M3U8_DOWNLOADER_APP_VERSION"] = version_text
    run_cmd(cmd, env=build_env)

    if is_windows:
        return DIST_DIR / f"{APP_NAME}.exe", ", ".join(bundled_items) or "none"
    if is_macos:
        return DIST_DIR / f"{APP_NAME}.app", ", ".join(bundled_items) or "none"

    raise RuntimeError("当前仅支持在 Windows/macOS 上生成正式客户端产物。")


def build_dmg(app_path: Path) -> Path:
    if not app_path.exists():
        raise FileNotFoundError(f"未找到 .app：{app_path}")
    dmg_path = DIST_DIR / f"{APP_NAME}-macOS.dmg"
    if dmg_path.exists():
        dmg_path.unlink()
    run_cmd(
        [
            "hdiutil",
            "create",
            "-volname",
            APP_NAME,
            "-srcfolder",
            str(app_path),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ]
    )
    return dmg_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="一键构建客户端产物：Windows 生成 .exe，macOS 生成 .app + .dmg"
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="用于构建的 Python 可执行文件（默认当前解释器）",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="跳过 pip 安装依赖步骤",
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="不使用本地构建虚拟环境（默认会自动创建 .build-venv）",
    )
    parser.add_argument(
        "--no-bundle-ffmpeg",
        action="store_true",
        help="不尝试把系统 ffmpeg/ffprobe 打进客户端",
    )
    parser.add_argument(
        "--index-url",
        default=None,
        help="可选：指定 pip 源，例如 https://pypi.tuna.tsinghua.edu.cn/simple",
    )
    parser.add_argument(
        "--app-version",
        default=os.environ.get("M3U8_DOWNLOADER_APP_VERSION", "1.0.0"),
        help="写入客户端的版本号（用于应用内更新检测显示）",
    )
    return parser.parse_args()


def ensure_venv(base_python: str) -> str:
    if not DEFAULT_VENV_DIR.exists():
        run_cmd([base_python, "-m", "venv", str(DEFAULT_VENV_DIR)])

    if os.name == "nt":
        venv_python = DEFAULT_VENV_DIR / "Scripts" / "python.exe"
    else:
        venv_python = DEFAULT_VENV_DIR / "bin" / "python"

    if not venv_python.exists():
        raise FileNotFoundError(f"虚拟环境 Python 不存在：{venv_python}")
    return str(venv_python)


def ensure_modules(python_bin: str, modules: list[str]) -> None:
    missing: list[str] = []
    for mod in modules:
        result = subprocess.run(
            [python_bin, "-c", f"import {mod}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            missing.append(mod)

    if missing:
        raise RuntimeError(
            "缺少构建依赖模块："
            + ", ".join(missing)
            + "。请先运行不带 --skip-install 的一键构建，或手动安装这些模块。"
        )


def main() -> int:
    try:
        args = parse_args()
        system_name = platform.system().lower()
        if system_name not in {"windows", "darwin"}:
            print("仅支持在 Windows/macOS 上执行一键构建。")
            return 2

        print(f"Workspace: {ROOT}")
        print(f"Platform: {platform.system()}")
        build_python = args.python
        if not args.no_venv:
            build_python = ensure_venv(args.python)

        print(f"Python: {args.python}")
        print(f"Build Python: {build_python}")
        print(f"App Version: {args.app_version}")

        if not args.skip_install:
            install_deps(build_python, args.index_url)
        ensure_modules(build_python, ["PyInstaller", "PySide6"])

        artifact, bundled = build_app(
            python_bin=build_python,
            bundle_ffmpeg=not args.no_bundle_ffmpeg,
            app_version=args.app_version,
        )
        print(f"Bundled binaries: {bundled}")

        if system_name == "windows":
            print(f"Build done: {artifact}")
            return 0

        dmg_path = build_dmg(artifact)
        print(f"Build done: {artifact}")
        print(f"Build done: {dmg_path}")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
