# MaaGC 项目理解文档

## 1. 项目概述

MaaGC 是一款基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 开发的诸神皇冠/百年骑士团游戏自动化助手工具，旨在为玩家提供便捷的游戏自动化功能。

## 2. 游戏背景

- **游戏名称**: 诸神皇冠/百年骑士团
- **类型**: 策略战旗类游戏
- **核心玩法**: 佣兵养成、结婚生子、血统遗传、战斗冒险

## 3. 核心功能

| 功能模块 | 功能描述 | 入口任务 |
|---------|---------|----------|
| **基础功能** | | |
| 启动游戏 | 自动启动游戏客户端 | GameStartUp |
| **任务自动化** | | |
| 推月 | 月度任务自动化 | Auto_FightTask |
| 推年 | 年度任务自动化 | Auto_YearlyTask |
| 每日任务 | 综合处理每日礼包、市场折扣、商城礼包和悬赏令 | Auto_DailyTask |
| **市场与商城** | | |
| 市场折扣 | 大地图市场管理 | BigMapMarket |
| 商城免费礼包 | 商城物品领取 | BigMapMall |
| 悬赏令 | 悬赏令令牌领取 | BigMapRewardToken |
| **角色系统** | | |
| 孩子信息识别 | 识别子女属性/血脉/特性并命名 | Auto_PannelCheck |
| 相亲匹配 | 识别相亲对象并匹配高血统姓名 | 待添加 |
| 婚礼系统 | 根据爵位选择宴会档位 | CastleWedding |

## 4. 项目架构

```
MAAGC/
├── agent/                    # 自动化逻辑核心
│   ├── action/               # 具体游戏操作实现
│   │   ├── fight/            # 战斗相关处理
│   │   │   ├── fight_processor.py
│   │   │   └── fight_utils.py
│   │   └── zshg/             # 诸神皇冠游戏逻辑
│   │       ├── child.py          # 孩子信息识别系统
│   │       ├── daily_task.py     # 每日任务处理
│   │       ├── marry.py          # 相亲/婚礼系统
│   │       ├── role_utils.py     # 角色信息通用模块
│   │       └── task_extractor.py # 任务提取器
│   ├── utils/                # 通用工具模块
│   │   ├── __init__.py
│   │   └── logger.py
│   ├── agent_allfile.py      # 代理文件汇总
│   └── main.py               # 主入口文件
├── assets/                   # 游戏资源与配置
│   ├── MaaCommonAssets/      # MAA 通用资源
│   │   └── OCR/              # OCR 模型
│   ├── table/                # 配置表格文件
│   │   ├── high_blood_names.json  # 高血统姓名表
│   │   ├── task_blacklist.txt     # 任务黑名单
│   │   ├── task_blacklist.json    # 任务黑名单(JSON格式)
│   │   └── task_names.json        # 任务名称列表
│   ├── resource/             # 游戏资源
│   │   └── base/             # 基础资源
│   │       ├── image/        # 图片资源
│   │       │   ├── Marry/    # 结婚相关图片
│   │       │   └── UI/       # 界面图片
│   │       ├── model/        # 模型文件
│   │       └── pipeline/     # OCR/Pipeline 配置
│   │           ├── auto_task.json     # 自动任务配置
│   │           ├── child_info.json    # 孩子信息识别配置
│   │           ├── city.json          # 城市相关配置
│   │           ├── event_utils.json   # 事件工具配置
│   │           ├── fight_utils.json   # 战斗工具配置
│   │           ├── main_ui.json       # 主界面配置
│   │           ├── marry.json         # 相亲系统配置
│   │           ├── role.json          # 角色相关配置
│   │           └── start_up.json      # 启动配置
│   ├── description.md        # 项目描述
│   ├── interface.json        # 接口配置
│   └── logo.png              # 项目 logo
├── deps/                     # 依赖文件
│   └── tools/                # 工具依赖
│       ├── custom.action.schema.json
│       ├── custom.recognition.schema.json
│       ├── interface.schema.json
│       ├── interface_config.schema.json
│       └── pipeline.schema.json
├── docs/                     # 项目文档
│   ├── maafw_doc/            # MAAFW 协议文档
│   └── zh_cn/                # 中文文档
│       ├── MaaPiCli 使用说明.md
│       ├── panel.md         # Panel 识别系统设计
│       ├── 个性化配置.md
│       ├── 功能介绍.md
│       ├── 常见问题.md
│       ├── 战斗系统开发文档.md
│       ├── 新手上路.md
│       └── 连接设置.md
├── tools/                    # 工具脚本
│   ├── ci/                   # CI 相关工具
│   ├── minify_json.py        # JSON 压缩工具
│   └── validate_schema.py    # Schema 验证工具
├── .github/                  # GitHub 配置
├── check_resource.py         # 资源检查脚本
├── claude.md                 # 项目理解文档
├── README.md                 # 项目说明
└── requirements.txt          # Python 依赖包列表
```

