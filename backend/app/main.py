from contextlib import asynccontextmanager
from datetime import datetime
import asyncio
import json
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from .f1signal import F1SignalRTranslator
from .config import settings
from .openf1 import OpenF1Client
from .history import build_circuit_history
from .jolpica import JolpicaClient
from .predictions import PredictionService
from .radio_transcription import (
    RadioTranscriptionUnavailable,
    TeamRadioTranscriber,
)
from .telemetry import FastF1Service, TelemetryUnavailable
from .weather import WeatherClient


client = OpenF1Client()
jolpica = JolpicaClient()
telemetry = FastF1Service()
weather = WeatherClient()
predictions = PredictionService(jolpica, telemetry, weather)
f1signal = F1SignalRTranslator()
radio_transcriber = TeamRadioTranscriber()
radio_transcription_tasks: dict[str, asyncio.Task] = {}
radio_transcription_semaphore = asyncio.Semaphore(
    max(1, settings.team_radio_auto_transcription_concurrency)
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    for task in radio_transcription_tasks.values():
        task.cancel()
    f1signal.stop()
    await client.close()
    await jolpica.close()
    await weather.close()
    await radio_transcriber.close()


app = FastAPI(
    title="F1 Companion API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", include_in_schema=False)
@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def race_datetime(race: dict[str, Any]) -> datetime:
    time = race.get("time", "12:00:00Z").replace("Z", "+00:00")
    return datetime.fromisoformat(f"{race['date']}T{time}")


@app.get("/api/seasons")
async def seasons() -> dict[str, list[int]]:
    current_year = datetime.now().year
    return {"seasons": list(range(current_year, 2022, -1))}


@app.get("/api/circuits")
async def circuits():
    try:
        rows = await jolpica.circuits()
        return [
            {
                "id": row["circuitId"],
                "name": row["circuitName"],
                "locality": row["Location"]["locality"],
                "country": row["Location"]["country"],
            }
            for row in rows
        ]
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Jolpica non è raggiungibile",
        ) from exc


@app.get("/api/circuits/{circuit_id}/history")
async def circuit_history(circuit_id: str):
    try:
        return await build_circuit_history(circuit_id, jolpica, client)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Le fonti storiche F1 non sono raggiungibili",
        ) from exc


@app.get("/api/circuits/{circuit_id}/layout")
async def circuit_layout(
    circuit_id: str,
    year: int = Query(ge=2018, le=2100),
):
    try:
        races = await jolpica.season_schedule(year)
        race = next(
            (
                item
                for item in races
                if item["Circuit"]["circuitId"] == circuit_id
            ),
            None,
        )
        if race is None:
            raise ValueError("Circuito non presente nella stagione selezionata")
        return await telemetry.circuit_layout(year, int(race["round"]))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TelemetryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Calendario F1 non raggiungibile",
        ) from exc


@app.get("/api/analysis/events")
async def analysis_events(year: int = Query(ge=2018, le=2100)):
    try:
        races = await jolpica.season_schedule(year)
        now = datetime.now().astimezone()
        return [
            {
                "round": int(race["round"]),
                "name": race["raceName"],
                "date": race["date"],
                "circuit": race["Circuit"]["circuitName"],
                "completed": race_datetime(race) < now,
            }
            for race in races
        ]
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Calendario F1 non raggiungibile",
        ) from exc


@app.get("/api/analysis/sessions")
async def analysis_sessions(
    year: int = Query(ge=2018, le=2100),
    round_number: int = Query(ge=1, le=30),
):
    try:
        return await telemetry.available_sessions(year, round_number)
    except TelemetryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/analysis/post-race")
async def post_race_analysis(
    year: int = Query(ge=2018, le=2100),
    round_number: int = Query(ge=1, le=30),
    telemetry_session: Literal[
        "fp1",
        "fp2",
        "fp3",
        "sprint_qualifying",
        "sprint",
        "qualifying",
        "race",
    ] = "race",
    lap_mode: Literal["best", "number"] = "best",
    lap_number: int | None = Query(default=None, ge=1, le=200),
):
    try:
        return await telemetry.post_race(
            year, round_number, telemetry_session, lap_mode, lap_number
        )
    except TelemetryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/predictions/next-race")
async def next_race_prediction(
    year: int = Query(default_factory=lambda: datetime.now().year, ge=2018),
    include_practice: bool = True,
):
    try:
        return await predictions.next_race(year, include_practice)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Dati del campionato non raggiungibili",
        ) from exc


@app.get("/api/predictions/features")
async def prediction_features(
    year: int = Query(default_factory=lambda: datetime.now().year, ge=2018),
    min_prior_races: int = Query(default=3, ge=1, le=12),
    include_rows: bool = False,
    limit: int = Query(default=200, ge=1, le=2000),
):
    try:
        return await predictions.feature_dataset(
            year,
            min_prior_races,
            include_rows,
            limit,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Dati del campionato non raggiungibili",
        ) from exc


@app.get("/api/meetings")
async def meetings(year: int = Query(ge=2023, le=2100)):
    return await proxy("meetings", {"year": year}, ttl=3600)


@app.get("/api/sessions")
async def sessions(meeting_key: int):
    return await proxy(
        "sessions", {"meeting_key": meeting_key}, ttl=3600
    )


