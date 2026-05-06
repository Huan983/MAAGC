"""战场网格与单位识别模块 - 重构后结构清晰的数据层、识别层、结构层"""

import os
import sys
import cv2
import numpy as np
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional

current_file_path = os.path.abspath(__file__)
current_script_dir = os.path.dirname(current_file_path)
agent_dir = os.path.dirname(os.path.dirname(current_script_dir))
project_root_dir = os.path.dirname(agent_dir)

if os.getcwd() != project_root_dir:
    os.chdir(project_root_dir)
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

from utils import logger


# ========================
# 数据层：Cell + CellRect
# ========================


class CellType(Enum):
    NONE = "none"
    SELF = "self"
    ENEMY = "enemy"
    FRIEND = "friend"


@dataclass
class CellRect:
    x: int = 0
    y: int = 0
    width: int = 120
    height: int = 120

    def to_box(self) -> List[int]:
        return [self.x, self.y, self.width, self.height]

    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass
class Cell:
    row: int
    col: int
    rect: CellRect
    cell_type: CellType = CellType.NONE
    have_person: bool = False
    unit_center: Tuple[int, int] = field(default=(0, 0))  # 单位精确位置（颜色区域中心）
    is_threat: bool = False
    is_moveable: bool = False
    is_attackable: bool = False


# ========================
# 识别层：RecoProcessor
# ========================


