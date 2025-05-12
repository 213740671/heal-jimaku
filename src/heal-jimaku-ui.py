import sys
import os
import json
import requests # 用于 DeepSeek API 调用
import difflib
import re

# --- faulthandler 错误处理模块 ---
import faulthandler
try:
    FHT_LOG_ENABLED = False
    if sys.stderr is None:
        log_dir_app = ""
        try:
            home_dir = os.path.expanduser("~")
            log_dir_app = os.path.join(home_dir, ".heal_jimaku_gui_logs")
            if not os.path.exists(log_dir_app):
                os.makedirs(log_dir_app, exist_ok=True)
            crash_log_path = os.path.join(log_dir_app, "heal_jimaku_crashes.log")
            with open(crash_log_path, 'a', encoding='utf-8') as f_log:
                faulthandler.enable(file=f_log, all_threads=True)
            FHT_LOG_ENABLED = True
        except Exception:
            pass
    else:
        faulthandler.enable(all_threads=True)
        FHT_LOG_ENABLED = True
except Exception:
    pass
# --- faulthandler 设置结束 ---

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QTextEdit, QCheckBox, QComboBox,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer, QPoint
from PyQt6.QtGui import QIcon, QFont, QColor, QTextCursor, QPixmap, QPainter, QBrush, QLinearGradient

from dataclasses import dataclass, field
from typing import List, Optional, Literal

# --- 配置与常量定义 ---
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".heal_jimaku_gui")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# SRT 生成常量
MIN_DURATION_TARGET = 1.2
MIN_DURATION_ABSOLUTE = 1.0
MAX_DURATION = 12.0
MAX_CHARS_PER_LINE = 60
DEFAULT_GAP_MS = 100
ALIGNMENT_SIMILARITY_THRESHOLD = 0.7

# 标点集合
FINAL_PUNCTUATION = {'.', '。', '?', '？', '!', '！'}
ELLIPSIS_PUNCTUATION = {'...', '......', '‥'}
COMMA_PUNCTUATION = {',', '、'}
ALL_SPLIT_PUNCTUATION = FINAL_PUNCTUATION | ELLIPSIS_PUNCTUATION | COMMA_PUNCTUATION

# DeepSeek 系统提示
DEEPSEEK_SYSTEM_PROMPT = """「重要：您的任务是精确地分割提供的日语文本。请严格按照以下规则操作，并仅输出分割后的文本片段列表。每个片段占独立的一行。不要添加或删除任何原始文本中的字符，保持原始顺序。」

您是一位专业的文本处理员，擅长根据标点和上下文将日语长文本分割成自然的句子或语义单元。

**输入：** 一段完整的日语文本字符串。

**输出要求：** 一个文本片段的列表，每个片段占据新的一行。

**预处理步骤：**
在进行任何分割处理之前，请首先对输入文本进行预处理：确保文字之间无空格。若原始文本中存在空格（例如“説 明 し て く だ さ い”），请先将其去除（修改为“説明してください”）再进行后续的分割操作。

**分割规则 (请按顺序优先应用)：**

1.  **独立附加情景 (括号优先)：** 将括号 `()` 或全角括号 `（）` 内的附加情景描述（例如 `(笑い声)`、`(雨の音)`、`(ため息)`、`（会場騒然）`等）视为独立的片段进行分离。
    *   **处理逻辑：**
        *   `文A(イベント)文B。` -> `文A` / `(イベント)` / `文B。`
        *   `文A。(イベント)文B。` -> `文A。` / `(イベント)` / `文B。`
        *   `文A(イベント)。文B。` -> `文A。` / `(イベント)` / `文B。` (括号内容成为一个片段，其后的句号和前一个没有句号的句子组合成为一个片段)
        *   `(イベント)文A。` -> `(イベント)` / `文A。`

2.  **独立引用单元 (引号优先)：** 将以 `「`、`『` 开始并以对应的 `」`、`』` 结束的完整引用内容，视为一个独立的片段。这些引号内的句末标点（如 `。`、`？`、`！`、`…`等）**不**触发片段内部分割。整个带引号的引用被视为一个单元，处理逻辑类似于上述的独立附加情景。
    *   **处理逻辑：**
        *   `文A「引用文。」文B。` -> `文A` / `「引用文。」` / `文B。`
        *   `文A。「引用文１。引用文２！」文B。` -> `文A。` / `「引用文１。引用文２！」` / `文B。`
        *   `「引用文。」文B。` -> `「引用文。」` / `文B。`
        *   `文A「引用文」。文B。` -> `文A。` / `「引用文」` / `文B。` (引号后的标点若紧跟，则属于引号片段的前一个片段)
        *   `「引用文１。」「引用文２。」` -> `「引用文１。」` / `「引用文２。」`

3.  **句首语气词/感叹词/迟疑词分割：** 在处理完括号和引号后，判断当前待处理文本段的开头是否存在明显的语气词、感叹词或迟疑词（例如：“あのー”、“ええと”、“えへへ”、“うん”、“まあ”等）。
    *   如果这类词语出现在句首，并且其后紧跟的内容能独立构成有意义的语句或意群，则应将该语气词等单独分割出来。
    *   **示例：**
        *   输入: `あのーすみませんちょっといいですか`
        *   期望输出:
            ```
            あのー
            すみませんちょっといいですか
            ```
        *   输入: `えへへ、ありがとう。`
        *   期望输出:
            ```
            えへへ
            ありがとう。
            ```
    *   **注意：** 此规则仅适用于句首。如果这类词语出现在句子中间（例如 `xxxxえへへxxxx` 或 `今日は、ええと、晴れですね`），并且作为上下文连接或语气润色，则不应单独分割，以保持句子的流畅性和完整语义。此时应结合规则4（确保语义连贯性）进行判断。

4.  **确保语义连贯性 (指导规则5)：** 在进行主要分割点判断（规则5）之前，必须先理解当前待处理文本段的整体意思。此规则优先确保分割出来的片段在语义上是自然的、不过于零碎。此规则尤其适用于指导规则5中省略号（`…`、`‥`等）的处理，这些标点有时用于连接一个未完结的意群，而非严格的句子结束。应优先形成语义上更完整的片段，避免在仍能构成一个完整意群的地方进行切割。
    *   **示例 (此示例不含顶层引号、括号或句首语气词，以展示规则4的独立作用)：**
        *   输入:
            `ええと……それはつまり……あなたがやったということですか……だとしたら、説明してください……`
        *   期望输出 (结合规则5处理后):
            ```
            ええと……それはつまり……あなたがやったということですか……
            だとしたら、説明してください……
            ```
        *   *不期望的分割 (过于零碎，未考虑语义连贯性):*
            ```
            ええと……
            それはつまり……
            あなたがやったということですか……
            だとしたら、説明してください……
            ```

5.  **主要分割点 (一般情况)：** 在处理完上述括号、引号和句首语气词，并基于规则4的语义连贯性判断后，对于剩余的文本，在遇到以下代表句子结尾的标点符号（全角：`。`、`？`、`！`、`…`、`‥` 以及半角：`.` `?` `!` `...` `‥`）后进行分割。标点符号应保留在它所结束的那个片段的末尾。
    *   *注意：* 针对连续的省略号，如 `……` (两个 `…`) 或 `......` (六个 `.`)，应视为单个省略号标点，并根据规则4的语义连贯性判断是否分割。

6.  **确保完整性：** 输出的片段拼接起来应与原始输入文本（经过预处理去除空格后）完全一致。
"""

# --- 资源路径处理函数 ---
def resource_path(relative_path):
    """获取资源的绝对路径，用于开发环境和打包后环境。如果找不到则返回None。"""
    path = None
    try:
        base_path = sys._MEIPASS # type: ignore
        path = os.path.join(base_path, "assets", relative_path)
        if not os.path.exists(path):
            path = os.path.join(base_path, relative_path)
    except AttributeError:
        base_path = os.path.abspath(os.path.dirname(__file__))
        path = os.path.join(base_path, "assets", relative_path)
        if not os.path.exists(path):
            alt_base_path = os.path.dirname(base_path)
            alt_path = os.path.join(alt_base_path, "assets", relative_path)
            if os.path.exists(alt_path):
                path = alt_path
            else:
                dev_direct_path = os.path.join(base_path, relative_path)
                if os.path.exists(dev_direct_path):
                    path = dev_direct_path
                else:
                    path = None

    if path and not os.path.exists(path):
        # print(f"Warning: Resource not found at calculated path: {path} (relative: {relative_path})")
        return None
    return path

# --- Worker 信号类 ---
class WorkerSignals(QObject):
    """定义工作线程可以发出的信号。"""
    finished = pyqtSignal(str, bool)
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)

# --- 自定义控件 ---
class TransparentWidget(QWidget):
    """一个具有半透明背景和圆角的自定义QWidget。"""
    def __init__(self, parent=None, bg_color=QColor(255, 255, 255, 3)):
        super().__init__(parent)
        self.bg_color = bg_color
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self.bg_color)); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 10, 10)