## 5. 核心概念

### 5.1 Panel 识别系统

游戏中的信息通过不同的 Panel（面板）展示，系统通过图像识别技术提取这些信息：

| Panel 类型 | 识别内容 | 技术实现 |
|-----------|---------|----------|
| 父母信息 | 父亲/母亲的姓名、爵位、佣兵团 | ROI 区域 + OCR |
| 潜力面板 | 六维属性（力量、体质、技巧、感知、敏捷、意志）| 锚点定位 + 动态 ROI |
| 血脉面板 | 血统名称及百分比 | 动态高度计算 + OCR |
| 特性面板 | 特性列表（带滚动）| 连续失败终止机制 |

### 5.2 Pipeline 配置系统

Pipeline 是 MaaFramework 中的核心概念，用于定义自动化任务的流程。配置文件采用 JSON 格式，定义了任务的识别方式、预期结果、ROI 区域等信息。

**JSON 配置格式示例**:
```json
{
    "TaskName": {
        "recognition": "OCR",
        "expected": ["关键词1", "关键词2"],
        "roi": [x, y, width, height],
        "timeout": 2000
    }
}
```

**常用 Recognition 类型**:
- `OCR` - 文字识别
- `DirectHit` - 图像直击
- `TemplateMatch` - 模板匹配
- `ColorMatch` - 颜色匹配

## 6. 核心模块详解

### 6.1 孩子信息识别系统 (agent/action/zshg/child.py)

**功能**: 识别子女属性、血脉、特性并自动命名

**主要方法**:
- `extract_parent_info()` - 提取父母信息
- `compare_parent_titles()` - 比较父母爵位
- `extract_potential()` - 提取潜力属性
- `extract_bloodlines()` - 提取血脉信息
- `extract_features()` - 提取特性列表
- `generate_child_name()` - 根据属性生成孩子名字

### 6.2 每日任务处理系统 (agent/action/zshg/daily_task.py)

**功能**: 自动化处理游戏中的每日任务

**主要功能**:
- 自动处理每日礼包和密令
- 自动进入市场购买折扣物品
- 自动进入商城领取免费礼包
- 自动进入悬赏令界面领取奖励

### 6.3 角色信息通用模块 (agent/action/zshg/role_utils.py)

**功能**: 通用角色信息识别模块，被 child.py 和 marry.py 共用

**主要函数**:
- `extract_all_role_info()` - 完整识别角色信息（潜力+血脉+特性）

### 6.4 相亲与婚礼系统 (agent/action/zshg/marry.py)

**功能**: 自动化处理游戏中的相亲和婚礼流程

**主要类**:
- `MarryProcessor` - 相亲处理器
  - `_detect_gender()` - 识别性别
  - `_detect_available_partners()` - 检测可相亲对象
  - `_match_name()` - 姓名匹配
- `WeddingProcessor` - 婚礼处理器
  - `_extract_title_from_ocr()` - 从 OCR 提取爵位
  - `_compare_titles()` - 比较爵位等级
  - `_get_target_banquet()` - 获取目标宴会

## 7. 开发指南

### 7.1 开发注意事项

