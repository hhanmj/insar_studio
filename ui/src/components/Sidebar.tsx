import {
  Download,
  FileText,
  FolderTree,
  LayoutDashboard,
  MapPinned,
  Radar,
  Repeat2,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type NavKey =
  | "overview"
  | "workspace"
  | "aoi"
  | "scenes"
  | "download"
  | "convert"
  | "report"
  | "settings";

type Item = { key: NavKey; label: string; icon: typeof LayoutDashboard };

const GROUPS: { label: string; items: Item[] }[] = [
  {
    label: "主流程",
    items: [
      { key: "overview", label: "总览", icon: LayoutDashboard },
      { key: "workspace", label: "工作区", icon: FolderTree },
      { key: "aoi", label: "区域 AOI", icon: MapPinned },
      { key: "download", label: "数据下载", icon: Download },
      { key: "convert", label: "DEM 转换", icon: Repeat2 },
      { key: "report", label: "报告", icon: FileText },
    ],
  },
  {
    label: "系统",
    items: [{ key: "settings", label: "设置", icon: Settings }],
  },
];

export function Sidebar({
  active,
  onChange,
}: {
  active: NavKey;
  onChange: (key: NavKey) => void;
}) {
  return (
    <aside className="flex h-full w-64 shrink-0 flex-col bg-[#0b1220] text-slate-300">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <Radar className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-white">InSAR Assistant</div>
          <div className="text-[11px] text-slate-400">数据准备工作台</div>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-2">
        {GROUPS.map((group) => (
          <div key={group.label}>
            <div className="px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-slate-500">
              {group.label}
            </div>
            <div className="space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = active === item.key;
                return (
                  <button
                    key={item.key}
                    onClick={() => onChange(item.key)}
                    className={cn(
                      "group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                      isActive
                        ? "bg-primary/15 text-white"
                        : "text-slate-300 hover:bg-white/5 hover:text-white",
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4",
                        isActive
                          ? "text-primary"
                          : "text-slate-400 group-hover:text-slate-200",
                      )}
                    />
                    <span>{item.label}</span>
                    {isActive && (
                      <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-white/5 px-5 py-4 text-[11px] text-slate-500">
        v0.16.0 · 离线优先
      </div>
    </aside>
  );
}
