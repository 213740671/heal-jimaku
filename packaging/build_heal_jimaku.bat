@ECHO OFF
SETLOCAL ENABLEDELAYEDEXPANSION

REM --- 基本配置 ---
ECHO [信息] 开始执行打包脚本...
ECHO [信息] 当前时间: %DATE% %TIME%
SET SCRIPT_DIR=%~dp0
IF "%SCRIPT_DIR:~-1%"=="\" SET "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
SET PROJECT_ROOT=%SCRIPT_DIR%\..
FOR %%I IN ("%PROJECT_ROOT%") DO SET "PROJECT_ROOT=%%~fI"
SET SRC_DIR=%PROJECT_ROOT%\src
SET ASSETS_DIR=%PROJECT_ROOT%\assets

REM 主脚本现在是 src 目录下的 main.py
SET MAIN_SCRIPT_NAME=main.py
SET MAIN_SCRIPT_PATH=%SRC_DIR%\%MAIN_SCRIPT_NAME%

SET REQUIREMENTS_FILE=%PROJECT_ROOT%\requirements.txt
SET VERSION_FILE_PATH=%SCRIPT_DIR%\file_version_info.txt
SET ICON_PATH=%ASSETS_DIR%\icon.ico
SET EXE_NAME=治幕.exe
SET DIST_PATH=%PROJECT_ROOT%\dist_custom
SET BUILD_PATH=%PROJECT_ROOT%\build_custom
SET SPEC_PATH=%PROJECT_ROOT%
SET VENV_DIR=%PROJECT_ROOT%\.venv_packaging
SET PYTHON_EXE_VENV=%VENV_DIR%\Scripts\python.exe
SET PIP_EXE_VENV=%VENV_DIR%\Scripts\pip.exe
SET PYINSTALLER_EXE_VENV=%VENV_DIR%\Scripts\pyinstaller.exe

ECHO [信息] ==================================================
ECHO [信息] 项目配置:
ECHO [信息]     项目根目录: %PROJECT_ROOT%
ECHO [信息]     源文件目录 (SRC_DIR): %SRC_DIR%
ECHO [信息]     主脚本路径 (MAIN_SCRIPT_PATH): %MAIN_SCRIPT_PATH%
ECHO [信息]     EXE 初始输出目录: %DIST_PATH%
ECHO [信息]     虚拟环境目录: %VENV_DIR%
ECHO [信息] ==================================================
PAUSE

REM --- [1/7] 清理旧的构建文件 ---
ECHO.
ECHO [步骤 1/7] 清理旧的构建文件和已生成的EXE...
IF EXIST "%DIST_PATH%" (ECHO [清理] 删除已存在的输出目录: "%DIST_PATH%" && RMDIR /S /Q "%DIST_PATH%")
IF EXIST "%BUILD_PATH%" (ECHO [清理] 删除已存在的构建目录: "%BUILD_PATH%" && RMDIR /S /Q "%BUILD_PATH%")
SET SPEC_FILE_TO_CLEAN=%SPEC_PATH%\%EXE_NAME%.spec
IF EXIST "%SPEC_FILE_TO_CLEAN%" (ECHO [清理] 删除已存在的 .spec 文件: "%SPEC_FILE_TO_CLEAN%" && DEL /F /Q "%SPEC_FILE_TO_CLEAN%")
IF EXIST "%PROJECT_ROOT%\%EXE_NAME%" (ECHO [清理] 删除项目根目录下已存在的 "%EXE_NAME%" && DEL /F /Q "%PROJECT_ROOT%\%EXE_NAME%")
ECHO [步骤 1/7] 清理完成。

REM --- [2/7] 检查 Python 环境 ---
ECHO.
ECHO [步骤 2/7] 检查 Python 环境...
python --version >NUL 2>NUL
IF ERRORLEVEL 1 (ECHO [错误] 未找到 Python。请确保 Python 已安装并添加到系统 PATH 环境变量中。 && PAUSE && EXIT /B 1)
ECHO [信息] Python 版本: & python --version
ECHO [信息] Pip 版本: & python -m pip --version
ECHO [步骤 2/7] Python 环境检查通过。

REM --- [3/7] 创建或更新虚拟环境 ---
ECHO.
ECHO [步骤 3/7] 设置 Python 虚拟环境...
IF NOT EXIST "%PYTHON_EXE_VENV%" (
    ECHO [信息] 虚拟环境不存在，正在创建: "%VENV_DIR%"
    python -m venv "%VENV_DIR%"
    IF ERRORLEVEL 1 (ECHO [错误] 创建虚拟环境失败。 && PAUSE && EXIT /B 1)
    ECHO [信息] 虚拟环境创建成功。
) ELSE (ECHO [信息] 虚拟环境已存在: "%VENV_DIR%")
ECHO [步骤 3/7] 虚拟环境设置完成。

