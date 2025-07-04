import logging
from typing import List
import os
import argparse

from langchain_chroma import Chroma
from smolagents import Tool, CodeAgent, LiteLLMModel

from rag_database_builder import build_rag_database

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv(override=True)

class LocalRetrieverTool(Tool):
    """本地文档检索工具"""
    
    name = "local_retriever"
    description = """
    使用语义搜索从本地文档库中检索相关信息。
    这个工具可以搜索本地的txt、pdf、docx、md等格式的文档。
    支持中文和英文文档检索。
    """
    
    inputs = {
        "query": {
            "type": "string",
            "description": "要搜索的查询内容。应该使用陈述句而不是疑问句，例如：'机器学习模型训练方法' 而不是 '如何训练机器学习模型？'"
        },
        "top_k": {
            "type": "integer", 
            "description": "返回的相关文档数量，默认为5",
            "default": 5,
            "nullable": True
        }
    }
    output_type = "string"
    
    def __init__(self, vector_store: Chroma, **kwargs):
        super().__init__(**kwargs)
        self.vector_store = vector_store
    
    def forward(self, query: str, top_k: int = 5) -> str:
        """执行文档检索"""
        try:
            # 执行相似度搜索
            docs = self.vector_store.similarity_search_with_score(query, k=top_k)
            
            if not docs:
                return "没有找到相关文档。请尝试使用不同的关键词或检查文档是否已正确加载。"
            
            # 格式化结果
            results = []
            for i, (doc, score) in enumerate(docs):
                # 获取文档信息
                filename = doc.metadata.get('filename', '未知文件')
                file_type = doc.metadata.get('file_type', '未知')
                
                results.append(f"""
===== 文档 {i+1} (相似度分数: {score:.3f}) =====
来源文件: {filename} ({file_type})
内容: {doc.page_content.strip()}
""")
            
            return "\n检索到的相关文档:\n" + "\n".join(results)
            
        except Exception as e:
            error_msg = f"检索过程中出现错误: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def get_database_stats(self) -> dict:
        """获取数据库统计信息"""
        try:
            collection = self.vector_store._collection
            count = collection.count()
            return {
                "total_documents": count,
                "database_path": self.vector_store._persist_directory,
                "collection_name": self.vector_store._collection.name
            }
        except Exception as e:
            return {"error": str(e)}

def create_retriever_tool_from_builder(
    force_rebuild: bool = False
) -> LocalRetrieverTool:
    """
    从数据库构建器创建检索工具
    
    Args:
        builder: RAG数据库构建器
        force_rebuild: 是否强制重建数据库
    
    Returns:
        LocalRetrieverTool: 检索工具实例
    """
    # 构建或加载数据库
    vector_store = build_rag_database(force_rebuild=force_rebuild)
    
    # 创建工具
    return LocalRetrieverTool(vector_store)

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="本地RAG文档检索代理",
        epilog="""
使用示例:
  python rag_tool.py "机器学习模型训练方法"
  python rag_tool.py "什么是DynaSaur" --force-rebuild
  python rag_tool.py "深度学习优化算法" --max-steps 30 --verbosity 1
  python rag_tool.py "AI发展趋势" --model-id gpt-4o --max-steps 15
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "query",
        type=str,
        help="要搜索的查询内容"
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="强制重建向量数据库"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=20,
        help="代理最大执行步数 (默认: 20)"
    )
    parser.add_argument(
        "--verbosity",
        type=int,
        default=2,
        help="日志详细程度 (0-2, 默认: 2)"
    )
    parser.add_argument(
        "--planning-interval",
        type=int,
        default=4,
        help="规划间隔步数 (默认: 4)"
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default="o3",
        help="LLM模型ID (默认: o3，将自动添加 litellm_proxy/ 前缀)"
    )
    
    return parser.parse_args()

# 使用示例
if __name__ == "__main__":
    # 解析命令行参数
    args = parse_arguments()
    
    print(f"🔍 正在处理查询: {args.query}")
    print(f"📊 强制重建数据库: {args.force_rebuild}")
    print(f"🤖 使用模型: litellm_proxy/{args.model_id}")
    
    # 创建检索工具
    retriever_tool = create_retriever_tool_from_builder(force_rebuild=args.force_rebuild)
    
    # 配置模型参数
    model_params = {
        "model_id": f"litellm_proxy/{args.model_id}",
        "max_completion_tokens": 8192,
        "api_key": os.getenv("API_KEY"),
        "base_url": os.getenv("BASE_URL")
    }
    model = LiteLLMModel(**model_params)

    # 创建代理
    agent = CodeAgent(
        tools=[retriever_tool],
        model=model,
        max_steps=args.max_steps,
        verbosity_level=args.verbosity,
        planning_interval=args.planning_interval,
        name="local_rag_agent",
        description="""
        一个本地文档检索代理，可以搜索本地文档库中的相关信息。
        这个代理可以搜索本地的txt、pdf、docx、md等格式的文档。
        支持中文和英文文档检索。
        """,
    )
    
    # 运行代理处理查询
    print("🚀 开始执行查询...")
    result = agent.run(args.query)
    print(f"✅ 查询完成!")
    print(f"📋 结果: {result}")