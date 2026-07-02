# splash.py

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRect,
    QParallelAnimationGroup, QSequentialAnimationGroup,
)
from PySide6.QtGui import QPixmap, QFont

from utils import resource_path


class SplashScreen(QWidget):
    """Rahmenloses, transparentes Splash-Fenster mit Build-Info."""

    def __init__(self, build_info: str, parent=None) -> None:
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.build_info = build_info
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pix = QPixmap(str(resource_path("assets/splash.png")))
        self._full_w = pix.width()
        self._full_h = pix.height()

        # Äußeres Fenster: immer volle Größe, nur für Positionierung
        self.resize(self._full_w, self._full_h)

        # Inneres Frame-Widget: dieses wird animiert (Scale)
        self._frame = QWidget(self)
        self._frame.setGeometry(0, 0, self._full_w, self._full_h)

        layout = QVBoxLayout(self._frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splash_label = QLabel()
        self.splash_label.setPixmap(pix)
        self.splash_label.setAlignment(Qt.AlignCenter)
        self.splash_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.splash_label)

        # Build-Info absolut über dem Bild
        self.info_label = QLabel(self.build_info, parent=self._frame)
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setFont(QFont("Segoe UI", 25, QFont.Bold))
        self.info_label.setStyleSheet("color: black; background: transparent;")
        self.info_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.info_label.setGeometry(-100, self._full_h - 300, self._full_w, 90)

    def mousePressEvent(self, event) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def _animate(self) -> None:
        """
        Animations-Ablauf:
          Phase 1 (350ms, parallel):
            - Fade-In des Hauptfensters: Opacity 0.0 → 1.0
            - Scale des _frame von 85 % → 100 %, Mittelpunkt fix
          Phase 2 (300ms):
            - Puls: _frame kurz auf 90 % Größe, dann zurück auf 100 %

        Das Hauptfenster bewegt sich NICHT – nur _frame skaliert.
        Dadurch bleibt die Bildschirmposition stabil.
        """
        w, h = self._full_w, self._full_h
        cx, cy = w // 2, h // 2  # Mittelpunkt im Fenster-Koordinatensystem

        # Vollgröße des _frame
        full_rect = QRect(0, 0, w, h)

        # Startgröße: 85 % aus der Mitte
        scale = 0.85
        sw, sh = int(w * scale), int(h * scale)
        small_rect = QRect(cx - sw // 2, cy - sh // 2, sw, sh)

        # Puls-Größe: 95 %
        pw, ph = int(w * 0.95), int(h * 0.95)
        pulse_rect = QRect(cx - pw // 2, cy - ph // 2, pw, ph)

        # -- Startzustand --
        self._frame.setGeometry(small_rect)
        self.setWindowOpacity(0.0)

        # -- Phase 1: Fade-In --
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(350)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.InOutQuad)

        # -- Phase 1: Scale aus Mitte --
        grow = QPropertyAnimation(self._frame, b"geometry", self)
        grow.setDuration(350)
        grow.setStartValue(small_rect)
        grow.setEndValue(full_rect)
        grow.setEasingCurve(QEasingCurve.OutCubic)

        intro = QParallelAnimationGroup(self)
        intro.addAnimation(fade)
        intro.addAnimation(grow)

        # -- Phase 2: Puls --
        pulse_out = QPropertyAnimation(self._frame, b"geometry", self)
        pulse_out.setDuration(150)
        pulse_out.setStartValue(full_rect)
        pulse_out.setEndValue(pulse_rect)
        pulse_out.setEasingCurve(QEasingCurve.OutQuad)

        pulse_in = QPropertyAnimation(self._frame, b"geometry", self)
        pulse_in.setDuration(150)
        pulse_in.setStartValue(pulse_rect)
        pulse_in.setEndValue(full_rect)
        pulse_in.setEasingCurve(QEasingCurve.OutBounce)

        pulse_seq = QSequentialAnimationGroup(self)
        pulse_seq.addAnimation(pulse_out)
        pulse_seq.addAnimation(pulse_in)

        # -- Gesamt-Sequenz --
        self._anim_group = QSequentialAnimationGroup(self)
        self._anim_group.addAnimation(intro)
        self._anim_group.addAnimation(pulse_seq)
        self._anim_group.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_centered(self, parent: QWidget) -> None:
        """
        Positioniert das Fenster zentriert über dem Parent und startet die Animation.
        Das Hauptfenster wird einmalig an die richtige Stelle bewegt und bleibt dort.
        """
        parent_geo = parent.frameGeometry()
        x = parent_geo.x() + (parent_geo.width()  - self.width())  // 2
        y = parent_geo.y() + (parent_geo.height() - self.height()) // 2 - 50
        self.move(x, y)
        self.show()
        self._animate()
