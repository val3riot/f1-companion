from types import SimpleNamespace
import sys

import httpx
import pytest

from app import radio_transcription
from app.radio_transcription import (
    RadioTranscriptionUnavailable,
    TeamRadioTranscriber,
    is_meaningful_transcript,
)


@pytest.mark.asyncio
async def test_team_radio_transcriber_uses_local_provider_without_openai(monkeypatch):
    monkeypatch.setattr(
        radio_transcription,
        "settings",
        SimpleNamespace(
            team_radio_transcription_provider="local",
            team_radio_translation_provider="openai",
            team_radio_auto_translate_enabled=False,
            openai_api_key=None,
        ),
    )
    transcriber = TeamRadioTranscriber()

    async def download_audio(_: str) -> bytes:
        return b"audio"

    async def transcribe_audio_local(_: bytes) -> str:
        return "Box this lap"

    monkeypatch.setattr(transcriber, "_download_audio", download_audio)
    monkeypatch.setattr(transcriber, "_transcribe_audio_local", transcribe_audio_local)

    try:
        result = await transcriber.transcribe({"url": "https://example.test/radio.mp3"})
    finally:
        await transcriber.close()

    assert result == {
        "transcript": "Box this lap",
        "translation_it": "",
    }


def test_team_radio_rejects_punctuation_only_transcripts():
    assert is_meaningful_transcript(". . . . . . . . .") is False
    assert is_meaningful_transcript("Box this lap") is True


def test_local_transcriber_retries_when_first_pass_is_punctuation():
    class Segment:
        def __init__(self, text: str):
            self.text = text

    class FakeModel:
        def __init__(self):
            self.calls = 0

        def transcribe(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return [Segment(". . . . .")], None
            return [Segment("Box this lap")], None

    transcriber = TeamRadioTranscriber()
    transcriber._local_model = FakeModel()

    assert transcriber._best_local_transcript("/tmp/fake.mp3") == "Box this lap"


@pytest.mark.asyncio
async def test_team_radio_download_rejects_forbidden_f1_audio():
    transcriber = TeamRadioTranscriber()
    await transcriber.close()

    class FakeClient:
        async def get(self, url: str):
            request = httpx.Request("GET", url)
            return httpx.Response(403, request=request)

    transcriber._http = FakeClient()

    with pytest.raises(RadioTranscriptionUnavailable) as exc_info:
        await transcriber._download_audio(
            "https://livetiming.formula1.com/static/radio.mp3"
        )

    assert str(exc_info.value) == (
        "Clip team radio non accessibile da F1 Live Timing"
    )


@pytest.mark.asyncio
async def test_team_radio_transcriber_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(
        radio_transcription,
        "settings",
        SimpleNamespace(
            team_radio_transcription_provider="unknown",
            team_radio_translation_provider="none",
            team_radio_auto_translate_enabled=False,
            openai_api_key=None,
        ),
    )
    transcriber = TeamRadioTranscriber()

    async def download_audio(_: str) -> bytes:
        return b"audio"

    monkeypatch.setattr(transcriber, "_download_audio", download_audio)

    try:
        with pytest.raises(RadioTranscriptionUnavailable):
            await transcriber.transcribe({"url": "https://example.test/radio.mp3"})
    finally:
        await transcriber.close()


@pytest.mark.asyncio
async def test_team_radio_transcriber_translates_with_googletrans(monkeypatch):
    class FakeResult:
        text = "Rientra ai box questo giro"

    class FakeTranslator:
        def translate(self, text: str, dest: str):
            assert text == "Box this lap"
            assert dest == "it"
            return FakeResult()

    monkeypatch.setitem(
        sys.modules,
        "googletrans",
        SimpleNamespace(Translator=FakeTranslator),
    )
    monkeypatch.setattr(
        radio_transcription,
        "settings",
        SimpleNamespace(
            team_radio_translation_provider="googletrans",
            openai_api_key=None,
        ),
    )
    transcriber = TeamRadioTranscriber()

    try:
        result = await transcriber.translate_to_italian("Box this lap")
    finally:
        await transcriber.close()

    assert result == "Rientra ai box questo giro"


@pytest.mark.asyncio
async def test_team_radio_translate_rejects_empty_translation(monkeypatch):
    monkeypatch.setattr(
        radio_transcription,
        "settings",
        SimpleNamespace(
            team_radio_translation_provider="openai",
            openai_api_key=None,
        ),
    )
    transcriber = TeamRadioTranscriber()

    try:
        with pytest.raises(RadioTranscriptionUnavailable):
            await transcriber.translate_to_italian("Box this lap")
    finally:
        await transcriber.close()
