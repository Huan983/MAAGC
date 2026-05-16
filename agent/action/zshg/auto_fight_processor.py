from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from utils import logger
import time

from .battle_grid import BattleGrid, Cell, CellType, GridScanner, ROWS, COLS


class FightPhase(Enum):
    DETECTION = "detection"
    ACTION = "action"


@dataclass
class CharacterState:
    cell: Cell
    has_acted: bool = False


@AgentServer.custom_action("AutoFightProcessor")
class AutoFightProcessor(CustomAction):
    """处理战斗相关任务"""

    def __init__(self) -> None:
        super().__init__()
        self.scanner = GridScanner()

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        """战斗主流程"""

        phase = FightPhase.DETECTION
        grid: Optional[BattleGrid] = None
        allies: List[CharacterState] = []
        current_ally_index = 0

        while True:
            if context.tasker.stopping:
                logger.info("任务执行被停止")
                break

            if phase == FightPhase.DETECTION:
                logger.info("=== 检测阶段 ===")

                if grid is None:
                    grid = BattleGrid()

                # 扫描所有格子识别单位
                self.scanner.scan_grid(grid, context)

                logger.info(f"战场识别: {COLS}x{ROWS} 网格")

                allies = [
                    CharacterState(cell=cell, has_acted=False)
                    for cell in grid.self_units
                ]
                logger.info(f"我方角色: {len(allies)}")

                if not allies:
                    logger.info("没有我方角色，结束")
                    break

                phase = FightPhase.ACTION
                current_ally_index = 0

            elif phase == FightPhase.ACTION:
                logger.info("=== 行动阶段 ===")

                if context.tasker.stopping:
                    break

                # 找到下一个未行动的角色
                current_ally = None
                for i in range(current_ally_index, len(allies)):
                    if not allies[i].has_acted:
                        current_ally = allies[i]
                        current_ally_index = i
                        break

                if current_ally is None:
                    logger.info("所有角色已行动完毕，点击结束回合")

                    # ============================================================
                    # ⑲ 等待敌方回合 - 点击结束回合按钮让敌方行动
                    # ============================================================
                    context.run_task("FightEndRound")
                    time.sleep(8)  # 敌方行动时间

                    # ============================================================
                    # 22 下一回合，回到检测阶段
                    # ============================================================
                    phase = FightPhase.DETECTION
                    continue

                ally_cell = current_ally.cell
                logger.info(
                    f"选择角色 {current_ally_index}: grid=({ally_cell.row},{ally_cell.col})"
                )

                # 1. 点击我方单位（用实际识别到的单位位置）
                if ally_cell.unit_center != (0, 0):
                    click_x, click_y = ally_cell.unit_center
                else:
                    click_x, click_y = ally_cell.rect.center()
                logger.info(f"点击我方坐标: ({click_x}, {click_y})")
                self._click_unit_and_wait(context, click_x, click_y)

                # 2. 扫描攻击/移动范围
                grid.reset_flags()
                self.scanner.scan_ranges(grid, context)

                # ============================================================
                # ⑥ 构建统一矩阵（合并检测+范围）
                # ============================================================
                matrix_lines = []
                for r in range(ROWS):
                    row_vals = []
                    for c in range(COLS):
                        cell = grid.cells[r][c]

                        # 确定基础标记
                        if r == ally_cell.row and c == ally_cell.col:
                            base = "A"  # 当前选中
                        elif cell.cell_type == CellType.ENEMY:
                            base = "E"
                        elif cell.cell_type == CellType.FRIEND:
                            base = "F"
                        elif cell.cell_type == CellType.SELF:
                            base = "S"
                        elif cell.have_person:
                            base = "?"
                        else:
                            base = "0"

                        # 叠加范围标记
                        marker = base
                        if cell.is_attackable:
                            marker += "1"
                        if cell.is_moveable:
                            marker += "2"

                        row_vals.append(marker)
                    matrix_lines.append(" ".join(row_vals))
                logger.info(
                    f"统一矩阵 (A=当前, E=敌人, F=友军, S=我方, 1=可攻击, 2=可移动):\n"
                    + "\n".join(matrix_lines)
                )

                # ============================================================
                # ⑬ 决策执行: 攻击 > 移动 > 待机
                # ============================================================

                # 攻击目标: cell_type==ENEMY 且 is_attackable==True (即 E1)
                attack_targets = [
                    (r, c)
                    for r in range(ROWS)
                    for c in range(COLS)
                    if grid.cells[r][c].cell_type == CellType.ENEMY
                    and grid.cells[r][c].is_attackable
                ]
                logger.info(f"可攻击敌人位置(E1): {attack_targets}")

                if attack_targets:
                    # 选择最近的敌人攻击
                    target_row, target_col = min(
                        attack_targets,
                        key=lambda p: abs(p[0] - ally_cell.row)
                        + abs(p[1] - ally_cell.col),
                    )
                    target_cell = grid.cells[target_row][target_col]
                    logger.info(f"攻击目标格子: ({target_cell.row}, {target_cell.col})")
                    self._attack_cell(context, target_cell)
                    context.run_task("Battle_Cancel")
                    current_ally.has_acted = True
                else:
                    # 移动目标: is_moveable 且空白 (即 2)
                    move_targets = [
                        (r, c)
                        for r in range(ROWS)
                        for c in range(COLS)
                        if grid.cells[r][c].is_moveable
                        and not grid.cells[r][c].have_person
                    ]
                    logger.info(f"可移动空白位置(2): {move_targets}")

                    if not move_targets:
                        logger.info("没有可移动位置，原地待机")
                        context.run_task("Battle_Cancel")
                        current_ally.has_acted = True
                    else:
                        # 推断敌人位置: 所有 ENEMY 格子
                        enemy_positions = {
                            (r, c)
                            for r in range(ROWS)
                            for c in range(COLS)
                            if grid.cells[r][c].cell_type == CellType.ENEMY
                        }

                        best_cell = None
                        best_score = float("inf")

                        for r, c in move_targets:
                            cell = grid.cells[r][c]
                            if enemy_positions:
                                min_dist = min(
                                    abs(r - er) + abs(c - ec)
                                    for er, ec in enemy_positions
                                )
                            else:
                                min_dist = float("inf")

                            if min_dist < best_score:
                                best_score = min_dist
                                best_cell = cell

                        if best_cell:
                            logger.info(f"移动到 ({best_cell.row}, {best_cell.col})")
                            self._move_to_cell(context, best_cell)
                            context.run_task("Battle_Cancel")
                        else:
                            logger.info("找不到合适的移动位置，原地待机")
                            context.run_task("Battle_Cancel")

                        current_ally.has_acted = True

                current_ally_index += 1

        logger.info("战斗流程结束")
        return CustomAction.RunResult(success=True)

    def _click_unit_and_wait(self, context: Context, x: int, y: int) -> None:
        context.tasker.controller.post_click(x, y).wait()
        time.sleep(1.0)

    def _move_to_cell(self, context: Context, cell: Cell) -> None:
        """移动到指定格子（双击），使用实际位置或有人的位置"""
        if cell.unit_center != (0, 0):
            x, y = cell.unit_center
        else:
            x, y = cell.rect.center()
        logger.info(f"移动点击: ({cell.row}, {cell.col}) -> ({x}, {y})")
        context.tasker.controller.post_click(x, y).wait()
        context.tasker.controller.post_click(x, y).wait()
        time.sleep(1)

    def _attack_cell(self, context: Context, cell: Cell) -> None:
        """攻击指定格子（双击），使用实际位置或有人的位置"""
        if cell.unit_center != (0, 0):
            x, y = cell.unit_center
        else:
            x, y = cell.rect.center()
        logger.info(f"攻击点击: ({cell.row}, {cell.col}) -> ({x}, {y})")
        context.tasker.controller.post_click(x, y).wait()
        context.tasker.controller.post_click(x, y).wait()
        time.sleep(1)
