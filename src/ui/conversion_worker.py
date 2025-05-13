import os
import json
import traceback
from typing import Optional, Any, Dict # 添加 Dict

from PyQt6.QtCore import QObject, pyqtSignal, QThread

from core.transcription_parser import TranscriptionParser
from core.srt_processor import SrtProcessor
from core.llm_api import call_deepseek_api
from core.data_models import ParsedTranscription
from config import ( # 导入默认值，以防 srt_params 中某些键缺失
    DEFAULT_MIN_DURATION_TARGET, DEFAULT_MAX_DURATION,
    DEFAULT_MAX_CHARS_PER_LINE, DEFAULT_DEFAULT_GAP_MS
)


class WorkerSignals(QObject):
    finished = pyqtSignal(str, bool)
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)


class ConversionWorker(QObject):
    def __init__(self, api_key: str, json_path: str, output_dir: str,
                 srt_processor: SrtProcessor, source_format: str,
                 srt_params: Dict[str, Any], # 修改：接收 srt_params 字典
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.signals = WorkerSignals(parent=self)
        self.api_key = api_key
        self.json_path = json_path
        self.output_dir = output_dir
        self.srt_processor = srt_processor
        self.source_format = source_format
        self.srt_params = srt_params # 存储SRT参数
        self.transcription_parser = TranscriptionParser(signals_forwarder=self.signals)
        self.is_running = True

    def stop(self):
        self.is_running = False
        if self.signals: # 确保signals存在
            self.signals.log_message.emit("接收到停止信号...")

    def run(self):
        try:
            if not self.is_running:
                self.signals.finished.emit("任务开始前被取消。", False)
                return
            self.signals.progress.emit(5)
            self.signals.log_message.emit(f"开始转换任务: JSON文件 '{os.path.basename(self.json_path)}', 格式 '{self.source_format}'")
            self.signals.log_message.emit(f"当前SRT参数: {self.srt_params}")


            with open(self.json_path, "r", encoding="utf-8") as f:
                raw_api_data = json.load(f)
            parsed_transcription_data: Optional[ParsedTranscription] = self.transcription_parser.parse(raw_api_data, self.source_format)

            if parsed_transcription_data is None:
                self.signals.log_message.emit(f"JSON文件 '{os.path.basename(self.json_path)}' 解析失败 ({self.source_format} 格式)。")
                self.signals.finished.emit(f"JSON 解析失败 ({self.source_format} 格式)。", False)
                return

            text_to_segment = parsed_transcription_data.full_text
            if not text_to_segment:
                if parsed_transcription_data.words:
                    self.signals.log_message.emit("JSON中无完整文本，将从词语列表中拼接。")
                    text_to_segment = " ".join([word.text for word in parsed_transcription_data.words])
                if not text_to_segment:
                    self.signals.log_message.emit("错误: 无法从JSON中获取用于LLM分割的文本。")
                    self.signals.finished.emit("无法获取LLM分割用文本。", False)
                    return
            self.signals.log_message.emit(f"获取到待分割文本，长度: {len(text_to_segment)} 字符。")

            if not self.is_running:
                self.signals.finished.emit("任务在读取/解析JSON后被取消。", False)
                return
            self.signals.progress.emit(10)

            llm_segments = call_deepseek_api(self.api_key, text_to_segment, self.signals)
            if llm_segments is None:
                self.signals.finished.emit("DeepSeek API 调用失败或返回空。" if self.is_running else "任务在API调用期间被取消。", False)
                return

            if not self.is_running:
                self.signals.finished.emit("任务在API调用成功后被取消。", False)
                return
            self.signals.progress.emit(40)
            self.signals.log_message.emit("开始使用LLM返回的片段生成 SRT 内容...")

            # 从 srt_params 字典中安全地获取参数，如果缺失则使用默认值
            min_dur_target = self.srt_params.get('min_duration_target', DEFAULT_MIN_DURATION_TARGET)
            max_dur = self.srt_params.get('max_duration', DEFAULT_MAX_DURATION)
            max_chars = self.srt_params.get('max_chars_per_line', DEFAULT_MAX_CHARS_PER_LINE)
            gap_ms = self.srt_params.get('default_gap_ms', DEFAULT_DEFAULT_GAP_MS)

            final_srt = self.srt_processor.process_to_srt(
                parsed_transcription_data,
                llm_segments,
                self.signals,
                min_duration_target=float(min_dur_target), #确保是float
                max_duration=float(max_dur), #确保是float
                max_chars_per_line=int(max_chars), #确保是int
                default_gap_ms=int(gap_ms) #确保是int
            )


            if final_srt is None:
                self.signals.log_message.emit("SRT 内容生成失败。")
                self.signals.finished.emit("SRT 内容生成失败。" if self.is_running else "任务在SRT生成期间被取消。", False)
                return

            if not self.is_running:
                self.signals.finished.emit("任务在SRT生成成功后立即被取消。", False)
                return
            self.signals.progress.emit(99)

            base_name = os.path.splitext(os.path.basename(self.json_path))[0]
            output_srt_filepath = os.path.join(self.output_dir, f"{base_name}.srt")
            with open(output_srt_filepath, "w", encoding="utf-8") as f:
                f.write(final_srt)
            self.signals.log_message.emit(f"SRT 文件已成功保存到: {output_srt_filepath}")

            if not self.is_running:
                self.signals.finished.emit(f"文件已保存到 {output_srt_filepath}，但任务随后被标记为取消。", False)
                return

            self.signals.progress.emit(100)
            self.signals.finished.emit(f"转换完成！SRT 文件已保存到:\n{output_srt_filepath}", True)
        except Exception as e:
            error_msg = f"处理过程中发生严重错误: {e}\n详细追溯:\n{traceback.format_exc()}"
            self.signals.log_message.emit(error_msg)
            final_message = f"处理失败: {e}" if self.is_running else f"任务因用户取消而停止，过程中出现异常: {e}"
            self.signals.finished.emit(final_message, False)
        finally:
            self.is_running = False