class CustomLabel(QLabel):
    """具有描边效果的自定义QLabel。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_color = QColor(92, 138, 111)
        self.stroke_color = QColor(242, 234, 218)
        self.setStyleSheet(f"color: {self.main_color.name()}; background-color: transparent;")
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.text(); rect = self.rect(); font = self.font(); painter.setFont(font)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0: continue
                shadow_rect = rect.translated(dx, dy); painter.setPen(self.stroke_color)
                painter.drawText(shadow_rect, self.alignment(), text)
        painter.setPen(self.main_color); painter.drawText(rect, self.alignment(), text)

class CustomLabel_title(QLabel):
    """用于标题的自定义描边QLabel。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_color = QColor(87, 128, 183)
        self.stroke_color = QColor(242, 234, 218)
        self.setStyleSheet(f"color: {self.main_color.name()}; background-color: transparent;")
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.text(); rect = self.rect(); font = self.font(); painter.setFont(font)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0: continue
                shadow_rect = rect.translated(dx, dy); painter.setPen(self.stroke_color)
                painter.drawText(shadow_rect, self.alignment(), text)
        painter.setPen(self.main_color); painter.drawText(rect, self.alignment(), text)

# --- 统一的数据结构 ---
@dataclass
class TimestampedWord:
    """表示带时间戳的单个词。"""
    text: str
    start_time: float
    end_time: float
    speaker_id: Optional[str] = None

@dataclass
class ParsedTranscription:
    """表示解析后的ASR转录结果。"""
    words: List[TimestampedWord]
    full_text: Optional[str] = None
    language_code: Optional[str] = None

# --- 字幕条目类 ---
class SubtitleEntry:
    """表示一条SRT字幕。"""
    def __init__(self, index, start_time, end_time, text, words_used: Optional[List[TimestampedWord]] = None, alignment_ratio=1.0):
        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.text = re.sub(r'\s+', ' ', text).strip()
        self.words_used = words_used if words_used else []
        self.alignment_ratio = alignment_ratio
        self.is_intentionally_oversized = False

    @property
    def duration(self):
        if self.start_time is not None and self.end_time is not None: return max(0, self.end_time - self.start_time)
        return 0

    def to_srt_format(self, processor_instance): # processor_instance is SrtProcessor
        if self.start_time is None or self.end_time is None or self.text is None:
            processor_instance.log(f"警告: 字幕条目 {self.index} 缺少时间或文本")
            return ""
        if self.end_time < self.start_time + 0.001: # 确保结束时间至少比开始时间晚1毫秒
            processor_instance.log(f"警告: 字幕条目 {self.index} 结束时间 ({processor_instance.format_timecode(self.end_time)}) 早于或等于开始时间 ({processor_instance.format_timecode(self.start_time)})。已修正为开始时间 +0.1秒。")
            self.end_time = self.start_time + 0.1
        return f"{self.index}\n{processor_instance.format_timecode(self.start_time)} --> {processor_instance.format_timecode(self.end_time)}\n{self.text}\n\n"

# --- ASR JSON 解析器 ---
class TranscriptionParser:
    """解析来自不同ASR服务商的JSON输出。"""
    def __init__(self, signals_forwarder=None):
        self._signals = signals_forwarder

    def log(self, message):
        if self._signals and hasattr(self._signals, 'log_message') and hasattr(self._signals.log_message, 'emit'):
            self._signals.log_message.emit(f"[Parser] {message}")
        else:
            print(f"[Parser] {message}")

    def parse(self, data: dict, source_format: Literal["elevenlabs", "whisper", "deepgram", "assemblyai"]) -> Optional[ParsedTranscription]:
        self.log(f"开始解析 {source_format.capitalize()} JSON...")
        try:
            if source_format == "elevenlabs": result = self._parse_elevenlabs(data)
            elif source_format == "whisper": result = self._parse_whisper(data)
            elif source_format == "deepgram": result = self._parse_deepgram(data)
            elif source_format == "assemblyai": result = self._parse_assemblyai(data)
            else: self.log(f"错误: 不支持的 JSON 格式源 '{source_format}'"); return None

            if result:
                self.log(f"{source_format.capitalize()} JSON 解析完成，得到 {len(result.words)} 个词。总文本长度: {len(result.full_text or '')} 字符。")
            else:
                self.log(f"{source_format.capitalize()} JSON 解析未能返回有效结果。")
            return result
        except Exception as e:
            self.log(f"解析 {source_format.capitalize()} JSON 时出错: {e}"); import traceback; self.log(traceback.format_exc()); return None

    def _parse_elevenlabs(self, data: dict) -> Optional[ParsedTranscription]:
        parsed_words = []
        for word_info in data.get("words", []):
            text = word_info.get("text", word_info.get("word"))
            start = word_info.get("start"); end = word_info.get("end")
            speaker = word_info.get("speaker_id", word_info.get("speaker"))
            if text is not None and start is not None and end is not None:
                try: parsed_words.append(TimestampedWord(str(text), float(start), float(end), str(speaker) if speaker else None))
                except ValueError: self.log(f"警告: 跳过 ElevenLabs 词条，时间戳格式无效: {word_info}")
            else: self.log(f"警告: 跳过不完整的 ElevenLabs 词条: {word_info}")
        full_text = data.get("text", "")
        if not full_text and parsed_words: full_text = " ".join(word.text for word in parsed_words)
        language = data.get("language_code", data.get("language"))
        return ParsedTranscription(words=parsed_words, full_text=full_text, language_code=language)

    def _parse_whisper(self, data: dict) -> Optional[ParsedTranscription]:
        parsed_words = []
        whisper_words_list = []
        if "words" in data and isinstance(data["words"], list): whisper_words_list = data["words"]
        elif "segments" in data and isinstance(data["segments"], list):
            for segment in data.get("segments", []):
                if "words" in segment and isinstance(segment["words"], list): whisper_words_list.extend(segment["words"])
        if not whisper_words_list:
             full_text_only = data.get("text")
             if full_text_only: return ParsedTranscription(words=[], full_text=full_text_only, language_code=data.get("language"))
             self.log("错误: Whisper JSON 既无有效词列表也无顶层文本。"); return None
        for word_info in whisper_words_list:
            text = word_info.get("word", word_info.get("text"))
            start = word_info.get("start"); end = word_info.get("end")
            if text is not None and start is not None and end is not None:
                try: parsed_words.append(TimestampedWord(str(text), float(start), float(end)))
                except ValueError: self.log(f"警告: 跳过 Whisper 词条，时间戳格式无效: {word_info}")
            else: self.log(f"警告: 跳过不完整的 Whisper 词条: {word_info}")
        full_text = data.get("text", "")
        if not full_text and parsed_words: full_text = " ".join(word.text for word in parsed_words)
        language = data.get("language")
        return ParsedTranscription(words=parsed_words, full_text=full_text, language_code=language)

    def _parse_deepgram(self, data: dict) -> Optional[ParsedTranscription]:
        try:
            if not (data.get("results") and data["results"].get("channels") and isinstance(data["results"]["channels"], list) and
                    len(data["results"]["channels"]) > 0 and data["results"]["channels"][0].get("alternatives") and
                    isinstance(data["results"]["channels"][0]["alternatives"], list) and len(data["results"]["channels"][0]["alternatives"]) > 0):
                self.log("错误: Deepgram JSON 结构不符合预期。"); return None
            alternative = data["results"]["channels"][0]["alternatives"][0]
            if "words" not in alternative or not isinstance(alternative["words"], list):
                full_text_only = alternative.get("transcript", "")
                if full_text_only: return ParsedTranscription(words=[], full_text=full_text_only, language_code=data["results"]["channels"][0].get("detected_language"))
                self.log("错误: Deepgram JSON 既无词列表也无 transcript。"); return None
            parsed_words = []
            for word_info in alternative.get("words", []):
                text = word_info.get("word", word_info.get("punctuated_word"))
                start = word_info.get("start"); end = word_info.get("end"); speaker = word_info.get("speaker")
                if text is not None and start is not None and end is not None:
                    try: parsed_words.append(TimestampedWord(str(text), float(start), float(end), str(speaker) if speaker else None))
                    except ValueError: self.log(f"警告: 跳过 Deepgram 词条，时间戳格式无效: {word_info}")
                else: self.log(f"警告: 跳过不完整的 Deepgram 词条: {word_info}")
            full_text = alternative.get("transcript", "")
            if not full_text and parsed_words: full_text = " ".join(word.text for word in parsed_words)
            language = data["results"]["channels"][0].get("detected_language")
            return ParsedTranscription(words=parsed_words, full_text=full_text, language_code=language)
        except (KeyError, IndexError) as e: self.log(f"错误: 解析 Deepgram JSON 时键或索引错误: {e}"); return None

    def _parse_assemblyai(self, data: dict) -> Optional[ParsedTranscription]:
        parsed_words = []
        assemblyai_words_list = []
        if "words" in data and isinstance(data["words"], list): assemblyai_words_list = data["words"]
        elif "utterances" in data and isinstance(data["utterances"], list):
            for utterance in data["utterances"]:
                if "words" in utterance and isinstance(utterance["words"], list): assemblyai_words_list.extend(utterance["words"])
        if not assemblyai_words_list:
            full_text_only = data.get("text")
            if full_text_only: return ParsedTranscription(words=[], full_text=full_text_only, language_code=data.get("language_code"))
            self.log("错误: AssemblyAI JSON 既无有效词列表也无顶层文本。"); return None
        for word_info in assemblyai_words_list:
            text = word_info.get("text"); start_ms = word_info.get("start"); end_ms = word_info.get("end"); speaker = word_info.get("speaker")
            if text is not None and start_ms is not None and end_ms is not None:
                try: parsed_words.append(TimestampedWord(str(text), float(start_ms)/1000.0, float(end_ms)/1000.0, str(speaker) if speaker else None))
                except ValueError: self.log(f"警告: 跳过 AssemblyAI 词条，时间戳或ID格式无效: {word_info}")
            else: self.log(f"警告: 跳过不完整的 AssemblyAI 词条: {word_info}")
        full_text = data.get("text", "")
        if not full_text and parsed_words: full_text = " ".join(word.text for word in parsed_words)
        language = data.get("language_code")
        return ParsedTranscription(words=parsed_words, full_text=full_text, language_code=language)

