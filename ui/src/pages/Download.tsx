import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CloudDownload,
  Database,
  FolderOpen,
  KeyRound,
  Loader2,
  Mountain,
  Orbit,
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
import { Progress } from "@/components/ui/progress";
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
  formatBridgeError,
  type DownloadStatus,
  type Json,
  pauseAsfDownload,
  pickDirectory,
  planAsfDownload,
  planDemDownload,
  planDemDownloadBbox,
  planGacosRequest,
  downloadOrbits,
  getOrbitDownloadStatus,
  matchOrbitsDirectory,
  pauseOrbitDownload,
  resumeAsfDownload,
  resumeOrbitDownload,
  runDemDownload,
  runDemDownloadBbox,
  setDemDataset,
  startAsfDownload,
  startOrbitDownload,
  stopAsfDownload,
  stopOrbitDownload,
  type RunSummaryOk,
  type OrbitDownloadOk,
  type OrbitDownloadStatus,
  type OrbitMatchOk,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

const DEM_DATASETS = ["COP30", "COP90", "NASADEM", "SRTM_GL1", "SRTM_GL1_ELLIPSOIDAL"];

const DEFAULT_BBOX = {
  west: 110.22,
  east: 110.52,
  south: 30.92,
  north: 31.14,
};

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

function formatBytes(value: number | null | undefined): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = n;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}

