@echo off
echo ======================================
echo  Build BackupFolders.exe
echo ======================================
echo.

REM Install pyinstaller if needed
pip install pyinstaller

echo.
echo Building executable...
echo.

python -m PyInstaller --onefile --windowed --name BackupFolders --clean BackupFolders.py

echo.
echo ======================================
if exist "dist\BackupFolders.exe" (
  echo Build OK ! L'executable se trouve dans dist\BackupFolders.exe
  ) else (
  echo Erreur lors du build.
)
echo ======================================
pause
