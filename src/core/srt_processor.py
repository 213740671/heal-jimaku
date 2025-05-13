# src/core/srt_processor.py
import re
import difflib
from typing import List, Optional, Any

from core.data_models import TimestampedWord, ParsedTranscription, SubtitleEntry
# 从config导入硬性下限和标点等，但时长/字符数等参数将通过方法传入
from config import (
    MIN_DURATION_ABSOLUTE, # 这个仍然作为硬性下限
    ALIGNMENT_SIMILARITY_THRESHOLD,
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
            print(f"[SRT Processor] {message}")

    def _is_running(self) -> bool:
        """检查任务是否仍在运行 (通过信号转发器)。"""
        if self._signals and hasattr(self._signals, 'is_running'):
            return self._signals.is_running
        return True

    def _emit_progress(self, value: int):
        """发出进度信号 (通过信号转发器)。"""
        if self._signals and hasattr(self._signals, 'progress') and hasattr(self._signals.progress, 'emit'):
            self._signals.progress.emit(value)

    def format_timecode(self, seconds_float: float) -> str:
        """将浮点数秒转换为SRT时间码格式 (HH:MM:SS,ms)。"""
        if not isinstance(seconds_float, (int, float)) or seconds_float < 0:
            return "00:00:00,000"
        total_seconds_int = int(seconds_float)
        milliseconds = int(round((seconds_float - total_seconds_int) * 1000))
        if milliseconds >= 1000:
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
        segment_clean = text_segment.strip().replace(" ", "")
        if not segment_clean:
            return [], start_search_index, 1.0

        best_match_words_ts_objects: List[TimestampedWord] = []
        best_match_ratio = 0.0
        best_match_end_index = start_search_index

        search_window_size = len(segment_clean) * 3 + 20
        max_lookahead = min(start_search_index + search_window_size, len(all_parsed_words))

        for i in range(start_search_index, max_lookahead):
            current_words_text_list = []
            current_word_ts_object_list: List[TimestampedWord] = []
            max_j_lookahead = min(i + search_window_size // 2 + 10, len(all_parsed_words))
            for j in range(i, max_j_lookahead):
                word_obj = all_parsed_words[j]
                current_word_ts_object_list.append(word_obj)
                current_words_text_list.append(word_obj.text.replace(" ", ""))
                built_text = "".join(current_words_text_list)
                if not built_text.strip():
                    continue

                matcher = difflib.SequenceMatcher(None, segment_clean, built_text, autojunk=False)
                ratio = matcher.ratio()

                update_best = False
                if ratio > best_match_ratio:
                    update_best = True
                elif abs(ratio - best_match_ratio) < 1e-9 and best_match_words_ts_objects:
                    current_len_diff = abs(len(built_text) - len(segment_clean))
                    best_len_diff = abs(len("".join(w.text.replace(" ","") for w in best_match_words_ts_objects)) - len(segment_clean))
                    if current_len_diff < best_len_diff:
                        update_best = True

                if update_best and ratio > 0:
                    best_match_ratio = ratio
                    best_match_words_ts_objects = list(current_word_ts_object_list)
                    best_match_end_index = j + 1

                if ratio > 0.95 and len(built_text) > len(segment_clean) * 1.5:
                    break
        if not best_match_words_ts_objects:
            self.log(f"严重警告: LLM片段 \"{text_segment}\" (清理后: \"{segment_clean}\") 无法在ASR词语中找到任何匹配。将跳过此片段。搜索起始索引: {start_search_index}")
            return [], start_search_index, 0.0

        if best_match_ratio < ALIGNMENT_SIMILARITY_THRESHOLD:
            matched_text_preview = "".join([w.text for w in best_match_words_ts_objects])
            self.log(f"警告: LLM片段 \"{text_segment}\" (清理后: \"{segment_clean}\") 与ASR词语的对齐相似度较低 ({best_match_ratio:.2f})。ASR匹配文本: \"{matched_text_preview}\"")

        return best_match_words_ts_objects, best_match_end_index, best_match_ratio

    def split_long_sentence(self, sentence_text: str, sentence_words: List[TimestampedWord],
                            original_start_time: float, original_end_time: float,
                            # 新增参数
                            min_duration_target: float, max_duration: float, max_chars_per_line: int
                           ) -> List[SubtitleEntry]:
        if len(sentence_words) <= 1:
            entry_to_return = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, sentence_words)
            if entry_to_return.duration < MIN_DURATION_ABSOLUTE: # 使用硬性下限
                entry_to_return.end_time = entry_to_return.start_time + MIN_DURATION_ABSOLUTE
            if entry_to_return.duration > max_duration or len(sentence_text) > max_chars_per_line: # 使用传入参数
                 entry_to_return.is_intentionally_oversized = True
            return [entry_to_return]

        entries: List[SubtitleEntry] = []
        words_to_process = list(sentence_words)

        while words_to_process:
            current_segment_text = "".join([w.text for w in words_to_process])
            if not words_to_process: break
            current_segment_start_time = words_to_process[0].start_time
            current_segment_end_time = words_to_process[-1].end_time
            current_segment_duration = current_segment_end_time - current_segment_start_time
            current_segment_len_chars = len(current_segment_text)

            if current_segment_duration <= max_duration and current_segment_len_chars <= max_chars_per_line: # 使用传入参数
                final_seg_end_time = current_segment_end_time
                if current_segment_duration < MIN_DURATION_ABSOLUTE: # 硬性下限
                    final_seg_end_time = current_segment_start_time + MIN_DURATION_ABSOLUTE
                elif current_segment_duration < min_duration_target: # 使用传入参数
                    final_seg_end_time = current_segment_start_time + min_duration_target
                entries.append(SubtitleEntry(0, current_segment_start_time, final_seg_end_time, current_segment_text, list(words_to_process)))
                break

            potential_split_indices_by_priority = {'final': [], 'ellipsis': [], 'comma': []}
            num_words_in_current_chunk = len(words_to_process)

            for i in range(num_words_in_current_chunk):
                if i >= num_words_in_current_chunk - 1: continue
                word_obj_in_loop = words_to_process[i]
                word_text_in_loop = word_obj_in_loop.text
                if self.check_word_has_punctuation(word_text_in_loop, FINAL_PUNCTUATION):
                    potential_split_indices_by_priority['final'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, ELLIPSIS_PUNCTUATION):
                    potential_split_indices_by_priority['ellipsis'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, COMMA_PUNCTUATION):
                    potential_split_indices_by_priority['comma'].append(i)

            chosen_priority_indices: Optional[List[int]] = None
            if potential_split_indices_by_priority['final']:
                chosen_priority_indices = potential_split_indices_by_priority['final']
            elif potential_split_indices_by_priority['ellipsis']:
                chosen_priority_indices = potential_split_indices_by_priority['ellipsis']
            elif potential_split_indices_by_priority['comma']:
                chosen_priority_indices = potential_split_indices_by_priority['comma']

            valid_split_points_info: List[tuple[int, int]] = []
            if chosen_priority_indices:
                for idx in chosen_priority_indices:
                    first_segment_words = words_to_process[:idx + 1]
                    if not first_segment_words: continue
                    first_segment_start_time = first_segment_words[0].start_time
                    first_segment_end_time = first_segment_words[-1].end_time
                    first_segment_duration = first_segment_end_time - first_segment_start_time
                    if first_segment_duration >= min_duration_target: # 使用传入参数
                        first_segment_char_len = len("".join(w.text for w in first_segment_words))
                        valid_split_points_info.append((idx, first_segment_char_len))

            best_split_index = -1
            if valid_split_points_info:
                target_char_len_half = current_segment_len_chars / 2.0
                best_split_point_data = min(valid_split_points_info, key=lambda p_info: abs(p_info[1] - target_char_len_half))
                best_split_index = best_split_point_data[0]

            if best_split_index != -1:
                words_for_this_sub_entry = words_to_process[:best_split_index + 1]
                words_to_process = words_to_process[best_split_index + 1:]
                if not words_for_this_sub_entry: continue
                sub_text = "".join([w.text for w in words_for_this_sub_entry])
                sub_start_time = words_for_this_sub_entry[0].start_time
                sub_end_time = words_for_this_sub_entry[-1].end_time
                entries.append(SubtitleEntry(0, sub_start_time, sub_end_time, sub_text, words_used=words_for_this_sub_entry))
            else:
                if chosen_priority_indices:
                     self.log(f"警告: 片段 '{current_segment_text[:30]}...' 找到潜在分割点，但所有分割都会导致第一部分时长 < {min_duration_target}s。") # 使用传入参数
                final_seg_end_time_fallback = current_segment_end_time
                if current_segment_duration < MIN_DURATION_ABSOLUTE: # 硬性下限
                    final_seg_end_time_fallback = current_segment_start_time + MIN_DURATION_ABSOLUTE
                entry = SubtitleEntry(0, current_segment_start_time, final_seg_end_time_fallback, current_segment_text, list(words_to_process))
                entry.is_intentionally_oversized = True
                if entry.duration > max_duration or len(entry.text) > max_chars_per_line: # 使用传入参数
                    self.log(f"  (确认仍超限) 时长 {entry.duration:.2f}s, 字符 {len(entry.text)}")
                entries.append(entry)
                break
            if not words_to_process: break
        return entries

    def process_to_srt(self, parsed_transcription: ParsedTranscription,
                       llm_segments_text: List[str], signals_forwarder: Any,
                       # 新增参数
                       min_duration_target: float,
                       max_duration: float,
                       max_chars_per_line: int,
                       default_gap_ms: int
                      ) -> Optional[str]:
        self._signals = signals_forwarder
        self.log("--- 开始对齐 LLM 片段 ---")
        intermediate_entries: List[SubtitleEntry] = []
        word_search_start_index = 0
        unaligned_segments: List[str] = []

        all_parsed_words = parsed_transcription.words
        if not llm_segments_text:
            self.log("错误：LLM 未返回任何分割片段。")
            return None
        if not all_parsed_words:
            self.log("错误：解析后的词列表为空，无法进行对齐。")
            return None

        self.log(f"ASR共有 {len(all_parsed_words)} 个带时间戳的词。LLM返回 {len(llm_segments_text)} 个待对齐片段。")
        self.log(f"SRT参数: min_target_dur={min_duration_target}, max_dur={max_duration}, max_chars={max_chars_per_line}, gap_ms={default_gap_ms}")


        total_segments_to_align = len(llm_segments_text)
        for i, text_seg in enumerate(llm_segments_text):
            if not self._is_running():
                self.log("任务被用户中断(对齐阶段)。")
                return None
            self._emit_progress(int(10 + 30 * ((i + 1) / total_segments_to_align)))

            matched_words, next_search_idx, match_ratio = self.get_segment_words_fuzzy(text_seg, all_parsed_words, word_search_start_index)

            if not matched_words or match_ratio == 0:
                unaligned_segments.append(text_seg)
                self.log(f"警告: LLM片段 \"{text_seg[:50]}...\" 未能在ASR词中找到匹配，已跳过。")
                continue

            word_search_start_index = next_search_idx
            entry_text = "".join([w.text for w in matched_words])
            entry_start_time = matched_words[0].start_time
            entry_end_time = matched_words[-1].end_time
            entry_duration = entry_end_time - entry_start_time
            text_len = len(entry_text)

            is_audio_event = all(not w.text.strip() or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in matched_words)

            if is_audio_event:
                final_audio_event_end_time = entry_end_time
                if entry_duration < MIN_DURATION_ABSOLUTE: # 硬性下限
                    final_audio_event_end_time = entry_start_time + MIN_DURATION_ABSOLUTE
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_audio_event_end_time, entry_text, matched_words, match_ratio))
            elif entry_duration > max_duration or text_len > max_chars_per_line: # 使用传入参数
                self.log(f"片段超限，需分割: \"{entry_text[:50]}...\" (时长: {entry_duration:.2f}s, 字符: {text_len})")
                split_sub_entries = self.split_long_sentence(
                    entry_text, matched_words, entry_start_time, entry_end_time,
                    min_duration_target, max_duration, max_chars_per_line # 传递参数
                )
                for sub_entry in split_sub_entries:
                    sub_entry.alignment_ratio = match_ratio
                intermediate_entries.extend(split_sub_entries)
            elif entry_duration < min_duration_target : # 使用传入参数
                final_short_entry_end_time = entry_start_time + (MIN_DURATION_ABSOLUTE if entry_duration < MIN_DURATION_ABSOLUTE else min_duration_target)
                max_allowed_extension = matched_words[-1].end_time + 0.5
                final_short_entry_end_time = min(final_short_entry_end_time, max_allowed_extension)
                if final_short_entry_end_time <= entry_start_time:
                    final_short_entry_end_time = entry_start_time + 0.1
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_short_entry_end_time, entry_text, matched_words, match_ratio))
            else:
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, entry_end_time, entry_text, matched_words, match_ratio))

        self.log("--- LLM片段对齐结束 ---")
        if unaligned_segments:
            self.log(f"\n--- 以下 {len(unaligned_segments)} 个LLM片段未能成功对齐，已跳过 ---")
            for seg_idx, seg_text in enumerate(unaligned_segments):
                self.log(f"- 片段 {seg_idx+1}: \"{seg_text}\"")
            self.log("----------------------------------------\n")

        if not intermediate_entries:
            self.log("错误：对齐后没有生成任何有效的字幕条目。")
            return None

        self.log(f"--- 对齐后得到 {len(intermediate_entries)} 个初步字幕条目，开始合并和调整 ---")
        intermediate_entries.sort(key=lambda e: e.start_time)

        merged_entries: List[SubtitleEntry] = []
        i = 0
        total_intermediate_entries = len(intermediate_entries)
        while i < total_intermediate_entries:
            if not self._is_running():
                self.log("任务被用户中断(合并阶段)。")
                return None
            self._emit_progress(int(40 + 50 * ((i + 1) / total_intermediate_entries if total_intermediate_entries > 0 else 1)))

            current_entry_to_merge = intermediate_entries[i]
            merged_this_iteration = False

            if i + 1 < len(intermediate_entries):
                next_entry = intermediate_entries[i+1]
                gap_between = next_entry.start_time - current_entry_to_merge.end_time
                combined_text_len = len(current_entry_to_merge.text) + len(next_entry.text) + 1
                combined_duration = next_entry.end_time - current_entry_to_merge.start_time

                next_is_audio_event = any(not w.text.strip() or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in next_entry.words_used)

                # 使用传入参数进行判断
                if current_entry_to_merge.duration < min_duration_target and \
                   not next_is_audio_event and \
                   combined_text_len <= max_chars_per_line and \
                   combined_duration <= max_duration and \
                   gap_between < 0.5 and \
                   combined_duration >= min_duration_target :

                    merged_text = current_entry_to_merge.text + " " + next_entry.text
                    merged_start_time = current_entry_to_merge.start_time
                    merged_end_time = next_entry.end_time
                    merged_words = current_entry_to_merge.words_used + next_entry.words_used
                    merged_ratio = min(current_entry_to_merge.alignment_ratio, next_entry.alignment_ratio)

                    self.log(f"合并字幕: \"{current_entry_to_merge.text[:30]}...\" 和 \"{next_entry.text[:30]}...\"")
                    merged_entries.append(SubtitleEntry(0, merged_start_time, merged_end_time, merged_text, merged_words, merged_ratio))
                    i += 2
                    merged_this_iteration = True

            if not merged_this_iteration:
                merged_entries.append(current_entry_to_merge)
                i += 1
        self.log(f"--- 合并调整后得到 {len(merged_entries)} 个字幕条目，开始最终格式化 ---")

        final_srt_formatted_list: List[str] = []
        last_processed_entry_object: Optional[SubtitleEntry] = None
        subtitle_index = 1

        for entry_idx, current_entry in enumerate(merged_entries):
            if not self._is_running():
                self.log("任务被用户中断(最终格式化阶段)。")
                return None
            self._emit_progress(int(90 + 9 * ((entry_idx + 1) / len(merged_entries) if len(merged_entries) > 0 else 1) ))

            if last_processed_entry_object is not None:
                gap_seconds = default_gap_ms / 1000.0 # 使用传入参数
                if current_entry.start_time < last_processed_entry_object.end_time + gap_seconds:
                    new_previous_end_time = current_entry.start_time - gap_seconds
                    min_duration_for_previous = 0.010

                    if new_previous_end_time > last_processed_entry_object.start_time + min_duration_for_previous:
                        last_processed_entry_object.end_time = new_previous_end_time
                    else:
                        safe_previous_end_time = current_entry.start_time - 0.001
                        if safe_previous_end_time > last_processed_entry_object.start_time + min_duration_for_previous:
                            last_processed_entry_object.end_time = safe_previous_end_time

                    if final_srt_formatted_list:
                        final_srt_formatted_list[-1] = last_processed_entry_object.to_srt_format(self)

            current_duration = current_entry.duration
            min_duration_to_apply_val: Optional[float] = None # 重命名以避免与参数冲突
            entry_is_audio_event = any(not w.text.strip() or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in current_entry.words_used)

            if not current_entry.is_intentionally_oversized and not entry_is_audio_event:
                if current_duration < MIN_DURATION_ABSOLUTE: min_duration_to_apply_val = MIN_DURATION_ABSOLUTE # 硬性下限
                elif current_duration < min_duration_target: min_duration_to_apply_val = min_duration_target # 使用传入参数

            if min_duration_to_apply_val is not None:
                current_entry.end_time = max(current_entry.end_time, current_entry.start_time + min_duration_to_apply_val)

            if not current_entry.is_intentionally_oversized and current_entry.duration > max_duration: # 使用传入参数
                self.log(f"字幕 \"{current_entry.text[:30]}...\" 时长 {current_entry.duration:.2f}s 超出最大值 {max_duration}s，将被截断。")
                current_entry.end_time = current_entry.start_time + max_duration # 使用传入参数
            
            if current_entry.end_time <= current_entry.start_time:
                 current_entry.end_time = current_entry.start_time + 0.001

            current_entry.index = subtitle_index
            final_srt_formatted_list.append(current_entry.to_srt_format(self))
            last_processed_entry_object = current_entry
            subtitle_index += 1

        self.log("--- SRT 内容生成和格式化完成 ---")
        return "".join(final_srt_formatted_list).strip()