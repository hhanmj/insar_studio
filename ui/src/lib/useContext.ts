import { useCallback, useEffect, useState } from "react";
import { type Context, getContext, watchBridgeReady } from "@/lib/bridge";

export function usePrepContext() {
  const [ctx, setCtx] = useState<Context | null>(null);

  const refresh = useCallback(async () => {
    setCtx(await getContext());
  }, []);

  useEffect(() => {
    void refresh();
    const stopWatchingBridge = watchBridgeReady();
    window.addEventListener("insar-context-changed", refresh);
    return () => {
      stopWatchingBridge();
      window.removeEventListener("insar-context-changed", refresh);
    };
  }, [refresh]);

  return { ctx, refresh };
}
