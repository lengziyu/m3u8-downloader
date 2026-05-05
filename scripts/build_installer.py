#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


APP_NAME = "Taoying"
APP_DISPLAY_NAME = "桃影"
MAC_APP_ID = "com.lens.taoying"
# Inno Setup AppId should use GUID form (escaped with double '{{' in iss).
WIN_APP_ID = "{{8A8D3E35-2D02-4D88-A8D0-4D1D6D2F7C31}"
ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
WINDOWS_ICON_PATH = ROOT / "assets" / "app_icon.ico"


def read_project_version(default: str = "1.0.0") -> str:
    version_file = ROOT / "VERSION"
    if not version_file.exists():
        return default
    try:
        line = (version_file.read_text(encoding="utf-8").splitlines() or [default])[0].strip()
    except Exception:
        return default
    if not line:
        return default
    return line[1:] if line.lower().startswith("v") else line


def run_cmd(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def run_build_oneclick(args: argparse.Namespace, app_version: str) -> None:
    cmd = [args.python, "scripts/build_oneclick.py"]
    if args.skip_install:
        cmd.append("--skip-install")
    if args.no_venv:
        cmd.append("--no-venv")
    if args.no_bundle_ffmpeg:
        cmd.append("--no-bundle-ffmpeg")
    if args.index_url:
        cmd.extend(["--index-url", args.index_url])
    cmd.extend(["--app-version", app_version])
    run_cmd(cmd)


def normalize_installer_version(version: str) -> str:
    text = version.strip()
    if text.lower().startswith("v"):
        text = text[1:]
    parts = [p for p in text.split(".") if p.isdigit()]
    if not parts:
        return "1.0.0"
    return ".".join(parts[:3])


def find_iscc() -> str:
    local_programs = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"
    candidates = [
        shutil.which("iscc"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        str(local_programs) if str(local_programs) else None,
    ]
    for path in candidates:
        if path and Path(path).exists():
            return str(path)
    raise FileNotFoundError(
        "未找到 Inno Setup 编译器 ISCC。请先安装 Inno Setup 6 并确保 iscc 可用。"
    )


def build_windows_installer(version: str) -> Path:
    app_exe = DIST_DIR / f"{APP_NAME}.exe"
    if not app_exe.exists():
        raise FileNotFoundError(f"未找到可打包应用：{app_exe}")

    iscc = find_iscc()
    setup_icon_line = f"SetupIconFile={WINDOWS_ICON_PATH}\n" if WINDOWS_ICON_PATH.exists() else ""
    iss_content = f"""
[Setup]
AppId={WIN_APP_ID}
AppName={APP_DISPLAY_NAME}
AppVersion={version}
DefaultDirName={{{{autopf}}}}\\{APP_NAME}
DefaultGroupName={APP_DISPLAY_NAME}
OutputDir={DIST_DIR}
OutputBaseFilename={APP_NAME}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={{{{app}}}}\\{APP_NAME}.exe
{setup_icon_line}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional tasks:"

[Files]
Source: "{app_exe}"; DestDir: "{{app}}"; Flags: ignoreversion

[Icons]
Name: "{{autoprograms}}\\{APP_DISPLAY_NAME}"; Filename: "{{app}}\\{APP_NAME}.exe"
Name: "{{autodesktop}}\\{APP_DISPLAY_NAME}"; Filename: "{{app}}\\{APP_NAME}.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{APP_NAME}.exe"; Description: "Launch {APP_DISPLAY_NAME}"; Flags: nowait postinstall skipifsilent
"""
    with tempfile.TemporaryDirectory() as td:
        iss_file = Path(td) / "installer.iss"
        # Inno Setup reliably handles UTF-8 text when BOM is present.
        iss_file.write_text(iss_content.strip() + "\n", encoding="utf-8-sig")
        run_cmd([iscc, str(iss_file)])

    return DIST_DIR / f"{APP_NAME}-Setup.exe"


def build_macos_installer(version: str) -> tuple[Path, Path]:
    app_path = DIST_DIR / f"{APP_NAME}.app"
    if not app_path.exists():
        raise FileNotFoundError(f"未找到可打包应用：{app_path}")

    pkg_path = DIST_DIR / f"{APP_NAME}-Installer.pkg"
    dmg_path = DIST_DIR / f"{APP_NAME}-Installer.dmg"

    if pkg_path.exists():
        pkg_path.unlink()
    if dmg_path.exists():
        dmg_path.unlink()

    run_cmd(
        [
            "pkgbuild",
            "--identifier",
            MAC_APP_ID,
            "--version",
            version,
            "--install-location",
            "/Applications",
            "--component",
            str(app_path),
            str(pkg_path),
        ]
    )

    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "stage"
        stage.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pkg_path, stage / pkg_path.name)
        run_cmd(
            [
                "hdiutil",
                "create",
                "-volname",
                f"{APP_NAME} Installer",
                "-srcfolder",
                str(stage),
                "-ov",
                "-format",
                "UDZO",
                str(dmg_path),
            ]
        )

    return pkg_path, dmg_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="构建标准安装器：Windows 安装向导 .exe / macOS 安装向导 .pkg + .dmg"
    )
    parser.add_argument("--python", default=sys.executable, help="构建用 Python")
    parser.add_argument("--version", default=read_project_version(), help="安装器版本号")
    parser.add_argument("--app-version", default=None, help="客户端版本号（默认跟随 --version）")
    parser.add_argument("--skip-build", action="store_true", help="跳过基础应用构建")
    parser.add_argument("--skip-install", action="store_true", help="传递给 build_oneclick.py")
    parser.add_argument("--no-venv", action="store_true", help="传递给 build_oneclick.py")
    parser.add_argument(
        "--no-bundle-ffmpeg", action="store_true", help="传递给 build_oneclick.py"
    )
    parser.add_argument("--index-url", default=None, help="传递给 build_oneclick.py")
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        system_name = platform.system().lower()
        if system_name not in {"windows", "darwin"}:
            print("仅支持 Windows/macOS 构建安装器。")
            return 2

        print(f"Workspace: {ROOT}")
        print(f"Platform: {platform.system()}")

        version = normalize_installer_version(args.version)
        app_version = normalize_installer_version(args.app_version or args.version)

        if not args.skip_build:
            run_build_oneclick(args, app_version)

        if system_name == "windows":
            setup_exe = build_windows_installer(version)
            print(f"Installer done: {setup_exe}")
            return 0

        pkg_path, dmg_path = build_macos_installer(version)
        print(f"Installer done: {pkg_path}")
        print(f"Installer done: {dmg_path}")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