REM --- [4/7] 在虚拟环境中安装依赖 ---
ECHO.
ECHO [步骤 4/7] 在虚拟环境中安装依赖项 (来自 "%REQUIREMENTS_FILE%")...
IF NOT EXIST "%REQUIREMENTS_FILE%" (ECHO [错误] 依赖文件 "%REQUIREMENTS_FILE%" 不存在 && PAUSE && EXIT /B 1)
ECHO [信息] 执行: "%PIP_EXE_VENV%" install -r "%REQUIREMENTS_FILE%"
"%PIP_EXE_VENV%" install -r "%REQUIREMENTS_FILE%"
IF ERRORLEVEL 1 (
    ECHO [错误] 安装依赖项失败。请检查错误信息和 "%REQUIREMENTS_FILE%" 文件。
    ECHO [提示] 如果遇到UnicodeDecodeError，请确保requirements.txt文件为UTF-8编码。
    PAUSE
    EXIT /B 1
)
ECHO [步骤 4/7] 依赖项安装成功。

REM --- [5/7] 使用 PyInstaller 打包 ---
ECHO.
ECHO [步骤 5/7] 使用 PyInstaller 进行打包...
IF NOT EXIST "%MAIN_SCRIPT_PATH%" (ECHO [错误] 主Python脚本 "%MAIN_SCRIPT_PATH%" 未找到 && PAUSE && EXIT /B 1)
IF NOT EXIST "%VERSION_FILE_PATH%" (ECHO [警告] 版本信息文件 "%VERSION_FILE_PATH%" 未找到)
SET "ICON_OPTION="
IF EXIST "%ICON_PATH%" (SET "ICON_OPTION=--icon="%ICON_PATH%"") ELSE (ECHO [警告] 图标文件 "%ICON_PATH%" 未找到)

SET "ADD_DATA_OPTION="
IF EXIST "%ASSETS_DIR%" (SET "ADD_DATA_OPTION=--add-data "%ASSETS_DIR%;assets"" && ECHO [信息] 添加资源数据: !ADD_DATA_OPTION!) ELSE (ECHO [警告] 资源目录 "%ASSETS_DIR%" 不存在)

ECHO [信息] 执行 PyInstaller 命令 (详情见下一行)...
REM --- 修改开始：添加 --paths "%SRC_DIR%" ---
ECHO "%PYINSTALLER_EXE_VENV%" --name "%EXE_NAME%" --onefile --windowed --paths "%SRC_DIR%" !ICON_OPTION! !ADD_DATA_OPTION! --version-file "%VERSION_FILE_PATH%" --distpath "%DIST_PATH%" --workpath "%BUILD_PATH%" --specpath "%SPEC_PATH%" --log-level INFO "%MAIN_SCRIPT_PATH%"

"%PYINSTALLER_EXE_VENV%" ^
    --name "%EXE_NAME%" ^
    --onefile ^
    --windowed ^
    --paths "%SRC_DIR%" ^
    !ICON_OPTION! ^
    !ADD_DATA_OPTION! ^
    --version-file "%VERSION_FILE_PATH%" ^
    --distpath "%DIST_PATH%" ^
    --workpath "%BUILD_PATH%" ^
    --specpath "%SPEC_PATH%" ^
    --log-level INFO ^
    "%MAIN_SCRIPT_PATH%"
REM --- 修改结束 ---

IF ERRORLEVEL 1 (
    ECHO [错误] PyInstaller 打包失败。请检查上面的错误日志。
    PAUSE
    EXIT /B 1
)
ECHO [步骤 5/7] PyInstaller 打包成功。

REM --- [步骤 6/7] 移动EXE并清理构建文件 (不包括虚拟环境) ---
ECHO.
ECHO [步骤 6/7] 开始移动 "%EXE_NAME%" 并清理构建产物 (不包括虚拟环境)...

SET FINAL_EXE_PATH_IN_DIST=%DIST_PATH%\%EXE_NAME%
SET TARGET_EXE_PATH_IN_ROOT=%PROJECT_ROOT%\%EXE_NAME%

IF EXIST "%FINAL_EXE_PATH_IN_DIST%" (
    ECHO [信息] 找到了EXE文件: "%FINAL_EXE_PATH_IN_DIST%"
    ECHO [信息] 准备移动到: "%TARGET_EXE_PATH_IN_ROOT%"
    MOVE /Y "%FINAL_EXE_PATH_IN_DIST%" "%TARGET_EXE_PATH_IN_ROOT%"
    IF !ERRORLEVEL! EQU 0 (
        ECHO [成功] "%EXE_NAME%" 已成功移动到项目根目录: "%PROJECT_ROOT%"
    ) ELSE (
        ECHO [错误] 移动 "%EXE_NAME%" 失败! Errorlevel: !ERRORLEVEL!
        ECHO [提示] 文件可能仍在 "%DIST_PATH%" 中，或者目标路径无法写入。
    )
) ELSE (
    ECHO [错误] 打包后的EXE文件 "%FINAL_EXE_PATH_IN_DIST%" 未找到! 无法移动。
    ECHO [提示] 请检查PyInstaller步骤是否有错误，或输出路径是否正确。
)

