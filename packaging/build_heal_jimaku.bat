@ECHO OFF
SETLOCAL ENABLEDELAYEDEXPANSION

REM --- �������� ---
ECHO [��Ϣ] ��ʼִ�д���ű�...
ECHO [��Ϣ] ��ǰʱ��: %DATE% %TIME%
SET SCRIPT_DIR=%~dp0
IF "%SCRIPT_DIR:~-1%"=="\" SET "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
SET PROJECT_ROOT=%SCRIPT_DIR%\..
FOR %%I IN ("%PROJECT_ROOT%") DO SET "PROJECT_ROOT=%%~fI"
SET SRC_DIR=%PROJECT_ROOT%\src
SET ASSETS_DIR=%PROJECT_ROOT%\assets

REM ���ű������� src Ŀ¼�µ� main.py
SET MAIN_SCRIPT_NAME=main.py
SET MAIN_SCRIPT_PATH=%SRC_DIR%\%MAIN_SCRIPT_NAME%

SET REQUIREMENTS_FILE=%PROJECT_ROOT%\requirements.txt
SET VERSION_FILE_PATH=%SCRIPT_DIR%\file_version_info.txt
SET ICON_PATH=%ASSETS_DIR%\icon.ico
SET EXE_NAME=��Ļ.exe
SET DIST_PATH=%PROJECT_ROOT%\dist_custom
SET BUILD_PATH=%PROJECT_ROOT%\build_custom
SET SPEC_PATH=%PROJECT_ROOT%
SET VENV_DIR=%PROJECT_ROOT%\.venv_packaging
SET PYTHON_EXE_VENV=%VENV_DIR%\Scripts\python.exe
SET PIP_EXE_VENV=%VENV_DIR%\Scripts\pip.exe
SET PYINSTALLER_EXE_VENV=%VENV_DIR%\Scripts\pyinstaller.exe

ECHO [��Ϣ] ==================================================
ECHO [��Ϣ] ��Ŀ����:
ECHO [��Ϣ]     ��Ŀ��Ŀ¼: %PROJECT_ROOT%
ECHO [��Ϣ]     Դ�ļ�Ŀ¼ (SRC_DIR): %SRC_DIR%
ECHO [��Ϣ]     ���ű�·�� (MAIN_SCRIPT_PATH): %MAIN_SCRIPT_PATH%
ECHO [��Ϣ]     EXE ��ʼ���Ŀ¼: %DIST_PATH%
ECHO [��Ϣ]     ���⻷��Ŀ¼: %VENV_DIR%
ECHO [��Ϣ] ==================================================
PAUSE

REM --- [1/7] ����ɵĹ����ļ� ---
ECHO.
ECHO [���� 1/7] ����ɵĹ����ļ��������ɵ�EXE...
IF EXIST "%DIST_PATH%" (ECHO [����] ɾ���Ѵ��ڵ����Ŀ¼: "%DIST_PATH%" && RMDIR /S /Q "%DIST_PATH%")
IF EXIST "%BUILD_PATH%" (ECHO [����] ɾ���Ѵ��ڵĹ���Ŀ¼: "%BUILD_PATH%" && RMDIR /S /Q "%BUILD_PATH%")
SET SPEC_FILE_TO_CLEAN=%SPEC_PATH%\%EXE_NAME%.spec
IF EXIST "%SPEC_FILE_TO_CLEAN%" (ECHO [����] ɾ���Ѵ��ڵ� .spec �ļ�: "%SPEC_FILE_TO_CLEAN%" && DEL /F /Q "%SPEC_FILE_TO_CLEAN%")
IF EXIST "%PROJECT_ROOT%\%EXE_NAME%" (ECHO [����] ɾ����Ŀ��Ŀ¼���Ѵ��ڵ� "%EXE_NAME%" && DEL /F /Q "%PROJECT_ROOT%\%EXE_NAME%")
ECHO [���� 1/7] ������ɡ�

REM --- [2/7] ��� Python ���� ---
ECHO.
ECHO [���� 2/7] ��� Python ����...
python --version >NUL 2>NUL
IF ERRORLEVEL 1 (ECHO [����] δ�ҵ� Python����ȷ�� Python �Ѱ�װ����ӵ�ϵͳ PATH ���������С� && PAUSE && EXIT /B 1)
ECHO [��Ϣ] Python �汾: & python --version
ECHO [��Ϣ] Pip �汾: & python -m pip --version
ECHO [���� 2/7] Python �������ͨ����

REM --- [3/7] ������������⻷�� ---
ECHO.
ECHO [���� 3/7] ���� Python ���⻷��...
IF NOT EXIST "%PYTHON_EXE_VENV%" (
    ECHO [��Ϣ] ���⻷�������ڣ����ڴ���: "%VENV_DIR%"
    python -m venv "%VENV_DIR%"
    IF ERRORLEVEL 1 (ECHO [����] �������⻷��ʧ�ܡ� && PAUSE && EXIT /B 1)
    ECHO [��Ϣ] ���⻷�������ɹ���
) ELSE (ECHO [��Ϣ] ���⻷���Ѵ���: "%VENV_DIR%")
ECHO [���� 3/7] ���⻷��������ɡ�

