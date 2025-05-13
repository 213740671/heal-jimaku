import os
import json
from typing import Optional, Any, Dict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QTextEdit, QCheckBox, QComboBox,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QThread
from PyQt6.QtGui import QIcon, QFont, QColor, QTextCursor, QPixmap, QPainter, QBrush, QLinearGradient

# Corrected imports: removed 'src.' prefix
from config import CONFIG_DIR, CONFIG_FILE # 项目配置常量
from utils.file_utils import resource_path # 资源路径工具
from ui.custom_widgets import TransparentWidget, CustomLabel, CustomLabel_title # 自定义UI控件 (or from .custom_widgets)
from ui.conversion_worker import ConversionWorker # 后台工作线程 (or from .conversion_worker)
from core.srt_processor import SrtProcessor # SRT处理逻辑核心


class HealJimakuApp(QMainWindow):
    """应用程序的主窗口和UI逻辑。"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heal-Jimaku (治幕)")
        self.resize(1024, 864)

        self.srt_processor = SrtProcessor() # 初始化SRT处理器
        self.config: Dict[str, Any] = {} # 应用配置字典
        self.conversion_thread: Optional[QThread] = None # 后台转换线程
        self.worker: Optional[ConversionWorker] = None # 后台工作者对象
        self.app_icon: Optional[QIcon] = None # 应用图标
        self.background: Optional[QPixmap] = None # 背景图片

        self.is_dragging = False # 用于窗口拖动
        self.drag_pos = QPoint() # 记录拖动起始位置

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint) # 无边框窗口
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True) # 允许透明背景

        self.log_area_early_messages: list[str] = [] # 存储早期日志消息 (在log_area初始化前)

        # 加载应用图标
        icon_path = resource_path("icon.ico")
        if icon_path and os.path.exists(icon_path):
            self.app_icon = QIcon(icon_path)
        else:
            self._early_log("警告: 应用图标 icon.ico 未找到。")
            self.app_icon = QIcon() # 使用默认空图标
        self.setWindowIcon(self.app_icon)

        # 加载背景图片
        bg_path = resource_path("background.png")
        if bg_path and os.path.exists(bg_path):
            self.background = QPixmap(bg_path)
        else:
            self._early_log("警告: 背景图片 background.png 未找到。")

        if self.background is None or self.background.isNull():
            self._create_fallback_background() # 如果背景加载失败，创建回退背景
        else:
            # 初始缩放背景以适应窗口大小
            self.background = self.background.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)


        self.main_widget = QWidget(self) # 主控件
        self.setCentralWidget(self.main_widget)
        self.main_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) # 主控件也设为透明

        # UI 初始化相关变量声明 (避免 linter 警告)
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

        self.init_ui() # 初始化UI元素
        self._process_early_logs() # 处理早期日志
        self.load_config() # 加载配置
        self.center_window() # 居中窗口
        QTimer.singleShot(100, self.apply_taskbar_icon) # 稍后应用任务栏图标

    def _early_log(self, message: str):
        """早期日志记录，在UI完全初始化之前使用。"""
        if hasattr(self, 'log_area') and self.log_area: # 如果日志区域已存在
            self.log_message(message)
        else: # 否则暂存
            self.log_area_early_messages.append(message)
            print(f"[Log Early]: {message}") # 同时打印到控制台

    def _process_early_logs(self):
        """处理在log_area初始化前积累的早期日志消息。"""
        if hasattr(self, 'log_area') and self.log_area:
            for msg in self.log_area_early_messages:
                self.log_area.append(msg)
            self.log_area_early_messages = [] # 清空暂存

    def _create_fallback_background(self):
        """创建一个渐变色回退背景。"""
        self.background = QPixmap(self.size())
        if self.background.isNull(): # 确保 QPixmap 创建成功
             self.background = QPixmap(1024, 864) # 默认大小，如果 self.size() 有问题

        self.background.fill(Qt.GlobalColor.transparent) # 透明填充
        painter = QPainter(self.background)
        gradient = QLinearGradient(0, 0, 0, self.height()) # 线性渐变
        gradient.setColorAt(0, QColor(40, 40, 80, 200))
        gradient.setColorAt(1, QColor(20, 20, 40, 220)) # 设置渐变色
        painter.fillRect(self.rect(), gradient)
        painter.end()

    def apply_taskbar_icon(self):
        """尝试再次设置任务栏图标。"""
        if hasattr(self, 'windowHandle') and self.windowHandle() is not None: # 检查窗口句柄
            if self.app_icon and not self.app_icon.isNull():
                self.windowHandle().setIcon(self.app_icon)
        elif self.app_icon and not self.app_icon.isNull():
            self.setWindowIcon(self.app_icon) # 回退方法

    def center_window(self):
        """将窗口居中显示在屏幕上。"""
        try:
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.geometry() # 获取屏幕几何信息
                self.move((screen_geometry.width() - self.width()) // 2, (screen_geometry.height() - self.height()) // 2) # 移动窗口
        except Exception as e: # 异常处理
            self._early_log(f"居中窗口时出错: {e}")
            # 提供一个非常基础的回退（可能不完美）
            self.move(100,100)


    def paintEvent(self, event): # event: QPaintEvent
        """绘制事件，用于绘制背景。"""
        painter = QPainter(self)
        if self.background and not self.background.isNull():
            painter.drawPixmap(self.rect(), self.background) # 绘制背景图片
        else:
            painter.fillRect(self.rect(), QColor(30, 30, 50, 230)) # 如果没有背景图，则填充纯色
        super().paintEvent(event)

    def resizeEvent(self, event): # event: QResizeEvent
        """窗口大小调整事件，用于重新缩放背景。"""
        bg_path = resource_path("background.png")
        if bg_path and os.path.exists(bg_path):
            new_pixmap = QPixmap(bg_path)
            if not new_pixmap.isNull():
                self.background = new_pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            else:
                self._create_fallback_background() # 如果加载新图片失败，则使用回退
        else:
            self._create_fallback_background() # 如果路径不存在，也使用回退
        super().resizeEvent(event)
        self.update() # 更新界面

    def init_ui(self):
        """初始化用户界面元素。"""
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(30,30,30,30)
        main_layout.setSpacing(20) # 主布局
        QApplication.setFont(QFont('楷体', 12)) # 设置全局默认字体

        # 标题栏布局
        title_bar_layout = QHBoxLayout()
        title = CustomLabel_title("Heal-Jimaku (治幕)")
        title_font = QFont('楷体', 24)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        control_btn_layout = QHBoxLayout()
        control_btn_layout.setSpacing(10) # 控制按钮 (最小化，关闭)
        min_btn = QPushButton("─")
        min_btn.setFixedSize(30,30)
        min_btn.setObjectName("minButton")
        min_btn.clicked.connect(self.showMinimized)
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30,30)
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.close_application)
        control_btn_layout.addWidget(min_btn)
        control_btn_layout.addWidget(close_btn)

        title_bar_layout.addStretch(1)
        title_bar_layout.addWidget(title,2,Qt.AlignmentFlag.AlignCenter)
        title_bar_layout.addStretch(1)
        title_bar_layout.addLayout(control_btn_layout)
        main_layout.addLayout(title_bar_layout)
        main_layout.addSpacing(20) # 添加标题栏到主布局

        # 内容区域 (使用透明控件)
        content_widget = TransparentWidget(bg_color=QColor(191,191,191,50)) # 半透明背景
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(25,25,25,25)
        content_layout.setSpacing(15)

        # API 设置组
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

        # 文件选择组
        file_group = QGroupBox("文件选择")
        file_group.setObjectName("fileGroup")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(12)
        json_layout = QHBoxLayout()
        json_label = CustomLabel("JSON 文件:")
        json_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.json_path_entry = QLineEdit()
        self.json_path_entry.setPlaceholderText("选择包含ASR结果的 JSON 文件")
        self.json_path_entry.setObjectName("pathEdit")
        self.json_browse_button = QPushButton("浏览...")
        self.json_browse_button.setObjectName("browseButton")
        self.json_browse_button.clicked.connect(self.browse_json_file)
        json_layout.addWidget(json_label,1)
        json_layout.addWidget(self.json_path_entry,4)
        json_layout.addWidget(self.json_browse_button,1)
        file_layout.addLayout(json_layout)

        format_layout = QHBoxLayout()
        format_label = CustomLabel("JSON 格式:")
        format_label.setFont(QFont('楷体', 13, QFont.Weight.Bold))
        self.json_format_combo = QComboBox()
        self.json_format_combo.addItems(["ElevenLabs(推荐)", "Whisper(推荐)", "Deepgram", "AssemblyAI"])
        self.json_format_combo.setObjectName("formatCombo")
        format_layout.addWidget(format_label,1)
        format_layout.addWidget(self.json_format_combo,5)
        file_layout.addLayout(format_layout)

        # 导出与控制组
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
        self.progress_bar.setFormat("%p%") # 显示百分比
        self.progress_bar.setObjectName("progressBar") # 进度条
        export_layout.addWidget(self.progress_bar)
        self.start_button = QPushButton("开始转换")
        self.start_button.setFixedHeight(45)
        self.start_button.setFont(QFont('楷体', 14, QFont.Weight.Bold))
        self.start_button.setObjectName("startButton") # 开始按钮
        self.start_button.clicked.connect(self.start_conversion)
        export_layout.addWidget(self.start_button)

        # 日志区域组
        log_group = QGroupBox("日志")
        log_group.setObjectName("logGroup")
        log_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setObjectName("logArea") # 日志文本框
        log_layout.addWidget(self.log_area)

        content_layout.addWidget(api_group,22)
        content_layout.addWidget(file_group,23) # 添加组到内容布局 (权重用于调整比例)
        content_layout.addWidget(export_group,20)
        content_layout.addWidget(log_group,35)
        main_layout.addWidget(content_widget,1) # 添加内容控件到主布局
        self.apply_styles() # 应用QSS样式

    def apply_styles(self):
        """应用QSS样式表来美化界面。"""
        group_title_red = "#B34A4A"; input_text_red = "#7a1723"; soft_orangebrown_text = "#CB7E47" # 颜色定义
        button_blue_bg = "rgba(100, 149, 237, 190)"; button_blue_hover = "rgba(120, 169, 247, 210)"
        control_min_blue = "rgba(135, 206, 235, 180)"; control_min_hover = "rgba(135, 206, 235, 220)"
        control_close_red = "rgba(255, 99, 71, 180)"; control_close_hover = "rgba(255, 99, 71, 220)"
        group_bg = "rgba(52, 129, 184, 30)" # 组背景色 (带透明度)
        input_bg = "rgba(255, 255, 255, 30)"; input_hover_bg = "rgba(255, 255, 255, 40)" # 输入框背景
        input_focus_bg = "rgba(255, 255, 255, 50)"; input_border_color = "rgba(135, 206, 235, 90)" # 输入框边框
        input_focus_border_color = "#87CEEB" # 输入框聚焦时边框颜色
        log_bg = "rgba(0, 0, 0, 55)"; log_text_custom_color = "#F0783C" # 日志区域颜色
        combo_dropdown_bg = "rgba(250, 250, 250, 235)"; combo_dropdown_text_color = "#2c3e50" # 下拉列表颜色
        combo_dropdown_border_color = "rgba(135, 206, 235, 150)"
        combo_dropdown_selection_bg = button_blue_hover; combo_dropdown_selection_text_color = "#FFFFFF"
        combo_dropdown_hover_bg = "rgba(173, 216, 230, 150)"

        qss_image_url = "" # QSS中的图片URL
        raw_arrow_path = resource_path('dropdown_arrow.png') # 获取下拉箭头图片路径

        if raw_arrow_path and os.path.exists(raw_arrow_path): # 如果图片存在
            abs_arrow_path = os.path.abspath(raw_arrow_path) # 获取绝对路径
            formatted_path = abs_arrow_path.replace(os.sep, '/') # 格式化为QSS兼容的路径
            qss_image_url = f"url('{formatted_path}')"
        else:
            self.log_message(f"警告: 下拉箭头图标 'dropdown_arrow.png' 未找到。将使用默认或无图标。") # 日志记录图标缺失
            pass # 如果找不到，则不设置图片

        style = f"""
            QGroupBox {{ font: bold 17pt '楷体'; border: 1px solid rgba(135,206,235,80); border-radius:8px; margin-top:12px; background-color:{group_bg}; }}
            QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top left; left:15px; padding:2px 5px; color:{group_title_red}; font:bold 15pt '楷体'; }}
            QLineEdit#apiKeyEdit, QLineEdit#pathEdit {{ background-color:{input_bg}; color:{input_text_red}; border:1px solid {input_border_color}; border-radius:5px; padding:6px; font:bold 11pt 'Microsoft YaHei'; min-height:1.8em; }}
            QLineEdit#apiKeyEdit:hover, QLineEdit#pathEdit:hover {{ background-color:{input_hover_bg}; border:1px solid {input_focus_border_color}; }}
            QLineEdit#apiKeyEdit:focus, QLineEdit#pathEdit:focus {{ background-color:{input_focus_bg}; border:1px solid {input_focus_border_color}; }}
            QLineEdit#apiKeyEdit {{ font-family:'Consolas','Courier New',monospace; font-size:12pt; font-weight:bold; }} /* API Key 特殊字体 */
            QCheckBox#rememberCheckbox {{ color:{soft_orangebrown_text}; font:bold 10pt 'Microsoft YaHei'; spacing:5px; background-color:transparent; }}
            QCheckBox#rememberCheckbox::indicator {{ width:18px; height:18px; border:1px solid {input_focus_border_color}; border-radius:3px; background-color:rgba(255,255,255,30); }}
            QCheckBox#rememberCheckbox::indicator:checked {{ background-color:rgba(105,207,247,150); image:none; }} /* 选中时无图片，仅背景色 */
            QPushButton#browseButton, QPushButton#startButton {{ background-color:{button_blue_bg}; color:white; border:none; border-radius:5px; font-family:'Microsoft YaHei'; font-weight:bold; }}
            QPushButton#browseButton {{ padding:6px 15px; font-size:10pt; }}
            QPushButton#startButton {{ padding:8px 25px; font:bold 14pt '楷体'; }}
            QPushButton#browseButton:hover, QPushButton#startButton:hover {{ background-color:{button_blue_hover}; }}
            QPushButton#startButton:disabled {{ background-color:rgba(100,100,100,150); color:#bbbbbb; }} /* 禁用状态 */
            #minButton {{ background-color:{control_min_blue}; color:white; border:none; border-radius:15px; font-weight:bold; font-size:14pt; }}
            #minButton:hover {{ background-color:{control_min_hover}; }}
            #closeButton {{ background-color:{control_close_red}; color:white; border:none; border-radius:15px; font-weight:bold; font-size:14pt; }}
            #closeButton:hover {{ background-color:{control_close_hover}; }}
            QProgressBar#progressBar {{ border:1px solid rgba(135,206,235,80); border-radius:5px; text-align:center; background:rgba(0,0,0,40); height:22px; color:#f0f0f0; font-weight:bold; }}
            QProgressBar#progressBar::chunk {{ background-color:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5C8A6F,stop:1 #69CFF7); border-radius:5px; }} /* 进度条块样式 */
            QTextEdit#logArea {{ background-color:{log_bg}; border:1px solid rgba(135,206,235,80); border-radius:5px; color:{log_text_custom_color}; font-family:'SimSun'; font-size:10pt; font-weight:bold;}}

            /* QComboBox 样式 */
            QComboBox#formatCombo {{
                background-color:{input_bg}; color:{input_text_red};
                border:1px solid {input_border_color}; border-radius:5px;
                padding: 2.5px 8px 2.5px 8px; /* 上 右 下 左 内边距 */
                font:bold 11pt 'Microsoft YaHei'; min-height:0.8em; /* 调整最小高度 */
            }}
            QComboBox#formatCombo:hover {{ background-color:{input_hover_bg}; border-color:{input_focus_border_color}; }}
            QComboBox#formatCombo:focus {{ background-color:{input_focus_bg}; border-color:{input_focus_border_color}; }}
            QComboBox#formatCombo:on {{ background-color:{input_focus_bg}; border-color:{input_focus_border_color}; padding-right: 8px; }} /* 下拉时样式 */

            QComboBox#formatCombo::drop-down {{ /* 下拉按钮区域 */
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px; /* 按钮宽度 */
                border: none; /* 无边框 */
            }}
            QComboBox#formatCombo::down-arrow {{ /* 下拉箭头图标 */
                image: {qss_image_url if qss_image_url else "none"}; /* 使用资源图片或无图标 */
                width: 8px; /* 图标大小 */
                height: 8px;
            }}
            QComboBox#formatCombo::down-arrow:on {{ /* 下拉时箭头的状态 (可以用于旋转等，这里未使用) */
                /* top: 1px; */
            }}

            /* QComboBox 下拉列表视图样式 */
            QComboBox QAbstractItemView {{ background-color:{combo_dropdown_bg}; color:{combo_dropdown_text_color}; border:1px solid {combo_dropdown_border_color}; border-radius:5px; padding:4px; outline:0px; /* 去除焦点轮廓 */ }}
            QComboBox QAbstractItemView::item {{ padding:6px 10px; min-height:1.7em; border-radius:3px; background-color:transparent; }} /* 列表项 */
            QComboBox QAbstractItemView::item:selected {{ background-color:{combo_dropdown_selection_bg}; color:{combo_dropdown_selection_text_color}; }} /* 选中项 */
            QComboBox QAbstractItemView::item:hover {{ background-color:{combo_dropdown_hover_bg}; color:{combo_dropdown_text_color}; }} /* 悬浮项 */

            /* 确保自定义标签背景透明 */
            CustomLabel, CustomLabel_title {{ background-color:transparent; }}
            QLabel {{ background-color:transparent; }} /* 普通QLabel也设为透明以防万一 */
        """
        self.setStyleSheet(style) # 应用样式

    def log_message(self, message: str):
        """在日志区域显示消息。"""
        if self.log_area and self.log_area.isVisible(): # 确保日志区域存在且可见
            self.log_area.append(message) # 追加消息
            self.log_area.moveCursor(QTextCursor.MoveOperation.End) # 滚动到底部
        else: # 如果日志区域不可用
            if hasattr(self, 'log_area_early_messages'): # 尝试早期日志列表
                self.log_area_early_messages.append(message)
            print(f"[Log]: {message}") # 打印到控制台作为回退


    def load_config(self):
        """加载应用程序配置。"""
        if not os.path.exists(CONFIG_DIR): # 如果配置目录不存在
            try:
                os.makedirs(CONFIG_DIR) # 创建目录
            except OSError as e:
                self._early_log(f"创建配置目录失败: {e}"); return
        try:
            if os.path.exists(CONFIG_FILE): # 如果配置文件存在
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f) # 加载JSON
            else:
                self.config = {} # 如果文件不存在，则从空配置开始

            api_key = self.config.get('deepseek_api_key', '') # 获取API Key
            remember = self.config.get('remember_api_key', True) # 是否记住API Key
            last_json_path = self.config.get('last_json_path', '') # 上次JSON路径
            last_output_path = self.config.get('last_output_path', '') # 上次输出路径
            last_source_format = self.config.get('last_source_format', 'ElevenLabs(推荐)') # 上次源格式

            if self.json_format_combo:
                format_index = self.json_format_combo.findText(last_source_format) # 根据文本查找索引
                if format_index != -1:
                    self.json_format_combo.setCurrentIndex(format_index)
                else: # 如果保存的格式字符串不在当前项目中，则回退
                    self.json_format_combo.setCurrentIndex(0) # 默认选第一个

            if self.api_key_entry and self.remember_api_key_checkbox:
                if api_key and remember: # 如果有Key且勾选了记住
                    self.api_key_entry.setText(api_key)
                    self.remember_api_key_checkbox.setChecked(True)
                else: # 否则清空并取消勾选
                    self.api_key_entry.clear()
                    self.remember_api_key_checkbox.setChecked(False)

            if self.json_path_entry and os.path.isfile(last_json_path):
                self.json_path_entry.setText(last_json_path) # 恢复上次JSON路径

            if self.output_path_entry:
                if os.path.isdir(last_output_path):
                    self.output_path_entry.setText(last_output_path) # 恢复上次输出目录
                elif os.path.isdir(os.path.join(os.path.expanduser("~"),"Documents")): # 否则尝试 "文档" 目录
                    self.output_path_entry.setText(os.path.join(os.path.expanduser("~"),"Documents"))
                else:
                    self.output_path_entry.setText(os.path.expanduser("~")) # 再否则使用用户主目录

        except (json.JSONDecodeError, Exception) as e: # 处理加载或解析错误
             self.log_message(f"加载配置出错或配置格式错误: {e}")
             self.config = {} # 重置配置

    def save_config(self):
        """保存应用程序配置。"""
        if not (self.api_key_entry and self.remember_api_key_checkbox and \
                self.json_path_entry and self.output_path_entry and self.json_format_combo):
            self.log_message("警告: UI组件未完全初始化，无法保存配置。")
            return

        if not os.path.exists(CONFIG_DIR): # 确保配置目录存在
            try:
                os.makedirs(CONFIG_DIR)
            except OSError as e:
                self.log_message(f"创建配置目录失败: {e}"); return

        api_key = self.api_key_entry.text().strip()
        remember = self.remember_api_key_checkbox.isChecked()
        self.config['remember_api_key'] = remember
        if remember and api_key:
            self.config['deepseek_api_key'] = api_key # 如果记住且Key不为空，则保存
        elif 'deepseek_api_key' in self.config:
            del self.config['deepseek_api_key'] # 如果不记住，则从配置中删除

        self.config['last_json_path'] = self.json_path_entry.text()
        self.config['last_output_path'] = self.output_path_entry.text()
        self.config['last_source_format'] = self.json_format_combo.currentText() # 保存当前选中的格式文本
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False) # 保存为JSON
        except Exception as e:
            self.log_message(f"保存配置失败: {e}")

    def browse_json_file(self):
        """打开文件对话框选择JSON文件。"""
        if not self.json_path_entry: return
        start_dir = os.path.dirname(self.json_path_entry.text()) \
            if self.json_path_entry.text() and os.path.exists(os.path.dirname(self.json_path_entry.text())) \
            else os.path.expanduser("~") # 起始目录
        filepath, _ = QFileDialog.getOpenFileName(self, "选择 JSON 文件", start_dir, "JSON 文件 (*.json);;所有文件 (*.*)")
        if filepath:
            self.json_path_entry.setText(filepath) # 设置路径

    def select_output_dir(self):
        """打开目录对话框选择导出目录。"""
        if not self.output_path_entry: return
        start_dir = self.output_path_entry.text() \
            if self.output_path_entry.text() and os.path.isdir(self.output_path_entry.text()) \
            else os.path.expanduser("~") # 起始目录
        dirpath = QFileDialog.getExistingDirectory(self, "选择导出目录", start_dir)
        if dirpath:
            self.output_path_entry.setText(dirpath) # 设置路径

    def start_conversion(self):
        """开始转换过程。"""
        if not (self.api_key_entry and self.json_path_entry and self.output_path_entry and \
                self.json_format_combo and self.start_button and self.progress_bar and self.log_area):
            QMessageBox.critical(self, "错误", "UI组件未完全初始化，无法开始转换。")
            return

        api_key = self.api_key_entry.text().strip()
        json_path = self.json_path_entry.text().strip()
        output_dir = self.output_path_entry.text().strip()
        # 输入验证
        if not api_key: QMessageBox.warning(self, "缺少信息", "请输入 DeepSeek API Key。"); return
        if not json_path: QMessageBox.warning(self, "缺少信息", "请选择 JSON 文件。"); return
        if not os.path.isfile(json_path): QMessageBox.critical(self, "错误", f"JSON 文件不存在: {json_path}"); return
        if not output_dir: QMessageBox.warning(self, "缺少信息", "请选择导出目录。"); return
        if not os.path.isdir(output_dir): QMessageBox.critical(self, "错误", f"导出目录无效: {output_dir}"); return

        self.save_config(); # 保存当前配置
        self.start_button.setEnabled(False)
        self.start_button.setText("转换中...") # 更新按钮状态
        self.progress_bar.setValue(0)
        self.log_area.clear() # 重置进度条和日志
        self.log_message("准备开始...")
        selected_format_text = self.json_format_combo.currentText() # 获取选中的格式文本
        # 将UI显示的格式文本映射到内部使用的键名
        source_format_map = {"ElevenLabs(推荐)":"elevenlabs", "Whisper(推荐)":"whisper", "Deepgram":"deepgram", "AssemblyAI":"assemblyai"}
        source_format_key = source_format_map.get(selected_format_text, "elevenlabs") # 默认为elevenlabs

        if self.conversion_thread and self.conversion_thread.isRunning(): # 防止重复启动
             self.log_message("警告：上一个转换任务仍在进行中。请等待其完成后再开始新的任务。")
             self.start_button.setEnabled(True) # 如果提前返回，则重新启用按钮
             self.start_button.setText("开始转换")
             return

        # 创建并启动工作线程
        self.conversion_thread = QThread(parent=self) # parent=self 确保线程随主窗口关闭而结束
        self.worker = ConversionWorker(api_key, json_path, output_dir, self.srt_processor, source_format_key)
        self.worker.moveToThread(self.conversion_thread) # 将worker移到新线程
        # 连接信号槽
        self.worker.signals.finished.connect(self.on_conversion_finished)
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.log_message.connect(self.log_message)
        self.conversion_thread.started.connect(self.worker.run) # 线程启动时运行worker的run方法
        # 线程完成后自动清理
        self.worker.signals.finished.connect(self.conversion_thread.quit)
        self.worker.signals.finished.connect(self.worker.deleteLater) # type: ignore
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater) # type: ignore
        self.conversion_thread.finished.connect(self._clear_worker_references) # 清理引用
        self.conversion_thread.start() # 启动线程

    def _clear_worker_references(self):
        """清理 worker 和线程引用，并重置开始按钮状态。"""
        self.worker = None
        self.conversion_thread = None
        if hasattr(self, 'start_button') and self.start_button: # 确保按钮存在
            self.start_button.setEnabled(True)
            self.start_button.setText("开始转换")


    def update_progress(self, value: int):
        """更新进度条的值。"""
        if self.progress_bar:
            self.progress_bar.setValue(value)

    @staticmethod
    def show_message_box(parent_widget: Optional[QWidget], title: str, message: str, success: bool):
        """静态方法，用于显示消息框 (确保在主线程执行)。"""
        if parent_widget and parent_widget.isVisible(): # 确保父控件存在且可见
            # 使用 QTimer.singleShot 确保在 GUI 线程中执行消息框的显示
            QTimer.singleShot(0, lambda: (
                QMessageBox.information(parent_widget, title, message) if success
                else QMessageBox.critical(parent_widget, title, message)
            ))
        else: # 如果父控件不可用，可以考虑打印到控制台或记录到日志
            print(f"消息框 [{title}]: {message} (父控件不可用)")


    def on_conversion_finished(self, message: str, success: bool):
        """转换完成时的处理函数。"""
        if hasattr(self, 'start_button') and self.start_button: # 检查按钮是否存在
             self.start_button.setEnabled(True)
             self.start_button.setText("开始转换")

        if self.progress_bar:
            current_progress = self.progress_bar.value()
            if success:
                self.progress_bar.setValue(100) # 成功则设为100%
            else: # 失败则保持当前进度或0 (如果从未开始)
                self.progress_bar.setValue(current_progress if current_progress > 0 else 0)

        # Worker 已经通过信号记录了其最终消息，这里仅显示弹窗。
        # self.log_message(message) # 可选：再次记录到日志区
        HealJimakuApp.show_message_box(self, "转换结果", message, success) # 显示结果消息框


    def mousePressEvent(self, event): # event: QMouseEvent
        """鼠标按下事件，用于实现窗口拖动。"""
        if event.button() == Qt.MouseButton.LeftButton: # 仅左键
            # 检查是否点击在标题栏区域且不是在交互控件上
            title_bar_height = 80 # 假设标题栏区域高度
            is_on_title_bar_area = event.position().y() < title_bar_height

            # 获取鼠标位置的控件
            widget_at_pos = self.childAt(event.position().toPoint())
            is_interactive_control = False
            current_widget = widget_at_pos
            # 定义可交互控件类型，避免在这些控件上触发拖动
            interactive_widgets = (QPushButton, QLineEdit, QCheckBox, QTextEdit, QProgressBar, QComboBox, QAbstractItemView)

            while current_widget is not None: # 向上遍历父控件
                if isinstance(current_widget, interactive_widgets) or \
                   (hasattr(current_widget, 'objectName') and current_widget.objectName().startswith('qt_scrollarea')) or \
                   (QApplication.activePopupWidget() and isinstance(current_widget, QApplication.activePopupWidget().__class__)):
                    is_interactive_control = True
                    break
                current_widget = current_widget.parentWidget()

            if is_on_title_bar_area and not is_interactive_control: # 如果在标题栏区域且不是交互控件
                self.drag_pos = event.globalPosition().toPoint()
                self.is_dragging = True
                event.accept()
            else:
                event.ignore() # 否则忽略事件，允许控件自身处理

    def mouseMoveEvent(self, event): # event: QMouseEvent
        """鼠标移动事件，用于窗口拖动。"""
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton: # 如果正在拖动
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos) # 移动窗口
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event): # event: QMouseEvent
        """鼠标释放事件，停止窗口拖动。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            event.accept()

    def close_application(self):
        """关闭应用程序的槽函数。"""
        self.close()

    def closeEvent(self, event): # event: QCloseEvent
        """窗口关闭事件。"""
        self.log_message("正在关闭应用程序...")
        if self.conversion_thread and self.conversion_thread.isRunning(): # 如果转换线程仍在运行
            self.log_message("尝试停止正在进行的转换任务...")
            if self.worker:
                self.worker.stop() # 通知worker停止
            # 不直接 quit 和 wait，依赖 deleteLater 和 QThread 的父子关系来清理
            # self.conversion_thread.quit() # 请求线程退出
            # if not self.conversion_thread.wait(3000): # 等待最多3秒
            #     self.log_message("警告：工作线程在3秒内未能正常停止。可能需要强制退出。")
        self.save_config() # 保存配置
        super().closeEvent(event) # 调用父类关闭事件