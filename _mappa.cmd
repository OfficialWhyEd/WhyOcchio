@echo off
cd /d %~dp0
python -u mappa.py > %~dp0\mappa_out.txt 2>&1
