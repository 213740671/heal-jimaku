import os
import requests
from typing import Optional, List, Any, Dict
import traceback
import time
import re

import config as app_config # 使用别名

from langdetect import detect, LangDetectException

DEFAULT_SYSTEM_PROMPT_FOR_SEGMENTATION = app_config.DEEPSEEK_SYSTEM_PROMPT_EN
DEFAULT_SYSTEM_PROMPT_FOR_SUMMARY = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_EN

MAX_CHARS_PER_CHUNK = 2800


def _parse_api_url_and_model(
    input_base_url_str: Optional[str],
    input_model_name: Optional[str],
    default_api_base_for_v1: str = app_config.DEFAULT_LLM_API_BASE_URL,
    default_model: str = app_config.DEFAULT_LLM_MODEL_NAME
) -> tuple[str, str]:
    final_url = ""
    effective_model = input_model_name if input_model_name else default_model
    if not input_base_url_str:
        # 如果没有提供URL，使用默认的并添加/v1和/chat/completions
        final_url = default_api_base_for_v1
        if not final_url.endswith('/'):
            final_url += '/'
        final_url += "v1/chat/completions"
        return final_url, effective_model

    raw_url = input_base_url_str.strip()
    
    # 检查是否以 '#' 结尾，表示用户提供了完整的API路径
    if raw_url.endswith("#"):
        final_url = raw_url[:-1]
    # 检查是否已经包含 /v1 或 /v2
    elif "/v1" in raw_url or "/v2" in raw_url:
        # 如果已经包含版本号，则直接使用，并确保以 /chat/completions 结尾
        if not raw_url.endswith('/'):
            raw_url += '/'
        if not raw_url.endswith('chat/completions'):
            final_url = raw_url + "chat/completions"
        else:
            final_url = raw_url
    # 如果以 '/' 结尾，但在前面没有版本号，则添加 /v1/chat/completions
    elif raw_url.endswith('/'):
        final_url = raw_url + "v1/chat/completions"
    # 如果不以 '/' 结尾，且没有版本号，则添加 /v1/chat/completions
    else:
        final_url = raw_url + "/v1/chat/completions"
        
    return final_url, effective_model

def _log_api_message(message: str, signals_forwarder: Optional[Any], prefix: str = "[LLM API]"):
    """辅助函数，用于将日志消息发送到信号或打印到控制台"""
    if signals_forwarder and hasattr(signals_forwarder, 'log_message') and hasattr(signals_forwarder.log_message, 'emit'):
        signals_forwarder.log_message.emit(f"{prefix} {message}")
    else:
        print(f"{prefix} {message}")

def _split_text_into_chunks(text: str, max_chars: int, signals_forwarder: Optional[Any]) -> List[str]:
    def _log_splitter(message: str):
        _log_api_message(message, signals_forwarder, prefix="[LLM API - Splitter]")

    chunks: List[str] = []
    current_pos = 0; text_len = len(text)
    if not text.strip(): _log_splitter("输入文本为空或仅包含空白，不进行分割。"); return []
    while current_pos < text_len:
        end_pos = min(current_pos + max_chars, text_len); actual_chunk_end = end_pos
        if end_pos < text_len:
            para_break = text.rfind('\n\n', current_pos, end_pos)
            if para_break != -1 and para_break > current_pos: actual_chunk_end = para_break + 2
            else:
                line_break = text.rfind('\n', current_pos, end_pos)
                if line_break != -1 and line_break > current_pos: actual_chunk_end = line_break + 1
                else:
                    search_start_for_sentence_end = max(current_pos, end_pos - max(100, int(max_chars * 0.2)))
                    best_sentence_break = -1
                    sentence_terminators = r'[。．\.！\!？\?]'; 
                    for match in re.finditer(sentence_terminators, text[search_start_for_sentence_end:end_pos]):
                        break_candidate = search_start_for_sentence_end + match.end()
                        if break_candidate > current_pos: best_sentence_break = break_candidate
                    if best_sentence_break != -1: actual_chunk_end = best_sentence_break
                    else:
                        space_break = text.rfind(' ', current_pos, end_pos)
                        if space_break != -1 and space_break > current_pos: actual_chunk_end = space_break + 1
        chunk_to_add = text[current_pos:actual_chunk_end]
        if chunk_to_add.strip(): chunks.append(chunk_to_add)
        current_pos = actual_chunk_end
    if not chunks and text.strip(): chunks.append(text)
    _log_splitter(f"文本被分割为 {len(chunks)} 块."); return chunks

