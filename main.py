"""AutoBackup v1.0.2 入口"""
import sys
import os
import time
import ctypes
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_LOCK_DIR = os.path.join(os.environ.get("TEMP", os.path.dirname(os.path.abspath(__file__))), "AutoBackup")
os.makedirs(_LOCK_DIR, exist_ok=True)
LOCK_FILE = os.path.join(_LOCK_DIR, ".autobackup.lock")
ACTIVATE_FILE = os.path.join(_LOCK_DIR, ".autobackup.activate")


def _find_and_activate_window():
    """查找已有窗口并激活（由新进程调用，有前台权限）"""
    user32 = ctypes.windll.user32

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found_hwnd = []

    def enum_callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if title and "AutoBackup" in title:
            found_hwnd.append(hwnd)
            return False
        return True

    callback = WNDENUMPROC(enum_callback)
    user32.EnumWindows(callback, 0)

    if found_hwnd:
        hwnd = found_hwnd[0]
        kernel32 = ctypes.windll.kernel32
        SW_RESTORE = 9

        user32.ShowWindow(hwnd, SW_RESTORE)

        # AttachThreadInput: 把本进程线程挂到前台线程上，以绕过前台锁定
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread_id = user32.GetWindowThreadProcessId(fg_hwnd, None)
        target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        our_thread_id = kernel32.GetCurrentThreadId()

        if fg_thread_id and fg_thread_id != our_thread_id:
            user32.AttachThreadInput(our_thread_id, fg_thread_id, True)
        if target_thread_id and target_thread_id != our_thread_id:
            user32.AttachThreadInput(our_thread_id, target_thread_id, True)

        user32.SetForegroundWindow(hwnd)

        if fg_thread_id and fg_thread_id != our_thread_id:
            user32.AttachThreadInput(our_thread_id, fg_thread_id, False)
        if target_thread_id and target_thread_id != our_thread_id:
            user32.AttachThreadInput(our_thread_id, target_thread_id, False)
        return True
    return False


def check_existing_instance():
    """检查是否已有实例运行"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
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
    if check_existing_instance():
        _find_and_activate_window()
        time.sleep(0.3)
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