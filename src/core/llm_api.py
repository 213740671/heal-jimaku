import requests
from typing import Optional, List, Any
import traceback
import time # 导入 time 模块用于延时
import re # 导入 re 模块用于更复杂的标点查找

# 从 config.py 导入配置
from config import (
    DEEPSEEK_API_URL, DEEPSEEK_MODEL,
    DEEPSEEK_SYSTEM_PROMPT_JA,
    DEEPSEEK_SYSTEM_PROMPT_ZH,
    DEEPSEEK_SYSTEM_PROMPT_EN,
    # 新增导入摘要提示词
    DEEPSEEK_SYSTEM_PROMPT_SUMMARY_JA,
    DEEPSEEK_SYSTEM_PROMPT_SUMMARY_ZH,
    DEEPSEEK_SYSTEM_PROMPT_SUMMARY_EN,
    DEFAULT_LLM_TEMPERATURE # 导入默认温度（虽然下面会用固定的，但可能未会用到）
)
from langdetect import detect, LangDetectException # 导入 langdetect

# 默认系统提示词，以防语言检测失败或都不是目标语言
# 注意：这个 DEFAULT_SYSTEM_PROMPT 现在主要用于摘要任务的语言判断（如果需要）
# 或者作为分割任务在没有检测到特定语言时的备用（但我们已经为中日英分别修改了提示词）
DEFAULT_SYSTEM_PROMPT_FOR_SEGMENTATION = DEEPSEEK_SYSTEM_PROMPT_EN # 分割任务的默认提示
DEFAULT_SYSTEM_PROMPT_FOR_SUMMARY = DEEPSEEK_SYSTEM_PROMPT_SUMMARY_EN # 摘要任务的默认提示


# --- 参数配置 ---
# 定义每个文本块的最大字符数
# 极限测试的样本是 19219 字符，之前分成2块 (约12000/块)，效果不佳
# 目标是分成约4块， 19219 / 4 = 约 4800 字符/块。所以们设置一个略大的值。
MAX_CHARS_PER_CHUNK = 5500  

# DeepSeek Chat 最大输出 tokens 数 (用于分割任务的每个块)
MAX_OUTPUT_TOKENS_SEGMENTATION = 8192

# 用于摘要任务的最大输出 tokens 数 (摘要本身不应过长)
MAX_OUTPUT_TOKENS_SUMMARY = 512 # 摘要在512 tokens内足够

# 固定temperature值
FIXED_TEMPERATURE = 0.2
USER_LLM_TEMPERATURE_SUMMARY_KEY = 0.6

# --- 文本分块函数  ---
def _split_text_into_chunks(text: str, max_chars: int, signals_forwarder: Optional[Any]) -> List[str]:
    """
    将长文本分割成较小的块，尝试在自然断点处分割。
    """
    def _log_splitter(message: str): # 局部日志函数，加下划线以示内部
        if signals_forwarder and hasattr(signals_forwarder, 'log_message') and hasattr(signals_forwarder.log_message, 'emit'):
            signals_forwarder.log_message.emit(f"[LLM API - Splitter] {message}")
        else:
            print(f"[LLM API - Splitter] {message}")

    chunks: List[str] = []
    current_pos = 0
    text_len = len(text)

    if not text.strip():
        _log_splitter("输入文本为空或仅包含空白，不进行分割。")
        return []

    while current_pos < text_len:
        end_pos = min(current_pos + max_chars, text_len)
        actual_chunk_end = end_pos

        if end_pos < text_len:
            para_break = text.rfind('\n\n', current_pos, end_pos)
            if para_break != -1 and para_break > current_pos:
                actual_chunk_end = para_break + 2
                _log_splitter(f"块在段落处分割于位置 {actual_chunk_end} (段落符)")
            else:
                line_break = text.rfind('\n', current_pos, end_pos)
                if line_break != -1 and line_break > current_pos:
                    actual_chunk_end = line_break + 1
                    _log_splitter(f"块在换行处分割于位置 {actual_chunk_end} (换行符)")
                else:
                    search_start_for_sentence_end = max(current_pos, end_pos - max(100, int(max_chars * 0.2)))
                    best_sentence_break = -1
                    sentence_terminators = r'[。．\.！\!？\?]'
                    for match in re.finditer(sentence_terminators, text[search_start_for_sentence_end:end_pos]):
                        break_candidate = search_start_for_sentence_end + match.end()
                        if break_candidate > current_pos:
                            best_sentence_break = break_candidate
                    
                    if best_sentence_break != -1:
                        actual_chunk_end = best_sentence_break
                        _log_splitter(f"块在句子末尾分割于位置 {actual_chunk_end} (标点)")
                    else:
                        space_break = text.rfind(' ', current_pos, end_pos)
                        if space_break != -1 and space_break > current_pos:
                            actual_chunk_end = space_break + 1
                            _log_splitter(f"块在空格处分割于位置 {actual_chunk_end} (空格)")
                        else:
                            _log_splitter(f"未能找到理想分割点，块在位置 {actual_chunk_end} 进行硬切分")
        
        chunk_to_add = text[current_pos:actual_chunk_end]
        if chunk_to_add.strip():
            chunks.append(chunk_to_add)
        current_pos = actual_chunk_end
    
    if not chunks and text.strip():
        chunks.append(text)
        
    _log_splitter(f"文本被分割为 {len(chunks)} 块.")
    return chunks

