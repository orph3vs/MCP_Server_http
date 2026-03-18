@echo off
setlocal
cd /d C:\MCP_Server\MyMcpServer-http
set PYTHONUNBUFFERED=1
"C:\Users\orph3\AppData\Local\Programs\Python\Python314\python.exe" -u -m src.mcp_stdio_server
