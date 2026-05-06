import numpy as np
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from utils import logger

from .battle_grid import BattleGrid, Cell, CellType


# 右上角空白区域（取消选择）
CANCEL_AREA = (600, 0, 100, 100)


class FightPhase(Enum):
    DETECTION = "detection"
    ACTION = "action"


@dataclass
class CharacterState:
    """角色状态"""
    cell: Cell
    has_acted: bool = False


@AgentServer.custom_action("AutoFightProcessor")
class AutoFightProcessor(CustomAction):
    """处理战斗相关任务"""

    def __init__(self) -> None:
        super().__init__()

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
                # ===== 检测阶段 =====
                logger.info("=== 检测阶段 ===")

                # 创建 BattleGrid（默认 10x6 网格）
                if grid is None:
                    grid = BattleGrid.create_default()

                # 检测所有格子中的单位
                grid.detect(context)

                logger.info(f"战场识别: {grid.COLS}x{grid.ROWS} 网格")

                # 构建我方角色列表
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
                # ===== 行动阶段 =====
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
                    logger.info("所有角色已行动完毕，本回合结束")
                    phase = FightPhase.DETECTION
                    continue

                ally_cell = current_ally.cell
                logger.info(
                    f"选择角色 {current_ally_index}: grid=({ally_cell.row},{ally_cell.col})"
                )

                # 1. 点击我方单位
                click_x, click_y = ally_cell.rect.center()
                logger.info(f"点击我方坐标: ({click_x}, {click_y})")
                self._click_unit_and_wait(context, click_x, click_y)

                # 2. 截图检测攻击/移动范围
                self._scan_range(context, grid)

                # 3. 判断可攻击的敌人格子
                attackable_cells = [
                    cell
                    for cell in grid.enemy_units
                    if cell.is_attackable
                ]

                if attackable_cells:
                    # 能攻击 - 找距离最近的敌人进行攻击
                    target_cell = min(
                        attackable_cells,
                        key=lambda c: abs(c.row - ally_cell.row) + abs(c.col - ally_cell.col),
                    )
                    logger.info(
                        f"攻击目标格子: ({target_cell.row}, {target_cell.col})"
                    )
                    self._attack_cell(context, target_cell)
                    self._click_cancel(context)
                    current_ally.has_acted = True
                else:
                    # 不能攻击 - 找可移动的空格子，且离敌人最近
                    moveable_cells = [
                        grid.cells[r][c]
                        for r in range(grid.ROWS)
                        for c in range(grid.COLS)
                        if grid.cells[r][c].is_moveable
                        and not grid.cells[r][c].have_person
                    ]

                    best_cell = None
                    min_dist = float("inf")

                    for cell in moveable_cells:
                        # 计算到所有敌人的最小距离
                        for enemy_cell in grid.enemy_units:
                            dist = abs(cell.row - enemy_cell.row) + abs(cell.col - enemy_cell.col)
                            if dist < min_dist:
                                min_dist = dist
                                best_cell = cell

                    if best_cell:
                        logger.info(f"移动到 ({best_cell.row}, {best_cell.col})")
                        self._move_to_cell(context, best_cell)
                        self._click_cancel(context)
                        current_ally.has_acted = True
                    else:
                        logger.info("找不到合适的移动位置，原地待机")
                        self._click_cancel(context)
                        current_ally.has_acted = True

                current_ally_index += 1

        logger.info("战斗流程结束")
        return CustomAction.RunResult(success=True)

    def _click_unit_and_wait(self, context: Context, x: int, y: int):
        """点击单位并等待范围显示"""
        context.tasker.controller.post_click(x, y).wait()
        import time
        time.sleep(1.0)

    def _scan_range(self, context: Context, grid: BattleGrid):
        """扫描攻击和移动范围"""
        img = context.tasker.controller.post_screencap().wait().get()

        # 检测攻击范围（红色）
        reco = context.run_recognition("Battle_AttackRange", img)
        if reco and reco.hit and reco.all_results:
            self._mark_cells_in_range(grid, reco.all_results, "attack")

        # 检测移动范围（绿色）
        reco = context.run_recognition("Battle_MoveRange", img)
        if reco and reco.hit and reco.all_results:
            self._mark_cells_in_range(grid, reco.all_results, "move")

    def _mark_cells_in_range(self, grid: BattleGrid, results, range_type: str):
        """将识别结果标记到对应格子"""
        for result in results:
            if not hasattr(result, "box") or not result.box:
                continue
            bx, by, bw, bh = result.box

            # 找到这个检测结果属于哪个格子
            for r in range(grid.ROWS):
                for c in range(grid.COLS):
                    cell = grid.cells[r][c]
                    # 检查检测结果是否在格子内
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

    def _move_to_cell(self, context: Context, cell: Cell):
        """移动到指定格子（快速单击两下）"""
        x, y = cell.rect.center()
        logger.info(f"移动点击: ({cell.row}, {cell.col})")
        context.tasker.controller.post_click(x, y).wait()
        context.tasker.controller.post_click(x, y).wait()
        import time
        time.sleep(0.5)

    def _attack_cell(self, context: Context, cell: Cell):
        """攻击指定格子（快速单击两下）"""
        x, y = cell.rect.center()
        logger.info(f"攻击点击: ({cell.row}, {cell.col})")
        context.tasker.controller.post_click(x, y).wait()
        context.tasker.controller.post_click(x, y).wait()

    def _click_cancel(self, context: Context):
        """点击空白区域取消选择"""
        x, y, w, h = CANCEL_AREA
        cancel_x = x + w // 2
        cancel_y = y + h // 2
        logger.info(f"取消点击坐标: ({cancel_x}, {cancel_y})")
        context.tasker.controller.post_click(cancel_x, cancel_y).wait()
