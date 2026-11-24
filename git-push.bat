@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM ========== 使用前改这 4 行 ==========
set "GITEE_REPO=https://gitee.com/你的用户名/DeepinOfflineMaker.git"
set "GITHUB_REPO=https://github.com/你的用户名/DeepinOfflineMaker.git"
set "GIT_NAME=你的名字或ID"
set "GIT_EMAIL=你的邮箱@example.com"
REM ======================================

echo.
echo   Gitee : %GITEE_REPO%
echo   GitHub: %GITHUB_REPO%
echo.
echo 说明：
echo   1. 先在 Gitee / GitHub 网页各建一个【空仓库】（不要勾选初始化 README）。
echo   2. 把上面 4 行改成你自己的地址和提交身份，保存后重新双击本文件。
echo   3. 推送时会弹出 Git Credential Manager 窗口，输入账号 + 访问令牌(PAT)。
echo      GitHub 已禁用密码登录，密码栏请粘贴 Personal Access Token。
echo      令牌不会写进本文件，由 Windows 凭据管理器保存。
echo.
pause

if not exist ".git" (
  git init -b main
)

git config user.name "%GIT_NAME%" >nul
git config user.email "%GIT_EMAIL%" >nul
git config credential.helper manager >nul

git remote remove gitee  >nul 2>&1
git remote remove github >nul 2>&1
git remote add gitee  "%GITEE_REPO%"
git remote add github "%GITHUB_REPO%"

git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Import DeepinOfflineMaker"
) else (
  echo 没有新改动，跳过提交。
)

echo.
echo === 1/2 推送 Gitee（国内直连，通常几秒） ===
git -c http.lowSpeedLimit=0 -c http.lowSpeedTime=999999 push gitee HEAD:master
if errorlevel 1 (
  echo [失败] Gitee 推送未成功，请检查仓库地址与令牌。
  goto :end
)

echo.
echo === 2/2 推送 GitHub（直连较慢，失败自动重试 3 次） ===
for /L %%i in (1,1,3) do (
  git -c http.lowSpeedLimit=0 -c http.lowSpeedTime=999999 -c http.postBuffer=524288000 push github HEAD:main
  if not errorlevel 1 goto :github_ok
  echo GitHub 第 %%i 次失败，重试中...
)
echo.
echo [备选方案] GitHub 直连不稳定时，别硬推：
echo   打开 https://github.com/new/import ，填入 Gitee 仓库 URL 导入，
echo   GitHub 服务器去拉 Gitee，比本机 push 快且稳。
goto :end

:github_ok
echo.
echo === 两边都推送成功 ===
git remote -v

:end
echo.
pause
