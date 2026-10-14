@echo off
chcp 65001 >nul
echo Dang kiem tra va cai dat thu vien...
pip install -r requirements.txt
echo Khoi dong tool...
python gui_app.py
pause
