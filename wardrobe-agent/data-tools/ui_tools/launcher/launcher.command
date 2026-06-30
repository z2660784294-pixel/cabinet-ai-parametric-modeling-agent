#!/bin/bash
# macOS 双击启动 Wardrobe Agent 启动器（需先 chmod +x launcher.command）
cd "$(dirname "$0")"
if command -v python3 &>/dev/null; then
    exec python3 launcher.py
fi
if command -v python &>/dev/null; then
    exec python launcher.py
fi
echo "未找到 python3，请先运行 wain/setup_mac.sh 安装环境。" >&2
read -r -p "按回车键关闭…"
