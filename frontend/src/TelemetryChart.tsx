import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import type { PostRaceAnalysis } from "./types";

type Driver = PostRaceAnalysis["drivers"][number];
type Channel = "speed" | "throttle" | "brake";
type Range = { start: number; end: number };

const COLORS = [
  "#ff2b36",
  "#3d8bff",
  "#ffd23f",
  "#a76cff",
  "#35c778",
  "#ff8c42",
  "#38cfd9",
  "#ff69b4",
];

const CHANNELS: Record<
  Channel,
  { label: string; index: 1 | 2 | 3; unit: string; fixedMax?: number }
> = {
  speed: { label: "Velocità", index: 1, unit: "km/h" },
  throttle: { label: "Acceleratore", index: 2, unit: "%", fixedMax: 100 },
  brake: { label: "Freno", index: 3, unit: "%", fixedMax: 100 },
};

const SESSION_LABELS: Record<PostRaceAnalysis["telemetry_session"], string> = {
  fp1: "BEST LAP FP1",
  fp2: "BEST LAP FP2",
  fp3: "BEST LAP FP3",
  sprint_qualifying: "BEST LAP SPRINT QUALI",
  sprint: "BEST LAP SPRINT",
  qualifying: "BEST LAP QUALIFICA",
  race: "BEST LAP GARA",
};

