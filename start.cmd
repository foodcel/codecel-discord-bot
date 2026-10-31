@echo off
cd /d "%~dp0"
title Bug bot
:loop
node src\index.js >> data\bot.log 2>&1
echo Bot stopped, restarting in 10s...
timeout /t 10 /nobreak >nul
goto loop
