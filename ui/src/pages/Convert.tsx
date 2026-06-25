import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Info,
  Loader2,
  Mountain,
  RefreshCw,
  Repeat2,
  Sparkles,
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
import {
  BridgeBadge,
  ErrorNote,
  PageHeader,
  RegionBanner,
} from "@/components/common";
import {
  type ConversionAuto,
  hasBridge,
  type Json,
  planDemConversion,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

export function Convert() {
  const bridged = hasBridge();
  const { ctx } = usePrepContext();
  const region = ctx?.region ?? null;
  const dataset = ctx?.dem_dataset ?? "COP30";

  const [auto, setAuto] = useState<ConversionAuto | null>(null);
  const [plan, setPlan] = useState<Json | null>(null);
  const [report, setReport] = useState<Json | null>(null);
  const [busy, setBusy] = useState(false);
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
    } finally {
      setBusy(false);
    }
  }, []);

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
        desc="正高（EGM96 / EGM2008）→ WGS84 椭球高，输出 SARscape 就绪 DEM"
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

      {!region?.has_aoi ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            请先在『区域 AOI』设置处理范围后，系统会自动判定转换方案。
          </CardContent>
        </Card>
      ) : (
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
            <Button variant="outline" size="sm" onClick={detect} disabled={busy}>
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              重新检测
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && <ErrorNote text={error} />}

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
