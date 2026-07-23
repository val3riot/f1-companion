import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { PredictionDriver, RacePrediction } from "./types";

const currentYear = new Date().getFullYear();

function formatLap(seconds?: number) {
  if (seconds === undefined) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}

function formatSignedSeconds(value?: number) {
  if (value === undefined || value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(3)}s`;
}

function modelStatusLabel(phase?: RacePrediction["phase"]) {
  if (phase === "post_qualifying") return "AGGIORNATO DOPO QUALIFICA";
  if (phase === "post_practice") return "AGGIORNATO DOPO LE LIBERE";
  return "PRE-WEEKEND";
}

export function PredictionView() {
  const [year, setYear] = useState(currentYear);
  const [baseline, setBaseline] = useState<RacePrediction>();
  const [updated, setUpdated] = useState<RacePrediction>();
  const [factorMode, setFactorMode] = useState<"selected" | "all">("selected");
  const [selectedDriverIds, setSelectedDriverIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    setLoading(true);
    setError(undefined);
    Promise.all([
      api.nextRacePrediction(year, false),
      api.nextRacePrediction(year, true),
    ])
      .then(([beforePractice, afterPractice]) => {
        setBaseline(beforePractice);
        setUpdated(afterPractice);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [year]);

  const prediction = updated ?? baseline;
  useEffect(() => {
    if (!prediction?.predictions.length) {
      setSelectedDriverIds([]);
      return;
    }
    setSelectedDriverIds((current) => {
      const available = new Set(
        prediction.predictions.map((driver) => driver.driver_id),
      );
      const kept = current.filter((driverId) => available.has(driverId));
      const fallback = prediction.predictions
        .slice(0, 3)
        .map((driver) => driver.driver_id);
      const next = [...kept];
      for (const driverId of fallback) {
        if (next.length >= 3) break;
        if (!next.includes(driverId)) next.push(driverId);
      }
      return next.slice(0, 3);
    });
  }, [prediction]);

  const baselineRanks = useMemo(
    () =>
      new Map(
        baseline?.predictions.map((driver) => [driver.driver_id, driver.rank]),
      ),
    [baseline],
  );
  const selectedDrivers = useMemo(() => {
    if (!prediction) return [];
    if (factorMode === "all") return prediction.predictions;
    const byId = new Map(
      prediction.predictions.map((driver) => [driver.driver_id, driver]),
    );
    return selectedDriverIds
      .map((driverId) => byId.get(driverId))
      .filter((driver): driver is PredictionDriver => Boolean(driver));
  }, [factorMode, prediction, selectedDriverIds]);

  const updateSelectedDriver = (index: number, driverId: string) => {
    setSelectedDriverIds((current) => {
      const next = [...current];
      next[index] = driverId;
      return next;
    });
  };

  return (
    <>
      <section className="hero prediction-hero">
        <div>
          <p className="eyebrow">RACE FORECAST</p>
          <h1>Vantaggio, non certezza.</h1>
          <p className="subtitle">
            Un ranking spiegabile che evolve dalla forma storica ai dati reali
            di libere e qualifica.
          </p>
        </div>
      </section>

      <section className="prediction-toolbar panel">
        <label>
          CAMPIONATO
          <select value={year} onChange={(event) => setYear(+event.target.value)}>
            <option>{currentYear}</option>
            <option>{currentYear + 1}</option>
          </select>
        </label>
        <div>
          <span>STATO MODELLO</span>
          <strong>{modelStatusLabel(prediction?.phase)}</strong>
        </div>
        <div>
          <span>CONFIDENZA</span>
          <strong>{prediction?.confidence ?? "—"}%</strong>
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}
      {loading && <div className="analysis-loading panel">Calcolo del ranking…</div>}

      {prediction && (
        <>
          <section className="next-race panel">
            <div>
              <p className="eyebrow">PROSSIMA GARA · ROUND {prediction.race.round}</p>
              <h2>{prediction.race.name}</h2>
              <span>
                {prediction.race.circuit_name} · {prediction.race.locality},{" "}
                {prediction.race.country} ·{" "}
                {new Date(prediction.race.date).toLocaleDateString("it-IT")}
              </span>
            </div>
            <div className="practice-status">
              <span>DATI WEEKEND</span>
              <strong>{prediction.practice_status}</strong>
            </div>
          </section>

          <section className="forecast-grid">
            <TrackProfile profile={prediction.track_profile} />
            <WeatherForecast weather={prediction.weather} />
            <UpgradeSummary upgrades={prediction.upgrades} />
            <ModelWeights weights={prediction.weights} />
          </section>

          <section className="prediction-layout">
            <div className="panel prediction-ranking">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">COMPETITIVE INDEX</p>
                  <h2>Chi parte con un vantaggio</h2>
                </div>
                <span>
                  {prediction.predictions.length} PILOTI · {prediction.completed_races} GARE
                  ANALIZZATE
                </span>
              </div>
              {prediction.predictions.map((driver) => (
                <PredictionRow
                  key={driver.driver_id}
                  driver={driver}
                  baselineRank={baselineRanks.get(driver.driver_id)}
                />
              ))}
            </div>

            <div className="panel factor-panel">
              <div className="panel-heading compact">
                <div>
                  <p className="eyebrow">PERCHÉ</p>
                  <h2>Fattore per fattore</h2>
                </div>
              </div>
              <div className="factor-controls">
                <div className="factor-mode">
                  <button
                    className={factorMode === "selected" ? "active" : ""}
                    type="button"
                    onClick={() => setFactorMode("selected")}
                  >
                    Scegli
                  </button>
                  <button
                    className={factorMode === "all" ? "active" : ""}
                    type="button"
                    onClick={() => setFactorMode("all")}
                  >
                    Tutti
                  </button>
                </div>
                {factorMode === "selected" && (
                  <div className="factor-selectors">
                    {[0, 1, 2].map((index) => (
                      <select
                        key={index}
                        value={selectedDriverIds[index] ?? ""}
                        onChange={(event) =>
                          updateSelectedDriver(index, event.target.value)
                        }
                      >
                        {prediction.predictions.map((driver) => (
                          <option key={driver.driver_id} value={driver.driver_id}>
                            {driver.driver} · {driver.team} · P{driver.rank}
                          </option>
                        ))}
                      </select>
                    ))}
                  </div>
                )}
              </div>
              {selectedDrivers.map((driver) => (
                <DriverFactors driver={driver} key={driver.driver_id} />
              ))}
            </div>
          </section>

          <p className="data-note">{prediction.disclaimer}</p>
        </>
      )}
    </>
  );
}

function PredictionRow({
  driver,
  baselineRank,
}: {
  driver: PredictionDriver;
  baselineRank?: number;
}) {
  const movement = baselineRank ? baselineRank - driver.rank : 0;
  return (
    <div className="prediction-row">
      <strong className="prediction-position">{driver.rank}</strong>
      <div className="prediction-driver">
        <b>{driver.driver}</b>
        <span>{driver.team}</span>
        {driver.practice && (
          <small>
            FP {driver.practice.score.toFixed(0)} · best{" "}
            {formatLap(driver.practice.best_lap)} ·{" "}
            {formatSignedSeconds(driver.practice.qualifying_gap)} secco ·{" "}
            {formatSignedSeconds(driver.practice.long_run_gap)} long ·{" "}
            {driver.practice.laps} giri
          </small>
        )}
        {driver.qualifying_result && (
          <small>
            QUALI P{driver.qualifying_result.position} ·{" "}
            {driver.qualifying_result.q3 ??
              driver.qualifying_result.q2 ??
              driver.qualifying_result.q1 ??
              "senza tempo"}{" "}
            · score {driver.qualifying_result.score.toFixed(0)}
          </small>
        )}
      </div>
      <div className="score-track">
        <i style={{ width: `${driver.score}%` }} />
      </div>
      <strong className="prediction-score">{driver.score}</strong>
      <span className={`movement ${movement > 0 ? "up" : movement < 0 ? "down" : ""}`}>
        {movement > 0 ? `↑${movement}` : movement < 0 ? `↓${Math.abs(movement)}` : "—"}
      </span>
    </div>
  );
}

function DriverFactors({ driver }: { driver: PredictionDriver }) {
  const factors = [
    ["Forma", driver.factors.recent_form],
    ["Forma pulita", driver.factors.clean_recent_form],
    ["Forza vettura/team", driver.factors.team_strength],
    ["Circuiti simili", driver.factors.track_affinity],
    ["Qualifica", driver.factors.qualifying],
    ["Vs compagno", driver.factors.teammate_delta],
    ["Upgrade team", driver.factors.upgrade_signal],
    [
      `Affidabilità team ${driver.evidence.technical_failures} guasti/${driver.evidence.team_starts}`,
      driver.factors.technical_reliability,
    ],
    [
      `Incidenti pilota ${driver.evidence.incidents}/${driver.evidence.starts}`,
      driver.factors.incident_avoidance,
    ],
    [
      `Fiducia pilota ${driver.evidence.confidence_events ?? driver.evidence.incidents}/${driver.evidence.starts}`,
      driver.factors.driver_confidence,
    ],
    ["Resa temp. simile", driver.factors.temperature_match],
    ["Free practice", driver.practice?.score],
    ["Qualifica reale", driver.qualifying_result?.score],
  ] as const;
  return (
    <div className="driver-factors">
      <div><strong>{driver.driver}</strong><span>{driver.score}</span></div>
      {factors.map(([label, value]) => (
        value !== undefined && (
          <p key={label}>
            <span>{label}</span>
            <i><b style={{ width: `${value}%` }} /></i>
            <strong>{value.toFixed(0)}</strong>
          </p>
        )
      ))}
      {driver.evidence.unknown_retirements > 0 && (
        <small className="factor-note">
          {driver.evidence.unknown_retirements} ritiri con causa non specificata,
          esclusi dai fattori affidabilità e incidenti.
        </small>
      )}
      {driver.factors.temperature_match !== undefined && (
        <small className="factor-note">
          Temperatura è un indice relativo sul rendimento in gare con meteo
          simile, non una temperatura in gradi.
        </small>
      )}
    </div>
  );
}

function UpgradeSummary({ upgrades }: { upgrades: RacePrediction["upgrades"] }) {
  return (
    <div className="panel forecast-card upgrade-card">
      <p className="eyebrow">UPGRADE</p>
      {upgrades.available ? (
        <>
          {upgrades.records.slice(0, 3).map((record) => (
            <div className="upgrade-row" key={`${record.team}-${record.signal}`}>
              <strong>{record.team}</strong>
              <span>{record.areas?.join(", ") || record.note || "pacchetto tecnico"}</span>
              <b>{record.signal.toFixed(0)}</b>
            </div>
          ))}
          {upgrades.validation?.map((item) => (
            <small key={item.team}>
              FP {item.team}: {item.practice_score.toFixed(0)} su {item.drivers} piloti
            </small>
          ))}
        </>
      ) : (
        <div className="forecast-unavailable">Nessun pacchetto dichiarato.</div>
      )}
    </div>
  );
}

function TrackProfile({ profile }: { profile: RacePrediction["track_profile"] }) {
  const factors = [
    ["Curve lente", profile.slow],
    ["Curve medie", profile.medium],
    ["Curve veloci", profile.fast],
    ["Rettilinei", profile.straight],
    ["Stress gomme", profile.tyre],
  ] as const;
  return (
    <div className="panel forecast-card">
      <p className="eyebrow">DNA DEL CIRCUITO</p>
      {factors.map(([label, value]) => (
        <div className="profile-row" key={label}>
          <span>{label}</span>
          <i><b style={{ width: `${value * 100}%` }} /></i>
          <strong>{Math.round(value * 100)}</strong>
        </div>
      ))}
    </div>
  );
}

function WeatherForecast({ weather }: { weather: RacePrediction["weather"] }) {
  return (
    <div className="panel forecast-card weather-forecast">
      <p className="eyebrow">METEO GARA</p>
      {weather.available ? (
        <>
          <strong>{weather.temperature_min}—{weather.temperature_max}°C</strong>
          <span>Pioggia {weather.rain_probability}%</span>
          <span>Vento max {weather.wind_speed_max} km/h</span>
          <small>{weather.source}</small>
        </>
      ) : (
        <div className="forecast-unavailable">{weather.reason}</div>
      )}
    </div>
  );
}

function ModelWeights({ weights }: { weights: Record<string, number> }) {
  const labels: Record<string, string> = {
    recent_form: "forma recente",
    clean_recent_form: "forma pulita",
    team_strength: "forza vettura/team",
    track_affinity: "circuiti simili",
    qualifying: "qualifica",
    teammate_delta: "vs compagno",
    technical_reliability: "affidabilità team",
    incident_avoidance: "incidenti pilota",
    driver_confidence: "fiducia pilota",
    temperature_match: "resa temp. simile",
    upgrade_signal: "upgrade team",
    "baseline/practice": "storico/libere",
    free_practice: "free practice",
  };
  return (
    <div className="panel forecast-card">
      <p className="eyebrow">PESI DEL MODELLO</p>
      {Object.entries(weights).map(([name, value]) => (
        <div className="weight-row" key={name}>
          <span>{labels[name] ?? name.replaceAll("_", " ")}</span>
          <strong>{Math.round(value * 100)}%</strong>
        </div>
      ))}
    </div>
  );
}
