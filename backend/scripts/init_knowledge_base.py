"""
初始化 RAG 知识库
从 data/documents 加载商旅文档，向量化后写入 Milvus（Docker）

用法（在 backend/ 目录下）：
    python scripts/init_knowledge_base.py
"""
import sys
from pathlib import Path

# 将 backend 根目录加入 sys.path，保证 `app` 包可导入
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger
from app.services.rag_service import rag_service


def main():
    print("=" * 60)
    print("初始化 RAG 知识库")
    print("=" * 60)

    # 1. 重建知识库
    logger.info("开始重建知识库...")
    result = rag_service.rebuild_knowledge_base()

    if result["status"] != "success":
        print(f"❌ 重建知识库失败: {result.get('message', '未知错误')}")
        return

    print(f"✓ 成功添加 {result['added_count']} 个片段")
    print(f"✓ 知识库总文档数: {result['total_count']}")
    print()

    # 2. 测试检索
    print("测试知识检索...")
    test_queries = [
        "出差住宿标准是多少？",
        "航班延误了怎么办？",
        "机票应该提前多久预订？",
        "高铁可以订商务座吗？",
    ]
    for query in test_queries:
        print(f"\n  查询: {query}")
        results = rag_service.search_knowledge(query, top_k=2)
        if results:
            print(f"  ✓ 找到 {len(results)} 个相关文档")
            for doc in results:
                meta = doc.get("metadata", {})
                title = meta.get("title", "未知")
                distance = doc.get("distance", 0.0)
                sim = 1 - distance  # COSINE 距离转相似度
                print(f"    [{title}] (相似度: {sim:.3f})")
                print(f"      内容: {doc['content'][:80]}...")
        else:
            print("  ❌ 未找到相关文档")

    print()
    print("=" * 60)
    print("知识库初始化完成！")


if __name__ == "__main__":
    main()
