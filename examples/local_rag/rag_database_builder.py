"""
RAG数据库构建器

使用方法：
1. 使用默认参数：
   builder = RAGDatabaseBuilder()

2. 自定义配置：
   builder = RAGDatabaseBuilder(
       documents_path="./docs",
       embedding_model="Qwen/Qwen3-Embedding-0.6B",
       chunk_size=1200
   )

3. 使用命令行参数：
   python rag_database_builder.py --force-rebuild
   python rag_database_builder.py --embedding-model Qwen/Qwen3-Embedding-0.6B
"""

import os
import logging
from pathlib import Path
from typing import List, Optional
import hashlib



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

# 禁用匿名遥测
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RAGDatabaseBuilder:
    """本地RAG向量数据库构建器"""
    
    def __init__(
        self,
        documents_path: str = "./my_documents",
        vector_db_path: str = "./local_vector_db", 
        embedding_model: str = "Qwen/Qwen3-Embedding-0.6B",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        collection_name: str = "local_documents"
    ):
        self.documents_path = Path(documents_path)
        self.vector_db_path = Path(vector_db_path)
        self.embedding_model_name = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.collection_name = collection_name
        
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
            logger.info("向量数据库已存在，尝试加载现有数据库...")
            try:
                return self.load_database()
            except Exception as e:
                if "expecting embedding with dimension" in str(e):
                    logger.warning(f"⚠️  检测到嵌入模型维度不匹配: {e}")
                    logger.warning(f"当前模型 {self.embedding_model_name} 与现有数据库不兼容")
                    logger.info("🔄 自动切换到重建模式...")
                    force_rebuild = True
                else:
                    raise e
        
        # 如果需要重建，先删除旧数据库
        if force_rebuild and self.database_exists():
            logger.info("🗑️  删除现有数据库...")
            self.delete_database()
        
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
    documents_path: str = "./my_documents",
    vector_db_path: str = "./local_vector_db",
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    force_rebuild: bool = False
) -> Chroma:
    """
    构建RAG向量数据库的便捷函数
    
    Args:
        documents_path: 文档路径
        vector_db_path: 向量数据库保存路径
        embedding_model: 嵌入模型名称
        chunk_size: 文档分块大小
        chunk_overlap: 分块重叠大小
        force_rebuild: 是否强制重建
    
    Returns:
        Chroma: 向量数据库实例
    """
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
    import argparse
    
    parser = argparse.ArgumentParser(
        description="RAG向量数据库构建器",
        epilog="""
使用示例:
  python rag_database_builder.py                    # 正常构建/加载数据库
  python rag_database_builder.py --force-rebuild   # 强制重建数据库
  python rag_database_builder.py --info            # 显示数据库信息
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="强制重建向量数据库，即使已存在"
    )
    
    parser.add_argument(
        "--info",
        action="store_true", 
        help="显示数据库信息而不构建"
    )
    
    parser.add_argument(
        "--documents-path",
        type=str,
        default="./my_documents",
        help="文档路径 (默认: ./my_documents)"
    )
    
    parser.add_argument(
        "--vector-db-path", 
        type=str,
        default="./local_vector_db",
        help="向量数据库路径 (默认: ./local_vector_db)"
    )
    
    parser.add_argument(
        "--embedding-model",
        type=str,
        default="Qwen/Qwen3-Embedding-0.6B",
        help="嵌入模型名称 (默认: Qwen/Qwen3-Embedding-0.6B)"
    )
    
    args = parser.parse_args()
    
    if args.info:
        # 显示数据库信息
        try:
            builder = RAGDatabaseBuilder(
                documents_path=args.documents_path,
                vector_db_path=args.vector_db_path,
                embedding_model=args.embedding_model
            )
            
            if builder.database_exists():
                print("📊 数据库信息:")
                info = builder.get_database_info()
                for key, value in info.items():
                    print(f"   {key}: {value}")
            else:
                print("❌ 数据库不存在")
        except Exception as e:
            print(f"❌ 获取数据库信息失败: {e}")
    else:
        # 构建/加载数据库
        print(f"🔨 开始构建RAG数据库...")
        print(f"📊 强制重建: {args.force_rebuild}")
        print(f"📁 文档路径: {args.documents_path}")
        print(f"💾 数据库路径: {args.vector_db_path}")
        print(f"🤖 嵌入模型: {args.embedding_model}")
            
        vector_store = build_rag_database(
            documents_path=args.documents_path,
            vector_db_path=args.vector_db_path,
            embedding_model=args.embedding_model,
            force_rebuild=args.force_rebuild
        )
        
        print("✅ 数据库构建完成！")