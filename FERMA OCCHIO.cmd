@echo off
title FERMA OCCHIO
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
echo OCCHIO fermato. Nessun processo attivo.
timeout /t 3 >nul
