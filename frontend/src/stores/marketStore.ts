import { create } from 'zustand';

export type Session = 'pre' | 'regular' | 'after' | 'closed';
export type EmaState = 'BULLISH' | 'BEARISH' | null;
export type Trend = 'BULL' | 'BEAR' | 'NEUTRAL' | null;
export type VwapPosition = 'ABOVE' | 'BELOW' | null;
export type VwapMotion = 'TOWARD' | 'AWAY' | 'FLAT' | null;
export type Prediction = 'UP' | 'DOWN' | 'NEUTRAL' | 'ABSTAIN' | null;

export interface OHLCV {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  session: Session;
  timeframe: string;
}

export interface IndicatorSnapshot {
  ticker: string;
  timestamp: string;
  ema9: number | null;
  ema21: number | null;
  ema50: number | null;
  ema_state: EmaState;
  ema_cross_ts: string | null;
  vwap: number | null;
  vwap_distance_pct: number | null;
  vwap_motion: VwapMotion;
  vwap_slope: number | null;
  price_vs_vwap: VwapPosition;
  daily_trend: Trend;
  poc: number | null;
  nearest_support: number | null;
  nearest_resistance: number | null;
  swing_high: number | null;
  swing_high_ts: string | null;
  swing_low: number | null;
  swing_low_ts: string | null;
  recent_return_5m: number | null;
  recent_volatility: number | null;
  // Session levels (v2)
  pm_high: number | null;
  pm_low: number | null;
  orb_high: number | null;
  orb_low: number | null;
  prev_day_high: number | null;
  prev_day_low: number | null;
  poc_pre: number | null;
  poc_regular: number | null;
  poc_after: number | null;
  // v3 additions
  rsi_14: number | null;
  rsi_state: 'OVERBOUGHT' | 'OVERSOLD' | 'NEUTRAL' | null;
  rvol: number | null;
  volume_state: 'HIGH' | 'LOW' | 'NORMAL' | null;
  ema_spread_pct: number | null;
  bull_score: number | null;
  bear_score: number | null;
  confluence_bias: 'BULL' | 'BEAR' | 'MIXED' | null;
}

export interface Signal {
  id: number;
  ticker: string;
  timestamp: string;
  signal_type: string;
  direction: 'UP' | 'DOWN';
  details: string;
}

export interface CompositeAlert {
  id?: number;
  ticker: string;
  timestamp: string;
  signal: string;
  direction: 'UP' | 'DOWN' | 'WARNING';
  tier: 1 | 2 | 3;
  ai_confidence: number;
  components: string[];
  suppressed_by: string | null;
  timeframe: string;
  level_name?: string;
  level_price?: number;
  poc_level?: number;
}

export interface PredictionRow {
  id: number;
  ticker: string;
  timestamp: string;
  prediction: Prediction;
  confidence: number;
  evidence: string;
  rules_triggered: string;
  notes: string | null;
  outcome: string | null;
}

export interface TickerState {
  price: number | null;
  session: Session;
  candles: OHLCV[];
  indicators: IndicatorSnapshot | null;
  latestPrediction: PredictionRow | null;
}

interface MarketStore {
  tickers: Record<string, TickerState>;
  signals: Signal[];
  compositeAlerts: CompositeAlert[];
  initialized: boolean;

  // Actions
  initTicker: (ticker: string) => void;
  setPrice: (ticker: string, price: number, session: Session) => void;
  setCandles: (ticker: string, candles: OHLCV[]) => void;
  setIndicators: (ticker: string, snapshot: IndicatorSnapshot) => void;
  setPrediction: (ticker: string, prediction: PredictionRow) => void;
  addSignal: (signal: Signal) => void;
  addCompositeAlert: (alert: CompositeAlert) => void;
  setInitialized: (v: boolean) => void;
  handleWsMessage: (msg: WsMessage) => void;
}

export interface WsMessage {
  type: 'price_update' | 'signal' | 'prediction' | 'composite_alert';
  data: Record<string, unknown>;
}

const EMPTY_TICKER = (): TickerState => ({
  price: null,
  session: 'closed',
  candles: [],
  indicators: null,
  latestPrediction: null,
});

export const useMarketStore = create<MarketStore>((set, get) => ({
  tickers: {},
  signals: [],
  compositeAlerts: [],
  initialized: false,

  initTicker: (ticker) =>
    set((s) => ({
      tickers: { ...s.tickers, [ticker]: s.tickers[ticker] ?? EMPTY_TICKER() },
    })),

  setPrice: (ticker, price, session) =>
    set((s) => ({
      tickers: {
        ...s.tickers,
        [ticker]: { ...(s.tickers[ticker] ?? EMPTY_TICKER()), price, session },
      },
    })),

  setCandles: (ticker, candles) =>
    set((s) => ({
      tickers: { ...s.tickers, [ticker]: { ...(s.tickers[ticker] ?? EMPTY_TICKER()), candles } },
    })),

  setIndicators: (ticker, snapshot) =>
    set((s) => ({
      tickers: {
        ...s.tickers,
        [ticker]: { ...(s.tickers[ticker] ?? EMPTY_TICKER()), indicators: snapshot },
      },
    })),

  setPrediction: (ticker, prediction) =>
    set((s) => ({
      tickers: {
        ...s.tickers,
        [ticker]: { ...(s.tickers[ticker] ?? EMPTY_TICKER()), latestPrediction: prediction },
      },
    })),

  addSignal: (signal) =>
    set((s) => ({ signals: [signal, ...s.signals].slice(0, 200) })),

  addCompositeAlert: (alert) =>
    set((s) => ({ compositeAlerts: [alert, ...s.compositeAlerts].slice(0, 200) })),

  setInitialized: (v) => set({ initialized: v }),

  handleWsMessage: (msg) => {
    const { setPrice, addSignal, addCompositeAlert, setPrediction, setIndicators } = get();
    if (msg.type === 'price_update') {
      const d = msg.data as Record<string, unknown>;
      const ticker = d.ticker as string;
      setPrice(ticker, d.price as number, d.session as Session);
      const existing = get().tickers[ticker]?.indicators ?? {} as IndicatorSnapshot;
      setIndicators(ticker, { ...existing, ...d } as unknown as IndicatorSnapshot);
    } else if (msg.type === 'signal') {
      addSignal(msg.data as unknown as Signal);
    } else if (msg.type === 'composite_alert') {
      addCompositeAlert(msg.data as unknown as CompositeAlert);
    } else if (msg.type === 'prediction') {
      const d = msg.data as Record<string, unknown>;
      setPrediction(d.ticker as string, d as unknown as PredictionRow);
    }
  },
}));
