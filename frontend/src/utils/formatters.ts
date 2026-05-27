export const TICKERS = ['SPY', 'QQQ', 'SPX', 'AAPL', 'GOOGL', 'NVDA', 'TSLA', 'AMZN', 'MSFT', 'PLTR'] as const;
export type Ticker = typeof TICKERS[number];

const isLocal = window.location.hostname === 'localhost';

export const API_BASE = isLocal
  ? 'http://localhost:8000/api'
  : 'https://nyse-picker-007.vercel.app/api';

export function formatPrice(p: number | null): string {
  if (p == null) return '—';
  return p >= 1000 ? p.toFixed(2) : p.toFixed(4);
}

export function formatPct(p: number | null): string {
  if (p == null) return '—';
  const sign = p >= 0 ? '+' : '';
  return `${sign}${(p * 100).toFixed(2)}%`;
}

export function formatConfidence(c: number | null): string {
  if (c == null) return '—';
  return `${Math.round(c * 100)}%`;
}

export function signalColor(direction: 'UP' | 'DOWN' | null | undefined): string {
  if (direction === 'UP') return '#26a69a';
  if (direction === 'DOWN') return '#ef5350';
  return '#9e9e9e';
}

export function predictionColor(pred: string | null | undefined): string {
  if (pred === 'UP') return '#26a69a';
  if (pred === 'DOWN') return '#ef5350';
  if (pred === 'NEUTRAL') return '#ffa726';
  return '#9e9e9e';
}

export function sessionLabel(s: string | null): string {
  const map: Record<string, string> = {
    pre: 'PRE',
    regular: 'REG',
    after: 'AH',
    closed: 'CLOSED',
  };
  return s ? (map[s] ?? s.toUpperCase()) : '—';
}