1. **设计规范分离**: 设计类内容（数据结构、命名规则、爵位等级等）应放在专门的子文档中
2. **ROI 规范**: 使用 `roi` 而非 `crop_box`，更符合 MAA 标准
3. **容错设计**: `expected` 使用数组提高识别容错率
4. **属性处理**: 属性区间应该是连续的，避免空隙
5. **动态内容**: 使用锚点定位 + 相对坐标计算
6. **滚动面板**: 连续失败 2 次时终止识别

### 7.2 常用开发命令

```bash
# 编译检查
python -m py_compile agent/action/zshg/marry.py

# 资源检查
python check_resource.py

# 运行主程序
python agent/main.py
```

### 7.3 测试功能

#### 好苗子弹窗功能测试

创建 `agent/action/zshg/test_child_alert.py` 文件，包含以下测试函数：
- `test_potential_evaluation()` - 测试潜力属性评估
- `test_feature_evaluation()` - 测试特性评估
- `test_alert_trigger()` - 测试弹窗触发逻辑

#### 特性配置文件

在 `assets/table/` 目录下创建以下配置文件：
- `good_features.json` - 好特性列表
- `bad_features.json` - 负面特性列表
- `race_features.json` - 种族特性列表

### 7.4 参考文档

#### MAAFW 核心协议文档

| 文档名称 | 用途 | 路径 | 重要性 |
|---------|------|------|--------|
| 任务流水线协议 | 编写 JSON 格式的 node 任务 | `docs/maafw_doc/3.1-任务流水线协议.md` | **必须学习** |
| ProjectInterfaceV2 协议 | 编写外部 interface 接口 | `docs/maafw_doc/3.3-ProjectInterfaceV2协议.md` | **必须学习** |
| 快速开始 | MAAFW 快速入门指南 | `docs/maafw_doc/1.1-快速开始.md` | 推荐学习 |
| 术语解释 | MAAFW 核心术语说明 | `docs/maafw_doc/1.2-术语解释.md` | 推荐学习 |

#### 项目文档

- [设计规范](./docs/zh_cn/设计规范.md) - 数据结构、命名规则、爵位等级等设计规范
- [Panel 识别系统设计](./docs/zh_cn/panel.md)
- [功能介绍](./docs/zh_cn/功能介绍.md)
- [新手上路](./docs/zh_cn/新手上路.md)
- [MaaPiCli 使用说明](./docs/zh_cn/MaaPiCli 使用说明.md)
- [个性化配置](./docs/zh_cn/个性化配置.md)
- [常见问题](./docs/zh_cn/常见问题.md)
- [战斗系统开发文档](./docs/zh_cn/战斗系统开发文档.md)
- [连接设置](./docs/zh_cn/连接设置.md)

## 8. 工具与资源

### 8.1 Pipeline 工具节点

| 节点名称 | 功能 |
|----------|------|
| PropertyPanelSwipeDown | 属性面板下滑 |
| PannelChildInfoButton | 孩子信息按钮 |
| PannelFatherInfo / PannelMotherInfo | 父母信息 |
| PannelPotential | 潜力面板 |
| PannelBloodline | 血脉面板 |
| PannelFeature | 特性面板 |
| Event_MercenaryBaby | 佣兵生娃事件 |
| Event_WeddingTitleCheckLeft/Right | 婚礼爵位检测 |
| Event_WeddingTitleButton | 宴会按钮 |

### 8.2 配置文件说明

**主要 Pipeline 配置文件**:
- `auto_task.json` - 自动任务配置
- `child_info.json` - 孩子信息识别配置
- `city.json` - 城市相关配置
- `event_utils.json` - 事件工具配置
- `fight_utils.json` - 战斗工具配置
- `main_ui.json` - 主界面配置
- `marry.json` - 相亲系统配置
- `role.json` - 角色相关配置
- `start_up.json` - 启动配置

**任务配置文件**:
- `task_names.json` - 任务名称列表
- `task_blacklist.txt` - 任务黑名单(文本格式)
- `task_blacklist.json` - 任务黑名单(JSON格式)
- `high_blood_names.json` - 高血统姓名表
