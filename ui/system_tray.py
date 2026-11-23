"""
DevListen Windows System Tray Integration.
Provides a discreet icon in the Windows notification area with quick controls:
- Toggle HUD (Alt+Shift+L / Alt+Shift+Space)
- Mini-Pill Mode (Alt+Shift+M)
- Transparency controls (100%, 75%, 50%, 25%)
- Export Meeting Summary (Alt+Shift+E)
- Quit (Alt+Shift+Q)
"""
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PySide6.QtCore import Qt, Signal, QObject

def create_tray_icon() -> QIcon:
    """Generates high-resolution sleek dark-mode system tray icon programmatically."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Background circle
    painter.setBrush(QColor('#1E1E2E'))
    painter.setPen(QColor('#00E676'))
    painter.drawEllipse(4, 4, 56, 56)
    # Audio waves
    painter.setPen(QColor('#00E676'))
    painter.setBrush(QColor('#00E676'))
    painter.drawRoundedRect(28, 16, 8, 32, 4, 4)
    painter.drawRoundedRect(16, 24, 6, 16, 3, 3)
    painter.drawRoundedRect(42, 24, 6, 16, 3, 3)
    painter.end()
    return QIcon(pixmap)

class DevListenSystemTray(QObject):
    toggle_hud_requested = Signal()
    toggle_pill_requested = Signal()
    opacity_changed = Signal(float)
    export_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray_icon = QSystemTrayIcon(parent)
        self.tray_icon.setIcon(create_tray_icon())
        self.tray_icon.setToolTip("DevListen • Screen-Share Protected (Local AI)")

        self._build_menu()
        self.tray_icon.activated.connect(self._on_activated)
        self.tray_icon.show()

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #1A1C23;
                color: #ECEFF1;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 4px;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3F51B5;
                color: #FFFFFF;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.12);
                margin: 4px 6px;
            }
        """)

        # Main Actions
        act_toggle = menu.addAction("👁️ Toggle HUD (Alt+Shift+L)")
        act_toggle.triggered.connect(self.toggle_hud_requested.emit)

        act_pill = menu.addAction("💊 Toggle Mini-Pill (Alt+Shift+M)")
        act_pill.triggered.connect(self.toggle_pill_requested.emit)

        # Transparency Submenu
        trans_menu = menu.addMenu("👻 Transparency")
        for label, val in [("100% Solid", 1.0), ("75% Subtle", 0.75), ("50% Translucent", 0.50), ("25% Ghost", 0.25)]:
            act_t = trans_menu.addAction(label)
            act_t.triggered.connect(lambda checked=False, v=val: self.opacity_changed.emit(v))

        menu.addSeparator()

        act_export = menu.addAction("📄 Export Meeting Minutes (Alt+Shift+E)")
        act_export.triggered.connect(self.export_requested.emit)

        menu.addSeparator()

        act_quit = menu.addAction("✕ Quit DevListen (Alt+Shift+Q)")
        act_quit.triggered.connect(self.quit_requested.emit)

        self.tray_icon.setContextMenu(menu)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_hud_requested.emit()

    def show_message(self, title: str, message: str):
        """Displays a clean Windows notification popup."""
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
