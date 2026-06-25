@echo off
cd /d "%~dp0"
set NODE_PATH=node_modules
set CI=true
node "node_modules/.pnpm/vite@5.4.21_@types+node@25.9.3/node_modules/vite/bin/vite.js" build
echo Exit code: %ERRORLEVEL%
pause
