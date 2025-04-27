import asyncio
from typing import Optional
from contextlib import AsyncExitStack
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()  # load environment variables from .env


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        
        # 尝试获取API密钥
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("警告: 未找到ANTHROPIC_API_KEY环境变量")
            api_key = input("请输入Anthropic API密钥: ").strip()
            if not api_key:
                raise ValueError("必须提供Anthropic API密钥")
            # 临时将其设置为环境变量
            os.environ["ANTHROPIC_API_KEY"] = api_key
        
        self.anthropic = Anthropic(api_key=api_key)
        # methods will go here

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

    async def process_query(self, query: str, history_messages=[]) -> str:
        """Process a query using Claude and available tools"""
        history_messages.append(
            {
                "role": "user",
                "content": query
            }
        )

        response = await self.session.list_tools()
        available_tools = [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]

        # Initial Claude API call
        response = self.anthropic.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=history_messages,
            tools=available_tools
        )

        # Process response and handle tool calls
        final_text = []

        for content in response.content:
            if content.type == 'text':
                final_text.append(content.text)
            elif content.type == 'tool_use':
                tool_name = content.name
                tool_args = content.input

                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                # Continue conversation with tool results
                if hasattr(content, 'text') and content.text:
                    history_messages.append({
                        "role": "assistant",
                        "content": content.text
                    })
                history_messages.append({
                    "role": "tool",
                    "content": result.content
                })

                # Get next response from Claude
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=history_messages,
                )

                final_text.append(response.content[0].text)
                history_messages.append({
                    "role": "assistant",
                    "content": response.content[0].text
                })

        return "\n".join(final_text)

    async def process_query(self, query: str, history_messages) -> str:
        """Process a query using Claude and available tools"""
        history_messages.append(
            {
                "role": "user",
                "content": query
            }
        )

        response = await self.session.list_tools()
        available_tools = [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]

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
                    
                print("\n正在处理你的请求，请稍候...")
                response = await self.process_query(query, history_messages=histroy_messages)
                print("\n" + response)

            except KeyboardInterrupt:
                print("\n收到中断信号，正在退出...")
                break
            except Exception as e:
                print(f"\n错误: {str(e)}")
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
    import sys
    import os

    asyncio.run(main())
