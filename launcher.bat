@echo off
REM Wardrobe Agent 启动器（Windows 双击入口，不依赖 .pyw 文件关联）
set "LAUNCHER_DIR=%~dp0wardrobe-agent\data-tools\ui_tools\launcher\"
cd /d "%LAUNCHER_DIR%"
start "" pyw -3 "%LAUNCHER_DIR%launcher.pyw"
