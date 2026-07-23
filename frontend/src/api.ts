import type {
  CircuitHistory,
  CircuitOption,
  CircuitLayout,
  AnalysisEvent,
  AnalysisSession,
  Meeting,
  PostRaceAnalysis,
  RacePrediction,
  Session,
  Snapshot,
  TelemetrySession,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Errore durante il caricamento");
  }
  return response.json() as Promise<T>;
}

export const api = {
  analysisEvents: (year: number) =>
    request<AnalysisEvent[]>(`/api/analysis/events?year=${year}`),
  analysisSessions: (year: number, round: number) =>
    request<AnalysisSession[]>(
      `/api/analysis/sessions?year=${year}&round_number=${round}`,
    ),
  postRace: (
    year: number,
    round: number,
    telemetrySession: TelemetrySession,
    lapMode: "best" | "number" = "best",
    lapNumber?: number,
  ) =>
    request<PostRaceAnalysis>(
      `/api/analysis/post-race?year=${year}&round_number=${round}&telemetry_session=${telemetrySession}&lap_mode=${lapMode}${lapMode === "number" && lapNumber ? `&lap_number=${lapNumber}` : ""}`,
    ),
  nextRacePrediction: (year: number, includePractice: boolean) =>
    request<RacePrediction>(
      `/api/predictions/next-race?year=${year}&include_practice=${includePractice}`,
    ),
  circuits: () => request<CircuitOption[]>("/api/circuits"),
  circuitHistory: (circuitId: string) =>
    request<CircuitHistory>(
      `/api/circuits/${encodeURIComponent(circuitId)}/history`,
    ),
  circuitLayout: (circuitId: string, year: number) =>
    request<CircuitLayout>(
      `/api/circuits/${encodeURIComponent(circuitId)}/layout?year=${year}`,
    ),
  seasons: () =>
    request<{ seasons: number[] }>("/api/seasons").then(
      (result) => result.seasons,
    ),
  meetings: (year: number) =>
    request<Meeting[]>(`/api/meetings?year=${year}`),
  sessions: (meetingKey: number) =>
    request<Session[]>(`/api/sessions?meeting_key=${meetingKey}`),
  snapshot: (sessionKey: number) =>
    request<Snapshot>(`/api/snapshot?session_key=${sessionKey}`),
  f1SignalSnapshot: () =>
    request<Snapshot>("/api/f1signal/snapshot"),
  transcribeTeamRadio: (path: string) =>
    request<NonNullable<Snapshot["team_radio"]>[number]>(
      `/api/f1signal/team-radio/transcribe?path=${encodeURIComponent(path)}`,
      { method: "POST" },
    ),
  translateTeamRadio: (path: string) =>
    request<NonNullable<Snapshot["team_radio"]>[number]>(
      `/api/f1signal/team-radio/translate?path=${encodeURIComponent(path)}`,
      { method: "POST" },
    ),
};
