#!/bin/bash
cd "$(dirname "$0")" || exit 1
python3 -m venv .venv || exit 1
.venv/bin/python -m pip install -r requirements-build.txt || exit 1
.venv/bin/python scripts/build.py || exit 1
echo "应用位于 dist/WiFiDrop.app。"
read -r -p "按回车键退出…"

