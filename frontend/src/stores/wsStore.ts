import { create } from 'zustand';
import ReconnectingWebSocket from 'reconnecting-websocket';
import { useMarketStore } from './marketStore';
import type { WsMessage } from './marketStore';

const isLocal = window.location.hostname === 'localhost';

const WS_URL = isLocal
  ? 'ws://localhost:8000/ws'
  : 'wss://nyse-picker-007.vercel.app/ws';

interface WsStore {
  connected: boolean;
  socket: ReconnectingWebSocket | null;
  connect: () => void;
  disconnect: () => void;
}

export const useWsStore = create<WsStore>((set, get) => ({
  connected: false,
  socket: null,

  connect: () => {
    if (get().socket) return;

    const ws = new ReconnectingWebSocket(WS_URL, [], {
      connectionTimeout: 2000,        // ← replaces reconnectInterval
      maxRetries: Infinity,           // ← replaces maxReconnectAttempts
    });

    ws.addEventListener('open', () => {
      set({ connected: true });
      // Heartbeat
      const interval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 20000);
      ws.addEventListener('close', () => clearInterval(interval));
    });

    ws.addEventListener('close', () => set({ connected: false }));

    ws.addEventListener('message', (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data as string);
        useMarketStore.getState().handleWsMessage(msg);
      } catch {
        // ignore non-JSON (e.g. "pong")
      }
    });

    set({ socket: ws });
  },

  disconnect: () => {
    get().socket?.close();
    set({ socket: null, connected: false });
  },
}));
