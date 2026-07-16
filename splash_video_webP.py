# splash_video_webp.py
#
# Transparenter Splash-Screen via animated WebP (Qt-nativ, voller Alpha-Kanal).
# Eine einzige .webp-Datei ersetzt die PNG-Sequenz – typ. 80–95 % kleiner.

import sys
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRect,
    QParallelAnimationGroup, QSequentialAnimationGroup,
)
from PyQt6.QtGui import QPainter, QImage, QMovie, QColor, QPainterPath, QPen


def resource_path(relative_path: str) -> Path:
    """
    Liefert den Pfad zu einer Ressource innerhalb dieses Submodule-Ordners
    (SplashScreenPython/assets/...). Verwendet immer die eigenen Assets des
    Submodules, unabhängig davon, ob es eigenständig oder als Submodul im
    Hauptprogramm ausgeführt wird.
    """
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS) / "SplashScreenPython"  # type: ignore[attr-defined]
        if not base_path.exists():
            base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / relative_path


# ══════════════════════════════════════════════════════════════════════════════
# Config  –  alle Werte hier editierbar
# ══════════════════════════════════════════════════════════════════════════════

# --- Timing (Millisekunden) --------------------------------------------------
ANIM_INTRO_MS        = 280   # Phase 1: pop von Start-Scale bis Overshoot
ANIM_SETTLE_MS       = 150   # Phase 2: Rückkehr von Overshoot auf 100 %
ANIM_FADE_MS         = 220   # Opacity Fade-in (läuft parallel zu Phase 1)

# --- Scale -------------------------------------------------------------------
ANIM_START_SCALE     = 0.82
ANIM_OVERSHOOT_SCALE = 1.03

# --- Animated WebP -----------------------------------------------------------
ANIM_PATH   = "assets/splash_ChloeGraceMoretz_90percent.webp"  # Pfad zur animated .webp Datei
ANIM_WIDTH  = 960                   # Ausgabegröße (px) – unabhängig von Frame-Größe
ANIM_HEIGHT = 960
ANIM_SPEED  = 100                   # Wiedergabegeschwindigkeit in %
                                    # (FPS steckt in der .webp; setSpeed skaliert sie)

# --- Text (Build-Info Label) -------------------------------------------------
TEXT_FONT_SIZE = 10
TEXT_X         = -250
TEXT_Y         = 620
TEXT_WIDTH     = None
TEXT_HEIGHT    = 200


