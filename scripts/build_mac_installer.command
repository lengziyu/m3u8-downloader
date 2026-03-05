#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/build_installer.py "$@"
echo
echo "安装器构建完成，按回车退出..."
read -r
