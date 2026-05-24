import React, { useEffect, useRef } from 'react';
import axios from 'axios';
import { useMarketStore } from '../../stores/marketStore';
import { API_BASE, formatPrice, formatConfidence, predictionColor } from '../../utils/formatters';
import CandlestickChart from '../Chart/CandlestickChart';

// ── Rule metadata: educational descriptions for every possible trigger ──────
interface RuleMeta { direction: 'UP' | 'DOWN' | 'BOTH'; label: string; weight: number; explanation: string; }
const RULE_META: Record<string, RuleMeta> = {
  ema_bullish:                { direction: 'UP',   weight: 1.5, label: 'EMA Crossover — Bullish',           explanation: 'EMA 9 is above EMA 21. Short-term momentum outpaces the medium-term average (a "golden cross" setup). Buyers are in control of price action.' },
  ema_bearish:                { direction: 'DOWN', weight: 1.5, label: 'EMA Crossover — Bearish',           explanation: 'EMA 9 is below EMA 21. Short-term momentum has faded below the medium-term average (a "death cross" setup). Sellers dominate the near-term flow.' },
  ema_stack_bullish:          { direction: 'UP',   weight: 1.2, label: 'EMA Stack — Bullish',               explanation: 'EMA 9 > EMA 21 > EMA 50 — all three EMAs are in perfect bullish order. High-conviction trend alignment: short, medium, and longer-term momentum all point up.' },
  ema_stack_bearish:          { direction: 'DOWN', weight: 1.2, label: 'EMA Stack — Bearish',               explanation: 'EMA 9 < EMA 21 < EMA 50 — all three EMAs are in perfect bearish order. Short, medium, and longer-term momentum all point down. High-conviction trend alignment to the downside.' },
  price_above_vwap:           { direction: 'UP',   weight: 1.0, label: 'Price Above VWAP',                  explanation: 'Price is trading above the Volume Weighted Average Price — the intraday "fair value" anchor used by institutions. Being above VWAP signals bullish sentiment and that buyers are paying a premium.' },
  price_below_vwap:           { direction: 'DOWN', weight: 1.0, label: 'Price Below VWAP',                  explanation: 'Price is trading below VWAP. Sellers are willing to transact at a discount to fair value, signalling bearish institutional flow. Rallies back to VWAP often face supply.' },
  vwap_moving_away_above:     { direction: 'UP',   weight: 1.0, label: 'Trending Away from VWAP (Above)',   explanation: 'Price is above VWAP and the gap is expanding — strong trend confirmation. Buyers are aggressively pushing price higher; the premium over fair value is being accepted by the market.' },
  vwap_moving_away_below:     { direction: 'DOWN', weight: 1.0, label: 'Trending Away from VWAP (Below)',   explanation: 'Price is below VWAP and the discount is growing. Sellers are in full control; demand is not strong enough to bring price back toward fair value. Bearish momentum is building.' },
  vwap_converging_from_above: { direction: 'DOWN', weight: 1.0, label: 'Pulling Back to VWAP (From Above)', explanation: 'Price was above VWAP but is now falling back toward it — mean reversion in progress. The premium over fair value is being sold off; expect continued weakness until VWAP is re-tested.' },
  vwap_converging_from_below: { direction: 'UP',   weight: 1.0, label: 'Recovering to VWAP (From Below)',   explanation: 'Price was below VWAP and is now rising back toward it — discount buying in progress. The market is unwinding the discount to fair value; expect strength until VWAP is reached.' },
  vwap_reclaim_bullish:       { direction: 'UP',   weight: 1.3, label: 'VWAP Reclaim — Bullish',            explanation: 'Price crossed back above VWAP on this bar (previous bar closed below, current bar closes above). A VWAP reclaim is a high-conviction intraday reversal signal — sellers have lost control of fair value.' },
  vwap_lose_bearish:          { direction: 'DOWN', weight: 1.3, label: 'VWAP Lost — Bearish',               explanation: 'Price broke below VWAP on this bar (previous bar closed above, current bar closes below). Losing VWAP is a high-conviction bearish shift — buyers have failed to defend fair value.' },
  daily_trend_bull:           { direction: 'UP',   weight: 1.2, label: 'Daily Trend — Bullish',             explanation: 'The higher-timeframe (daily) trend is up. "Trade with the trend" is one of the most reliable principles in technical analysis. Long setups have higher probability when the daily bias is bullish.' },
  daily_trend_bear:           { direction: 'DOWN', weight: 1.2, label: 'Daily Trend — Bearish',             explanation: 'The higher-timeframe (daily) trend is down. Bearish daily context means rallies are likely distribution rather than accumulation — institutional sellers use strength to exit long positions.' },
  price_above_poc:            { direction: 'UP',   weight: 1.0, label: 'Price Above POC',                   explanation: 'Price is above the Point of Control — the price level with the most traded volume. Trading above POC means the market is paying above accepted value, a bullish structural signal.' },
  price_below_poc:            { direction: 'DOWN', weight: 1.0, label: 'Price Below POC',                   explanation: 'Price is below the Point of Control. The market is trading at a discount to the highest-volume price node. Sellers are pushing below accepted value — a bearish structural signal.' },
  price_near_support:         { direction: 'UP',   weight: 1.0, label: 'Near Support Level',                explanation: 'Price is within 0.3% of the nearest support zone. Historical price floors concentrate buy orders. This is a potential bounce zone — watch for a reaction or consolidation.' },
  price_near_resistance:      { direction: 'DOWN', weight: 1.0, label: 'Near Resistance Level',             explanation: 'Price is within 0.3% of the nearest resistance zone. Historical price ceilings concentrate sell orders. This is a potential rejection zone — watch for selling pressure as price approaches supply.' },
  sr_support_bounce:          { direction: 'UP',   weight: 0.8, label: 'Support Bounce',                    explanation: 'Price is within 0.2% above a key support level and the most recent bar closed higher. Buy-side order flow is absorbing supply at this known price floor — a classic bounce setup.' },
  positive_momentum:          { direction: 'UP',   weight: 1.0, label: 'Positive Short-Term Momentum',      explanation: 'The last 5-minute bar gained more than +0.3%. Momentum signals that buyers are actively engaged right now. Short-term momentum tends to persist — aggressive buyers are willing to lift offers.' },
  negative_momentum:          { direction: 'DOWN', weight: 1.0, label: 'Negative Short-Term Momentum',      explanation: 'The last 5-minute bar fell more than -0.3%. Sellers are actively engaged and hitting bids. Downside momentum tends to continue in the very short term — sellers are not waiting for rallies to exit.' },
  volume_surge_up:            { direction: 'UP',   weight: 1.1, label: 'Volume Surge — Bullish',            explanation: 'Current bar volume is more than 1.5× the 20-bar average while price is rising. High-volume up moves signal institutional participation — large buyers are accumulating, giving the move conviction.' },
  volume_surge_down:          { direction: 'DOWN', weight: 1.1, label: 'Volume Surge — Bearish',            explanation: 'Current bar volume is more than 1.5× the 20-bar average while price is falling. High-volume down moves signal institutional distribution — large sellers are unloading positions with urgency.' },
  volume_dry_up:              { direction: 'BOTH', weight: 0.6, label: 'Dry Volume — Trend Likely Resumes', explanation: 'Volume is less than 0.5× the 20-bar average on a counter-trend bar. Low-volume retracements lack conviction — there are no committed participants behind this counter-move, suggesting the primary trend will reassert itself.' },
  higher_low_formed:          { direction: 'UP',   weight: 0.9, label: 'Higher Low Formed',                 explanation: 'The current bar set a higher low than the previous bar during a pullback. Higher lows are the structural definition of an uptrend — each wave down finds support at a higher price, showing buyers stepping in earlier.' },
  lower_high_formed:          { direction: 'DOWN', weight: 0.9, label: 'Lower High Formed',                 explanation: 'The current bar set a lower high than the previous bar during a bounce. Lower highs define a downtrend — each rally fails at a lower price, confirming that supply is overwhelming demand on the way up.' },
  opening_range_hold:         { direction: 'UP',   weight: 0.7, label: 'Opening Range Hold (ORB)',           explanation: 'Price has pulled back to the Opening Range Breakout high and is holding (within 0.2% above it). A successful ORB retest turns prior resistance into support — bulls defended the breakout level, a classic continuation setup.' },
  // v3 rules
  rsi_overbought:             { direction: 'DOWN', weight: 0.9, label: 'RSI Overbought (>70)',                explanation: 'RSI-14 is above 70 — the instrument is in overbought territory. Momentum is extended to the upside; mean-reversion risk increases. Sellers may step in to fade the move.' },
  rsi_oversold:               { direction: 'UP',   weight: 0.9, label: 'RSI Oversold (<30)',                 explanation: 'RSI-14 is below 30 — deeply oversold. Selling pressure is extreme and a bounce or relief rally is likely as short-term sellers cover.' },
  ema_cross_imminent_bull:    { direction: 'UP',   weight: 0.8, label: 'EMA Bullish Cross Imminent',         explanation: 'EMA 9 is below EMA 21 but the gap has narrowed to under 0.08% — a bullish crossover is about to occur. Early entry signal ahead of a potential "golden cross" event.' },
  ema_cross_imminent_bear:    { direction: 'DOWN', weight: 0.8, label: 'EMA Bearish Cross Imminent',         explanation: 'EMA 9 is above EMA 21 but the gap has narrowed to under 0.08% — a bearish crossover is imminent. Early warning of a potential "death cross" forming on the 5-minute chart.' },
  confluence_strong_bull:     { direction: 'UP',   weight: 1.8, label: 'Strong Bullish Confluence (6+)',     explanation: '6 or more independent indicators are simultaneously aligned bullish: EMA state, EMA stack, VWAP position, VWAP motion, daily trend, RSI, POC, ORB, and volume. Multi-signal agreement is the highest-conviction setup.' },
  confluence_strong_bear:     { direction: 'DOWN', weight: 1.8, label: 'Strong Bearish Confluence (6+)',     explanation: '6 or more independent indicators are simultaneously aligned bearish. Multi-indicator agreement to the downside is the strongest signal the engine can produce — each additional aligned signal dramatically lowers the probability of a failed trade.' },
};

