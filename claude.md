# MaaGC 项目理解文档

## 项目概述

MaaGC 是一款基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 开发的诸神皇冠/百年骑士团游戏自动化助手工具。

## 游戏背景

- **游戏名称**: 诸神皇冠/ 百年骑士团
- **类型**: 策略战旗类游戏
- **核心玩法**: 佣兵养成、结婚生子、血统遗传、战斗冒险

## 核心功能

| 功能 | 描述 | 入口任务 |
|------|------|----------|
| 启动游戏 | 自动启动游戏客户端 | GameStartUp |
| 推月 | 月度任务自动化 | Auto_FightTask |
| 推年 | 年度任务自动化 | Auto_YearlyTask |
| 市场折扣 | 大地图市场管理 | BigMapMarket |
| 商城免费礼包 | 商城物品领取 | BigMapMall |
| 悬赏令 | 悬赏令令牌领取 | BigMapRewardToken |
| **孩子信息识别** | 识别子女属性/血脉/特性并命名 | Auto_PannelCheck |
| **相亲匹配** | 识别相亲对象并匹配高血统姓名 | 待添加 |
| **婚礼系统** | 根据爵位选择宴会档位 | CastleWedding |

## 项目架构

```
MAAGC/
├── agent/                    # 自动化逻辑核心
│   ├── action/
│   │   ├── fight/           # 战斗相关处理
│   │   │   ├── fight_processor.py
│   │   │   └── fight_utils.py
│   │   └── zshg/            # 诸神皇冠/百年骑士团游戏逻辑
│   │       ├── child.py          # 孩子信息识别系统
│   │       ├── marry.py           # 相亲/婚礼系统
│   │       ├── role_utils.py      # 角色信息通用模块
│   │       └── task_extractor.py  # 任务提取器
│   ├── utils/
│   │   └── logger.py
│   └── main.py
├── assets/                   # 游戏资源与配置
│   ├── assets/
│   │   ├── high_blood_names.json  # 高血统姓名表
│   │   └── task_names.json
│   └── resource/
│       └── base/
│           └── pipeline/     # OCR/Pipeline 配置
│               ├── child_info.json   # 孩子信息识别配置
│               ├── marry.json        # 相亲系统配置
│               ├── event_utils.json  # 事件工具配置
│               ├── fight_utils.json  # 战斗工具配置
│               └── main_ui.json      # 主界面配置
├── docs/                     # 中文文档
│   └── zh_cn/
│       ├── panel.md         # Panel 识别系统设计
│       └── 功能介绍.md
└── deps/                     # JSON Schema 定义
```

## 关键概念

### 1. Panel 识别系统

游戏中的信息通过不同的 Panel（面板）展示：

| Panel | 识别内容 | 关键配置 |
|-------|----------|----------|
| 父母信息 | 父亲/母亲的姓名、爵位、佣兵团 | ROI 区域 + OCR |
| 潜力面板 | 六维属性（力量、体质、技巧、感知、敏捷、意志）| 锚点定位 + 动态 ROI |
| 血脉面板 | 血统名称及百分比 | 动态高度计算 + OCR |
| 特性面板 | 特性列表（带滚动）| 连续失败终止机制 |

### 2. 数据结构

```python
@dataclass
class Potential:
    """潜力属性"""
    values: dict[str, float]  # 属性名 -> 属性值

@dataclass
class Bloodline:
    """血脉信息"""
    bloodlines: list[dict]    # 血统列表

@dataclass
class Feature:
    """特性信息"""
    features: list[str]       # 特性列表

@dataclass
class ParentInfo:
    """父母信息"""
    name: str
    title: str       # 爵位
    mercenary_group: str
```

### 3. 命名规则

孩子命名格式：`最高属性 + 次高属性 + 特性 + 爵位`

示例：`力 ss 技 ss 太科公`

- 力: 最高属性（力量）
- ss: 属性等级（>0.93）
- 技: 次高属性（技巧）
- 太: 特性（太阳）
- 科: 特性（科内塔）
- 公: 爵位（公爵）

### 4. 爵位等级

```python
TITLE_RANK = {
    "公爵": 4,   # 最高 → 乡村宴会
    "伯爵": 3,
    "男爵": 2,
    "骑士": 1,
    "无爵位": 0,
}
```

### 5. 婚礼宴会选择

- **公爵（等级 4）** → 乡村宴会
- **伯爵及以下** → 祝福婚宴

## 核心文件说明

### agent/action/zshg/child.py

**功能**: 孩子信息识别与命名系统

**主要方法**:

- `extract_parent_info()` - 提取父母信息
- `compare_parent_titles()` - 比较父母爵位
- `extract_potential()` - 提取潜力属性
- `extract_bloodlines()` - 提取血脉信息
- `extract_features()` - 提取特性列表
- `generate_child_name()` - 生成孩子名字

### agent/action/zshg/role_utils.py

**功能**: 角色信息通用识别模块（被 child.py 和 marry.py 共用）

**主要函数**:

- `extract_all_role_info()` - 完整识别角色信息（潜力+血脉+特性）

### agent/action/zshg/marry.py

**功能**: 相亲与婚礼系统

**主要类**:

- `MarryProcessor` - 相亲处理器
  - `_detect_gender()` - 识别性别
  - `_detect_available_partners()` - 检测可相亲对象
  - `_match_name()` - 姓名匹配
- `WeddingProcessor` - 婚礼处理器
  - `_extract_title_from_ocr()` - 从 OCR 提取爵位
  - `_compare_titles()` - 比较爵位等级
  - `_get_target_banquet()` - 获取目标宴会

### assets/resource/base/pipeline/*.json

**JSON 配置格式**:

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
- `Template模板匹配
-Match` -  `ColorMatch` - 颜色匹配

## 常用工具任务

### Pipeline 工具节点

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

## 开发注意事项

1. **ROI vs CropBox**: 使用 `roi` 而非 `crop_box`，更符合 MAA 标准
2. **期望值数组**: `expected` 使用数组提高识别容错率
3. **属性区间**: 属性区间应该是连续的，避免空隙
4. **动态内容**: 使用锚点定位 + 相对坐标计算
5. **滚动面板**: 连续失败 2 次时终止识别

## 常用命令

```bash
# 编译检查
python -m py_compile agent/action/zshg/marry.py

# 资源检查
python check_resource.py
```

## 相关文档

- [Panel 识别系统设计](./docs/zh_cn/panel.md)
- [功能介绍](./docs/zh_cn/功能介绍.md)
- [新手上路](./docs/zh_cn/新手上路.md)