REM --- [4/7] �����⻷���а�װ���� ---
ECHO.
ECHO [���� 4/7] �����⻷���а�װ������ (���� "%REQUIREMENTS_FILE%")...
IF NOT EXIST "%REQUIREMENTS_FILE%" (ECHO [����] �����ļ� "%REQUIREMENTS_FILE%" ������ && PAUSE && EXIT /B 1)
ECHO [��Ϣ] ִ��: "%PIP_EXE_VENV%" install -r "%REQUIREMENTS_FILE%"
"%PIP_EXE_VENV%" install -r "%REQUIREMENTS_FILE%"
IF ERRORLEVEL 1 (
    ECHO [����] ��װ������ʧ�ܡ����������Ϣ�� "%REQUIREMENTS_FILE%" �ļ���
    ECHO [��ʾ] �������UnicodeDecodeError����ȷ��requirements.txt�ļ�ΪUTF-8���롣
    PAUSE
    EXIT /B 1
)
ECHO [���� 4/7] �����װ�ɹ���

REM --- [5/7] ʹ�� PyInstaller ��� ---
ECHO.
ECHO [���� 5/7] ʹ�� PyInstaller ���д��...
IF NOT EXIST "%MAIN_SCRIPT_PATH%" (ECHO [����] ��Python�ű� "%MAIN_SCRIPT_PATH%" δ�ҵ� && PAUSE && EXIT /B 1)
IF NOT EXIST "%VERSION_FILE_PATH%" (ECHO [����] �汾��Ϣ�ļ� "%VERSION_FILE_PATH%" δ�ҵ�)
SET "ICON_OPTION="
IF EXIST "%ICON_PATH%" (SET "ICON_OPTION=--icon="%ICON_PATH%"") ELSE (ECHO [����] ͼ���ļ� "%ICON_PATH%" δ�ҵ�)

SET "ADD_DATA_OPTION="
IF EXIST "%ASSETS_DIR%" (SET "ADD_DATA_OPTION=--add-data "%ASSETS_DIR%;assets"" && ECHO [��Ϣ] �����Դ����: !ADD_DATA_OPTION!) ELSE (ECHO [����] ��ԴĿ¼ "%ASSETS_DIR%" ������)

ECHO [��Ϣ] ִ�� PyInstaller ���� (�������һ��)...
REM --- �޸Ŀ�ʼ����� --paths "%SRC_DIR%" ---
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
REM --- �޸Ľ��� ---

IF ERRORLEVEL 1 (
    ECHO [����] PyInstaller ���ʧ�ܡ���������Ĵ�����־��
    PAUSE
    EXIT /B 1
)
ECHO [���� 5/7] PyInstaller ����ɹ���

REM --- [���� 6/7] �ƶ�EXE���������ļ� (���������⻷��) ---
ECHO.
ECHO [���� 6/7] ��ʼ�ƶ� "%EXE_NAME%" ������������ (���������⻷��)...

SET FINAL_EXE_PATH_IN_DIST=%DIST_PATH%\%EXE_NAME%
SET TARGET_EXE_PATH_IN_ROOT=%PROJECT_ROOT%\%EXE_NAME%

IF EXIST "%FINAL_EXE_PATH_IN_DIST%" (
    ECHO [��Ϣ] �ҵ���EXE�ļ�: "%FINAL_EXE_PATH_IN_DIST%"
    ECHO [��Ϣ] ׼���ƶ���: "%TARGET_EXE_PATH_IN_ROOT%"
    MOVE /Y "%FINAL_EXE_PATH_IN_DIST%" "%TARGET_EXE_PATH_IN_ROOT%"
    IF !ERRORLEVEL! EQU 0 (
        ECHO [�ɹ�] "%EXE_NAME%" �ѳɹ��ƶ�����Ŀ��Ŀ¼: "%PROJECT_ROOT%"
    ) ELSE (
        ECHO [����] �ƶ� "%EXE_NAME%" ʧ��! Errorlevel: !ERRORLEVEL!
        ECHO [��ʾ] �ļ��������� "%DIST_PATH%" �У�����Ŀ��·���޷�д�롣
    )
) ELSE (
    ECHO [����] ������EXE�ļ� "%FINAL_EXE_PATH_IN_DIST%" δ�ҵ�! �޷��ƶ���
    ECHO [��ʾ] ����PyInstaller�����Ƿ��д��󣬻����·���Ƿ���ȷ��
)

ECHO [��Ϣ] ��ʼ�����������������в�������ʱ�ļ���Ŀ¼...

