import os
import sys
import asyncio
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict, Any

import torch
from transformers import AutoTokenizer, AutoModel
from sentence_transformers import CrossEncoder

from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc, setup_logger
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.llm.openai import openai_complete_if_cache
from lightrag.llm.hf import hf_embed

# 临时修改 sys.argv 以避免与 lightrag.api 的 argparse 冲突
# lightrag.api.config 在导入时会调用 parse_args()
_original_argv = sys.argv.copy()
sys.argv = [sys.argv[0]]  # 只保留脚本名，清空其他参数
from lightrag.api.routers.document_routes import pipeline_index_files
sys.argv = _original_argv  # 恢复原始参数

from smolagents import Tool

from dotenv import load_dotenv
load_dotenv(override=True)

# ========== 配置 ==========
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "Qwen/Qwen3-Reranker-0.6B")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5-chat")
LLM_BASE_URL = os.getenv("BASE_URL", "http://localhost:dummy/v1")
LLM_API_KEY = os.getenv("API_KEY", "dummy")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "10"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ========== 全局模型缓存 ==========
import threading

_model_lock = threading.Lock()  # 仅用于模型加载时的单例保护
_embedding_model = None
_embedding_tokenizer = None
_reranker_model = None


def load_embedding_model():
    """加载 Embedding 模型（线程安全）"""
    global _embedding_model, _embedding_tokenizer
    
    if _embedding_model is not None:
        return _embedding_model, _embedding_tokenizer
    
    with _model_lock:
        if _embedding_model is None:
            print(f"🔧 加载 Embedding 模型: {EMBEDDING_MODEL}")
            _embedding_tokenizer = AutoTokenizer.from_pretrained(
                EMBEDDING_MODEL, trust_remote_code=True
            )
            _embedding_model = AutoModel.from_pretrained(
                EMBEDDING_MODEL, trust_remote_code=True
            ).to(DEVICE)
            _embedding_model.eval()
            print(f"✅ Embedding 模型加载完成，设备: {DEVICE}")
    
    return _embedding_model, _embedding_tokenizer


def load_reranker_model():
    """
    加载 Reranker 模型（线程安全）
    """
    global _reranker_model
    
    if _reranker_model is not None:
        return _reranker_model
    
    with _model_lock:
        if _reranker_model is None:
            print(f"🔧 加载 Reranker 模型: {RERANKER_MODEL}")
            _reranker_model = CrossEncoder(RERANKER_MODEL, device=DEVICE)
            
            print(f"✅ Reranker 加载完成，设备: {DEVICE}")
    
    return _reranker_model


async def custom_embedding_func(texts: List[str]) -> np.ndarray:
    """
    自定义嵌入函数（使用 LightRAG 的 hf_embed + 增强）
    
    Args:
        texts: 要嵌入的文本列表
        
    Returns:
        嵌入向量数组，形状为 (len(texts), embedding_dim)
    """
    model, tokenizer = load_embedding_model()
    
    # 使用 LightRAG 的 hf_embed 进行推理
    embeddings = await hf_embed(texts, tokenizer, model)
    
    # 添加 L2 归一化（对余弦相似度很重要）
    embeddings_tensor = torch.from_numpy(embeddings)
    embeddings_tensor = torch.nn.functional.normalize(embeddings_tensor, p=2, dim=1)
    
    return embeddings_tensor.numpy()


