import logging
from typing import List, Optional, Union
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

try:
    from sentence_transformers import CrossEncoder
    RERANK_AVAILABLE = True
except ImportError:
    RERANK_AVAILABLE = False
    logger.warning("sentence-transformers未安装，无法使用rerank功能")

class LocalRetrieverTool(Tool):
    """本地文档检索工具，支持rerank模型"""
    
    name = "local_retriever"
    description = """
    使用语义搜索从本地文档库中检索相关信息。
    这个工具可以搜索本地的txt、pdf、docx、md等格式的文档。
    支持中文和英文文档检索。
    可选择使用rerank模型进行结果重排序以提高检索精度。
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
        },
        "use_rerank": {
            "type": "boolean",
            "description": "是否使用rerank模型进行结果重排序，默认为True",
            "default": True,
            "nullable": True
        }
    }
    output_type = "string"
    
    def __init__(
        self, 
        vector_store: Chroma, 
        rerank_model: str = "Qwen/Qwen3-Reranker-0.6B",
        rerank_top_k: int = 20,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.vector_store = vector_store
        self.rerank_model_name = rerank_model
        self.rerank_top_k = rerank_top_k
        self.rerank_model = None
        
        # 初始化rerank模型
        if RERANK_AVAILABLE:
            self._init_rerank_model()
    
    def _init_rerank_model(self):
        """初始化rerank模型"""
        try:
            logger.info(f"正在加载rerank模型: {self.rerank_model_name}")
            self.rerank_model = CrossEncoder(self.rerank_model_name)
            logger.info("Rerank模型加载成功")
        except Exception as e:
            logger.error(f"加载rerank模型失败: {e}")
            self.rerank_model = None
    
    def _rerank_documents(self, query: str, docs_with_scores: List[tuple]) -> List[tuple]:
        """使用rerank模型对文档进行重排序"""
        if not self.rerank_model or not docs_with_scores:
            # 返回格式：(doc, rerank_score, original_score)，这里用原始分数作为rerank分数
            return [(doc, original_score, original_score) for doc, original_score in docs_with_scores]
        
        try:
            # 逐个处理以避免批量处理的padding问题
            rerank_scores = []
            for doc, original_score in docs_with_scores:
                # 限制文档长度避免超出模型限制
                content = doc.page_content[:512]
                query_doc_pair = [query, content]
                
                try:
                    # 单个处理避免批量padding问题
                    score = self.rerank_model.predict([query_doc_pair])[0]
                    rerank_scores.append(float(score))
                except Exception as e:
                    logger.warning(f"单个文档rerank失败，使用原始分数: {e}")
                    rerank_scores.append(float(original_score))
            
            # 组合原始文档和新分数
            reranked_docs = []
            for i, (doc, original_score) in enumerate(docs_with_scores):
                reranked_docs.append((doc, rerank_scores[i], original_score))
            
            # 按rerank分数排序
            reranked_docs.sort(key=lambda x: x[1], reverse=True)
            
            # 返回格式：(doc, rerank_score, original_score)
            return reranked_docs
            
        except Exception as e:
            logger.error(f"Rerank过程出错: {e}")
            # 返回格式：(doc, rerank_score, original_score)，使用原始分数
            return [(doc, original_score, original_score) for doc, original_score in docs_with_scores]
    
    def forward(self, query: str, top_k: int = 5, use_rerank: bool = True) -> str:
        """执行文档检索"""
        try:
            # 第一阶段：粗检索
            # 如果使用rerank，则检索更多候选文档
            initial_k = self.rerank_top_k if (use_rerank and self.rerank_model) else top_k
            
            # 执行相似度搜索
            docs_with_scores = self.vector_store.similarity_search_with_score(query, k=initial_k)
            
            if not docs_with_scores:
                return "没有找到相关文档。请尝试使用不同的关键词或检查文档是否已正确加载。"
            
            # 第二阶段：重排序（如果启用）
            if use_rerank and self.rerank_model:
                logger.info(f"使用rerank模型重排序 {len(docs_with_scores)} 个候选文档")
                reranked_docs = self._rerank_documents(query, docs_with_scores)
                
                # 取top_k个重排序后的文档
                final_docs = reranked_docs[:top_k]
                
                # 格式化结果（包含rerank信息）
                results = []
                for i, (doc, rerank_score, original_score) in enumerate(final_docs):
                    filename = doc.metadata.get('filename', '未知文件')
                    file_type = doc.metadata.get('file_type', '未知')
                    
                    results.append(f"""
