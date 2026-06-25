import { useEffect, useState } from "react";
import {
  CloudDownload,
  Database,
  FolderOpen,
  KeyRound,
  Layers,
  Loader2,
  Mountain,
  Pause,
  Play,
  Satellite,
  Square,
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
import { Input } from "@/components/ui/input";
import { SceneImportSection } from "@/components/SceneImportSection";
import {
  BridgeBadge,
  ErrorNote,
  FieldLabel,
  PageHeader,
  RegionBanner,
} from "@/components/common";
import {
  getCredentialStatus,
  getDownloadStatus,
  hasBridge,
  type DownloadStatus,
  type Json,
  pauseAsfDownload,
  pickDirectory,
  planAsfDownload,
  planDemDownload,
  planGacosRequest,
  resumeAsfDownload,
  setDemDataset,
  startAsfDownload,
  stopAsfDownload,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

const DEM_DATASETS = ["COP30", "COP90", "NASADEM", "SRTM_GL1", "SRTM_GL1_ELLIPSOIDAL"];

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 py-0.5">
      <span className="text-muted-foreground">{k}</span>
      <span className="truncate text-right font-mono text-xs text-foreground">{v}</span>
    </div>
  );
}

function credText(value: string): { label: string; ok: boolean } {
  if (!value || value === "none") return { label: "未配置", ok: false };
  if (value === "unavailable") return { label: "不可用", ok: false };
  return { label: value, ok: true };
}

