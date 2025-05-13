import re
import difflib
from typing import List, Optional, Any

# Corrected imports: removed 'src.' prefix
from core.data_models import TimestampedWord, ParsedTranscription, SubtitleEntry
# from .data_models import TimestampedWord, ParsedTranscription, SubtitleEntry # Alternative
from config import (
    MIN_DURATION_TARGET, MIN_DURATION_ABSOLUTE, MAX_DURATION, MAX_CHARS_PER_LINE,
    DEFAULT_GAP_MS, ALIGNMENT_SIMILARITY_THRESHOLD,
    FINAL_PUNCTUATION, ELLIPSIS_PUNCTUATION, COMMA_PUNCTUATION
)


class SrtProcessor:
    """处理转录数据并生成SRT字幕内容。"""
    def __init__(self):
        self._signals: Optional[Any] = None # 将由 worker 设置信号转发器

    def log(self, message: str):
        """记录日志消息。"""
        if self._signals and hasattr(self._signals, 'log_message') and hasattr(self._signals.log_message, 'emit'):
            self._signals.log_message.emit(f"[SRT Processor] {message}")
        else:
            print(f"[SRT Processor] {message}") # 如果信号未设置，则回退到打印

    def _is_running(self) -> bool:
        """检查任务是否仍在运行 (通过信号转发器)。"""
        if self._signals and hasattr(self._signals, 'is_running'):
            return self._signals.is_running
        return True # 默认情况下，假定它正在运行

    def _emit_progress(self, value: int):
        """发出进度信号 (通过信号转发器)。"""
        if self._signals and hasattr(self._signals, 'progress') and hasattr(self._signals.progress, 'emit'):
            self._signals.progress.emit(value)

    def format_timecode(self, seconds_float: float) -> str:
        """将浮点数秒转换为SRT时间码格式 (HH:MM:SS,ms)。"""
        if not isinstance(seconds_float, (int, float)) or seconds_float < 0:
            return "00:00:00,000" # 无效输入处理
        total_seconds_int = int(seconds_float)
        milliseconds = int(round((seconds_float - total_seconds_int) * 1000))
        if milliseconds >= 1000: # 处理毫秒向上取整到1000的情况
            total_seconds_int += 1
            milliseconds = 0
        hours = total_seconds_int // 3600
        minutes = (total_seconds_int % 3600) // 60
        seconds = total_seconds_int % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def check_word_has_punctuation(self, word_text: str, punctuation_set: set) -> bool:
        """检查词语是否以指定标点集合中的任一标点结尾。"""
        cleaned_text = word_text.strip()
        if not cleaned_text:
            return False
        for punct in punctuation_set:
            if cleaned_text.endswith(punct):
                return True
        return False

    def get_segment_words_fuzzy(self, text_segment: str, all_parsed_words: List[TimestampedWord], start_search_index: int) -> tuple[List[TimestampedWord], int, float]:
        """
        使用模糊匹配从ASR词列表中找到与LLM文本片段最匹配的词序列。
        :param text_segment: LLM 返回的文本片段。
        :param all_parsed_words: 完整的ASR带时间戳词列表。
        :param start_search_index: 在ASR词列表中的起始搜索索引。
        :return: (匹配的词对象列表, 下一个搜索起始索引, 匹配比率)
        """
        segment_clean = text_segment.strip().replace(" ", "") # 清理LLM片段：去空格
        if not segment_clean:
            return [], start_search_index, 1.0 # 空片段直接返回

        best_match_words_ts_objects: List[TimestampedWord] = [] # 最佳匹配的词对象
        best_match_ratio = 0.0 # 最佳匹配比率
        best_match_end_index = start_search_index # 最佳匹配结束时的ASR索引

        # 根据片段长度动态调整搜索窗口大小 (启发式)
        search_window_size = len(segment_clean) * 3 + 20
        max_lookahead = min(start_search_index + search_window_size, len(all_parsed_words))

        for i in range(start_search_index, max_lookahead):
            current_words_text_list = [] # 当前尝试组合的ASR词文本列表
            current_word_ts_object_list: List[TimestampedWord] = [] # 当前尝试组合的ASR词对象列表
            # 限制 j 的前瞻范围，以构建候选ASR短语 (启发式)
            max_j_lookahead = min(i + search_window_size // 2 + 10, len(all_parsed_words))
            for j in range(i, max_j_lookahead):
                word_obj = all_parsed_words[j]
                current_word_ts_object_list.append(word_obj)
                current_words_text_list.append(word_obj.text.replace(" ", "")) # 规范化ASR词 (去空格)
                built_text = "".join(current_words_text_list) # 从ASR词构建的文本
                if not built_text.strip():
                    continue # 跳过空构建文本

                matcher = difflib.SequenceMatcher(None, segment_clean, built_text, autojunk=False) # 禁用自动丢弃垃圾数据
                ratio = matcher.ratio() # 计算相似度

                update_best = False
                if ratio > best_match_ratio:
                    update_best = True
                elif abs(ratio - best_match_ratio) < 1e-9 and best_match_words_ts_objects: # 如果比率相同 (使用浮点数比较容差)
                    # 优先选择 ASR 匹配文本长度更接近 LLM 片段长度的
                    current_len_diff = abs(len(built_text) - len(segment_clean))
                    best_len_diff = abs(len("".join(w.text.replace(" ","") for w in best_match_words_ts_objects)) - len(segment_clean))
                    if current_len_diff < best_len_diff:
                        update_best = True

                if update_best and ratio > 0: # 只有在有一定匹配度时才更新
                    best_match_ratio = ratio
                    best_match_words_ts_objects = list(current_word_ts_object_list) # 深拷贝
                    best_match_end_index = j + 1 # 下一个搜索的起始索引

                # 如果找到一个非常好的匹配并且ASR文本变得过长，则提前退出
                if ratio > 0.95 and len(built_text) > len(segment_clean) * 1.5:
                    break
        if not best_match_words_ts_objects: # 未找到任何匹配
            self.log(f"严重警告: LLM片段 \"{text_segment}\" (清理后: \"{segment_clean}\") 无法在ASR词语中找到任何匹配。将跳过此片段。搜索起始索引: {start_search_index}")
            return [], start_search_index, 0.0 # 返回空列表和0比率

        if best_match_ratio < ALIGNMENT_SIMILARITY_THRESHOLD: # 如果相似度低于阈值
            matched_text_preview = "".join([w.text for w in best_match_words_ts_objects])
            self.log(f"警告: LLM片段 \"{text_segment}\" (清理后: \"{segment_clean}\") 与ASR词语的对齐相似度较低 ({best_match_ratio:.2f})。ASR匹配文本: \"{matched_text_preview}\"")

        return best_match_words_ts_objects, best_match_end_index, best_match_ratio

    def split_long_sentence(self, sentence_text: str, sentence_words: List[TimestampedWord], original_start_time: float, original_end_time: float) -> List[SubtitleEntry]:
        """
        分割过长或字符数过多的句子。
        尝试在标点处分割，优先保证第一部分的最小持续时间。
        如果无法按标点有效分割，则将整个句子标记为“故意超限”。
        :param sentence_text: 完整的句子文本。
        :param sentence_words: 构成该句子的带时间戳的词对象列表。
        :param original_start_time: 原始句子的开始时间。
        :param original_end_time: 原始句子的结束时间。
        :return: 一个包含分割后（或未分割）的 SubtitleEntry 对象的列表。
        """
        # self.log(f"尝试分割长句: '{sentence_text}' (词数: {len(sentence_words)}, 时长: {original_end_time - original_start_time:.2f}s)")

        if len(sentence_words) <= 1: # 处理空或单字片段
            # self.log(f"  片段只有一个词或为空，不进行分割。")
            entry_to_return = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, sentence_words)
            if entry_to_return.duration < MIN_DURATION_ABSOLUTE: # 确保绝对最小持续时间
                entry_to_return.end_time = entry_to_return.start_time + MIN_DURATION_ABSOLUTE
            # 如果仍然超限（例如，非常长的单个词），则标记
            if entry_to_return.duration > MAX_DURATION or len(sentence_text) > MAX_CHARS_PER_LINE:
                 # self.log(f"警告: 单/无词长句仍超限: '{sentence_text}' (时长 {entry_to_return.duration:.2f}s, 字符 {len(sentence_text)})")
                 entry_to_return.is_intentionally_oversized = True
            return [entry_to_return]

        entries: List[SubtitleEntry] = [] # 存储分割后的字幕条目
        words_to_process = list(sentence_words) # 创建一个副本以进行修改

        while words_to_process:
            current_segment_text = "".join([w.text for w in words_to_process]) # 当前处理的片段文本
            if not words_to_process: break # 安全中断，如果列表意外变空
            current_segment_start_time = words_to_process[0].start_time
            current_segment_end_time = words_to_process[-1].end_time
            current_segment_duration = current_segment_end_time - current_segment_start_time
            current_segment_len_chars = len(current_segment_text)

            # 如果当前剩余片段在限制内，添加并结束此原始调用
            if current_segment_duration <= MAX_DURATION and current_segment_len_chars <= MAX_CHARS_PER_LINE:
                final_seg_end_time = current_segment_end_time
                # 如果需要，为最后一部分调整最小持续时间
                if current_segment_duration < MIN_DURATION_ABSOLUTE:
                    final_seg_end_time = current_segment_start_time + MIN_DURATION_ABSOLUTE
                elif current_segment_duration < MIN_DURATION_TARGET: # 注意这里是 TARGET
                    final_seg_end_time = current_segment_start_time + MIN_DURATION_TARGET
                entries.append(SubtitleEntry(0, current_segment_start_time, final_seg_end_time, current_segment_text, list(words_to_process)))
                # self.log(f"  剩余部分 '{current_segment_text[:30]}...' 已在限制内，添加为最终子片段。")
                break # 跳出 while 循环

            # --- 查找潜在和有效的分割点 ---
            potential_split_indices_by_priority = {'final': [], 'ellipsis': [], 'comma': []} # 按优先级存储潜在分割点
            num_words_in_current_chunk = len(words_to_process)

            for i in range(num_words_in_current_chunk):
                if i >= num_words_in_current_chunk - 1: continue # 确保分割后还有剩余部分

                word_obj_in_loop = words_to_process[i]
                word_text_in_loop = word_obj_in_loop.text

                if self.check_word_has_punctuation(word_text_in_loop, FINAL_PUNCTUATION):
                    potential_split_indices_by_priority['final'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, ELLIPSIS_PUNCTUATION):
                    potential_split_indices_by_priority['ellipsis'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, COMMA_PUNCTUATION):
                    potential_split_indices_by_priority['comma'].append(i)

            chosen_priority_indices: Optional[List[int]] = None
            # priority_level_debug_str = "无" # 用于日志记录
            if potential_split_indices_by_priority['final']:
                chosen_priority_indices = potential_split_indices_by_priority['final']
                # priority_level_debug_str = '句末标点'
            elif potential_split_indices_by_priority['ellipsis']:
                chosen_priority_indices = potential_split_indices_by_priority['ellipsis']
                # priority_level_debug_str = '省略号'
            elif potential_split_indices_by_priority['comma']:
                chosen_priority_indices = potential_split_indices_by_priority['comma']
                # priority_level_debug_str = '逗号'

            valid_split_points_info: List[tuple[int, int]] = [] # (索引, 第一段字符长度)
            if chosen_priority_indices:
                # self.log(f"  找到 {len(chosen_priority_indices)} 个潜在分割点 (优先级: {priority_level_debug_str})。检查有效性 (第一部分时长 >= {MIN_DURATION_TARGET}s)...")
                for idx in chosen_priority_indices:
                    first_segment_words = words_to_process[:idx + 1]
                    if not first_segment_words: continue

                    first_segment_start_time = first_segment_words[0].start_time
                    first_segment_end_time = first_segment_words[-1].end_time
                    first_segment_duration = first_segment_end_time - first_segment_start_time

                    if first_segment_duration >= MIN_DURATION_TARGET: # 检查第一部分是否满足目标最小时长
                        first_segment_char_len = len("".join(w.text for w in first_segment_words))
                        valid_split_points_info.append((idx, first_segment_char_len))
                        # self.log(f"    索引 {idx} 有效 (时长 {first_segment_duration:.2f}s, 长度 {first_segment_char_len})")
                    # else:
                        # self.log(f"    索引 {idx} 无效 (时长 {first_segment_duration:.2f}s < {MIN_DURATION_TARGET}s)")

            best_split_index = -1 # 最佳分割索引
            if valid_split_points_info:
                # self.log(f"  找到 {len(valid_split_points_info)} 个有效分割点。选择字符长度最接近原长一半的点...")
                target_char_len_half = current_segment_len_chars / 2.0 # 目标是分割后两部分长度尽量接近
                
                best_split_point_data = min(valid_split_points_info, key=lambda p_info: abs(p_info[1] - target_char_len_half))
                best_split_index = best_split_point_data[0]
                # self.log(f"  选择索引 {best_split_index} (第一部分长 {best_split_point_data[1]}, 目标半长 {target_char_len_half:.1f}) 作为最佳分割点。")


            # --- 处理分割或回退 ---
            if best_split_index != -1: # 找到了有效且最佳的分割点
                words_for_this_sub_entry = words_to_process[:best_split_index + 1]
                words_to_process = words_to_process[best_split_index + 1:] # 更新剩余待处理的词

                if not words_for_this_sub_entry: continue # 不应发生

                sub_text = "".join([w.text for w in words_for_this_sub_entry])
                sub_start_time = words_for_this_sub_entry[0].start_time
                sub_end_time = words_for_this_sub_entry[-1].end_time
                
                entries.append(SubtitleEntry(0, sub_start_time, sub_end_time, sub_text, words_used=words_for_this_sub_entry))
                # self.log(f"  分割出子片段: '{sub_text[:50]}...'")
            else: # 回退：未找到有效的分割点
                if chosen_priority_indices:
                     self.log(f"警告: 片段 '{current_segment_text[:30]}...' 找到潜在分割点，但所有分割都会导致第一部分时长 < {MIN_DURATION_TARGET}s。")
                # else:
                     # self.log(f"警告: 片段 '{current_segment_text[:30]}...' 无内部优先标点可供分割。")

                self.log(f"  将剩余部分 '{current_segment_text[:50]}...' 标记为 '故意超限' 并添加。")
                final_seg_end_time_fallback = current_segment_end_time
                if current_segment_duration < MIN_DURATION_ABSOLUTE: # 对整个未分割片段应用绝对最小时长
                    final_seg_end_time_fallback = current_segment_start_time + MIN_DURATION_ABSOLUTE

                entry = SubtitleEntry(0, current_segment_start_time, final_seg_end_time_fallback, current_segment_text, list(words_to_process))
                entry.is_intentionally_oversized = True # 标记
                if entry.duration > MAX_DURATION or len(entry.text) > MAX_CHARS_PER_LINE:
                    self.log(f"  (确认仍超限) 时长 {entry.duration:.2f}s, 字符 {len(entry.text)}")
                entries.append(entry)
                break # 退出 while 循环

            if not words_to_process: break # 如果没有更多词了，则退出
        return entries

    def process_to_srt(self, parsed_transcription: ParsedTranscription, llm_segments_text: List[str], signals_forwarder: Any) -> Optional[str]:
        """
        核心处理函数：将解析后的转录数据和LLM分割的文本转换为SRT格式。
        :param parsed_transcription: 解析后的ASR转录对象。
        :param llm_segments_text: LLM返回的文本片段列表。
        :param signals_forwarder: 用于日志和进度更新的信号转发器。
        :return: SRT格式的字符串，或在失败时返回None。
        """
        self._signals = signals_forwarder # 设置信号转发器
        self.log("--- 开始对齐 LLM 片段 ---")
        intermediate_entries: List[SubtitleEntry] = [] # 存储中间字幕条目
        word_search_start_index = 0 # ASR词列表的搜索起始索引
        unaligned_segments: List[str] = [] # 存储未能对齐的LLM片段

        all_parsed_words = parsed_transcription.words # 所有带时间戳的ASR词
        if not llm_segments_text:
            self.log("错误：LLM 未返回任何分割片段。")
            return None
        if not all_parsed_words:
            self.log("错误：解析后的词列表为空，无法进行对齐。")
            return None

        self.log(f"ASR共有 {len(all_parsed_words)} 个带时间戳的词。LLM返回 {len(llm_segments_text)} 个待对齐片段。")

        total_segments_to_align = len(llm_segments_text)
        for i, text_seg in enumerate(llm_segments_text): # 遍历LLM片段进行对齐
            if not self._is_running():
                self.log("任务被用户中断(对齐阶段)。")
                return None # 检查任务是否被中断
            self._emit_progress(int(10 + 30 * ((i + 1) / total_segments_to_align))) # 更新进度 (10% -> 40%)

            matched_words, next_search_idx, match_ratio = self.get_segment_words_fuzzy(text_seg, all_parsed_words, word_search_start_index)

            if not matched_words or match_ratio == 0: # 如果完全没有匹配
                unaligned_segments.append(text_seg)
                self.log(f"警告: LLM片段 \"{text_seg[:50]}...\" 未能在ASR词中找到匹配，已跳过。")
                continue # 跳过此片段

            word_search_start_index = next_search_idx # 更新下一次搜索的起始索引

            entry_text = "".join([w.text for w in matched_words]) # 从匹配的ASR词构建文本
            entry_start_time = matched_words[0].start_time
            entry_end_time = matched_words[-1].end_time
            entry_duration = entry_end_time - entry_start_time
            text_len = len(entry_text) # 使用匹配的ASR词的组合文本长度

            is_audio_event = all(not w.text.strip() or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in matched_words)

            if is_audio_event: # 如果是音频事件
                final_audio_event_end_time = entry_end_time
                if entry_duration < MIN_DURATION_ABSOLUTE:
                    final_audio_event_end_time = entry_start_time + MIN_DURATION_ABSOLUTE # 确保最小持续时间
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_audio_event_end_time, entry_text, matched_words, match_ratio))
            elif entry_duration > MAX_DURATION or text_len > MAX_CHARS_PER_LINE: # 如果片段超限
                self.log(f"片段超限，需分割: \"{entry_text[:50]}...\" (时长: {entry_duration:.2f}s, 字符: {text_len})")
                split_sub_entries = self.split_long_sentence(entry_text, matched_words, entry_start_time, entry_end_time) # 分割长句
                for sub_entry in split_sub_entries:
                    sub_entry.alignment_ratio = match_ratio # 保留原始对齐质量
                intermediate_entries.extend(split_sub_entries)
            elif entry_duration < MIN_DURATION_TARGET : # 如果太短，需要延长
                final_short_entry_end_time = entry_start_time + (MIN_DURATION_ABSOLUTE if entry_duration < MIN_DURATION_ABSOLUTE else MIN_DURATION_TARGET)
                max_allowed_extension = matched_words[-1].end_time + 0.5 # 限制最大延长
                final_short_entry_end_time = min(final_short_entry_end_time, max_allowed_extension)
                if final_short_entry_end_time <= entry_start_time:
                    final_short_entry_end_time = entry_start_time + 0.1 # 安全检查
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_short_entry_end_time, entry_text, matched_words, match_ratio))
            else: # 时长和长度都合适
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, entry_end_time, entry_text, matched_words, match_ratio))

        self.log("--- LLM片段对齐结束 ---")
        if unaligned_segments: # 记录未对齐的片段
            self.log(f"\n--- 以下 {len(unaligned_segments)} 个LLM片段未能成功对齐，已跳过 ---")
            for seg_idx, seg_text in enumerate(unaligned_segments):
                self.log(f"- 片段 {seg_idx+1}: \"{seg_text}\"")
            self.log("----------------------------------------\n")

        if not intermediate_entries:
            self.log("错误：对齐后没有生成任何有效的字幕条目。")
            return None

        self.log(f"--- 对齐后得到 {len(intermediate_entries)} 个初步字幕条目，开始合并和调整 ---")
        intermediate_entries.sort(key=lambda e: e.start_time) # 合并前确保按开始时间排序

        merged_entries: List[SubtitleEntry] = [] # 存储合并后的字幕条目
        i = 0
        total_intermediate_entries = len(intermediate_entries)
        while i < total_intermediate_entries:
            if not self._is_running():
                self.log("任务被用户中断(合并阶段)。")
                return None
            self._emit_progress(int(40 + 50 * ((i + 1) / total_intermediate_entries if total_intermediate_entries > 0 else 1))) # 更新进度 (40% -> 90%)

            current_entry_to_merge = intermediate_entries[i]
            merged_this_iteration = False # 标记当前条目是否已合并

            if i + 1 < len(intermediate_entries):
                next_entry = intermediate_entries[i+1]
                gap_between = next_entry.start_time - current_entry_to_merge.end_time # 两者间的间隙
                combined_text_len = len(current_entry_to_merge.text) + len(next_entry.text) + 1 # 合并后的文本长度 (+1 为空格)
                combined_duration = next_entry.end_time - current_entry_to_merge.start_time # 合并后的持续时间

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
                    merged_ratio = min(current_entry_to_merge.alignment_ratio, next_entry.alignment_ratio) # 取两者中较差的对齐比率

                    self.log(f"合并字幕: \"{current_entry_to_merge.text[:30]}...\" ({self.format_timecode(current_entry_to_merge.start_time)}-{self.format_timecode(current_entry_to_merge.end_time)}) 和 \"{next_entry.text[:30]}...\" ({self.format_timecode(next_entry.start_time)}-{self.format_timecode(next_entry.end_time)})")
                    merged_entries.append(SubtitleEntry(0, merged_start_time, merged_end_time, merged_text, merged_words, merged_ratio))
                    i += 2 # 跳过下一个条目，因为它已被合并
                    merged_this_iteration = True

            if not merged_this_iteration: # 如果没有合并，则直接添加当前条目
                merged_entries.append(current_entry_to_merge)
                i += 1
        self.log(f"--- 合并调整后得到 {len(merged_entries)} 个字幕条目，开始最终格式化 ---")

        final_srt_formatted_list: List[str] = [] # 存储最终格式化的SRT字符串列表
        last_processed_entry_object: Optional[SubtitleEntry] = None # 上一个处理的字幕对象
        subtitle_index = 1 # SRT字幕序号从1开始

        for entry_idx, current_entry in enumerate(merged_entries): # 遍历合并后的条目进行最终格式化
            if not self._is_running():
                self.log("任务被用户中断(最终格式化阶段)。")
                return None
            self._emit_progress(int(90 + 9 * ((entry_idx + 1) / len(merged_entries) if len(merged_entries) > 0 else 1) ))

            if last_processed_entry_object is not None:
                gap_seconds = DEFAULT_GAP_MS / 1000.0 # 默认间隙
                if current_entry.start_time < last_processed_entry_object.end_time + gap_seconds:
                    new_previous_end_time = current_entry.start_time - gap_seconds
                    min_duration_for_previous = 0.010 # 上一个字幕至少保留 10ms

                    if new_previous_end_time > last_processed_entry_object.start_time + min_duration_for_previous:
                        last_processed_entry_object.end_time = new_previous_end_time
                    else:
                        safe_previous_end_time = current_entry.start_time - 0.001 # 1ms 间隙
                        if safe_previous_end_time > last_processed_entry_object.start_time + min_duration_for_previous:
                            last_processed_entry_object.end_time = safe_previous_end_time

                    if final_srt_formatted_list: # 更新已添加到列表中的上一个字幕的SRT字符串
                        final_srt_formatted_list[-1] = last_processed_entry_object.to_srt_format(self) # `self` is SrtProcessor instance

            current_duration = current_entry.duration
            min_duration_to_apply: Optional[float] = None
            entry_is_audio_event = any(not w.text.strip() or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in current_entry.words_used)

            if not current_entry.is_intentionally_oversized and not entry_is_audio_event:
                if current_duration < MIN_DURATION_ABSOLUTE: min_duration_to_apply = MIN_DURATION_ABSOLUTE
                elif current_duration < MIN_DURATION_TARGET: min_duration_to_apply = MIN_DURATION_TARGET

            if min_duration_to_apply is not None: # 应用最小持续时间调整
                current_entry.end_time = max(current_entry.end_time, current_entry.start_time + min_duration_to_apply)

            if not current_entry.is_intentionally_oversized and current_entry.duration > MAX_DURATION:
                self.log(f"字幕 \"{current_entry.text[:30]}...\" 时长 {current_entry.duration:.2f}s 超出最大值 {MAX_DURATION}s，将被截断。")
                current_entry.end_time = current_entry.start_time + MAX_DURATION
            
            if current_entry.end_time <= current_entry.start_time: # 安全检查
                 current_entry.end_time = current_entry.start_time + 0.001 # 至少1ms

            current_entry.index = subtitle_index # 设置字幕序号
            final_srt_formatted_list.append(current_entry.to_srt_format(self)) # `self` is SrtProcessor instance
            last_processed_entry_object = current_entry # 更新上一个处理的字幕对象
            subtitle_index += 1

        self.log("--- SRT 内容生成和格式化完成 ---")
        return "".join(final_srt_formatted_list).strip() # 合并所有SRT条目并去除首尾空格