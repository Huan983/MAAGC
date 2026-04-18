"""战场网格与单位识别模块 - 通过红色威胁区域推断网格结构，识别单位位置"""

import os
import sys
import cv2
import numpy as np
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set, Tuple, Optional
from PIL import Image

current_file_path = os.path.abspath(__file__)
current_script_dir = os.path.dirname(current_file_path)
agent_dir = os.path.dirname(os.path.dirname(current_script_dir))
project_root_dir = os.path.dirname(agent_dir)

if os.getcwd() != project_root_dir:
    os.chdir(project_root_dir)
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

from utils import logger


class UnitType(Enum):
    ALLY = "ally"
    ENEMY = "enemy"
    FRIENDLY = "friendly"


@dataclass
class GridPosition:
    row: int
    col: int
    x: int
    y: int


@dataclass
class Unit:
    unit_type: UnitType
    grid_pos: GridPosition
    hp: int = 0
    pixel_box: List[int] = None

    def __post_init__(self):
        if self.pixel_box is None:
            self.pixel_box = []


@dataclass
class BattleGrid:
    cell_width: int = 0
    cell_height: int = 0
    offset_x: int = 0
    offset_y: int = 0
    total_rows: int = 0
    total_cols: int = 0
    units: List[Unit] = field(default_factory=list)
    threat_cells: Set[Tuple[int, int]] = field(default_factory=set)

    def pixel_to_grid(self, pixel_x: int, pixel_y: int) -> Tuple[int, int]:
        col = (
            round((pixel_x - self.offset_x) / self.cell_width)
            if self.cell_width > 0
            else 0
        )
        row = (
            round((pixel_y - self.offset_y) / self.cell_height)
            if self.cell_height > 0
            else 0
        )
        return (row, col)

    def grid_to_pixel(self, row: int, col: int) -> Tuple[int, int]:
        pixel_x = self.offset_x + col * self.cell_width + self.cell_width // 2
        pixel_y = self.offset_y + row * self.cell_height + self.cell_height // 2
        return (pixel_x, pixel_y)

    def is_valid_cell(self, row: int, col: int) -> bool:
        return 0 <= row < self.total_rows and 0 <= col < self.total_cols

    def is_threat_cell(self, row: int, col: int) -> bool:
        return (row, col) in self.threat_cells


@dataclass
class DetectedCell:
    x: int
    y: int
    width: int
    height: int
    grid_row: int = 0
    grid_col: int = 0
    score: int = 0


