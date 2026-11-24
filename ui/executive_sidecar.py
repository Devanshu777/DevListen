"""
DevListen Executive Sidecar UI — Granola & Raycast Inspired Obsidian HUD.
Crafted for modern knowledge workers:
- Screen-Share Hardware Exclusion (WDA_EXCLUDEFROMCAPTURE = 0x11).
- Deep obsidian glassmorphism with subtle hairline border highlights.
- Crisp inline SVG vector icons (Lucide-inspired) for zero-blur rendering.
- Smooth QPropertyAnimation fade-in transitions on cards, tabs, and nudges.
- Breathing live pulse indicator & real-time dual LED audio meters.
- Segmented Capsule Tabs:
    1. Notes (Live dual-stream speech flow with cohesive paragraph cards).
    2. Decisions ([ACTIVE] vs [SUPERSEDED] bi-temporal decision log).
    3. Actions (Action item accountability checklist with 1-click copy).
- Heads-Up Teleprompter Flashcard for Zero-Click Local RAG Inquiries.
"""
import math
import time
import ctypes
import datetime
from typing import Callable, Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QStackedWidget, QSlider, QProgressBar, QApplication,
    QGraphicsOpacityEffect
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QTimer, QPoint, QSettings, QSize,
    QPropertyAnimation, QEasingCurve
)
from PySide6.QtGui import QWheelEvent, QPixmap, QIcon

user32 = ctypes.windll.user32
WDA_EXCLUDEFROMCAPTURE = 0x11


def make_svg_icon(svg_body: str, color: str = "#94A3B8", size: int = 14) -> QIcon:
    """Renders crisp inline SVG vector icons into a QIcon."""
    svg_str = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{svg_body}</svg>'
    )
    pixmap = QPixmap()
    pixmap.loadFromData(svg_str.encode("utf-8"), "SVG")
    return QIcon(pixmap)


def animate_fade_in(widget: QWidget, duration_ms: int = 240):
    """Applies a smooth OutCubic opacity fade-in without clipping child rendering."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    # Remove effect after finish so ClearType / subpixel text stays razor sharp
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._fade_anim = anim
    anim.start()


SVG_NOTES = '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'
SVG_DECISIONS = '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" y1="9" x2="6" y2="21"/>'
SVG_ACTIONS = '<polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>'
SVG_COPY = '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'
SVG_EXPORT = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>'
SVG_MINIMIZE = '<line x1="5" y1="12" x2="19" y2="12"/>'
SVG_CLOSE = '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>'
SVG_SEARCH = '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'


class AudioVUMeter(QWidget):
    """Sleek, minimalist micro audio level indicator for Mic and Call."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Mic channel
        self.mic_lbl = QLabel("MIC", self)
        self.mic_lbl.setStyleSheet("color: #64748B; font-size: 8px; font-weight: 700; letter-spacing: 0.4px;")
        self.mic_bar = QProgressBar(self)
        self.mic_bar.setRange(0, 100)
        self.mic_bar.setValue(0)
        self.mic_bar.setTextVisible(False)
        self.mic_bar.setFixedSize(26, 4)
        self.mic_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 2px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #10B981;
                border-radius: 2px;
            }
        """)

        # Call channel
        self.call_lbl = QLabel("CALL", self)
        self.call_lbl.setStyleSheet("color: #64748B; font-size: 8px; font-weight: 700; letter-spacing: 0.4px;")
        self.call_bar = QProgressBar(self)
        self.call_bar.setRange(0, 100)
        self.call_bar.setValue(0)
        self.call_bar.setTextVisible(False)
        self.call_bar.setFixedSize(26, 4)
        self.call_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 2px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #818CF8;
                border-radius: 2px;
            }
        """)

        layout.addWidget(self.mic_lbl)
        layout.addWidget(self.mic_bar)
        layout.addWidget(self.call_lbl)
        layout.addWidget(self.call_bar)

    def set_levels(self, mic_val: float, call_val: float):
        self.mic_bar.setValue(int(mic_val * 100))
        self.call_bar.setValue(int(call_val * 100))
        self.mic_lbl.setStyleSheet(
            f"color: {'#10B981' if mic_val > 0.08 else '#64748B'}; font-size: 8px; font-weight: 700; letter-spacing: 0.4px;"
        )
        self.call_lbl.setStyleSheet(
            f"color: {'#818CF8' if call_val > 0.08 else '#64748B'}; font-size: 8px; font-weight: 700; letter-spacing: 0.4px;"
        )


