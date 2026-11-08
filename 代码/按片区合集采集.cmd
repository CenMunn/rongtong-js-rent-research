@echo off
setlocal
cd /d "%~dp0"
if not exist ".wechat-venv\Scripts\python.exe" (
  py -m venv .wechat-venv || goto done
)
".wechat-venv\Scripts\python.exe" -c "import bs4,requests,playwright,lxml,PIL,rapidocr_onnxruntime,pymupdf" >nul 2>&1
if errorlevel 1 (
  ".wechat-venv\Scripts\python.exe" -m pip install requests beautifulsoup4 playwright lxml pillow pymupdf "rapidocr-onnxruntime==1.2.3" || goto done
)
".wechat-venv\Scripts\python.exe" wechat_album.py
:done
pause
