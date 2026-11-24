@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "GITEE_REPO=https://gitee.com/debrnr/deepin-offline-maker.git"
set "GITHUB_REPO=https://github.com/debrnr/DeepinOfflineMaker.git"

echo.
echo   Gitee : %GITEE_REPO%
echo   GitHub: %GITHUB_REPO%
echo.
echo 说明：
echo   1. 凭据由 Windows 凭据管理器(GCM)保存，本文件不含任何令牌。
echo   2. Gitee 国内直连；GitHub 若 git 直连被代理阻断，会自动改走 api.github.com。
echo.
pause

if not exist ".git" (
  git init -b main
)

git config credential.helper manager >nul
git config user.name  >nul 2>&1
if errorlevel 1 git config user.name "debrnr"
git config user.email >nul 2>&1
if errorlevel 1 git config user.email "debrnr@users.noreply.github.com"

git remote remove gitee  >nul 2>&1
git remote remove github >nul 2>&1
git remote add gitee  "%GITEE_REPO%"
git remote add github "%GITHUB_REPO%"

git add -A
git diff --cached --quiet
if errorlevel 1 (
  git -c user.name="debrnr" -c user.email="debrnr@users.noreply.github.com" commit -m "Update DeepinOfflineMaker"
) else (
  echo 没有新改动，跳过提交。
)

echo.
echo === 1/2 推送 Gitee（国内直连，通常几秒） ===
git -c http.version=HTTP/1.1 -c http.postBuffer=524288000 push gitee HEAD:main
if errorlevel 1 (
  echo [失败] Gitee 推送未成功，请检查仓库地址与令牌。
  goto :end
)

echo.
echo === 2/2 推送 GitHub（直连失败则自动走 api.github.com） ===
git -c http.version=HTTP/1.1 -c http.postBuffer=524288000 push github HEAD:main
if not errorlevel 1 goto :github_ok
echo.
echo GitHub git 直连被代理阻断，改用 REST API 通道...
python "tools\push_github_api.py"
if errorlevel 1 (
  echo [失败] GitHub API 同步未成功。
  goto :end
)

:github_ok
echo.
echo === 两端同步完成 ===
git remote -v

:end
echo.
pause
