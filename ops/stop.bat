@echo off
setlocal
set ROOT_DIR=%~dp0..
set BACKEND_DIR=%ROOT_DIR%\back-end
pushd "%BACKEND_DIR%"
docker compose down
popd
endlocal
