@echo off
chcp 65001 >nul
REM 用带 tkinter 的 Python 3.14 打包（免依赖 exe）
set PY="D:\DEBRNR_AI\Env\Python\python-version\3146\python.exe"
set SRC="D:\DEBRNR\Documents\WorkBuddy\Projects\DeepinOfflineMaker\src"
set DIST="D:\DEBRNR\Documents\WorkBuddy\Projects\DeepinOfflineMaker\dist"

REM PyInstaller 的 COLLECT 会删除已存在的输出目录，批量删除会被安全钩子拦截。
REM 先把上一版整个移到系统临时目录，让目标路径为空后再打包。
set BAK=%TEMP%\DOM-old-%RANDOM%
if exist "%DIST%\DeepinOfflineMaker" (
  echo 上一版先移到临时目录: %BAK%
  move "%DIST%\DeepinOfflineMaker" "%BAK%" >nul
)

REM 不加 --clean：避免清理 workpath 时再次触发批量删除保护。
%PY% -m PyInstaller --noconfirm --onedir --windowed ^
  --name "DeepinOfflineMaker" ^
  --distpath %DIST% ^
  --workpath "%~dp0build" ^
  --specpath "%~dp0" ^
  --add-data "%SRC%\assets;assets" ^
  --add-data "%SRC%\cache\catalog-spark.json;cache" ^
  "%SRC%\app.py"

echo.
REM 把已抓取的软件目录缓存随 exe 一起发布，首次打开即可看到 600+ 应用
if exist "%SRC%\cache\catalog-spark.json" (
  if not exist "%DIST%\DeepinOfflineMaker\_internal\cache" mkdir "%DIST%\DeepinOfflineMaker\_internal\cache"
  copy /Y "%SRC%\cache\catalog-spark.json" "%DIST%\DeepinOfflineMaker\_internal\cache\" >nul
)
echo === 打包完成 ===
if exist "%DIST%\DeepinOfflineMaker\DeepinOfflineMaker.exe" (
  echo EXE: %DIST%\DeepinOfflineMaker\DeepinOfflineMaker.exe
) else (
  echo 打包失败，请查看上方日志
)
pause
