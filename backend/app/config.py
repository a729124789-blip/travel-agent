"""
后端配置管理 - 使用 Pydantic Settings 从 .env 读取
"""
from pydantic_settings import BaseSettings
from typing import Dict, Any


class Settings(BaseSettings):
    """应用配置"""

    # ===== 应用 =====
    app_name: str = "智能旅行助手"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # ===== CORS =====
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ===== LLM =====
    llm_api_key: str = ""
    llm_base_url: str = "https://tokenhub.tencentmaas.com/v1"
    # 按任务类型配置模型，模型名从 .env 读取（LLM_MODEL_DEFAULT / INTENT / PLANNING / RAG）
    llm_model_default: str = "deepseek-v4-flash"
    llm_model_intent: str = "deepseek-v4-flash"
    llm_model_planning: str = "glm-5.3-flash"
    llm_model_rag: str = "deepseek-v4-flash"

    @property
    def llm_models(self) -> Dict[str, Dict[str, Any]]:
        """按任务类型组装模型配置（模型名来自 .env，温度/长度保持代码默认值）"""
        return {
            "default": {"model": self.llm_model_default, "temperature": 0.7, "max_tokens": 4096},
            "intent": {"model": self.llm_model_intent, "temperature": 0.3, "max_tokens": 2048},
            "planning": {"model": self.llm_model_planning, "temperature": 0.5, "max_tokens": 12000, "reasoning_effort": "high"},
            "rag": {"model": self.llm_model_rag, "temperature": 0.3, "max_tokens": 2048},
        }

    # ===== 嵌入模型 =====
    embedding_provider: str = "local"  # local / openai / dashscope
    embedding_model: str = "bge-small-zh-v1.5"
    # 本地模型路径（相对 backend 根目录）
    embedding_local_path: str = "data/models/bge-small-zh-v1.5"

    # ===== 向量库 =====
    vector_store_type: str = "milvus"  # milvus(Docker) / milvus_lite / chroma / faiss
    milvus_uri: str = "http://localhost:19530"
    milvus_collection: str = "business_travel_knowledge"
    vector_store_path: str = "data/vector_store.db"
    vector_top_k: int = 3
    documents_dir: str = "data/documents"

    # ===== 记忆 =====
    memory_path: str = "data/memory"
    short_term_max_turns: int = 10

    # ===== 韧性 =====
    max_retries: int = 3
    retry_base_delay_sec: float = 1.0
    retry_max_delay_sec: float = 30.0
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout_sec: float = 60.0

    # ===== 高德地图（后续启用） =====
    amap_key: str = ""

    # ===== Unsplash（图片素材，备用） =====
    unsplash_access_key: str = ""
    unsplash_secret_key: str = ""

    # ===== MCP 服务 URL（魔搭 ModelScope 托管，含用户专属 UUID，从 .env 读取） =====
    hotel_mcp_url: str = ""
    rail_mcp_url: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
