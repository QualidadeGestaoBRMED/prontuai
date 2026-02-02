@echo off
setlocal
set ROOT_DIR=%~dp0..
set BACKEND_DIR=%ROOT_DIR%\back-end
pushd "%BACKEND_DIR%"
docker compose up -d
if errorlevel 1 (
  echo Failed to start containers. Ensure Docker Desktop is running.
  exit /b 1
)
docker compose ps
popd
endlocal
