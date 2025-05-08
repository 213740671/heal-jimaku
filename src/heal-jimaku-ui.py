import sys
import os
import json
import threading
import requests # 用于 DeepSeek API 调用
import difflib
import re
import math
import time # 用于进度条模拟
# import faulthandler # 将 faulthandler 的导入和启用放到下面的专用块中

# --- faulthandler 错误处理模块设置 ---
import faulthandler # 在这里导入
import io # 如果需要用作虚拟文件流

try:
    FHT_LOG_ENABLED = False
    # 检查 sys.stderr 是否为 None (在 --windowed 打包应用中常见)
    if sys.stderr is None:
        # 如果 stderr 不可用，尝试将 faulthandler 的输出重定向到日志文件
        log_dir_app = ""
        try:
            # 定义日志文件存放目录
            # 您可以根据您应用中 CONFIG_DIR 的定义来调整此路径
            # 这里使用用户主目录下一个专门的日志文件夹作为示例
            home_dir = os.path.expanduser("~")
            # 确保文件夹名称的兼容性，或者您的CONFIG_DIR能正确处理
            log_dir_app = os.path.join(home_dir, ".heal_jimaku_gui_logs") 
            if not os.path.exists(log_dir_app):
                os.makedirs(log_dir_app, exist_ok=True)
            
            crash_log_path = os.path.join(log_dir_app, "heal_jimaku_crashes.log")
            
            # 以追加模式打开日志文件，保留历史崩溃记录
            with open(crash_log_path, 'a', encoding='utf-8') as f_log:
                faulthandler.enable(file=f_log, all_threads=True)
            FHT_LOG_ENABLED = True
            # print(f"faulthandler enabled, logging crashes to: {crash_log_path}") # 在窗口模式下不可见
            
        except Exception as e_fht:
            # print(f"Failed to set up file logging for faulthandler: {e_fht}") # 在窗口模式下不可见
            pass 
    else:
        # 如果 sys.stderr 存在 (例如通过命令行运行脚本时)
        faulthandler.enable(all_threads=True)
        FHT_LOG_ENABLED = True
        # print("faulthandler enabled, logging crashes to sys.stderr")

    # if not FHT_LOG_ENABLED:
        # print("Warning: faulthandler could not be enabled.") # 在窗口模式下不可见

except Exception as e_global_fht:
    # print(f"Global exception during faulthandler setup: {e_global_fht}") # 在窗口模式下不可见
    pass
# --- faulthandler 设置结束 ---


from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QTextEdit, QCheckBox, QComboBox,
    QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer, QPoint
from PyQt6.QtGui import QIcon, QFont, QColor, QTextCursor, QPixmap, QPainter, QBrush, QLinearGradient

# --- Configuration & Constants ---
# CONFIG_DIR 的定义要确保在 faulthandler 日志路径之后，或者 faulthandler 使用独立的路径逻辑
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".heal_jimaku_gui")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# SRT Generation Constants
MIN_DURATION_TARGET = 1.2
MIN_DURATION_ABSOLUTE = 1.0
MAX_DURATION = 12.0
MAX_CHARS_PER_LINE = 60
DEFAULT_GAP_MS = 100
ALIGNMENT_SIMILARITY_THRESHOLD = 0.7

# Punctuation Sets
FINAL_PUNCTUATION = {'.', '。', '?', '？', '!', '！'}
ELLIPSIS_PUNCTUATION = {'...', '......', '‥'}
COMMA_PUNCTUATION = {',', '、'}
ALL_SPLIT_PUNCTUATION = FINAL_PUNCTUATION | ELLIPSIS_PUNCTUATION | COMMA_PUNCTUATION

# DeepSeek System Prompt (保持不变)
DEEPSEEK_SYSTEM_PROMPT = """「重要：您的任务是精确地分割提供的日语文本。请严格按照以下规则操作，并仅输出分割后的文本片段列表。每个片段占独立的一行。不要添加或删除任何原始文本中的字符，保持原始顺序。」

您是一位专业的文本处理员，擅长根据标点和上下文将日语长文本分割成自然的句子或语义单元。

**输入：** 一段完整的日语文本字符串。

**输出要求：** 一个文本片段的列表，每个片段占据新的一行。

**分割规则 (请按顺序优先应用)：**

1.  **独立附加情景 (括号优先)：** 将括号 `()` 或全角括号 `（）` 内的附加情景描述（例如 `(笑い声)`、`(雨の音)`、`(ため息)`、`（会場騒然）`等）视为独立的片段进行分离。
    * **处理逻辑：**
        * `文A(イベント)文B。` -> `文A` / `(イベント)` / `文B。`
        * `文A。(イベント)文B。` -> `文A。` / `(イベント)` / `文B。`
        * `文A(イベント)。文B。` -> `文A` / `(イベント)。` / `文B。` (括号内容和其后的句号一起成为一个片段)
        * `(イベント)文A。` -> `(イベント)` / `文A。`
2.  **独立引用单元 (引号优先)：** 将以 `「`、`『` 开始并以对应的 `」`、`』` 结束的完整引用内容，视为一个独立的片段。这些引号内的句末标点（如 `。`、`？`、`！`、`…`等）**不**触发片段内部分割。整个带引号的引用被视为一个单元，处理逻辑类似于上述的独立附加情景。
    * **处理逻辑：**
        * `文A「引用文。」文B。` -> `文A` / `「引用文。」` / `文B。`
        * `文A。「引用文１。引用文２！」文B。` -> `文A。` / `「引用文１。引用文２！」` / `文B。`
        * `「引用文。」文B。` -> `「引用文。」` / `文B。`
        * `文A「引用文」。文B。` -> `文A` / `「引用文」。` / `文B。` (引号后的标点若紧跟，则属于引号片段)
        * `「引用文１。」「引用文２。」` -> `「引用文１。」` / `「引用文２。」`
3.  **主要分割点 (一般情况)：** 在处理完上述括号和引号独立单元后，对于剩余的、非括号非引号包裹的文本，在遇到以下代表句子结尾的标点符号（全角：`。`、`？`、`！`、`…`、`‥` 以及半角：`.` `?` `!` `...` `‥`）后进行分割。标点符号应保留在它所结束的那个片段的末尾。
    * *注意：* 针对连续的省略号，如 `……` (两个 `…`) 或 `......` (六个 `.`)，应视为单个省略号标点，并根据规则4的语义连贯性判断是否分割。
4.  **确保语义连贯性 (指导规则3)：** 必须先理解完整文本的意思，再根据规则3进行分割，保证分割出来的片段在语义上是自然的、不过于零碎。此规则尤其适用于指导规则3中省略号（`…`、`‥`等）的处理，这些标点有时用于连接一个未完结的意群，而非严格的句子结束。应优先形成语义上更完整的片段，避免在仍能构成一个完整意群的地方进行切割。
    * **示例 (此示例不含顶层引号，以展示规则4的独立作用)：**
        * 输入:
            `ええと……それはつまり……あなたがやったということですか……だとしたら、説明してください……`
        * 期望输出:
            ```
            ええと……それはつまり……あなたがやったということですか……
            だとしたら、説明してください……
            ```
        * *不期望的分割 (过于零碎):*
            ```
            ええと……
            それはつまり……
            あなたがやったということですか……
            だとしたら、説明してください……
            ```
5.  **确保完整性：** 输出的片段拼接起来应与原始输入文本完全一致，包括空格（如果原始文本中存在）。"""


