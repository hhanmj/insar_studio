import { useCallback, useEffect, useState } from "react";
import { type Context, getContext } from "@/lib/bridge";

export function usePrepContext() {
  const [ctx, setCtx] = useState<Context | null>(null);

  const refresh = useCallback(async () => {
    setCtx(await getContext());
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { ctx, refresh };
}
