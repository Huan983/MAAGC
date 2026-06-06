---
name: pipeline-option
description: Add runtime UI options (select/checkbox/switch/input) to interface.json and wire them to Python via context.get_node_data(). Critical 3-place pattern: option definition + task option array + pre-defined pipeline node. Use when adding a new user-facing toggle, multi-choice selector, or custom input that must persist through MaaFramework's v2.3.0+ protocol.
---

# Pipeline Option 工作流

## TL;DR：3 处联动

新增一个 UI 选项需要**同时**改 3 个地方，缺一不可：

| # | 位置 | 内容 |
|---|------|------|
| 1 | `assets/interface.json` 的 `option` 字典 | 选项定义（type / cases / pipeline_override） |
| 2 | `assets/interface.json` 对应 task 的 `option: []` 数组 | 注册到具体任务（否则 UI 上看不到） |
| 3 | `assets/resource/base/pipeline/*.json` | **预定义**目标节点（pipeline_override 不会创建节点） |
| 4 | Python 代码 | `context.get_node_data()` 读取 + 业务分支 |

> ⚠️ **pipeline_override 只做属性合并，不会凭空创建节点。** 少了第 3 步，`context.get_node_data()` 会返回 `None`，运行时静默失败。

完整协议参考（嵌套 option、global_option、controller/resource 限制、占位符注入）：[references/protocol.md](references/protocol.md)

---

## 4 种 type 速查

| type | 选择 | override 字段 | 节点预定义形态 |
|------|------|---------------|---------------|
| `select` | 单选互斥 | `expected` | `recognition: "OCR"` + `expected: [...]` |
| `switch` | 二元 Yes/No | `enabled` | `{"enabled": bool}` |
| `input` | 自由文本 | `custom_action_param` | `action.param.custom_action_param` |
| `checkbox` | 多选 | `enabled` | `{"enabled": false}` |

---

## 模式 A：开关（switch + Flag 节点）— 最常用

**适用**：开启/关闭某个功能。

### interface.json

```jsonc
"开启5月城堡相亲": {
    "type": "switch",
    "description": "是否开启5月自动相亲",
    "default_case": "Yes",
    "cases": [
        {
            "name": "Yes",
            "pipeline_override": { "Flag_EnableMarryTask": { "enabled": true } }
        },
        {
            "name": "No",
            "pipeline_override": { "Flag_EnableMarryTask": { "enabled": false } }
        }
    ]
}
```

### 配套 pipeline 节点（必须预定义！）

```jsonc
"Flag_EnableMarryTask": { "enabled": true }
```

### 注册到 task

```jsonc
"task": [{
    "name": "推年计划",
    "entry": "Auto_YearlyTask",
    "option": ["开启5月城堡相亲", /* 其他选项 */]
}]
```

### Python 读取（建议放在业务函数入口）

```python
def handle_marry_festival(context: Context) -> bool:
    """处理春林节相亲（5月）"""
    EnableMarryTask = context.get_node_data("Flag_EnableMarryTask").get("enabled")
    if not EnableMarryTask:
        logger.info("自动相亲已关闭，跳过")
        return True
    # ... 正常逻辑
```

---

## 模式 B：单选（select + OCR 节点）

**适用**：选择城市、关卡、模式等互斥选项。

### interface.json

```jsonc
"选择刷取任务国家": {
    "type": "select",
    "description": "选择要刷取任务的目标城市",
    "default_case": "雄月城",
    "cases": [
        { "name": "王座堡", "pipeline_override": { "EnterCity": { "expected": ["王座堡"] } } },
        { "name": "雄月城", "pipeline_override": { "EnterCity": { "expected": ["雄月城"] } } }
    ]
}
```

### 配套 OCR 节点

```jsonc
"EnterCity": {
    "recognition": "OCR",          // ⚠️ 必须是 OCR，否则 expected 不生效
    "expected": ["王座堡", "圣盾堡", "雄月城", "翠庭"],
    "roi": [58, 320, 600, 682],
    "action": "Click"
}
```

### Python 读取

```python
data = context.get_node_data("EnterCity")
city = data.get("recognition", {}).get("param", {}).get("expected", ["王座堡"])[0]
```

