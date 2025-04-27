# MCP Project (Model Control Protocol)

MCP Project 是一个基于 Model Control Protocol 的智能助手系统，支持多种大语言模型的接入和工具调用功能。

## 项目特点

- 支持多种大语言模型接入（Claude、Qwen等）
- 灵活的工具调用系统
- 支持多种传输方式（SSE、STDIO）
- 支持会话历史记录
- 内置多种实用工具（天气查询、文生图等）

## 系统要求

- Python 3.7+
- Node.js（可选，用于JavaScript服务器）

## 安装说明

1. 克隆项目到本地：
```bash
git clone [repository-url]
cd mcp_project
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 环境配置：
   - 创建 `.env` 文件
   - 添加必要的API密钥，例如：
     ```
     ANTHROPIC_API_KEY=your_api_key_here
     ```

## 使用方法

### 启动Claude客户端

```bash
python client_claud.py
```

### 启动Qwen客户端

```bash
python client_qwen.py
```

### 启动多服务器客户端

```bash
python client_multi_servers.py
```

## 工具配置

工具配置在 `tools.json` 文件中定义，目前支持的工具包括：
- 天气查询
- 文生图（可灵版）

## 项目结构

```
├── servers/            # 服务器实现目录
│   └── server_sse.py   # SSE服务器实现
├── client_claud.py    # Claude模型客户端
├── client_qwen.py     # Qwen模型客户端
├── client_test.py     # 测试客户端
├── client_multi_servers.py  # 多服务器客户端
├── utils.py           # 工具函数
└── tools.json         # 工具配置文件
```

## 开发说明

- 支持SSE和STDIO两种传输方式
- 可以通过修改 `tools.json` 添加新的工具
- 支持会话历史记录，方便上下文理解

## 注意事项

1. 使用前请确保已配置正确的API密钥
2. SSE传输方式默认使用8000端口
3. 请确保有足够的系统权限运行服务

## 贡献指南

欢迎提交Issue和Pull Request来帮助改进项目。

## 许可证

[许可证类型]