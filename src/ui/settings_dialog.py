# src/ui/settings_dialog.py
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QDialogButtonBox, QSpacerItem, QSizePolicy, QDoubleSpinBox, QSpinBox, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QLocale
from PyQt6.QtGui import QFont, QColor, QIcon

from ui.custom_widgets import CustomLabel # 复用自定义控件
from config import ( # 导入默认值
    DEFAULT_MIN_DURATION_TARGET, DEFAULT_MAX_DURATION,
    DEFAULT_MAX_CHARS_PER_LINE, DEFAULT_DEFAULT_GAP_MS
)
from utils.file_utils import resource_path # 用于加载图标


class SettingsDialog(QDialog):
    # 定义一个信号，当设置被接受时发出，携带新的设置值
    settings_applied = pyqtSignal(dict)

    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自定义高级设置")
        self.setModal(True) # 确保是模态对话框
        self.current_settings = current_settings # 存储从主窗口传入的当前设置

        # 设置窗口基本属性
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # 使用一个容器 QWidget 来应用圆角和背景色，避免 QDialog 直接应用样式的问题
        container = QWidget(self)
        container.setObjectName("settingsDialogContainer")
        container.setStyleSheet("""
            QWidget#settingsDialogContainer {
                background-color: rgba(60, 60, 80, 220); /* 深灰色半透明 */
                border-radius: 10px;
            }
        """)

        dialog_layout = QVBoxLayout(self) # QDialog的布局
        dialog_layout.setContentsMargins(0,0,0,0) # QDialog 本身不留边距
        dialog_layout.addWidget(container)


        main_layout = QVBoxLayout(container) # 内容放在容器的布局中
        main_layout.setContentsMargins(25, 20, 25, 20)
        main_layout.setSpacing(18)

        # --- 标题栏 ---
        title_bar_layout = QHBoxLayout()
        title_label = CustomLabel("自定义高级设置")
        title_font = QFont('楷体', 16, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #E0E0E0; background-color: transparent;")

        close_button = QPushButton("×")
        close_button.setFixedSize(25, 25)
        close_button.setObjectName("dialogCloseButton")
        close_button.setToolTip("关闭")
        close_button.clicked.connect(self.reject) # 关闭按钮等同于取消

        title_bar_layout.addStretch()
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(close_button)
        main_layout.addLayout(title_bar_layout)


        # --- 参数控件 ---
        self.param_widgets = {}

        self.param_widgets['min_duration_target'] = self._create_slider_spinbox_row(
            "目标最小持续时间 (秒):",
            min_val=0.1, max_val=5.0, step=0.1, decimals=1,
            current_val=self.current_settings.get('min_duration_target', DEFAULT_MIN_DURATION_TARGET)
        )
        main_layout.addLayout(self.param_widgets['min_duration_target']['layout'])

        self.param_widgets['max_duration'] = self._create_slider_spinbox_row(
            "最大持续时间 (秒):",
            min_val=1.0, max_val=30.0, step=0.1, decimals=1,
            current_val=self.current_settings.get('max_duration', DEFAULT_MAX_DURATION)
        )
        main_layout.addLayout(self.param_widgets['max_duration']['layout'])

        self.param_widgets['max_chars_per_line'] = self._create_slider_spinbox_row(
            "每行最大字符数:",
            min_val=10, max_val=200, step=1, decimals=0,
            current_val=self.current_settings.get('max_chars_per_line', DEFAULT_MAX_CHARS_PER_LINE)
        )
        main_layout.addLayout(self.param_widgets['max_chars_per_line']['layout'])

        self.param_widgets['default_gap_ms'] = self._create_slider_spinbox_row(
            "字幕间默认间隙 (毫秒):",
            min_val=0, max_val=1000, step=10, decimals=0,
            current_val=self.current_settings.get('default_gap_ms', DEFAULT_DEFAULT_GAP_MS)
        )
        main_layout.addLayout(self.param_widgets['default_gap_ms']['layout'])

        main_layout.addSpacerItem(QSpacerItem(20, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # --- 按钮 ---
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        button_layout.addStretch()

        self.confirm_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.reset_button = QPushButton("重置")

        self.confirm_button.clicked.connect(self.accept_settings)
        self.cancel_button.clicked.connect(self.reject)
        self.reset_button.clicked.connect(self.reset_settings)

        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.confirm_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.apply_styles()
        self.resize(600, 420)


    def apply_styles(self):
        # 获取主窗口的QSS以便参考，或者定义一套独立的协调风格
        # 这里我们简单定义一些协调的样式
        qss_image_up_arrow = ""
        qss_image_down_arrow = ""
        up_arrow_path_str = resource_path('up_arrow.png')
        down_arrow_path_str = resource_path('down_arrow.png')

        if up_arrow_path_str and os.path.exists(up_arrow_path_str):
            qss_image_up_arrow = f"url('{up_arrow_path_str.replace(os.sep, '/')}')"
        if down_arrow_path_str and os.path.exists(down_arrow_path_str):
            qss_image_down_arrow = f"url('{down_arrow_path_str.replace(os.sep, '/')}')"


        style = f"""
            QDialog {{ /* 这个可能不会生效，因为我们用了容器QWidget */
                background-color: rgba(60, 60, 80, 210);
                border-radius: 12px;
            }}
            CustomLabel {{ /* SettingsDialog内的CustomLabel */
                color: #E0E0E0;
                background-color: transparent;
            }}
            QPushButton {{
                background-color: rgba(100, 149, 237, 170); color: white;
                border: 1px solid rgba(135, 206, 235, 100);
                border-radius: 6px;
                font-family: '楷体'; font-weight: bold; font-size: 11pt;
                padding: 7px 18px;
                min-width: 70px;
            }}
            QPushButton:hover {{ background-color: rgba(120, 169, 247, 200); }}
            QPushButton:pressed {{ background-color: rgba(80, 129, 217, 200); }}

            QPushButton#dialogCloseButton {{
                background-color: rgba(255, 99, 71, 160); color: white;
                border: none; border-radius: 12px; font-weight:bold; font-size: 10pt;
                padding: 0px; min-width: 25px; max-width:25px; min-height:25px; max-height:25px;
            }}
            QPushButton#dialogCloseButton:hover {{ background-color: rgba(255, 99, 71, 200); }}

            QSlider::groove:horizontal {{
                border: 1px solid rgba(120,120,120,150);
                background: rgba(255,255,255,60);
                height: 8px;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #A0A0A0, stop:1 #707070);
                border: 1px solid #4A4A4A;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
            QSlider::sub-page:horizontal {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5C8A6F, stop:1 #69CFF7); /* 沿用主窗口进度条颜色 */
                border: 1px solid rgba(120,120,120,150);
                height: 8px;
                border-radius: 4px;
            }}
            QSpinBox, QDoubleSpinBox {{
                background-color: rgba(255, 255, 255, 50); color: #EAEAEA;
                border: 1px solid rgba(135, 206, 235, 120); border-radius: 5px;
                padding: 4px;
                font-family: 'Microsoft YaHei'; font-size: 10pt;
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                subcontrol-origin: border;
                width: 18px;
                border-left: 1px solid rgba(135, 206, 235, 120);
                background-color: rgba(135, 206, 235, 100);
            }}
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
                background-color: rgba(135, 206, 235, 160);
            }}
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
                image: {qss_image_up_arrow if qss_image_up_arrow else "none"};
                width: 9px; height: 9px;
            }}
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
                image: {qss_image_down_arrow if qss_image_down_arrow else "none"};
                width: 9px; height: 9px;
            }}
        """
        self.setStyleSheet(style)


    def _create_slider_spinbox_row(self, label_text: str, min_val, max_val, step, decimals: int, current_val):
        row_layout = QHBoxLayout()
        row_layout.setSpacing(10)
        label = CustomLabel(label_text)
        label.setFont(QFont('楷体', 11))
        # label.setStyleSheet("color: #D0D0D0; background-color: transparent;") # 样式通过全局CustomLabel或QDialog的QSS统一

        if decimals > 0:
            spin_box = QDoubleSpinBox()
            spin_box.setDecimals(decimals)
            spin_box.setSingleStep(step)
            slider_multiplier = 10**decimals
            slider_min = int(min_val * slider_multiplier)
            slider_max = int(max_val * slider_multiplier)
            slider_step = int(step * slider_multiplier)
            slider_current = int(current_val * slider_multiplier)
        else:
            spin_box = QSpinBox()
            spin_box.setSingleStep(int(step))
            slider_multiplier = 1
            slider_min = int(min_val)
            slider_max = int(max_val)
            slider_step = int(step)
            slider_current = int(current_val)

        spin_box.setRange(min_val, max_val)
        spin_box.setValue(current_val)
        spin_box.setFixedWidth(85)


        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(slider_min, slider_max)
        slider.setSingleStep(slider_step)
        slider.setValue(slider_current)
        # slider.setTickPosition(QSlider.TickPosition.TicksBelow) # 可以按需添加刻度
        # slider.setTickInterval(slider_step * 5 if slider_step * 5 < (slider_max - slider_min) / 2 else slider_step)


        if decimals > 0:
            spin_box.valueChanged.connect(lambda value, s=slider, m=slider_multiplier: s.setValue(int(round(value * m))))
            slider.valueChanged.connect(lambda value, sb=spin_box, m=slider_multiplier: sb.setValue(float(value / m)))
        else:
            spin_box.valueChanged.connect(slider.setValue)
            slider.valueChanged.connect(spin_box.setValue)

        row_layout.addWidget(label, 3) # 增加label权重
        row_layout.addWidget(slider, 5) # 增加slider权重
        row_layout.addWidget(spin_box, 2) # spinbox权重

        return {"layout": row_layout, "slider": slider, "spin_box": spin_box}

    def accept_settings(self):
        new_settings = {
            'min_duration_target': self.param_widgets['min_duration_target']['spin_box'].value(),
            'max_duration': self.param_widgets['max_duration']['spin_box'].value(),
            'max_chars_per_line': self.param_widgets['max_chars_per_line']['spin_box'].value(),
            'default_gap_ms': self.param_widgets['default_gap_ms']['spin_box'].value(),
        }
        self.settings_applied.emit(new_settings)
        self.accept()

    def reset_settings(self):
        self.param_widgets['min_duration_target']['spin_box'].setValue(DEFAULT_MIN_DURATION_TARGET)
        self.param_widgets['max_duration']['spin_box'].setValue(DEFAULT_MAX_DURATION)
        self.param_widgets['max_chars_per_line']['spin_box'].setValue(DEFAULT_MAX_CHARS_PER_LINE)
        self.param_widgets['default_gap_ms']['spin_box'].setValue(DEFAULT_DEFAULT_GAP_MS)

    # 实现拖动 (如果需要对话框也能拖动，但通常模态对话框不需要)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否点击在标题栏区域 (假设标题栏高度约40)
            if event.position().y() < 40:
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