class ExecutiveSidecar(QWidget):
    """
    Granola / Raycast Inspired Executive Copilot Sidecar.
    Dockable right-hand assistant with segmented capsule tabs, animations, and screen-share exclusion.
    """
    quit_requested = Signal()
    export_requested = Signal()

    def __init__(self, on_query_callback: Optional[Callable[[str], str]] = None):
        super().__init__()
        self.on_query_callback = on_query_callback
        self.drag_position = QPoint()

        # Window Flags: Frameless, Always on Top, Discrete Tool window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.settings = QSettings("DevListen", "ExecutiveSidecar")
        self.current_opacity = float(self.settings.value("opacity", 0.96))
        self.start_time = datetime.datetime.now()
        self._pulse_phase = 0.0

        # Speaker colors
        self.speaker_colors = {
            "YOU": "#10B981",
            "USER": "#10B981",
            "ATTENDEES": "#818CF8",
            "REMOTE": "#818CF8",
        }

        self._active_stream_cards = {}
        self._init_ui()
        self._setup_stealth_watchdog()
        self._setup_clock()
        self._setup_live_pulse()

    def _setup_stealth_watchdog(self):
        self._enforce_stealth()
        self.stealth_timer = QTimer(self)
        self.stealth_timer.timeout.connect(self._enforce_stealth)
        self.stealth_timer.start(2500)

    def _enforce_stealth(self):
        try:
            hwnd = int(self.winId())
            user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass

    def _setup_live_pulse(self):
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._tick_pulse)
        self.pulse_timer.start(80)

    def _tick_pulse(self):
        self._pulse_phase = (self._pulse_phase + 0.16) % (2 * math.pi)
        alpha = int(135 + 120 * math.sin(self._pulse_phase))
        self.live_dot.setStyleSheet(f"color: rgba(16, 185, 129, {alpha}); font-size: 10px;")

    def set_opacity(self, opacity: float):
        self.current_opacity = max(0.20, min(1.0, opacity))
        self.setWindowOpacity(self.current_opacity)
        if hasattr(self, 'opacity_slider') and not self.opacity_slider.isSliderDown():
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(int(self.current_opacity * 100))
            self.opacity_slider.blockSignals(False)
        self.settings.setValue("opacity", self.current_opacity)

    def _setup_clock(self):
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

    def _update_clock(self):
        delta = datetime.datetime.now() - self.start_time
        tot_sec = int(delta.total_seconds())
        hrs, rem = divmod(tot_sec, 3600)
        mins, secs = divmod(rem, 60)
        if hrs > 0:
            time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
        else:
            time_str = f"{mins:02d}:{secs:02d}"
        self.timer_label.setText(time_str)

    def _init_ui(self):
        self.setFixedSize(444, 728)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 464, max(40, (screen.height() - 760) // 2))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Master Obsidian Frame
        self.card_frame = QFrame(self)
        self.card_frame.setObjectName("card_frame")
        self.card_frame.setStyleSheet("""
            QFrame#card_frame {
                background-color: rgba(11, 13, 18, 0.97);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 16px;
            }
        """)
        card_layout = QVBoxLayout(self.card_frame)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        # 1. Header Bar (Brand, Status, Clock, Audio Meters, Controls)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(7)

        title_box = QHBoxLayout()
        title_box.setSpacing(6)
        self.live_dot = QLabel("●", self)
        self.live_dot.setStyleSheet("color: #10B981; font-size: 10px;")
        self.title_label = QLabel("DevListen", self)
        self.title_label.setStyleSheet("""
            color: #F8FAFC;
            font-weight: 700;
            font-size: 13px;
            font-family: 'Segoe UI Variable Display', 'Inter', -apple-system, sans-serif;
            letter-spacing: -0.3px;
        """)
        title_box.addWidget(self.live_dot)
        title_box.addWidget(self.title_label)
        header_layout.addLayout(title_box)

        # Timer Badge
        self.timer_label = QLabel("00:00", self)
        self.timer_label.setStyleSheet("""
            color: #94A3B8;
            font-size: 10px;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.045);
            border: 1px solid rgba(255, 255, 255, 0.06);
            padding: 2px 7px;
            border-radius: 6px;
        """)
        header_layout.addWidget(self.timer_label)

        # Hardware Tier Pill
        self.tier_pill = QLabel("Edge AI", self)
        self.tier_pill.setStyleSheet("""
            color: #A78BFA;
            font-size: 9px;
            font-weight: 600;
            background: rgba(167, 139, 250, 0.10);
            border: 1px solid rgba(167, 139, 250, 0.22);
            padding: 2px 6px;
            border-radius: 5px;
        """)
        header_layout.addWidget(self.tier_pill)

        header_layout.addStretch()

        # VU Meter
        self.vu_meter = AudioVUMeter(self)
        header_layout.addWidget(self.vu_meter)

        # Opacity Slider
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.current_opacity * 100))
        self.opacity_slider.setFixedWidth(36)
        self.opacity_slider.setToolTip("Transparency: Drag or Ctrl + Wheel")
        self.opacity_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 2px; background: rgba(255, 255, 255, 0.15); border-radius: 1px; }
            QSlider::sub-page:horizontal { background: #818CF8; border-radius: 1px; }
            QSlider::handle:horizontal { background: #FFFFFF; width: 6px; margin: -2px 0; border-radius: 3px; }
        """)
        self.opacity_slider.valueChanged.connect(lambda v: self.set_opacity(v / 100.0))
        header_layout.addWidget(self.opacity_slider)

        # Minimize / Hide Button
        self.btn_minimize = QPushButton(self)
        self.btn_minimize.setIcon(make_svg_icon(SVG_MINIMIZE, "#64748B", 12))
        self.btn_minimize.setIconSize(QSize(12, 12))
        self.btn_minimize.setToolTip("Hide Sidecar (Alt+Shift+Space to toggle)")
        self.btn_minimize.setFixedSize(22, 22)
        self.btn_minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minimize.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 5px; }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); }
        """)
        self.btn_minimize.clicked.connect(lambda: self.setVisible(False))
        header_layout.addWidget(self.btn_minimize)

        # Close / Quit Button
        self.btn_close = QPushButton(self)
        self.btn_close.setIcon(make_svg_icon(SVG_CLOSE, "#64748B", 12))
        self.btn_close.setIconSize(QSize(12, 12))
        self.btn_close.setToolTip("Quit DevListen completely")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 5px; }
            QPushButton:hover { background: rgba(239, 68, 68, 0.22); }
        """)
        self.btn_close.clicked.connect(self.quit_requested.emit)
        header_layout.addWidget(self.btn_close)

        card_layout.addLayout(header_layout)

        # Proactive Zero-Click Flashcard Toast (Hidden by default)
        self.flashcard_frame = QFrame(self)
        self.flashcard_frame.setVisible(False)
        self.flashcard_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.20);
                border-left: 3px solid #F59E0B;
                border-radius: 8px;
                padding: 6px 10px;
            }
        """)
        self.flashcard_layout = QVBoxLayout(self.flashcard_frame)
        self.flashcard_layout.setContentsMargins(8, 6, 8, 6)
        self.flashcard_label = QLabel(self)
        self.flashcard_label.setWordWrap(True)
        self.flashcard_layout.addWidget(self.flashcard_label)
        card_layout.addWidget(self.flashcard_frame)

        # 2. Segmented Capsule Tab Bar (Granola / Linear style with SVG icons)
        tab_capsule = QFrame(self)
        tab_capsule.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 9px;
            }
        """)
        tab_layout = QHBoxLayout(tab_capsule)
        tab_layout.setSpacing(3)
        tab_layout.setContentsMargins(3, 3, 3, 3)

        self.btn_tab_stream = QPushButton(" Notes", tab_capsule)
        self.btn_tab_stream.setIcon(make_svg_icon(SVG_NOTES, "#CBD5E1", 12))
        self.btn_tab_stream.setIconSize(QSize(12, 12))

        self.btn_tab_decisions = QPushButton(" Decisions (0)", tab_capsule)
        self.btn_tab_decisions.setIcon(make_svg_icon(SVG_DECISIONS, "#94A3B8", 12))
        self.btn_tab_decisions.setIconSize(QSize(12, 12))

        self.btn_tab_actions = QPushButton(" Actions (0)", tab_capsule)
        self.btn_tab_actions.setIcon(make_svg_icon(SVG_ACTIONS, "#94A3B8", 12))
        self.btn_tab_actions.setIconSize(QSize(12, 12))

        tab_style = """
            QPushButton {
                background: transparent;
                color: #94A3B8;
                font-size: 11px;
                font-weight: 500;
                border: none;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QPushButton:hover {
                color: #F1F5F9;
                background: rgba(255, 255, 255, 0.04);
            }
            QPushButton:checked {
                background: rgba(255, 255, 255, 0.11);
                color: #FFFFFF;
                font-weight: 600;
            }
        """

        for btn in (self.btn_tab_stream, self.btn_tab_decisions, self.btn_tab_actions):
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(tab_style)

        self.btn_tab_stream.setChecked(True)
        self.btn_tab_stream.clicked.connect(lambda: self._switch_tab(0))
        self.btn_tab_decisions.clicked.connect(lambda: self._switch_tab(1))
        self.btn_tab_actions.clicked.connect(lambda: self._switch_tab(2))

        tab_layout.addWidget(self.btn_tab_stream)
        tab_layout.addWidget(self.btn_tab_decisions)
        tab_layout.addWidget(self.btn_tab_actions)
        card_layout.addWidget(tab_capsule)

        # 3. Stacked View Pages
        self.stack = QStackedWidget(self)

        scroll_style = """
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 4px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.14);
                min-height: 20px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.30);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """

        # Page 0: Live Stream / Notes Scroll
        self.stream_scroll = QScrollArea(self)
        self.stream_scroll.setWidgetResizable(True)
        self.stream_scroll.setStyleSheet(scroll_style)
        self.stream_container = QWidget()
        self.stream_container.setStyleSheet("background: transparent;")
        self.stream_layout = QVBoxLayout(self.stream_container)
        self.stream_layout.setContentsMargins(0, 2, 4, 2)
        self.stream_layout.setSpacing(10)
        self.stream_layout.addStretch()
        self.stream_scroll.setWidget(self.stream_container)
        self.stack.addWidget(self.stream_scroll)

        # Page 1: Decisions Scroll
        self.dec_scroll = QScrollArea(self)
        self.dec_scroll.setWidgetResizable(True)
        self.dec_scroll.setStyleSheet(scroll_style)
        self.dec_container = QWidget()
        self.dec_container.setStyleSheet("background: transparent;")
        self.dec_layout = QVBoxLayout(self.dec_container)
        self.dec_layout.setContentsMargins(0, 2, 4, 2)
        self.dec_layout.setSpacing(8)
        self.dec_empty_lbl = QLabel("No architectural decisions logged yet.\nSpoken decisions are automatically indexed.", self)
        self.dec_empty_lbl.setStyleSheet("color: #64748B; font-size: 11px; margin-top: 36px; line-height: 1.5;")
        self.dec_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dec_layout.addWidget(self.dec_empty_lbl)
        self.dec_layout.addStretch()
        self.dec_scroll.setWidget(self.dec_container)
        self.stack.addWidget(self.dec_scroll)

        # Page 2: Commitments Scroll
        self.act_scroll = QScrollArea(self)
        self.act_scroll.setWidgetResizable(True)
        self.act_scroll.setStyleSheet(scroll_style)
        self.act_container = QWidget()
        self.act_container.setStyleSheet("background: transparent;")
        self.act_layout = QVBoxLayout(self.act_container)
        self.act_layout.setContentsMargins(0, 2, 4, 2)
        self.act_layout.setSpacing(8)
        self.act_empty_lbl = QLabel("No action items detected yet.\nCommitments and tasks appear here automatically.", self)
        self.act_empty_lbl.setStyleSheet("color: #64748B; font-size: 11px; margin-top: 36px; line-height: 1.5;")
        self.act_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.act_layout.addWidget(self.act_empty_lbl)
        self.act_layout.addStretch()
        self.act_scroll.setWidget(self.act_container)
        self.stack.addWidget(self.act_scroll)

        card_layout.addWidget(self.stack)

        # 4. Command Search Bar (Raycast-inspired with icon)
        search_frame = QFrame(self)
        search_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 9px;
            }
            QFrame:focus-within {
                border: 1px solid #818CF8;
                background-color: rgba(255, 255, 255, 0.06);
            }
        """)
        search_box = QHBoxLayout(search_frame)
        search_box.setContentsMargins(10, 0, 10, 0)
        search_box.setSpacing(6)

        search_icon_lbl = QLabel(search_frame)
        search_icon_lbl.setPixmap(make_svg_icon(SVG_SEARCH, "#64748B", 13).pixmap(13, 13))
        search_icon_lbl.setStyleSheet("background: transparent; border: none;")

        self.search_input = QLineEdit(search_frame)
        self.search_input.setPlaceholderText("Ask Copilot or search memory (e.g. 'Redis')... ↵")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #F8FAFC;
                border: none;
                padding: 8px 0px;
                font-size: 11px;
                font-family: 'Segoe UI Variable Text', 'Inter', sans-serif;
            }
        """)
        self.search_input.returnPressed.connect(self._handle_search)
        search_box.addWidget(search_icon_lbl)
        search_box.addWidget(self.search_input)
        card_layout.addWidget(search_frame)

        # 5. Quick Actions Footer
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        btn_pill_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #CBD5E1;
                font-size: 10px;
                font-weight: 600;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 7px;
                padding: 6px 11px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.09);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.14);
            }
        """

        self.btn_copy_actions = QPushButton(" Copy Actions", self)
        self.btn_copy_actions.setIcon(make_svg_icon(SVG_COPY, "#F59E0B", 12))
        self.btn_copy_actions.setIconSize(QSize(12, 12))
        self.btn_copy_actions.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_actions.setStyleSheet(btn_pill_style)
        self.btn_copy_actions.clicked.connect(self._copy_all_commitments)

        self.btn_export = QPushButton(" Export Minutes", self)
        self.btn_export.setIcon(make_svg_icon(SVG_EXPORT, "#818CF8", 12))
        self.btn_export.setIconSize(QSize(12, 12))
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setStyleSheet(btn_pill_style)
        self.btn_export.clicked.connect(self.export_requested.emit)

        footer_layout.addWidget(self.btn_copy_actions)
        footer_layout.addStretch()
        footer_layout.addWidget(self.btn_export)
        card_layout.addLayout(footer_layout)

        main_layout.addWidget(self.card_frame)
        self.set_opacity(self.current_opacity)

        self._decisions_count = 0
        self._commitments_count = 0
        self._commitments_list = []

    def _switch_tab(self, idx: int):
        if self.stack.currentIndex() == idx:
            return
        self.stack.setCurrentIndex(idx)
        self.btn_tab_stream.setChecked(idx == 0)
        self.btn_tab_decisions.setChecked(idx == 1)
        self.btn_tab_actions.setChecked(idx == 2)

        # Update active tab icon colors
        self.btn_tab_stream.setIcon(make_svg_icon(SVG_NOTES, "#FFFFFF" if idx == 0 else "#94A3B8", 12))
        self.btn_tab_decisions.setIcon(make_svg_icon(SVG_DECISIONS, "#FFFFFF" if idx == 1 else "#94A3B8", 12))
        self.btn_tab_actions.setIcon(make_svg_icon(SVG_ACTIONS, "#FFFFFF" if idx == 2 else "#94A3B8", 12))

        current_page = self.stack.currentWidget()
        if current_page:
            animate_fade_in(current_page, duration_ms=170)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            step = 0.05 if delta > 0 else -0.05
            self.set_opacity(self.current_opacity + step)
            event.accept()
        else:
            super().wheelEvent(event)

    # Window Dragging
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def set_tier_badge(self, label: str, tooltip: str = ""):
        """Updates the Hardware Tier indicator in the top header."""
        self.tier_pill.setText(label)
        if tooltip:
            self.tier_pill.setToolTip(tooltip)

    @Slot(float, float)
    def update_audio_levels(self, mic_level: float, call_level: float):
        """Updates the animated audio level meters."""
        self.vu_meter.set_levels(mic_level, call_level)

    @Slot(str, str, bool)
    def add_or_update_stream_card(self, text: str, speaker: str, is_final: bool = False):
        """Adds or updates a sleek, Granola-style speech bubble in the live stream."""
        clean_text = text.strip()
        if not clean_text:
            return

        speaker_up = speaker.upper()
        if speaker_up in ("USER", "YOU"):
            speaker_up = "YOU"
            theme_color = "#10B981"
            bg_color = "rgba(16, 185, 129, 0.045)"
            border_color = "rgba(16, 185, 129, 0.15)"
            hover_border = "rgba(16, 185, 129, 0.35)"
            pill_bg = "rgba(16, 185, 129, 0.15)"
        elif speaker_up in ("REMOTE", "ATTENDEES", "ATTENDEE"):
            speaker_up = "ATTENDEES"
            theme_color = "#818CF8"
            bg_color = "rgba(129, 140, 248, 0.045)"
            border_color = "rgba(129, 140, 248, 0.15)"
            hover_border = "rgba(129, 140, 248, 0.35)"
            pill_bg = "rgba(129, 140, 248, 0.15)"
        else:
            theme_color = self.speaker_colors.get(speaker_up, "#38BDF8")
            bg_color = "rgba(56, 189, 248, 0.045)"
            border_color = "rgba(56, 189, 248, 0.15)"
            hover_border = "rgba(56, 189, 248, 0.35)"
            pill_bg = "rgba(56, 189, 248, 0.15)"

        now_time = datetime.datetime.now().strftime("%I:%M %p")
        now_ts = time.time()

        # Group consecutive paragraphs by the same speaker within 30s into the same speech bubble
        prev_card = getattr(self, '_last_finalized_card', None)
        prev_spk = getattr(self, '_last_finalized_speaker', None)
        prev_ts = getattr(self, '_last_finalized_time', 0.0)

        card = self._active_stream_cards.get(speaker_up)
        if (card is None or card.property("is_final") == True) and prev_spk == speaker_up and (now_ts - prev_ts < 30.0) and prev_card is not None:
            txt_lbl = prev_card.property("txt_lbl")
            if txt_lbl:
                txt_lbl.setText(f"{txt_lbl.text()}\n\n{clean_text}")
                prev_card.setProperty("is_final", is_final)
                self._active_stream_cards[speaker_up] = prev_card
                if is_final:
                    self._last_finalized_time = now_ts
                QTimer.singleShot(50, lambda: self.stream_scroll.verticalScrollBar().setValue(self.stream_scroll.verticalScrollBar().maximum()))
                return

        # Reuse active speaking bubble for speaker if speaking
        if card is None or card.property("is_final") == True:
            card = QFrame(self.stream_container)
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_color};
                    border: 1px solid {border_color};
                    border-left: 3px solid {theme_color};
                    border-radius: 9px;
                    padding: 8px;
                }}
                QFrame:hover {{
                    border: 1px solid {hover_border};
                    border-left: 3px solid {theme_color};
                }}
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(10, 8, 10, 8)
            c_layout.setSpacing(6)

            hdr = QHBoxLayout()
            hdr.setSpacing(6)

            badge = QLabel(f" {speaker_up} ", card)
            badge.setStyleSheet(f"""
                background-color: {pill_bg};
                color: {theme_color};
                font-weight: 700;
                font-size: 9px;
                border: none;
                border-radius: 3px;
                padding: 1px 5px;
                letter-spacing: 0.4px;
            """)
            time_lbl = QLabel(now_time, card)
            time_lbl.setStyleSheet("color: #64748B; font-size: 9px; font-weight: 500; border: none;")

            hdr.addWidget(badge)
            hdr.addWidget(time_lbl)
            hdr.addStretch()
            c_layout.addLayout(hdr)

            txt_lbl = QLabel(clean_text, card)
            txt_lbl.setWordWrap(True)
            txt_lbl.setStyleSheet("""
                color: #F1F5F9;
                font-size: 12px;
                line-height: 1.5;
                border: none;
                font-family: 'Segoe UI Variable Text', 'Inter', -apple-system, sans-serif;
            """)
            c_layout.addWidget(txt_lbl)

            card.setProperty("txt_lbl", txt_lbl)
            card.setProperty("is_final", is_final)
            self._active_stream_cards[speaker_up] = card

            self.stream_layout.insertWidget(self.stream_layout.count() - 1, card)
            animate_fade_in(card, duration_ms=220)
        else:
            txt_lbl = card.property("txt_lbl")
            txt_lbl.setText(clean_text)
            card.setProperty("is_final", is_final)

        if is_final:
            self._last_finalized_card = card
            self._last_finalized_speaker = speaker_up
            self._last_finalized_time = now_ts
            self._active_stream_cards.pop(speaker_up, None)

        QTimer.singleShot(50, lambda: self.stream_scroll.verticalScrollBar().setValue(self.stream_scroll.verticalScrollBar().maximum()))

    @Slot(dict)
    def add_decision_card(self, dec: Dict[str, Any]):
        """Adds an architectural decision card to the Decisions Tab."""
        if self._decisions_count == 0:
            self.dec_empty_lbl.setVisible(False)

        self._decisions_count += 1
        self.btn_tab_decisions.setText(f" Decisions ({self._decisions_count})")

        card = QFrame(self.dec_container)
        status = dec.get("status", "ACTIVE")
        if status == "ACTIVE":
            badge_color = "#10B981"
            badge_bg = "rgba(16, 185, 129, 0.12)"
            border_left = "#10B981"
        else:
            badge_color = "#F43F5E"
            badge_bg = "rgba(244, 63, 94, 0.12)"
            border_left = "#F43F5E"

        card.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(255, 255, 255, 0.025);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-left: 3px solid {border_left};
                border-radius: 9px;
                padding: 8px;
            }}
            QFrame:hover {{
                background-color: rgba(255, 255, 255, 0.045);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-left: 3px solid {border_left};
            }}
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(10, 8, 10, 8)
        c_layout.setSpacing(5)

        hdr = QHBoxLayout()
        st_pill = QLabel(f" {status} ", card)
        st_pill.setStyleSheet(f"background: {badge_bg}; color: {badge_color}; font-weight: 700; font-size: 9px; border: none; border-radius: 3px; padding: 1px 5px;")
        entity_lbl = QLabel(dec.get('entity', 'Decision'), card)
        entity_lbl.setStyleSheet("color: #F8FAFC; font-weight: 600; font-size: 11px; border: none;")

        hdr.addWidget(st_pill)
        hdr.addWidget(entity_lbl)
        hdr.addStretch()
        c_layout.addLayout(hdr)

        body = QLabel(dec.get("summary", ""), card)
        body.setWordWrap(True)
        body.setStyleSheet("color: #CBD5E1; font-size: 11px; line-height: 1.45; border: none;")
        c_layout.addWidget(body)

        meta = QLabel(f"Proposed by {dec.get('proposed_by', 'You')} • Decided by {dec.get('agreed_by', 'Team')}", card)
        meta.setStyleSheet("color: #64748B; font-size: 9px; border: none;")
        c_layout.addWidget(meta)

        self.dec_layout.insertWidget(self.dec_layout.count() - 1, card)
        animate_fade_in(card, duration_ms=250)

    @Slot(dict)
    def add_commitment_card(self, act: Dict[str, Any]):
        """Adds an action item to the Commitments Tab."""
        if self._commitments_count == 0:
            self.act_empty_lbl.setVisible(False)

        self._commitments_count += 1
        self.btn_tab_actions.setText(f" Actions ({self._commitments_count})")
        self._commitments_list.append(act)

        card = QFrame(self.act_container)
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.025);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-left: 3px solid #F59E0B;
                border-radius: 9px;
                padding: 8px;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.045);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-left: 3px solid #F59E0B;
            }
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(10, 8, 10, 8)
        c_layout.setSpacing(5)

        hdr = QHBoxLayout()
        assignee = act.get("assignee", "Team")
        who_pill = QLabel(f" @{assignee} ", card)
        who_pill.setStyleSheet("background: rgba(245, 158, 11, 0.14); color: #F59E0B; font-size: 9px; font-weight: 700; border: none; border-radius: 3px; padding: 1px 5px;")
        hdr.addWidget(who_pill)
        hdr.addStretch()
        c_layout.addLayout(hdr)

        task_lbl = QLabel(f"☐  {act.get('task', '')}", card)
        task_lbl.setWordWrap(True)
        task_lbl.setStyleSheet("color: #F1F5F9; font-size: 11px; line-height: 1.45; border: none;")
        c_layout.addWidget(task_lbl)

        self.act_layout.insertWidget(self.act_layout.count() - 1, card)
        animate_fade_in(card, duration_ms=250)

    @Slot(str, str)
    def show_ambient_nudge(self, html_content: str, source_text: str):
        """Shows the zero-click teleprompter flashcard toast with smooth fade-in."""
        trimmed = source_text.strip()
        if len(trimmed) > 55:
            trimmed = trimmed[:52] + "..."
        msg = f"<b style='color: #F59E0B;'>⚡ ZERO-CLICK LOCAL RAG:</b> \"{trimmed}\"<br>{html_content}"
        self.flashcard_label.setText(msg)
        self.flashcard_frame.setVisible(True)
        animate_fade_in(self.flashcard_frame, duration_ms=260)
        if not self.isVisible():
            self.show()
            self._enforce_stealth()
        QTimer.singleShot(12000, lambda: self.flashcard_frame.setVisible(False))

    def _handle_search(self):
        text = self.search_input.text().strip()
        if not text or not self.on_query_callback:
            return
        result_html = self.on_query_callback(text)
        self.show_ambient_nudge(result_html, f"Query: {text}")
        self.search_input.clear()

    def _copy_all_commitments(self):
        if not self._commitments_list:
            self.btn_copy_actions.setText(" No actions yet")
            QTimer.singleShot(1800, lambda: self.btn_copy_actions.setText(" Copy Actions"))
            return
        lines = ["### ⚡ DevListen Action Items & Commitments:"]
        for c in self._commitments_list:
            lines.append(f"- [ ] **{c['assignee']}**: {c['task']}")
        md = "\n".join(lines)
        QApplication.clipboard().setText(md)
        self.btn_copy_actions.setText(" ✓ Copied!")
        QTimer.singleShot(2200, lambda: self.btn_copy_actions.setText(" Copy Actions"))
