"""
FAZ113: Matriks Terminal adaptörü — Düzey 2 + VİOP verisi için pencere bağlantısı ve ekran yakalama.
pygetwindow ile pencere bulunur; PIL.ImageGrab ile bölge yakalanır (opsiyonel işleme sonrası metin/veri).
"""
from __future__ import annotations

import importlib
from typing import Any, Optional


class MatriksTerminalAdapter:
    """Matriks terminal penceresine bağlanıp ekran bölgesini yakalayan adaptör (Düzey 2 / VİOP verisi)."""

    def __init__(self) -> None:
        self.window: Optional[Any] = None

    def connect(self, title: str = "Matriks") -> None:
        """Pencere başlığı ile Matriks terminal penceresini bulur ve atar."""
        try:
            gw = importlib.import_module("pygetwindow")
        except ImportError:
            raise ImportError("pygetwindow module is not available")
        wins = gw.getWindowsWithTitle(title)
        if not wins:
            raise RuntimeError("Matriks window not found")
        self.window = wins[0]

    def get_data(self) -> Any:
        """Bağlı pencerenin ekran görüntüsünü döner. Gerçek senaryoda görüntü işlenip metin/veri çıkarılabilir."""
        if not self.window:
            raise RuntimeError("Not connected to Matriks terminal")
        try:
            ImageGrab = importlib.import_module("PIL.ImageGrab")
        except ImportError:
            raise ImportError("PIL ImageGrab module is not available")
        bbox = (
            self.window.left,
            self.window.top,
            self.window.left + getattr(self.window, "width", 0),
            self.window.top + getattr(self.window, "height", 0),
        )
        img = ImageGrab.grab(bbox=bbox)
        return img
