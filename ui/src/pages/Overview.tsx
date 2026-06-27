import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Circle,
  Database,
  Download,
  FileText,
  FolderTree,
  Loader2,
  MapPinned,
  Radar,
  Satellite,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { MapCard } from "@/components/MapCard";
import { BridgeBadge } from "@/components/common";
import {
  getActivity,
  getWorkflowStatus,
  hasBridge,
  type ActivityEntry,
  type WorkflowSource,
  type WorkflowStage,
  type WorkflowStatus,
} from "@/lib/bridge";
import type { NavKey } from "@/components/Sidebar";
import { usePrepContext } from "@/lib/useContext";

const SOURCE_ICONS: Record<string, typeof Satellite> = {
  asf: Satellite,
  dem: Database,
  gacos: Radar,
  report: FileText,
};

function asNav(value: string): NavKey {
  const allowed: NavKey[] = [
    "overview",
    "workspace",
    "aoi",
    "scenes",
    "download",
    "convert",
    "report",
    "settings",
  ];
  return allowed.includes(value as NavKey) ? (value as NavKey) : "overview";
}

function statusLabel(status: string): string {
  switch (status) {
    case "done":
      return "完成";
    case "running":
      return "运行中";
    case "blocked":
      return "等待前置";
    case "active":
      return "下一步";
    case "configured":
      return "已配置";
    case "needs_config":
      return "待配置";
    case "ready":
      return "就绪";
    case "waiting":
      return "等待数据";
    default:
      return status;
  }
}

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(diff) || diff < 0) return "刚刚";
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  return new Date(iso).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function stageVariant(status: string): "success" | "warning" | "neutral" {
  if (status === "done") return "success";
  if (status === "active" || status === "running") return "warning";
  return "neutral";
}

function sourceVariant(status: string): "success" | "warning" | "neutral" {
  if (status === "configured" || status === "ready") return "success";
  if (status === "needs_config") return "warning";
  return "neutral";
}

function StageRail({
  stages,
  onNavigate,
}: {
  stages: WorkflowStage[];
  onNavigate?: (key: NavKey) => void;
}) {
  return (
    <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-7">
      {stages.map((stage) => {
        const active = stage.status === "active" || stage.status === "running";
        const done = stage.status === "done";
        return (
          <button
            key={stage.id}
            type="button"
            onClick={() => onNavigate?.(asNav(stage.nav))}
            className={
              "min-h-[112px] rounded-lg border bg-card p-3 text-left transition-colors hover:border-primary/60 " +
              (active ? "border-primary/70 ring-1 ring-primary/20" : "border-border")
            }
          >
            <div className="flex items-center justify-between gap-2">
              <div
                className={
                  "flex h-8 w-8 items-center justify-center rounded-full border " +
                  (done
                    ? "border-success bg-success text-white"
                    : active
                      ? "border-primary text-primary"
                      : "border-border text-muted-foreground")
                }
              >
                {done ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : stage.status === "running" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : active ? (
                  <ArrowRight className="h-4 w-4" />
                ) : (
                  <Circle className="h-4 w-4" />
                )}
              </div>
              <Badge variant={stageVariant(stage.status)}>{statusLabel(stage.status)}</Badge>
            </div>
            <div className="mt-3 text-sm font-semibold">{stage.label}</div>
            <div className="mt-1 text-xs text-muted-foreground">{stage.summary}</div>
          </button>
        );
      })}
    </div>
  );
}

