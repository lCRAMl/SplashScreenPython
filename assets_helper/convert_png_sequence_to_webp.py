"""
convert_png_sequence_to_webp.py

Konvertiert eine PNG-Sequenz (mit Alpha-Kanal) in eine einzige animated WebP-Datei.
Behält Transparenz, dramatisch kleinere Dateigröße.

Voraussetzung:  pip install Pillow PyQt6
"""

from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# ───────────── Default-Config ──────────────────────────────────────────────
SRC_FOLDER  = r"Z:\Instagram\Keri Russell\ai\2026-06-13_09-15-56_green_video3"
DST_FILE    = r"assets\splash_KeriRussell.webp"

FPS         = 30      # Wiedergabe-FPS  (Frame-Delay = 1000/FPS ms)
QUALITY     = 90      # 0–100  (85–92 ist meist optisch verlustfrei für UI-Animationen)
LOSSLESS    = True    # True = verlustfrei (größer, aber pixelgenau)
METHOD      = 6       # 0–6  (6 = langsam aber beste Kompression)
LOOP        = 0       # 0 = Endlosschleife
# ──────────────────────────────────────────────────────────────────────────────


def _natural_sort_key(p: Path) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def _load_frame(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def convert(
    src_folder: str,
    dst_file: str,
    fps: int = FPS,
    quality: int = QUALITY,
    lossless: bool = LOSSLESS,
    method: int = METHOD,
    loop: int = LOOP,
    log=print,
    progress=None,
) -> None:
    """progress(phase, current, total) wird optional aufgerufen:
    phase="loading"  → current/total = geladene/gesamte Frames
    phase="encoding" → current=total=0 (Dauer nicht vorhersagbar, libwebp arbeitet intern sequenziell)
    phase="done"     → current=total=1
    """
    folder = Path(src_folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Ordner nicht gefunden: {folder}")

    files = sorted(folder.glob("*.png"), key=_natural_sort_key)
    if not files:
        raise FileNotFoundError(f"Keine PNG-Dateien in: {folder}")

    total = len(files)
    workers = os.cpu_count() or 4
    log(f"Lade {total} Frames aus {folder} (parallel, {workers} Threads) …")

    results: dict[int, Image.Image] = {}
    done = 0
    if progress:
        progress("loading", 0, total)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {executor.submit(_load_frame, f): i for i, f in enumerate(files)}
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            results[index] = future.result()
            done += 1
            if progress:
                progress("loading", done, total)

    frames = [results[i] for i in range(total)]

    duration_ms = int(round(1000 / fps))
    dst = Path(dst_file)
    dst.parent.mkdir(parents=True, exist_ok=True)

    log(f"Schreibe → {dst}  (quality={quality}, lossless={lossless}, fps={fps})")
    if progress:
        progress("encoding", 0, 0)
    frames[0].save(
        dst,
        save_all=True,
        append_images=frames[1:],
        format="WEBP",
        duration=duration_ms,
        loop=loop,
        quality=quality,
        lossless=lossless,
        method=method,
        allow_mixed=False,
    )
    if progress:
        progress("done", 1, 1)

    # Größenvergleich ausgeben
    src_bytes = sum(f.stat().st_size for f in files)
    dst_bytes = dst.stat().st_size
    log("")
    log(f"PNG-Sequenz : {src_bytes / 1024 / 1024:8.2f} MB")
    log(f"WebP        : {dst_bytes / 1024 / 1024:8.2f} MB")
    log(f"Reduktion   : {(1 - dst_bytes / src_bytes) * 100:8.2f} %")


class ConvertWorker(QThread):
    log_line = Signal(str)
    progress = Signal(str, int, int)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, src_folder, dst_file, fps, quality, lossless, method, loop):
        super().__init__()
        self.src_folder = src_folder
        self.dst_file = dst_file
        self.fps = fps
        self.quality = quality
        self.lossless = lossless
        self.method = method
        self.loop = loop

    def run(self) -> None:
        try:
            convert(
                self.src_folder,
                self.dst_file,
                fps=self.fps,
                quality=self.quality,
                lossless=self.lossless,
                method=self.method,
                loop=self.loop,
                log=self.log_line.emit,
                progress=self.progress.emit,
            )
            self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PNG-Sequenz → animiertes WebP")
        self.resize(640, 560)

        self.worker: ConvertWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ── Pfade ──
        paths_box = QGroupBox("Pfade")
        paths_layout = QFormLayout(paths_box)

        self.src_edit = QLineEdit(SRC_FOLDER)
        src_row = QHBoxLayout()
        src_browse = QPushButton("Durchsuchen …")
        src_browse.clicked.connect(self._browse_src)
        src_row.addWidget(self.src_edit)
        src_row.addWidget(src_browse)
        paths_layout.addRow("Quellordner (PNGs):", src_row)

        self.dst_edit = QLineEdit(DST_FILE)
        dst_row = QHBoxLayout()
        dst_browse = QPushButton("Speichern unter …")
        dst_browse.clicked.connect(self._browse_dst)
        dst_row.addWidget(self.dst_edit)
        dst_row.addWidget(dst_browse)
        paths_layout.addRow("Ziel-Datei (.webp):", dst_row)

        root.addWidget(paths_box)

        # ── Optionen ──
        opts_box = QGroupBox("Optionen")
        opts_layout = QFormLayout(opts_box)

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 240)
        self.fps_spin.setValue(FPS)
        opts_layout.addRow("FPS:", self.fps_spin)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 100)
        self.quality_spin.setValue(QUALITY)
        opts_layout.addRow("Quality (0–100):", self.quality_spin)

        self.lossless_check = QCheckBox("Verlustfrei (lossless)")
        self.lossless_check.setChecked(LOSSLESS)
        self.lossless_check.toggled.connect(
            lambda checked: self.quality_spin.setEnabled(not checked)
        )
        self.quality_spin.setEnabled(not LOSSLESS)
        opts_layout.addRow("", self.lossless_check)

        self.method_spin = QSpinBox()
        self.method_spin.setRange(0, 6)
        self.method_spin.setValue(METHOD)
        opts_layout.addRow("Method (0–6, 6=beste Kompression):", self.method_spin)

        self.loop_spin = QSpinBox()
        self.loop_spin.setRange(0, 999)
        self.loop_spin.setValue(LOOP)
        self.loop_spin.setSpecialValueText("Endlos (0)")
        opts_layout.addRow("Loop (0=endlos):", self.loop_spin)

        root.addWidget(opts_box)

        # ── Start-Button ──
        self.convert_btn = QPushButton("Konvertieren")
        self.convert_btn.clicked.connect(self._start_conversion)
        root.addWidget(self.convert_btn)

        # ── Fortschritt ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        root.addWidget(self.progress_bar)

        # ── Log ──
        root.addWidget(QLabel("Log:"))
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        root.addWidget(self.log_edit)

    def _browse_src(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Quellordner wählen", self.src_edit.text()
        )
        if folder:
            self.src_edit.setText(folder)

    def _browse_dst(self) -> None:
        file, _ = QFileDialog.getSaveFileName(
            self, "Ziel-Datei wählen", self.dst_edit.text(), "WebP-Dateien (*.webp)"
        )
        if file:
            self.dst_edit.setText(file)

    def _start_conversion(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        self.log_edit.clear()
        self.convert_btn.setEnabled(False)
        self.convert_btn.setText("Konvertiere …")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")

        self.worker = ConvertWorker(
            src_folder=self.src_edit.text(),
            dst_file=self.dst_edit.text(),
            fps=self.fps_spin.value(),
            quality=self.quality_spin.value(),
            lossless=self.lossless_check.isChecked(),
            method=self.method_spin.value(),
            loop=self.loop_spin.value(),
        )
        self.worker.log_line.connect(self._append_log)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_finished_ok)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _append_log(self, line: str) -> None:
        self.log_edit.appendPlainText(line)

    def _on_progress(self, phase: str, current: int, total: int) -> None:
        if phase == "loading":
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"Lade Frames … %p% ({current}/{total})")
        elif phase == "encoding":
            self.progress_bar.setRange(0, 0)  # unbestimmter Modus (Balken pulsiert)
            self.progress_bar.setFormat("Encodiere WebP … (kann dauern)")
        elif phase == "done":
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            self.progress_bar.setFormat("Fertig")

    def _on_finished_ok(self) -> None:
        self.convert_btn.setEnabled(True)
        self.convert_btn.setText("Konvertieren")
        QMessageBox.information(self, "Fertig", "Konvertierung erfolgreich abgeschlossen.")

    def _on_failed(self, message: str) -> None:
        self.convert_btn.setEnabled(True)
        self.convert_btn.setText("Konvertieren")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Fehler")
        self._append_log(f"FEHLER: {message}")
        QMessageBox.critical(self, "Fehler", message)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
