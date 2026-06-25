"""AutoBackup v1.1.1 主窗口"""
import ctypes
import os
import sys
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QSpinBox,
    QCheckBox, QGroupBox, QFileDialog, QApplication, QMessageBox,
    QMenu, QSystemTrayIcon, QStyle, QTabWidget, QHeaderView,
    QAbstractItemView
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QBrush, QColor

from core.config import Config, BackupLogger
from core.engine import backup_all, restore_backup
from core.scheduler import BackupScheduler
from ui.floating_button import FloatingButton

ACTIVATE_FILE = os.path.join(os.environ.get('TEMP', os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'AutoBackup', '.autobackup.activate')



class MainWindow(QMainWindow):
    def __init__(self, start_minimized=False):
        super().__init__()
        self.config = Config()
        self.logger = BackupLogger()
        self.scheduler = BackupScheduler()
        self._tray = None
        self._quitting = False
        self.floating_button = None
        self._next_backup_time = None
        self._scheduler_menu_action = None
        self._show_password = False

        self.setWindowTitle("AutoBackup v1.1.1")
        self.setMinimumSize(680, 600)
        self._restore_geometry()

        self._build_ui()
        self._load_config_to_ui()
        self._connect_signals()

        self._activation_timer = QTimer(self)
        self._activation_timer.timeout.connect(self._check_activation_file)
        self._activation_timer.start(1000)


        self._init_floating_button()

        if self.config.auto_backup_on_start and not start_minimized:
            QTimer.singleShot(1000, lambda: self._do_backup(source="自动"))

        if self.config.scheduler_enabled and self.config.interval_minutes > 0:
            self._start_scheduler()

        if start_minimized:
            self.hide()
        else:
            self.show()

    def _restore_geometry(self):
        geo = self.config.window_geometry
        self.resize(geo.get("width", 800), geo.get("height", 600))
        x = geo.get("x", 100)
        y = geo.get("y", 100)
        self.move(x, y)

    def _save_geometry(self):
        geo = {"x": self.x(), "y": self.y(), "width": self.width(), "height": self.height()}
        self.config.window_geometry = geo
        self.config.save()

    def _init_floating_button(self):
        if self.config.show_floating_button:
            self._show_floating_button()
        else:
            self._hide_floating_button()

    def _show_floating_button(self):
        if not self.floating_button:
            pos = self.config.floating_button_pos
            self.floating_button = FloatingButton(
                on_click_callback=self._do_backup,
                on_toggle_scheduler=self._toggle_scheduler_from_menu,
                on_close=self._close_floating_from_menu
            )
            self.floating_button.move(pos.get("x", 100), pos.get("y", 100))
        self.floating_button.set_scheduler_state(self.scheduler.is_running)
        if self._next_backup_time:
            self.floating_button.set_next_backup_time(self._next_backup_time.strftime('%H:%M:%S'))
        self.floating_button.show()

    def _save_floating_button_pos(self):
        if self.floating_button:
            pos = {"x": self.floating_button.x(), "y": self.floating_button.y()}
            self.config.floating_button_pos = pos
            self.config.save()

    def _hide_floating_button(self):
        if self.floating_button:
            self.floating_button.close()
            self.floating_button = None

    def _close_floating_from_menu(self):
        self.config.show_floating_button = False
        self.config.save()
        self.floating_btn_cb.setChecked(False)
        self._hide_floating_button()

    def _find_latest_backup(self, source_path):
        """查找源路径对应的最新备份文件（源路径可能已被删除）"""
        if not self.config.destination or not source_path:
            return None
        
        source_name = os.path.basename(source_path.rstrip("\\/"))
        name_without_ext = os.path.splitext(source_name)[0]
        
        # 同时检查文件和文件夹两种备份目录命名
        candidate_folders = [
            os.path.join(self.config.destination, f"{name_without_ext}备份"),
            os.path.join(self.config.destination, f"{source_name}备份"),
        ]
        
        backup_folder = None
        for folder in candidate_folders:
            if os.path.exists(folder):
                backup_folder = folder
                break
        
        if not backup_folder:
            return None
        
        zip_files = [f for f in os.listdir(backup_folder) if f.endswith('.zip')]
        if not zip_files:
            return None
        
        zip_files.sort(reverse=True)
        return os.path.join(backup_folder, zip_files[0])


    def _get_password_for_backup(self, zip_path):
        """从日志中查找备份文件对应的密码"""
        if not zip_path:
            return None
        for entry in self.logger.get_all():
            if entry.get("zip_path") == zip_path:
                pwd = entry.get("password", "")
                return pwd if pwd else None
        return None
    def _restore_from_source(self, row):
        """从源路径行恢复备份"""
        item = self.src_table.item(row, 3)
        if not item:
            return
        
        source_path = item.toolTip() or item.text()
        if not source_path:
            QMessageBox.warning(self, "恢复失败", "无法确定源文件路径。")
            return
        
        latest_backup = self._find_latest_backup(source_path)
        if not latest_backup or not os.path.exists(latest_backup):
            QMessageBox.warning(self, "恢复失败", "未找到该路径的备份文件。")
            return
        
        # 通过备份目录名推断是文件还是文件夹
        backup_basename = os.path.basename(os.path.dirname(latest_backup))
        source_basename = os.path.basename(source_path.rstrip("\\/"))
        name_without_ext = os.path.splitext(source_basename)[0]
        is_file = (backup_basename == f"{name_without_ext}备份" and backup_basename != f"{source_basename}备份")
        type_text = "文件" if is_file else "文件夹"
        
        msg = QMessageBox(self)
        msg.setWindowTitle("确认恢复")
        msg.setText(f"将使用最新备份恢复{type_text}：\n\n{source_path}\n\n备份文件：{os.path.basename(latest_backup)}\n\n注意：这将覆盖现有内容。")
        msg.setIcon(QMessageBox.Question)
        yes_btn = msg.addButton("是", QMessageBox.AcceptRole)
        no_btn = msg.addButton("否", QMessageBox.RejectRole)
        msg.exec()
        reply = msg.clickedButton()
        
        if reply != yes_btn:
            return
        
        stored_pwd = self._get_password_for_backup(latest_backup)
        password = stored_pwd if stored_pwd else (self.config.backup_password if self.config.backup_password else None)
        success, error = restore_backup(latest_backup, os.path.dirname(source_path), password)
        
        if success:
            QMessageBox.information(self, "恢复成功", f"{type_text}已成功恢复。")
        else:
            QMessageBox.critical(self, "恢复失败", f"恢复失败：\n{error}")
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)

        dest_group = QGroupBox("备份存放位置")
        dest_layout = QHBoxLayout(dest_group)
        self.dest_edit = QLineEdit()
        self.dest_edit.setPlaceholderText("选择备份文件存放的文件夹...")
        self.dest_btn = QPushButton("浏览...")
        self.dest_btn.setFixedWidth(80)
        self.open_dest_btn = QPushButton("打开文件夹")
        self.open_dest_btn.setFixedWidth(80)
        dest_layout.addWidget(self.dest_edit, 1)
        dest_layout.addWidget(self.dest_btn)
        dest_layout.addWidget(self.open_dest_btn)
        main_layout.addWidget(dest_group)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        src_tab = QWidget()
        src_layout = QVBoxLayout(src_tab)

        self.src_table = QTableWidget(0, 6)
        self.src_table.setHorizontalHeaderLabels(["恢复", "状态", "文件名", "路径", "最近备份", "状态文本"])
        self.src_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.src_table.setColumnWidth(0, 60)
        self.src_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.src_table.setColumnWidth(1, 40)
        self.src_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.src_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.src_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.src_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.src_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.src_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.src_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.src_table.verticalHeader().setVisible(False)
        self.src_table.cellDoubleClicked.connect(self._on_source_double_clicked)
        self.src_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.src_table.customContextMenuRequested.connect(self._show_source_context_menu)
        src_layout.addWidget(self.src_table)

        src_btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("添加")
        self.remove_btn = QPushButton("移除")
        self.pause_btn = QPushButton("启用/暂停")
        src_btn_layout.addWidget(self.add_btn)
        src_btn_layout.addWidget(self.remove_btn)
        src_btn_layout.addWidget(self.pause_btn)
        src_btn_layout.addStretch()
        src_layout.addLayout(src_btn_layout)

        self.tabs.addTab(src_tab, "待备份")

        hist_tab = QWidget()
        hist_layout = QVBoxLayout(hist_tab)

        self.hist_table = QTableWidget(0, 6)
        self.hist_table.setHorizontalHeaderLabels(["恢复", "文件名", "备份路径", "备份时间", "结果", "详情"])
        self.hist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.hist_table.setColumnWidth(0, 60)
        self.hist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.hist_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.hist_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.hist_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.hist_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.hist_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hist_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hist_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.hist_table.verticalHeader().setVisible(False)
        self.hist_table.cellDoubleClicked.connect(self._on_history_double_clicked)
        hist_layout.addWidget(self.hist_table)

        hist_btn_layout = QHBoxLayout()
        self.remove_hist_btn = QPushButton("移除记录")
        self.clear_hist_btn = QPushButton("清空记录")
        hist_btn_layout.addWidget(self.remove_hist_btn)
        hist_btn_layout.addWidget(self.clear_hist_btn)
        hist_btn_layout.addStretch()
        hist_layout.addLayout(hist_btn_layout)

        self.tabs.addTab(hist_tab, "备份记录")

        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)

        interval_group = QGroupBox("定时备份")
        interval_layout = QHBoxLayout(interval_group)
        interval_layout.addWidget(QLabel("间隔（分钟）："))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(0, 1440)
        self.interval_spin.setValue(0)
        interval_layout.addWidget(self.interval_spin)
        self.schedule_toggle_btn = QPushButton("启动定时")
        interval_layout.addWidget(self.schedule_toggle_btn)
        self.next_backup_label = QLabel("")
        interval_layout.addWidget(self.next_backup_label)
        interval_layout.addStretch()
        settings_layout.addWidget(interval_group)

        password_group = QGroupBox("备份加密")
        password_layout = QHBoxLayout(password_group)
        password_layout.addWidget(QLabel("密码："))
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("留空表示不加密")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setMinimumWidth(200)
        password_layout.addWidget(self.password_edit)
        self.toggle_password_btn = QPushButton("显示")
        self.toggle_password_btn.setFixedWidth(50)
        password_layout.addWidget(self.toggle_password_btn)
        password_layout.addStretch()
        settings_layout.addWidget(password_group)

        autostart_group = QGroupBox("启动设置")
        autostart_layout = QVBoxLayout(autostart_group)
        self.autostart_cb = QCheckBox("开机自启动")
        self.autobackup_cb = QCheckBox("启动时自动执行备份")
        self.floating_btn_cb = QCheckBox("显示悬浮备份按钮")
        autostart_layout.addWidget(self.autostart_cb)
        autostart_layout.addWidget(self.autobackup_cb)
        autostart_layout.addWidget(self.floating_btn_cb)
        settings_layout.addWidget(autostart_group)

        
        about_group = QGroupBox("关于")
        about_layout = QVBoxLayout(about_group)
        author_label = QLabel("作者：byonesheart")
        about_layout.addWidget(author_label)
        
        github_label = QLabel()
        github_label.setText('GitHub：<a href="https://github.com/byonesheart/AutoBackup">byonesheart/AutoBackup</a>')
        github_label.setOpenExternalLinks(True)
        about_layout.addWidget(github_label)
        
        bilibili_label = QLabel()
        bilibili_label.setText('B站：<a href="https://space.bilibili.com/481766725">byonesheart</a>')
        bilibili_label.setOpenExternalLinks(True)
        about_layout.addWidget(bilibili_label)
        
        free_label = QLabel("本软件完全免费，无偿分享。")
        about_layout.addWidget(free_label)
        settings_layout.addWidget(about_group)
        settings_layout.addStretch()
        self.tabs.addTab(settings_tab, "设置")

        bottom_layout = QHBoxLayout()
        self.backup_btn = QPushButton("立即备份")
        self.backup_btn.setFixedHeight(40)
        bottom_layout.addWidget(self.backup_btn)
        main_layout.addLayout(bottom_layout)

    def _load_config_to_ui(self):
        self.dest_edit.setText(self.config.destination)
        self.interval_spin.setValue(self.config.interval_minutes)
        self.autostart_cb.setChecked(self.config.auto_start_with_system)
        self.autobackup_cb.setChecked(self.config.auto_backup_on_start)
        self.floating_btn_cb.setChecked(self.config.show_floating_button)
        self.password_edit.setText(self.config.backup_password)
        self._refresh_source_table()
        self._refresh_history_table()
        self._update_schedule_button()

    def _connect_signals(self):
        self.dest_btn.clicked.connect(self._pick_destination)
        self.open_dest_btn.clicked.connect(self._open_backup_folder)
        self.add_btn.clicked.connect(self._add_source)
        self.remove_btn.clicked.connect(self._remove_source)
        self.pause_btn.clicked.connect(self._toggle_source)
        self.backup_btn.clicked.connect(lambda: self._do_backup())
        self.remove_hist_btn.clicked.connect(self._remove_selected_history)
        self.clear_hist_btn.clicked.connect(self._clear_history)
        self.dest_edit.textChanged.connect(self._on_dest_changed)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        self.autostart_cb.stateChanged.connect(self._on_autostart_changed)
        self.autobackup_cb.stateChanged.connect(self._on_autobackup_changed)
        self.floating_btn_cb.stateChanged.connect(self._on_floating_btn_changed)
        self.password_edit.textChanged.connect(self._on_password_changed)
        self.toggle_password_btn.clicked.connect(self._toggle_password_visibility)
        self.schedule_toggle_btn.clicked.connect(self._toggle_scheduler)

    def _toggle_password_visibility(self):
        self._show_password = not self._show_password
        if self._show_password:
            self.password_edit.setEchoMode(QLineEdit.Normal)
            self.toggle_password_btn.setText("隐藏")
        else:
            self.password_edit.setEchoMode(QLineEdit.Password)
            self.toggle_password_btn.setText("显示")
        self._refresh_history_table()

    def _check_activation_file(self):
        if os.path.exists(ACTIVATE_FILE):
            try:
                os.remove(ACTIVATE_FILE)
            except:
                pass
            self.force_activate()
 
    def _on_floating_btn_changed(self, state):
        self.config.show_floating_button = state == Qt.CheckState.Checked.value
        self.config.save()
        self._init_floating_button()

    def _on_password_changed(self, text):
        self.config.backup_password = text
        self.config.save()

    def _show_source_context_menu(self, pos):
        row = self.src_table.rowAt(pos.y())
        if row < 0:
            return
        
        menu = QMenu(self)
        
        item = self.src_table.item(row, 3)
        if item:
            path = item.toolTip() or item.text()
            is_file = os.path.isfile(path) if path else False
            
            restore_action = menu.addAction("恢复备份")
            restore_action.triggered.connect(lambda: self._restore_from_source(row))
            
            menu.addSeparator()
            
            toggle_action = menu.addAction("启用/暂停")
            toggle_action.triggered.connect(lambda: self._toggle_source_single(row))
            
            remove_action = menu.addAction("移除")
            remove_action.triggered.connect(lambda: self._remove_source_single(row))
        
        menu.exec(self.src_table.viewport().mapToGlobal(pos))
    
    def _toggle_source_single(self, row):
        item = self.src_table.item(row, 3)
        if item:
            path = item.toolTip() or item.text()
            self.config.toggle_source(path)
            self._refresh_source_table()
    
    def _remove_source_single(self, row):
        item = self.src_table.item(row, 3)
        if not item:
            return
        
        path = item.toolTip() or item.text()
        
        is_file = os.path.isfile(path) if path else False
        type_text = "文件" if is_file else "文件夹"
        
        msg = QMessageBox(self)
        msg.setWindowTitle("确认移除")
        msg.setText(f"确定要移除这个{type_text}吗？\n\n{path}")
        msg.setIcon(QMessageBox.Question)
        yes_btn = msg.addButton("是", QMessageBox.AcceptRole)
        no_btn = msg.addButton("否", QMessageBox.RejectRole)
        msg.exec()
        reply = msg.clickedButton()
        
        if reply == yes_btn:
            self.config.remove_source(path)
            self._refresh_source_table()
    
    def _on_source_double_clicked(self, row, col):
        if col == 1:
            item = self.src_table.item(row, 3)
            if item:
                path = item.toolTip() or item.text()
                self.config.toggle_source(path)
                self._refresh_source_table()
        elif col == 2:
            item = self.src_table.item(row, 3)
            if item:
                path = item.toolTip() or item.text()
                if path and os.path.exists(path):
                    os.startfile(path)
        elif col == 3:
            item = self.src_table.item(row, 3)
            if item:
                path = item.toolTip() or item.text()
                if path and os.path.exists(path):
                    os.startfile(os.path.dirname(path))

    def _add_source(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("选择备份类型")
        msg.setText("请选择要备份的类型：")
        msg.setIcon(QMessageBox.Question)
        
        file_btn = msg.addButton("选择文件", QMessageBox.AcceptRole)
        folder_btn = msg.addButton("选择文件夹", QMessageBox.RejectRole)
        cancel_btn = msg.addButton("取消", QMessageBox.RejectRole)
        
        msg.exec()
        
        clicked = msg.clickedButton()
        
        if clicked == file_btn:
            path, _ = QFileDialog.getOpenFileName(
                self, 
                "选择待备份文件", 
                "", 
                "所有文件 (*.*);;所有文件 (*)"
            )
        elif clicked == folder_btn:
            path = QFileDialog.getExistingDirectory(self, "选择待备份")
        else:
            return
        
        if not path:
            return
        
        for src in self.config.sources:
            if src.get("path") == path:
                QMessageBox.warning(self, "提示", "该路径已存在")
                return
        
        self.config.add_source(path)
        self._refresh_source_table()

    def _remove_source(self):
        selected_rows = sorted(set(idx.row() for idx in self.src_table.selectedIndexes()), reverse=True)
        if not selected_rows:
            return
        
        if len(selected_rows) > 1:
            msg = f"确定要移除选中的 {len(selected_rows)} 个项目吗？"
        else:
            item = self.src_table.item(selected_rows[0], 3)
            path = item.toolTip() or item.text() if item else ""
            is_file = os.path.isfile(path) if path else False
            type_text = "文件" if is_file else "文件夹"
            msg = f"确定要移除这个{type_text}吗？\n\n{path}"
        
        msgbox = QMessageBox(self)
        msgbox.setWindowTitle("确认移除")
        msgbox.setText(msg)
        msgbox.setIcon(QMessageBox.Question)
        yes_btn = msgbox.addButton("是", QMessageBox.AcceptRole)
        no_btn = msgbox.addButton("否", QMessageBox.RejectRole)
        msgbox.exec()
        reply = msgbox.clickedButton()
        
        if reply != yes_btn:
            return
        
        for row in selected_rows:
            item = self.src_table.item(row, 3)
            if item:
                path = item.toolTip() or item.text()
                self.config.remove_source(path)
        
        self._refresh_source_table()
    
    def _toggle_source(self):
        selected_rows = sorted(set(idx.row() for idx in self.src_table.selectedIndexes()), reverse=True)
        if not selected_rows:
            return
        
        for row in selected_rows:
            item = self.src_table.item(row, 3)
            if item:
                path = item.toolTip() or item.text()
                self.config.toggle_source(path)
        
        self._refresh_source_table()

    def _restore_backup(self, row):
        item = self.hist_table.item(row, 2)
        if not item:
            return
        
        zip_path = item.data(Qt.UserRole)
        if not zip_path or not os.path.exists(zip_path):
            QMessageBox.warning(self, "恢复失败", "备份文件不存在，可能已被删除。")
            return
        
        source_path = item.toolTip() or item.text()
        if not source_path:
            QMessageBox.warning(self, "恢复失败", "无法确定源文件路径。")
            return
        
        msg = QMessageBox(self)
        msg.setWindowTitle("确认恢复")
        msg.setText(f"确定要恢复到以下位置吗？\n\n{source_path}\n\n注意：这将覆盖现有文件。")
        msg.setIcon(QMessageBox.Question)
        yes_btn = msg.addButton("是", QMessageBox.AcceptRole)
        no_btn = msg.addButton("否", QMessageBox.RejectRole)
        msg.exec()
        reply = msg.clickedButton()
        
        if reply != yes_btn:
            return
        
        stored_pwd = self._get_password_for_backup(zip_path)
        password = stored_pwd if stored_pwd else (self.config.backup_password if self.config.backup_password else None)
        success, error = restore_backup(zip_path, os.path.dirname(source_path), password)
        
        if success:
            QMessageBox.information(self, "恢复成功", "备份已成功恢复。")
        else:
            QMessageBox.critical(self, "恢复失败", f"恢复失败：\n{error}")

    def _do_backup(self, source="手动"):
        self.backup_btn.setEnabled(False)
        self.backup_btn.setText("备份中...")
        self._refresh_source_table()

        password = self.config.backup_password if self.config.backup_password else None

        class BackupThread(QThread):
            finished = Signal()

            def run(self_thread):
                results = backup_all(self.config.sources, self.config.destination, password)
                for result in results:
                    self.config.update_source_status(
                        result["path"], 
                        result["success"], 
                        result.get("error", "")
                    )
                    self.logger.add_entry({
                        "path": result["path"],
                        "success": result["success"],
                        "zip_path": result.get("zip_path", ""),
                        "skipped": result.get("skipped", []),
                        "error": result.get("error", ""),
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "encrypted": password is not None,
                        "password": password or "",
                        "source": source
                    })
                self_thread.finished.emit()

        self._backup_thread = BackupThread()
        self._backup_thread.finished.connect(self._after_backup)
        self._backup_thread.start()

    def _after_backup(self):
        self.backup_btn.setEnabled(True)
        self.backup_btn.setText("立即备份")
        self._refresh_source_table()
        self._refresh_history_table()
        self._update_next_backup_time()
        
        # 检查是否有失败的备份，更新悬浮窗颜色
        if self.floating_button:
            has_failure = False
            for src in self.config.sources:
                if src.get("last_backup_success") is False:
                    has_failure = True
                    break
            self.floating_button.set_backup_failed(has_failure)

    def _refresh_source_table(self):
        self.src_table.setRowCount(0)
        sources = self.config.sources
        for src in sources:
            row = self.src_table.rowCount()
            self.src_table.insertRow(row)

            restore_btn = QPushButton("恢复")
            restore_btn.setProperty("row", row)
            restore_btn.clicked.connect(lambda checked, r=row: self._restore_from_source(r))
            self.src_table.setCellWidget(row, 0, restore_btn)

            path = src.get("path", "")
            enabled = src.get("enabled", True)

            status_item = QTableWidgetItem("●")
            if enabled:
                status_item.setForeground(QColor("#4CAF50"))
            else:
                status_item.setForeground(QColor("#F44336"))
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setFlags(Qt.ItemIsEnabled)
            self.src_table.setItem(row, 1, status_item)

            filename = os.path.basename(path.rstrip("\\/")) if path else ""
            filename_item = QTableWidgetItem(filename)
            if not enabled:
                filename_item.setForeground(QBrush(QColor("gray")))
            self.src_table.setItem(row, 2, filename_item)

            path_item = QTableWidgetItem(path)
            path_item.setToolTip(path)
            if not enabled:
                path_item.setForeground(QBrush(QColor("gray")))
            self.src_table.setItem(row, 3, path_item)

            last_time = src.get("last_backup_time", "")
            time_item = QTableWidgetItem(last_time if last_time else "-")
            if not enabled:
                time_item.setForeground(QBrush(QColor("gray")))
            self.src_table.setItem(row, 4, time_item)

            if "last_backup_time" not in src or not last_time:
                status_text = "-"
                tooltip = ""
            elif src.get("last_backup_success", True):
                status_text = "成功"
                tooltip = ""
            else:
                status_text = "失败"
                tooltip = src.get("last_backup_fail_reason", "")

            status_item = QTableWidgetItem(status_text)
            if not enabled:
                status_item.setForeground(QBrush(QColor("gray")))
            if tooltip:
                status_item.setToolTip(tooltip)
            self.src_table.setItem(row, 5, status_item)

    def _refresh_history_table(self):
        self.hist_table.setRowCount(0)
        logs = self.logger.get_all()
        for entry in logs:
            row = self.hist_table.rowCount()
            self.hist_table.insertRow(row)

            restore_btn = QPushButton("恢复")
            restore_btn.setProperty("row", row)
            restore_btn.clicked.connect(lambda checked, r=row: self._restore_backup(r))
            self.hist_table.setCellWidget(row, 0, restore_btn)

            path = entry.get("path", "")
            filename = os.path.basename(path.rstrip("\\/")) if path else ""
            filename_item = QTableWidgetItem(filename)
            self.hist_table.setItem(row, 1, filename_item)

            zip_path = entry.get("zip_path", "")
            path_item = QTableWidgetItem(path)
            path_item.setToolTip(path)
            path_item.setData(Qt.UserRole, zip_path)
            self.hist_table.setItem(row, 2, path_item)

            self.hist_table.setItem(row, 3, QTableWidgetItem(entry.get("time", "")))

            skipped = entry.get("skipped", [])
            encrypted = entry.get("encrypted", False)
            if entry.get("success", False):
                result_text = "成功"
                source = entry.get("source", "手动")
                detail_parts = []
                if encrypted:
                    if self._show_password:
                        pwd = entry.get("password", "")
                        if pwd:
                            detail_parts.append(f"密码: {pwd}")
                        else:
                            detail_parts.append("已加密")
                    else:
                        detail_parts.append("已加密")
                if skipped:
                    detail_parts.append(f"跳过 {len(skipped)} 个锁定文件")
                if source != "手动":
                    detail_parts.append(f"{source}备份")
                detail_text = "，".join(detail_parts) if detail_parts else ""
            else:
                result_text = "失败"
                detail_text = entry.get("error", "")

            self.hist_table.setItem(row, 4, QTableWidgetItem(result_text))

            detail_item = QTableWidgetItem(detail_text)
            if skipped:
                detail_item.setToolTip("\n".join(skipped))
            elif not entry.get("success", False):
                detail_item.setToolTip(detail_text)
            self.hist_table.setItem(row, 5, detail_item)

            if not entry.get("success", False):
                for col in range(self.hist_table.columnCount()):
                    item = self.hist_table.item(row, col)
                    if item:
                        item.setForeground(QBrush(QColor(220, 50, 50)))
                btn_widget = self.hist_table.cellWidget(row, 0)
                if btn_widget:
                    btn_widget.setStyleSheet('color: rgb(220, 50, 50);')

    def _pick_destination(self):
        path = QFileDialog.getExistingDirectory(self, "选择备份存放位置")
        if path:
            self.dest_edit.setText(path)

    def _open_backup_folder(self):
        dest = self.config.destination
        if dest and os.path.isdir(dest):
            os.startfile(dest)

    def _remove_selected_history(self):
        rows = sorted(set(idx.row() for idx in self.hist_table.selectedIndexes()), reverse=True)
        if not rows:
            return

        if len(rows) > 1:
            msg = f"确定要移除选中的 {len(rows)} 条记录吗？"
        else:
            msg = "确定要移除这条记录吗？"

        cb = QCheckBox("同时删除对应的 ZIP 文件")
        msgbox = QMessageBox(self)
        msgbox.setWindowTitle("确认移除")
        msgbox.setText(msg)
        msgbox.setCheckBox(cb)
        msgbox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        if msgbox.exec() != QMessageBox.Yes:
            return

        delete_files = cb.isChecked()
        for row in rows:
            item = self.hist_table.item(row, 2)
            if item:
                zip_path = item.data(Qt.UserRole)
                self.logger.remove_by_index(row)
                if delete_files and zip_path and os.path.exists(zip_path):
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass

            self._refresh_history_table()

    def _clear_history(self):
        self.logger.clear()
        self._refresh_history_table()

    def _on_history_double_clicked(self, row, col):
        if col == 1:
            item = self.hist_table.item(row, 2)
            if item:
                zip_path = item.data(Qt.UserRole)
                if zip_path and os.path.exists(zip_path):
                    os.startfile(zip_path)
        elif col == 2:
            item = self.hist_table.item(row, 2)
            if item:
                zip_path = item.data(Qt.UserRole)
                if zip_path and os.path.exists(zip_path):
                    os.startfile(os.path.dirname(zip_path))

    def _toggle_scheduler(self):
        if self.scheduler.is_running:
            self._stop_scheduler()
        else:
            self._start_scheduler()
        self._update_schedule_button()

    def _toggle_scheduler_from_menu(self):
        self._toggle_scheduler()
        self._update_tray_menu_scheduler_text()
        if self.floating_button:
            self.floating_button.set_scheduler_state(self.scheduler.is_running)

    def _start_scheduler(self):
        if self.config.interval_minutes > 0:
            self.scheduler.start(self.config.interval_minutes, lambda: self._do_backup(source='自动'))
            self.config.scheduler_enabled = True
            self.config.save()
            self._update_next_backup_time()
            if self.floating_button:
                self.floating_button.set_scheduler_state(True)
            self._update_schedule_button()

    def _stop_scheduler(self):
        self.scheduler.stop()
        self.config.scheduler_enabled = False
        self.config.save()
        self.next_backup_label.setText("")
        if self.floating_button:
            self.floating_button.set_scheduler_state(False)
            self._update_schedule_button()

    def _update_next_backup_time(self):
        if self.scheduler.is_running and self.config.interval_minutes > 0:
            self._next_backup_time = datetime.now() + timedelta(minutes=self.config.interval_minutes)
            time_str = self._next_backup_time.strftime("%H:%M:%S")
            self.next_backup_label.setText(f"下次备份: {time_str}")
            if self.floating_button:
                self.floating_button.set_next_backup_time(time_str)
        else:
            self.next_backup_label.setText("")
            if self.floating_button:
                self.floating_button.set_next_backup_time("")

    def _update_schedule_button(self):
        if self.scheduler.is_running:
            self.schedule_toggle_btn.setText("停止定时")
            self._update_next_backup_time()
        else:
            self.schedule_toggle_btn.setText("启动定时")
            self.next_backup_label.setText("")

    def _on_dest_changed(self, text):
        self.config.destination = text
        self.config.save()

    def _on_interval_changed(self, value):
        self.config.interval_minutes = value
        self.config.save()
        if self.scheduler.is_running:
            self.scheduler.update_interval(value)
            self._update_next_backup_time()

    def _on_autostart_changed(self, state):
        enabled = state == Qt.CheckState.Checked.value
        self.config.auto_start_with_system = enabled
        self.config.save()
        self._set_system_autostart(enabled)

    def _on_autobackup_changed(self, state):
        self.config.auto_backup_on_start = state == Qt.CheckState.Checked.value
        self.config.save()

    def _set_system_autostart(self, enable):
        import subprocess
        shortcut_dir = os.path.join(os.environ["APPDATA"],
            "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        shortcut_path = os.path.join(shortcut_dir, "AutoBackup.lnk")

        if enable:
            if getattr(sys, "frozen", False):
                target = sys.executable
                args = "--minimized"
                workdir = os.path.dirname(target)
            else:
                target = sys.executable.replace("python.exe", "pythonw.exe")
                main_script = os.path.abspath(sys.argv[0])
                args = f'"{main_script}" --minimized'
                workdir = os.path.dirname(main_script)

            os.makedirs(shortcut_dir, exist_ok=True)
            ps_cmd = (
                "$ws = New-Object -ComObject WScript.Shell; "
                f"$sc = $ws.CreateShortcut('{shortcut_path}'); "
                f"$sc.TargetPath = '{target}'; "
                f"$sc.Arguments = '{args}'; "
                f"$sc.WorkingDirectory = '{workdir}'; "
                "$sc.Save()"
            )
            subprocess.Popen(["powershell", "-Command", ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
    def _show_tray_msg(self, title, msg):
        if self._tray and self._tray.supportsMessages():
            self._tray.showMessage(
                title, msg, QSystemTrayIcon.MessageIcon.Information, 3000
            )

    def setup_tray(self, app):
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_DriveHDIcon
        ))
        self._tray.setToolTip("AutoBackup v1.1.1")

        self._tray_menu = QMenu()
        show_action = self._tray_menu.addAction("显示主窗口")
        show_action.triggered.connect(self.force_activate)
        backup_action = self._tray_menu.addAction("立即备份")
        backup_action.triggered.connect(lambda: self._do_backup())
        self._tray_menu.addSeparator()
        self._scheduler_menu_action = self._tray_menu.addAction("启动定时")
        self._scheduler_menu_action.triggered.connect(self._toggle_scheduler_from_menu)
        self._tray_menu.addSeparator()
        hide_floating_action = self._tray_menu.addAction("关闭悬浮窗")
        hide_floating_action.triggered.connect(self._close_floating_from_menu)
        self._tray_menu.addSeparator()
        quit_action = self._tray_menu.addAction("退出")
        quit_action.triggered.connect(self._real_quit)

        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()
        self._update_tray_menu_scheduler_text()

    def _update_tray_menu_scheduler_text(self):
        if self._scheduler_menu_action:
            self._scheduler_menu_action.setText("停止定时" if self.scheduler.is_running else "启动定时")

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.force_activate()

    def force_activate(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.ShowWindow(hwnd, 9)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        if self.floating_button:
            self.floating_button.set_backup_failed(False)

    def closeEvent(self, event):
        self._save_geometry()
        if self.floating_button:
            self._save_floating_button_pos()
        if self._tray and not self._quitting:
            self.hide()
            self._show_tray_msg("AutoBackup", "已最小化到系统托盘")
            event.ignore()
        else:
            if self.floating_button:
                self.floating_button.close()
            event.accept()
    def _real_quit(self):
        self._quitting = True
        self.scheduler.stop()
        if self._tray:
            self._tray.hide()
        if self.floating_button:
            self.floating_button.close()
        QApplication.quit()













