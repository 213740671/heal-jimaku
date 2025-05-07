import json
import math
import re
import glob
import os  

# --- 配置参数 ---
MIN_DURATION_TARGET = 1.2  # 秒，目标最小时长
MIN_DURATION_ABSOLUTE = 1.0 # 秒，特殊情况下允许的最小时长
MAX_DURATION = 12.0       # 秒，最大时长
PAUSE_THRESHOLD = 0.8     # 秒，用于判断显著停顿的阈值
TARGET_CHARS_PER_LINE = 25 # 日文字符，单行目标字数
MAX_CHARS_PER_LINE = 60    # 日文字符，单行最大字数 (硬上限)
DEFAULT_GAP_MS = 100       # 毫秒，字幕间的默认间隙


# --- Helper Functions ---

def format_timecode(seconds_float):
    """将浮点数秒转换为SRT时间码格式 HH:MM:SS,ms"""
    if not isinstance(seconds_float, (int, float)) or seconds_float < 0:
        # 对于无效的输入，可以返回一个默认值或抛出错误
        # 这里为了演示，如果出现非数字或负数，暂时返回一个明显的错误标记
        # 在实际使用中，应该确保传入的都是有效的秒数
        print(f"警告: 无效的秒数输入到 format_timecode: {seconds_float}")
        return "00:00:00,000"
        
    total_seconds_int = int(seconds_float)
    milliseconds = int(round((seconds_float - total_seconds_int) * 1000))
    
    hours = total_seconds_int // 3600
    minutes = (total_seconds_int % 3600) // 60
    seconds = total_seconds_int % 60
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def get_segment_words(text_segment, all_words, start_search_index):
    """
    尝试将文本片段与all_words中的词进行对齐。
    返回 (匹配到的words列表, 下一个搜索的开始索引, 是否精确匹配)
    这是一个简化的实现，实际中可能需要更复杂的对齐算法。
    """
    segment_clean = text_segment.strip()
    if not segment_clean:
        return [], start_search_index, True

    current_match_words = []
    temp_text_build = ""
    
    # 尝试精确匹配整个片段
    for i in range(start_search_index, len(all_words)):
        # 尝试从当前位置开始构建匹配
        current_match_words_temp = []
        temp_text_build_temp = ""
        exact_match_found_at_i = False
        for j in range(i, len(all_words)):
            word_obj = all_words[j]
            # 忽略纯粹的 spacing 类型，但如果它们是分割的一部分，则需要考虑
            if word_obj.get("type") == "spacing" and not word_obj.get("text", "").strip():
                if not current_match_words_temp: # 开头的空格忽略
                    continue
                # 中间的空格如果LLM的片段里没有，这里也不加
            
            current_match_words_temp.append(word_obj)
            temp_text_build_temp += word_obj.get("text", "")
            
            # 使用更宽松的比较，去除所有空格后比较
            if temp_text_build_temp.replace(" ", "") == segment_clean.replace(" ", ""):
                return current_match_words_temp, j + 1, True
            # 如果当前构建的文本已经比目标长，则此路径不可能匹配
            if len(temp_text_build_temp.replace(" ", "")) > len(segment_clean.replace(" ", "")):
                break
        
        # 如果循环完都没有精确匹配整个片段，我们需要回退，或者采用更复杂的对齐
        # 为简化，这里只处理能精确匹配的情况。
        # 如果你发现LLM分割的文本和words数组中的text拼接有出入，这里需要增强

    # 如果没有找到精确匹配，这是一个问题点，需要更好的对齐策略或错误处理
    print(f"警告: 未能精确对齐文本片段: '{segment_clean}' 从索引 {start_search_index} 开始。可能需要手动检查或改进对齐算法。")
    # 尝试一种非常基础的回退：如果片段是 (xxx) 形式，且在words里有完全匹配的 (xxx) audio_event
    if segment_clean.startswith("(") and segment_clean.endswith(")") and len(segment_clean) > 2:
        for k in range(start_search_index, len(all_words)):
            if all_words[k].get("text", "") == segment_clean and all_words[k].get("type") == "audio_event":
                return [all_words[k]], k + 1, True
    
    return [], start_search_index, False # 表示未找到或未精确匹配