class RecoProcessor:
    """单例识别器：颜色检测、威胁区域、攻击/移动范围"""
    _instance = None

    PIPELINE_NODES = {
        "threat": "Battle_ThreatRegion",
        "ocr": "Battle_UnitScan_OCR",
        CellType.SELF: "Battle_UnitScan_Blue",
        CellType.ENEMY: "Battle_UnitScan_Red",
        CellType.FRIEND: "Battle_UnitScan_Green",
    }

    CELL_SIZE = 120

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def init(self):
        """初始化识别器"""
        self._initialized = True
        logger.info("RecoProcessor 初始化完成")

    def detect_cell_type(self, cell: Cell, context) -> CellType:
        """通过 Pipeline Node 检测单个格子内的单位类型"""
        img = context.tasker.controller.post_screencap().wait().get()

        # 优先检测我方（蓝色），因为战斗中主要操作我方单位
        for cell_type, node_name in [
            (CellType.SELF, self.PIPELINE_NODES.get(CellType.SELF)),
            (CellType.ENEMY, self.PIPELINE_NODES.get(CellType.ENEMY)),
            (CellType.FRIEND, self.PIPELINE_NODES.get(CellType.FRIEND)),
        ]:
            if not node_name:
                continue

            reco = context.run_recognition(node_name, img)

            if reco and reco.hit and reco.all_results:
                # 检查检测结果是否在当前格子内
                for result in reco.all_results:
                    if hasattr(result, "box") and result.box:
                        bx, by, bw, bh = result.box
                        # 检查是否在格子内
                        if (
                            bx >= cell.rect.x
                            and bx + bw <= cell.rect.x + cell.rect.width
                            and by >= cell.rect.y
                            and by + bh <= cell.rect.y + cell.rect.height
                        ):
                            # 计算单位中心
                            cell.unit_center = (bx + bw // 2, by + bh // 2)
                            return cell_type

        return CellType.NONE

    def detect_threat_region(self, context) -> List[Tuple[int, int, int, int]]:
        """通过 Pipeline Node 检测威胁区域，返回匹配区域列表 [(x, y, w, h), ...]"""
        img = context.tasker.controller.post_screencap().wait().get()
        reco = context.run_recognition(self.PIPELINE_NODES["threat"], img)

        results = []
        if reco and reco.hit and reco.all_results:
            for result in reco.all_results:
                if hasattr(result, "box") and result.box:
                    results.append(result.box)
            logger.info(f"威胁区域识别: {len(results)} 个结果")
        else:
            logger.info("威胁区域识别未命中")
        return results

    def scan_all_cells(self, grid: 'BattleGrid', context) -> List[Cell]:
        """一次截图，批量检测所有格子内的单位类型"""
        img = context.tasker.controller.post_screencap().wait().get()
        units = []

        # 一次截图后，对每种颜色只调用一次 run_recognition
        for cell_type, node_name in [
            (CellType.SELF, self.PIPELINE_NODES.get(CellType.SELF)),
            (CellType.ENEMY, self.PIPELINE_NODES.get(CellType.ENEMY)),
            (CellType.FRIEND, self.PIPELINE_NODES.get(CellType.FRIEND)),
        ]:
            if not node_name:
                continue

            reco = context.run_recognition(node_name, img)
            if not reco or not reco.hit or not reco.all_results:
                continue

            # 遍历所有检测结果，归类到对应格子
            for result in reco.all_results:
                if not hasattr(result, "box") or not result.box:
                    continue
                bx, by, bw, bh = result.box

                # 找到这个检测结果属于哪个格子
                for r in range(grid.ROWS):
                    for c in range(grid.COLS):
                        cell = grid.cells[r][c]
                        # 如果该格子已有单位，跳过（一个格子只能有一个单位）
                        if cell.have_person:
                            continue
                        # 检查检测结果是否在格子内
                        if (
                            bx >= cell.rect.x
                            and bx + bw <= cell.rect.x + cell.rect.width
                            and by >= cell.rect.y
                            and by + bh <= cell.rect.y + cell.rect.height
                        ):
                            cell.cell_type = cell_type
                            cell.have_person = True
                            cell.unit_center = (bx + bw // 2, by + bh // 2)
                            units.append(cell)
                            break

        return units


# ========================
# 结构层：BattleGrid
# ========================


@dataclass
class BattleGrid:
    ROWS: int = 10
    COLS: int = 6
    CELL_WIDTH: int = 120
    CELL_HEIGHT: int = 120

    offset_x: int = 0
    offset_y: int = 0
    cells: List[List[Cell]] = field(default_factory=list)

    reco_processor: RecoProcessor = field(default_factory=RecoProcessor)
    self_units: List[Cell] = field(default_factory=list)
    enemy_units: List[Cell] = field(default_factory=list)
    friend_units: List[Cell] = field(default_factory=list)

    def __post_init__(self):
        if not self.cells:
            self.init_cells()
        if not self.reco_processor._initialized:
            self.reco_processor.init()

    def init_cells(self):
        """初始化网格"""
        for r in range(self.ROWS):
            row = []
            for c in range(self.COLS):
                rect = CellRect(
                    x=self.offset_x + c * self.CELL_WIDTH,
                    y=self.offset_y + r * self.CELL_HEIGHT,
                    width=self.CELL_WIDTH,
                    height=self.CELL_HEIGHT,
                )
                row.append(Cell(row=r, col=c, rect=rect))
            self.cells.append(row)

    def get_cell(self, row: int, col: int) -> Optional[Cell]:
        """获取格子"""
        if 0 <= row < self.ROWS and 0 <= col < self.COLS:
            return self.cells[row][col]
        return None

    def pixel_to_grid(self, pixel_x: int, pixel_y: int) -> Tuple[int, int]:
        """像素坐标转网格坐标"""
        col = round((pixel_x - self.offset_x) / self.CELL_WIDTH) if self.CELL_WIDTH > 0 else 0
        row = round((pixel_y - self.offset_y) / self.CELL_HEIGHT) if self.CELL_HEIGHT > 0 else 0
        return (row, col)

    def grid_to_pixel(self, row: int, col: int) -> Tuple[int, int]:
        """网格坐标转像素中心"""
        x = self.offset_x + col * self.CELL_WIDTH + self.CELL_WIDTH // 2
        y = self.offset_y + row * self.CELL_HEIGHT + self.CELL_HEIGHT // 2
        return (x, y)

    def clear_units(self):
        """清空单位列表"""
        self.self_units.clear()
        self.enemy_units.clear()
        self.friend_units.clear()

    def detect(self, context):
        """检测所有格子，更新类型和单位"""
        self.clear_units()

        # 使用 scan_all_cells 一次截图批量检测
        units = self.reco_processor.scan_all_cells(self, context)

        # 按单位类型分类到不同队列
        for unit in units:
            if unit.cell_type == CellType.SELF:
                self.self_units.append(unit)
            elif unit.cell_type == CellType.ENEMY:
                self.enemy_units.append(unit)
            elif unit.cell_type == CellType.FRIEND:
                self.friend_units.append(unit)

    def detect_threat(self, context):
        """检测威胁区域"""
        threat_regions = self.reco_processor.detect_threat_region(context)
        # 清空所有格子的威胁标记
        for r in range(self.ROWS):
            for c in range(self.COLS):
                self.cells[r][c].is_threat = False
        # 标记威胁区域内的格子
        for (bx, by, bw, bh) in threat_regions:
            for r in range(self.ROWS):
                for c in range(self.COLS):
                    cell = self.cells[r][c]
                    # 检查格子中心是否在威胁区域内
                    cx, cy = self.grid_to_pixel(r, c)
                    if bx <= cx < bx + bw and by <= cy < by + bh:
                        cell.is_threat = True

    def reset_move_attack_flags(self):
        """重置移动/攻击标记"""
        for r in range(self.ROWS):
            for c in range(self.COLS):
                self.cells[r][c].is_moveable = False
                self.cells[r][c].is_attackable = False

    def battle(self, controller_id: str, context):
        """战斗循环"""
        while self.self_units:
            cur = self.self_units.pop(0)
            self.reset_move_attack_flags()
            self.detect_round(cur, controller_id, context)
            self.battle_decision(cur, controller_id, context)

    def detect_round(self, cell: Cell, controller_id: str, context):
        """采集攻击和移动范围：点击单位后截图检测"""
        # 1. 点击选中我方单位
        cx, cy = cell.rect.center()
        from maa_mcp import click
        click(controller_id, cx, cy)

        # 2. 等待 UI 响应（攻击/移动范围显示）
        from maa_mcp import wait
        wait(1)  # 等待 1 秒

        # 3. 截图检测攻击和移动范围
        img = context.tasker.controller.post_screencap().wait().get()

        # 检测移动范围（绿色）
        self._detect_range(context, img, "move")

        # 检测攻击范围（红色）
        self._detect_range(context, img, "attack")

    def _detect_range(self, context, img, range_type: str):
        """检测攻击或移动范围"""
        node_name = f"Battle_{range_type.capitalize()}Range"
        reco = context.run_recognition(node_name, img)

        if not reco or not reco.hit or not reco.all_results:
            logger.info(f"{range_type} 范围识别未命中")
            return

        for result in reco.all_results:
            if not hasattr(result, "box") or not result.box:
                continue
            bx, by, bw, bh = result.box

            # 找到这个检测结果属于哪个格子，标记为可攻击/可移动
            for r in range(self.ROWS):
                for c in range(self.COLS):
                    cell = self.cells[r][c]
                    if (
                        bx >= cell.rect.x
                        and bx + bw <= cell.rect.x + cell.rect.width
                        and by >= cell.rect.y
                        and by + bh <= cell.rect.y + cell.rect.height
                    ):
                        if range_type == "attack":
                            cell.is_attackable = True
                        else:
                            cell.is_moveable = True
                        break

    def battle_decision(self, cell: Cell, controller_id: str, context):
        """战斗决策：攻击欧式距离最短的敌人"""
        # TODO: 实现攻击决策逻辑
        raise NotImplementedError("battle_decision 需要用户实现")

    @classmethod
    def create_default(cls, offset_x: int = 0, offset_y: int = 0) -> 'BattleGrid':
        """创建默认尺寸的网格"""
        return cls(
            ROWS=10,
            COLS=6,
            CELL_WIDTH=120,
            CELL_HEIGHT=120,
            offset_x=offset_x,
            offset_y=offset_y,
        )


# ========================
# 辅助函数
# ========================


def click_cell(controller_id: str, cell: Cell, duration: int = 50):
    """点击格子"""
    cx, cy = cell.rect.center()
    from maa_mcp import click
    click(controller_id, cx, cy)


def double_click_cell(controller_id: str, cell: Cell, duration: int = 50):
    """双击格子"""
    cx, cy = cell.rect.center()
    from maa_mcp import double_click
    double_click(controller_id, cx, cy)


def draw_battle_grid_debug(
    image: np.ndarray, grid: BattleGrid, output_path: str = None
) -> np.ndarray:
    """绘制调试图像：在截图上显示网格线和单位位置"""
    bgr = image if isinstance(image, np.ndarray) else np.array(image)

    # 绘制网格线
    for r in range(grid.ROWS + 1):
        y = grid.offset_y + r * grid.CELL_HEIGHT
        cv2.line(
            bgr,
            (grid.offset_x, y),
            (grid.offset_x + grid.COLS * grid.CELL_WIDTH, y),
            (255, 255, 0),
            1,
        )
    for c in range(grid.COLS + 1):
        x = grid.offset_x + c * grid.CELL_WIDTH
        cv2.line(
            bgr,
            (x, grid.offset_y),
            (x, grid.offset_y + grid.ROWS * grid.CELL_HEIGHT),
            (255, 255, 0),
            1,
        )

    # 绘制威胁区域
    threat_overlay = bgr.copy()
    for r in range(grid.ROWS):
        for c in range(grid.COLS):
            cell = grid.cells[r][c]
            if cell.is_threat:
                x = grid.offset_x + c * grid.CELL_WIDTH
                y = grid.offset_y + r * grid.CELL_HEIGHT
                cv2.rectangle(
                    threat_overlay,
                    (x, y),
                    (x + grid.CELL_WIDTH, y + grid.CELL_HEIGHT),
                    (0, 0, 255),
                    -1,
                )
    cv2.addWeighted(bgr, 0.7, threat_overlay, 0.3, 0, bgr)

    # 绘制单位
    unit_colors = {
        CellType.SELF: (255, 0, 0),
        CellType.ENEMY: (0, 0, 255),
        CellType.FRIEND: (0, 255, 0),
    }
    for r in range(grid.ROWS):
        for c in range(grid.COLS):
            cell = grid.cells[r][c]
            if not cell.have_person:
                continue
            color = unit_colors.get(cell.cell_type, (128, 128, 128))
            cx, cy = cell.rect.center()
            cv2.circle(bgr, (cx, cy), 5, color, -1)
            cv2.putText(
                bgr,
                f"({r},{c})",
                (cx + 10, cy - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
            )

    if output_path:
        cv2.imwrite(output_path, bgr)
        logger.info(f"调试图像已保存: {output_path}")
    return bgr


def grid_to_text_report(grid: BattleGrid) -> str:
    """生成网格识别的文本报告"""
    threat_count = sum(1 for row in grid.cells for cell in row if cell.is_threat)
    all_units = [cell for row in grid.cells for cell in row if cell.have_person]

    lines = [
        "=" * 50,
        "战场网格识别报告",
        "=" * 50,
        f"网格尺寸: {grid.COLS} 列 x {grid.ROWS} 行",
        f"格子大小: {grid.CELL_WIDTH} x {grid.CELL_HEIGHT} 像素",
        f"网格偏移: ({grid.offset_x}, {grid.offset_y})",
        "",
        f"威胁区域: {threat_count} 格子",
        f"单位数量: {len(all_units)}",
        "",
        "单位详情:",
        "-" * 30,
    ]

    type_labels = {
        CellType.SELF: "我方单位",
        CellType.ENEMY: "敌方单位",
        CellType.FRIEND: "友军单位",
    }
    for cell_type, label in type_labels.items():
        group = [u for u in all_units if u.cell_type == cell_type]
        if group:
            lines.append(f"{label} ({len(group)}):")
            for unit in group:
                lines.append(
                    f"  - 网格坐标: ({unit.row}, {unit.col}), "
                    f"像素: {unit.rect.center()}"
                )

    lines.append("=" * 50)
    return "\n".join(lines)


def main(dir_path: str, image_path: str):
    """调试主函数"""
    full_path = os.path.join(dir_path, image_path)
    debug_dir = dir_path

    print(f"读取图片: {full_path}", flush=True)
    if not os.path.exists(full_path):
        print(f"图片不存在: {full_path}", flush=True)
        return

    image = cv2.imread(full_path)
    if image is None:
        print(f"无法读取图片: {full_path}", flush=True)
        return

    print(f"图片尺寸: {image.shape}", flush=True)

    grid = BattleGrid.create_default()
    # 注意：旧 API 需要 context，这里用不了
    logger.warning("main() 需要 context 参数，请使用新的 API")
    logger.info("如需调试，请直接使用 BattleGrid.detect(context)")

    report = grid_to_text_report(grid)
    print(report, flush=True)


# ========================
# 兼容层：支持旧 API
# ========================

# 旧 API 的 UnitType 映射到新的 CellType
class UnitType(Enum):
    ALLY = "ally"
    ENEMY = "enemy"
    FRIENDLY = "friendly"


def _convert_unit_type(old_type: UnitType) -> CellType:
    """将旧 UnitType 转换为新的 CellType"""
    mapping = {
        UnitType.ALLY: CellType.SELF,
        UnitType.ENEMY: CellType.ENEMY,
        UnitType.FRIENDLY: CellType.FRIEND,
    }
    return mapping.get(old_type, CellType.NONE)


def _convert_cell_type(new_type: CellType) -> UnitType:
    """将新的 CellType 转换为旧 UnitType"""
    mapping = {
        CellType.SELF: UnitType.ALLY,
        CellType.ENEMY: UnitType.ENEMY,
        CellType.FRIEND: UnitType.FRIENDLY,
    }
    return mapping.get(new_type, UnitType.ALLY)


@dataclass
class GridPosition:
    """兼容层：保留旧 API 的 GridPosition"""
    row: int
    col: int
    x: int
    y: int


@dataclass
class Unit:
    """兼容层：保留旧 API 的 Unit 类"""
    unit_type: UnitType
    grid_pos: GridPosition
    pixel_box: List[int] = field(default_factory=list)


class BattleGridRecognizer:
    """兼容层：保留 BattleGridRecognizer 接口"""

    def __init__(self, is_opencv: bool = True):
        self.is_opencv = is_opencv
        self.detect_only_units = True
        self.grid: Optional[BattleGrid] = None
        self.debug_dir: str = ""

    def recognize(self, image, debug_dir: str = "", context=None):
        """兼容层的识别方法"""
        if context is None:
            raise ValueError("BattleGridRecognizer 需要 context 参数")

        self.debug_dir = debug_dir

        # 创建 BattleGrid
        self.grid = BattleGrid.create_default()

        # 检测单位
        self.grid.detect(context)

        return self.grid

    def _convert_units(self):
        """将新的 Cell 转换为旧的 Unit"""
        if self.grid is None:
            return []

        units = []
        for r in range(self.grid.ROWS):
            for c in range(self.grid.COLS):
                cell = self.grid.cells[r][c]
                if cell.have_person:
                    unit_type = _convert_cell_type(cell.cell_type)
                    grid_pos = GridPosition(
                        row=cell.row,
                        col=cell.col,
                        x=cell.unit_center[0],
                        y=cell.unit_center[1],
                    )
                    pixel_box = cell.rect.to_box()
                    units.append(Unit(unit_type=unit_type, grid_pos=grid_pos, pixel_box=pixel_box))
        return units