@app.get("/api/snapshot")
async def snapshot(session_key: int, at: datetime | None = None):
    try:
        return await client.snapshot(session_key, at)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = "OpenF1 non ha reso disponibili questi dati"
        if exc.response.status_code in (401, 402, 403):
            detail = "I dati live richiedono un accesso OpenF1 Sponsor"
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=detail,
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="OpenF1 non è raggiungibile",
        ) from exc


@app.get("/api/f1signal/status")
async def f1signal_status():
    return f1signal.status()


@app.get("/api/f1signal/snapshot")
async def f1signal_snapshot(wait: bool = True):
    f1signal.start()
    if wait:
        await f1signal.wait_for_first_message()
    snapshot = f1signal.snapshot(archive=True)
    f1signal.hydrate_team_radio_transcription_cache(snapshot)
    schedule_team_radio_transcriptions(snapshot)
    return snapshot


@app.get("/api/f1signal/stream")
async def f1signal_stream(interval: float = Query(default=1, ge=0.25, le=10)):
    async def events():
        f1signal.start()
        await f1signal.wait_for_first_message()
        while True:
            snapshot = f1signal.snapshot(archive=True)
            f1signal.hydrate_team_radio_transcription_cache(snapshot)
            schedule_team_radio_transcriptions(snapshot)
            payload = json.dumps(snapshot, default=str)
            yield f"event: snapshot\ndata: {payload}\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/api/f1signal/team-radio/transcribe")
async def transcribe_team_radio(path: str):
    radio = f1signal.team_radio_by_path(path)
    if radio is None:
        raise HTTPException(status_code=404, detail="Team radio non trovata")
    f1signal.set_team_radio_transcription_status(path, "transcribing")
    try:
        result = await radio_transcriber.transcribe(radio)
    except RadioTranscriptionUnavailable as exc:
        f1signal.set_team_radio_transcription_status(path, "error", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        f1signal.set_team_radio_transcription_status(
            path,
            "error",
            "Trascrizione OpenAI non disponibile",
        )
        raise HTTPException(
            status_code=502,
            detail="Trascrizione OpenAI non disponibile",
        ) from exc
    except httpx.HTTPError as exc:
        f1signal.set_team_radio_transcription_status(
            path,
            "error",
            "Audio team radio o OpenAI non raggiungibile",
        )
        raise HTTPException(
            status_code=502,
            detail="Audio team radio o OpenAI non raggiungibile",
        ) from exc

    updated = f1signal.set_team_radio_text(
        path,
        result["transcript"],
        result["translation_it"],
    )
    snapshot = f1signal.snapshot()
    f1signal.cache_team_radio_transcription(
        snapshot.get("session", {}),
        updated or radio,
        result["transcript"],
        result["translation_it"],
    )
    return updated or {**radio, **result}


@app.post("/api/f1signal/team-radio/translate")
async def translate_team_radio(path: str):
    radio = f1signal.team_radio_by_path(path)
    if radio is None:
        raise HTTPException(status_code=404, detail="Team radio non trovata")
    transcript = radio.get("transcript") or radio.get("message")
    if not isinstance(transcript, str) or not transcript.strip():
        raise HTTPException(
            status_code=409,
            detail="Transcript non ancora disponibile",
        )
    try:
        translation = await radio_transcriber.translate_to_italian(transcript)
    except RadioTranscriptionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail="Traduzione non disponibile",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Servizio traduzione non raggiungibile",
        ) from exc

    updated = f1signal.set_team_radio_text(path, transcript, translation)
    snapshot = f1signal.snapshot()
    f1signal.cache_team_radio_transcription(
        snapshot.get("session", {}),
        updated or radio,
        transcript,
        translation,
    )
    return updated or {**radio, "translation_it": translation}


def schedule_team_radio_transcriptions(snapshot: dict) -> None:
    if not settings.team_radio_auto_transcription_enabled:
        return
    if not radio_transcriber.enabled():
        return
    for radio in snapshot.get("team_radio", []):
        path = radio.get("path")
        url = radio.get("url")
        status = radio.get("transcription_status")
        attempts = int(radio.get("transcription_attempts") or 0)
        if not isinstance(path, str) or not path:
            continue
        if not isinstance(url, str) or not url:
            continue
        if radio.get("transcript") or status in {"queued", "transcribing", "done"}:
            continue
        if status == "error" and attempts >= 2:
            continue
        if path in radio_transcription_tasks:
            continue
        f1signal.set_team_radio_transcription_status(path, "queued")
        radio_transcription_tasks[path] = asyncio.create_task(
            transcribe_team_radio_background(path)
        )


async def transcribe_team_radio_background(path: str) -> None:
    async with radio_transcription_semaphore:
        radio = f1signal.team_radio_by_path(path)
        if radio is None:
            radio_transcription_tasks.pop(path, None)
            return
        f1signal.set_team_radio_transcription_status(path, "transcribing")
        try:
            result = await radio_transcriber.transcribe(radio)
        except Exception as exc:
            f1signal.set_team_radio_transcription_status(
                path,
                "error",
                str(exc),
            )
        else:
            updated = f1signal.set_team_radio_text(
                path,
                result["transcript"],
                result["translation_it"],
            )
            snapshot = f1signal.snapshot()
            f1signal.cache_team_radio_transcription(
                snapshot.get("session", {}),
                updated or radio,
                result["transcript"],
                result["translation_it"],
            )
        finally:
            radio_transcription_tasks.pop(path, None)


async def proxy(endpoint: str, params: dict, ttl: int):
    try:
        return await client.get(endpoint, params, ttl)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="OpenF1 non è raggiungibile",
        ) from exc
