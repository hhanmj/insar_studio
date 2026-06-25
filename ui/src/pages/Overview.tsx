import {
  ArrowUpRight,
  CheckCircle2,
  Circle,
  Database,
  Download,
  FileText,
  FolderTree,
  Layers,
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

const STATS = [
  { label: "项目", value: "3", sub: "+1 本周", icon: FolderTree },
  { label: "区域", value: "7", sub: "2 个待下载", icon: MapPinned },
  { label: "影像 (SLC)", value: "42", sub: "全部一致", icon: Satellite },
  { label: "报告", value: "5", sub: "JSON · MD · HTML", icon: FileText },
];

const STEPS = [
  { label: "工作区", done: true },
  { label: "AOI", done: true },
  { label: "影像核查", done: true },
  { label: "数据下载", done: false, active: true },
  { label: "DEM 转换", done: false },
  { label: "报告", done: false },
];

const DOWNLOADS = [
  { name: "S1A IW SLC · 2024-03-12", kind: "ASF", pct: 100, state: "done" as const },
  { name: "S1A IW SLC · 2024-03-24", kind: "ASF", pct: 64, state: "running" as const },
  { name: "Copernicus DEM 30m · 巴东", kind: "DEM", pct: 38, state: "running" as const },
  { name: "GACOS · 2024-03-24", kind: "GACOS", pct: 0, state: "queued" as const },
];

const ACTIVITY = [
  { text: "石榴树包 区域 AOI 已绑定 (W110.22 S30.92 E110.52 N31.14)", time: "12 分钟前" },
  { text: "影像一致性核查通过 — 18 景，同轨同模式", time: "1 小时前" },
  { text: "生成数据准备报告 baxia_data_preparation_report.html", time: "今天 10:24" },
  { text: "Earthdata 凭据已通过系统密钥串验证", time: "昨天" },
];

export function Overview() {
  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">总览</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            离线优先的 Sentinel-1 InSAR 数据准备工作台 · 当前区域：石榴树包
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <Database className="h-4 w-4" />
            打开工作区
          </Button>
          <Button size="sm">
            <Download className="h-4 w-4" />
            继续下载
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {STATS.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label}>
              <CardContent className="flex items-center justify-between p-5">
                <div>
                  <div className="text-sm text-muted-foreground">{s.label}</div>
                  <div className="mt-1 text-3xl font-semibold tracking-tight">
                    {s.value}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">{s.sub}</div>
                </div>
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <Icon className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>准备流程</CardTitle>
            <CardDescription>从工作区到可交付报告的标准链路</CardDescription>
          </div>
          <Badge variant="warning">进行中 · 数据下载</Badge>
        </CardHeader>
        <CardContent>
          <div className="flex items-center">
            {STEPS.map((step, i) => (
              <div key={step.label} className="flex flex-1 items-center last:flex-none">
                <div className="flex flex-col items-center gap-2">
                  <div
                    className={
                      "flex h-9 w-9 items-center justify-center rounded-full border-2 " +
                      (step.done
                        ? "border-primary bg-primary text-primary-foreground"
                        : step.active
                          ? "border-primary text-primary"
                          : "border-border text-muted-foreground")
                    }
                  >
                    {step.done ? (
                      <CheckCircle2 className="h-5 w-5" />
                    ) : step.active ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Circle className="h-4 w-4" />
                    )}
                  </div>
                  <span
                    className={
                      "text-xs " +
                      (step.done || step.active
                        ? "font-medium text-foreground"
                        : "text-muted-foreground")
                    }
                  >
                    {step.label}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    className={
                      "mx-2 mb-6 h-0.5 flex-1 rounded " +
                      (step.done ? "bg-primary" : "bg-border")
                    }
                  />
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>下载队列</CardTitle>
              <CardDescription>ASF SLC · DEM · GACOS</CardDescription>
            </div>
            <Button variant="ghost" size="sm">
              查看全部
              <ArrowUpRight className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {DOWNLOADS.map((d) => (
              <div key={d.name} className="space-y-1.5">
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <Layers className="h-4 w-4 text-muted-foreground" />
                    <span className="font-medium">{d.name}</span>
                    <Badge variant="neutral">{d.kind}</Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {d.state === "done"
                      ? "完成"
                      : d.state === "queued"
                        ? "排队中"
                        : `${d.pct}%`}
                  </span>
                </div>
                <Progress value={d.pct} />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="flex flex-col lg:col-span-3">
          <CardHeader>
            <CardTitle>区域地图</CardTitle>
            <CardDescription>处理 AOI（OpenStreetMap）</CardDescription>
          </CardHeader>
          <CardContent className="flex-1 pt-0">
            <MapCard />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>近期活动</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {ACTIVITY.map((a, i) => (
            <div key={i} className="flex items-start gap-3">
              <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-primary" />
              <div className="flex-1 text-sm">{a.text}</div>
              <div className="shrink-0 text-xs text-muted-foreground">{a.time}</div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
