# encoding=utf-8
# created @2025/4/27
# created by zhanzq
#

import json


def parse_keling_image_result(image_exec_result: str) -> str:
    """
    解析可灵图像生成接口的返回结果，提取生成的图片 URL。
    Args:
        image_exec_result (dict): 可灵图像接口返回的数据，包括状态码、信息和图像 URL。
    Returns:
        str: 图片的 URL 地址。如果解析失败，返回空字符串。
    Example:
        >>> result = "{'sid': '12345', 'code': 0, 'message': 'success', 'data': {'image_url': 'https://abc/image.jpg'}}"
        >>> parse_keling_image_result(result)
        'https://abc/image.jpg'
    """
    image_info = json.loads(image_exec_result)
    data_path = image_info.get("data", {}).get("image_url")
    if data_path:
        return f"图片生成成功，地址为：{data_path}"
    else:
        return f"图片生成失败"


def parse_tool_result(tool_name: str, tool_exec_result: str) -> str:
    """
    解析工具返回结果
    :param tool_name:
    :param tool_exec_result:
    :return: str
    """
    if tool_name == "文生图-可灵版-MCP":
        return parse_keling_image_result(tool_exec_result)
    else:
        return tool_exec_result
