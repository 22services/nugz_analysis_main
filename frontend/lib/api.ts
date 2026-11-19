/* Client typé de l'API du comité. */

import type { Localized } from "./i18n";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

// -- Types partagés avec le backend -----------------------------------
export type Direction = "LONG" | "SHORT" | "NEUTRAL" | "NO_TRADE";
export type RiskVerdict = "APPROVED" | "REDUCE" | "REJECT";
export type AgentStatus =
  | "IDLE" | "RUNNING" | "DONE" | "BLOCKED" | "SKIPPED" | "FAILED";
export type RunStage =
  | "DATA" | "ANALYSIS" | "RED_TEAM" | "REBUTTAL" | "RISK"
  | "DECISION" | "COMPLETE" | "HALTED";

export interface ToolSpec {
  name: string;
  provider: string;
  purpose: Localized;
  connected: boolean;
}

export interface AgentCard {
  id: string;
  order: number;
  name: Localized;
  role: Localized;
  mandate: Localized;
  plain: Localized;
  can_veto: boolean;
  tools: ToolSpec[];
  model_hint: string;
  stage: RunStage;
}

export interface Evidence {
  label: Localized;
  value: string;
  reading: Localized;
  weight: number;
  supports: Direction;
}

export interface AgentOutput {
  agent_id: string;
  status: AgentStatus;
  duration_ms: number | null;
  headline: Localized | null;
  detail: Localized | null;
  evidence: Evidence[];
  conviction: number | null;
  direction: Direction | null;
  horizon: Localized | null;
  warnings: Localized[];
  payload: Record<string, unknown>;
}

export interface TicketSection {
  title: Localized;
  rows: [string, string][];
}

export interface TradeTicket {
  instrument: string;
  contract: string;
  timestamp: string;
  horizon: string;
  trend: Localized;
  volatility: Localized;
  macro_regime: Localized;
  event_risk: Localized;
  direction: Direction;
  conviction: number;
  expected_horizon: Localized;
  thesis: Localized;
  technical: TicketSection;
  macro: TicketSection;
  futures: TicketSection;
  catalysts: TicketSection;
  bull_case: Localized[];
  bear_case: Localized[];
  invalidation: Localized[];
  entry_zone: Localized;
  stop_logic: Localized;
  target_logic: Localized;
  time_stop: Localized;
  risk_budget: Localized;
  liquidity: Localized;
  event_exposure: Localized;
  risk_verdict: RiskVerdict;
  final_decision: Direction;
  decision_rationale: Localized;
  monitoring: Localized[];
}

export interface Run {
  run_id: string;
  started_at: string;
  finished_at: string | null;
  trigger: string;
  stage: RunStage;
  decision: Direction | null;
  conviction: number | null;
  risk_verdict: RiskVerdict | null;
  event_risk: string | null;
  spot_at_decision: number | null;
  halted: boolean;
  outputs: Record<string, AgentOutput>;
  ticket: TradeTicket | null;
  input_snapshot: Record<string, unknown>;
}

export interface DataSource {
  name: string;
  kind: string;
  age_seconds: number;
  max_age_seconds: number;
  is_stale: boolean;
  connected: boolean;
}

export interface TimeframeRead {
  timeframe: string;
  structure: string;
  quality: string;
  momentum: number;
  atr: number;
  atr_percentile: number;
  above_vwap: boolean;
  vwap: number;
  close: number;
}

export interface Level {
  price: number;
  touches: number;
  kind: string;
  distance_pct: number;
}

export interface CalendarEvent {
  name: Localized;
  scheduled_at: string;
  minutes_until: number;
  importance: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  exposed_variables: Localized[];
  consensus: string | null;
  previous: string | null;
}

export interface Trigger {
  kind: string;
  priority: number;
  timeframe: string;
  reason: Localized;
  dedup_key: string;
}

export interface Candle {
  t: string; o: number; h: number; l: number; c: number; v: number;
}

export interface MarketState {
  features: {
    schema_version: string;
    as_of: string;
    spot: number;
    contract: { symbol: string; days_to_roll: number; series_type: string;
                roll_warning: Localized | null };
    session: { session: string; is_liquid_hours: boolean };
    vwap_distance_atr: { value: number; unit: string; meaning: string };
    atr_percentile: { value: number };
    alignment: { value: number };
    structure_by_tf: Record<string, string>;
    momentum_by_tf: Record<string, number>;
    extras: Record<string, { value: number; unit: string }>;
    state_summary: Localized;
  };
  reads: TimeframeRead[];
  levels: Level[];
  sources: DataSource[];
  calendar: CalendarEvent[];
  triggers: Trigger[];
  change_pct: number;
  candles: Candle[];
}

export interface AgentsResponse {
  agents: AgentCard[];
  total: number;
  llm_agents: number;
  deterministic_agents: number;
  tools_total: number;
  tools_connected: number;
}

export interface JournalEntry {
  run_id: string;
  timestamp: string;
  decision: Direction;
  conviction: number;
  risk_verdict: RiskVerdict;
  spot: number;
  outcome: string;
  notes: Localized | null;
}

export interface CalibrationBucket {
  lower: number;
  upper: number;
  n_trades: number;
  n_wins: number;
  observed_rate: number | null;
}

export interface AgentReliability {
  agent_id: string;
  n_trades: number;
  hit_rate: number | null;
  buckets: (CalibrationBucket & { reliable: boolean })[];
  reliable_buckets: number;
  sample_sufficient: boolean;
}

export interface JournalResponse {
  entries: JournalEntry[];
  stats: {
    total_runs: number;
    decisions: number;
    no_trades: number;
    no_trade_rate: number;
    closed: number;
    hit_rate: number | null;
    avg_conviction: number | null;
    sample_sufficient: boolean;
  };
  calibration: CalibrationBucket[];
  by_agent: AgentReliability[];
}

export interface Scenario {
  id: string;
  seed: number;
  fr: string;
  en: string;
}

// -- Appels -----------------------------------------------------------
async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

/**
 * `/api/runs` ne renvoie que des resumes : ni `outputs`, ni `ticket`.
 * Pour afficher le comite il faut le run complet, d'ou `runDetail`.
 */
export type RunSummary = Omit<Run, "outputs" | "ticket" | "input_snapshot">;

export const api = {
  agents: () => get<AgentsResponse>("/api/agents"),
  market: (scenario = "long") =>
    get<MarketState>(`/api/market?scenario=${scenario}`),
  journal: () => get<JournalResponse>("/api/journal"),
  scenarios: () => get<{ scenarios: Scenario[] }>("/api/scenarios"),
  runs: () => get<{ runs: RunSummary[] }>("/api/runs"),
  runDetail: (id: string) => get<Run>(`/api/runs/${id}`),

  run: async (scenario: string): Promise<Run> => {
    const res = await fetch(`${API_BASE}/api/run?scenario=${scenario}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error(`run → ${res.status}`);
    return res.json();
  },
};