# --- 资源路径处理 ---
def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    assets_path = os.path.join(base_path, "..", "assets", relative_path)
    if os.path.exists(assets_path): return assets_path
    dev_path = os.path.join(base_path, "assets", relative_path)
    if os.path.exists(dev_path): print(f"警告：在../assets未找到资源，但在同级assets找到: {relative_path}"); return dev_path
    print(f"警告：未在指定assets目录找到资源，尝试直接加载: {relative_path}"); return os.path.join(base_path, relative_path)


# --- Worker Signals ---
class WorkerSignals(QObject):
    finished = pyqtSignal(str, bool)
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)

# --- 自定义控件 ---
class TransparentWidget(QWidget):
    def __init__(self, parent=None, bg_color=QColor(255, 255, 255, 3)):
        super().__init__(parent)
        self.bg_color = bg_color
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self.bg_color)); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 10, 10)

class CustomLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_color = QColor(92, 138, 111)  # #5C8A6F
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_color = QColor(87, 128, 183) # #5780b7
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


# --- Subtitle Entry Class ---
class SubtitleEntry:
    def __init__(self, index, start_time, end_time, text, words_used=None, alignment_ratio=1.0):
        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.text = re.sub(r'\s+', ' ', text).strip()
        self.words_used = words_used if words_used else []
        self.alignment_ratio = alignment_ratio
        self.is_intentionally_oversized = False # 新增标志，默认为 False

    @property
    def duration(self):
        if self.start_time is not None and self.end_time is not None: return max(0, self.end_time - self.start_time)
        return 0

    def to_srt_format(self, processor_instance):
        if self.start_time is None or self.end_time is None or self.text is None:
            processor_instance.log(f"警告: 字幕条目 {self.index} 缺少时间或文本")
            return ""
        # 确保结束时间不早于开始时间，且至少有一个微小的间隔 (例如0.001s)
        if self.end_time < self.start_time + 0.001: # 使用0.001秒作为最小差值检查
            processor_instance.log(f"警告: 字幕条目 {self.index} 结束时间 ({processor_instance.format_timecode(self.end_time)}) 不大于或过近于开始时间 ({processor_instance.format_timecode(self.start_time)})。已修正。")
            self.end_time = self.start_time + 0.1 # 确保至少0.1秒
        return f"{self.index}\n{processor_instance.format_timecode(self.start_time)} --> {processor_instance.format_timecode(self.end_time)}\n{self.text}\n\n"


