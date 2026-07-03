# splash.py

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRect,
    QParallelAnimationGroup, QSequentialAnimationGroup,
)
from PyQt6.QtGui import QPixmap

from utils import resource_path


# ══════════════════════════════════════════════════════════════════════════════
# Animation & Style Config  –  alle Werte hier editierbar
# ══════════════════════════════════════════════════════════════════════════════

# --- Timing (Millisekunden) --------------------------------------------------
ANIM_INTRO_MS        = 280   # Phase 1: pop von Start-Scale bis Overshoot
ANIM_SETTLE_MS       = 150   # Phase 2: Rückkehr von Overshoot auf 100 %
ANIM_FADE_MS         = 220   # Opacity Fade-in (läuft parallel zu Phase 1)

# --- Scale -------------------------------------------------------------------
ANIM_START_SCALE     = 0.82  # Startgröße  (< 1.0 – kleiner = dramatischer)
ANIM_OVERSHOOT_SCALE = 1.03  # Spitze des Overshoots (> 1.0, macOS-Spring)

# --- Text (Build-Info Label) -------------------------------------------------
TEXT_FONT_SIZE       = 15    # Schriftgröße in pt
TEXT_Y_FROM_BOTTOM   = 300   # Abstand von der Unterkante des Bildes (px)
TEXT_HEIGHT          = 90    # Höhe des Labels (px)


class SplashScreen(QWidget):
    """Rahmenloses, transparentes Splash mit macOS-Spring-Pop-Animation."""

    def __init__(self, build_info: str, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.build_info = build_info
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pix = QPixmap(str(resource_path("assets/splash.png")))
        self._full_w = pix.width()
        self._full_h = pix.height()
        self._pix    = pix

        self.resize(self._full_w, self._full_h)

        self._frame = QWidget(self)
        self._frame.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._frame.setStyleSheet("background: transparent;")
        self._frame.setGeometry(0, 0, self._full_w, self._full_h)

        layout = QVBoxLayout(self._frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splash_label = QLabel()
        self.splash_label.setPixmap(pix)
        self.splash_label.setScaledContents(True)
        self.splash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.splash_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.splash_label)

        self.info_label = QLabel(self.build_info, parent=self._frame)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet(
            f"color: black; background: transparent;"
            f" font-family: Segoe UI; font-size: {TEXT_FONT_SIZE}pt; font-weight: bold;"
        )
        self.info_label.setScaledContents(True)
        self.info_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.info_label.setGeometry(
            -100,
            self._full_h - TEXT_Y_FROM_BOTTOM,
            self._full_w,
            TEXT_HEIGHT,
        )

    def mousePressEvent(self, event) -> None:
        self._animate_close()

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def _centered_rect(self, scale: float) -> QRect:
        w, h   = self._full_w, self._full_h
        sw, sh = int(w * scale), int(h * scale)
        cx, cy = w // 2, h // 2
        return QRect(cx - sw // 2, cy - sh // 2, sw, sh)

    def _animate(self) -> None:
        """
        macOS-Fenster-Pop:
          Phase 1 (parallel, ANIM_INTRO_MS):
            • Fade-in  0.0 → 1.0          (InQuad)
            • Scale    START → OVERSHOOT  (OutCubic – schneller Snap)
          Phase 2 (ANIM_SETTLE_MS):
            • Scale    OVERSHOOT → 100 %  (OutQuad – weiches Einrasten)
        """
        full_rect      = QRect(0, 0, self._full_w, self._full_h)
        start_rect     = self._centered_rect(ANIM_START_SCALE)
        overshoot_rect = self._centered_rect(ANIM_OVERSHOOT_SCALE)

        self._frame.setGeometry(start_rect)
        self.setWindowOpacity(0.0)

        # Fade-in ──────────────────────────────────────────────────────
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(ANIM_FADE_MS)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.InQuad)

        # Phase 1 – Pop: START_SCALE → OVERSHOOT_SCALE ────────────────
        pop = QPropertyAnimation(self._frame, b"geometry", self)
        pop.setDuration(ANIM_INTRO_MS)
        pop.setStartValue(start_rect)
        pop.setEndValue(overshoot_rect)
        pop.setEasingCurve(QEasingCurve.Type.OutCubic)

        intro = QParallelAnimationGroup(self)
        intro.addAnimation(fade)
        intro.addAnimation(pop)

        # Phase 2 – Settle: OVERSHOOT_SCALE → 100 % ───────────────────
        settle = QPropertyAnimation(self._frame, b"geometry", self)
        settle.setDuration(ANIM_SETTLE_MS)
        settle.setStartValue(overshoot_rect)
        settle.setEndValue(full_rect)
        settle.setEasingCurve(QEasingCurve.Type.OutQuad)

        self._anim_group = QSequentialAnimationGroup(self)
        self._anim_group.addAnimation(intro)
        self._anim_group.addAnimation(settle)
        self._anim_group.start()
    
    def _animate_close(self) -> None:
        """
        Pop-Down (Spiegel der Öffnungs-Animation):
          Phase 1 (ANIM_SETTLE_MS):  Scale 100 % → Overshoot  (InQuad)
          Phase 2 (parallel, ANIM_INTRO_MS + ANIM_FADE_MS):
            • Scale    Overshoot → Start-Scale  (InCubic)
            • Fade-out 1.0 → 0.0               (OutQuad)
        """
        if getattr(self, "_closing", False):
            return
        self._closing = True

        if hasattr(self, "_anim_group"):
            self._anim_group.stop()

        full_rect      = QRect(0, 0, self._full_w, self._full_h)
        start_rect     = self._centered_rect(ANIM_START_SCALE)
        overshoot_rect = self._centered_rect(ANIM_OVERSHOOT_SCALE)

        bounce = QPropertyAnimation(self._frame, b"geometry", self)
        bounce.setDuration(ANIM_SETTLE_MS)
        bounce.setStartValue(full_rect)
        bounce.setEndValue(overshoot_rect)
        bounce.setEasingCurve(QEasingCurve.Type.InQuad)

        shrink = QPropertyAnimation(self._frame, b"geometry", self)
        shrink.setDuration(ANIM_INTRO_MS)
        shrink.setStartValue(overshoot_rect)
        shrink.setEndValue(start_rect)
        shrink.setEasingCurve(QEasingCurve.Type.InCubic)

        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(ANIM_FADE_MS)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.OutQuad)

        outro = QParallelAnimationGroup(self)
        outro.addAnimation(shrink)
        outro.addAnimation(fade)

        self._close_anim = QSequentialAnimationGroup(self)
        self._close_anim.addAnimation(bounce)
        self._close_anim.addAnimation(outro)
        self._close_anim.finished.connect(self.close)
        self._close_anim.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_centered(self, parent: QWidget) -> None:
        """Zentriert über Parent-Fenster, startet dann die Animation."""
        geo = parent.frameGeometry()
        x   = geo.x() + (geo.width()  - self.width())  // 2
        y   = geo.y() + (geo.height() - self.height()) // 2 - 50
        self.move(x, y)
        self.show()
        self._animate()


# ══════════════════════════════════════════════════════════════════════════════
# Standalone-Test  –  python splash.py
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    host = QMainWindow()
    host.setWindowTitle("Splash – Test-Host")
    host.resize(900, 700)
    host.show()

    splash = SplashScreen("Gallery Downloader Extended \nVersion 0.39\n")
    splash.show_centered(host)
    splash.destroyed.connect(app.quit)   # App beendet sich wenn Splash geschlossen wird

    sys.exit(app.exec())
