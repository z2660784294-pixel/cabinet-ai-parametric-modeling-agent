#!/bin/bash
# macOS 双击启动 Wardrobe Agent 启动器（需先 chmod +x launcher.command）
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_DIR="$ROOT_DIR/wardrobe-agent/data-tools/ui_tools/launcher"
cd "$LAUNCHER_DIR"
if command -v python3 &>/dev/null; then
    exec python3 launcher.py
fi
if command -v python &>/dev/null; then
    exec python launcher.py
fi
echo "未找到 python3，请先运行 setup.sh 安装环境。" >&2
read -r -p "按回车键关闭…"
