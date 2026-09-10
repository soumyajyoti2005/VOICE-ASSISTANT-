import asyncio
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional, Callable, AsyncGenerator
import numpy as np
import pyaudio

from backend.config import config


@dataclass
class AudioChunk:
    data: bytes
    timestamp: float
    sample_rate: int


class AudioCapture:
    def __init__(
        self,
        sample_rate: int = None,
        channels: int = None,
        chunk_size: int = None,
        on_chunk: Optional[Callable[[AudioChunk], None]] = None,
    ):
        self.sample_rate = sample_rate or config.audio_sample_rate
        self.channels = channels or config.audio_channels
        self.chunk_size = chunk_size or config.audio_chunk_size
        self.on_chunk = on_chunk
        self._stream: Optional[pyaudio.Stream] = None
        self._pyaudio: Optional[pyaudio.PyAudio] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        try:
            self._pyaudio = pyaudio.PyAudio()
            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._callback,
            )
            self._running = True
        except Exception as e:
            print(f"Warning: AudioCapture could not initialize mic hardware ({e}). Server will continue.")
            self._running = False

    def _callback(self, in_data, frame_count, time_info, status):
        if getattr(self, '_frame_counter', None) is None:
            self._frame_counter = 0
        self._frame_counter += 1
        if self._frame_counter % 50 == 0:
            import numpy as np
            samples = np.frombuffer(in_data, dtype=np.int16)
            energy = float(np.sqrt(np.mean(samples.astype(np.float32)**2))) / 32768.0 if len(samples) > 0 else 0
            print(f"[AudioCapture] Energy: {energy:.4f}")

        if self._running and self.on_chunk:
            chunk = AudioChunk(
                data=in_data,
                timestamp=time.time(),
                sample_rate=self.sample_rate,
            )
            self.on_chunk(chunk)
        return (None, pyaudio.paContinue)

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pyaudio:
            self._pyaudio.terminate()
            self._pyaudio = None


class AudioPlayback:
    def __init__(
        self,
        sample_rate: int = None,
        channels: int = None,
    ):
        self.sample_rate = sample_rate or config.rime_sample_rate
        self.channels = channels or config.audio_channels
        self._stream: Optional[pyaudio.Stream] = None
        self._pyaudio: Optional[pyaudio.PyAudio] = None
        self._buffer = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_playing_chunk = False

    def start(self):
        if self._running:
            return
        try:
            self._pyaudio = pyaudio.PyAudio()
            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
            )
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._playback_loop, daemon=True)
            self._thread.start()
        except Exception as e:
            print(f"Warning: AudioPlayback could not initialize speaker hardware ({e}). Playback via local hardware disabled.")
            self._running = False

    def _playback_loop(self):
        while self._running or not self._buffer.empty():
            try:
                chunk = self._buffer.get(timeout=0.1)
                if chunk is None:
                    break
                if self._stream and self._running:
                    self._is_playing_chunk = True
                    self._stream.write(chunk)
                    self._is_playing_chunk = False
            except queue.Empty:
                continue
            except Exception:
                self._is_playing_chunk = False
                break

    def write(self, data: bytes):
        if self._running:
            self._buffer.put(data)

    def clear_buffer(self):
        while not self._buffer.empty():
            try:
                self._buffer.get_nowait()
            except queue.Empty:
                break

    def stop(self):
        self._running = False
        self._stop_event.set()
        self.clear_buffer()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pyaudio:
            self._pyaudio.terminate()
            self._pyaudio = None

    def is_playing(self) -> bool:
        return self._is_playing_chunk



class FullDuplexAudio:
    def __init__(
        self,
        on_input_chunk: Optional[Callable[[AudioChunk], None]] = None,
    ):
        self.capture = AudioCapture(on_chunk=on_input_chunk)
        self.playback = AudioPlayback()
        self._vad_buffer = bytearray()
        self._vad_threshold = config.vad_threshold

    def start(self):
        self.capture.start()
        self.playback.start()

    def stop(self):
        self.capture.stop()
        self.playback.stop()

    def write_playback(self, data: bytes):
        self.playback.write(data)

    def stop_playback_immediately(self):
        self.playback.clear_buffer()

    def is_playing(self) -> bool:
        return not self.playback._buffer.empty() or self.playback.is_playing()