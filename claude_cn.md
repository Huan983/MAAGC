<!--
⚠️ 同步规则 (Sync Rule):
This file is maintained in both English and Chinese.
ANY change to one file MUST be mirrored to the other.
- claude.md (English) ↔ claude_cn.md (中文)
当修改此文件时，请同步更新另一个语言版本。
-->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MaaGC 项目概述

MaaGC 是一款基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 开发的诸神皇冠/百年骑士团游戏自动化助手工具，为玩家提供佣兵养成、结婚生子、血统遗传、战斗冒险等自动化功能。

### 核心功能

| 功能模块 | 功能描述 | 入口任务 |
|---------|---------|----------|
| 启动游戏 | 自动启动游戏客户端 | GameStartUp |
| 推月 | 月度任务自动化 | Auto_FightTask |
| 推年 | 年度任务自动化 | Auto_YearlyTask |
| 每日任务 | 每日礼包、市场折扣、商城礼包、悬赏令 | Auto_DailyTask |
| 孩子信息识别 | 识别子女属性/血脉/特性并命名 | Auto_PannelCheck |
| 相亲匹配 | 识别相亲对象并匹配高血统姓名 | Auto_MarryTask |
| 婚礼系统 | 根据爵位选择宴会档位 | CastleWedding |

### 项目架构

``` struct
agent/                    # 自动化逻辑核心
├── action/
│   ├── fight/            # 战斗相关
│   └── zshg/             # 诸神皇冠游戏逻辑
│       ├── child.py      # 孩子信息识别
│       ├── marry.py      # 相亲/婚礼系统
│       ├── daily_task.py # 每日任务
│       └── role_utils.py # 角色信息通用模块
└── main.py               # 主入口

assets/
├── table/                # 配置表格
│   ├── high_blood_names.json    # 高血统姓名表
│   └── child_alert_conditions.json  # 好苗子条件
└── resource/base/pipeline/  # Pipeline JSON 配置
    ├── main_ui.json      # 主界面
    ├── marry.json        # 相亲系统
    └── child_info.json   # 孩子信息
```

## 常用开发命令

```bash
python -m py_compile agent/action/zshg/marry.py  # 编译检查
python check_resource.py                          # 资源检查
python agent/main.py                              # 运行主程序
```

## 开发注意事项

1. **ROI 规范**: 使用 `roi` 而非 `crop_box`
2. **容错设计**: `expected` 使用数组提高识别容错率
3. **连续范围**: 属性区间应连续，避免空隙
4. **滚动面板**: 连续失败 2 次时终止识别
5. **Table 路径**: 引用 `assets/table/` 时使用 `cwd_dir + "table/xxx.json"` 格式
6. **Pre-commit**: JSON/YAML 自动格式化 (oxipng 图片, prettier 配置)

## MCP 工具使用

- **图片理解**: 分析图片时，使用 `mcp__MiniMax__understand_image` 工具
- **网络搜索**: 搜索外部信息时，使用 `mcp__MiniMax__web_search` 工具

## 必读文档

- `docs/maafw_doc/zh_cn/3.1-任务流水线协议.md` - 任务流水线协议（**新增功能前必读**）
- `docs/maafw_doc/zh_cn/3.3-ProjectInterfaceV2协议.md` - 外部接口协议（**新增功能前必读**）
- `docs/zh_cn/项目概述.md` - 项目概述与详细架构
- `docs/zh_cn/设计规范.md` - 数据结构、爵位等级、命名规则

## 数据结构

```python
@dataclass
class Potential:
    values: dict[str, float]  # 属性名 -> 值 (0.0-1.0)

@dataclass
class Bloodline:
    bloodlines: dict[str, float]  # 血统名 -> 百分比

@dataclass
class Feature:
    name: str
    is_hidden: bool = False

@dataclass
class ParentInfo:
    name: str
    title: str      # "公爵", "伯爵", "男爵", "骑士", "无爵位"
    mercenary_group: str
```

**爵位等级**: 公爵(4) > 伯爵(3) > 男爵(2) > 骑士(1) > 无爵位(0)

**属性等级**: SS(>0.93) > S(0.74-0.93) > A(0.55-0.74) > B(0.35-0.55) > C(0.20-0.35) > D(0.10-0.20) > E(<0.10)

## 工作流规则

### 1. 计划节点默认设置

- 对于任何非 trivial 的任务（3 个以上步骤或架构决策），进入计划模式。
- 如果事情出错，立即停止并重新规划 — 不要继续推进。
- 在验证步骤中使用计划模式，而不仅仅是构建。
- 提前编写详细规格说明以减少歧义。

### 2. 子代理策略

- 自由使用子代理以保持主内容窗口整洁。
- 将研究、探索和并行分析任务委托给子代理。
- 对于复杂问题，通过子代理投入更多计算资源。
- 每个子代理一个任务，以集中执行。

### 3. 自我提升循环

- 在用户进行任何修正后：使用该模式更新 `tasks/lessons.md` 文件。
- 为自己写规则，防止同样的错误再次发生。
- 粗暴地迭代这些教训，直到错误率下降。
- 在会议开始时回顾与相关项目相关的经验教训。

### 4. 完成前验证

- 不要未经验证就标记任务完成。
- 在相关情况下，比较主分支与你所做的更改之间的行为差异。
- 自问："员工工程师会批准这个吗？"
- 运行测试，检查日志，展示正确性。

### 5. 需求优雅（平衡）

- 对于非小改动：暂停并询问"是否有更优的方案？"
- 如果修复感觉很 hacky："知道我现在所了解的一切，实现优雅的解决方案。"
- 对于简单的、常见的修复，跳过此步骤 — 不要过度工程化。
- 在展示自己的作品前，先对其提出质疑。

### 6. 自主修复错误

- 当收到错误报告时：直接修复它。不要要求指导。
- 指向日志、错误和失败的测试 — 然后解决它们。
- 用户无需进行任何上下文切换。
- 在未被告知的情况下自行修复失败的 CI 测试。

## 任务管理

1. **先计划**：在 `tasks/todo.md` 中编写可检查的计划项。
2. **验证计划**：在开始实现前检查。
3. **跟踪进度**：在进行中标记任务完成状态。
4. **解释变更**：每一步都进行高层级的总结。
5. **记录结果**：在 `tasks/todo.md` 中添加评审部分。
6. **记录经验教训**：修正后更新 `tasks/lessons.md` 文件。

## 核心原则

- **简单优先**：让每次更改尽可能简化，影响最小化代码。
- **无懈怠**：找出根本原因。不要使用临时修复。遵循高级开发者的标准。

## 测试技巧

### Pipeline 测试流程

1. **连接设备**

   ```python
   find_adb_device_list()  # 或 find_window_list()
   connect_adb_device(device_name="xxx")  # 或 connect_window()
   ```

2. **读取 pipeline 文件**

   ```python
   load_pipeline(pipeline_path="<pipeline_json_path>")
   ```

3. **逐个测试节点**

   ```python
   run_pipeline(controller_id=CONTROLLER_ID, pipeline_path=PIPELINE_PATH, entry="node_name", resource_path=RESOURCE_PATH)
   ```

4. **分析结果**
   - `status == "succeeded"` + `all_results` 有内容 = 识别成功
   - `score > 0.9` = 可靠的匹配

5. **资源保护**：绝对不要点击升级、供奉、购买等消耗资源的确认按钮

6. **返回**：使用 `main_ui.json` 中的 `BackButton_500ms` 作为最可靠的返回方式
