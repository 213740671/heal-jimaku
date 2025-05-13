from typing import Optional 
from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtGui import QPainter, QColor, QBrush, QLinearGradient, QFont
from PyQt6.QtCore import Qt

# --- 自定义控件 ---
class TransparentWidget(QWidget):
    """一个具有半透明背景和圆角的自定义QWidget。"""
    def __init__(self, parent: Optional[QWidget] = None, bg_color: QColor = QColor(255, 255, 255, 3)):
        super().__init__(parent)
        self.bg_color = bg_color
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) # 允许透明
    def paintEvent(self, event): # event 参数是 QPaintEvent，但通常不直接使用
        """绘制控件背景。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing) # 抗锯齿
        painter.setBrush(QBrush(self.bg_color))
        painter.setPen(Qt.PenStyle.NoPen) # 无边框
        painter.drawRoundedRect(self.rect(), 10, 10) # 绘制圆角矩形

class CustomLabel(QLabel):
    """具有描边效果的自定义QLabel。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_color = QColor(92, 138, 111) # 主文本颜色
        self.stroke_color = QColor(242, 234, 218) # 描边颜色
        self.setStyleSheet(f"color: {self.main_color.name()}; background-color: transparent;") # 设置样式
    def paintEvent(self, event): # event 参数是 QPaintEvent
        """绘制带描边的文本。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.text()
        rect = self.rect()
        font = self.font()
        painter.setFont(font)
        # 绘制描边
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0: continue # 跳过中心点
                shadow_rect = rect.translated(dx, dy)
                painter.setPen(self.stroke_color)
                painter.drawText(shadow_rect, self.alignment(), text)
        # 绘制主文本
        painter.setPen(self.main_color)
        painter.drawText(rect, self.alignment(), text)

class CustomLabel_title(QLabel):
    """用于标题的自定义描边QLabel。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_color = QColor(87, 128, 183) # 主标题颜色
        self.stroke_color = QColor(242, 234, 218) # 描边颜色
        self.setStyleSheet(f"color: {self.main_color.name()}; background-color: transparent;")
    def paintEvent(self, event): # event 参数是 QPaintEvent
        """绘制带描边的标题文本。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.text()
        rect = self.rect()
        font = self.font()
        painter.setFont(font)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0: continue
                shadow_rect = rect.translated(dx, dy)
                painter.setPen(self.stroke_color)
                painter.drawText(shadow_rect, self.alignment(), text)
        painter.setPen(self.main_color)
        painter.drawText(rect, self.alignment(), text)