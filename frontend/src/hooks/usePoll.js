import { useEffect, useRef } from "react";

export function usePoll(callback, interval, active = true) {
  const cbRef = useRef(callback);
  cbRef.current = callback;

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => cbRef.current(), interval);
    return () => clearInterval(id);
  }, [interval, active]);
}
