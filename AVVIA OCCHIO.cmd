@echo off
title OCCHIO
cd /d %~dp0
start "" pythonw occhio.py
echo OCCHIO avviato.  Dal telefono: http://IP-DEL-PC:8099
timeout /t 3 >nul
