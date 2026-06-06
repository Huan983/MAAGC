"""
MaaGC Pipeline 关系图谱生成器 v2

四个产物:
  1. pipeline_overview.html            总览: 5 入口 → 13 文件 → 244 节点
  2. pipeline_external_entries.html    Python → Pipeline 调用图
  3. pipeline_utility_usage.html       工具节点被谁调用
  4. <file>.html x13                   每个 Pipeline 文件的细节图

边类型 (4 种):
  - interface-task   用户级入口 → Pipeline 节点      实线箭头 -->
  - python-call      Python 函数 → Pipeline 节点      实线箭头 -->
  - next             状态机转移                       实线箭头 -->
  - jumpback         子例程调用(执行后返回调用方)        粗箭头 ==>

节点形状 (4 种):
  - 外部入口     id([name])      Stadium(药片)
  - 普通节点     id[name]        Rectangle
  - 工具节点     id((name))      Circle(双圆)
  - 终止节点     id>name]        Parallelogram(平行四边形)
"""
from __future__ import annotations

import ast
import json
import re
import sys
import time
import webbrowser
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Windows 终端默认 GBK,emoji 打印会爆。强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# ----------------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = REPO_ROOT / "assets" / "resource" / "pipeline" / "base"
INTERFACE_JSON = REPO_ROOT / "assets" / "interface.json"
AGENT_DIR = REPO_ROOT / "agent"
OUT_DIR = REPO_ROOT / "docs" / "zh_cn" / "graph"   # 全部 HTML 产物放这里(已被 .gitignore)

# 兜底:用户工程可能用 resource/base 或 pipeline/base 任一路径
if not PIPELINE_DIR.exists():
    alt = REPO_ROOT / "assets" / "resource" / "base" / "pipeline"
    if alt.exists():
        PIPELINE_DIR = alt

# 工具节点(标准库级别,被反复调用,应该画在不同位置)
UTILITY_NODES: frozenset[str] = frozenset({
    "BackButton_500ms",
    "BackButton_DirectHit",
    "ClickCenter_500ms",
    "PopUpWindowTip",
    "PopUpWindowsTipConfirm",
    "PopUpWindowConfirm",
    "PopUpWindowCancel",
    "UI_PopInform",
    "UI_ReturnBigMap",
    "UI_TaskPannelPageOpen",
    "UI_TaskPannelPageClose",
})

# 节点/边配色
COLORS = {
    "interface": "#f4d03f",     # 金黄 - 用户级入口
    "external": "#e67e22",      # 橙 - 内部 Python 调用入口
    "utility": "#bb8fce",       # 紫 - 工具节点
    "normal": "#aed6f1",        # 蓝 - 普通节点
    "leaf": "#d5dbdb",          # 灰 - 终止节点
    "next_edge": "#34495e",     # 深蓝灰
    "jumpback_edge": "#c0392b", # 红
    "py_edge": "#16a085",       # 绿
    "iface_edge": "#7d6608",    # 暗金
}

# 文档首页说明
DOC_INTRO = """
> **这是 MaaGC 的 Pipeline 关系图谱 v2**。由 `tools/pipeline_to_mermaid.py` 自动生成。
>
> **图例**:
> - 🟡 金黄 Stadium = `interface.json` 暴露的用户级入口
> - 🟠 橙 Stadium = Python `context.run_task()` 调用入口
> - 🟣 紫 Circle = 工具节点(BackButton / ClickCenter / PopUp*)
> - 🔵 蓝 Rectangle = 普通子流程节点
> - ⚪ 灰 Parallelogram = 终止状态(无 next)
>
> **边类型**:
> - ───> 细实线 = 状态机转移 `next` / Python 调用
> - ═══> 粗红线 = 子例程调用 `[JumpBack]`(执行完返回调用方)
"""


# ----------------------------------------------------------------------------
# 数据结构(不可变)
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Node:
    file: str
    name: str
    spec: dict[str, Any]

    @property
    def recognition(self) -> str:
        return self.spec.get("recognition", "-")

    @property
    def action(self) -> str:
        return self.spec.get("action", "-")

    @property
    def has_next(self) -> bool:
        return "next" in self.spec


@dataclass(frozen=True)
class Edge:
    src_file: str   # "__py__" 表示 Python 调用方
    src_name: str
    dst_file: str   # Pipeline 文件名
    dst_name: str
    kind: str       # "next" | "jumpback" | "python-call" | "interface-task"
    src_class: str = ""   # 仅 python-call 用
    src_method: str = ""  # 仅 python-call 用


# ----------------------------------------------------------------------------
# JSON 解析辅助
# ----------------------------------------------------------------------------
def _strip_jsonc_comments(text: str) -> str:
    """MaaFramework 允许 JSON5 风格的 // 注释,这里剥掉再交给 stdlib json。"""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    quote = ""
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _load_jsonc(path: Path) -> dict[str, Any]:
    return json.loads(_strip_jsonc_comments(path.read_text(encoding="utf-8")))


# ----------------------------------------------------------------------------
# Pipeline 解析
# ----------------------------------------------------------------------------
def _normalize_next(nxt: Any) -> list[tuple[str, bool]]:
    """把 next 字段标准化为 [(target, is_jumpback), ...]"""
    if nxt is None:
        return []
    if isinstance(nxt, str):
        nxt = [nxt]
    if not isinstance(nxt, list):
        return []
    out: list[tuple[str, bool]] = []
    for x in nxt:
        if not isinstance(x, str):
            continue
        if x.startswith("[JumpBack]"):
            out.append((x[len("[JumpBack]"):], True))
        else:
            out.append((x, False))
    return out


