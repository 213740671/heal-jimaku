import sys
import os

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from utils.file_utils import resource_path, setup_faulthandler
from ui.main_window import HealJimakuApp

if __name__ == "__main__":
    setup_faulthandler()
    app = QApplication(sys.argv)

    high_dpi_scaling_set = False
    high_dpi_pixmaps_set = False

    try:
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            high_dpi_scaling_set = True
        else:
            pass # 忽略错误
            #print("信息: Qt.AA_EnableHighDpiScaling 属性未在当前PyQt6环境中找到。")

        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
            high_dpi_pixmaps_set = True
        else:
            pass # 忽略错误
            #print("信息: Qt.AA_UseHighDpiPixmaps 属性未在当前PyQt6环境中找到。")

        # if high_dpi_scaling_set or high_dpi_pixmaps_set:
        #     print("已尝试设置高DPI相关属性。")

    except AttributeError as e:
        # 这个捕获理论上应该不会再被触发，因为我们先用 hasattr 检查了
        # 但保留它以防万一 setAttribute 内部仍因其他原因抛出 AttributeError
        print(f"警告: 设置高DPI属性时遇到 AttributeError (可能是Qt版本内部问题): {e}")
    except Exception as e_generic:
        print(f"警告: 设置高DPI属性时发生未知错误: {e_generic}")

    app.setApplicationName("HealJimaku")
    # ... 后续代码 ...
    if os.name == 'nt':
        try:
            import ctypes
            myappid_str = 'fuxiaomoke.HealJimaku.Refactored.Project.0.0.3' # 更新一下ID
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid_str)
        except Exception:
            pass # 忽略错误

    app_icon_early_path = resource_path("icon.ico")
    if app_icon_early_path and os.path.exists(app_icon_early_path):
        app.setWindowIcon(QIcon(app_icon_early_path))
    else:
        print("[Log Early Main] 应用图标 'icon.ico' 在主程序启动时未找到。")

    window = HealJimakuApp()
    window.show()
    sys.exit(app.exec())