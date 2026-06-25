import { useEffect, useState } from "react";
import { Sidebar, type NavKey } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { Overview } from "@/pages/Overview";
import { Placeholder } from "@/pages/Placeholder";
import { Workspace } from "@/pages/Workspace";
import { Aoi } from "@/pages/Aoi";
import { Scenes } from "@/pages/Scenes";
import { Download } from "@/pages/Download";
import { Convert } from "@/pages/Convert";
import { Report } from "@/pages/Report";

const PAGES: Partial<Record<NavKey, () => React.ReactNode>> = {
  overview: () => <Overview />,
  workspace: () => <Workspace />,
  aoi: () => <Aoi />,
  scenes: () => <Scenes />,
  download: () => <Download />,
  convert: () => <Convert />,
  report: () => <Report />,
};

const NAV_KEYS: NavKey[] = [
  "overview",
  "workspace",
  "aoi",
  "scenes",
  "download",
  "convert",
  "report",
  "settings",
];

function navFromHash(): NavKey {
  if (typeof window === "undefined") return "overview";
  const raw = window.location.hash.replace(/^#/, "") as NavKey;
  if (raw === "scenes") return "download";
  return NAV_KEYS.includes(raw) ? raw : "overview";
}

export default function App() {
  const [active, setActive] = useState<NavKey>(navFromHash);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    const onHashChange = () => setActive(navFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const changeNav = (key: NavKey) => {
    setActive(key);
    if (typeof window !== "undefined") window.location.hash = key;
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar active={active} onChange={changeNav} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar dark={dark} onToggleDark={() => setDark((v) => !v)} />
        <main className="flex-1 overflow-y-auto p-6">
          {(PAGES[active] ?? (() => <Placeholder navKey={active} />))()}
        </main>
      </div>
    </div>
  );
}
