/* Client du service Terminal (données réelles OpenBB). */

import { API_BASE, type Candle } from "./api";

export interface WatchItem {
  symbol: string;
  name: string;
  group: "metals" | "fx" | "rates" | "equity" | "energy" | "crypto";
  last: number | null;
  change: number | null;
  change_pct: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  bid: number | null;
  ask: number | null;
  volume: number | null;
  year_high: number | null;
  year_low: number | null;
  ma_50d: number | null;
  ma_200d: number | null;
  spark: number[];
}

export type Interval = "5m" | "15m" | "1h" | "1d" | "1W";

export interface History {
  symbol: string;
  name: string;
  interval: Interval;
  candles: Candle[];
}

export interface NewsItem {
  date: string | null;
  title: string;
  url: string;
  source: string | null;
  summary: string;
  title_original?: string;
  translated?: boolean;
}

export interface CurvePoint {
  tenor: string;
  now: number | null;
  prev: number | null;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}/api/terminal${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const terminal = {
  watchlist: () => get<{ as_of: string; items: WatchItem[] }>("/watchlist"),
  history: (symbol: string, interval: Interval) =>
    get<History>(
      `/history?symbol=${encodeURIComponent(symbol)}&interval=${interval}`),
  news: (symbols: string, lang: "fr" | "en" = "en") =>
    get<{ items: NewsItem[] }>(
      `/news?symbols=${encodeURIComponent(symbols)}&limit=25&lang=${lang}`),
  curve: () =>
    get<{ as_of: string; compare_to: string; points: CurvePoint[] }>("/curve"),
};