# --- 新增：获取摘要的辅助函数 ---
def _get_summary(api_key: str, full_text: str,
                 system_prompt_summary: str,
                 signals_forwarder: Optional[Any] = None) -> Optional[str]:
    """
    调用DeepSeek API为给定文本生成摘要。
    """
    def _log_summary_api(message: str):
        if signals_forwarder and hasattr(signals_forwarder, 'log_message') and hasattr(signals_forwarder.log_message, 'emit'):
            signals_forwarder.log_message.emit(f"[LLM API - Summary] {message}")
        else:
            print(f"[LLM API - Summary] {message}")

    _log_summary_api(f"向 DeepSeek API 请求文本摘要 (模型: {DEEPSEEK_MODEL}, 文本长度: {len(full_text)} chars)...")
    
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt_summary},
            {"role": "user", "content": full_text}
        ],
        "stream": False,
        "max_tokens": MAX_OUTPUT_TOKENS_SUMMARY, # 摘要任务的max_tokens
        "temperature": USER_LLM_TEMPERATURE_SUMMARY_KEY # 固定温度
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=180) # 摘要任务也用3分钟超时
        response.raise_for_status()
        data = response.json()

        if "choices" in data and data["choices"]:
            choice = data["choices"][0]
            content = choice.get("message", {}).get("content")
            finish_reason = choice.get("finish_reason")

            if content:
                _log_summary_api(f"摘要获取成功。完成原因: {finish_reason}")
                if finish_reason == "length":
                    _log_summary_api(f"警告: 摘要输出可能因为达到 max_tokens ({MAX_OUTPUT_TOKENS_SUMMARY}) 而被截断。")
                return content.strip()
            else:
                _log_summary_api(f"错误: DeepSeek API 对摘要请求的响应中 'content' 为空。完成原因: {finish_reason}")
        else:
            error_info = data.get('error', {})
            error_msg = error_info.get('message', str(data))
            _log_summary_api(f"错误: DeepSeek API 对摘要请求的响应格式错误或API返回错误。消息: {error_msg}")
        return None

    except requests.exceptions.Timeout:
        _log_summary_api(f"错误: DeepSeek API 对摘要请求超时 (180秒)。")
        return None
    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else 'N/A'
        _log_summary_api(f"错误: DeepSeek API 对摘要请求失败 (状态码: {status_code}): {e}")
        return None
    except Exception as e:
        _log_summary_api(f"错误: 处理 DeepSeek API 对摘要请求的响应时发生未知错误: {e}")
        _log_summary_api(traceback.format_exc())
        return None

