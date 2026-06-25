import { Bell, ChevronRight, Languages, Moon, Plus, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";

export function TopBar({
  dark,
  onToggleDark,
}: {
  dark: boolean;
  onToggleDark: () => void;
}) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b bg-card/70 px-6 backdrop-blur">
      <div className="flex items-center gap-1.5 text-sm">
        <span className="text-muted-foreground">三峡示范工作区</span>
        <ChevronRight className="h-4 w-4 text-muted-foreground/50" />
        <span className="text-muted-foreground">巴东项目</span>
        <ChevronRight className="h-4 w-4 text-muted-foreground/50" />
        <span className="font-medium text-foreground">石榴树包 区域</span>
      </div>

      <div className="flex items-center gap-1.5">
        <Button variant="ghost" size="icon" title="中 / EN">
          <Languages className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={onToggleDark} title="切换主题">
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <Button variant="ghost" size="icon" title="通知">
          <Bell className="h-4 w-4" />
        </Button>
        <Button size="sm" className="ml-1">
          <Plus className="h-4 w-4" />
          新建区域
        </Button>
        <div className="ml-2 flex h-9 w-9 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary">
          HM
        </div>
      </div>
    </header>
  );
}
