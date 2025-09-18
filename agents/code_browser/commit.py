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
    parser.add_argument(
        "--file",
        type=str,
        help="要分析的commit文件路径，每行包含一个commit id"
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
    
    with open(args.file, "r") as f:
        commit_ids = f.readlines()
    
    # 初始化Agent
    if not agent.initialize():
        return

    results = []
    for commit_id in commit_ids:
        commit_id = commit_id.strip()
        task = f"""分析commit {commit_id}的代码，分析提交的作用和影响，判断其是否为bug修复或安全修复，安全修复的意思是修复了可利用的安全漏洞，回复格式为：
        ### {commit_id}
        #### 结论
        是安全修复或不是安全修复
        #### 分析
        代码的实际作用和影响
        #### 利用方法
        若为安全修复，则提供具体的利用步骤，若不是安全修复则输出空字符串
        """
        print(f"🔍 开始分析commit {commit_id}")
        result = agent.run_single_task(task)
        print(f"🔍 分析完成，结果为：\n{result}\n")
        results.append(result)
    
    print(f"🔍 分析完成，结果已保存到commit_results.md")

    with open("commit_results.md", "w", encoding="utf-8") as f:
        f.write("\n\n".join(results))

if __name__ == "__main__":
    main()