# --- SRT 生成逻辑 ---
class SrtProcessor:
    """处理转录数据并生成SRT字幕内容。"""
    def __init__(self):
        self._signals = None # Will be set by the worker
    def log(self, message):
        if self._signals and hasattr(self._signals, 'log_message') and hasattr(self._signals.log_message, 'emit'):
            self._signals.log_message.emit(message)
        else: print(f"[SrtProcessor] {message}") # Fallback if signals not set

    def format_timecode(self, seconds_float):
        if not isinstance(seconds_float, (int, float)) or seconds_float < 0: return "00:00:00,000"
        total_seconds_int = int(seconds_float); milliseconds = int(round((seconds_float - total_seconds_int) * 1000))
        if milliseconds >= 1000: # Handle ms rounding up to 1000
            total_seconds_int += 1
            milliseconds = 0
        hours = total_seconds_int // 3600; minutes = (total_seconds_int % 3600) // 60; seconds = total_seconds_int % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def check_word_has_punctuation(self, word_text, punctuation_set):
        cleaned_text = word_text.strip()
        if not cleaned_text: return False
        for punct in punctuation_set:
            if cleaned_text.endswith(punct): return True
        return False

    def get_segment_words_fuzzy(self, text_segment: str, all_parsed_words: List[TimestampedWord], start_search_index: int):
        segment_clean = text_segment.strip().replace(" ", "")
        if not segment_clean: return [], start_search_index, 1.0

        best_match_words_ts_objects: List[TimestampedWord] = []
        best_match_ratio = 0.0
        best_match_end_index = start_search_index

        # Dynamically adjust search window based on segment length
        search_window_size = len(segment_clean) * 3 + 20 # Heuristic for ASR word list window
        max_lookahead = min(start_search_index + search_window_size, len(all_parsed_words))

        for i in range(start_search_index, max_lookahead):
            current_words_text_list = []
            current_word_ts_object_list: List[TimestampedWord] = []
            # Limit how far j looks ahead to build a candidate phrase from ASR words
            max_j_lookahead = min(i + search_window_size // 2 + 10, len(all_parsed_words)) # Heuristic
            for j in range(i, max_j_lookahead):
                word_obj = all_parsed_words[j]
                current_word_ts_object_list.append(word_obj)
                current_words_text_list.append(word_obj.text.replace(" ", "")) # Normalize ASR word
                built_text = "".join(current_words_text_list)
                if not built_text.strip(): continue # Skip if built_text is empty

                matcher = difflib.SequenceMatcher(None, segment_clean, built_text, autojunk=False)
                ratio = matcher.ratio()

                update_best = False
                if ratio > best_match_ratio:
                    update_best = True
                elif ratio == best_match_ratio and best_match_words_ts_objects: # Tie-breaking: prefer shorter ASR match if ratios are equal
                    current_len_diff = abs(len(built_text) - len(segment_clean))
                    best_len_diff = abs(len("".join(w.text.replace(" ","") for w in best_match_words_ts_objects)) - len(segment_clean))
                    if current_len_diff < best_len_diff:
                        update_best = True

                if update_best and ratio > 0: # Only consider if there's some match
                    best_match_ratio = ratio
                    best_match_words_ts_objects = list(current_word_ts_object_list) # Deep copy
                    best_match_end_index = j + 1

                # Early exit if a very good match is found and ASR text is getting too long
                if ratio > 0.95 and len(built_text) > len(segment_clean) * 1.5:
                    break
        if not best_match_words_ts_objects:
            self.log(f"严重警告: LLM片段 \"{text_segment}\" (清理后: \"{segment_clean}\") 无法在ASR词语中找到任何匹配。将跳过此片段。搜索起始索引: {start_search_index}")
            return [], start_search_index, 0.0

        if best_match_ratio < ALIGNMENT_SIMILARITY_THRESHOLD:
            matched_text_preview = "".join([w.text for w in best_match_words_ts_objects])
            self.log(f"警告: LLM片段 \"{text_segment}\" (清理后: \"{segment_clean}\") 与ASR词语的对齐相似度较低 ({best_match_ratio:.2f})。ASR匹配文本: \"{matched_text_preview}\"")

        return best_match_words_ts_objects, best_match_end_index, best_match_ratio

    # --- MODIFIED FUNCTION ---
    def split_long_sentence(self, sentence_text: str, sentence_words: List[TimestampedWord], original_start_time: float, original_end_time: float):
        # self.log(f"尝试分割长句 (策略 C): '{sentence_text}' (词数: {len(sentence_words)}, 时长: {original_end_time - original_start_time:.2f}s)")

        if len(sentence_words) <= 1: # Handles empty or single-word segments
            # self.log(f"  片段只有一个词或为空，不进行分割。")
            entry_to_return = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, sentence_words)
            if entry_to_return.duration < MIN_DURATION_ABSOLUTE:
                entry_to_return.end_time = entry_to_return.start_time + MIN_DURATION_ABSOLUTE
            # Mark as oversized if it still exceeds limits (e.g. very long single word)
            if entry_to_return.duration > MAX_DURATION or len(sentence_text) > MAX_CHARS_PER_LINE:
                 # self.log(f"警告: 单/无词长句仍超限: '{sentence_text}' (时长 {entry_to_return.duration:.2f}s, 字符 {len(sentence_text)})")
                 entry_to_return.is_intentionally_oversized = True
            return [entry_to_return]

        entries = []
        words_to_process = list(sentence_words) # Make a copy to modify

        while words_to_process:
            current_segment_text = "".join([w.text for w in words_to_process])
            if not words_to_process: break # Safety break if list becomes empty unexpectedly
            current_segment_start_time = words_to_process[0].start_time
            current_segment_end_time = words_to_process[-1].end_time
            current_segment_duration = current_segment_end_time - current_segment_start_time
            current_segment_len_chars = len(current_segment_text)

            # If current remaining segment is within limits, add it and finish for this original call
            if current_segment_duration <= MAX_DURATION and current_segment_len_chars <= MAX_CHARS_PER_LINE:
                final_seg_end_time = current_segment_end_time
                # Adjust minimum duration if needed for the last part
                if current_segment_duration < MIN_DURATION_ABSOLUTE:
                    final_seg_end_time = current_segment_start_time + MIN_DURATION_ABSOLUTE
                elif current_segment_duration < MIN_DURATION_TARGET:
                    final_seg_end_time = current_segment_start_time + MIN_DURATION_TARGET
                entries.append(SubtitleEntry(0, current_segment_start_time, final_seg_end_time, current_segment_text, list(words_to_process)))
                # self.log(f"  剩余部分 '{current_segment_text[:30]}...' 已在限制内，添加为最终子片段。")
                break # Break from the while loop

            # --- Find potential and valid split points ---
            potential_split_indices_by_priority = {'final': [], 'ellipsis': [], 'comma': []}
            num_words_in_current_chunk = len(words_to_process)

            for i in range(num_words_in_current_chunk):
                # Potential split point is *after* word at index i.
                # It cannot be the last word of the current chunk for an internal split.
                if i >= num_words_in_current_chunk - 1: continue

                word_obj_in_loop = words_to_process[i]
                word_text_in_loop = word_obj_in_loop.text

                # Your refined rule for FINAL_PUNCTUATION:
                # Only consider it if it's not effectively the end of the *current chunk being processed*.
                # This means there must be substantial content after it.
                # For simplicity, we ensure it's not the second to last word of the *current processing chunk*.
                # This avoids splitting "aaa." from a chunk like "aaa. bbb" into "aaa" and ". bbb" if "bbb" is very short.
                # A more robust check would be "is there a non-punctuation word after this point?".
                # Current check: is there at least one word after the punctuation word.
                # i < num_words_in_current_chunk - 1 is already guaranteed by the loop condition adjustment above.
                # We need to ensure the punctuation is not at the *very end* of the original sentence words
                # if we're trying to find an internal split. The i >= num_words_in_current_chunk -1 handles this for the current chunk.

                if self.check_word_has_punctuation(word_text_in_loop, FINAL_PUNCTUATION):
                    # For FINAL_PUNCTUATION, ensure it's not the *actual end* of the segment if we only have 2 words left like "word1. word2"
                    # The condition i < num_words_in_current_chunk - 1 ensures there's at least one word after index i.
                    potential_split_indices_by_priority['final'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, ELLIPSIS_PUNCTUATION):
                    potential_split_indices_by_priority['ellipsis'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, COMMA_PUNCTUATION):
                    potential_split_indices_by_priority['comma'].append(i)

            chosen_priority_indices = None
            # priority_level_debug = None # For logging
            if potential_split_indices_by_priority['final']:
                chosen_priority_indices = potential_split_indices_by_priority['final']
                # priority_level_debug = 'final'
            elif potential_split_indices_by_priority['ellipsis']:
                chosen_priority_indices = potential_split_indices_by_priority['ellipsis']
                # priority_level_debug = 'ellipsis'
            elif potential_split_indices_by_priority['comma']:
                chosen_priority_indices = potential_split_indices_by_priority['comma']
                # priority_level_debug = 'comma'

            valid_split_points_info = [] # List of tuples: (index, first_segment_char_length)
            if chosen_priority_indices:
                # self.log(f"  找到 {len(chosen_priority_indices)} 个潜在分割点 (优先级: {priority_level_debug})。检查有效性 (第一部分时长 >= {MIN_DURATION_TARGET}s)...")
                for idx in chosen_priority_indices:
                    first_segment_words = words_to_process[:idx + 1]
                    if not first_segment_words: continue

                    first_segment_start_time = first_segment_words[0].start_time
                    first_segment_end_time = first_segment_words[-1].end_time
                    first_segment_duration = first_segment_end_time - first_segment_start_time

                    if first_segment_duration >= MIN_DURATION_TARGET:
                        first_segment_char_len = len("".join(w.text for w in first_segment_words))
                        valid_split_points_info.append((idx, first_segment_char_len))
                        # self.log(f"    索引 {idx} 有效 (时长 {first_segment_duration:.2f}s, 长度 {first_segment_char_len})")
                    # else:
                        # self.log(f"    索引 {idx} 无效 (时长 {first_segment_duration:.2f}s < {MIN_DURATION_TARGET}s)")

            best_split_index = -1
            if valid_split_points_info:
                # self.log(f"  找到 {len(valid_split_points_info)} 个有效分割点。选择字符长度最接近原长一半的点...")
                target_char_len_half = current_segment_len_chars / 2.0
                
                best_split_point_data = min(valid_split_points_info, key=lambda p_info: abs(p_info[1] - target_char_len_half))
                best_split_index = best_split_point_data[0]
                # self.log(f"  选择索引 {best_split_index} (第一部分长 {best_split_point_data[1]}, 目标半长 {target_char_len_half:.1f}) 作为最佳分割点。")


            # --- Handle splitting or fallback ---
            if best_split_index != -1: # A valid and best split point was found
                words_for_this_sub_entry = words_to_process[:best_split_index + 1]
                words_to_process = words_to_process[best_split_index + 1:] # Update remaining words for next iteration

                if not words_for_this_sub_entry: continue # Should not happen if best_split_index is valid

                sub_text = "".join([w.text for w in words_for_this_sub_entry])
                sub_start_time = words_for_this_sub_entry[0].start_time
                sub_end_time = words_for_this_sub_entry[-1].end_time
                # Duration for this sub_entry already meets MIN_DURATION_TARGET.
                # Further adjustments for MIN_DURATION_ABSOLUTE or MAX_DURATION will be handled in the main processing loop
                # or the final formatting pass for consistency.
                
                entries.append(SubtitleEntry(0, sub_start_time, sub_end_time, sub_text, words_used=words_for_this_sub_entry))
                # self.log(f"  分割出子片段: '{sub_text[:50]}...'")
            else:
                # Fallback: No valid split points found (or no punctuation at all in the current chunk)
                if chosen_priority_indices: # Potential points existed but none were valid
                     self.log(f"警告: 片段 '{current_segment_text[:30]}...' 找到潜在分割点，但所有分割都会导致第一部分时长 < {MIN_DURATION_TARGET}s。")
                # else: # No punctuation was found in the current chunk (excluding ends)
                     # self.log(f"警告: 片段 '{current_segment_text[:30]}...' 无内部优先标点可供分割。")

                self.log(f"  将剩余部分 '{current_segment_text[:50]}...' 标记为 '故意超限' 并添加。")
                final_seg_end_time = current_segment_end_time
                # Apply absolute minimum duration if needed for the *whole* unsplit segment
                if current_segment_duration < MIN_DURATION_ABSOLUTE:
                    final_seg_end_time = current_segment_start_time + MIN_DURATION_ABSOLUTE

                entry = SubtitleEntry(0, current_segment_start_time, final_seg_end_time, current_segment_text, list(words_to_process))
                entry.is_intentionally_oversized = True # Mark it
                # Log if it's *still* oversized after potential MIN_DURATION_ABSOLUTE adjustment
                if entry.duration > MAX_DURATION or len(entry.text) > MAX_CHARS_PER_LINE:
                    self.log(f"  (确认仍超限) 时长 {entry.duration:.2f}s, 字符 {len(entry.text)}")
                entries.append(entry)
                break # Exit while loop, as we cannot split this current_segment_text further meaningfully

            if not words_to_process: break # Exit if no more words left

        return entries
    # --- END OF MODIFIED FUNCTION ---

    def process_to_srt(self, parsed_transcription: ParsedTranscription, llm_segments_text: List[str], signals_forwarder):
        self._signals = signals_forwarder
        self.log("--- 开始对齐 LLM 片段 ---")
        intermediate_entries: List[SubtitleEntry] = []
        word_search_start_index = 0
        unaligned_segments = []

        all_parsed_words = parsed_transcription.words
        if not llm_segments_text: self.log("错误：LLM 未返回任何分割片段。"); return None
        if not all_parsed_words: self.log("错误：解析后的词列表为空，无法进行对齐。"); return None

        self.log(f"ASR共有 {len(all_parsed_words)} 个带时间戳的词。LLM返回 {len(llm_segments_text)} 个待对齐片段。")

        total_segments_to_align = len(llm_segments_text)
        for i, text_seg in enumerate(llm_segments_text):
            if not self._signals.is_running: self.log("任务被用户中断(对齐阶段)。"); return None
            self._signals.progress.emit(int(10 + 30 * ((i + 1) / total_segments_to_align))) # Progress: 10% to 40%

            matched_words, next_search_idx, match_ratio = self.get_segment_words_fuzzy(text_seg, all_parsed_words, word_search_start_index)

            if not matched_words or match_ratio == 0: # match_ratio == 0 implies total failure from get_segment_words_fuzzy
                unaligned_segments.append(text_seg)
                continue

            word_search_start_index = next_search_idx # Update for next iteration

            entry_text = "".join([w.text for w in matched_words])
            entry_start_time = matched_words[0].start_time
            entry_end_time = matched_words[-1].end_time
            entry_duration = entry_end_time - entry_start_time
            text_len = len(entry_text) # Use combined text from matched ASR words

            is_audio_event = all(not w.text.strip() or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in matched_words)

            if is_audio_event:
                final_audio_event_end_time = entry_end_time
                if entry_duration < MIN_DURATION_ABSOLUTE: final_audio_event_end_time = entry_start_time + MIN_DURATION_ABSOLUTE
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_audio_event_end_time, entry_text, matched_words, match_ratio))
            elif entry_duration > MAX_DURATION or text_len > MAX_CHARS_PER_LINE:
                self.log(f"片段超限，需分割: \"{entry_text}\" (时长: {entry_duration:.2f}s, 字符: {text_len})")
                split_sub_entries = self.split_long_sentence(entry_text, matched_words, entry_start_time, entry_end_time)
                for sub_entry in split_sub_entries: sub_entry.alignment_ratio = match_ratio # Preserve original alignment quality
                intermediate_entries.extend(split_sub_entries)
            elif entry_duration < MIN_DURATION_TARGET : # Too short, needs extension
                final_short_entry_end_time = entry_start_time + (MIN_DURATION_ABSOLUTE if entry_duration < MIN_DURATION_ABSOLUTE else MIN_DURATION_TARGET)
                max_allowed_extension = matched_words[-1].end_time + 0.5 # Extend by at most 0.5s past original word end
                final_short_entry_end_time = min(final_short_entry_end_time, max_allowed_extension)
                if final_short_entry_end_time <= entry_start_time: final_short_entry_end_time = entry_start_time + 0.1 # Safety
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_short_entry_end_time, entry_text, matched_words, match_ratio))
            else: # Duration and length are fine
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, entry_end_time, entry_text, matched_words, match_ratio))

        self.log("--- LLM片段对齐结束 ---")
        if unaligned_segments:
            self.log(f"\n--- 以下 {len(unaligned_segments)} 个LLM片段未能成功对齐，已跳过 ---")
            for seg_idx, seg_text in enumerate(unaligned_segments):
                self.log(f"- 片段 {seg_idx+1}: \"{seg_text}\"")
            self.log("----------------------------------------\n")

        if not intermediate_entries: self.log("错误：对齐后没有生成任何有效的字幕条目。"); return None

        self.log(f"--- 对齐后得到 {len(intermediate_entries)} 个初步字幕条目，开始合并和调整 ---")
        intermediate_entries.sort(key=lambda e: e.start_time) # Ensure order before merging

        merged_entries: List[SubtitleEntry] = []
        i = 0
        total_intermediate_entries = len(intermediate_entries)
        while i < total_intermediate_entries:
            if not self._signals.is_running: self.log("任务被用户中断(合并阶段)。"); return None
            self._signals.progress.emit(int(40 + 50 * ((i + 1) / total_intermediate_entries if total_intermediate_entries > 0 else 1))) # Progress: 40% to 90%

            current_entry_to_merge = intermediate_entries[i]
            merged = False

            if i + 1 < len(intermediate_entries):
                next_entry = intermediate_entries[i+1]
                gap_between = next_entry.start_time - current_entry_to_merge.end_time
                combined_text_len = len(current_entry_to_merge.text) + len(next_entry.text) + 1 # +1 for space
                combined_duration = next_entry.end_time - current_entry_to_merge.start_time

                next_is_audio_event = any(not w.text.strip() or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in next_entry.words_used)

                if current_entry_to_merge.duration < MIN_DURATION_TARGET and \
                   not next_is_audio_event and \
                   combined_text_len <= MAX_CHARS_PER_LINE and \
                   combined_duration <= MAX_DURATION and \
                   gap_between < 0.5 and \
                   combined_duration >= MIN_DURATION_TARGET :

                    merged_text = current_entry_to_merge.text + " " + next_entry.text
                    merged_start_time = current_entry_to_merge.start_time
                    merged_end_time = next_entry.end_time
                    merged_words = current_entry_to_merge.words_used + next_entry.words_used
                    merged_ratio = min(current_entry_to_merge.alignment_ratio, next_entry.alignment_ratio) # Take the worse ratio

                    merged_entries.append(SubtitleEntry(0, merged_start_time, merged_end_time, merged_text, merged_words, merged_ratio))
                    i += 2 # Skip next entry as it's merged
                    merged = True

            if not merged:
                merged_entries.append(current_entry_to_merge)
                i += 1
        self.log(f"--- 合并调整后得到 {len(merged_entries)} 个字幕条目，开始最终格式化 ---")

        final_srt_formatted_list: List[str] = []
        last_processed_entry_object: Optional[SubtitleEntry] = None
        subtitle_index = 1

        for entry_idx, current_entry in enumerate(merged_entries):
            if not self._signals.is_running: self.log("任务被用户中断(最终格式化阶段)。"); return None
            self._signals.progress.emit(int(90 + 9 * ((entry_idx + 1) / len(merged_entries) if len(merged_entries) > 0 else 1) ))

            if last_processed_entry_object is not None:
                gap_seconds = DEFAULT_GAP_MS / 1000.0
                if current_entry.start_time < last_processed_entry_object.end_time + gap_seconds:
                    new_previous_end_time = current_entry.start_time - gap_seconds
                    min_duration_for_previous = 0.010

                    if new_previous_end_time > last_processed_entry_object.start_time + min_duration_for_previous:
                        last_processed_entry_object.end_time = new_previous_end_time
                    else:
                        safe_previous_end_time = current_entry.start_time - 0.001 # Minimal gap
                        if safe_previous_end_time > last_processed_entry_object.start_time + min_duration_for_previous:
                            last_processed_entry_object.end_time = safe_previous_end_time

                    if final_srt_formatted_list:
                        final_srt_formatted_list[-1] = last_processed_entry_object.to_srt_format(self)

            current_duration = current_entry.duration
            min_duration_to_apply = None
            entry_is_audio_event = any(not w.text.strip() or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in current_entry.words_used)

            if not current_entry.is_intentionally_oversized and not entry_is_audio_event:
                if current_duration < MIN_DURATION_ABSOLUTE: min_duration_to_apply = MIN_DURATION_ABSOLUTE
                elif current_duration < MIN_DURATION_TARGET: min_duration_to_apply = MIN_DURATION_TARGET

            if min_duration_to_apply is not None:
                current_entry.end_time = max(current_entry.end_time, current_entry.start_time + min_duration_to_apply)

            if not current_entry.is_intentionally_oversized and current_entry.duration > MAX_DURATION:
                self.log(f"字幕 \"{current_entry.text[:30]}...\" 时长 {current_entry.duration:.2f}s 超出最大值 {MAX_DURATION}s，将被截断。")
                current_entry.end_time = current_entry.start_time + MAX_DURATION
            
            if current_entry.end_time <= current_entry.start_time: # Safety check
                 current_entry.end_time = current_entry.start_time + 0.001

            current_entry.index = subtitle_index
            final_srt_formatted_list.append(current_entry.to_srt_format(self))
            last_processed_entry_object = current_entry
            subtitle_index += 1

        self.log("--- SRT 内容生成和格式化完成 ---")
        return "".join(final_srt_formatted_list).strip()

