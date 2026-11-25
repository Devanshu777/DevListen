"""
DevListen v1.0 — Native Desktop Studio UI (Linear / Vercel Obsidian Aesthetic).
Features:
- Frameless draggable desktop window (#09090B canvas, #111115 cards, 1px hairline borders).
- 220px Persistent Left Sidebar (Live Capture, Session Library, AI Workspace, Decisions & RAG, Preferences).
- Live Cyan-to-Purple QPainter Audio Waveform Visualizer driven by real-time Mic + Loopback levels.
- Center Scrolling Diarization Timeline with [YOU] (Cyan) & [ATTENDEES] (Purple) speaker cards.
- Right-hand AI Insights & Raw JSON Inspector with live syntax-highlighted JSON payload.
- 24px Bottom Telemetry Status Bar & optional WDA_EXCLUDEFROMCAPTURE Screen-Share Stealth.
"""
import os
import json
import math
import time
import ctypes
import random
import datetime
from typing import Callable, Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QStackedWidget, QSlider, QComboBox, QTextEdit,
    QApplication, QGraphicsOpacityEffect, QSizePolicy, QFileDialog
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QTimer, QPoint, QSettings, QSize,
    QPropertyAnimation, QEasingCurve
)
from PySide6.QtGui import (
    QWheelEvent, QPixmap, QIcon, QPainter, QLinearGradient, QColor, QBrush
)

user32 = ctypes.windll.user32
WDA_EXCLUDEFROMCAPTURE = 0x11
WDA_NONE = 0x0


def make_svg_icon(svg_body: str, color: str = "#94A3B8", size: int = 15) -> QIcon:
    svg_str = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{svg_body}</svg>'
    )
    pixmap = QPixmap()
    pixmap.loadFromData(svg_str.encode("utf-8"), "SVG")
    return QIcon(pixmap)


def animate_fade_in(widget: QWidget, duration_ms: int = 220):
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._fade_anim = anim
    anim.start()


SVG_WAVE = '<path d="M2 12h2"/><path d="M6 8v8"/><path d="M10 5v14"/><path d="M14 9v6"/><path d="M18 4v16"/><path d="M22 12h-2"/>'
SVG_RADIO = '<circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/>'
SVG_FOLDER = '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
SVG_CPU = '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>'
SVG_BRANCH = '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" y1="9" x2="6" y2="21"/>'
SVG_SLIDERS = '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>'
SVG_EXPORT = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'
SVG_CODE = '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>'
SVG_SEARCH = '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'
SVG_SHIELD = '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'


class WaveformVisualizer(QWidget):
    """Real-time Cyan-to-Purple gradient vertical bar audio waveform visualizer."""
    def __init__(self, parent=None, num_bars: int = 68):
        super().__init__(parent)
        self.num_bars = num_bars
        self.bars = [0.12 + 0.08 * math.sin(i * 0.4) for i in range(num_bars)]
        self.target_energy = 0.08
        self.phase = 0.0
        self.setFixedHeight(64)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(45)

    def set_energy(self, mic_level: float, call_level: float):
        self.target_energy = max(0.08, min(1.0, max(mic_level, call_level) * 1.25))

    def _tick(self):
        self.phase += 0.28
        for i in range(self.num_bars):
            env = math.sin(math.pi * i / (self.num_bars - 1))
            wave = 0.5 + 0.5 * math.sin(self.phase + i * 0.37)
            jitter = random.uniform(0.85, 1.15)
            target = max(0.08, min(0.96, (0.10 + self.target_energy * 0.85 * wave) * (0.35 + 0.65 * env) * jitter))
            self.bars[i] = self.bars[i] * 0.55 + target * 0.45
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor("#06B6D4"))   # Cyan
        grad.setColorAt(0.55, QColor("#6366F1"))  # Indigo
        grad.setColorAt(1.0, QColor("#A855F7"))   # Purple

        step = w / self.num_bars
        bar_w = max(2.0, step * 0.52)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))

        for i, val in enumerate(self.bars):
            bh = max(4.0, val * (h - 8))
            x = i * step + (step - bar_w) / 2.0
            y = (h - bh) / 2.0
            painter.drawRoundedRect(x, y, bar_w, bh, bar_w / 2.0, bar_w / 2.0)


