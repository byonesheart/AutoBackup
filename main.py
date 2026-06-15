"""AutoBackup v1.1.0 入口"""
import sys
import os
import time
import ctypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_LOCK_DIR = os.path.join(os.environ.get("TEMP", os.path.dirname(os.path.abspath(__file__))), "AutoBackup")
os.makedirs(_LOCK_DIR, exist_ok=True)
LOCK_FILE = os.path.join(_LOCK_DIR, ".autobackup.lock")
ACTIVATE_FILE = os.path.join(_LOCK_DIR, ".autobackup.activate")


def check_existing_instance():
    """检查是否已有实例运行，返回 PID 或 None"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return pid
        except:
            pass
    return None


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
    existing_pid = check_existing_instance()
    if existing_pid:
        # 授权旧进程前台权限，然后通知它自己激活
        ctypes.windll.user32.AllowSetForegroundWindow(existing_pid)
        with open(ACTIVATE_FILE, "w") as f:
            f.write(str(time.time()))
        sys.exit(0)

    write_lock_file()

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