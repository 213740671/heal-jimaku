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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self.bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 10, 10)

class CustomLabel(QLabel):
    """具有描边效果的自定义QLabel。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 这些是默认颜色，主窗口中的 CustomLabel 将使用这些
        self.main_color = QColor(92, 138, 111) # 默认主文本颜色 (绿色)
        self.stroke_color = QColor(242, 234, 218) # 默认描边颜色 (白/米白色)
        # self.setStyleSheet(f"color: {self.main_color.name()}; background-color: transparent;")
        # 上一行setStyleSheet可以保留，也可以移除，因为paintEvent优先。
        # 为了避免混淆，如果主要通过paintEvent控制颜色，可以考虑简化或移除此处的setStyleSheet color部分。
        # 或者，让main_color受QSS影响，但这需要修改paintEvent。目前paintEvent直接用self.main_color。
        self.setStyleSheet("background-color: transparent;") # 只设置背景透明


    # 允许单独设置颜色
    def setCustomColors(self, main_color: QColor, stroke_color: QColor):
        self.main_color = main_color
        self.stroke_color = stroke_color
        self.update() # 请求重新绘制以应用新颜色

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.text()
        rect = self.rect()
        font = self.font()
        painter.setFont(font)
        
        # 绘制描边 (只有当描边颜色不是完全透明时才绘制)
        if self.stroke_color.alpha() > 0:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    shadow_rect = rect.translated(dx, dy)
                    painter.setPen(self.stroke_color)
                    painter.drawText(shadow_rect, self.alignment(), text)
        
        # 绘制主文本
        painter.setPen(self.main_color)
        painter.drawText(rect, self.alignment(), text)

class CustomLabel_title(QLabel): # 主窗口标题用的这个
    """用于标题的自定义描边QLabel。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 这些是默认颜色，主窗口的标题 CustomLabel_title 将使用这些
        self.main_color = QColor(87, 128, 183) # 默认主标题颜色 (蓝色)
        self.stroke_color = QColor(242, 234, 218) # 默认描边颜色 (白/米白色)
        # self.setStyleSheet(f"color: {self.main_color.name()}; background-color: transparent;")
        self.setStyleSheet("background-color: transparent;")

    # 允许单独设置颜色 
    def setCustomColors(self, main_color: QColor, stroke_color: QColor):
        self.main_color = main_color
        self.stroke_color = stroke_color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.text()
        rect = self.rect()
        font = self.font()
        painter.setFont(font)

        if self.stroke_color.alpha() > 0:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    shadow_rect = rect.translated(dx, dy)
                    painter.setPen(self.stroke_color)
                    painter.drawText(shadow_rect, self.alignment(), text)
        
        painter.setPen(self.main_color)
        painter.drawText(rect, self.alignment(), text)