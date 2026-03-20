#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用OpenCV将图像中像素值为0的区域转换为绿色(0, 255, 0)的脚本
"""

import os
import cv2
import numpy as np


def convert_black_to_green(input_image_path, output_image_path=None):
    """
    将图像中像素值为0的区域转换为绿色

    Args:
        input_image_path (str): 输入图像路径
        output_image_path (str, optional): 输出图像路径，默认为输入图像路径加"_green"后缀
    """
    # 检查输入文件是否存在
    if not os.path.exists(input_image_path):
        print(f"错误：输入文件 '{input_image_path}' 不存在")
        return False

    # 检查文件扩展名
    file_name = os.path.basename(input_image_path)
    if "." not in file_name:
        print(f"错误：文件 '{input_image_path}' 没有扩展名")
        return False

    # 获取文件扩展名
    ext = os.path.splitext(file_name)[1].lower()
    supported_formats = (".png", ".jpg", ".jpeg", ".bmp", ".tiff")

    if ext not in supported_formats:
        print(f"错误：不支持的文件格式 '{ext}'，仅支持 {supported_formats}")
        return False

    # 设置默认输出路径
    if output_image_path is None or output_image_path == "":
        dir_name, file_name = os.path.split(input_image_path)
        base_name, ext = os.path.splitext(file_name)
        output_image_path = os.path.join(dir_name, f"{base_name}_green{ext}")

    try:
        # 使用numpy和cv2.imdecode读取中文路径的图像
        try:
            # 读取图像文件为字节流
            with open(input_image_path, "rb") as f:
                img_data = np.fromfile(f, dtype=np.uint8)
            # 使用cv2.imdecode解码图像
            img = cv2.imdecode(img_data, cv2.IMREAD_UNCHANGED)  # 保持透明通道
        except Exception as e:
            print(f"错误：读取图像文件失败: {str(e)}")
            return False

        if img is None:
            print(f"错误：无法解码图像 '{input_image_path}'")
            return False

        print(f"图像信息：")
        print(f"  尺寸: {img.shape[1]}x{img.shape[0]}")
        print(f"  通道数: {img.shape[2] if len(img.shape) > 2 else 1}")
        print(f"  数据类型: {img.dtype}")

        # 预处理：识别黑色连通块
        # 将图像转换为灰度图用于处理
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        # 创建黑色像素掩码（像素值为0）
        black_mask = gray == 0

        # 对黑色区域进行连通区域分析
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            black_mask.astype(np.uint8), connectivity=8
        )

        # 创建最终的涂绿掩码：只保留面积超过5的黑色连通块
        green_mask = np.zeros_like(black_mask, dtype=bool)

        for i in range(1, num_labels):  # 跳过背景（label 0）
            area = stats[i, cv2.CC_STAT_AREA]
            if area > 5:  # 只处理面积超过5像素的连通块
                component_mask = labels == i
                green_mask = green_mask | component_mask

        # 根据通道数处理图像
        if len(img.shape) == 3:
            # 彩色图像 (BGR 或 BGRA)
            if img.shape[2] == 4:
                # BGRA - 带透明通道
                print(f"  模式: BGRA (带透明通道)")

                # 分离通道
                b, g, r, a = cv2.split(img)

                # 创建掩码：所有通道都是0且alpha通道不是0且在绿色掩码内
                mask = (b == 0) & (g == 0) & (r == 0) & (a > 0) & green_mask

                # 将黑色像素转换为绿色
                b[mask] = 0
                g[mask] = 255
                r[mask] = 0

                # 合并通道
                img = cv2.merge([b, g, r, a])

            elif img.shape[2] == 3:
                # BGR - 彩色图像
                print(f"  模式: BGR")

                # 创建掩码：所有通道都是0且在绿色掩码内
                mask = (
                    (img[:, :, 0] == 0)
                    & (img[:, :, 1] == 0)
                    & (img[:, :, 2] == 0)
                    & green_mask
                )

                # 将黑色像素转换为绿色 (注意OpenCV是BGR顺序)
                img[mask] = [0, 255, 0]

        else:
            # 灰度图像
            print(f"  模式: 灰度图")

            # 将灰度图转换为BGR
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

            # 创建掩码：在绿色掩码内的像素
            mask = green_mask

            # 将黑色像素转换为绿色
            img[mask] = [0, 255, 0]

        # 保存处理后的图像
        try:
            # 直接使用PNG格式保存
            encode_param = [int(cv2.IMWRITE_PNG_COMPRESSION), 0]
            success, encoded_img = cv2.imencode(".png", img, encode_param)

            if success:
                # 使用np.tofile保存到中文路径
                encoded_img.tofile(output_image_path)
                print(f"\n图像处理完成！")
                print(f"输入: {input_image_path}")
                print(f"输出: {output_image_path}")
                return True
            else:
                print(f"\n错误：无法编码图像 '{output_image_path}'")
                return False
        except Exception as e:
            print(f"\n错误：保存图像失败: {str(e)}")
            import traceback

            traceback.print_exc()
            return False

    except Exception as e:
        print(f"\n图像处理失败: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def batch_convert(directory):
    """
    批量处理目录中的所有图像文件

    Args:
        directory (str): 包含图像文件的目录路径
    """
    # 支持的图像格式
    supported_formats = (".png", ".jpg", ".jpeg", ".bmp", ".tiff")

    # 检查目录是否存在
    if not os.path.isdir(directory):
        print(f"错误：目录 '{directory}' 不存在")
        return

    print(f"\n=== 批量处理目录: {directory} ===")

    # 获取目录中的所有文件
    file_list = os.listdir(directory)

    if not file_list:
        print(f"目录 '{directory}' 为空")
        return

    # 统计处理结果
    success_count = 0
    fail_count = 0

    # 遍历目录中的所有文件
    for file_name in file_list:
        # 检查文件扩展名
        if file_name.lower().endswith(supported_formats):
            input_path = os.path.join(directory, file_name)
            print(f"\n处理: {file_name}")

            if convert_black_to_green(input_path):
                success_count += 1
            else:
                fail_count += 1

    print(f"\n=== 批量处理完成 ===")
    print(f"总计: {len(file_list)} 个文件")
    print(f"成功: {success_count} 个文件")
    print(f"失败: {fail_count} 个文件")


if __name__ == "__main__":
    print("=== OpenCV黑色像素转绿色工具 ===")

    # ==========================
    # 在这里直接设置输入和输出路径
    # ==========================

    # 选项1: 处理单个文件
    # 请将下面的路径替换为您实际的图像文件路径
    # 直接使用原始字符串路径
    input_path = (
        r"f:\workspace\MAAGC\assets\resource\base\image\FacialFeatures\上古灵性.png"
    )
    # 输出图像路径（可选，留空则自动生成）
    output_path = ""  # <-- 留空则自动在原文件名后加"_green"

    print(f"\n准备处理图像: {input_path}")
    # 执行单个文件处理
    result = convert_black_to_green(input_path, output_path)

    if not result:
        print("\n提示：")
        print("1. 请确保输入路径正确，包含完整的文件名和扩展名")
        print("2. 支持的格式：PNG, JPG, JPEG, BMP, TIFF")
        print("3. 示例：input_path = os.path.join('assets', 'image.png')")

    # 选项2: 批量处理目录
    # 要处理的目录路径
    # directory_path = "f:\\workspace\\MAAGC\\assets\\resource\\base\\image\\FacialFeatures"  # <-- 请修改这里的目录路径
    # 执行批量处理
    # batch_convert(directory_path)

    # 注意：如果要使用批量处理，请注释掉单个文件处理部分，取消注释批量处理部分
