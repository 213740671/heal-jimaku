import os
import json
import traceback
from typing import Optional, Any, Dict

from PyQt6.QtCore import QObject, pyqtSignal

from core.transcription_parser import TranscriptionParser
from core.srt_processor import SrtProcessor
from core.llm_api import call_llm_api_for_segmentation
from core.data_models import ParsedTranscription
from core.elevenlabs_api import ElevenLabsSTTClient
from config import (
    USER_LLM_API_KEY_KEY, DEFAULT_LLM_API_KEY,
    USER_LLM_API_BASE_URL_KEY, DEFAULT_LLM_API_BASE_URL,
    USER_LLM_MODEL_NAME_KEY, DEFAULT_LLM_MODEL_NAME,
    USER_LLM_TEMPERATURE_KEY, DEFAULT_LLM_TEMPERATURE
)

class WorkerSignals(QObject):
    finished = pyqtSignal(str, bool)
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)
    free_transcription_json_generated = pyqtSignal(str)


class ConversionWorker(QObject):
    def __init__(self,
                 input_json_path: str,
                 output_dir: str,
                 srt_processor: SrtProcessor, # 已配置好的 SrtProcessor 实例
                 source_format: str,
                 input_mode: str,
                 free_transcription_params: Optional[Dict[str, Any]],
                 elevenlabs_stt_client: ElevenLabsSTTClient,
                 llm_config: Dict[str, Any], # 包含LLM配置的字典
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.signals = WorkerSignals()
        
        self.input_json_path = input_json_path
        self.output_dir = output_dir
        self.srt_processor = srt_processor # 这个实例应该已经包含了所有SRT和LLM参数
        self.source_format = source_format
        self.input_mode = input_mode
        self.free_transcription_params = free_transcription_params
        self.elevenlabs_stt_client = elevenlabs_stt_client
        
        self.llm_config = llm_config 

        # 确保 SrtProcessor 和 ElevenLabsSTTClient (如果需要) 有 set_signals_forwarder 方法
        if self.srt_processor and hasattr(self.srt_processor, 'set_signals_forwarder'):
            self.srt_processor.set_signals_forwarder(self.signals)
        
        if self.elevenlabs_stt_client and hasattr(self.elevenlabs_stt_client, 'set_signals_forwarder'):
            self.elevenlabs_stt_client.set_signals_forwarder(self.signals)
        elif self.elevenlabs_stt_client and hasattr(self.elevenlabs_stt_client, '_signals'): # Fallback if it uses _signals
            self.elevenlabs_stt_client._signals = self.signals


        self.transcription_parser = TranscriptionParser(signals_forwarder=self.signals)
        self.is_running = True

    def stop(self):
        self.is_running = False
        self.signals.log_message.emit("接收到停止信号，尝试优雅停止任务...")
        if self.elevenlabs_stt_client and hasattr(self.elevenlabs_stt_client, 'stop_current_task'):
            self.elevenlabs_stt_client.stop_current_task()

    def run(self):
        try:
            generated_json_path = self.input_json_path
            actual_source_format = self.source_format
            current_overall_progress = 0 

            PROGRESS_INIT = 5
            PROGRESS_STT_COMPLETE_FREE = 35      
            PROGRESS_JSON_SAVED_FREE = 38        
            PROGRESS_JSON_PARSED_FREE = 40       
            PROGRESS_LLM_COMPLETE_FREE = 70      
            PROGRESS_JSON_PARSED_LOCAL = 10 
            PROGRESS_LLM_COMPLETE_LOCAL = 40     
            PROGRESS_SRT_PROCESSING_MAX = 99 
            PROGRESS_FINAL = 100

            self.signals.progress.emit(PROGRESS_INIT)
            current_overall_progress = PROGRESS_INIT

            if self.input_mode == "free_transcription":
                if not self.free_transcription_params or not self.free_transcription_params.get("audio_file_path"):
                    self.signals.finished.emit("错误：免费转录模式下未提供音频文件参数。", False); return

                self.signals.log_message.emit("--- 开始免费在线转录 (ElevenLabs) ---")
                audio_path = self.free_transcription_params["audio_file_path"]
                lang_from_dialog = self.free_transcription_params.get("language")
                num_speakers = self.free_transcription_params.get("num_speakers")
                tag_events = self.free_transcription_params.get("tag_audio_events", True)

                transcription_data = self.elevenlabs_stt_client.transcribe_audio(
                    audio_file_path=audio_path, language_code=lang_from_dialog,
                    num_speakers=num_speakers, tag_audio_events=tag_events
                )
                if not self.is_running: self.signals.finished.emit("任务在ElevenLabs API调用后被取消。", False); return
                if transcription_data is None: self.signals.finished.emit("ElevenLabs API 转录失败或返回空。", False); return
                
                current_overall_progress = PROGRESS_STT_COMPLETE_FREE
                self.signals.progress.emit(current_overall_progress)
                
                base_name = os.path.splitext(os.path.basename(audio_path))[0]
                generated_json_path = os.path.join(self.output_dir, f"{base_name}_elevenlabs_transcript.json")
                try:
                    with open(generated_json_path, "w", encoding="utf-8") as f_json:
                        json.dump(transcription_data, f_json, ensure_ascii=False, indent=4)
                    self.signals.log_message.emit(f"ElevenLabs转录结果已保存到: {generated_json_path}")
                    self.signals.free_transcription_json_generated.emit(generated_json_path)
                except IOError as e:
                    self.signals.finished.emit(f"保存ElevenLabs转录JSON失败: {e}", False); return
                actual_source_format = "elevenlabs"
                self.signals.log_message.emit("--- 免费在线转录与JSON保存完成 ---")
                
                current_overall_progress = PROGRESS_JSON_SAVED_FREE
                self.signals.progress.emit(current_overall_progress)
            else: 
                self.signals.log_message.emit(f"使用本地JSON文件: {os.path.basename(generated_json_path)}")
            
            if not self.is_running: self.signals.finished.emit("任务在加载/生成JSON前被取消。", False); return

            self.signals.log_message.emit(f"开始解析JSON文件 '{os.path.basename(generated_json_path)}', 格式 '{actual_source_format}'")
            try:
                with open(generated_json_path, "r", encoding="utf-8") as f: raw_api_data = json.load(f)
            except FileNotFoundError:
                self.signals.finished.emit(f"错误：无法找到输入JSON文件 '{generated_json_path}'。", False); return
            except json.JSONDecodeError as e:
                self.signals.finished.emit(f"错误：解析JSON文件 '{generated_json_path}' 失败: {e}", False); return
            
            parsed_transcription_data: Optional[ParsedTranscription] = self.transcription_parser.parse(raw_api_data, actual_source_format)
            if parsed_transcription_data is None:
                self.signals.finished.emit(f"JSON 解析失败 ({actual_source_format} 格式)。", False); return
            
            if self.input_mode == "local_json":
                current_overall_progress = PROGRESS_JSON_PARSED_LOCAL
            else: 
                current_overall_progress = PROGRESS_JSON_PARSED_FREE
            self.signals.progress.emit(current_overall_progress)

            text_to_segment = parsed_transcription_data.full_text
            if not text_to_segment:
                if parsed_transcription_data.words:
                    text_to_segment = " ".join([word.text for word in parsed_transcription_data.words if word.text is not None])
                if not text_to_segment: self.signals.finished.emit("无法获取LLM分割用文本。", False); return
            self.signals.log_message.emit(f"获取到待分割文本，长度: {len(text_to_segment)} 字符。")
            if not self.is_running: self.signals.finished.emit("任务在解析JSON后被取消。", False); return
            
            llm_target_language_for_api: Optional[str] = None
            if self.input_mode == "free_transcription" and self.free_transcription_params:
                lang_code_from_dialog = self.free_transcription_params.get("language")
                if lang_code_from_dialog and lang_code_from_dialog != "auto":
                    llm_target_language_for_api = lang_code_from_dialog
                    self.signals.log_message.emit(f"LLM处理将优先使用对话框指定的语言: {llm_target_language_for_api}")
            
            if not llm_target_language_for_api and parsed_transcription_data and \
               parsed_transcription_data.language_code:
                asr_lang_code = parsed_transcription_data.language_code.lower()
                mapped_lang = None
                if asr_lang_code.startswith('zh'): mapped_lang = 'zh'
                elif asr_lang_code == 'ja' or asr_lang_code == 'jpn': mapped_lang = 'ja'
                elif asr_lang_code == 'en' or asr_lang_code.startswith('en-') or asr_lang_code == 'eng': mapped_lang = 'en'
                
                if mapped_lang:
                    llm_target_language_for_api = mapped_lang
                    self.signals.log_message.emit(f"LLM处理将使用ASR检测到的语言: {llm_target_language_for_api} (原始ASR代码: '{asr_lang_code}')")
                else:
                    self.signals.log_message.emit(f"ASR语言代码 '{asr_lang_code}' 未能映射到目标语言 (中/日/英)，LLM将进行自动语言检测。")
            elif not llm_target_language_for_api:
                 self.signals.log_message.emit(f"未从对话框或ASR结果中获得明确语言指示，LLM将进行自动语言检测。")

            # --- 从 self.llm_config (由MainWindow传入) 获取LLM参数 ---
            llm_api_key = self.llm_config.get(USER_LLM_API_KEY_KEY, DEFAULT_LLM_API_KEY)
            llm_base_url_str = self.llm_config.get(USER_LLM_API_BASE_URL_KEY, DEFAULT_LLM_API_BASE_URL)
            llm_model_name = self.llm_config.get(USER_LLM_MODEL_NAME_KEY, DEFAULT_LLM_MODEL_NAME)
            llm_temperature = self.llm_config.get(USER_LLM_TEMPERATURE_KEY, DEFAULT_LLM_TEMPERATURE)
            # --- 获取结束 ---

            self.signals.log_message.emit(f"调用LLM API进行文本分割 (URL配置: '{llm_base_url_str}', 模型: '{llm_model_name}', 温度: {llm_temperature})...")
            llm_segments = call_llm_api_for_segmentation(
                api_key=llm_api_key,
                text_to_segment=text_to_segment,
                custom_api_base_url_str=llm_base_url_str,
                custom_model_name=llm_model_name,
                custom_temperature=llm_temperature,
                signals_forwarder=self.signals, # 传递信号转发器
                target_language=llm_target_language_for_api
            ) 
            if not self.is_running : self.signals.finished.emit("任务在LLM API调用期间被取消。", False); return
            if llm_segments is None: self.signals.finished.emit("LLM API 调用失败或返回空。", False); return
            
            if self.input_mode == "free_transcription":
                current_overall_progress = PROGRESS_LLM_COMPLETE_FREE
            else: 
                current_overall_progress = PROGRESS_LLM_COMPLETE_LOCAL
            self.signals.progress.emit(current_overall_progress)

            self.signals.log_message.emit("开始使用LLM返回的片段生成 SRT 内容...")
            
            # SrtProcessor 实例 (self.srt_processor) 应该已经通过 MainWindow 正确配置了其SRT参数和LLM参数

            srt_progress_offset = current_overall_progress 
            srt_progress_range = PROGRESS_SRT_PROCESSING_MAX - srt_progress_offset
            self.signals.log_message.emit(f"SRT处理阶段 - 全局进度偏移: {srt_progress_offset}%, 范围: {srt_progress_range}%")

            # 设置 SrtProcessor 实例的进度参数，以便其内部的 _emit_srt_progress 能正确计算全局进度
            if self.srt_processor: # 确保 srt_processor 实例存在
                self.srt_processor._current_progress_offset = srt_progress_offset
                self.srt_processor._current_progress_range = srt_progress_range

            final_srt = self.srt_processor.process_to_srt(
                parsed_transcription_data, llm_segments
            )

            if not self.is_running: self.signals.finished.emit("任务在SRT生成期间被取消。", False); return
            if final_srt is None: self.signals.finished.emit("SRT 内容生成失败。", False); return
            
            if self.input_mode == "local_json":
                output_base_name = os.path.splitext(os.path.basename(generated_json_path))[0]
            elif self.free_transcription_params and self.free_transcription_params.get("audio_file_path"):
                output_base_name = os.path.splitext(os.path.basename(self.free_transcription_params["audio_file_path"]))[0]
            else: 
                output_base_name = "processed_subtitle"

            if self.input_mode == "free_transcription" and output_base_name.endswith("_elevenlabs_transcript"):
                output_base_name = output_base_name[:-len("_elevenlabs_transcript")] 

            output_srt_filepath = os.path.join(self.output_dir, f"{output_base_name}.srt")
            try:
                with open(output_srt_filepath, "w", encoding="utf-8") as f: f.write(final_srt)
                self.signals.log_message.emit(f"SRT 文件已成功保存到: {output_srt_filepath}")
            except IOError as e:
                self.signals.finished.emit(f"保存最终SRT文件失败: {e}", False); return

            if not self.is_running: self.signals.finished.emit(f"文件已保存，但任务随后被取消。", True); return

            self.signals.progress.emit(PROGRESS_FINAL)
            self.signals.finished.emit(f"转换完成！SRT 文件已保存到:\n{output_srt_filepath}", True)

        except Exception as e:
            error_msg = f"处理过程中发生严重错误: {e}\n详细追溯:\n{traceback.format_exc()}"
            self.signals.log_message.emit(error_msg)
            final_message = f"处理失败: {e}" if self.is_running else f"任务因用户取消而停止，过程中出现异常: {e}"
            self.signals.finished.emit(final_message, False)
        finally:
            self.is_running = False
