@echo off
rem ================================================================
rem  Copia los modelos a una USB para instalar en otro computador
rem  sin descargarlos de nuevo (~6 GB).
rem  Uso:  preparar_usb.bat E:\storybook_usb
rem ================================================================
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Uso: preparar_usb.bat E:\storybook_usb   ^(cambie E: por la letra de su USB^)
  pause & exit /b 1
)
set DESTINO=%~1
echo Copiando modelos a %DESTINO% ...
for %%M in (dreamshaper-8 lcm-lora-sdv1-5 piper) do (
  if exist "models\%%M" robocopy "models\%%M" "%DESTINO%\models\%%M" /E /NFL /NDL /NJH /NJS /NP
)
echo Copiando el modelo de texto de Ollama...
robocopy "%USERPROFILE%\.ollama\models" "%DESTINO%\ollama_models" /E /NFL /NDL /NJH /NJS /NP
echo.
echo Listo. En el otro computador ejecute:  instalar.bat %DESTINO%
echo (No se copian SD 1.4 ni AudioLDM: son opcionales y pesan ~7 GB.)
pause
