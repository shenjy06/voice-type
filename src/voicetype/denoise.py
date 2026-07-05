"""Lightweight spectral-gate noise reduction (numpy-only).

Self-contained stationary noise suppression that avoids pulling scipy or
noisereduce into the bundle — the PyInstaller spec explicitly excludes
scipy to keep the EXE small. Designed for 16 kHz mono speech, the
dictation use case where the goal is to clean steady background noise
(fans, AC, mains hum) before sending audio to the ASR provider.

Algorithm:
    1. STFT with a periodic Hann window at 75% overlap.
    2. Estimate a per-frequency noise floor from the quietest frames.
    3. Apply a soft spectral gate: pass through where |X| exceeds the
       noise floor times a threshold; attenuate elsewhere.
    4. Reconstruct via overlap-add ISTFT with window-squared normalization.

Limitation: spectral gating targets *stationary* noise — sounds whose
spectrum stays roughly constant over time (fans, AC, hum). Transient
sounds (keyboard clicks, coughs, door slams) are NOT handled well; a
deep-learning denoiser (RNNoise, DeepFilterNet) would be needed for
those. This module is a lightweight, zero-dependency baseline — good
enough for the common dictation scenario, not the best available.

Best-effort: any unexpected failure returns the input untouched so the
recording pipeline is never broken by denoising.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Strength presets — tuned for 16 kHz mono speech.
#   threshold     — gate opens at noise_floor * threshold
#   attenuation   — gain applied where gate is closed (0.1 ≈ -20 dB)
#   noise_frames  — number of quietest frames averaged for the noise profile
_STRENGTH_PRESETS: dict[str, dict[str, float]] = {
    "low":    {"threshold": 1.3, "attenuation": 0.35, "noise_frames": 6.0},
    "medium": {"threshold": 1.6, "attenuation": 0.12, "noise_frames": 6.0},
    "high":   {"threshold": 2.1, "attenuation": 0.05, "noise_frames": 8.0},
}

# STFT parameters — periodic Hann at 75% overlap. The window-squared sum
# is constant in the signal interior, giving clean reconstruction; edge
# samples are handled by explicit normalization in ``_istft``.
_N_FFT = 512
_HOP_LENGTH = 128


def _periodic_hann(n_fft: int) -> np.ndarray:
    """Return the periodic Hann window of length ``n_fft``.

    Unlike the symmetric ``np.hanning(n_fft)`` (which is zero at both
    ends), the periodic variant is zero only at index 0 — the form used
    by librosa/scipy.signal for STFT analysis frames.
    """
    return np.hanning(n_fft + 1)[:-1]


def _stft(x: np.ndarray, n_fft: int, hop_length: int) -> np.ndarray:
    """Compute the STFT as a complex matrix of shape (n_frames, n_fft // 2 + 1).

    The signal is padded at the tail so every original sample is covered
    by at least one analysis frame.
    """
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    # Pad the tail to a whole number of hops beyond the first frame so
    # the last few samples are not silently dropped.
    remainder = (len(x) - n_fft) % hop_length
    if remainder > 0:
        x = np.pad(x, (0, hop_length - remainder))
    n_frames = 1 + (len(x) - n_fft) // hop_length

    window = _periodic_hann(n_fft)
    frames = np.empty((n_frames, n_fft), dtype=np.float64)
    for i in range(n_frames):
        start = i * hop_length
        frames[i] = x[start:start + n_fft] * window
    return np.fft.rfft(frames, axis=1)


def _istft(spec: np.ndarray, n_fft: int, hop_length: int, length: int) -> np.ndarray:
    """Invert ``_stft`` via overlap-add with window-squared normalization."""
    window = _periodic_hann(n_fft)
    n_frames = spec.shape[0]
    out_len = (n_frames - 1) * hop_length + n_fft
    x = np.zeros(out_len, dtype=np.float64)
    w_sum = np.zeros(out_len, dtype=np.float64)
    frames = np.fft.irfft(spec, n=n_fft, axis=1)
    for i in range(n_frames):
        start = i * hop_length
        x[start:start + n_fft] += frames[i] * window
        w_sum[start:start + n_fft] += window * window
    # Where the window-squared sum is ~0 (signal boundaries), output
    # silence rather than amplifying boundary samples.
    w_sum = np.where(w_sum > 1e-8, w_sum, 1.0)
    x = x / w_sum
    return x[:length].astype(np.float32)


def _spectral_gate(
    audio: np.ndarray,
    sample_rate: int,
    *,
    threshold: float,
    attenuation: float,
    noise_frames: int,
    n_fft: int = _N_FFT,
    hop_length: int = _HOP_LENGTH,
) -> np.ndarray:
    """Apply spectral-gate noise reduction to mono float audio."""
    if audio.size == 0:
        return np.asarray(audio, dtype=np.float32)
    # Flatten multi-channel input to mono by averaging channels.
    if audio.ndim > 1:
        audio = audio.mean(axis=tuple(range(1, audio.ndim)))
    audio = np.ascontiguousarray(audio, dtype=np.float64)
    original_length = audio.size
    if original_length < n_fft:
        # Too short for a single analysis frame — nothing to denoise.
        return audio.astype(np.float32)

    spec = _stft(audio, n_fft, hop_length)
    mag = np.abs(spec)

    # Noise floor: average magnitude spectrum of the quietest frames.
    # Robust to recordings that start with speech (no leading silence) —
    # we pick whichever frames are quietest, wherever they sit. Cap at
    # half the frame count so the estimate never includes speech frames
    # in very short clips.
    frame_energy = np.sum(mag * mag, axis=1)
    n_noise = min(noise_frames, max(1, mag.shape[0] // 2))
    quietest = np.argsort(frame_energy)[:n_noise]
    noise_floor = np.mean(mag[quietest], axis=0)

    # Soft gate: smooth transition from ``attenuation`` to 1.0 around the
    # threshold. A hard binary gate produces "musical noise" artifacts;
    # the smoothed step avoids them without extra cost.
    ratio = mag / (noise_floor + 1e-10)
    width = max(0.25, threshold * 0.25)
    gate = np.clip((ratio - (threshold - width)) / (2.0 * width), 0.0, 1.0)
    gain = attenuation + (1.0 - attenuation) * gate

    spec_denoised = spec * gain
    return _istft(spec_denoised, n_fft, hop_length, length=original_length)


def denoise(audio: np.ndarray, sample_rate: int, strength: str = "medium") -> np.ndarray:
    """Denoise mono audio with a named strength preset.

    Returns audio of the same length and dtype (float32) as the input.
    Multi-channel input is flattened to mono (by averaging channels)
    before processing — downstream ASR expects mono anyway.

    On any unexpected failure, returns the original audio unchanged so
    the recording pipeline is never broken by denoising.
    """
    preset = _STRENGTH_PRESETS.get(strength, _STRENGTH_PRESETS["medium"])
    try:
        # Flatten to mono up front so the length check below compares
        # against the mono length consistently.
        audio = np.asarray(audio, dtype=np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=tuple(range(1, audio.ndim)))
        original_length = audio.size

        result = _spectral_gate(
            audio,
            sample_rate,
            threshold=float(preset["threshold"]),
            attenuation=float(preset["attenuation"]),
            noise_frames=int(preset["noise_frames"]),
        )
        if result.size != original_length:
            logger.warning(
                "Denoise length mismatch (%d vs %d) — using original",
                result.size,
                original_length,
            )
            return audio
        return result
    except Exception as e:
        logger.warning("Denoise failed (%s) — using original audio", e)
        return np.asarray(audio, dtype=np.float32)