---

## 模式 C：多选（checkbox + 多个 Flag 节点）

**适用**：多条件检测（好苗子条件）、可叠加的功能模块。

### interface.json

```jsonc
"开启好娃提醒": {
    "type": "checkbox",
    "default_case": ["科内塔之怒"],
    "cases": [
        { "name": "科内塔之怒",   "pipeline_override": { "检测_科内塔之怒":     { "enabled": true } } },
        { "name": "太阳+科内塔之怒", "pipeline_override": { "检测_太阳+科内塔之怒": { "enabled": true } } }
    ]
}
```

### 配套节点（每个 case 一个，默认全 false）

```jsonc
"检测_科内塔之怒":      { "expected": ["koneita"],            "enabled": false },
"检测_太阳+科内塔之怒": { "expected": ["sun_and_koneita"],    "enabled": false }
```

### Python 读取（遍历收集）

```python
def _get_enabled_checks(context) -> list:
    enabled = []
    for key in ["检测_科内塔之怒", "检测_太阳+科内塔之怒"]:
        node = context.get_node_data(key)
        if node and node.get("enabled", False):
            expected = node.get("recognition", {}).get("param", {}).get("expected", [])
            if expected:
                enabled.append(expected[0])
    return enabled
```

---

## 模式 D：自由输入（input + 占位符注入）

**适用**：用户输入自定义关卡号、自定义黑名单任务等。

### interface.json

```jsonc
"自定义任务黑名单": {
    "type": "input",
    "inputs": [
        {
            "name": "任务名称",
            "pipeline_type": "string",
            "default": "",
            "verify": "^[^,，]*$",
            "pattern_msg": "不能包含逗号"
        }
    ],
    "pipeline_override": {
        "CustomTaskBlacklist": {
            "expected": ["{任务名称}"]   // {名称} 占位符被实际输入替换
        }
    }
}
```

### Python 读取

```python
data = context.get_node_data("CustomTaskBlacklist")
value = data.get("recognition", {}).get("param", {}).get("expected", [""])[0]
```

---

## 命名与默认值

### 命名约定

| 角色 | 风格 | 示例 |
|------|------|------|
| option 名（用户可见） | 中文动词起头 | `开启5月城堡相亲`、`选择刷取任务国家` |
| 节点名（pipeline） | 英文 | `Flag_EnableMarryTask`、`EnterCity`、`检测_科内塔之怒` |
| switch case 名 | **严格 `Yes` / `No`** | 不要用 `true/false` 或 `是/否`（Client 解析跨平台不一致） |

### 默认值策略

> **保持现有行为是底线。** 老用户不该因新选项而行为改变。

| 场景 | 推荐 default |
|------|-------------|
| 新开关让功能默认关闭 | `No`（明确告知用户"关了"） |
| 新开关让功能默认开启 | `Yes`（保留旧行为） |
| 旧代码无条件开启 | `Yes`（兼容） |
| 旧代码无条件关闭 | `No`（兼容） |

---

## 读取位置

| 决策类型 | 放哪读 | 理由 |
|---------|-------|------|
| 是否执行某段流程 | 业务函数入口 `handle_xxx` | 与现有同名函数风格一致，子函数自治 |
| 用哪个值做主逻辑 | 任务入口 `run` 或 `YearlyTaskProcessor` | 一次读取、多次复用 |

> **反例**：不要把"是否开启 X"的判断堆在通用 `dispatch` 函数（如 `handle_festival_by_month`）里。每加一个开关 dispatch 就多一个 `if-elif`，越来越臃肿。

---

## ✅ 推荐做法

1. **先复用现有模式**：参考同项目里现成的同类选项（开关 → `开启5月城堡相亲`；选择 → `选择刷取任务国家`）
2. **3 处同步改完再跑**：不要中途停下来"先编译试试"
3. **JSON 改完跑 `python check_resource.py`**：pipeline 加载错误（如重复 key）会立刻报
4. **默认值遵循现状**：选项是"开"还是"关"取决于旧代码行为，不是你的偏好
5. **在 task 的 `doc` 数组里加一行说明**：用户能看懂每个选项的作用

