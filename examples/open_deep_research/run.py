import argparse
import os
import threading

from dotenv import load_dotenv
from huggingface_hub import login
from scripts.text_inspector_tool import TextInspectorTool
from scripts.text_web_browser import (
    ArchiveSearchTool,
    FinderTool,
    FindNextTool,
    PageDownTool,
    PageUpTool,
    SimpleTextBrowser,
    VisitTool,
)
from scripts.visual_qa import visualizer

from smolagents import (
    CodeAgent,
    GoogleSearchTool,
    # InferenceClientModel,
    LiteLLMModel,
    ToolCallingAgent,
    MCPClient,
    Tool,
    MemoryCompressedToolCallingAgent, 
    MemoryCompressedCodeAgent,
)

from mcp import StdioServerParameters


load_dotenv(override=True)
#login(os.getenv("HF_TOKEN"))

_github_mcp_client = None
_github_tools = None

def get_github_tools():
    """获取GitHub工具，如果不存在则初始化"""
    global _github_mcp_client, _github_tools
    
    if not _github_mcp_client:
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            print("💡 未设置GITHUB_TOKEN，跳过GitHub MCP server集成")
            _github_tools = []
            return _github_tools
            
        try:
            print("🔗 正在连接GitHub MCP server...")
            github_mcp_config = StdioServerParameters(
                command="docker", 
                args=[
                    "run", "-i", "--rm", 
                    "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={github_token}", 
                    "-e", "GITHUB_TOOLSETS=repos,issues,pull_requests", 
                    "ghcr.io/github/github-mcp-server"
                ]
            )
            
            _github_mcp_client = MCPClient(github_mcp_config)
            raw_github_tools = _github_mcp_client.get_tools()
            
            _github_tools = fix_github_tool_types(raw_github_tools)
            
            print(f"✅ GitHub MCP server已连接，获得 {len(_github_tools)} 个GitHub工具")
            
        except Exception as e:
            print(f"⚠️ 连接GitHub MCP server失败: {e}")
            print(f"   错误类型: {type(e).__name__}")
            _github_mcp_client = None
            _github_tools = []
    
    return _github_tools

def fix_github_tool_types(github_tools):
    """
    GitHub MCP server 期望 JSON Schema 的 "number" 类型，但 Python 的 int 会被映射为 "integer" 类型。
    """
    wrapped_tools = []
    
    for tool in github_tools:
        class GitHubToolWrapper(Tool):
            skip_forward_signature_validation = True  # 跳过签名验证
            
            def __init__(self, original_tool):
                self.original_tool = original_tool
                self.name = original_tool.name
                self.description = original_tool.description
                self.inputs = original_tool.inputs.copy()
                self.output_type = original_tool.output_type
                self.is_initialized = True
                
                # 修改 inputs 定义，将 number 类型改为 integer，避免类型验证错误
                for key, input_def in self.inputs.items():
                    if input_def.get("type") == "number":
                        self.inputs[key] = input_def.copy()
                        self.inputs[key]["type"] = "integer"
                
            def forward(self, *args, **kwargs):
                return self.original_tool(*args, **kwargs)
        
        wrapped_tools.append(GitHubToolWrapper(tool))
    
    return wrapped_tools

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "question", type=str, help="for example: 'How many studio albums did Mercedes Sosa release before 2007?'"
    )
    parser.add_argument("--model-id", type=str, default="o1")
    parser.add_argument(
        "--enable-monitoring", 
        action="store_true", 
        help="启用Phoenix监控，查看LLM输入输出 (需要安装phoenix和openinference相关包)"
    )
    return parser.parse_args()


custom_role_conversions = {"tool-call": "assistant", "tool-response": "user"}

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"

BROWSER_CONFIG = {
    "viewport_size": 1024 * 5,
    "downloads_folder": "downloads_folder",
    "request_kwargs": {
        "headers": {"User-Agent": user_agent},
        "timeout": 300,
    },
    "serpapi_key": os.getenv("SERPAPI_API_KEY"),
}

os.makedirs(f"./{BROWSER_CONFIG['downloads_folder']}", exist_ok=True)


