# encoding=utf-8
# created @2025/4/27
# created by zhanzq
#

import asyncio
from contextlib import AsyncExitStack
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
import os
from utils import parse_tool_result


from openai import OpenAI


class MCPClient:
    def __init__(self):
        # 使用字典存储多个会话
        self.sessions = {}
        self.exit_stack = AsyncExitStack()

        # 尝试获取API密钥
        api_key = os.environ.get("ANTHROPIC_API_KEY", "hello")
        self.llm = OpenAI(api_key=api_key, base_url="http://localhost:11434/v1")

    async def connect_to_server(self, server_config: dict):
        """连接到MCP服务器

        Args:
            server_config: 服务器配置字典
            {
                'id': 服务器唯一标识,
                'script_path': 服务器脚本路径,
                'transport': 传输方式('sse'或'stdio'),
                'sse_url': SSE URL(当transport为'sse'时需要)
            }
        """
        server_id = server_config['id']
        transport = server_config.get('transport', 'sse')

        if transport == "sse":
            print(f"使用SSE传输方式连接服务器 {server_id}")
            sse_url = server_config.get('sse_url', "http://localhost:8000/sse")
            print(f"连接到SSE服务器: {sse_url}")

            try:
                sse_transport = await self.exit_stack.enter_async_context(
                    sse_client(sse_url)
                )
                if isinstance(sse_transport, tuple) and len(sse_transport) == 2:
                    read_stream, write_stream = sse_transport
                    session = await self.exit_stack.enter_async_context(
                        ClientSession(read_stream, write_stream)
                    )
                    self.sessions[server_id] = session
                else:
                    raise ValueError(f"SSE传输格式不正确: {sse_transport}")
            except Exception as e:
                print(f"连接到SSE服务器 {server_id} 失败: {str(e)}")
                raise
        else:
            print(f"使用标准输入输出传输方式连接服务器 {server_id}")
            server_params = self.start_server_stdio(server_config['script_path'])
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            stdio, write = stdio_transport
            session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
            self.sessions[server_id] = session

        await session.initialize()
        response = await session.list_tools()
        print(f"\n已连接到服务器 {server_id}，可用工具:", [tool.name for tool in response.tools])

    async def process_query(self, query: str, history_messages) -> str:
        """处理查询，使用所有可用服务器的工具"""
        history_messages.append({"role": "user", "content": query})

        # 收集所有服务器的工具
        all_tools = []
        for server_id, session in self.sessions.items():
            response = await session.list_tools()
            for tool in response.tools:
                # 为工具名添加服务器前缀以区分
                tool_with_prefix = {
                    "type": "function",
                    "function": {
                        "name": f"{server_id}_{tool.name}",
                        "description": f"[{server_id}] {tool.description}",
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
                }
                all_tools.append(tool_with_prefix)

        # 处理响应和工具调用的逻辑保持不变，但需要解析工具名中的服务器ID
        response = self.llm.chat.completions.create(
            model="qwen2.5",
            messages=history_messages,
            tools=all_tools,
            tool_choice="auto",
            temperature=0.2
        )

        # ... 其余处理逻辑相似，但在调用工具时需要解析服务器ID ...
        tool_results = []
        final_text = []

        assistant_message_content = []
        for content in response.choices:
            if content.finish_reason == "stop":
                final_text.append(content.message.content)
                assistant_message_content.append(content.message.content)
                history_messages.append({
                    "role": "assistant",
                    "content": content.message.content
                })
            elif content.finish_reason == "tool_calls":
                for tool_call in content.message.tool_calls:
                    # 解析服务器ID和实际工具名
                    server_id, tool_name = tool_call.function.name.split('_', 1)
                    tool_args = json.loads(tool_call.function.arguments)

                    # Execute tool call
                    try:
                        result = await self.sessions[server_id].call_tool(tool_name, tool_args)
                        tool_results.append({"call": tool_name, "result": result})
                        final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")
                        tool_result_content = parse_tool_result(tool_name, result.content[0].text)
                    except Exception as e:
                        tool_result_content = f"Error: {str(e)}"
                        final_text.append(f"[Error calling tool {tool_name}: {str(e)}]")

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
                        "content": tool_result_content
                    })

                    # Get next response from Claude
                    response = self.llm.chat.completions.create(
                        model="qwen2.5",
                        messages=history_messages,
                        tools=all_tools,
                        tool_choice="auto",
                        temperature=0.2
                    )

                    final_text.append(response.choices[0].message.content)
                    history_messages.append({
                        "role": "assistant",
                        "content": response.choices[0].message.content
                    })
        # print(json.dumps(history_messages, indent=4, ensure_ascii=False))
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
        """清理所有资源"""
        await self.exit_stack.aclose()


async def main():
    client = MCPClient()
    try:
        # 配置两个服务器
        server1_config = {
            'id': 'server1',
            'script_path': 'servers/weather_server.py',
            'transport': 'sse',
            'sse_url': 'http://localhost:8000/sse'
        }

        server2_config = {
            'id': 'server2',
            'script_path': '',
            'transport': 'sse',
            'sse_url': 'https://mcp.amap.com/sse?key=dd7072d3fbb1ef79013b8207bdb6ea54'
        }

        server3_config = {
            'id': 'server3',
            'script_path': '',
            'transport': 'sse',
            'sse_url': 'https://xingchen-api.xf-yun.com/mcp/xingchen/flow/7315369205743927298/sse'
        }

        # 连接到多个服务器
        await client.connect_to_server(server1_config)
        # await client.connect_to_server(server2_config)
        await client.connect_to_server(server3_config)

        # 运行聊天循环
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
