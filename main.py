"""AutoBackup v1.0.0 入口"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".autobackup.lock")
ACTIVATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".autobackup.activate")


def check_existing_instance():
    """检查是否已有实例运行"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            # 检查进程是否存在
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
        except:
            pass
    return False


def write_lock_file():
    """写入锁文件"""
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_lock_file():
    """移除锁文件"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass


def main():
    # 单实例检查
    if check_existing_instance():
        # 写入激活文件
        with open(ACTIVATE_FILE, "w") as f:
            f.write(str(time.time()))
        sys.exit(0)

    # 写入锁文件
    write_lock_file()

    # CLI 模式
    if len(sys.argv) > 1 and sys.argv[1] != "--minimized":
        from cli.commands import main as cli_main
        cli_main(sys.argv[1:])
        remove_lock_file()
        return

    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    start_minimized = "--minimized" in sys.argv
    window = MainWindow(start_minimized=start_minimized)
    window.setup_tray(app)

    def cleanup():
        remove_lock_file()
        try:
            if os.path.exists(ACTIVATE_FILE):
                os.remove(ACTIVATE_FILE)
        except:
            pass
    
    app.aboutToQuit.connect(cleanup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
