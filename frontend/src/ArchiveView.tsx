import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { CircuitLayoutMap } from "./CircuitLayoutMap";
import type {
  CircuitHistory,
  CircuitLayout,
  CircuitOption,
  RankedStat,
} from "./types";

const DEFAULT_CIRCUIT = "monza";

function formatLap(seconds?: number) {
  if (seconds === undefined) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}

function ArchiveView() {
  const [circuits, setCircuits] = useState<CircuitOption[]>([]);
  const [circuitId, setCircuitId] = useState(DEFAULT_CIRCUIT);
  const [history, setHistory] = useState<CircuitHistory>();
  const [layoutYear, setLayoutYear] = useState<number>();
  const [layout, setLayout] = useState<CircuitLayout>();
  const [layoutLoading, setLayoutLoading] = useState(false);
  const [layoutError, setLayoutError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  useEffect(() => {
    api
      .circuits()
      .then((items) =>
        setCircuits(
          [...items].sort(
            (a, b) =>
              a.country.localeCompare(b.country) ||
              a.name.localeCompare(b.name),
          ),
        ),
      )
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(undefined);
    api
      .circuitHistory(circuitId)
      .then(setHistory)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [circuitId]);

  const layoutYears = useMemo(
    () =>
      [...new Set((history?.editions ?? []).map((edition) => edition.year))]
        .filter((year) => year >= 2018)
        .sort((a, b) => b - a),
    [history],
  );

  useEffect(() => {
    setLayout(undefined);
    setLayoutError(undefined);
    setLayoutYear(layoutYears[0]);
  }, [layoutYears]);

  useEffect(() => {
    if (!layoutYear) return;
    setLayoutLoading(true);
    setLayoutError(undefined);
    setLayout(undefined);
    api
      .circuitLayout(circuitId, layoutYear)
      .then(setLayout)
      .catch((reason: Error) => setLayoutError(reason.message))
      .finally(() => setLayoutLoading(false));
  }, [circuitId, layoutYear]);

  const groupedCircuits = useMemo(
    () =>
      Object.entries(
        circuits.reduce<Record<string, CircuitOption[]>>((groups, circuit) => {
          (groups[circuit.country] ??= []).push(circuit);
          return groups;
        }, {}),
      ),
    [circuits],
  );

  return (
    <>
      <section className="hero archive-hero">
        <div>
          <p className="eyebrow">
            {history?.circuit.country ?? "FORMULA 1"} · CIRCUIT DOSSIER
          </p>
          <h1>{history?.circuit.name ?? "La storia, curva dopo curva."}</h1>
          <p className="subtitle">
            {history
              ? `${history.circuit.locality} · ${history.overview.first_year ?? "—"}—${history.overview.last_year ?? "—"}`
              : "Risultati, record e tendenze di ogni circuito del mondiale."}
          </p>
        </div>
        {history?.circuit.image && (
          <img
            className="circuit-hero"
            src={history.circuit.image}
            alt={history.circuit.name}
          />
        )}
      </section>

      <section className="circuit-selector panel">
        <label>
          CIRCUITO
          <select
            value={circuitId}
            onChange={(event) => setCircuitId(event.target.value)}
          >
            {groupedCircuits.map(([country, items]) => (
              <optgroup key={country} label={country}>
                {items.map((circuit) => (
                  <option key={circuit.id} value={circuit.id}>
                    {circuit.name} · {circuit.locality}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <div className="selector-meta">
          <span>COORDINATE</span>
          <strong>
            {history
              ? `${history.circuit.latitude.toFixed(4)}, ${history.circuit.longitude.toFixed(4)}`
              : "—"}
          </strong>
        </div>
        {history && (
          <a href={history.circuit.url} target="_blank" rel="noreferrer">
            SCHEDA CIRCUITO ↗
          </a>
        )}
      </section>

      {error && <div className="error-banner">{error}</div>}
      {history?.data_status?.historical_reason && (
        <div className="error-banner soft">
          {history.data_status.historical_reason}. Archivio aperto con i dati
          circuito disponibili.
        </div>
      )}

      {history && (
        <>
          <section className="kpi-grid">
            <Kpi
              label="EDIZIONI MONDIALI"
              value={history.overview.editions}
              detail={
                history.overview.first_year && history.overview.last_year
                  ? `${history.overview.first_year}—${history.overview.last_year}`
                  : "storico non disponibile"
              }
              accent
            />
            <Kpi
              label="VINCITORI DIVERSI"
              value={history.overview.unique_winners}
              detail={`${history.overview.unique_constructors} costruttori`}
            />
            <Kpi
              label="VITTORIE DALLA POLE"
              value={`${history.overview.wins_from_pole_rate ?? 0}%`}
              detail={`${history.overview.wins_from_pole} gare`}
            />
            <Kpi
              label="AFFIDABILITÀ"
              value={`${history.overview.completion_rate ?? 0}%`}
              detail={`${history.overview.total_starters} partenze`}
            />
            <Kpi
              label="GRIGLIA MEDIA VINCENTE"
              value={`P${history.overview.average_winner_grid ?? "—"}`}
              detail="posizione di partenza"
            />
          </section>

          <section className="record-grid">
            <div className="panel hero-record">
              <div>
                <p className="eyebrow">RECORD SUL GIRO DISPONIBILE</p>
                <strong>{history.records.lap?.time ?? "—"}</strong>
                <span>
                  {history.records.lap
                    ? `${history.records.lap.driver} · ${history.records.lap.constructor} · ${history.records.lap.year}`
                    : "Dato non disponibile"}
                </span>
              </div>
              <div className="record-speed">
                <span>VELOCITÀ MEDIA</span>
                <strong>
                  {history.records.lap?.average_speed
                    ? `${history.records.lap.average_speed} km/h`
                    : "—"}
                </strong>
              </div>
            </div>
            <div className="panel comeback-card">
              <div className="panel-heading compact">
                <div>
                  <p className="eyebrow">SU QUESTO CIRCUITO</p>
                  <h2>Da più indietro</h2>
                </div>
              </div>
              {history.records.best_comebacks.slice(0, 3).map((item) => (
                <div className="comeback-row" key={`${item.year}-${item.driver}`}>
                  <strong>P{item.grid}</strong>
                  <span>{item.driver}</span>
                  <small>{item.year}</small>
                </div>
              ))}
            </div>
          </section>

          <section className="leader-grid">
            <Ranking
              title="Più vittorie"
              eyebrow="PILOTI"
              rows={history.leaders.wins}
            />
            <Ranking
              title="Più vittorie"
              eyebrow="COSTRUTTORI"
              rows={history.leaders.constructor_wins}
            />
            <Ranking
              title="Più podi"
              eyebrow="CONSISTENZA"
              rows={history.leaders.podiums}
            />
            <Ranking
              title="Più pole"
              eyebrow="QUALIFICA"
              rows={history.leaders.poles}
            />
          </section>

          <section className="analysis-grid">
            <Distribution
              title="Da dove si vince"
              eyebrow="POSIZIONE IN GRIGLIA"
              rows={history.winning_grid}
            />
            <OpenF1Panel data={history} />
          </section>

          <LayoutArchivePanel
            error={layoutError}
            layout={layout}
            loading={layoutLoading}
            onYearChange={setLayoutYear}
            selectedYear={layoutYear}
            years={layoutYears}
          />

          <EditionsTable editions={history.editions} />

          <p className="data-note">
            I dati all-time provengono da Jolpica. Il record sul giro riflette
            quanto disponibile nel dataset e può non coincidere con il record
            ufficiale del tracciato. Pit stop, mescole, sorpassi e meteo hanno
            copertura OpenF1 dal 2023.
          </p>
        </>
      )}

      {loading && <div className="loading-line" />}
    </>
  );
}

function LayoutArchivePanel({
  error,
  layout,
  loading,
  onYearChange,
  selectedYear,
  years,
}: {
  error?: string;
  layout?: CircuitLayout;
  loading: boolean;
  onYearChange: (year: number) => void;
  selectedYear?: number;
  years: number[];
}) {
  if (!years.length) {
    return (
      <section className="panel layout-archive-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">LAYOUT HISTORY</p>
            <h2>Evoluzione tracciato</h2>
          </div>
        </div>
        <div className="empty-state">
          Layout FastF1 disponibili solo per stagioni recenti.
        </div>
      </section>
    );
  }

  return (
    <section className="layout-archive-panel">
      <div className="panel layout-archive-toolbar">
        <div>
          <p className="eyebrow">LAYOUT HISTORY</p>
          <h2>Evoluzione tracciato</h2>
          <span>
            Scorri le edizioni con copertura FastF1 per confrontare varianti e
            numeri curva.
          </span>
        </div>
        <label>
          ANNO
          <select
            value={selectedYear ?? ""}
            onChange={(event) => onYearChange(+event.target.value)}
          >
            {years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </label>
      </div>
      {loading && (
        <div className="analysis-loading panel">Caricamento layout…</div>
      )}
      {error && <div className="error-banner">{error}</div>}
      {layout && (
        <>
          <CircuitLayoutMap map={layout.circuit_map} />
          <p className="data-note">
            {layout.event.name} · Round {layout.event.round} ·{" "}
            {new Date(layout.event.date).toLocaleDateString("it-IT")}. La
            mappa usa la sessione Race FastF1 dell'edizione selezionata.
          </p>
        </>
      )}
    </section>
  );
}

function Kpi({
  label,
  value,
  detail,
  accent = false,
}: {
  label: string;
  value: string | number;
  detail: string;
  accent?: boolean;
}) {
  return (
    <div className={`panel kpi ${accent ? "accent" : ""}`}>
      <p className="eyebrow">{label}</p>
      <strong>{value}</strong>
      <span>{detail}</span>
    </div>
  );
}

function Ranking({
  title,
  eyebrow,
  rows,
}: {
  title: string;
  eyebrow: string;
  rows: RankedStat[];
}) {
  const max = rows[0]?.value ?? 1;
  return (
    <div className="panel ranking">
      <div className="panel-heading compact">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="ranking-list">
        {rows.slice(0, 6).map((row, index) => (
          <div className="rank-row" key={row.name}>
            <span className="rank-position">{index + 1}</span>
            <div>
              <strong>{row.name}</strong>
              <span
                className="bar"
                style={{ width: `${Math.max(5, (row.value / max) * 100)}%` }}
              />
            </div>
            <b>{row.value}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function Distribution({
  title,
  eyebrow,
  rows,
}: {
  title: string;
  eyebrow: string;
  rows: RankedStat[];
}) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <div className="panel distribution">
      <div className="panel-heading compact">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="distribution-chart">
        {rows.map((row) => (
          <div className="distribution-column" key={row.name}>
            <span>{row.value}</span>
            <i style={{ height: `${Math.max(4, (row.value / max) * 100)}%` }} />
            <small>{row.name}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function OpenF1Panel({ data }: { data: CircuitHistory }) {
  const openf1 = data.openf1;
  return (
    <div className="panel openf1-panel">
      <div className="panel-heading compact">
        <div>
          <p className="eyebrow">ANALISI AVANZATA</p>
          <h2>Era OpenF1</h2>
        </div>
        <span>
          {openf1.coverage?.from ?? "—"}—{openf1.coverage?.to ?? "—"}
        </span>
      </div>
      {!openf1.available ? (
        <div className="empty-state">
          {openf1.reason ??
            "Questo circuito non ha sessioni OpenF1 dal 2023."}
        </div>
      ) : (
        <>
          <div className="openf1-metrics">
            <div>
              <span>SORPASSI / GP</span>
              <strong>{openf1.overtakes?.average_per_race ?? "—"}</strong>
            </div>
            <div>
              <span>PIT STOP / GP</span>
              <strong>{openf1.pit_stops?.average_per_race ?? "—"}</strong>
            </div>
            <div>
              <span>PIT MEDIO</span>
              <strong>
                {openf1.pit_stops?.average_duration
                  ? `${openf1.pit_stops.average_duration}s`
                  : "—"}
              </strong>
            </div>
            <div>
              <span>GARE BAGNATE</span>
              <strong>{openf1.wet_races?.length ?? 0}</strong>
            </div>
          </div>
          <div className="openf1-records">
            <p>
              <span>Miglior giro 2023+</span>
              <strong>
                {formatLap(openf1.fastest_lap?.lap_duration)}
                {openf1.fastest_lap?.driver_name
                  ? ` · ${openf1.fastest_lap.driver_name}`
                  : ""}
              </strong>
            </p>
            <p>
              <span>Pit più rapido</span>
              <strong>
                {openf1.pit_stops?.fastest
                  ? `${openf1.pit_stops.fastest.pit_duration.toFixed(2)}s · ${openf1.pit_stops.fastest.year}`
                  : "—"}
              </strong>
            </p>
          </div>
          <div className="compound-list">
            {openf1.compounds?.map((compound) => (
              <span key={compound.name}>
                <i className={`tyre ${compound.name.toLowerCase()}`} />
                {compound.name} <b>{compound.value}</b>
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function EditionsTable({
  editions,
}: {
  editions: CircuitHistory["editions"];
}) {
  return (
    <section className="panel editions-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">ALBO E TENDENZE</p>
          <h2>Tutte le edizioni</h2>
        </div>
        <span>{editions.length} GARE</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Anno</th>
              <th>Vincitore</th>
              <th>Costruttore</th>
              <th>Griglia</th>
              <th>Pole</th>
              <th>Giro veloce</th>
              <th>Ritiri</th>
            </tr>
          </thead>
          <tbody>
            {editions.map((edition) => (
              <tr key={`${edition.year}-${edition.date}`}>
                <td><strong>{edition.year}</strong></td>
                <td>{edition.winner}</td>
                <td>{edition.constructor}</td>
                <td>
                  <span className={edition.grid === 1 ? "pole-badge" : ""}>
                    P{edition.grid}
                  </span>
                </td>
                <td>{edition.pole ?? "—"}</td>
                <td>
                  {edition.fastest_lap
                    ? `${edition.fastest_lap} · ${edition.fastest_lap_driver}`
                    : "—"}
                </td>
                <td>{edition.dnfs}/{edition.starters}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default ArchiveView;
