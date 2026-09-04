"""
RAG 知识库节点：基于商旅知识库的语义检索问答
（差旅标准 / 报销政策 / 预订指南 等，严格基于知识库回答）
"""
from loguru import logger

from app.state import TravelState
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service


async def rag_node(state: TravelState) -> dict:
    """
    LangGraph 节点：知识库问答

    从 state 读取 user_input（或 rewritten_query），检索商旅知识库，
    结合检索片段用 LLM 生成严格基于知识库的回答。
    """
    user_input = state.get("user_input", "")
    rewritten = state.get("rewritten_query", "") or user_input
    query = rewritten or user_input

    if not query:
        return {"rag_result": {"status": "error", "message": "无法获取用户查询"}}

    # 检索知识库
    try:
        retrieved_docs = rag_service.search_knowledge(query)
    except Exception as e:
        logger.error(f"知识库检索失败: {e}")
        return {"rag_result": {"status": "error", "message": f"知识库检索失败: {str(e)}"}}

    if not retrieved_docs:
        return {
            "rag_result": {
                "status": "no_knowledge",
                "query": query,
                "answer": "抱歉，我在知识库中没有找到相关信息。",
                "retrieved_documents": [],
            }
        }

    # 构建知识上下文
    knowledge_context = "\n\n".join(
        f"【知识片段{i + 1}】\n{doc['content']}" for i, doc in enumerate(retrieved_docs)
    )

    prompt = f"""你是商旅知识专家。请严格基于以下知识库中的信息回答用户的问题。

【用户问题】
{query}

【知识库信息】
{knowledge_context}

【任务说明】
请基于知识库中的信息回答用户的问题。

【重要约束】
1. 如果【知识库信息】中没有包含回答用户问题所需的信息，请直接回答"抱歉，知识库中没有找到相关信息"，不要尝试根据你自己的知识编造答案。
2. 严格只回答与用户问题【直接相关】的内容：只提取知识片段中与问题主题一致的部分。
   - 例如用户问"住宿标准"，就只回答住宿相关内容；片段中提到的出租车、餐饮、报销等其他主题一律忽略，不要写进回答。
3. 多个知识片段中与问题无关的段落不要汇总进答案，避免冗余。
4. 即使问题很基础，如果知识库里没写，就说不知道。
5. 请以专业、客观的语气回答。"""

    try:
        answer = await llm_service.ainvoke(
            messages=[
                {"role": "system", "content": "你是商旅知识专家。"},
                {"role": "user", "content": prompt},
            ],
            task_type="rag",
        )
        if not answer:
            answer = "无法生成答案"

        logger.info(f"RAG 回答: {query[:30]}...")
        return {
            "rag_result": {
                "status": "success",
                "query": query,
                "answer": answer,
                "retrieved_documents": [
                    {
                        "content": doc["content"][:200] + ("..." if len(doc["content"]) > 200 else ""),
                        "metadata": doc["metadata"],
                    }
                    for doc in retrieved_docs
                ],
            }
        }
    except Exception as e:
        logger.error(f"RAG 生成答案失败: {e}")
        return {
            "rag_result": {
                "status": "error",
                "message": f"知识库中找到相关信息，但生成答案时出错: {str(e)}",
                "query": query,
            }
        }
