import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Circle,
  Database,
  Download,
  FileText,
  FolderTree,
  Loader2,
  MapPinned,
  Satellite,
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
  getDownloadStatus,
  getTree,
  hasBridge,
  type DownloadStatus,
  type Tree,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

import type { NavKey } from "@/components/Sidebar";

type NavFn = (key: NavKey) => void;

const STEPS = [
  { key: "workspace", label: "工作区" },
  { key: "aoi", label: "AOI" },
  { key: "download", label: "场景/下载" },
  { key: "convert", label: "DEM 转换" },
  { key: "report", label: "报告" },
] as const;

export function Overview({ onNavigate }: { onNavigate?: NavFn }) {
  const bridged = hasBridge();
  const { ctx } = usePrepContext();
  const [tree, setTree] = useState<Tree | null>(null);
  const [dlStatus, setDlStatus] = useState<DownloadStatus | null>(null);

  const region = ctx?.region ?? null;

  useEffect(() => {
    void getTree().then(setTree);
    void getDownloadStatus().then(setDlStatus);
    const id = window.setInterval(() => {
      void getDownloadStatus().then(setDlStatus);
    }, 2000);
    return () => window.clearInterval(id);
  }, [ctx?.region?.region_id, ctx?.region?.scene_count]);

  const regionCount = useMemo(
    () => tree?.projects.reduce((n, p) => n + p.regions.length, 0) ?? 0,
    [tree],
  );

  const stepDone = {
    workspace: !!ctx?.workspace,
    aoi: !!region?.has_aoi,
    download: (region?.scene_count ?? 0) > 0,
    convert: false,
    report: false,
  };

  const activeStep = !stepDone.workspace
    ? "workspace"
    : !stepDone.aoi
      ? "aoi"
      : !stepDone.download
        ? "download"
        : dlStatus?.state === "running" || dlStatus?.state === "paused"
          ? "download"
          : "convert";

  const stats = [
    {
      label: "项目",
      value: tree ? String(tree.projects.length) : "—",
      sub: ctx?.workspace ? "当前工作区" : "未创建工作区",
      icon: FolderTree,
    },
    {
      label: "区域",
      value: tree ? String(regionCount) : "—",
      sub: region ? `当前：${region.name}` : "未选择区域",
      icon: MapPinned,
    },
    {
      label: "影像 (SLC)",
      value: region ? String(region.scene_count) : "—",
      sub: region?.scene_count ? "已导入场景" : "待导入",
      icon: Satellite,
    },
    {
      label: "凭据",
      value: bridged ? "系统" : "预览",
      sub: "Earthdata / OpenTopo / GACOS",
      icon: FileText,
    },
  ];

  const dlActive = dlStatus?.state === "running" || dlStatus?.state === "paused";
  const dlPct =
    dlStatus && dlStatus.total > 0 ? Math.round((dlStatus.done / dlStatus.total) * 100) : 0;

  const go = (key: string) => onNavigate?.(key);

  if (!ctx?.workspace) {
    return (
      <div className="mx-auto max-w-[960px] space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">总览</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              尚未创建工作区 — 下方数据均为空，不会保留演示状态
            </p>
          </div>
          <BridgeBadge bridged={bridged} />
        </div>
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
            <FolderTree className="h-12 w-12 text-muted-foreground/40" />
            <div>
              <div className="font-medium">从工作区开始</div>
              <p className="mt-1 max-w-md text-sm text-muted-foreground">
                创建或打开工作区 → 添加项目与区域 → 绑定 AOI → 在「数据下载」导入场景并下载
              </p>
            </div>
            <Button onClick={() => go("workspace")}>
              <Database className="h-4 w-4" />
              打开工作区
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1280px] space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">总览</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {ctx.project?.name ?? "—"} · {region?.name ?? "未选择区域"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <BridgeBadge bridged={bridged} />
          <Button variant="outline" size="sm" onClick={() => go("workspace")}>
            <Database className="h-4 w-4" />
            工作区
          </Button>
          <Button size="sm" onClick={() => go("download")} disabled={!region}>
            <Download className="h-4 w-4" />
            数据下载
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label}>
              <CardContent className="flex items-center justify-between p-4">
                <div className="min-w-0">
                  <div className="text-xs text-muted-foreground">{s.label}</div>
                  <div className="mt-0.5 text-2xl font-semibold">{s.value}</div>
                  <div className="mt-0.5 truncate text-[11px] text-muted-foreground">{s.sub}</div>
                </div>
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="h-4 w-4" />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
          <div>
            <CardTitle className="text-base">准备流程</CardTitle>
            <CardDescription>反映当前会话真实进度（非演示数据）</CardDescription>
          </div>
          <Badge variant={dlActive ? "warning" : "neutral"}>
            {dlActive ? "下载进行中" : `当前：${STEPS.find((s) => s.key === activeStep)?.label}`}
          </Badge>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-y-4">
            {STEPS.map((step, i) => {
              const done = stepDone[step.key as keyof typeof stepDone];
              const active = step.key === activeStep;
              return (
                <div key={step.key} className="flex items-center">
                  <button
                    type="button"
                    onClick={() => go(step.key)}
                    className="flex flex-col items-center gap-1.5"
                  >
                    <div
                      className={
                        "flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors " +
                        (done
                          ? "border-primary bg-primary text-primary-foreground"
                          : active
                            ? "border-primary text-primary"
                            : "border-border text-muted-foreground")
                      }
                    >
                      {done ? (
                        <CheckCircle2 className="h-4 w-4" />
                      ) : active ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Circle className="h-3.5 w-3.5" />
                      )}
                    </div>
                    <span className="text-[11px] font-medium">{step.label}</span>
                  </button>
                  {i < STEPS.length - 1 && (
                    <div
                      className={"mx-2 h-0.5 w-8 rounded sm:w-12 " + (done ? "bg-primary" : "bg-border")}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">ASF 下载</CardTitle>
            <CardDescription>仅显示本会话真实下载任务</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!dlStatus || dlStatus.state === "idle" ? (
              <div className="rounded-md border border-dashed py-8 text-center text-sm text-muted-foreground">
                尚无下载记录。前往「数据下载」导入场景并开始下载。
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between text-sm">
                  <span>
                    {dlStatus.done}/{dlStatus.total} 景
                  </span>
                  <Badge variant={dlActive ? "warning" : "success"}>{dlStatus.state}</Badge>
                </div>
                <Progress value={dlPct} />
                {dlStatus.summary_line && (
                  <p className="text-xs text-muted-foreground">{dlStatus.summary_line}</p>
                )}
                <div className="max-h-36 space-y-1 overflow-y-auto font-mono text-[11px]">
                  {dlStatus.log.slice(-8).map((line, i) => (
                    <div key={i} className="truncate text-muted-foreground">
                      {line.detail}
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="flex flex-col xl:col-span-3">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">区域地图</CardTitle>
            <CardDescription>
              {region?.has_aoi && region.bbox
                ? `AOI · W${region.bbox.west.toFixed(2)} E${region.bbox.east.toFixed(2)}`
                : "绑定 AOI 后在此显示处理范围"}
            </CardDescription>
          </CardHeader>
          <CardContent className="min-h-[380px] flex-1 pt-0">
            {region?.has_aoi && region.bbox ? (
              <MapCard bbox={region.bbox} label={`AOI · ${region.name}`} minHeight={380} />
            ) : (
              <div className="flex h-[380px] items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground">
                暂无 AOI — 请先在「区域 AOI」绘制或导入
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
