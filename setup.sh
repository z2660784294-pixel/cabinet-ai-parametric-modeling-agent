#!/usr/bin/env bash
#
# 一键部署 MCP Server 和 Wardrobe Agent 环境 (macOS 版)
#
# 配置 mcp-server 和 wardrobe-agent，
# 完成后启动桌面启动器（launcher.py）：
#   - 后台运行 MCP Server（窗口打开时自动启动）
#   - 展示登录态并提供登录 / 注销
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MCP_DEST="$SCRIPT_DIR/mcp-server"
AGENT_DEST="$SCRIPT_DIR/wardrobe-agent"
NODE_MIN_VERSION="18.0.0"
PYTHON_MIN_VERSION="3.10.5"

# ── 输出工具函数 ─────────────────────────────────────────────────────────────
step()  { echo ""; echo -e "\033[36m>>> $1\033[0m"; }
ok()    { echo -e "\033[32m    [OK] $1\033[0m"; }
fail()  { echo -e "\033[31m    [ERROR] $1\033[0m"; exit 1; }

# ── 版本比较函数 ─────────────────────────────────────────────────────────────
version_ge() {
    # 如果 $1 >= $2 返回 0 (true)
    local IFS=.
    local i a=($1) b=($2)
    for ((i=0; i<${#b[@]}; i++)); do
        local va=${a[i]:-0}
        local vb=${b[i]:-0}
        if ((va > vb)); then return 0; fi
        if ((va < vb)); then return 1; fi
    done
    return 0
}

# ── 0. 检查子模块目录 ────────────────────────────────────────────────────────
step "检查子模块目录"
[ -d "$MCP_DEST" ]   || fail "找不到 mcp-server 子模块目录：$MCP_DEST，请先执行 git submodule update --init"
[ -d "$AGENT_DEST" ] || fail "找不到 wardrobe-agent 子模块目录：$AGENT_DEST，请先执行 git submodule update --init"
ok "子模块目录检查通过"

# 修复解压后目录缺少执行权限（Windows 打包的 zip 在 macOS 解压后可能丢失目录的 x 权限）
chmod -R +rX "$MCP_DEST" "$AGENT_DEST" 2>/dev/null || true

# ── 1. 选择 Agent 工具 ───────────────────────────────────────────────────────
step "选择 Agent 工具"
AGENT_TOOL=""
while [ -z "$AGENT_TOOL" ]; do
    echo -e "\033[33m    请选择要使用的 Agent 工具：\033[0m"
    echo "      [1] Cursor"
    echo "      [2] Claude Code"
    printf "    请输入 1 或 2: "
    read -r choice
    case "$choice" in
        1) AGENT_TOOL="cursor" ;;
        2) AGENT_TOOL="claude" ;;
        *) echo -e "\033[31m    无效输入，请重新选择\033[0m" ;;
    esac
done

if [ "$AGENT_TOOL" = "cursor" ]; then
    AGENT_DISPLAY_NAME="Cursor"
    AGENT_HIDDEN_DIR=".cursor"
    AGENT_LAUNCH_CMD="agent --force --approve-mcps"
    AGENT_CHECK_CMD="agent"
else
    AGENT_DISPLAY_NAME="Claude Code"
    AGENT_HIDDEN_DIR=".claude"
    AGENT_LAUNCH_CMD="claude"
    AGENT_CHECK_CMD="claude"
fi
ok "已选择：$AGENT_DISPLAY_NAME"

# ── 2. 检查 / 安装 Node.js ──────────────────────────────────────────────────
step "检查 Node.js (需要 >= $NODE_MIN_VERSION)"
NODE_OK=false
if command -v node &>/dev/null; then
    NODE_VER="$(node --version 2>/dev/null | sed 's/^v//')"
    if version_ge "$NODE_VER" "$NODE_MIN_VERSION"; then
        ok "Node.js $NODE_VER 已安装，满足要求"
        NODE_OK=true
    else
        echo -e "\033[33m    Node.js $NODE_VER 版本过低，需要升级\033[0m"
    fi
else
    echo -e "\033[33m    未检测到 Node.js，准备安装...\033[0m"
fi

