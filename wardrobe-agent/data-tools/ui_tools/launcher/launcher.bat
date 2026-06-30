@echo off
REM Wardrobe Agent 启动器（Windows 双击入口，不依赖 .pyw 文件关联）
cd /d "%~dp0"
start "" pyw -3 "%~dp0launcher.pyw"
