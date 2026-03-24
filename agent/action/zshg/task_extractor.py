from dataclasses import dataclass
from typing import List, Optional, Dict, Union
from maa.define import OCRResult, Rect
import json
import os

from utils import logger


@dataclass
class TaskInfo:
    task_name: str
    task_description: str
    reward: Optional[str] = None
    time_limit: Optional[str] = None
    enemy_level: Optional[str] = None
    accept_button_box: Optional[Rect] = None
    abandon_button_box: Optional[Rect] = None


class TaskExtractor:
    # 类变量，用于单例模式
    _instance = None
    _initialized = False

    # 类变量，用于缓存数据，避免重复加载
    _task_blacklist_cache = None
    _task_blacklist_file_cache = None

    def __new__(cls, roi: List[int] = None):
        # 单例模式实现
        if cls._instance is None:
            cls._instance = super(TaskExtractor, cls).__new__(cls)
        return cls._instance

    def __init__(self, roi: List[int] = None):
        # 防止重复初始化
        if self._initialized:
            return
        self._initialized = True
        self.roi = roi or [0, 0, 1920, 1080]
        self.roi_rect = Rect(*self.roi)
        self.accept_buttons = []
        # 使用当前工作目录作为基础路径
        cwd_dir = os.getcwd()
        logger.info(f"TaskExtractor初始化，当前工作目录: {cwd_dir}")

        self.task_blacklist_file = os.path.join(cwd_dir, "table", "task_blacklist.json")
        logger.info(f"黑名单文件路径: {self.task_blacklist_file}")

        # 使用缓存的类变量，避免重复加载
        self.task_blacklist = self._get_cached_task_blacklist()

    def _get_cached_task_blacklist(self):
        """获取缓存的task黑名单，避免重复加载"""
        # 如果文件路径发生变化或缓存为空，重新加载
        if (
            TaskExtractor._task_blacklist_cache is None
            or TaskExtractor._task_blacklist_file_cache != self.task_blacklist_file
        ):

            TaskExtractor._task_blacklist_file_cache = self.task_blacklist_file
            TaskExtractor._task_blacklist_cache = self._load_task_blacklist()
            logger.info("黑名单缓存已更新")
        else:
            logger.info("使用缓存的黑名单数据")

        return TaskExtractor._task_blacklist_cache

    def _load_task_blacklist(self):
        try:
            if os.path.exists(self.task_blacklist_file):
                with open(self.task_blacklist_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    blacklist = set(data.get("blacklist", []))
                    logger.info(
                        f"载入黑名单成功，共 {len(blacklist)} 个任务: {list(blacklist)}"
                    )
                    return blacklist
            else:
                logger.info(f"黑名单文件不存在: {self.task_blacklist_file}")
                return set()
        except Exception as e:
            logger.error(f"载入黑名单失败: {e}")
            return set()

    @classmethod
    def add_to_blacklist(cls, task_names: str):
        """动态添加任务名到黑名单（同时持久化到文件）

        Args:
            task_names: 逗号分隔的任务名称字符串，如 "任务A,任务B"
        """
        if not task_names:
            return
        names = [name.strip() for name in task_names.replace("，", ",").split(",") if name.strip()]
        if not names:
            return

        # 添加到内存中的黑名单集合
        for name in names:
            cls._task_blacklist_cache.add(name)
        logger.info(f"动态添加黑名单任务: {names}，当前黑名单共 {len(cls._task_blacklist_cache)} 个")

        # 持久化到文件
        try:
            with open(cls._task_blacklist_file_cache, "w", encoding="utf-8") as f:
                json.dump({"blacklist": list(cls._task_blacklist_cache)}, f, ensure_ascii=False, indent=4)
            logger.info(f"黑名单已保存到文件: {cls._task_blacklist_file_cache}")
        except Exception as e:
            logger.error(f"保存黑名单到文件失败: {e}")

    def extract_tasks(self, ocr_results: List) -> List[TaskInfo]:
        if not ocr_results:
            return []

        # 预处理：先缓存所有接受和放弃按钮，同时过滤无效文本
        filtered_results = []
        self.accept_buttons = []
        self.abandon_buttons = []
        for res in ocr_results:
            text = self._get_text(res).strip()
            if not text:
                continue
            if "接受" in text:
                self.accept_buttons.append(
                    (
                        self._get_box_y(self._get_box_from_result(res)),
                        self._get_box_from_result(res),
                    )
                )
            elif "放弃" in text:
                self.abandon_buttons.append(
                    (
                        self._get_box_y(self._get_box_from_result(res)),
                        self._get_box_from_result(res),
                    )
                )
            else:
                filtered_results.append(res)

        # 按Y坐标排序（还原视觉顺序）
        sorted_results = sorted(
            filtered_results,
            key=lambda r: self._get_box_y(self._get_box_from_result(r)),
        )

        # 重新分组：以任务名称为分隔符，精准拆分任务
        task_groups = self._group_by_task_name(sorted_results)

        tasks = []
        for group in task_groups:
            task = self._extract_single_task(group)
            if task and task.task_name not in self.task_blacklist:
                tasks.append(task)

        return tasks

    def _get_box_y(self, box) -> int:
        if isinstance(box, Rect):
            return box.y
        elif isinstance(box, (list, tuple)) and len(box) >= 2:
            return box[1]
        elif hasattr(box, "y"):
            return box.y
        return 0

    def _get_box(self, box) -> Rect:
        if isinstance(box, Rect):
            return box
        elif isinstance(box, (list, tuple)) and len(box) >= 4:
            return Rect(box[0], box[1], box[2], box[3])
        return Rect(0, 0, 0, 0)

    def _get_text(self, result) -> str:
        if hasattr(result, "text"):
            return result.text
        elif isinstance(result, dict):
            return result.get("text", "")
        return ""

    def _get_box_from_result(self, result):
        if hasattr(result, "box"):
            return result.box
        elif isinstance(result, dict):
            return result.get("box", [0, 0, 0, 0])
        return [0, 0, 0, 0]

    def _is_task_name_candidate(self, text: str, y_pos: int) -> bool:
        """判断是否为任务名称候选"""
        # 文本长度判断：任务名称通常较短
        if len(text) < 2 or len(text) > 10:
            return False

        # 排除明显不是任务名称的文本
        exclude_patterns = [
            "奖励",
            "任务时限",
            "敌人等级",
            "接受",
            "放弃",
            "当前任务",
            "失败：",
            "有一",
            "一名",
            "一支",
            "一位",
            "这个",
            "委托",
            "有-",
            "-300",
            "x",
            "X",
            "×",
        ]
        for pattern in exclude_patterns:
            if pattern in text:
                return False

        # 排除纯数字和带有数字前缀的文本（如"x328"、"400"等）
        if text.isdigit():
            return False
        if text.startswith(("x", "X", "×")) and len(text) > 1 and text[1:].isdigit():
            return False

        # 基于位置和上下文的启发式判断
        # 这里可以根据实际情况调整位置阈值
        if y_pos < 300 or y_pos > 1200:
            return False

        return True

    def _group_by_task_name(self, sorted_results: List) -> List[List]:
        """以任务名称为分隔符，精准拆分任务"""
        groups = []
        current_group = []

        for i, res in enumerate(sorted_results):
            text = self._get_text(res).strip()
            box = self._get_box_from_result(res)
            box_y = self._get_box_y(box)

            # 检查是否为有效的任务名称候选
            if self._is_task_name_candidate(text, box_y):
                # 检查是否与前一个元素有较大的垂直间距（任务分隔）
                if current_group:
                    prev_res = sorted_results[i - 1]
                    prev_box = self._get_box_from_result(prev_res)
                    prev_box_y = self._get_box_y(prev_box)

                    # 如果垂直间距大于阈值，认为是新任务
                    if box_y - prev_box_y > 50:
                        groups.append(current_group)
                        current_group = [res]
                    else:
                        # 否则认为是当前任务的一部分
                        current_group.append(res)
                else:
                    # 第一个元素，直接作为新任务的开始
                    current_group = [res]
            else:
                # 非任务名称，添加到当前组
                current_group.append(res)

        if current_group:
            groups.append(current_group)

        return groups

    def _extract_single_task(self, ocr_results: List) -> Optional[TaskInfo]:
        task_name = None
        task_description = ""
        reward = []
        time_limit = None
        enemy_level = None
        accept_button_box = None
        abandon_button_box = None

        # 提取当前任务的Y范围（用于匹配对应接受按钮）
        group_min_y = self._get_box_y(self._get_box_from_result(ocr_results[0]))
        group_max_y = self._get_box_y(self._get_box_from_result(ocr_results[-1]))

        # 存储每个元素的位置信息，用于更好地判断上下文
        elements = []
        for result in ocr_results:
            text = self._get_text(result).strip()
            box = self._get_box_from_result(result)
            box_y = self._get_box_y(box)
            elements.append((text, box_y, box))

        # 按Y坐标排序元素
        elements.sort(key=lambda x: x[1])

        # 提取任务信息
        for i, (text, box_y, box) in enumerate(elements):
            # 提取任务名称（通常是第一个有效的候选）
            if not task_name and self._is_task_name_candidate(text, box_y):
                task_name = text
            # 提取任务描述
            elif self._is_description(text):
                task_description += text
            # 提取任务时限
            elif text.startswith("任务时限："):
                time_limit = text.replace("任务时限：", "").strip()
            # 提取敌人等级
            elif text.startswith("敌人等级："):
                enemy_level = text.replace("敌人等级：", "").strip()
            # 提取奖励（匹配x开头的数值或纯数字，通常在"奖励："附近）
            elif (
                text.startswith(("x", "X", "×"))
                and len(text) > 1
                and text[1:].isdigit()
            ) or text.isdigit():
                # 检查是否在"奖励："附近
                has_reward_label = False
                for j in range(max(0, i - 5), min(len(elements), i + 5)):
                    if "奖励：" in elements[j][0]:
                        has_reward_label = True
                        break
                if has_reward_label:
                    reward.append(text)

        # 匹配当前任务对应的接受按钮（Y轴在任务范围内）
        for btn_y, btn_box in self.accept_buttons:
            if group_min_y <= btn_y <= group_max_y:
                accept_button_box = self._get_box(btn_box)
                break

        # 匹配当前任务对应的放弃按钮（Y轴在任务范围内）
        for btn_y, btn_box in self.abandon_buttons:
            if group_min_y <= btn_y <= group_max_y:
                abandon_button_box = self._get_box(btn_box)
                break

        if not task_name:
            return None

        # 整理奖励格式
        reward_str = " + ".join(reward) if reward else None

        return TaskInfo(
            task_name=task_name,
            task_description=task_description,
            reward=reward_str,
            time_limit=time_limit,
            enemy_level=enemy_level,
            accept_button_box=accept_button_box,
            abandon_button_box=abandon_button_box,
        )

    def _is_description(self, text: str) -> bool:
        """判断是否为任务描述"""
        description_starts = [
            "有一名",
            "有一",
            "一名",
            "一支",
            "必须",
            "委托",
            "尽快",
            "一位",
            "这个",
        ]
        for pattern in description_starts:
            if text.startswith(pattern):
                return True
        return len(text) >= 15

    def print_task_details(self, tasks: List[TaskInfo]):
        """输出任务详情"""
        for task in tasks:
            logger.info(f"任务名称: {task.task_name}")
            logger.info(f"任务描述: {task.task_description}")
            if task.reward:
                logger.info(f"奖励: {task.reward}")
            if task.time_limit:
                logger.info(f"时限: {task.time_limit}")
            if task.enemy_level:
                logger.info(f"敌人等级: {task.enemy_level}")
            if task.accept_button_box:
                logger.info(f"接受按钮位置: {task.accept_button_box}")
            if task.abandon_button_box:
                logger.info(f"放弃按钮位置: {task.abandon_button_box}")
            logger.info("-" * 50)