def create_agent(model_id="o1"):
    model_params = {
        "model_id": f"litellm_proxy/{model_id}",
        "custom_role_conversions": custom_role_conversions,
        "max_completion_tokens": 8192,
        "api_key": os.getenv("API_KEY"),
        "base_url": os.getenv("BASE_URL")
    }
    
    model = LiteLLMModel(**model_params)
    
    text_limit = 100000
    browser = SimpleTextBrowser(**BROWSER_CONFIG)
    
    WEB_TOOLS = [
        GoogleSearchTool(),
        VisitTool(browser),
        PageUpTool(browser),
        PageDownTool(browser),
        FinderTool(browser),
        FindNextTool(browser),
        ArchiveSearchTool(browser),
        TextInspectorTool(model, text_limit),
    ]
    
    GITHUB_TOOLS = get_github_tools()

    text_webbrowser_agent = MemoryCompressedToolCallingAgent(
        model=model,
        tools=WEB_TOOLS,
        max_steps=20,
        verbosity_level=2,
        planning_interval=4,
        name="search_agent",
        description="""A team member that will search the internet to answer your question.
    Ask him for all your questions that require browsing the web.
    Provide him as much context as possible, in particular if you need to search on a specific timeframe!
    And don't hesitate to provide him with a complex search task, like finding a difference between two webpages.
    Your request must be a real sentence, not a google search! Like "Find me this information (...)" rather than a few keywords.
    """,
    )
    text_webbrowser_agent.prompt_templates["managed_agent"]["task"] += """You can navigate to .txt online files.
    If a non-html page is in another format, especially .pdf or a Youtube video, use tool 'inspect_file_as_text' to inspect it.
    Additionally, if after some searching you find out that you need more information to answer the question, you can use `final_answer` with your request for clarification as argument to request for more information."""

    # 创建GitHub MCP agent（如果有GitHub工具）
    managed_agents = [text_webbrowser_agent]
    
    if GITHUB_TOOLS:
        github_agent = MemoryCompressedToolCallingAgent(
            model=model,
            tools=GITHUB_TOOLS,
            max_steps=10,
            verbosity_level=2,
            planning_interval=3,
            name="github_agent",
            description="""A specialized team member for GitHub operations and code repository analysis.
        Ask him for all your questions related to GitHub and code repositories.
        He can:
        - Search GitHub repositories and code
        - Create and manage GitHub issues and pull requests
        - Analyze repository information and statistics
        - Retrieve and analyze commit history
        - Search for code patterns and implementations
        - Analyze repository structures and dependencies
        - Find popular repositories and trending projects
        
        He specializes in code analysis, repository management, and GitHub ecosystem exploration.
        Provide him with specific requests about repositories, code searches, or GitHub operations.
        """,
        )
        github_agent.prompt_templates["managed_agent"]["task"] += """
        When working with GitHub:
        - Be specific about repository names and owners when known
        - Use appropriate search terms for code and repository searches
        - Consider repository popularity, activity, and maintenance status
        - Analyze code quality, documentation, and community engagement
        - Provide insights about development trends and best practices
        - Help with repository discovery and comparison
        """
        
        managed_agents.append(github_agent)

    manager_agent = MemoryCompressedCodeAgent(
        model=model,
        tools=[visualizer, TextInspectorTool(model, text_limit)],
        max_steps=12,
        verbosity_level=2,
        additional_authorized_imports=["*"],
        planning_interval=4,
        managed_agents=managed_agents,
    )

    return manager_agent


def main():
    args = parse_args()

    # 根据参数决定是否启用监控插桩
    if args.enable_monitoring:
        try:
            from phoenix.otel import register
            from openinference.instrumentation.smolagents import SmolagentsInstrumentor
            
            print("🔍 启用Phoenix监控，LLM输入输出将被记录...")
            register()
            SmolagentsInstrumentor().instrument()
            print("✅ 监控插桩已启用")
        except ImportError as e:
            print(f"❌ 无法启用监控功能，缺少依赖包: {e}")
            print("请安装: pip install 'arize-phoenix[evals]' openinference-instrumentation-smolagents")
            return
    else:
        print("📝 监控功能已禁用，如需启用请添加 --enable-monitoring 参数")

    # 检查GitHub集成配置
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        print("🔗 检测到GITHUB_TOKEN，将集成GitHub MCP server功能")
    else:
        print("💡 提示：设置GITHUB_TOKEN环境变量可启用GitHub集成功能")
        print("   可以创建issues、搜索代码、分析仓库等")
        print("   创建GitHub Personal Access Token: https://github.com/settings/tokens")

    agent = create_agent(model_id=args.model_id)

    answer = agent.run(args.question)

    print(f"Got this answer: {answer}")


if __name__ == "__main__":
    main()
