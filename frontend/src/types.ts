export interface Meeting {
  meeting_key: number;
  meeting_name: string;
  meeting_official_name: string;
  location: string;
  country_name: string;
  country_code: string;
  country_flag?: string;
  circuit_short_name: string;
  circuit_image?: string;
  date_start: string;
  date_end: string;
}

export interface Session {
  session_key: number;
  session_name: string;
  session_type: string;
  date_start: string;
  date_end: string;
  meeting_key: number;
  location: string;
  country_name: string;
  circuit_short_name: string;
}

export interface Driver {
  driver_number: number;
  full_name: string;
  name_acronym: string;
  team_name: string;
  team_colour: string;
  headshot_url?: string;
}

export interface DriverPoint {
  driver_number: number;
  date?: string;
  position?: number;
  gap_to_leader?: number | string | null;
  interval?: number | string | null;
  last_lap_time?: string | null;
  last_lap_duration?: number | null;
  best_lap_time?: string | null;
  best_lap_duration?: number | null;
  x?: number;
  y?: number;
  z?: number;
  mapped_to_track?: boolean;
  speed?: number;
  rpm?: number;
  n_gear?: number;
  throttle?: number;
  brake?: number;
  drs?: number;
}

export interface Result {
  driver_number: number;
  position?: number;
  number_of_laps?: number;
  duration?: number;
  gap_to_leader?: number | string | null;
  dnf?: boolean;
  dns?: boolean;
  dsq?: boolean;
}

export interface BestLap {
  driver_number: number;
  lap_duration: number;
  lap_number: number;
  sectors?: Array<{
    number: number;
    time?: string | null;
    status: string;
    segments: Array<{
      number: number;
      status: string;
      time?: string | null;
    }>;
  }>;
}

export interface Snapshot {
  provider?: string;
  session: Session;
  cursor: string;
  is_live_window: boolean;
  status?: {
    provider: string;
    started: boolean;
    connected: boolean;
    authenticated: boolean;
    token_source?: string;
    subscribed_at?: string | null;
    last_message_at?: string | null;
    last_error?: string | null;
    topics: string[];
    note?: string;
  };
  drivers: Driver[];
  results: Result[];
  positions: DriverPoint[];
  intervals: DriverPoint[];
  locations: DriverPoint[];
  track_map?: {
    source: string;
    coordinate_system?: string;
    driver_number: number;
    trace: Array<[x: number, y: number]>;
    coverage: Record<string, number>;
    corners?: Array<{
      number: number;
      letter?: string;
      distance?: number;
      x: number;
      y: number;
    }>;
  } | null;
  telemetry: DriverPoint[];
  weather: {
    air_temperature?: number;
    track_temperature?: number;
    humidity?: number;
    rainfall?: number;
    wind_speed?: number;
  } | null;
  best_lap: BestLap | null;
  best_laps?: BestLap[];
  track_status?: {
    Status?: string;
    Message?: string;
  } | null;
  race_control?: {
    Messages?: Array<{
      Utc?: string;
      Lap?: number;
      Category?: string;
      Flag?: string;
      Scope?: string;
      RacingNumber?: string;
      Message?: string;
    }>;
  } | null;
  team_radio?: Array<{
    utc?: string;
    driver_number?: number;
    path?: string;
    url?: string;
    message?: string;
    transcript?: string;
    translation_it?: string;
    transcription_status?: "pending" | "queued" | "transcribing" | "done" | "error";
    transcription_error?: string;
  }>;
  lap_count?: {
    CurrentLap?: number;
    TotalLaps?: number;
  } | null;
}

export interface CircuitOption {
  id: string;
  name: string;
  locality: string;
  country: string;
}

export interface RankedStat {
  name: string;
  value: number;
}

export interface CircuitMap {
  source: string;
  trace: Array<[x: number, y: number]>;
  corners: Array<{
    number: number;
    letter?: string;
    distance?: number;
    x: number;
    y: number;
  }>;
}

export interface CircuitLayout {
  event: {
    year: number;
    round: number;
    name: string;
    location: string;
    date: string;
  };
  circuit_map: CircuitMap;
}

export interface CircuitHistory {
  circuit: {
    id: string;
    name: string;
    locality: string;
    country: string;
    latitude: number;
    longitude: number;
    url: string;
    image?: string;
  };
  data_status?: {
    historical_available: boolean;
    historical_reason?: string | null;
  };
  overview: {
    editions: number;
    first_year?: number;
    last_year?: number;
    unique_winners: number;
    unique_constructors: number;
    total_starters: number;
    completion_rate?: number;
    wins_from_pole: number;
    wins_from_pole_rate?: number;
    average_winner_grid?: number;
  };
  records: {
    lap: {
      seconds: number;
      time: string;
      driver: string;
      constructor: string;
      year: number;
      lap: number;
      average_speed?: number | null;
    } | null;
    best_comebacks: Array<{
      year: number;
      driver: string;
      grid: number;
    }>;
  };
  leaders: {
    wins: RankedStat[];
    constructor_wins: RankedStat[];
    podiums: RankedStat[];
    poles: RankedStat[];
  };
  winning_grid: RankedStat[];
  editions: Array<{
    year: number;
    date: string;
    race_name: string;
    winner: string;
    constructor: string;
    grid: number;
    pole?: string;
    fastest_lap_driver?: string;
    fastest_lap?: string;
    dnfs: number;
    starters: number;
  }>;
  openf1: {
    available: boolean;
    reason?: string;
    coverage: {
      from?: number;
      to?: number;
      races: number;
    } | null;
    fastest_lap?: {
      driver_number: number;
      driver_name?: string;
      lap_duration: number;
      lap_number: number;
      session_key: number;
    };
    pit_stops?: {
      total: number;
      average_per_race?: number;
      average_duration?: number;
      fastest?: {
        driver_number: number;
        driver_name?: string;
        pit_duration: number;
        lap_number: number;
        year: number;
      };
    };
    compounds?: RankedStat[];
    overtakes?: {
      total: number;
      average_per_race?: number;
      by_year: Array<{ year: number; value: number }>;
    };
    wet_races?: number[];
  };
}

