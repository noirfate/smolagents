from dotenv import load_dotenv
import argparse
from browser import CodeBrowserAgent

load_dotenv(override=True)

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="代码浏览器 - 基于大模型的智能代码分析工具")
    parser.add_argument(
        "--model-id",
        type=str,
        default="gpt-5-chat",
        help="使用的LLM模型ID，默认为gpt-5-chat"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=50,
        help="Agent最大执行步数，默认为50"
    )
    parser.add_argument(
        "--db",
        type=str,
        help="codeql database路径，如果不指定则不启用CodeQL功能"
    )
    parser.add_argument(
        "--enable-monitoring",
        action="store_true",
        help="启用Phoenix监控"
    )
    parser.add_argument(
        "--code",
        type=str,
        default="code",
        help="代码路径"
    )
    parser.add_argument(
        "--work",
        type=str,
        default="workspace",
        help="CodeQL工作目录"
    )
    
    return parser.parse_args()

def main():
    """主程序入口"""
    args = parse_args()
    
    # 创建CodeBrowserAgent实例
    # args.db 如果没有提供就是 None，这样只有明确指定时才启用CodeQL功能
    
    agent = CodeBrowserAgent(
        model_id=args.model_id,
        max_steps=args.max_steps,
        db_path=args.db,
        code_dir=args.code,
        work_dir=args.work,
        enable_monitoring=args.enable_monitoring
    )
    
    # 初始化Agent
    if not agent.initialize():
        return
    
    # 运行交互式对话模式
    agent.run_interactive()


if __name__ == "__main__":
    main()