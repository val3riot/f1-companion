from __future__ import annotations

import asyncio
import inspect
import os
import string
import tempfile
from typing import Any

import httpx

from .config import settings


def is_meaningful_transcript(text: str) -> bool:
    compact = text.strip().strip(string.punctuation + " ")
    if not compact:
        return False
    words = [
        token
        for token in text.replace("'", " ").split()
        if any(character.isalnum() for character in token)
    ]
    return len(words) >= 2 or (len(words) == 1 and len(words[0]) >= 3)


class RadioTranscriptionUnavailable(RuntimeError):
    pass


class TeamRadioTranscriber:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(60))
        self._local_model: Any | None = None

    async def close(self) -> None:
        await self._http.aclose()

    def enabled(self) -> bool:
        if settings.team_radio_transcription_provider == "local":
            return True
        return bool(settings.openai_api_key)

    async def transcribe(self, radio: dict[str, Any]) -> dict[str, str]:
        url = radio.get("url")
        if not isinstance(url, str) or not url:
            raise RadioTranscriptionUnavailable(
                "Clip team radio senza URL audio"
            )

        audio = await self._download_audio(url)
        provider = settings.team_radio_transcription_provider
        if provider == "local":
            transcript = await self._transcribe_audio_local(audio)
        elif provider == "openai":
            transcript = await self._transcribe_audio_openai(audio)
        else:
            raise RadioTranscriptionUnavailable(
                f"Provider trascrizione non supportato: {provider}"
            )
        if not is_meaningful_transcript(transcript):
            raise RadioTranscriptionUnavailable(
                "Trascrizione non significativa per questa clip"
            )
        translation = (
            await self._maybe_translate_to_italian(transcript)
            if settings.team_radio_auto_translate_enabled
            else ""
        )
        return {
            "transcript": transcript,
            "translation_it": translation,
        }

    async def translate_to_italian(self, text: str) -> str:
        if not text.strip():
            raise RadioTranscriptionUnavailable("Transcript vuoto")
        translation = await self._maybe_translate_to_italian(text)
        if not translation.strip():
            raise RadioTranscriptionUnavailable(
                "Traduzione non configurata o vuota"
            )
        return translation

    async def _download_audio(self, url: str) -> bytes:
        try:
            response = await self._http.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 402, 403):
                raise RadioTranscriptionUnavailable(
                    "Clip team radio non accessibile da F1 Live Timing"
                ) from exc
            if exc.response.status_code == 404:
                raise RadioTranscriptionUnavailable(
                    "Clip team radio non trovata su F1 Live Timing"
                ) from exc
            raise
        return response.content

    async def _transcribe_audio_openai(self, audio: bytes) -> str:
        if not settings.openai_api_key:
            raise RadioTranscriptionUnavailable(
                "OPENAI_API_KEY non configurata"
            )
        response = await self._http.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            data={
                "model": settings.openai_transcription_model,
                "response_format": "text",
                "prompt": (
                    "Formula 1 team radio. Keep driver abbreviations, tyre "
                    "compound names, lap references and pit commands accurate."
                ),
            },
            files={
                "file": ("team-radio.mp3", audio, "audio/mpeg"),
            },
        )
        response.raise_for_status()
        return response.text.strip()

    async def _transcribe_audio_local(self, audio: bytes) -> str:
        return await asyncio.to_thread(self._transcribe_audio_local_sync, audio)

    def _transcribe_audio_local_sync(self, audio: bytes) -> str:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RadioTranscriptionUnavailable(
                "faster-whisper non installato. Esegui: pip install -e \".[dev]\""
            ) from exc

        if self._local_model is None:
            self._local_model = WhisperModel(
                settings.team_radio_local_whisper_model,
                device=settings.team_radio_local_whisper_device,
                compute_type=settings.team_radio_local_whisper_compute_type,
            )

        path = self._write_temp_audio(audio)
        try:
            transcript = self._best_local_transcript(path)
        finally:
            os.unlink(path)

        if not is_meaningful_transcript(transcript):
            raise RadioTranscriptionUnavailable(
                "Trascrizione locale non significativa per questa clip"
            )
        return transcript

    def _best_local_transcript(self, path: str) -> str:
        attempts = [
            {
                "language": "en",
                "vad_filter": False,
                "condition_on_previous_text": False,
                "no_speech_threshold": 0.15,
            },
            {
                "language": "en",
                "vad_filter": True,
                "condition_on_previous_text": False,
                "no_speech_threshold": 0.2,
            },
            {
                "vad_filter": False,
                "condition_on_previous_text": False,
                "no_speech_threshold": 0.1,
            },
        ]
        best = ""
        for options in attempts:
            segments, _ = self._local_model.transcribe(
                path,
                beam_size=5,
                temperature=(0.0, 0.2, 0.4),
                initial_prompt=(
                    "Formula 1 team radio. Short noisy radio message. "
                    "Transcribe spoken English commands, driver feedback, "
                    "pit instructions, tyre references and lap references."
                ),
                **options,
            )
            transcript = " ".join(
                segment.text.strip()
                for segment in segments
                if segment.text.strip()
            ).strip()
            if is_meaningful_transcript(transcript):
                return transcript
            if len(transcript) > len(best):
                best = transcript
        return best

    def _write_temp_audio(self, audio: bytes) -> str:
        with tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False,
        ) as file:
            file.write(audio)
            return file.name

    async def _maybe_translate_to_italian(self, text: str) -> str:
        if settings.team_radio_translation_provider == "none":
            return ""
        if settings.team_radio_translation_provider != "openai":
            if settings.team_radio_translation_provider == "googletrans":
                return await self._translate_to_italian_googletrans(text)
            raise RadioTranscriptionUnavailable(
                "Provider traduzione non supportato: "
                f"{settings.team_radio_translation_provider}"
            )
        if not settings.openai_api_key:
            return ""
        return await self._translate_to_italian_openai(text)

    async def _translate_to_italian_googletrans(self, text: str) -> str:
        try:
            from googletrans import Translator
        except ImportError as exc:
            raise RadioTranscriptionUnavailable(
                "googletrans non installato. Esegui: pip install -e \".[dev]\""
            ) from exc

        translator = Translator()
        try:
            result = translator.translate(text, dest="it")
            if inspect.isawaitable(result):
                result = await result
            translated = getattr(result, "text", "")
        finally:
            client = getattr(translator, "client", None)
            close = getattr(client, "aclose", None)
            if close:
                closed = close()
                if inspect.isawaitable(closed):
                    await closed
        if not isinstance(translated, str) or not translated.strip():
            raise RadioTranscriptionUnavailable(
                "Traduzione googletrans vuota"
            )
        return translated.strip()

    async def _translate_to_italian_openai(self, text: str) -> str:
        response = await self._http.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_translation_model,
                "input": (
                    "Traduci in italiano questa comunicazione team radio F1. "
                    "Mantieni sigle pilota, nomi mescola, numeri giro e comandi "
                    "tecnici. Rispondi solo con la traduzione.\n\n"
                    f"{text}"
                ),
            },
        )
        response.raise_for_status()
        body = response.json()
        output_text = body.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        return self._extract_response_text(body).strip()

    def _extract_response_text(self, body: dict[str, Any]) -> str:
        chunks: list[str] = []
        for item in body.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)
