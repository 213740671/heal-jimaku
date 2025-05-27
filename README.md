# Heal-Jimaku (治幕) - 字幕优化导出工具

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-yellow.svg)](https://www.apache.org/licenses/LICENSE-2.0) [![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/) [![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/) [![DeepSeek API](https://img.shields.io/badge/AI%20Model-DeepSeek-orange.svg)](https://platform.deepseek.com/) [![ElevenLabs API](https://img.shields.io/badge/Free%20STT-ElevenLabs-blueviolet.svg)](https://elevenlabs.io/) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/fuxiaomoke/heal-jimaku)

**Heal-Jimaku (治幕)** 是一款利用大语言模型对多语言文本（现已优化支持日语、中文、英文的智能分割处理提示词）进行智能分割，并将带有精确时间戳的 JSON 文件（可来自本地文件或通过内置的 **免费语音转文字(STT)服务** 生成）转换为更自然、易读且适配DLsite审核（现已支持用户自行调整格式）要求的 SRT 字幕文件的桌面应用程序。它的开发初衷是"治愈"那些因没有断句功能或断句不佳导致缺乏语义连贯性而难以编辑阅读的音声转录结果，从而提高我对同人音声字幕的翻译效率。

![Heal-Jimaku 应用截图](https://github.com/fuxiaomoke/heal-jimaku/blob/main/assets/screenshot.png)

## ✨ 项目特性

- **智能文本分割**: 深度整合大语言模型API**（默认使用 [DeepSeek](https://platform.deepseek.com/)，但现已支持配置其他兼容OpenAI格式的API）**，利用其强大的语言理解能力及**两阶段处理方法（先生成全文摘要辅助理解上下文，再对文本块进行智能分割）**，并使用优化的多语言处理提示词（支持日语、中文、英文），根据语义和标点符号进行自然断句，**有效处理长文本并提升分割准确性**。

- **一键音频转字幕（新功能！！！）**: 新增"免费获取JSON"功能，允许用户直接上传音频文件，通过集成的免费高品质语音转录API（当前使用 ElevenLabs）快速生成带有逐词时间戳的JSON，并接续进行智能分割和SRT优化导出，实现从音频到高质量字幕的一站式体验。

- **STT 结果优化**: 专为处理包含逐词时间戳的 JSON 文件设计，支持多种主流 ASR 服务商格式（如 ElevenLabs, Whisper, Deepgram, AssemblyAI），优化语音转录文字 (STT) 的原始输出。

- **SRT 字幕生成**: 输出行业标准的 `.srt` 字幕文件，兼容各类字幕编辑器以及视频播放器。

- **用户可配置的参数系统**:

  - SRT参数配置，允许用户通过设置对话框自定义关键SRT生成参数，包括：

    - 字幕目标最小持续时间 (秒)
    - 字幕最大持续时间 (秒)
    - 每行字幕最大字符数
    - 字幕间默认间隙 (毫秒)
  
  - LLM高级设置 **（新增LLM配置对话框！！！）**，支持：

    - 自定义API地址（支持其他**兼容OpenAI格式的API服务**）
    - 模型名称配置
    - 温度参数调节（控制输出随机性）
    - API连接测试功能
    - API Key管理与持久化保存
  
- **图形用户界面**: 基于 PyQt6 构建，提供直观易用的操作界面。自定义控件和优化后的UI显示，提供更舒适的用户体验。

- **配置持久化**:

  - 保存 LLM API配置（API地址、模型名称、温度、API Key等）。
  - 记住上次使用的文件、目录路径、选择的JSON格式以及输入模式（本地JSON或免费获取）。
  - 保存用户自定义的SRT生成参数、免费转录参数。
  
- **处理反馈**: 提供优化后的**详细日志输出**和**LLM处理进度条**显示。

- **错误处理**: 集成 `faulthandler` 以记录崩溃日志，方便调试。

## 🚀 解决的问题

许多语音转录文字(STT) 工具可以生成带有word级或character级的时间戳的json响应，但这些文本要么缺少自然的断句输出，无法直接导出标准格式的字幕使用，要么导出的字幕断句效果一般，依旧需要费时费力的人工校对。Heal-Jimaku 通过以下方式，在一定程度上解决了这个问题：

1. **语义断句**: 利用大语言模型理解文本内容，**并通过预先生成的全文摘要来增强对长文本上下文的把握**，在最符合语义逻辑的地方进行分割。
2. **标点优化**: 智能处理括号、引号及各种句末标点，确保字幕的连贯性。
3. **时长与字数控制**: 遵循字幕的基本规范（现在可通过用户设置进行调整），调整字幕条目的显示时长和每行字数。
4. **便捷获取初始JSON**: 新增的"免费获取JSON"功能，使用户无需依赖外部STT工具即可快速开始字幕优化流程。
5. **灵活的API配置**: 支持配置第三方大语言模型API服务，不再局限于特定的API提供商。

## 🛠️ 安装指南

### 操作系统

- Windows

### 依赖环境

- Python 3.8 或更高版本
- 一个有效的大语言模型 API Key（默认支持 [DeepSeek](https://platform.deepseek.com/)，可通过LLM高级设置配置其他兼容OpenAI格式的API）
- (可选，若使用免费获取JSON功能) 网络连接[多节点最佳，没有也不要紧]

### (最简单) 直接运行打包好的可执行文件

1. **在release界面找到最新的发行版，下载Heal-Jimaku.zip压缩包**
2. **解压到本地**
3. **双击运行 治幕.exe 文件**

### 从源码运行

1. **克隆仓库**:

   ```bash
   git clone https://github.com/fuxiaomoke/heal-jimaku.git
   cd heal-jimaku
   ```

2. **创建并激活虚拟环境** (推荐):

   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **安装依赖**:

   ```bash
   pip install -r requirements.txt
   ```

   主要依赖包括：

   - `PyQt6`
   - `requests`
   - `mutagen`
   - `langdetect`

4. **运行应用**:

   ```bash
   python src/main.py
   ```

   *(注意: 启动脚本已更改为 `src/main.py`)*

### (可选) 打包为可执行文件

如果您希望构建独立的可执行文件，可以使用packaging子文件夹中的build_heal_jimaku.bat脚本。

在packaging子文件夹中直接双击脚本，或在该文件夹下打开cmd命令提示符：

```bash
..\heal-jimaku\packaging>build_heal_jimaku.bat
```

打包后的文件将位于项目根目录下，双击运行即可。

(注意：`packaging/file_version_info.txt` 文件用于 Windows 打包时定义版本信息，PyInstaller 会自动查找。当前版本为 `0.1.3.0`)

## 📖 使用说明

详细的使用步骤和界面说明，包括如何使用新增的 **免费获取JSON** 功能、**自定义高级SRT设置** 以及 **LLM高级配置**，请参见 [**USAGE.md**](https://github.com/fuxiaomoke/heal-jimaku/blob/main/docs/USAGE.md)。

## ⚙️ 配置文件

应用程序会在首次成功保存设置或启动时，在用户主目录下的 `.heal_jimaku_gui` 文件夹中创建一个 `config.json` 文件。该文件用于存储：

- LLM API配置（API地址、模型名称、温度参数、API Key [如果选择了"记住 API Key"]）
- 上次使用的 JSON 文件路径 (本地模式) 或 音频文件路径 (免费获取模式)
- 上次使用的导出目录路径
- 上次选择的JSON格式 (本地模式)
- 上次使用的输入模式 ("local_json" 或 "free_transcription")
- 用户自定义的高级SRT参数 (最小/最大时长、每行最大字符数、字幕间默认间隙)
- 用户自定义的免费转录API参数 (转录语言、说话人数、是否标记音频事件)

同时，崩溃日志会保存在用户主目录下的 `.heal_jimaku_gui_logs/heal_jimaku_crashes.log`。

## 🛣️ 未来规划 (后面要是有空的话)

- [x] 允许用户在界面中自行调整 SRT 生成参数 (如最小/最大时长、每行最大字符数)。 *(已通过设置对话框实现)*
- [x] 支持更多的 json 输入格式（比如whisper、assemblyai、deepgram等）。 *(已实现)*
- [x] 与作者的另一个语音转字幕项目功能类似，一键上传音频生成高质量字幕。 *(已通过"免费获取JSON"功能初步实现)*
- [x] 允许用户配置不同的大语言模型API服务，支持更多API提供商。 *(已通过LLM高级设置实现)*
- [ ] 批量处理功能。
- [ ] 拖拽处理功能。

## 🤝 贡献

欢迎各种形式的贡献！如果您有任何建议、发现 Bug 或想要添加新功能，请随时：

1. 提交 [Issues](https://github.com/fuxiaomoke/heal-jimaku/issues) 来报告问题或提出建议。
2. 直接发 [邮件](mailto:l1335575367@gmail.com) 拷打作者，虽然我很菜，但是会尽力解决问题的。

## 📄 开源许可

本项目基于 [Apache License 2.0](https://www.google.com/search?q=LICENSE.txt) 开源。

## 🙏 致谢

- 感谢 [DeepSeek](https://www.deepseek.com/) 提供的强大语言模型支持。
- 感谢 [LINUX DO](https://linux.do/) 的佬友们提供的各种大模型公益API。
- 感谢 [ElevenLabs](https://elevenlabs.io/) (当前"免费获取JSON"功能主要依赖其STT服务), [OpenAI (Whisper)](https://openai.com/research/whisper), [Deepgram](https://deepgram.com/), [AssemblyAI](https://www.assemblyai.com/) 等提供的优质语音转录服务与模型。
- 感谢 [PyQt](https://riverbankcomputing.com/software/pyqt/intro) 开发团队。
