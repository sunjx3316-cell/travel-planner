@echo off
chcp 65001 >nul
title 旅行智规 - 小红书采集
cd /d "%~dp0.."
echo ============================================
echo   旅行智规 · 小红书采集工具
echo   1) 登录(首次必做,弹浏览器扫码)
echo   2) 采集指定景区
echo   3) 采集全部缺笔记景区
echo   4) 探测会话状态(采集前推荐)
echo ============================================
set /p choice=请选择(1/2/3/4):
if "%choice%"=="1" goto login
if "%choice%"=="2" goto spot
if "%choice%"=="3" goto all
if "%choice%"=="4" goto probe
echo 无效选择
pause
exit

:login
.venv\Scripts\python.exe scripts\collect_xhs.py --login
pause
exit

:spot
set /p spot=请输入景区名称(如:天坛公园):
.venv\Scripts\python.exe scripts\collect_xhs.py %spot%
pause
exit

:all
.venv\Scripts\python.exe scripts\collect_xhs.py
pause
exit

:probe
.venv\Scripts\python.exe scripts\collect_xhs.py --probe
pause
exit
