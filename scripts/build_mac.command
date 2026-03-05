#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/build_oneclick.py "$@"
echo
echo "构建完成，按回车退出..."
read -r
