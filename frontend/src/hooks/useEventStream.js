import { useEffect, useRef, useState } from "react";
import { api } from "../api";

export function useEventStream() {
  const [liveEvents, setLiveEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef(null);

  useEffect(() => {
    const source = new EventSource(`${api.base}/api/stream`);
    sourceRef.current = source;

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    source.addEventListener("event", (e) => {
      const data = JSON.parse(e.data);
      setLiveEvents((prev) => [data, ...prev].slice(0, 100));
    });

    return () => source.close();
  }, []);

  return { liveEvents, connected };
}
