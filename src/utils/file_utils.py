import sys
import os
import faulthandler

# --- 资源路径处理函数 ---
def resource_path(relative_path):
    """获取资源的绝对路径，用于开发环境和打包后环境。如果找不到则返回None。"""
    path = None
    try:
        # PyInstaller 创建一个临时文件夹并将路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS # type: ignore # 打包后的路径
        path = os.path.join(base_path, "assets", relative_path)
        if not os.path.exists(path): # 尝试不带 "assets" 子目录
            path = os.path.join(base_path, relative_path) # 有些资源可能直接在 MEIPASS 根目录
    except AttributeError: # 开发环境
        # 获取当前文件 (file_utils.py) 所在的目录 (src/utils/)
        current_file_dir = os.path.abspath(os.path.dirname(__file__))
        # 从 src/utils/ 回到 src/
        src_dir = os.path.dirname(current_file_dir)
        # 从 src/ 回到项目根目录 heal_jimaku_project/
        project_root = os.path.dirname(src_dir)

        # 优先尝试项目根目录下的 assets/ 文件夹
        path_in_project_assets = os.path.join(project_root, "assets", relative_path)
        if os.path.exists(path_in_project_assets):
            path = path_in_project_assets
        else:
            # 如果项目根目录的 assets/ 中找不到，尝试直接在项目根目录（用于非 assets 资源，如果需要）
            # 或者 src/assets/ (如果有些资源错误地放在那里)
            # 但通常我们期望 assets/ 就在项目根目录
            # 为了兼容原逻辑中一些复杂的查找，这里简化为优先项目根目录下的assets
            # 如果你的资源也可能在 src/assets/，可以取消注释下面的行
            # path_in_src_assets = os.path.join(src_dir, "assets", relative_path)
            # if os.path.exists(path_in_src_assets):
            #     path = path_in_src_assets
            # else:
            #     # 最后的尝试，直接在项目根目录（比如 README.md 等文件如果需要路径）
            #     direct_project_path = os.path.join(project_root, relative_path)
            #     if os.path.exists(direct_project_path):
            #         path = direct_project_path
            #     else:
            path = None # 最终找不到

    if path and not os.path.exists(path):
        # print(f"警告: 在计算路径处未找到资源: {path} (相对路径: {relative_path})") # 仅调试时使用
        return None
    return path


# --- faulthandler 错误处理模块设置 ---
def setup_faulthandler():
    """初始化 faulthandler 用于错误日志记录。"""
    try:
        FHT_LOG_ENABLED = False # pylint: disable=unused-variable
        if sys.stderr is None: # 通常在没有控制台的 GUI 应用中 (例如通过 pyinstaller --noconsole 打包)
            log_dir_app = ""
            try:
                home_dir = os.path.expanduser("~")
                # 将日志文件夹放在用户目录下的 .config 或类似位置更标准，但为了保持原样：
                log_dir_app = os.path.join(home_dir, ".heal_jimaku_gui_logs")
                if not os.path.exists(log_dir_app):
                    os.makedirs(log_dir_app, exist_ok=True)
                crash_log_path = os.path.join(log_dir_app, "heal_jimaku_crashes.log")
                with open(crash_log_path, 'a', encoding='utf-8') as f_log:
                    faulthandler.enable(file=f_log, all_threads=True)
                FHT_LOG_ENABLED = True # pylint: disable=unused-variable
                print(f"Faulthandler enabled, logging to: {crash_log_path}") # GUI下此print可能不可见
            except Exception as e_fh_file:
                print(f"Failed to enable faulthandler to file: {e_fh_file}") # 尝试打印错误
                pass # 如果文件日志设置失败，则不启用
        else: # 如果有 stderr (例如从命令行运行)
            faulthandler.enable(all_threads=True)
            FHT_LOG_ENABLED = True # pylint: disable=unused-variable
            # print("Faulthandler enabled, logging to stderr.")
    except Exception as e_fh_setup:
        print(f"Failed to setup faulthandler: {e_fh_setup}")
        pass