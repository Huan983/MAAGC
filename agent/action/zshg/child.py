from dataclasses import dataclass
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from utils import logger

import re
import time

from .role_utils import (
    extract_potential,
    extract_bloodlines,
    extract_features,
    get_highest_bloodline,
    get_potential_grade,
    extract_all_role_info,
    Potential,
    Bloodline,
    Feature,
)

# 属性等级优先级（用于排序）
ATTRIBUTE_RANK = {
    "SS": 7,
    "S": 6,
    "A": 5,
    "B": 4,
    "C": 3,
    "D": 2,
    "E": 1,
}


def generate_child_name(
    potential,
    bloodline,
    features: list,
    highest_title: str,
) -> str:
    """
    生成子孙命名
    格式：最高属性 + 次高属性 + 特性 + 爵位
    例如：力 ss 技 ss 太科公.2
    """
    # 1. 找出最高和次高属性
    attributes = []
    for attr_name, attr_value in potential.values.items():
        grade = get_potential_grade(attr_value)
        attributes.append((attr_name, attr_value, grade))

    # 按属性值排序
    attributes.sort(key=lambda x: x[1], reverse=True)

    # 获取最高和次高属性
    if len(attributes) >= 2:
        top_attr = attributes[0]
        second_attr = attributes[1]

        # 属性名称取第一个汉字
        top_attr_short = top_attr[0][0]  # 如"力"
        second_attr_short = second_attr[0][0]  # 如"技"

        # 等级转小写
        top_grade = top_attr[2].lower()  # 如"ss"
        second_grade = second_attr[2].lower()  # 如"ss"

        attr_part = f"{top_attr_short}{top_grade}{second_attr_short}{second_grade}"
    else:
        attr_part = ""

    # 2. 提取特性（跳过隐藏特性）
    feature_chars = []
    for feature in features:
        if "隐藏" not in feature.name:
            # 取特性名称第一个汉字
            feature_chars.append(feature.name[0])

    feature_part = "".join(feature_chars[:3])  # 最多取 3 个特性

    # 3. 爵位取第一个汉字
    title_short = highest_title[0] if highest_title else ""

    # 4. 组合命名
    name = f"{attr_part}{feature_part}{title_short}"

    return name


# 爵位等级
title_rank: dict = {
    "公爵": 4,
    "伯爵": 3,
    "男爵": 2,
    "骑士": 1,
    "无爵位": 0,
}


@dataclass
class ParentInfo:
    """
    父母信息结构体
    """

    name: str = ""  # 姓名
    title: str = ""  # 爵位（男爵、伯爵、公爵、骑士、无爵位）
    mercenary_group: str = ""  # 佣兵团


@AgentServer.custom_action("ChildRec")
class ChildRec(CustomAction):
    """
    识别子项信息
    """

    def __init__(self) -> None:
        """ """
        super().__init__()
        self.potential = None
        self.bloodline = None
        self.features = []

    def extract_parent_info(
        self, context: Context, is_father: bool = True
    ) -> ParentInfo:
        """
        提取父母信息
        Args:
            context: MAA 上下文
            is_father: True 为父亲，False 为母亲
        """
        parent_info = ParentInfo()

        # 选择识别任务
        title_task = "PannelFatherTitle" if is_father else "PannelMotherTitle"
        parent_type = "父亲" if is_father else "母亲"

        # 识别父母信息
        reco_result = context.run_recognition(
            title_task,
            context.tasker.controller.post_screencap().wait().get(),
        )

        if not reco_result.hit:
            logger.error(f"识别{parent_type}信息失败")
            return parent_info

        # 解析 OCR 结果
        ocr_results = reco_result.all_results
        filtered_results = [
            item for item in ocr_results if item.score > 0.5 and item.text.strip()
        ]

        # 提取姓名、爵位、佣兵团
        name_candidates = []
        for item in filtered_results:
            text = item.text.strip()

            # 判断爵位
            if any(title in text for title in ["男爵", "伯爵", "公爵", "骑士"]):
                if "公爵" in text:
                    parent_info.title = "公爵"
                elif "伯爵" in text:
                    parent_info.title = "伯爵"
                elif "男爵" in text:
                    parent_info.title = "男爵"
                elif "骑士" in text:
                    parent_info.title = "骑士"
                # 同时提取姓名（如"慧根女公爵"中的"慧根女"）
                name_part = (
                    text.replace("公爵", "")
                    .replace("伯爵", "")
                    .replace("男爵", "")
                    .replace("骑士", "")
                )
                if name_part:
                    name_candidates.append(name_part)
            # 佣兵团：通常是英文或短文本
            elif len(text) <= 10 and any(c.isascii() for c in text):
                parent_info.mercenary_group = text
            # 姓名：剩余的汉字文本
            elif all("\u4e00" <= c <= "\u9fff" for c in text) and 2 <= len(text) <= 10:
                name_candidates.append(text)

        # 选择最合适的姓名
        if name_candidates:
            parent_info.name = name_candidates[0]

        # 如果没有识别到爵位，设置为"无爵位"
        if not parent_info.title:
            parent_info.title = "无爵位"

        # logger.info(
        #     f"{parent_type}信息：姓名={parent_info.name}, 爵位={parent_info.title}, "
        #     f"佣兵团={parent_info.mercenary_group}"
        # )

        return parent_info

    def compare_parent_titles(
        self, father_info: ParentInfo, mother_info: ParentInfo
    ) -> tuple:
        """
        比较父母爵位等级
        Returns:
            (最高爵位，数量)
        """
        title_rank = {
            "公爵": 4,
            "伯爵": 3,
            "男爵": 2,
            "骑士": 1,
            "无爵位": 0,
        }

        father_rank = title_rank.get(father_info.title, 0)
        mother_rank = title_rank.get(mother_info.title, 0)

        if father_rank > mother_rank:
            return father_info.title, 1
        elif mother_rank > father_rank:
            return mother_info.title, 1
        else:
            return father_info.title, 2

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        # 0.佣兵生娃

        # 1.识别父母信息
        father_info = self.extract_parent_info(context, is_father=True)
        mother_info = self.extract_parent_info(context, is_father=False)

        highest_title, count = self.compare_parent_titles(father_info, mother_info)
        logger.info(f"最高爵位是{highest_title}，最高爵位有{count}个")

        # 2. 提取天赋属性、血脉、特性（完整识别流程）
        context.run_task("PannelChildInfoButton")
        self.potential, self.bloodline, self.features = extract_all_role_info(context)

        if not self.potential.values or all(
            v == 0.0 for v in self.potential.values.values()
        ):
            logger.error("提取子项属性失败")
            return CustomAction.RunResult(success=False)

        if not self.bloodline.bloodlines:
            logger.error("提取血脉信息失败")
            return CustomAction.RunResult(success=False)

        # 5. 生成子孙命名
        # 注意：这里需要在 extract_attributes 中保存 potential 对象
        child_name = generate_child_name(
            self.potential, self.bloodline, self.features, highest_title
        )
        logger.info(f"子孙命名：{child_name}")

        # 6. 输入子孙命名
        context.run_task("BackButton_500ms")
        context.run_task(
            "PannelChildSetName",
            pipeline_override={"PannelChildSetNameCopy": {"input_text": child_name}},
        )

        return CustomAction.RunResult(success=True)
