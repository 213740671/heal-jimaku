import os
import json
from typing import Optional, Any, Dict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QTextEdit, QCheckBox, QComboBox,
    QAbstractItemView, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QThread, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QColor, QTextCursor, QPixmap, QPainter, QBrush, QLinearGradient

import config as app_config

from config import (
    CONFIG_DIR, CONFIG_FILE,
    USER_MIN_DURATION_TARGET_KEY, USER_MAX_DURATION_KEY,
    USER_MAX_CHARS_PER_LINE_KEY, USER_DEFAULT_GAP_MS_KEY,
    DEFAULT_MIN_DURATION_TARGET, DEFAULT_MAX_DURATION,
    DEFAULT_MAX_CHARS_PER_LINE, DEFAULT_DEFAULT_GAP_MS,
    USER_FREE_TRANSCRIPTION_LANGUAGE_KEY,
    USER_FREE_TRANSCRIPTION_NUM_SPEAKERS_KEY,
    USER_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS_KEY,
    DEFAULT_FREE_TRANSCRIPTION_LANGUAGE,
    DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS,
    DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS,
    USER_LLM_API_BASE_URL_KEY, USER_LLM_MODEL_NAME_KEY,
    USER_LLM_API_KEY_KEY, USER_LLM_REMEMBER_API_KEY_KEY, USER_LLM_TEMPERATURE_KEY,
    DEFAULT_LLM_API_BASE_URL, DEFAULT_LLM_MODEL_NAME,
    DEFAULT_LLM_API_KEY, DEFAULT_LLM_REMEMBER_API_KEY, DEFAULT_LLM_TEMPERATURE
)

from utils.file_utils import resource_path
from .custom_widgets import TransparentWidget, CustomLabel, CustomLabel_title
from .conversion_worker import ConversionWorker
from core.srt_processor import SrtProcessor
from .settings_dialog import SettingsDialog
from .free_transcription_dialog import FreeTranscriptionDialog
from core.elevenlabs_api import ElevenLabsSTTClient
from .llm_advanced_settings_dialog import LlmAdvancedSettingsDialog


