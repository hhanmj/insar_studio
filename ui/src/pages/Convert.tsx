import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  FileUp,
  FolderOpen,
  Info,
  Loader2,
  Mountain,
  RefreshCw,
  Repeat2,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  BridgeBadge,
  ErrorNote,
  FieldLabel,
  PageHeader,
  RegionBanner,
} from "@/components/common";
import {
  type ConversionAuto,
  formatBridgeError,
  hasBridge,
  type Json,
  pickDirectory,
  pickOpenFile,
  planDemConversion,
  planDemConversionBbox,
  planLocalDemConversion,
  runDemConversion,
  runDemConversionBbox,
  runLocalDemConversion,
  type RunSummaryOk,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

export function Convert() {
  const bridged = hasBridge();
  const { ctx } = usePrepContext();
  const region = ctx?.region ?? null;
  const dataset = ctx?.dem_dataset ?? "COP30";

  const [outputDir, setOutputDir] = useState("");
  const [west, setWest] = useState("110.22");
  const [east, setEast] = useState("110.52");
  const [south, setSouth] = useState("30.92");
  const [north, setNorth] = useState("31.14");
  const [localDemPath, setLocalDemPath] = useState("");
  const [localDatum, setLocalDatum] = useState("auto");

  const [auto, setAuto] = useState<ConversionAuto | null>(null);
  const [plan, setPlan] = useState<Json | null>(null);
  const [report, setReport] = useState<Json | null>(null);
  const [runResult, setRunResult] = useState<RunSummaryOk | null>(null);
  const [busy, setBusy] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const detect = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await planDemConversion();
      if (res.ok) {
        setAuto(res.auto);
        setPlan(res.plan);
        setReport(res.report);
      } else {
        setAuto(null);
        setPlan(null);
        setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setAuto(null);
      setPlan(null);
      setError(formatBridgeError(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const detectStandalone = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await planDemConversionBbox(
        Number(west),
        Number(east),
        Number(south),
        Number(north),
        outputDir,
        dataset,
      );
      if (res.ok) {
        setAuto(res.auto);
        setPlan(res.plan);
        setReport(res.report);
      } else {
        setAuto(null);
        setPlan(null);
        setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setAuto(null);
      setPlan(null);
      setError(formatBridgeError(e));
    } finally {
      setBusy(false);
    }
  }, [dataset, east, north, outputDir, south, west]);

  async function onBrowseOutput() {
    const pick = await pickDirectory("选择 DEM 转换输出根目录");
    if (pick.ok && pick.path) setOutputDir(pick.path);
  }

  async function onBrowseLocalDem() {
    const pick = await pickOpenFile("选择本地 DEM GeoTIFF", [
      "GeoTIFF (*.tif;*.tiff)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) setLocalDemPath(pick.path);
  }

  async function detectLocalDem() {
    setBusy(true);
    setError(null);
    try {
      const res = await planLocalDemConversion(localDemPath, outputDir, localDatum);
      if (res.ok) {
        setAuto(res.auto);
        setPlan(res.plan);
        setReport(res.report);
      } else {
        setAuto(null);
        setPlan(null);
        setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setAuto(null);
      setPlan(null);
      setError(formatBridgeError(e));
    } finally {
      setBusy(false);
    }
  }

  async function runConvert() {
    setRunBusy(true);
    setError(null);
    try {
      const res = region?.has_aoi
        ? await runDemConversion(outputDir)
        : await runDemConversionBbox(
            Number(west),
            Number(east),
            Number(south),
            Number(north),
            outputDir,
            dataset,
          );
      if (res.ok) setRunResult(res);
      else setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setError(formatBridgeError(e));
    } finally {
      setRunBusy(false);
    }
  }

  async function runLocalConvert() {
    setRunBusy(true);
    setError(null);
    try {
      const res = await runLocalDemConversion(localDemPath, outputDir, localDatum);
      if (res.ok) setRunResult(res);
      else setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setError(formatBridgeError(e));
    } finally {
      setRunBusy(false);
    }
  }

  // Auto-detect whenever a usable region/dataset is available — no user choice.
  useEffect(() => {
    if (region?.has_aoi) void detect();
  }, [region?.has_aoi, region?.region_id, dataset, detect]);

  const steps = (plan?.steps as Json[] | undefined) ?? [];
  const noConvert = auto && !auto.requires_conversion;

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <PageHeader
        title="DEM 转换"
        desc="正高（EGM96 / EGM2008）→ WGS84 椭球高，输出 SARscape ENVI _dem + .hdr + .sml"
        right={<BridgeBadge bridged={bridged} />}
      />
      <RegionBanner ctx={ctx} />

      <div className="flex items-start gap-2 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <span>
          转换方式（是否需要转换、采用哪种大地水准面）由系统根据所选 DEM 数据集
          <b className="mx-1 font-mono">{dataset}</b>
          自动识别并应用，无需手动选择。数据集在『数据下载 › DEM』中设置。
        </span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileUp className="h-4 w-4 text-primary" />
            本地 DEM 输入
          </CardTitle>
          <CardDescription>
            选择用户已有 GeoTIFF，系统尝试识别高程基准；识别不准时可手动指定转换方式。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <FieldLabel>本地 DEM 文件</FieldLabel>
            <div className="flex gap-2">
              <Input
                value={localDemPath}
                onChange={(e) => setLocalDemPath(e.target.value)}
                placeholder="选择 .tif / .tiff"
                spellCheck={false}
                className="font-mono text-xs"
              />
              <Button variant="outline" onClick={onBrowseLocalDem}>
                <FolderOpen className="h-4 w-4" />
                浏览
              </Button>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-[240px_1fr]">
            <div>
              <FieldLabel>源高程基准</FieldLabel>
              <select
                value={localDatum}
                onChange={(e) => setLocalDatum(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="auto">自动识别</option>
                <option value="EGM96">EGM96 正高</option>
                <option value="EGM2008">EGM2008 正高</option>
                <option value="ORTHOMETRIC">正高（未知 geoid）</option>
                <option value="WGS84_ELLIPSOID">WGS84 椭球高</option>
                <option value="UNKNOWN">未知，先生成人工复核计划</option>
              </select>
            </div>
            <div>
              <FieldLabel>输出根目录（留空用当前研究区或 DEM 文件所在目录）</FieldLabel>
              <div className="flex gap-2">
                <Input
                  value={outputDir}
                  onChange={(e) => setOutputDir(e.target.value)}
                  placeholder="可选"
                  spellCheck={false}
                  className="font-mono text-xs"
                />
                <Button variant="outline" onClick={onBrowseOutput}>
                  <FolderOpen className="h-4 w-4" />
                  浏览
                </Button>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={detectLocalDem} disabled={busy || !localDemPath.trim()}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              识别并生成转换方案
            </Button>
            <Button
              variant="outline"
              onClick={runLocalConvert}
              disabled={runBusy || !localDemPath.trim()}
            >
              {runBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Repeat2 className="h-4 w-4" />}
              转换本地 DEM
            </Button>
          </div>
        </CardContent>
      </Card>

      {!region?.has_aoi && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Repeat2 className="h-4 w-4 text-primary" />
              独立 DEM 转换方案
            </CardTitle>
            <CardDescription>
              不依赖当前研究区，直接用 bbox 和输出目录生成转换计划。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <FieldLabel>输出根目录</FieldLabel>
              <div className="flex gap-2">
                <Input
                  value={outputDir}
                  onChange={(e) => setOutputDir(e.target.value)}
                  placeholder="没有工作区时必须指定"
                  spellCheck={false}
                  className="font-mono text-xs"
                />
                <Button variant="outline" onClick={onBrowseOutput}>
                  <FolderOpen className="h-4 w-4" />
                  浏览
                </Button>
              </div>
            </div>
            <div className="grid gap-2 md:grid-cols-4">
              <div>
                <FieldLabel>West</FieldLabel>
                <Input value={west} onChange={(e) => setWest(e.target.value)} inputMode="decimal" />
              </div>
              <div>
                <FieldLabel>East</FieldLabel>
                <Input value={east} onChange={(e) => setEast(e.target.value)} inputMode="decimal" />
              </div>
              <div>
                <FieldLabel>South</FieldLabel>
                <Input value={south} onChange={(e) => setSouth(e.target.value)} inputMode="decimal" />
              </div>
              <div>
                <FieldLabel>North</FieldLabel>
                <Input value={north} onChange={(e) => setNorth(e.target.value)} inputMode="decimal" />
              </div>
            </div>
            <Button onClick={detectStandalone} disabled={busy}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              生成独立转换方案
            </Button>
            <Button onClick={runConvert} disabled={runBusy} variant="outline">
              {runBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Repeat2 className="h-4 w-4" />}
              执行独立转换
            </Button>
          </CardContent>
        </Card>
      )}

      {(region?.has_aoi || plan || error) && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Repeat2 className="h-4 w-4 text-primary" />
                自动转换方案
              </CardTitle>
              <CardDescription>
                数据集 <span className="font-mono">{dataset}</span> · 目标 WGS84 椭球高
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={region?.has_aoi ? detect : detectStandalone}
              disabled={busy}
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              重新检测
            </Button>
            <Button size="sm" onClick={runConvert} disabled={runBusy}>
              {runBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Repeat2 className="h-4 w-4" />}
              执行转换
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && <ErrorNote text={error} />}

            {runResult && (
              <div
                className={
                  "rounded-md border px-3 py-2.5 text-sm " +
                  (runResult.has_failures
                    ? "border-warning/40 bg-warning/10"
                    : "border-success/40 bg-success/10")
                }
              >
                <div className="font-medium">{runResult.summary_line}</div>
                {runResult.results_path && (
                  <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
                    {runResult.results_path}
                  </div>
                )}
              </div>
            )}

            {auto && (
              <div
                className={
                  "flex items-start gap-2 rounded-md border px-3 py-2.5 text-sm " +
                  (noConvert
                    ? "border-success/40 bg-success/10"
                    : "border-warning/40 bg-warning/10")
                }
              >
                {noConvert ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                ) : (
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                )}
                <div className="space-y-1">
                  <div>{auto.message}</div>
                  <div className="flex flex-wrap gap-2 pt-0.5">
                    <Badge variant="neutral">源 {auto.source}</Badge>
                    <Badge variant="neutral">目标 {auto.target}</Badge>
                    {auto.geoid_model && (
                      <Badge variant="neutral">大地水准面 {auto.geoid_model}</Badge>
                    )}
                    <Badge variant={noConvert ? "success" : "warning"}>
                      {noConvert ? "无需转换" : "需要转换"}
                    </Badge>
                  </div>
                </div>
              </div>
            )}

            {steps.length > 0 && (
              <div className="space-y-2">
                {steps.map((s, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-md border px-3 py-2">
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                      {i + 1}
                    </span>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        {String(s.step_type)}
                        {s.geoid_model ? (
                          <Badge variant="neutral" className="text-[10px]">
                            geoid: {String(s.geoid_model)}
                          </Badge>
                        ) : null}
                      </div>
                      <div className="text-xs text-muted-foreground">{String(s.description)}</div>
                    </div>
                    {(s.requires_geoid as boolean) ? (
                      <Mountain className="h-4 w-4 text-warning" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-success" />
                    )}
                  </div>
                ))}
              </div>
            )}

            {plan && (
              <div className="space-y-1.5 rounded-md border bg-muted/30 p-3 text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-20 shrink-0 text-muted-foreground">raw</span>
                  <span className="truncate font-mono">{String(plan.raw_dem_path)}</span>
                </div>
                {!noConvert && (
                  <div className="flex items-center gap-2">
                    <ArrowRight className="h-3 w-3 text-muted-foreground" />
                    <span className="w-16 shrink-0 text-muted-foreground">ellipsoid</span>
                    <span className="truncate font-mono">{String(plan.ellipsoid_dem_path)}</span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  <span className="w-16 shrink-0 text-muted-foreground">sarscape</span>
                  <span className="truncate font-mono">{String(plan.sarscape_ready_dem_path)}</span>
                </div>
              </div>
            )}

            {report ? (
              <Badge variant={(report.has_errors as boolean) ? "warning" : "success"}>
                {(report.has_errors as boolean) ? "校验有阻断" : "校验通过"}
              </Badge>
            ) : null}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
