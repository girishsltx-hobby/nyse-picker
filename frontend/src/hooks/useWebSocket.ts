import { useEffect } from 'react';
import { useWsStore } from '../stores/wsStore';

export function useWebSocket() {
  const { connect, disconnect, connected } = useWsStore();

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { connected };
}
