import { ChevronRight, Moon, Plus, Sun } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NAV_LABELS, type NavKey } from "@/components/Sidebar";
import { usePrepContext } from "@/lib/useContext";

export function TopBar({
  active,
  dark,
  onToggleDark,
  onNewRegion,
}: {
  active: NavKey;
  dark: boolean;
  onToggleDark: () => void;
  onNewRegion?: () => void;
}) {
  const { ctx } = usePrepContext();
  const ws = ctx?.workspace;
  const proj = ctx?.project;
  const region = ctx?.region;
  const workspaceLabel = ws ? ws.name || ws.root : "";

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b bg-background/95 px-5 backdrop-blur lg:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-2 text-sm">
        <span className="shrink-0 rounded-md bg-muted px-2 py-1 text-xs font-medium text-foreground">
          {NAV_LABELS[active]}
        </span>
        {workspaceLabel ? (
          <div className="flex min-w-0 items-center gap-1.5 truncate text-muted-foreground">
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
            <span className="truncate">{workspaceLabel}</span>
            {proj && (
              <>
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                <span className="truncate">{proj.name}</span>
              </>
            )}
            {region && (
              <>
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                <span className="truncate font-medium text-foreground">{region.name}</span>
              </>
            )}
          </div>
        ) : (
          <span className="truncate text-muted-foreground">未选择工作区</span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <Badge variant={ws ? "success" : "warning"}>
          {ws ? "工作区已连接" : "未初始化"}
        </Badge>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onToggleDark} title="切换主题">
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <Button
          size="sm"
          className="h-8"
          disabled={!ws || !proj}
          onClick={onNewRegion}
        >
          <Plus className="h-4 w-4" />
          新建研究区
        </Button>
      </div>
    </header>
  );
}
