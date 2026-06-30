<#
.SYNOPSIS
    一键部署 MCP Server 和 Wardrobe Agent 环境
.DESCRIPTION
    配置 mcp-server 和 wardrobe-agent（已通过 git submodule 引入），
    完成后启动桌面启动器（launcher.pyw）：
    - 后台静默运行 MCP Server
    - 展示登录态并提供登录 / 注销
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 检查是否以管理员身份运行
function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# 需要管理员时，以提权方式重启本脚本
function Request-Elevation {
    Write-Host "    需要管理员权限安装软件，正在请求提权..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.ScriptName
    Start-Process powershell.exe -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$scriptPath`"" -Verb RunAs
    exit 0
}

# ── 配置项 ──────────────────────────────────────────────────────────────────
$ScriptDir      = $PSScriptRoot
$McpDest        = Join-Path $ScriptDir "mcp-server"
$AgentDest      = Join-Path $ScriptDir "wardrobe-agent"
$NodeMinVersion = [Version]"18.0.0"
$PythonMinVersion = [Version]"3.10.5"
# ────────────────────────────────────────────────────────────────────────────

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ">>> $Message" -ForegroundColor Cyan
}

function Write-OK {
    param([string]$Message)
    Write-Host "    [OK] $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "    [ERROR] $Message" -ForegroundColor Red
    exit 1
}

# ── 0. 检查子模块目录是否存在 ─────────────────────────────────────────────────
Write-Step "检查子模块目录"
if (-not (Test-Path $McpDest))   { Write-Fail "找不到 mcp-server 子模块目录：$McpDest，请先执行 git submodule update --init" }
if (-not (Test-Path $AgentDest)) { Write-Fail "找不到 wardrobe-agent 子模块目录：$AgentDest，请先执行 git submodule update --init" }
Write-OK "子模块目录检查通过"

# ── 1. 选择 Agent 工具 ───────────────────────────────────────────────────────
Write-Step "选择 Agent 工具"
$AgentTool = $null
while (-not $AgentTool) {
    Write-Host "    请选择要使用的 Agent 工具：" -ForegroundColor Yellow
    Write-Host "      [1] Cursor"
    Write-Host "      [2] Claude Code"
    $choice = Read-Host "    请输入 1 或 2"
    switch ($choice) {
        "1" { $AgentTool = "cursor" }
        "2" { $AgentTool = "claude" }
        default { Write-Host "    无效输入，请重新选择" -ForegroundColor Red }
    }
}
if ($AgentTool -eq "cursor") {
    $AgentDisplayName  = "Cursor"
    $AgentHiddenDir    = ".cursor"
    $AgentLaunchCmd    = "agent --force --approve-mcps"
    $AgentCheckCommand = "agent"
} else {
    $AgentDisplayName  = "Claude Code"
    $AgentHiddenDir    = ".claude"
    $AgentLaunchCmd    = "claude"
    $AgentCheckCommand = "claude"
}
Write-OK "已选择：$AgentDisplayName"

# ── 2. 检查 / 安装 Node.js ───────────────────────────────────────────────────
Write-Step "检查 Node.js（需要 >= $NodeMinVersion）"
$nodeOk = $false
try {
    $nodeVer = (node --version 2>$null) -replace '^v',''
    if ([Version]$nodeVer -ge $NodeMinVersion) {
        Write-OK "Node.js $nodeVer 已安装，满足要求"
        $nodeOk = $true
    } else {
        Write-Host "    Node.js $nodeVer 版本过低，需要升级" -ForegroundColor Yellow
    }
} catch {
    Write-Host "    未检测到 Node.js，准备安装..." -ForegroundColor Yellow
}

if (-not $nodeOk) {
    Write-Host "    正在通过 winget 安装 Node.js LTS..." -ForegroundColor Yellow
    if (-not (Test-IsAdmin)) { Request-Elevation }
    try {
        winget install --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements -e
        # 刷新 PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $nodeVer = (node --version) -replace '^v',''
        Write-OK "Node.js $nodeVer 安装成功"
    } catch {
        Write-Fail "自动安装 Node.js 失败，请手动从 https://nodejs.org/ 安装 18+ 版本后重试"
    }
}

# ── 3. 安装 mcp-server 依赖 ──────────────────────────────────────────────────
Write-Step "安装 mcp-server 依赖（npm install）"

if (-not (Test-Path (Join-Path $McpDest "package.json"))) {
    Write-Fail "在 $McpDest 中找不到 package.json，请检查 mcp-server 子模块内容"
}

Push-Location $McpDest
try {
    cmd /c "npm install"
    if ($LASTEXITCODE -ne 0) { Write-Fail "npm install 失败" }
    Write-OK "依赖安装完成"
} finally {
    Pop-Location
}

# ── 4. 检查 / 安装 Python ────────────────────────────────────────────────────
Write-Step "检查 Python（需要 >= $PythonMinVersion）"
$pythonOk = $false
$pythonCmd = $null

foreach ($cmd in @("python", "python3")) {
    try {
        $raw = & $cmd --version 2>&1
        if ($raw -match "Python\s+(\d+\.\d+\.\d+)") {
            $ver = [Version]$Matches[1]
            if ($ver -ge $PythonMinVersion) {
                Write-OK "Python $ver 已安装，满足要求（命令：$cmd）"
                $pythonCmd = $cmd
                $pythonOk = $true
                break
            } else {
                Write-Host "    Python $ver 版本过低，需要升级" -ForegroundColor Yellow
            }
        }
    } catch { }
}

if (-not $pythonOk) {
    Write-Host "    未检测到满足条件的 Python，准备安装..." -ForegroundColor Yellow
    if (-not (Test-IsAdmin)) { Request-Elevation }
    try {
        winget install --id Python.Python.3.10 --accept-source-agreements --accept-package-agreements -e
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $raw = python --version 2>&1
        if ($raw -match "Python\s+(\d+\.\d+\.\d+)") {
            Write-OK "Python $($Matches[1]) 安装成功"
            $pythonCmd = "python"
        } else {
            Write-Fail "Python 安装后仍无法检测到，请重新开启终端再运行本脚本"
        }
    } catch {
        Write-Fail "自动安装 Python 失败，请手动从 https://www.python.org/ 安装 3.10.5+ 版本后重试"
    }
}

# ── 5. 检查 / 安装 Agent CLI ─────────────────────────────────────────────────
Write-Step "检查 $AgentDisplayName"
if (Get-Command $AgentCheckCommand -ErrorAction SilentlyContinue) {
    Write-OK "$AgentDisplayName 已安装"
} else {
    Write-Host "    未检测到 $AgentCheckCommand 命令，正在安装 $AgentDisplayName..." -ForegroundColor Yellow
    try {
        if ($AgentTool -eq "cursor") {
            Invoke-RestMethod 'https://cursor.com/install?win32=true' | Invoke-Expression
        } else {
            cmd /c "npm install -g @anthropic-ai/claude-code"
            if ($LASTEXITCODE -ne 0) { Write-Fail "npm install -g @anthropic-ai/claude-code 失败" }
        }
        # 刷新 PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        if (Get-Command $AgentCheckCommand -ErrorAction SilentlyContinue) {
            Write-OK "$AgentDisplayName 安装成功"
        } else {
            Write-Fail "$AgentDisplayName 安装后仍无法检测到，请重新开启终端再运行本脚本"
        }
    } catch {
        Write-Fail "安装 $AgentDisplayName 失败：$_"
    }
}

# ── 6. 配置 wardrobe-agent 快捷方式 ──────────────────────────────────────────
Write-Step "配置 wardrobe-agent 快捷方式（让 $AgentDisplayName 共享 agents/ 与 skills/）"
$setupAgentScript = Join-Path $AgentDest "scripts\setup_agent.py"
if (-not (Test-Path $setupAgentScript)) {
    Write-Fail "找不到 setup_agent.py：$setupAgentScript"
}

Push-Location $AgentDest
try {
    & $pythonCmd $setupAgentScript $AgentTool
    if ($LASTEXITCODE -ne 0) { Write-Fail "setup_agent.py 执行失败，请检查上方输出" }
    Write-OK "$AgentDisplayName 快捷方式创建完成"
} finally {
    Pop-Location
}

# ── 7. 安装登录依赖库 ────────────────────────────────────────────────────────
Write-Step "安装登录依赖库"
Write-Host "    正在安装登录依赖库，请耐心等待..." -ForegroundColor Yellow

# 安装 requirements.txt 中的包
$requirementsFile = Join-Path $ScriptDir "requirements.txt"
if (Test-Path $requirementsFile) {
    Write-Host "    正在安装 requirements.txt 中的依赖包..." -ForegroundColor Yellow
    Push-Location $AgentDest
    try {
        & $pythonCmd -m pip install -r $requirementsFile -i https://pypi.tuna.tsinghua.edu.cn/simple/
        if ($LASTEXITCODE -ne 0) { Write-Fail "pip install -r requirements.txt 失败" }
        Write-OK "requirements.txt 依赖包安装完成"
    } finally {
        Pop-Location
    }
} else {
    Write-Fail "找不到 requirements.txt：$requirementsFile"
}

# 安装 playwright
Push-Location $AgentDest
try {
    & $pythonCmd -m pip install playwright -i https://pypi.tuna.tsinghua.edu.cn/simple/
    if ($LASTEXITCODE -ne 0) { Write-Fail "pip install playwright 失败" }
    Write-OK "playwright 安装完成"
} finally {
    Pop-Location
}

# 安装浏览器
$browserInstallScript = Join-Path $ScriptDir "install_playwright_browsers_cn.ps1"
if (Test-Path $browserInstallScript) {
    Write-Host "    正在安装 Playwright 浏览器..." -ForegroundColor Yellow
    & powershell.exe -ExecutionPolicy Bypass -File $browserInstallScript
    if ($LASTEXITCODE -ne 0) { Write-Fail "浏览器安装失败" }
    Write-OK "浏览器安装完成"
} else {
    Write-Fail "找不到浏览器安装脚本：$browserInstallScript"
}

# ── 8. 启动桌面启动器 ────────────────────────────────────────────────────────
Write-Step "启动 Wardrobe Agent 桌面启动器"
$launcherPy = Join-Path $AgentDest "data-tools\ui_tools\launcher\launcher.py"
if (-not (Test-Path $launcherPy)) {
    Write-Fail "找不到启动器：$launcherPy"
}

$pythonExe = (Get-Command $pythonCmd).Source
Start-Process -FilePath $pythonExe -ArgumentList "`"$launcherPy`""
Write-OK "桌面启动器已打开（MCP Server 将在后台静默启动）"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Green
Write-Host "  部署完成！已打开 Wardrobe Agent 启动器窗口：" -ForegroundColor Green
Write-Host "  - MCP Server：后台静默运行" -ForegroundColor Green
Write-Host "  - 登录态：在启动器窗口中登录 / 注销" -ForegroundColor Green
Write-Host "  - Agent CLI：请在 Cursor 或终端中自行使用 $AgentDisplayName" -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
