"""
RAG 服务：文档切分 + 向量化（bge 本地）+ Milvus（Docker）检索

- 嵌入模型：bge-small-zh-v1.5（本地，512 维，懒加载）
- 向量库：Milvus（Docker，http://localhost:19530）
- 支持：初始化知识库、添加文档、检索 top_k
"""
import json
import os
from pathlib import Path
from loguru import logger

from app.config import settings

# 避免 gRPC 长连接被服务端断开（Milvus keepalive 相关）
os.environ.setdefault("GRPC_KEEPALIVE_TIME_MS", "2147483647")
os.environ.setdefault("GRPC_KEEPALIVE_TIMEOUT_MS", "20000")
os.environ.setdefault("GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS", "0")
os.environ.setdefault("GRPC_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS", "2147483647")
os.environ.setdefault("GRPC_HTTP2_MIN_PING_INTERVAL_WITHOUT_DATA_MS", "2147483647")

from pymilvus import MilvusClient, DataType  # noqa: E402


class RAGService:
    """RAG 服务：封装嵌入模型与 Milvus 向量检索"""

    def __init__(self):
        self._embedding_model = None
        self._milvus_client = None
        self.collection_name = settings.milvus_collection
        self.top_k = settings.vector_top_k
        self.documents_dir = Path(settings.documents_dir)

    # ---------- 懒加载 ----------

    @property
    def embedding_model(self):
        """懒加载 bge 嵌入模型（首次调用时才加载，避免拖慢服务启动）"""
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer
            model_path = Path(settings.embedding_local_path)
            if not model_path.is_absolute():
                # 相对于 backend 根目录
                project_root = Path(__file__).resolve().parents[2]
                model_path = project_root / model_path
            logger.info(f"加载嵌入模型: {model_path}")
            self._embedding_model = SentenceTransformer(str(model_path))
        return self._embedding_model

    @property
    def milvus_client(self) -> MilvusClient:
        """懒加载 Milvus 客户端（Docker 版）"""
        if self._milvus_client is None:
            logger.info(f"连接 Milvus: {settings.milvus_uri}")
            self._milvus_client = MilvusClient(uri=settings.milvus_uri)
        return self._milvus_client

    # ---------- 文档切分 ----------

    def split_text(self, text: str, max_chars: int = 300, overlap: int = 60) -> list[str]:
        """按段落切分，控制每块大小（调细粒度，让每个 chunk 主题更聚焦）"""
        chunks = []
        paragraphs = []
        current_para = []
        for line in text.split("\n"):
            if line.strip() == "":
                if current_para:
                    paragraphs.append("\n".join(current_para))
                    current_para = []
            else:
                current_para.append(line)
        if current_para:
            paragraphs.append("\n".join(current_para))

        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) <= max_chars:
                current_chunk += "\n\n" + para
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                if len(para) > max_chars:
                    remaining = para
                    while len(remaining) > max_chars:
                        chunks.append(remaining[:max_chars])
                        remaining = remaining[max_chars - overlap:]
                    current_chunk = remaining
                else:
                    current_chunk = para
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    def load_documents_from_directory(self) -> list[dict]:
        """从 data/documents 加载并切分所有文档"""
        if not self.documents_dir.exists():
            logger.error(f"文档目录不存在: {self.documents_dir}")
            return []

        category_mapping = {
            "travel_standards": "差旅规定",
            "reimbursement_policy": "报销规定",
            "booking_guide": "预订指南",
            "faq": "FAQ",
            "emergency_procedures": "应急指南",
            "platform_guide": "平台指南",
            "city_specific_tips": "城市指南",
            "environmental_initiatives": "环保倡议",
        }

        documents = []
        for file_path in sorted(self.documents_dir.glob("*.txt")):
            try:
                parts = file_path.stem.split("_", 1)
                doc_num = parts[0]
                doc_key = parts[1] if len(parts) > 1 else ""
                base_doc_id = f"doc_{doc_num}"

                content = file_path.read_text(encoding="utf-8").strip()
                if not content:
                    continue

                title = content.split("\n")[0].strip()
                category = "商旅知识"
                for key, cat in category_mapping.items():
                    if key in doc_key:
                        category = cat
                        break

                chunks = self.split_text(content)
                for i, chunk in enumerate(chunks, 1):
                    documents.append({
                        "id": f"{base_doc_id}_{i}",
                        "content": chunk,
                        "metadata": {
                            "category": category,
                            "title": f"{title} (Part {i})",
                            "source": "商旅知识库文档",
                            "file_path": str(file_path),
                            "version": "2024版",
                            "parent_doc": file_path.name,
                        },
                    })
                logger.info(f"加载文档: {file_path.name} -> {len(chunks)} chunks")
            except Exception as e:
                logger.error(f"加载文档失败 {file_path.name}: {e}")
        return documents

    # ---------- 知识库管理 ----------

    def rebuild_knowledge_base(self) -> dict:
        """删除并重建知识库，重新写入全部文档"""
        documents = self.load_documents_from_directory()
        if not documents:
            return {"status": "error", "message": "未加载到任何文档"}

        dim = self.embedding_model.get_sentence_embedding_dimension()
        mc = self.milvus_client

        # 删除重建 collection
        if mc.has_collection(self.collection_name):
            mc.drop_collection(self.collection_name)
            logger.info(f"已删除旧 collection: {self.collection_name}")

        # 显式定义 schema：id 为 VARCHAR 主键（文档 id 形如 doc_001_1）
        schema = mc.create_schema(auto_id=False)
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=4000)
        schema.add_field(field_name="metadata", datatype=DataType.VARCHAR, max_length=2000)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
        index_params = mc.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
        mc.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"已创建 collection: {self.collection_name}, 维度={dim}")

        # 批量插入
        data = []
        for doc in documents:
            vec = self.embedding_model.encode(doc["content"]).tolist()
            data.append({
                "id": doc["id"],
                "vector": vec,
                "content": doc["content"],
                "metadata": json.dumps(doc["metadata"], ensure_ascii=False),
            })
            # 分批插入，避免一次性过大
            if len(data) >= 50:
                mc.insert(collection_name=self.collection_name, data=data)
                data = []
        if data:
            mc.insert(collection_name=self.collection_name, data=data)

        mc.flush(self.collection_name)
        # 加载到内存，确保立即可查询（Milvus 重启后也需重新 load）
        try:
            mc.load_collection(self.collection_name)
        except Exception as e:
            logger.warning(f"load collection 失败: {e}")
        stats = mc.get_collection_stats(self.collection_name)
        return {
            "status": "success",
            "added_count": len(documents),
            "total_count": stats.get("row_count", len(documents)),
            "collection": self.collection_name,
        }

    # ---------- 检索 ----------

    def search_knowledge(self, query: str, top_k: int = None) -> list[dict]:
        """语义检索 top_k 个相关文档"""
        k = top_k or self.top_k
        if not self.milvus_client.has_collection(self.collection_name):
            logger.warning(f"collection 不存在: {self.collection_name}，请先初始化知识库")
            return []

        # Milvus 重启后 collection 需重新加载才可查询；load 幂等且会等待就绪
        try:
            self.milvus_client.load_collection(self.collection_name)
        except Exception as e:
            logger.warning(f"load collection 失败（可能已加载）: {e}")

        query_vec = self.embedding_model.encode(query).tolist()
        results = self.milvus_client.search(
            collection_name=self.collection_name,
            data=[query_vec],
            limit=k,
            output_fields=["id", "content", "metadata"],
        )

        retrieved = []
        if results and len(results) > 0:
            for hit in results[0]:
                entity = hit.get("entity", {})
                try:
                    metadata = json.loads(entity.get("metadata", "{}"))
                except Exception:
                    metadata = {}
                retrieved.append({
                    "id": entity.get("id", ""),
                    "content": entity.get("content", ""),
                    "metadata": metadata,
                    "distance": hit.get("distance", 0.0),
                })
        logger.info(f"检索到 {len(retrieved)} 条知识, query: {query[:30]}")
        return retrieved

    def get_stats(self) -> dict:
        """知识库统计"""
        try:
            if not self.milvus_client.has_collection(self.collection_name):
                return {"status": "error", "message": "collection 不存在"}
            stats = self.milvus_client.get_collection_stats(self.collection_name)
            return {
                "status": "success",
                "collection_name": self.collection_name,
                "total_documents": stats.get("row_count", 0),
                "milvus_uri": settings.milvus_uri,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# 全局单例
rag_service = RAGService()
