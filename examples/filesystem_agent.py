#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
文件系统代理示例

这个示例展示如何创建一个使用文件系统工具的 CodeAgent，
能够进行本地文件操作，包括列目录、读写文件、搜索文件等功能。
"""

import os
from dotenv import load_dotenv

from smolagents import (
    CodeAgent,
    LiteLLMModel,
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
    FileSearchTool,
    FileContentSearchTool,
)

load_dotenv(override=True)


def create_filesystem_agent(model_id="gpt-4o", max_steps=15):
    """创建文件系统代理"""
    
    # 创建模型 - 使用 LiteLLMModel 配置
    model_params = {
        "model_id": f"litellm_proxy/{model_id}",
        "max_completion_tokens": 8192,
        "api_key": os.getenv("API_KEY"),
        "base_url": os.getenv("BASE_URL")
    }
    model = LiteLLMModel(**model_params)
    
    # 初始化文件系统工具
    filesystem_tools = [
        ListDirectoryTool(),      # 列出目录内容
        ReadFileTool(),           # 读取文件
        WriteFileTool(),          # 写入文件
        FileSearchTool(),         # 搜索文件
        FileContentSearchTool(),  # 搜索文件内容
    ]
    
    # 创建代理
    agent = CodeAgent(
        model=model,
        tools=filesystem_tools,
        max_steps=max_steps,
        verbosity_level=2,
        additional_authorized_imports=["*"],  # 允许导入额外的库
        planning_interval=3,
        name="filesystem_agent",
        description="""文件系统操作专家，专门负责本地文件和目录操作。

我可以帮助您完成以下任务：
1. 📁 浏览和列出目录内容
2. 📖 读取文件内容
3. ✏️ 创建和写入文件
4. 🔍 按文件名搜索文件
5. 🔎 在文件内容中搜索文本
6. 📊 分析目录结构
7. 🗂️ 批量处理文件操作
8. 📋 生成文件清单和报告

支持的文件操作包括但不限于：
- 目录浏览和文件列表
- 文本文件读写
- 文件搜索和过滤
- 内容搜索和匹配
- 文件系统分析
- 批量文件处理

请告诉我您想要进行什么样的文件操作！
""",
    )
    
    return agent


def parse_args():
    """解析命令行参数"""
    import argparse
    parser = argparse.ArgumentParser(description="文件系统操作代理")
    parser.add_argument(
        "--model-id", 
        type=str, 
        default="gpt-5-chat",
        help="使用的模型ID，默认为 gpt-5-chat"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="代理的最大执行步数，默认为15"
    )
    parser.add_argument(
        "--task",
        type=str,
        help="要执行的任务，如果不指定则进入交互模式"
    )
    return parser.parse_args()


def main():
    """主函数 - 运行文件系统代理示例"""
    
    args = parse_args()
    
    print("🗂️ 正在创建文件系统代理...")
    print(f"🤖 使用模型: {args.model_id}")
    print(f"📊 最大步数: {args.max_steps}")
    
    agent = create_filesystem_agent(args.model_id, args.max_steps)
    
    # 如果指定了任务，直接执行
    if args.task:
        print(f"\n🤖 执行任务: {args.task}")
        try:
            agent.run(args.task)
        except Exception as e:
            print(f"❌ 执行任务时发生错误: {e}")
        return
    
    # 否则进入交互式会话
    print("\n🤖 启动交互式文件系统代理...")
    print("输入您的文件操作需求，或输入 'exit' 退出")
    print("\n💡 示例任务:")
    print("  • 列出当前目录中的所有Python文件")
    print("  • 读取README.md文件的内容")
    print("  • 创建一个测试文件")
    print("  • 在src目录中搜索包含'Tool'的文件")
    
    while True:
        try:
            user_input = input("\n👤 用户: ").strip()
            if user_input.lower() in ['exit', 'quit', '退出']:
                print("👋 再见！")
                break
            elif user_input:
                print(f"\n🤖 文件系统代理正在处理: {user_input}")
                agent.run(user_input)
        except KeyboardInterrupt:
            print("\n\n👋 用户中断，再见！")
            break
        except Exception as e:
            print(f"\n❌ 发生错误: {e}")

if __name__ == "__main__":
    main()