def load_pipeline() -> tuple[dict[str, dict[str, Node]], list[Edge]]:
    """加载所有 Pipeline JSON,返回 (file -> name -> Node), edges。

    两遍解析:
      1) 扫所有文件,建立 name -> file 索引
      2) 再扫一次,根据索引解析 next 目标
    """
    # Pass 1: 解析所有节点,建立全局 name → file 索引
    raw: dict[str, dict[str, Any]] = {}
    nodes: dict[str, dict[str, Node]] = defaultdict(dict)
    all_names: dict[str, str] = {}

    for json_path in sorted(PIPELINE_DIR.glob("*.json")):
        file_key = json_path.stem
        try:
            data = _load_jsonc(json_path)
        except json.JSONDecodeError as e:
            print(f"[WARN] {json_path} parse failed: {e}")
            continue
        raw[file_key] = data
        for name, spec in data.items():
            if not isinstance(spec, dict):
                continue
            nodes[file_key][name] = Node(file=file_key, name=name, spec=spec)
            all_names.setdefault(name, file_key)

    # Pass 2: 解析 next 边(此时 all_names 已完整)
    edges: list[Edge] = []
    for file_key, data in raw.items():
        for name, spec in data.items():
            if not isinstance(spec, dict):
                continue
            for target, is_jb in _normalize_next(spec.get("next")):
                if target in nodes[file_key]:
                    dst_file = file_key
                elif target in all_names:
                    dst_file = all_names[target]
                else:
                    continue  # 真正的悬挂引用
                edges.append(Edge(
                    src_file=file_key, src_name=name,
                    dst_file=dst_file, dst_name=target,
                    kind="jumpback" if is_jb else "next",
                ))

    return dict(nodes), edges