class SubtitleEntry:
    def __init__(self, index, start_time, end_time, text, words_used=None):
        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.text = text.strip() # 确保单行且无多余空白
        self.words_used = words_used if words_used else []

    @property
    def duration(self):
        if self.start_time is not None and self.end_time is not None:
            return self.end_time - self.start_time
        return 0

    def to_srt_format(self):
        if self.start_time is None or self.end_time is None or self.text is None:
             print(f"警告: 字幕条目 {self.index} 缺少时间或文本: start={self.start_time}, end={self.end_time}, text='{self.text}'")
             return "" # 或者抛出错误
        return f"{self.index}\n{format_timecode(self.start_time)} --> {format_timecode(self.end_time)}\n{self.text}\n\n"

def split_long_sentence(sentence_text, sentence_words, original_start_time, original_end_time):
    """
    根据规则分割超长句子 (Python 实现 Stage 3)
    返回一个 SubtitleEntry 对象的列表
    """
    entries = []
    current_segment_words = []
    current_segment_text = ""
    
    # 检查是否真的需要分割 (这个函数被调用时，通常是需要的)
    # 这里的逻辑是：输入的是一个已经被判断为超长的句子片段及其对应的words
    # 我们需要根据逗号规则将其分割成更小的片段

    # 找到所有预备分割点 (逗号、省略号) 的索引 (在 sentence_words 内部的索引)
    split_point_indices = []
    for i, word_obj in enumerate(sentence_words):
        if word_obj.get("text") in ["、", "...", "‥"]: # 可以扩展更多标点
            split_point_indices.append(i)

    words_to_process = list(sentence_words) # 创建副本进行处理

    while words_to_process:
        segment_text_parts = []
        current_sub_segment_words = []
        current_sub_segment_start_time = None
        current_sub_segment_end_time = None
        
        # 确定当前子片段的分割点
        # 这个逻辑需要基于剩余的 words_to_process 和原始的分割规则
        # 这是一个简化的实现，直接尝试构建不超过11秒和50字符的片段
        
        temp_words_for_this_sub_entry = []
        temp_text_for_this_sub_entry = ""
        
        # 尝试根据逗号规则找到一个切分点 (简化版，先只处理一次切分)
        # 完整的逗号分割逻辑（两个逗号在前一个，三个以上倒数第二个）会更复杂
        # 这里我们先尝试一种更通用的基于时长和字数的贪婪分割
        
        split_at_word_index = -1 # 在哪个词之后分割

        if len(words_to_process) == 0:
            break

        current_potential_start_time = words_to_process[0]["start"]
        accumulated_text = ""
        
        for i, word_obj in enumerate(words_to_process):
            # 检查加入这个词是否会导致超限
            next_accumulated_text = accumulated_text + word_obj.get("text", "")
            current_potential_end_time = word_obj["end"]
            duration_if_added = current_potential_end_time - current_potential_start_time
            
            if len(next_accumulated_text) > MAX_CHARS_PER_LINE or duration_if_added > MAX_DURATION:
                if i > 0: # 必须至少包含一个词
                    split_at_word_index = i - 1
                else: # 第一个词就超限了，也只能取这一个词（虽然不太可能，因为外层已经判断过）
                    split_at_word_index = 0
                break
            
            accumulated_text = next_accumulated_text
            temp_words_for_this_sub_entry.append(word_obj)
            if i == len(words_to_process) - 1: # 已经是最后一个词了
                split_at_word_index = i
        
        if split_at_word_index != -1:
            current_sub_segment_words = words_to_process[:split_at_word_index + 1]
            words_to_process = words_to_process[split_at_word_index + 1:]
        else: # 如果没有找到合适的分割点（例如单个词就超长，这不太可能）
            current_sub_segment_words = list(words_to_process) # 取全部剩余
            words_to_process = []

        if not current_sub_segment_words:
            continue

        sub_text = "".join([w.get("text", "") for w in current_sub_segment_words])
        sub_start_time = current_sub_segment_words[0]["start"]
        sub_end_time = current_sub_segment_words[-1]["end"]
        
        # 检查并应用最小时长规则 (1.5s, 特殊1s)
        current_duration = sub_end_time - sub_start_time
        if current_duration < MIN_DURATION_TARGET:
            if current_duration < MIN_DURATION_ABSOLUTE: # 少于1秒，尝试延长到1秒
                # 确保不与下一片段的实际开始时间冲突
                # 这个检查比较复杂，因为下一片段的第一个词的start时间是已知的
                # 并且也不能超过本片段最后一个词的原始结束时间太多
                potential_next_word_start = words_to_process[0]["start"] if words_to_process else float('inf')
                max_allowed_extension = current_sub_segment_words[-1]["end"] + 0.2 # 最多延长0.2秒
                
                new_end_time = sub_start_time + MIN_DURATION_ABSOLUTE
                if new_end_time < potential_next_word_start and new_end_time <= max_allowed_extension:
                    sub_end_time = new_end_time
                elif max_allowed_extension < potential_next_word_start: # 如果延长0.2秒不冲突
                     sub_end_time = max_allowed_extension
                # else, 保持原始的end_time，即使它小于1秒，后续的合并阶段可能会处理

        # 强制单行
        entries.append(SubtitleEntry(0, sub_start_time, sub_end_time, sub_text.replace("\n", " "), words_used=current_sub_segment_words))
        
    return entries


