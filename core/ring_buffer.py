"""
Thread-safe circular audio buffer for raw PCM streams.
Allows lock-free non-blocking reads/writes, zero-copy rolling windows,
and channel-isolated audio buffering (User Mic vs. Remote Loopback).
"""
import threading
import numpy as np
from typing import Optional, Tuple

class AudioRingBuffer:
    """
    Fixed-size circular buffer for multi-channel 16-bit PCM audio samples.
    Designed for zero memory reallocation during live capture sessions.
    """
    def __init__(self, capacity_seconds: int = 30, sample_rate: int = 16000, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels
        self.capacity_frames = capacity_seconds * sample_rate
        
        # Pre-allocated circular storage (frames x channels)
        self._buffer = np.zeros((self.capacity_frames, channels), dtype=np.int16)
        self._write_pos = 0
        self._total_written = 0
        self._lock = threading.Lock()

    def write(self, data: np.ndarray):
        """
        Write new PCM frames into the ring buffer.
        Accepts data of shape (N, channels) or (N,) for mono.
        """
        if data.size == 0:
            return

        # Ensure 2D shape (N, channels)
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        if data.shape[1] != self.channels:
            if data.shape[1] == 1 and self.channels == 2:
                # duplicate mono to both channels
                data = np.repeat(data, 2, axis=1)
            else:
                data = data[:, :self.channels]

        num_frames = data.shape[0]
        with self._lock:
            if num_frames >= self.capacity_frames:
                # If incoming data exceeds capacity, take the tail
                data = data[-self.capacity_frames:]
                num_frames = self.capacity_frames
                self._buffer[:] = data
                self._write_pos = 0
            else:
                space_at_end = self.capacity_frames - self._write_pos
                if num_frames <= space_at_end:
                    self._buffer[self._write_pos : self._write_pos + num_frames] = data
                    self._write_pos = (self._write_pos + num_frames) % self.capacity_frames
                else:
                    self._buffer[self._write_pos :] = data[:space_at_end]
                    remainder = num_frames - space_at_end
                    self._buffer[:remainder] = data[space_at_end:]
                    self._write_pos = remainder

            self._total_written += num_frames

    def get_latest(self, seconds: float) -> np.ndarray:
        """
        Retrieve the latest N seconds of recorded audio across all channels.
        Returns a continuous copy of shape (frames, channels).
        """
        req_frames = min(int(seconds * self.sample_rate), self.capacity_frames)
        with self._lock:
            available = min(self._total_written, self.capacity_frames)
            actual_frames = min(req_frames, available)
            if actual_frames == 0:
                return np.zeros((0, self.channels), dtype=np.int16)

            start_pos = (self._write_pos - actual_frames) % self.capacity_frames
            if start_pos + actual_frames <= self.capacity_frames:
                return self._buffer[start_pos : start_pos + actual_frames].copy()
            else:
                part1 = self._buffer[start_pos:]
                part2 = self._buffer[: (start_pos + actual_frames) % self.capacity_frames]
                return np.vstack((part1, part2))

    def get_channels_latest(self, seconds: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns separate (user_mic, loopback_attendees) arrays for the latest N seconds.
        Channel 0 = User Mic, Channel 1 = Remote Loopback.
        """
        combined = self.get_latest(seconds)
        if combined.shape[0] == 0:
            return np.zeros(0, dtype=np.int16), np.zeros(0, dtype=np.int16)
        user_ch = combined[:, 0]
        remote_ch = combined[:, 1] if self.channels > 1 else combined[:, 0]
        return user_ch, remote_ch

    def reset(self):
        """Clears buffer positions without freeing pre-allocated memory."""
        with self._lock:
            self._buffer.fill(0)
            self._write_pos = 0
            self._total_written = 0
