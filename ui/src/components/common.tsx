import type { ReactNode } from "react";
import {
  AlertCircle,
  CheckCircle2,
  MapPinned,
  Plug,
  PlugZap,
  Satellite,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Context } from "@/lib/bridge";

export function PageHeader({
  title,
  desc,
  right,
}: {
  title: string;
  desc: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{desc}</p>
      </div>
      {right}
    </div>
  );
}

export function BridgeBadge({ bridged }: { bridged: boolean }) {
  return (
    <Badge variant={bridged ? "success" : "warning"}>
      {bridged ? (
        <>
          <PlugZap className="h-3.5 w-3.5" />
          已连接核心
        </>
      ) : (
        <>
          <Plug className="h-3.5 w-3.5" />
          预览模式（mock）
        </>
      )}
    </Badge>
  );
}

export function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
      {children}
    </label>
  );
}

export function ErrorNote({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{text}</span>
    </div>
  );
}

// Shows the active Workspace > Project > Region, or a hint to set one up first.
export function RegionBanner({ ctx }: { ctx: Context | null }) {
  if (!ctx) return null;
  if (!ctx.region) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
        <span>
          尚未选择研究区。请先到『项目设置』创建或选中当前项目，本面板将作用于当前研究区。
        </span>
      </div>
    );
  }
  const r = ctx.region;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border bg-muted/40 px-4 py-3 text-sm">
      <MapPinned className="h-4 w-4 text-primary" />
      <span className="font-medium">{r.name}</span>
      <span className="font-mono text-xs text-muted-foreground">{r.safe_name}</span>
      <span className="ml-auto flex items-center gap-2">
        <Badge variant={r.has_aoi ? "success" : "neutral"}>
          {r.has_aoi ? (
            <>
              <CheckCircle2 className="h-3.5 w-3.5" />
              AOI 已设
            </>
          ) : (
            "AOI 未设"
          )}
        </Badge>
        <Badge variant="neutral">
          <Satellite className="h-3.5 w-3.5" />
          {r.scene_count} 景
        </Badge>
      </span>
    </div>
  );
}
