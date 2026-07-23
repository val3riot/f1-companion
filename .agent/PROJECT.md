# F1 Insight — agent guide

## Purpose

F1 Insight is a personal Formula 1 analytics application. It combines:

- live timing from the Formula 1 SignalR feed;
- historical results from Jolpica;
- optional session data from OpenF1;
- circuit layouts and telemetry from FastF1;
- post-race analysis and next-race predictions;
- local or OpenAI team-radio transcription and optional Italian translation.

The user-facing language is Italian. Preserve Italian UI copy and API error
messages unless the task explicitly requests another language.

## Repository layout

```text
.
├── backend/                 FastAPI application and Python tests
│   ├── app/
│   │   ├── main.py          API routes, service wiring, background radio jobs
│   │   ├── config.py        Environment-backed settings
│   │   ├── f1signal.py      SignalR connection, topic merge, live snapshots
│   │   ├── signal_archive.py Live snapshot/map/radio cache
│   │   ├── radio_transcription.py  Audio download, Whisper/OpenAI, translation
│   │   ├── jolpica.py       Historical results client
│   │   ├── openf1.py        OpenF1 client and snapshots
│   │   ├── telemetry.py     FastF1 layouts and telemetry
│   │   ├── history.py       Circuit-history aggregation
│   │   ├── predictions.py   Prediction scoring
│   │   ├── upgrades.py      Declared team upgrade data
│   │   └── weather.py       Weather integration
│   └── tests/               Pytest suite, generally one file per module
├── frontend/                React 19 + TypeScript + Vite
│   └── src/
│       ├── App.tsx          Four-view navigation
│       ├── LiveView.tsx     SSE live timing, map, race control, team radio
│       ├── ArchiveView.tsx  Historical circuit view
│       ├── PostRaceView.tsx Post-race analysis
│       ├── PredictionView.tsx Prediction center
│       ├── api.ts           Typed HTTP client
│       ├── types.ts         Shared frontend response shapes
│       └── styles.css       Global styling
├── docs/DOCUMENTAZIONE_TECNICA.md
├── compose.yaml             Stack locale con build delle immagini
├── scripts/ci/              Test, build immagini e validazione provider-neutral
└── run-dev.sh               Generic bootstrap and development launcher
```

## Startup

The preferred command is:

```bash
./run-dev.sh
```

The root script repairs or creates `backend/.venv`, installs Python packages
when required, installs frontend packages when Vite is absent, starts both
services, and stops both if either exits. Backend runs on `127.0.0.1:8000` and
frontend on `127.0.0.1:5173`. Vite proxies `/api` to the backend.

Alternative container startup:

```bash
cp .env.example .env
docker compose up --build
```

The frontend container is Nginx on port 8080 internally and proxies `/api` to
the private `api:8000` service. Local Compose publishes it on
`127.0.0.1:5173`. Production manifests and infrastructure details live in a
separate private repository and must not be added to this public repository.
The public workflow may publish images and send a repository dispatch when
explicitly enabled, but it must never contain deployment-host details.

Do not assume that a running Vite server means the backend is healthy. Check:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/f1signal/status
```

## Validation

Run the narrowest relevant tests during development, then the complete checks
for cross-cutting changes.

```bash
backend/.venv/bin/pytest -q backend/tests/test_f1signal.py
backend/.venv/bin/pytest -q backend/tests/test_radio_transcription.py
backend/.venv/bin/pytest -q backend/tests
npm run lint --prefix frontend
npm run build --prefix frontend
git diff --check
```

Tests must not depend on live internet services. Mock SignalR payloads and HTTP
responses. A manual live-feed smoke test is useful but never replaces tests.

## Backend conventions

- API routes live in `backend/app/main.py` and use the `/api` prefix.
- Convert expected upstream failures into concise Italian `HTTPException`
  details; do not expose tokens, raw upstream bodies, or stack traces.
- Settings belong in `backend/app/config.py`, backed by environment variables.
- Use async I/O for HTTP and route work. CPU/blocking libraries such as local
  Whisper and some FastF1 operations must not block the event loop.
- Preserve upstream degradation: an OpenF1 failure should not prevent Jolpica
  history from loading.
- Cache paths below `backend/.cache/` are runtime data and must not be committed.
- Add or update pytest coverage with behavioral changes.

## Live SignalR flow

The Live view is independent of OpenF1:

```text
F1 SignalR topics
  -> F1SignalRTranslator.apply_message()
  -> merged topic state and accumulators
  -> snapshot()
  -> /api/f1signal/stream (SSE)
  -> LiveView.tsx
