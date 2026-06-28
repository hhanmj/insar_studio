import {
  Activity,
  CheckCircle2,
  Download,
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

export const NAV_LABELS: Record<NavKey, string> = {
  overview: "总览",
  workspace: "工作区",
  aoi: "区域 AOI",
  scenes: "影像导入",
  download: "数据任务",
  convert: "DEM 转换",
  report: "报告",
  settings: "设置",
};

const GROUPS: { label: string; items: Item[] }[] = [
  {
    label: "准备流程",
    items: [
      { key: "overview", label: "总览", icon: LayoutDashboard },
      { key: "workspace", label: "工作区", icon: FolderTree },
      { key: "aoi", label: "区域 AOI", icon: MapPinned },
      { key: "download", label: "数据任务", icon: Download },
      { key: "convert", label: "DEM 转换", icon: Repeat2 },
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
    <aside className="flex h-full w-[276px] shrink-0 flex-col border-r bg-card/95 text-card-foreground">
      <div className="border-b px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-foreground text-background shadow-sm">
            <Radar className="h-5 w-5" />
          </div>
          <div className="min-w-0 leading-tight">
            <div className="truncate text-sm font-semibold">InSAR Assistant</div>
            <div className="truncate text-[11px] text-muted-foreground">
              Sentinel-1 数据准备台
            </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {GROUPS.map((group) => (
          <div key={group.label}>
            <div className="px-3 pb-2 text-[11px] font-medium text-muted-foreground">
              {group.label}
            </div>
            <div className="space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = active === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => onChange(item.key)}
                    className={cn(
                      "group flex h-10 w-full items-center gap-3 rounded-md border border-transparent px-3 text-sm transition-colors",
                      isActive
                        ? "border-border bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4",
                        isActive
                          ? "text-primary"
                          : "text-muted-foreground group-hover:text-foreground",
                      )}
                    />
                    <span className="truncate">{item.label}</span>
                    {isActive && <CheckCircle2 className="ml-auto h-3.5 w-3.5 text-primary" />}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="px-3 pb-3">
        <div className="rounded-md border bg-background px-3 py-3">
          <div className="flex items-center gap-2 text-xs font-medium">
            <Activity className="h-3.5 w-3.5 text-primary" />
            本地桌面模式
          </div>
          <div className="mt-1 text-[11px] leading-5 text-muted-foreground">
            v0.16.0 · 离线优先 · 任务状态保留
          </div>
        </div>
      </div>
    </aside>
  );
}