class HealJimakuApp(QMainWindow):
    _log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heal-Jimaku (治幕)")
        self.resize(1024, 864)

        self.srt_processor = SrtProcessor()
        self.elevenlabs_stt_client = ElevenLabsSTTClient()
        self.config: Dict[str, Any] = {}
        self.conversion_thread: Optional[QThread] = None
        self.worker: Optional[ConversionWorker] = None
        self.app_icon: Optional[QIcon] = None
        self.background: Optional[QPixmap] = None
        self.settings_button: Optional[QPushButton] = None
        self.free_transcription_button: Optional[QPushButton] = None
        self.llm_advanced_settings_button: Optional[QPushButton] = None
        self.llm_advanced_settings_dialog_instance: Optional[LlmAdvancedSettingsDialog] = None

        self.is_dragging = False
        self.drag_pos = QPoint()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.log_area_early_messages: list[str] = []
        self.advanced_srt_settings: Dict[str, Any] = {}
        self.free_transcription_settings: Dict[str, Any] = {}
        self.llm_advanced_settings: Dict[str, Any] = {}
        self._current_input_mode = "local_json"
        self._temp_audio_file_for_free_transcription: Optional[str] = None
        
        # 新增：跟踪免费转录按钮的状态
        self._free_transcription_button_is_in_cancel_mode = False

        icon_path_str = resource_path("icon.ico")
        if icon_path_str and os.path.exists(icon_path_str):
            self.app_icon = QIcon(icon_path_str)
        else:
            self._early_log("警告: 应用图标 icon.ico 未找到。")
            self.app_icon = QIcon()
        self.setWindowIcon(self.app_icon)

        bg_path_str = resource_path("background.png")
        if bg_path_str and os.path.exists(bg_path_str):
            self.background = QPixmap(bg_path_str)
        else:
            self._early_log("警告: 背景图片 background.png 未找到。")

        if self.background is None or self.background.isNull():
            self._create_fallback_background()
        else:
            self.background = self.background.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)

        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        self.main_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.api_key_entry: Optional[QLineEdit] = None
        self.remember_api_key_checkbox: Optional[QCheckBox] = None
        self.json_path_entry: Optional[QLineEdit] = None
        self.json_browse_button: Optional[QPushButton] = None
        self.json_format_combo: Optional[QComboBox] = None
        self.output_path_entry: Optional[QLineEdit] = None
        self.output_browse_button: Optional[QPushButton] = None
        self.progress_bar: Optional[QProgressBar] = None
        self.start_button: Optional[QPushButton] = None
        self.log_area: Optional[QTextEdit] = None

        self.init_ui()
        self._log_signal.connect(self.log_message)
        self._process_early_logs()
        self.load_config()
        self.center_window()
        QTimer.singleShot(100, self.apply_taskbar_icon)

    def _early_log(self, message: str):
        if hasattr(self, 'log_area') and self.log_area and self.log_area.isVisible():
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
        self.background = QPixmap(self.size())
        if self.background.isNull():
             self.background = QPixmap(1024, 864)
        self.background.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self.background)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(40, 40, 80, 200))
        gradient.setColorAt(1, QColor(20, 20, 40, 220))
        painter.fillRect(self.rect(), gradient)
        painter.end()

    def apply_taskbar_icon(self):
        if hasattr(self, 'windowHandle') and self.windowHandle() is not None:
            if self.app_icon and not self.app_icon.isNull():
                self.windowHandle().setIcon(self.app_icon)
        elif self.app_icon and not self.app_icon.isNull():
            self.setWindowIcon(self.app_icon)

    def center_window(self):
        try:
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.geometry()
                self.move((screen_geometry.width() - self.width()) // 2, (screen_geometry.height() - self.height()) // 2)
        except Exception as e:
            self._early_log(f"居中窗口时出错: {e}")
            self.move(100,100)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.background and not self.background.isNull():
            painter.drawPixmap(self.rect(), self.background)
        else:
            painter.fillRect(self.rect(), QColor(30, 30, 50, 230))
        super().paintEvent(event)

    def resizeEvent(self, event):
        bg_path_str = resource_path("background.png")
        if bg_path_str and os.path.exists(bg_path_str):
            new_pixmap = QPixmap(bg_path_str)
            if not new_pixmap.isNull():
                self.background = new_pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            else:
                self._create_fallback_background()
        else:
            self._create_fallback_background()
        super().resizeEvent(event)
        self.update()

    def _update_input_mode_ui(self):
        """根据当前的输入模式更新UI元素的启用/禁用状态"""
        if not self.json_path_entry or not self.json_browse_button or not self.json_format_combo:
            return

        if self._current_input_mode == "free_transcription":
            self.json_path_entry.setEnabled(False)
            self.json_browse_button.setEnabled(False)
            self.json_format_combo.setEnabled(False)
            self.json_path_entry.setPlaceholderText("通过'免费获取JSON'模式提供音频文件")
            
            # 新增：更新按钮文本为取消模式
            if self.free_transcription_button:
                self.free_transcription_button.setText("取消转录音频模式")
                self.free_transcription_button.setProperty("cancelMode", True)
                self.free_transcription_button.style().unpolish(self.free_transcription_button)
                self.free_transcription_button.style().polish(self.free_transcription_button)
                self._free_transcription_button_is_in_cancel_mode = True
            
            elevenlabs_index = self.json_format_combo.findText("ElevenLabs(推荐)")
            if elevenlabs_index != -1:
                self.json_format_combo.setCurrentIndex(elevenlabs_index)
        else: # local_json mode
            self.json_path_entry.setEnabled(True)
            self.json_browse_button.setEnabled(True)
            self.json_format_combo.setEnabled(True)
            self.json_path_entry.setPlaceholderText("选择包含ASR结果的 JSON 文件")
            
            # 新增：恢复按钮文本为正常模式
            if self.free_transcription_button:
                self.free_transcription_button.setText("免费获取JSON")
                self.free_transcription_button.setProperty("cancelMode", False)
                self.free_transcription_button.style().unpolish(self.free_transcription_button)
                self.free_transcription_button.style().polish(self.free_transcription_button)
                self._free_transcription_button_is_in_cancel_mode = False
            
            last_format = self.config.get('last_source_format', 'ElevenLabs(推荐)')
            last_format_index = self.json_format_combo.findText(last_format)
            if last_format_index != -1:
                 self.json_format_combo.setCurrentIndex(last_format_index)

    def init_ui(self):
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(30,30,30,30)
        main_layout.setSpacing(20)
        QApplication.setFont(QFont('楷体', 12))

        title_bar_layout = QHBoxLayout()
        
        # SRT高级参数设置按钮
        self.settings_button = QPushButton()
        settings_icon_path_str = resource_path("settings_icon.png")
        button_size = 38
        if settings_icon_path_str and os.path.exists(settings_icon_path_str):
            self.settings_button.setIcon(QIcon(settings_icon_path_str))
            icon_padding = 8
            calculated_icon_dim = max(1, button_size - icon_padding)
            self.settings_button.setIconSize(QSize(calculated_icon_dim, calculated_icon_dim))
        else:
            self.settings_button.setText("⚙S")
            self._early_log("警告: 设置图标 'settings_icon.png' 未找到。")
        
        self.settings_button.setFixedSize(button_size, button_size)
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setToolTip("自定义高级SRT参数")
        self.settings_button.clicked.connect(self.open_settings_dialog)
        title_bar_layout.addWidget(self.settings_button)

        # LLM 高级设置按钮
        self.llm_advanced_settings_button = QPushButton()
        llm_icon_path_str = resource_path("llm_setting_icon.png")
        if llm_icon_path_str and os.path.exists(llm_icon_path_str):
            self.llm_advanced_settings_button.setIcon(QIcon(llm_icon_path_str))
            icon_padding = 8
            calculated_icon_dim = max(1, button_size - icon_padding)
            self.llm_advanced_settings_button.setIconSize(QSize(calculated_icon_dim, calculated_icon_dim))
        else:
            self.llm_advanced_settings_button.setText("⚙L")
            self._early_log(f"警告: LLM 设置图标 'llm_setting_icon.png' 未找到于 {llm_icon_path_str}")
        
        self.llm_advanced_settings_button.setFixedSize(button_size, button_size)
        self.llm_advanced_settings_button.setObjectName("llmSettingsButton")
        self.llm_advanced_settings_button.setToolTip("LLM高级设置 (API地址, 模型, 温度等)")
        self.llm_advanced_settings_button.clicked.connect(self.open_llm_advanced_settings_dialog)
        title_bar_layout.addWidget(self.llm_advanced_settings_button)

        title = CustomLabel_title("Heal-Jimaku (治幕)")
        title_font = QFont('楷体', 24)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        control_btn_layout = QHBoxLayout()
        control_btn_layout.setSpacing(10)
        min_btn = QPushButton("─")
        min_btn.setFixedSize(30,30)
        min_btn.setObjectName("minButton")
        min_btn.clicked.connect(self.showMinimized)
        min_btn.setToolTip("最小化")

        close_btn = QPushButton("×")
        close_btn.setFixedSize(30,30)
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.close_application)
        close_btn.setToolTip("关闭")

        control_btn_layout.addWidget(min_btn)
        control_btn_layout.addWidget(close_btn)

        title_bar_layout.addStretch(1)
        title_bar_layout.addWidget(title,2,Qt.AlignmentFlag.AlignCenter)
        title_bar_layout.addStretch(1)
        title_bar_layout.addLayout(control_btn_layout)
        main_layout.addLayout(title_bar_layout)
        main_layout.addSpacing(20)

        content_widget = TransparentWidget(bg_color=QColor(191,191,191,50))
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(25,25,25,25)
        content_layout.setSpacing(15)

        api_group = QGroupBox("大模型 API KEY 设置(默认请输入ds官key)")
        api_group.setObjectName("apiGroup")
        api_layout = QVBoxLayout(api_group)
        api_layout.setSpacing(12)
        api_key_layout = QHBoxLayout()
        api_label = CustomLabel("API Key:")
        api_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.api_key_entry = QLineEdit()
        self.api_key_entry.setPlaceholderText("在此输入 API Key (详情请见LLM高级设置)")
        self.api_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_entry.setObjectName("apiKeyEdit")
        
        api_key_layout.addWidget(api_label)
        api_key_layout.addWidget(self.api_key_entry)
        api_layout.addLayout(api_key_layout)
        self.remember_api_key_checkbox = QCheckBox("记住 API Key")
        self.remember_api_key_checkbox.setObjectName("rememberCheckbox")
        api_layout.addWidget(self.remember_api_key_checkbox, alignment=Qt.AlignmentFlag.AlignLeft)

        file_group = QGroupBox("文件选择")
        file_group.setObjectName("fileGroup")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(12)
        
        json_input_line_layout = QHBoxLayout()

        json_label = CustomLabel("JSON 文件:")
        json_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        json_input_line_layout.addWidget(json_label,1)

        self.json_path_entry = QLineEdit()
        self.json_path_entry.setPlaceholderText("选择包含ASR结果的 JSON 文件")
        self.json_path_entry.setObjectName("pathEdit")
        json_input_line_layout.addWidget(self.json_path_entry,3)

        self.json_browse_button = QPushButton("浏览...")
        self.json_browse_button.setObjectName("browseButton")
        self.json_browse_button.clicked.connect(self.browse_json_file)
        json_input_line_layout.addWidget(self.json_browse_button,1)

        self.free_transcription_button = QPushButton("免费获取JSON")
        self.free_transcription_button.setObjectName("freeButton")
        self.free_transcription_button.clicked.connect(self.handle_free_transcription_button_click)
        json_input_line_layout.addWidget(self.free_transcription_button,1)

        file_layout.addLayout(json_input_line_layout)

        format_layout = QHBoxLayout()
        format_label = CustomLabel("JSON 格式:")
        format_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.json_format_combo = QComboBox()
        self.json_format_combo.addItems(["ElevenLabs(推荐)", "Whisper(推荐)", "Deepgram", "AssemblyAI"])
        self.json_format_combo.setObjectName("formatCombo")
        format_layout.addWidget(format_label,1)
        format_layout.addWidget(self.json_format_combo,5)
        file_layout.addLayout(format_layout)

        export_group = QGroupBox("导出与控制")
        export_group.setObjectName("exportGroup")
        export_layout = QVBoxLayout(export_group)
        export_layout.setSpacing(12)
        output_layout = QHBoxLayout()
        output_label = CustomLabel("导出目录:")
        output_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.output_path_entry = QLineEdit()
        self.output_path_entry.setPlaceholderText("选择 SRT 文件保存目录")
        self.output_path_entry.setObjectName("pathEdit")
        self.output_browse_button = QPushButton("浏览...")
        self.output_browse_button.setObjectName("browseButton")
        self.output_browse_button.clicked.connect(self.select_output_dir)
        output_layout.addWidget(output_label,1)
        output_layout.addWidget(self.output_path_entry,4)
        output_layout.addWidget(self.output_browse_button,1)
        export_layout.addLayout(output_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setObjectName("progressBar")
        export_layout.addWidget(self.progress_bar)
        
        self.start_button = QPushButton("开始转换")
        self.start_button.setFixedHeight(45)
        self.start_button.setFont(QFont('楷体', 14, QFont.Weight.Bold))
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.start_conversion)
        export_layout.addWidget(self.start_button)

        log_group = QGroupBox("日志")
        log_group.setObjectName("logGroup")
        log_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setObjectName("logArea")
        log_layout.addWidget(self.log_area)

        content_layout.addWidget(api_group,25)
        content_layout.addWidget(file_group,20)
        content_layout.addWidget(export_group,20)
        content_layout.addWidget(log_group,35)
        main_layout.addWidget(content_widget,1)
        
        self._update_input_mode_ui()
        self.apply_styles()

    def apply_styles(self):
        group_title_red = "#B34A4A"; input_text_red = "#7a1723"; soft_orangebrown_text = "#CB7E47"
        button_blue_bg = "rgba(100, 149, 237, 190)"; button_blue_hover = "rgba(80, 129, 217, 220)"
        control_min_blue = "rgba(135, 206, 235, 180)"; control_min_hover = "rgba(110, 180, 210, 220)"
        control_close_red = "rgba(255, 99, 71, 180)"; control_close_hover = "rgba(220, 70, 50, 220)"
        settings_btn_bg = "rgba(120, 120, 150, 180)"; settings_btn_hover = "rgba(100, 100, 130, 210)"
        group_bg = "rgba(52, 129, 184, 30)"
        input_bg = "rgba(255, 255, 255, 30)"; input_hover_bg = "rgba(255, 255, 255, 40)"
        input_focus_bg = "rgba(255, 255, 255, 50)"; input_border_color = "rgba(135, 206, 235, 90)"
        input_focus_border_color = "#87CEEB"
        log_bg = "rgba(0, 0, 0, 55)"; log_text_custom_color = "#F0783C"
        combo_dropdown_bg = "rgba(250, 250, 250, 235)"; combo_dropdown_text_color = "#2c3e50"
        combo_dropdown_border_color = "rgba(135, 206, 235, 150)"
        combo_dropdown_selection_bg = button_blue_hover; combo_dropdown_selection_text_color = "#FFFFFF"
        combo_dropdown_hover_bg = "rgba(173, 216, 230, 150)"

        label_green_color = QColor(92, 138, 111).name()

        qss_image_url = ""
        raw_arrow_path = resource_path("dropdown_arrow.png")
        if raw_arrow_path and os.path.exists(raw_arrow_path):
            abs_arrow_path = os.path.abspath(raw_arrow_path)
            formatted_path = abs_arrow_path.replace(os.sep, '/')
            qss_image_url = f"url('{formatted_path}')"
        else:
            self._early_log(f"警告: 下拉箭头图标 'dropdown_arrow.png' 未找到。")

        qss_checkmark_image_url = ""
        raw_checkmark_path = resource_path('checkmark.png')
        if raw_checkmark_path and os.path.exists(raw_checkmark_path):
            abs_checkmark_path = os.path.abspath(raw_checkmark_path)
            formatted_checkmark_path = abs_checkmark_path.replace(os.sep, '/')
            qss_checkmark_image_url = f"url('{formatted_checkmark_path}')"
        else:
            self._early_log(f"警告: 选中标记图标 'checkmark.png' 未找到。")

        free_button_bg = "rgba(100, 180, 120, 190)"; free_button_hover = "rgba(80, 160, 100, 220)"
        # 取消模式的样式
        cancel_button_bg = "rgba(200, 80, 80, 190)"; cancel_button_hover = "rgba(220, 100, 100, 220)"

        style = f"""
            QGroupBox {{ font: bold 17pt '楷体'; border: 1px solid rgba(135,206,235,80); border-radius:8px; margin-top:12px; background-color:{group_bg}; }}
            QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top left; left:15px; padding:2px 5px; color:{group_title_red}; font:bold 15pt '楷体'; }}
            QLineEdit#apiKeyEdit, QLineEdit#pathEdit {{ background-color:{input_bg}; color:{input_text_red}; border:1px solid {input_border_color}; border-radius:5px; padding:6px; font:bold 11pt 'Microsoft YaHei'; min-height:1.8em; }}
            QLineEdit#apiKeyEdit:hover, QLineEdit#pathEdit:hover {{ background-color:{input_hover_bg}; border:1px solid {input_focus_border_color}; }}
            QLineEdit#apiKeyEdit:focus, QLineEdit#pathEdit:focus {{ background-color:{input_focus_bg}; border:1px solid {input_focus_border_color}; }}
            QLineEdit#apiKeyEdit {{ font-family:'Consolas','Courier New',monospace; font-size:12pt; font-weight:bold; }}
            QPushButton#browseButton, QPushButton#startButton {{ background-color:{button_blue_bg}; color:white; border:none; border-radius:5px; font-family:'Microsoft YaHei'; font-weight:bold; }}
            QPushButton#browseButton {{ padding:6px 15px; font-size:10pt; }}
            QPushButton#freeButton {{ 
                background-color:{free_button_bg}; color:white; border:none; border-radius:5px;
                font-family:'Microsoft YaHei'; font-weight:bold; font-size:10pt; padding:6px 15px;
            }}
            QPushButton#freeButton:hover {{ background-color:{free_button_hover}; }}
            QPushButton#freeButton[cancelMode="true"] {{ 
                background-color:{cancel_button_bg}; color:white; border:none; border-radius:5px;
                font-family:'Microsoft YaHei'; font-weight:bold; font-size:10pt; padding:6px 15px;
            }}
            QPushButton#freeButton[cancelMode="true"]:hover {{ background-color:{cancel_button_hover}; }}
            QPushButton#startButton {{ padding:8px 25px; font:bold 14pt '楷体'; }}
            QPushButton#browseButton:hover, QPushButton#startButton:hover {{ background-color:{button_blue_hover}; }}
            QPushButton#startButton:disabled {{ background-color:rgba(100,100,100,150); color:#bbbbbb; }}
            QPushButton#minButton {{ background-color:{control_min_blue}; color:white; border:none; border-radius:15px; font-weight:bold; font-size:14pt; }}
            QPushButton#minButton:hover {{ background-color:{control_min_hover}; }}
            QPushButton#closeButton {{ background-color:{control_close_red}; color:white; border:none; border-radius:15px; font-weight:bold; font-size:14pt; }}
            QPushButton#closeButton:hover {{ background-color:{control_close_hover}; }}
            QPushButton#settingsButton, QPushButton#llmSettingsButton {{
                background-color:{settings_btn_bg}; color:white;
                border:none; border-radius:19px; 
                font-weight:bold; font-size:11pt; padding: 0px;
            }}
            QPushButton#settingsButton:hover, QPushButton#llmSettingsButton:hover {{ background-color:{settings_btn_hover}; }}
            QProgressBar#progressBar {{ border:1px solid rgba(135,206,235,80); border-radius:5px; text-align:center; background:rgba(0,0,0,40); height:22px; color:#f0f0f0; font-weight:bold; }}
            QProgressBar#progressBar::chunk {{ background-color:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5C8A6F,stop:1 #69CFF7); border-radius:5px; }}
            QTextEdit#logArea {{ background-color:{log_bg}; border:1px solid rgba(135,206,235,80); border-radius:5px; color:{log_text_custom_color}; font-family:'SimSun'; font-size:10pt; font-weight:bold;}}
            QComboBox#formatCombo {{
                background-color:{input_bg}; color:{input_text_red};
                border:1px solid {input_border_color}; border-radius:5px;
                padding: 2.5px 8px 2.5px 8px;
                font:bold 11pt 'Microsoft YaHei'; min-height:1.8em;
            }}
            QComboBox#formatCombo:hover {{ background-color:{input_hover_bg}; border-color:{input_focus_border_color}; }}
            QComboBox#formatCombo:focus {{ background-color:{input_focus_bg}; border-color:{input_focus_border_color}; }}
            QComboBox#formatCombo:on {{ background-color:{input_focus_bg}; border-color:{input_focus_border_color}; padding-right: 8px; }}
            QComboBox#formatCombo::drop-down {{
                subcontrol-origin: padding; subcontrol-position: center right;
                width: 20px; border: none;
            }}
            QComboBox#formatCombo::down-arrow {{
                image: {qss_image_url if qss_image_url else "none"};
                width: 8px; height: 8px;
            }}
            QComboBox QAbstractItemView {{ background-color:{combo_dropdown_bg}; color:{combo_dropdown_text_color}; border:1px solid {combo_dropdown_border_color}; border-radius:5px; padding:4px; outline:0px; }}
            QComboBox QAbstractItemView::item {{ padding:6px 10px; min-height:1.7em; border-radius:3px; background-color:transparent; }}
            QComboBox QAbstractItemView::item:selected {{ background-color:{combo_dropdown_selection_bg}; color:{combo_dropdown_selection_text_color}; }}
            QComboBox QAbstractItemView::item:hover {{ background-color:{combo_dropdown_hover_bg}; color:{combo_dropdown_text_color}; }}
            CustomLabel, CustomLabel_title {{ background-color:transparent; }}
            QLabel {{ background-color:transparent; }}

            QCheckBox#rememberCheckbox {{
                color: {label_green_color};
                font-family: '楷体';
                font-size: 13pt;
                font-weight: bold;
                spacing: 5px;
                background-color: transparent;
                padding: 0px;
            }}
            QCheckBox#rememberCheckbox::indicator {{
                width: 20px; height: 20px;
                border: 1px solid rgba(135, 206, 235, 180);
                border-radius: 4px;
                background-color: rgba(255,255,255,40);
            }}
            QCheckBox#rememberCheckbox::indicator:checked {{
                background-color: rgba(100, 180, 230, 200);
                image: {qss_checkmark_image_url if qss_checkmark_image_url else "none"};
                background-repeat: no-repeat;
                background-position: center;
            }}
        """
        self.setStyleSheet(style)

    def log_message(self, message: str):
        if self.log_area and self.log_area.isVisible():
            self.log_area.append(message)
            self.log_area.moveCursor(QTextCursor.MoveOperation.End)
        else:
            if hasattr(self, 'log_area_early_messages'):
                self.log_area_early_messages.append(message)
            print(f"[Log]: {message}")

    def load_config(self):
        if not os.path.exists(CONFIG_DIR):
            try:
                os.makedirs(CONFIG_DIR)
            except OSError as e:
                self._early_log(f"创建配置目录失败: {e}"); return

        default_cfg_structure = {
            'deepseek_api_key': "",
            'remember_api_key': True,
            'last_json_path': '',
            'last_output_path': '',
            'last_source_format': 'ElevenLabs(推荐)',
            'last_input_mode': 'local_json', # Default initial mode
            'last_free_transcription_audio_path': None,
            USER_MIN_DURATION_TARGET_KEY: DEFAULT_MIN_DURATION_TARGET,
            USER_MAX_DURATION_KEY: DEFAULT_MAX_DURATION,
            USER_MAX_CHARS_PER_LINE_KEY: DEFAULT_MAX_CHARS_PER_LINE,
            USER_DEFAULT_GAP_MS_KEY: DEFAULT_DEFAULT_GAP_MS,
            USER_FREE_TRANSCRIPTION_LANGUAGE_KEY: DEFAULT_FREE_TRANSCRIPTION_LANGUAGE,
            USER_FREE_TRANSCRIPTION_NUM_SPEAKERS_KEY: DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS,
            USER_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS_KEY: DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS,
            USER_LLM_API_BASE_URL_KEY: DEFAULT_LLM_API_BASE_URL,
            USER_LLM_MODEL_NAME_KEY: DEFAULT_LLM_MODEL_NAME,
            USER_LLM_API_KEY_KEY: DEFAULT_LLM_API_KEY,
            USER_LLM_REMEMBER_API_KEY_KEY: DEFAULT_LLM_REMEMBER_API_KEY,
            USER_LLM_TEMPERATURE_KEY: DEFAULT_LLM_TEMPERATURE,
        }

        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                self.config = default_cfg_structure.copy()
                self.config.update(loaded_config)
            else:
                self.config = default_cfg_structure.copy()

            if not self.config.get(USER_LLM_API_KEY_KEY) and self.config.get('deepseek_api_key'):
                self.config[USER_LLM_API_KEY_KEY] = self.config['deepseek_api_key']
            if self.config.get('remember_api_key') is not None:
                 self.config[USER_LLM_REMEMBER_API_KEY_KEY] = self.config['remember_api_key']

            if self.api_key_entry and self.remember_api_key_checkbox:
                remember_status = self.config.get(app_config.USER_LLM_REMEMBER_API_KEY_KEY, app_config.DEFAULT_LLM_REMEMBER_API_KEY)
                api_key_val = self.config.get(app_config.USER_LLM_API_KEY_KEY, app_config.DEFAULT_LLM_API_KEY)

                self.remember_api_key_checkbox.setChecked(remember_status)
                if remember_status:
                    self.api_key_entry.setText(api_key_val)
                else:
                    self.api_key_entry.clear()
            
            self.advanced_srt_settings = {
                'min_duration_target': self.config.get(USER_MIN_DURATION_TARGET_KEY, DEFAULT_MIN_DURATION_TARGET),
                'max_duration': self.config.get(USER_MAX_DURATION_KEY, DEFAULT_MAX_DURATION),
                'max_chars_per_line': self.config.get(USER_MAX_CHARS_PER_LINE_KEY, DEFAULT_MAX_CHARS_PER_LINE),
                'default_gap_ms': self.config.get(USER_DEFAULT_GAP_MS_KEY, DEFAULT_DEFAULT_GAP_MS),
            }
            self.free_transcription_settings = {
                'language': self.config.get(USER_FREE_TRANSCRIPTION_LANGUAGE_KEY, DEFAULT_FREE_TRANSCRIPTION_LANGUAGE),
                'num_speakers': self.config.get(USER_FREE_TRANSCRIPTION_NUM_SPEAKERS_KEY, DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS),
                'tag_audio_events': self.config.get(USER_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS_KEY, DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS),
            }
            self.llm_advanced_settings = {
                USER_LLM_API_BASE_URL_KEY: self.config.get(USER_LLM_API_BASE_URL_KEY, DEFAULT_LLM_API_BASE_URL),
                USER_LLM_MODEL_NAME_KEY: self.config.get(USER_LLM_MODEL_NAME_KEY, DEFAULT_LLM_MODEL_NAME),
                USER_LLM_API_KEY_KEY: self.config.get(USER_LLM_API_KEY_KEY, DEFAULT_LLM_API_KEY),
                USER_LLM_REMEMBER_API_KEY_KEY: self.config.get(USER_LLM_REMEMBER_API_KEY_KEY, DEFAULT_LLM_REMEMBER_API_KEY),
                USER_LLM_TEMPERATURE_KEY: self.config.get(USER_LLM_TEMPERATURE_KEY, DEFAULT_LLM_TEMPERATURE),
            }

            # --- 修改点 开始 ---
            # 总是以 local_json 模式启动，忽略上次保存的 input_mode
            self._current_input_mode = 'local_json'
            # 同时，清除可能残留的临时音频文件路径，因为我们强制进入本地JSON模式
            self._temp_audio_file_for_free_transcription = None
            # 更新内存中的配置，以便如果立即保存，它也会反映这个状态
            self.config['last_input_mode'] = 'local_json' 
            self.config['last_free_transcription_audio_path'] = None
            # --- 修改点 结束 ---
            
            if self.json_path_entry:
                # 由于上面强制_current_input_mode = 'local_json'，这里不再需要检查它
                # 直接尝试加载 last_json_path
                if os.path.isfile(self.config.get('last_json_path', '')):
                    self.json_path_entry.setText(self.config.get('last_json_path', ''))
                # 如果 _current_input_mode 被强制为 'local_json' 后, json_path_entry 应该显示本地json的占位符
                # self._update_input_mode_ui() 会处理这个
            
            if self.json_format_combo:
                format_index = self.json_format_combo.findText(self.config.get('last_source_format', 'ElevenLabs(推荐)'))
                self.json_format_combo.setCurrentIndex(format_index if format_index != -1 else 0)
            
            if self.output_path_entry:
                last_output = self.config.get('last_output_path', '')
                if os.path.isdir(last_output):
                    self.output_path_entry.setText(last_output)
                elif os.path.isdir(os.path.join(os.path.expanduser("~"),"Documents")):
                    self.output_path_entry.setText(os.path.join(os.path.expanduser("~"),"Documents"))
                else:
                    self.output_path_entry.setText(os.path.expanduser("~"))

            self._update_input_mode_ui() # 这将确保按钮基于强制的 'local_json' 模式正确更新

        except (json.JSONDecodeError, Exception) as e:
             self.log_message(f"加载配置出错或配置格式错误: {e}")
             self.config = default_cfg_structure.copy()
             self.advanced_srt_settings = {
                'min_duration_target': DEFAULT_MIN_DURATION_TARGET, 'max_duration': DEFAULT_MAX_DURATION,
                'max_chars_per_line': DEFAULT_MAX_CHARS_PER_LINE, 'default_gap_ms': DEFAULT_DEFAULT_GAP_MS,
             }
             self.free_transcription_settings = {
                'language': DEFAULT_FREE_TRANSCRIPTION_LANGUAGE, 'num_speakers': DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS,
                'tag_audio_events': DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS,
             }
             self.llm_advanced_settings = {
                USER_LLM_API_BASE_URL_KEY: DEFAULT_LLM_API_BASE_URL, USER_LLM_MODEL_NAME_KEY: DEFAULT_LLM_MODEL_NAME,
                USER_LLM_API_KEY_KEY: DEFAULT_LLM_API_KEY, USER_LLM_REMEMBER_API_KEY_KEY: DEFAULT_LLM_REMEMBER_API_KEY,
                USER_LLM_TEMPERATURE_KEY: DEFAULT_LLM_TEMPERATURE,
             }
             # 确保在异常情况下也重置为 local_json 模式
             self._current_input_mode = 'local_json'
             self._temp_audio_file_for_free_transcription = None
             self._update_input_mode_ui()

    def save_config(self):
        if not (self.api_key_entry and \
                self.json_path_entry and self.output_path_entry and self.json_format_combo):
            self.log_message("警告: UI组件未完全初始化，无法保存配置。")
            return

        if self.remember_api_key_checkbox:
            remember_main_ui = self.remember_api_key_checkbox.isChecked()
            self.config[app_config.USER_LLM_REMEMBER_API_KEY_KEY] = remember_main_ui
            if not remember_main_ui and self.api_key_entry and self.api_key_entry.text().strip():
                self.config[app_config.USER_LLM_API_KEY_KEY] = ""
            elif remember_main_ui and self.api_key_entry:
                self.config[app_config.USER_LLM_API_KEY_KEY] = self.api_key_entry.text().strip()

        if self.advanced_srt_settings:
            self.config[USER_MIN_DURATION_TARGET_KEY] = self.advanced_srt_settings.get('min_duration_target', DEFAULT_MIN_DURATION_TARGET)
            self.config[USER_MAX_DURATION_KEY] = self.advanced_srt_settings.get('max_duration', DEFAULT_MAX_DURATION)
            self.config[USER_MAX_CHARS_PER_LINE_KEY] = self.advanced_srt_settings.get('max_chars_per_line', DEFAULT_MAX_CHARS_PER_LINE)
            self.config[USER_DEFAULT_GAP_MS_KEY] = self.advanced_srt_settings.get('default_gap_ms', DEFAULT_DEFAULT_GAP_MS)
        
        if self.free_transcription_settings:
            self.config[USER_FREE_TRANSCRIPTION_LANGUAGE_KEY] = self.free_transcription_settings.get('language', DEFAULT_FREE_TRANSCRIPTION_LANGUAGE)
            self.config[USER_FREE_TRANSCRIPTION_NUM_SPEAKERS_KEY] = self.free_transcription_settings.get('num_speakers', DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS)
            self.config[USER_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS_KEY] = self.free_transcription_settings.get('tag_audio_events', DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS)
        
        self.config[USER_LLM_API_BASE_URL_KEY] = self.llm_advanced_settings.get(USER_LLM_API_BASE_URL_KEY, DEFAULT_LLM_API_BASE_URL)
        self.config[USER_LLM_MODEL_NAME_KEY] = self.llm_advanced_settings.get(USER_LLM_MODEL_NAME_KEY, DEFAULT_LLM_MODEL_NAME)
        self.config[USER_LLM_TEMPERATURE_KEY] = self.llm_advanced_settings.get(USER_LLM_TEMPERATURE_KEY, DEFAULT_LLM_TEMPERATURE)

        if self._current_input_mode == 'local_json':
            self.config['last_json_path'] = self.json_path_entry.text()
        elif self._temp_audio_file_for_free_transcription:
             self.config['last_free_transcription_audio_path'] = self._temp_audio_file_for_free_transcription
        
        self.config['last_output_path'] = self.output_path_entry.text()
        self.config['last_source_format'] = self.json_format_combo.currentText()
        self.config['last_input_mode'] = self._current_input_mode
        
        if USER_LLM_API_KEY_KEY in self.config and 'deepseek_api_key' in self.config:
            del self.config['deepseek_api_key']
        if USER_LLM_REMEMBER_API_KEY_KEY in self.config and 'remember_api_key' in self.config:
            del self.config['remember_api_key']

        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log_message(f"保存配置失败: {e}")

    def browse_json_file(self):
        if not self.json_path_entry: return
        if self._current_input_mode != "local_json":
            self.log_message("提示：当前为'免费获取JSON'模式，请通过对应对话框选择音频文件。")
            return

        start_dir = os.path.dirname(self.json_path_entry.text()) \
            if self.json_path_entry.text() and os.path.exists(os.path.dirname(self.json_path_entry.text())) \
            else os.path.expanduser("~")
        filepath, _ = QFileDialog.getOpenFileName(self, "选择 JSON 文件", start_dir, "JSON 文件 (*.json);;所有文件 (*.*)")
        if filepath:
            self.json_path_entry.setText(filepath)
            self._current_input_mode = "local_json"
            self._temp_audio_file_for_free_transcription = None
            self._update_input_mode_ui()

    def select_output_dir(self):
        if not self.output_path_entry: return
        start_dir = self.output_path_entry.text() \
            if self.output_path_entry.text() and os.path.isdir(self.output_path_entry.text()) \
            else os.path.expanduser("~")
        dirpath = QFileDialog.getExistingDirectory(self, "选择导出目录", start_dir)
        if dirpath:
            self.output_path_entry.setText(dirpath)

    def open_settings_dialog(self):
        if not self.advanced_srt_settings: 
             self.advanced_srt_settings = {
                'min_duration_target': self.config.get(USER_MIN_DURATION_TARGET_KEY, DEFAULT_MIN_DURATION_TARGET),
                'max_duration': self.config.get(USER_MAX_DURATION_KEY, DEFAULT_MAX_DURATION),
                'max_chars_per_line': self.config.get(USER_MAX_CHARS_PER_LINE_KEY, DEFAULT_MAX_CHARS_PER_LINE),
                'default_gap_ms': self.config.get(USER_DEFAULT_GAP_MS_KEY, DEFAULT_DEFAULT_GAP_MS),
             }
        dialog = SettingsDialog(self.advanced_srt_settings, self)
        dialog.settings_applied.connect(self.apply_advanced_settings)
        dialog.exec()

    def apply_advanced_settings(self, new_settings: dict):
        self.advanced_srt_settings = new_settings
        self.log_message(f"高级SRT参数已更新: {new_settings}")
        self.save_config()

    def open_llm_advanced_settings_dialog(self):
        """打开LLM高级设置对话框"""
        self.llm_advanced_settings = {
            USER_LLM_API_BASE_URL_KEY: self.config.get(USER_LLM_API_BASE_URL_KEY, DEFAULT_LLM_API_BASE_URL),
            USER_LLM_MODEL_NAME_KEY: self.config.get(USER_LLM_MODEL_NAME_KEY, DEFAULT_LLM_MODEL_NAME),
            USER_LLM_API_KEY_KEY: self.config.get(USER_LLM_API_KEY_KEY, DEFAULT_LLM_API_KEY),
            USER_LLM_REMEMBER_API_KEY_KEY: self.config.get(USER_LLM_REMEMBER_API_KEY_KEY, DEFAULT_LLM_REMEMBER_API_KEY),
            USER_LLM_TEMPERATURE_KEY: self.config.get(USER_LLM_TEMPERATURE_KEY, DEFAULT_LLM_TEMPERATURE),
        }

        if not self.llm_advanced_settings_dialog_instance:
            self.llm_advanced_settings_dialog_instance = LlmAdvancedSettingsDialog(self, self.llm_advanced_settings.copy(), log_signal=self._log_signal)
            self.llm_advanced_settings_dialog_instance.settings_saved.connect(self._on_llm_settings_saved)
        else:
            self.llm_advanced_settings_dialog_instance.current_config = self.llm_advanced_settings.copy()
            self.llm_advanced_settings_dialog_instance.log_signal = self._log_signal
            self.llm_advanced_settings_dialog_instance._load_settings_to_ui()
        
        self.llm_advanced_settings_dialog_instance.exec()

    def _on_llm_settings_saved(self):
        """当LLM高级设置对话框点击"确认"并保存后调用"""
        if self.llm_advanced_settings_dialog_instance:
            updated_settings_from_dialog = self.llm_advanced_settings_dialog_instance.get_current_settings()
            
            self.config[USER_LLM_API_BASE_URL_KEY] = updated_settings_from_dialog.get(USER_LLM_API_BASE_URL_KEY)
            self.config[USER_LLM_MODEL_NAME_KEY] = updated_settings_from_dialog.get(USER_LLM_MODEL_NAME_KEY)
            self.config[USER_LLM_TEMPERATURE_KEY] = updated_settings_from_dialog.get(USER_LLM_TEMPERATURE_KEY)
            self.config[USER_LLM_REMEMBER_API_KEY_KEY] = updated_settings_from_dialog.get(USER_LLM_REMEMBER_API_KEY_KEY)
            
            api_key_from_dialog = updated_settings_from_dialog.get(USER_LLM_API_KEY_KEY, "")
            if self.config[USER_LLM_REMEMBER_API_KEY_KEY]:
                self.config[USER_LLM_API_KEY_KEY] = api_key_from_dialog
            else:
                self.config[USER_LLM_API_KEY_KEY] = ""

            self.llm_advanced_settings = updated_settings_from_dialog.copy()

            if self.api_key_entry and self.remember_api_key_checkbox:
                key_to_display = ""
                if self.config.get(app_config.USER_LLM_REMEMBER_API_KEY_KEY):
                    key_to_display = self.config.get(app_config.USER_LLM_API_KEY_KEY, "")
                
                if self.api_key_entry.text() != key_to_display:
                    self.api_key_entry.setText(key_to_display)
                self.remember_api_key_checkbox.setChecked(self.config.get(USER_LLM_REMEMBER_API_KEY_KEY))
            
            self.srt_processor.update_llm_config(
                api_key=self.config.get(USER_LLM_API_KEY_KEY),
                base_url=self.config.get(USER_LLM_API_BASE_URL_KEY),
                model=self.config.get(USER_LLM_MODEL_NAME_KEY),
                temperature=self.config.get(USER_LLM_TEMPERATURE_KEY)
            )
            self.log_message("LLM高级设置已更新并保存。")

    def handle_free_transcription_button_click(self):
        """处理免费转录按钮点击事件，根据当前模式执行不同操作"""
        if self._free_transcription_button_is_in_cancel_mode:
            # 当前是取消模式，执行取消操作
            self._cancel_free_transcription_mode()
        else:
            # 当前是正常模式，打开免费转录对话框
            self._open_free_transcription_dialog()

    def _cancel_free_transcription_mode(self):
        """取消免费转录模式，恢复到本地JSON模式"""
        self.log_message("用户取消免费转录模式，切换回本地JSON文件模式。")
        self._current_input_mode = "local_json"
        
        # 清除音频文件路径
        self._temp_audio_file_for_free_transcription = None
        
        # 尝试恢复上次的本地JSON路径
        if self.json_path_entry:
            last_json_path = self.config.get('last_json_path', '')
            self.json_path_entry.setText(last_json_path)
            if not last_json_path:
                self.json_path_entry.setPlaceholderText("选择包含ASR结果的 JSON 文件")
        
        # 更新UI状态
        self._update_input_mode_ui()
        
        # 保存配置
        self.save_config()

    def _open_free_transcription_dialog(self):
        """打开免费转录对话框（原来的open_free_transcription_dialog逻辑）"""
        current_dialog_settings = self.free_transcription_settings.copy()
        current_dialog_settings['audio_file_path'] = self._temp_audio_file_for_free_transcription or ""
        
        dialog = FreeTranscriptionDialog(current_dialog_settings, self)
        dialog.settings_confirmed.connect(self.apply_free_transcription_settings)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            pass
        else:
            self._cancel_free_transcription_mode()

    def apply_free_transcription_settings(self, new_settings: dict):
        self._current_input_mode = "free_transcription"
        self._temp_audio_file_for_free_transcription = new_settings.get('audio_file_path')
        
        self.free_transcription_settings['language'] = new_settings.get('language')
        self.free_transcription_settings['num_speakers'] = new_settings.get('num_speakers')
        self.free_transcription_settings['tag_audio_events'] = new_settings.get('tag_audio_events')
        
        if self.json_path_entry and self._temp_audio_file_for_free_transcription:
            self.json_path_entry.setText(f"音频: {os.path.basename(self._temp_audio_file_for_free_transcription)}")
        
        self._update_input_mode_ui()  # 这会更新按钮文本
        self.log_message(f"免费转录参数已更新: { {k:v for k,v in new_settings.items() if k != 'audio_file_path'} }")
        self.log_message(f"  将使用音频文件: {self._temp_audio_file_for_free_transcription}")
        self.save_config()

    def start_conversion(self):
        if not (self.api_key_entry and self.output_path_entry and \
                self.start_button and self.progress_bar and self.log_area and \
                self.json_format_combo and self.json_path_entry):
            QMessageBox.critical(self, "错误", "UI组件未完全初始化，无法开始转换。")
            return

        current_ui_api_key = self.api_key_entry.text().strip()
        if current_ui_api_key:
            effective_api_key = current_ui_api_key
            if self.config.get(app_config.USER_LLM_REMEMBER_API_KEY_KEY):
                self.config[app_config.USER_LLM_API_KEY_KEY] = effective_api_key
        else:
            effective_api_key = self.config.get(app_config.USER_LLM_API_KEY_KEY, app_config.DEFAULT_LLM_API_KEY)

        llm_base_url = self.config.get(app_config.USER_LLM_API_BASE_URL_KEY, app_config.DEFAULT_LLM_API_BASE_URL)
        llm_model_name = self.config.get(app_config.USER_LLM_MODEL_NAME_KEY, app_config.DEFAULT_LLM_MODEL_NAME)
        llm_temperature = self.config.get(app_config.USER_LLM_TEMPERATURE_KEY, app_config.DEFAULT_LLM_TEMPERATURE)
        
        output_dir = self.output_path_entry.text().strip()

        if not effective_api_key:
            QMessageBox.warning(self, "缺少信息", "请在API设置或LLM高级设置中配置 API Key。"); return
        if not output_dir:
            QMessageBox.warning(self, "缺少信息", "请选择导出目录。"); return
        if not os.path.isdir(output_dir):
            QMessageBox.critical(self, "错误", f"导出目录无效: {output_dir}"); return

        json_path_for_worker = ""
        source_format_key = "elevenlabs"

        if self._current_input_mode == "free_transcription":
            if not self._temp_audio_file_for_free_transcription or \
               not os.path.isfile(self._temp_audio_file_for_free_transcription):
                QMessageBox.critical(self, "错误", "请在'免费获取'中选择一个有效的音频文件。")
                return
            self.log_message("准备通过免费ElevenLabs API获取JSON...")
        elif self._current_input_mode == "local_json":
            json_path_for_worker = self.json_path_entry.text().strip()
            if not json_path_for_worker:
                QMessageBox.warning(self, "缺少信息", "请选择 JSON 文件。"); return
            if not os.path.isfile(json_path_for_worker):
                QMessageBox.critical(self, "错误", f"JSON 文件不存在: {json_path_for_worker}"); return
            
            selected_format_text = self.json_format_combo.currentText()
            source_format_map = {"ElevenLabs(推荐)":"elevenlabs", "Whisper(推荐)":"whisper", "Deepgram":"deepgram", "AssemblyAI":"assemblyai"}
            source_format_key = source_format_map.get(selected_format_text, "elevenlabs")
        else:
            QMessageBox.critical(self, "内部错误", "未知的输入模式。"); return

        self.srt_processor.configure_from_main_config(self.config)

        current_llm_config_for_worker = {
            app_config.USER_LLM_API_KEY_KEY: effective_api_key,
            app_config.USER_LLM_API_BASE_URL_KEY: llm_base_url,
            app_config.USER_LLM_MODEL_NAME_KEY: llm_model_name,
            app_config.USER_LLM_TEMPERATURE_KEY: llm_temperature,
        }

        self.save_config()
        self.start_button.setEnabled(False)
        self.start_button.setText("转换中...")
        self.progress_bar.setValue(0)
        self.log_message("--------------------")
        self.log_message("开始新的转换任务...")

        if self.conversion_thread and self.conversion_thread.isRunning():
             self.log_message("警告：上一个转换任务仍在进行中。请等待其完成后再开始新的任务。")
             self.start_button.setEnabled(True)
             self.start_button.setText("开始转换")
             return
        
        self.log_message("创建新的转换线程和工作对象...")

        free_transcription_params_for_worker = None
        if self._current_input_mode == "free_transcription":
            free_transcription_params_for_worker = {
                "audio_file_path": self._temp_audio_file_for_free_transcription,
                **self.free_transcription_settings
            }

        self.conversion_thread = QThread(parent=self) 
        self.worker = ConversionWorker(
            input_json_path=json_path_for_worker, 
            output_dir=output_dir,
            srt_processor=self.srt_processor,
            source_format=source_format_key, 
            input_mode=self._current_input_mode, 
            free_transcription_params=free_transcription_params_for_worker, 
            elevenlabs_stt_client=self.elevenlabs_stt_client,
            llm_config=current_llm_config_for_worker
        )
        self.worker.moveToThread(self.conversion_thread)
        
        self.worker.signals.finished.connect(self.on_conversion_finished)
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.log_message.connect(self.log_message)
        if hasattr(self.worker.signals, 'free_transcription_json_generated'):
            self.worker.signals.free_transcription_json_generated.connect(self.on_free_json_generated_by_worker)

        self.conversion_thread.started.connect(self.worker.run)
        
        self.worker.signals.finished.connect(self.conversion_thread.quit)
        self.worker.signals.finished.connect(self.worker.deleteLater) 
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater) 
        self.conversion_thread.finished.connect(self._clear_worker_references) 
        
        self.conversion_thread.start()

    def on_free_json_generated_by_worker(self, generated_json_path: str):
        self.log_message(f"Worker已生成JSON字幕: {generated_json_path}")
        pass

    def _clear_worker_references(self):
        self.log_message("清理旧的worker和线程引用...")
        self.worker = None
        self.conversion_thread = None 
        if hasattr(self, 'start_button') and self.start_button: 
            self.start_button.setEnabled(True)
            self.start_button.setText("开始转换")

    def update_progress(self, value: int):
        if self.progress_bar:
            self.progress_bar.setValue(value)

    @staticmethod
    def show_message_box(parent_widget: Optional[QWidget], title: str, message: str, success: bool):
        if parent_widget and parent_widget.isVisible():
            QTimer.singleShot(0, lambda: (
                QMessageBox.information(parent_widget, title, message) if success
                else QMessageBox.critical(parent_widget, title, message)
            ))
        else:
            print(f"消息框 [{title} - {'成功' if success else '失败'}]: {message} (父控件不可用)")

    def on_conversion_finished(self, message: str, success: bool):
        if hasattr(self, 'start_button') and self.start_button:
             self.start_button.setEnabled(True)
             self.start_button.setText("开始转换")

        if self.progress_bar:
            current_progress = self.progress_bar.value()
            if success:
                self.progress_bar.setValue(100)
            else:
                self.progress_bar.setValue(current_progress if current_progress > 0 else 0) 
        
        HealJimakuApp.show_message_box(self, "转换结果", message, success)

        self.log_message("任务结束，输入模式已重置为本地JSON文件模式。")
        self._current_input_mode = "local_json"
        
        last_local_json_path = self.config.get('last_json_path', '')
        if self.json_path_entry:
            self.json_path_entry.setText(last_local_json_path) 
            if not last_local_json_path:
                 self.json_path_entry.setPlaceholderText("选择包含ASR结果的 JSON 文件")

        self._temp_audio_file_for_free_transcription = None
        self._update_input_mode_ui()  # 这会重置按钮文本
        self.save_config()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            title_bar_height = 80 
            is_on_title_bar_area = event.position().y() < title_bar_height
            widget_at_pos = self.childAt(event.position().toPoint())

            interactive_title_bar_buttons = {self.settings_button, self.llm_advanced_settings_button}
            if widget_at_pos in interactive_title_bar_buttons or \
               (hasattr(widget_at_pos, 'objectName') and widget_at_pos.objectName() in ["minButton", "closeButton"]):
                super().mousePressEvent(event)
                return

            is_interactive_control = False
            current_widget = widget_at_pos
            interactive_widgets_tuple = (QPushButton, QLineEdit, QCheckBox, QTextEdit, QProgressBar, QComboBox, QAbstractItemView, QDialog)
            
            active_popup = QApplication.activePopupWidget()
            if active_popup and active_popup.geometry().contains(event.globalPosition().toPoint()):
                super().mousePressEvent(event)
                return

            while current_widget is not None:
                if isinstance(current_widget, interactive_widgets_tuple) or \
                   (hasattr(current_widget, 'objectName') and current_widget.objectName().startswith('qt_scrollarea')):
                    is_interactive_control = True
                    break
                current_widget = current_widget.parentWidget()

            if is_on_title_bar_area and not is_interactive_control:
                self.drag_pos = event.globalPosition().toPoint()
                self.is_dragging = True
                event.accept()
            else:
                super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_dragging and event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            
    def close_application(self):
        self.save_config()
        self.close()

    def closeEvent(self, event):
        self.log_message("正在关闭应用程序...")
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.log_message("尝试停止正在进行的转换任务...")
            if self.worker:
                self.worker.stop() 
        
        self.save_config()
        super().closeEvent(event)
        QApplication.instance().quit()