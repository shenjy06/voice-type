"""Shared icon creation utilities for UI components."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont


def make_circle_icon(text_char: str, bg_color: tuple[int, int, int],
                     size: int = 32, font_size: int = 16,
                     fg_color: tuple[int, int, int] = (255, 255, 255),
                     font_family: str = "Arial") -> QIcon:
    """Create a circular icon with a centered text character.

    Args:
        text_char: Single character or short symbol to display.
        bg_color: RGB tuple for the circle background.
        size: Icon size in pixels (square).
        font_size: Font size for the text character.
        fg_color: RGB tuple for the text color.
        font_family: Font family name.

    Returns:
        QIcon ready for use as window or tray icon.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(*bg_color))
    painter.setPen(Qt.NoPen)

    margin = max(2, size // 16)
    painter.drawEllipse(margin, margin, size - margin * 2, size - margin * 2)

    painter.setPen(QColor(*fg_color))
    font = QFont(font_family, font_size, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, text_char)
    painter.end()
    return QIcon(pixmap)
