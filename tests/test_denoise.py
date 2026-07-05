"""Tests for voicetype.denoise — spectral-gate noise reduction."""

import numpy as np
import pytest

from voicetype.denoise import (
    _istft,
    _spectral_gate,
    _stft,
    _STRENGTH_PRESETS,
    denoise,
)

SAMPLE_RATE = 16000


def _sine(freq: int, duration_s: float, sr: int = SAMPLE_RATE, amp: float = 0.3) -> np.ndarray:
    """Generate a pure sine wave as float32."""
    t = np.arange(int(sr * duration_s)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _white_noise(duration_s: float, sr: int = SAMPLE_RATE, amp: float = 0.05, seed: int = 42) -> np.ndarray:
    """Generate deterministic white noise as float32."""
    rng = np.random.default_rng(seed)
    return (amp * rng.standard_normal(int(sr * duration_s))).astype(np.float32)


class TestDenoiseBasic:
    def test_empty_audio_returns_empty(self):
        result = denoise(np.array([], dtype=np.float32), SAMPLE_RATE)
        assert result.size == 0

    def test_short_audio_returns_unchanged(self):
        """Audio shorter than one analysis frame is returned as-is."""
        audio = _sine(440, 0.01)  # ~10 ms < 32 ms (n_fft at 16 kHz)
        result = denoise(audio, SAMPLE_RATE)
        assert result.size == audio.size
        np.testing.assert_array_equal(result, audio)

    def test_preserves_length(self):
        audio = _sine(440, 1.0) + _white_noise(1.0)
        result = denoise(audio, SAMPLE_RATE, strength="medium")
        assert result.size == audio.size

    def test_returns_float32(self):
        audio = (_sine(440, 1.0) + _white_noise(1.0)).astype(np.float64)
        result = denoise(audio, SAMPLE_RATE)
        assert result.dtype == np.float32

    def test_accepts_float32_input(self):
        audio = _sine(440, 1.0) + _white_noise(1.0)
        result = denoise(audio, SAMPLE_RATE)
        assert result.dtype == np.float32


class TestStftIstftRoundTrip:
    def test_round_trip_reconstructs_interior(self):
        """STFT → ISTFT reconstructs the original signal in the interior.

        Edge samples (first/last n_fft) are excluded because the
        window-squared sum is small there and normalization is imperfect.
        """
        audio = _sine(440, 1.0)
        n_fft, hop = 512, 128
        spec = _stft(audio, n_fft, hop)
        reconstructed = _istft(spec, n_fft, hop, length=audio.size)
        # Interior region has full 4-frame overlap → near-perfect reconstruction.
        margin = 3 * hop
        interior = slice(margin, audio.size - margin)
        np.testing.assert_allclose(
            reconstructed[interior],
            audio[interior],
            atol=1e-3,
        )

    def test_stft_output_shape(self):
        audio = _sine(440, 0.5)
        n_fft, hop = 512, 128
        spec = _stft(audio, n_fft, hop)
        assert spec.shape[1] == n_fft // 2 + 1
        assert spec.ndim == 2


class TestNoiseReduction:
    def test_pure_noise_is_attenuated(self):
        """Denoising a noise-only signal reduces its energy."""
        noise = _white_noise(1.0, amp=0.1)
        result = denoise(noise, SAMPLE_RATE, strength="high")
        # Skip edges (window boundary effects) when comparing energy.
        margin = 512
        in_energy = float(np.sqrt(np.mean(noise[margin:-margin] ** 2)))
        out_energy = float(np.sqrt(np.mean(result[margin:-margin] ** 2)))
        assert out_energy < in_energy * 0.5  # at least halved

    def test_pure_tone_is_preserved(self):
        """A strong tone well above the noise floor survives denoising.

        Real recordings always have a brief noise-only lead before speech
        starts — the quietest frames are picked from there, so a signal
        well above the floor is left untouched. A continuous pure tone
        with no noise floor is an unrealistic edge case that spectral
        gating is not designed for (it cannot distinguish a constant
        tone from stationary noise at the same frequency).
        """
        noise_lead = _white_noise(0.3, amp=0.02)  # 300 ms noise floor
        tone = _sine(440, 1.0, amp=0.3)
        audio = np.concatenate([noise_lead, tone])
        result = denoise(audio, SAMPLE_RATE, strength="medium")
        # Compare energy in the tone-only region (skip edges / transition).
        tone_start = len(noise_lead) + 512
        tone_end = audio.size - 512
        in_energy = float(np.sqrt(np.mean(tone[512:-512] ** 2)))
        out_energy = float(np.sqrt(np.mean(result[tone_start:tone_end] ** 2)))
        # Tone energy should be largely preserved (within ~30 %).
        assert out_energy > in_energy * 0.7

    def test_higher_strength_attenuates_more(self):
        """Stronger presets suppress noise more aggressively."""
        noise = _white_noise(1.0, amp=0.1)
        low = denoise(noise, SAMPLE_RATE, strength="low")
        high = denoise(noise, SAMPLE_RATE, strength="high")
        margin = 512
        low_energy = float(np.sqrt(np.mean(low[margin:-margin] ** 2)))
        high_energy = float(np.sqrt(np.mean(high[margin:-margin] ** 2)))
        assert high_energy < low_energy


class TestStrengthPresets:
    def test_all_presets_present(self):
        for key in ("low", "medium", "high"):
            assert key in _STRENGTH_PRESETS

    def test_unknown_strength_falls_back_to_medium(self):
        """An unknown strength string does not crash — uses medium preset."""
        audio = _sine(440, 0.5) + _white_noise(0.5)
        result = denoise(audio, SAMPLE_RATE, strength="nonsense")
        assert result.size == audio.size
        assert result.dtype == np.float32

    def test_each_strength_runs_without_error(self):
        audio = _sine(440, 0.5) + _white_noise(0.5)
        for strength in ("low", "medium", "high"):
            result = denoise(audio, SAMPLE_RATE, strength=strength)
            assert result.size == audio.size


class TestMultiChannel:
    def test_stereo_flattened_to_mono(self):
        """Multi-channel input is averaged to mono before processing."""
        base = _sine(440, 1.0) + _white_noise(1.0)
        stereo = np.stack([base, base], axis=1)  # shape (N, 2)
        result = denoise(stereo, SAMPLE_RATE, strength="medium")
        assert result.ndim == 1
        assert result.size == base.size


class TestErrorHandling:
    def test_returns_original_on_internal_failure(self, monkeypatch):
        """If the spectral gate raises, denoise returns the input unchanged."""

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("voicetype.denoise._spectral_gate", _boom)
        audio = _sine(440, 1.0)
        result = denoise(audio, SAMPLE_RATE)
        np.testing.assert_array_equal(result, audio)
        assert result.dtype == np.float32

    def test_length_mismatch_returns_original(self, monkeypatch):
        """If the gate returns the wrong length, the original is returned."""

        def _wrong_length(audio, sample_rate, **kwargs):
            return np.zeros(10, dtype=np.float32)

        monkeypatch.setattr("voicetype.denoise._spectral_gate", _wrong_length)
        audio = _sine(440, 1.0)
        result = denoise(audio, SAMPLE_RATE)
        np.testing.assert_array_equal(result, audio)


class TestSpectralGateDirect:
    def test_empty_audio(self):
        result = _spectral_gate(
            np.array([], dtype=np.float32),
            SAMPLE_RATE,
            threshold=1.5,
            attenuation=0.1,
            noise_frames=6,
        )
        assert result.size == 0

    def test_short_audio_returns_float32(self):
        audio = np.zeros(100, dtype=np.float32)
        result = _spectral_gate(
            audio,
            SAMPLE_RATE,
            threshold=1.5,
            attenuation=0.1,
            noise_frames=6,
        )
        assert result.dtype == np.float32
        assert result.size == audio.size
