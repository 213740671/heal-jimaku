import os
import json
import traceback # 用于打印详细错误
from typing import Optional, Any

from PyQt6.QtCore import QObject, pyqtSignal, QThread

# Corrected imports: removed 'src.' prefix
from core.transcription_parser import TranscriptionParser
from core.srt_processor import SrtProcessor
from core.llm_api import call_deepseek_api
from core.data_models import ParsedTranscription

# --- Worker 信号类 ---
class WorkerSignals(QObject):
    """定义工作线程可以发出的信号。"""
    finished = pyqtSignal(str, bool) # 任务完成信号 (消息, 是否成功)
    progress = pyqtSignal(int) # 进度更新信号 (百分比)
    log_message = pyqtSignal(str) # 日志消息信号

# --- 工作线程类 ---
class ConversionWorker(QObject):
    """执行转换任务的后台线程。"""
    def __init__(self, api_key: str, json_path: str, output_dir: str, srt_processor: SrtProcessor, source_format: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.signals = WorkerSignals(parent=self) # 在 worker 内部创建 signals 实例
        self.api_key = api_key
        self.json_path = json_path
        self.output_dir = output_dir
        self.srt_processor = srt_processor # SrtProcessor 实例由外部传入
        self.source_format = source_format
        self.transcription_parser = TranscriptionParser(signals_forwarder=self.signals) # 解析器使用 worker 的信号
        self.is_running = True # 标记线程是否应继续运行

    def stop(self):
        """停止工作线程的执行。"""
        self.is_running = False
        if self.signals:
            self.signals.log_message.emit("接收到停止信号...")

    def run(self):
        """线程执行的主函数。"""
        try:
            if not self.is_running:
                self.signals.finished.emit("任务开始前被取消。", False)
                return
            self.signals.progress.emit(5)
            self.signals.log_message.emit(f"开始转换任务: JSON文件 '{os.path.basename(self.json_path)}', 格式 '{self.source_format}'")

            # 读取并解析JSON文件
            with open(self.json_path, "r", encoding="utf-8") as f:
                raw_api_data = json.load(f)
            parsed_transcription_data: Optional[ParsedTranscription] = self.transcription_parser.parse(raw_api_data, self.source_format)

            if parsed_transcription_data is None: # JSON解析失败
                self.signals.log_message.emit(f"JSON文件 '{os.path.basename(self.json_path)}' 解析失败 ({self.source_format} 格式)。")
                self.signals.finished.emit(f"JSON 解析失败 ({self.source_format} 格式)。", False)
                return

            text_to_segment = parsed_transcription_data.full_text # 获取完整文本用于分割
            if not text_to_segment: # 如果JSON中没有完整文本
                if parsed_transcription_data.words: # 尝试从词列表中拼接
                    self.signals.log_message.emit("JSON中无完整文本，将从词语列表中拼接。")
                    text_to_segment = " ".join([word.text for word in parsed_transcription_data.words])
                if not text_to_segment: # 如果仍然没有文本
                    self.signals.log_message.emit("错误: 无法从JSON中获取用于LLM分割的文本。")
                    self.signals.finished.emit("无法获取LLM分割用文本。", False)
                    return
            self.signals.log_message.emit(f"获取到待分割文本，长度: {len(text_to_segment)} 字符。")

            if not self.is_running:
                self.signals.finished.emit("任务在读取/解析JSON后被取消。", False)
                return
            self.signals.progress.emit(10) # JSON解析部分完成

            # 调用DeepSeek API进行文本分割
            llm_segments = call_deepseek_api(self.api_key, text_to_segment, self.signals)
            if llm_segments is None: # API调用失败或返回空
                self.signals.finished.emit("DeepSeek API 调用失败或返回空。" if self.is_running else "任务在API调用期间被取消。", False)
                return

            if not self.is_running:
                self.signals.finished.emit("任务在API调用成功后被取消。", False)
                return
            self.signals.progress.emit(40) # API调用后，SRT处理前
            self.signals.log_message.emit("开始使用LLM返回的片段生成 SRT 内容...")

            final_srt = self.srt_processor.process_to_srt(parsed_transcription_data, llm_segments, self.signals)


            if final_srt is None: # SRT内容生成失败
                self.signals.log_message.emit("SRT 内容生成失败。")
                self.signals.finished.emit("SRT 内容生成失败。" if self.is_running else "任务在SRT生成期间被取消。", False)
                return

            if not self.is_running:
                self.signals.finished.emit("任务在SRT生成成功后立即被取消。", False)
                return
            self.signals.progress.emit(99) # 即将完成

            # 保存SRT文件
            base_name = os.path.splitext(os.path.basename(self.json_path))[0] # 从JSON文件名获取基础名
            output_srt_filepath = os.path.join(self.output_dir, f"{base_name}.srt")
            with open(output_srt_filepath, "w", encoding="utf-8") as f:
                f.write(final_srt)
            self.signals.log_message.emit(f"SRT 文件已成功保存到: {output_srt_filepath}")

            if not self.is_running: # 应该很少见
                self.signals.finished.emit(f"文件已保存到 {output_srt_filepath}，但任务随后被标记为取消。", False)
                return

            self.signals.progress.emit(100) # 完成
            self.signals.finished.emit(f"转换完成！SRT 文件已保存到:\n{output_srt_filepath}", True)
        except Exception as e: # 发生严重错误
            error_msg = f"处理过程中发生严重错误: {e}\n详细追溯:\n{traceback.format_exc()}"
            self.signals.log_message.emit(error_msg)
            final_message = f"处理失败: {e}" if self.is_running else f"任务因用户取消而停止，过程中出现异常: {e}"
            self.signals.finished.emit(final_message, False)
        finally:
            self.is_running = False # 确保 worker 逻辑上的运行状态结束