import os
import json
from typing import Optional, Any, Dict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QTextEdit, QCheckBox, QComboBox,
    QAbstractItemView, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QThread, QSize
from PyQt6.QtGui import QIcon, QFont, QColor, QTextCursor, QPixmap, QPainter, QBrush, QLinearGradient

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
    DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS
)
from utils.file_utils import resource_path
from .custom_widgets import TransparentWidget, CustomLabel, CustomLabel_title
from .conversion_worker import ConversionWorker
from core.srt_processor import SrtProcessor
from .settings_dialog import SettingsDialog
from .free_transcription_dialog import FreeTranscriptionDialog # 新增导入
from core.elevenlabs_api import ElevenLabsSTTClient # 新增导入


class HealJimakuApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heal-Jimaku (治幕)")
        self.resize(1024, 864)

        self.srt_processor = SrtProcessor()
        self.elevenlabs_stt_client = ElevenLabsSTTClient() # 初始化 ElevenLabs 客户端
        self.config: Dict[str, Any] = {}
        self.conversion_thread: Optional[QThread] = None
        self.worker: Optional[ConversionWorker] = None
        self.app_icon: Optional[QIcon] = None
        self.background: Optional[QPixmap] = None
        self.settings_button: Optional[QPushButton] = None
        self.free_transcription_button: Optional[QPushButton] = None # 新增按钮

        self.is_dragging = False
        self.drag_pos = QPoint()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.log_area_early_messages: list[str] = []
        self.advanced_srt_settings: Dict[str, Any] = {}
        self.free_transcription_settings: Dict[str, Any] = {} # 用于存储免费转录对话框的设置
        self._current_input_mode = "local_json" # "local_json" 或 "free_transcription"
        self._temp_audio_file_for_free_transcription: Optional[str] = None # 临时存储选择的音频文件路径

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
        self._process_early_logs()
        self.load_config() # 加载配置，会应用保存的输入模式
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
            self.json_format_combo.setEnabled(False) # 从免费转录获取的JSON格式固定为ElevenLabs
            self.json_path_entry.setPlaceholderText("通过“免费获取”模式提供音频文件")
            # 自动将格式设置为ElevenLabs并禁用
            elevenlabs_index = self.json_format_combo.findText("ElevenLabs(推荐)")
            if elevenlabs_index != -1:
                self.json_format_combo.setCurrentIndex(elevenlabs_index)
        else: # local_json mode
            self.json_path_entry.setEnabled(True)
            self.json_browse_button.setEnabled(True)
            self.json_format_combo.setEnabled(True)
            self.json_path_entry.setPlaceholderText("选择包含ASR结果的 JSON 文件")
            # 恢复上次选择的格式（如果不是ElevenLabs）
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
        self.settings_button = QPushButton()
        settings_icon_path_str = resource_path("settings_icon.png")
        button_size = 38
        if settings_icon_path_str and os.path.exists(settings_icon_path_str):
            self.settings_button.setIcon(QIcon(settings_icon_path_str))
            icon_padding = 8
            calculated_icon_dim = max(1, button_size - icon_padding)
            self.settings_button.setIconSize(QSize(calculated_icon_dim, calculated_icon_dim))
        else:
            self.settings_button.setText("⚙")
            self._early_log("警告: 设置图标 'settings_icon.png' 未找到。")
        
        self.settings_button.setFixedSize(button_size, button_size)
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setToolTip("自定义高级SRT参数")
        self.settings_button.clicked.connect(self.open_settings_dialog)

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

        title_bar_layout.addWidget(self.settings_button)
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

        api_group = QGroupBox("DeepSeek API 设置")
        api_group.setObjectName("apiGroup")
        api_layout = QVBoxLayout(api_group)
        api_layout.setSpacing(12)
        api_key_layout = QHBoxLayout()
        api_label = CustomLabel("API Key:")
        api_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.api_key_entry = QLineEdit()
        self.api_key_entry.setPlaceholderText("sk-...")
        self.api_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_entry.setObjectName("apiKeyEdit")
        self.remember_api_key_checkbox = QCheckBox("记住 API Key")
        self.remember_api_key_checkbox.setChecked(True)
        self.remember_api_key_checkbox.setObjectName("rememberCheckbox")
        api_key_layout.addWidget(api_label)
        api_key_layout.addWidget(self.api_key_entry)
        api_layout.addLayout(api_key_layout)
        api_layout.addWidget(self.remember_api_key_checkbox, alignment=Qt.AlignmentFlag.AlignLeft)

        file_group = QGroupBox("文件选择")
        file_group.setObjectName("fileGroup")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(12)
        
        json_input_line_layout = QHBoxLayout() # 用于放置 JSON输入框 和 两个按钮

        json_label = CustomLabel("JSON 文件:")
        json_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        json_input_line_layout.addWidget(json_label,1) # Label 占1份

        self.json_path_entry = QLineEdit()
        self.json_path_entry.setPlaceholderText("选择包含ASR结果的 JSON 文件")
        self.json_path_entry.setObjectName("pathEdit")
        json_input_line_layout.addWidget(self.json_path_entry,3) # 输入框占3份

        self.json_browse_button = QPushButton("浏览...")
        self.json_browse_button.setObjectName("browseButton")
        self.json_browse_button.clicked.connect(self.browse_json_file)
        json_input_line_layout.addWidget(self.json_browse_button,1) # 浏览按钮占1份

        self.free_transcription_button = QPushButton("免费获取JSON") # 新增按钮
        self.free_transcription_button.setObjectName("freeButton") # 给新按钮一个对象名以便应用样式
        self.free_transcription_button.clicked.connect(self.open_free_transcription_dialog)
        json_input_line_layout.addWidget(self.free_transcription_button,1) # 免费获取按钮占1份

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
        self.output_path_entry.setObjectName("pathEdit") # 与JSON路径使用相同对象名以共享样式
        self.output_browse_button = QPushButton("浏览...")
        self.output_browse_button.setObjectName("browseButton") # 与JSON浏览按钮共享样式
        self.output_browse_button.clicked.connect(self.select_output_dir)
        output_layout.addWidget(output_label,1)
        output_layout.addWidget(self.output_path_entry,4)
        output_layout.addWidget(self.output_browse_button,1)
        export_layout.addLayout(output_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%") # 显示百分比
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

        content_layout.addWidget(api_group,22) # 调整权重以适应界面
        content_layout.addWidget(file_group,23)
        content_layout.addWidget(export_group,20)
        content_layout.addWidget(log_group,35)
        main_layout.addWidget(content_widget,1)
        
        self._update_input_mode_ui() # 初始化UI状态
        self.apply_styles()

    def apply_styles(self):
        # ... (之前的样式代码保持不变) ...
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

        qss_image_url = ""
        raw_arrow_path = resource_path('dropdown_arrow.png')
        if raw_arrow_path and os.path.exists(raw_arrow_path):
            abs_arrow_path = os.path.abspath(raw_arrow_path)
            formatted_path = abs_arrow_path.replace(os.sep, '/')
            qss_image_url = f"url('{formatted_path}')"
        else:
            self._early_log(f"警告: 下拉箭头图标 'dropdown_arrow.png' 未找到。")

        # 为 "免费获取" 按钮添加样式 (可以与 "browseButton" 类似或单独设计)
        free_button_bg = "rgba(100, 180, 120, 190)"; free_button_hover = "rgba(80, 160, 100, 220)"


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
            QPushButton#freeButton {{ /* “免费获取”按钮样式 */
                background-color:{free_button_bg}; color:white; border:none; border-radius:5px;
                font-family:'Microsoft YaHei'; font-weight:bold; font-size:10pt; padding:6px 15px;
            }}
            QPushButton#freeButton:hover {{ background-color:{free_button_hover}; }}
            QPushButton#startButton {{ padding:8px 25px; font:bold 14pt '楷体'; }}
            QPushButton#browseButton:hover, QPushButton#startButton:hover {{ background-color:{button_blue_hover}; }}
            QPushButton#startButton:disabled {{ background-color:rgba(100,100,100,150); color:#bbbbbb; }}
            QPushButton#minButton {{ background-color:{control_min_blue}; color:white; border:none; border-radius:15px; font-weight:bold; font-size:14pt; }}
            QPushButton#minButton:hover {{ background-color:{control_min_hover}; }}
            QPushButton#closeButton {{ background-color:{control_close_red}; color:white; border:none; border-radius:15px; font-weight:bold; font-size:14pt; }}
            QPushButton#closeButton:hover {{ background-color:{control_close_hover}; }}
            QPushButton#settingsButton {{
                background-color:{settings_btn_bg}; color:white;
                border:none; border-radius:19px; 
                font-weight:bold; font-size:11pt; padding: 0px;
            }}
            QPushButton#settingsButton:hover {{ background-color:{settings_btn_hover}; }}
            QProgressBar#progressBar {{ border:1px solid rgba(135,206,235,80); border-radius:5px; text-align:center; background:rgba(0,0,0,40); height:22px; color:#f0f0f0; font-weight:bold; }}
            QProgressBar#progressBar::chunk {{ background-color:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5C8A6F,stop:1 #69CFF7); border-radius:5px; }}
            QTextEdit#logArea {{ background-color:{log_bg}; border:1px solid rgba(135,206,235,80); border-radius:5px; color:{log_text_custom_color}; font-family:'SimSun'; font-size:10pt; font-weight:bold;}}
            QComboBox#formatCombo {{
                background-color:{input_bg}; color:{input_text_red};
                border:1px solid {input_border_color}; border-radius:5px;
                padding: 2.5px 8px 2.5px 8px; /* 调整内边距以适应字体和高度 */
                font:bold 11pt 'Microsoft YaHei'; min-height:1.8em; /* 与QLineEdit一致 */
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
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                self.config = {}

            api_key = self.config.get('deepseek_api_key', '')
            remember = self.config.get('remember_api_key', True)
            last_json_path = self.config.get('last_json_path', '')
            last_output_path = self.config.get('last_output_path', '')
            last_source_format = self.config.get('last_source_format', 'ElevenLabs(推荐)') # 默认 ElevenLabs
            
            # 加载高级SRT设置
            self.advanced_srt_settings = {
                'min_duration_target': self.config.get(USER_MIN_DURATION_TARGET_KEY, DEFAULT_MIN_DURATION_TARGET),
                'max_duration': self.config.get(USER_MAX_DURATION_KEY, DEFAULT_MAX_DURATION),
                'max_chars_per_line': self.config.get(USER_MAX_CHARS_PER_LINE_KEY, DEFAULT_MAX_CHARS_PER_LINE),
                'default_gap_ms': self.config.get(USER_DEFAULT_GAP_MS_KEY, DEFAULT_DEFAULT_GAP_MS),
            }

            # 加载免费转录设置
            self.free_transcription_settings = {
                'language': self.config.get(USER_FREE_TRANSCRIPTION_LANGUAGE_KEY, DEFAULT_FREE_TRANSCRIPTION_LANGUAGE),
                'num_speakers': self.config.get(USER_FREE_TRANSCRIPTION_NUM_SPEAKERS_KEY, DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS),
                'tag_audio_events': self.config.get(USER_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS_KEY, DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS),
                # audio_file_path 是临时的，不从配置加载
            }
            # 从配置加载上次的输入模式，默认为 "local_json"
            self._current_input_mode = self.config.get('last_input_mode', 'local_json')
            self._temp_audio_file_for_free_transcription = self.config.get('last_free_transcription_audio_path', None)
            if self._current_input_mode == "free_transcription" and self._temp_audio_file_for_free_transcription:
                if self.json_path_entry: # 确保UI已初始化
                    self.json_path_entry.setText(f"音频: {os.path.basename(self._temp_audio_file_for_free_transcription)}")
            elif self.json_path_entry and os.path.isfile(last_json_path): # 仅当不是免费模式时才加载上次的JSON路径
                 self.json_path_entry.setText(last_json_path)


            if self.json_format_combo:
                format_index = self.json_format_combo.findText(last_source_format)
                if format_index != -1:
                    self.json_format_combo.setCurrentIndex(format_index)
                else: # 如果找不到上次的格式，默认第一个
                    self.json_format_combo.setCurrentIndex(0) 
            
            self._update_input_mode_ui() # 根据加载的模式更新UI

            if self.api_key_entry and self.remember_api_key_checkbox:
                if api_key and remember:
                    self.api_key_entry.setText(api_key)
                self.remember_api_key_checkbox.setChecked(remember)


            if self.output_path_entry:
                if os.path.isdir(last_output_path):
                    self.output_path_entry.setText(last_output_path)
                elif os.path.isdir(os.path.join(os.path.expanduser("~"),"Documents")): # 默认到用户文档目录
                    self.output_path_entry.setText(os.path.join(os.path.expanduser("~"),"Documents"))
                else:
                    self.output_path_entry.setText(os.path.expanduser("~")) # 最后回退到用户主目录

        except (json.JSONDecodeError, Exception) as e:
             self.log_message(f"加载配置出错或配置格式错误: {e}")
             self.config = {} # 重置配置
             self.advanced_srt_settings = { # 重置为默认
                'min_duration_target': DEFAULT_MIN_DURATION_TARGET,
                'max_duration': DEFAULT_MAX_DURATION,
                'max_chars_per_line': DEFAULT_MAX_CHARS_PER_LINE,
                'default_gap_ms': DEFAULT_DEFAULT_GAP_MS,
            }
             self.free_transcription_settings = {
                'language': DEFAULT_FREE_TRANSCRIPTION_LANGUAGE,
                'num_speakers': DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS,
                'tag_audio_events': DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS,
            }
             self._current_input_mode = 'local_json'
             self._temp_audio_file_for_free_transcription = None
             self._update_input_mode_ui()


    def save_config(self):
        if not (self.api_key_entry and self.remember_api_key_checkbox and \
                self.json_path_entry and self.output_path_entry and self.json_format_combo):
            self.log_message("警告: UI组件未完全初始化，无法保存配置。")
            return

        if not os.path.exists(CONFIG_DIR):
            try:
                os.makedirs(CONFIG_DIR)
            except OSError as e:
                self.log_message(f"创建配置目录失败: {e}"); return

        api_key = self.api_key_entry.text().strip()
        remember = self.remember_api_key_checkbox.isChecked()
        self.config['remember_api_key'] = remember
        if remember and api_key:
            self.config['deepseek_api_key'] = api_key
        elif 'deepseek_api_key' in self.config and not api_key : # 如果不记住且为空，则删除
            del self.config['deepseek_api_key']
        elif not remember and 'deepseek_api_key' in self.config: # 如果不记住，也删除
            del self.config['deepseek_api_key']


        if self._current_input_mode == 'local_json':
            self.config['last_json_path'] = self.json_path_entry.text()
        else: # free_transcription mode
            # 保存当前选择的音频文件路径，以便下次启动时能提示用户
            if self._temp_audio_file_for_free_transcription:
                 self.config['last_free_transcription_audio_path'] = self._temp_audio_file_for_free_transcription
            elif 'last_free_transcription_audio_path' in self.config: # 如果当前没有选择，但之前有，则清除
                 del self.config['last_free_transcription_audio_path']


        self.config['last_output_path'] = self.output_path_entry.text()
        self.config['last_source_format'] = self.json_format_combo.currentText()
        self.config['last_input_mode'] = self._current_input_mode


        # 保存高级SRT设置
        if self.advanced_srt_settings: 
            self.config[USER_MIN_DURATION_TARGET_KEY] = self.advanced_srt_settings.get('min_duration_target', DEFAULT_MIN_DURATION_TARGET)
            self.config[USER_MAX_DURATION_KEY] = self.advanced_srt_settings.get('max_duration', DEFAULT_MAX_DURATION)
            self.config[USER_MAX_CHARS_PER_LINE_KEY] = self.advanced_srt_settings.get('max_chars_per_line', DEFAULT_MAX_CHARS_PER_LINE)
            self.config[USER_DEFAULT_GAP_MS_KEY] = self.advanced_srt_settings.get('default_gap_ms', DEFAULT_DEFAULT_GAP_MS)

        # 保存免费转录设置 (不保存audio_file_path)
        if self.free_transcription_settings:
            self.config[USER_FREE_TRANSCRIPTION_LANGUAGE_KEY] = self.free_transcription_settings.get('language', DEFAULT_FREE_TRANSCRIPTION_LANGUAGE)
            self.config[USER_FREE_TRANSCRIPTION_NUM_SPEAKERS_KEY] = self.free_transcription_settings.get('num_speakers', DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS)
            self.config[USER_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS_KEY] = self.free_transcription_settings.get('tag_audio_events', DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS)

        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log_message(f"保存配置失败: {e}")

    def browse_json_file(self):
        if not self.json_path_entry: return
        # 确保在 local_json 模式下才执行
        if self._current_input_mode != "local_json":
            self.log_message("提示：当前为“免费获取”模式，请通过对应对话框选择音频文件。")
            return

        start_dir = os.path.dirname(self.json_path_entry.text()) \
            if self.json_path_entry.text() and os.path.exists(os.path.dirname(self.json_path_entry.text())) \
            else os.path.expanduser("~")
        filepath, _ = QFileDialog.getOpenFileName(self, "选择 JSON 文件", start_dir, "JSON 文件 (*.json);;所有文件 (*.*)")
        if filepath:
            self.json_path_entry.setText(filepath)
            self._current_input_mode = "local_json" # 切换回本地模式
            self._temp_audio_file_for_free_transcription = None # 清除免费模式的音频文件
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
        # 确保 advanced_srt_settings 已从配置加载或使用默认值
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
        self.save_config() # 保存到配置文件

    def open_free_transcription_dialog(self):
        # 使用 self.free_transcription_settings 和 self._temp_audio_file_for_free_transcription 来初始化对话框
        current_dialog_settings = self.free_transcription_settings.copy()
        current_dialog_settings['audio_file_path'] = self._temp_audio_file_for_free_transcription or ""
        
        dialog = FreeTranscriptionDialog(current_dialog_settings, self)
        dialog.settings_confirmed.connect(self.apply_free_transcription_settings)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 用户点击了“确定”，apply_free_transcription_settings 已经被调用
            pass
        else: # 用户点击了“取消”或关闭了对话框
            # 如果之前是 free_transcription 模式，但用户取消了，是否恢复到 local_json？
            # 根据之前的讨论，是的，取消则放弃免费模式
            self._current_input_mode = "local_json"
            # self._temp_audio_file_for_free_transcription = None # 不清除，以便下次打开对话框时能恢复
            self.json_path_entry.setText(self.config.get('last_json_path','')) # 尝试恢复上次的本地JSON路径
            self._update_input_mode_ui()
            self.log_message("已取消免费转录模式，请选择本地JSON文件。")


    def apply_free_transcription_settings(self, new_settings: dict):
        self._current_input_mode = "free_transcription"
        self._temp_audio_file_for_free_transcription = new_settings.get('audio_file_path')
        
        # 更新持久化设置 (除了 audio_file_path)
        self.free_transcription_settings['language'] = new_settings.get('language')
        self.free_transcription_settings['num_speakers'] = new_settings.get('num_speakers')
        self.free_transcription_settings['tag_audio_events'] = new_settings.get('tag_audio_events')
        
        if self.json_path_entry and self._temp_audio_file_for_free_transcription:
            self.json_path_entry.setText(f"音频: {os.path.basename(self._temp_audio_file_for_free_transcription)}")
        
        self._update_input_mode_ui()
        self.log_message(f"免费转录参数已更新: { {k:v for k,v in new_settings.items() if k != 'audio_file_path'} }")
        self.log_message(f"  将使用音频文件: {self._temp_audio_file_for_free_transcription}")
        self.save_config() # 保存到配置文件

    def start_conversion(self):
        if not (self.api_key_entry and self.output_path_entry and \
                self.start_button and self.progress_bar and self.log_area and \
                self.json_format_combo and self.json_path_entry): # 确保所有需要的UI元素都存在
            QMessageBox.critical(self, "错误", "UI组件未完全初始化，无法开始转换。")
            return

        api_key = self.api_key_entry.text().strip()
        output_dir = self.output_path_entry.text().strip()

        if not api_key:
            QMessageBox.warning(self, "缺少信息", "请输入 DeepSeek API Key。"); return
        if not output_dir:
            QMessageBox.warning(self, "缺少信息", "请选择导出目录。"); return
        if not os.path.isdir(output_dir):
            QMessageBox.critical(self, "错误", f"导出目录无效: {output_dir}"); return

        json_path_for_worker = ""
        source_format_key = "elevenlabs" # 默认，对于免费转录也是这个格式

        if self._current_input_mode == "free_transcription":
            if not self._temp_audio_file_for_free_transcription or \
               not os.path.isfile(self._temp_audio_file_for_free_transcription):
                QMessageBox.critical(self, "错误", "请在“免费获取”中选择一个有效的音频文件。")
                return
            self.log_message("准备通过免费ElevenLabs API获取JSON...")
            # json_path_for_worker 在此模式下初始为空，将在转录后由worker内部生成和使用

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


        self.save_config() # 保存当前所有配置
        self.start_button.setEnabled(False)
        self.start_button.setText("转换中...")
        self.progress_bar.setValue(0) # 重置进度条
        # self.log_area.clear() # 不再清除日志，以便用户看到之前的参数更新信息
        self.log_message("--------------------") # 添加分割线
        self.log_message("开始新的转换任务...")


        # 检查当前是否有正在运行的线程
        if self.conversion_thread and self.conversion_thread.isRunning():
             self.log_message("警告：上一个转换任务仍在进行中。请等待其完成后再开始新的任务。")
             self.start_button.setEnabled(True) # 允许用户可能想取消（如果实现了取消逻辑）或重试
             self.start_button.setText("开始转换")
             return
        
        self.log_message("创建新的转换线程和工作对象...")

        current_srt_params = self.advanced_srt_settings 
        free_transcription_params_for_worker = None
        if self._current_input_mode == "free_transcription":
            free_transcription_params_for_worker = {
                "audio_file_path": self._temp_audio_file_for_free_transcription,
                **self.free_transcription_settings # language, num_speakers, tag_audio_events
            }

        self.conversion_thread = QThread(parent=self) 
        self.worker = ConversionWorker(
            api_key=api_key,
            input_json_path=json_path_for_worker, 
            output_dir=output_dir,
            srt_processor=self.srt_processor,
            source_format=source_format_key, 
            srt_params=current_srt_params,
            input_mode=self._current_input_mode, 
            free_transcription_params=free_transcription_params_for_worker, 
            elevenlabs_stt_client=self.elevenlabs_stt_client 
        )
        self.worker.moveToThread(self.conversion_thread)
        
        self.worker.signals.finished.connect(self.on_conversion_finished)
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.log_message.connect(self.log_message)
        
        self.conversion_thread.started.connect(self.worker.run)
        
        self.worker.signals.finished.connect(self.conversion_thread.quit)
        self.worker.signals.finished.connect(self.worker.deleteLater) 
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater) 
        self.conversion_thread.finished.connect(self._clear_worker_references) 
        
        self.conversion_thread.start()
    
    def _clear_worker_references(self):
        self.log_message("清理旧的worker和线程引用...") # 添加日志
        self.worker = None
        self.conversion_thread = None 
        if hasattr(self, 'start_button') and self.start_button: 
            self.start_button.setEnabled(True)
            self.start_button.setText("开始转换")
        # 转换结束后，如果之前是免费转录模式，可以考虑是否要清除json_path_entry的"音频: xxx"文本
        # 或者保留，让用户知道上次用的是哪个音频

    def update_progress(self, value: int):
        if self.progress_bar:
            self.progress_bar.setValue(value)

    @staticmethod
    def show_message_box(parent_widget: Optional[QWidget], title: str, message: str, success: bool):
        # 使用 QTimer.singleShot 确保在主线程中执行 QMessageBox
        if parent_widget and parent_widget.isVisible():
            QTimer.singleShot(0, lambda: (
                QMessageBox.information(parent_widget, title, message) if success
                else QMessageBox.critical(parent_widget, title, message)
            ))
        else: # 如果父控件不可用（例如程序正在关闭），则打印到控制台
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

        # 无论成功与否，转换结束后都重置为本地JSON模式 ---
        self.log_message("任务结束，输入模式已重置为本地JSON文件模式。")
        self._current_input_mode = "local_json"
        
        # 清空或恢复JSON路径输入框
        last_local_json_path = self.config.get('last_json_path', '')
        if self.json_path_entry:
            self.json_path_entry.setText(last_local_json_path) 
            if not last_local_json_path: # 如果没有上次的本地路径，则显示占位符
                 self.json_path_entry.setPlaceholderText("选择包含ASR结果的 JSON 文件")


        self._temp_audio_file_for_free_transcription = None # 清除临时音频文件路径
        self._update_input_mode_ui() # 更新UI状态，重新启用JSON相关控件
        self.save_config() # 保存一下当前的输入模式状态

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            title_bar_height = 80 
            is_on_title_bar_area = event.position().y() < title_bar_height
            widget_at_pos = self.childAt(event.position().toPoint())

            # 确保不拦截设置按钮和免费获取按钮的点击
            if widget_at_pos == self.settings_button or widget_at_pos == self.free_transcription_button:
                event.ignore() 
                return

            is_interactive_control = False
            current_widget = widget_at_pos
            interactive_widgets_tuple = (QPushButton, QLineEdit, QCheckBox, QTextEdit, QProgressBar, QComboBox, QAbstractItemView)
            while current_widget is not None:
                if isinstance(current_widget, interactive_widgets_tuple) or \
                   (hasattr(current_widget, 'objectName') and current_widget.objectName().startswith('qt_scrollarea')) or \
                   (QApplication.activePopupWidget() and isinstance(current_widget, QApplication.activePopupWidget().__class__)):
                    is_interactive_control = True
                    break
                current_widget = current_widget.parentWidget()

            if is_on_title_bar_area and not is_interactive_control:
                self.drag_pos = event.globalPosition().toPoint()
                self.is_dragging = True
                event.accept()
            else:
                # 对于非标题栏区域或交互控件，让事件继续传递
                super().mousePressEvent(event) # 修改：确保其他事件能被处理


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
        self.save_config() # 确保在关闭前保存配置
        self.close()

    def closeEvent(self, event):
        self.log_message("正在关闭应用程序...")
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.log_message("尝试停止正在进行的转换任务...")
            if self.worker:
                self.worker.stop() # 请求worker停止
            # self.conversion_thread.quit() # 请求线程退出
            # self.conversion_thread.wait(3000) # 等待最多3秒
            # if self.conversion_thread.isRunning(): # 如果仍在运行，则强制终止
            #     self.log_message("警告：转换线程未能正常停止，将尝试强制终止。")
            #     self.conversion_thread.terminate() # 不推荐，但作为最后手段
            #     self.conversion_thread.wait()

        self.save_config() # 再次保存，以防有状态更新
        super().closeEvent(event)