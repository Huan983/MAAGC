"""
pipeline-generate ROI Sweep 测试工具。

用法:
    python generate_sweep.py <target_text> <box> [expands]
    python generate_sweep.py "角色" "46,1248,50,30"
    python generate_sweep.py "角色" "46,1248,50,30" 0,5,10,15,20,25,30,50,100

输出:
    在 generate_sweep/<text>_<expands>.json 生成测试 pipeline
    打印每条 expand 的 ROI 范围
    然后用 run_pipeline 逐个测试（手动）
"""

import sys
import json
from pathlib import Path

# 720p 硬编码常量
SCREEN_W, SCREEN_H = 720, 1280

# 项目根目录：脚本位于 .claude/skills/pipeline-generate/
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def parse_expands(arg: str) -> list[int]:
    """解析 '0,5,10,20' 字符串为 [0, 5, 10, 20]"""
    return [int(x.strip()) for x in arg.split(",")]


def parse_box(arg: str) -> tuple[int, int, int, int]:
    """解析 'x,y,w,h' 字符串为 (x, y, w, h) 元组"""
    parts = [int(x.strip()) for x in arg.split(",")]
    if len(parts) != 4:
        raise ValueError(f"box 格式错误: {arg}，应为 'x,y,w,h'")
    return tuple(parts)


def compute_roi(box: tuple[int, int, int, int], expand: int) -> list[int]:
    """计算扩大后的 ROI，限制不超出屏幕边界"""
    x, y, w, h = box
    roi_x = max(0, x - expand)
    roi_y = max(0, y - expand)
    roi_w = min(SCREEN_W - roi_x, w + 2 * expand)
    roi_h = min(SCREEN_H - roi_y, h + 2 * expand)
    return [roi_x, roi_y, roi_w, roi_h]


def make_sweep_pipeline(
    target_text: str,
    box: tuple[int, int, int, int],
    expands: list[int],
    output_path: str,
) -> dict:
    """生成 ROI sweep 测试 pipeline"""
    nodes = {}
    for e in expands:
        roi = compute_roi(box, e)
        node_name = f"Sweep_{target_text}_e{e}"
        nodes[node_name] = {
            "recognition": "OCR",
            "expected": [target_text],
            "roi": roi,
            "action": "DoNothing",  # 只测识别，不点
            "post_delay": 100,
            "timeout": 2000,
        }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)
    return nodes


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    target_text = sys.argv[1]
    box = parse_box(sys.argv[2])
    expands = parse_expands(sys.argv[3]) if len(sys.argv) > 3 else [0, 5, 10, 15, 20, 25, 30, 50, 100]

    output_dir = PROJECT_ROOT / "generate_sweep"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{target_text}.json"

    nodes = make_sweep_pipeline(target_text, box, expands, str(output_path))

    print(f"生成 sweep pipeline: {output_path}")
    print(f"目标文字: {target_text}")
    print(f"原始 box: {box}")
    print(f"测试 expand: {expands}")
    print()
    print("ROI 范围预览:")
    for name, node in nodes.items():
        print(f"  {name}: roi={node['roi']}")

    print()
    print("=" * 60)
    print("下一步: 用 run_pipeline 逐个测试 (action: DoNothing)")
    print(f"  run_pipeline(pipeline_path='{output_path}', entry='Sweep_{target_text}_e20', ...)")
    print()
    print("测试后选最佳 expand, 然后从项目根目录运行:")
    print(f"  python .claude/skills/pipeline-generate/generate_node.py \"{target_text}\" <NodeName> <target_pipeline> --expand <best> --overwrite")


if __name__ == "__main__":
    main()