if [ "$NODE_OK" = false ]; then
    if command -v brew &>/dev/null; then
        echo -e "\033[33m    正在通过 Homebrew 安装 Node.js LTS...\033[0m"
        brew install node@22 || brew upgrade node@22 || true
        brew link --overwrite node@22 2>/dev/null || true
    else
        fail "未检测到 Homebrew，请先安装 Homebrew (https://brew.sh/) 或手动安装 Node.js 18+ (https://nodejs.org/)"
    fi
    if ! command -v node &>/dev/null; then
        fail "Node.js 安装后仍无法检测到，请重新开启终端再运行本脚本"
    fi
    NODE_VER="$(node --version | sed 's/^v//')"
    ok "Node.js $NODE_VER 安装成功"
fi

# ── 3. 安装 mcp-server 依赖 ─────────────────────────────────────────────────
step "安装 mcp-server 依赖 (npm install)"
[ -f "$MCP_DEST/package.json" ] || fail "在 $MCP_DEST 中找不到 package.json，请检查 mcp-server 子模块内容"

# 删除指向内网 registry 的 lockfile，使用公网镜像重新生成
if [ -f "$MCP_DEST/package-lock.json" ] && grep -q "qunhequnhe" "$MCP_DEST/package-lock.json" 2>/dev/null; then
    echo -e "\033[33m    检测到内网 registry lockfile，正在删除以使用公网镜像...\033[0m"
    rm -f "$MCP_DEST/package-lock.json"
fi
rm -f "$MCP_DEST/yarn.lock"

