#!/bin/bash

# 在国内安装 Playwright Chromium 相关浏览器（绕过 builds/cft 镜像 404）
# 用法（bash）:
#   cd F:\code\wardrobe-agent\data-tools
#   ./scripts/install_playwright_browsers_cn_mac.sh
#
# 若 playwright 升级后版本号变化，先执行: playwright install chromium --dry-run
# 并对照修改下方 CHROMIUM_BUILD / CHROMIUM_VERSION

set -e

CHROMIUM_BUILD="1223"
CHROMIUM_VERSION="148.0.7778.96"

NPM_MIRROR_CFT="https://cdn.npmmirror.com/binaries/chrome-for-testing"
NPM_MIRROR_PW="https://cdn.npmmirror.com/binaries/playwright"

PW_DIR="$HOME/Library/Caches/ms-playwright"
CURRENT_DIR=$(pwd)
TEMP_DIR="$CURRENT_DIR"

mkdir -p "$PW_DIR"

function extract_zip_inner_to {
    local zip_path=$1
    local dest_dir=$2
    
    local extract_root="/tmp/$(basename "${zip_path%.*}")-$$"
    
    if [[ -d "$extract_root" ]]; then
        rm -rf "$extract_root"
    fi
    
    unzip -q "$zip_path" -d "$extract_root"
    
    mkdir -p "$dest_dir"
    
    # 获取解压后的顶层目录和文件
    local dirs_at_root=($(find "$extract_root" -mindepth 1 -maxdepth 1 -type d))
    local files_at_root=($(find "$extract_root" -mindepth 1 -maxdepth 1 -type f))
    
    # chrome-mac-arm64.zip：单层目录
    if [[ ${#dirs_at_root[@]} -eq 1 && ${#files_at_root[@]} -eq 0 ]]; then
        cp -r "$extract_root"/*/.[^.]* "$extract_root"/*/* "$dest_dir"/ 2>/dev/null || true
        cp -r "$extract_root"/*/.??* "$extract_root"/*/* "$dest_dir"/ 2>/dev/null || true
        cp -r "$extract_root"/*/* "$dest_dir"/ 2>/dev/null || true
        cp -r "$extract_root"/*/[^.]* "$dest_dir"/ 2>/dev/null || true
    elif [[ ${#dirs_at_root[@]} -gt 0 || ${#files_at_root[@]} -gt 0 ]]; then
        cp -r "$extract_root"/* "$dest_dir"/
    else
        echo "错误: 解压后为空: $zip_path"
        rm -rf "$extract_root"
        exit 1
    fi
    rm -rf "$extract_root"
}

function install_cft_browser {
    local url=$1
    local zip_name=$2
    local browser_root=$3
    local inner_dir_name=$4
    
    local marker="$browser_root/INSTALLATION_COMPLETE"
    
    if [[ -f "$marker" ]]; then
        echo "[skip] 已存在: $browser_root"
        return
    fi
    
    local zip_path="$TEMP_DIR/$zip_name"
    echo "[download] $url"
    curl -L -o "$zip_path" "$url"
    
    local dest="$browser_root/$inner_dir_name"
    extract_zip_inner_to "$zip_path" "$dest"
    rm -f "$zip_path"
    
    echo "1" > "$marker"
    echo "[done] $browser_root/$inner_dir_name"
}

# Chromium（npmmirror 路径无 builds/cft）
install_cft_browser \
    "$NPM_MIRROR_CFT/$CHROMIUM_VERSION/mac-arm64/chrome-mac-arm64.zip" \
    "chrome-mac-arm64.zip" \
    "$PW_DIR/chromium-$CHROMIUM_BUILD" \
    "chrome-mac-arm64"

install_cft_browser \
    "$NPM_MIRROR_CFT/$CHROMIUM_VERSION/mac-arm64/chrome-headless-shell-mac-arm64.zip" \
    "chrome-headless-shell-mac-arm64.zip" \
    "$PW_DIR/chromium_headless_shell-$CHROMIUM_BUILD" \
    "chrome-headless-shell-mac-arm64"

echo ""
echo "========================================"
echo " 安装检查完成（[skip] = 该组件此前已装好）"
echo " 目录: $PW_DIR"
echo "========================================"
echo ""

echo "正在运行 playwright install chromium 做最终校验…"

unset PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST
export PLAYWRIGHT_DOWNLOAD_HOST="$NPM_MIRROR_PW"
playwright install chromium
if [ $? -ne 0 ]; then
    echo "playwright 校验返回非零退出码" >&2
else
    echo "Playwright Chromium 已就绪，可启动 UI 使用浏览器登录功能。"
fi