export interface AnalysisEvent {
  round: number;
  name: string;
  date: string;
  circuit: string;
  completed: boolean;
}

export type TelemetrySession =
  | "fp1"
  | "fp2"
  | "fp3"
  | "sprint_qualifying"
  | "sprint"
  | "qualifying"
  | "race";

export interface AnalysisSession {
  value: TelemetrySession;
  label: string;
  name: string;
  date: string;
}

export interface CornerMetric {
  corners: number;
  average_min_speed?: number;
  average_speed?: number;
}

export interface PostRaceAnalysis {
  event: {
    year: number;
    round: number;
    name: string;
    location: string;
    date: string;
  };
  telemetry_session: TelemetrySession;
  lap_mode: "best" | "number";
  requested_lap_number?: number | null;
  available_laps: number[];
  circuit_map: CircuitMap;
  methodology: {
    representative_lap: string;
    race_pace: string;
    corner_classes: Record<string, string>;
    stint_trend: string;
  };
  weather: {
    air_temperature?: number;
    track_temperature?: number;
    rainfall?: boolean;
  };
  drivers: Array<{
    driver: string;
    full_name: string;
    team: string;
    position?: number;
    race_pace: number;
    best_lap: number;
    telemetry_lap?: number;
    telemetry_lap_number?: number | null;
    telemetry_lap_mode?: "best" | "number";
    requested_lap_number?: number | null;
    top_speed?: number;
    full_throttle_pct?: number;
    braking_pct?: number;
    corners: {
      slow: CornerMetric;
      medium: CornerMetric;
      fast: CornerMetric;
    };
    stints: Array<{
      stint: number;
      compound: string;
      laps: number;
      median_lap: number;
      pace_trend_seconds_per_lap?: number;
    }>;
    available_laps: Array<{
      lap_number: number;
      lap_time: number;
      compound?: string;
      stint?: number | null;
    }>;
    telemetry_trace: Array<
      [distance: number, speed: number, throttle: number, brake: number]
    >;
  }>;
}

export interface PredictionDriver {
  rank: number;
  driver_id: string;
  driver: string;
  full_name: string;
  team: string;
  score: number;
  factors: {
    recent_form?: number;
    clean_recent_form?: number;
    team_strength?: number;
    track_affinity?: number;
    qualifying?: number;
    teammate_delta?: number;
    technical_reliability?: number;
    incident_avoidance?: number;
    driver_confidence?: number;
    temperature_match?: number;
    upgrade_signal?: number;
  };
  evidence: {
    technical_failures: number;
    team_starts: number;
    incidents: number;
    starts: number;
    unknown_retirements: number;
    sporting_events?: number;
    confidence_events?: number;
  };
  practice?: {
    best_lap?: number;
    qualifying_gap: number;
    long_run_gap?: number;
    laps: number;
    score: number;
    sessions?: string[];
  } | null;
  qualifying_result?: {
    position: number;
    q1?: string | null;
    q2?: string | null;
    q3?: string | null;
    score: number;
  } | null;
}

export interface RacePrediction {
  race: {
    year: number;
    round: number;
    name: string;
    date: string;
    time?: string;
    circuit_id: string;
    circuit_name: string;
    locality: string;
    country: string;
  };
  phase: "baseline" | "post_practice" | "post_qualifying";
  practice_status: string;
  confidence: number;
  completed_races: number;
  track_profile: {
    slow: number;
    medium: number;
    fast: number;
    straight: number;
    tyre: number;
  };
  weather: {
    available: boolean;
    reason?: string;
    source?: string;
    temperature_min?: number;
    temperature_max?: number;
    rain_probability?: number;
    wind_speed_max?: number;
  };
  upgrades: {
    available: boolean;
    source: string;
    records: Array<{
      year: number;
      round: number;
      team: string;
      magnitude?: number;
      confidence?: number;
      areas?: string[];
      source?: string;
      note?: string;
      signal: number;
    }>;
    signals: Record<string, number>;
    validation?: Array<{
      team: string;
      practice_score: number;
      drivers: number;
    }> | null;
    note: string;
  };
  weights: Record<string, number>;
  predictions: PredictionDriver[];
  disclaimer: string;
}
