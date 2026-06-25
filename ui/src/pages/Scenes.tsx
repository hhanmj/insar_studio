import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardPaste,
  FileUp,
  Loader2,
  ShieldCheck,
  XCircle,
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
import { Textarea } from "@/components/ui/textarea";
import {
  BridgeBadge,
  ErrorNote,
  FieldLabel,
  PageHeader,
  RegionBanner,
} from "@/components/common";
import {
  checkScenes,
  hasBridge,
  importScenesFile,
  importScenesText,
  type Json,
  type SceneRow,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

function sevBadge(severity: string) {
  if (severity === "ERROR")
    return (
      <Badge variant="warning" className="bg-destructive/15 text-destructive">
        <XCircle className="h-3.5 w-3.5" />
        ERROR
      </Badge>
    );
  if (severity === "WARNING")
    return (
      <Badge variant="warning">
        <AlertTriangle className="h-3.5 w-3.5" />
        WARN
      </Badge>
    );
  return <Badge variant="neutral">INFO</Badge>;
}

export function Scenes() {
  const bridged = hasBridge();
  const { ctx, refresh } = usePrepContext();
  const region = ctx?.region ?? null;

  const [text, setText] = useState("");
  const [path, setPath] = useState("");
  const [scenes, setScenes] = useState<SceneRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string | null>(null);

  const [report, setReport] = useState<Json | null>(null);
  const [cBusy, setCBusy] = useState(false);
  const [cError, setCError] = useState<string | null>(null);

  async function handleImport(run: () => ReturnType<typeof importScenesText>) {
    setBusy(true);
    setError(null);
    setNotes(null);
    setReport(null);
    try {
      const res = await run();
      if (res.ok) {
        setScenes(res.scenes);
        await refresh();
        const bits: string[] = [`导入 ${res.scenes.length} 景`];
        if (res.duplicates.length) bits.push(`去重 ${res.duplicates.length}`);
        if (res.errors.length) bits.push(`跳过 ${res.errors.length} 行无效`);
        setNotes(bits.join(" · "));
      } else {
        setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onCheck() {
    setCBusy(true);
    setCError(null);
    try {
      const res = await checkScenes();
      if (res.ok) setReport(res.report);
      else setCError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setCError(String(e));
    } finally {
      setCBusy(false);
    }
  }

  const issues = (report?.issues as Json[] | undefined) ?? [];

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <PageHeader
        title="影像核查"
        desc="导入 ASF 购物车或粘贴颗粒名 / 链接，并对场景集做一致性核查"
        right={<BridgeBadge bridged={bridged} />}
      />
      <RegionBanner ctx={ctx} />

      <Card>
        <CardHeader>
          <CardTitle>导入场景</CardTitle>
          <CardDescription>每行一个 Sentinel-1 IW SLC 颗粒名或 ASF 下载链接</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"S1A_IW_SLC__1SDV_20240312T223805_..._8F5C\nS1A_IW_SLC__1SDV_20240324T223805_..._1A2B"}
            spellCheck={false}
            className="min-h-[120px] font-mono text-xs"
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={() => handleImport(() => importScenesText(text))}
              disabled={!region || busy || !text.trim()}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardPaste className="h-4 w-4" />}
              导入粘贴内容
            </Button>
            <span className="text-xs text-muted-foreground">或从购物车文件：</span>
            <div className="flex min-w-[260px] flex-1 items-center gap-2">
              <Input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="C:\\InSAR\\cart\\asf-sbas.py"
                spellCheck={false}
              />
              <Button
                variant="outline"
                onClick={() => handleImport(() => importScenesFile(path.trim()))}
                disabled={!region || busy || !path.trim()}
              >
                <FileUp className="h-4 w-4" />
                导入文件
              </Button>
            </div>
          </div>
          {notes && (
            <div className="inline-flex items-center gap-1.5 text-sm text-success">
              <CheckCircle2 className="h-4 w-4" />
              {notes}
            </div>
          )}
          {error && <ErrorNote text={error} />}
        </CardContent>
      </Card>

      {scenes.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>场景列表（{scenes.length}）</CardTitle>
              <CardDescription>解析自颗粒名 / 链接的关键元数据</CardDescription>
            </div>
            {(() => {
              const pols = Array.from(
                new Set(scenes.map((s) => s.polarization).filter(Boolean)),
              );
              const consistent = pols.length <= 1;
              return (
                <Badge variant={consistent ? "success" : "warning"}>
                  {consistent
                    ? `极化：${pols[0] ?? "—"}（一致）`
                    : `极化混合：${pols.join(" / ")}`}
                </Badge>
              );
            })()}
          </CardHeader>
          <CardContent className="pt-0">
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                    <th className="px-3 py-2 font-medium">Scene ID</th>
                    <th className="px-3 py-2 font-medium">平台</th>
                    <th className="px-3 py-2 font-medium">模式</th>
                    <th className="px-3 py-2 font-medium">极化</th>
                    <th className="px-3 py-2 font-medium">采集时间</th>
                    <th className="px-3 py-2 font-medium">绝对轨道</th>
                    <th className="px-3 py-2 font-medium">URL</th>
                  </tr>
                </thead>
                <tbody>
                  {scenes.map((s) => (
                    <tr key={s.scene_id} className="border-b last:border-0">
                      <td className="max-w-[320px] truncate px-3 py-2 font-mono text-xs" title={s.scene_id}>
                        {s.scene_id}
                      </td>
                      <td className="px-3 py-2">{s.platform}</td>
                      <td className="px-3 py-2">
                        {s.beam_mode} / {s.product_type}
                      </td>
                      <td className="px-3 py-2">{s.polarization}</td>
                      <td className="px-3 py-2">{s.acquisition_datetime?.slice(0, 16).replace("T", " ")}</td>
                      <td className="px-3 py-2">{s.absolute_orbit ?? "—"}</td>
                      <td className="px-3 py-2">
                        {s.has_url ? (
                          <Badge variant="success">有</Badge>
                        ) : (
                          <Badge variant="neutral">缺</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>一致性核查</CardTitle>
            <CardDescription>产品类型 / 波束 / 极化 / 重复项 / 覆盖</CardDescription>
          </div>
          <Button onClick={onCheck} disabled={!region || cBusy}>
            {cBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            运行核查
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {cError && <ErrorNote text={cError} />}
          {report ? (
            <>
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <Badge variant={report.has_errors ? "warning" : "success"}>
                  {report.has_errors ? (
                    <>
                      <XCircle className="h-3.5 w-3.5" />
                      存在阻断项
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      无阻断项
                    </>
                  )}
                </Badge>
                <span className="text-muted-foreground">
                  有效 {String(report.valid_scenes ?? "—")} / 共 {String(report.total_scenes ?? "—")} 景
                </span>
              </div>
              {issues.length === 0 ? (
                <div className="rounded-md border border-dashed py-6 text-center text-sm text-muted-foreground">
                  没有发现问题
                </div>
              ) : (
                <div className="space-y-2">
                  {issues.map((it, i) => (
                    <div key={i} className="flex items-start gap-3 rounded-md border px-3 py-2">
                      {sevBadge(String(it.severity))}
                      <div className="flex-1 text-sm">
                        <span className="font-mono text-xs text-muted-foreground">{String(it.code)}</span>
                        <div>{String(it.message)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="rounded-md border border-dashed py-6 text-center text-sm text-muted-foreground">
              导入场景后运行核查
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
