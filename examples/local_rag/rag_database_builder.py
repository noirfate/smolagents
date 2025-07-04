"""
RAG数据库构建器

支持从环境变量或.env文件获取配置参数。

使用方法：
1. 创建 .env 文件（可选）：
   RAG_DOCUMENTS_PATH=./my_documents
   RAG_VECTOR_DB_PATH=./local_vector_db
   RAG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
   RAG_CHUNK_SIZE=1000
   RAG_CHUNK_OVERLAP=200
   RAG_COLLECTION_NAME=local_documents
   RAG_FORCE_REBUILD=false

2. 使用环境变量：
   builder = RAGDatabaseBuilder()  # 从环境变量获取所有配置

3. 显式传递参数：
   builder = RAGDatabaseBuilder(
       documents_path="./docs",
       embedding_model="shibing624/text2vec-base-chinese"
   )
"""

import os
import logging
from pathlib import Path
from typing import List, Optional
import hashlib

# 环境变量支持
from dotenv import load_dotenv

# 文档加载器
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredFileLoader,
    DirectoryLoader
)
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# 加载环境变量
load_dotenv()
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# 支持的环境变量：
# RAG_DOCUMENTS_PATH - 文档路径
# RAG_VECTOR_DB_PATH - 向量数据库路径
# RAG_EMBEDDING_MODEL - 嵌入模型名称
# RAG_CHUNK_SIZE - 分块大小
# RAG_CHUNK_OVERLAP - 分块重叠大小
# RAG_COLLECTION_NAME - 集合名称
# RAG_FORCE_REBUILD - 是否强制重建 (true/false)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RAGDatabaseBuilder:
    """本地RAG向量数据库构建器"""
    
    def __init__(
        self,
        documents_path: str = None,
        vector_db_path: str = None,
        embedding_model: str = None,
        chunk_size: int = None,
        chunk_overlap: int = None,
        collection_name: str = None
    ):
        # 从环境变量获取配置，如果没有提供参数的话
        self.documents_path = Path(
            documents_path or 
            os.getenv("RAG_DOCUMENTS_PATH", "./my_documents")
        )
        self.vector_db_path = Path(
            vector_db_path or 
            os.getenv("RAG_VECTOR_DB_PATH", "./local_vector_db")
        )
        self.embedding_model_name = (
            embedding_model or 
            os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        )
        self.chunk_size = (
            chunk_size or 
            int(os.getenv("RAG_CHUNK_SIZE", "1000"))
        )
        self.chunk_overlap = (
            chunk_overlap or 
            int(os.getenv("RAG_CHUNK_OVERLAP", "200"))
        )
        self.collection_name = (
            collection_name or 
            os.getenv("RAG_COLLECTION_NAME", "local_documents")
        )
        
        # 支持的文件格式
        self.supported_extensions = {
            '.txt': TextLoader,
            '.pdf': PyPDFLoader,
            '.docx': Docx2txtLoader,
            '.doc': UnstructuredFileLoader,
            '.md': TextLoader,
            '.html': UnstructuredFileLoader,
            '.xml': UnstructuredFileLoader,
        }
        
        # 初始化嵌入模型
        self.embeddings = None
        self._init_embeddings()
    
    def _init_embeddings(self):
        """初始化嵌入模型"""
        logger.info(f"加载嵌入模型: {self.embedding_model_name}")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=self.embedding_model_name,
            model_kwargs={'device': 'cpu'},  # 使用CPU，如果有GPU可以改为'cuda'
            encode_kwargs={'normalize_embeddings': True}
        )
    
    def _get_file_hash(self, file_path: Path) -> str:
        """获取文件哈希值，用于检测文件变化"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def _load_documents(self) -> List[Document]:
        """加载本地文档"""
        logger.info(f"从 {self.documents_path} 加载文档...")
        
        if not self.documents_path.exists():
            raise ValueError(f"文档路径不存在: {self.documents_path}")
        
        all_docs = []
        file_count = 0
        
        # 遍历文档目录
        for file_path in self.documents_path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                try:
                    docs = self._load_single_file(file_path)
                    all_docs.extend(docs)
                    file_count += 1
                    logger.info(f"已加载: {file_path.name}")
                except Exception as e:
                    logger.error(f"加载文件失败 {file_path}: {e}")
        
        logger.info(f"总共加载了 {file_count} 个文件，{len(all_docs)} 个文档片段")
        return all_docs
    
    def _load_single_file(self, file_path: Path) -> List[Document]:
        """加载单个文件"""
        file_extension = file_path.suffix.lower()
        loader_class = self.supported_extensions[file_extension]
        
        try:
            loader = loader_class(str(file_path))
            docs = loader.load()
            
            # 添加元数据
            for doc in docs:
                doc.metadata.update({
                    'source': str(file_path),
                    'filename': file_path.name,
                    'file_type': file_extension,
                    'file_hash': self._get_file_hash(file_path)
                })
            
            return docs
        except Exception as e:
            logger.error(f"使用 {loader_class} 加载 {file_path} 失败: {e}")
            # 尝试使用通用加载器
            try:
                loader = UnstructuredFileLoader(str(file_path))
                docs = loader.load()
                for doc in docs:
                    doc.metadata.update({
                        'source': str(file_path),
                        'filename': file_path.name,
                        'file_type': file_extension,
                        'file_hash': self._get_file_hash(file_path)
                    })
                return docs
            except Exception as e2:
                logger.error(f"通用加载器也失败: {e2}")
                return []
    
    def _split_documents(self, docs: List[Document]) -> List[Document]:
        """分割文档"""
        logger.info("分割文档...")
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
            add_start_index=True,
        )
        
        # 过滤空文档
        valid_docs = [doc for doc in docs if doc.page_content.strip()]
        
        split_docs = text_splitter.split_documents(valid_docs)
        
        # 去重
        unique_docs = []
        seen_content = set()
        
        for doc in split_docs:
            content_hash = hashlib.md5(doc.page_content.encode()).hexdigest()
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_docs.append(doc)
        
        logger.info(f"分割后得到 {len(split_docs)} 个文档片段，去重后 {len(unique_docs)} 个")
        return unique_docs
    
    def build_database(self, force_rebuild: bool = False) -> Chroma:
        """构建向量数据库"""
        # 检查是否需要重建
        if not force_rebuild and self.database_exists():
            logger.info("向量数据库已存在，加载现有数据库...")
            return self.load_database()
        
        # 加载文档
        documents = self._load_documents()
        
        if not documents:
            raise ValueError("没有找到可加载的文档")
        
        # 分割文档
        split_docs = self._split_documents(documents)
        
        # 创建向量数据库
        logger.info("创建向量数据库...")
        vector_store = Chroma.from_documents(
            documents=split_docs,
            embedding=self.embeddings,
            persist_directory=str(self.vector_db_path),
            collection_name=self.collection_name
        )
        
        logger.info(f"向量数据库已保存到: {self.vector_db_path}")
        return vector_store
    
    def load_database(self) -> Chroma:
        """加载现有向量数据库"""
        if not self.database_exists():
            raise ValueError(f"向量数据库不存在: {self.vector_db_path}")
        
        logger.info("加载现有向量数据库...")
        vector_store = Chroma(
            persist_directory=str(self.vector_db_path),
            embedding_function=self.embeddings,
            collection_name=self.collection_name
        )
        
        # 检查数据库是否为空
        try:
            collection = vector_store._collection
            count = collection.count()
            logger.info(f"向量数据库包含 {count} 个文档")
            
            if count == 0:
                logger.warning("向量数据库为空，需要重新构建")
                
        except Exception as e:
            logger.error(f"检查向量数据库时出错: {e}")
        
        return vector_store
    
    def database_exists(self) -> bool:
        """检查向量数据库是否存在"""
        return self.vector_db_path.exists() and len(list(self.vector_db_path.iterdir())) > 0
    
    def add_documents_to_database(self, new_docs_path: str, vector_store: Chroma = None):
        """添加新文档到现有数据库"""
        logger.info(f"添加新文档从: {new_docs_path}")
        
        if vector_store is None:
            vector_store = self.load_database()
        
        # 临时改变文档路径
        original_path = self.documents_path
        self.documents_path = Path(new_docs_path)
        
        try:
            # 加载新文档
            new_documents = self._load_documents()
            if new_documents:
                # 分割新文档
                split_docs = self._split_documents(new_documents)
                
                # 添加到现有向量数据库
                vector_store.add_documents(split_docs)
                logger.info(f"成功添加 {len(split_docs)} 个新文档片段")
        finally:
            # 恢复原始路径
            self.documents_path = original_path
    
    def get_database_info(self, vector_store: Chroma = None) -> dict:
        """获取数据库信息"""
        if vector_store is None:
            if not self.database_exists():
                return {"error": "数据库不存在"}
            vector_store = self.load_database()
        
        try:
            collection = vector_store._collection
            count = collection.count()
            
            return {
                "document_count": count,
                "embedding_model": self.embedding_model_name,
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "vector_db_path": str(self.vector_db_path),
                "documents_path": str(self.documents_path),
                "collection_name": self.collection_name
            }
        except Exception as e:
            return {"error": str(e)}
    
    def delete_database(self):
        """删除向量数据库"""
        if self.vector_db_path.exists():
            import shutil
            shutil.rmtree(self.vector_db_path)
            logger.info(f"已删除向量数据库: {self.vector_db_path}")

def build_rag_database(
    documents_path: str = None,
    vector_db_path: str = None,
    embedding_model: str = None,
    chunk_size: int = None,
    chunk_overlap: int = None,
    force_rebuild: bool = False
) -> Chroma:
    """
    构建RAG向量数据库的便捷函数
    
    Args:
        documents_path: 文档路径（可选，从环境变量 RAG_DOCUMENTS_PATH 获取）
        vector_db_path: 向量数据库保存路径（可选，从环境变量 RAG_VECTOR_DB_PATH 获取）
        embedding_model: 嵌入模型名称（可选，从环境变量 RAG_EMBEDDING_MODEL 获取）
        chunk_size: 文档分块大小（可选，从环境变量 RAG_CHUNK_SIZE 获取）
        chunk_overlap: 分块重叠大小（可选，从环境变量 RAG_CHUNK_OVERLAP 获取）
        force_rebuild: 是否强制重建（可选，从环境变量 RAG_FORCE_REBUILD 获取）
    
    Returns:
        Chroma: 向量数据库实例
    """
    # 从环境变量获取 force_rebuild 参数
    if force_rebuild is False:  # 只有在默认值时才从环境变量获取
        force_rebuild = os.getenv("RAG_FORCE_REBUILD", "false").lower() == "true"
    
    builder = RAGDatabaseBuilder(
        documents_path=documents_path,
        vector_db_path=vector_db_path,
        embedding_model=embedding_model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    
    return builder.build_database(force_rebuild=force_rebuild)

# 使用示例
if __name__ == "__main__":
    vector_store = build_rag_database()