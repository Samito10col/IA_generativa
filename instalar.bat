@echo off
rem ================================================================
rem  Erase una IA - instalacion en un computador nuevo (Windows)
rem  Uso:  instalar.bat                 (descarga los modelos)
rem        instalar.bat E:\storybook_usb (copia los modelos de una USB)
rem  Requisitos previos: Python 3.11, Git y Ollama instalados.
rem ================================================================
setlocal
cd /d "%~dp0"
echo.
echo === Erase una IA: instalacion ===
echo.

py -3.11 --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encontro Python 3.11.
  echo Instalelo desde https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
  pause & exit /b 1
)
where ollama >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encontro Ollama. Instalelo desde https://ollama.com/download
  echo Luego cierre esta ventana y vuelva a ejecutar instalar.bat
  pause & exit /b 1
)

echo [1/4] Creando el entorno de Python...
if not exist venv\Scripts\python.exe py -3.11 -m venv venv
call venv\Scripts\activate.bat

echo [2/4] Instalando librerias (puede tardar 10-20 minutos)...
python -m pip install --upgrade pip
pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 ( echo [ERROR] Fallo la instalacion de PyTorch & pause & exit /b 1 )
pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] Fallo la instalacion de librerias & pause & exit /b 1 )

echo [3/4] Modelos...
if not "%~1"=="" (
  echo Copiando modelos desde %~1 ...
  if exist "%~1\models" robocopy "%~1\models" "%~dp0models" /E /NFL /NDL /NJH /NJS /NP
  if exist "%~1\ollama_models" robocopy "%~1\ollama_models" "%USERPROFILE%\.ollama\models" /E /NFL /NDL /NJH /NJS /NP
)
if not exist models\dreamshaper-8\model_index.json (
  echo Descargando modelos de imagen y voz...
  python descargar_modelos.py dreamshaper lcm voz
)

echo [4/4] Modelo de texto (Ollama)...
ollama list | findstr /i "qwen3:4b-instruct" >nul
if errorlevel 1 ollama pull qwen3:4b-instruct

echo.
echo === Listo. Para abrir la aplicacion: doble clic en iniciar.bat ===
pause
