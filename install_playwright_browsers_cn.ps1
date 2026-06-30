# 在国内安装 Playwright Chromium 相关浏览器（绕过 builds/cft 镜像 404）
# 用法（PowerShell）:
#   cd F:\code\wardrobe-agent\data-tools
#   .\scripts\install_playwright_browsers_cn.ps1
#
# 若 playwright 升级后版本号变化，先执行: playwright install chromium --dry-run
# 并对照修改下方 $ChromiumBuild / $ChromiumVersion

$ErrorActionPreference = "Stop"

$ChromiumBuild = "1223"
$ChromiumVersion = "148.0.7778.96"

$NpmmirrorCft = "https://cdn.npmmirror.com/binaries/chrome-for-testing"
$NpmmirrorPw = "https://cdn.npmmirror.com/binaries/playwright"

$MsPlaywright = Join-Path $env:USERPROFILE "AppData\Local\ms-playwright"
$CurrentDir = (Get-Item -Path .).FullName
$TempDir = $CurrentDir
New-Item -ItemType Directory -Force -Path $MsPlaywright | Out-Null

function Expand-ZipInnerTo {
    param(
        [string]$ZipPath,
        [string]$DestDir
    )
    $extractRoot = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetFileNameWithoutExtension($ZipPath))
    if (Test-Path $extractRoot) { Remove-Item -Recurse -Force $extractRoot }
    Expand-Archive -Path $ZipPath -DestinationPath $extractRoot -Force
    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
    $dirsAtRoot = @(Get-ChildItem -Path $extractRoot -Directory)
    $filesAtRoot = @(Get-ChildItem -Path $extractRoot -File)
    # chrome-win64.zip：单层目录
    if ($dirsAtRoot.Count -eq 1 -and $filesAtRoot.Count -eq 0) {
        Copy-Item -Path (Join-Path $dirsAtRoot[0].FullName '*') -Destination $DestDir -Recurse -Force
    } elseif ($dirsAtRoot.Count -gt 0 -or $filesAtRoot.Count -gt 0) {
        Copy-Item -Path (Join-Path $extractRoot '*') -Destination $DestDir -Recurse -Force
    } else {
        throw "解压后为空: $ZipPath"
    }
    Remove-Item -Recurse -Force $extractRoot
}

function Install-CftBrowser {
    param(
        [string]$Url,
        [string]$ZipName,
        [string]$BrowserRoot,
        [string]$InnerDirName
    )
    $marker = Join-Path $BrowserRoot "INSTALLATION_COMPLETE"
    if (Test-Path $marker) {
        Write-Host "[skip] 已存在: $BrowserRoot"
        return
    }
    $zipPath = Join-Path $TempDir $ZipName
    Write-Host "[download] $Url"
    Invoke-WebRequest -Uri $Url -OutFile $zipPath -UseBasicParsing
    $dest = Join-Path $BrowserRoot $InnerDirName
    Expand-ZipInnerTo -ZipPath $zipPath -DestDir $dest
    Remove-Item -Force $zipPath
    Set-Content -Path $marker -Value "1" -Encoding ascii
    Write-Host "[done] $BrowserRoot\$InnerDirName"
}

# Chromium（npmmirror 路径无 builds/cft）
Install-CftBrowser `
    -Url "$NpmmirrorCft/$ChromiumVersion/win64/chrome-win64.zip" `
    -ZipName "chrome-win64.zip" `
    -BrowserRoot (Join-Path $MsPlaywright "chromium-$ChromiumBuild") `
    -InnerDirName "chrome-win64"

Install-CftBrowser `
    -Url "$NpmmirrorCft/$ChromiumVersion/win64/chrome-headless-shell-win64.zip" `
    -ZipName "chrome-headless-shell-win64.zip" `
    -BrowserRoot (Join-Path $MsPlaywright "chromium_headless_shell-$ChromiumBuild") `
    -InnerDirName "chrome-headless-shell-win64"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " 安装检查完成（[skip] = 该组件此前已装好）" -ForegroundColor Green
Write-Host " 目录: $MsPlaywright" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "正在运行 playwright install chromium 做最终校验…"

Remove-Item Env:PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST -ErrorAction SilentlyContinue
$env:PLAYWRIGHT_DOWNLOAD_HOST = $NpmmirrorPw
$pwResult = playwright install chromium 2>&1
$pwResult | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Host "playwright 校验返回非零退出码: $LASTEXITCODE" -ForegroundColor Yellow
} else {
    Write-Host "Playwright Chromium 已就绪，可启动 UI 使用浏览器登录功能。" -ForegroundColor Green
}