class OutlinedLabel(QLabel):
    """QLabel mit farbiger Textkontur via QPainterPath."""

    outline_color = QColor(255, 255, 255)  # weiße Kontur
    fill_color    = QColor(0, 0, 0)        # schwarzer Text
    outline_px    = 2

    def paintEvent(self, a0) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        fm    = painter.fontMetrics()
        rect  = self.contentsRect()
        align = self.alignment()
        lines = self.text().split("\n")

        line_h  = fm.height()
        total_h = line_h * len(lines)
        ascent  = fm.ascent()

        if align & Qt.AlignmentFlag.AlignVCenter:
            y = rect.top() + (rect.height() - total_h) / 2 + ascent
        elif align & Qt.AlignmentFlag.AlignBottom:
            y = rect.bottom() - total_h + ascent
        else:
            y = rect.top() + ascent

        path = QPainterPath()
        for line in lines:
            text_w = fm.horizontalAdvance(line)
            if align & Qt.AlignmentFlag.AlignHCenter:
                x = rect.left() + (rect.width() - text_w) / 2
            elif align & Qt.AlignmentFlag.AlignRight:
                x = rect.right() - text_w
            else:
                x = rect.left()
            path.addText(x, y, self.font(), line)
            y += line_h

        pen = QPen(self.outline_color, self.outline_px * 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(path, self.fill_color)
        painter.end()


class SplashScreen(QWidget):
    """Rahmenloses, transparentes Splash mit macOS-Spring-Pop-Animation (Animated WebP)."""

    def __init__(self, build_info: str, parent=None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.build_info = build_info
        self._full_w = ANIM_WIDTH
        self._full_h = ANIM_HEIGHT
        self._current_image: QImage | None = None
        self._movie: QMovie | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.resize(self._full_w, self._full_h)

        # Transparenter Platzhalter als Geometrie-Anker für die Scale-Animation
        self._frame = QWidget(self)
        self._frame.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._frame.setStyleSheet("background: transparent;")
        self._frame.setGeometry(0, 0, self._full_w, self._full_h)
        self._frame.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._load_movie(str(resource_path(ANIM_PATH)))

        # --- Build-Info Label -----------------------------------------
        text_w = TEXT_WIDTH if TEXT_WIDTH is not None else self._full_w - TEXT_X
        self.info_label = OutlinedLabel(self.build_info, parent=self._frame)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet(
            f"background: transparent;"
            f" font-family: Segoe UI; font-size: {TEXT_FONT_SIZE}pt; font-weight: bold;"
        )
        self.info_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.info_label.setGeometry(TEXT_X, TEXT_Y, text_w, TEXT_HEIGHT)
        self.info_label.raise_()

    # ------------------------------------------------------------------
    # WebP laden
    # ------------------------------------------------------------------

    def _load_movie(self, path: str) -> None:
        movie = QMovie(path)
        if not movie.isValid():
            print(f"[SplashScreen] WebP konnte nicht geladen werden: {path}")
            print(f"[SplashScreen] Unterstützte Formate: {QMovie.supportedFormats()}")
            return

        movie.setCacheMode(QMovie.CacheMode.CacheAll)  # alle Frames im RAM (klein!)
        movie.setSpeed(ANIM_SPEED)
        movie.frameChanged.connect(self._on_frame)

        # Ersten Frame sofort holen → kein Flash beim Erscheinen
        movie.jumpToFrame(0)
        self._current_image = self._scaled(movie.currentImage())

        self._movie = movie
        print(f"[SplashScreen] WebP geladen: {movie.frameCount()} Frames")

    def _scaled(self, img: QImage) -> QImage:
        if img.isNull():
            return img
        if img.width() == ANIM_WIDTH and img.height() == ANIM_HEIGHT:
            return img
        return img.scaled(
            ANIM_WIDTH, ANIM_HEIGHT,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _on_frame(self, _frame_number: int) -> None:
        if self._movie is None:
            return
        self._current_image = self._scaled(self._movie.currentImage())
        self.update()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        if self._current_image and not self._current_image.isNull():
            geo = self._frame.geometry()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawImage(geo, self._current_image)
        painter.end()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mousePressEvent(self, a0) -> None:  # noqa: ARG002
        self._animate_close()

    def closeEvent(self, a0) -> None:
        self._stop()
        super().closeEvent(a0)

    def _stop(self) -> None:
        if self._movie is not None:
            self._movie.stop()

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

        if self._movie is not None:
            self._movie.start()

        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(ANIM_FADE_MS)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.InQuad)

        pop = QPropertyAnimation(self._frame, b"geometry", self)
        pop.setDuration(ANIM_INTRO_MS)
        pop.setStartValue(start_rect)
        pop.setEndValue(overshoot_rect)
        pop.setEasingCurve(QEasingCurve.Type.OutCubic)

        intro = QParallelAnimationGroup(self)
        intro.addAnimation(fade)
        intro.addAnimation(pop)

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
        self._close_anim.finished.connect(self._on_close_anim_finished)
        self._close_anim.start()

    def _on_close_anim_finished(self) -> None:
        self._stop()
        self.close()

    # ------------------------------------------------------------------
    # Public API  (kompatibel zu DownloadFromGalleryExtended)
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
# Standalone-Test  –  python splash_video.py
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    host = QMainWindow()
    host.setWindowTitle("Splash – Test-Host")
    host.resize(900, 700)
    host.show()

    splash = SplashScreen("Gallery Downloader \nVersion 0.41\n")
    splash.show_centered(host)
    splash.destroyed.connect(app.quit)

    sys.exit(app.exec())
