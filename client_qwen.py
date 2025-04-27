import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from contextlib import AsyncExitStack
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from openai import OpenAI

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
        
        # 尝试获取API密钥
        api_key = os.environ.get("ANTHROPIC_API_KEY", "hello")
        self.llm = OpenAI(api_key=api_key, base_url="http://localhost:11434/v1")

    def start_server_sse(self, server_script_path):
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")
        # 启动新的服务器进程
        print("正在启动服务器...")
        try:
            subprocess.Popen(
                [sys.executable, server_script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # 等待服务器启动
            time.sleep(3)
            print("服务器已启动")
        except Exception as e:
            print(f"启动服务器失败: {str(e)}")
            raise

    def start_server_stdio(self, server_script_path):
        is_python = server_script_path.endswith('.py')
        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        return server_params

    async def connect_to_server(self, server_script_path: str, transport: str = "sse"):
        """Connect to an MCP server  

        Args:
            :param server_script_path: Path to the server script (.py or .js)
            :param transport: Transport method, either 'sse' or 'stdio'
        """
        # 根据服务器脚本内容选择传输方式
        if transport == "sse":
            # 使用SSE传输
            print("使用SSE传输方式连接服务器")
            # 默认端口为8000（uvicorn默认端口）
            sse_url = "http://localhost:8000/sse"
            print(f"连接到SSE服务器: {sse_url}")
            # 启动服务器
            # self.start_server_sse(server_script_path)
            try:
                sse_transport = await self.exit_stack.enter_async_context(
                    sse_client(sse_url)
                )
                # SSE 传输返回一个元组 (read_stream, write_stream)
                if isinstance(sse_transport, tuple) and len(sse_transport) == 2:
                    read_stream, write_stream = sse_transport
                    self.session = await self.exit_stack.enter_async_context(
                        ClientSession(read_stream, write_stream)
                    )
                else:
                    print(f"SSE传输返回了意外的结果: {sse_transport}")
                    raise ValueError(f"SSE传输格式不正确: {sse_transport}")
            except Exception as e:
                print(f"连接到SSE服务器失败: {str(e)}")
                import traceback
                traceback.print_exc()
                raise
        else:
            # 使用stdio传输
            print("使用标准输入输出传输方式连接服务器")
            server_params = self.start_server_stdio(server_script_path)
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            self.stdio, self.write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\n已连接到服务器，可用工具:", [tool.name for tool in tools])

    async def process_query(self, query: str, history_messages) -> str:
        """Process a query using Claude and available tools"""
        history_messages.append(
            {
                "role": "user",
                "content": query
            }
        )

        response = await self.session.list_tools()

        # Qwen模型的工具调用格式
        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            k: {
                                "type": v.get("type"),
                                "description": v.get("description")
                            } for k, v in tool.inputSchema.get("properties").items()
                        },
                        "required": list(tool.inputSchema.keys())
                    }
                }
            } for tool in response.tools
        ]

        # print(json.dumps(available_tools, indent=4, ensure_ascii=False))
        # Initial Qwen API call
        response = self.llm.chat.completions.create(
            model="qwen2.5",
            messages=history_messages,
            tools=available_tools,
            tool_choice="auto",
            temperature=0.2
        )

        # Process response and handle tool calls
        final_text = []

        assistant_message_content = []
        for content in response.choices:
            if content.finish_reason == "stop":
                final_text.append(content.message.content)
                assistant_message_content.append(content.message.content)
                history_messages.append({
                    "role": "assistant",
                    "content": response.choices[0].message.content
                })
            elif content.finish_reason == "tool_calls":
                tool_chosen = content.message.tool_calls[0]
                tool_name = tool_chosen.function.name
                tool_args = tool_chosen.function.arguments
                tool_args = json.loads(tool_args)
                # Execute tool call
                try:
                    result = await self.session.call_tool(tool_name, tool_args)
                    logging.info(f"call: {tool_name}, result: {result}")
                    logging.info(f"[Calling tool {tool_name} with args {tool_args}]")
                    tool_result = parse_tool_result(tool_name, result.content[0].text)
                except Exception as e:
                    tool_result = f"Error: {str(e)}"
                    logging.error(f"[Error calling tool {tool_name}: {str(e)}]")

                assistant_message_content.append(content.message.content)
                history_messages.append({
                    "role": "assistant",
                    "tool_calls": [{
                        "id": it.id,
                        "type": it.type,
                        "function": {
                            "name": it.function.name,
                            "arguments": it.function.arguments
                        }
                    } for it in content.message.tool_calls]
                })
                history_messages.append({
                    "role": "tool",
                    "content": tool_result
                })

                # Get next response from Claude
                response = self.llm.chat.completions.create(
                    model="qwen2.5",
                    messages=history_messages,
                    tools=available_tools,
                    tool_choice="auto",
                    temperature=0.2
                )

                final_text.append(response.choices[0].message.content)
                history_messages.append({
                    "role": "assistant",
                    "content": response.choices[0].message.content
                })
        return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP客户端已启动！")
        print("输入你的问题或输入'quit'退出。")
        print("示例查询: '查询北京的天气'")

        histroy_messages = []
        while True:
            try:
                query = input("\n问题: ").strip()

                if query.lower() in ['quit', '退出', 'exit', 'q']:
                    break

                if not query:
                    continue
                    
                logging.info("正在处理你的请求，请稍候...")
                response = await self.process_query(query, history_messages=histroy_messages)
                print("\n" + response)

            except KeyboardInterrupt:
                logging.info("收到中断信号，正在退出...")
                break
            except Exception as e:
                logging.error(f"错误: {str(e)}")
                import traceback
                traceback.print_exc()

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    if len(sys.argv) < 2:
        print("用法: python client.py <服务器脚本路径>")
        sys.exit(1)

    client = MCPClient()
    try:
        server_path = sys.argv[1]
        if not os.path.exists(server_path):
            print(f"错误: 服务器脚本 '{server_path}' 不存在")
            sys.exit(1)
            
        try:
            await client.connect_to_server(server_path)
            await client.chat_loop()
        except FileNotFoundError:
            print(f"错误: 找不到服务器脚本 '{server_path}'")
            sys.exit(1)
        except Exception as e:
            print(f"连接到服务器时出错: {str(e)}")
            sys.exit(1)
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
