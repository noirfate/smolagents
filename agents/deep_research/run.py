import argparse
import os

from dotenv import load_dotenv
from scripts.visual_qa import visualizer
from filesystem_agent import create_filesystem_agent

from smolagents import (
    LiteLLMModel,
    MemoryCompressedCodeAgent,
    GitHubTools,
    GoalDriftCallback,
    PlanningStep,
    WebTools,
    OpenAIServerModel,
)

load_dotenv(override=True)

# GitHub工具现在由GitHubTools类统一管理
_github_tools_instance = None

def get_github_tools():
    """获取GitHub工具实例的工具列表"""
    global _github_tools_instance
    
    if _github_tools_instance is None:
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            print("💡 未设置GITHUB_TOKEN，跳过GitHub MCP server集成")
            return []
        
        try:
            _github_tools_instance = GitHubTools(github_token)
            return _github_tools_instance.tools
        except Exception as e:
            print(f"⚠️ 创建GitHub工具实例失败: {e}")
            return []
    
    return _github_tools_instance.tools

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "question", type=str, help="for example: 'How many studio albums did Mercedes Sosa release before 2007?'"
    )
    parser.add_argument("--model-id", type=str, default="gpt-5-chat")
    parser.add_argument(
        "--max-steps", 
        type=int, 
        default=50, 
        help="设置Agent的最大执行步数，默认为50"
    )
    parser.add_argument(
        "--search-engine",
        type=str,
        default="google",
        choices=["google", "duckduckgo"],
        help="选择搜索引擎：google (需要SerpAPI密钥) 或 duckduckgo (免费但结果较少)，默认为google"
    )
    parser.add_argument(
        "--enable-monitoring", 
        action="store_true", 
        help="启用Phoenix监控，查看LLM输入输出 (需要安装phoenix和openinference相关包)"
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="进入多轮对话模式：在初次回答后继续与Agent对话，输入 exit/quit 退出，会话内保持上下文（reset=False）",
    )
    return parser.parse_args()


#custom_role_conversions = {"tool-call": "assistant", "tool-response": "user"}

def create_agent(model_id="gpt-5-chat", max_steps=50, search_engine="google"):
    # 创建模型
    model_params = {
        "model_id": f"{model_id}",
        #"max_completion_tokens": 8192,
        "api_key": os.getenv("API_KEY"),
        "api_base": os.getenv("BASE_URL")
    }
    model = OpenAIServerModel(**model_params)

    # 创建Web工具集合
    web_tools = WebTools(model=model, text_limit=100000, search_engine=search_engine)
    
    GITHUB_TOOLS = get_github_tools()

    text_webbrowser_agent = MemoryCompressedCodeAgent(
        model=model,
        tools=web_tools.tools,
        max_steps=max_steps,
        additional_authorized_imports=["*"],
        verbosity_level=2,
        planning_interval=6,
        name="search_agent",
        aggressive_compression=False,
        description="""A team member that will search the internet to answer your question.
    Ask him for all your questions that require browsing the web.
    Provide him as much context as possible, in particular if you need to search on a specific timeframe!
    And don't hesitate to provide him with a complex search task, like finding a difference between two webpages.
    Your request must be a real sentence, not a google search! Like "Find me this information (...)" rather than a few keywords.
    """,
    )
    text_webbrowser_agent.prompt_templates["managed_agent"]["task"] += """\nHint:\n
    - You can navigate to .txt online files. 
    - visit_page tool native support for paging, you can print without any string interception, like `result=visit_page(url);print(result)`.
    - do not use filter_years parameter for web_search toolunless necessary.
    - If a non-html page is in another format, especially .pdf or a Youtube video, use tool 'inspect_file_as_text' to inspect it.

    Additionally, if after some searching you find out that you need more information to answer the question, you can use `final_answer` with your request for clarification as argument to request for more information."""

    # 创建GitHub MCP agent（如果有GitHub工具）
    managed_agents = [text_webbrowser_agent]
    
    if GITHUB_TOOLS:
        github_agent = MemoryCompressedCodeAgent(
            model=model,
            tools=GITHUB_TOOLS,
            max_steps=max_steps,
            additional_authorized_imports=["*"],
            verbosity_level=2,
            planning_interval=6,
            name="github_agent",
            description="""A specialized team member for GitHub operations and code repository analysis.
        Ask him for all your questions related to GitHub and code repositories.
        your request must contain the repository name or commit hash or issue number or pull request number or user name.
        He can:
        - Search GitHub repositories and code
        - Analyze repository information and statistics
        - Retrieve and analyze commit history
        - Search for code patterns and implementations
        - Analyze repository structures and dependencies
        
        He specializes in code analysis, repository management, and GitHub ecosystem exploration.
        Provide him with specific requests about repositories, code searches, or GitHub operations.
        """,
        )
        github_agent.prompt_templates["managed_agent"]["task"] += """
        When working with GitHub:
        - Be specific about repository names and owners or commit hashes when known
        - Use appropriate search terms for code and repository searches
        - Consider repository popularity, activity, and maintenance status
        - Analyze code quality, documentation, and community engagement
        - Provide insights about development trends and best practices
        - Help with repository discovery and comparison
        """
        
        managed_agents.append(github_agent)

    # 创建文件系统操作agent
    filesystem_agent = create_filesystem_agent(model, max_steps)
    managed_agents.append(filesystem_agent)

    # 创建目标偏离检测回调
    goal_drift_detector = GoalDriftCallback()
    
    manager_agent = MemoryCompressedCodeAgent(
        model=model,
        tools=[visualizer, web_tools.get_text_inspector()],
        max_steps=max_steps,
        verbosity_level=2,
        planning_interval=4,
        managed_agents=managed_agents,
        name="deep_research_agent",
        step_callbacks={
            PlanningStep: goal_drift_detector  # 在每个规划步骤后检测目标偏离
        },
        aggressive_compression=False,
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
    
    print(f"🔍 使用搜索引擎: {args.search_engine}")
    if args.search_engine == "google":
        serpapi_key = os.getenv("SERPAPI_API_KEY")
        if not serpapi_key:
            print("⚠️ 警告：使用Google搜索需要设置SERPAPI_API_KEY环境变量")
            print("   获取密钥: https://serpapi.com/")
            print("   或者使用 --search-engine duckduckgo 切换到免费搜索引擎")
    
    agent = create_agent(
        model_id=args.model_id, 
        max_steps=args.max_steps,
        search_engine=args.search_engine
    )

    # 首次问题
    answer = agent.run(args.question)
    print(f"Got this answer: {answer}")

    # 多轮对话模式：在同一Agent实例上继续追问（reset=False 保留上下文记忆）
    if args.chat:
        print("\n🗣 进入对话模式。提示：输入 'exit' 或 'quit' 退出，会话内输入 '/reset' 可清空历史记忆。\n")
        while True:
            try:
                user_input = input("user>: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 退出对话模式。")
                break

            if not user_input:
                continue

            lower_input = user_input.lower()
            if lower_input in ("exit", "quit", "q"):
                print("👋 退出对话模式。")
                break

            if user_input.startswith("/reset"):
                # 清空记忆但保留系统提示
                agent.memory.reset()
                print("♻️ 已清空会话历史记忆。")
                continue

            # 继续在同一会话中运行，保留上下文
            follow_up_answer = agent.run(user_input, reset=False, max_steps=args.max_steps)
            print(f"Agent: {follow_up_answer}")


if __name__ == "__main__":
    main()
