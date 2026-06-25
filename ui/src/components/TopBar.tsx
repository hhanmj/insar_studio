import { ChevronRight, Languages, Moon, Plus, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePrepContext } from "@/lib/useContext";

export function TopBar({
  dark,
  onToggleDark,
  onNewRegion,
}: {
  dark: boolean;
  onToggleDark: () => void;
  onNewRegion?: () => void;
}) {
  const { ctx } = usePrepContext();
  const ws = ctx?.workspace;
  const proj = ctx?.project;
  const region = ctx?.region;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card/80 px-5 backdrop-blur">
      <div className="flex min-w-0 items-center gap-1.5 truncate text-sm">
        {ws ? (
          <>
            <span className="truncate text-muted-foreground">{ws.name || ws.root}</span>
            {proj && (
              <>
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                <span className="truncate text-muted-foreground">{proj.name}</span>
              </>
            )}
            {region && (
              <>
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                <span className="truncate font-medium text-foreground">{region.name}</span>
              </>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">未创建工作区</span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Button variant="ghost" size="icon" className="h-8 w-8" title="中 / EN">
          <Languages className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onToggleDark} title="切换主题">
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <Button
          size="sm"
          className="ml-1 h-8"
          disabled={!ws || !proj}
          onClick={onNewRegion}
        >
          <Plus className="h-4 w-4" />
          新建区域
        </Button>
      </div>
    </header>
  );
}
