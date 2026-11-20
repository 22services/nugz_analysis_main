/* Client typé de l'API nugz (comité 15 min, graphique, terminal). */

import type { Localized } from "./i18n";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export type Direction = "LONG" | "SHORT" | "NEUTRAL" | "NO_TRADE";
export type RiskVerdict = "APPROVED" | "REDUCE" | "REJECT";

export interface Candle { t: string; o: number; h: number; l: number; c: number; v: number }

// ---------------------------------------------------------------------
// Décision
// ---------------------------------------------------------------------
export interface Evidence {
  label: Localized;
  value: string | Localized;
  reading: Localized | null;
  supports: number;
}

export interface Agent {
  id: "structure" | "vwap" | "profile" | "volatility" | "cross";
  name: Localized;
  role: Localized;
  group: "trend" | "location" | "context" | "filter";
  status: "OK" | "UNAVAILABLE";
  score: number;
  direction: Direction;
  headline: Localized;
  evidence: Evidence[];
  warnings: Localized[];
  multiplier?: number;
}

export interface Objection { severity: number; claim: Localized; targets: string[] }

export interface RiskCheck {
  name: Localized; passed: boolean; hard: boolean; detail: Localized | null;
}

export interface Risk {
  verdict: RiskVerdict;
  checks: RiskCheck[];
  entry: number; stop: number; stop_atr: number; stop_source: Localized;
  t1: number; t1_name: Localized; t2: number; t2_name: Localized;
  rr1: number; rr2: number; chase_limit: number;
  risk_usd: number; size_factor: number;
  contracts: { GC: number; MGC: number };
  risk_per_contract: { GC: number; MGC: number };
}

export interface Decision {
  engine_version: string;
  symbol: string;
  name: string;
  bar_start: string;
  bar_end: string;
  decided_at: string;
  decision: Direction;
  reason: string | null;
  conviction: number;
  rationale: Localized;
  market: {
    price: number; session: string; session_label: Localized;
    atr: number; atr_pct: number; regime: string;
    daily_atr: number | null; range_consumed: number | null;
    vwap: number | null; vwap_sd: number | null;
    poc: number | null; vah: number | null; val: number | null; dpoc: number | null;
    pdh: number | null; pdl: number | null;
  };
  agents: Agent[];
  cio: {
    raw_score: number; threshold: number; min_conviction: number;
    groups: { trend: number | null; location: number | null; context: number | null };
    weights: { trend: number; location: number; context: number };
    naive_vote: { long: number; short: number; neutral: number };
    probe_direction: number;
  };
  red_team: { objections: Objection[]; penalty: number };
  risk: Risk;
  schedule?: { next_run_at: string | null; last_error: string | null; data_delay_s: number };
}

export interface JournalEntry {
  source: "live" | "replay";
  bar_start: string;
  bar_end: string;
  decision: Direction;
  reason: string | null;
  conviction: number;
  price: number;
  entry_ref: number; stop: number; t1: number; rr1: number;
  outcome: "NO_TRADE" | "OPEN" | "WIN" | "LOSS" | "SCRATCH" | "MISSED";
  entry: number | null; exit: number | null; pnl_r: number | null;
  taken: boolean;
}

export interface JournalStats {
  source: string;
  decisions: number; signals: number; trades: number; in_position_skipped: number;
  no_trade_rate: number | null;
  closed: number; open: number; missed: number; wins: number; losses: number;
  hit_rate: number | null; hit_ci: [number, number] | null;
  expectancy_r: number | null; expectancy_ci: [number, number] | null;
  total_r: number | null;
  profit_factor: number | null; worst_losing_streak: number;
  sample_sufficient: boolean;
  from: string | null; to: string | null;
}

export interface History {
  items: JournalEntry[];
  stats: { live: JournalStats; replay: JournalStats };
  replay: { status: string; done: number; total: number };
}

// ---------------------------------------------------------------------
// Graphique
// ---------------------------------------------------------------------
export type ChartInterval = "5m" | "15m" | "1h" | "1d" | "1W";

export interface PatternEvent {
  i: number; kind: string; dir: number;
  level?: number; from_i?: number; top?: number; bottom?: number;
  p1?: number; p2?: number; neckline?: number;
}

export interface Swing { i: number; kind: "H" | "L"; price: number; label: string | null }

export interface Fvg { i: number; dir: number; top: number; bottom: number; filled_at: number | null }

export interface PatternStat {
  kind: string; n: number; hit_rate?: number; ci?: [number, number];
  baseline: number; lift?: number; hit_is?: number | null; hit_oos?: number | null;
  avg_gain_atr?: number | null; label: "INSUFFICIENT" | "NOT_PROVEN" | "PLAUSIBLE";
}

export interface PatternMeta {
  dir: number; group: string; fr: string; en: string; plain_fr: string; plain_en: string;
}

export interface Profile { poc: number; vah: number; val: number; bin_size: number; bins: [number, number][] }

export interface ChartData {
  symbol: string;
  interval: ChartInterval;
  horizon: number;
  decimals: number;
  candles: Candle[];
  atr: number;
  structure: { trend: string };
  has_volume: boolean;
  vwap: { vwap: (number | null)[]; u1: (number | null)[]; l1: (number | null)[];
          u2: (number | null)[]; l2: (number | null)[] } | null;
  session_breaks?: number[];
  prior_session?: { poc: number; vah: number; val: number; high: number; low: number };
  profile: Profile | null;
  swings: Swing[];
  events: PatternEvent[];
  fvgs: Fvg[];
  stats: PatternStat[];
  meta: Record<string, PatternMeta>;
  sample: { bars: number; from: string; to: string };
}

// ---------------------------------------------------------------------
async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  decision: () => get<Decision>("/api/decision"),
  history: (source: "live" | "replay", limit = 96) =>
    get<History>(`/api/decision/history?source=${source}&limit=${limit}`),
  chart: (symbol: string, interval: ChartInterval, bars = 160) =>
    get<ChartData>(
      `/api/chart?symbol=${encodeURIComponent(symbol)}&interval=${interval}&bars=${bars}`),
  refresh: async (): Promise<Decision> => {
    const res = await fetch(`${API_BASE}/api/decision/refresh`, { method: "POST" });
    if (!res.ok) throw new Error(`refresh → ${res.status}`);
    return res.json();
  },
};
