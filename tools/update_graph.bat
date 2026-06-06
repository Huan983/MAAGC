@echo off
REM 一键重新生成状态机图谱(Windows)
REM 用法: tools\update_graph.bat           生成并打印统计
REM      tools\update_graph.bat --open    生成完自动打开浏览器
REM      tools\update_graph.bat --watch   watch 模式,文件变更自动重生成

setlocal
cd /d "%~dp0\.."
python tools\pipeline_to_mermaid.py %*
endlocal
