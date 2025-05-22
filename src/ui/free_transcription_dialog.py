import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QSpacerItem, QSizePolicy, QWidget, QComboBox,
    QCheckBox, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from ui.custom_widgets import CustomLabel # 确保 CustomLabel 已导入
from utils.file_utils import resource_path
from config import (
    DEFAULT_FREE_TRANSCRIPTION_LANGUAGE,
    DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS,
    DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS
)


class FreeTranscriptionDialog(QDialog):
    settings_confirmed = pyqtSignal(dict)

    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JSON输出参数设置") # 保持窗口标题
        self.setModal(True)
        self.current_settings = current_settings
        self.selected_audio_file_path = current_settings.get('audio_file_path', "")

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # 使用与 SettingsDialog 相似的容器和背景色
        container = QWidget(self)
        container.setObjectName("freeTranscriptionDialogContainer") # 可以用新名字或与settingsDialogContainer共享样式
        container.setStyleSheet("""
            QWidget#freeTranscriptionDialogContainer {
                background-color: rgba(60, 60, 80, 220); /* 与 SettingsDialog 一致的背景色 */
                border-radius: 10px;
            }
        """)

        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0,0,0,0)
        dialog_layout.addWidget(container)

        main_layout = QVBoxLayout(container)
        # 与 SettingsDialog 一致的边距和间距
        main_layout.setContentsMargins(25, 20, 25, 20) 
        main_layout.setSpacing(18) 

        # 标题栏与 SettingsDialog 一致
        title_bar_layout = QHBoxLayout()
        title_label = CustomLabel("JSON输出参数设置") 
        # 沿用SettingsDialog的标题颜色方案
        title_label.setCustomColors(main_color=QColor(87, 128, 183), stroke_color=QColor(242, 234, 218)) 
        title_font = QFont('楷体', 20, QFont.Weight.Bold) # 与 SettingsDialog 一致的字体
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.setObjectName("dialogCloseButton") # 与 SettingsDialog 一致的对象名以共享样式
        close_button.setToolTip("关闭")
        close_button.clicked.connect(self.reject)

        title_bar_layout.addStretch()
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(close_button)
        main_layout.addLayout(title_bar_layout)

        # 参数的颜色也与SettingsDialog的参数标签一致
        self.param_label_main_color = QColor(87, 128, 183)
        self.param_label_stroke_color = QColor(242, 234, 218)

        # --- 音频文件选择 ---
        audio_file_layout = QHBoxLayout()
        audio_file_label = CustomLabel("音频文件:")
        audio_file_label.setFont(QFont('楷体', 16, QFont.Weight.Bold)) # 与 SettingsDialog 参数标签字体一致
        audio_file_label.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)

        self.audio_file_path_entry = QLineEdit(self.selected_audio_file_path)
        self.audio_file_path_entry.setPlaceholderText("请选择本地音频文件")
        self.audio_file_path_entry.setObjectName("pathEditDialogFT") # 新的对象名以应用特定样式
        self.audio_file_path_entry.setReadOnly(True) 

        browse_audio_button = QPushButton("浏览...")
        browse_audio_button.setObjectName("dialogBrowseButton") # 新的对象名
        browse_audio_button.clicked.connect(self._browse_audio_file)

        audio_file_layout.addWidget(audio_file_label, 2) # 调整比例
        audio_file_layout.addWidget(self.audio_file_path_entry, 5)
        audio_file_layout.addWidget(browse_audio_button, 1)
        main_layout.addLayout(audio_file_layout)

        # --- 语言选择 ---
        language_layout = QHBoxLayout()
        language_label = CustomLabel("转录语言:")
        language_label.setFont(QFont('楷体', 16, QFont.Weight.Bold)) #
        language_label.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        self.language_combo = QComboBox()
        self.language_combo.addItems(["自动检测", "日语", "中文", "英文"])
        current_lang_api_code = self.current_settings.get('language', DEFAULT_FREE_TRANSCRIPTION_LANGUAGE)
        lang_map_to_display = {"auto": "自动检测", "ja": "日语", "zh": "中文", "en": "英文"}
        display_lang_to_set = lang_map_to_display.get(current_lang_api_code, "自动检测")
        self.language_combo.setCurrentText(display_lang_to_set)
        self.language_combo.setObjectName("dialogComboBoxFT") # 新的对象名

        language_layout.addWidget(language_label, 2)
        language_layout.addWidget(self.language_combo, 6) # 占据更多空间
        main_layout.addLayout(language_layout)

        # --- 说话人数 ---
        num_speakers_layout = QHBoxLayout()
        num_speakers_label = CustomLabel("说话人数:")
        num_speakers_label.setFont(QFont('楷体', 16, QFont.Weight.Bold)) #
        num_speakers_label.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        self.num_speakers_combo = QComboBox()
        self.num_speakers_combo.addItem("自动检测", 0) 
        for i in range(1, 33):
            self.num_speakers_combo.addItem(str(i), i)
        current_num_speakers = self.current_settings.get('num_speakers', DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS)
        num_speaker_index = self.num_speakers_combo.findData(current_num_speakers)
        if num_speaker_index != -1:
            self.num_speakers_combo.setCurrentIndex(num_speaker_index)
        else:
            self.num_speakers_combo.setCurrentText("自动检测")

        self.num_speakers_combo.setObjectName("dialogComboBoxFT") # 与语言选择框共享样式

        num_speakers_layout.addWidget(num_speakers_label, 2)
        num_speakers_layout.addWidget(self.num_speakers_combo, 6)
        main_layout.addLayout(num_speakers_layout)
        
        # --- 标记音频事件 ---
        # 创建一个水平布局来容纳复选框，使其看起来不那么突兀
        checkbox_layout = QHBoxLayout()
        checkbox_layout.addStretch(1) # 左侧空白，使其居中一些
        self.tag_events_checkbox = QCheckBox("生成非语音声音事件") # 文本稍作调整
        self.tag_events_checkbox.setChecked(self.current_settings.get('tag_audio_events', DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS))
        self.tag_events_checkbox.setObjectName("dialogCheckboxFT") # 新的对象名
        checkbox_layout.addWidget(self.tag_events_checkbox)
        checkbox_layout.addStretch(1) # 右侧空白
        main_layout.addLayout(checkbox_layout)

        # 移除之前可能导致大片空白的 SpacerItem，或者调整其大小
        # main_layout.addSpacerItem(QSpacerItem(20, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        # 替换为一个固定高度的 Spacer，或者让按钮组自动填充剩余空间
        main_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)) #

        # --- 按钮组 ---
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15) # 与 SettingsDialog 一致
        button_layout.addStretch()
        self.confirm_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.reset_button = QPushButton("重置")
        self.confirm_button.clicked.connect(self._accept_settings)
        self.cancel_button.clicked.connect(self.reject)
        self.reset_button.clicked.connect(self._reset_settings)
        button_layout.addWidget(self.confirm_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self._apply_styles()
        self.resize(600, 420) # 调整对话框大小，参考 SettingsDialog (600,480)，略小因内容少

    def _browse_audio_file(self):
        start_dir = os.path.dirname(self.selected_audio_file_path) \
            if self.selected_audio_file_path and os.path.exists(os.path.dirname(self.selected_audio_file_path)) \
            else os.path.expanduser("~")
        
        supported_formats = "音频文件 (*.mp3 *.wav *.flac *.m4a *.ogg *.opus *.aac *.webm *.mp4 *.mov);;所有文件 (*.*)"
        filepath, _ = QFileDialog.getOpenFileName(self, "选择音频文件", start_dir, supported_formats)
        if filepath:
            self.selected_audio_file_path = filepath
            self.audio_file_path_entry.setText(filepath)

    def _accept_settings(self):
        if not self.selected_audio_file_path or not os.path.exists(self.selected_audio_file_path):
            error_dialog = QMessageBox(self)
            error_dialog.setWindowTitle("错误")
            error_dialog.setText("请选择一个有效的音频文件。")
            error_dialog.setIcon(QMessageBox.Icon.Warning)
            error_dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
            error_dialog.exec()
            return

        lang_display_to_api = {"自动检测": "auto", "日语": "ja", "中文": "zh", "英文": "en"}
        selected_lang_display = self.language_combo.currentText()
        
        new_settings = {
            'audio_file_path': self.selected_audio_file_path,
            'language': lang_display_to_api.get(selected_lang_display, DEFAULT_FREE_TRANSCRIPTION_LANGUAGE),
            'num_speakers': self.num_speakers_combo.currentData(),
            'tag_audio_events': self.tag_events_checkbox.isChecked(),
        }
        self.settings_confirmed.emit(new_settings)
        self.accept()

    def _reset_settings(self):
        # 音频文件路径不清空，允许用户保留之前的选择
        # self.selected_audio_file_path = ""
        # self.audio_file_path_entry.setText("")
        
        lang_map_to_display = {"auto": "自动检测", "ja": "日语", "zh": "中文", "en": "英文"}
        default_display_lang = lang_map_to_display.get(DEFAULT_FREE_TRANSCRIPTION_LANGUAGE, "自动检测")
        self.language_combo.setCurrentText(default_display_lang)

        default_num_speaker_index = self.num_speakers_combo.findData(DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS)
        if default_num_speaker_index != -1:
             self.num_speakers_combo.setCurrentIndex(default_num_speaker_index)
        else:
             self.num_speakers_combo.setCurrentText("自动检测")
            
        self.tag_events_checkbox.setChecked(DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS)

    def _apply_styles(self):
        # 借鉴 SettingsDialog 的样式
        # 并为新对话框的特定控件添加或调整样式
        style = f"""
            CustomLabel {{ /* 由 setCustomColors 控制颜色 */
                background-color: transparent;
            }}
            QLineEdit#pathEditDialogFT {{ /* 为音频路径输入框定制 */
                background-color: rgba(255, 255, 255, 50); 
                color: #EAEAEA; 
                border: 1px solid rgba(135, 206, 235, 120); 
                border-radius: 5px;
                padding: 5px; 
                font-family: 'Microsoft YaHei'; font-size: 12pt; /* 稍大一点 */
            }}
            QComboBox#dialogComboBoxFT {{ /* 为下拉框定制 */
                background-color: rgba(255, 255, 255, 50); 
                color: #EAEAEA;
                border: 1px solid rgba(135, 206, 235, 120); 
                border-radius: 5px;
                padding: 5px 8px; 
                font-family: 'Microsoft YaHei'; font-size: 12pt; /* 稍大一点 */
                min-height: 1.9em; /* 调整最小高度以匹配QLineEdit */
            }}
            QComboBox#dialogComboBoxFT::drop-down {{
                subcontrol-origin: padding; subcontrol-position: center right;
                width: 22px; /* 稍宽一点 */
                border-left: 1px solid rgba(135, 206, 235, 120);
            }}
            /* 如果需要自定义箭头图标，可以像 SettingsDialog 中那样添加 */
            
            QCheckBox#dialogCheckboxFT {{ /* 为复选框定制 */
                color: #E0E8F0; /* 浅色字体 */
                font-family: '楷体'; font-size: 14pt; font-weight: bold; /* 更清晰的字体 */
                spacing: 8px;
                background-color: transparent;
                padding: 5px 0px; /* 上下一点padding */
            }}
            QCheckBox#dialogCheckboxFT::indicator {{
                width: 20px; height: 20px; /* 稍大一点的指示器 */
                border: 1px solid rgba(135, 206, 235, 180);
                border-radius: 4px;
                background-color: rgba(255,255,255,40);
            }}
            QCheckBox#dialogCheckboxFT::indicator:checked {{
                background-color: rgba(100, 180, 230, 200); /* 更亮的选中色 */
                image: url('{resource_path('checkmark.png').replace(os.sep, '/') if resource_path('checkmark.png') and os.path.exists(resource_path('checkmark.png')) else "" }');
                background-repeat: no-repeat;
                background-position: center;
            }}

            QPushButton {{ /* 与 SettingsDialog 按钮样式一致 */
                background-color: rgba(100, 149, 237, 170); color: white;
                border: 1px solid rgba(135, 206, 235, 100);
                border-radius: 6px;
                font-family: '楷体'; font-weight: bold; font-size: 14pt;
                padding: 8px 20px;
                min-width: 80px;
            }}
            QPushButton:hover {{ background-color: rgba(120, 169, 247, 200); }}
            QPushButton:pressed {{ background-color: rgba(80, 129, 217, 200); }}

            QPushButton#dialogBrowseButton {{ /* 浏览按钮特定样式 */
                font-size: 12pt; /* 稍小一点 */
                padding: 6px 15px;
                min-width: 70px;
                 background-color: rgba(120, 170, 130, 170); /* 不同颜色以区分 */
            }}
             QPushButton#dialogBrowseButton:hover {{ background-color: rgba(140, 190, 150, 200); }}
             QPushButton#dialogBrowseButton:pressed {{ background-color: rgba(100, 150, 110, 200); }}


            QPushButton#dialogCloseButton {{ /* 与 SettingsDialog 关闭按钮一致 */
                background-color: rgba(255, 99, 71, 160); color: white;
                border: none; border-radius: 15px; 
                font-weight:bold; font-size: 12pt; 
                padding: 0px; min-width: 30px; max-width:30px; min-height:30px; max-height:30px;
            }}
            QPushButton#dialogCloseButton:hover {{ background-color: rgba(255, 99, 71, 200); }}
        """
        self.setStyleSheet(style)
        
        # 下拉箭头图标 (如果 SettingsDialog 有，这里也保持一致)
        # up_arrow_path_str = resource_path('up_arrow.png') # 这些是spinbox的，combobox用另一个
        # down_arrow_path_str = resource_path('down_arrow.png')
        dropdown_arrow_path_str = resource_path('dropdown_arrow.png') # 假设有这个图标
        qss_dropdown_arrow = ""
        if dropdown_arrow_path_str and os.path.exists(dropdown_arrow_path_str):
            qss_dropdown_arrow = f"url('{dropdown_arrow_path_str.replace(os.sep, '/')}')"

        combo_style_sheet = self.language_combo.styleSheet() # 获取基础样式
        combo_style_sheet += f"""
            QComboBox#dialogComboBoxFT::down-arrow {{
                image: {qss_dropdown_arrow if qss_dropdown_arrow else "none"};
                width: 10px; height: 10px; /* 调整箭头大小 */
                padding-right: 5px; /* 箭头右边距 */
            }}
            QComboBox#dialogComboBoxFT QAbstractItemView {{ /* 下拉菜单样式，参考主窗口 */
                background-color: rgba(70, 70, 90, 240); /* 深色背景 */
                color: #EAEAEA; 
                border: 1px solid rgba(135, 206, 235, 150); 
                border-radius:5px; padding:4px; outline:0px;
                selection-background-color: rgba(100, 149, 237, 190); /* 选中项背景 */
            }}
        """
        self.language_combo.setStyleSheet(combo_style_sheet)
        self.num_speakers_combo.setStyleSheet(combo_style_sheet)


    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, 'container') and self.container.layout().itemAt(0) and \
               event.position().y() < (self.container.layout().itemAt(0).geometry().height() + \
                                        self.container.layout().contentsMargins().top()):
                self.drag_pos = event.globalPosition().toPoint()
                self.is_dragging_dialog = True
                event.accept()
            else:
                self.is_dragging_dialog = False
                super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, 'is_dragging_dialog') and self.is_dragging_dialog and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, 'is_dragging_dialog'):
            self.is_dragging_dialog = False
        super().mouseReleaseEvent(event)