def _get_summary(
    api_key: str,
    full_text: str,
    system_prompt_summary: str,
    custom_api_base_url_str: Optional[str],
    custom_model_name: Optional[str],
    custom_temperature: Optional[float],
    signals_forwarder: Optional[Any] = None
) -> Optional[str]:
    def _log_summary_api(message: str):
        _log_api_message(message, signals_forwarder, prefix="[LLM API - Summary]")

    target_url, effective_model = _parse_api_url_and_model(
        custom_api_base_url_str, custom_model_name,
        app_config.DEFAULT_LLM_API_BASE_URL, app_config.DEFAULT_LLM_MODEL_NAME
    )
    effective_summary_temperature = custom_temperature if custom_temperature is not None else 0.5

    _log_summary_api(f"向 LLM API 请求文本摘要 (URL: {target_url}, 模型: {effective_model}, 温度: {effective_summary_temperature})...")
    
    payload = {"model": effective_model, "messages": [{"role": "system", "content": system_prompt_summary}, {"role": "user", "content": full_text}]}
    if custom_temperature is not None: payload["temperature"] = effective_summary_temperature
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    try:
        response = requests.post(target_url, headers=headers, json=payload, timeout=180)
        response.raise_for_status(); data = response.json()
        content = None; finish_reason = "unknown"
        if "choices" in data and data["choices"] and isinstance(data["choices"], list) and len(data["choices"]) > 0 and \
           isinstance(data["choices"][0], dict) and data["choices"][0].get("message", {}).get("content") is not None:
            choice = data["choices"][0]; content = choice.get("message", {}).get("content"); finish_reason = choice.get("finish_reason", "unknown")
        elif data.get("candidates") and isinstance(data["candidates"], list) and len(data["candidates"]) > 0 and \
             isinstance(data["candidates"][0], dict) and \
             data["candidates"][0].get("content", {}).get("parts", [{}]) and \
             isinstance(data["candidates"][0].get("content").get("parts"), list) and \
             len(data["candidates"][0].get("content").get("parts")) > 0 and \
             isinstance(data["candidates"][0].get("content").get("parts")[0], dict) and \
             data["candidates"][0].get("content").get("parts")[0].get("text") is not None:
            content = data["candidates"][0].get("content").get("parts")[0].get("text"); finish_reason = data["candidates"][0].get("finishReason", "unknown")

        if content is not None:
            _log_summary_api(f"摘要获取成功。完成原因: {finish_reason}")
            if finish_reason == "MAX_TOKENS" or finish_reason == "length": 
                _log_summary_api(f"警告: 摘要输出可能因达到API的默认max_tokens限制而被截断。")
            return content.strip()
        else: 
            error_info = data.get('error', {}); 
            if not error_info and data.get("code") and data.get("message"): error_info = data
            error_msg = error_info.get('message', str(data))
            _log_summary_api(f"错误: LLM API 对摘要请求的响应中内容为空或格式不符。完成原因: {finish_reason}, 响应数据: {str(data)[:500]}")
    except requests.exceptions.Timeout: _log_summary_api(f"错误: LLM API 对摘要请求超时 (180秒)。URL: {target_url}"); return None
    except requests.exceptions.RequestException as e: 
        status_code = e.response.status_code if e.response is not None else 'N/A'
        _log_summary_api(f"错误: LLM API 对摘要请求失败 (状态码: {status_code}) URL: {target_url}: {e}"); return None
    except Exception as e: _log_summary_api(f"错误: 处理 LLM API 对摘要请求的响应时发生未知错误 (URL: {target_url}): {e}"); _log_summary_api(traceback.format_exc()); return None
    return None

