from dataclasses import dataclass
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from utils import logger

# 使用 BattleGridRecognizer 进行战场识别
from .battle_grid import BattleGridRecognizer


@AgentServer.custom_action("AutoFightProcessor")
class AutoFightProcessor(CustomAction):
    """
    处理战斗相关任务
    """

    def __init__(self) -> None:
        super().__init__()

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        """处理战斗任务主流程"""

        img = context.tasker.controller.post_screencap().wait().get()

        # Pipeline 模式：is_opencv=False
        recognizer = BattleGridRecognizer(is_opencv=False)
        grid = recognizer.recognize(img, debug_dir="debug", context=context)

        logger.info(f"战场识别完成: {grid.total_cols}x{grid.total_rows} 网格")
        logger.info(f"威胁格子: {len(grid.threat_cells)} 个")
        logger.info(f"单位数量: {len(grid.units)} 个")

        # TODO: 基于识别结果进行战斗策略决策和执行

        return CustomAction.RunResult(success=True)