# --- 主逻辑 ---
def process_json_to_srt(json_filepath, llm_segmented_text_filepath):
    try:
        with open(json_filepath, "r", encoding="utf-8") as f:
            api_data = json.load(f)
        all_words = api_data.get("words", [])
        # full_text_from_json = api_data.get("text", "") # LLM的输入
    except Exception as e:
        print(f"错误: 无法读取或解析JSON文件 {json_filepath}: {e}")
        return ""

    try:
        with open(llm_segmented_text_filepath, "r", encoding="utf-8") as f:
            llm_segments_text = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"错误: 无法读取LLM分割的文本文件 {llm_segmented_text_filepath}: {e}")
        return ""

    if not all_words:
        print("警告: JSON文件中没有找到'words'数据。")
        return ""
    if not llm_segments_text:
        print("警告: LLM分割的文本文件为空。")
        return ""

    processed_subtitle_entries = []
    word_search_start_index = 0
    
    # --- Stage 2: Align LLM segments, Calculate initial timestamps, Validate duration ---
    intermediate_entries = []

    for text_seg in llm_segments_text:
        matched_words, next_search_idx, _ = get_segment_words(text_seg, all_words, word_search_start_index)
        
        if not matched_words:
            print(f"警告: LLM片段 '{text_seg}' 未能在原始words中找到对应。跳过此片段。")
            # 如果一个片段没匹配上，后续的对齐可能会完全错乱，这是一个严重问题
            # 理想情况下，需要一个机制来重新同步或标记这个错误
            # 为简单起见，我们这里仅跳过，但下一个片段会从上一个成功匹配的结束点开始搜索
            continue 
        
        word_search_start_index = next_search_idx # 更新搜索起点

        entry_text = "".join([w.get("text", "") for w in matched_words])
        entry_start_time = matched_words[0]["start"]
        entry_end_time = matched_words[-1]["end"]
        entry_duration = entry_end_time - entry_start_time

        is_audio_event = any(w.get("type") == "audio_event" for w in matched_words)

        if is_audio_event:
            intermediate_entries.append(SubtitleEntry(0, entry_start_time, entry_end_time, entry_text, matched_words))
        else:
            # 时长校验和初步处理
            if entry_duration > MAX_DURATION or len(entry_text) > MAX_CHARS_PER_LINE:
                # --- Stage 3: Split overlong sentences (Python logic) ---
                print(f"信息: 句子 '{entry_text[:30]}...' (时长: {entry_duration:.2f}s, 字数: {len(entry_text)}) 超限，尝试分割。")
                split_sub_entries = split_long_sentence(entry_text, matched_words, entry_start_time, entry_end_time)
                intermediate_entries.extend(split_sub_entries)
            elif entry_duration < MIN_DURATION_TARGET: # 少于1.5秒，但没有超长
                # 尝试延长到1秒 (如果原时长不足1秒)
                if entry_duration < MIN_DURATION_ABSOLUTE:
                    new_end_time = entry_start_time + MIN_DURATION_ABSOLUTE
                    # 安全检查: 不能超过本片段最后一个词的原始end太多，也不能和下一个已知片段冲突
                    # 这个检查在分块独立处理时，只能基于当前块的最后一个词的原始end
                    max_allowed_extension = matched_words[-1]["end"] + 0.2 
                    
                    # 尝试找到下一个非空片段的开始时间作为硬性上限
                    next_actual_start = float('inf')
                    # （这部分逻辑在没有全局视图时较难完美实现，分块合并时再处理块间冲突更好）
                    # 这里简化为不超过原始end太多
                    if new_end_time <= max_allowed_extension:
                         entry_end_time = new_end_time
                    else:
                         entry_end_time = max_allowed_extension
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, entry_end_time, entry_text, matched_words))
            else: # 1.5秒 <= 时长 <= 11秒，且字数不超限
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, entry_end_time, entry_text, matched_words))

    # --- 后处理合并和最终调整 (简化版，完整的合并逻辑会更复杂) ---
    final_srt_entries = []
    if not intermediate_entries:
        return ""

    # 首先进行一次初步的合并尝试（仅针对相邻且合并后满足条件的）
    merged_entries_pass1 = []
    i = 0
    while i < len(intermediate_entries):
        current_entry = intermediate_entries[i]
        if i + 1 < len(intermediate_entries):
            next_entry = intermediate_entries[i+1]
            # 尝试合并条件：当前条目太短，下一条目不是场景，合并后不超过最大时长和字数
            if current_entry.duration < MIN_DURATION_TARGET and \
               not any(w.get("type") == "audio_event" for w in next_entry.words_used) and \
               (current_entry.duration + next_entry.duration) <= MAX_DURATION and \
               (len(current_entry.text) + len(next_entry.text)) <= MAX_CHARS_PER_LINE:
                
                # 确保合并后的时间戳是合理的（基于原始单词）
                merged_text = current_entry.text + " " + next_entry.text # 合并时加空格
                merged_start_time = current_entry.start_time
                merged_end_time = next_entry.end_time # 结束时间应为下一条的结束时间
                merged_words = current_entry.words_used + next_entry.words_used
                
                # 重新检查合并后的时长是否达到目标
                if (merged_end_time - merged_start_time) >= MIN_DURATION_TARGET:
                    merged_entries_pass1.append(SubtitleEntry(0, merged_start_time, merged_end_time, merged_text, merged_words))
                    i += 2 # 跳过两条
                    continue
        
        merged_entries_pass1.append(current_entry)
        i += 1
        
    # 对合并后的条目再次检查最小时长 (特别是那些无法合并或合并后仍不足的)
    for entry in merged_entries_pass1:
        # 非音频事件且时长不足1.5秒
        if not any(w.get("type") == "audio_event" for w in entry.words_used) and entry.duration < MIN_DURATION_TARGET:
            if entry.duration < MIN_DURATION_ABSOLUTE: # 不足1秒，尝试延长到1秒
                new_end_time = entry.start_time + MIN_DURATION_ABSOLUTE
                # 安全检查：不应大幅超过原始最后一个词的end，并且不能影响下一条字幕的开始
                # 这个检查在最终排序和编号时会更可靠
                max_allowed_original_end = entry.words_used[-1]["end"] + 0.2 # 最多延长0.2秒
                if new_end_time <= max_allowed_original_end:
                    entry.end_time = new_end_time
                else:
                    entry.end_time = max_allowed_original_end
        final_srt_entries.append(entry)


    # 确保时间戳严格递增且无重叠，并加入间隙
    # 这个步骤在所有片段都处理完并排序后进行会更准确
    # 这里先做一个简单的排序，后续如果需要，可以增加更复杂的块间对齐逻辑
    final_srt_entries.sort(key=lambda e: e.start_time)
    
    output_srt_entries = []
    last_end_time = -1.0 

    for i, entry in enumerate(final_srt_entries):
        # 强制单行
        entry.text = entry.text.replace('\n', ' ').replace('\r', '')
        
        # 检查时间重叠或顺序问题 (基于排序后的列表)
        if entry.start_time < last_end_time:
            print(f"警告: 字幕 {i+1} 开始时间 ({format_timecode(entry.start_time)}) 早于前一条字幕结束时间 ({format_timecode(last_end_time)})。尝试修正。")
            entry.start_time = last_end_time + (DEFAULT_GAP_MS / 1000.0) # 强制推后并加间隙
            if entry.start_time >= entry.end_time: # 如果修正后导致开始>=结束，则此条字幕可能有问题
                 entry.end_time = entry.start_time + MIN_DURATION_ABSOLUTE # 强制一个最小时长
                 print(f"  修正后字幕 {i+1} end_time: {format_timecode(entry.end_time)}")


        # 确保字幕间有最小间隙 (除非是紧密连接的)
        if last_end_time > 0 and entry.start_time < last_end_time + (DEFAULT_GAP_MS / 1000.0):
            # 如果实际间隔小于默认间隙，可以不强制推后，除非有重叠
            pass
        elif last_end_time > 0 and entry.start_time > last_end_time + (DEFAULT_GAP_MS / 1000.0) + 0.1: # 间隙过大时，可以考虑拉近，但这较复杂
            pass


        # 再次检查时长，以防调整后出问题
        if not any(w.get("type") == "audio_event" for w in entry.words_used):
            current_duration = entry.end_time - entry.start_time
            if current_duration < MIN_DURATION_ABSOLUTE: # 最后的硬底线
                entry.end_time = entry.start_time + MIN_DURATION_ABSOLUTE
            elif current_duration > MAX_DURATION:
                 print(f"警告: 字幕 {i+1} 在最终调整后仍超过最大时长: {current_duration:.2f}s. 文本: {entry.text[:30]}...")
                 # 理论上不应发生，因为split_long_sentence应该处理了

        output_srt_entries.append(SubtitleEntry(i + 1, entry.start_time, entry.end_time, entry.text))
        last_end_time = entry.end_time

    # 生成最终SRT字符串
    srt_output_string = ""
    for entry in output_srt_entries:
        srt_output_string += entry.to_srt_format()
        
    return srt_output_string.strip()