===== 文档 {i+1} =====
来源文件: {filename} ({file_type})
原始相似度分数: {original_score:.3f}
Rerank分数: {rerank_score:.3f}
内容: {doc.page_content.strip()}
""")
                
                return f"\n使用rerank模型重排序后的相关文档 (从{initial_k}个候选中选择{top_k}个):\n" + "\n".join(results)
            
            else:
                # 不使用rerank，直接返回embedding检索结果
                final_docs = docs_with_scores[:top_k]
                
                # 格式化结果
                results = []
                for i, (doc, score) in enumerate(final_docs):
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
                "collection_name": self.vector_store._collection.name,
                "rerank_model": self.rerank_model_name if self.rerank_model else "未加载",
                "rerank_available": RERANK_AVAILABLE
            }
        except Exception as e:
            return {"error": str(e)}

def create_retriever_tool_from_builder(
    force_rebuild: bool = False,
    rerank_model: str = "Qwen/Qwen3-Reranker-0.6B",
    rerank_top_k: int = 20
) -> LocalRetrieverTool:
    """
    从数据库构建器创建检索工具
    
    Args:
        force_rebuild: 是否强制重建数据库
        rerank_model: rerank模型名称
        rerank_top_k: rerank阶段的候选文档数量
    
    Returns:
        LocalRetrieverTool: 检索工具实例
    """
    # 构建或加载数据库
    vector_store = build_rag_database(force_rebuild=force_rebuild)
    
    # 创建工具
    return LocalRetrieverTool(
        vector_store, 
        rerank_model=rerank_model, 
        rerank_top_k=rerank_top_k
    )

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="本地RAG文档检索代理",
        epilog="""
使用示例:
  python rag_tool.py "机器学习模型训练方法"
  python rag_tool.py "什么是DynaSaur" --force-rebuild
  python rag_tool.py "深度学习优化算法" --max-steps 30 --verbosity 1
  python rag_tool.py "AI发展趋势" --model-id gpt-4o --max-steps 15 --no-rerank
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
    parser.add_argument(
        "--rerank-model",
        type=str,
        default="Qwen/Qwen3-Reranker-0.6B",
        help="Rerank模型名称 (默认: Qwen/Qwen3-Reranker-0.6B，备选: BAAI/bge-reranker-base)"
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="禁用rerank模型"
    )
    parser.add_argument(
        "--rerank-top-k",
        type=int,
        default=20,
        help="Rerank阶段的候选文档数量 (默认: 20)"
    )
    
    return parser.parse_args()

# 使用示例
if __name__ == "__main__":
    # 解析命令行参数
    args = parse_arguments()
    
    print(f"🔍 正在处理查询: {args.query}")
    print(f"📊 强制重建数据库: {args.force_rebuild}")
    print(f"🤖 使用模型: litellm_proxy/{args.model_id}")
    print(f"🎯 Rerank模型: {args.rerank_model if not args.no_rerank else '已禁用'}")
    
    # 创建检索工具
    retriever_tool = create_retriever_tool_from_builder(
        force_rebuild=args.force_rebuild,
        rerank_model=args.rerank_model,
        rerank_top_k=args.rerank_top_k
    )
    
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
        description=f"""
        一个本地文档检索代理，可以搜索本地文档库中的相关信息。
        这个代理可以搜索本地的txt、pdf、docx、md等格式的文档。
        支持中文和英文文档检索。
        {'已启用rerank模型进行结果重排序。' if not args.no_rerank else '未启用rerank模型。'}
        """,
    )
    
    # 运行代理处理查询
    print("🚀 开始执行查询...")
    result = agent.run(args.query)
    print(f"✅ 查询完成!")
    print(f"📋 结果: {result}")