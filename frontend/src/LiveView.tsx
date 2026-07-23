import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type { Driver, DriverPoint, Snapshot } from "./types";

type MapPoint = {
  driver_number: number;
  date?: string;
  x: number;
  y: number;
  z?: number;
  mapped_to_track?: boolean;
};

type TimedMapPoint = MapPoint & {
  receivedAt: number;
};

type TrackBounds = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
};

type MapOffset = {
  x: number;
  y: number;
};

type PanState = {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startOffset: MapOffset;
};

type RaceControlMessage = NonNullable<
  NonNullable<Snapshot["race_control"]>["Messages"]
>[number];

const GPS_EXTRAPOLATE_LIMIT_MS = 700;
const GPS_HISTORY_WINDOW_MS = 6000;
const GPS_RENDER_DELAY_MS = 1000;
const GPS_SNAP_DISTANCE = 2500;
const TRACK_LAYOUT_MIN_POINTS = 120;
const TRACK_VIEWBOX_HEIGHT = 380;
const TRACK_VIEWBOX_WIDTH = 1000;
const TRACK_VIEWBOX_PADDING_X = 78;
const TRACK_VIEWBOX_PADDING_Y = 52;

function formatTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString("it-IT", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatGap(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") return "Leader";
  return typeof value === "number" ? `+${value.toFixed(3)}` : value;
}

function formatLapTime(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return "-";
  return typeof value === "number" ? value.toFixed(3) : value;
}

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function teamColor(driver?: Driver) {
  return driver?.team_colour ? `#${driver.team_colour}` : "#747982";
}

function translateRaceMessage(message?: string) {
  if (!message) return "";
  const replacements: Array<[RegExp, string]> = [
    [/\bGREEN LIGHT - PIT EXIT OPEN\b/g, "SEMAFORO VERDE - USCITA PIT APERTA"],
    [/\bPIT EXIT CLOSED\b/g, "USCITA PIT CHIUSA"],
    [/\bCHEQUERED FLAG\b/g, "BANDIERA A SCACCHI"],
    [/\bYELLOW IN TRACK SECTOR\b/g, "GIALLA NEL SETTORE"],
    [/\bDOUBLE YELLOW IN TRACK SECTOR\b/g, "DOPPIA GIALLA NEL SETTORE"],
    [/\bCLEAR IN TRACK SECTOR\b/g, "PISTA LIBERA NEL SETTORE"],
    [/\bTRACK CLEAR\b/g, "PISTA LIBERA"],
    [/\bWAVED BLUE FLAG FOR CAR\b/g, "BANDIERA BLU PER LA VETTURA"],
    [/\bBLACK AND WHITE FLAG FOR CAR\b/g, "BANDIERA BIANCA E NERA PER LA VETTURA"],
    [/\bVSC DEPLOYED\b/g, "VSC ATTIVATA"],
    [/\bVSC ENDING\b/g, "VSC IN CHIUSURA"],
    [/\bOVERTAKE DISABLED\b/g, "SORPASSO DISABILITATO"],
    [/\bOVERTAKE ENABLED\b/g, "SORPASSO ABILITATO"],
    [/\bRISK OF RAIN FOR THE F1 RACE IS\b/g, "RISCHIO PIOGGIA PER LA GARA F1:"],
    [/\bAIR TEMPERATURE\b/g, "TEMPERATURA ARIA"],
    [/\bDEGREES\b/g, "GRADI"],
    [/\bINCIDENT INVOLVING CAR\b/g, "INCIDENTE CON VETTURA"],
    [/\bTURN\b/g, "CURVA"],
    [/\bNOTED\b/g, "ANNOTATO"],
    [/\bUNDER INVESTIGATION\b/g, "SOTTO INVESTIGAZIONE"],
    [/\bNO FURTHER ACTION\b/g, "NESSUNA ULTERIORE AZIONE"],
    [/\bWILL BE INVESTIGATED AFTER THE RACE\b/g, "SARA' INVESTIGATO DOPO LA GARA"],
    [/\bREVIEWED NO FURTHER INVESTIGATION\b/g, "REVISIONATO, NESSUNA ULTERIORE INDAGINE"],
    [/\bTIME\b/g, "TEMPO"],
    [/\bLAP DELETED\b/g, "GIRO CANCELLATO"],
    [/\bDELETED\b/g, "CANCELLATO"],
    [/\bTRACK LIMITS\b/g, "LIMITI DELLA PISTA"],
    [/\bLEAVING THE TRACK AND GAINING AN ADVANTAGE\b/g, "USCITA DI PISTA CON VANTAGGIO"],
    [/\bFORCING ANOTHER DRIVER OFF THE TRACK\b/g, "HA FORZATO UN ALTRO PILOTA FUORI PISTA"],
    [/\bSTARTING PROCEDURE INFRINGEMENT\b/g, "INFRAZIONE PROCEDURA DI PARTENZA"],
    [/\bYELLOW FLAG INFRINGEMENT\b/g, "INFRAZIONE IN REGIME DI GIALLA"],
    [/\bMARSHALS ON TRACK\b/g, "COMMISSARI IN PISTA"],
    [/\bTRACK SURFACE SLIPPERY\b/g, "SUPERFICIE PISTA SCIVOLOSA"],
    [/\bFIA STEWARDS\b/g, "COMMISSARI FIA"],
    [/\bCAR\b/g, "VETTURA"],
    [/\bLAP\b/g, "GIRO"],
    [/\bPIT\b/g, "BOX"],
  ];
  return replacements.reduce(
    (current, [pattern, replacement]) => current.replace(pattern, replacement),
    message,
  );
}

export function LiveView() {
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [error, setError] = useState<string>();
  const [streaming, setStreaming] = useState(false);
  const [translateMessages, setTranslateMessages] = useState(true);
  const [showLapSectors, setShowLapSectors] = useState(false);
  const [translatingPath, setTranslatingPath] = useState<string>();
  const [transcribingPath, setTranscribingPath] = useState<string>();
  const [playingPath, setPlayingPath] = useState<string>();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioPathRef = useRef<string | undefined>(undefined);
  const rememberedRaceControlRef = useRef<RaceControlMessage[]>([]);
  const rememberedTeamRadioRef = useRef<NonNullable<Snapshot["team_radio"]>>([]);
  const rememberedSessionRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    setError(undefined);
    const source = new EventSource("/api/f1signal/stream?interval=0.5");

    source.addEventListener("snapshot", (event) => {
      setSnapshot(JSON.parse((event as MessageEvent).data) as Snapshot);
      setStreaming(true);
    });
    source.onerror = () => {
      setStreaming(false);
      api
        .f1SignalSnapshot()
        .then(setSnapshot)
        .catch((reason: Error) => setError(reason.message));
    };

    return () => source.close();
  }, []);

  useEffect(
    () => () => {
      audioRef.current?.pause();
      audioRef.current = null;
    },
    [],
  );

  const driversByNumber = useMemo(
    () =>
      new Map(
        asArray(snapshot?.drivers).map((driver) => [
          driver.driver_number,
          driver,
        ]),
      ),
    [snapshot],
  );
  const intervalsByNumber = useMemo(
    () =>
      new Map(
        asArray(snapshot?.intervals).map((point) => [
          point.driver_number,
          point,
        ]),
      ),
    [snapshot],
  );
  const telemetryByNumber = useMemo(
    () =>
      new Map(
        asArray(snapshot?.telemetry).map((point) => [
          point.driver_number,
          point,
        ]),
      ),
    [snapshot],
  );
  const bestLapsByNumber = useMemo(
    () =>
      new Map(
        asArray(snapshot?.best_laps).map((lap) => [
          lap.driver_number,
          lap,
        ]),
      ),
    [snapshot],
  );

  const rows = [...asArray(snapshot?.positions)].sort(
    (a, b) =>
      (a.position ?? Number.MAX_SAFE_INTEGER) -
      (b.position ?? Number.MAX_SAFE_INTEGER),
  );
  const sessionMemoryKey = snapshot
    ? `${snapshot.session.date_start}-${snapshot.session.session_name}`
    : undefined;
  if (sessionMemoryKey && rememberedSessionRef.current !== sessionMemoryKey) {
    rememberedSessionRef.current = sessionMemoryKey;
    rememberedRaceControlRef.current = [];
    rememberedTeamRadioRef.current = [];
  }

  const currentRaceControl = asArray(snapshot?.race_control?.Messages);
  if (currentRaceControl.length > 0) {
    rememberedRaceControlRef.current = currentRaceControl;
  }
  const visibleRaceControl =
    currentRaceControl.length > 0 || snapshot?.is_live_window
      ? currentRaceControl
      : rememberedRaceControlRef.current;
  const raceControl = [...visibleRaceControl].reverse();
  const currentTeamRadio = asArray(snapshot?.team_radio);
  if (currentTeamRadio.length > 0) {
    rememberedTeamRadioRef.current = currentTeamRadio;
  }
  const visibleTeamRadio =
    currentTeamRadio.length > 0 || snapshot?.is_live_window
      ? currentTeamRadio
      : rememberedTeamRadioRef.current;

  function toggleRadio(path?: string, url?: string) {
    if (!path || !url) return;
    if (audioRef.current && audioPathRef.current === path) {
      if (audioRef.current.paused) {
        audioRef.current
          .play()
          .then(() => setPlayingPath(path))
          .catch(() => setError("Audio team radio non riproducibile"));
      } else {
        audioRef.current.pause();
        setPlayingPath(undefined);
      }
      return;
    }

    audioRef.current?.pause();
    const audio = new Audio(url);
    audioRef.current = audio;
    audioPathRef.current = path;
    audio.addEventListener("ended", () => setPlayingPath(undefined));
    audio.addEventListener("pause", () => {
      if (audioPathRef.current === path) {
        setPlayingPath(undefined);
      }
    });
    audio
      .play()
      .then(() => setPlayingPath(path))
      .catch(() => setError("Audio team radio non riproducibile"));
  }

  async function retryRadioTranscription(path?: string) {
    if (!path) return;
    setTranscribingPath(path);
    setError(undefined);
    try {
      const updated = await api.transcribeTeamRadio(path);
      setSnapshot((current) =>
        current
          ? {
              ...current,
              team_radio: (current.team_radio ?? []).map((radio) =>
                radio.path === path ? updated : radio,
              ),
            }
          : current,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Trascrizione non disponibile");
    } finally {
      setTranscribingPath(undefined);
    }
  }

  async function translateRadio(path?: string) {
    if (!path) return;
    setTranslatingPath(path);
    setError(undefined);
    try {
      const updated = await api.translateTeamRadio(path);
      setSnapshot((current) =>
        current
          ? {
              ...current,
              team_radio: (current.team_radio ?? []).map((radio) =>
                radio.path === path ? updated : radio,
              ),
            }
          : current,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Traduzione non disponibile");
    } finally {
      setTranslatingPath(undefined);
    }
  }

  return (
    <>
      <section className="hero live-hero">
        <div>
          <p className="eyebrow">
            {snapshot?.session.country_name
              ? `${snapshot.session.country_name} · LIVE TIMING`
              : "F1 SIGNALR · LIVE TIMING"}
          </p>
          <h1>{snapshot?.session.session_name ?? "Race control room."}</h1>
          <p className="subtitle">
            {snapshot?.session.location
              ? `${snapshot.session.location} · ${snapshot.session.circuit_short_name}`
              : "Timing, distacchi, meteo e messaggi FIA dal feed SignalR."}
          </p>
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}

      <section className="live-strip panel">
        <LiveStatus
          label="CONNESSIONE"
          value={snapshot?.status?.connected ? "ONLINE" : "IN ATTESA"}
          active={streaming && !!snapshot?.status?.connected}
        />
        <LiveStatus
          label="SESSIONE"
          value={snapshot?.is_live_window ? "LIVE" : "CONCLUSA"}
          active={!!snapshot?.is_live_window}
        />
        <LiveStatus
          label="GIRO"
          value={
            snapshot?.lap_count
              ? `${snapshot.lap_count.CurrentLap ?? "-"} / ${snapshot.lap_count.TotalLaps ?? "-"}`
              : "-"
          }
        />
        <LiveStatus
          label="TRACK"
          value={snapshot?.track_status?.Message ?? "-"}
          active={snapshot?.track_status?.Message !== "AllClear"}
        />
        <LiveStatus
          label="UPDATE"
          value={formatTime(snapshot?.cursor)}
        />
      </section>

      {!snapshot && <div className="analysis-loading panel">Connessione al feed F1...</div>}

      {snapshot && (
        <section className="dashboard live-dashboard">
          <div className="panel leaderboard">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">CLASSIFICA</p>
                <h2>Posizioni e distacchi</h2>
              </div>
              <span>{rows.length} PILOTI</span>
            </div>
            <div className="driver-list">
              {rows.map((point) => (
                <LiveDriverRow
                  bestLap={bestLapsByNumber.get(point.driver_number)}
                  driver={driversByNumber.get(point.driver_number)}
                  interval={intervalsByNumber.get(point.driver_number)}
                  key={point.driver_number}
                  position={point}
                  telemetry={telemetryByNumber.get(point.driver_number)}
                />
              ))}
              {rows.length === 0 && (
                <div className="empty-state">Nessuna posizione ricevuta.</div>
              )}
            </div>
          </div>

          <div className="right-column">
            <LiveTrackMap
              driversByNumber={driversByNumber}
              locations={asArray(snapshot.locations)}
              sessionId={`${snapshot.session.date_start}-${snapshot.session.session_name}`}
              trackMap={snapshot.track_map}
            />

            <section className="panel race-control-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">RACE CONTROL</p>
                  <h2>Messaggi FIA</h2>
                </div>
                <div className="message-tools">
                  <span>{visibleRaceControl.length} EVENTI</span>
                  <button
                    className={translateMessages ? "active" : ""}
                    onClick={() => setTranslateMessages((current) => !current)}
                  >
                    IT
                  </button>
                </div>
              </div>
              <div className="race-control-list">
                {raceControl.map((message, index) => (
                  <RaceMessage
                    key={`${message.Utc}-${index}`}
                    message={message}
                    translated={translateMessages}
                  />
                ))}
                {raceControl.length === 0 && (
                  <div className="empty-state">Nessun messaggio race control.</div>
                )}
              </div>
            </section>

            <section className="panel team-radio-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">TEAM RADIO</p>
                  <h2>Comunicazioni</h2>
                </div>
                <span>{visibleTeamRadio.length} CLIP</span>
              </div>
              <div className="team-radio-list">
                {visibleTeamRadio.slice().reverse().map((radio, index) => {
                  const driver = radio.driver_number
                    ? driversByNumber.get(radio.driver_number)
                    : undefined;
                  const isWorking =
                    radio.transcription_status === "queued" ||
                    radio.transcription_status === "transcribing";
                  const text =
                    radio.translation_it ||
                    radio.transcript ||
                    radio.message ||
                    (isWorking ? "Trascrizione in corso..." : "Team radio");
                  return (
                    <div className="radio-message" key={`${radio.utc}-${radio.path}-${index}`}>
                      <span
                        className="team-stripe"
                        style={{ background: teamColor(driver) }}
                      />
                      <div className="radio-body">
                        <div className="radio-meta">
                          <div>
                            <strong>{driver?.name_acronym ?? radio.driver_number ?? "RADIO"}</strong>
                            <small>{formatTime(radio.utc)}</small>
                          </div>
                          <div className="radio-actions">
                            {radio.transcription_status === "error" && (
                              <button
                                className="radio-transcribe"
                                aria-label="Riprova trascrizione team radio"
                                title="Riprova trascrizione"
                                disabled={!radio.path || transcribingPath === radio.path}
                                onClick={() => retryRadioTranscription(radio.path)}
                              >
                                {transcribingPath === radio.path ? "…" : "TXT"}
                              </button>
                            )}
                            <button
                              className="radio-it"
                              aria-label="Traduci team radio in italiano"
                              title="Traduci in italiano"
                              disabled={
                                !radio.path ||
                                !radio.transcript ||
                                Boolean(radio.translation_it) ||
                                translatingPath === radio.path
                              }
                              onClick={() => translateRadio(radio.path)}
                            >
                              IT
                            </button>
                            <button
                              className={
                                playingPath === radio.path
                                  ? "radio-play playing"
                                  : "radio-play"
                              }
                              aria-label="Riproduci team radio"
                              title="Riproduci team radio"
                              disabled={!radio.path || !radio.url}
                              onClick={() => toggleRadio(radio.path, radio.url)}
                            />
                          </div>
                        </div>
                        <p className={radio.translation_it ? "radio-translation" : "radio-transcript"}>
                          {text}
                        </p>
                        {radio.translation_it && radio.transcript && (
                          <p className="radio-transcript">{radio.transcript}</p>
                        )}
                        {radio.transcription_status === "error" && (
                          <p className="radio-error">
                            {radio.transcription_error ?? "Trascrizione non disponibile"}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
                {visibleTeamRadio.length === 0 && (
                  <div className="empty-state">Nessuna team radio ricevuta.</div>
                )}
              </div>
            </section>

            <section className="metrics">
              <Metric
                label="ARIA"
                value={
                  snapshot.weather?.air_temperature !== undefined
                    ? `${snapshot.weather.air_temperature}°C`
                    : "-"
                }
                accent
              />
              <Metric
                label="PISTA"
                value={
                  snapshot.weather?.track_temperature !== undefined
                    ? `${snapshot.weather.track_temperature}°C`
                    : "-"
                }
              />
              <BestLapPanel
                bestLap={snapshot.best_lap}
                driver={snapshot.best_lap ? driversByNumber.get(snapshot.best_lap.driver_number) : undefined}
                expanded={showLapSectors}
                onToggle={() => setShowLapSectors((current) => !current)}
              />
            </section>
          </div>
        </section>
      )}
    </>
  );
}

function drawableLocations(locations: DriverPoint[]): MapPoint[] {
  return locations
    .filter(
      (point) =>
        typeof point.x === "number" &&
        typeof point.y === "number" &&
        Number.isFinite(point.x) &&
        Number.isFinite(point.y),
    )
    .map((point) => ({
      driver_number: point.driver_number,
      date: point.date,
      x: point.x as number,
      y: point.y as number,
      z: point.z,
      mapped_to_track: point.mapped_to_track,
    }));
}

function interpolatePoint(
  start: TimedMapPoint,
  end: TimedMapPoint,
  progress: number,
): MapPoint {
  return {
    driver_number: end.driver_number,
    date: end.date,
    x: start.x + (end.x - start.x) * progress,
    y: start.y + (end.y - start.y) * progress,
    z:
      typeof start.z === "number" && typeof end.z === "number"
        ? start.z + (end.z - start.z) * progress
        : end.z,
  };
}

function distanceBetween(start: MapPoint, end: MapPoint) {
  return Math.hypot(end.x - start.x, end.y - start.y);
}

function boundsFor(points: Array<Pick<MapPoint, "x" | "y">>): TrackBounds {
  return points.reduce(
    (current, point) => ({
      minX: Math.min(current.minX, point.x),
      maxX: Math.max(current.maxX, point.x),
      minY: Math.min(current.minY, point.y),
      maxY: Math.max(current.maxY, point.y),
    }),
    {
      minX: Number.POSITIVE_INFINITY,
      maxX: Number.NEGATIVE_INFINITY,
      minY: Number.POSITIVE_INFINITY,
      maxY: Number.NEGATIVE_INFINITY,
    },
  );
}

function paddedBounds(bounds: TrackBounds): TrackBounds {
  const width = Math.max(bounds.maxX - bounds.minX, 1);
  const height = Math.max(bounds.maxY - bounds.minY, 1);
  const paddingX = width * 0.08;
  const paddingY = height * 0.08;
  return {
    minX: bounds.minX - paddingX,
    maxX: bounds.maxX + paddingX,
    minY: bounds.minY - paddingY,
    maxY: bounds.maxY + paddingY,
  };
}

function fallbackBounds(points: Array<Pick<MapPoint, "x" | "y">>): TrackBounds {
  if (!points.length) {
    return { minX: 0, maxX: 1, minY: 0, maxY: 1 };
  }
  const bounds = boundsFor(points);
  const width = bounds.maxX - bounds.minX;
  const height = bounds.maxY - bounds.minY;
  const minSpan = Math.max(width, height, 2500);
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;
  return paddedBounds({
    minX: centerX - Math.max(width, minSpan) / 2,
    maxX: centerX + Math.max(width, minSpan) / 2,
    minY: centerY - Math.max(height, minSpan) / 2,
    maxY: centerY + Math.max(height, minSpan) / 2,
  });
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function pointForRenderTime(
  history: TimedMapPoint[],
  renderAt: number,
): MapPoint | undefined {
  if (history.length === 0) return undefined;
  if (history.length === 1) return history[0];

  let before: TimedMapPoint | undefined;
  let after: TimedMapPoint | undefined;

  for (const sample of history) {
    if (sample.receivedAt <= renderAt) {
      before = sample;
    }
    if (sample.receivedAt >= renderAt) {
      after = sample;
      break;
    }
  }

  if (!before) {
    return after ?? history[0];
  }

  if (after && after.receivedAt !== before.receivedAt) {
    if (distanceBetween(before, after) > GPS_SNAP_DISTANCE) {
      return before;
    }
    const progress =
      (renderAt - before.receivedAt) / (after.receivedAt - before.receivedAt);
    return interpolatePoint(before, after, Math.min(Math.max(progress, 0), 1));
  }

  const latest = history[history.length - 1];
  const previous = history[history.length - 2];
  const extrapolateMs = Math.min(
    Math.max(renderAt - latest.receivedAt, 0),
    GPS_EXTRAPOLATE_LIMIT_MS,
  );

  if (
    extrapolateMs <= 0 ||
    latest.receivedAt === previous.receivedAt ||
    distanceBetween(previous, latest) > GPS_SNAP_DISTANCE
  ) {
    return before;
  }

  const elapsed = latest.receivedAt - previous.receivedAt;
  const velocityX = (latest.x - previous.x) / elapsed;
  const velocityY = (latest.y - previous.y) / elapsed;
  return {
    ...latest,
    x: latest.x + velocityX * extrapolateMs,
    y: latest.y + velocityY * extrapolateMs,
  };
}

function useSmoothedLocations(locations: DriverPoint[]): MapPoint[] {
  const historyRef = useRef<Map<number, TimedMapPoint[]>>(new Map());
  const frameRef = useRef<number | undefined>(undefined);
  const [display, setDisplay] = useState<MapPoint[]>(() =>
    drawableLocations(locations),
  );

  useEffect(() => {
    const now = performance.now();
    const latest = drawableLocations(locations);
    const activeDrivers = new Set(latest.map((point) => point.driver_number));
    const history = historyRef.current;

    for (const point of latest) {
      const samples = history.get(point.driver_number) ?? [];
      const previous = samples[samples.length - 1];
      if (!previous || previous.x !== point.x || previous.y !== point.y) {
        samples.push({ ...point, receivedAt: now });
      }
      history.set(
        point.driver_number,
        samples.filter(
          (sample) => now - sample.receivedAt <= GPS_HISTORY_WINDOW_MS,
        ),
      );
    }

    for (const number of history.keys()) {
      if (!activeDrivers.has(number)) {
        history.delete(number);
      }
    }

    if (frameRef.current !== undefined) {
      return;
    }

    const tick = () => {
      const renderAt = performance.now() - GPS_RENDER_DELAY_MS;
      const points: MapPoint[] = [];
      let hasFutureSamples = false;

      for (const samples of historyRef.current.values()) {
        const point = pointForRenderTime(samples, renderAt);
        if (point) {
          points.push(point);
        }
        if (samples.some((sample) => sample.receivedAt > renderAt)) {
          hasFutureSamples = true;
        }
      }

      setDisplay(
        points.sort(
          (a, b) => a.driver_number - b.driver_number,
        ),
      );

      const newestSampleAt = Math.max(
        ...Array.from(historyRef.current.values()).map(
          (samples) => samples[samples.length - 1]?.receivedAt ?? 0,
        ),
        0,
      );
      const shouldContinue =
        hasFutureSamples ||
        performance.now() - newestSampleAt <
          GPS_RENDER_DELAY_MS + GPS_EXTRAPOLATE_LIMIT_MS;

      if (shouldContinue) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        frameRef.current = undefined;
      }
    };

    frameRef.current = requestAnimationFrame(tick);

    return () => {
      if (frameRef.current !== undefined) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = undefined;
      }
    };
  }, [locations]);

  return display;
}

function LiveTrackMap({
  driversByNumber,
  locations,
  sessionId,
  trackMap,
}: {
  driversByNumber: Map<number, Driver>;
  locations: DriverPoint[];
  sessionId: string;
  trackMap?: Snapshot["track_map"];
}) {
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState<MapOffset>({ x: 0, y: 0 });
  const [panState, setPanState] = useState<PanState | null>(null);
  const boundsRef = useRef<{
    sessionId: string;
    bounds: TrackBounds;
  } | null>(null);
  const stableTrackRef = useRef<{
    sessionId: string;
    trackMap: NonNullable<Snapshot["track_map"]>;
  } | null>(null);

  if (stableTrackRef.current?.sessionId !== sessionId) {
    stableTrackRef.current = null;
  }
  const hasIncomingTrack =
    trackMap && asArray(trackMap.trace).length >= TRACK_LAYOUT_MIN_POINTS;
  if (
    stableTrackRef.current &&
    hasIncomingTrack &&
    (stableTrackRef.current.trackMap.source !== trackMap.source ||
      stableTrackRef.current.trackMap.coordinate_system !==
        trackMap.coordinate_system)
  ) {
    stableTrackRef.current = { sessionId, trackMap };
  }
  if (
    !stableTrackRef.current &&
    hasIncomingTrack
  ) {
    stableTrackRef.current = { sessionId, trackMap };
  }

  const stableTrackMap = stableTrackRef.current?.trackMap;
  const requiresMappedLocations =
    !!stableTrackMap && stableTrackMap.source !== "F1 SignalR Position.z";
  const visibleLocationRows = useMemo(
    () =>
      requiresMappedLocations
        ? locations.filter((point) => point.mapped_to_track)
        : locations,
    [locations, requiresMappedLocations],
  );
  const targetLocations = useMemo(
    () => drawableLocations(visibleLocationRows),
    [visibleLocationRows],
  );
  const drawable = useSmoothedLocations(visibleLocationRows);
  const trace = stableTrackMap?.trace ?? [];
  const tracePoints = trace.map(([x, y]) => ({ x, y }));
  const livePoints = targetLocations.map((point) => ({ x: point.x, y: point.y }));
  const layoutPoints = tracePoints;
  const allPoints = [...layoutPoints, ...livePoints];

  if (boundsRef.current?.sessionId !== sessionId) {
    boundsRef.current = null;
  }
  if (!boundsRef.current && layoutPoints.length) {
    boundsRef.current = {
      sessionId,
      bounds: fallbackBounds(layoutPoints),
    };
  }

  const bounds =
    boundsRef.current?.bounds ?? fallbackBounds(allPoints);
  const width = Math.max(bounds.maxX - bounds.minX, 1);
  const height = Math.max(bounds.maxY - bounds.minY, 1);
  const drawableWidth = TRACK_VIEWBOX_WIDTH - TRACK_VIEWBOX_PADDING_X * 2;
  const drawableHeight = TRACK_VIEWBOX_HEIGHT - TRACK_VIEWBOX_PADDING_Y * 2;
  const baseScale = Math.min(drawableWidth / width, drawableHeight / height);
  const scale = baseScale * zoom;
  const maxOffsetX = Math.max((TRACK_VIEWBOX_WIDTH * (zoom - 1)) / 2, 0);
  const maxOffsetY = Math.max((TRACK_VIEWBOX_HEIGHT * (zoom - 1)) / 2, 0);
  const clampedOffset = useMemo(
    () => ({
      x: clamp(offset.x, -maxOffsetX, maxOffsetX),
      y: clamp(offset.y, -maxOffsetY, maxOffsetY),
    }),
    [maxOffsetX, maxOffsetY, offset.x, offset.y],
  );
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;
  const x = (value: number) =>
    TRACK_VIEWBOX_WIDTH / 2 + clampedOffset.x + (value - centerX) * scale;
  const y = (value: number) =>
    TRACK_VIEWBOX_HEIGHT / 2 + clampedOffset.y - (value - centerY) * scale;
  const changeZoom = (next: number) => {
    const clampedZoom = Math.min(Math.max(next, 0.45), 2.5);
    setZoom(clampedZoom);
    if (clampedZoom <= 1) setOffset({ x: 0, y: 0 });
  };

  useEffect(() => {
    setOffset({ x: 0, y: 0 });
    setPanState(null);
  }, [sessionId]);

  useEffect(() => {
    if (clampedOffset.x === offset.x && clampedOffset.y === offset.y) return;
    setOffset(clampedOffset);
  }, [clampedOffset, offset.x, offset.y]);

  function svgPanDelta(
    event: React.PointerEvent<SVGSVGElement>,
    state: PanState,
  ) {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: ((event.clientX - state.startClientX) / rect.width) * TRACK_VIEWBOX_WIDTH,
      y: ((event.clientY - state.startClientY) / rect.height) * TRACK_VIEWBOX_HEIGHT,
    };
  }

  return (
    <section className="panel track-panel live-track-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">GPS AUTO</p>
          <h2>Posizione in pista</h2>
        </div>
        <div className="track-map-tools">
          <span>{trace.length ? `${trace.length} PUNTI` : `${drawable.length} AUTO`}</span>
          <button type="button" onClick={() => changeZoom(zoom - 0.15)} aria-label="Dezoom pista">-</button>
          <input
            aria-label="Zoom pista"
            max="2.5"
            min="0.45"
            onChange={(event) => changeZoom(Number(event.target.value))}
            step="0.05"
            type="range"
            value={zoom}
          />
          <button type="button" onClick={() => changeZoom(zoom + 0.15)} aria-label="Zoom pista">+</button>
          <button type="button" onClick={() => changeZoom(1)} aria-label="Reset zoom pista">1x</button>
          <button
            type="button"
            onClick={() => setOffset({ x: 0, y: 0 })}
            disabled={zoom <= 1}
            aria-label="Centra mappa"
          >
            Centra
          </button>
        </div>
      </div>
      {allPoints.length > 0 ? (
        <div className="live-position-frame">
          <svg
            className={`track-map live-position-map ${zoom > 1 ? "pannable" : ""}`}
            viewBox={`0 0 ${TRACK_VIEWBOX_WIDTH} ${TRACK_VIEWBOX_HEIGHT}`}
            onPointerDown={(event) => {
              if (zoom <= 1) return;
              const state = {
                pointerId: event.pointerId,
                startClientX: event.clientX,
                startClientY: event.clientY,
                startOffset: clampedOffset,
              };
              setPanState(state);
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              if (!panState || panState.pointerId !== event.pointerId) return;
              const delta = svgPanDelta(event, panState);
              setOffset({
                x: clamp(panState.startOffset.x + delta.x, -maxOffsetX, maxOffsetX),
                y: clamp(panState.startOffset.y + delta.y, -maxOffsetY, maxOffsetY),
              });
            }}
            onPointerUp={(event) => {
              if (panState?.pointerId === event.pointerId) {
                setPanState(null);
                event.currentTarget.releasePointerCapture(event.pointerId);
              }
            }}
            onPointerCancel={() => setPanState(null)}
          >
            {tracePoints.length > 1 && (
              <polyline
                className="position-trace"
                fill="none"
                points={tracePoints
                  .map((point) => `${x(point.x)},${y(point.y)}`)
                  .join(" ")}
              />
            )}
            {drawable.map((point) => {
              const driver = driversByNumber.get(point.driver_number);
              return (
                <g
                  className="car-marker"
                  key={point.driver_number}
                  transform={`translate(${x(point.x ?? 0)} ${y(point.y ?? 0)})`}
                >
                  <circle r="10" fill={teamColor(driver)} />
                  <rect
                    className="car-label-bg"
                    x="-18"
                    y="13"
                    width="36"
                    height="17"
                    rx="3"
                  />
                  <text className="car-label" y="25">
                    {driver?.name_acronym ?? point.driver_number}
                  </text>
                </g>
              );
            })}
          </svg>
          {!targetLocations.length && (
            <div className="track-map-note">
              {requiresMappedLocations
                ? "Layout circuito disponibile. In attesa mapping GPS auto."
                : "Layout circuito disponibile. In attesa coordinate auto dal feed GPS."}
            </div>
          )}
        </div>
      ) : (
        <div className="track-empty">
          <div className="track-placeholder" />
          <span>Coordinate auto non disponibili per questa sessione.</span>
        </div>
      )}
    </section>
  );
}

function RaceMessage({
  message,
  translated,
}: {
  message: RaceControlMessage;
  translated: boolean;
}) {
  return (
    <div className="race-message">
      <strong>{message.Flag ?? message.Category ?? "INFO"}</strong>
      <span>L{message.Lap ?? "-"}</span>
      <p>{translated ? translateRaceMessage(message.Message) : message.Message}</p>
    </div>
  );
}

function sectorClass(status?: string) {
  if (status === "overall_best") return "overall";
  if (status === "personal_best") return "personal";
  if (status === "pit") return "pit";
  return "normal";
}

function sectorLabel(status?: string) {
  if (status === "overall_best") return "Best";
  if (status === "personal_best") return "PB";
  if (status === "pit") return "Pit";
  return "";
}

function BestLapPanel({
  bestLap,
  driver,
  expanded,
  onToggle,
}: {
  bestLap: Snapshot["best_lap"];
  driver?: Driver;
  expanded: boolean;
  onToggle: () => void;
}) {
  const sectors = asArray(bestLap?.sectors).filter(
    (sector) =>
      Boolean(sector.time) ||
      asArray(sector.segments).length > 0 ||
      sector.status !== "normal",
  );
  const hasSegments = sectors.some(
    (sector) => asArray(sector.segments).length > 0,
  );

  return (
    <div className="metric best-lap-panel">
      <button
        className="best-lap-summary"
        disabled={!bestLap}
        onClick={onToggle}
        type="button"
      >
        <span>BEST LAP SESSIONE</span>
        <strong>
          {bestLap
            ? `${driver?.name_acronym ?? bestLap.driver_number} · ${bestLap.lap_duration.toFixed(3)}`
            : "-"}
        </strong>
        <small>{bestLap?.lap_number ? `LAP ${bestLap.lap_number}` : " "}</small>
      </button>
      {expanded && bestLap && (
        <div className="microsector-panel">
          {sectors.length > 0 ? (
            sectors.map((sector) => (
              <div className="sector-row" key={sector.number}>
                <div className="sector-meta">
                  <strong>S{sector.number}</strong>
                  <span>{sector.time ?? "-"}</span>
                </div>
                <div className="microsector-strip">
                  {asArray(sector.segments).map((segment) => (
                    <span
                      className={`microsector ${sectorClass(segment.status)}`}
                      key={`${sector.number}-${segment.number}`}
                      title={`S${sector.number}.${segment.number} ${sectorLabel(segment.status)}`}
                    />
                  ))}
                  {asArray(sector.segments).length === 0 && (
                    <span className={`microsector wide ${sectorClass(sector.status)}`} />
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">Microsettori non ancora ricevuti.</div>
          )}
          {hasSegments && (
            <div className="microsector-legend">
              <span><i className="microsector overall" />Best</span>
              <span><i className="microsector personal" />PB</span>
              <span><i className="microsector normal" />Std</span>
              <span><i className="microsector pit" />Pit</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function LiveStatus({
  label,
  value,
  active,
}: {
  label: string;
  value: string;
  active?: boolean;
}) {
  return (
    <div>
      <span>
        <i className={active ? "active" : ""} />
        {label}
      </span>
      <strong>{value}</strong>
    </div>
  );
}

function LiveDriverRow({
  bestLap,
  driver,
  interval,
  position,
  telemetry,
}: {
  bestLap?: NonNullable<Snapshot["best_lap"]>;
  driver?: Driver;
  interval?: DriverPoint;
  position: DriverPoint;
  telemetry?: DriverPoint;
}) {
  return (
    <div className="driver-row">
      <span className="position">P{position.position ?? "-"}</span>
      <span
        className="team-stripe"
        style={{ background: teamColor(driver) }}
      />
      <div className="driver-name">
        <strong>{driver?.name_acronym ?? position.driver_number}</strong>
        <span>{driver?.team_name ?? "Driver"}</span>
      </div>
      <div className="telemetry-mini">
        <span>
          {telemetry?.speed ?? "-"} <small>km/h</small>
        </span>
        <span>
          {telemetry?.n_gear ?? "-"} <small>gear</small>
        </span>
      </div>
      <span className="gap">{formatGap(interval?.gap_to_leader)}</span>
      <div className="lap-times-mini">
        <span>
          LAST <strong>{formatLapTime(position.last_lap_time ?? position.last_lap_duration)}</strong>
        </span>
        <span>
          BEST <strong>{formatLapTime(position.best_lap_time ?? bestLap?.lap_duration)}</strong>
        </span>
      </div>
      <DriverBestLap bestLap={bestLap} />
    </div>
  );
}

function DriverBestLap({
  bestLap,
}: {
  bestLap?: NonNullable<Snapshot["best_lap"]>;
}) {
  const sectors = asArray(bestLap?.sectors).filter(
    (sector) =>
      Boolean(sector.time) ||
      asArray(sector.segments).length > 0 ||
      sector.status !== "normal",
  );
  if (!bestLap) {
    return <div className="driver-best-lap muted">PB -</div>;
  }

  return (
    <div className="driver-best-lap">
      <div className="driver-best-lap-meta">
        <span>PB</span>
        <strong>{bestLap.lap_duration.toFixed(3)}</strong>
        <small>L{bestLap.lap_number ?? "-"}</small>
      </div>
      {sectors.length > 0 && (
        <div className="driver-sector-strip">
          {sectors.map((sector) => (
            <div className="driver-sector" key={sector.number}>
              <span>S{sector.number}</span>
              <b>{sector.time ?? "-"}</b>
              <div className="microsector-strip">
                {asArray(sector.segments).map((segment) => (
                  <i
                    className={`microsector ${sectorClass(segment.status)}`}
                    key={`${sector.number}-${segment.number}`}
                    title={`S${sector.number}.${segment.number} ${sectorLabel(segment.status)}`}
                  />
                ))}
                {asArray(sector.segments).length === 0 && (
                  <i className={`microsector wide ${sectorClass(sector.status)}`} />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className={`panel metric ${accent ? "accent" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
