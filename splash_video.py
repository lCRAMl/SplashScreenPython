# splash_video.py
#
# Transparenter Splash-Screen via PNG-Sequenz (Qt-nativ, voller Alpha-Kanal).
# Streaming-Modus: sofortiger Start nach erstem Frame, max. ~315 MB RAM.
# ANIM_PATH = Ordner mit PNG-Dateien  –ODER–  eine Datei aus der Sequenz.

import re
import threading
import time
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRect, QTimer,
    QParallelAnimationGroup, QSequentialAnimationGroup,
)
from PyQt6.QtGui import QPainter, QImage

from utils import resource_path


# ══════════════════════════════════════════════════════════════════════════════
# Config  –  alle Werte hier editierbar
# ══════════════════════════════════════════════════════════════════════════════

# --- Timing (Millisekunden) --------------------------------------------------
ANIM_INTRO_MS        = 280   # Phase 1: pop von Start-Scale bis Overshoot
ANIM_SETTLE_MS       = 150   # Phase 2: Rückkehr von Overshoot auf 100 %
ANIM_FADE_MS         = 220   # Opacity Fade-in (läuft parallel zu Phase 1)

# --- Scale -------------------------------------------------------------------
ANIM_START_SCALE     = 0.82  # Startgröße  (< 1.0 – kleiner = dramatischer)
ANIM_OVERSHOOT_SCALE = 1.03  # Spitze des Overshoots (> 1.0, macOS-Spring)

# --- PNG-Sequenz -------------------------------------------------------------
# Ordner-Pfad ODER eine beliebige Datei aus der Sequenz (Elternordner wird genutzt)
ANIM_PATH   = "assets\\2026-06-11_03-45-14_mokup_greenscreen_1x1_video2" # Beispiel: "C:\\path\\to\\frames"  –ODER–  "C:\\path\\to\\frames\\frame_001.png"
ANIM_WIDTH  = 960    # Ausgabegröße des Splash (px) – unabhängig von Frame-Größe
ANIM_HEIGHT = 960
ANIM_FPS    = 45     # Frames pro Sekunde der PNG-Sequenz
ANIM_LOOP   = True   # Endlosschleife

# Puffergröße: max. Frames gleichzeitig im RAM
# 90 Frames × ~3.5 MB (960×960 RGBA) ≈ 315 MB
FRAME_BUFFER = 90

# --- Text (Build-Info Label) -------------------------------------------------
TEXT_FONT_SIZE = 10    # Schriftgröße in pt
TEXT_X         = -350   # Linker Abstand vom Rand (px); Label reicht bis rechts
TEXT_Y         = 580   # Abstand von oben (px)
TEXT_WIDTH     = None  # Breite in px (None = ANIM_WIDTH - TEXT_X)
TEXT_HEIGHT    = 90    # Höhe des Labels (px)


