import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { useWebSocket } from './hooks/useWebSocket'
import { useMarketStore } from './stores/marketStore'
import { TICKERS, API_BASE } from './utils/formatters'
import TickerGrid from './components/Dashboard/TickerGrid'
import TickerDetail from './components/Detail/TickerDetail'
import AlertsPanel from './components/Alerts/AlertsPanel'
import './App.css'

function App() {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [displayTickers, setDisplayTickers] = useState<string[]>(() => {
    try { const s = localStorage.getItem('picker_tickers'); if (!s) return [...TICKERS]; const saved: string[] = JSON.parse(s); const merged = [...saved]; TICKERS.forEach(t => { if (!merged.includes(t)) merged.push(t); }); return merged; }
    catch { return [...TICKERS]; }
  })
  const [sortBy, setSortBy] = useState<'ticker' | 'price' | 'ai' | null>(null)
  const { connected } = useWebSocket()
  const { setIndicators, setPrediction, setInitialized, initTicker, setPrice } = useMarketStore()
  const initialized = useMarketStore((s) => s.initialized)

  useEffect(() => {
    localStorage.setItem('picker_tickers', JSON.stringify(displayTickers));
  }, [displayTickers]);

  useEffect(() => {
    if (initialized) return
    displayTickers.forEach((ticker) => initTicker(ticker))
    axios.get(`${API_BASE}/dashboard`, { params: { tickers: displayTickers.join(',') } }).then((r) => {
      const dashboard = r.data.dashboard as Record<string, {
        indicators: Record<string, unknown> | null
        prediction: Record<string, unknown> | null
        price: number | null
        session: string | null
      }>
      for (const [ticker, data] of Object.entries(dashboard)) {
        if (data.indicators) setIndicators(ticker, data.indicators as any)
        if (data.prediction) setPrediction(ticker, data.prediction as any)
        if (data.price != null) {
          const session = (data.session ?? 'closed') as any
          setPrice(ticker, data.price, session)
        }
      }
    }).finally(() => setInitialized(true))
  }, [initialized])

  const handleSelectTicker = (ticker: string) =>
    setSelectedTicker(ticker === selectedTicker ? null : ticker)

  const handleAddTicker = async (t: string): Promise<string | null> => {
    initTicker(t);
    setDisplayTickers((p) => [...p, t]);
    try {
      // Add ticker to backend config
      await axios.post(`${API_BASE}/tickers/add?ticker=${t}`);
      
      // Fetch data for the new ticker
      const r = await axios.post(`${API_BASE}/ticker/${t}/refresh`);
      if (r.data.indicators) setIndicators(t, r.data.indicators as any);
      if (r.data.price != null) setPrice(t, r.data.price, (r.data.session ?? 'closed') as any);
      if (r.data.prediction) setPrediction(t, r.data.prediction as any);
      return null;
    } catch (e: any) {
      setDisplayTickers((p) => p.filter((x) => x !== t));
      if (selectedTicker === t) setSelectedTicker(null);
      return (e?.response?.data?.detail as string) ?? `Could not find ticker "${t}"`;
    }
  };
  const handleRemoveTicker = async (t: string) => {
    try {
      await axios.post(`${API_BASE}/tickers/remove?ticker=${t}`);
    } catch (e: any) {
      console.error("Failed to remove ticker from config:", e);
    }
    setDisplayTickers((p) => p.filter((x) => x !== t));
    if (selectedTicker === t) setSelectedTicker(null);
  };

  // ── Draggable left-panel divider ──
  const [listWidth, setListWidth] = useState(170);
  const dragRef = useRef(false);
  const dragStartX = useRef(0);
  const dragStartW = useRef(0);
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragRef.current) return;
      const delta = e.clientX - dragStartX.current;
      setListWidth(Math.max(120, Math.min(340, dragStartW.current + delta)));
    };
    const onUp = () => { dragRef.current = false; document.body.style.cursor = ''; document.body.style.userSelect = ''; };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
  }, []);

  return (
    <div className={`app${sidebarOpen ? ' sidebar-open' : ''}`}>
      <header className="app-header">
        <span className="app-title">Picker 📈 NYSE Dashboard</span>
        <div className="header-controls">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen((o) => !o)}
            title={sidebarOpen ? 'Hide alerts' : 'Show alerts'}
          >
            {sidebarOpen ? '◀ Alerts' : '▶ Alerts'}
          </button>
          <span className={`ws-status ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? '● LIVE' : '○ CONNECTING…'}
          </span>
        </div>
      </header>
      <main className="app-main">
        {/* Narrow left ticker list */}
        <div className="ticker-list-panel" style={{ width: listWidth }}>
          <TickerGrid
            tickers={displayTickers}
            onSelectTicker={handleSelectTicker}
            selectedTicker={selectedTicker}
            sortBy={sortBy}
            onSortChange={setSortBy}
            onAddTicker={handleAddTicker}
            onRemoveTicker={handleRemoveTicker}
          />
        </div>
        {/* Drag handle */}
        <div
          onMouseDown={(e) => {
            dragRef.current = true;
            dragStartX.current = e.clientX;
            dragStartW.current = listWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
          }}
          style={{
            width: 4, flexShrink: 0, cursor: 'col-resize',
            background: 'transparent',
            borderRight: '1px solid var(--border)',
            transition: 'background 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--accent)')}
          onMouseLeave={(e) => { if (!dragRef.current) e.currentTarget.style.background = 'transparent'; }}
        />
        {/* Right: detail view fills remaining space */}
        <div className="detail-area">
          {selectedTicker ? (
            <TickerDetail key={selectedTicker} ticker={selectedTicker} onClose={() => setSelectedTicker(null)} />
          ) : (
            <div className="detail-empty">← Select a ticker to view chart &amp; analysis</div>
          )}
        </div>
      </main>
      {sidebarOpen && (
        <aside className="app-sidebar">
          <AlertsPanel />
        </aside>
      )}
    </div>
  )
}

export default App
