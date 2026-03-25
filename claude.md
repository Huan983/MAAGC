<!--
⚠️ 同步规则 (Sync Rule):
This file is maintained in both English and Chinese.
ANY change to one file MUST be mirrored to the other.
- claude.md (English) ↔ claude_cn.md (中文)
当修改此文件时，请同步更新另一个语言版本。
-->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MaaGC Project Overview

MaaGC is an automation assistant tool for "Gods' Crown / Century Knights" game, developed based on [MaaFramework](https://github.com/MaaXYZ/MaaFramework). It provides automated features for mercenary cultivation, marriage and children, bloodline inheritance, combat adventures, etc.

### Core Features

| Module | Description | Entry Task |
|--------|-------------|------------|
| Game Launch | Auto-launch game client | GameStartUp |
| Monthly Push | Monthly task automation | Auto_FightTask |
| Yearly Push | Yearly task automation | Auto_YearlyTask |
| Daily Tasks | Daily礼包, market discounts, shop礼包, bounties | Auto_DailyTask |
| Child Info Recognition | Identify child attributes/bloodlines/features and name them | Auto_PannelCheck |
| Matchmaking | Identify candidates and match high-bloodline names | Auto_MarryTask |
| Wedding System | Choose banquet tier based on title | CastleWedding |

### Project Architecture

```struct
agent/                    # Core automation logic
├── action/
│   ├── fight/            # Combat related
│   └── zshg/             # Gods' Crown game logic
│       ├── child.py      # Child info recognition
│       ├── marry.py      # Matchmaking/Wedding system
│       ├── daily_task.py # Daily tasks
│       └── role_utils.py # Role info common module
└── main.py               # Main entry

assets/
├── table/                # Configuration tables
│   ├── high_blood_names.json    # High bloodline name table
│   └── child_alert_conditions.json  # Good seedling conditions
└── resource/base/pipeline/  # Pipeline JSON config
    ├── main_ui.json      # Main interface
    ├── marry.json        # Matchmaking system
    └── child_info.json   # Child info
```

## Common Development Commands

```bash
python -m py_compile agent/action/zshg/marry.py  # Compile check
python check_resource.py                          # Resource check
python agent/main.py                              # Run main program
```

## Development Notes

1. **ROI Standard**: Use `roi` instead of `crop_box`
2. **Fault Tolerance**: Use arrays in `expected` to improve recognition fault tolerance
3. **Continuous Ranges**: Attribute ranges should be continuous, avoid gaps
4. **Scroll Panels**: Terminate recognition after 2 consecutive failures
5. **Table Paths**: When referencing `assets/table/`, use `cwd_dir + "table/xxx.json"` format
6. **Pre-commit**: JSON/YAML auto-formatting (oxipng images, prettier config)

## Required Reading

- `docs/maafw_doc/3.1-任务流水线协议.md` - Task Pipeline Protocol (**必读 before adding new features**)
- `docs/maafw_doc/3.3-ProjectInterfaceV2协议.md` - External Interface Protocol (**必读 before adding new features**)
- `docs/zh_cn/项目概述.md` - Project overview and detailed architecture
- `docs/zh_cn/设计规范.md` - Data structures, title levels, naming conventions

## Data Structures

```python
@dataclass
class Potential:
    values: dict[str, float]  # Attribute name -> value (0.0-1.0)

@dataclass
class Bloodline:
    bloodlines: dict[str, float]  # Bloodline name -> percentage

@dataclass
class Feature:
    name: str
    is_hidden: bool = False

@dataclass
class ParentInfo:
    name: str
    title: str      # "Duke", "Earl", "Baron", "Knight", "No Title"
    mercenary_group: str
```

**Title Levels**: Duke(4) > Earl(3) > Baron(2) > Knight(1) > No Title(0)

**Attribute Levels**: SS(>0.93) > S(0.74-0.93) > A(0.55-0.74) > B(0.35-0.55) > C(0.20-0.35) > D(0.10-0.20) > E(<0.10)

## Workflow Rules

### 1. Plan Node Default Settings

- For any non-trivial tasks (3+ steps or architectural decisions), enter plan mode.
- If something goes wrong, stop immediately and replan — don't keep pushing forward.
- Use plan mode during verification steps, not just during construction.
- Write detailed specifications upfront to reduce ambiguity.

### 2. Sub-agent Strategy

- Freely use sub-agents to keep the main content window clean.
- Delegate research, exploration, and parallel analysis tasks to sub-agents.
- For complex problems, invest more compute resources through sub-agents.
- One sub-agent per task to stay focused.

### 3. Self-improvement Loop

- After any user correction: use that mode to update the `tasks/lessons.md` file.
- Write rules for yourself to prevent the same mistakes from happening again.
- Iteratively brutalize these lessons until error rates drop.
- Review lessons related to the current project at the start of sessions.

### 4. Pre-completion Verification

- Don't mark tasks complete without verification.
- When relevant, compare behavior differences between main branch and your changes.
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness.

### 5. Requirements Grace (Balance)

- For non-trivial changes: pause and ask "Is there a better approach?"
- If a fix feels hacky: "Given everything I know now, implement an elegant solution."
- For simple, common fixes, skip this step — don't over-engineer.
- Question your work before presenting it.

### 6. Self-directed Error Fixing

- When receiving error reports: fix it directly. Don't ask for guidance.
- Point to logs, errors, and failing tests — then fix them.
- Users don't need any context switching.
- Fix failing CI tests on your own without being told.

## Task Management

1. **Plan First**: Write checkable plan items in `tasks/todo.md`.
2. **Verify Plan**: Check before starting implementation.
3. **Track Progress**: Mark in-progress items as complete.
4. **Explain Changes**: Summarize each step at a high level.
5. **Record Results**: Add a review section in `tasks/todo.md`.
6. **Record Lessons Learned**: Update `tasks/lessons.md` after corrections.

## Core Principles

- **Simplicity First**: Make every change as simple as possible, minimize code impact.
- **No Slack**: Find root causes. Don't use temporary fixes. Follow senior developer standards.

## Testing Skills

### Pipeline Testing

When testing Pipeline JSON files, use: `.trae/skills/pipeline-testing.md`

Key points:

- Connect device first (ADB or Window)
- Use `run_pipeline` with correct paths
- **DO NOT click confirm** on resource-consuming actions (upgrades, offerings, purchases)
- Use `BackButton_500ms` (main_ui.json) as reliable return
- Record results in test summary format
