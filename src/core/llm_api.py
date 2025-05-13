import requests
from typing import Optional, List, Any # Any 用于 signals_forwarder 的duck typing
import traceback

# Corrected import: removed 'src.' prefix
from config import DEEPSEEK_API_URL, DEEPSEEK_MODEL, DEEPSEEK_SYSTEM_PROMPT

def call_deepseek_api(api_key: str, text_to_segment: str, signals_forwarder: Optional[Any] = None) -> Optional[List[str]]:
    """
    调用 DeepSeek API 进行文本分割。
    :param api_key: DeepSeek API 密钥。
    :param text_to_segment: 需要分割的文本。
    :param signals_forwarder: 用于日志记录的信号转发器对象 (应有 log_message.emit 方法和 is_running 属性)。
    :return: 分割后的文本片段列表，或在失败时返回 None。
    """
    def log_message(message: str):
        if signals_forwarder and hasattr(signals_forwarder, 'log_message') and hasattr(signals_forwarder.log_message, 'emit'):
            signals_forwarder.log_message.emit(message)
        else:
            print(f"[LLM API] {message}") # 回退日志

    def is_running() -> bool:
        if signals_forwarder and hasattr(signals_forwarder, 'is_running'):
            return signals_forwarder.is_running
        return True # 如果没有提供，则假定一直在运行

    if not is_running():
        log_message("API调用前任务已取消。")
        return None

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
            {"role": "user", "content": text_to_segment}
        ],
        "stream": False
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    log_message(f"向 DeepSeek API 发送文本进行分割 (模型: {DEEPSEEK_MODEL}, 文本长度: {len(text_to_segment)} chars)...")
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=180) # 3 分钟超时
        response.raise_for_status() # 如果HTTP状态码表示错误，则抛出异常
        data = response.json()

        if not is_running():
            log_message("API响应后任务已取消。")
            return None

        if "choices" in data and data["choices"]:
            content = data["choices"][0].get("message", {}).get("content")
            if content:
                segments = [seg.strip() for seg in content.split('\n') if seg.strip()] # 按换行符分割并去除空行
                log_message(f"DeepSeek API 成功返回 {len(segments)} 个文本片段。")
                return segments
            else:
                log_message("错误: DeepSeek API 响应中 'content' 为空。")
                return None
        else:
            error_msg = data.get('error', {}).get('message', str(data))
            log_message(f"错误: DeepSeek API 响应格式错误: {error_msg}")
            return None
    except requests.exceptions.Timeout:
        log_message("错误: DeepSeek API 请求超时 (180秒)。")
        return None
    except requests.exceptions.RequestException as e:
        error_details = ""
        status_code = 'N/A'
        if e.response is not None:
            status_code = e.response.status_code
            try:
                error_details = f": {e.response.json().get('error', {}).get('message', '')}"
            except requests.exceptions.JSONDecodeError: # Guard against non-JSON error responses
                error_details = f": {e.response.text}"
        log_message(f"错误: DeepSeek API 请求失败 (状态码: {status_code}){error_details}")
        return None
    except Exception as e:
        log_message(f"错误: 处理 DeepSeek API 响应时发生未知错误: {e}")
        log_message(traceback.format_exc())
        return None