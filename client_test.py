import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import Optional

from mcp import ClientSession
from mcp.client.sse import sse_client

from utils import parse_tool_result

# 配置日志记录器
logging.basicConfig(
    level=logging.INFO,  # 设置日志记录级别
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # 设置日志格式
    handlers=[logging.StreamHandler()]  # 控制日志输出到控制台
)

# 获取日志记录器
logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()

    async def connect_to_server(self, sse_url: str):
        """连接到MCP服务器
        :param sse_url: SSE URL
        """
        print(f"连接到SSE服务器: {sse_url}")

        try:
            sse_transport = await self.exit_stack.enter_async_context(
                sse_client(sse_url)
            )
            if isinstance(sse_transport, tuple) and len(sse_transport) == 2:
                read_stream, write_stream = sse_transport
                self.session = await self.exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await self.session.initialize()
                response = await self.session.list_tools()
                print(f"\n已连接到服务器 {sse_url}，可用工具:", [tool.name for tool in response.tools])
            else:
                raise ValueError(f"SSE传输格式不正确: {sse_transport}")
        except Exception as e:
            print(f"连接到SSE服务器 {sse_url} 失败: {str(e)}")
            raise

    async def send_request(self, **kwargs):
        tool_name = kwargs.get("tool_name", "get_weather")
        tool_args = kwargs.get("tool_args", {"city": "北京", "date": "今天"})
        if isinstance(tool_args, str):
            tool_args = json.loads(tool_args)
        # Execute tool call
        try:
            result = await self.session.call_tool(tool_name, tool_args)
            logging.debug(f"call: {tool_name}, args: {json.dumps(tool_args, ensure_ascii=False)} result: {result}")
            tool_result = parse_tool_result(tool_name, result.content[0].text)
        except Exception as e:
            tool_result = f"Error: {str(e)}"
            logging.error(f"[Error calling tool {tool_name}: {str(e)}]")

        logging.info(f"tool_result: {tool_result}")

        return tool_result

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    sse_url = "http://localhost:8000/sse"

    client = MCPClient()
    await client.connect_to_server(sse_url=sse_url)
    tool_name = "get_weather"
    tool_args = {"city": "北京", "date": "今天"}
    res = await client.send_request(tool_name=tool_name, tool_args=tool_args)
    print(res)

    await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
