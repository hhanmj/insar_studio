import { useEffect, useState, type ReactNode } from "react";
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
import { Settings } from "@/pages/Settings";
import { Workbench } from "@/pages/Workbench";
import { cn } from "@/lib/utils";

const PAGES: Partial<
  Record<NavKey, (props?: { onNavigate?: (key: NavKey) => void }) => ReactNode>
> = {
  overview: (props) => <Overview onNavigate={props?.onNavigate} />,
  workspace: () => <Workspace />,
  aoi: () => <Aoi />,
  scenes: () => <Scenes />,
  download: () => <Download />,
  convert: () => <Convert />,
  report: () => <Report />,
  settings: () => <Settings />,
};

const NAV_KEYS: NavKey[] = [
  "overview",
  "workspace",
  "aoi",
  "scenes",
  "download",
  "convert",
  "settings",
];

function navFromHash(): NavKey {
  if (typeof window === "undefined") return "overview";
  const raw = window.location.hash.replace(/^#/, "");
  if (raw === "workbench") return "overview";
  if (raw === "scenes") return "download";
  if (raw === "report") return "overview";
  return NAV_KEYS.includes(raw as NavKey) ? (raw as NavKey) : "overview";
}

export default function App() {
  const [active, setActive] = useState<NavKey>(navFromHash);
  const [visited, setVisited] = useState<NavKey[]>(() => [navFromHash()]);
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("insar-theme") === "dark";
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("insar-theme", dark ? "dark" : "light");
    }
  }, [dark]);

  useEffect(() => {
    const onHashChange = () => setActive(navFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    setVisited((prev) => (prev.includes(active) ? prev : [...prev, active]));
  }, [active]);

  const changeNav = (key: NavKey) => {
    setActive(key);
    if (typeof window !== "undefined") window.location.hash = key;
  };

  const renderPage = (key: NavKey) => {
    const Page = PAGES[key];
    return Page ? Page({ onNavigate: changeNav }) : <Placeholder navKey={key} />;
  };

  if (active === "overview") {
    return (
      <Workbench
        dark={dark}
        onToggleDark={() => setDark((v) => !v)}
      />
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar active={active} onChange={changeNav} />
      <div className="flex min-w-0 flex-1 flex-col bg-background">
        <TopBar
          active={active}
          dark={dark}
          onToggleDark={() => setDark((v) => !v)}
          onNewRegion={() => changeNav("workspace")}
        />
        <main className="flex-1 overflow-y-auto">
          <div className="px-5 py-5 lg:px-6">
            {visited.map((key) => (
              <section
                key={key}
                aria-hidden={active !== key}
                className={cn("min-h-full", active === key ? "block" : "hidden")}
              >
                {renderPage(key)}
              </section>
            ))}
          </div>
        </main>
      </div>
    </div>
  );
}
