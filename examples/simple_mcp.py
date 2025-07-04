from smolagents import CodeAgent, LiteLLMModel
from smolagents.mcp_client import MCPClient
from smolagents.models import OpenAIModel
from mcp import StdioServerParameters
from dotenv import load_dotenv
import os

load_dotenv(override=True)

# MCP服务器脚本
echo_server_script = '''
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Echo Server")

@mcp.tool()
def echo_tool(text: str) -> str:
    """Echo the input text"""
    return f"Echo: {text}"

mcp.run()
'''

server_params = StdioServerParameters(
    command="python", 
    args=["-c", echo_server_script]
)

with MCPClient(server_params) as mcp_tools:
    model_params = {
        "model_id": f"litellm_proxy/o3-mini",
        "max_completion_tokens": 8192,
        "api_key": os.getenv("API_KEY"),
        "base_url": os.getenv("BASE_URL")
    }

    model = LiteLLMModel(**model_params)
    agent = CodeAgent(
        tools=mcp_tools,
        model=model,
        additional_authorized_imports=["*"]
    )
    
    result = agent.run("请使用echo_tool回显一条消息：Hello MCP!")
    print(result)