"""AutoBackup v1.1.0 定时调度器"""
from PySide6.QtCore import QTimer


class BackupScheduler:
    def __init__(self):
        self._timer = None
        self._job_func = None
        self._interval_minutes = 0

    def start(self, interval_minutes, job_func):
        """启动定时调度"""
        self.stop()
        
        self._interval_minutes = interval_minutes
        self._job_func = job_func
        
        if interval_minutes > 0:
            self._timer = QTimer()
            self._timer.timeout.connect(self._job_func)
            self._timer.start(interval_minutes * 60 * 1000)

    def stop(self):
        """停止定时调度"""
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._job_func = None

    def update_interval(self, interval_minutes):
        """更新定时间隔"""
        if interval_minutes > 0 and self._job_func:
            self.start(interval_minutes, self._job_func)

    @property
    def is_running(self):
        return self._timer is not None and self._timer.isActive()