IF EXIST "%BUILD_PATH%" (
    ECHO [����] ׼��ɾ������Ŀ¼: "%BUILD_PATH%"
    RMDIR /S /Q "%BUILD_PATH%"
    IF !ERRORLEVEL! EQU 0 (ECHO [�ɹ�] ����Ŀ¼ "%BUILD_PATH%" ��ɾ����) ELSE (ECHO [����] ɾ������Ŀ¼ "%BUILD_PATH%" ʧ��! Errorlevel: !ERRORLEVEL!)
) ELSE (ECHO [��Ϣ] ����Ŀ¼ "%BUILD_PATH%" �����ڣ�����ɾ����)

IF EXIST "%DIST_PATH%" (
    ECHO [����] ׼��ɾ��ԭʼ���Ŀ¼: "%DIST_PATH%"
    RMDIR /S /Q "%DIST_PATH%"
    IF !ERRORLEVEL! EQU 0 (ECHO [�ɹ�] ԭʼ���Ŀ¼ "%DIST_PATH%" ��ɾ����) ELSE (ECHO [����] ɾ��ԭʼ���Ŀ¼ "%DIST_PATH%" ʧ��! Errorlevel: !ERRORLEVEL!)
) ELSE (ECHO [��Ϣ] ԭʼ���Ŀ¼ "%DIST_PATH%" �����ڣ�����ɾ����)

SET SPEC_FILE_TO_DELETE=%SPEC_PATH%\%EXE_NAME%.spec
IF EXIST "%SPEC_FILE_TO_DELETE%" (
    ECHO [����] ׼��ɾ�� .spec �ļ�: "%SPEC_FILE_TO_DELETE%"
    DEL /F /Q "%SPEC_FILE_TO_DELETE%"
    IF !ERRORLEVEL! EQU 0 (ECHO [�ɹ�] .spec �ļ� "%SPEC_FILE_TO_DELETE%" ��ɾ����) ELSE (ECHO [����] ɾ�� .spec �ļ� "%SPEC_FILE_TO_DELETE%" ʧ��! Errorlevel: !ERRORLEVEL!)
) ELSE (ECHO [��Ϣ] .spec �ļ� "%SPEC_FILE_TO_DELETE%" �����ڣ�����ɾ����)

ECHO [���� 6/7] ��Ҫ���������ɡ�

REM --- [���� 7/7] ������������� ---
ECHO.
ECHO [���� 7/7] ������̻���������
IF EXIST "%TARGET_EXE_PATH_IN_ROOT%" (
    ECHO [���ճɹ�] "%EXE_NAME%" �ѳɹ����ɲ��������Ŀ��Ŀ¼:
    ECHO                "%TARGET_EXE_PATH_IN_ROOT%"
) ELSE (
    ECHO [���վ���] "%EXE_NAME%" δ����Ŀ��Ŀ¼�ҵ���
    ECHO [��ʾ] ����ϸ���������־��
    IF EXIST "%FINAL_EXE_PATH_IN_DIST%" (
        ECHO [��ʾ] �ļ������Ա�����ԭʼ���Ŀ¼: "%FINAL_EXE_PATH_IN_DIST%"
    )
)
ECHO.
ECHO �����Լ����Ŀ��Ŀ¼ "%PROJECT_ROOT%" �Ƿ��� "%EXE_NAME%" �ļ���
ECHO.
ECHO ��������󣬽ű�����ɾ�� Python ���⻷�����˳��ű�
PAUSE

REM --- ɾ�����⻷��Ŀ¼ ---
ECHO.
ECHO [��������]ɾ�����⻷��Ŀ¼...
ECHO [��������] Ŀ��Ŀ¼: "%VENV_DIR%"

IF NOT EXIST "%VENV_DIR%" (
    ECHO [��Ϣ] ���⻷��Ŀ¼ "%VENV_DIR%" ����������ǰ�Ѳ����ڡ�
    GOTO FinalExit
)

ECHO [��Ϣ] �ȴ� 5 ��... (���ļ����ͷ�ʱ��)
TIMEOUT /T 5 /NOBREAK >NUL

RMDIR /S /Q "%VENV_DIR%"
SET VENV_DEL_ERRORLEVEL=!ERRORLEVEL!

IF !VENV_DEL_ERRORLEVEL! EQU 0 (
    ECHO [�ɹ�] ���⻷��Ŀ¼ "%VENV_DIR%" �������������гɹ�ɾ����
) ELSE (
    ECHO [����] ɾ�����⻷��Ŀ¼ "%VENV_DIR%" ʧ�ܡ�Errorlevel: !VENV_DEL_ERRORLEVEL!
    ECHO [��ʾ] ��������ΪĳЩ�ļ��Ա�ռ�á������Գ����ֶ�ɾ������
)

:FinalExit
ECHO.
ECHO [��Ϣ] �ű�ִ����ϡ�
ENDLOCAL
EXIT /B 0
