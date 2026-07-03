# utils.py
from pathlib import Path
import sys


def resource_path(relative_path):
    """
    Liefert den korrekten Pfad zu einer Ressource, auch wenn das Programm
    als PyInstaller onefile gebündelt wurde.
    """
    if getattr(sys, "frozen", False):
        # temporärer Ordner, in den PyInstaller extrahiert
        base_path = Path(sys._MEIPASS)
    elif __package__:
        # Als Submodul (Package "SplashScreenPython") eingebunden
        # → Assets des Hauptprogramms verwenden (ein Verzeichnis höher).
        base_path = Path(__file__).resolve().parent.parent
    else:
        # Direkt als eigenständiges Skript ausgeführt → eigene Assets verwenden.
        base_path = Path(__file__).resolve().parent

    return base_path / relative_path