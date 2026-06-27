import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardPaste,
  FolderOpen,
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
import { ErrorNote, FieldLabel } from "@/components/common";
import {
  checkScenes,
  formatBridgeError,
  importScenesFile,
  importScenesDirectory,
  importScenesText,
  listScenes,
  pickDirectory,
  pickOpenFile,
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

function orbitLabel(dir: string): string {
  const u = (dir || "").toUpperCase();
  if (u === "ASCENDING" || u === "A") return "升轨";
  if (u === "DESCENDING" || u === "D") return "降轨";
  return "—";
}

function formatBytes(value: number | null | undefined): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n) || n <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = n;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}

export function SceneImportSection() {
  const { ctx, refresh } = usePrepContext();
  const region = ctx?.region ?? null;

  const [text, setText] = useState("");
  const [path, setPath] = useState("");
  const [slcDir, setSlcDir] = useState("");
  const [scenes, setScenes] = useState<SceneRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string | null>(null);

  const [report, setReport] = useState<Json | null>(null);
  const [cBusy, setCBusy] = useState(false);
  const [cError, setCError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const res = await listScenes();
      if (res.ok) setScenes(res.scenes);
    })();
  }, [region?.region_id, region?.scene_count]);

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
      setError(formatBridgeError(e));
    } finally {
      setBusy(false);
    }
  }

  async function onBrowseCart() {
    const pick = await pickOpenFile("选择 ASF 购物车文件", [
      "ASF cart (*.py;*.metalink;*.csv;*.geojson;*.json;*.txt;*.metadata;*.meta;*.met)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) setPath(pick.path);
  }

  async function onBrowseSlcDir() {
    const pick = await pickDirectory("选择已有 Sentinel-1 数据目录");
    if (pick.ok && pick.path) setSlcDir(pick.path);
  }

  async function onCheck() {
    setCBusy(true);
    setCError(null);
    try {
      const res = await checkScenes();
      if (res.ok) setReport(res.report);
      else setCError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setCError(formatBridgeError(e));
    } finally {
      setCBusy(false);
    }
  }

  const issues = (report?.issues as Json[] | undefined) ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>影像核查 · 导入场景</CardTitle>
          <CardDescription>
            导入 ASF 购物车或粘贴颗粒名 / 链接，并对场景集做一致性核查
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"S1A_IW_SLC__1SDV_20240312T223805_..._8F5C\nS1A_IW_GRDH_1SDV_20240324T223805_..._1A2B"}
            spellCheck={false}
            className="min-h-[100px] font-mono text-xs"
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={() => handleImport(() => importScenesText(text))}
              disabled={busy || !text.trim()}
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ClipboardPaste className="h-4 w-4" />
              )}
              导入粘贴内容
            </Button>
            <span className="text-xs text-muted-foreground">或从 ASF 文件：</span>
            <div className="flex min-w-[280px] flex-1 items-center gap-2">
              <Input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="选择 .py / .metalink / .csv / .geojson / metadata"
                spellCheck={false}
                readOnly
                className="font-mono text-xs"
              />
              <Button variant="outline" onClick={onBrowseCart} disabled={busy}>
                <FolderOpen className="h-4 w-4" />
                浏览
              </Button>
              <Button
                onClick={() => handleImport(() => importScenesFile(path.trim()))}
                disabled={busy || !path.trim()}
              >
                <FileUp className="h-4 w-4" />
                导入
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs text-muted-foreground">已有 Sentinel-1 数据目录：</span>
            <div className="flex min-w-[280px] flex-1 items-center gap-2">
              <Input
                value={slcDir}
                onChange={(e) => setSlcDir(e.target.value)}
                placeholder="自动识别目录内 SLC / GRD .zip / .SAFE 文件名"
                spellCheck={false}
                readOnly
                className="font-mono text-xs"
              />
              <Button variant="outline" onClick={onBrowseSlcDir} disabled={busy}>
                <FolderOpen className="h-4 w-4" />
                浏览
              </Button>
              <Button
                onClick={() => handleImport(() => importScenesDirectory(slcDir.trim()))}
                disabled={busy || !slcDir.trim()}
              >
                <FileUp className="h-4 w-4" />
                识别目录
              </Button>
            </div>
          </div>
          {busy && (
            <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                <span className="font-medium">正在解析场景并补全 ASF 元数据</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-primary/10">
                <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                Path、Frame、覆盖范围和文件大小需要向 ASF 元数据服务查询，网络慢时会多等一会儿。
              </div>
            </div>
          )}
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
              <CardDescription>解析自颗粒名 / ASF 购物车元数据</CardDescription>
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
                    <th className="px-3 py-2 font-medium">产品</th>
                    <th className="px-3 py-2 font-medium">升降轨</th>
                    <th className="px-3 py-2 font-medium">Path</th>
                    <th className="px-3 py-2 font-medium">Frame</th>
                    <th className="px-3 py-2 font-medium">极化</th>
                    <th className="px-3 py-2 font-medium">采集时间</th>
                    <th className="px-3 py-2 font-medium">绝对轨道</th>
                    <th className="px-3 py-2 font-medium">大小</th>
                    <th className="px-3 py-2 font-medium">覆盖</th>
                    <th className="px-3 py-2 font-medium">URL</th>
                  </tr>
                </thead>
                <tbody>
                  {scenes.map((s) => (
                    <tr key={s.scene_id} className="border-b last:border-0">
                      <td
                        className="max-w-[280px] truncate px-3 py-2 font-mono text-xs"
                        title={s.scene_id}
                      >
                        {s.scene_id}
                      </td>
                      <td className="px-3 py-2">{s.platform}</td>
                      <td className="px-3 py-2">{s.product_type}</td>
                      <td className="px-3 py-2">{orbitLabel(s.orbit_direction)}</td>
                      <td className="px-3 py-2">{s.path ?? s.relative_orbit ?? "—"}</td>
                      <td className="px-3 py-2">{s.frame ?? "—"}</td>
                      <td className="px-3 py-2">{s.polarization}</td>
                      <td className="px-3 py-2">
                        {s.acquisition_datetime?.slice(0, 16).replace("T", " ")}
                      </td>
                      <td className="px-3 py-2">{s.absolute_orbit ?? "—"}</td>
                      <td className="px-3 py-2">{formatBytes(s.file_size_remote)}</td>
                      <td className="px-3 py-2">
                        {s.footprint_bbox ? (
                          <Badge variant="success">有</Badge>
                        ) : (
                          <Badge variant="neutral">—</Badge>
                        )}
                      </td>
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
          <Button onClick={onCheck} disabled={cBusy || scenes.length === 0}>
            {cBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            运行核查
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {cBusy && (
            <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                <span className="font-medium">正在核查场景一致性</span>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                正在检查产品类型、波束、极化、重复项和覆盖信息。
              </div>
            </div>
          )}
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
                  有效 {String(report.valid_scenes ?? "—")} / 共{" "}
                  {String(report.total_scenes ?? "—")} 景
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
                        <span className="font-mono text-xs text-muted-foreground">
                          {String(it.code)}
                        </span>
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
