import { useState } from "react";
import {
  FileCode2,
  FileJson,
  FileSpreadsheet,
  FileText,
  FileWarning,
  Loader2,
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
import { Input } from "@/components/ui/input";
import {
  BridgeBadge,
  ErrorNote,
  FieldLabel,
  PageHeader,
  RegionBanner,
} from "@/components/common";
import { formatBridgeError, generateReport, hasBridge, type Json } from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

const FILE_META: Record<string, { label: string; icon: typeof FileJson }> = {
  json: { label: "JSON", icon: FileJson },
  markdown: { label: "Markdown", icon: FileText },
  html: { label: "HTML", icon: FileCode2 },
  manifest: { label: "manifest.csv", icon: FileSpreadsheet },
  warnings: { label: "warnings.csv", icon: FileWarning },
};

const SECTION_LABELS: Record<string, string> = {
  scene_check: "场景核查",
  dem_planning: "DEM 规划",
  dem_conversion: "DEM 转换",
  gacos_planning: "GACOS 规划",
};

export function Report() {
  const bridged = hasBridge();
  const { ctx } = usePrepContext();
  const region = ctx?.region ?? null;

  const [outputDir, setOutputDir] = useState("");
  const [result, setResult] = useState<{
    report: Json;
    reports_dir: string;
    included: string[];
    paths: Record<string, string>;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onGenerate() {
    setBusy(true);
    setError(null);
    try {
      const res = await generateReport(outputDir);
      if (res.ok)
        setResult({
          report: res.report,
          reports_dir: res.reports_dir,
          included: res.included,
          paths: res.paths,
        });
      else setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setError(formatBridgeError(e));
    } finally {
      setBusy(false);
    }
  }

  const summary = (result?.report.summary as Json | undefined) ?? {};
  const status = String(summary.overall_status ?? "—");

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <PageHeader
        title="报告"
        desc="生成离线数据准备报告：JSON · Markdown · HTML · manifest · warnings"
        right={<BridgeBadge bridged={bridged} />}
      />
      <RegionBanner ctx={ctx} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            生成报告集
          </CardTitle>
          <CardDescription>
            汇总场景核查 / DEM / GACOS 等结果，写入 &lt;输出根&gt;/&lt;区域&gt;/07_reports/
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <span>报告由系统自动汇总已完成的各环节结果（场景核查 / DEM / GACOS），无需逐项配置。</span>
          </div>
          <div className="max-w-xl">
            <FieldLabel>输出根目录（留空用工作区根）</FieldLabel>
            <Input
              value={outputDir}
              onChange={(e) => setOutputDir(e.target.value)}
              placeholder="默认：工作区根路径"
              spellCheck={false}
            />
          </div>
          {error && <ErrorNote text={error} />}
          <Button onClick={onGenerate} disabled={!region || busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
            生成报告
          </Button>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>{String(result.report.title ?? "数据准备报告")}</CardTitle>
              <CardDescription className="font-mono text-xs">{result.reports_dir}</CardDescription>
            </div>
            <Badge
              variant={
                status === "ready" ? "success" : status === "blocked" ? "warning" : "neutral"
              }
            >
              状态：{status}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-4">
            {result.included.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-muted-foreground">自动汇总环节：</span>
                {result.included.map((s) => (
                  <Badge key={s} variant="default">
                    {SECTION_LABELS[s] ?? s}
                  </Badge>
                ))}
              </div>
            )}
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {Object.entries(result.paths).map(([key, path]) => {
                const meta = FILE_META[key] ?? { label: key, icon: FileText };
                const Icon = meta.icon;
                return (
                  <div
                    key={key}
                    className="flex items-center gap-3 rounded-md border bg-card px-3 py-2"
                  >
                    <Icon className="h-4 w-4 shrink-0 text-primary" />
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{meta.label}</div>
                      <div className="truncate font-mono text-[11px] text-muted-foreground" title={path}>
                        {path}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