def _natural_sort_key(p: Path) -> list:
    """Sortiert 'frame_001.png' vor 'frame_010.png' (numerisch, nicht lexikalisch)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


class SplashScreen(QWidget):
    """Rahmenloses, transparentes Splash mit macOS-Spring-Pop-Animation (PNG-Streaming)."""

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

        # Streaming-State
        self._png_files: list[Path] = []
        self._total: int = 0
        self._buf: dict[int, QImage] = {}  # globale_position → QImage
        self._buf_lock = threading.Lock()
        self._play_pos: int = 0   # aktuell angezeigter Frame (globale Position)
        self._load_pos: int = 0   # nächste zu ladende globale Position
        self._current_image: QImage | None = None
        self._timer: QTimer | None = None
        self._loader_stop = threading.Event()
        self._loader_thread: threading.Thread | None = None

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

        self._load_frames(str(resource_path(ANIM_PATH)))

        # --- Build-Info Label -----------------------------------------
        text_w = TEXT_WIDTH if TEXT_WIDTH is not None else self._full_w - TEXT_X
        self.info_label = QLabel(self.build_info, parent=self._frame)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet(
            f"color: black; background: transparent;"
            f" font-family: Segoe UI; font-size: {TEXT_FONT_SIZE}pt; font-weight: bold;"
        )
        self.info_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.info_label.setGeometry(TEXT_X, TEXT_Y, text_w, TEXT_HEIGHT)
        self.info_label.raise_()

    # ------------------------------------------------------------------
    # Frame-Laden (Streaming)
    # ------------------------------------------------------------------

    def _decode(self, path: Path) -> QImage:
        """Dekodiert PNG → QImage, skaliert auf Zielgröße. Thread-sicher (kein QPixmap)."""
        img = QImage(str(path))
        if not img.isNull() and (img.width() != ANIM_WIDTH or img.height() != ANIM_HEIGHT):
            img = img.scaled(
                ANIM_WIDTH, ANIM_HEIGHT,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return img

    def _load_frames(self, path: str) -> None:
        p = Path(path)
        folder = p if p.is_dir() else p.parent

        if not folder.is_dir():
            print(f"[SplashScreen] Ordner nicht gefunden: {folder}")
            return

        files = sorted(folder.glob("*.png"), key=_natural_sort_key)
        if not files:
            print(f"[SplashScreen] Keine PNG-Dateien in: {folder}")
            return

        self._png_files = files
        self._total = len(files)

        # Ersten Frame synchron laden → sofortiger Start ohne Wartezeit
        first = self._decode(files[0])
        with self._buf_lock:
            self._buf[0] = first
            self._load_pos = 1
        self._current_image = first

        print(f"[SplashScreen] {self._total} Frames – Streaming-Modus (Puffer: {FRAME_BUFFER} Frames)")

        # Rest im Hintergrundthread laden
        self._loader_thread = threading.Thread(target=self._bg_loader, daemon=True)
        self._loader_thread.start()

    def _bg_loader(self) -> None:
        """
        Lädt Frames im Hintergrund und hält den Puffer auf FRAME_BUFFER Einträge.
        Globale Positions-Arithmetik erlaubt nahtloses Looping ohne Neustart.
        """
        while not self._loader_stop.is_set():
            with self._buf_lock:
                lookahead = self._load_pos - self._play_pos
                load_pos  = self._load_pos

            # Puffer voll → kurz warten bis Abspielkopf Frames konsumiert hat
            if lookahead >= FRAME_BUFFER:
                time.sleep(0.02)
                continue

            # Bei einmaligem Abspielen: stoppen wenn alle Frames geladen sind
            if not ANIM_LOOP and load_pos >= self._total:
                break

            file_idx = load_pos % self._total
            img = self._decode(self._png_files[file_idx])

            with self._buf_lock:
                self._buf[load_pos] = img
                self._load_pos += 1

    # ------------------------------------------------------------------
    # Wiedergabe
    # ------------------------------------------------------------------

    def _start_playback(self) -> None:
        if not self._png_files:
            return
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)
        self._timer.start(max(1, int(1000 / ANIM_FPS)))

    def _advance_frame(self) -> None:
        next_pos = self._play_pos + 1

        if not ANIM_LOOP and next_pos >= self._total:
            self._stop_playback()
            return

        with self._buf_lock:
            next_img = self._buf.get(next_pos)
            if next_img is None:
                return  # Frame noch nicht geladen → gleichen Frame nochmal zeigen

            self._play_pos = next_pos
            self._current_image = next_img

            # Alte Frames hinter dem Abspielkopf verwerfen (5 Frames Schwanz behalten)
            cutoff = next_pos - 5
            for k in [k for k in self._buf if k < cutoff]:
                del self._buf[k]

        self.update()

    def _stop_playback(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._loader_stop.set()

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
        self._stop_playback()
        self.close()

    def closeEvent(self, a0) -> None:
        self._stop_playback()
        super().closeEvent(a0)

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

        self._start_playback()

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
