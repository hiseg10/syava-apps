@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion
set "PYTHONUTF8=1"

REM ==========================================================
REM  BOOTLOADER - repositorio syava-apps (SysAva\apps)
REM  Detecta/cria o venv do SysAva e inicia os apps Streamlit
REM ==========================================================

set "APPS_DIR=%~dp0"
for %%a in ("%APPS_DIR%..") do set "SYSAVA_ROOT=%%~fa"
set "VENV_PATH=%SYSAVA_ROOT%\.sysenv"

echo ========================================================
echo          SYAVA-APPS - BOOTLOADER
echo ========================================================
echo [INFO] SysAva: "%SYSAVA_ROOT%"

REM ----------------------------------------------------------
REM 1. BUSCA DO PYTHON 3.11
REM ----------------------------------------------------------
set "PYTHON_EXECUTABLE="
for /f "tokens=*" %%i in ('py -3.11 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXECUTABLE=%%i"

if not defined PYTHON_EXECUTABLE (
    echo [ERRO] Python 3.11 nao encontrado. Instale em https://www.python.org/downloads/release/python-3119/
    pause & exit /b 1
)

REM ----------------------------------------------------------
REM 2. VENV DO SYSAVA (cria se nao existir)
REM ----------------------------------------------------------
if not exist "%VENV_PATH%\Scripts\python.exe" (
    echo [INFO] Criando ambiente virtual em "%VENV_PATH%"...
    "%PYTHON_EXECUTABLE%" -m venv "%VENV_PATH%"
    if not exist "%VENV_PATH%\Scripts\python.exe" (
        echo [ERRO] Falha ao criar o venv.
        pause & exit /b 1
    )
    set "NEED_DEPS=1"
)

if not defined NEED_DEPS (
    CHOICE /C sn /T 7 /D n /M "Verificar/atualizar as dependencias (requirements)?"
    if !errorlevel! == 1 set "NEED_DEPS=1"
)

if defined NEED_DEPS (
    echo [INFO] Instalando dependencias...
    "%VENV_PATH%\Scripts\python.exe" -m pip install --upgrade pip >nul
    if exist "%APPS_DIR%requirements.txt" (
        "%VENV_PATH%\Scripts\pip.exe" install -r "%APPS_DIR%requirements.txt"
    ) else (
        "%VENV_PATH%\Scripts\pip.exe" install -r "%SYSAVA_ROOT%\requirements.txt"
    )
)

set STREAMLIT_SERVER_ADDRESS=localhost
set FORCE_LOCAL_MODE=1

REM ----------------------------------------------------------
REM 3. MENU
REM ----------------------------------------------------------
:menu
cls
echo ========================================================
echo                 SYAVA-APPS - MENU
echo ========================================================
echo.
echo [1] Verificador de Duplicatas        (porta 8502)
echo [2] Monitor de Consumo Supabase      (porta 8503)
echo [3] Down SeducTec                    (porta 8504)
echo [4] Planejamento e Registro          (porta 8510)
echo [5] Analise de Notas (dashboard)
echo [6] Abrir README do repositorio
echo [7] Repositorio no GitHub
echo [8] Sair
echo.
echo ========================================================
set /p escolha="Digite a opcao desejada (1-8): "

if "%escolha%"=="1" goto start_dup
if "%escolha%"=="2" goto start_mon
if "%escolha%"=="3" goto start_sed
if "%escolha%"=="4" goto start_plan
if "%escolha%"=="5" goto start_notas
if "%escolha%"=="6" goto start_readme
if "%escolha%"=="7" goto start_github
if "%escolha%"=="8" exit /b 0
goto menu

:start_dup
call "%VENV_PATH%\Scripts\streamlit.exe" run "%APPS_DIR%duplicate_checker\duplicate_checker_streamlit.py" --server.port 8502
pause & goto menu

:start_mon
call "%VENV_PATH%\Scripts\streamlit.exe" run "%APPS_DIR%supabase_monitor\supabase_monitor_streamlit.py" --server.port 8503
pause & goto menu

:start_sed
call "%VENV_PATH%\Scripts\streamlit.exe" run "%APPS_DIR%down_seductec\down_seductec_streamlit.py" --server.port 8504
pause & goto menu

:start_plan
call "%VENV_PATH%\Scripts\streamlit.exe" run "%APPS_DIR%planejamento_registro\planejamento_registro_streamlit.py" --server.port 8510
pause & goto menu

:start_notas
if exist "%APPS_DIR%analise_notas\README_DASHBOARD.md" (
    start "" "%APPS_DIR%analise_notas\README_DASHBOARD.md"
) else (
    echo [INFO] Rode: %VENV_PATH%\Scripts\python.exe "%APPS_DIR%analise_notas\export_student_scores.py"
)
pause & goto menu

:start_readme
start "" "%APPS_DIR%README.md"
goto menu

:start_github
start "" "https://github.com/hiseg10/syava-apps"
goto menu
