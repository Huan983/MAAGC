from dataclasses import dataclass
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from utils import logger

import re
import time
import json
from pathlib import Path


@AgentServer.custom_action("MarryProcessor")
class MarryProcessor(CustomAction):
    """
    处理联姻相关任务
    """

    def __init__(self) -> None:
        super().__init__()
        self.all_boxes = []
        self.blood_names = {}  # 存储各国姓名表 {国家名：{男：[...], 女：[...]}}
        self._init_boxes()
        self._load_blood_names()

    def _load_blood_names(self) -> None:
        """
        加载高阶血统姓名表
        从 assets/assets/high_blood_names.json 读取
        """
        try:
            # 获取项目根目录
            project_root = Path(__file__).parent.parent.parent.parent.parent
            names_file = project_root / "assets" / "assets" / "high_blood_names.json"

            with open(names_file, "r", encoding="utf-8") as f:
                self.blood_names = json.load(f)

            logger.info(f"成功加载 {len(self.blood_names)} 个国家的姓名表")
            for country, genders in self.blood_names.items():
                male_count = len(genders.get("男", []))
                female_count = len(genders.get("女", []))
                logger.debug(f"  - {country}: 男{male_count}人，女{female_count}人")
        except Exception as e:
            logger.error(f"加载姓名表失败：{e}")
            self.blood_names = {}

    def _init_boxes(self) -> None:
        """
        初始化 3 行 5 列的 box 网格
        """
        # 基准 box：第一行第一列 [x, y, width, height]
        base_box = [30, 700, 120, 120]

        # 计算 3 行 5 列的 box 网格
        base_x, base_y, box_width, box_height = base_box
        x_gap = 15  # X 轴间距
        y_gap = 15  # Y 轴间距
        cols = 5  # 每行 5 列
        rows = 3  # 共 3 行

        # 生成二维列表：[row][col] -> box
        self.all_boxes = []
        for row in range(rows):
            row_boxes = []
            for col in range(cols):
                x = base_x + col * (box_width + x_gap)
                y = base_y + row * (box_height + y_gap)
                row_boxes.append([x, y, box_width, box_height])
            self.all_boxes.append(row_boxes)

        logger.info(f"生成 {rows}x{cols} 的 box 网格，共{rows * cols}个 box")

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        # 0. 五月触发联姻事件

        # 1. 首先先进入联姻界面，查看是否有联姻次数。
        # 1.0 先进入联姻大厅
        context.run_task("CastleHall")

        if context.run_recognition(
            "CastleMarryWindow", context.tasker.controller.post_screencap().wait().get()
        ).hit:
            logger.info("联姻界面已显示")

            # 1.1检查相亲次数
            img = context.tasker.controller.post_screencap().wait().get()
            RecoDetail = context.run_recognition(
                "CastleMarryObjectsCheck",
                img,
            )

            # 1.2 检查还有没有相亲对象
            ObjectsCount = 0
            if RecoDetail.hit:
                text = RecoDetail.best_result.text
                match = re.search(r"对象数量：(\d{1,2})", text)
                if match:
                    ObjectsCount = int(match.group(1))
                    if ObjectsCount > 0:
                        logger.info(f"当前有 {ObjectsCount} 个联姻对象")
                    else:
                        logger.info(f"当前联姻对象数量为{ObjectsCount}，无法进行联姻")
                        return CustomAction.RunResult(success=False)
            else:
                logger.info("未识别到联姻对象数量")
                return CustomAction.RunResult(success=False)

            # 1.3 检查是否有回信数量
            RecoEmail = context.run_recognition(
                "CastleMarryEmailsCheck",
                img,
            )
            if RecoEmail.hit:
                text = RecoEmail.best_result.text
                # 抽取回信数量（格式：回信数量：5/8）
                match = re.search(r"回信数量：(\d+)/(\d+)", text)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))

                    if current < total:
                        logger.info(f"当前回信数量：{current}/{total} 还可以进行联姻")
                    else:
                        logger.info(
                            f"当前回信数量：{current}/{total} 回信已满，无法继续联姻"
                        )
                        return CustomAction.RunResult(success=False)
            else:
                logger.info("未识别到回信数量信息")
                return CustomAction.RunResult(success=False)
        else:
            logger.error("联姻界面未进入,可能存在Bug")
            return CustomAction.RunResult(success=False)

        # 2. 寻找相亲对象
        # 使用已初始化的 self.all_boxes，检测每个格子里面是否有爵位（联姻对象）&& 每个格子是否正在联姻
        available_boxes = []  # 存储可以相亲的 box 队列 [(row, col, box), ...]

        img = context.tasker.controller.post_screencap().wait().get()
        for row_idx, row_boxes in enumerate(self.all_boxes):
            for col_idx, box in enumerate(row_boxes):
                MarryingRecoResult = context.run_recognition(
                    "CastleMarryingCheck",
                    img,
                    pipeline_override={"CastleMarryingCheck": {"roi": box}},
                )
                TitileRecoResult = context.run_recognition(
                    "CastleMarryTitleCheck",
                    img,
                    pipeline_override={"CastleMarryTitleCheck": {"roi": box}},
                )
                if not MarryingRecoResult.hit and TitileRecoResult.hit:
                    available_boxes.append((row_idx, col_idx, box))
                    logger.info(f"发现可相亲对象：第{row_idx + 1}行第{col_idx + 1}列")

        # 记录可用的相亲对象数量
        logger.info(f"可相亲队列大小：{len(available_boxes)}")
        # 3. 进行相亲 ing
        # 这里应该是一个循环条件，{len(available_boxes)}归零  or ObjectsCount 归零时，停止相亲。每次循环按照以下顺序执行。
        # 3.1 长按点击进入角色详情 每个相亲对象，确定相亲对象是男还是女标记一个性别，查看该对象的最高的血统是那个国家的。根据血统映射到对应的国家。然后选择联姻国家
        # 3.2 确定信息后 进入正式相亲页面 正式相亲

        # 3.3 每次通点击“就这个”按钮，来获取目标相亲对象的姓名，多个模式（高血姓名表、混血、上自专），默认姓名表相亲，其他的暂时等待未来开发
        # 3.3.1 首先根据上面的性别，来选择目标性别名单，比如我们相亲对象是女，目标对象则是男，反之亦然。
        # 3.3.2 判断目标相亲对象姓名是否在对应国家，对应性别里面的高血名单里面。
        # 3.3.3 如果存在，则直接相亲，说明匹配上了目标对象。
        # 3.3.4 如果不存在，则点击下一个。

        # 4. 结束相亲

        return CustomAction.RunResult(success=True)