def call_llm_api_for_segmentation(
    api_key: str, text_to_segment: str,
    custom_api_base_url_str: Optional[str], custom_model_name: Optional[str],
    custom_temperature: Optional[float],
    signals_forwarder: Optional[Any] = None, target_language: Optional[str] = None
) -> Optional[List[str]]:
    def _log_main_api(message: str):
        _log_api_message(message, signals_forwarder, prefix="[LLM API - Main]")

    def is_running() -> bool:
        if signals_forwarder and hasattr(signals_forwarder, 'parent') and hasattr(signals_forwarder.parent(), 'is_running'):
            return signals_forwarder.parent().is_running
        return True
    if not is_running(): _log_main_api("API调用前任务已取消。"); return None

    target_url, effective_model = _parse_api_url_and_model(
        custom_api_base_url_str, custom_model_name,
        app_config.DEFAULT_LLM_API_BASE_URL, app_config.DEFAULT_LLM_MODEL_NAME
    )
    effective_temperature = custom_temperature if custom_temperature is not None else app_config.DEFAULT_LLM_TEMPERATURE

    detected_lang_code_for_prompt = None
    if target_language and target_language in ['zh', 'ja', 'en']: detected_lang_code_for_prompt = target_language
    else:
        try:
            if text_to_segment.strip():
                detected_lang_raw = detect(text_to_segment)
                if detected_lang_raw.startswith('zh'): detected_lang_code_for_prompt = 'zh'
                elif detected_lang_raw == 'ja': detected_lang_code_for_prompt = 'ja'
                elif detected_lang_raw == 'en': detected_lang_code_for_prompt = 'en'
        except Exception: pass 
    system_prompt_segmentation = DEFAULT_SYSTEM_PROMPT_FOR_SEGMENTATION
    if detected_lang_code_for_prompt == 'ja': system_prompt_segmentation = app_config.DEEPSEEK_SYSTEM_PROMPT_JA
    elif detected_lang_code_for_prompt == 'zh': system_prompt_segmentation = app_config.DEEPSEEK_SYSTEM_PROMPT_ZH
    elif detected_lang_code_for_prompt == 'en': system_prompt_segmentation = app_config.DEEPSEEK_SYSTEM_PROMPT_EN
    system_prompt_summary_task = DEFAULT_SYSTEM_PROMPT_FOR_SUMMARY
    if detected_lang_code_for_prompt == 'ja': system_prompt_summary_task = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_JA
    elif detected_lang_code_for_prompt == 'zh': system_prompt_summary_task = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_ZH
    elif detected_lang_code_for_prompt == 'en': system_prompt_summary_task = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_EN
    _log_main_api(f"分割任务选用的系统提示词语言: {detected_lang_code_for_prompt or 'default (en)'}")

    summary_text = ""
    if text_to_segment.strip():
        _log_main_api("尝试获取全文摘要...")
        summary_text_optional = _get_summary(
            api_key, text_to_segment, system_prompt_summary_task,
            custom_api_base_url_str, custom_model_name, effective_temperature,
            signals_forwarder=signals_forwarder
        )
        if summary_text_optional: summary_text = summary_text_optional; _log_main_api("成功获取到摘要。")
        else: _log_main_api("未能获取到摘要，将不带摘要继续进行分割。")
    else: _log_main_api("输入文本为空，跳过摘要获取。")

    all_segments: List[str] = []
    text_chunks = _split_text_into_chunks(text_to_segment, MAX_CHARS_PER_CHUNK, signals_forwarder)
    num_chunks = len(text_chunks)
    if num_chunks == 0: 
        if text_to_segment.strip(): text_chunks = [text_to_segment]; num_chunks = 1
        else: return []

    for i, chunk in enumerate(text_chunks):
        if not is_running(): _log_main_api(f"处理块 {i+1}/{num_chunks} 前任务已取消。"); return all_segments if all_segments else None 
        _log_main_api(f"向 LLM API 发送块 {i+1}/{num_chunks} 进行分割 (URL: {target_url}, 模型: {effective_model}, 温度: {effective_temperature})...")
        
        user_content_with_summary = f"【全文摘要】:\n{summary_text}\n\n【当前文本块】:\n{chunk}"
        if not summary_text: user_content_with_summary = f"【当前文本块】:\n{chunk}"

        payload = {"model": effective_model, "messages": [{"role": "system", "content": system_prompt_segmentation}, {"role": "user", "content": user_content_with_summary }]}
        if custom_temperature is not None: payload["temperature"] = effective_temperature
        
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        try:
            response = requests.post(target_url, headers=headers, json=payload, timeout=180)
            if not is_running(): _log_main_api(f"API 对块 {i+1}/{num_chunks} 响应接收后任务已取消。"); return all_segments if all_segments else None
            response.raise_for_status(); data = response.json()
            if not is_running(): _log_main_api(f"API 对块 {i+1}/{num_chunks} 响应解析后任务已取消。"); return all_segments if all_segments else None
            content = None; finish_reason = "unknown"
            if "choices" in data and data["choices"] and isinstance(data["choices"], list) and len(data["choices"]) > 0 and \
               isinstance(data["choices"][0], dict) and data["choices"][0].get("message", {}).get("content") is not None:
                choice = data["choices"][0]; content = choice.get("message", {}).get("content"); finish_reason = choice.get("finish_reason", "unknown")
            elif data.get("candidates") and isinstance(data["candidates"], list) and len(data["candidates"]) > 0 and \
                 isinstance(data["candidates"][0], dict) and \
                 data["candidates"][0].get("content", {}).get("parts", [{}]) and \
                 isinstance(data["candidates"][0].get("content").get("parts"), list) and \
                 len(data["candidates"][0].get("content").get("parts")) > 0 and \
                 isinstance(data["candidates"][0].get("content").get("parts")[0], dict) and \
                 data["candidates"][0].get("content").get("parts")[0].get("text") is not None:
                content = data["candidates"][0].get("content").get("parts")[0].get("text"); finish_reason = data["candidates"][0].get("finishReason", "unknown")

            if content is not None:
                segments_from_chunk = [seg.strip() for seg in content.split('\n') if seg.strip()]
                all_segments.extend(segments_from_chunk)
                _log_main_api(f"块 {i+1}/{num_chunks} 成功处理，获得 {len(segments_from_chunk)} 个片段。完成原因: {finish_reason}")
                if finish_reason == "length" or finish_reason == "MAX_TOKENS":
                    _log_main_api(f"警告: 块 {i+1}/{num_chunks} 的输出可能因为达到API的默认max_tokens限制而被截断。")
            else: 
                error_info = data.get('error', {}); 
                if not error_info and data.get("code") and data.get("message"): error_info = data 
                error_msg = error_info.get('message', str(data)); error_type = error_info.get('type', error_info.get("status")); error_code_val = error_info.get('code')
                _log_main_api(f"错误: LLM API 对块 {i+1}/{num_chunks} 的响应格式错误或API返回错误。类型: {error_type}, Code: {error_code_val}, 消息: {str(data)[:500]}")
        except requests.exceptions.Timeout: _log_main_api(f"错误: LLM API 对块 {i+1}/{num_chunks} 的请求超时 (180秒)。URL: {target_url}")
        except requests.exceptions.RequestException as e: 
            error_details = ""; status_code = 'N/A'
            if e.response is not None:
                status_code = e.response.status_code
                try: 
                    err_json_data = e.response.json(); err_info_openai = err_json_data.get('error', {}); err_info_gemini = err_json_data if "message" in err_json_data and "code" in err_json_data else {}
                    message = err_info_openai.get('message', err_info_gemini.get('message', e.response.text)); err_type = err_info_openai.get('type', err_info_gemini.get('status', 'UnknownType')); err_code = err_info_openai.get('code', err_info_gemini.get('code', 'UnknownCode'))
                    error_details = f": [{err_type}/{err_code}] {message}"
                except requests.exceptions.JSONDecodeError: error_details = f": {e.response.text[:200]}"
            else: error_details = f": {str(e)}"
            _log_main_api(f"错误: LLM API 对块 {i+1}/{num_chunks} 的请求失败 (状态码: {status_code}, URL: {target_url}){error_details}")
        except Exception as e: _log_main_api(f"错误: 处理 LLM API 对块 {i+1}/{num_chunks} 的响应时发生未知错误 (URL: {target_url}): {e}"); _log_main_api(traceback.format_exc())
        if signals_forwarder and hasattr(signals_forwarder, 'llm_progress_signal') and hasattr(signals_forwarder.llm_progress_signal, 'emit'):
             signals_forwarder.llm_progress_signal.emit(int(((i + 1) / num_chunks) * 100))
        if num_chunks > 1 and i < num_chunks - 1:
            if not is_running(): _log_main_api(f"处理完块 {i+1}/{num_chunks} 后任务已取消，不再延时。"); return all_segments if all_segments else None
            time.sleep(0.5)
    if not all_segments and text_to_segment.strip(): _log_main_api("所有块处理完毕，但未能从任何块中获取到有效的分割结果。"); return None 
    _log_main_api(f"所有 {num_chunks} 个块处理完成。总共收集到 {len(all_segments)} 个片段。"); return all_segments