async def custom_rerank_func(
    query: str,
    documents: List[str],
    top_n: Optional[int] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Qwen3 重排序函数（逐个处理避免 padding 问题）
    
    Args:
        query: 查询文本
        documents: 文档列表
        top_n: 返回前 N 个结果
        
    Returns:
        重排序结果列表，每个元素包含 index 和 relevance_score
    """
    if not documents:
        return []
    
    model = load_reranker_model()
    
    try:
        # 逐个处理文档以避免批量处理的 padding 问题
        rerank_scores = []
        
        for i, doc in enumerate(documents):
            try:
                query_doc_pair = [query, doc]
                
                score = model.predict([query_doc_pair], show_progress_bar=False)[0]
                rerank_scores.append(float(score))
                
            except Exception as e:
                print(f"⚠️ 文档 {i} rerank 失败: {e}")
                rerank_scores.append(0.0)
        
        results = [
            {"index": i, "relevance_score": score}
            for i, score in enumerate(rerank_scores)
        ]
        
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        if top_n is not None and top_n > 0:
            results = results[:top_n]
            
        return results
        
    except Exception as e:
        print(f"⚠️ Reranker 整体失败: {e}")
        import traceback
        traceback.print_exc()
        return [{"index": i, "relevance_score": 0.0} for i in range(len(documents))]


async def llm_model_func(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: List = [],
    **kwargs
) -> str:
    """
    LLM 函数，使用 OpenAI 兼容 API
    
    Args:
        prompt: 用户提示
        system_prompt: 系统提示
        history_messages: 历史消息
        
    Returns:
        LLM 生成的响应
    """
    return await openai_complete_if_cache(
        LLM_MODEL,
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        **kwargs,
    )


class LightRAGManager:
    """
    LightRAG 管理器，负责 RAG 的生命周期管理
    
    职责：
    - 初始化和加载 LightRAG 实例
    - 构建文档索引
    - 执行查询
    - 管理数据库状态
    """
    
    def __init__(
        self,
        working_dir: str = "./lightrag_storage",
        embedding_dim: Optional[int] = None,
    ):
        """
        初始化 RAG 管理器
        
        Args:
            working_dir: LightRAG 工作目录
            embedding_dim: 嵌入维度（如果为 None，会自动检测）
        """
        self.working_dir = working_dir
        self.embedding_dim = embedding_dim
        self.rag: Optional[LightRAG] = None
        self._initialized = False
        
        setup_logger("lightrag")
    
    async def initialize(self) -> None:
        if self._initialized:
            return
        
        print(f"🔧 初始化 LightRAG，工作目录: {self.working_dir}")
        
        os.makedirs(self.working_dir, exist_ok=True)
        
        if self.embedding_dim is None:
            print("🔍 检测 Embedding 维度...")
            test_embedding = await custom_embedding_func(["test"])
            self.embedding_dim = test_embedding.shape[1]
            print(f"📐 Embedding 维度: {self.embedding_dim}")
        
        self.rag = LightRAG(
            working_dir=self.working_dir,
            llm_model_func=llm_model_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=self.embedding_dim,
                func=custom_embedding_func,
            ),
            rerank_model_func=custom_rerank_func,
        )
        
        await self.rag.initialize_storages()
        await initialize_pipeline_status()
        
        self._initialized = True
        print("✅ LightRAG 初始化完成")
    
    def is_database_built(self) -> bool:
        """
        检查数据库是否已构建
        
        Returns:
            如果数据库存在且非空，返回 True
        """
        if not os.path.exists(self.working_dir):
            return False
        
        required_files = [
            "kv_store_full_docs.json",  # 文档存储
            "vdb_chunks.json",          # 向量数据库
        ]
        
        for filename in required_files:
            file_path = os.path.join(self.working_dir, filename)
            if not os.path.exists(file_path):
                return False
            if os.path.getsize(file_path) == 0:
                return False
        
        return True
    
    async def build_from_directory(
        self,
        documents_path: str,
        force_rebuild: bool = False
    ) -> int:
        """
        从目录构建文档索引
        
        Args:
            documents_path: 文档目录路径
            force_rebuild: 是否强制重建
            
        Returns:
            成功处理的文件数量
        """
        if not self._initialized:
            await self.initialize()
        
        if not force_rebuild and self.is_database_built():
            print("📚 数据库已存在，跳过构建（使用 force_rebuild=True 强制重建）")
            return 0
        
        directory_path = Path(documents_path)
        file_paths = []
        for file_path in directory_path.rglob("*"):
            if file_path.is_file():
                file_paths.append(file_path)
        
        if not file_paths:
            print(f"⚠️ 在 {documents_path} 中未找到文件")
            return 0
        
        print(f"📊 找到 {len(file_paths)} 个文件，开始索引...")
        
        try:
            await pipeline_index_files(self.rag, file_paths)
            print(f"✅ 文件索引完成（查看日志了解处理详情）")
            return len(file_paths)
        except Exception as e:
            print(f"❌ 索引文件时出错: {e}")
            import traceback
            traceback.print_exc()
            return 0
    
    async def query(
        self,
        query: str,
        mode: str = "mix",
        top_k: int = 5,
        use_rerank: bool = False
    ) -> str:
        """
        执行查询
        
        Args:
            query: 查询文本
            mode: 检索模式 (naive/local/global/hybrid/mix)
            top_k: 返回结果数量
            use_rerank: 是否使用重排序
            
        Returns:
            查询结果
        """
        if not self._initialized:
            await self.initialize()
        
        if not self.is_database_built():
            return "❌ 数据库未构建。请先构建文档索引。"
        
        result = await self.rag.aquery(
            query,
            param=QueryParam(
                mode=mode,
                top_k=top_k,
                chunk_top_k=top_k * 2,
                enable_rerank=use_rerank,
            )
        )
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取数据库统计信息
        
        Returns:
            统计信息字典
        """
        stats = {
            "working_dir": self.working_dir,
            "embedding_dim": self.embedding_dim,
            "embedding_model": EMBEDDING_MODEL,
            "reranker_model": RERANKER_MODEL,
            "llm_model": LLM_MODEL,
            "device": DEVICE,
            "database_built": self.is_database_built(),
            "initialized": self._initialized,
        }
        
        return stats


class LightRAGRetrieverTool(Tool):
    """
    基于 LightRAG 的检索工具
    """
    
    name = "lightrag_retriever"
    description = """基于知识图谱的语义检索工具，从本地文档知识库中检索相关信息。"""
    
    inputs = {
        "query": {
            "type": "string",
            "description": "要搜索的内容，不要使用简单的关键词，查询尽量具体且用意明确。"
        }
    }
    output_type = "string"
    
    def __init__(
        self,
        working_dir: str = "./lightrag_storage",
        **kwargs
    ):
        """
        初始化 LightRAG 检索工具
        
        Args:
            working_dir: LightRAG 工作目录（数据库存储位置）
        """
        super().__init__(**kwargs)
        
        self.working_dir = working_dir
        
        self.rag_manager = LightRAGManager(working_dir=working_dir)
        
        try:
            self._run_async_init()
            
            if self.rag_manager.is_database_built():
                print("✅ LightRAG 数据库加载成功")
                stats = self.rag_manager.get_stats()
                print(f"   - 工作目录: {stats['working_dir']}")
                print(f"   - 嵌入维度: {stats['embedding_dim']}")
                print(f"   - 设备: {stats['device']}")
            else:
                print("⚠️ 未找到 LightRAG 数据库")
                print(f"   工作目录: {self.working_dir}")
            
        except Exception as e:
            print(f"⚠️ 初始化 LightRAG 时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _run_async_init(self):
        """
        运行异步初始化
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        lambda: asyncio.run(self.rag_manager.initialize())
                    )
                    future.result(timeout=60.0)
            else:
                loop.run_until_complete(self.rag_manager.initialize())
        except RuntimeError:
            asyncio.run(self.rag_manager.initialize())
    
    def forward(
        self,
        query: str
    ) -> str:
        """
        从文档库中检索相关信息
        
        Args:
            query: 查询内容
            
        Returns:
            基于文档内容生成的综合答案
        """

        mode = "mix"
        top_k = RAG_TOP_K
        use_rerank = True
        try:
            if not self.rag_manager.is_database_built():
                return "未找到相关内容。数据库尚未构建。"
            
            result = self._run_async_query(query, mode, top_k, use_rerank)
            return result
            
        except Exception as e:
            error_msg = f"检索过程中出现错误: {str(e)}"
            return error_msg
    
    def _run_async_query(
        self,
        query: str,
        mode: str,
        top_k: int,
        use_rerank: bool
    ) -> str:
        """
        运行异步查询
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        lambda: asyncio.run(self.rag_manager.query(query, mode, top_k, use_rerank))
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.rag_manager.query(query, mode, top_k, use_rerank)
                )
        except RuntimeError:
            return asyncio.run(self.rag_manager.query(query, mode, top_k, use_rerank))
    
    
    def get_stats(self) -> Dict[str, Any]:
        return self.rag_manager.get_stats()
    

def example_with_smolagents():
    """与 smolagents 集成使用示例"""
    print("\n" + "=" * 80)
    print("📖 LightRAG + Smolagents 集成示例")
    print("=" * 80 + "\n")
    
    from smolagents import CodeAgent, LiteLLMModel
    
    tool = LightRAGRetrieverTool(working_dir="./lightrag_storage")
    
    model = LiteLLMModel(
        model_id=f"litellm_proxy/{LLM_MODEL}",
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL")
    )
    
    agent = CodeAgent(
        tools=[tool],
        model=model,
        max_steps=20,
        verbosity_level=2,
    )
    
    query = "使用文档检索工具，总结DynaSaur相关内容"
    print(f"🤖 Agent 查询: {query}")
    print("-" * 80)
    result = agent.run(query)
    print(f"\n✅ Agent 结果:\n{result}")


async def example_manual_workflow():
    """手动工作流示例（更灵活的控制）"""
    print("\n" + "=" * 80)
    print("📖 LightRAG 手动工作流示例")
    print("=" * 80 + "\n")
    
    print("步骤1: 创建 RAG 管理器")
    manager = LightRAGManager(working_dir="./lightrag_storage")
    await manager.initialize()
    
    print("\n步骤2: 检查数据库状态")
    if not manager.is_database_built():
        print("   数据库未构建，开始构建...")
        file_count = await manager.build_from_directory("./my_documents")
        print(f"   已索引 {file_count} 个文件")
    else:
        print("   数据库已存在")
    
    print("\n步骤3: 执行查询")
    result = await manager.query(
        query="什么是DynaSaur",
        mode="mix",
        top_k=RAG_TOP_K,
        use_rerank=True
    )
    print(f"   查询结果:\n{result}")
    
    print("\n步骤4: 查看统计信息")
    stats = manager.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

def main():
    """测试函数"""
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "--agent":
            example_with_smolagents()
        elif mode == "--manual":
            asyncio.run(example_manual_workflow())
        else:
            print(f"❌ 未知模式: {mode}")
            print("\n可用模式:")
            print("  (无参数)  - 独立使用示例")
            print("  --agent   - 与 smolagents 集成示例")
            print("  --manual  - 手动工作流示例")

if __name__ == "__main__":
    main()
