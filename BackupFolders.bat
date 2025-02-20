@echo off
chcp 65001 > nul
title Backup - by Laxe4k

REM Creating necessary variables for the backup
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do (set BackupDate=%%c-%%b-%%a)
SET "TempDir=%temp%\.Backup"
SET compression=9

REM Read the backup folder path from the text file
if exist "BackupDir.txt" (
    set /p BackupDir=<BackupDir.txt
    attrib +h BackupDir.txt
) else (
    goto :changeBackupDir
)

REM Check if 7-Zip is installed, if not, install it
if not exist "%ProgramFiles%\7-Zip\7z.exe" (
    call :install7zip
)

REM Script arguments (to run the backup automatically)
if "%1"=="-auto" (
    SET "auto=true"
    if not exist "%BackupDir%" goto :exit
    goto :backup
) else (
    SET "auto=false"
    goto :menu
)

:menu
if not exist "%BackupDir%" goto :changeBackupDir
cls
color 0a
echo ----------------------------------------------
echo.
echo Backup - by Laxe4k
echo.
echo This script allows you to backup folders.
echo.
echo ----------------------------------------------
echo.
echo Backup folder:
echo.
echo "%BackupDir%"
echo.
echo ----------------------------------------------
echo.
echo Folder to be backed up
echo.
if not exist "Folders.txt" (
    echo No folder to backup.
) else (
    for /f "delims=" %%f in (Folders.txt) do (
        echo %%f
    )
    attrib +h Folders.txt
)
echo.
echo ----------------------------------------------
echo.
echo 7z file compression level: %compression%
echo.
echo ----------------------------------------------
echo.
echo Options:
echo.
echo 1 - Perform a backup
echo 2 - Change the backup folder
echo 3 - Change the compression level
echo 4 - Add folders to backup
echo 5 - Clear the list of folders to backup
echo 6 - Quit
echo.
echo ----------------------------------------------
set /p choix=Your choice: 
if %choix%==1 goto :backup
if %choix%==2 goto :changeBackupDir
if %choix%==3 goto :setCompression
if %choix%==4 goto :addFolders
if %choix%==5 goto :clearFolders
if %choix%==6 goto :exit
goto :menu

:addFolders
cls
color 0e
echo Enter the paths of the folders to backup.
echo Enter "done" to finish.
echo Leave empty to return to the menu.
echo.
echo Example: C:\Users\%username%\Documents
echo.
echo ----------------------------------------------
echo.
echo Folders to backup:
echo.
if not exist "Folders.txt" (
    echo No folder to backup.
) else (
    for /f "delims=" %%f in (Folders.txt) do (
        echo %%f
    )
)
echo.
echo ----------------------------------------------
echo.
set "dir="
set /p "dir=Folder path:"
if "%dir%"=="done" goto :menu
if "%dir%"=="" goto :menu
echo %dir% >> Folders.txt
attrib +h Folders.txt
goto :addFolders

:backup
REM Creating necessary folders for the backup
if exist "%BackupDir%\Backup-%username%_%BackupDate%.7z" (
    cls
    color 0c
    echo A backup has already been performed today.
    timeout /t 5
    exit
)
if exist "%TempDir%\Backup-%username%_%BackupDate%" rmdir /S /Q "%TempDir%\Backup-%username%_%BackupDate%"
if not exist "%TempDir%" mkdir "%TempDir%"
if not exist "%TempDir%\Backup-%username%_%BackupDate%" mkdir "%TempDir%\Backup-%username%_%BackupDate%"

REM Copy files listed in Folders.txt
cls
color 0b
for /f "delims=" %%f in (Folders.txt) do (
    robocopy "%%f" "%TempDir%\Backup-%username%_%BackupDate%\%%~pnxf" /E /Z /R:0 /W:0 /MT:32 /NP
)

REM Compress the folder Backup-%username%_%BackupDate% into 7z
cls
color 0e
echo Compressing the folder Backup-%username%_%BackupDate% into 7z...
echo.
"%ProgramFiles%\7-Zip\7z.exe" a -t7z "%TempDir%\Backup-%username%_%BackupDate%.7z" -r "%TempDir%\Backup-%username%_%BackupDate%" -mx=%compression%
cls
color 0b
echo Moving the 7z file to the backup folder...
move "%TempDir%\Backup-%username%_%BackupDate%.7z" "%BackupDir%"
rmdir /S /Q "%TempDir%\Backup-%username%_%BackupDate%"
cls
color 0a
echo The backup was successful.
timeout 3
exit

:changeBackupDir
cls
color 0e
echo Enter the backup folder path without quotes,
echo you can leave it empty to use the script folder.
echo.
echo Example: C:\Users\%username%\Desktop\Backup
echo.
echo This is where the backups will be stored.
echo.
set /p BackupDir=Backup folder path: 
if "%BackupDir%"==""
(
    set "BackupDir=%~dp0"
)
if not exist "%BackupDir%" (
    color 0c
    echo The backup folder does not exist.
    goto :changeBackupDir
)
echo %BackupDir% > BackupDir.txt
attrib +h BackupDir.txt
color 0a
goto :menu

:setCompression
cls
color 0e
echo Choose the compression level:
echo.
echo 0 - No compression, just store (mx=0)
echo 1 - Very low compression (mx=1)
echo 2 - Low compression (mx=2)
echo 3 - Below average compression (mx=3)
echo 4 - Average compression (mx=4)
echo 5 - Above average compression (mx=5)
echo 6 - High compression (mx=6)
echo 7 - Very high compression (mx=7)
echo 8 - Extreme compression (mx=8)
echo 9 - Maximum (mx=9)
echo.
set /p choix=Your choice: 
set compression=%choix%
goto :menu

:install7zip
cls
color 0e
echo 7-Zip is not installed.
echo.
echo Please wait while 7-Zip is being installed...
echo.
winget install --id 7zip.7zip --exact --source winget --accept-source-agreements --force
if not exist "%ProgramFiles%\7-Zip\7z.exe" (
    cls
    color 0c
    echo 7-Zip installation failed.
    echo.
    echo Please install it manually.
    start https://www.7-zip.org/
    pause
    exit
)
goto :start

:clearFolders
cls
color 0e
echo Clearing the list of folders to backup...
echo.
del Folders.txt
echo The list of folders to backup has been cleared.
timeout 3
goto :menu

:exit
cls
color 0f
echo Closing the script...
timeout /t 5
color 0f & cls
exit