# --- 测试连接函数 ---
def test_llm_connection(
    api_key: str,
    custom_api_base_url_str: Optional[str],
    custom_model_name: Optional[str],
    custom_temperature: Optional[float],
    signals_forwarder: Optional[Any] = None # 新增 signals_forwarder 参数
) -> tuple[bool, str]:
    def _log_test_connection(message: str):
        _log_api_message(message, signals_forwarder, prefix="[LLM API - Test Connection]")

    target_url, effective_model = _parse_api_url_and_model(
        custom_api_base_url_str, custom_model_name,
        app_config.DEFAULT_LLM_API_BASE_URL, app_config.DEFAULT_LLM_MODEL_NAME
    )
    test_temperature = custom_temperature if custom_temperature is not None else app_config.DEFAULT_LLM_TEMPERATURE
    
    _log_test_connection(f"DEBUG Test Connection: URL='{target_url}', Model='{effective_model}', Temp='{test_temperature}'")

    payload = {"model": effective_model, "messages": [{"role": "user", "content": "Hello"}]}
    if custom_temperature is not None: payload["temperature"] = test_temperature
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    try:
        response = requests.post(target_url, headers=headers, json=payload, timeout=20) 
        response.raise_for_status()
        data = response.json()
        if (data.get("choices") and isinstance(data["choices"], list) and len(data["choices"]) > 0 and isinstance(data["choices"][0], dict) and data["choices"][0].get("message", {}).get("content") is not None) or \
           (data.get("candidates") and isinstance(data["candidates"], list) and len(data["candidates"]) > 0 and isinstance(data["candidates"][0], dict) and data["candidates"][0].get("content", {}).get("parts", [{}]) and isinstance(data["candidates"][0].get("content").get("parts"), list) and len(data["candidates"][0].get("content").get("parts")) > 0 and isinstance(data["candidates"][0].get("content").get("parts")[0], dict) and data["candidates"][0].get("content").get("parts")[0].get("text") is not None):
            return True, f"连接成功！模型 {effective_model} 在 {target_url} 返回了响应。"
        else:
            return True, f"连接测试：收到HTTP 200响应，但响应内容格式未知或不完整。模型: {effective_model}, URL: {target_url}. 响应: {str(data)[:200]}"
    except requests.exceptions.Timeout: return False, f"连接超时 (20秒)。URL: {target_url}"
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code; error_text = e.response.text[:200] 
        if status_code == 401: return False, f"认证失败 (401)。检查API Key。URL: {target_url}"
        elif status_code == 404: return False, f"API端点未找到 (404)。检查API地址: {target_url}"
        elif status_code == 500: return False, f"服务器内部错误 (500)。API: {target_url}。错误: {error_text}"
        else: return False, f"API请求失败，状态码: {status_code}。URL: {target_url}。错误: {error_text}"
    except requests.exceptions.RequestException as e: return False, f"连接错误。URL: {target_url}。错误: {e}"
    except Exception as e: return False, f"测试连接未知错误。URL: {target_url}。错误: {type(e).__name__} - {str(e)[:100]}"
