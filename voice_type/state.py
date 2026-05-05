"""Application state constants and enums."""

from enum import Enum, auto


class RecorderState(Enum):
    """State machine for the recording workflow."""
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    DONE = auto()
    ERROR = auto()