class BattleGridRecognizer:
    BLOOD_COLORS = {
        UnitType.ALLY: {
            "lower": np.array([200, 140, 0]),
            "upper": np.array([255, 200, 50]),
        },
        UnitType.ENEMY: {
            "lower": np.array([20, 0, 180]),
            "upper": np.array([80, 60, 255]),
        },
        UnitType.FRIENDLY: {
            "lower": np.array([100, 200, 100]),
            "upper": np.array([180, 255, 180]),
        },
    }

    CELL_SIZE = 105
    UI_BOTTOM_MARGIN = 100
    THREAT_RED_HSV = {
        "lower": np.array([6, 150, 91]),
        "upper": np.array([18, 181, 162]),
    }

    def __init__(self):
        self.grid: Optional[BattleGrid] = None
        self.debug_dir: str = ""

    def detect_grid_from_threat(
        self, image: Image.Image, debug_dir: str = ""
    ) -> BattleGrid:
        self.debug_dir = debug_dir
        img_array = np.array(image)
        bgr_array = img_array[:, :, ::-1]

        threat_mask = self._detect_threat_region(bgr_array)

        if self.debug_dir:
            os.makedirs(self.debug_dir, exist_ok=True)
            cv2.imwrite(
                os.path.join(self.debug_dir, "debug_threat_mask.png"), threat_mask
            )

        detected_cells = self._detect_cells_from_hough(threat_mask)
        base_cell = self._select_base_cell(detected_cells)
        grid = self._build_grid_from_base(base_cell, img_array.shape)
        grid = self._identify_threat_cells(grid, threat_mask)

        self.grid = grid
        logger.info(
            f"网格检测完成: {grid.total_cols}x{grid.total_rows}, "
            f"格子尺寸: {grid.cell_width}x{grid.cell_height}"
        )
        return grid

    def _detect_threat_region(self, bgr_array: np.ndarray) -> np.ndarray:
        hsv_array = cv2.cvtColor(bgr_array, cv2.COLOR_BGR2HSV)
        lower = self.THREAT_RED_HSV["lower"]
        upper = self.THREAT_RED_HSV["upper"]
        mask = cv2.inRange(hsv_array, lower, upper)
        logger.info(
            f"THREAT_RED_HSV lower={lower}, upper={upper}, 匹配像素数={np.count_nonzero(mask)}"
        )
        return mask

    def _detect_cells_from_hough(self, threat_mask: np.ndarray) -> List[DetectedCell]:
        binary_mask = (threat_mask > 0).astype(np.uint8) * 255
        edges = cv2.Canny(binary_mask, 50, 150)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, 50, minLineLength=30, maxLineGap=10
        )

        detected_cells = []

        if lines is not None:
            h_lines, v_lines = [], []

            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle_deg = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                angle_deg = min(angle_deg, 180 - angle_deg)

                if angle_deg <= 10:
                    h_lines.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
                elif abs(angle_deg - 90) <= 10:
                    v_lines.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))

            cs = self.CELL_SIZE
            for hx1, hy1, hx2, _ in h_lines:
                for vx1, _, _, vy2 in v_lines:
                    w, h = hx2 - hx1, vy2 - hy1
                    if cs - 5 <= w <= cs + 5 and cs - 5 <= h <= cs + 5:
                        detected_cells.append(
                            DetectedCell(x=vx1, y=hy1, width=w, height=h, score=1)
                        )

        if not detected_cells:
            logger.info("霍夫未检测到格子，尝试从威胁区域像素分布推断")
            detected_cells = self._detect_cells_from_mask_area(threat_mask)

        logger.info(f"共检测到 {len(detected_cells)} 个符合{self.CELL_SIZE}±5的格子")
        return detected_cells

    def _detect_cells_from_mask_area(
        self, threat_mask: np.ndarray
    ) -> List[DetectedCell]:
        rows, cols = np.where(threat_mask > 0)
        if len(rows) == 0:
            return []

        min_y, max_y = np.min(rows), np.max(rows)
        min_x, max_x = np.min(cols), np.max(cols)
        logger.info(f"威胁区域边界: x[{min_x}, {max_x}], y[{min_y}, {max_y}]")

        est_cols = max(1, round((max_x - min_x) / self.CELL_SIZE))
        est_rows = max(1, round((max_y - min_y) / self.CELL_SIZE))
        logger.info(f"推断网格: {est_cols}列 x {est_rows}行")

        cs = self.CELL_SIZE
        return [
            DetectedCell(
                x=min_x + col * cs, y=min_y + row * cs, width=cs, height=cs, score=1
            )
            for row in range(est_rows)
            for col in range(est_cols)
        ]

    def _select_base_cell(self, detected_cells: List[DetectedCell]) -> DetectedCell:
        if not detected_cells:
            logger.info(f"未检测到格子，使用默认{self.CELL_SIZE}x{self.CELL_SIZE}基准")
            return DetectedCell(
                x=50, y=200, width=self.CELL_SIZE, height=self.CELL_SIZE, score=0
            )

        sorted_cells = sorted(detected_cells, key=lambda c: c.score, reverse=True)
        top3 = sorted_cells[:3]
        logger.info(f"Top3格子: {[(c.x, c.y, c.width, c.height) for c in top3]}")

        base_cell = top3[0]
        logger.info(
            f"选择基准格子: ({base_cell.x}, {base_cell.y}), {base_cell.width}x{base_cell.height}"
        )
        return base_cell

    def _build_grid_from_base(
        self, base_cell: DetectedCell, img_shape: Tuple[int, ...]
    ) -> BattleGrid:
        """
        基于基准格子向四个方向逐步扩展生成完整网格

        扩展流程：
        1. 从基准格子向左逐步扩展，直到触碰左边界 → 记录左方列数
        2. 从基准格子向右逐步扩展，直到触碰右边界 → 记录右方列数
        3. 一行格子数 = 左方列数 + 1(基准) + 右方列数
        4. 从基准格子向上逐步扩展，直到触碰上边界 → 记录上方行数
        5. 从基准格子向下逐步扩展，直到触碰下边界 → 记录下方行数
        6. 一列格子数 = 上方行数 + 1(基准) + 下方行数
        7. 基于行数和列数一次性生成完整网格矩阵

        Args:
            base_cell: 基准格子
            img_shape: 图像尺寸

        Returns:
            BattleGrid 对象
        """
        height, width = img_shape[0], img_shape[1]
        cs = self.CELL_SIZE

        cols_left = 0
        x = base_cell.x - cs
        while x >= 0:
            cols_left += 1
            x -= cs

        cols_right = 0
        x = base_cell.x + cs
        while x + cs <= width:
            cols_right += 1
            x += cs

        rows_up = 0
        y = base_cell.y - cs
        while y >= 0:
            rows_up += 1
            y -= cs

        rows_down = 0
        y = base_cell.y + cs
        while y + cs <= height - self.UI_BOTTOM_MARGIN:
            rows_down += 1
            y += cs

        total_cols = cols_left + 1 + cols_right
        total_rows = rows_up + 1 + rows_down
        offset_x = base_cell.x - cols_left * cs
        offset_y = base_cell.y - rows_up * cs

        base_cell.grid_row = rows_up
        base_cell.grid_col = cols_left

        logger.info(
            f"行扩展: ←左{cols_left}格 + 基准 + 右{cols_right}格→ = 一行{total_cols}格"
        )
        logger.info(
            f"列扩展: ↑上{rows_up}格 + 基准 + 下{rows_down}格↓ = 一列{total_rows}格"
        )
        logger.info(
            f"网格矩阵: {total_cols}列x{total_rows}行, "
            f"起始偏移({offset_x}, {offset_y}), "
            f"基准格子位于(row={base_cell.grid_row}, col={base_cell.grid_col})"
        )

        all_cells = self._expand_grid_cells(total_rows, total_cols, offset_x, offset_y)

        if self.debug_dir:
            self._draw_debug_overlay(all_cells, base_cell)

        return BattleGrid(
            cell_width=cs,
            cell_height=cs,
            offset_x=offset_x,
            offset_y=offset_y,
            total_rows=total_rows,
            total_cols=total_cols,
        )

    def _expand_grid_cells(
        self, total_rows: int, total_cols: int, offset_x: int, offset_y: int
    ) -> List[DetectedCell]:
        cs = self.CELL_SIZE
        return [
            DetectedCell(
                x=offset_x + col * cs,
                y=offset_y + row * cs,
                width=cs,
                height=cs,
                grid_row=row,
                grid_col=col,
                score=0,
            )
            for row in range(total_rows)
            for col in range(total_cols)
        ]

    def _draw_debug_overlay(
        self, all_cells: List[DetectedCell], base_cell: DetectedCell
    ) -> None:
        """
        在调试图像上绘制所有格子

        Args:
            all_cells: 所有格子的列表
            base_cell: 基准格子（跳过绘制，由_draw_base_cell_marker单独标记）
        """
        debug_img_path = os.path.join(self.debug_dir, "debug_threat_mask.png")
        if not os.path.exists(debug_img_path):
            return

        img = cv2.imread(debug_img_path)
        if img is None:
            return

        for cell in all_cells:
            is_base = (
                cell.grid_row == base_cell.grid_row
                and cell.grid_col == base_cell.grid_col
            )

            if is_base:
                cx = cell.x + cell.width // 2
                cy = cell.y + cell.height // 2
                size = 30
                color = (0, 255, 255)
                cv2.line(img, (cx - size, cy - size), (cx + size, cy + size), color, 3)
                cv2.line(img, (cx + size, cy - size), (cx - size, cy + size), color, 3)
                cv2.circle(img, (cx, cy), size // 2, color, 2)
                cv2.putText(
                    img,
                    f"BASE({cell.grid_row},{cell.grid_col})",
                    (cx - 40, cy - size - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                )
            else:
                x1, y1 = cell.x, cell.y
                x2, y2 = cell.x + cell.width, cell.y + cell.height
                color = (100, 100, 100)
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 1)
                cv2.putText(
                    img,
                    f"({cell.grid_row},{cell.grid_col})",
                    (x1 + 2, y1 + 15),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    color,
                    1,
                )

        cv2.imwrite(debug_img_path, img)
        logger.info(f"调试覆盖已绘制: {debug_img_path}, 共{len(all_cells)}个格子")

    def _identify_threat_cells(
        self, grid: BattleGrid, threat_mask: np.ndarray
    ) -> BattleGrid:
        """识别威胁区域格子"""
        threat_cells = set()
        mask_h, mask_w = threat_mask.shape[:2]
        for row in range(grid.total_rows):
            for col in range(grid.total_cols):
                cx, cy = grid.grid_to_pixel(row, col)
                if 0 <= cx < mask_w and 0 <= cy < mask_h and threat_mask[cy, cx] > 0:
                    threat_cells.add((row, col))
        grid.threat_cells = threat_cells
        logger.info(f"识别到 {len(grid.threat_cells)} 个威胁格子")
        return grid

    def scan_units(self, image: Image.Image) -> List[Unit]:
        """
        扫描血条识别单位

        Args:
            image: PIL Image对象

        Returns:
            Unit 列表
        """
        if self.grid is None:
            logger.error("请先调用 detect_grid_from_threat()")
            return []

        bgr_array = np.array(image)[:, :, ::-1]
        units = []
        for unit_type in self.BLOOD_COLORS:
            units.extend(self._scan_blood_color(bgr_array, unit_type))

        self.grid.units = units
        logger.info(f"识别到 {len(units)} 个单位")
        for unit in units:
            logger.debug(
                f"  - {unit.unit_type.value}: "
                f"网格({unit.grid_pos.row}, {unit.grid_pos.col}), "
                f"像素({unit.grid_pos.x}, {unit.grid_pos.y})"
            )
        return units

    def _scan_blood_color(
        self, bgr_array: np.ndarray, unit_type: UnitType
    ) -> List[Unit]:
        color_config = self.BLOOD_COLORS[unit_type]
        mask = cv2.inRange(bgr_array, color_config["lower"], color_config["upper"])
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        units = []
        for contour in contours:
            if cv2.contourArea(contour) < 50:
                continue

            x, y, w, h = cv2.boundingRect(contour)
            center_x = x + w // 2
            center_y = y + h // 2
            row, col = self.grid.pixel_to_grid(center_x, center_y)
            grid_pos = GridPosition(row=row, col=col, x=center_x, y=center_y)
            units.append(
                Unit(unit_type=unit_type, grid_pos=grid_pos, pixel_box=[x, y, w, h])
            )

        return units

    def recognize(self, image: Image.Image, debug_dir: str = "") -> BattleGrid:
        """
        完整的战场识别流程

        Args:
            image: PIL Image对象
            debug_dir: 调试图片保存目录

        Returns:
            BattleGrid 对象（包含网格和单位信息）
        """
        logger.info("开始战场识别...")
        grid = self.detect_grid_from_threat(image, debug_dir)
        units = self.scan_units(image)
        grid.units = units

        counts = {t: sum(1 for u in units if u.unit_type == t) for t in UnitType}
        logger.info("战场识别完成:")
        logger.info(f"  - 我方单位: {counts[UnitType.ALLY]}")
        logger.info(f"  - 敌方单位: {counts[UnitType.ENEMY]}")
        logger.info(f"  - 友军单位: {counts[UnitType.FRIENDLY]}")
        logger.info(f"  - 威胁区域: {len(grid.threat_cells)} 格子")
        return grid


def draw_battle_grid_debug(
    image: Image.Image, grid: BattleGrid, output_path: str = None
) -> Image.Image:
    """
    绘制调试图像：在截图上显示网格线和单位位置

    Args:
        image: 原始截图
        grid: 识别出的战场网格
        output_path: 输出路径（可选）

    Returns:
        绘制了调试信息的图像
    """
    if cv2 is None:
        logger.error("opencv-python 未安装，无法生成调试图像")
        return image

    # 转换为 OpenCV 格式 (BGR)
    img_array = np.array(image)
    bgr_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

    for row in range(grid.total_rows + 1):
        y = grid.offset_y + row * grid.cell_height
        cv2.line(
            bgr_array,
            (grid.offset_x, y),
            (grid.offset_x + grid.total_cols * grid.cell_width, y),
            (255, 255, 0),
            1,
        )

    for col in range(grid.total_cols + 1):
        x = grid.offset_x + col * grid.cell_width
        cv2.line(
            bgr_array,
            (x, grid.offset_y),
            (x, grid.offset_y + grid.total_rows * grid.cell_height),
            (255, 255, 0),
            1,
        )

    threat_overlay = bgr_array.copy()
    for row, col in grid.threat_cells:
        x = grid.offset_x + col * grid.cell_width
        y = grid.offset_y + row * grid.cell_height
        cv2.rectangle(
            threat_overlay,
            (x, y),
            (x + grid.cell_width, y + grid.cell_height),
            (0, 0, 255),
            -1,
        )
    cv2.addWeighted(bgr_array, 0.7, threat_overlay, 0.3, 0, bgr_array)

    unit_colors = {
        UnitType.ALLY: (255, 0, 0),
        UnitType.ENEMY: (0, 0, 255),
        UnitType.FRIENDLY: (0, 255, 0),
    }
    for unit in grid.units:
        color = unit_colors[unit.unit_type]
        if unit.pixel_box:
            x, y, w, h = unit.pixel_box
            cv2.rectangle(bgr_array, (x, y), (x + w, y + h), color, 2)
        cv2.circle(bgr_array, (unit.grid_pos.x, unit.grid_pos.y), 5, color, -1)
        cv2.putText(
            bgr_array,
            f"({unit.grid_pos.row},{unit.grid_pos.col})",
            (unit.grid_pos.x + 10, unit.grid_pos.y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
        )

    result_image = Image.fromarray(cv2.cvtColor(bgr_array, cv2.COLOR_BGR2RGB))
    if output_path:
        result_image.save(output_path)
        logger.info(f"调试图像已保存到: {output_path}")
    return result_image


def grid_to_text_report(grid: BattleGrid) -> str:
    """
    生成网格识别的文本报告

    Args:
        grid: 识别出的战场网格

    Returns:
        格式化的文本报告
    """
    lines = [
        "=" * 50,
        "战场网格识别报告",
        "=" * 50,
        f"网格尺寸: {grid.total_cols} 列 x {grid.total_rows} 行",
        f"格子大小: {grid.cell_width} x {grid.cell_height} 像素",
        f"网格偏移: ({grid.offset_x}, {grid.offset_y})",
        "",
        f"威胁区域: {len(grid.threat_cells)} 格子",
        f"单位数量: {len(grid.units)}",
        "",
        "单位详情:",
        "-" * 30,
    ]

    type_labels = {
        UnitType.ALLY: "我方单位",
        UnitType.ENEMY: "敌方单位",
        UnitType.FRIENDLY: "友军单位",
    }
    for unit_type, label in type_labels.items():
        group = [u for u in grid.units if u.unit_type == unit_type]
        if group:
            lines.append(f"{label} ({len(group)}):")
            for unit in group:
                lines.append(
                    f"  - 网格坐标: ({unit.grid_pos.row}, {unit.grid_pos.col}), "
                    f"像素: ({unit.grid_pos.x}, {unit.grid_pos.y})"
                )

    lines.append("=" * 50)
    return "\n".join(lines)


def main(dir_path: str, image_path: str):
    """
    调试主函数：读取图片，识别网格和单位，输出调试图像

    Args:
        dir_path: 测试图片所在文件夹路径
        image_path: 测试图片文件名
    """
    import cv2
    import os

    full_image_path = os.path.join(dir_path, image_path)
    debug_dir = dir_path

    print(f"读取图片: {full_image_path}", flush=True)
    if not os.path.exists(full_image_path):
        print(f"图片文件不存在: {full_image_path}", flush=True)
        return

    image = cv2.imread(full_image_path)
    if image is None:
        print(f"无法读取图片: {full_image_path}", flush=True)
        return

    print(f"图片读取成功，尺寸: {image.shape}", flush=True)
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    print("开始识别...", flush=True)
    recognizer = BattleGridRecognizer()
    grid = recognizer.recognize(pil_image, debug_dir)

    output_path = os.path.join(debug_dir, image_path.rsplit(".", 1)[0] + "_debug.png")
    print(f"生成调试图像: {output_path}", flush=True)
    draw_battle_grid_debug(pil_image, grid, output_path)

    report = grid_to_text_report(grid)
    print(report, flush=True)
    print(f"\n调试图像已保存到: {output_path}", flush=True)


if __name__ == "__main__":
    TEST_DIR_PATH = r"F:\workspace\MAAGC\assets\resource\base\image\Fight"
    TEST_IMAGE_PATH = r"1.png"
    main(TEST_DIR_PATH, TEST_IMAGE_PATH)