```

Important topics include `SessionInfo`, `DriverList`, `TimingData`,
`Position.z`, `CarData.z`, `WeatherData`, `RaceControlMessages`, `LapCount`,
and `TeamRadio`.

SignalR payloads may be full objects or partial/deep updates. Do not replace a
merged dictionary with a partial update. Session changes must reset per-session
accumulators without leaking data from the prior session.

The live track map prefers an official/reference layout. When unavailable, it
uses the chronological `Position.z` history of the car with the most complete
trace. Never create a circuit outline by angle-sorting mixed points from all
cars; that crosses lines on non-convex circuits. Live car coordinates and the
selected layout must share a coordinate system or be explicitly transformed.

## Team-radio flow

`TeamRadio` captures are normalized in `f1signal.py`. Their relative paths are
resolved against the current session static directory. `main.py` schedules
bounded background transcription jobs, and `radio_transcription.py` downloads
and transcribes audio. Successful text is saved by `signal_archive.py` and
rehydrated into later snapshots.

Audio can appear on the F1 static host later than its SignalR metadata. Treat
temporary download/transcription errors as recoverable and retain manual retry.
Do not mark punctuation, empty output, or obvious silence as a successful
transcript. Keep local Whisper work off the event loop and preserve the
configured concurrency limit.

## Frontend conventions

- Keep API response types synchronized in `frontend/src/types.ts`.
- Add backend calls through `frontend/src/api.ts`; avoid scattered absolute
  backend URLs because Vite and Docker rely on the `/api` proxy.
- `LiveView` receives snapshots every 0.5 seconds. Avoid resetting local UI
  state or expensive structures on every SSE event.
- Preserve accessibility labels on icon-only buttons.
- Reuse existing CSS patterns and responsive behavior before adding libraries.
- The application intentionally has no client router; `App.tsx` switches the
  four main views with local state.

## External data and temporal behavior

- Jolpica: long historical coverage, incomplete fields in older seasons.
- OpenF1: optional enrichment, rate-limited and potentially sponsor-gated.
- FastF1: large downloads on first access, then local cache.
- F1 SignalR: experimental, session/token dependent, partial outside live
  windows, and subject to payload changes.
- Team-radio audio: may be silent, delayed, forbidden, missing, or noisy.

Code must handle missing data explicitly. Do not fabricate records, telemetry,
coordinates, transcripts, or certainty when an upstream source is incomplete.

## Secrets and local files

Never display or commit `backend/.env`. Sensitive values include:

- `F1_SIGNALR_LOGIN_SESSION`
- `F1_SIGNALR_AUTH_TOKEN`
- `OPENAI_API_KEY`

When inspecting configuration, print only variable names or redact entire
values. A SignalR login session contains a usable subscription JWT even though
the variable name does not contain `TOKEN` or `SECRET`.

Do not delete or overwrite user cache data unless explicitly requested. Avoid
destructive changes to `.venv`, `node_modules`, and `backend/.cache`; the root
launcher already repairs invalid setup in normal use.

## Documentation maintenance

Update `README.md` for user-facing setup or feature changes and
`docs/DOCUMENTAZIONE_TECNICA.md` for architecture, formulas, data contracts,
or known limitations. Update this guide when agent workflow or component
ownership changes.
