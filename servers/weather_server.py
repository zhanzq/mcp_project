# encoding=utf-8
# created @2025/4/24
# created by zhanzq
#

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")


@mcp.tool()
def get_weather(city: str, date: str = "今天") -> str:
    """获取指定地点的天气预报。
    参数：
        city (str): 城市名，如 'New York'。
        date (str): 日期，如 '今天' 或 '明天'。
    返回：
        str: 天气信息。
    """
    # todo: 实现天气查询逻辑
    return f"{city}{date}的天气：温度 25°C，晴朗"


if __name__ == "__main__":
    print(mcp.settings)
    # mcp.run(transport="stdio")
    mcp.run(transport="sse")
