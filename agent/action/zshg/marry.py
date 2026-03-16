from dataclasses import dataclass
from math import log
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from utils import logger

import re
import time
import json
from pathlib import Path

from .role_utils import (
    extract_potential,
    extract_bloodlines,
    extract_features,
    get_highest_bloodline,
    extract_all_role_info,
    Bloodline,
)


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
        从 assets/table/high_blood_names.json 读取
        """
        try:
            # 获取项目根目录
            project_root = Path(__file__).parent.parent.parent.parent
            names_file = project_root / "assets" / "table" / "high_blood_names.json"

            with open(names_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            # 简化结构：直接用种族名作为 key，value 是该种族所有名字的列表
            self.blood_names = {}
            for race, genders in raw_data.items():
                all_names = []
                for gender_names in genders.values():
                    all_names.extend(gender_names)
                self.blood_names[race] = all_names

            logger.info(f"成功加载 {len(self.blood_names)} 个种族的姓名表")
            for race, names in self.blood_names.items():
                logger.info(f"  - {race}: 共{len(names)}个名字")
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
                if context.run_recognition(
                    "CastleMarryingCheck",
                    img,
                    pipeline_override={"CastleMarryingCheck": {"roi": box}},
                ).hit:
                    continue

                if context.run_recognition(
                    "CastleMarryTitleCheck",
                    img,
                    pipeline_override={"CastleMarryTitleCheck": {"roi": box}},
                ).hit:
                    available_boxes.append((row_idx, col_idx, box))
                    logger.info(
                        f"发现可相亲对象：第{row_idx + 1}行第{col_idx + 1}列， box为{box}"
                    )

        # 记录可用的相亲对象数量
        logger.info(f"可相亲队列大小：{len(available_boxes)}")

        # 3. 进行相亲 ing
        # 循环条件：available_boxes 归零 or ObjectsCount 归零时，停止相亲
        for row_idx, col_idx, box in available_boxes:
            if context.tasker.stopping:
                logger.info("相亲任务已停止")
                return CustomAction.RunResult(success=False)

            roleBoxCenter = box[0] + box[2] // 2, box[1] + box[3] // 2
            logger.info(
                f"开始处理第{row_idx + 1}行第{col_idx + 1}列的相亲对象， boxCenter为{roleBoxCenter}"
            )
            # 3.1 每个相亲对象，单机选中角色，长按进入角色详情
            context.tasker.controller.post_click(
                roleBoxCenter[0], roleBoxCenter[1]
            ).wait()
            context.run_task(
                "LongPressRole",
                pipeline_override={"LongPressRole": {"target": roleBoxCenter}},
            )

            # 3.1. 确定是男还是女
            gender = ""
            if context.run_recognition(
                "RolePanel_GirlCheck",
                context.tasker.controller.post_screencap().wait().get(),
            ).hit:
                gender = "女"
            else:
                gender = "男"
            logger.info(f"识别性别：{gender}")

            # 3.2. 先进入血统面板，查看该苗子的潜力、血脉、特性面板，检查橙特：例如太阳、科内塔、上自专等（后续开发）
            context.run_task("RolePanel_BloodPage")
            potential, bloodline, features = extract_all_role_info(context)

            highest_bloodline = get_highest_bloodline(bloodline)
            logger.info(f"最高血统：{highest_bloodline}")

            # 3.3. 根据血统确定联姻国家和种族
            target_race, target_country = self._get_marriage_info(
                highest_bloodline
            )  # 使用模糊匹配获取种族和国家
            logger.info(f"联姻国家：{target_country}，联姻种族：{target_race}")
            if not target_country or target_country == "未知":
                logger.warning(f"未识别到联姻国家")
                continue

            # 4. 确定信息后，进入正式相亲页面，正式相亲
            context.run_task("BackButton_500ms")
            context.run_task(
                "CastleMarrySelectStart",
                pipeline_override={
                    "CastleMarrySelectCountry": {"expected": [target_country]}
                },
            )

            # 4.1 循环匹配姓名，直到找到匹配的或放弃
            max_attempts = 5  # 最多尝试 5 次
            match_found = False

            for attempt in range(max_attempts):
                logger.info(f"第 {attempt + 1}/{max_attempts} 次尝试匹配姓名")

                # 4.1.1 直接判断该种族里有没有这个名字
                target_names = self.blood_names.get(target_race, [])

                if not target_names:
                    logger.warning(f"{target_race} 的姓名表为空")
                    break

                # 4.1.2 点击"就这个"按钮，触发姓名识别
                context.run_task("CastleMarryJustThisButton")

                # 4.1.3 识别显示的姓名
                reco_result = context.run_recognition(
                    "CastleMarryJustThisReadName",
                    context.tasker.controller.post_screencap().wait().get(),
                )

                if not reco_result.hit:
                    logger.warning(f"识别姓名失败, 请检查是否显示了姓名")
                    return CustomAction.RunResult(success=False)

                # 4.1.4 提取识别到的姓名
                ocr_text = reco_result.best_result.text
                logger.info(f"识别到的姓名：{ocr_text}")

                # 4.1.5 使用正则提取姓名（格式：确认向 XXX 发送...）
                name_match = re.search(r"向([\u4e00-\u9fa5]{1,5})发送", ocr_text)
                if not name_match:
                    logger.warning(
                        f"无法从 OCR 结果中提取姓名：{ocr_text}, 请检查是否显示了姓名"
                    )
                    return CustomAction.RunResult(success=False)

                detected_name = name_match.group(1)
                logger.info(f"提取到的姓名：{detected_name}")

                # 4.1.6 判断姓名是否在高血名单中
                if detected_name in target_names:
                    logger.info(
                        f"姓名匹配成功：{detected_name} 在 {target_race} 的高血名单中"
                    )
                    match_found = True
                    # 点击"确定"确认相亲
                    context.run_task("PopUpWindowConfirm")
                    break
                else:
                    logger.info(
                        f"姓名不匹配：{detected_name} 不在高血名单中，尝试下一个"
                    )
                    # 取消匹配，点击"下一位"继续
                    context.run_task("PopUpWindowCancel")
                    context.run_task("CastleMarryNextOneButton")

            if not match_found:
                logger.warning(f"经过{max_attempts}次尝试，仍未找到匹配的姓名")
                # 点击"取消"退出
                context.run_task("PopUpWindowCancel")
                context.run_task("CastleMarryLeave")

            logger.info(f"完成第{row_idx + 1}行第{col_idx + 1}列的处理")

        # 4. 结束相亲
        return CustomAction.RunResult(success=True)

    def _get_marriage_info(self, bloodline: str) -> tuple[str, str]:
        """
        根据血统确定联姻种族和国家（支持模糊匹配）
        Args:
            bloodline: 血统名称
        Returns:
            (种族名称, 国家名称) 元组
        """
        # 种族和国家映射配置
        race_country_mapping = {
            "祖扎尔达王族": "加尔提斯商会",
            "瓦诺遗族": "加尔提斯商会",
            "萨尼德罕": "加尔提斯商会",
            "宏朝贵胄": "加尔提斯商会",
            "高阶精灵": "森之祈愿",
            "法拉希尔血裔": "森之祈愿",
            "弗莱德里王族": "弗莱德里王族",
            "古特雅尔": "北地自由民",
            "切瓦利王族": "切瓦利王族",
            "佩尔弗因王族": "佩尔弗因王族",
            "希尔王族": "希尔王族",
            "塞宁王族": "塞宁王族",
            "玛夏贵族": "玛夏审判军",
        }

        # 模糊匹配关键词映射
        fuzzy_mapping = {
            "祖扎": ("祖扎尔达王族", "加尔提斯商会"),
            "瓦诺": ("瓦诺遗族", "加尔提斯商会"),
            "萨尼": ("萨尼德罕", "加尔提斯商会"),
            "宏朝": ("宏朝贵胄", "加尔提斯商会"),
            "精灵": ("高阶精灵", "森之祈愿"),
            "法拉": ("法拉希尔血裔", "森之祈愿"),
            "弗莱": ("弗莱德里王族", "弗莱德里王族"),
            "古特": ("古特雅尔", "北地自由民"),
            "切瓦利": ("切瓦利王族", "切瓦利王族"),
            "佩尔": ("佩尔弗因王族", "佩尔弗因王族"),
            "希尔": ("希尔王族", "希尔王族"),
            "塞宁": ("塞宁王族", "塞宁王族"),
            "玛夏": ("玛夏贵族", "玛夏审判军"),
        }

        # 精确匹配
        if bloodline in race_country_mapping:
            race = bloodline
            country = race_country_mapping[bloodline]
            return race, country

        # 模糊匹配
        for keyword, (race, country) in fuzzy_mapping.items():
            if keyword in bloodline:
                return race, country

        # 都匹配不到，返回原始值和未知国家
        return bloodline, "未知"


@AgentServer.custom_action("WeddingProcessor")
class WeddingProcessor(CustomAction):
    """
    处理婚礼相关任务
    """

    # 爵位优先级映射
    title_rank = {
        "公爵": 4,
        "伯爵": 3,
        "男爵": 2,
        "骑士": 1,
        "无爵位": 0,
    }

    def __init__(self) -> None:
        super().__init__()

    def _extract_title_from_ocr(self, reco_result) -> str:
        """
        从 OCR 结果中提取爵位
        Args:
            reco_result: OCR 识别结果
        Returns:
            爵位名称
        """
        if not reco_result.hit:
            return "无爵位"

        # 遍历所有 OCR 结果，找爵位关键词
        ocr_results = reco_result.all_results
        highest_title = "无爵位"
        highest_rank = 0

        for item in ocr_results:
            text = item.text.strip()
            # 检查是否包含爵位关键词
            for title, rank in self.title_rank.items():
                if title in text and rank > highest_rank:
                    highest_title = title
                    highest_rank = rank

        return highest_title

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        """
        处理婚礼事件
        """
        # 1. 先检查是否在婚礼界面
        if not context.run_recognition(
            "Event_WeddingPage",
            context.tasker.controller.post_screencap().wait().get(),
        ).hit:
            logger.error("婚礼界面未进入,可能存在Bug")
            return CustomAction.RunResult(success=False)

        logger.info("婚礼界面已进入")

        # 2. 处理婚礼事件
        # 2.1 检测当前双方最高爵位
        left_title = context.run_recognition(
            "Event_WeddingTitleCheckLeft",
            context.tasker.controller.post_screencap().wait().get(),
        )
        right_title = context.run_recognition(
            "Event_WeddingTitleCheckRight",
            context.tasker.controller.post_screencap().wait().get(),
        )

        # 提取左右两侧的爵位
        left_highest = self._extract_title_from_ocr(left_title)
        right_highest = self._extract_title_from_ocr(right_title)

        # 比较爵位等级，取最高的
        highest_title = self._compare_titles(left_highest, right_highest)

        if not highest_title or highest_title == "无爵位":
            logger.info("未识别到双方最高爵位")
            return CustomAction.RunResult(success=False)

        logger.info(f"当前双方最高爵位：{highest_title}")

        # 2.2 计算当前用什么档位来结婚
        target_banquet = self._get_target_banquet(highest_title)
        logger.info(f"选择宴会档位：{target_banquet}")

        # 3. 找到目标宴会的 button
        context.run_task(
            "Event_WeddingTitleButton",
            pipeline_override={
                "Event_WeddingTitleEntry": {"expected": [target_banquet[:2]]}
            },
        )
        context.run_task("PopUpWindowConfirm")
        return CustomAction.RunResult(success=True)

    def _compare_titles(self, left_title: str, right_title: str) -> str:
        """
        比较两个爵位，返回最高的爵位
        Args:
            left_title: 左侧爵位
            right_title: 右侧爵位
        Returns:
            最高的爵位
        """
        left_rank = self.title_rank.get(left_title, 0)
        right_rank = self.title_rank.get(right_title, 0)

        if left_rank > right_rank:
            return left_title
        elif right_rank > left_rank:
            return right_title
        else:
            return left_title

    def _get_target_banquet(self, title: str) -> str:
        """
        根据爵位获取目标宴会档位
        Args:
            title: 爵位名称
        Returns:
            宴会档位名称
        """
        if title not in self.title_rank:
            logger.warning(f"未识别的爵位：{title}，使用默认档位：乡村宴会")
            return "乡村宴会"

        title_level = self.title_rank[title]
        logger.info(f"爵位等级：{title} (等级{title_level})")

        # 公爵 (等级 4) 使用乡村宴会，其他使用祝福婚宴
        if title_level >= 4:
            return "乡村宴会"
        else:
            return "祝福婚宴"