class DevListenStudio(QWidget):
    """
    DevListen v1.0 — Full Multi-View Desktop Studio Shell.
    Drop-in compatible with ExecutiveSidecar signals/slots.
    """
    quit_requested = Signal()
    export_requested = Signal()

    def __init__(self, on_query_callback: Optional[Callable[[str], str]] = None):
        super().__init__()
        self.on_query_callback = on_query_callback
        self.drag_position = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.settings = QSettings("DevListen", "StudioDesktop")
        self.current_opacity = float(self.settings.value("opacity", 0.98))
        self.stealth_enabled = True
        self.start_time = datetime.datetime.now()

        self._active_stream_cards: Dict[str, QFrame] = {}
        self._decisions_list: List[Dict[str, Any]] = []
        self._commitments_list: List[Dict[str, Any]] = []
        self._transcript_log: List[Dict[str, Any]] = []
        self._show_raw_json = True

        self._init_ui()
        self._apply_stealth(True)
        self._setup_clock()

    def _apply_stealth(self, enabled: bool):
        self.stealth_enabled = enabled
        try:
            hwnd = int(self.winId())
            user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE if enabled else WDA_NONE)
        except Exception:
            pass
        if hasattr(self, "stealth_pill"):
            if enabled:
                self.stealth_pill.setText("● Screen-Share Invisible")
                self.stealth_pill.setStyleSheet(
                    "background: rgba(6, 182, 212, 0.12); color: #22D3EE; border: 1px solid rgba(6, 182, 212, 0.28);"
                    "border-radius: 6px; padding: 3px 10px; font-size: 10.5px; font-weight: 600;"
                )
            else:
                self.stealth_pill.setText("○ Recordable Mode")
                self.stealth_pill.setStyleSheet(
                    "background: rgba(245, 158, 11, 0.12); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.28);"
                    "border-radius: 6px; padding: 3px 10px; font-size: 10.5px; font-weight: 600;"
                )

    def toggle_stealth(self):
        self._apply_stealth(not self.stealth_enabled)

    def set_opacity(self, opacity: float):
        self.current_opacity = max(0.30, min(1.0, opacity))
        self.setWindowOpacity(self.current_opacity)
        self.settings.setValue("opacity", self.current_opacity)

    def _setup_clock(self):
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

    def _update_clock(self):
        delta = datetime.datetime.now() - self.start_time
        tot = int(delta.total_seconds())
        mins, secs = divmod(tot, 60)
        hrs, mins = divmod(mins, 60)
        txt = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}"
        self.wave_timer_lbl.setText(f"{txt}  /  LIVE")

    def _init_ui(self):
        self.resize(1180, 740)
        screen = QApplication.primaryScreen().geometry()
        self.move(max(20, (screen.width() - 1180) // 2), max(20, (screen.height() - 740) // 2))

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # Outer Obsidian Window Shell
        self.shell = QFrame(self)
        self.shell.setObjectName("shell")
        self.shell.setStyleSheet("""
            QFrame#shell {
                background-color: #09090B;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 14px;
            }
        """)
        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        # Body = Left Sidebar (220px) + Main Content Area
        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)

        body_row.addWidget(self._build_sidebar())
        body_row.addWidget(self._build_main_area(), 1)
        shell_layout.addLayout(body_row, 1)

        # Bottom 24px Desktop Status Bar
        shell_layout.addWidget(self._build_status_bar())

        root.addWidget(self.shell)
        self.set_opacity(self.current_opacity)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame(self)
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #0C0C10;
                border-right: 1px solid rgba(255, 255, 255, 0.07);
                border-top-left-radius: 14px;
            }
        """)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)

        # Window Controls (Red / Amber / Green dots)
        win_row = QHBoxLayout()
        win_row.setSpacing(7)
        for color, tip, fn in (
            ("#EF4444", "Quit DevListen", self.quit_requested.emit),
            ("#F59E0B", "Minimize", self.showMinimized),
            ("#10B981", "Hide to Tray", lambda: self.setVisible(False)),
        ):
            dot = QPushButton(sidebar)
            dot.setFixedSize(12, 12)
            dot.setToolTip(tip)
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.setStyleSheet(f"QPushButton {{ background: {color}; border-radius: 6px; border: none; }} QPushButton:hover {{ opacity: 0.85; }}")
            dot.clicked.connect(fn)
            win_row.addWidget(dot)
        win_row.addStretch()
        lay.addLayout(win_row)

        lay.addSpacing(8)

        # Brand Row
        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        icon_lbl = QLabel(sidebar)
        icon_lbl.setPixmap(make_svg_icon(SVG_WAVE, "#06B6D4", 20).pixmap(20, 20))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        brand_lbl = QLabel("DevListen", sidebar)
        brand_lbl.setStyleSheet("color: #FAFAFA; font-size: 16px; font-weight: 800; letter-spacing: -0.4px; border: none;")
        ver_pill = QLabel("v1.0", sidebar)
        ver_pill.setStyleSheet("background: rgba(255,255,255,0.06); color: #A1A1AA; font-size: 9.5px; font-weight: 600; padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);")
        brand_row.addWidget(icon_lbl)
        brand_row.addWidget(brand_lbl)
        brand_row.addWidget(ver_pill)
        brand_row.addStretch()
        lay.addLayout(brand_row)

        lay.addSpacing(12)

        # Navigation Buttons
        self.nav_buttons: List[QPushButton] = []
        nav_items = [
            ("Live Capture", SVG_RADIO, 0),
            ("Session Library", SVG_FOLDER, 1),
            ("AI Workspace", SVG_CPU, 2),
            ("Decisions & RAG", SVG_BRANCH, 3),
            ("Preferences", SVG_SLIDERS, 4),
        ]

        nav_style = """
            QPushButton {
                text-align: left;
                padding: 9px 12px;
                border-radius: 8px;
                color: #A1A1AA;
                font-size: 12.5px;
                font-weight: 500;
                background: transparent;
                border: 1px solid transparent;
            }
            QPushButton:hover {
                color: #F4F4F5;
                background: rgba(255, 255, 255, 0.04);
            }
            QPushButton:checked {
                color: #FFFFFF;
                font-weight: 600;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(6,182,212,0.16), stop:1 rgba(99,102,241,0.08));
                border: 1px solid rgba(6, 182, 212, 0.30);
            }
        """

        for label, svg, idx in nav_items:
            btn = QPushButton(f"  {label}", sidebar)
            btn.setIcon(make_svg_icon(svg, "#06B6D4" if idx == 0 else "#71717A", 15))
            btn.setIconSize(QSize(15, 15))
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(nav_style)
            btn.clicked.connect(lambda checked=False, i=idx: self._switch_page(i))
            self.nav_buttons.append(btn)
            lay.addWidget(btn)

        lay.addStretch()

        # Bottom Privacy Vault Badge
        vault_card = QFrame(sidebar)
        vault_card.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 8px;
                padding: 6px;
            }
        """)
        vlay = QHBoxLayout(vault_card)
        vlay.setContentsMargins(8, 6, 8, 6)
        v_icon = QLabel(vault_card)
        v_icon.setPixmap(make_svg_icon(SVG_SHIELD, "#10B981", 14).pixmap(14, 14))
        v_icon.setStyleSheet("border: none;")
        v_txt = QLabel("Zero-Trust Vault\nDPAPI + AES-256", vault_card)
        v_txt.setStyleSheet("color: #A1A1AA; font-size: 10px; border: none;")
        vlay.addWidget(v_icon)
        vlay.addWidget(v_txt)
        lay.addWidget(vault_card)

        return sidebar

    def _build_main_area(self) -> QWidget:
        container = QWidget(self)
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Top 46px Titlebar
        topbar = QFrame(container)
        topbar.setFixedHeight(46)
        topbar.setStyleSheet("QFrame { background: #09090B; border-bottom: 1px solid rgba(255,255,255,0.07); border-top-right-radius: 14px; }")
        tlay = QHBoxLayout(topbar)
        tlay.setContentsMargins(18, 0, 18, 0)
        tlay.setSpacing(10)

        self.page_title_lbl = QLabel("Live Capture & Diarization", topbar)
        self.page_title_lbl.setStyleSheet("color: #FAFAFA; font-size: 13.5px; font-weight: 700; border: none;")
        tlay.addWidget(self.page_title_lbl)
        tlay.addStretch()

        dev_pill = QLabel("🎙️ System Audio + Mic (16kHz)", topbar)
        dev_pill.setStyleSheet(
            "background: #111115; color: #D4D4D8; border: 1px solid rgba(255,255,255,0.08);"
            "border-radius: 6px; padding: 3px 10px; font-size: 10.5px;"
        )
        tlay.addWidget(dev_pill)

        self.tier_pill = QLabel("⚡ INT8 CPU • Ready", topbar)
        self.tier_pill.setStyleSheet(
            "background: rgba(99, 102, 241, 0.14); color: #A5B4FC; border: 1px solid rgba(99, 102, 241, 0.30);"
            "border-radius: 6px; padding: 3px 10px; font-size: 10.5px; font-weight: 600;"
        )
        tlay.addWidget(self.tier_pill)

        self.stealth_pill = QPushButton("● Screen-Share Invisible", topbar)
        self.stealth_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stealth_pill.setToolTip("Click to toggle Win32 WDA_EXCLUDEFROMCAPTURE")
        self.stealth_pill.clicked.connect(self.toggle_stealth)
        tlay.addWidget(self.stealth_pill)

        lay.addWidget(topbar)

        # Stacked Pages
        self.pages = QStackedWidget(container)
        self.pages.addWidget(self._build_live_capture_page())
        self.pages.addWidget(self._build_session_library_page())
        self.pages.addWidget(self._build_ai_workspace_page())
        self.pages.addWidget(self._build_decisions_rag_page())
        self.pages.addWidget(self._build_preferences_page())

        lay.addWidget(self.pages, 1)
        return container

    def _build_live_capture_page(self) -> QWidget:
        page = QWidget(self)
        outer = QHBoxLayout(page)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(14)

        # Center Column: Waveform + Diagnostics + Timeline
        center_col = QVBoxLayout()
        center_col.setSpacing(12)

        # Waveform Card
        wave_card = QFrame(page)
        wave_card.setStyleSheet("""
            QFrame {
                background-color: #111115;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)
        wlay = QVBoxLayout(wave_card)
        wlay.setContentsMargins(14, 10, 14, 10)
        wlay.setSpacing(6)

        self.waveform = WaveformVisualizer(wave_card)
        wlay.addWidget(self.waveform)

        meta_row = QHBoxLayout()
        self.wav_name_lbl = QLabel("Live_Meeting_Active.wav", wave_card)
        self.wav_name_lbl.setStyleSheet("color: #A1A1AA; font-family: 'Consolas', monospace; font-size: 11px; border: none;")
        self.wave_timer_lbl = QLabel("00:00  /  LIVE", wave_card)
        self.wave_timer_lbl.setStyleSheet("color: #E4E4E7; font-family: 'Consolas', monospace; font-size: 11px; border: none;")
        live_dot = QLabel("● REC", wave_card)
        live_dot.setStyleSheet("color: #EF4444; font-size: 10px; font-weight: 700; border: none;")
        meta_row.addWidget(self.wav_name_lbl)
        meta_row.addStretch()
        meta_row.addWidget(self.wave_timer_lbl)
        meta_row.addSpacing(8)
        meta_row.addWidget(live_dot)
        wlay.addLayout(meta_row)
        center_col.addWidget(wave_card)

        # Diagnostics Pill Strip
        diag_row = QHBoxLayout()
        diag_pill = QFrame(page)
        diag_pill.setStyleSheet("QFrame { background: #111115; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; }")
        dlay = QHBoxLayout(diag_pill)
        dlay.setContentsMargins(12, 5, 12, 5)
        dlay.setSpacing(14)
        for txt, col in (
            ("● Confidence: 97.4%", "#10B981"),
            ("⏱ Latency: <190ms", "#22D3EE"),
            ("🔊 16kHz Mono PCM", "#A1A1AA"),
        ):
            lbl = QLabel(txt, diag_pill)
            lbl.setStyleSheet(f"color: {col}; font-family: 'Consolas', monospace; font-size: 10.5px; border: none;")
            dlay.addWidget(lbl)
        diag_row.addStretch()
        diag_row.addWidget(diag_pill)
        diag_row.addStretch()
        center_col.addLayout(diag_row)

        # Proactive Zero-Click RAG Toast (Hidden until triggered)
        self.nudge_frame = QFrame(page)
        self.nudge_frame.setVisible(False)
        self.nudge_frame.setStyleSheet("""
            QFrame {
                background: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.25);
                border-left: 3px solid #F59E0B;
                border-radius: 9px;
                padding: 8px 10px;
            }
        """)
        nlay = QVBoxLayout(self.nudge_frame)
        nlay.setContentsMargins(6, 4, 6, 4)
        self.nudge_label = QLabel(self.nudge_frame)
        self.nudge_label.setWordWrap(True)
        self.nudge_label.setStyleSheet("border: none; background: transparent;")
        nlay.addWidget(self.nudge_label)
        center_col.addWidget(self.nudge_frame)

        # Scrolling Speaker Timeline
        self.stream_scroll = QScrollArea(page)
        self.stream_scroll.setWidgetResizable(True)
        self.stream_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 5px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,0.14); border-radius: 2px; }
        """)
        self.stream_container = QWidget()
        self.stream_container.setStyleSheet("background: transparent;")
        self.stream_layout = QVBoxLayout(self.stream_container)
        self.stream_layout.setContentsMargins(0, 4, 6, 4)
        self.stream_layout.setSpacing(10)
        self.stream_layout.addStretch()
        self.stream_scroll.setWidget(self.stream_container)
        center_col.addWidget(self.stream_scroll, 1)

        outer.addLayout(center_col, 1)

        # Right Column: AI Insights & Raw JSON Inspector (330px)
        right_panel = QFrame(page)
        right_panel.setFixedWidth(330)
        right_panel.setStyleSheet("""
            QFrame {
                background-color: #111115;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)
        rlay = QVBoxLayout(right_panel)
        rlay.setContentsMargins(14, 14, 14, 14)
        rlay.setSpacing(10)

        r_hdr = QLabel("AI Insights & JSON", right_panel)
        r_hdr.setStyleSheet("color: #FAFAFA; font-size: 13px; font-weight: 700; border: none;")
        rlay.addWidget(r_hdr)

        # Live Summary Card
        self.insights_lbl = QLabel(
            "<span style='color:#06B6D4;'>●</span> <b>Summary:</b> Listening to live session...<br><br>"
            "<span style='color:#6366F1;'>●</span> <b>Decisions:</b> 0 logged<br><br>"
            "<span style='color:#F59E0B;'>●</span> <b>Action Items:</b> 0 extracted",
            right_panel
        )
        self.insights_lbl.setWordWrap(True)
        self.insights_lbl.setStyleSheet(
            "background: rgba(255,255,255,0.025); border: 1px solid rgba(255,255,255,0.06);"
            "border-radius: 8px; padding: 10px; color: #D4D4D8; font-size: 11.5px; line-height: 1.45;"
        )
        rlay.addWidget(self.insights_lbl)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_style = """
            QPushButton {
                background: rgba(255,255,255,0.04); color: #D4D4D8;
                border: 1px solid rgba(255,255,255,0.09); border-radius: 7px;
                padding: 6px 10px; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background: rgba(255,255,255,0.09); color: #FFFFFF; }
        """
        self.btn_toggle_json = QPushButton(" Raw JSON", right_panel)
        self.btn_toggle_json.setIcon(make_svg_icon(SVG_CODE, "#06B6D4", 13))
        self.btn_toggle_json.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_json.setStyleSheet(btn_style)
        self.btn_toggle_json.clicked.connect(self._toggle_json_box)

        self.btn_export_md = QPushButton(" Export MD", right_panel)
        self.btn_export_md.setIcon(make_svg_icon(SVG_EXPORT, "#A855F7", 13))
        self.btn_export_md.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_md.setStyleSheet(btn_style)
        self.btn_export_md.clicked.connect(self.export_requested.emit)

        btn_row.addWidget(self.btn_toggle_json)
        btn_row.addWidget(self.btn_export_md)
        rlay.addLayout(btn_row)

        # Embedded JSON Code Inspector
        self.json_box = QTextEdit(right_panel)
        self.json_box.setReadOnly(True)
        self.json_box.setStyleSheet("""
            QTextEdit {
                background-color: #09090D;
                color: #22D3EE;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 8px;
                font-family: 'Consolas', 'JetBrains Mono', monospace;
                font-size: 10.5px;
            }
        """)
        self.json_box.setPlainText('{\n  "status": "listening",\n  "engine": "faster-whisper-int8",\n  "rag_index": "bge-small-en-v1.5"\n}')
        rlay.addWidget(self.json_box, 1)

        # Quick Semantic Search Input
        self.search_input = QLineEdit(right_panel)
        self.search_input.setPlaceholderText("Ask Local RAG (e.g. 'Redis') + Enter...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #09090D; color: #FAFAFA;
                border: 1px solid rgba(255,255,255,0.10); border-radius: 8px;
                padding: 8px 10px; font-size: 11px;
            }
            QLineEdit:focus { border: 1px solid #06B6D4; }
        """)
        self.search_input.returnPressed.connect(self._handle_search)
        rlay.addWidget(self.search_input)

        outer.addWidget(right_panel)
        return page

    def _build_session_library_page(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)

        # 3 Telemetry Cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        for title, val, accent in (
            ("Total Recordings", "Local SQLite WAL", "#06B6D4"),
            ("Avg Inference Latency", "< 190 ms", "#10B981"),
            ("Encryption Standard", "DPAPI + AES-256-GCM", "#A855F7"),
        ):
            card = QFrame(page)
            card.setStyleSheet("QFrame { background: #111115; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 10px; }")
            cl = QVBoxLayout(card)
            t = QLabel(title, card)
            t.setStyleSheet("color: #A1A1AA; font-size: 11px; border: none;")
            v = QLabel(val, card)
            v.setStyleSheet(f"color: {accent}; font-size: 17px; font-weight: 700; border: none;")
            cl.addWidget(t)
            cl.addWidget(v)
            stats_row.addWidget(card)
        lay.addLayout(stats_row)

        # Local Drop / Browse Card + Actions
        drop_card = QFrame(page)
        drop_card.setStyleSheet("QFrame { background: #111115; border: 1px dashed rgba(6,182,212,0.35); border-radius: 12px; padding: 20px; }")
        dl = QVBoxLayout(drop_card)
        dl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("Local Batch Audio Ingestion (.wav, .mp3, .m4a)\n100% Offline CTranslate2 INT8 Worker", drop_card)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #D4D4D8; font-size: 12.5px; border: none;")
        btn = QPushButton("Browse Local Audio File...", drop_card)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("QPushButton { background: rgba(6,182,212,0.15); color: #22D3EE; border: 1px solid rgba(6,182,212,0.35); border-radius: 7px; padding: 7px 14px; font-weight: 600; }")
        btn.clicked.connect(lambda: QFileDialog.getOpenFileName(self, "Select Audio File", "", "Audio (*.wav *.mp3 *.m4a)"))
        dl.addWidget(lbl)
        dl.addSpacing(8)
        dl.addWidget(btn)
        lay.addWidget(drop_card)
        lay.addStretch()
        return page

    def _build_ai_workspace_page(self) -> QWidget:
        page = QWidget(self)
        lay = QHBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)

        left = QFrame(page)
        left.setStyleSheet("QFrame { background: #111115; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 14px; }")
        ll = QVBoxLayout(left)
        ll.setSpacing(10)
        hdr = QLabel("Local Model & VAD Configuration", left)
        hdr.setStyleSheet("color: #FAFAFA; font-size: 13px; font-weight: 700; border: none;")
        ll.addWidget(hdr)

        for label_txt, opts in (
            ("Loopback ASR Model (Attendees)", ["faster-whisper base (INT8 CPU)", "faster-whisper small (INT8)", "faster-whisper large-v3"]),
            ("Real-Time Mic Model (You)", ["RealtimeSTT tiny + base", "RealtimeSTT base.en"]),
            ("Local Vector Embedding Model", ["BAAI/bge-small-en-v1.5 (384-d ONNX)"]),
        ):
            l = QLabel(label_txt, left)
            l.setStyleSheet("color: #A1A1AA; font-size: 11px; border: none;")
            cb = QComboBox(left)
            cb.addItems(opts)
            cb.setStyleSheet("QComboBox { background: #09090D; color: #FAFAFA; border: 1px solid rgba(255,255,255,0.10); border-radius: 6px; padding: 6px; font-size: 11px; }")
            ll.addWidget(l)
            ll.addWidget(cb)

        sl_lbl = QLabel("Acoustic Overlap Window: 400ms (Fast-Speech Guard)", left)
        sl_lbl.setStyleSheet("color: #22D3EE; font-size: 11px; border: none;")
        sl = QSlider(Qt.Orientation.Horizontal, left)
        sl.setRange(200, 800)
        sl.setValue(400)
        sl.valueChanged.connect(lambda v: sl_lbl.setText(f"Acoustic Overlap Window: {v}ms (Fast-Speech Guard)"))
        ll.addWidget(sl_lbl)
        ll.addWidget(sl)
        ll.addStretch()

        right = QFrame(page)
        right.setStyleSheet("QFrame { background: #111115; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 14px; }")
        rl = QVBoxLayout(right)
        rh = QLabel("Live Markdown Export Preview", right)
        rh.setStyleSheet("color: #FAFAFA; font-size: 13px; font-weight: 700; border: none;")
        self.md_preview = QTextEdit(right)
        self.md_preview.setReadOnly(True)
        self.md_preview.setStyleSheet("QTextEdit { background: #09090D; color: #E4E4E7; border: 1px solid rgba(255,255,255,0.07); border-radius: 8px; padding: 10px; font-family: 'Consolas', monospace; font-size: 11px; }")
        self.md_preview.setPlainText("# DevListen Meeting Brief\n\n- Engine: 100% Offline\n- Decisions & Action Items sync live here.")
        rl.addWidget(rh)
        rl.addWidget(self.md_preview)

        lay.addWidget(left, 1)
        lay.addWidget(right, 1)
        return page

    def _build_decisions_rag_page(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        hdr = QLabel("Bi-Temporal Knowledge Graph (ACTIVE vs SUPERSEDED) & Commitments", page)
        hdr.setStyleSheet("color: #FAFAFA; font-size: 13px; font-weight: 700;")
        lay.addWidget(hdr)

        cols = QHBoxLayout()
        cols.setSpacing(12)

        self.dec_scroll = QScrollArea(page)
        self.dec_scroll.setWidgetResizable(True)
        self.dec_scroll.setStyleSheet("QScrollArea { background: #111115; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; }")
        self.dec_container = QWidget()
        self.dec_layout = QVBoxLayout(self.dec_container)
        self.dec_layout.setContentsMargins(12, 12, 12, 12)
        self.dec_layout.setSpacing(8)
        self.dec_layout.addStretch()
        self.dec_scroll.setWidget(self.dec_container)

        self.act_scroll = QScrollArea(page)
        self.act_scroll.setWidgetResizable(True)
        self.act_scroll.setStyleSheet("QScrollArea { background: #111115; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; }")
        self.act_container = QWidget()
        self.act_layout = QVBoxLayout(self.act_container)
        self.act_layout.setContentsMargins(12, 12, 12, 12)
        self.act_layout.setSpacing(8)
        self.act_layout.addStretch()
        self.act_scroll.setWidget(self.act_container)

        cols.addWidget(self.dec_scroll, 1)
        cols.addWidget(self.act_scroll, 1)
        lay.addLayout(cols, 1)
        return page

    def _build_preferences_page(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        card = QFrame(page)
        card.setStyleSheet("QFrame { background: #111115; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; }")
        cl = QVBoxLayout(card)
        cl.setSpacing(10)
        h = QLabel("Window Privacy, Opacity & Global Shortcuts", card)
        h.setStyleSheet("color: #FAFAFA; font-size: 13px; font-weight: 700; border: none;")
        cl.addWidget(h)

        op_lbl = QLabel(f"Window Opacity: {int(self.current_opacity * 100)}%", card)
        op_lbl.setStyleSheet("color: #A1A1AA; font-size: 11px; border: none;")
        op_sl = QSlider(Qt.Orientation.Horizontal, card)
        op_sl.setRange(35, 100)
        op_sl.setValue(int(self.current_opacity * 100))
        op_sl.valueChanged.connect(lambda v: (self.set_opacity(v / 100.0), op_lbl.setText(f"Window Opacity: {v}%")))
        cl.addWidget(op_lbl)
        cl.addWidget(op_sl)

        hotkeys_lbl = QLabel(
            "• Alt + Shift + Space / L  —  Toggle HUD Visibility\n"
            "• Alt + Shift + E          —  Export Markdown Minutes\n"
            "• Alt + Shift + Q          —  Quit DevListen\n"
            "• Ctrl + MouseWheel        —  Adjust Window Opacity",
            card
        )
        hotkeys_lbl.setStyleSheet("color: #D4D4D8; font-family: 'Consolas', monospace; font-size: 11px; border: none; padding-top: 8px;")
        cl.addWidget(hotkeys_lbl)
        lay.addWidget(card)
        lay.addStretch()
        return page

    def _build_status_bar(self) -> QFrame:
        bar = QFrame(self)
        bar.setFixedHeight(26)
        bar.setStyleSheet("""
            QFrame {
                background-color: #0C0C10;
                border-top: 1px solid rgba(255, 255, 255, 0.07);
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 14, 0)
        self.status_lbl = QLabel("Local Engine: faster-whisper INT8  |  Vector RAG: BGE-Small ONNX  |  Latency: <190ms  |  Vault: Encrypted WAL", bar)
        self.status_lbl.setStyleSheet("color: #71717A; font-family: 'Consolas', monospace; font-size: 10px; border: none;")
        lay.addWidget(self.status_lbl)
        lay.addStretch()
        return bar

    def _switch_page(self, idx: int):
        titles = [
            "Live Capture & Diarization",
            "Session Library & Batch Queue",
            "AI Workspace & Model Engine",
            "Bi-Temporal Decisions & RAG",
            "Preferences & Privacy",
        ]
        svgs = [SVG_RADIO, SVG_FOLDER, SVG_CPU, SVG_BRANCH, SVG_SLIDERS]
        self.page_title_lbl.setText(titles[idx])
        self.pages.setCurrentIndex(idx)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == idx)
            btn.setIcon(make_svg_icon(svgs[i], "#06B6D4" if i == idx else "#71717A", 15))
        animate_fade_in(self.pages.currentWidget(), duration_ms=170)

    def _toggle_json_box(self):
        self._show_raw_json = not self._show_raw_json
        self.json_box.setVisible(self._show_raw_json)

    def _refresh_insights_and_json(self):
        last_entry = self._transcript_log[-1] if self._transcript_log else {"speaker": "SYSTEM", "text": "Listening..."}
        summary_txt = last_entry["text"][:90] + ("..." if len(last_entry["text"]) > 90 else "")
        self.insights_lbl.setText(
            f"<span style='color:#06B6D4;'>●</span> <b>Latest Context:</b> {summary_txt}<br><br>"
            f"<span style='color:#6366F1;'>●</span> <b>Decisions Logged:</b> {len(self._decisions_list)}<br><br>"
            f"<span style='color:#F59E0B;'>●</span> <b>Action Items:</b> {len(self._commitments_list)}"
        )
        payload = {
            "latest_turn": last_entry,
            "decisions_count": len(self._decisions_list),
            "action_items_count": len(self._commitments_list),
            "decisions": self._decisions_list[-2:],
            "actions": self._commitments_list[-2:],
        }
        self.json_box.setPlainText(json.dumps(payload, indent=2))

    # --- Public Slots (100% compatible with main.py & demo_mode.py) ---

    def set_tier_badge(self, label: str, tooltip: str = ""):
        self.tier_pill.setText(f"⚡ {label}")
        if tooltip:
            self.tier_pill.setToolTip(tooltip)

    @Slot(float, float)
    def update_audio_levels(self, mic_level: float, call_level: float):
        self.waveform.set_energy(mic_level, call_level)

    @Slot(str, str, bool)
    def add_or_update_stream_card(self, text: str, speaker: str, is_final: bool = False):
        clean_text = text.strip()
        if not clean_text:
            return

        spk = speaker.upper()
        if spk in ("USER", "YOU"):
            spk = "YOU"
            accent = "#06B6D4"
            bg = "rgba(6, 182, 212, 0.05)"
            border = "rgba(6, 182, 212, 0.22)"
            pill_bg = "rgba(6, 182, 212, 0.16)"
        else:
            spk = "ATTENDEES" if spk in ("REMOTE", "ATTENDEES", "ATTENDEE") else spk
            accent = "#A855F7"
            bg = "rgba(168, 85, 247, 0.05)"
            border = "rgba(168, 85, 247, 0.22)"
            pill_bg = "rgba(168, 85, 247, 0.16)"

        now_time = datetime.datetime.now().strftime("%H:%M:%S")
        card = self._active_stream_cards.get(spk)

        if card is None or card.property("is_final"):
            card = QFrame(self.stream_container)
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg};
                    border: 1px solid {border};
                    border-left: 3px solid {accent};
                    border-radius: 10px;
                    padding: 8px;
                }}
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(5)

            hdr = QHBoxLayout()
            pill = QLabel(f" {spk} ", card)
            pill.setStyleSheet(f"background: {pill_bg}; color: {accent}; font-weight: 700; font-size: 10px; border-radius: 4px; padding: 2px 6px; border: none;")
            ts = QLabel(now_time, card)
            ts.setStyleSheet("color: #71717A; font-family: 'Consolas', monospace; font-size: 10px; border: none;")
            hdr.addWidget(pill)
            hdr.addWidget(ts)
            hdr.addStretch()
            cl.addLayout(hdr)

            txt_lbl = QLabel(clean_text, card)
            txt_lbl.setWordWrap(True)
            txt_lbl.setStyleSheet("color: #F4F4F5; font-size: 12.5px; line-height: 1.5; border: none;")
            cl.addWidget(txt_lbl)

            card.setProperty("txt_lbl", txt_lbl)
            card.setProperty("is_final", is_final)
            self._active_stream_cards[spk] = card
            self.stream_layout.insertWidget(self.stream_layout.count() - 1, card)
            animate_fade_in(card, duration_ms=200)
        else:
            card.property("txt_lbl").setText(clean_text)
            card.setProperty("is_final", is_final)

        if is_final:
            self._active_stream_cards.pop(spk, None)
            self._transcript_log.append({"speaker": spk, "timestamp": now_time, "text": clean_text})
            self._refresh_insights_and_json()

        QTimer.singleShot(40, lambda: self.stream_scroll.verticalScrollBar().setValue(self.stream_scroll.verticalScrollBar().maximum()))

    @Slot(dict)
    def add_decision_card(self, dec: Dict[str, Any]):
        self._decisions_list.append(dec)
        status = dec.get("status", "ACTIVE")
        col = "#10B981" if status == "ACTIVE" else "#F43F5E"
        card = QFrame(self.dec_container)
        card.setStyleSheet(f"QFrame {{ background: #09090D; border: 1px solid rgba(255,255,255,0.08); border-left: 3px solid {col}; border-radius: 8px; padding: 8px; }}")
        cl = QVBoxLayout(card)
        lbl = QLabel(f"<b style='color:{col};'>[{status}] {dec.get('entity', 'Decision')}</b><br>{dec.get('summary', '')}", card)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #E4E4E7; font-size: 11.5px; border: none;")
        cl.addWidget(lbl)
        self.dec_layout.insertWidget(self.dec_layout.count() - 1, card)
        self._refresh_insights_and_json()

    @Slot(dict)
    def add_commitment_card(self, act: Dict[str, Any]):
        self._commitments_list.append(act)
        card = QFrame(self.act_container)
        card.setStyleSheet("QFrame { background: #09090D; border: 1px solid rgba(255,255,255,0.08); border-left: 3px solid #F59E0B; border-radius: 8px; padding: 8px; }")
        cl = QVBoxLayout(card)
        lbl = QLabel(f"<b style='color:#F59E0B;'>@{act.get('assignee', 'Team')}</b><br>☐ {act.get('task', '')}", card)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #E4E4E7; font-size: 11.5px; border: none;")
        cl.addWidget(lbl)
        self.act_layout.insertWidget(self.act_layout.count() - 1, card)
        self._refresh_insights_and_json()

    @Slot(str, str)
    def show_ambient_nudge(self, html_content: str, source_text: str):
        trimmed = source_text.strip()
        if len(trimmed) > 65:
            trimmed = trimmed[:62] + "..."
        self.nudge_label.setText(f"<b style='color:#F59E0B;'>⚡ ZERO-CLICK LOCAL RAG:</b> \"{trimmed}\"<br>{html_content}")
        self.nudge_frame.setVisible(True)
        animate_fade_in(self.nudge_frame, duration_ms=220)
        QTimer.singleShot(11000, lambda: self.nudge_frame.setVisible(False))

    def _handle_search(self):
        text = self.search_input.text().strip()
        if not text or not self.on_query_callback:
            return
        res = self.on_query_callback(text)
        self.show_ambient_nudge(res, f"Query: {text}")
        self.search_input.clear()

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = 0.05 if event.angleDelta().y() > 0 else -0.05
            self.set_opacity(self.current_opacity + step)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
