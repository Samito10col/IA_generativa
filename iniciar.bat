@echo off
rem Abre "Erase una IA" en el navegador (http://127.0.0.1:7860)
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
  echo Primero ejecute instalar.bat
  pause & exit /b 1
)
call venv\Scripts\activate.bat
python app.py
pause
