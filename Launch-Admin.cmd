@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto pythonfallback
py -3 -m clair_storage.permissions %*
if errorlevel 1 pause
exit /b
:pythonfallback
where python >nul 2>nul
if errorlevel 1 goto missing
python -m clair_storage.permissions %*
if errorlevel 1 pause
exit /b
:missing
echo Python est introuvable. Installez Python 3.11 ou 3.12 avec Tcl/Tk.
echo Puis relancez Launch-Admin.cmd. Aucun logiciel ne sera installe automatiquement.
pause