# ----------------------------------------------------------------------------
# Python 源码扫描
# ----------------------------------------------------------------------------
def _safe_attr_chain(node: ast.AST) -> str:
    """ast.Attribute 链 → 'context.tasker.controller'"""
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def scan_python_calls() -> list[Edge]:
    """扫 agent/*.py 下所有 context.run_task("X") 调用,带类/方法归属。"""
    edges: list[Edge] = []
    for py in sorted(AGENT_DIR.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            for method in [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                for sub in ast.walk(method):
                    if not isinstance(sub, ast.Call):
                        continue
                    # 形如 context.run_task("X")
                    if isinstance(sub.func, ast.Attribute) and sub.func.attr == "run_task":
                        if sub.args and isinstance(sub.args[0], ast.Constant) and isinstance(sub.args[0].value, str):
                            task_name = sub.args[0].value
                            edges.append(Edge(
                                src_file="__py__",
                                src_name=f"{cls.name}.{method.name}",
                                dst_file="__unknown__",  # 后处理填充
                                dst_name=task_name,
                                kind="python-call",
                                src_class=cls.name,
                                src_method=method.name,
                            ))
    return edges


# ----------------------------------------------------------------------------
# interface.json 解析
# ----------------------------------------------------------------------------
def scan_interface_tasks() -> list[Edge]:
    """读 assets/interface.json 的 task[].entry,作为用户级入口。"""
    if not INTERFACE_JSON.exists():
        return []
    data = json.loads(INTERFACE_JSON.read_text(encoding="utf-8"))
    edges: list[Edge] = []
    for t in data.get("task", []):
        entry = t.get("entry")
        if not entry:
            continue
        edges.append(Edge(
            src_file="__interface__",
            src_name=f"📲 {t.get('name', entry)}",
            dst_file="__unknown__",
            dst_name=entry,
            kind="interface-task",
        ))
    return edges


# ----------------------------------------------------------------------------
# 工具:resolve dst_file
# ----------------------------------------------------------------------------
def resolve_destinations(edges: list[Edge], nodes: dict[str, dict[str, Node]]) -> list[Edge]:
    """把 dst_file='__unknown__' 的边按 name 在 nodes 里查表填上。"""
    lookup: dict[str, str] = {}
    for f, ns in nodes.items():
        for n in ns:
            lookup.setdefault(n, f)
    resolved: list[Edge] = []
    for e in edges:
        if e.dst_file == "__unknown__":
            df = lookup.get(e.dst_name)
            if df is None:
                continue  # 指向不存在的节点
            resolved.append(Edge(
                src_file=e.src_file, src_name=e.src_name,
                dst_file=df, dst_name=e.dst_name,
                kind=e.kind,
                src_class=e.src_class, src_method=e.src_method,
            ))
        else:
            resolved.append(e)
    return resolved


# ----------------------------------------------------------------------------
# 统计
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Stats:
    files: int
    nodes: int
    edges_next: int
    edges_jumpback: int
    edges_python: int
    edges_interface: int
    utility_nodes: int
    external_entry_nodes: frozenset[str]


def compute_stats(
    nodes: dict[str, dict[str, Node]],
    edges: list[Edge],
) -> Stats:
    by_kind: dict[str, int] = defaultdict(int)
    for e in edges:
        by_kind[e.kind] += 1
    util = frozenset(n.name for ns in nodes.values() for n in ns.values()
                     if n.name in UTILITY_NODES)
    ext = frozenset(e.dst_name for e in edges if e.kind in ("python-call", "interface-task"))
    return Stats(
        files=len(nodes),
        nodes=sum(len(ns) for ns in nodes.values()),
        edges_next=by_kind["next"],
        edges_jumpback=by_kind["jumpback"],
        edges_python=by_kind["python-call"],
        edges_interface=by_kind["interface-task"],
        utility_nodes=len(util),
        external_entry_nodes=ext,
    )


# ----------------------------------------------------------------------------
# Mermaid 节点 ID
# ----------------------------------------------------------------------------
def _id_hash(file: str, name: str) -> str:
    """中文 / emoji 转 ASCII 后,追加 4 位 hash 防止重名。"""
    h = hash((file, name)) & 0xFFFF
    return f"{h:04x}"


def mid(file: str, name: str) -> str:
    """生成 Mermaid 安全且唯一的 ID。"""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", f"{file}__{name}")[:50]
    return f"{safe}_{_id_hash(file, name)}"


def mermaid_id_safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s)[:60]


# ----------------------------------------------------------------------------
# 边分类
# ----------------------------------------------------------------------------
def categorize_nodes(
    nodes: dict[str, dict[str, Node]],
    external_entry_names: frozenset[str] = frozenset(),
) -> dict[str, set[str]]:
    """返回:
        - utility: 工具节点名集合
        - external: 外部入口(被 Python 或 interface.json 调用的节点)
        - leaf: 终止状态(有 recog/action 但无 next,且不是外部入口)
        - normal: 其余
    """
    cat: dict[str, set[str]] = {
        "utility": {n.name for ns in nodes.values() for n in ns.values() if n.name in UTILITY_NODES},
        "external": set(external_entry_names),
        "leaf": {
            n.name for ns in nodes.values() for n in ns.values()
            if not n.has_next
            and n.name not in UTILITY_NODES
            and n.name not in external_entry_names
        },
    }
    return cat


# ----------------------------------------------------------------------------
# 图 1: 总览 (stateDiagram-v2)
# ----------------------------------------------------------------------------
def _safe_state_id(name: str) -> str:
    """stateDiagram-v2 不允许空格/点/中文,转成 ASCII 别名。"""
    s = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not s or not s[0].isalpha():
        s = "s_" + s
    return s[:50]


def build_state_overview(
    nodes: dict[str, dict[str, Node]],
    edges: list[Edge],
    stats: Stats,
) -> str:
    """用 stateDiagram-v2 渲染总览:复合状态按文件分组。"""
    iface_names = frozenset(e.dst_name for e in edges if e.kind == "interface-task")
    py_names = frozenset(e.dst_name for e in edges if e.kind == "python-call")
    external = iface_names | py_names
    cat = categorize_nodes(nodes, external)

    lines: list[str] = ["stateDiagram-v2"]
    lines.append("    direction LR")
    lines.append("")
    lines.append("    %% ===== 用户级入口 =====")
    lines.append("    state User_Entry {")
    lines.append("        direction LR")
    lines.append("        [*] --> User_Click")
    lines.append("        User_Click: 用户在 MaaPiCli 点击任务")
    lines.append("    }")

    lines.append("")
    lines.append("    %% ===== Pipeline 文件:每个文件是一个复合状态 =====")
    file_alias: dict[str, str] = {}
    for fname in sorted(nodes.keys()):
        if not nodes[fname]:
            continue
        alias = _safe_state_id(f"f_{fname}")
        file_alias[fname] = alias
        lines.append(f"    state \"{fname}.json\" as {alias} {{")
        lines.append("        direction LR")
        # 节点定义
        for n in sorted(nodes[fname].values(), key=lambda x: x.name):
            sid = _safe_state_id(n.name)
            label = n.name.replace('"', "'")
            if n.name in cat["utility"]:
                lines.append(f"        {sid} : {label} (utility)")
            elif n.name in cat["external"]:
                lines.append(f"        {sid} : {label} (entry)")
            else:
                lines.append(f"        {sid} : {label}")
        # 内部 next 转移
        for e in edges:
            if e.kind == "next" and e.src_file == fname and e.dst_file == fname:
                s = _safe_state_id(e.src_name)
                d = _safe_state_id(e.dst_name)
                lines.append(f"        {s} --> {d}")
        # 内部 JumpBack 转移(标 "calls"/"returns")
        for e in edges:
            if e.kind == "jumpback" and e.src_file == fname and e.dst_file == fname:
                s = _safe_state_id(e.src_name)
                d = _safe_state_id(e.dst_name)
                lines.append(f"        {s} --> {d} : calls")
                lines.append(f"        {d} --> {s} : returns")
        # 初始状态:文件内无入边的节点
        incoming = {e.dst_name for e in edges
                    if e.kind == "next" and e.dst_file == fname
                    and (e.src_file == fname or e.src_file != fname)}
        for n in nodes[fname].values():
            sid = _safe_state_id(n.name)
            if n.name in incoming:
                continue  # 已被其他节点转移进来
            if n.name in cat["utility"]:
                continue
            # 标记为初始候选
            lines.append(f"        [*] --> {sid}")
        # 终止状态:无 next
        for n in nodes[fname].values():
            sid = _safe_state_id(n.name)
            if n.has_next:
                continue
            if n.name in cat["utility"]:
                continue
            lines.append(f"        {sid} --> [*]")
        lines.append("    }")

    lines.append("")
    lines.append("    %% ===== 文件间转移 (next 跨文件) =====")
    for e in edges:
        if e.kind == "next" and e.src_file != e.dst_file:
            src_alias = _safe_state_id(e.src_name)
            dst_alias = _safe_state_id(e.dst_name)
            src_compound = f"{file_alias[e.src_file]}.{src_alias}"
            dst_compound = f"{file_alias[e.dst_file]}.{dst_alias}"
            lines.append(f"    {src_compound} --> {dst_compound}")

    lines.append("")
    lines.append("    %% ===== Python 入口触发 =====")
    py_aliases: set[str] = set()
    for e in edges:
        if e.kind == "python-call":
            dst_alias = _safe_state_id(e.dst_name)
            dst_compound = f"{file_alias.get(e.dst_file, '')}.{dst_alias}"
            label = f"🐍 {e.src_name}".replace('"', "'")[:60]
            py_aliases.add(label)
            lines.append(f"    User_Click --> {dst_compound} : {label}")

    lines.append("")
    lines.append("    %% ===== interface 入口触发 =====")
    for e in edges:
        if e.kind == "interface-task":
            dst_alias = _safe_state_id(e.dst_name)
            dst_compound = f"{file_alias.get(e.dst_file, '')}.{dst_alias}"
            label = f"📲 {e.src_name}".replace('"', "'")[:60]
            lines.append(f"    User_Click --> {dst_compound} : {label}")

    lines.append("")
    lines.append("    %% ===== 样式 =====")
    lines.append("    classDef user fill:" + COLORS["interface"] + ",stroke:#7d6608,color:#000")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# 图 1 兼容 (flowchart 版本, 保留)
# ----------------------------------------------------------------------------
def build_overview(
    nodes: dict[str, dict[str, Node]],
    edges: list[Edge],
    stats: Stats,
) -> str:
    iface_names = frozenset(e.dst_name for e in edges if e.kind == "interface-task")
    py_names = frozenset(e.dst_name for e in edges if e.kind == "python-call")
    external = iface_names | py_names
    py_only = py_names - iface_names
    cat = categorize_nodes(nodes, external)

    lines: list[str] = ["flowchart LR"]

    # 1) 用户级入口(interface.json)
    lines.append('    %% ===== 用户级入口 =====')
    lines.append('    subgraph iface_grp["📲 interface.json 暴露的入口"]')
    lines.append("        direction LR")
    for e in edges:
        if e.kind == "interface-task":
            iid = mid("iface", e.src_name)
            esc = e.src_name.replace('"', "'")
            lines.append(f'        {iid}(["{esc}"]):::iface')
    lines.append("    end")

    # 2) Python 内部入口不在子图里重复画
    if py_only:
        lines.append('    %% ===== 外部入口说明 =====')
        lines.append(f'    note_for_py["🐍 共 {len(py_only)} 个节点被 Python `context.run_task()` 调用"]:::note')
        lines.append("    classDef note fill:#fef9e7,stroke:#7d6608,color:#000,font-style:italic")

    # 3) 工具节点
    lines.append('    %% ===== 工具节点 =====')
    lines.append('    subgraph util["🟣 工具节点(标准库级别)"]')
    lines.append("        direction TB")
    for fname in sorted(nodes.keys()):
        for n in nodes[fname].values():
            if n.name in cat["utility"]:
                nid = mid(n.file, n.name)
                lbl = n.name.replace('"', "'")
                lines.append(f'        {nid}(("{lbl}")):::util')
    lines.append("    end")

    # 4) 各 Pipeline 文件
    lines.append("    %% ===== 各 Pipeline 文件 =====")
    for fname in sorted(nodes.keys()):
        if not nodes[fname]:
            continue
        lines.append(f'    subgraph {mermaid_id_safe(fname)}["📁 {fname}.json"]')
        lines.append("        direction TB")
        for n in sorted(nodes[fname].values(), key=lambda x: x.name):
            nid = mid(n.file, n.name)
            lbl = n.name.replace('"', "'")
            if n.name in cat["utility"]:
                continue
            if n.name in cat["external"]:
                lines.append(f'        {nid}(["{lbl}"]):::pyent')
                continue
            if n.name in cat["leaf"]:
                lines.append(f'        {nid}[/"{lbl}"/]:::leaf')
                continue
            lines.append(f'        {nid}["{lbl}"]:::normal')
        lines.append("    end")

    # 5) 边
    lines.append("    %% ===== 边 =====")
    seen_iface: set[tuple[str, str]] = set()
    for e in edges:
        if e.kind == "interface-task":
            k = (e.src_name, e.dst_name)
            if k in seen_iface:
                continue
            seen_iface.add(k)
            iid = mid("iface", e.src_name)
            did = mid(e.dst_file, e.dst_name)
            lines.append(f"    {iid} ==> {did}")

    for e in edges:
        if e.kind != "next":
            continue
        s = mid(e.src_file, e.src_name)
        d = mid(e.dst_file, e.dst_name)
        if s == d:
            continue
        lines.append(f"    {s} --> {d}")

    for e in edges:
        if e.kind != "jumpback":
            continue
        s = mid(e.src_file, e.src_name)
        d = mid(e.dst_file, e.dst_name)
        if s == d:
            continue
        lines.append(f"    {s} ==> {d}")

    lines.append("    classDef iface fill:" + COLORS["interface"] + ",stroke:#7d6608,color:#000")
    lines.append("    classDef pyent fill:" + COLORS["external"] + ",stroke:#a04000,color:#000")
    lines.append("    classDef util fill:" + COLORS["utility"] + ",stroke:#5b2c6f,color:#000")
    lines.append("    classDef normal fill:" + COLORS["normal"] + ",stroke:#1f618d,color:#000")
    lines.append("    classDef leaf fill:" + COLORS["leaf"] + ",stroke:#566573,color:#000")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# 图 2: 外部入口图 (Python 函数 → Pipeline 节点)
# ----------------------------------------------------------------------------
def build_external_entries(edges: list[Edge]) -> str:
    py_edges = [e for e in edges if e.kind == "python-call"]
    if not py_edges:
        return "flowchart LR\n    empty([无 Python 外部调用]):::normal"

    # 按 Python 方法分组
    by_method: dict[str, list[Edge]] = defaultdict(list)
    for e in py_edges:
        by_method[e.src_name].append(e)

    # 按 Pipeline 目标文件分组
    by_target: dict[str, set[str]] = defaultdict(set)
    for e in py_edges:
        by_target[e.dst_file].add(e.dst_name)

    lines: list[str] = ["flowchart LR"]
    lines.append("    %% ===== Python 侧 =====")
    lines.append('    subgraph py["🐍 Python 调度层 (agent/)"]')
    lines.append("        direction TB")
    method_ids: dict[str, str] = {}
    for m in sorted(by_method.keys()):
        m_id = mermaid_id_safe(f"py_{m}")
        method_ids[m] = m_id
        # 把 "Class.method" 拆两行
        if "." in m:
            cls, meth = m.split(".", 1)
            esc = f"{cls}<br/><sub>.{meth}()</sub>".replace('"', "'")
        else:
            esc = m.replace('"', "'")
        lines.append(f'        {m_id}["{esc}"]:::py')
    lines.append("    end")

    lines.append("    %% ===== Pipeline 侧 =====")
    for f in sorted(by_target.keys()):
        f_id = mermaid_id_safe(f)
        lines.append(f'    subgraph {f_id}["📁 {f}.json"]')
        lines.append("        direction TB")
        for n in sorted(by_target[f]):
            n_id = mid(f, n)
            label = n.replace('"', "'")
            lines.append(f'        {n_id}["{label}"]:::normal')
        lines.append("    end")

    lines.append("    %% ===== 调用边 =====")
    for e in py_edges:
        m_id = method_ids[e.src_name]
        n_id = mid(e.dst_file, e.dst_name)
        lines.append(f"    {m_id} -- run_task --> {n_id}")

    lines.append("    classDef py fill:" + COLORS["external"] + ",stroke:#a04000,color:#000")
    lines.append("    classDef normal fill:" + COLORS["normal"] + ",stroke:#1f618d,color:#000")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# 图 3: 工具节点使用图
# ----------------------------------------------------------------------------
def build_utility_usage(edges: list[Edge]) -> str:
    cat = categorize_nodes({})  # just to get the structure
    util_set = UTILITY_NODES

    # 谁在 next 指向工具 / 谁通过 Python 调用工具
    callers_of_util: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for e in edges:
        if e.dst_name in util_set:
            kind = "🐍 py" if e.kind == "python-call" else "next"
            callers_of_util[e.dst_name].append((e.src_file, e.src_name, kind))

    lines: list[str] = ["flowchart LR"]
    lines.append("    %% ===== 工具节点(中心) =====")
    lines.append('    subgraph util["🟣 工具节点"]')
    lines.append("        direction TB")
    util_ids: dict[str, str] = {}
    for u in sorted(util_set):
        uid = mid("util", u)
        util_ids[u] = uid
        lbl = u.replace('"', "'")
        lines.append(f'        {uid}(("{lbl}")):::util')
    lines.append("    end")

    # 调用方(去重)
    seen: set[tuple[str, str, str, str]] = set()
    for util_name, callers in callers_of_util.items():
        # 按 src_name 聚合
        by_src: dict[tuple[str, str], set[str]] = defaultdict(set)
        for sf, sn, kind in callers:
            by_src[(sf, sn)].add(kind)
        for (sf, sn), kinds in by_src.items():
            k = (util_name, sf, sn, ",".join(sorted(kinds)))
            if k in seen:
                continue
            seen.add(k)
            caller_id = mid(sf, sn)
            util_id = util_ids[util_name]
            tag = "+".join("py" if "🐍" in kk else "next" for kk in kinds)
            lines.append(f'    {caller_id} =={tag}==> {util_id}')

    # utility 之间相互调用
    for e in edges:
        if e.src_name in util_set and e.dst_name in util_set:
            lines.append(f"    {util_ids[e.src_name]} --> {util_ids[e.dst_name]}")

    lines.append("    classDef util fill:" + COLORS["utility"] + ",stroke:#5b2c6f,color:#000")
    lines.append("    classDef normal fill:" + COLORS["normal"] + ",stroke:#1f618d,color:#000")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# 图 4: 单文件细节 (stateDiagram-v2)
# ----------------------------------------------------------------------------
def build_state_per_file(
    file: str,
    nodes: dict[str, Node],
    edges: list[Edge],
    external_names: frozenset[str] = frozenset(),
) -> str:
    """单个 Pipeline 文件的真·状态机(stateDiagram-v2)。"""
    cat = categorize_nodes({file: nodes}, external_names)

    lines: list[str] = ["stateDiagram-v2"]
    lines.append("    direction LR")
    lines.append(f"    state \"{file}.json 状态机\" as root {{")
    lines.append("        direction LR")

    # 节点定义(state 名称带描述)
    for n in sorted(nodes.values(), key=lambda x: x.name):
        sid = _safe_state_id(n.name)
        if n.name in cat["utility"]:
            lines.append(f"        {sid} : {n.name} (utility)")
        elif n.name in cat["external"]:
            lines.append(f"        {sid} : {n.name} (entry)")
        else:
            lines.append(f"        {sid} : {n.name}")

    # 内部 next 转移
    for e in edges:
        if e.kind == "next" and e.src_file == file and e.dst_file == file:
            s = _safe_state_id(e.src_name)
            d = _safe_state_id(e.dst_name)
            lines.append(f"        {s} --> {d}")

    # 内部 JumpBack:用 calls/returns 显式表达栈语义
    for e in edges:
        if e.kind == "jumpback" and e.src_file == file and e.dst_file == file:
            s = _safe_state_id(e.src_name)
            d = _safe_state_id(e.dst_name)
            lines.append(f"        {s} --> {d} : calls")
            lines.append(f"        {d} --> {s} : returns")

    # 跨文件 next 出边
    for e in edges:
        if e.kind == "next" and e.src_file == file and e.dst_file != file:
            s = _safe_state_id(e.src_name)
            d = _safe_state_id(e.dst_name)
            lines.append(f"        {s} --> {d} : → {e.dst_file}")

    # 跨文件 JumpBack 出边
    for e in edges:
        if e.kind == "jumpback" and e.src_file == file and e.dst_file != file:
            s = _safe_state_id(e.src_name)
            d = _safe_state_id(e.dst_name)
            lines.append(f"        {s} --> {d} : calls ({e.dst_file})")
            lines.append(f"        {d} --> {s} : returns ({e.dst_file})")

    # 跨文件 next 入边
    for e in edges:
        if e.kind == "next" and e.dst_file == file and e.src_file != file:
            s = _safe_state_id(e.src_name)
            d = _safe_state_id(e.dst_name)
            lines.append(f"        {s} --> {d} : ← {e.src_file}")

    # 跨文件 JumpBack 入边
    for e in edges:
        if e.kind == "jumpback" and e.dst_file == file and e.src_file != file:
            s = _safe_state_id(e.src_name)
            d = _safe_state_id(e.dst_name)
            lines.append(f"        {s} --> {d} : returns ({e.src_file})")

    # 初始 / 终止
    incoming_internal = {e.dst_name for e in edges
                        if e.kind in ("next", "jumpback")
                        and e.dst_file == file
                        and e.src_file == file}
    for n in nodes.values():
        sid = _safe_state_id(n.name)
        if n.name in cat["utility"]:
            continue
        if n.name not in incoming_internal:
            # 还要排除被跨文件 next 跳过的(那些有外部入边)
            if any(e.dst_name == n.name and e.dst_file == file and e.src_file != file and e.kind in ("next", "jumpback")
                   for e in edges):
                continue
            lines.append(f"        [*] --> {sid}")

    for n in nodes.values():
        sid = _safe_state_id(n.name)
        if n.has_next:
            continue
        if n.name in cat["utility"]:
            continue
        lines.append(f"        {sid} --> [*]")

    lines.append("    }")
    return "\n".join(lines)


def build_per_file(file: str, nodes: dict[str, Node], edges: list[Edge]) -> str:
    """flowchart 版本(保留)。"""
    cat = categorize_nodes({file: nodes})
    lines: list[str] = ["flowchart LR"]
    lines.append(f"    %% ===== {file}.json =====")
    for n in sorted(nodes.values(), key=lambda x: x.name):
        nid = mid(n.file, n.name)
        lbl = f"{n.name}<br/><sub>{n.recognition} → {n.action}</sub>".replace('"', "'")
        if n.name in cat["utility"]:
            lines.append(f'    {nid}(("{lbl}")):::util')
        elif n.name in cat["leaf"]:
            lines.append(f'    {nid}[/"{lbl}"/]:::leaf')
        else:
            lines.append(f'    {nid}["{lbl}"]:::normal')

    for e in edges:
        if e.src_file == file and e.dst_file == file:
            s = mid(e.src_file, e.src_name)
            d = mid(e.dst_file, e.dst_name)
            if e.kind == "jumpback":
                lines.append(f"    {s} ==> {d}")
            else:
                lines.append(f"    {s} --> {d}")

    for e in edges:
        if e.src_file == file and e.dst_file != file:
            s = mid(e.src_file, e.src_name)
            d = mid(e.dst_file, e.dst_name)
            tag = f"→ {e.dst_file}"
            if e.kind == "jumpback":
                lines.append(f'    {s} =={tag}==> {d}')
            else:
                lines.append(f'    {s} --{tag}--> {d}')

    for e in edges:
        if e.dst_file == file and e.src_file != file:
            s = mid(e.src_file, e.src_name)
            d = mid(e.dst_file, e.dst_name)
            tag = f"{e.src_file} →"
            if e.kind == "jumpback":
                lines.append(f'    {s} =={tag}==> {d}')
            else:
                lines.append(f'    {s} --{tag}--> {d}')

    lines.append("    classDef util fill:" + COLORS["utility"] + ",stroke:#5b2c6f,color:#000")
    lines.append("    classDef normal fill:" + COLORS["normal"] + ",stroke:#1f618d,color:#000")
    lines.append("    classDef leaf fill:" + COLORS["leaf"] + ",stroke:#566573,color:#000")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# HTML 模板(带导航栏)
# ----------------------------------------------------------------------------
def _nav_html(current: str = "") -> str:
    """顶部导航栏,所有图共享一套链接,当前文件高亮。"""
    items = [
        ("index.html", "🏠 首页"),
        ("pipeline_overview.html", "🌐 总览图"),
        ("pipeline_external_entries.html", "🐍 Python 调用"),
        ("pipeline_utility_usage.html", "🟣 工具使用"),
    ]
    parts = ['<nav class="navbar">']
    for href, label in items:
        cls = "current" if href == current else ""
        parts.append(f'<a href="{href}" class="{cls}">{label}</a>')
    if current.startswith("pipeline_") and current != "pipeline_overview.html" \
            and current not in ("pipeline_external_entries.html", "pipeline_utility_usage.html"):
        # 提取 file 名
        stem = current.replace("pipeline_", "").replace(".html", "")
        parts.append(f'<span class="current">📁 {stem}.json</span>')
    parts.append("</nav>")
    return "\n  ".join(parts)


def wrap_html(title: str, mermaid_code: str, subtitle: str = "", current: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 0; background: #fafafa; }}
  .navbar {{ position: sticky; top: 0; z-index: 100;
            background: #2c3e50; color: white; padding: 8px 24px;
            display: flex; gap: 16px; align-items: center;
            font-size: 13px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  .navbar a {{ color: #ecf0f1; text-decoration: none; padding: 4px 8px;
              border-radius: 3px; }}
  .navbar a:hover {{ background: #34495e; }}
  .navbar .current {{ background: #e67e22; color: white; padding: 4px 8px;
                     border-radius: 3px; font-weight: bold; }}
  .content {{ padding: 24px; }}
  h1 {{ margin: 0 0 4px; font-size: 22px; }}
  h2 {{ margin: 24px 0 8px; font-size: 16px; color: #2c3e50;
        border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  .sub {{ color: #666; font-size: 13px; margin-bottom: 16px; }}
  .legend {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0 20px; font-size: 13px; }}
  .legend span {{ padding: 4px 10px; border-radius: 4px; border: 1px solid #ccc; }}
  .mermaid {{ background: white; border: 1px solid #ddd; border-radius: 6px;
              padding: 16px; overflow: auto; max-height: 80vh; }}
  .hint {{ color: #666; font-size: 12px; margin-top: 8px; }}
  .controls {{ margin: 8px 0; }}
  .controls button {{ padding: 4px 10px; margin-right: 6px; cursor: pointer; }}
  table {{ border-collapse: collapse; font-size: 13px; margin-top: 8px; }}
  td, th {{ border: 1px solid #ddd; padding: 4px 8px; text-align: left; }}
  th {{ background: #ecf0f1; }}
  pre {{ background: #f4f4f4; padding: 8px; border-radius: 4px; overflow: auto; font-size: 12px; }}
  .card-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
                gap: 12px; margin: 16px 0; }}
  .card {{ background: white; border: 1px solid #ddd; border-radius: 6px;
           padding: 12px; text-decoration: none; color: #2c3e50;
           transition: all 0.2s; display: block; }}
  .card:hover {{ border-color: #e67e22; transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
  .card h3 {{ margin: 0 0 4px; font-size: 14px; color: #2c3e50; }}
  .card .meta {{ color: #888; font-size: 12px; }}
  .card .badge {{ display: inline-block; padding: 2px 6px; border-radius: 3px;
                  font-size: 11px; margin-right: 4px; }}
</style>
</head>
<body>
  {_nav_html(current)}
  <div class="content">
    <h1>{title}</h1>
    <div class="sub">{subtitle}</div>
    <div class="legend">
      <span style="background:{COLORS['interface']}">🟡 用户入口</span>
      <span style="background:{COLORS['external']}">🟠 Python 入口</span>
      <span style="background:{COLORS['utility']}">🟣 工具节点</span>
      <span style="background:{COLORS['normal']}">🔵 普通节点</span>
      <span style="background:{COLORS['leaf']}">⚪ 终止</span>
    </div>
    <div class="controls">
      <button onclick="setScale(0.5)">50%</button>
      <button onclick="setScale(0.7)">70%</button>
      <button onclick="setScale(1.0)">100%</button>
      <button onclick="setScale(1.5)">150%</button>
      <button onclick="setScale(2.0)">200%</button>
      <button onclick="window.print()">打印/PDF</button>
    </div>
    <div class="mermaid">
{mermaid_code}
    </div>
    <p class="hint">滚轮缩放、拖动平移。生成于 tools/pipeline_to_mermaid.py</p>
  </div>
<script>
  function setScale(s) {{
    const el = document.querySelector('.mermaid');
    el.style.transform = 'scale(' + s + ')';
    el.style.transformOrigin = '0 0';
  }}
</script>
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  mermaid.initialize({{
    startOnLoad: true,
    flowchart: {{ useMaxWidth: false, htmlLabels: true }},
    securityLevel: "loose",
    theme: "default"
  }});
</script>
</body>
</html>
"""


# ----------------------------------------------------------------------------
# 主目录 index.html
# ----------------------------------------------------------------------------
def build_index_html(
    nodes: dict[str, dict[str, Node]],
    edges: list[Edge],
    stats: Stats,
) -> str:
    by_kind: dict[str, int] = defaultdict(int)
    for e in edges:
        by_kind[e.kind] += 1

    file_cards: list[str] = []
    for fname, ns in sorted(nodes.items()):
        n_nodes = len(ns)
        in_edges = sum(1 for e in edges if e.dst_file == fname)
        out_edges = sum(1 for e in edges if e.src_file == fname)
        file_cards.append(f"""
        <a class="card" href="pipeline_{fname}.html">
          <h3>📁 {fname}.json</h3>
          <div class="meta">
            <span class="badge" style="background:#aed6f1">{n_nodes} 节点</span>
            <span class="badge" style="background:#d5dbdb">入 {in_edges}</span>
            <span class="badge" style="background:#d5dbdb">出 {out_edges}</span>
          </div>
        </a>""")

    cards_html = "\n".join(file_cards)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>MaaGC Pipeline 状态机图谱</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 0; background: #fafafa; }}
  .navbar {{ position: sticky; top: 0; z-index: 100;
            background: #2c3e50; color: white; padding: 8px 24px;
            display: flex; gap: 16px; align-items: center;
            font-size: 13px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  .navbar a {{ color: #ecf0f1; text-decoration: none; padding: 4px 8px;
              border-radius: 3px; }}
  .navbar a:hover {{ background: #34495e; }}
  .navbar .current {{ background: #e67e22; color: white; padding: 4px 8px;
                     border-radius: 3px; font-weight: bold; }}
  .content {{ padding: 24px; max-width: 1200px; margin: 0 auto; }}
  h1 {{ margin: 0 0 8px; font-size: 24px; }}
  h2 {{ margin: 28px 0 12px; font-size: 17px; color: #2c3e50;
        border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  .sub {{ color: #666; font-size: 14px; margin-bottom: 16px; }}
  .stat-bar {{ display: flex; gap: 24px; flex-wrap: wrap; margin: 16px 0;
              padding: 12px 16px; background: white; border: 1px solid #ddd;
              border-radius: 6px; }}
  .stat-bar .stat {{ display: flex; flex-direction: column; }}
  .stat-bar .stat .v {{ font-size: 20px; font-weight: bold; color: #2c3e50; }}
  .stat-bar .stat .l {{ font-size: 11px; color: #888; }}
  .card-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
                gap: 12px; margin: 16px 0; }}
  .card {{ background: white; border: 1px solid #ddd; border-radius: 6px;
           padding: 14px; text-decoration: none; color: #2c3e50;
           transition: all 0.2s; display: block; }}
  .card:hover {{ border-color: #e67e22; transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
  .card h3 {{ margin: 0 0 6px; font-size: 14px; color: #2c3e50; }}
  .card .meta {{ color: #888; font-size: 12px; }}
  .card .badge {{ display: inline-block; padding: 2px 6px; border-radius: 3px;
                  font-size: 11px; margin-right: 4px; color: #000; }}
  .card.main {{ background: linear-gradient(135deg, #f9e79f 0%, #f4d03f 100%); }}
  .card.aux {{ background: linear-gradient(135deg, #d5dbdb 0%, #bb8fce 100%); }}
</style>
</head>
<body>
  <nav class="navbar">
    <a href="index.html" class="current">🏠 首页</a>
    <a href="pipeline_overview.html">🌐 总览图</a>
    <a href="pipeline_external_entries.html">🐍 Python 调用</a>
    <a href="pipeline_utility_usage.html">🟣 工具使用</a>
  </nav>
  <div class="content">
    <h1>🎮 MaaGC Pipeline 状态机图谱</h1>
    <div class="sub">
      由 <code>tools/pipeline_to_mermaid.py</code> 自动生成。
      本目录所有 HTML 都是 <strong>动态可交互</strong>的(基于 Mermaid.js 11)。
    </div>

    <div class="stat-bar">
      <div class="stat"><span class="v">{len(nodes)}</span><span class="l">Pipeline 文件</span></div>
      <div class="stat"><span class="v">{stats.nodes}</span><span class="l">节点总数</span></div>
      <div class="stat"><span class="v">{stats.edges_next}</span><span class="l">next 转移</span></div>
      <div class="stat"><span class="v">{stats.edges_jumpback}</span><span class="l">JumpBack 调用</span></div>
      <div class="stat"><span class="v">{stats.edges_python}</span><span class="l">Python 调用</span></div>
      <div class="stat"><span class="v">{stats.edges_interface}</span><span class="l">interface 入口</span></div>
      <div class="stat"><span class="v">{stats.utility_nodes}</span><span class="l">工具节点</span></div>
    </div>

    <h2>🌐 主视图</h2>
    <div class="card-grid">
      <a class="card main" href="pipeline_overview.html">
        <h3>🌐 Pipeline 总览 (stateDiagram-v2)</h3>
        <div class="meta">
          13 个文件作为复合状态<br/>全局视野,适合排查跨文件关系
        </div>
      </a>
      <a class="card aux" href="pipeline_external_entries.html">
        <h3>🐍 Python → Pipeline 调用图</h3>
        <div class="meta">
          {stats.edges_python} 处 <code>context.run_task()</code> 调用<br/>
          看 Python 怎么驱动 Pipeline
        </div>
      </a>
      <a class="card aux" href="pipeline_utility_usage.html">
        <h3>🟣 工具节点使用图</h3>
        <div class="meta">
          {stats.utility_nodes} 个工具节点被谁调用<br/>
          BackButton / ClickCenter / PopUp 集中点
        </div>
      </a>
    </div>

    <h2>📁 单文件状态机 ({len(nodes)} 个)</h2>
    <div class="card-grid">
      {cards_html}
    </div>

    <h2>🔧 重新生成</h2>
    <pre>python tools/pipeline_to_mermaid.py</pre>
  </div>
</body>
</html>
"""


# ----------------------------------------------------------------------------
# 写产物
# ----------------------------------------------------------------------------
def write_all(
    nodes: dict[str, dict[str, Node]],
    edges: list[Edge],
    stats: Stats,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 计算外部入口节点(用于 stateDiagram 标识)
    external_names = frozenset(
        e.dst_name for e in edges
        if e.kind in ("python-call", "interface-task")
    )

    # 1) overview (stateDiagram-v2)
    code = build_state_overview(nodes, edges, stats)
    html = wrap_html(
        "MaaGC Pipeline 总览图 (stateDiagram-v2)",
        code,
        f"复合状态按 13 个文件分组 / "
        f"{stats.edges_next} next / {stats.edges_jumpback} jumpback / "
        f"{stats.edges_python} Python 调用",
        current="pipeline_overview.html",
    )
    (OUT_DIR / "pipeline_overview.html").write_text(html, encoding="utf-8")
    print(f"[OK] pipeline_overview.html  (stateDiagram)")

    # 2) external entries (flowchart, 因为本质是调用图)
    code = build_external_entries(edges)
    html = wrap_html(
        "MaaGC Python → Pipeline 调用图 (flowchart)",
        code,
        f"{stats.edges_python} 处 `context.run_task()` 调用 — 此图为调用图,非状态机",
        current="pipeline_external_entries.html",
    )
    (OUT_DIR / "pipeline_external_entries.html").write_text(html, encoding="utf-8")
    print(f"[OK] pipeline_external_entries.html  (flowchart)")

    # 3) utility usage (flowchart, 因为本质是反向调用图)
    code = build_utility_usage(edges)
    html = wrap_html(
        "MaaGC 工具节点使用图 (flowchart)",
        code,
        f"被反向引用的 {len(UTILITY_NODES)} 个工具节点 — 此图为反向调用图,非状态机",
        current="pipeline_utility_usage.html",
    )
    (OUT_DIR / "pipeline_utility_usage.html").write_text(html, encoding="utf-8")
    print(f"[OK] pipeline_utility_usage.html  (flowchart)")

    # 4) per-file (stateDiagram-v2)
    for fname, ns in sorted(nodes.items()):
        file_edges = [e for e in edges if e.src_file == fname or e.dst_file == fname]
        code = build_state_per_file(fname, ns, file_edges, external_names)
        html = wrap_html(
            f"{fname}.json 状态机 (stateDiagram-v2)",
            code,
            f"{len(ns)} 节点 — 真·状态机视图",
            current=f"pipeline_{fname}.html",
        )
        (OUT_DIR / f"pipeline_{fname}.html").write_text(html, encoding="utf-8")
        print(f"[OK] pipeline_{fname}.html  ({len(ns)} nodes, stateDiagram)")

    # 5) index.html (主目录)
    html = build_index_html(nodes, edges, stats)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"[OK] index.html  (主目录)")


# ----------------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------------
def _print_stats(stats: Stats) -> None:
    print(f"Pipeline files: {stats.files}")
    print(f"Total nodes:    {stats.nodes}")
    print(f"Edges:")
    print(f"  next:           {stats.edges_next}")
    print(f"  jumpback:       {stats.edges_jumpback}")
    print(f"  python-call:    {stats.edges_python}")
    print(f"  interface-task: {stats.edges_interface}")
    print(f"Utility nodes: {stats.utility_nodes}")
    print(f"External entry nodes (from Python or interface.json): {len(stats.external_entry_nodes)}")


def _print_next_steps(stats: Stats, opened: bool = False) -> None:
    print()
    print(f"📁 产物在 docs/zh_cn/graph/  ({stats.files + 1} 个 HTML,已被 .gitignore)")
    print(f"🌐 主目录: docs/zh_cn/graph/index.html")
    if opened:
        print(f"✅ 已在默认浏览器打开")
    else:
        if sys.platform.startswith("win"):
            print(f"   浏览器打开: start docs\\zh_cn\\graph\\index.html")
        else:
            print(f"   浏览器打开: xdg-open docs/zh_cn/graph/index.html")
    print()
    print(f"💡 改了 Pipeline JSON 或 agent/*.py 后,再次运行本脚本即可刷新")


def _run_once() -> tuple[dict[str, dict[str, Node]], list[Edge], Stats]:
    nodes, pipe_edges = load_pipeline()
    py_edges = scan_python_calls()
    iface_edges = scan_interface_tasks()
    all_edges = resolve_destinations(pipe_edges + py_edges + iface_edges, nodes)
    stats = compute_stats(nodes, all_edges)
    _print_stats(stats)
    write_all(nodes, all_edges, stats)
    return nodes, all_edges, stats


def _watch_loop() -> None:  # noqa: C901  (轮询监控)
    """简易轮询 watch:每 2 秒扫一次,文件变更就重生。无外部依赖。"""
    watch_paths = [
        PIPELINE_DIR,
        INTERFACE_JSON,
        AGENT_DIR,
    ]
    print("👀 Watch 模式启动 (Ctrl+C 退出)")
    print(f"   监控: {[str(p) for p in watch_paths]}")
    last_mtimes: dict[str, float] = {}
    while True:
        changed = False
        for p in watch_paths:
            if not p.exists():
                continue
            if p.is_file():
                files = [p]
            else:
                files = list(p.rglob("*.json")) + list(p.rglob("*.py"))
            for f in files:
                try:
                    mt = f.stat().st_mtime
                except OSError:
                    continue
                key = str(f)
                if key not in last_mtimes:
                    last_mtimes[key] = mt
                elif mt > last_mtimes[key]:
                    last_mtimes[key] = mt
                    changed = True
        if changed:
            print()
            print(f"🔄 [{time.strftime('%H:%M:%S')}] 检测到变更,重新生成...")
            try:
                _run_once()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] {e}")
        time.sleep(2)


def main() -> None:
    args = sys.argv[1:]
    do_open = "--open" in args
    do_watch = "--watch" in args

    if do_watch:
        # 首次跑一次,然后进入轮询
        _run_once()
        if do_open:
            webbrowser.open((OUT_DIR / "index.html").as_uri())
        _watch_loop()
        return

    nodes, all_edges, stats = _run_once()

    if do_open:
        webbrowser.open((OUT_DIR / "index.html").as_uri())
    _print_next_steps(stats, opened=do_open)


if __name__ == "__main__":
    main()
