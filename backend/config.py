import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    rime_api_key: str
    stt_api_key: str
    llm_api_key: str
    places_api_key: Optional[str] = None

    rime_base_url: str = "https://api.rime.ai/v1"
    stt_base_url: str = "https://api.openai.com/v1"
    llm_base_url: str = "https://api.openai.com/v1"

    rime_voice: str = "rube"
    rime_model: str = "mist"
    rime_sample_rate: int = 24000
    rime_encoding: str = "pcm_s16le"

    stt_model: str = "whisper-1"
    stt_language: str = "en"

    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.7

    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_chunk_size: int = 1024

    vad_threshold: float = 0.5
    vad_silence_duration: float = 0.8

    @classmethod
    def from_env(cls) -> "Config":
        required_keys = {
            "RIME_API_KEY": "rime_api_key",
            "STT_API_KEY": "stt_api_key",
            "LLM_API_KEY": "llm_api_key",
        }

        missing = [key for key in required_keys if not os.getenv(key)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        return cls(
            rime_api_key=os.getenv("RIME_API_KEY"),
            stt_api_key=os.getenv("STT_API_KEY"),
            llm_api_key=os.getenv("LLM_API_KEY"),
            places_api_key=os.getenv("PLACES_API_KEY"),
            rime_base_url=os.getenv("RIME_BASE_URL", "https://api.rime.ai/v1"),
            stt_base_url=os.getenv("STT_BASE_URL", "https://api.openai.com/v1"),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            rime_voice=os.getenv("RIME_VOICE", "rube"),
            rime_model=os.getenv("RIME_MODEL", "mist"),
            rime_sample_rate=int(os.getenv("RIME_SAMPLE_RATE", "24000")),
            rime_encoding=os.getenv("RIME_ENCODING", "pcm_s16le"),
            stt_model=os.getenv("STT_MODEL", "whisper-1"),
            stt_language=os.getenv("STT_LANGUAGE", "en"),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            audio_sample_rate=int(os.getenv("AUDIO_SAMPLE_RATE", "16000")),
            audio_channels=int(os.getenv("AUDIO_CHANNELS", "1")),
            audio_chunk_size=int(os.getenv("AUDIO_CHUNK_SIZE", "1024")),
            vad_threshold=float(os.getenv("VAD_THRESHOLD", "0.5")),
            vad_silence_duration=float(os.getenv("VAD_SILENCE_DURATION", "0.8")),
        )


config = Config.from_env()