function confColor(c: number): string {
  if (c >= 0.75) return '#26a69a';
  if (c >= 0.60) return '#FFB300';
  return '#ef5350';
}

function confLabel(c: number, n: number): string {
  if (c >= 0.85) return `Extremely high conviction — ${n} signals in strong agreement`;
  if (c >= 0.75) return `High conviction — clear directional alignment across signals`;
  if (c >= 0.65) return `Moderate conviction — majority of signals lean this direction`;
  if (c >= 0.55) return `Low conviction — marginal signal agreement; treat cautiously`;
  return `Very low conviction — conflicting or weak signals`;
}

interface ConfluenceSignal { label: string; side: 'bull' | 'bear'; }
function computeConfluenceBreakdown(ind: import('../../stores/marketStore').IndicatorSnapshot | null, price: number | null): ConfluenceSignal[] {
  if (!ind) return [];
  const out: ConfluenceSignal[] = [];

  // 1. EMA state
  if (ind.ema_state === 'BULLISH') out.push({ label: 'EMA Cross', side: 'bull' });
  else if (ind.ema_state === 'BEARISH') out.push({ label: 'EMA Cross', side: 'bear' });

  // 2. EMA stack
  if (ind.ema9 != null && ind.ema21 != null && ind.ema50 != null) {
    if (ind.ema9 > ind.ema21 && ind.ema21 > ind.ema50) out.push({ label: 'EMA Stack', side: 'bull' });
    else if (ind.ema9 < ind.ema21 && ind.ema21 < ind.ema50) out.push({ label: 'EMA Stack', side: 'bear' });
  }

  // 3. VWAP position
  if (ind.price_vs_vwap === 'ABOVE') out.push({ label: 'VWAP Position', side: 'bull' });
  else if (ind.price_vs_vwap === 'BELOW') out.push({ label: 'VWAP Position', side: 'bear' });

  // 4. VWAP motion (AWAY in same direction as position)
  if (ind.vwap_motion === 'AWAY') {
    if (ind.price_vs_vwap === 'ABOVE') out.push({ label: 'VWAP Motion', side: 'bull' });
    else if (ind.price_vs_vwap === 'BELOW') out.push({ label: 'VWAP Motion', side: 'bear' });
  }

  // 5. Daily trend
  if (ind.daily_trend === 'BULL') out.push({ label: 'Daily Trend', side: 'bull' });
  else if (ind.daily_trend === 'BEAR') out.push({ label: 'Daily Trend', side: 'bear' });

  // 6. RSI vs 50
  if (ind.rsi_14 != null) {
    if (ind.rsi_14 > 50) out.push({ label: `RSI ${ind.rsi_14.toFixed(0)} > 50`, side: 'bull' });
    else if (ind.rsi_14 < 50) out.push({ label: `RSI ${ind.rsi_14.toFixed(0)} < 50`, side: 'bear' });
  }

  // 7. Price vs POC
  if (ind.poc != null && price != null) {
    if (price > ind.poc) out.push({ label: 'Price vs POC', side: 'bull' });
    else if (price < ind.poc) out.push({ label: 'Price vs POC', side: 'bear' });
  }

  // 8. Price vs ORB high
  if (ind.orb_high != null && price != null) {
    if (price > ind.orb_high) out.push({ label: 'Price vs ORB', side: 'bull' });
    else out.push({ label: 'Price vs ORB', side: 'bear' });
  }

  // 9. RVOL conviction
  if (ind.rvol != null && ind.recent_return_5m != null && ind.rvol > 1.5) {
    if (ind.recent_return_5m > 0) out.push({ label: 'RVOL Conviction', side: 'bull' });
    else if (ind.recent_return_5m < 0) out.push({ label: 'RVOL Conviction', side: 'bear' });
  }

  return out;
}