# --- SRT Generation Logic ---
class SrtProcessor:
    def __init__(self):
        self._signals = None
    def log(self, message):
        if self._signals: self._signals.log_message.emit(message)
        else: print(message)
    def format_timecode(self, seconds_float):
        if not isinstance(seconds_float, (int, float)) or seconds_float < 0: self.log(f"警告: 无效秒数 {seconds_float}"); return "00:00:00,000"
        total_seconds_int = int(seconds_float); milliseconds = int(round((seconds_float - total_seconds_int) * 1000))
        hours = total_seconds_int // 3600; minutes = (total_seconds_int % 3600) // 60; seconds = total_seconds_int % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    def check_word_has_punctuation(self, word_text, punctuation_set):
        cleaned_text = word_text.strip();
        if not cleaned_text: return False
        for punct in punctuation_set:
            if cleaned_text.endswith(punct): return True
        return False
    def get_segment_words_fuzzy(self, text_segment, all_words, start_search_index):
        segment_clean = text_segment.strip().replace(" ", "")
        if not segment_clean: return [], start_search_index, 1.0
        best_match_words = []; best_match_ratio = 0.0; best_match_end_index = start_search_index
        search_window_size = len(segment_clean) * 3 + 20; max_lookahead = min(start_search_index + search_window_size, len(all_words))
        for i in range(start_search_index, max_lookahead):
            current_words_text_list = []; current_word_list = []; max_j_lookahead = min(i + search_window_size // 2 + 10, len(all_words))
            for j in range(i, max_j_lookahead):
                word_obj = all_words[j]; word_text_orig = word_obj.get("text", ""); current_word_list.append(word_obj); current_words_text_list.append(word_text_orig.replace(" ", ""))
                built_text = "".join(current_words_text_list)
                if not built_text.strip(): continue
                matcher = difflib.SequenceMatcher(None, segment_clean, built_text, autojunk=False); ratio = matcher.ratio()
                update_best = False
                if ratio > best_match_ratio: update_best = True
                elif ratio == best_match_ratio and best_match_words:
                     current_len_diff = abs(len(built_text) - len(segment_clean)); best_len_diff = abs(len("".join(w.get("text","").replace(" ","") for w in best_match_words)) - len(segment_clean))
                     if current_len_diff < best_len_diff: update_best = True
                if update_best and ratio > 0: best_match_ratio = ratio; best_match_words = list(current_word_list); best_match_end_index = j + 1
                if ratio > 0.95 and len(built_text) > len(segment_clean) * 1.5: break
        if not best_match_words: self.log(f"严重警告: LLM片段 '{text_segment}' 无法对齐。跳过。"); return [], start_search_index, 0.0
        if best_match_ratio < ALIGNMENT_SIMILARITY_THRESHOLD:
            matched_text_preview = "".join([w.get("text", "") for w in best_match_words]); self.log(f"警告: LLM片段 '{text_segment}' 对齐相似度较低 ({best_match_ratio:.2f})。"); self.log(f"  - LLM: '{segment_clean}'"); self.log(f"  - 对齐: '{matched_text_preview}'")
        return best_match_words, best_match_end_index, best_match_ratio

    def split_long_sentence(self, sentence_text, sentence_words, original_start_time, original_end_time):
        has_split_punctuation = any(self.check_word_has_punctuation(word.get("text", ""), ALL_SPLIT_PUNCTUATION) for word in sentence_words)

        # 情况1: 整个原始片段没有标点，并且不止一个词
        if not has_split_punctuation and len(sentence_words) > 1:
            self.log(f"信息: 完整超限片段 '{sentence_text[:30]}...' (原始时长: {(original_end_time - original_start_time):.2f}s) 无标点，不进行分割。")
            final_end_time = original_end_time
            current_duration_val = final_end_time - original_start_time

            if current_duration_val < MIN_DURATION_ABSOLUTE:
                final_end_time = original_start_time + MIN_DURATION_ABSOLUTE
                self.log(f"  -> 上述无标点片段因过短，调整为绝对最小持续时间: {MIN_DURATION_ABSOLUTE:.2f}s")

            entry = SubtitleEntry(0, original_start_time, final_end_time, sentence_text, sentence_words)
            if entry.duration > MAX_DURATION:
                self.log(f"  -> 此无标点片段将保留超长时间戳并标记为特意超长。最终时间: {self.format_timecode(entry.start_time)} --> {self.format_timecode(entry.end_time)} (时长: {entry.duration:.2f}s)")
                entry.is_intentionally_oversized = True
            else:
                self.log(f"  -> 此无标点片段时长 ({entry.duration:.2f}s) 未超过 {MAX_DURATION}s，不标记为特意超长。")
            return [entry]

        # 情况2: 单个词的片段
        if len(sentence_words) == 1:
            word_obj = sentence_words[0]
            word_start_time = word_obj["start"]
            word_end_time = word_obj["end"]
            word_text = word_obj["text"]
            current_duration_val = word_end_time - word_start_time
            
            final_word_end_time = word_end_time # 默认为原始结束时间
            entry_to_return = SubtitleEntry(0, word_start_time, final_word_end_time, word_text, [word_obj])
            # is_intentionally_oversized 默认为 False

            if current_duration_val > MAX_DURATION:
                self.log(f"信息: 单个词 '{word_text}' 跨度({current_duration_val:.2f}s)超长。将根据通用规则处理（最终可能被限制为 {MAX_DURATION}s）。")
                # 不在此处直接截断，让 process_to_srt 中的最终循环统一处理非特意超长的情况
            elif current_duration_val < MIN_DURATION_ABSOLUTE:
                entry_to_return.end_time = word_start_time + MIN_DURATION_ABSOLUTE
            return [entry_to_return]

        # 情况3: 有标点，尝试按标点分割
        entries = []
        words_to_process = list(sentence_words)

        while words_to_process:
            current_segment_text = "".join([w.get("text", "") for w in words_to_process])
            current_segment_start_time = words_to_process[0]["start"]
            current_segment_end_time = words_to_process[-1]["end"]
            current_segment_duration = current_segment_end_time - current_segment_start_time

            if current_segment_duration <= MAX_DURATION and len(current_segment_text) <= MAX_CHARS_PER_LINE:
                final_seg_end_time = current_segment_end_time
                if current_segment_duration < MIN_DURATION_ABSOLUTE:
                    final_seg_end_time = current_segment_start_time + MIN_DURATION_ABSOLUTE
                elif current_segment_duration < MIN_DURATION_TARGET:
                    final_seg_end_time = current_segment_start_time + MIN_DURATION_TARGET
                entries.append(SubtitleEntry(0, current_segment_start_time, final_seg_end_time, current_segment_text, list(words_to_process)))
                break 

            best_split_index = -1
            split_indices_by_priority = {p: [] for p in ['final', 'ellipsis', 'comma']}
            # 仅在当前待处理片段（words_to_process）内部查找标点
            for i, word_obj_in_loop in enumerate(words_to_process):
                # 不在片段的第一个词和最后一个词处分割（除非它是唯一的分割点，但通常标点在中间）
                if i == 0 or i == len(words_to_process) - 1: continue 
                word_text_in_loop = word_obj_in_loop.get("text", "")
                if self.check_word_has_punctuation(word_text_in_loop, FINAL_PUNCTUATION): split_indices_by_priority['final'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, ELLIPSIS_PUNCTUATION): split_indices_by_priority['ellipsis'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, COMMA_PUNCTUATION): split_indices_by_priority['comma'].append(i)
            
            chosen_indices = None
            # 优先选择分割点
            if split_indices_by_priority['final']: chosen_indices = split_indices_by_priority['final']; best_split_index = min(chosen_indices)
            elif split_indices_by_priority['ellipsis']: chosen_indices = split_indices_by_priority['ellipsis']; best_split_index = chosen_indices[0] # 简单取第一个
            elif split_indices_by_priority['comma']: chosen_indices = split_indices_by_priority['comma']; best_split_index = chosen_indices[0] # 简单取第一个


            if best_split_index == -1: # 在当前片段中未找到合适的内部标点分割点
                self.log(f"  -> 在当前待分割片段 '{current_segment_text[:30]}...' (时长: {current_segment_duration:.2f}s) 中未找到有效内部标点分割点。")
                final_seg_end_time = current_segment_end_time 
                
                if current_segment_duration < MIN_DURATION_ABSOLUTE:
                    final_seg_end_time = current_segment_start_time + MIN_DURATION_ABSOLUTE

                entry = SubtitleEntry(0, current_segment_start_time, final_seg_end_time, current_segment_text, list(words_to_process))
                if entry.duration > MAX_DURATION:
                    self.log(f"    -> 此剩余片段仍超长 ({entry.duration:.2f}s)，将被标记为特意超长。")
                    entry.is_intentionally_oversized = True
                else:
                    self.log(f"    -> 此剩余片段时长 ({entry.duration:.2f}s) 未超限，正常处理。")
                entries.append(entry)
                break 

            words_for_this_sub_entry = words_to_process[:best_split_index + 1]
            words_to_process = words_to_process[best_split_index + 1:]

            if not words_for_this_sub_entry: continue

            sub_text = "".join([w.get("text", "") for w in words_for_this_sub_entry])
            sub_start_time = words_for_this_sub_entry[0]["start"]
            sub_end_time = words_for_this_sub_entry[-1]["end"]
            sub_duration = sub_end_time - sub_start_time
            final_sub_end_time = sub_end_time

            if sub_duration < MIN_DURATION_ABSOLUTE:
                potential_next_word_start = words_to_process[0]["start"] if words_to_process else float('inf')
                max_allowed_extension_time = min(potential_next_word_start - (DEFAULT_GAP_MS / 1000.0), sub_end_time + 0.5)
                new_end_time_abs = sub_start_time + MIN_DURATION_ABSOLUTE
                final_sub_end_time = max(sub_end_time, new_end_time_abs)
                final_sub_end_time = min(final_sub_end_time, max_allowed_extension_time)
                if final_sub_end_time <= sub_start_time: final_sub_end_time = sub_start_time + 0.1
            elif sub_duration < MIN_DURATION_TARGET:
                potential_next_word_start = words_to_process[0]["start"] if words_to_process else float('inf')
                max_allowed_extension_time = min(potential_next_word_start - (DEFAULT_GAP_MS / 1000.0), sub_end_time + 0.5)
                new_end_time_target = sub_start_time + MIN_DURATION_TARGET
                final_sub_end_time = max(sub_end_time, new_end_time_target)
                final_sub_end_time = min(final_sub_end_time, max_allowed_extension_time)
                if final_sub_end_time <= sub_start_time: final_sub_end_time = sub_start_time + 0.1
            
            entries.append(SubtitleEntry(0, sub_start_time, final_sub_end_time, sub_text, words_used=words_for_this_sub_entry))
            
            if not words_to_process:
                break
        return entries

    def process_to_srt(self, all_words, llm_segments_text, signals_forwarder):
        self._signals = signals_forwarder
        self.log("--- 开始对齐 LLM 片段 ---")
        intermediate_entries = []
        word_search_start_index = 0
        unaligned_segments = []

        if not llm_segments_text:
            self.log("错误：LLM 未返回任何分割片段。")
            return None

        total_segments = len(llm_segments_text)
        for i, text_seg in enumerate(llm_segments_text):
            if not self._signals.is_running:
                self.log("任务被用户中断(对齐阶段)。")
                return None
            progress_align = int(10 + 30 * ((i + 1) / total_segments))
            self._signals.progress.emit(progress_align)
            time.sleep(0.01) # 模拟部分耗时操作或确保UI响应

            matched_words, next_search_idx, match_ratio = self.get_segment_words_fuzzy(text_seg, all_words, word_search_start_index)

            if not matched_words or match_ratio == 0:
                unaligned_segments.append(text_seg)
                continue

            word_search_start_index = next_search_idx
            entry_text = "".join([w.get("text", "") for w in matched_words])
            entry_start_time = matched_words[0]["start"]
            entry_end_time = matched_words[-1]["end"]
            entry_duration = entry_end_time - entry_start_time
            text_len = len(entry_text)
            is_audio_event = all(w.get("type") == "audio_event" or not w.get("text","").strip() for w in matched_words)

            if is_audio_event:
                final_audio_event_end_time = entry_end_time
                if entry_duration < MIN_DURATION_ABSOLUTE:
                    final_audio_event_end_time = entry_start_time + MIN_DURATION_ABSOLUTE
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_audio_event_end_time, entry_text, matched_words, match_ratio))
            elif entry_duration > MAX_DURATION or text_len > MAX_CHARS_PER_LINE:
                self.log(f"信息: 片段 (LLM:{text_seg[:20]}... / 对齐:{entry_text[:20]}...) (时长: {entry_duration:.2f}s, 字数: {text_len}) 超限，尝试分割。")
                split_sub_entries = self.split_long_sentence(entry_text, matched_words, entry_start_time, entry_end_time)
                for sub_entry in split_sub_entries:
                    sub_entry.alignment_ratio = match_ratio # 继承父片段的对齐率
                intermediate_entries.extend(split_sub_entries)
            elif entry_duration < MIN_DURATION_TARGET: # 不超限，但可能过短
                final_short_entry_end_time = entry_end_time
                if entry_duration < MIN_DURATION_ABSOLUTE:
                    final_short_entry_end_time = entry_start_time + MIN_DURATION_ABSOLUTE
                elif entry_duration < MIN_DURATION_TARGET:
                    final_short_entry_end_time = entry_start_time + MIN_DURATION_TARGET
                
                # 限制延长，避免与下一个词重叠过多
                max_allowed_extension = matched_words[-1]["end"] + 0.5 
                final_short_entry_end_time = min(final_short_entry_end_time, max_allowed_extension)
                if final_short_entry_end_time <= entry_start_time: # 安全检查
                    final_short_entry_end_time = entry_start_time + 0.1

                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_short_entry_end_time, entry_text, matched_words, match_ratio))
            else: # 时长和长度都合适
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, entry_end_time, entry_text, matched_words, match_ratio))

        self.log("--- 对齐结束 ---")
        if unaligned_segments:
            self.log("\n--- 以下 LLM 片段未能成功对齐，已跳过 ---")
            for seg in unaligned_segments: self.log(f"- {seg}")
            self.log("----------------------------------------\n")

        if not intermediate_entries:
            self.log("错误：没有成功处理任何字幕条目。")
            return None

        self.log("--- 开始合并和调整 ---")
        intermediate_entries.sort(key=lambda e: e.start_time)
        merged_entries = []
        i = 0
        total_intermediate = len(intermediate_entries)
        while i < total_intermediate:
            if not self._signals.is_running:
                self.log("任务被用户中断(合并阶段)。")
                return None
            progress_merge = int(40 + 50 * ((i + 1) / total_intermediate)) # 进度条从40%到90%
            self._signals.progress.emit(progress_merge)
            time.sleep(0.005)

            current_entry = intermediate_entries[i]
            merged = False
            if i + 1 < len(intermediate_entries):
                next_entry = intermediate_entries[i+1]
                gap_between = next_entry.start_time - current_entry.end_time
                combined_text_len = len(current_entry.text) + len(next_entry.text) + 1 # 加1是空格
                combined_duration = next_entry.end_time - current_entry.start_time

                # 合并条件：当前条目过短，下一个不是音效，合并后长度和时长不超限，间隔小
                if current_entry.duration < MIN_DURATION_TARGET and \
                   not any(w.get("type") == "audio_event" for w in next_entry.words_used) and \
                   combined_text_len <= MAX_CHARS_PER_LINE and \
                   combined_duration <= MAX_DURATION and \
                   gap_between < 0.5 : # 0.5秒内的可以尝试合并
                    
                    # 合并后时长应至少达到目标时长
                    if combined_duration >= MIN_DURATION_TARGET :
                        merged_text = current_entry.text + " " + next_entry.text
                        merged_start_time = current_entry.start_time
                        merged_end_time = next_entry.end_time # 使用下一个条目的结束时间
                        merged_words = current_entry.words_used + next_entry.words_used
                        merged_ratio = min(current_entry.alignment_ratio, next_entry.alignment_ratio)
                        
                        # 创建新的合并条目，is_intentionally_oversized 默认为 False
                        # 这是合理的，因为合并改变了原始片段的结构
                        new_merged_entry = SubtitleEntry(0, merged_start_time, merged_end_time, merged_text, merged_words, merged_ratio)
                        merged_entries.append(new_merged_entry)
                        i += 2 # 跳过当前和下一个
                        merged = True
            
            if not merged:
                merged_entries.append(current_entry)
                i += 1

        final_srt_formatted_list = []
        last_end_time = -1.0 # 用于确保字幕条目按时间顺序且有最小间隔
        subtitle_index = 1
        for entry in merged_entries:
            if not self._signals.is_running:
                self.log("任务被用户中断(最终格式化阶段)。")
                return None
            
            required_start_time = last_end_time + (DEFAULT_GAP_MS / 1000.0)
            original_entry_duration_before_gap_adj = entry.duration

            if entry.start_time < required_start_time:
                entry.start_time = required_start_time
                entry.end_time = entry.start_time + original_entry_duration_before_gap_adj

            current_duration = entry.duration # 重新获取，因为 start_time 可能变了
            min_duration_to_apply = None
            
            if not entry.is_intentionally_oversized: # 非特意超长的片段才考虑延长
                if not any(w.get("type") == "audio_event" for w in entry.words_used):
                    if current_duration < MIN_DURATION_ABSOLUTE:
                        min_duration_to_apply = MIN_DURATION_ABSOLUTE
                    elif current_duration < MIN_DURATION_TARGET:
                        min_duration_to_apply = MIN_DURATION_TARGET
            
            if min_duration_to_apply is not None:
                target_end_time = entry.start_time + min_duration_to_apply
                entry.end_time = max(entry.end_time, target_end_time)

            # --- 修改后的 MAX_DURATION 限制逻辑 ---
            if entry.is_intentionally_oversized:
                if entry.duration > MAX_DURATION: 
                    self.log(f"信息: 字幕 {subtitle_index} (特意超长) 保留原始时长 ({entry.duration:.2f}s)，该时长超过了常规最大时长 {MAX_DURATION}s。文本: '{entry.text[:30]}...'")
                # 对于特意超长的条目，不做任何截断
            else: # 对于非特意超长的条目，应用 MAX_DURATION 限制
                if entry.duration > MAX_DURATION:
                    self.log(f"警告: 字幕 {subtitle_index} (非特意超长) 时长 ({entry.duration:.2f}s) > {MAX_DURATION}s。将强制截断为 {MAX_DURATION}s。文本: '{entry.text[:30]}...'")
                    entry.end_time = entry.start_time + MAX_DURATION
            # --- 限制逻辑修改结束 ---

            if entry.end_time < entry.start_time + 0.001:
                self.log(f"警告: 字幕 {subtitle_index} 在最终调整后结束时间不大于开始时间或过于接近。修正。 {self.format_timecode(entry.start_time)} -> {self.format_timecode(entry.end_time)}")
                entry.end_time = entry.start_time + 0.1 

            entry.index = subtitle_index
            final_srt_formatted_list.append(entry.to_srt_format(self))
            last_end_time = entry.end_time
            subtitle_index += 1
            
        self.log("--- 合并和调整结束 ---")
        srt_output_string = "".join(final_srt_formatted_list)
        return srt_output_string.strip()