# --- 主程序入口 ---
if __name__ == "__main__":
    # LLM分割后的文本文件名是固定的，或者你可以让用户输入
    llm_segmented_file_path = "llm_segmented_output.txt"

    # 自动查找当前目录下的.json文件
    json_files_in_current_directory = glob.glob("*.json")
    
    json_file_path = None
    if not json_files_in_current_directory:
        print("错误：在当前目录下未找到任何 .json 文件。请确保JSON文件与脚本在同一目录，或在代码中指定完整路径。")
        exit()
    elif len(json_files_in_current_directory) == 1:
        json_file_path = json_files_in_current_directory[0]
        print(f"自动找到JSON文件: {json_file_path}")
    else:
        print("错误：在当前目录下找到多个 .json 文件。请确保只有一个JSON文件，或在代码中明确指定要处理的文件名。")
        print("找到的文件列表:")
        for f_name in json_files_in_current_directory:
            print(f"- {f_name}")
        # 你也可以在这里添加逻辑让用户选择一个文件，但为简单起见，先报错退出
        exit()

    # --- 确保llm_segmented_output.txt存在 ---
    # 如果llm_segmented_output.txt不存在，你可能需要提示用户先生成它，或者保留之前的临时生成逻辑
    if not os.path.exists(llm_segmented_file_path):
        print(f"警告: 未找到LLM分割的文本文件 '{llm_segmented_file_path}'。")
        print("请先使用LLM处理JSON中的'text'字段，并将结果保存为该文件。")
        # 以下是生成临时文件的示例代码，你可以根据需要保留或删除
        # 如果保留，它会在真实LLM输出文件不存在时创建一个基于简单规则的临时文件
        try:
            with open(json_file_path, "r", encoding="utf-8") as f_json:
                temp_api_data = json.load(f_json)
                full_text = temp_api_data.get("text", "")
                if full_text:
                    temp_segments = []
                    current_segment = ""
                    in_paren = False
                    # 改进的简单分割逻辑
                    # 将文本按句末标点分割，同时尝试将括号内容作为独立片段
                    # 这仍然是简化的，真实LLM效果会更好
                    
                    # 使用正则表达式来帮助分割括号内容和主要标点
                    # 这个正则表达式尝试匹配括号内容或者非括号、非标点内容，或者标点
                    # (?P<paren>\([^)]*\)|（[^）]*）) 匹配括号内容
                    # (?P<punct>[。？！…‥]) 匹配句末标点
                    # (?P<text>[^。？！…‥（）()]+) 匹配非标点非括号的文本
                    # 这个正则可能还需要根据实际文本进一步完善
                    
                    # 一个更简单的方法是逐字处理，如之前的示例
                    # 为了让脚本能直接运行并演示，这里保留之前的简单分割逻辑
                    # 但强烈建议你用真实的LLM输出来覆盖llm_segmented_output.txt
                    for char in full_text:
                        current_segment += char
                        if char == '(' or char == '（':
                            if current_segment[:-1].strip():
                               temp_segments.append(current_segment[:-1].strip())
                            current_segment = char 
                            in_paren = True
                        elif char == ')' or char == '）':
                            if in_paren:
                                temp_segments.append(current_segment.strip())
                                current_segment = ""
                                in_paren = False
                        elif char in ['。', '？', '！', '…', '‥'] and not in_paren: 
                            if current_segment.strip():
                                temp_segments.append(current_segment.strip())
                            current_segment = ""
                    if current_segment.strip():
                        temp_segments.append(current_segment.strip())

                    with open(llm_segmented_file_path, "w", encoding="utf-8") as f_llm:
                        for seg in temp_segments:
                            f_llm.write(seg + "\n")
                    print(f"已生成临时的LLM分割文件: {llm_segmented_file_path} (使用简单规则代替真实LLM输出)")
                else:
                    print(f"错误: {json_file_path} 中未找到 'text' 字段或内容为空。无法生成临时分割文件。")
                    exit()
        except Exception as e:
            print(f"生成临时的LLM分割文件时出错: {e}")
            exit()
    else:
        print(f"找到LLM分割的文本文件: {llm_segmented_file_path}")


    final_srt = process_json_to_srt(json_file_path, llm_segmented_file_path)

    if final_srt:
        # 生成与输入JSON文件同名（但扩展名为.srt）的输出文件
        base_name, _ = os.path.splitext(json_file_path)
        output_srt_filepath = base_name + ".srt"
        with open(output_srt_filepath, "w", encoding="utf-8") as f:
            f.write(final_srt)
        print(f"SRT文件已生成: {output_srt_filepath}")
    else:
        print("未能生成SRT文件。")