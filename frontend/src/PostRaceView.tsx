import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { CircuitLayoutMap } from "./CircuitLayoutMap";
import { TelemetryChart } from "./TelemetryChart";
import type {
  AnalysisEvent,
  AnalysisSession,
  PostRaceAnalysis,
  TelemetrySession,
} from "./types";

const currentYear = new Date().getFullYear();
const SESSION_FALLBACK: TelemetrySession[] = [
  "race",
  "qualifying",
  "sprint",
  "sprint_qualifying",
  "fp3",
  "fp2",
  "fp1",
];

const SESSION_LABELS: Record<TelemetrySession, string> = {
  fp1: "FP1",
  fp2: "FP2",
  fp3: "FP3",
  sprint_qualifying: "Sprint qualifying",
  sprint: "Sprint",
  qualifying: "Qualifica",
  race: "Gara",
};

function formatLap(seconds?: number) {
  if (seconds === undefined) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}

export function PostRaceView() {
  const [year, setYear] = useState(currentYear);
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [round, setRound] = useState<number>();
  const [telemetrySession, setTelemetrySession] = useState<TelemetrySession>("race");
  const [availableSessions, setAvailableSessions] = useState<AnalysisSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [lapMode, setLapMode] = useState<"best" | "number">("best");
  const [lapNumber, setLapNumber] = useState<number>();
  const [analysis, setAnalysis] = useState<PostRaceAnalysis>();
  const [loading, setLoading] = useState(false);
  const [telemetryLoading, setTelemetryLoading] = useState(false);
  const [error, setError] = useState<string>();
  const analysisRef = useRef<PostRaceAnalysis | undefined>(undefined);

  useEffect(() => {
    analysisRef.current = analysis;
  }, [analysis]);

  useEffect(() => {
    setError(undefined);
    api
      .analysisEvents(year)
      .then((items) => {
        const completed = items.filter((item) => item.completed);
        const nextEvent = items.find((item) => !item.completed);
        const nextEventDate = nextEvent ? new Date(nextEvent.date) : undefined;
        const includeNextEvent =
          nextEventDate !== undefined &&
          nextEventDate.getTime() <= Date.now() + 4 * 24 * 60 * 60 * 1000;
        const visible = [
          ...completed,
          ...(nextEvent && includeNextEvent ? [nextEvent] : []),
        ].filter(
          (event, index, list) =>
            list.findIndex((item) => item.round === event.round) === index,
        );
        setEvents(visible);
        setRound(
          nextEvent && includeNextEvent
            ? nextEvent.round
            : completed.at(-1)?.round,
        );
      })
      .catch((reason: Error) => setError(reason.message));
  }, [year]);

  useEffect(() => {
    setAvailableSessions([]);
    setAnalysis(undefined);
    setLapMode("best");
    setLapNumber(undefined);
    if (!round) return;
    let cancelled = false;
    setSessionsLoading(true);
    setError(undefined);

    api
      .analysisSessions(year, round)
      .then((sessions) => {
        if (cancelled) return;
        setAvailableSessions(sessions);
        const values = new Set(sessions.map((session) => session.value));
        const preferred =
          SESSION_FALLBACK.find((session) => values.has(session)) ??
          sessions[0]?.value;
        if (preferred) {
          setTelemetrySession((current) =>
            values.has(current) ? current : preferred,
          );
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      })
      .finally(() => {
        if (!cancelled) setSessionsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [year, round]);

  useEffect(() => {
    if (!round) return;
    if (!availableSessions.some((session) => session.value === telemetrySession)) {
      return;
    }
    const selectedRound = round;
    const currentAnalysis = analysisRef.current;
    const keepCurrentAnalysis =
      currentAnalysis?.event.year === year &&
      currentAnalysis?.event.round === selectedRound &&
      currentAnalysis?.telemetry_session === telemetrySession;
    setLoading(!keepCurrentAnalysis);
    setTelemetryLoading(keepCurrentAnalysis);
    setError(undefined);
    if (!keepCurrentAnalysis) setAnalysis(undefined);
    let cancelled = false;

    async function load() {
      try {
        const result = await api.postRace(
          year,
          selectedRound,
          telemetrySession,
          lapMode,
          lapNumber,
        );
        if (cancelled) return;
        setAnalysis(result);
      } catch (reason) {
        const shouldFallback =
          !keepCurrentAnalysis &&
          telemetrySession === "race" &&
          lapMode === "best";
        if (!shouldFallback) {
          if (!cancelled) setError((reason as Error).message);
          return;
        }
        for (const session of SESSION_FALLBACK.filter((item) => item !== "race")) {
          if (!availableSessions.some((item) => item.value === session)) {
            continue;
          }
          try {
            const result = await api.postRace(year, selectedRound, session, "best");
            if (cancelled) return;
            setTelemetrySession(session);
            setAnalysis(result);
            return;
          } catch {
            // Try the next completed session of the current weekend.
          }
        }
        if (!cancelled) setError((reason as Error).message);
      } finally {
        if (!cancelled) {
          setLoading(false);
          setTelemetryLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [year, round, telemetrySession, lapMode, lapNumber, availableSessions]);

  useEffect(() => {
    setLapMode("best");
    setLapNumber(undefined);
  }, [year, round, telemetrySession]);

  const paceLeader = useMemo(
    () =>
      analysis
        ? Math.min(...analysis.drivers.map((driver) => driver.race_pace))
        : 0,
    [analysis],
  );
  const lapOptions = analysis?.available_laps ?? (lapNumber ? [lapNumber] : []);

  const changeLap = (value: string) => {
    if (value === "best") {
      setLapMode("best");
      setLapNumber(undefined);
      return;
    }
    setLapMode("number");
    setLapNumber(+value);
  };

  return (
    <>
      <section className="hero lab-hero">
        <div>
          <p className="eyebrow">TELEMETRY LAB</p>
          <h1>Ogni sessione, giro per giro.</h1>
          <p className="subtitle">
            Passo, degrado, velocità e percorrenza curva ricavati dai dati
            FastF1 appena una sessione è disponibile.
          </p>
        </div>
      </section>

      <section className="selectors analysis-selectors panel">
        <label>
          STAGIONE
          <select value={year} onChange={(event) => setYear(+event.target.value)}>
            {Array.from({ length: currentYear - 2017 }, (_, index) => currentYear - index).map(
              (item) => <option key={item}>{item}</option>,
            )}
          </select>
        </label>
        <label>
          GRAN PREMIO
          <select
            value={round ?? ""}
            onChange={(event) => setRound(+event.target.value)}
          >
            {events.map((event) => (
              <option key={event.round} value={event.round}>
                R{event.round} · {event.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          TELEMETRIA
          <select
            value={telemetrySession}
            disabled={sessionsLoading || !availableSessions.length}
            onChange={(event) =>
              setTelemetrySession(event.target.value as TelemetrySession)
            }
          >
            {availableSessions.length ? (
              availableSessions.map((session) => (
                <option key={session.value} value={session.value}>
                  {session.label || SESSION_LABELS[session.value]}
                </option>
              ))
            ) : (
              <option value={telemetrySession}>
                {sessionsLoading ? "Carico sessioni..." : "Nessuna sessione conclusa"}
              </option>
            )}
          </select>
        </label>
      </section>

      {error && <div className="error-banner">{error}</div>}
      {loading && <div className="analysis-loading panel">Elaborazione telemetria…</div>}

      {analysis && (
        <>
          <section className="telemetry-summary">
            <div className="panel telemetry-event">
              <p className="eyebrow">SESSION REPORT</p>
              <h2>{analysis.event.name}</h2>
              <span>{analysis.event.location} · {analysis.event.year}</span>
            </div>
            <div className="panel weather-kpi">
              <span>ARIA</span>
              <strong>{analysis.weather.air_temperature ?? "—"}°C</strong>
            </div>
            <div className="panel weather-kpi">
              <span>PISTA</span>
              <strong>{analysis.weather.track_temperature ?? "—"}°C</strong>
            </div>
            <div className="panel weather-kpi">
              <span>CONDIZIONE</span>
              <strong>{analysis.weather.rainfall ? "WET" : "DRY"}</strong>
            </div>
          </section>

          <CircuitLayoutMap map={analysis.circuit_map} />

          <TelemetryChart
            drivers={analysis.drivers}
            telemetrySession={analysis.telemetry_session}
            lapMode={analysis.lap_mode}
            requestedLapNumber={analysis.requested_lap_number}
            lapOptions={lapOptions}
            lapValue={lapMode === "best" ? "best" : String(lapNumber ?? "")}
            onLapChange={changeLap}
            loading={telemetryLoading}
          />

          <section className="panel telemetry-table-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">DRIVER COMPARISON</p>
                <h2>Prestazione rappresentativa</h2>
              </div>
              <span>{analysis.drivers.length} PILOTI</span>
            </div>
            <div className="table-scroll">
              <table className="telemetry-table">
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Pilota</th>
                    <th>Passo</th>
                    <th>Gap passo</th>
                    <th>Best lap</th>
                    <th>Giro telem.</th>
                    <th>V max</th>
                    <th>Full throttle</th>
                    <th>Curve lente</th>
                    <th>Curve medie</th>
                    <th>Curve veloci</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.drivers.map((driver) => (
                    <tr key={driver.driver}>
                      <td><strong>P{driver.position ?? "—"}</strong></td>
                      <td>
                        <b>{driver.driver}</b>
                        <small>{driver.team}</small>
                      </td>
                      <td>{formatLap(driver.race_pace)}</td>
                      <td>+{(driver.race_pace - paceLeader).toFixed(3)}s</td>
                      <td>{formatLap(driver.best_lap)}</td>
                      <td>
                        {driver.telemetry_lap_number
                          ? `L${driver.telemetry_lap_number} · ${formatLap(driver.telemetry_lap)}`
                          : formatLap(driver.telemetry_lap)}
                        {driver.telemetry_lap_mode === "best" &&
                          analysis.lap_mode === "number" && (
                            <small>fallback best</small>
                          )}
                      </td>
                      <td>{driver.top_speed ?? "—"} km/h</td>
                      <td>{driver.full_throttle_pct ?? "—"}%</td>
                      <td>{driver.corners.slow.average_min_speed ?? "—"} km/h</td>
                      <td>{driver.corners.medium.average_min_speed ?? "—"} km/h</td>
                      <td>{driver.corners.fast.average_min_speed ?? "—"} km/h</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="degradation-grid">
            {analysis.drivers.slice(0, 10).map((driver) => (
              <div className="panel degradation-card" key={driver.driver}>
                <div>
                  <strong>{driver.driver}</strong>
                  <span>{driver.team}</span>
                </div>
                {driver.stints.map((stint) => (
                  <p key={stint.stint}>
                    <i className={`tyre ${stint.compound.toLowerCase()}`} />
                    <span>{stint.compound} · {stint.laps} giri</span>
                    <b>
                      {stint.pace_trend_seconds_per_lap !== undefined
                        ? `${stint.pace_trend_seconds_per_lap > 0 ? "+" : ""}${stint.pace_trend_seconds_per_lap}s/giro`
                        : "—"}
                    </b>
                  </p>
                ))}
              </div>
            ))}
          </section>

          <p className="data-note">
            {analysis.methodology.representative_lap}. {analysis.methodology.race_pace}.
            Le classi curva sono proxy basati sulla velocità minima nella
            finestra attorno a ciascuna curva FastF1.{" "}
            {analysis.methodology.stint_trend}.
          </p>
        </>
      )}
    </>
  );
}
