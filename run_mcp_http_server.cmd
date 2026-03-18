@echo off
setlocal
cd /d C:\MCP_Server\MyMcpServer-http
if "%NLIC_OC%"=="" (
  echo NLIC_OC environment variable is required.
  exit /b 1
)
set PYTHONUNBUFFERED=1
"C:\Users\orph3\AppData\Local\Programs\Python\Python314\python.exe" -u -m src.mcp_http_server
