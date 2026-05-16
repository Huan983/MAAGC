"""战场网格与单位识别模块 - 专注于识别层"""

import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional
from maa.context import Context, RecognitionDetail
from utils import logger

from typing import Any

current_file_path = os.path.abspath(__file__)
current_script_dir = os.path.dirname(current_file_path)
agent_dir = os.path.dirname(os.path.dirname(current_script_dir))
project_root_dir = os.path.dirname(agent_dir)

if os.getcwd() != project_root_dir:
    os.chdir(project_root_dir)
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

# ========================
# 数据层：Cell + CellRect
# ========================
ROWS: int = 10
COLS: int = 6
CELL_WIDTH: int = 120
CELL_HEIGHT: int = 120


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
    unit_center: Tuple[int, int] = field(default=(0, 0))
    is_moveable: bool = False
    is_attackable: bool = False


# ========================
# 识别层：GridScanner
# ========================


class GridScanner:
    """战场网格识别器：负责扫描所有格子，识别单位类型和可攻击/可移动范围"""

    _instance = None

    UNIT_NODES = {
        CellType.SELF: "Battle_UnitScan_Blue",
        CellType.ENEMY: "Battle_UnitScan_Red",
        CellType.FRIEND: "Battle_UnitScan_Green",
    }

    def __new__(cls) -> "GridScanner":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def init(self) -> None:
        self._initialized = True
        logger.info("GridScanner 初始化完成")

    def scan_grid(self, grid: "BattleGrid", context: Context) -> None:
        """扫描整个网格，识别所有格子中的单位类型"""
        img = context.tasker.controller.post_screencap().wait().get()

        all_results: List[Tuple[CellType, Any]] = []

        for cell_type, node_name in self.UNIT_NODES.items():
            reco: RecognitionDetail = context.run_recognition(node_name, img)
            if reco.hit and reco.filtered_results:
                for result in reco.filtered_results:
                    all_results.append((cell_type, result))

        # 统一处理所有识别结果，避免因 return 提前退出导致漏检
        for cell_type, result in all_results:
            cell_row = result.box[1] // CELL_HEIGHT
            cell_col = result.box[0] // CELL_WIDTH
            if 0 <= cell_row < ROWS and 0 <= cell_col < COLS:
                cell = grid.cells[cell_row][cell_col]
                cell.cell_type = cell_type
                cell.have_person = True
                # 保存识别到的实际中心位置，而不是格子中心
                unit_center_x = result.box[0] + result.box[2] // 2
                unit_center_y = result.box[1] + result.box[3] // 2
                cell.unit_center = (unit_center_x, unit_center_y)

    def _detect_cell(self, cell: Cell, img: Any, context: Context):
        """截取单个格子图片并检测单位类型"""
        cell_img = img[
            cell.rect.y : cell.rect.y + cell.rect.height,
            cell.rect.x : cell.rect.x + cell.rect.width,
        ]

        for cell_type, node_name in self.UNIT_NODES.items():
            reco: RecognitionDetail = context.run_recognition(node_name, cell_img)
            if reco.hit and reco.filtered_results:
                cell.cell_type = cell_type
                cell.have_person = True
                return

        cell.cell_type = CellType.NONE
        cell.have_person = False

    def scan_ranges(self, grid: "BattleGrid", context: Context) -> None:
        """扫描攻击/移动范围并标记到格子"""
        img = context.tasker.controller.post_screencap().wait().get()

        # 检测攻击范围（红色）
        self._detect_range(grid, img, "attack", context)
        # 检测移动范围（绿色）
        self._detect_range(grid, img, "move", context)

    def _detect_range(
        self, grid: "BattleGrid", img: Any, range_type: str, context: Context
    ):
        """检测并标记某种范围"""
        node_name = f"Battle_{range_type.capitalize()}Range"
        reco = context.run_recognition(node_name, img)

        if not reco.hit or not reco.filtered_results:
            logger.info(f"{range_type} 范围识别未命中")
            return

        for result in reco.filtered_results:
            # 找到检测结果对应的格子
            cell_row = result.box[1] // CELL_HEIGHT
            cell_col = result.box[0] // CELL_WIDTH
            cell = grid.cells[cell_row][cell_col]

            if range_type == "attack":
                cell.is_attackable = True
            else:
                cell.is_moveable = True


# ========================
# 结构层：BattleGrid
# ========================
@dataclass
class BattleGrid:
    """战场网格：只包含数据结构，提供格子访问接口"""

    cells: List[List[Cell]] = field(
        default_factory=lambda: [
            [
                Cell(
                    row=r,
                    col=c,
                    rect=CellRect(
                        x=c * CELL_WIDTH,
                        y=r * CELL_HEIGHT,
                        width=CELL_WIDTH,
                        height=CELL_HEIGHT,
                    ),
                )
                for c in range(6)
            ]
            for r in range(10)
        ]
    )

    @property
    def self_units(self) -> List[Cell]:
        return [
            cell
            for row in self.cells
            for cell in row
            if cell.cell_type == CellType.SELF and cell.have_person
        ]

    @property
    def enemy_units(self) -> List[Cell]:
        return [
            cell
            for row in self.cells
            for cell in row
            if cell.cell_type == CellType.ENEMY and cell.have_person
        ]

    @property
    def friend_units(self) -> List[Cell]:
        return [
            cell
            for row in self.cells
            for cell in row
            if cell.cell_type == CellType.FRIEND and cell.have_person
        ]

    def reset_flags(self) -> None:
        """重置所有格子的移动/攻击标记"""
        for row in self.cells:
            for cell in row:
                cell.is_moveable = False
                cell.is_attackable = False

    def get_cell(self, row: int, col: int) -> Optional[Cell]:
        if 0 <= row < ROWS and 0 <= col < COLS:
            return self.cells[row][col]
        return None
