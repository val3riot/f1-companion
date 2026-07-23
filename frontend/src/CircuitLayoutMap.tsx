import type { CircuitMap } from "./types";


type Point = { x: number; y: number };

function rotateToBottom(points: Point[], anchor?: Point) {
  if (!points.length || !anchor) return points;
  const center = {
    x: points.reduce((total, point) => total + point.x, 0) / points.length,
    y: points.reduce((total, point) => total + point.y, 0) / points.length,
  };
  const angle = Math.atan2(anchor.y - center.y, anchor.x - center.x);
  const target = Math.PI / 2;
  const rotation = target - angle;
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);

  return points.map((point) => {
    const dx = point.x - center.x;
    const dy = point.y - center.y;
    return {
      x: center.x + dx * cos - dy * sin,
      y: center.y + dx * sin + dy * cos,
    };
  });
}

export function CircuitLayoutMap({ map }: { map: CircuitMap }) {
  const tracePoints = map.trace.map(([x, y]) => ({ x, y }));
  const cornerPoints = map.corners.map((corner) => ({
    ...corner,
    label: `${corner.number}${corner.letter ?? ""}`,
  }));
  const points = [...tracePoints, ...cornerPoints];

  if (!points.length) {
    return (
      <section className="panel circuit-layout-panel">
        <div className="panel-heading compact">
          <div>
            <p className="eyebrow">LAYOUT</p>
            <h2>Tracciato non disponibile</h2>
          </div>
        </div>
        <div className="circuit-layout-empty">
          FastF1 non ha coordinate circuito per questa sessione.
        </div>
      </section>
    );
  }

  const cornerOne = cornerPoints.find((corner) => corner.number === 1);
  const rotated = rotateToBottom(points, cornerOne);
  const rotatedTrace = rotated.slice(0, tracePoints.length);
  const rotatedCorners = rotated.slice(tracePoints.length).map((point, index) => ({
    ...cornerPoints[index],
    x: point.x,
    y: point.y,
  }));
  const xs = rotated.map((point) => point.x);
  const ys = rotated.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const width = maxX - minX || 1;
  const height = maxY - minY || 1;
  const padding = 8;
  const scaleX = (value: number) =>
    padding + ((value - minX) / width) * (100 - padding * 2);
  const scaleY = (value: number) =>
    padding + ((value - minY) / height) * (100 - padding * 2);
  const path = rotatedTrace
    .map(({ x, y }) => `${scaleX(x).toFixed(2)},${scaleY(y).toFixed(2)}`)
    .join(" ");

  return (
    <section className="panel circuit-layout-panel">
      <div className="panel-heading compact">
        <div>
          <p className="eyebrow">LAYOUT {map.source}</p>
          <h2>Tracciato e curve</h2>
        </div>
        <span>{map.corners.length} CURVE</span>
      </div>
      <svg
        className="circuit-layout-map"
        viewBox="0 0 100 100"
        role="img"
        aria-label="Mappa del tracciato con numeri curva"
      >
        {map.trace.length > 1 && (
          <polyline
            className="circuit-layout-line"
            points={path}
            fill="none"
            vectorEffect="non-scaling-stroke"
          />
        )}
        {rotatedCorners.map((corner) => {
          const x = scaleX(corner.x);
          const y = scaleY(corner.y);
          return (
            <g
              className="circuit-corner"
              key={`${corner.label}-${corner.distance ?? `${corner.x}-${corner.y}`}`}
              transform={`translate(${x} ${y})`}
            >
              <circle r="1.8" />
              <text x="2.8" y="1.2">{corner.label}</text>
            </g>
          );
        })}
      </svg>
      <p className="circuit-layout-note">
        Layout ricostruito dalle coordinate FastF1 della sessione selezionata;
        le curve arrivano dal circuito info dello stesso evento. La vista viene
        ruotata per posizionare curva 1 nella parte bassa del riquadro quando
        disponibile.
      </p>
    </section>
  );
}
