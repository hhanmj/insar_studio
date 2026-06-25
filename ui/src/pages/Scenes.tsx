import { useEffect } from "react";
import { Download as DownloadPage } from "@/pages/Download";

/** @deprecated Standalone nav removed; scenes live under 数据下载. */
export function Scenes() {
  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash !== "#download") {
      window.location.hash = "download";
    }
  }, []);
  return <DownloadPage />;
}
