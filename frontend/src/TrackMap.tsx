import type { Driver, DriverPoint } from "./types";

interface Props {
  locations: DriverPoint[];
  drivers: Driver[];
}

export function TrackMap({ locations, drivers }: Props) {
  const usable = locations.filter(
    (point) => point.x !== undefined && point.y !== undefined,
  );

  if (!usable.length) {
    return (
      <div className="track-empty">
        <div className="track-placeholder" />
        <span>Coordinate pista non disponibili in questo istante</span>
      </div>
    );
  }

  const xs = usable.map((point) => point.x!);
  const ys = usable.map((point) => point.y!);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const scaleX = (value: number) => 8 + ((value - minX) / (maxX - minX || 1)) * 84;
  const scaleY = (value: number) => 8 + ((value - minY) / (maxY - minY || 1)) * 84;

  return (
    <svg className="track-map" viewBox="0 0 100 100" role="img">
      <defs>
        <filter id="driverGlow">
          <feGaussianBlur stdDeviation="1.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {usable.map((point) => {
        const driver = drivers.find(
          (item) => item.driver_number === point.driver_number,
        );
        const x = scaleX(point.x!);
        const y = scaleY(point.y!);
        return (
          <g key={point.driver_number} transform={`translate(${x} ${y})`}>
            <circle
              r="2.5"
              fill={`#${driver?.team_colour ?? "ffffff"}`}
              filter="url(#driverGlow)"
            />
            <text x="3.5" y="1.3">
              {driver?.name_acronym ?? point.driver_number}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

