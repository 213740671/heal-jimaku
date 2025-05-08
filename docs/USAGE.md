# Heal-Jimaku (治幕) - 使用指南

本文档将指导您如何使用 Heal-Jimaku (治幕) 应用程序来优化并导出您需要的日语字幕。

## 📋 前提条件

1.  **Heal-Jimaku 应用程序**:
    * 如果您从源码运行，请确保已按照 `README.md` 中的指导完成安装和依赖配置。
    * 如果您使用的是打包好的可执行文件，直接运行即可。
2.  **DeepSeek API Key**: 您需要一个有效的 DeepSeek API Key。可以从 [DeepSeek 开放平台](https://platform.deepseek.com/) 注册并获取。
3.  **输入 JSON 文件**: 一个包含日语文本和逐词时间戳的 JSON 文件。文件必须符合特定格式 (详见下文)。

## 📄 输入 JSON 文件格式

Heal-Jimaku 需要特定格式的 JSON 文件作为输入。目前暂时只支持 [ElevenLabs](https://elevenlabs.io/) 的 JSON 响应格式（计划后续抽空加入其他模型的 JSON 格式，如whisper）。

ElevenLa的 JSON 文件应至少包含以下两个主要字段：

* `"text"`: 一个字符串，包含完整的日语文本内容。
* `"words"`: 一个对象列表，列表中的每个对象代表一个词语及其时间信息，包含以下键：
    * `"text"`: (字符串) 词语的文本内容。
    * `"start"`: (浮点数/整数) 该词语的开始时间，单位为秒。
    * `"end"`: (浮点数/整数) 该词语的结束时间，单位为秒。
    * `"speaker_id"`: (字符串) 该词语的说话对象，如果音频全程只有一个人在说话，默认为"speaker_0"，如果有其他人，那就用"speaker_1""speaker_2"这样来标记，以此类推。
    * `"type"`: (可选, 字符串) 词语类型，例如 `"audio_event"` 用于表示非语音的音频事件描述如 `(笑い声)`。如果非语音事件也带有时间戳，此字段有助于特殊处理。

**示例 JSON 结构:**

```json
{
  "text": "そう、あの視線感じたので、そうなのかなって思って。(笑い)",
  "words": [
    {
      "text": "そ",
      "start": 22.719,
      "end": 22.859,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "う",
      "start": 22.859,
      "end": 22.92,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "、",
      "start": 22.92,
      "end": 22.979,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "あ",
      "start": 22.979,
      "end": 23.1,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "の",
      "start": 23.1,
      "end": 24.1,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "視",
      "start": 24.1,
      "end": 24.359,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "線",
      "start": 24.359,
      "end": 24.659,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "感",
      "start": 24.659,
      "end": 24.879,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "じ",
      "start": 24.879,
      "end": 25.059,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "た",
      "start": 25.059,
      "end": 25.18,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "の",
      "start": 25.18,
      "end": 25.379,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "で",
      "start": 25.379,
      "end": 25.939,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "、",
      "start": 25.939,
      "end": 26.039,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "そ",
      "start": 26.379,
      "end": 26.519,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "う",
      "start": 26.519,
      "end": 26.639,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "な",
      "start": 26.639,
      "end": 26.76,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "の",
      "start": 26.76,
      "end": 26.979,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "か",
      "start": 26.979,
      "end": 27.139,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "な",
      "start": 27.139,
      "end": 27.359,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "っ",
      "start": 27.359,
      "end": 27.459,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "て",
      "start": 27.459,
      "end": 27.699,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "思",
      "start": 27.699,
      "end": 28.039,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "っ",
      "start": 28.039,
      "end": 28.119,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "て",
      "start": 28.119,
      "end": 30.519,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "。",
      "start": 30.519,
      "end": 30.619,
      "type": "word",
      "speaker_id": "speaker_0",
      "characters": null
    },
    {
      "text": "(笑い)",
      "start": 31.059,
      "end": 32.399,
      "type": "audio_event",
      "speaker_id": "speaker_0",
      "characters": null
    }
  ]
}
````

## 🚀 启动应用程序

  * **源码运行**: 在您的项目目录（并激活虚拟环境后），执行：
    ```bash
    python src/heal-jimaku-ui.py
    ```
  * **可执行文件**: 直接双击运行 `治幕.exe` (Windows) 或对应的可执行文件。

## 🖼️ 界面概览

![Heal-Jimaku 应用截图](https://github.com/fuxiaomoke/heal-jimaku/blob/test-before/assets/screenshot.png)

Heal-Jimaku 的主界面主要包含以下几个区域：

1.  **标题栏与窗口控制**:
      * **标题**: 显示 "Heal-Jimaku (治幕)"。
      * **最小化按钮 (─)**: 将窗口最小化。
      * **关闭按钮 (×)**: 关闭应用程序。
2.  **DeepSeek API 设置**:
      * **API Key 输入框**: 用于输入您的 DeepSeek API Key (格式通常为 `sk-...`)。
      * **记住 API Key 复选框**: 勾选此项后，API Key 会被保存到配置文件中，下次启动时自动填充。
3.  **文件选择**:
      * **JSON 文件输入框**: 显示当前选择的 JSON 文件的路径。
      * **浏览... (JSON 文件)**: 点击打开文件对话框，选择包含语音文本和时间戳的 JSON 文件。
4.  **导出与控制**:
      * **导出目录输入框**: 显示 SRT 字幕文件的保存目录。
      * **浏览... (导出目录)**: 点击打开目录选择对话框，选择 SRT 文件的保存位置。
      * **进度条**: 显示当前转换任务的进度。
      * **开始转换按钮**: 点击开始处理 JSON 文件并生成 SRT 字幕。
5.  **日志区域**:
      * 显示应用程序的运行日志、处理步骤、警告和错误信息。

## 📝 操作步骤

1.  **输入 API Key**:

      * 在 "DeepSeek API 设置"区域的 "API Key" 输入框中，粘贴您的 DeepSeek API Key。
      * 如果您希望下次启动时自动填充，请勾选 "记住 API Key"。

2.  **选择 JSON 文件**:

      * 点击 "文件选择" 区域中 "JSON 文件" 旁边的 "浏览..." 按钮。
      * 在弹出的文件对话框中，找到并选择您要处理的 JSON 文件。文件路径将显示在输入框中。

3.  **选择导出目录**:

      * 点击 "导出与控制" 区域中 "导出目录" 旁边的 "浏览..." 按钮。
      * 在弹出的目录选择对话框中，选择您希望保存生成的 SRT 文件的文件夹。目录路径将显示在输入框中。

4.  **开始转换**:

      * 确认以上信息无误后，点击 "开始转换" 按钮。
      * 此时，按钮会变为不可用状态，进度条开始更新，日志区域会显示处理过程。

5.  **监控进度与日志**:
      * 在转换过程中，您可以观察进度条的变化。
      * 日志区域会输出详细信息，包括与 DeepSeek API 的交互、文本片段的对齐情况、字幕条目的调整等。如果出现任何问题，错误信息也会在此显示。
    
6.  **获取 SRT 文件**:

      * 当转换完成后，进度条会达到 100%，并且会弹出提示框告知结果。
      * 生成的 SRT 文件（与输入 JSON 文件同名，扩展名为 `.srt`）将保存在您选择的导出目录中。

## ⚙️ 配置与日志文件

  * **用户配置**:
      * 路径: `~/.heal_jimaku_gui/config.json` ( `~` 代表用户主目录)
      * 内容: 保存 API Key (可选)、上次使用的 JSON 路径、上次使用的输出路径。
  * **崩溃日志**:
      * 路径: `~/.heal_jimaku_gui_logs/heal_jimaku_crashes.log`
      * 内容: 如果应用程序意外崩溃，此文件会记录 Python 的错误回溯信息。

## 🔍 故障排查

  * **"缺少信息" / "错误" 弹窗**:

      * 确保 API Key、JSON 文件路径和导出目录都已正确填写或选择。
      * 检查所选的 JSON 文件是否存在且可读。
      * 检查所选的导出目录是否存在且可写。

  * **DeepSeek API 相关错误 (日志中显示)**:

      * **认证失败 (401 Unauthorized)**: 请检查您的 API Key 是否正确，以及账户余额是否充足。
      * **请求超时**: 网络连接问题或 DeepSeek API 服务繁忙。可以稍后重试。
      * **API 响应格式错误/内容为空**: 可能是 DeepSeek API 临时问题，或输入文本过于特殊（例如过长）导致模型无法处理。

  * **"LLM 片段无法对齐" / "对齐相似度较低" (日志中显示)**:
      * 这表示 DeepSeek API 返回的文本片段在原始带时间戳的词语中找不到足够相似的匹配。
      * 原因可能包括：
          * DeepSeek 对文本的改写程度较大（尽管 Prompt 要求不增删字符，但模型行为有时难以完全控制）。
          * 原始 JSON 中的 `text` 字段与 `words` 拼接起来的内容不完全一致。
          * `difflib` 的模糊匹配阈值 (`ALIGNMENT_SIMILARITY_THRESHOLD`) 设置不当（目前是代码内固定值 `0.7`）。
      * 少量此类警告通常不影响整体字幕质量，但如果大量出现，可能需要检查输入数据或调整对齐逻辑。
      
  * **程序无响应**:
      * 如果转换的文件非常大，DeepSeek API 调用和后续处理可能需要较长时间。请耐心等待日志区域的输出。
      * 如果长时间无响应且无日志更新，可以尝试关闭程序并检查崩溃日志文件。
      
  * **界面显示问题/字体问题**:

      * 确保您的系统已安装常见的中文和日文字体（如楷体、SimSun、Microsoft YaHei 等代码中可能引用的字体）。

## ⚠️ 注意！！！

用 治幕 生成的 SRT 文件并不是百分百完美的。如果你是为了通过字幕审核，那么请务必使用字幕编辑工具进行简单的校对。放心，不符合审核要求的大部分字幕都已经被程序优化掉了，你只需要稍微过一遍字幕，把那些我特地留下来的非常容易发现但程序无法处理的小问题手动解决一下即可。


如果遇到无法解决的问题，欢迎在项目的 GitHub Issues 页面提交详细的问题描述、相关的日志信息以及您的电脑环境和 Python 版本。

-----