interface TickerDetailProps {
  ticker: string;
  onClose: () => void;
}

const TickerDetail: React.FC<TickerDetailProps> = ({ ticker, onClose }) => {
  const state = useMarketStore((s) => s.tickers[ticker]);
  const setCandles = useMarketStore((s) => s.setCandles);
  const ind = state?.indicators ?? null;
  const pred = state?.latestPrediction ?? null;

  // Draggable chart/sidebar divider
  const [chartPct, setChartPct] = React.useState(65);
  const bodyRef = useRef<HTMLDivElement>(null);
  const divDrag = useRef(false);
  const divStartX = useRef(0);
  const divStartPct = useRef(0);

  // Draggable AI/Indicators vertical divider
  const [aiPct, setAiPct] = React.useState(55);
  const sidebarColRef = useRef<HTMLDivElement>(null);
  const sidebarDivDrag = useRef(false);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!divDrag.current || !bodyRef.current) return;
      const rect = bodyRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setChartPct(Math.max(25, Math.min(80, pct)));
    };
    const onUp = () => { divDrag.current = false; document.body.style.cursor = ''; document.body.style.userSelect = ''; };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!sidebarDivDrag.current || !sidebarColRef.current) return;
      const rect = sidebarColRef.current.getBoundingClientRect();
      const pct = ((e.clientY - rect.top) / rect.height) * 100;
      setAiPct(Math.max(20, Math.min(80, pct)));
    };
    const onUp = () => { sidebarDivDrag.current = false; document.body.style.cursor = ''; document.body.style.userSelect = ''; };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
  }, []);

  useEffect(() => {
    axios.get(`${API_BASE}/candles/${ticker}?limit=400&today_only=true`).then((r) => {
      setCandles(ticker, r.data.bars);
    });
  }, [ticker, setCandles]);

  const evidence = pred?.evidence ? (() => {
    try { return JSON.parse(pred.evidence); } catch { return null; }
  })() : null;

  const rules = pred?.rules_triggered ? (() => {
    try { return JSON.parse(pred.rules_triggered) as string[]; } catch { return []; }
  })() : [];

  return (
    <div className="detail-panel">
      {/* ── Header + inline summary ── */}
      {(() => {
        const dir = pred?.prediction;
        const conf = pred?.confidence;
        const isUp = dir === 'UP';
        const isDown = dir === 'DOWN';
        const dirColor = isUp ? '#26a69a' : isDown ? '#ef5350' : '#9e9e9e';
        const arrow = isUp ? '▲' : isDown ? '▼' : '—';
        const dirLabel = isUp ? 'BULLISH' : isDown ? 'BEARISH' : (dir ?? '');

        type Chip = { label: string; color: string };
        const chips: Chip[] = [];
        if (rules.includes('ema_stack_bullish'))      chips.push({ label: 'EMA Stack ▲▲▲', color: '#26a69a' });
        else if (rules.includes('ema_stack_bearish')) chips.push({ label: 'EMA Stack ▼▼▼', color: '#ef5350' });
        else if (ind?.ema_state === 'BULLISH')        chips.push({ label: 'EMA ▲', color: '#26a69a' });
        else if (ind?.ema_state === 'BEARISH')        chips.push({ label: 'EMA ▼', color: '#ef5350' });
        if (rules.includes('vwap_reclaim_bullish'))   chips.push({ label: 'VWAP Reclaim ⚡', color: '#26a69a' });
        else if (rules.includes('vwap_lose_bearish')) chips.push({ label: 'VWAP Lost ⚡', color: '#ef5350' });
        else if (ind?.price_vs_vwap === 'ABOVE')      chips.push({ label: 'Above VWAP', color: '#26a69a' });
        else if (ind?.price_vs_vwap === 'BELOW')      chips.push({ label: 'Below VWAP', color: '#ef5350' });
        if (ind?.daily_trend === 'BULL')              chips.push({ label: 'Daily Bull', color: '#26a69a' });
        else if (ind?.daily_trend === 'BEAR')         chips.push({ label: 'Daily Bear', color: '#ef5350' });

        return (
          <div className="detail-header" style={{ gap: 10 }}>
            <h2 style={{ marginRight: 4, whiteSpace: 'nowrap' }}>{ticker} — Detail View</h2>
            {dirLabel && (
              <>
                <span style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.15)', flexShrink: 0 }} />
                <span style={{ fontWeight: 800, fontSize: '0.9rem', color: dirColor }}>{arrow}</span>
                <span style={{ fontWeight: 700, fontSize: '0.73rem', color: dirColor, letterSpacing: '0.07em', whiteSpace: 'nowrap' }}>{dirLabel}</span>
              </>
            )}
            {chips.map((c, i) => (
              <span key={i} style={{
                fontSize: '0.66rem', fontWeight: 600, color: c.color,
                background: `${c.color}1a`, border: `1px solid ${c.color}38`,
                borderRadius: 4, padding: '1px 6px', whiteSpace: 'nowrap',
              }}>{c.label}</span>
            ))}
            {conf != null && (
              <span style={{ fontSize: '0.71rem', fontWeight: 700, color: confColor(conf), whiteSpace: 'nowrap' }}>
                {Math.round(conf * 100)}% confidence
              </span>
            )}
            <button className="close-btn" style={{ marginLeft: 'auto' }} onClick={onClose}>✕</button>
          </div>
        );
      })()}

      <div className="detail-body" ref={bodyRef}>
        {/* ── chart column — width % draggable ── */}
        <div className="detail-chart-col" style={{ flex: `0 0 ${chartPct}%` }}>
          <CandlestickChart
            ticker={ticker}
            candles={state?.candles ?? []}
            indicators={ind}
          />
        </div>

        {/* Drag handle */}
        <div
          onMouseDown={(e) => {
            divDrag.current = true;
            divStartX.current = e.clientX;
            divStartPct.current = chartPct;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
          }}
          style={{
            width: 4, flexShrink: 0, cursor: 'col-resize',
            background: 'transparent', transition: 'background 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--accent)')}
          onMouseLeave={(e) => { if (!divDrag.current) e.currentTarget.style.background = 'transparent'; }}
        />

        {/* ── sidebar column ── */}
        <div className="detail-sidebar-col" ref={sidebarColRef} style={{ display: 'flex', flexDirection: 'column', minHeight: 0, gap: 0, padding: 6 }}>

          {/* AI Evaluation card */}
          <div className="detail-card detail-card-scroll" style={{ flex: `0 0 calc(${aiPct}% - 3px)`, minHeight: 0, marginBottom: 0 }}>
            <h3>AI Evaluation</h3>
            {pred ? (
              <>
                <div className="prediction-badge" style={{ color: predictionColor(pred.prediction) }}>
                  {pred.prediction}
                </div>

                <div style={{ marginTop: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: '0.72rem', color: '#9e9e9e', letterSpacing: '0.04em' }}>CONFIDENCE</span>
                    <span style={{ fontWeight: 700, fontSize: '0.85rem', color: confColor(pred.confidence) }}>
                      {formatConfidence(pred.confidence)}
                    </span>
                  </div>
                  <div style={{ background: '#2a2a3e', borderRadius: 4, height: 7, overflow: 'hidden' }}>
                    <div style={{
                      width: `${Math.round(pred.confidence * 100)}%`,
                      background: confColor(pred.confidence),
                      height: '100%', borderRadius: 4, transition: 'width 0.4s ease',
                    }} />
                  </div>
                  <p style={{ fontSize: '0.71rem', color: '#9e9e9e', margin: '5px 0 0', lineHeight: 1.4 }}>
                    {confLabel(pred.confidence, rules.length)}
                  </p>
                </div>

                {pred.notes && (
                  <div style={{
                    marginTop: 12, padding: '10px 12px',
                    background: 'rgba(99,102,241,0.08)',
                    border: '1px solid rgba(99,102,241,0.25)',
                    borderRadius: 8,
                  }}>
                    <div style={{ fontSize: '0.62rem', fontWeight: 700, color: '#818cf8', letterSpacing: '0.08em', marginBottom: 5 }}>
                      🤖 AI COMMENTARY
                    </div>
                    <p style={{ fontSize: '0.76rem', color: '#c7c7e8', margin: 0, lineHeight: 1.6 }}>
                      {pred.notes}
                    </p>
                  </div>
                )}

                {rules.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontSize: '0.70rem', fontWeight: 600, color: '#9e9e9e', letterSpacing: '0.08em', marginBottom: 8 }}>
                      SIGNALS FIRED ({rules.length})
                    </div>
                    {rules.map((r) => {
                      const meta = RULE_META[r];
                      const dir = meta?.direction ?? (r.includes('bear') || r.includes('down') || r.includes('below') || r.includes('lose') ? 'DOWN' : 'UP');
                      const color = dir === 'UP' ? '#26a69a' : dir === 'DOWN' ? '#ef5350' : '#60a5fa';
                      const arrow = dir === 'UP' ? '▲' : dir === 'DOWN' ? '▼' : '▲▼';
                      return (
                        <div key={r} style={{
                          marginBottom: 8, padding: '8px 10px',
                          background: '#131325', borderRadius: 6,
                          borderLeft: `3px solid ${color}`,
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                            <span style={{ color, fontSize: '0.7rem', fontWeight: 700 }}>{arrow}</span>
                            <span style={{ color, fontWeight: 600, fontSize: '0.77rem' }}>{meta?.label ?? r}</span>
                            {meta && meta.weight > 1 && (
                              <span style={{ fontSize: '0.62rem', background: '#2a2a3e', borderRadius: 3, padding: '1px 5px', color: '#c8c8c8', marginLeft: 'auto' }}>
                                ×{meta.weight} weight
                              </span>
                            )}
                          </div>
                          <p style={{ fontSize: '0.71rem', color: '#a0a0b8', margin: 0, lineHeight: 1.5 }}>
                            {meta?.explanation ?? '—'}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                )}

                {evidence && (
                  <details style={{ marginTop: 12 }}>
                    <summary style={{ cursor: 'pointer', color: '#9e9e9e', fontSize: '0.72rem' }}>Raw evidence data</summary>
                    <pre className="evidence-pre">{JSON.stringify(evidence, null, 2)}</pre>
                  </details>
                )}
              </>
            ) : (
              <p style={{ color: '#9e9e9e' }}>No prediction yet</p>
            )}
          </div>

          {/* Vertical drag handle between AI and Indicators */}
          <div
            onMouseDown={(e) => {
              sidebarDivDrag.current = true;
              document.body.style.cursor = 'row-resize';
              document.body.style.userSelect = 'none';
              e.preventDefault();
            }}
            style={{
              height: 5, flexShrink: 0, cursor: 'row-resize',
              background: 'transparent', transition: 'background 0.15s',
              borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)',
              margin: '2px 0',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--accent)')}
            onMouseLeave={(e) => { if (!sidebarDivDrag.current) e.currentTarget.style.background = 'transparent'; }}
          />

          {/* Indicators card — 40% */}
          <div className="detail-card detail-card-scroll" style={{ flex: '1 1 0', minHeight: 0, marginTop: 0 }}>
            <h3>Indicators</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 12px' }}>

              {/* Left: EMA + VWAP */}
              <div>
                <div className="ind-section-hdr">EMA / Trend</div>
                <table className="detail-table"><tbody>
                  <tr><td>EMA 9</td><td>{formatPrice(ind?.ema9 ?? null)}</td></tr>
                  <tr><td>EMA 21</td><td>{formatPrice(ind?.ema21 ?? null)}</td></tr>
                  <tr><td>Spread</td><td style={{ color: (ind?.ema_spread_pct ?? 0) > 0 ? '#26a69a' : '#ef5350' }}>{ind?.ema_spread_pct != null ? `${ind.ema_spread_pct.toFixed(3)}%` : '—'}</td></tr>
                  <tr><td>State</td><td style={{ color: ind?.ema_state === 'BULLISH' ? '#26a69a' : '#ef5350' }}>{ind?.ema_state ?? '—'}</td></tr>
                  <tr><td>Daily</td><td>{ind?.daily_trend ?? '—'}</td></tr>
                  <tr><td>POC</td><td>{formatPrice(ind?.poc ?? null)}</td></tr>
                </tbody></table>
                <div className="ind-section-hdr" style={{ marginTop: 8 }}>VWAP</div>
                <table className="detail-table"><tbody>
                  <tr><td>Value</td><td>{formatPrice(ind?.vwap ?? null)}</td></tr>
                  <tr><td>Pos</td><td>{ind?.price_vs_vwap ?? '—'}</td></tr>
                  <tr><td>Dist%</td><td>{ind?.vwap_distance_pct?.toFixed(3) ?? '—'}%</td></tr>
                  <tr><td>Motion</td><td>{ind?.vwap_motion ?? '—'}</td></tr>
                </tbody></table>
                <div className="ind-section-hdr" style={{ marginTop: 8, color: '#f59e0b' }}>Momentum</div>
                <table className="detail-table"><tbody>
                  <tr>
                    <td>RSI 14</td>
                    <td style={{ color: ind?.rsi_state === 'OVERBOUGHT' ? '#ef5350' : ind?.rsi_state === 'OVERSOLD' ? '#26a69a' : '#e0e0e0' }}>
                      {ind?.rsi_14 != null ? ind.rsi_14.toFixed(1) : '—'}
                      {ind?.rsi_state ? <span style={{ fontSize: '0.62rem', color: '#9e9e9e', marginLeft: 4 }}>{ind.rsi_state}</span> : null}
                    </td>
                  </tr>
                  <tr>
                    <td>RVOL</td>
                    <td style={{ color: ind?.volume_state === 'HIGH' ? '#26a69a' : ind?.volume_state === 'LOW' ? '#ef5350' : '#e0e0e0' }}>
                      {ind?.rvol != null ? `${ind.rvol.toFixed(2)}×` : '—'}
                      {ind?.volume_state ? <span style={{ fontSize: '0.62rem', color: '#9e9e9e', marginLeft: 4 }}>{ind.volume_state}</span> : null}
                    </td>
                  </tr>
                </tbody></table>
                <div className="ind-section-hdr" style={{ marginTop: 8, color: '#818cf8' }}>Confluence</div>
                <table className="detail-table"><tbody>
                  <tr><td>Bull</td><td style={{ color: '#26a69a', fontWeight: 700 }}>{ind?.bull_score ?? '—'}</td></tr>
                  <tr><td>Bear</td><td style={{ color: '#ef5350', fontWeight: 700 }}>{ind?.bear_score ?? '—'}</td></tr>
                  <tr><td>Bias</td><td style={{ color: ind?.confluence_bias === 'BULL' ? '#26a69a' : ind?.confluence_bias === 'BEAR' ? '#ef5350' : '#60a5fa' }}>{ind?.confluence_bias ?? '—'}</td></tr>
                </tbody></table>
                {(() => {
                  const breakdown = computeConfluenceBreakdown(ind, state?.price ?? null);
                  if (!breakdown.length) return null;
                  return (
                    <div style={{ marginTop: 6 }}>
                      {breakdown.map((s, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3, fontSize: '0.7rem' }}>
                          <span style={{
                            width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                            background: s.side === 'bull' ? '#26a69a' : '#ef5350',
                          }} />
                          <span style={{ color: s.side === 'bull' ? '#26a69a' : '#ef5350' }}>{s.label}</span>
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>

              {/* Right: Levels */}
              <div>
                <div className="ind-section-hdr">S / R</div>
                <table className="detail-table"><tbody>
                  <tr><td>Supp</td><td style={{ color: '#26a69a' }}>{formatPrice(ind?.nearest_support ?? null)}</td></tr>
                  <tr><td>Res</td><td style={{ color: '#ef5350' }}>{formatPrice(ind?.nearest_resistance ?? null)}</td></tr>
                  <tr><td>Sw Hi</td><td>{formatPrice(ind?.swing_high ?? null)}</td></tr>
                  <tr><td>Sw Lo</td><td>{formatPrice(ind?.swing_low ?? null)}</td></tr>
                </tbody></table>
                <div className="ind-section-hdr" style={{ marginTop: 8, color: '#FF9800' }}>ORB 15m</div>
                <table className="detail-table"><tbody>
                  <tr><td>High</td><td style={{ color: '#FF9800' }}>{formatPrice(ind?.orb_high ?? null)}</td></tr>
                  <tr><td>Low</td><td style={{ color: '#FF9800' }}>{formatPrice(ind?.orb_low ?? null)}</td></tr>
                </tbody></table>
                <div className="ind-section-hdr" style={{ marginTop: 8, color: '#9c27b0' }}>Premarket</div>
                <table className="detail-table"><tbody>
                  <tr><td>High</td><td style={{ color: '#9c27b0' }}>{formatPrice(ind?.pm_high ?? null)}</td></tr>
                  <tr><td>Low</td><td style={{ color: '#9c27b0' }}>{formatPrice(ind?.pm_low ?? null)}</td></tr>
                </tbody></table>
                <div className="ind-section-hdr" style={{ marginTop: 8, color: '#78909C' }}>Prev Day</div>
                <table className="detail-table"><tbody>
                  <tr><td>High</td><td style={{ color: '#78909C' }}>{formatPrice(ind?.prev_day_high ?? null)}</td></tr>
                  <tr><td>Low</td><td style={{ color: '#78909C' }}>{formatPrice(ind?.prev_day_low ?? null)}</td></tr>
                </tbody></table>
              </div>

            </div>
          </div>

        </div>{/* end sidebar */}
      </div>{/* end detail-body */}
    </div>
  );
};

export default TickerDetail;