---

## ❌ 不要做

### 1. 不要只通过 pipeline_override 定义节点

```jsonc
// ❌ 错：节点没在 pipeline JSON 中预定义 → 不会被加载 → get_node_data() 返回 None

// ✅ 对：在 pipeline JSON 里预定义
"Flag_EnableSailingFestivalPurchase": { "enabled": true }
```

**验证方法**：加完后跑 `python check_resource.py`，并在 Python 里加个 `None` 兜底日志。

### 2. 不要忘了注册到 task 的 option 数组

```jsonc
// ❌ 错：option 定义了但 task 不引用 → UI 上看不到
"option": []

// ✅ 对：同步注册
"option": ["开启3月启航节购买"]
```

### 3. 不要把判断塞到 dispatch 函数

```python
# ❌ 错：dispatch 越来越臃肿
def handle_festival_by_month(month):
    if month == 3 and not context.get_node_data("Flag_X").get("enabled"):
        return True
    if month == 3:
        return handle_sailing_festival(context)
    # ... 每加一个开关都得多一个 if

# ✅ 对：业务函数自治
def handle_sailing_festival(context):
    if not context.get_node_data("Flag_X").get("enabled"):
        return True
    # ... 正常逻辑
```

### 4. 不要混淆字段路径

| 用途 | 字段路径 | 备注 |
|------|---------|------|
| `select` | `data["recognition"]["param"]["expected"][0]` | 节点必须 `recognition: "OCR"` |
| `input` | `data["action"]["param"]["custom_action_param"][key]` | 完全独立的机制 |
| `switch` / `checkbox` | `data["enabled"]` | 最简单 |

### 5. 不要用非 `Yes`/`No` 的 switch case 名

```jsonc
// ❌ 错：Client 解析可能不一致
{ "name": "true" } / { "name": "是" } / { "name": "ON" }

// ✅ 对：跨 Client 一致
{ "name": "Yes" } / { "name": "No" }
```

### 6. 不要在 input 里塞 OCR expected 路径

`input` 用 `custom_action_param` 注入自定义文本，**与 `select` 的 `expected` 是两套独立机制**。混用会导致节点配置混乱、后续维护者读不懂。

### 7. 不要用中文做 pipeline 节点名

```jsonc
// ❌ 错：中文节点名 + 英文字段访问
"开启5月": { "enabled": true }

// ✅ 对：英文 Flag_ 命名
"Flag_EnableMarryTask": { "enabled": true }
```

中文做 option 名（用户可见），英文做 pipeline 节点名（代码访问）。混了会让代码和配置都对不上。

### 8. 不要在多文件 pipeline 里重复定义同名节点

`parse_and_override_once` 合并所有 pipeline JSON 时**严格拒绝**重复顶层 key。检查方法：

```bash
grep -rn "^\s*\"YourNodeName\":" assets/resource/base/pipeline/
```

两个文件都定义同一个顶层节点会直接让整个 `check_resource.py` 失败，且 Python `json.load()` 检测不出来（Python 会静默覆盖），必须用 C++ 解析器或 C++ 模拟检测。

---

## 验证流程

改完一次完整流程，**按顺序**做这 4 步：

1. **JSON 语法检查**

   ```bash
   python -c "import json; json.load(open('assets/interface.json', encoding='utf-8'))"
   python -c "import json; json.load(open('assets/resource/base/pipeline/auto_task.json', encoding='utf-8'))"
   ```

2. **资源加载检查**

   ```bash
   python check_resource.py ./assets/resource/base
   ```

   期望输出 `All directories checked.`

3. **Pipeline 节点测试**（可选）

   ```python
   data = context.get_node_data("Flag_EnableSailingFestivalPurchase")
   assert data is not None, "节点未预定义"
   assert "enabled" in data
   ```

4. **端到端验证**：用 Pipeline Testing Skill 跑一次实际流程

---

## 完整协议

更多 type 字段、嵌套 option、global_option、controller/resource 限制、`{占位符}` 注入机制等高级特性见 [references/protocol.md](references/protocol.md)。
