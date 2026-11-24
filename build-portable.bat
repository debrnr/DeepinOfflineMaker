@echo off
chcp 65001 >nul
REM 打包「单文件便携版」：一个 exe 走天下，不需要 _internal 附属目录
set PY="D:\DEBRNR_AI\Env\Python\python-version\3146\python.exe"
set ROOT="%~dp0"
set SRC="%~dp0src"
set CACHE="%~dp0src\cache"
set OUT="%~dp0dist_portable"

REM 若上一次的单文件还在，先移走，避免 PyInstaller 删除时触发批量删除保护
if exist "%OUT%\DeepinOfflineMakerPortable.exe" (
  move /Y "%OUT%\DeepinOfflineMakerPortable.exe" "%TEMP%\DOM-portable-old-%RANDOM%.exe" >nul
)

%PY% -m PyInstaller --noconfirm --onefile --windowed ^
  --name "DeepinOfflineMakerPortable" ^
  --distpath %OUT% ^
  --workpath "%~dp0build_portable" ^
  --specpath "%~dp0" ^
  --add-data "%SRC%\assets;assets" ^
  --add-data "%CACHE%\catalog-spark.json;cache" ^
  "%SRC%\app.py"

echo.
if exist "%OUT%\DeepinOfflineMakerPortable.exe" (
  if not exist "%~dp0dist" mkdir "%~dp0dist"
  move /Y "%OUT%\DeepinOfflineMakerPortable.exe" "%~dp0dist\DeepinOfflineMakerPortable.exe" >nul
  echo === 单文件版打包完成 ===
  echo 文件: %~dp0dist\DeepinOfflineMakerPortable.exe
  echo 可直接单独拷贝到任意 Windows 机器使用，无需 _internal 目录。
  echo 注意: 软件目录缓存与项目基线已内置或写到可写数据目录，不会因临时解压目录删除而丢失。
) else (
  echo 打包失败，请查看上方日志
)
pause