export function Download() {
  const bridged = hasBridge();
  const { ctx } = usePrepContext();
  const region = ctx?.region ?? null;

  const [outputDir, setOutputDir] = useState("");
  const [creds, setCreds] = useState<{
    earthdata: string;
    opentopography: string;
    gacos: string;
  } | null>(null);

  const [asf, setAsf] = useState<Json | null>(null);
  const [asfBusy, setAsfBusy] = useState(false);
  const [asfErr, setAsfErr] = useState<string | null>(null);

  const [dataset, setDataset] = useState("COP30");
  const [dem, setDem] = useState<{ plan: Json; report: Json } | null>(null);
  const [demBusy, setDemBusy] = useState(false);
  const [demErr, setDemErr] = useState<string | null>(null);

  const [gacos, setGacos] = useState<{ plan: Json; report: Json } | null>(null);
  const [gacBusy, setGacBusy] = useState(false);
  const [gacErr, setGacErr] = useState<string | null>(null);

  const [dlStatus, setDlStatus] = useState<DownloadStatus | null>(null);
  const [dlErr, setDlErr] = useState<string | null>(null);
  const [dlStarting, setDlStarting] = useState(false);

  useEffect(() => {
    void getCredentialStatus().then((r) =>
      setCreds({ earthdata: r.earthdata, opentopography: r.opentopography, gacos: r.gacos }),
    );
  }, []);

  useEffect(() => {
    const active = dlStatus?.state === "running" || dlStatus?.state === "paused";
    if (!active) return;
    const id = window.setInterval(() => {
      void getDownloadStatus().then(setDlStatus);
    }, 800);
    return () => window.clearInterval(id);
  }, [dlStatus?.state]);

  async function onBrowseOutput() {
    const pick = await pickDirectory("选择下载输出根目录");
    if (pick.ok && pick.path) setOutputDir(pick.path);
  }

  async function onStartDownload() {
    setDlStarting(true);
    setDlErr(null);
    try {
      const res = await startAsfDownload(outputDir);
      if (!res.ok) {
        setDlErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      setDlStatus(await getDownloadStatus());
    } finally {
      setDlStarting(false);
    }
  }

  async function onAsf() {
    setAsfBusy(true);
    setAsfErr(null);
    try {
      const res = await planAsfDownload(outputDir);
      if (res.ok) setAsf(res.plan);
      else setAsfErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } finally {
      setAsfBusy(false);
    }
  }
  async function onDem() {
    setDemBusy(true);
    setDemErr(null);
    try {
      const res = await planDemDownload(outputDir, dataset);
      if (res.ok) setDem({ plan: res.plan, report: res.report });
      else setDemErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } finally {
      setDemBusy(false);
    }
  }
  async function onGacos() {
    setGacBusy(true);
    setGacErr(null);
    try {
      const res = await planGacosRequest(outputDir);
      if (res.ok) setGacos({ plan: res.plan, report: res.report });
      else setGacErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } finally {
      setGacBusy(false);
    }
  }

  const asfItems = (asf?.items as Json[] | undefined) ?? [];
  const gacDates = (gacos?.plan.unique_dates as string[] | undefined) ?? [];
  const dlActive = dlStatus?.state === "running" || dlStatus?.state === "paused";
  const dlPct =
    dlStatus && dlStatus.total > 0
      ? Math.round((dlStatus.done / dlStatus.total) * 100)
      : 0;

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <PageHeader
        title="数据下载"
        desc="导入 ASF 场景、核查一致性，并生成 SLC / DEM / GACOS 下载规划（dry-run）"
        right={<BridgeBadge bridged={bridged} />}
      />
      <RegionBanner ctx={ctx} />

      <SceneImportSection />

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-primary" />
              凭据状态
            </CardTitle>
            <CardDescription>仅做本地只读检查，不外发</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            {creds
              ? (
                  [
                    ["Earthdata", creds.earthdata],
                    ["OpenTopography", creds.opentopography],
                    ["GACOS", creds.gacos],
                  ] as const
                ).map(([label, val]) => {
                  const c = credText(val);
                  return (
                    <Badge key={label} variant={c.ok ? "success" : "neutral"}>
                      {label}: {c.label}
                    </Badge>
                  );
                })
              : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            凭据来源由系统自动解析（keyring → 环境变量 → netrc），无需手动选择；缺失时仅在执行下载前提示配置。
          </p>
          <div className="max-w-lg">
            <FieldLabel>输出根目录（留空用工作区根）</FieldLabel>
            <div className="flex items-center gap-2">
              <Input
                value={outputDir}
                onChange={(e) => setOutputDir(e.target.value)}
                placeholder="默认：工作区根路径"
                spellCheck={false}
                className="font-mono text-xs"
              />
              <Button variant="outline" onClick={onBrowseOutput}>
                <FolderOpen className="h-4 w-4" />
                浏览
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="flex flex-col lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Satellite className="h-4 w-4 text-primary" />
              ASF SLC · 真实下载
            </CardTitle>
            <CardDescription>
              需要 Earthdata 凭据；SLC 写入 &lt;输出根&gt;/02_slc · 支持暂停 / 停止
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={onStartDownload} disabled={!region || dlStarting || dlActive} size="sm">
                {dlStarting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                开始下载
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!dlActive || dlStatus?.state !== "running"}
                onClick={() => void pauseAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}
              >
                <Pause className="h-4 w-4" />
                暂停
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!dlActive || dlStatus?.state !== "paused"}
                onClick={() => void resumeAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}
              >
                <Play className="h-4 w-4" />
                继续
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={!dlActive}
                onClick={() => void stopAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}
              >
                <Square className="h-4 w-4" />
                停止
              </Button>
              {dlStatus && dlStatus.state !== "idle" && (
                <Badge variant={dlActive ? "warning" : "success"} className="ml-auto">
                  {dlStatus.state === "running" && `下载中 ${dlStatus.done}/${dlStatus.total}`}
                  {dlStatus.state === "paused" && "已暂停"}
                  {dlStatus.state === "finished" && "已完成"}
                  {dlStatus.state === "cancelled" && "已取消"}
                  {dlStatus.state === "failed" && "失败"}
                </Badge>
              )}
            </div>
            {dlErr && <ErrorNote text={dlErr} />}
            {dlStatus && dlStatus.state !== "idle" && (
              <>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${dlPct}%` }}
                  />
                </div>
                {dlStatus.current_scene && (
                  <div className="truncate font-mono text-xs text-muted-foreground">
                    当前：{dlStatus.current_scene}
                  </div>
                )}
                {dlStatus.summary_line && !dlActive && (
                  <div className="text-sm text-success">{dlStatus.summary_line}</div>
                )}
                {dlStatus.error && <ErrorNote text={dlStatus.error} />}
                {dlStatus.log.length > 0 && (
                  <div className="max-h-28 overflow-y-auto rounded-md border bg-muted/30 p-2 font-mono text-[11px]">
                    {dlStatus.log.map((line, i) => (
                      <div key={i}>{line.detail}</div>
                    ))}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Satellite className="h-4 w-4 text-primary" />
              ASF SLC
            </CardTitle>
            <CardDescription>Sentinel-1 IW SLC</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-3">
            <Button onClick={onAsf} disabled={!region || asfBusy} size="sm">
              {asfBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
              生成下载规划
            </Button>
            {asfErr && <ErrorNote text={asfErr} />}
            {asf && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                <KV k="场景数" v={String(asf.scene_count ?? 0)} />
                <KV k="可下载" v={String(asf.planned_count ?? 0)} />
                <KV k="缺 URL" v={String(asf.missing_url_count ?? 0)} />
                <KV k="需凭据" v={asf.credential_required ? "是" : "否"} />
                <div className="mt-2 max-h-32 space-y-1 overflow-y-auto">
                  {asfItems.slice(0, 6).map((it, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Layers className="h-3 w-3 text-muted-foreground" />
                      <span className="truncate font-mono text-[11px]" title={String(it.scene_id)}>
                        {String(it.scene_id)}
                      </span>
                      <Badge variant="neutral" className="ml-auto shrink-0 text-[10px]">
                        {String(it.status)}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Mountain className="h-4 w-4 text-primary" />
              DEM
            </CardTitle>
            <CardDescription>OpenTopography 全球 DEM</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-3">
            <div>
              <FieldLabel>数据集</FieldLabel>
              <select
                value={dataset}
                onChange={(e) => {
                  setDataset(e.target.value);
                  void setDemDataset(e.target.value);
                }}
                className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {DEM_DATASETS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <Button onClick={onDem} disabled={!region || demBusy} size="sm">
              {demBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
              生成下载规划
            </Button>
            {demErr && <ErrorNote text={demErr} />}
            {dem && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                <KV k="数据集" v={String(dem.plan.dataset)} />
                <KV k="来源" v={String(dem.plan.provider)} />
                <KV
                  k="垂直基准"
                  v={`${String(dem.plan.source_vertical_datum)}→${String(dem.plan.target_vertical_datum)}`}
                />
                <KV k="缓冲(°)" v={String(dem.plan.buffer_degrees)} />
                <Badge variant={(dem.report.has_errors as boolean) ? "warning" : "success"} className="mt-2">
                  {(dem.report.has_errors as boolean) ? "校验有阻断" : "校验通过"}
                </Badge>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="h-4 w-4 text-primary" />
              GACOS
            </CardTitle>
            <CardDescription>对流层延迟改正</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-3">
            <Button onClick={onGacos} disabled={!region || gacBusy} size="sm">
              {gacBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
              生成请求规划
            </Button>
            {gacErr && <ErrorNote text={gacErr} />}
            {gacos && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                <KV k="日期数" v={String(gacDates.length)} />
                <KV k="批次" v={String((gacos.plan.batches as Json[] | undefined)?.length ?? 0)} />
                <div className="mt-2 flex flex-wrap gap-1">
                  {gacDates.slice(0, 8).map((d) => (
                    <Badge key={d} variant="neutral" className="text-[10px]">
                      {d}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