function formatLap(seconds?: number) {
  if (seconds === undefined) return "-";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function TelemetryChart({
  drivers,
  telemetrySession,
  lapMode,
  requestedLapNumber,
  lapOptions,
  lapValue,
  onLapChange,
  loading,
}: {
  drivers: Driver[];
  telemetrySession: PostRaceAnalysis["telemetry_session"];
  lapMode?: PostRaceAnalysis["lap_mode"];
  requestedLapNumber?: number | null;
  lapOptions?: number[];
  lapValue?: string;
  onLapChange?: (value: string) => void;
  loading?: boolean;
}) {
  const available = useMemo(
    () => drivers.filter((driver) => driver.telemetry_trace.length > 1),
    [drivers],
  );
  const [selected, setSelected] = useState<string[]>([]);
  const [channel, setChannel] = useState<Channel>("speed");
  const [viewRange, setViewRange] = useState<Range | null>(null);
  const [dragStart, setDragStart] = useState<number | null>(null);
  const [dragEnd, setDragEnd] = useState<number | null>(null);
  const [overviewDragging, setOverviewDragging] = useState(false);

  useEffect(() => {
    setSelected(available.slice(0, 3).map((driver) => driver.driver));
  }, [available]);

  const selectedDrivers = available.filter((driver) =>
    selected.includes(driver.driver),
  );
  const definition = CHANNELS[channel];
  const maxDistance = Math.max(
    ...available.flatMap((driver) =>
      driver.telemetry_trace.map((point) => point[0]),
    ),
    1,
  );
  const visibleStart = viewRange?.start ?? 0;
  const visibleEnd = viewRange?.end ?? maxDistance;
  const visibleSpan = Math.max(visibleEnd - visibleStart, 1);
  const visibleDrivers = selectedDrivers.map((driver) => ({
    ...driver,
    telemetry_trace: driver.telemetry_trace.filter(
      (point) => point[0] >= visibleStart && point[0] <= visibleEnd,
    ),
  }));
  const rawMax = Math.max(
    ...visibleDrivers.flatMap((driver) =>
      driver.telemetry_trace.map((point) => point[definition.index]),
    ),
    1,
  );
  const maxValue =
    definition.fixedMax ?? Math.ceil((rawMax + 10) / 50) * 50;

  const width = 1000;
  const height = 360;
  const padding = { left: 58, right: 18, top: 22, bottom: 42 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const x = (distance: number) =>
    padding.left + ((distance - visibleStart) / visibleSpan) * plotWidth;
  const y = (value: number) =>
    padding.top + plotHeight - (value / maxValue) * plotHeight;
  const selectionStart = dragStart === null || dragEnd === null
    ? null
    : Math.min(dragStart, dragEnd);
  const selectionEnd = dragStart === null || dragEnd === null
    ? null
    : Math.max(dragStart, dragEnd);
  const rangeLabel = viewRange
    ? `${(visibleStart / 1000).toFixed(2)}-${(visibleEnd / 1000).toFixed(2)} km`
    : "Giro completo";

  useEffect(() => {
    setViewRange((current) => {
      if (!current || current.end <= maxDistance) return current;
      return null;
    });
  }, [maxDistance]);

  function toggleDriver(driver: string) {
    setSelected((current) =>
      current.includes(driver)
        ? current.filter((item) => item !== driver)
        : [...current, driver],
    );
  }

  function distanceFromPointer(event: React.PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const viewX = ((event.clientX - rect.left) / rect.width) * width;
    const plotX = clamp(viewX, padding.left, width - padding.right);
    return visibleStart + ((plotX - padding.left) / plotWidth) * visibleSpan;
  }

  function distanceFromOverview(event: React.PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const viewX = ((event.clientX - rect.left) / rect.width) * width;
    const plotX = clamp(viewX, padding.left, width - padding.right);
    return ((plotX - padding.left) / plotWidth) * maxDistance;
  }

  function moveWindowTo(center: number) {
    const targetSpan = viewRange
      ? visibleSpan
      : clamp(maxDistance * 0.35, Math.max(maxDistance * 0.04, 80), maxDistance);
    const start = clamp(center - targetSpan / 2, 0, maxDistance - targetSpan);
    setViewRange(targetSpan >= maxDistance ? null : { start, end: start + targetSpan });
  }

  function zoomBy(factor: number) {
    const center = visibleStart + visibleSpan / 2;
    const nextSpan = clamp(visibleSpan * factor, Math.max(maxDistance * 0.04, 80), maxDistance);
    const nextStart = clamp(center - nextSpan / 2, 0, maxDistance - nextSpan);
    setViewRange(nextSpan >= maxDistance ? null : { start: nextStart, end: nextStart + nextSpan });
  }

  function selectPreset(count: number) {
    setSelected(available.slice(0, count).map((driver) => driver.driver));
  }

  return (
    <section className="panel telemetry-chart-panel">
      <div className="panel-heading telemetry-chart-heading">
        <div>
          <p className="eyebrow">
            {lapMode === "number" && requestedLapNumber
              ? `GIRO ${requestedLapNumber}`
              : SESSION_LABELS[telemetrySession]}
          </p>
          <h2>Confronto telemetrico</h2>
        </div>
        <div className="telemetry-tools">
          <div className="channel-switcher">
            {(Object.keys(CHANNELS) as Channel[]).map((item) => (
              <button
                className={channel === item ? "active" : ""}
                key={item}
                onClick={() => setChannel(item)}
              >
                {CHANNELS[item].label}
              </button>
            ))}
          </div>
          <div className="telemetry-zoom-tools" aria-label="Controlli zoom telemetria">
            <button onClick={() => zoomBy(0.55)} disabled={!selectedDrivers.length}>
              Zoom +
            </button>
            <button onClick={() => zoomBy(1.7)} disabled={!viewRange}>
              Zoom -
            </button>
            <button onClick={() => setViewRange(null)} disabled={!viewRange}>
              Giro completo
            </button>
          </div>
          {loading && (
            <span className="telemetry-inline-loading">Aggiorno telemetria...</span>
          )}
        </div>
      </div>

      {onLapChange && (
        <div className="lap-strip" aria-label="Selezione giro telemetrico">
          <span>GIRO</span>
          <button
            className={(lapValue ?? "best") === "best" ? "active" : ""}
            onClick={() => onLapChange("best")}
            disabled={loading}
          >
            Best
          </button>
          {(lapOptions ?? []).map((lap) => (
            <button
              className={lapValue === String(lap) ? "active" : ""}
              key={lap}
              onClick={() => onLapChange(String(lap))}
              disabled={loading}
            >
              L{lap}
            </button>
          ))}
        </div>
      )}

      <div className="driver-picker">
        <div className="driver-picker-actions">
          <span>{selectedDrivers.length}/{available.length} piloti</span>
          <button onClick={() => selectPreset(3)}>Top 3</button>
          <button onClick={() => setSelected(available.map((driver) => driver.driver))}>
            Tutti
          </button>
          <button onClick={() => setSelected([])}>Clear</button>
        </div>
        {available.map((driver, index) => {
          const active = selected.includes(driver.driver);
          return (
            <button
              className={active ? "active" : ""}
              key={driver.driver}
              onClick={() => toggleDriver(driver.driver)}
              style={{ "--driver-color": COLORS[index % COLORS.length] } as CSSProperties}
            >
              <i>{initials(driver.driver)}</i>
              <span>
                <b>{driver.driver}</b>
                <small>
                  {driver.telemetry_lap_number ? `L${driver.telemetry_lap_number}` : "BEST"} ·{" "}
                  {formatLap(driver.telemetry_lap)}
                </small>
              </span>
            </button>
          );
        })}
      </div>

      {selectedDrivers.length ? (
        <>
        <div className="telemetry-range-bar">
          <span>{rangeLabel}</span>
          <strong>Trascina sul grafico per zoomare, usa la barra sotto per navigare</strong>
        </div>
        <div className="telemetry-chart-scroll">
          <svg
            className="telemetry-chart"
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`Confronto ${definition.label.toLowerCase()} dei piloti selezionati`}
            onPointerDown={(event) => {
              const distance = distanceFromPointer(event);
              setDragStart(distance);
              setDragEnd(distance);
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              if (dragStart === null) return;
              setDragEnd(distanceFromPointer(event));
            }}
            onPointerUp={(event) => {
              if (dragStart !== null && dragEnd !== null) {
                const start = Math.min(dragStart, dragEnd);
                const end = Math.max(dragStart, dragEnd);
                if (end - start > Math.max(maxDistance * 0.015, 35)) {
                  setViewRange({ start, end });
                }
              }
              setDragStart(null);
              setDragEnd(null);
              event.currentTarget.releasePointerCapture(event.pointerId);
            }}
            onPointerCancel={() => {
              setDragStart(null);
              setDragEnd(null);
            }}
          >
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
              <g key={`y-${ratio}`}>
                <line
                  x1={padding.left}
                  x2={width - padding.right}
                  y1={padding.top + plotHeight * (1 - ratio)}
                  y2={padding.top + plotHeight * (1 - ratio)}
                />
                <text
                  x={padding.left - 10}
                  y={padding.top + plotHeight * (1 - ratio) + 4}
                  textAnchor="end"
                >
                  {Math.round(maxValue * ratio)}
                </text>
              </g>
            ))}
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
              <g key={`x-${ratio}`}>
                <line
                  x1={padding.left + plotWidth * ratio}
                  x2={padding.left + plotWidth * ratio}
                  y1={padding.top}
                  y2={padding.top + plotHeight}
                />
                <text
                  x={padding.left + plotWidth * ratio}
                  y={height - 15}
                  textAnchor="middle"
                >
                  {Math.round(((visibleStart + visibleSpan * ratio) / 1000) * 10) / 10} km
                </text>
              </g>
            ))}
            <text x={8} y={14}>{definition.unit}</text>
            {selectionStart !== null && selectionEnd !== null && (
              <rect
                className="telemetry-selection"
                x={x(selectionStart)}
                y={padding.top}
                width={Math.max(x(selectionEnd) - x(selectionStart), 1)}
                height={plotHeight}
              />
            )}
            {visibleDrivers.map((driver) => {
              const color =
                COLORS[available.findIndex((item) => item.driver === driver.driver) % COLORS.length];
              const points = driver.telemetry_trace
                .map(
                  (point) =>
                    `${x(point[0]).toFixed(1)},${y(point[definition.index]).toFixed(1)}`,
                )
                .join(" ");
              return (
                <polyline
                  key={driver.driver}
                  points={points}
                  fill="none"
                  stroke={color}
                  strokeWidth="2.2"
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
          </svg>
        </div>
        <div className="telemetry-overview">
          <svg
            viewBox={`0 0 ${width} 54`}
            role="img"
            aria-label="Navigatore della telemetria"
            onPointerDown={(event) => {
              setOverviewDragging(true);
              moveWindowTo(distanceFromOverview(event));
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              if (!overviewDragging) return;
              moveWindowTo(distanceFromOverview(event));
            }}
            onPointerUp={(event) => {
              setOverviewDragging(false);
              event.currentTarget.releasePointerCapture(event.pointerId);
            }}
            onPointerCancel={() => setOverviewDragging(false)}
            onDoubleClick={() => setViewRange(null)}
          >
            <rect x={padding.left} y="10" width={plotWidth} height="30" />
            {selectedDrivers.map((driver) => {
              const color =
                COLORS[available.findIndex((item) => item.driver === driver.driver) % COLORS.length];
              const points = driver.telemetry_trace
                .map((point) => {
                  const overviewX = padding.left + (point[0] / maxDistance) * plotWidth;
                  const overviewY = 40 - (point[definition.index] / maxValue) * 28;
                  return `${overviewX.toFixed(1)},${overviewY.toFixed(1)}`;
                })
                .join(" ");
              return <polyline key={driver.driver} points={points} fill="none" stroke={color} />;
            })}
            <rect
              className="telemetry-overview-window"
              x={padding.left + (visibleStart / maxDistance) * plotWidth}
              y="8"
              width={(visibleSpan / maxDistance) * plotWidth}
              height="34"
            />
          </svg>
        </div>
        </>
      ) : (
        <div className="chart-empty">Seleziona almeno un pilota.</div>
      )}
    </section>
  );
}
