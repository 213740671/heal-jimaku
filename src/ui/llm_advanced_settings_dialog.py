import os
import json
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QSlider, QMessageBox, QSpacerItem, QSizePolicy, QApplication, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QObject, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QFont, QColor

import config
from ui.custom_widgets import CustomLabel
from utils.file_utils import resource_path

ICON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "info_icon.png"))

class LlmTestWorker(QObject):
    finished = pyqtSignal(bool, str)
    # 新增一个信号用于日志输出
    log_message = pyqtSignal(str)

    def __init__(self, api_key: str, base_url: str, model_name: str, temperature: float):
        super().__init__()
        self._api_key = api_key
        self._base_url = base_url
        self._model_name = model_name
        self._temperature = temperature

    def run(self):
        try:
            from core import llm_api
            # 将 log_message 信号传递给 llm_api.test_llm_connection
            # 确保 llm_api.test_llm_connection 能够接收并使用这个信号进行日志输出
            success, message = llm_api.test_llm_connection(
                api_key=self._api_key,
                custom_api_base_url_str=self._base_url,
                custom_model_name=self._model_name,
                custom_temperature=self._temperature,
                signals_forwarder=self # 传递自身作为信号转发器
            )
            self.finished.emit(success, message)
        except Exception as e:
            self.finished.emit(False, f"测试连接时发生内部错误: {e}")


class LlmAdvancedSettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(self, parent=None, current_llm_settings: Optional[Dict[str, Any]] = None, log_signal: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle("LLM高级设置")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(600, 420) # 调整窗口高度，使其更紧凑

        self.current_settings = current_llm_settings if current_llm_settings else self._load_default_llm_settings()

        self.test_thread = None
        self.test_worker = None
        self.status_message_box = None
        self.log_signal = log_signal # 保存日志信号

        # 鼠标拖动事件处理
        self.is_dragging_dialog = False
        self.drag_pos = QPoint()

        # 定义标题颜色，确保在_init_ui调用前已存在
        self.target_main_color = QColor(87, 128, 183) # 标题主颜色
        self.target_stroke_color = QColor(242, 234, 218) # 标题描边颜色

        self.container = QWidget(self)
        self.container.setObjectName("llmSettingsDialogContainer")

        # 这是对话框的顶层布局
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0,0,0,0)
        dialog_layout.addWidget(self.container)

        # 这是容器内部的布局，所有UI元素将添加到这里
        self.inner_content_layout = QVBoxLayout(self.container)
        self.inner_content_layout.setContentsMargins(25, 20, 25, 20)
        self.inner_content_layout.setSpacing(18)

        # 调用 _init_ui 来填充 inner_content_layout
        self._init_ui(self.inner_content_layout)

        # 应用样式、连接信号、加载设置
        self._apply_styles()
        self._connect_signals()
        self._load_settings_to_ui()


    def _init_ui(self, layout_to_populate: QVBoxLayout): # 接受要填充的布局作为参数
        # param_label_main_color 和 param_label_stroke_color 也可以在这里定义，或者作为类属性
        # 为了与标题颜色保持一致，这里直接使用 self.target_main_color 和 self.target_stroke_color
        self.param_label_main_color = self.target_main_color
        self.param_label_stroke_color = self.target_stroke_color

        # --- 标题栏 ---
        title_bar_layout = QHBoxLayout()
        title_label = CustomLabel("LLM高级设置")
        title_label.setCustomColors(main_color=self.target_main_color, stroke_color=self.target_stroke_color)
        title_font = QFont('楷体', 20, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.setObjectName("dialogCloseButton")
        close_button.setToolTip("关闭")
        close_button.clicked.connect(self.reject)

        title_bar_layout.addStretch()
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(close_button)
        layout_to_populate.addLayout(title_bar_layout) # 添加到传入的布局

        # --- API地址 ---
        api_url_layout = QHBoxLayout()
        api_url_label = CustomLabel("API地址:")
        api_url_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        api_url_label.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)

        self.api_url_edit = QLineEdit()
        self.api_url_edit.setObjectName("dialogLineEditFT")
        api_url_layout.addWidget(api_url_label, 2)
        api_url_layout.addWidget(self.api_url_edit, 5)

        self.api_url_hint_label = QLabel()
        try:
            info_icon_path_str = resource_path("info_icon.png")
            if info_icon_path_str and os.path.exists(info_icon_path_str):
                pixmap = QPixmap(info_icon_path_str).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.api_url_hint_label.setPixmap(pixmap)
            else:
                self.api_url_hint_label.setText("ⓘ") 
        except Exception:
            self.api_url_hint_label.setText("ⓘ") 

        api_url_tooltip = (
            "提示: 输入格式示例\n"
            "  - https://api.example.com -> 请求 https://api.example.com/v1/chat/completions\n"
            "  - https://api.example.com/ -> 请求 https://api.example.com/chat/completions\n"
            "  - https://api.example.com/custom_path# -> 请求 https://api.example.com/custom_path"
        )
        self.api_url_hint_label.setToolTip(api_url_tooltip)
        # self.api_url_edit.setToolTip(api_url_tooltip) # 移除输入框的tooltip
        api_url_layout.addWidget(self.api_url_hint_label, 1)
        layout_to_populate.addLayout(api_url_layout) # 添加到传入的布局

        # --- 模型名称 ---
        model_name_layout = QHBoxLayout()
        model_name_label = CustomLabel("API模型名称:")
        model_name_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        model_name_label.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        self.model_name_edit = QLineEdit()
        self.model_name_edit.setObjectName("dialogLineEditFT")
        model_name_layout.addWidget(model_name_label, 2)
        model_name_layout.addWidget(self.model_name_edit, 6)
        layout_to_populate.addLayout(model_name_layout) # 添加到传入的布局

        # --- 温度滑块 ---
        temp_layout = QHBoxLayout()
        temp_label = CustomLabel("温度(0到2):")
        temp_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        temp_label.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        
        self.temp_slider = QSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setMinimum(0)
        self.temp_slider.setMaximum(20)
        self.temp_slider.setSingleStep(1)
        self.temp_slider.setTickInterval(1)
        self.temp_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.temp_slider.setObjectName("dialogSlider")

        self.temp_value_label = QLabel(f"{config.DEFAULT_LLM_TEMPERATURE:.1f}")
        self.temp_value_label.setFont(QFont('Microsoft YaHei', 14))
        self.temp_value_label.setStyleSheet("color: #EAEAEA;")
        
        temp_layout.addWidget(temp_label, 3)
        temp_layout.addWidget(self.temp_slider, 7)
        temp_layout.addWidget(self.temp_value_label, 1)
        layout_to_populate.addLayout(temp_layout) # 添加到传入的布局

        # --- API Key 输入框 ---
        api_key_layout = QHBoxLayout()
        api_key_label = CustomLabel("API Key:")
        api_key_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        api_key_label.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setObjectName("dialogLineEditFT")
        api_key_layout.addWidget(api_key_label, 2)
        api_key_layout.addWidget(self.api_key_edit, 6)
        layout_to_populate.addLayout(api_key_layout) # 添加到传入的布局

        # --- 将“记住 API Key”复选框和“测试连接”按钮调换位置并调整间距 (35%/65%) ---
        test_and_remember_layout = QHBoxLayout()
        test_and_remember_layout.addStretch(7) # 左侧拉伸，推动“记住 API Key”到 35% 左右

        self.remember_api_key_checkbox = QCheckBox("记住 API Key") # 记住 API Key 复选框在左边
        self.remember_api_key_checkbox.setObjectName("dialogCheckboxFT")
        test_and_remember_layout.addWidget(self.remember_api_key_checkbox)

        test_and_remember_layout.addStretch(6) # 中间较大拉伸，将两者推开

        self.test_connection_button = QPushButton("测试连接") # 测试连接按钮在右边
        self.test_connection_button.setObjectName("dialogBrowseButton")
        test_and_remember_layout.addWidget(self.test_connection_button)

        test_and_remember_layout.addStretch(7) # 右侧拉伸，保持比例
        layout_to_populate.addLayout(test_and_remember_layout)
        
        # --- 按钮布局 (调换“确定”和“重置”的位置) ---
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        button_layout.addStretch()

        self.ok_button = QPushButton("确认") # 确定按钮提前
        self.ok_button.setObjectName("dialogButton")

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("dialogButton")
        
        self.reset_button = QPushButton("重置") # 重置按钮在最后
        self.reset_button.setObjectName("dialogButton")

        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        layout_to_populate.addLayout(button_layout)


    # 将样式代码封装到 _apply_styles 方法中
    def _apply_styles(self):
        # 容器背景色与 SettingsDialog 一致
        self.container.setStyleSheet("""
            QWidget#llmSettingsDialogContainer {
                background-color: rgba(60, 60, 80, 220);
                border-radius: 10px;
            }
        """)

        button_blue_bg = "rgba(100, 149, 237, 170)"
        button_blue_hover = "rgba(120, 169, 247, 200)"
        button_blue_pressed = "rgba(80, 129, 217, 200)"
        dialog_close_button_bg = "rgba(255, 99, 71, 160)"
        dialog_close_button_hover = "rgba(255, 99, 71, 200)"
        input_text_color = "#EAEAEA" # 浅色文本
        input_border_color = "rgba(135, 206, 235, 120)"
        input_bg = "rgba(255, 255, 255, 50)"
        input_hover_bg = "rgba(255, 255, 255, 60)"
        input_focus_bg = "rgba(255, 255, 255, 70)"
        
        qss_dropdown_arrow = ""
        dropdown_arrow_path_str = resource_path('dropdown_arrow.png')
        if dropdown_arrow_path_str and os.path.exists(dropdown_arrow_path_str):
            qss_dropdown_arrow = f"url('{dropdown_arrow_path_str.replace(os.sep, '/')}')"
        else:
            if self.log_signal: self.log_signal.emit(f"警告: 下拉箭头图标 'dropdown_arrow.png' 未找到。")

        qss_checkmark_image_url = ""
        raw_checkmark_path = resource_path('checkmark.png')
        if raw_checkmark_path and os.path.exists(raw_checkmark_path):
            abs_checkmark_path = os.path.abspath(raw_checkmark_path)
            formatted_checkmark_path = abs_checkmark_path.replace(os.sep, '/')
            qss_checkmark_image_url = f"url('{formatted_checkmark_path}')"
        else:
            if self.log_signal: self.log_signal.emit(f"警告: 选中标记图标 'checkmark.png' 未找到。")

        style = f"""
            CustomLabel {{
                background-color: transparent;
            }}
            QPushButton {{
                background-color: {button_blue_bg}; color: white;
                border: 1px solid rgba(135, 206, 235, 100);
                border-radius: 6px;
                font-family: '楷体'; font-weight: bold; font-size: 14pt;
                padding: 8px 20px;
                min-width: 80px;
            }}
            QPushButton:hover {{ background-color: {button_blue_hover}; }}
            QPushButton:pressed {{ background-color: {button_blue_pressed}; }}

            QPushButton#dialogCloseButton {{
                background-color: {dialog_close_button_bg}; color: white;
                border: none; border-radius: 15px; 
                font-weight:bold; font-size: 12pt; 
                padding: 0px; min-width: 30px; max-width:30px; min-height:30px; max-height:30px;
            }}
            QPushButton#dialogCloseButton:hover {{ background-color: {dialog_close_button_hover}; }}

            QLineEdit#dialogLineEditFT {{
                background-color: {input_bg}; 
                color: {input_text_color}; 
                border: 1px solid {input_border_color}; 
                border-radius: 5px;
                padding: 5px; 
                font-family: 'Microsoft YaHei'; font-size: 12pt;
            }}
            QLineEdit#dialogLineEditFT:hover {{
                background-color: {input_hover_bg};
            }}
            QLineEdit#dialogLineEditFT:focus {{
                background-color: {input_focus_bg};
                border: 1px solid rgba(135, 206, 235, 200);
            }}

            QSlider::groove:horizontal {{
                border: 1px solid rgba(120,120,120,150);
                background: rgba(255,255,255,60);
                height: 10px; 
                border-radius: 5px;
            }}
            QSlider::handle:horizontal {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #A0A0A0, stop:1 #707070);
                border: 1px solid #4A4A4A;
                width: 20px; 
                margin: -5px 0; 
                border-radius: 10px;
            }}
            QSlider::sub-page:horizontal {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5C8A6F, stop:1 #69CFF7); 
                border: 1px solid rgba(120,120,120,150);
                height: 10px; 
                border-radius: 5px;
            }}

            QCheckBox#dialogCheckboxFT {{
                color: {input_text_color};
                font-family: '楷体'; font-size: 14pt; font-weight: bold;
                spacing: 8px;
                background-color: transparent;
                padding: 5px 0px;
            }}
            QCheckBox#dialogCheckboxFT::indicator {{
                width: 20px; height: 20px;
                border: 1px solid {input_border_color};
                border-radius: 4px;
                background-color: {input_bg};
            }}
            QCheckBox#dialogCheckboxFT::indicator:checked {{
                background-color: rgba(100, 180, 230, 200);
                image: {qss_checkmark_image_url if qss_checkmark_image_url else "none"};
                background-repeat: no-repeat;
                background-position: center;
            }}

            QPushButton#dialogBrowseButton {{
                font-size: 12pt;
                padding: 6px 15px;
                min-width: 70px;
                background-color: rgba(120, 170, 130, 170); /* 绿色系 */
            }}
            QPushButton#dialogBrowseButton:hover {{ background-color: rgba(140, 190, 150, 200); }}
            QPushButton#dialogBrowseButton:pressed {{ background-color: rgba(100, 150, 110, 200); }}
        """
        self.setStyleSheet(style)

    def _connect_signals(self):
        self.ok_button.clicked.connect(self._save_settings_and_accept)
        self.cancel_button.clicked.connect(self.reject)
        self.reset_button.clicked.connect(self._reset_settings)
        self.test_connection_button.clicked.connect(self._test_connection)
        self.temp_slider.valueChanged.connect(self._update_temp_label)

    def _update_temp_label(self, value):
        self.temp_value_label.setText(f"{value / 10.0:.1f}")

    def _load_default_llm_settings(self) -> Dict[str, Any]:
        return {
            config.USER_LLM_API_BASE_URL_KEY: config.DEFAULT_LLM_API_BASE_URL,
            config.USER_LLM_MODEL_NAME_KEY: config.DEFAULT_LLM_MODEL_NAME,
            config.USER_LLM_API_KEY_KEY: config.DEFAULT_LLM_API_KEY,
            config.USER_LLM_REMEMBER_API_KEY_KEY: config.DEFAULT_LLM_REMEMBER_API_KEY,
            config.USER_LLM_TEMPERATURE_KEY: config.DEFAULT_LLM_TEMPERATURE
        }

    def _load_settings_to_ui(self):
        self.api_url_edit.setText(self.current_settings.get(config.USER_LLM_API_BASE_URL_KEY, config.DEFAULT_LLM_API_BASE_URL))
        self.model_name_edit.setText(self.current_settings.get(config.USER_LLM_MODEL_NAME_KEY, config.DEFAULT_LLM_MODEL_NAME))
        
        temp_value = self.current_settings.get(config.USER_LLM_TEMPERATURE_KEY, config.DEFAULT_LLM_TEMPERATURE)
        self.temp_slider.setValue(int(float(temp_value) * 10))
        self._update_temp_label(int(float(temp_value) * 10))

        self.api_key_edit.setText(self.current_settings.get(config.USER_LLM_API_KEY_KEY, config.DEFAULT_LLM_API_KEY))
        self.remember_api_key_checkbox.setChecked(self.current_settings.get(config.USER_LLM_REMEMBER_API_KEY_KEY, config.DEFAULT_LLM_REMEMBER_API_KEY))

    def _apply_ui_to_current_settings(self):
        self.current_settings[config.USER_LLM_API_BASE_URL_KEY] = self.api_url_edit.text().strip()
        self.current_settings[config.USER_LLM_MODEL_NAME_KEY] = self.model_name_edit.text().strip()
        self.current_settings[config.USER_LLM_TEMPERATURE_KEY] = self.temp_slider.value() / 10.0
        
        api_key = self.api_key_edit.text()
        remember_api_key = self.remember_api_key_checkbox.isChecked()
        self.current_settings[config.USER_LLM_REMEMBER_API_KEY_KEY] = remember_api_key

        if remember_api_key:
            self.current_settings[config.USER_LLM_API_KEY_KEY] = api_key
        else:
            self.current_settings[config.USER_LLM_API_KEY_KEY] = "" 

    def _save_settings_and_accept(self):
        self._apply_ui_to_current_settings()
        
        try:
            if not os.path.exists(config.CONFIG_DIR):
                os.makedirs(config.CONFIG_DIR)
            
            full_config_data = {}
            if os.path.exists(config.CONFIG_FILE):
                with open(config.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    full_config_data = json.load(f)
            
            full_config_data[config.USER_LLM_API_BASE_URL_KEY] = self.current_settings[config.USER_LLM_API_BASE_URL_KEY]
            full_config_data[config.USER_LLM_MODEL_NAME_KEY] = self.current_settings[config.USER_LLM_MODEL_NAME_KEY]
            full_config_data[config.USER_LLM_TEMPERATURE_KEY] = self.current_settings[config.USER_LLM_TEMPERATURE_KEY]
            full_config_data[config.USER_LLM_REMEMBER_API_KEY_KEY] = self.current_settings[config.USER_LLM_REMEMBER_API_KEY_KEY]

            if self.current_settings[config.USER_LLM_REMEMBER_API_KEY_KEY]:
                 full_config_data[config.USER_LLM_API_KEY_KEY] = self.current_settings[config.USER_LLM_API_KEY_KEY]
            elif config.USER_LLM_API_KEY_KEY in full_config_data: 
                del full_config_data[config.USER_LLM_API_KEY_KEY]

            with open(config.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(full_config_data, f, indent=4, ensure_ascii=False)
            
            self.settings_saved.emit() 
            self.accept() 
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置失败: {e}")

    def _reset_settings(self):
        reply = QMessageBox.question(self, "重置设置",
                                     "确定要将LLM高级设置重置为默认值吗？\n"
                                     "API地址、模型名称将恢复为DeepSeek官方设置，API Key将清空。",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.api_url_edit.setText(config.DEFAULT_LLM_API_BASE_URL)
            self.model_name_edit.setText(config.DEFAULT_LLM_MODEL_NAME)
            self.temp_slider.setValue(int(config.DEFAULT_LLM_TEMPERATURE * 10))
            self._update_temp_label(int(config.DEFAULT_LLM_TEMPERATURE * 10))
            self.api_key_edit.setText("") 
            self.remember_api_key_checkbox.setChecked(config.DEFAULT_LLM_REMEMBER_API_KEY)
            QMessageBox.information(self, "已重置", "LLM高级设置已恢复为默认值。请点击“确认”保存更改，或“取消”放弃。")

    def _test_connection(self):
        # 禁用按钮防止重复点击
        self.test_connection_button.setEnabled(False)
        self.ok_button.setEnabled(False) # 禁用确认按钮
        self.cancel_button.setEnabled(False) # 禁用取消按钮
        self.reset_button.setEnabled(False) # 禁用重置按钮

        # 获取当前UI中的值
        current_api_url = self.api_url_edit.text().strip()
        current_model_name = self.model_name_edit.text().strip()
        current_api_key = self.api_key_edit.text() 
        current_temperature = self.temp_slider.value() / 10.0

        # 创建并启动新线程
        self.test_thread = QThread()
        self.test_worker = LlmTestWorker(
            api_key=current_api_key,
            base_url=current_api_url,
            model_name=current_model_name,
            temperature=current_temperature
        )
        # 将 worker 的 log_message 信号连接到 dialog 的 log_signal
        self.test_worker.log_message.connect(self.log_signal)

        self.test_worker.moveToThread(self.test_thread)
        self.test_thread.started.connect(self.test_worker.run)
        self.test_worker.finished.connect(self._on_test_connection_finished)
        self.test_worker.finished.connect(self.test_thread.quit) # 测试完成后退出线程
        self.test_worker.finished.connect(self.test_worker.deleteLater) # 清理worker
        self.test_thread.finished.connect(self.test_thread.deleteLater) # 清理线程

        self.test_thread.start()
        
        # 显示一个非阻塞的提示信息，可以是一个临时的QLabel或者对话框
        self.status_message_box = QMessageBox(self) # 保持对这个QMessageBox的引用
        self.status_message_box.setWindowTitle("测试连接")
        self.status_message_box.setText("正在尝试连接，请稍候...")
        self.status_message_box.setIcon(QMessageBox.Icon.Information)
        self.status_message_box.setStandardButtons(QMessageBox.StandardButton.NoButton) # 没有按钮
        self.status_message_box.show() # 非阻塞显示

    def _on_test_connection_finished(self, success: bool, message: str):
        # 隐藏并清理之前的提示框
        if self.status_message_box:
            self.status_message_box.hide()
            self.status_message_box.deleteLater()
            self.status_message_box = None

        # 重新启用按钮
        self.test_connection_button.setEnabled(True)
        self.ok_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.reset_button.setEnabled(True)

        # 显示最终结果
        if success:
            QMessageBox.information(self, "测试连接成功", message)
        else:
            QMessageBox.warning(self, "测试连接失败", message)

    def get_current_settings(self) -> Dict[str, Any]:
        self._apply_ui_to_current_settings() 
        return self.current_settings

    # 鼠标拖动事件处理，与SettingsDialog和FreeTranscriptionDialog一致
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 假设标题栏高度为标题标签加其上下边距
            title_bar_height = self.container.layout().itemAt(0).geometry().height() + \
                               self.container.layout().contentsMargins().top()
            if event.position().y() < title_bar_height:
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