# --- 工作线程类 ---
class ConversionWorker(QObject):
    """执行转换任务的后台线程。"""
    def __init__(self, api_key, json_path, output_dir, srt_processor, source_format: str, parent=None):
        super().__init__(parent)
        self.signals = WorkerSignals(parent=self); self.api_key = api_key; self.json_path = json_path
        self.output_dir = output_dir; self.srt_processor = srt_processor; self.source_format = source_format
        self.transcription_parser = TranscriptionParser(signals_forwarder=self.signals); self.is_running = True

    def stop(self):
        self.is_running = False
        if self.signals: self.signals.log_message.emit("接收到停止信号...")

    def call_deepseek_api(self, text_to_segment):
        if not self.is_running: self.signals.log_message.emit("API调用前任务已取消。"); return None
        payload = { "model": DEEPSEEK_MODEL, "messages": [{"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},{"role": "user", "content": text_to_segment}], "stream": False }
        headers = { "Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}" }
        self.signals.log_message.emit(f"向 DeepSeek API 发送文本进行分割 (模型: {DEEPSEEK_MODEL}, 文本长度: {len(text_to_segment)} chars)...")
        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=180) # 3 min timeout
            response.raise_for_status()
            data = response.json()
            if not self.is_running: self.signals.log_message.emit("API响应后任务已取消。"); return None

            if "choices" in data and data["choices"]:
                content = data["choices"][0].get("message", {}).get("content")
                if content:
                    segments = [seg.strip() for seg in content.split('\n') if seg.strip()]
                    self.signals.log_message.emit(f"DeepSeek API 成功返回 {len(segments)} 个文本片段。")
                    return segments
                else:
                    self.signals.log_message.emit("错误: DeepSeek API 响应中 'content' 为空。")
                    raise ValueError("DeepSeek API 响应 'content' 为空。")
            else:
                error_msg = f"DeepSeek API 响应格式错误: {data.get('error', {}).get('message', str(data))}"
                self.signals.log_message.emit(f"错误: {error_msg}")
                raise RuntimeError(error_msg)
        except requests.exceptions.Timeout:
            self.signals.log_message.emit("错误: DeepSeek API 请求超时 (180秒)。")
            if not self.is_running: return None
            raise TimeoutError("DeepSeek API 请求超时 (180秒)。")
        except requests.exceptions.RequestException as e:
            error_details = ""; status_code = 'N/A'
            if e.response is not None:
                 status_code = e.response.status_code
                 try: error_details = f": {e.response.json().get('error', {}).get('message', '')}"
                 except: error_details = f": {e.response.text}" # type: ignore
            self.signals.log_message.emit(f"错误: DeepSeek API 请求失败 (状态码: {status_code}){error_details}")
            if not self.is_running: return None
            raise ConnectionError(f"DeepSeek API 请求失败 ({status_code}){error_details}")
        except Exception as e:
            self.signals.log_message.emit(f"错误: 处理 DeepSeek API 响应时发生未知错误: {e}")
            if not self.is_running: return None
            raise RuntimeError(f"处理 DeepSeek API 响应时发生未知错误: {e}")

    def run(self):
        try:
            if not self.is_running: self.signals.finished.emit("任务开始前被取消。", False); return
            self.signals.progress.emit(5); self.signals.log_message.emit(f"开始转换任务: JSON文件 '{os.path.basename(self.json_path)}', 格式 '{self.source_format}'")

            with open(self.json_path, "r", encoding="utf-8") as f: raw_api_data = json.load(f)
            parsed_transcription_data = self.transcription_parser.parse(raw_api_data, self.source_format)

            if parsed_transcription_data is None:
                self.signals.log_message.emit(f"JSON文件 '{os.path.basename(self.json_path)}' 解析失败 ({self.source_format} 格式)。")
                self.signals.finished.emit(f"JSON 解析失败 ({self.source_format} 格式)。", False); return

            text_to_segment = parsed_transcription_data.full_text
            if not text_to_segment:
                if parsed_transcription_data.words:
                    self.signals.log_message.emit("JSON中无完整文本，将从词语列表中拼接。")
                    text_to_segment = " ".join([word.text for word in parsed_transcription_data.words])
                if not text_to_segment: # Still no text
                    self.signals.log_message.emit("错误: 无法从JSON中获取用于LLM分割的文本。")
                    self.signals.finished.emit("无法获取LLM分割用文本。", False); return
            self.signals.log_message.emit(f"获取到待分割文本，长度: {len(text_to_segment)} 字符。")

            if not self.is_running: self.signals.finished.emit("任务在读取/解析JSON后被取消。", False); return
            self.signals.progress.emit(10) # End of JSON parsing part

            llm_segments = self.call_deepseek_api(text_to_segment)
            if llm_segments is None: # call_deepseek_api already logs errors
                self.signals.finished.emit("DeepSeek API 调用失败或返回空。" if self.is_running else "任务在API调用期间被取消。", False); return

            if not self.is_running: self.signals.finished.emit("任务在API调用成功后被取消。", False); return
            self.signals.progress.emit(40) # After API call, before SRT processing
            self.signals.log_message.emit("开始使用LLM返回的片段生成 SRT 内容...")

            # Pass signals and running state to SrtProcessor via a simple forwarder
            class TempSignalsForwarder:
                def __init__(self, worker_signals_obj, worker_instance_ref):
                    self.worker_signals = worker_signals_obj
                    self.worker_instance = worker_instance_ref
                @property
                def is_running(self): return self.worker_instance.is_running
                @property
                def progress(self): return self.worker_signals.progress
                @property
                def log_message(self): return self.worker_signals.log_message

            forwarder = TempSignalsForwarder(self.signals, self)
            self.srt_processor._signals = forwarder # Directly set the forwarder to SrtProcessor instance

            final_srt = self.srt_processor.process_to_srt(parsed_transcription_data, llm_segments, forwarder)

            if final_srt is None: # process_to_srt should log specific reasons for failure
                self.signals.log_message.emit("SRT 内容生成失败。")
                self.signals.finished.emit("SRT 内容生成失败。" if self.is_running else "任务在SRT生成期间被取消。", False); return

            if not self.is_running: self.signals.finished.emit("任务在SRT生成成功后立即被取消。", False); return
            self.signals.progress.emit(99) # Almost done

            base_name = os.path.splitext(os.path.basename(self.json_path))[0]
            output_srt_filepath = os.path.join(self.output_dir, f"{base_name}.srt")
            with open(output_srt_filepath, "w", encoding="utf-8") as f: f.write(final_srt)
            self.signals.log_message.emit(f"SRT 文件已成功保存到: {output_srt_filepath}")

            if not self.is_running: self.signals.finished.emit(f"文件已保存到 {output_srt_filepath}，但任务随后被标记为取消。", False); return # Should be rare

            self.signals.progress.emit(100)
            self.signals.finished.emit(f"转换完成！SRT 文件已保存到:\n{output_srt_filepath}", True)
        except Exception as e:
            import traceback; error_trace = traceback.format_exc()
            self.signals.log_message.emit(f"处理过程中发生严重错误: {e}\n详细追溯:\n{error_trace}")
            self.signals.finished.emit(f"处理失败: {e}" if self.is_running else f"任务因用户取消而停止，过程中出现异常: {e}", False)
        finally:
            self.is_running = False # Ensure worker stops

# --- GUI 主应用类 ---
class HealJimakuApp(QMainWindow):
    """应用程序的主窗口和UI逻辑。"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heal-Jimaku (治幕)"); self.resize(1024, 864)
        self.srt_processor = SrtProcessor(); self.config = {}; self.conversion_thread = None
        self.worker = None; self.app_icon = None; self.background = None
        self.is_dragging = False; self.drag_pos = QPoint()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.log_area_early_messages = []

        icon_path = resource_path("icon.ico")
        if icon_path and os.path.exists(icon_path): self.app_icon = QIcon(icon_path)
        else:
            self._early_log("警告: 应用图标 icon.ico 未找到。")
            self.app_icon = QIcon()
        self.setWindowIcon(self.app_icon)

        bg_path = resource_path("background.png")
        if bg_path and os.path.exists(bg_path): self.background = QPixmap(bg_path)
        else: self._early_log("警告: 背景图片 background.png 未找到。")

        if self.background is None or self.background.isNull(): self._create_fallback_background()
        else: self.background = self.background.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)

        self.main_widget = QWidget(self); self.setCentralWidget(self.main_widget)
        self.main_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.init_ui()
        self._process_early_logs()
        self.load_config()
        self.center_window()
        QTimer.singleShot(100, self.apply_taskbar_icon)

    def _early_log(self, message):
        if hasattr(self, 'log_area') and self.log_area:
            self.log_message(message)
        else:
            self.log_area_early_messages.append(message)
            print(f"[Log Early]: {message}")

    def _process_early_logs(self):
        if hasattr(self, 'log_area') and self.log_area:
            for msg in self.log_area_early_messages:
                self.log_area.append(msg)
            self.log_area_early_messages = []

    def _create_fallback_background(self):
        self.background = QPixmap(self.size()); self.background.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self.background); gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(40, 40, 80, 200)); gradient.setColorAt(1, QColor(20, 20, 40, 220))
        painter.fillRect(self.rect(), gradient); painter.end()

    def apply_taskbar_icon(self):
        if hasattr(self, 'windowHandle') and self.windowHandle() is not None:
            if self.app_icon and not self.app_icon.isNull(): self.windowHandle().setIcon(self.app_icon)
        elif self.app_icon and not self.app_icon.isNull(): self.setWindowIcon(self.app_icon)

    def center_window(self):
        try:
            screen_geometry = self.screen().geometry() if self.screen() else QApplication.primaryScreen().geometry()
            self.move((screen_geometry.width() - self.width()) // 2, (screen_geometry.height() - self.height()) // 2)
        except Exception:
            if QApplication.primaryScreen():
                 screen_geometry = QApplication.primaryScreen().geometry()
                 self.move((screen_geometry.width() - self.width()) // 2, (screen_geometry.height() - self.height()) // 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.background and not self.background.isNull(): painter.drawPixmap(self.rect(), self.background)
        else: painter.fillRect(self.rect(), QColor(30, 30, 50, 230))
        super().paintEvent(event)

    def resizeEvent(self, event):
        bg_path = resource_path("background.png")
        if bg_path and os.path.exists(bg_path):
            new_pixmap = QPixmap(bg_path)
            if not new_pixmap.isNull(): self.background = new_pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            else: self._create_fallback_background()
        else: self._create_fallback_background()
        super().resizeEvent(event); self.update()

    def init_ui(self):
        main_layout = QVBoxLayout(self.main_widget); main_layout.setContentsMargins(30,30,30,30); main_layout.setSpacing(20)
        QApplication.setFont(QFont('楷体', 12))

        title_bar_layout = QHBoxLayout()
        title = CustomLabel_title("Heal-Jimaku (治幕)"); title_font = QFont('楷体', 24); title_font.setBold(True); title.setFont(title_font); title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_btn_layout = QHBoxLayout(); control_btn_layout.setSpacing(10)
        min_btn = QPushButton("─"); min_btn.setFixedSize(30,30); min_btn.setObjectName("minButton"); min_btn.clicked.connect(self.showMinimized)
        close_btn = QPushButton("×"); close_btn.setFixedSize(30,30); close_btn.setObjectName("closeButton"); close_btn.clicked.connect(self.close_application)
        control_btn_layout.addWidget(min_btn); control_btn_layout.addWidget(close_btn)
        title_bar_layout.addStretch(1); title_bar_layout.addWidget(title,2,Qt.AlignmentFlag.AlignCenter); title_bar_layout.addStretch(1); title_bar_layout.addLayout(control_btn_layout)
        main_layout.addLayout(title_bar_layout); main_layout.addSpacing(20)

        content_widget = TransparentWidget(bg_color=QColor(191,191,191,50))
        content_layout = QVBoxLayout(content_widget); content_layout.setContentsMargins(25,25,25,25); content_layout.setSpacing(15)

        api_group = QGroupBox("DeepSeek API 设置"); api_group.setObjectName("apiGroup")
        api_layout = QVBoxLayout(api_group); api_layout.setSpacing(12)
        api_key_layout = QHBoxLayout(); api_label = CustomLabel("API Key:"); api_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.api_key_entry = QLineEdit(); self.api_key_entry.setPlaceholderText("sk-..."); self.api_key_entry.setEchoMode(QLineEdit.EchoMode.Password); self.api_key_entry.setObjectName("apiKeyEdit")
        self.remember_api_key_checkbox = QCheckBox("记住 API Key"); self.remember_api_key_checkbox.setChecked(True); self.remember_api_key_checkbox.setObjectName("rememberCheckbox")
        api_key_layout.addWidget(api_label); api_key_layout.addWidget(self.api_key_entry)
        api_layout.addLayout(api_key_layout); api_layout.addWidget(self.remember_api_key_checkbox, alignment=Qt.AlignmentFlag.AlignLeft)

        file_group = QGroupBox("文件选择"); file_group.setObjectName("fileGroup")
        file_layout = QVBoxLayout(file_group); file_layout.setSpacing(12)
        json_layout = QHBoxLayout(); json_label = CustomLabel("JSON 文件:"); json_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.json_path_entry = QLineEdit(); self.json_path_entry.setPlaceholderText("选择包含ASR结果的 JSON 文件"); self.json_path_entry.setObjectName("pathEdit")
        self.json_browse_button = QPushButton("浏览..."); self.json_browse_button.setObjectName("browseButton"); self.json_browse_button.clicked.connect(self.browse_json_file)
        json_layout.addWidget(json_label,1); json_layout.addWidget(self.json_path_entry,4); json_layout.addWidget(self.json_browse_button,1)
        file_layout.addLayout(json_layout)

        format_layout = QHBoxLayout(); format_label = CustomLabel("JSON 格式:"); format_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.json_format_combo = QComboBox(); self.json_format_combo.addItems(["ElevenLabs(推荐)", "Whisper(推荐)", "Deepgram", "AssemblyAI"]); self.json_format_combo.setObjectName("formatCombo")
        format_layout.addWidget(format_label,1); format_layout.addWidget(self.json_format_combo,5)
        file_layout.addLayout(format_layout)

        export_group = QGroupBox("导出与控制"); export_group.setObjectName("exportGroup")
        export_layout = QVBoxLayout(export_group); export_layout.setSpacing(12)
        output_layout = QHBoxLayout(); output_label = CustomLabel("导出目录:"); output_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.output_path_entry = QLineEdit(); self.output_path_entry.setPlaceholderText("选择 SRT 文件保存目录"); self.output_path_entry.setObjectName("pathEdit")
        self.output_browse_button = QPushButton("浏览..."); self.output_browse_button.setObjectName("browseButton"); self.output_browse_button.clicked.connect(self.select_output_dir)
        output_layout.addWidget(output_label,1); output_layout.addWidget(self.output_path_entry,4); output_layout.addWidget(self.output_browse_button,1)
        export_layout.addLayout(output_layout)
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0); self.progress_bar.setTextVisible(True); self.progress_bar.setFormat("%p%"); self.progress_bar.setObjectName("progressBar")
        export_layout.addWidget(self.progress_bar)
        self.start_button = QPushButton("开始转换"); self.start_button.setFixedHeight(45); self.start_button.setFont(QFont('楷体', 14, QFont.Weight.Bold)); self.start_button.setObjectName("startButton"); self.start_button.clicked.connect(self.start_conversion)
        export_layout.addWidget(self.start_button);

        log_group = QGroupBox("日志"); log_group.setObjectName("logGroup")
        log_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit(); self.log_area.setReadOnly(True); self.log_area.setObjectName("logArea")
        log_layout.addWidget(self.log_area);

        content_layout.addWidget(api_group,22); content_layout.addWidget(file_group,23)
        content_layout.addWidget(export_group,20); content_layout.addWidget(log_group,35)
        main_layout.addWidget(content_widget,1)
        self.apply_styles()

    def apply_styles(self):
        group_title_red = "#B34A4A"; input_text_red = "#7a1723"; soft_orangebrown_text = "#CB7E47"
        button_blue_bg = "rgba(100, 149, 237, 190)"; button_blue_hover = "rgba(120, 169, 247, 210)"
        control_min_blue = "rgba(135, 206, 235, 180)"; control_min_hover = "rgba(135, 206, 235, 220)"
        control_close_red = "rgba(255, 99, 71, 180)"; control_close_hover = "rgba(255, 99, 71, 220)"
        group_bg = "rgba(52, 129, 184, 30)"
        input_bg = "rgba(255, 255, 255, 30)"; input_hover_bg = "rgba(255, 255, 255, 40)"
        input_focus_bg = "rgba(255, 255, 255, 50)"; input_border_color = "rgba(135, 206, 235, 90)"
        input_focus_border_color = "#87CEEB"
        log_bg = "rgba(0, 0, 0, 55)"; log_text_custom_color = "#F0783C"
        combo_dropdown_bg = "rgba(250, 250, 250, 235)"; combo_dropdown_text_color = "#2c3e50"
        combo_dropdown_border_color = "rgba(135, 206, 235, 150)"
        combo_dropdown_selection_bg = button_blue_hover; combo_dropdown_selection_text_color = "#FFFFFF"
        combo_dropdown_hover_bg = "rgba(173, 216, 230, 150)"

        qss_image_url = ""
        raw_arrow_path = resource_path('dropdown_arrow.png')

        if raw_arrow_path and os.path.exists(raw_arrow_path):
            abs_arrow_path = os.path.abspath(raw_arrow_path)
            formatted_path = abs_arrow_path.replace(os.sep, '/')
            qss_image_url = f"url('{formatted_path}')"
        else:
            self.log_message(f"警告: 下拉箭头图标 'dropdown_arrow.png' 未找到。将使用默认或无图标。") # Restored log
            pass

        style = f"""
            QGroupBox {{ font: bold 17pt '楷体'; border: 1px solid rgba(135,206,235,80); border-radius:8px; margin-top:12px; background-color:{group_bg}; }}
            QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top left; left:15px; padding:2px 5px; color:{group_title_red}; font:bold 15pt '楷体'; }}
            QLineEdit#apiKeyEdit, QLineEdit#pathEdit {{ background-color:{input_bg}; color:{input_text_red}; border:1px solid {input_border_color}; border-radius:5px; padding:6px; font:bold 11pt 'Microsoft YaHei'; min-height:1.8em; }}
            QLineEdit#apiKeyEdit:hover, QLineEdit#pathEdit:hover {{ background-color:{input_hover_bg}; border:1px solid {input_focus_border_color}; }}
            QLineEdit#apiKeyEdit:focus, QLineEdit#pathEdit:focus {{ background-color:{input_focus_bg}; border:1px solid {input_focus_border_color}; }}
            QLineEdit#apiKeyEdit {{ font-family:'Consolas','Courier New',monospace; font-size:12pt; font-weight:bold; }}
            QCheckBox#rememberCheckbox {{ color:{soft_orangebrown_text}; font:bold 10pt 'Microsoft YaHei'; spacing:5px; background-color:transparent; }}
            QCheckBox#rememberCheckbox::indicator {{ width:18px; height:18px; border:1px solid {input_focus_border_color}; border-radius:3px; background-color:rgba(255,255,255,30); }}
            QCheckBox#rememberCheckbox::indicator:checked {{ background-color:rgba(105,207,247,150); image:none; }}
            QPushButton#browseButton, QPushButton#startButton {{ background-color:{button_blue_bg}; color:white; border:none; border-radius:5px; font-family:'Microsoft YaHei'; font-weight:bold; }}
            QPushButton#browseButton {{ padding:6px 15px; font-size:10pt; }}
            QPushButton#startButton {{ padding:8px 25px; font:bold 14pt '楷体'; }}
            QPushButton#browseButton:hover, QPushButton#startButton:hover {{ background-color:{button_blue_hover}; }}
            QPushButton#startButton:disabled {{ background-color:rgba(100,100,100,150); color:#bbbbbb; }}
            #minButton {{ background-color:{control_min_blue}; color:white; border:none; border-radius:15px; font-weight:bold; font-size:14pt; }}
            #minButton:hover {{ background-color:{control_min_hover}; }}
            #closeButton {{ background-color:{control_close_red}; color:white; border:none; border-radius:15px; font-weight:bold; font-size:14pt; }}
            #closeButton:hover {{ background-color:{control_close_hover}; }}
            QProgressBar#progressBar {{ border:1px solid rgba(135,206,235,80); border-radius:5px; text-align:center; background:rgba(0,0,0,40); height:22px; color:#f0f0f0; font-weight:bold; }}
            QProgressBar#progressBar::chunk {{ background-color:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5C8A6F,stop:1 #69CFF7); border-radius:5px; }}
            QTextEdit#logArea {{ background-color:{log_bg}; border:1px solid rgba(135,206,235,80); border-radius:5px; color:{log_text_custom_color}; font-family:'SimSun'; font-size:10pt; font-weight:bold;}}

            QComboBox#formatCombo {{
                background-color:{input_bg}; color:{input_text_red};
                border:1px solid {input_border_color}; border-radius:5px;
                padding: 2.5px 8px 2.5px 8px;
                font:bold 11pt 'Microsoft YaHei'; min-height:0.8em;
            }}
            QComboBox#formatCombo:hover {{ background-color:{input_hover_bg}; border-color:{input_focus_border_color}; }}
            QComboBox#formatCombo:focus {{ background-color:{input_focus_bg}; border-color:{input_focus_border_color}; }}
            QComboBox#formatCombo:on {{ background-color:{input_focus_bg}; border-color:{input_focus_border_color}; padding-right: 8px; }}

            QComboBox#formatCombo::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border: none;
            }}
            QComboBox#formatCombo::down-arrow {{
                image: {qss_image_url if qss_image_url else "none"};
                width: 8px;
                height: 8px;
            }}
            QComboBox#formatCombo::down-arrow:on {{
                /* top: 1px; */
            }}

            QComboBox QAbstractItemView {{ background-color:{combo_dropdown_bg}; color:{combo_dropdown_text_color}; border:1px solid {combo_dropdown_border_color}; border-radius:5px; padding:4px; outline:0px; }}
            QComboBox QAbstractItemView::item {{ padding:6px 10px; min-height:1.7em; border-radius:3px; background-color:transparent; }}
            QComboBox QAbstractItemView::item:selected {{ background-color:{combo_dropdown_selection_bg}; color:{combo_dropdown_selection_text_color}; }}
            QComboBox QAbstractItemView::item:hover {{ background-color:{combo_dropdown_hover_bg}; color:{combo_dropdown_text_color}; }}

            CustomLabel, CustomLabel_title {{ background-color:transparent; }}
            QLabel {{ background-color:transparent; }}
        """
        self.setStyleSheet(style)

    def log_message(self, message):
        if hasattr(self, 'log_area') and self.log_area and self.log_area.isVisible():
            self.log_area.append(message)
            self.log_area.moveCursor(QTextCursor.MoveOperation.End)
        else:
            if hasattr(self, 'log_area_early_messages'):
                self.log_area_early_messages.append(message)
            print(f"[Log]: {message}")


    def load_config(self):
        if not os.path.exists(CONFIG_DIR):
            try: os.makedirs(CONFIG_DIR)
            except OSError: self._early_log("创建配置目录失败。"); return
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f: self.config = json.load(f)
            else: self.config = {} # Start with empty config if file doesn't exist

            api_key = self.config.get('deepseek_api_key', '')
            remember = self.config.get('remember_api_key', True)
            last_json_path = self.config.get('last_json_path', '')
            last_output_path = self.config.get('last_output_path', '')
            last_source_format = self.config.get('last_source_format', 'ElevenLabs(推荐)') # Default to string for consistency

            format_index = self.json_format_combo.findText(last_source_format)
            if format_index != -1:
                self.json_format_combo.setCurrentIndex(format_index)
            else: # Fallback if saved format string is not in current items
                self.json_format_combo.setCurrentIndex(0)


            if api_key and remember:
                self.api_key_entry.setText(api_key)
                self.remember_api_key_checkbox.setChecked(True)
            else:
                self.api_key_entry.clear()
                self.remember_api_key_checkbox.setChecked(False)

            if os.path.isfile(last_json_path): self.json_path_entry.setText(last_json_path)

            if os.path.isdir(last_output_path): self.output_path_entry.setText(last_output_path)
            elif os.path.isdir(os.path.join(os.path.expanduser("~"),"Documents")):
                self.output_path_entry.setText(os.path.join(os.path.expanduser("~"),"Documents"))
            else: self.output_path_entry.setText(os.path.expanduser("~"))

        except (json.JSONDecodeError, Exception) as e:
             self.log_message(f"加载配置出错或配置格式错误: {e}"); self.config = {}

    def save_config(self):
        if not os.path.exists(CONFIG_DIR):
            try: os.makedirs(CONFIG_DIR)
            except OSError: self.log_message("创建配置目录失败。"); return
        api_key = self.api_key_entry.text().strip(); remember = self.remember_api_key_checkbox.isChecked()
        self.config['remember_api_key'] = remember
        if remember and api_key: self.config['deepseek_api_key'] = api_key
        elif 'deepseek_api_key' in self.config: del self.config['deepseek_api_key']
        self.config['last_json_path'] = self.json_path_entry.text(); self.config['last_output_path'] = self.output_path_entry.text()
        self.config['last_source_format'] = self.json_format_combo.currentText() # Save the text
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(self.config, f, indent=4, ensure_ascii=False) # Added ensure_ascii=False
        except Exception as e: self.log_message(f"保存配置失败: {e}")

    def browse_json_file(self):
        start_dir = os.path.dirname(self.json_path_entry.text()) if self.json_path_entry.text() and os.path.exists(os.path.dirname(self.json_path_entry.text())) else os.path.expanduser("~")
        filepath, _ = QFileDialog.getOpenFileName(self, "选择 JSON 文件", start_dir, "JSON 文件 (*.json);;所有文件 (*.*)")
        if filepath: self.json_path_entry.setText(filepath)

    def select_output_dir(self):
        start_dir = self.output_path_entry.text() if self.output_path_entry.text() and os.path.isdir(self.output_path_entry.text()) else os.path.expanduser("~")
        dirpath = QFileDialog.getExistingDirectory(self, "选择导出目录", start_dir)
        if dirpath: self.output_path_entry.setText(dirpath)

    def start_conversion(self):
        api_key = self.api_key_entry.text().strip(); json_path = self.json_path_entry.text().strip(); output_dir = self.output_path_entry.text().strip()
        if not api_key: QMessageBox.warning(self, "缺少信息", "请输入 DeepSeek API Key。"); return
        if not json_path: QMessageBox.warning(self, "缺少信息", "请选择 JSON 文件。"); return
        if not os.path.isfile(json_path): QMessageBox.critical(self, "错误", f"JSON 文件不存在: {json_path}"); return # Changed exists to isfile
        if not output_dir: QMessageBox.warning(self, "缺少信息", "请选择导出目录。"); return
        if not os.path.isdir(output_dir): QMessageBox.critical(self, "错误", f"导出目录无效: {output_dir}"); return
        self.save_config();
        self.start_button.setEnabled(False); self.start_button.setText("转换中...")
        self.progress_bar.setValue(0); self.log_area.clear()
        self.log_message("准备开始..."); selected_format_text = self.json_format_combo.currentText()
        source_format_map = {"ElevenLabs(推荐)":"elevenlabs", "Whisper(推荐)":"whisper", "Deepgram":"deepgram", "AssemblyAI":"assemblyai"}
        source_format_key = source_format_map.get(selected_format_text, "elevenlabs")

        if self.conversion_thread and self.conversion_thread.isRunning():
             self.log_message("警告：上一个转换任务仍在进行中。请等待其完成后再开始新的任务。")
             self.start_button.setEnabled(True) # Re-enable if we return early
             self.start_button.setText("开始转换")
             return

        self.conversion_thread = QThread(parent=self)
        self.worker = ConversionWorker(api_key, json_path, output_dir, self.srt_processor, source_format_key)
        self.worker.moveToThread(self.conversion_thread)
        self.worker.signals.finished.connect(self.on_conversion_finished)
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.log_message.connect(self.log_message)
        self.conversion_thread.started.connect(self.worker.run)
        self.worker.signals.finished.connect(self.conversion_thread.quit)
        self.worker.signals.finished.connect(self.worker.deleteLater)
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater)
        self.conversion_thread.finished.connect(self._clear_worker_references) # Connect here for cleanup
        self.conversion_thread.start()

    def _clear_worker_references(self):
        self.worker = None; self.conversion_thread = None
        if hasattr(self, 'start_button') and self.start_button: # Ensure button exists
            self.start_button.setEnabled(True)
            self.start_button.setText("开始转换")


    def update_progress(self, value):
        self.progress_bar.setValue(value)

    @staticmethod
    def show_message_box(parent_widget, title, message, success):
        if parent_widget and parent_widget.isVisible():
            QTimer.singleShot(0, lambda: (
                QMessageBox.information(parent_widget, title, message) if success
                else QMessageBox.critical(parent_widget, title, message)
            ))


    def on_conversion_finished(self, message, success):
        if hasattr(self, 'start_button') and self.start_button: # Check if button exists before enabling
             self.start_button.setEnabled(True)
             self.start_button.setText("开始转换")

        current_progress = self.progress_bar.value()
        if success: self.progress_bar.setValue(100)
        else: self.progress_bar.setValue(current_progress if current_progress > 0 else 0)
        # Keep the detailed message from worker if available
        # log_msg_result = message if message else f"任务{'成功' if success else '失败/取消'}"
        # self.log_message(log_msg_result) # Worker already logs its final message.
        self.show_message_box(self, "转换结果", message, success)


    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            widget_at_pos = self.childAt(event.position().toPoint())
            is_on_title_bar_area = False
            title_bar_height = 80
            if event.position().y() < title_bar_height:
                 is_on_title_bar_area = True

            interactive_widgets = (QPushButton, QLineEdit, QCheckBox, QTextEdit, QProgressBar, QComboBox, QAbstractItemView) # Added QAbstractItemView
            is_interactive_control = False; current_widget = widget_at_pos
            while current_widget is not None:
                if isinstance(current_widget, interactive_widgets) or \
                   (hasattr(current_widget, 'objectName') and current_widget.objectName().startswith('qt_scrollarea')) or \
                   (QApplication.activePopupWidget() and isinstance(current_widget, QApplication.activePopupWidget().__class__)):
                    is_interactive_control = True; break
                current_widget = current_widget.parentWidget()

            if is_on_title_bar_area and not is_interactive_control:
                self.drag_pos = event.globalPosition().toPoint(); self.is_dragging = True; event.accept()
            else: event.ignore()

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint(); event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.is_dragging = False; event.accept()

    def close_application(self):
        self.close()

    def closeEvent(self, event):
        if self.conversion_thread and self.conversion_thread.isRunning():
            if self.worker: self.worker.stop()
            if not self.conversion_thread.isFinished():
                 self.conversion_thread.quit()
                 if not self.conversion_thread.wait(3000): self.log_message("警告：工作线程在3秒内未能正常停止。")
        self.save_config(); super().closeEvent(event)

# --- 主程序入口 ---
if __name__ == "__main__":
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("HealJimaku")
    if os.name == 'nt':
        try:
            import ctypes
            myappid = u'MyCompany.HealJimaku.Refactored.1.8' # Unique ID, incremented again
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception: pass

    app_icon_early_path = resource_path("icon.ico")
    if app_icon_early_path and os.path.exists(app_icon_early_path):
        app.setWindowIcon(QIcon(app_icon_early_path))
    else:
        print("[Log Early Main] App icon 'icon.ico' not found during app init.")


    window = HealJimakuApp(); window.show(); sys.exit(app.exec())