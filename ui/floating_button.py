"""AutoBackup v1.0.2 悬浮按钮"""
from PySide6.QtWidgets import QWidget, QApplication, QMenu
from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QCursor


class FloatingButton(QWidget):
    def __init__(self, on_click_callback=None, on_toggle_scheduler=None, on_close=None, parent=None):
        super().__init__(parent)
        self.on_click_callback = on_click_callback
        self.on_toggle_scheduler = on_toggle_scheduler
        self.on_close = on_close
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        self.radius = 25
        self.setFixedSize(self.radius * 2, self.radius * 2)
        
        self._is_hovered = False
        self._is_snapped = False
        self._snap_edge = None
        self._offset = QPoint(0, 0)
        self._is_dragging = False
        self._scheduler_enabled = False
        self._next_backup_time = ''
        self._backup_failed = False
        
        self._animation = QPropertyAnimation(self, b"geometry")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)
        
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip("左键点击执行备份\n左键长按拖动\n右键打开菜单")

    def set_scheduler_state(self, enabled):
        self._scheduler_enabled = enabled
        self.update()

    def set_next_backup_time(self, time_str):
        """设置下次备份时间，用于 tooltip 显示"""
        self._next_backup_time = time_str
        self._update_tooltip()

    def set_backup_failed(self, failed):
        self._backup_failed = failed
        self.update()

    def _update_tooltip(self):
        tip = "左键点击执行备份\n左键长按拖动\n右键打开菜单"
        if self._next_backup_time:
            tip += f"\n\n下次备份: {self._next_backup_time}"
        self.setToolTip(tip)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self._is_snapped:
            if self._backup_failed:
                color = QColor(244, 67, 54, 200)
            elif self._scheduler_enabled:
                color = QColor(76, 175, 80, 200)
            else:
                color = QColor(100, 100, 255, 200)
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.NoPen))
            
            if self._snap_edge == 'left':
                painter.drawEllipse(-self.radius, 0, self.radius * 2, self.radius * 2)
            elif self._snap_edge == 'right':
                painter.drawEllipse(0, 0, self.radius * 2, self.radius * 2)
            elif self._snap_edge == 'top':
                painter.drawEllipse(0, -self.radius, self.radius * 2, self.radius * 2)
            elif self._snap_edge == 'bottom':
                painter.drawEllipse(0, 0, self.radius * 2, self.radius * 2)
        else:
            if self._backup_failed:
                color = QColor(211, 47, 47, 220)
                if self._is_hovered:
                    color = QColor(244, 67, 54, 240)
            elif self._scheduler_enabled:
                color = QColor(56, 142, 60, 220)
                if self._is_hovered:
                    color = QColor(76, 175, 80, 240)
            else:
                color = QColor(50, 150, 255, 220)
                if self._is_hovered:
                    color = QColor(80, 180, 255, 240)
                
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.NoPen))
            painter.drawEllipse(0, 0, self.radius * 2, self.radius * 2)
            
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            center_x = self.radius
            center_y = self.radius
            
            painter.drawLine(center_x, center_y + 8, center_x, center_y - 8)
            painter.drawLine(center_x - 5, center_y - 3, center_x, center_y - 8)
            painter.drawLine(center_x + 5, center_y - 3, center_x, center_y - 8)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._offset = event.globalPosition().toPoint() - self.pos()
            self._is_dragging = False
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def _show_context_menu(self, pos):
        menu = QMenu()
        
        backup_action = menu.addAction("立即备份")
        backup_action.triggered.connect(self.on_click_callback)
        
        menu.addSeparator()
        
        scheduler_text = "停止定时" if self._scheduler_enabled else "启动定时"
        scheduler_action = menu.addAction(scheduler_text)
        if self.on_toggle_scheduler:
            scheduler_action.triggered.connect(self.on_toggle_scheduler)
        
        menu.addSeparator()
        
        close_action = menu.addAction("关闭悬浮窗")
        if self.on_close:
            close_action.triggered.connect(self.on_close)
        
        menu.addSeparator()
        
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(QApplication.quit)
        
        menu.exec(pos)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if not self._is_dragging:
                diff = event.globalPosition().toPoint() - (self.pos() + self._offset)
                if abs(diff.x()) > 5 or abs(diff.y()) > 5:
                    self._is_dragging = True
                    self.setCursor(QCursor(Qt.SizeAllCursor))
            
            if self._is_dragging:
                self.move(event.globalPosition().toPoint() - self._offset)
                self._is_snapped = False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._is_dragging:
                if self.on_click_callback:
                    self.on_click_callback()
            else:
                self._check_edge_snap()
                self.setCursor(QCursor(Qt.PointingHandCursor))
            self._is_dragging = False

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        if self._is_snapped:
            self._unsnap()

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        self._check_edge_snap()

    def _check_edge_snap(self):
        screen = QApplication.primaryScreen().geometry()
        pos = self.pos()
        w = self.width()
        h = self.height()
        
        threshold = 10
        margin = 10
        
        if pos.x() <= screen.x() + threshold:
            self._snap('left', screen, margin)
        elif pos.x() + w >= screen.width() - threshold:
            self._snap('right', screen, margin)
        elif pos.y() <= screen.y() + threshold:
            self._snap('top', screen, margin)
        elif pos.y() + h >= screen.height() - threshold:
            self._snap('bottom', screen, margin)

    def _snap(self, edge, screen, margin):
        self._is_snapped = True
        self._snap_edge = edge
        
        if edge == 'left':
            new_pos = QPoint(screen.x() + margin, self.y())
            new_size = QPoint(self.radius, self.radius * 2)
        elif edge == 'right':
            new_pos = QPoint(screen.width() - margin - self.radius, self.y())
            new_size = QPoint(self.radius, self.radius * 2)
        elif edge == 'top':
            new_pos = QPoint(self.x(), screen.y() + margin)
            new_size = QPoint(self.radius * 2, self.radius)
        elif edge == 'bottom':
            new_pos = QPoint(self.x(), screen.height() - margin - self.radius)
            new_size = QPoint(self.radius * 2, self.radius)
            
        self._start_animation(new_pos, new_size)

    def _unsnap(self):
        self._is_snapped = False
        self._snap_edge = None
        self._start_animation(self.pos(), QPoint(self.radius * 2, self.radius * 2))

    def _start_animation(self, target_pos, target_size):
        self._animation.stop()
        start_geo = self.geometry()
        end_geo = self.geometry()
        end_geo.setTopLeft(target_pos)
        end_geo.setWidth(target_size.x())
        end_geo.setHeight(target_size.y())
        
        self._animation.setStartValue(start_geo)
        self._animation.setEndValue(end_geo)
        self._animation.start()