# --- Worker Thread Class ---
class ConversionWorker(QObject):
    def __init__(self, api_key, json_path, output_dir, srt_processor, parent=None):
        super().__init__(parent)
        self.signals = WorkerSignals(parent=self) # WorkerSignals 是 ConversionWorker 的子对象
        self.api_key = api_key
        self.json_path = json_path
        self.output_dir = output_dir
        self.srt_processor = srt_processor
        self.is_running = True

    def stop(self):
        self.is_running = False
        if self.signals:
             self.signals.log_message.emit("接收到停止信号...")

    def call_deepseek_api(self, text_to_segment):
        if not self.is_running: return None # 返回 None 而不是 [] 以便更好地区分取消和空结果
        payload = { "model": DEEPSEEK_MODEL, "messages": [{"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},{"role": "user", "content": text_to_segment}], "stream": False }
        headers = { "Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}" }
        self.signals.log_message.emit("调用 DeepSeek API 进行文本分割...")
        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            if not self.is_running: self.signals.log_message.emit("API响应接收后，任务被取消。"); return None
            if "choices" in data and data["choices"]:
                content = data["choices"][0].get("message", {}).get("content")
                if content:
                    segments = [seg.strip() for seg in content.split('\n') if seg.strip()]
                    self.signals.log_message.emit(f"DeepSeek API 分割完成，得到 {len(segments)} 个片段。")
                    return segments # 返回列表，可能为空列表
                else:
                    raise ValueError("DeepSeek API 响应 'content' 为空。")
            else:
                error_info = data.get("error", {}).get("message", str(data))
                raise RuntimeError(f"DeepSeek API 响应格式错误: {error_info}")
        except requests.exceptions.Timeout:
            if not self.is_running: self.signals.log_message.emit("DeepSeek API 请求因任务停止而被取消(超时期间)。"); return None
            raise TimeoutError("DeepSeek API 请求超时 (180秒)。")
        except requests.exceptions.RequestException as e:
            if not self.is_running: self.signals.log_message.emit("DeepSeek API 请求因任务停止而被取消(请求异常期间)。"); return None
            error_details = ""; status_code = 'N/A'
            if e.response is not None:
                 status_code = e.response.status_code
                 try: error_data = e.response.json(); error_details = f": {error_data.get('error', {}).get('message', '')}"
                 except: error_details = f": {e.response.text}" # 获取原始文本以防json解析失败
            raise ConnectionError(f"DeepSeek API 请求失败 ({status_code}){error_details}")
        except Exception as e: # 其他通用异常
            if not self.is_running: self.signals.log_message.emit("处理 DeepSeek API 响应时任务停止。"); return None
            raise RuntimeError(f"处理 DeepSeek API 响应时发生未知错误: {e}")


    def run(self):
        try:
            if not self.is_running: self.signals.finished.emit("任务开始前被取消。", False); return
            self.signals.progress.emit(5); self.signals.log_message.emit("开始转换...")
            self.signals.log_message.emit(f"读取 JSON: {self.json_path}")
            with open(self.json_path, "r", encoding="utf-8") as f: api_data = json.load(f)
            all_words = api_data.get("words", []); text_to_segment = api_data.get("text", "")
            if not all_words or not text_to_segment: raise ValueError("JSON 文件缺少 'words' 或 'text' 字段。")

            if not self.is_running: self.signals.finished.emit("任务在读取JSON后被取消。", False); return
            self.signals.progress.emit(10)
            
            llm_segments = self.call_deepseek_api(text_to_segment)
            
            if llm_segments is None: # 表示API调用失败或被取消（call_deepseek_api内部已处理日志）
                if self.is_running: # 如果不是因为is_running=False而返回None，说明是API本身错误
                    self.signals.finished.emit("DeepSeek API 调用失败或返回空。", False)
                else: # 是因为is_running=False导致返回None
                    self.signals.finished.emit("任务在API调用期间被取消。", False)
                return
            if not self.is_running: # 再次检查，以防API调用成功但之后立即取消
                self.signals.finished.emit("任务在API调用成功后被取消。", False); return

            self.signals.progress.emit(40) # API调用和初步处理占30% (10% -> 40%)
            self.signals.log_message.emit("开始生成 SRT 内容...")

            class TempSignalsForwarder:
                def __init__(self, worker_signals_obj, worker_instance_ref):
                    self.worker_signals = worker_signals_obj
                    self.worker_instance = worker_instance_ref
                @property
                def is_running(self):
                    return self.worker_instance.is_running
                @property
                def progress(self):
                    return self.worker_signals.progress
                @property
                def log_message(self):
                    return self.worker_signals.log_message

            forwarder = TempSignalsForwarder(self.signals, self)
            final_srt = self.srt_processor.process_to_srt(all_words, llm_segments, forwarder)

            if final_srt is None: # SRT生成失败或被取消 (process_to_srt内部已处理日志)
                if self.is_running:
                     self.signals.finished.emit("SRT 内容生成失败。", False)
                else:
                     self.signals.finished.emit("任务在SRT生成期间被取消。", False)
                return
            if not self.is_running: # 再次检查
                self.signals.finished.emit("任务在SRT生成成功后立即被取消。", False); return

            self.signals.progress.emit(90) # SRT生成占50% (40% -> 90%)
            
            base_name = os.path.splitext(os.path.basename(self.json_path))[0]
            output_srt_filepath = os.path.join(self.output_dir, f"{base_name}.srt")
            self.signals.log_message.emit(f"保存 SRT 文件到: {output_srt_filepath}")
            with open(output_srt_filepath, "w", encoding="utf-8") as f: f.write(final_srt)
            
            if not self.is_running: # 在保存文件后检查
                self.signals.log_message.emit(f"文件已保存到 {output_srt_filepath}，但任务随后被标记为取消。")
                self.signals.finished.emit("任务在保存文件后被取消。", False)
                return

            self.signals.progress.emit(100) # 保存文件占10% (90% -> 100%)
            self.signals.finished.emit(f"转换完成！SRT 文件已保存到:\n{output_srt_filepath}", True)

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            self.signals.log_message.emit(f"处理过程中发生严重错误: {e}\nTraceback:\n{error_trace}")
            if self.is_running :
                self.signals.finished.emit(f"处理失败: {e}", False)
            else: # 如果在取消过程中发生异常
                self.signals.finished.emit(f"任务因用户取消而停止，过程中出现异常: {e}", False)
        finally:
            self.is_running = False # 确保最终状态为不再运行


# --- GUI Class ---
class HealJimakuApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heal-Jimaku (治幕)")
        self.resize(1024, 864)
        self.srt_processor = SrtProcessor()
        self.config = {}
        self.conversion_thread = None
        self.worker = None
        self.app_icon = None
        self.background = None
        self.is_dragging = False
        self.drag_pos = QPoint()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path): self.app_icon = QIcon(icon_path)
        else: print(f"警告: 图标文件缺失: {icon_path}"); self.app_icon = QIcon()
        self.setWindowIcon(self.app_icon)

        bg_path = resource_path("background.png")
        if os.path.exists(bg_path): self.background = QPixmap(bg_path)
        if self.background is None or self.background.isNull():
             print(f"警告：无法加载背景图片: {bg_path}"); self._create_fallback_background()
        else: self.background = self.background.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)

        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        self.main_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.init_ui()
        self.load_config()
        self.center_window()
        QTimer.singleShot(100, self.apply_taskbar_icon) # 延迟应用图标，确保窗口句柄有效

    def _create_fallback_background(self):
        self.background = QPixmap(self.size()); self.background.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self.background); gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(40, 40, 80, 200)); gradient.setColorAt(1, QColor(20, 20, 40, 220))
        painter.fillRect(self.rect(), gradient); painter.end()

    def apply_taskbar_icon(self):
        if hasattr(self, 'windowHandle') and self.windowHandle() is not None: # 检查 windowHandle 是否存在且非 None
            window_handle = self.windowHandle()
            if self.app_icon and not self.app_icon.isNull():
                window_handle.setIcon(self.app_icon)
        elif self.app_icon and not self.app_icon.isNull(): # 备用方案，直接在 QMainWindow 上设置
            self.setWindowIcon(self.app_icon)


    def center_window(self):
        try:
            screen_geometry = self.screen().geometry() if self.screen() else QApplication.primaryScreen().geometry()
            self.move(
                (screen_geometry.width() - self.width()) // 2,
                (screen_geometry.height() - self.height()) // 2
            )
        except Exception as e:
            print(f"居中窗口时出错: {e}")
            # 备用居中方案（如果获取屏幕失败）
            if QApplication.primaryScreen():
                 screen_geometry = QApplication.primaryScreen().geometry()
                 self.move((screen_geometry.width() - self.width()) // 2, (screen_geometry.height() - self.height()) // 2)


    def paintEvent(self, event):
        painter = QPainter(self)
        if self.background and not self.background.isNull():
            painter.drawPixmap(self.rect(), self.background)
        else: # Fallback if background is still None or invalid
            painter.fillRect(self.rect(), QColor(30, 30, 50, 230)) # Semi-transparent dark color
        super().paintEvent(event)


    def resizeEvent(self, event):
        bg_path = resource_path("background.png")
        if os.path.exists(bg_path):
            new_pixmap = QPixmap(bg_path)
            if not new_pixmap.isNull():
                self.background = new_pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            else:
                self._create_fallback_background()
        else:
            self._create_fallback_background()
        super().resizeEvent(event)
        self.update()


    def init_ui(self):
        main_layout = QVBoxLayout(self.main_widget); main_layout.setContentsMargins(30, 30, 30, 30); main_layout.setSpacing(20)
        QApplication.setFont(QFont('楷体', 12))

        title_bar_layout = QHBoxLayout()
        title = CustomLabel_title("Heal-Jimaku (治幕)"); title_font = QFont('楷体', 24); title_font.setBold(True); title.setFont(title_font); title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_btn_layout = QHBoxLayout(); control_btn_layout.setSpacing(10)
        min_btn = QPushButton("─"); min_btn.setFixedSize(30, 30); min_btn.setObjectName("minButton"); min_btn.clicked.connect(self.showMinimized)
        close_btn = QPushButton("×"); close_btn.setFixedSize(30, 30); close_btn.setObjectName("closeButton"); close_btn.clicked.connect(self.close_application)
        control_btn_layout.addWidget(min_btn); control_btn_layout.addWidget(close_btn)
        title_bar_layout.addStretch(1); title_bar_layout.addWidget(title, 2, Qt.AlignmentFlag.AlignCenter); title_bar_layout.addStretch(1); title_bar_layout.addLayout(control_btn_layout)
        main_layout.addLayout(title_bar_layout); main_layout.addSpacing(20)

        content_widget = TransparentWidget(bg_color=QColor(191, 191, 191, 50))
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(25, 25, 25, 25)
        content_layout.setSpacing(15)

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
        self.json_path_entry = QLineEdit(); self.json_path_entry.setPlaceholderText("选择包含 'text' 和 'words' 的 JSON 文件"); self.json_path_entry.setObjectName("pathEdit")
        self.json_browse_button = QPushButton("浏览..."); self.json_browse_button.setObjectName("browseButton"); self.json_browse_button.clicked.connect(self.browse_json_file)
        json_layout.addWidget(json_label, 1); json_layout.addWidget(self.json_path_entry, 4); json_layout.addWidget(self.json_browse_button, 1)
        file_layout.addLayout(json_layout);

        export_group = QGroupBox("导出与控制"); export_group.setObjectName("exportGroup")
        export_layout = QVBoxLayout(export_group); export_layout.setSpacing(12)
        output_layout = QHBoxLayout(); output_label = CustomLabel("导出目录:"); output_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.output_path_entry = QLineEdit(); self.output_path_entry.setPlaceholderText("选择 SRT 文件保存目录"); self.output_path_entry.setObjectName("pathEdit")
        self.output_browse_button = QPushButton("浏览..."); self.output_browse_button.setObjectName("browseButton"); self.output_browse_button.clicked.connect(self.select_output_dir)
        output_layout.addWidget(output_label, 1); output_layout.addWidget(self.output_path_entry, 4); output_layout.addWidget(self.output_browse_button, 1)
        export_layout.addLayout(output_layout)
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0); self.progress_bar.setTextVisible(True); self.progress_bar.setFormat("%p%"); self.progress_bar.setObjectName("progressBar")
        export_layout.addWidget(self.progress_bar)
        self.start_button = QPushButton("开始转换"); self.start_button.setFixedHeight(45); self.start_button.setFont(QFont('楷体', 14, QFont.Weight.Bold)); self.start_button.setObjectName("startButton"); self.start_button.clicked.connect(self.start_conversion)
        export_layout.addWidget(self.start_button);

        log_group = QGroupBox("日志"); log_group.setObjectName("logGroup")
        log_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit(); self.log_area.setReadOnly(True); self.log_area.setObjectName("logArea")
        log_layout.addWidget(self.log_area);

        content_layout.addWidget(api_group, 22)
        content_layout.addWidget(file_group, 22)
        content_layout.addWidget(export_group, 22)
        content_layout.addWidget(log_group, 34)

        main_layout.addWidget(content_widget, 1)
        self.apply_styles()

    def apply_styles(self):
        group_title_red = "#B34A4A"
        input_text_red = "#7a1723"
        soft_orangebrown_text = "#CB7E47"
        button_blue_bg = "rgba(100, 149, 237, 190)"
        button_blue_hover = "rgba(120, 169, 247, 210)"
        control_min_blue = "rgba(135, 206, 235, 180)"
        control_min_hover = "rgba(135, 206, 235, 220)"
        control_close_red = "rgba(255, 99, 71, 180)"
        control_close_hover = "rgba(255, 99, 71, 220)"
        group_bg = "rgba(52, 129, 184, 30)"
        input_bg = "rgba(255, 255, 255, 20)"
        input_focus_bg = "rgba(255, 255, 255, 45)"
        log_bg = "rgba(0, 0, 0, 55)"
        log_text_custom_color = "#F0783C"
        style = f"""
            QGroupBox {{ font: bold 17pt '楷体'; border: 1px solid rgba(135, 206, 235, 80); border-radius: 8px; margin-top: 12px; background-color: {group_bg}; }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 15px; padding: 2px 5px 2px 5px; color: {group_title_red}; font: bold 15pt '楷体'; }}
            QLineEdit#apiKeyEdit, QLineEdit#pathEdit {{ background: {input_bg}; color: {input_text_red}; border: 1px solid rgba(135, 206, 235, 80); border-radius: 5px; padding: 6px; font: bold 11pt 'Microsoft YaHei'; }}
            QLineEdit#apiKeyEdit:focus, QLineEdit#pathEdit:focus {{ border: 1px solid #87CEEB; background: {input_focus_bg}; }}
            QLineEdit#apiKeyEdit {{ font-family: 'Consolas', 'Courier New', monospace; font-size: 12pt; font-weight: bold; }}
            QCheckBox#rememberCheckbox {{ color: {soft_orangebrown_text}; font: bold 10pt 'Microsoft YaHei'; spacing: 5px; background-color: transparent; }}
            QCheckBox#rememberCheckbox::indicator {{ width: 18px; height: 18px; border: 1px solid #87CEEB; border-radius: 3px; background-color: rgba(255, 255, 255, 30); }}
            QCheckBox#rememberCheckbox::indicator:checked {{ background-color: rgba(105, 207, 247, 150); image: none; }}
            QPushButton#browseButton, QPushButton#startButton {{ background-color: {button_blue_bg}; color: white; border: none; border-radius: 5px; font-family: 'Microsoft YaHei'; font-weight: bold; }}
            QPushButton#browseButton {{ padding: 6px 15px; font-size: 10pt; }}
            QPushButton#startButton {{ padding: 8px 25px; font: bold 14pt '楷体'; }}
            QPushButton#browseButton:hover, QPushButton#startButton:hover {{ background-color: {button_blue_hover}; }}
            QPushButton#startButton:disabled {{ background-color: rgba(100, 100, 100, 150); color: #bbbbbb; }}
            #minButton {{ background-color: {control_min_blue}; color: white; border: none; border-radius: 15px; font-weight: bold; font-size: 14pt; }}
            #minButton:hover {{ background-color: {control_min_hover}; }}
            #closeButton {{ background-color: {control_close_red}; color: white; border: none; border-radius: 15px; font-weight: bold; font-size: 14pt; }}
            #closeButton:hover {{ background-color: {control_close_hover}; }}
            QProgressBar#progressBar {{ border: 1px solid rgba(135, 206, 235, 80); border-radius: 5px; text-align: center; background: rgba(0, 0, 0, 40); height: 22px; color: #f0f0f0; font-weight: bold; }}
            QProgressBar#progressBar::chunk {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5C8A6F, stop:1 #69CFF7); border-radius: 5px; }}
            QTextEdit#logArea {{ background-color: {log_bg}; border: 1px solid rgba(135, 206, 235, 80); border-radius: 5px; color: {log_text_custom_color}; font-family: 'SimSun'; font-size: 10pt; font-weight: bold;}}
            CustomLabel, CustomLabel_title {{ background-color: transparent; }}
            QLabel {{ background-color: transparent; }}
        """
        self.setStyleSheet(style)

    def log_message(self, message):
        if self.log_area and self.log_area.isVisible():
            self.log_area.append(message)
            self.log_area.moveCursor(QTextCursor.MoveOperation.End)
        else:
            print(f"[Log - Fallback]: {message}")


    def load_config(self):
        if not os.path.exists(CONFIG_DIR):
            try: os.makedirs(CONFIG_DIR)
            except OSError as e: self.log_message(f"创建配置目录失败: {e}"); return
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f: self.config = json.load(f)
                api_key = self.config.get('deepseek_api_key', ''); remember = self.config.get('remember_api_key', True)
                last_json_path = self.config.get('last_json_path', ''); last_output_path = self.config.get('last_output_path', '')
                if api_key and remember: self.api_key_entry.setText(api_key); self.remember_api_key_checkbox.setChecked(True)
                else: self.api_key_entry.clear(); self.remember_api_key_checkbox.setChecked(False)
                if os.path.isfile(last_json_path): self.json_path_entry.setText(last_json_path)
                if os.path.isdir(last_output_path): self.output_path_entry.setText(last_output_path)
                elif os.path.isdir(os.path.join(os.path.expanduser("~"), "Documents")): self.output_path_entry.setText(os.path.join(os.path.expanduser("~"), "Documents"))
                else: self.output_path_entry.setText(os.path.expanduser("~"))
        except json.JSONDecodeError: self.log_message("警告：配置文件格式错误。"); self.config = {}
        except Exception as e: self.log_message(f"加载配置出错: {e}"); self.config = {}

    def save_config(self):
        if not os.path.exists(CONFIG_DIR):
            try: os.makedirs(CONFIG_DIR)
            except OSError as e: self.log_message(f"创建配置目录失败: {e}"); return
        api_key = self.api_key_entry.text().strip(); remember = self.remember_api_key_checkbox.isChecked()
        self.config['remember_api_key'] = remember
        if remember and api_key: self.config['deepseek_api_key'] = api_key
        elif 'deepseek_api_key' in self.config: del self.config['deepseek_api_key']
        self.config['last_json_path'] = self.json_path_entry.text(); self.config['last_output_path'] = self.output_path_entry.text()
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(self.config, f, indent=4)
        except Exception as e: self.log_message(f"保存配置失败: {e}")

    def browse_json_file(self):
        start_dir = os.path.dirname(self.json_path_entry.text()) if self.json_path_entry.text() and os.path.exists(os.path.dirname(self.json_path_entry.text())) else ""
        filepath, _ = QFileDialog.getOpenFileName(self, "选择 JSON 文件", start_dir, "JSON 文件 (*.json);;所有文件 (*.*)")
        if filepath: self.json_path_entry.setText(filepath)

    def select_output_dir(self):
        start_dir = self.output_path_entry.text() if self.output_path_entry.text() and os.path.isdir(self.output_path_entry.text()) else ""
        dirpath = QFileDialog.getExistingDirectory(self, "选择导出目录", start_dir)
        if dirpath: self.output_path_entry.setText(dirpath)

    def start_conversion(self):
        api_key = self.api_key_entry.text().strip(); json_path = self.json_path_entry.text().strip(); output_dir = self.output_path_entry.text().strip()
        if not api_key: QMessageBox.warning(self, "缺少信息", "请输入 DeepSeek API Key。"); return
        if not json_path: QMessageBox.warning(self, "缺少信息", "请选择 JSON 文件。"); return
        if not os.path.exists(json_path): QMessageBox.critical(self, "错误", f"JSON 文件不存在: {json_path}"); return
        if not output_dir: QMessageBox.warning(self, "缺少信息", "请选择导出目录。"); return
        if not os.path.isdir(output_dir): QMessageBox.critical(self, "错误", f"导出目录无效: {output_dir}"); return
        
        self.save_config()
        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_area.clear()
        self.log_message("准备开始...")

        # 创建 QThread 实例，并将其父对象设置为 self (QMainWindow)，以便在主窗口关闭时 Qt 可以管理其生命周期
        self.conversion_thread = QThread(parent=self)
        # 创建 Worker 实例，不设置父对象，因为它将被移动到新线程
        self.worker = ConversionWorker(api_key, json_path, output_dir, self.srt_processor)
        self.worker.moveToThread(self.conversion_thread)

        # 连接信号和槽
        self.worker.signals.finished.connect(self.on_conversion_finished)
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.log_message.connect(self.log_message)
        self.conversion_thread.started.connect(self.worker.run)

        # 线程结束后，请求退出事件循环，并标记对象以便稍后删除
        self.worker.signals.finished.connect(self.conversion_thread.quit)
        self.worker.signals.finished.connect(self.worker.deleteLater)
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater)
        # 当线程完成时（包括quit()之后），清理对worker和thread的引用
        self.conversion_thread.finished.connect(self._clear_worker_references)

        self.conversion_thread.start()

    def _clear_worker_references(self):
        self.log_message("清理工作线程引用。")
        self.worker = None
        self.conversion_thread = None


    def update_progress(self, value):
        self.progress_bar.setValue(value)

    @staticmethod
    def show_message_box(parent_widget, title, message, success):
        # 确保父窗口存在且可见
        if parent_widget and parent_widget.isVisible():
            if success:
                QMessageBox.information(parent_widget, title, message)
            else:
                QMessageBox.critical(parent_widget, title, message)
        else:
            # 如果父窗口不可见（例如正在关闭），则打印到控制台
            print(f"消息框被抑制 (父窗口不可见) - 标题: {title}, 状态: {'成功' if success else '失败'}, 信息: {message}")


    def on_conversion_finished(self, message, success):
        self.start_button.setEnabled(True) # 无论成功与否，都重新启用开始按钮
        
        current_progress = self.progress_bar.value()
        if success:
            self.progress_bar.setValue(100)
        else:
            # 如果失败，保留当前进度（如果大于0），否则置0
            self.progress_bar.setValue(current_progress if current_progress > 0 else 0)

        log_msg_result = f"任务{'成功' if success else '失败/取消'}"
        if message: # 添加来自worker的详细信息
            log_msg_result += f": {message}"
        self.log_message(log_msg_result)

        # 使用QTimer确保消息框在当前事件处理完成后显示，并检查窗口可见性
        if self.isVisible():
            QTimer.singleShot(0, lambda: self.show_message_box(self, "转换结果", message, success))
        else:
            self.log_message("主窗口不可见，转换结果消息框被抑制。")
        
        # self.worker 和 self.conversion_thread 的引用将由 _clear_worker_references 在 thread.finished 时清理

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查点击的是否是可交互组件的非标题部分
            widget = self.childAt(event.position().toPoint())
            interactive_widgets = (QPushButton, QLineEdit, QCheckBox, QTextEdit, QProgressBar, QGroupBox, QComboBox)
            is_interactive = False
            current = widget
            while current is not None:
                if isinstance(current, interactive_widgets):
                    # 特例：允许拖动 QGroupBox 的标题栏区域（近似判断）
                    if isinstance(current, QGroupBox) and event.position().y() < current.y() + 25 : # 假设标题栏高度约为25px
                        pass # 允许拖动
                    else:
                        is_interactive = True
                        break
                # 检查是否是滚动区域的控件，这些通常也是可交互的
                if hasattr(current, 'objectName') and current.objectName().startswith('qt_scrollarea'):
                    is_interactive = True
                    break
                current = current.parent()
            
            if not is_interactive:
                self.drag_pos = event.globalPosition().toPoint()
                self.is_dragging = True
                event.accept()
            else:
                event.ignore() # 交给子控件处理

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            event.accept()

    def close_application(self): # 由关闭按钮调用
        self.log_message("用户请求关闭程序...")
        self.close() # 调用 QMainWindow.close()，这将触发 closeEvent

    def closeEvent(self, event): # 当窗口将要关闭时（例如用户点击X，或调用self.close()）
        self.log_message("正在执行关闭程序前的清理操作...")
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.log_message("检测到正在运行的任务，尝试停止...")
            if self.worker:
                self.worker.stop() # 通知worker停止
            self.conversion_thread.quit() # 请求线程的事件循环退出
            # 等待线程结束，设置一个超时时间
            if not self.conversion_thread.wait(3000): # 等待3秒
                self.log_message("警告：工作线程在3秒内未能正常停止。程序将继续关闭。")
            else:
                self.log_message("工作线程已停止。")
        else:
            self.log_message("没有正在运行的任务或线程已结束。")

        self.save_config()
        self.log_message("配置已保存。程序即将退出。再见！")
        super().closeEvent(event) # 调用父类的closeEvent来实际关闭窗口


# --- Main Execution ---
if __name__ == "__main__":
    # 推荐为Qt6设置DPI感知属性 (可选, 但有助于在高DPI屏幕上获得更好的一致性)
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
    # 或者
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setApplicationName("HealJimaku")
    if os.name == 'nt': # 仅在Windows上设置AppUserModelID
        try:
            import ctypes
            # 使用一个唯一的AppUserModelID
            myappid = 'Google.HealJimaku.1.5.FixDurationAndCrash'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            print(f"设置 AppUserModelID 时出错 (此错误通常可以忽略): {e}")

    app_icon_path = resource_path("icon.ico") # 尝试加载图标
    if os.path.exists(app_icon_path):
        app.setWindowIcon(QIcon(app_icon_path))
    else:
        print(f"警告: 应用图标文件未找到: {app_icon_path}")

    window = HealJimakuApp()
    window.show()
    sys.exit(app.exec())