function SourceStrip({ sources }: { sources: WorkflowSource[] }) {
  return (
    <div className="grid gap-3 lg:grid-cols-4">
      {sources.map((source) => {
        const Icon = SOURCE_ICONS[source.id] ?? Database;
        const credential =
          source.credential && !["none", "unavailable"].includes(source.credential)
            ? `${source.credential} · `
            : "";
        return (
          <div key={source.id} className="rounded-lg border bg-card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{source.label}</div>
                  <div className="mt-0.5 truncate text-xs text-muted-foreground">
                    {credential}
                    {source.capabilities.join(" / ")}
                  </div>
                </div>
              </div>
              <Badge variant={sourceVariant(source.status)}>{statusLabel(source.status)}</Badge>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function Overview({ onNavigate }: { onNavigate?: (key: NavKey) => void }) {
  const bridged = hasBridge();
  const { ctx } = usePrepContext();
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(null);
  const [activities, setActivities] = useState<ActivityEntry[]>([]);

  useEffect(() => {
    let mounted = true;
    async function refresh() {
      const [wf, feed] = await Promise.all([getWorkflowStatus(), getActivity()]);
      if (!mounted) return;
      setWorkflow(wf);
      setActivities(feed.activities);
    }
    void refresh();
    const id = window.setInterval(refresh, 2000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, [ctx?.workspace?.workspace_id, ctx?.project?.project_id, ctx?.region?.region_id]);

  const region = workflow?.context.region ?? ctx?.region ?? null;
  const sceneCoverage = workflow?.scene_coverage ?? {
    bbox: region?.scene_footprint_bbox ?? null,
    count: region?.scene_footprint_bbox ? 1 : 0,
  };
  const download = workflow?.download;
  const downloadActive = download?.state === "running" || download?.state === "paused";
  const downloadPct =
    download && download.total > 0 ? Math.round((download.done / download.total) * 100) : 0;

  const stats = useMemo(
    () => [
      {
        label: "项目",
        value: workflow ? String(workflow.counts.projects) : "-",
        sub: workflow?.context.project?.name ?? "尚未选择",
        icon: FolderTree,
      },
      {
        label: "区域",
        value: workflow ? String(workflow.counts.regions) : "-",
        sub: region?.name ?? "尚未选择",
        icon: MapPinned,
      },
      {
        label: "影像",
        value: workflow ? String(workflow.counts.scenes) : "-",
        sub: region?.scene_count ? "已导入 ASF 场景" : "等待导入",
        icon: Satellite,
      },
      {
        label: "DEM",
        value: workflow?.dem_dataset ?? "-",
        sub: "自动判定垂直基准",
        icon: Database,
      },
    ],
    [workflow, region],
  );

  if (!workflow) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在读取工作流状态
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">InSAR 准备工作台</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            按设置、项目、AOI、影像、下载、DEM 转换和报告组织整个数据准备流程。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <BridgeBadge bridged={bridged} />
          <Button onClick={() => onNavigate?.(asNav(workflow.next_action.nav))}>
            {workflow.next_action.label}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {stats.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="rounded-lg border bg-card p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="text-xs text-muted-foreground">{item.label}</div>
                  <div className="mt-1 truncate text-2xl font-semibold">{item.value}</div>
                  <div className="mt-1 truncate text-xs text-muted-foreground">{item.sub}</div>
                </div>
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                  <Icon className="h-4 w-4" />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <StageRail stages={workflow.stages} onNavigate={onNavigate} />
      <SourceStrip sources={workflow.sources} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[420px_1fr]">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Download className="h-4 w-4 text-primary" />
              任务状态
            </CardTitle>
            <CardDescription>真实下载任务的进度、摘要和最近日志。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!download || download.state === "idle" ? (
              <div className="rounded-lg border border-dashed py-10 text-center text-sm text-muted-foreground">
                暂无任务。导入 ASF 场景后可在“数据下载”中生成计划并开始下载。
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{statusLabel(download.state)}</span>
                  <Badge variant={downloadActive ? "warning" : "success"}>
                    {download.done}/{download.total}
                  </Badge>
                </div>
                <Progress value={downloadPct} />
                {download.summary_line && (
                  <p className="text-xs text-muted-foreground">{download.summary_line}</p>
                )}
                {download.error && (
                  <div
                    className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
                  >
                    <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{download.error}</span>
                  </div>
                )}
                <div className="max-h-40 space-y-1 overflow-y-auto rounded-md bg-muted/40 p-2 font-mono text-[11px]">
                  {download.log.slice(-8).map((line, index) => (
                    <div key={`${line.scene_id}-${index}`} className="truncate">
                      {line.detail}
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="flex min-h-[420px] flex-col">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <MapPinned className="h-4 w-4 text-primary" />
              当前区域
            </CardTitle>
            <CardDescription>
              {region?.has_aoi && region.bbox
                ? `AOI: W${region.bbox.west.toFixed(3)} E${region.bbox.east.toFixed(
                    3,
                  )} S${region.bbox.south.toFixed(3)} N${region.bbox.north.toFixed(3)}`
                : sceneCoverage.bbox
                  ? `ASF 场景覆盖：${sceneCoverage.count} 景`
                : "设置 AOI 后会显示处理范围。"}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex-1 pt-0">
            {(region?.has_aoi && region.bbox) || sceneCoverage.bbox ? (
              <MapCard
                bbox={region?.bbox ?? sceneCoverage.bbox!}
                overlayBbox={region?.has_aoi ? null : sceneCoverage.bbox}
                label={region?.has_aoi ? `AOI / ${region.name}` : `ASF 覆盖 / ${region?.name ?? "未命名"}`}
                overlayLabel={`ASF 场景覆盖 / ${sceneCoverage.count} 景`}
                minHeight={350}
              />
            ) : (
              <div
                className="flex h-[350px] items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground"
              >
                尚未绑定 AOI
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4 text-primary" />
            最近活动
          </CardTitle>
          <CardDescription>本次桌面会话内的真实操作记录。</CardDescription>
        </CardHeader>
        <CardContent>
          {activities.length === 0 ? (
            <div
              className="flex items-center gap-2 rounded-lg border border-dashed px-4 py-6 text-sm text-muted-foreground"
            >
              <ShieldCheck className="h-4 w-4" />
              还没有活动。创建工作区、绑定 AOI、导入影像或开始任务后会出现在这里。
            </div>
          ) : (
            <div className="divide-y divide-border/60">
              {activities.map((entry, index) => (
                <div key={`${entry.ts}-${index}`} className="flex items-start gap-3 py-3">
                  <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />
                  <div className="min-w-0 flex-1 text-sm">{entry.text}</div>
                  <div className="shrink-0 text-xs text-muted-foreground">
                    {formatRelativeTime(entry.ts)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