function formatRate(value: number | null | undefined): string {
  return `${formatBytes(value)}/s`;
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

  const [orbitDir, setOrbitDir] = useState("");
  const [orbitMatch, setOrbitMatch] = useState<OrbitMatchOk | null>(null);
  const [orbitDownload, setOrbitDownload] = useState<OrbitDownloadOk | null>(null);
  const [orbitStatus, setOrbitStatus] = useState<OrbitDownloadStatus | null>(null);
  const [orbitBusy, setOrbitBusy] = useState(false);
  const [orbitDownloadBusy, setOrbitDownloadBusy] = useState(false);
  const [orbitErr, setOrbitErr] = useState<string | null>(null);

  const [dataset, setDataset] = useState("COP30");
  const [demWest, setDemWest] = useState(String(DEFAULT_BBOX.west));
  const [demEast, setDemEast] = useState(String(DEFAULT_BBOX.east));
  const [demSouth, setDemSouth] = useState(String(DEFAULT_BBOX.south));
  const [demNorth, setDemNorth] = useState(String(DEFAULT_BBOX.north));
  const [dem, setDem] = useState<{ plan: Json; report: Json } | null>(null);
  const [demRun, setDemRun] = useState<RunSummaryOk | null>(null);
  const [demBusy, setDemBusy] = useState(false);
  const [demRunBusy, setDemRunBusy] = useState(false);
  const [demErr, setDemErr] = useState<string | null>(null);

  const [gacos, setGacos] = useState<{ plan: Json; report: Json } | null>(null);
  const [gacBusy, setGacBusy] = useState(false);
  const [gacErr, setGacErr] = useState<string | null>(null);

  const [dlStatus, setDlStatus] = useState<DownloadStatus | null>(null);
  const [dlErr, setDlErr] = useState<string | null>(null);
  const [dlStarting, setDlStarting] = useState(false);
  const [confirmAsfStart, setConfirmAsfStart] = useState(false);

  useEffect(() => {
    void getCredentialStatus().then((r) =>
      setCreds({ earthdata: r.earthdata, opentopography: r.opentopography, gacos: r.gacos }),
    );
  }, []);

  useEffect(() => {
    let mounted = true;
    async function refreshOrbit() {
      const status = await getOrbitDownloadStatus();
      if (mounted) setOrbitStatus(status);
    }
    void refreshOrbit();
    const id = window.setInterval(refreshOrbit, 1000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    async function refreshStatus() {
      const status = await getDownloadStatus();
      if (mounted) setDlStatus(status);
    }
    void refreshStatus();
    const id = window.setInterval(refreshStatus, 1000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, []);

  async function onBrowseOutput() {
    const pick = await pickDirectory("选择下载输出根目录");
    if (pick.ok && pick.path) setOutputDir(pick.path);
  }

  async function onBrowseOrbitDir() {
    const pick = await pickDirectory("选择 Sentinel-1 精密轨道 EOF 目录");
    if (pick.ok && pick.path) setOrbitDir(pick.path);
  }

  const resolvedOutputDir = useMemo(
    () => outputDir.trim() || region?.root || ctx?.project?.root || ctx?.workspace?.root || "",
    [ctx?.project?.root, ctx?.workspace?.root, outputDir, region?.root],
  );

  async function startDownloadNow() {
    setDlStarting(true);
    setDlErr(null);
    try {
      const res = await startAsfDownload(resolvedOutputDir);
      if (!res.ok) {
        setDlErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      setDlStatus(await getDownloadStatus());
      setConfirmAsfStart(false);
    } catch (e) {
      setDlErr(formatBridgeError(e));
    } finally {
      setDlStarting(false);
    }
  }

  async function onStartDownload() {
    setDlErr(null);
    if (!resolvedOutputDir) {
      setDlErr("独立下载任务需要先确认输出目录");
      setConfirmAsfStart(true);
      return;
    }
    if (!confirmAsfStart) {
      setConfirmAsfStart(true);
      return;
    }
    await startDownloadNow();
  }

  async function onAsf() {
    setAsfBusy(true);
    setAsfErr(null);
    try {
      const res = await planAsfDownload(resolvedOutputDir);
      if (res.ok) setAsf(res.plan);
      else setAsfErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setAsfErr(formatBridgeError(e));
    } finally {
      setAsfBusy(false);
    }
  }
  async function onDem() {
    setDemBusy(true);
    setDemErr(null);
    try {
      const res = region
        ? await planDemDownload(resolvedOutputDir, dataset)
        : await planDemDownloadBbox(
            Number(demWest),
            Number(demEast),
            Number(demSouth),
            Number(demNorth),
            resolvedOutputDir,
            dataset,
          );
      if (res.ok) setDem({ plan: res.plan, report: res.report });
      else setDemErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setDemErr(formatBridgeError(e));
    } finally {
      setDemBusy(false);
    }
  }

  async function onOrbitMatch() {
    setOrbitBusy(true);
    setOrbitErr(null);
    try {
      const res = await matchOrbitsDirectory(orbitDir);
      if (res.ok) setOrbitMatch(res);
      else setOrbitErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setOrbitErr(formatBridgeError(e));
    } finally {
      setOrbitBusy(false);
    }
  }

  async function onOrbitDownload() {
    setOrbitDownloadBusy(true);
    setOrbitErr(null);
    try {
      const res = await startOrbitDownload(resolvedOutputDir);
      if (res.ok) {
        setOrbitStatus(await getOrbitDownloadStatus());
      } else {
        setOrbitErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setOrbitErr(formatBridgeError(e));
    } finally {
      setOrbitDownloadBusy(false);
    }
  }

  async function onDemDownload() {
    setDemRunBusy(true);
    setDemErr(null);
    try {
      const res = region
        ? await runDemDownload(resolvedOutputDir, dataset)
        : await runDemDownloadBbox(
            Number(demWest),
            Number(demEast),
            Number(demSouth),
            Number(demNorth),
            resolvedOutputDir,
            dataset,
          );
      if (res.ok) setDemRun(res);
      else setDemErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setDemErr(formatBridgeError(e));
    } finally {
      setDemRunBusy(false);
    }
  }
  async function onGacos() {
    setGacBusy(true);
    setGacErr(null);
    try {
      const res = await planGacosRequest(resolvedOutputDir);
      if (res.ok) setGacos({ plan: res.plan, report: res.report });
      else setGacErr(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setGacErr(formatBridgeError(e));
    } finally {
      setGacBusy(false);
    }
  }

  const gacDates = (gacos?.plan.unique_dates as string[] | undefined) ?? [];
  const dlActive = dlStatus?.state === "running" || dlStatus?.state === "paused";
  const transferredBytes = (dlStatus?.done_bytes ?? 0) + (dlStatus?.current_bytes ?? 0);
  const dlPct = dlStatus?.total_bytes
    ? Math.round((transferredBytes / dlStatus.total_bytes) * 100)
    : dlStatus && dlStatus.total > 0
      ? Math.round((dlStatus.done / dlStatus.total) * 100)
      : 0;
  const currentPct = dlStatus?.current_expected_size
    ? Math.round(((dlStatus.current_bytes ?? 0) / dlStatus.current_expected_size) * 100)
    : 0;
  const asfItems = (asf?.items as Json[] | undefined) ?? [];
  const orbitActive = orbitStatus?.state === "running" || orbitStatus?.state === "paused";
  const orbitPct =
    orbitStatus && orbitStatus.total > 0 ? Math.round((orbitStatus.done / orbitStatus.total) * 100) : 0;
  const asfProductCounts = asfItems.reduce<Record<string, number>>((acc, item) => {
    const key = String(item.product ?? "UNKNOWN");
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <PageHeader
        title="数据下载"
        desc="导入 ASF 场景、核查一致性，并按需执行 SLC / DEM / GACOS 任务"
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
            凭据来源由系统自动解析（keyring → 环境变量 → netrc）；输出目录在开始具体任务时确认。
          </p>
          <div className="max-w-lg">
            <FieldLabel>默认任务输出目录（可选，开始任务前会再次确认）</FieldLabel>
            <div className="flex items-center gap-2">
              <Input
                value={outputDir}
                onChange={(e) => setOutputDir(e.target.value)}
                placeholder={resolvedOutputDir || "独立任务请点击浏览选择输出目录"}
                spellCheck={false}
                className="font-mono text-xs"
              />
              <Button variant="outline" onClick={onBrowseOutput}>
                <FolderOpen className="h-4 w-4" />
                浏览
              </Button>
            </div>
            {resolvedOutputDir && (
              <div className="mt-2 truncate font-mono text-[11px] text-muted-foreground">
                当前将使用：{resolvedOutputDir}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="flex flex-col lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Satellite className="h-4 w-4 text-primary" />
              ASF Sentinel-1
            </CardTitle>
            <CardDescription>SLC / GRD 离线规划 + 真实下载（Earthdata 凭据）</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={onAsf} disabled={asfBusy} size="sm" variant="outline">
                {asfBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
                生成规划
              </Button>
              <Button onClick={onStartDownload} disabled={dlStarting || dlActive} size="sm">
                {dlStarting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {confirmAsfStart ? "确认并开始" : "开始下载"}
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
                强制结束
              </Button>
              {dlStatus && dlStatus.state !== "idle" && (
                <Badge variant={dlActive ? "warning" : "success"} className="ml-auto">
                  {dlStatus.state === "running" && `${dlStatus.done}/${dlStatus.total} · ${formatRate(dlStatus.bytes_per_second)}`}
                  {dlStatus.state === "paused" && "已暂停"}
                  {dlStatus.state === "finished" && "完成"}
                  {dlStatus.state === "cancelled" && "已结束"}
                  {dlStatus.state === "failed" && "失败"}
                </Badge>
              )}
            </div>
            {confirmAsfStart && (
              <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">确认 ASF 下载任务</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      本任务将使用当前导入的场景清单；没有 AOI 也允许下载。暂停或强制结束会保留
                      <span className="mx-1 font-mono">.part</span>
                      文件，后续同目录可断点续传。
                    </div>
                    <div className="mt-2 grid gap-2 text-xs md:grid-cols-2">
                      <KV k="输出根目录" v={resolvedOutputDir || "未选择"} />
                      <KV k="缓存/临时文件" v={`${resolvedOutputDir || "未选择"}\\.download_cache`} />
                    </div>
                  </div>
                  <Button size="sm" onClick={startDownloadNow} disabled={dlStarting || !resolvedOutputDir}>
                    {dlStarting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    确认执行
                  </Button>
                </div>
              </div>
            )}
            {dlStatus?.resume_supported && (
              <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                {dlStatus.resume_hint || "支持 .part 断点续传。"}
              </div>
            )}
            {asfErr && <ErrorNote text={asfErr} />}
            {dlErr && <ErrorNote text={dlErr} />}
            <div className="grid gap-3 md:grid-cols-2">
              {asf && (
                <div className="space-y-3 rounded-md border bg-muted/30 p-3 text-xs">
                  <div className="grid gap-2 md:grid-cols-2">
                    <KV k="规划含义" v="离线预检清单，不联网、不下载" />
                    <KV k="输出根" v={String(asf.output_directory ?? resolvedOutputDir)} />
                    <KV k="产品" v={Object.entries(asfProductCounts).map(([k, v]) => `${k}:${v}`).join(" / ") || "—"} />
                    <KV k="可下载" v={`${String(asf.planned_count ?? 0)} / ${String(asf.scene_count ?? 0)} 景`} />
                    <KV k="缺 URL" v={String(asf.missing_url_count ?? 0)} />
                    <KV k="产品目录" v={String(asf.slc_directory ?? "按产品自动分目录")} />
                  </div>
                  {asfItems.length > 0 && (
                    <div className="overflow-hidden rounded border bg-card">
                      {asfItems.slice(0, 5).map((item, i) => (
                        <div
                          key={`${String(item.scene_id)}-${i}`}
                          className="flex items-center gap-2 border-b px-2 py-1.5 last:border-0"
                        >
                          <Badge variant={String(item.status) === "PLANNED" ? "success" : "warning"}>
                            {String(item.status)}
                          </Badge>
                          <span className="min-w-0 flex-1 truncate font-mono" title={String(item.planned_path ?? "")}>
                            {String(item.expected_filename ?? item.scene_id)}
                          </span>
                          <span className="shrink-0 text-muted-foreground">
                            URL {String(item.url_status ?? "missing")}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {dlStatus && dlStatus.state !== "idle" && (
                <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted-foreground">整体进度</span>
                    <span className="font-mono">
                      {formatBytes(transferredBytes)}
                      {dlStatus.total_bytes ? ` / ${formatBytes(dlStatus.total_bytes)}` : ""}
                    </span>
                  </div>
                  <Progress value={dlPct} className="h-2" />
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted-foreground">下载速度</span>
                    <span className="font-mono">{formatRate(dlStatus.bytes_per_second)}</span>
                  </div>
                  {dlStatus.current_scene && (
                    <>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-muted-foreground">当前文件</span>
                        <span className="truncate font-mono" title={dlStatus.current_scene}>
                          {dlStatus.current_scene}
                        </span>
                      </div>
                      <Progress value={currentPct} className="h-1.5" />
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-muted-foreground">当前已下载</span>
                        <span className="font-mono">
                          {formatBytes(dlStatus.current_bytes)}
                          {dlStatus.current_expected_size ? ` / ${formatBytes(dlStatus.current_expected_size)}` : ""}
                        </span>
                      </div>
                    </>
                  )}
                  {dlStatus.summary_line && (
                    <div className={dlActive ? "text-muted-foreground" : "text-success"}>
                      {dlStatus.summary_line}
                    </div>
                  )}
                  {dlStatus.results_path && <KV k="结果 CSV" v={dlStatus.results_path} />}
                </div>
              )}
            </div>
            {dlStatus && dlStatus.log.length > 0 && (
              <div className="max-h-24 overflow-y-auto rounded-md border bg-muted/30 p-2 font-mono text-[11px]">
                {dlStatus.log.map((line, i) => (
                  <div key={i}>{line.detail}</div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Orbit className="h-4 w-4 text-primary" />
              精密轨道
            </CardTitle>
            <CardDescription>本地 EOF 匹配 / ASF POEORB 补下载</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-3">
            <div>
              <FieldLabel>本地轨道目录</FieldLabel>
              <div className="flex items-center gap-2">
                <Input
                  value={orbitDir}
                  onChange={(e) => setOrbitDir(e.target.value)}
                  placeholder="自动扫描 .EOF 文件名"
                  spellCheck={false}
                  className="font-mono text-xs"
                />
                <Button variant="outline" size="icon" onClick={onBrowseOrbitDir}>
                  <FolderOpen className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <Button onClick={onOrbitMatch} disabled={orbitBusy || !orbitDir.trim()} size="sm">
              {orbitBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Orbit className="h-4 w-4" />}
              扫描并匹配
            </Button>
            <Button onClick={onOrbitDownload} disabled={orbitDownloadBusy} size="sm" variant="outline">
              {orbitDownloadBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
              下载 POEORB
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!orbitActive || orbitStatus?.state !== "running"}
              onClick={() => void pauseOrbitDownload().then(() => getOrbitDownloadStatus().then(setOrbitStatus))}
            >
              <Pause className="h-4 w-4" />
              暂停
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!orbitActive || orbitStatus?.state !== "paused"}
              onClick={() => void resumeOrbitDownload().then(() => getOrbitDownloadStatus().then(setOrbitStatus))}
            >
              <Play className="h-4 w-4" />
              继续
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={!orbitActive}
              onClick={() => void stopOrbitDownload().then(() => getOrbitDownloadStatus().then(setOrbitStatus))}
            >
              <Square className="h-4 w-4" />
              结束
            </Button>
            <div className="rounded-md border bg-muted/30 p-3 text-xs">
              <KV k="自动保存目录" v="Sentinel_Orbit\\AUX_POEORB" />
            </div>
            {orbitErr && <ErrorNote text={orbitErr} />}
            {orbitStatus && orbitStatus.state !== "idle" && (
              <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-xs">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">
                    {orbitStatus.state === "running" && "轨道下载中"}
                    {orbitStatus.state === "paused" && "已暂停"}
                    {orbitStatus.state === "finished" && "下载完成"}
                    {orbitStatus.state === "cancelled" && "已结束"}
                    {orbitStatus.state === "failed" && "失败"}
                  </span>
                  <Badge variant={orbitActive ? "warning" : "success"}>
                    {orbitStatus.done}/{orbitStatus.total}
                  </Badge>
                </div>
                <Progress value={orbitPct} className="h-2" />
                {orbitStatus.current_scene && <KV k="当前场景" v={orbitStatus.current_scene} />}
                {orbitStatus.orbit_dir && <KV k="轨道目录" v={orbitStatus.orbit_dir} />}
                {orbitStatus.summary_line && <div className="text-muted-foreground">{orbitStatus.summary_line}</div>}
                {orbitStatus.pause_hint && <div className="text-muted-foreground">{orbitStatus.pause_hint}</div>}
                {orbitStatus.error && <ErrorNote text={orbitStatus.error} />}
                {orbitStatus.log.length > 0 && (
                  <div className="max-h-24 overflow-y-auto rounded border bg-card p-2 font-mono text-[11px]">
                    {orbitStatus.log.slice(-6).map((line, i) => (
                      <div key={i} className="truncate">{line.detail}</div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {orbitDownload && (
              <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-xs">
                <KV k="下载结果" v={orbitDownload.summary_line} />
                <KV k="轨道目录" v={orbitDownload.orbit_dir} />
                {orbitDownload.results.slice(0, 4).map((result, i) => (
                  <div key={i} className="rounded border bg-card px-2 py-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono" title={String(result.orbit_file || result.scene_id)}>
                        {String(result.orbit_file || result.scene_id)}
                      </span>
                      <Badge variant={String(result.outcome) === "success" ? "success" : "warning"}>
                        {String(result.outcome)}
                      </Badge>
                    </div>
                    <div className="mt-1 text-muted-foreground">{String(result.message ?? "")}</div>
                  </div>
                ))}
              </div>
            )}
            {orbitMatch && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                <KV k="EOF 文件" v={String(orbitMatch.orbit_files)} />
                <KV k="匹配" v={`${String(orbitMatch.report.matched_scenes ?? 0)} / ${String(orbitMatch.report.total_scenes ?? 0)} 景`} />
                <Badge
                  variant={
                    Number(orbitMatch.report.unmatched_scenes ?? 0) > 0 ? "warning" : "success"
                  }
                  className="mt-2"
                >
                  {Number(orbitMatch.report.unmatched_scenes ?? 0) > 0 ? "存在未匹配" : "全部匹配"}
                </Badge>
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
            {!region && (
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-2 text-xs font-medium text-foreground">独立 DEM bbox</div>
                <div className="grid grid-cols-2 gap-2">
                  <Input value={demWest} onChange={(e) => setDemWest(e.target.value)} inputMode="decimal" placeholder="West" />
                  <Input value={demEast} onChange={(e) => setDemEast(e.target.value)} inputMode="decimal" placeholder="East" />
                  <Input value={demSouth} onChange={(e) => setDemSouth(e.target.value)} inputMode="decimal" placeholder="South" />
                  <Input value={demNorth} onChange={(e) => setDemNorth(e.target.value)} inputMode="decimal" placeholder="North" />
                </div>
              </div>
            )}
            <Button onClick={onDem} disabled={demBusy} size="sm">
              {demBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
              生成下载规划
            </Button>
            <Button onClick={onDemDownload} disabled={demRunBusy} size="sm" variant="outline">
              {demRunBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              下载并转换
            </Button>
            {demErr && <ErrorNote text={demErr} />}
            {demRun && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                <KV k="执行结果" v={demRun.summary_line} />
                <KV k="下载 CSV" v={demRun.results_path || "—"} />
                <KV k="转换 CSV" v={demRun.conversion_results_path || "—"} />
                <KV k="原始 tif" v={demRun.raw_dem_path || "—"} />
                <KV k="椭球高 tif" v={demRun.ellipsoid_dem_path || "—"} />
                <KV k="SARscape DEM" v={demRun.sarscape_ready_dem_path || "—"} />
                <Badge variant={demRun.has_failures ? "warning" : "success"} className="mt-2">
                  {demRun.has_failures ? "存在失败项" : "下载与转换完成"}
                </Badge>
              </div>
            )}
            {dem && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                <KV k="数据集" v={String(dem.plan.dataset)} />
                <KV k="来源" v={String(dem.plan.provider)} />
                <KV
                  k="垂直基准"
                  v={`${String(dem.plan.source_vertical_datum)}→${String(dem.plan.target_vertical_datum)}`}
                />
                <KV k="缓冲(°)" v={String(dem.plan.buffer_degrees)} />
                <KV k="原始 tif" v={String(dem.plan.raw_dem_path ?? "—")} />
                <KV k="椭球高 tif" v={String(dem.plan.ellipsoid_dem_path ?? "—")} />
                <KV k="SARscape DEM" v={String(dem.plan.sarscape_ready_dem_path ?? "—")} />
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
