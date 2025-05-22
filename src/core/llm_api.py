import requests
from typing import Optional, List, Any
import traceback

# 导入新的配置和语言检测库
from config import (
    DEEPSEEK_API_URL, DEEPSEEK_MODEL,
    DEEPSEEK_SYSTEM_PROMPT_JA,
    DEEPSEEK_SYSTEM_PROMPT_ZH,
    DEEPSEEK_SYSTEM_PROMPT_EN
)
from langdetect import detect, LangDetectException # 导入 langdetect

# 默认系统提示词，以防语言检测失败或都不是目标语言
DEFAULT_SYSTEM_PROMPT = DEEPSEEK_SYSTEM_PROMPT_EN # 或者选择一个最通用的作为后备

def call_deepseek_api(api_key: str, text_to_segment: str,
                      signals_forwarder: Optional[Any] = None,
                      target_language: Optional[str] = None) -> Optional[List[str]]: # 新增 target_language 参数
    """
    调用 DeepSeek API 进行文本分割。
    :param api_key: DeepSeek API 密钥。
    :param text_to_segment: 需要分割的文本。
    :param signals_forwarder: 用于日志记录的信号转发器对象。
    :param target_language: 可选的目标语言代码 ('zh', 'ja', 'en')。如果提供，则使用对应提示词；否则尝试自动检测。
    :return: 分割后的文本片段列表，或在失败时返回 None。
    """
    def log_message(message: str):
        if signals_forwarder and hasattr(signals_forwarder, 'log_message') and hasattr(signals_forwarder.log_message, 'emit'):
            signals_forwarder.log_message.emit(f"[LLM API] {message}") # 添加模块前缀
        else:
            print(f"[LLM API] {message}")

    def is_running() -> bool:
        # 假设 signals_forwarder 是 WorkerSignals 实例，其 parent 是 ConversionWorker
        if signals_forwarder and hasattr(signals_forwarder, 'parent') and \
           hasattr(signals_forwarder.parent(), 'is_running'):
            return signals_forwarder.parent().is_running
        return True

    if not is_running():
        log_message("API调用前任务已取消。")
        return None

    system_prompt = DEFAULT_SYSTEM_PROMPT # 默认提示词

    detected_lang = None
    if target_language and target_language in ['zh', 'ja', 'en']:
        detected_lang = target_language
        log_message(f"使用用户指定的语言: {target_language}")
    else:
        try:
            if text_to_segment.strip(): # 确保文本不为空
                detected_lang_code = detect(text_to_segment)
                log_message(f"自动检测到文本语言: {detected_lang_code}")
                # 将 langdetect 返回的常见代码映射到我们的目标代码
                if detected_lang_code.startswith('zh'): # zh-cn, zh-tw etc.
                    detected_lang = 'zh'
                elif detected_lang_code == 'ja':
                    detected_lang = 'ja'
                elif detected_lang_code == 'en':
                    detected_lang = 'en'
                else:
                    log_message(f"自动检测到的语言 '{detected_lang_code}' 不是目标语言 (中日英之一)，将使用默认提示词。")
            else:
                log_message("输入文本为空，无法检测语言，将使用默认提示词。")
        except LangDetectException:
            log_message("语言检测失败，将使用默认提示词。")
        except Exception as e_detect:
            log_message(f"语言检测时发生未知错误: {e_detect}，将使用默认提示词。")


    if detected_lang == 'ja':
        system_prompt = DEEPSEEK_SYSTEM_PROMPT_JA
        log_message("选用日语分割提示词。")
    elif detected_lang == 'zh':
        system_prompt = DEEPSEEK_SYSTEM_PROMPT_ZH
        log_message("选用中文分割提示词。")
    elif detected_lang == 'en':
        system_prompt = DEEPSEEK_SYSTEM_PROMPT_EN
        log_message("选用英文分割提示词。")
    else: # 如果没有检测到或不是目标语言
        log_message(f"最终未能确定为中日英之一，使用默认提示词 (当前为英文)。")
        # system_prompt 保持为 DEFAULT_SYSTEM_PROMPT


    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
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
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=180)
        
        if not is_running():
            log_message("API响应接收前任务已取消。") # 更精确的取消点
            return None
            
        response.raise_for_status()
        data = response.json()

        if not is_running():
            log_message("API响应解析前任务已取消。")
            return None

        if "choices" in data and data["choices"]:
            content = data["choices"][0].get("message", {}).get("content")
            if content:
                # 对于英文，分割后可能需要确保不丢失句间空格（如果模型严格按行分割）
                # 但提示词已要求模型自行处理，这里直接按换行分割
                segments = [seg.strip() for seg in content.split('\n') if seg.strip()]
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
            except requests.exceptions.JSONDecodeError:
                error_details = f": {e.response.text}"
        log_message(f"错误: DeepSeek API 请求失败 (状态码: {status_code}){error_details}")
        return None
    except Exception as e:
        log_message(f"错误: 处理 DeepSeek API 响应时发生未知错误: {e}")
        log_message(traceback.format_exc())
        return None