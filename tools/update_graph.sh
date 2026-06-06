#!/usr/bin/env bash
# 一键重新生成状态机图谱(bash)
# 用法: ./tools/update_graph.sh           生成并打印统计
#      ./tools/update_graph.sh --open    生成完自动打开浏览器
#      ./tools/update_graph.sh --watch   watch 模式,文件变更自动重生成

set -e
cd "$(dirname "$0")/.."
python tools/pipeline_to_mermaid.py "$@"
