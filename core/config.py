"""AutoBackup v1.0.2 配置管理"""
import json
import os
import sys
import threading

DEFAULT_CONFIG = {
    "destination": "",
    "sources": [],
    "interval_minutes": 60,
    "auto_backup_on_start": False,
    "auto_start_with_system": False,
    "show_floating_button": False,
    "floating_button_pos": {"x": 100, "y": 100},
    "scheduler_enabled": False,
    "backup_password": "",
    "window_geometry": {
        "x": 100,
        "y": 100,
        "width": 800,
        "height": 600
    }
}

BASE_DIR = os.path.join(os.environ.get("APPDATA", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "AutoBackup")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOG_PATH = os.path.join(BASE_DIR, "backup_log.json")


class Config:
    def __init__(self, path=CONFIG_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._data = None
        self.load()

    def load(self):
        with self._lock:
            if os.path.exists(self._path):
                try:
                    with open(self._path, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    self._data = dict(DEFAULT_CONFIG)
            else:
                self._data = dict(DEFAULT_CONFIG)
            for k, v in DEFAULT_CONFIG.items():
                if k not in self._data:
                    self._data[k] = v

    def save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
            self.save()

    @property
    def destination(self):
        return self.get("destination", "")

    @destination.setter
    def destination(self, value):
        self.set("destination", value)

    @property
    def sources(self):
        return self.get("sources", [])

    @sources.setter
    def sources(self, value):
        self.set("sources", value)

    @property
    def interval_minutes(self):
        return self.get("interval_minutes", 60)

    @interval_minutes.setter
    def interval_minutes(self, value):
        self.set("interval_minutes", value)

    @property
    def auto_backup_on_start(self):
        return self.get("auto_backup_on_start", False)

    @auto_backup_on_start.setter
    def auto_backup_on_start(self, value):
        self.set("auto_backup_on_start", value)

    @property
    def auto_start_with_system(self):
        return self.get("auto_start_with_system", False)

    @auto_start_with_system.setter
    def auto_start_with_system(self, value):
        self.set("auto_start_with_system", value)

    @property
    def show_floating_button(self):
        return self.get("show_floating_button", False)

    @show_floating_button.setter
    def show_floating_button(self, value):
        self.set("show_floating_button", value)

    @property
    def floating_button_pos(self):
        return self.get("floating_button_pos", {"x": 100, "y": 100})

    @floating_button_pos.setter
    def floating_button_pos(self, value):
        self.set("floating_button_pos", value)

    @property
    def scheduler_enabled(self):
        return self.get("scheduler_enabled", False)

    @scheduler_enabled.setter
    def scheduler_enabled(self, value):
        self.set("scheduler_enabled", value)

    @property
    def backup_password(self):
        return self.get("backup_password", "")

    @backup_password.setter
    def backup_password(self, value):
        self.set("backup_password", value)

    @property
    def window_geometry(self):
        return self.get("window_geometry", DEFAULT_CONFIG["window_geometry"])

    @window_geometry.setter
    def window_geometry(self, value):
        self.set("window_geometry", value)

    def add_source(self, path, enabled=True):
        """添加备份源"""
        with self._lock:
            sources = self._data.get("sources", [])
            sources.append({"path": path, "enabled": enabled})
            self._data["sources"] = sources
            self.save()

    def remove_source(self, path):
        """移除备份源"""
        with self._lock:
            sources = self._data.get("sources", [])
            self._data["sources"] = [s for s in sources if s.get("path") != path]
            self.save()

    def toggle_source(self, path):
        """切换备份源启用状态"""
        with self._lock:
            sources = self._data.get("sources", [])
            for s in sources:
                if s.get("path") == path:
                    s["enabled"] = not s.get("enabled", True)
                    break
            self._data["sources"] = sources
            self.save()

    def to_dict(self):
        with self._lock:
            return dict(self._data)

    def update_source_status(self, source_path, success, fail_reason=""):
        """更新源文件夹备份状态"""
        with self._lock:
            from datetime import datetime
            sources = self._data.get("sources", [])
            for s in sources:
                if s.get("path") == source_path:
                    s["last_backup_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    s["last_backup_success"] = success
                    s["last_backup_fail_reason"] = fail_reason if not success else ""
                    break
            self._data["sources"] = sources
            self.save()


class BackupLogger:
    def __init__(self, path=LOG_PATH):
        self._path = path
        self._lock = threading.Lock()

    def add_entry(self, entry):
        """添加备份记录"""
        with self._lock:
            logs = self._read()
            logs.append(entry)
            self._write(logs)

    def get_all(self):
        """获取所有备份记录（最新在前）"""
        with self._lock:
            logs = self._read()
            return list(reversed(logs))

    def remove_by_index(self, display_index):
        """按显示索引移除记录（支持多选删除）"""
        with self._lock:
            logs = self._read()
            actual = len(logs) - 1 - display_index
            if 0 <= actual < len(logs):
                removed = logs.pop(actual)
                self._write(logs)
                return removed
        return None

    def clear(self):
        """清空所有记录"""
        with self._lock:
            self._write([])

    def _read(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _write(self, data):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