(cd "$MCP_DEST" && npm install --registry=https://registry.npmmirror.com/) || fail "npm install 失败"
ok "依赖安装完成"

# ── 4. 检查 / 安装 Python (含 tkinter) ──────────────────────────────────────
step "检查 Python + tkinter (需要 >= $PYTHON_MIN_VERSION)"
PYTHON_CMD=""
BREW_PYTHON="/opt/homebrew/bin/python3.13"

# macOS 系统自带的 Python 3.9 内置 Tcl/Tk 8.5.9 过旧，GUI 会白屏；
# 需要安装 python-tk@3.13（自带 Tcl/Tk 9.0），并确保 python3 指向它。
need_brew_python=false

if [ -x "$BREW_PYTHON" ]; then
    VER="$("$BREW_PYTHON" --version 2>&1 | sed 's/Python //')"
    if version_ge "$VER" "$PYTHON_MIN_VERSION"; then
        # 验证 tkinter 可用
        if "$BREW_PYTHON" -c "import tkinter" 2>/dev/null; then
            ok "Homebrew Python $VER + tkinter 已就绪"
            PYTHON_CMD="$BREW_PYTHON"
        else
            echo -e "\033[33m    Python $VER 已安装但缺少 tkinter，需要安装 python-tk@3.13\033[0m"
            need_brew_python=true
        fi
    else
        echo -e "\033[33m    Homebrew Python $VER 版本过低，需要升级\033[0m"
        need_brew_python=true
    fi
else
    echo -e "\033[33m    未检测到 Homebrew Python 3.13，准备安装...\033[0m"
    need_brew_python=true
fi

if [ "$need_brew_python" = true ]; then
    if ! command -v brew &>/dev/null; then
        fail "未检测到 Homebrew，请先安装 Homebrew (https://brew.sh/) 或手动安装 Python 3.10.5+ (https://www.python.org/)"
    fi
    echo -e "\033[33m    正在通过 Homebrew 安装 python-tk@3.13（含 Tcl/Tk 9.0）...\033[0m"
    brew install python-tk@3.13 || brew upgrade python-tk@3.13 || true

    if [ ! -x "$BREW_PYTHON" ]; then
        fail "python-tk@3.13 安装后仍无法检测到，请重新开启终端再运行本脚本"
    fi
    PYTHON_CMD="$BREW_PYTHON"
    VER="$("$PYTHON_CMD" --version 2>&1 | sed 's/Python //')"
    ok "Python $VER + tkinter 安装成功"
fi

# 确保 python3 命令指向 Homebrew Python（而非系统旧版）
if [ "$(readlink -f "$(command -v python3 2>/dev/null)" 2>/dev/null)" != "$(readlink -f "$BREW_PYTHON" 2>/dev/null)" ]; then
    echo -e "\033[33m    正在设置 python3 → python3.13 符号链接...\033[0m"
    ln -sf "$BREW_PYTHON" /opt/homebrew/bin/python3
    ln -sf /opt/homebrew/bin/pip3.13 /opt/homebrew/bin/pip3
fi

# 最终验证
"$PYTHON_CMD" -c "import tkinter" 2>/dev/null || fail "tkinter 不可用，请确认 python-tk@3.13 已正确安装"
ok "python3 → $("$PYTHON_CMD" --version 2>&1)"

# ── 5. 配置 wardrobe-agent 快捷方式 ─────────────────────────────────────────
step "配置 wardrobe-agent 快捷方式 (让 $AGENT_DISPLAY_NAME 共享 agents/ 与 skills/)"
SETUP_AGENT_SCRIPT="$AGENT_DEST/scripts/setup_agent.py"
[ -f "$SETUP_AGENT_SCRIPT" ] || fail "找不到 setup_agent.py：$SETUP_AGENT_SCRIPT"

(cd "$AGENT_DEST" && "$PYTHON_CMD" "$SETUP_AGENT_SCRIPT" "$AGENT_TOOL") || fail "setup_agent.py 执行失败，请检查上方输出"
ok "$AGENT_DISPLAY_NAME 快捷方式创建完成"

# ── 6. 安装登录依赖库 ────────────────────────────────────────────────────────
step "安装登录依赖库"
echo -e "\033[33m    正在安装登录依赖库，请耐心等待...\033[0m"

# 安装 requirements.txt 中的包
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
if [ -f "$REQUIREMENTS_FILE" ]; then
    echo -e "\033[33m    正在安装 requirements.txt 中的依赖包...\033[0m"
    (cd "$AGENT_DEST" && "$PYTHON_CMD" -m pip install --break-system-packages -r "$REQUIREMENTS_FILE" -i https://pypi.tuna.tsinghua.edu.cn/simple/) || fail "pip install -r requirements.txt 失败"
    ok "requirements.txt 依赖包安装完成"
else
    fail "找不到 requirements.txt：$REQUIREMENTS_FILE"
fi

# 安装 playwright
(cd "$AGENT_DEST" && "$PYTHON_CMD" -m pip install --break-system-packages playwright -i https://pypi.tuna.tsinghua.edu.cn/simple/) || fail "pip install playwright 失败"
ok "playwright 安装完成"

# 安装浏览器
BROWSER_INSTALL_SCRIPT="$SCRIPT_DIR/install_playwright_browsers_cn_mac.sh"
if [ -f "$BROWSER_INSTALL_SCRIPT" ]; then
    echo -e "\033[33m    正在安装 Playwright 浏览器...\033[0m"
    bash "$BROWSER_INSTALL_SCRIPT" || fail "浏览器安装失败"
    ok "浏览器安装完成"
else
    fail "找不到浏览器安装脚本：$BROWSER_INSTALL_SCRIPT"
fi

# ── 7. 启动桌面启动器 ────────────────────────────────────────────────────────
step "启动 Wardrobe Agent 桌面启动器"
LAUNCHER_PY="$AGENT_DEST/data-tools/ui_tools/launcher/launcher.py"
LAUNCHER_COMMAND="$AGENT_DEST/data-tools/ui_tools/launcher/launcher.command"
[ -f "$LAUNCHER_PY" ] || fail "找不到启动器：$LAUNCHER_PY"

if [ -f "$LAUNCHER_COMMAND" ]; then
    chmod +x "$LAUNCHER_COMMAND"
fi

("$PYTHON_CMD" "$LAUNCHER_PY" --login-env beta >/dev/null 2>&1 &)
ok "桌面启动器已打开（MCP Server 将在窗口打开后自动启动）"

echo ""
echo -e "\033[32m======================================================\033[0m"
echo -e "\033[32m  部署完成！已打开 Wardrobe Agent 启动器窗口：\033[0m"
echo -e "\033[32m  - MCP Server：由启动器后台运行\033[0m"
echo -e "\033[32m  - 登录态：在启动器窗口中登录 / 注销\033[0m"
echo -e "\033[32m  - Agent CLI：请在 Cursor 或终端中自行使用 $AGENT_DISPLAY_NAME\033[0m"
echo -e "\033[32m  - 日后手动启动：python3 $LAUNCHER_PY --login-env beta\033[0m"
echo -e "\033[32m    （使用生产环境：python3 $LAUNCHER_PY --login-env prod）\033[0m"
echo -e "\033[32m    或双击 launcher.command（需可执行权限）\033[0m"
echo -e "\033[32m======================================================\033[0m"
