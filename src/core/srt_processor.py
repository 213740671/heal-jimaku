# src/core/srt_processor.py

import re
import difflib
from typing import List, Optional, Any

from PyQt6.QtCore import QObject, pyqtSignal # 确保导入 QObject 和 pyqtSignal

from core.data_models import TimestampedWord, ParsedTranscription, SubtitleEntry
from config import (
    MIN_DURATION_ABSOLUTE,
    ALIGNMENT_SIMILARITY_THRESHOLD,
    FINAL_PUNCTUATION, ELLIPSIS_PUNCTUATION, COMMA_PUNCTUATION
)


class SrtProcessor:
    def __init__(self):
        self._signals: Optional[Any] = None
        self._current_progress_offset: int = 0
        self._current_progress_range: int = 100 

    def log(self, message: str):
        if self._signals and hasattr(self._signals, 'log_message') and hasattr(self._signals.log_message, 'emit'):
            self._signals.log_message.emit(f"[SRT Processor] {message}")
        else:
            print(f"[SRT Processor] {message}")

    def _is_worker_running(self) -> bool: 
        if self._signals and hasattr(self._signals, 'parent') and \
           hasattr(self._signals.parent(), 'is_running'): 
            return self._signals.parent().is_running
        return True

    def _emit_srt_progress(self, current_step: int, total_steps: int):
        """
        SrtProcessor 内部调用，基于已完成的步骤和总预估步骤。
        current_step 是从1开始的累积步骤。
        total_steps 是 SrtProcessor 内部的总预估操作数。
        """
        if total_steps == 0:
            internal_percentage = 100
        else:
            internal_percentage = min(int((current_step / total_steps) * 100), 100)
        
        if self._signals and hasattr(self._signals, 'progress') and hasattr(self._signals.progress, 'emit'):
            global_progress = self._current_progress_offset + int(internal_percentage * (self._current_progress_range / 100.0))
            capped_progress = min(max(global_progress, self._current_progress_offset), self._current_progress_offset + self._current_progress_range)
            capped_progress = min(capped_progress, 99) 
            self._signals.progress.emit(capped_progress)

    def format_timecode(self, seconds_float: float) -> str:
        if not isinstance(seconds_float, (int, float)) or seconds_float < 0:
            return "00:00:00,000"
        total_seconds_int = int(seconds_float)
        milliseconds = int(round((seconds_float - total_seconds_int) * 1000))
        if milliseconds >= 1000: # 处理四舍五入到1000ms的情况
            total_seconds_int += 1
            milliseconds = 0
        hours = total_seconds_int // 3600
        minutes = (total_seconds_int % 3600) // 60
        seconds = total_seconds_int % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def check_word_has_punctuation(self, word_text: str, punctuation_set: set) -> bool:
        cleaned_text = word_text.strip()
        if not cleaned_text:
            return False
        for punct in punctuation_set:
            if cleaned_text.endswith(punct):
                return True
        return False

    def get_segment_words_fuzzy(self, text_segment: str, all_parsed_words: List[TimestampedWord], start_search_index: int) -> tuple[List[TimestampedWord], int, float]:
        segment_clean = text_segment.strip().replace(" ", "")
        if not segment_clean: # 如果LLM片段清理后为空（例如LLM返回了纯空格的片段）
            return [], start_search_index, 0.0 # 返回无匹配

        best_match_words_ts_objects: List[TimestampedWord] = []
        best_match_ratio = 0.0
        best_match_end_index = start_search_index

        # 动态调整搜索窗口大小，基于清理后的LLM片段长度
        # 基本思路：窗口大小 = (片段长度 * 一个倍数) + 一个固定偏移量
        # 倍数可以大一些以容纳ASR可能的冗余或缺失，偏移量保证即使短片段也有足够的搜索范围
        base_len_factor = 3 
        min_additional_words = 20 # 至少额外看20个词
        max_additional_words = 60 # 最多额外看60个词（避免过长片段导致窗口过大）
        
        # 搜索窗口大小的计算，更依赖于LLM片段的词数而非字符数，但我们只有字符数
        # 我们可以假设平均词长，或者直接用一个更动态的因子
        estimated_words_in_segment = len(text_segment.split()) # 粗略估计词数
        search_window_size = len(segment_clean) * base_len_factor + min(max(estimated_words_in_segment * 2, min_additional_words), max_additional_words)
        
        max_lookahead_outer = min(start_search_index + search_window_size, len(all_parsed_words))

        for i in range(start_search_index, max_lookahead_outer):
            if not self._is_worker_running(): break # 提前退出

            current_words_text_list = []
            current_word_ts_object_list: List[TimestampedWord] = []
            # 内部循环的lookahead也应该有所限制，例如基于segment_clean的长度
            # 避免构建一个比 segment_clean 长很多的 built_text 来进行比较
            # +30 是一个缓冲，允许ASR结果比LLM片段稍长一些
            max_j_lookahead = min(i + len(segment_clean) + 30, len(all_parsed_words)) 
            
            for j in range(i, max_j_lookahead):
                word_obj = all_parsed_words[j]
                current_word_ts_object_list.append(word_obj)
                # 在构建built_text时，我们也去除空格，以匹配segment_clean
                current_words_text_list.append(word_obj.text.replace(" ", "")) 
                built_text = "".join(current_words_text_list)
                
                if not built_text.strip(): # 如果当前构建的文本为空或只有空格，则继续
                    continue

                matcher = difflib.SequenceMatcher(None, segment_clean, built_text, autojunk=False)
                ratio = matcher.ratio()

                update_best = False
                if ratio > best_match_ratio:
                    update_best = True
                # 如果相似度几乎相同，优先选择长度更接近的匹配
                elif abs(ratio - best_match_ratio) < 1e-9: 
                    if best_match_words_ts_objects: 
                        current_len_diff = abs(len(built_text) - len(segment_clean))
                        best_len_diff = abs(len("".join(w.text.replace(" ","") for w in best_match_words_ts_objects)) - len(segment_clean))
                        if current_len_diff < best_len_diff:
                            update_best = True
                    else: # 如果之前没有最佳匹配，当前的就是最佳的
                        update_best = True
                
                if update_best and ratio > 0.01 : # 只有当ratio有意义时才更新（例如大于一个很小的值）
                    best_match_ratio = ratio
                    best_match_words_ts_objects = list(current_word_ts_object_list) 
                    best_match_end_index = j + 1

                # 相似度非常高，但匹配的ASR文本比LLM片段长太多，可能匹配过头了，提前中断内部循环
                if ratio > 0.95 and len(built_text) > len(segment_clean) * 1.8: # 1.8倍作为阈值
                    break 
            
            # 如果当前i开头的搜索已经找到了非常好的匹配 (例如 > 0.98)，可以提前结束外层循环
            if best_match_ratio > 0.98 : 
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
                            min_duration_target: float, max_duration: float, max_chars_per_line: int
                           ) -> List[SubtitleEntry]:
        # (此方法内部逻辑与您仓库中的版本一致，此处不再重复，确保它是最新的)
        if not sentence_words: # 如果传入的词列表为空，直接返回空列表或基于sentence_text的单个条目
            if sentence_text.strip(): # 如果只有文本，没有词
                self.log(f"警告: split_long_sentence 收到空词列表但有文本: \"{sentence_text}\"。将尝试创建单个条目。")
                entry = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, [])
                if entry.duration < MIN_DURATION_ABSOLUTE: entry.end_time = entry.start_time + MIN_DURATION_ABSOLUTE
                if entry.duration > max_duration or len(sentence_text) > max_chars_per_line:
                    entry.is_intentionally_oversized = True
                return [entry]
            return []


        if len(sentence_words) <= 1:
            entry_to_return = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, sentence_words)
            if entry_to_return.duration < MIN_DURATION_ABSOLUTE:
                entry_to_return.end_time = entry_to_return.start_time + MIN_DURATION_ABSOLUTE
            if entry_to_return.duration > max_duration or len(sentence_text) > max_chars_per_line:
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

            if current_segment_duration <= max_duration and current_segment_len_chars <= max_chars_per_line:
                final_seg_end_time = current_segment_end_time
                if current_segment_duration < min_duration_target:
                    final_seg_end_time = current_segment_start_time + min_duration_target
                if current_segment_duration < MIN_DURATION_ABSOLUTE:
                     final_seg_end_time = current_segment_start_time + MIN_DURATION_ABSOLUTE
                final_seg_end_time = max(final_seg_end_time, current_segment_end_time)
                final_seg_end_time = max(final_seg_end_time, current_segment_start_time + 0.001)
                entries.append(SubtitleEntry(0, current_segment_start_time, final_seg_end_time, current_segment_text, list(words_to_process)))
                break 

            potential_split_indices_by_priority = {'final': [], 'ellipsis': [], 'comma': []}
            num_words_in_current_chunk = len(words_to_process)
            for i in range(num_words_in_current_chunk -1):
                word_obj_in_loop = words_to_process[i]
                word_text_in_loop = word_obj_in_loop.text
                if self.check_word_has_punctuation(word_text_in_loop, FINAL_PUNCTUATION):
                    potential_split_indices_by_priority['final'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, ELLIPSIS_PUNCTUATION):
                    potential_split_indices_by_priority['ellipsis'].append(i)
                elif self.check_word_has_punctuation(word_text_in_loop, COMMA_PUNCTUATION):
                    potential_split_indices_by_priority['comma'].append(i)

            chosen_priority_indices: Optional[List[int]] = None
            if potential_split_indices_by_priority['final']: chosen_priority_indices = potential_split_indices_by_priority['final']
            elif potential_split_indices_by_priority['ellipsis']: chosen_priority_indices = potential_split_indices_by_priority['ellipsis']
            elif potential_split_indices_by_priority['comma']: chosen_priority_indices = potential_split_indices_by_priority['comma']

            valid_split_points_info: List[tuple[int, int, float]] = []
            if chosen_priority_indices:
                for idx in chosen_priority_indices:
                    first_segment_words = words_to_process[:idx + 1]
                    if not first_segment_words: continue
                    first_segment_start_time = first_segment_words[0].start_time
                    first_segment_end_time = first_segment_words[-1].end_time
                    first_segment_duration = first_segment_end_time - first_segment_start_time
                    first_segment_char_len = len("".join(w.text for w in first_segment_words))
                    if first_segment_duration >= min_duration_target and \
                       first_segment_duration <= max_duration and \
                       first_segment_char_len <= max_chars_per_line:
                        valid_split_points_info.append((idx, first_segment_char_len, first_segment_duration))
            
            best_split_index = -1
            if valid_split_points_info:
                target_char_len_half = current_segment_len_chars / 2.0
                best_split_point_data = min(valid_split_points_info, key=lambda p_info: abs(p_info[1] - target_char_len_half))
                best_split_index = best_split_point_data[0]

            if best_split_index != -1:
                words_for_this_sub_entry = words_to_process[:best_split_index + 1]
                sub_text = "".join([w.text for w in words_for_this_sub_entry])
                sub_start_time = words_for_this_sub_entry[0].start_time
                sub_end_time = words_for_this_sub_entry[-1].end_time
                if (sub_end_time - sub_start_time) < min_duration_target: sub_end_time = sub_start_time + min_duration_target
                if (sub_end_time - sub_start_time) < MIN_DURATION_ABSOLUTE: sub_end_time = sub_start_time + MIN_DURATION_ABSOLUTE
                sub_end_time = max(sub_end_time, words_for_this_sub_entry[-1].end_time)
                sub_end_time = max(sub_end_time, sub_start_time + 0.001)
                entries.append(SubtitleEntry(0, sub_start_time, sub_end_time, sub_text, words_used=words_for_this_sub_entry))
                words_to_process = words_to_process[best_split_index + 1:]
            else: 
                self.log(f"警告: 无法在片段 '{current_segment_text[:50]}...' 中找到满足所有条件的分割点。将其作为一个（可能超限的）条目处理。")
                final_seg_end_time_fallback = current_segment_end_time
                if current_segment_duration < min_duration_target: final_seg_end_time_fallback = current_segment_start_time + min_duration_target
                if current_segment_duration < MIN_DURATION_ABSOLUTE: final_seg_end_time_fallback = current_segment_start_time + MIN_DURATION_ABSOLUTE
                final_seg_end_time_fallback = max(final_seg_end_time_fallback, current_segment_end_time)
                final_seg_end_time_fallback = max(final_seg_end_time_fallback, current_segment_start_time + 0.001)
                entry = SubtitleEntry(0, current_segment_start_time, final_seg_end_time_fallback, current_segment_text, list(words_to_process))
                entry.is_intentionally_oversized = True 
                if entry.duration > max_duration or len(entry.text) > max_chars_per_line:
                     self.log(f"  (确认仍超限) 时长 {entry.duration:.2f}s ({max_duration}s限制), 字符 {len(entry.text)} ({max_chars_per_line}限制)")
                entries.append(entry)
                break 
            
            if not words_to_process: break 
        return entries

    def process_to_srt(self, parsed_transcription: ParsedTranscription,
                       llm_segments_text: List[str], signals_forwarder: Any,
                       progress_offset: int, progress_range: int,
                       min_duration_target: float, max_duration: float,
                       max_chars_per_line: int, default_gap_ms: int
                      ) -> Optional[str]:
        self._signals = signals_forwarder
        self._current_progress_offset = progress_offset
        self._current_progress_range = progress_range
        
        self.log("--- 开始对齐 LLM 片段 (SrtProcessor) ---")
        intermediate_entries: List[SubtitleEntry] = []
        word_search_start_index = 0
        unaligned_segments: List[str] = []
        all_parsed_words = parsed_transcription.words

        if not llm_segments_text: self.log("错误：LLM 未返回任何分割片段。"); return None
        if not all_parsed_words: self.log("错误：解析后的词列表为空，无法进行对齐。"); return None
        
        total_llm_segments = len(llm_segments_text)
        
        WEIGHT_ALIGN = 40
        WEIGHT_MERGE = 30
        WEIGHT_FORMAT = 30
        
        completed_steps_phase1 = 0
        
        self.log("SRT阶段1: 对齐LLM片段...")
        for i, text_seg_from_llm in enumerate(llm_segments_text): # Renamed to avoid confusion
            if not self._is_worker_running(): self.log("任务被用户中断(对齐阶段)。"); return None
            
            self.log(f"  对齐LLM片段 {i+1}/{total_llm_segments}: \"{text_seg_from_llm[:30]}...\"")
            matched_words, next_search_idx, match_ratio = self.get_segment_words_fuzzy(text_seg_from_llm, all_parsed_words, word_search_start_index)
            
            if not matched_words or match_ratio == 0:
                unaligned_segments.append(text_seg_from_llm)
                # self.log(f"警告: LLM片段 \"{text_seg_from_llm[:50]}...\" 未能在ASR词中找到匹配，已跳过。") # get_segment_words_fuzzy会打印更详细的
                completed_steps_phase1 += 1
                self._emit_srt_progress(int( (completed_steps_phase1 / total_llm_segments) * WEIGHT_ALIGN ), 100)
                continue

            word_search_start_index = next_search_idx
            
            # --- 新的时间戳确定方式 ---
            first_actual_word_index = -1
            for idx_fw, word_obj_fw in enumerate(matched_words):
                # Check for non-empty stripped text and type is not 'spacing'
                # For ElevenLabs, "type": "spacing" or "text": " "
                # For Whisper, "word": " "
                # For AssemblyAI, "text": " " (after conversion from ms)
                # For Deepgram, "word": " " (or "punctuated_word")
                # A robust check is if word_obj_fw.text.strip() is empty.
                if word_obj_fw.text.strip(): # Simpler check for actual content
                    first_actual_word_index = idx_fw
                    break
            
            last_actual_word_index = -1
            for idx_bw in range(len(matched_words) - 1, -1, -1):
                if matched_words[idx_bw].text.strip():
                    last_actual_word_index = idx_bw
                    break

            entry_text_from_llm = text_seg_from_llm.strip() # Use LLM's text as the primary content
            
            actual_words_for_entry: List[TimestampedWord]
            if first_actual_word_index != -1 and last_actual_word_index != -1 :
                entry_start_time = matched_words[first_actual_word_index].start_time
                entry_end_time = matched_words[last_actual_word_index].end_time
                actual_words_for_entry = matched_words[first_actual_word_index : last_actual_word_index+1]
                if not actual_words_for_entry: # Should not happen if indices are valid
                    self.log(f"警告: 修正后的词列表为空，LLM片段 \"{entry_text_from_llm[:30]}...\"。将使用原始匹配边界。")
                    entry_start_time = matched_words[0].start_time
                    entry_end_time = matched_words[-1].end_time
                    actual_words_for_entry = matched_words
            else:
                # This case means the matched_words list likely only contains spacing or empty text words
                self.log(f"警告: LLM片段 \"{entry_text_from_llm[:30]}...\" 匹配到的所有ASR词元均为空或空格。将使用原始匹配边界。")
                entry_start_time = matched_words[0].start_time # Fallback
                entry_end_time = matched_words[-1].end_time # Fallback
                actual_words_for_entry = matched_words # Use original matched words

            # --- 时间戳确定方式结束 ---

            entry_duration = max(0.001, entry_end_time - entry_start_time) # Ensure duration is positive
            text_len = len(entry_text_from_llm)
            
            # is_audio_event should be determined from the content of words used for the entry
            is_audio_event = False
            if actual_words_for_entry: # Only check if we have actual words
                 is_audio_event = all(
                    not w.text.strip() or \
                    getattr(w, 'type', 'word') == 'audio_event' or \
                    re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) \
                    for w in actual_words_for_entry
                )


            if is_audio_event:
                final_audio_event_end_time = entry_end_time
                if entry_duration < MIN_DURATION_ABSOLUTE: final_audio_event_end_time = entry_start_time + MIN_DURATION_ABSOLUTE
                final_audio_event_end_time = max(final_audio_event_end_time, entry_start_time + 0.001)
                # Use the text from the actual words for audio events
                audio_event_text_content = "".join([w.text for w in actual_words_for_entry])
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_audio_event_end_time, audio_event_text_content, actual_words_for_entry, match_ratio))
            elif entry_duration > max_duration or text_len > max_chars_per_line:
                self.log(f"  片段超限，需分割: \"{entry_text_from_llm[:50]}...\" (时长: {entry_duration:.2f}s, 字符: {text_len})")
                split_sub_entries = self.split_long_sentence(
                    entry_text_from_llm, # Use LLM's text for splitting logic
                    actual_words_for_entry, # Pass the (potentially trimmed) list of word objects
                    entry_start_time, entry_end_time,
                    min_duration_target, max_duration, max_chars_per_line
                )
                for sub_entry in split_sub_entries: sub_entry.alignment_ratio = match_ratio
                intermediate_entries.extend(split_sub_entries)
            elif entry_duration < min_duration_target :
                final_short_entry_end_time = entry_start_time + min_duration_target
                if entry_duration < MIN_DURATION_ABSOLUTE: final_short_entry_end_time = entry_start_time + MIN_DURATION_ABSOLUTE
                
                original_end_of_last_actual_word = actual_words_for_entry[-1].end_time if actual_words_for_entry else entry_start_time
                max_allowed_extension = original_end_of_last_actual_word + 0.5 
                final_short_entry_end_time = min(final_short_entry_end_time, max_allowed_extension)
                final_short_entry_end_time = max(final_short_entry_end_time, entry_end_time) 
                final_short_entry_end_time = max(final_short_entry_end_time, entry_start_time + 0.001)
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_short_entry_end_time, entry_text_from_llm, actual_words_for_entry, match_ratio))
            else:
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, entry_end_time, entry_text_from_llm, actual_words_for_entry, match_ratio))

            completed_steps_phase1 += 1
            self._emit_srt_progress(int( (completed_steps_phase1 / total_llm_segments) * WEIGHT_ALIGN ), 100)

        # ... (rest of the method: unaligned_segments logging, sorting, phase 2, phase 3, cleanup) ...
        self.log("--- LLM片段对齐结束 ---")
        if unaligned_segments:
            self.log(f"\n--- 以下 {len(unaligned_segments)} 个LLM片段未能成功对齐，已跳过 ---")
            for seg_idx, seg_text in enumerate(unaligned_segments):
                self.log(f"- 片段 {seg_idx+1}: \"{seg_text}\"")
            self.log("----------------------------------------\n")

        if not intermediate_entries: self.log("错误：对齐后没有生成任何有效的字幕条目。"); return None
        intermediate_entries.sort(key=lambda e: e.start_time)

        self.log("SRT阶段2: 合并调整字幕条目...")
        merged_entries: List[SubtitleEntry] = []
        idx_merge = 0
        total_intermediate_entries = len(intermediate_entries)
        while idx_merge < total_intermediate_entries:
            if not self._is_worker_running(): self.log("任务被用户中断(合并阶段)。"); return None
            
            current_entry_to_merge = intermediate_entries[idx_merge]
            merged_this_iteration = False
            if idx_merge + 1 < len(intermediate_entries):
                next_entry = intermediate_entries[idx_merge+1]
                gap_between = next_entry.start_time - current_entry_to_merge.end_time
                combined_text_len = len(current_entry_to_merge.text) + len(next_entry.text) + 1 
                combined_duration = next_entry.end_time - current_entry_to_merge.start_time
                next_is_audio_event = False
                if next_entry.words_used: # Check if words_used is not empty
                    next_is_audio_event = all(not w.text.strip() or getattr(w, 'type', 'word') == 'audio_event' or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in next_entry.words_used)


                if current_entry_to_merge.duration < min_duration_target and \
                   not next_is_audio_event and \
                   combined_text_len <= max_chars_per_line and \
                   combined_duration <= max_duration and \
                   gap_between < 0.5 and \
                   combined_duration >= min_duration_target :
                    self.log(f"  合并字幕: \"{current_entry_to_merge.text[:20]}...\" + \"{next_entry.text[:20]}...\"")
                    merged_text = current_entry_to_merge.text + " " + next_entry.text
                    merged_start_time = current_entry_to_merge.start_time
                    merged_end_time = next_entry.end_time 
                    merged_words = current_entry_to_merge.words_used + next_entry.words_used
                    merged_ratio = min(current_entry_to_merge.alignment_ratio, next_entry.alignment_ratio)
                    merged_entries.append(SubtitleEntry(0, merged_start_time, merged_end_time, merged_text, merged_words, merged_ratio))
                    idx_merge += 2 
                    merged_this_iteration = True
            if not merged_this_iteration:
                merged_entries.append(current_entry_to_merge)
                idx_merge += 1
            
            current_phase2_progress_component = int(((idx_merge) / total_intermediate_entries if total_intermediate_entries > 0 else 1) * WEIGHT_MERGE)
            self._emit_srt_progress(WEIGHT_ALIGN + current_phase2_progress_component, 100)
        
        self.log(f"--- 合并调整后得到 {len(merged_entries)} 个字幕条目，开始最终格式化 ---")

        self.log("SRT阶段3: 最终格式化字幕...")
        final_srt_formatted_list: List[str] = []
        last_processed_entry_object: Optional[SubtitleEntry] = None
        subtitle_index = 1
        total_merged_final_entries = len(merged_entries)
        for entry_idx, current_entry in enumerate(merged_entries):
            if not self._is_worker_running(): self.log("任务被用户中断(最终格式化阶段)。"); return None
            
            self.log(f"  格式化条目 {entry_idx+1}/{total_merged_final_entries}: \"{current_entry.text[:30]}...\"")
            if last_processed_entry_object is not None: 
                gap_seconds = default_gap_ms / 1000.0 
                if current_entry.start_time < last_processed_entry_object.end_time + gap_seconds:
                    new_previous_end_time = current_entry.start_time - gap_seconds
                    min_duration_for_previous = MIN_DURATION_ABSOLUTE 
                    if new_previous_end_time > last_processed_entry_object.start_time + min_duration_for_previous:
                        last_processed_entry_object.end_time = new_previous_end_time
                    else: 
                        safe_previous_end_time = current_entry.start_time - 0.001 
                        if safe_previous_end_time > last_processed_entry_object.start_time + min_duration_for_previous:
                             last_processed_entry_object.end_time = safe_previous_end_time
                    if final_srt_formatted_list: 
                        final_srt_formatted_list[-1] = last_processed_entry_object.to_srt_format(self)
            
            current_duration = current_entry.duration 
            min_duration_to_apply_val: Optional[float] = None
            entry_is_audio_event = False
            if current_entry.words_used:
                entry_is_audio_event = any(not w.text.strip() or getattr(w, 'type', 'word') == 'audio_event' or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in current_entry.words_used)
            
            if not current_entry.is_intentionally_oversized and not entry_is_audio_event:
                if current_duration < min_duration_target: min_duration_to_apply_val = min_duration_target
                if current_duration < MIN_DURATION_ABSOLUTE: min_duration_to_apply_val = MIN_DURATION_ABSOLUTE 
            if min_duration_to_apply_val is not None:
                current_entry.end_time = max(current_entry.end_time, current_entry.start_time + min_duration_to_apply_val)
            if not current_entry.is_intentionally_oversized and current_entry.duration > max_duration:
                self.log(f"字幕 \"{current_entry.text[:30]}...\" 时长 {current_entry.duration:.2f}s 超出最大值 {max_duration}s，将被截断。")
                current_entry.end_time = current_entry.start_time + max_duration
            if current_entry.end_time <= current_entry.start_time: 
                 current_entry.end_time = current_entry.start_time + 0.001

            current_entry.index = subtitle_index
            final_srt_formatted_list.append(current_entry.to_srt_format(self))
            last_processed_entry_object = current_entry
            subtitle_index += 1
            
            current_phase3_progress_component = int(((entry_idx + 1) / total_merged_final_entries if total_merged_final_entries > 0 else 1) * WEIGHT_FORMAT)
            self._emit_srt_progress(WEIGHT_ALIGN + WEIGHT_MERGE + current_phase3_progress_component, 100)
            
        self.log("--- SRT 内容生成和格式化完成 ---")
        
        if hasattr(self, '_current_progress_offset'): del self._current_progress_offset
        if hasattr(self, '_current_progress_range'): del self._current_progress_range
        
        return "".join(final_srt_formatted_list).strip()