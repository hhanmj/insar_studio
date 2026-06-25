import { useState } from "react";
import { FileUp, Loader2, MapPinned, SquareDashedMousePointer } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MapCard } from "@/components/MapCard";
import {
  BridgeBadge,
  ErrorNote,
  FieldLabel,
  PageHeader,
  RegionBanner,
} from "@/components/common";
import { hasBridge, setRegionAoiBbox, setRegionAoiFile } from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

export function Aoi() {
  const bridged = hasBridge();
  const { ctx, refresh } = usePrepContext();
  const region = ctx?.region ?? null;

  const [west, setWest] = useState("110.22");
  const [south, setSouth] = useState("30.92");
  const [east, setEast] = useState("110.52");
  const [north, setNorth] = useState("31.14");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [path, setPath] = useState("");
  const [fBusy, setFBusy] = useState(false);
  const [fError, setFError] = useState<string | null>(null);

  async function onBindBbox() {
    setBusy(true);
    setError(null);
    try {
      const res = await setRegionAoiBbox(
        Number(west),
        Number(east),
        Number(south),
        Number(north),
      );
      if (res.ok) await refresh();
      else setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onImportFile() {
    if (!path.trim()) return;
    setFBusy(true);
    setFError(null);
    try {
      const res = await setRegionAoiFile(path.trim());
      if (res.ok) await refresh();
      else setFError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setFError(String(e));
    } finally {
      setFBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <PageHeader
        title="区域 AOI"
        desc="为当前区域绑定处理范围：矩形 bbox 或矢量文件（shp / kml / geojson）"
        right={<BridgeBadge bridged={bridged} />}
      />
      <RegionBanner ctx={ctx} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <SquareDashedMousePointer className="h-4 w-4 text-primary" />
              <CardTitle>矩形 bbox</CardTitle>
            </div>
            <CardDescription>EPSG:4326，十进制度（west &lt; east，south &lt; north）</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <FieldLabel>West（西经）</FieldLabel>
                <Input value={west} onChange={(e) => setWest(e.target.value)} inputMode="decimal" />
              </div>
              <div>
                <FieldLabel>East（东经）</FieldLabel>
                <Input value={east} onChange={(e) => setEast(e.target.value)} inputMode="decimal" />
              </div>
              <div>
                <FieldLabel>South（南纬）</FieldLabel>
                <Input value={south} onChange={(e) => setSouth(e.target.value)} inputMode="decimal" />
              </div>
              <div>
                <FieldLabel>North（北纬）</FieldLabel>
                <Input value={north} onChange={(e) => setNorth(e.target.value)} inputMode="decimal" />
              </div>
            </div>
            {error && <ErrorNote text={error} />}
            <Button onClick={onBindBbox} disabled={!region || busy}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPinned className="h-4 w-4" />}
              绑定为处理 AOI
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileUp className="h-4 w-4 text-primary" />
              <CardTitle>矢量文件导入</CardTitle>
            </div>
            <CardDescription>
              .shp / .kml / .kmz / .geojson / .json（EPSG:4326，Polygon/MultiPolygon）
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <FieldLabel>文件路径</FieldLabel>
              <Input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="C:\\InSAR\\aoi\\shiliushubao.geojson"
                spellCheck={false}
              />
            </div>
            {fError && <ErrorNote text={fError} />}
            <Button
              variant="outline"
              onClick={onImportFile}
              disabled={!region || fBusy || !path.trim()}
            >
              {fBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
              从文件导入 AOI
            </Button>
          </CardContent>
        </Card>
      </div>

      {region?.has_aoi && region.bbox && (
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle>已绑定 AOI 预览</CardTitle>
            <CardDescription>
              {region.name} · W{region.bbox.west} S{region.bbox.south} E{region.bbox.east} N
              {region.bbox.north}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="h-[420px]">
              <MapCard bbox={region.bbox} label={`处理 AOI · ${region.name}`} minHeight={420} />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
