"""
鲁棒 JSON 解析：处理 LLM 输出中常见的格式问题（markdown包裹、控制字符、尾部逗号等）
"""
import json
import re
from loguru import logger


def robust_json_parse(text: str, fallback=None) -> dict:
    """多级尝试解析 JSON，全部失败返回 fallback 或抛 ValueError"""
    if not text:
        if fallback is not None:
            return fallback
        raise ValueError("Empty text provided")

    if isinstance(text, dict):
        return text

    # 清理 markdown 代码块
    text = text.strip()
    if text.startswith('```json'):
        text = text[7:]
    elif text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    text = text.strip()

    # 提取 JSON 部分
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
        if fallback is not None:
            logger.warning("未找到 JSON，使用 fallback")
            return fallback
        raise ValueError("No JSON found in response")

    json_str = text[start_idx:end_idx + 1]

    # 尝试1: 直接解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON直接解析失败: {e}")

    # 尝试2: 移除控制字符
    try:
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 尝试3: 修复单引号
    try:
        fixed = re.sub(r"'([^']*)'(\s*:\s*)", r'"\1"\2', json_str)
        fixed = re.sub(r':\s*\'([^\']*)\'', r': "\1"', fixed)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 尝试4: 移除尾部逗号
    try:
        fixed = re.sub(r',(\s*[}\]])', r'\1', json_str)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 尝试5: 转义字符串内换行
    try:
        result = []
        in_string = False
        escape_next = False
        for char in json_str:
            if escape_next:
                result.append(char)
                escape_next = False
                continue
            if char == '\\':
                result.append(char)
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                result.append(char)
                continue
            if in_string and char in ('\n', '\r', '\t'):
                result.append({'\\n': '\\n', '\r': '\\r', '\t': '\\t'}[char])
            else:
                result.append(char)
        return json.loads(''.join(result))
    except json.JSONDecodeError:
        pass

    # 尝试6: json5（如可用）
    try:
        import json5
        return json5.loads(json_str)
    except ImportError:
        pass
    except Exception:
        pass

    logger.error(f"所有 JSON 解析尝试失败")
    if fallback is not None:
        return fallback
    raise ValueError("Failed to parse JSON after all attempts")


def extract_content(response, field_name: str = "content") -> str:
    """从 langchain AIMessage / dict / str 中提取文本内容"""
    if hasattr(response, 'content'):
        content = response.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    return item.get('text', '')
    if isinstance(response, dict) and field_name in response:
        return str(response[field_name])
    if isinstance(response, str):
        return response
    return str(response) if response else ""