# --- 主API调用函数 ---
def call_deepseek_api(api_key: str, text_to_segment: str,
                      signals_forwarder: Optional[Any] = None,
                      target_language: Optional[str] = None) -> Optional[List[str]]:
    
    def _log_main_api(message: str): # 主API调用的局部日志函数
        if signals_forwarder and hasattr(signals_forwarder, 'log_message') and hasattr(signals_forwarder.log_message, 'emit'):
            signals_forwarder.log_message.emit(f"[LLM API - Main] {message}")
        else:
            print(f"[LLM API - Main] {message}")

    def is_running() -> bool: # 保持不变
        if signals_forwarder and hasattr(signals_forwarder, 'parent') and \
           hasattr(signals_forwarder.parent(), 'is_running'):
            return signals_forwarder.parent().is_running
        return True

    if not is_running():
        _log_main_api("API调用前任务已取消。")
        return None

    # --- 语言检测，用于选择正确的系统提示词 (分割和摘要) ---
    detected_lang_code_for_prompt = None
    if target_language and target_language in ['zh', 'ja', 'en']:
        detected_lang_code_for_prompt = target_language
        _log_main_api(f"使用用户指定的语言: {target_language} 来选择提示词。")
    else:
        try:
            if text_to_segment.strip():
                detected_lang_raw = detect(text_to_segment)
                _log_main_api(f"自动检测到文本语言: {detected_lang_raw} 来选择提示词。")
                if detected_lang_raw.startswith('zh'): detected_lang_code_for_prompt = 'zh'
                elif detected_lang_raw == 'ja': detected_lang_code_for_prompt = 'ja'
                elif detected_lang_raw == 'en': detected_lang_code_for_prompt = 'en'
                else: _log_main_api(f"自动检测到的语言 '{detected_lang_raw}' 不是目标语言 (中日英之一)，将使用默认提示词。")
            else:
                _log_main_api("输入文本为空，无法检测语言，将使用默认提示词。")
        except LangDetectException:
            _log_main_api("语言检测失败，将使用默认提示词。")
        except Exception as e_detect:
            _log_main_api(f"语言检测时发生未知错误: {e_detect}，将使用默认提示词。")

    # 选择分割任务的系统提示词
    system_prompt_segmentation = DEFAULT_SYSTEM_PROMPT_FOR_SEGMENTATION
    if detected_lang_code_for_prompt == 'ja':
        system_prompt_segmentation = DEEPSEEK_SYSTEM_PROMPT_JA
    elif detected_lang_code_for_prompt == 'zh':
        system_prompt_segmentation = DEEPSEEK_SYSTEM_PROMPT_ZH
    elif detected_lang_code_for_prompt == 'en':
        system_prompt_segmentation = DEEPSEEK_SYSTEM_PROMPT_EN
    _log_main_api(f"分割任务选用的系统提示词语言: {detected_lang_code_for_prompt or 'default (en)'}")

    # 选择摘要任务的系统提示词
    system_prompt_summary_task = DEFAULT_SYSTEM_PROMPT_FOR_SUMMARY
    if detected_lang_code_for_prompt == 'ja':
        system_prompt_summary_task = DEEPSEEK_SYSTEM_PROMPT_SUMMARY_JA
    elif detected_lang_code_for_prompt == 'zh':
        system_prompt_summary_task = DEEPSEEK_SYSTEM_PROMPT_SUMMARY_ZH
    elif detected_lang_code_for_prompt == 'en':
        system_prompt_summary_task = DEEPSEEK_SYSTEM_PROMPT_SUMMARY_EN
    # (摘要提示词选择的日志已在 _get_summary 中处理，这里不再重复)

    # --- 步骤1: 获取全文摘要 ---
    summary_text = "" # 初始化摘要为空字符串
    if text_to_segment.strip(): # 仅当有实际文本时才尝试获取摘要
        # 估算输入文本的tokens，如果过长，可能需要跳过摘要或进行更复杂的处理
        # 之前的极限测试样本14664 tokens << 64k，所以这里我们上传的json中的文本是适合获取摘要的
        _log_main_api("尝试获取全文摘要...")
        summary_text_optional = _get_summary(api_key, text_to_segment, system_prompt_summary_task, signals_forwarder)
        if summary_text_optional:
            summary_text = summary_text_optional
            _log_main_api("成功获取到摘要。")
        else:
            _log_main_api("未能获取到摘要，将不带摘要继续进行分割。")
            # summary_text 保持为空字符串
    else:
        _log_main_api("输入文本为空，跳过摘要获取。")


    # --- 步骤2: 分块并处理 ---
    all_segments: List[str] = []
    text_chunks = _split_text_into_chunks(text_to_segment, MAX_CHARS_PER_CHUNK, signals_forwarder)
    
    num_chunks = len(text_chunks)
    if num_chunks == 0:
        if text_to_segment.strip():
            _log_main_api("警告: 文本非空但未能有效分割成块。尝试作为单个块处理。")
            text_chunks = [text_to_segment] # 将整个文本作为一个块
            num_chunks = 1
        else:
            _log_main_api("输入文本为空或只包含空格，无需调用API进行分割。")
            return []

    for i, chunk in enumerate(text_chunks):
        if not is_running():
            _log_main_api(f"处理块 {i+1}/{num_chunks} 前任务已取消。")
            return all_segments if all_segments else None 

        _log_main_api(f"向 DeepSeek API 发送块 {i+1}/{num_chunks} 进行分割 (模型: {DEEPSEEK_MODEL}, 文本长度: {len(chunk)} chars)...")
        
        # 构建用户输入，包含摘要和当前块
        user_content_with_summary = f"【全文摘要】:\n{summary_text}\n\n【当前文本块】:\n{chunk}"
        if not summary_text: # 如果没有获取到摘要，则不包含摘要部分
             user_content_with_summary = f"【当前文本块】:\n{chunk}"


        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt_segmentation}, # 使用修改后的分割提示词
                {"role": "user", "content": user_content_with_summary }
            ],
            "stream": False,
            "max_tokens": MAX_OUTPUT_TOKENS_SEGMENTATION, # 分割任务的max_tokens
            "temperature": FIXED_TEMPERATURE # 固定温度
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=180)
            
            if not is_running():
                _log_main_api(f"API 对块 {i+1}/{num_chunks} 响应接收后任务已取消。")
                return all_segments if all_segments else None
                
            response.raise_for_status()
            data = response.json()

            if not is_running():
                _log_main_api(f"API 对块 {i+1}/{num_chunks} 响应解析后任务已取消。")
                return all_segments if all_segments else None

            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                content = choice.get("message", {}).get("content")
                finish_reason = choice.get("finish_reason")

                if content:
                    segments_from_chunk = [seg.strip() for seg in content.split('\n') if seg.strip()]
                    all_segments.extend(segments_from_chunk)
                    _log_main_api(f"块 {i+1}/{num_chunks} 成功处理，获得 {len(segments_from_chunk)} 个片段。完成原因: {finish_reason}")
                    if finish_reason == "length":
                        _log_main_api(f"警告: 块 {i+1}/{num_chunks} 的输出可能因为达到 max_tokens ({MAX_OUTPUT_TOKENS_SEGMENTATION}) 而被截断。")
                else:
                    # 这里content为空，但finish_reason可能不是length，例如API内部错误但返回了200
                    _log_main_api(f"错误: DeepSeek API 对块 {i+1}/{num_chunks} 的响应中 'content' 为空。完成原因: {finish_reason}, 响应数据: {data}")

            else: # API返回了错误结构
                error_info = data.get('error', {})
                error_msg = error_info.get('message', str(data))
                error_type = error_info.get('type')
                error_code = error_info.get('code')
                _log_main_api(f"错误: DeepSeek API 对块 {i+1}/{num_chunks} 的响应格式错误或API返回错误。类型: {error_type}, Code: {error_code}, 消息: {error_msg}")
        
        except requests.exceptions.Timeout:
            _log_main_api(f"错误: DeepSeek API 对块 {i+1}/{num_chunks} 的请求超时 (180秒)。")
            # 决定是否中止，当前不中止，继续处理下一个块（如果需要）
        except requests.exceptions.RequestException as e:
            error_details = ""
            status_code = 'N/A'
            if e.response is not None:
                status_code = e.response.status_code
                try: 
                    err_json = e.response.json().get('error', {})
                    message = err_json.get('message', e.response.text)
                    error_details = f": [{err_json.get('type', 'UnknownType')}/{err_json.get('code', 'UnknownCode')}] {message}"
                except requests.exceptions.JSONDecodeError: 
                    error_details = f": {e.response.text}"
            else:
                error_details = f": {str(e)}"
            _log_main_api(f"错误: DeepSeek API 对块 {i+1}/{num_chunks} 的请求失败 (状态码: {status_code}){error_details}")
        except Exception as e:
            _log_main_api(f"错误: 处理 DeepSeek API 对块 {i+1}/{num_chunks} 的响应时发生未知错误: {e}")
            _log_main_api(traceback.format_exc())
        
        if signals_forwarder and hasattr(signals_forwarder, 'llm_progress_signal') and hasattr(signals_forwarder.llm_progress_signal, 'emit'):
             progress_percentage = int(((i + 1) / num_chunks) * 100)
             signals_forwarder.llm_progress_signal.emit(progress_percentage)

        if num_chunks > 1 and i < num_chunks - 1:
            if not is_running(): # 在sleep前再次检查
                _log_main_api(f"处理完块 {i+1}/{num_chunks} 后任务已取消，不再延时。")
                return all_segments if all_segments else None
            time.sleep(0.5)


    if not all_segments and text_to_segment.strip():
        _log_main_api("所有块处理完毕，但未能从任何块中获取到有效的分割结果。请检查API密钥、网络连接及DeepSeek服务状态。")
        return None 

    _log_main_api(f"所有 {num_chunks} 个块处理完成。总共收集到 {len(all_segments)} 个片段。")
    return all_segments