ECHO [信息] 开始清理其他构建过程中产生的临时文件和目录...

IF EXIST "%BUILD_PATH%" (
    ECHO [清理] 准备删除构建目录: "%BUILD_PATH%"
    RMDIR /S /Q "%BUILD_PATH%"
    IF !ERRORLEVEL! EQU 0 (ECHO [成功] 构建目录 "%BUILD_PATH%" 已删除。) ELSE (ECHO [错误] 删除构建目录 "%BUILD_PATH%" 失败! Errorlevel: !ERRORLEVEL!)
) ELSE (ECHO [信息] 构建目录 "%BUILD_PATH%" 不存在，无需删除。)

IF EXIST "%DIST_PATH%" (
    ECHO [清理] 准备删除原始输出目录: "%DIST_PATH%"
    RMDIR /S /Q "%DIST_PATH%"
    IF !ERRORLEVEL! EQU 0 (ECHO [成功] 原始输出目录 "%DIST_PATH%" 已删除。) ELSE (ECHO [错误] 删除原始输出目录 "%DIST_PATH%" 失败! Errorlevel: !ERRORLEVEL!)
) ELSE (ECHO [信息] 原始输出目录 "%DIST_PATH%" 不存在，无需删除。)

SET SPEC_FILE_TO_DELETE=%SPEC_PATH%\%EXE_NAME%.spec
IF EXIST "%SPEC_FILE_TO_DELETE%" (
    ECHO [清理] 准备删除 .spec 文件: "%SPEC_FILE_TO_DELETE%"
    DEL /F /Q "%SPEC_FILE_TO_DELETE%"
    IF !ERRORLEVEL! EQU 0 (ECHO [成功] .spec 文件 "%SPEC_FILE_TO_DELETE%" 已删除。) ELSE (ECHO [错误] 删除 .spec 文件 "%SPEC_FILE_TO_DELETE%" 失败! Errorlevel: !ERRORLEVEL!)
) ELSE (ECHO [信息] .spec 文件 "%SPEC_FILE_TO_DELETE%" 不存在，无需删除。)

ECHO [步骤 6/7] 主要清理操作完成。

REM --- [步骤 7/7] 完成与最终清理 ---
ECHO.
ECHO [步骤 7/7] 打包流程基本结束。
IF EXIST "%TARGET_EXE_PATH_IN_ROOT%" (
    ECHO [最终成功] "%EXE_NAME%" 已成功生成并存放于项目根目录:
    ECHO                "%TARGET_EXE_PATH_IN_ROOT%"
) ELSE (
    ECHO [最终警告] "%EXE_NAME%" 未在项目根目录找到。
    ECHO [提示] 请仔细检查以上日志。
    IF EXIST "%FINAL_EXE_PATH_IN_DIST%" (
        ECHO [提示] 文件可能仍保留在原始输出目录: "%FINAL_EXE_PATH_IN_DIST%"
    )
)
ECHO.
ECHO 您可以检查项目根目录 "%PROJECT_ROOT%" 是否有 "%EXE_NAME%" 文件。
ECHO.
ECHO 按任意键后，脚本将将删除 Python 虚拟环境并退出脚本
PAUSE

REM --- 删除虚拟环境目录 ---
ECHO.
ECHO [最终清理]删除虚拟环境目录...
ECHO [最终清理] 目标目录: "%VENV_DIR%"

IF NOT EXIST "%VENV_DIR%" (
    ECHO [信息] 虚拟环境目录 "%VENV_DIR%" 在最终清理前已不存在。
    GOTO FinalExit
)

ECHO [信息] 等待 5 秒... (给文件锁释放时间)
TIMEOUT /T 5 /NOBREAK >NUL

RMDIR /S /Q "%VENV_DIR%"
SET VENV_DEL_ERRORLEVEL=!ERRORLEVEL!

IF !VENV_DEL_ERRORLEVEL! EQU 0 (
    ECHO [成功] 虚拟环境目录 "%VENV_DIR%" 已在最终清理中成功删除。
) ELSE (
    ECHO [警告] 删除虚拟环境目录 "%VENV_DIR%" 失败。Errorlevel: !VENV_DEL_ERRORLEVEL!
    ECHO [提示] 可能是因为某些文件仍被占用。您可以尝试手动删除它。
)

:FinalExit
ECHO.
ECHO [信息] 脚本执行完毕。
ENDLOCAL
EXIT /B 0
