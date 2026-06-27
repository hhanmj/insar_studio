import { useEffect, useState } from "react";
import {
  CircleDot,
  FileUp,
  FolderOpen,
  Loader2,
  MapPinned,
  Pencil,
  SquareDashedMousePointer,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AoiDrawMap, type DrawMode } from "@/components/AoiDrawMap";
import {
  BridgeBadge,
  ErrorNote,
  FieldLabel,
  PageHeader,
  RegionBanner,
} from "@/components/common";
import {
  addRegion,
  formatBridgeError,
  hasBridge,
  pickOpenFile,
  setRegionAoiBbox,
  setRegionAoiFile,
  setRegionAoiGeojson,
  type Bbox,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

const DEFAULT_BBOX: Bbox = {
  west: 110.22,
  east: 110.52,
  south: 30.92,
  north: 31.14,
  crs: "EPSG:4326",
};

const MODES: { key: DrawMode; label: string; icon: typeof SquareDashedMousePointer }[] = [
  { key: "rect", label: "框选", icon: SquareDashedMousePointer },
  { key: "point", label: "打点", icon: CircleDot },
  { key: "polygon", label: "多边形", icon: Pencil },
];

export function Aoi() {
  const bridged = hasBridge();
  const { ctx, refresh } = usePrepContext();
  const region = ctx?.region ?? null;

  const [mode, setMode] = useState<DrawMode>("rect");
  const [west, setWest] = useState(String(DEFAULT_BBOX.west));
  const [south, setSouth] = useState(String(DEFAULT_BBOX.south));
  const [east, setEast] = useState(String(DEFAULT_BBOX.east));
  const [north, setNorth] = useState(String(DEFAULT_BBOX.north));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [quickRegion, setQuickRegion] = useState("region");
  const [quickBusy, setQuickBusy] = useState(false);

  const [path, setPath] = useState("");
  const [fBusy, setFBusy] = useState(false);
  const [fError, setFError] = useState<string | null>(null);

  useEffect(() => {
    if (region?.bbox) {
      setWest(String(region.bbox.west));
      setSouth(String(region.bbox.south));
      setEast(String(region.bbox.east));
      setNorth(String(region.bbox.north));
    }
  }, [region?.region_id, region?.bbox]);

  const previewBbox: Bbox = {
    west: Number(west) || DEFAULT_BBOX.west,
    east: Number(east) || DEFAULT_BBOX.east,
    south: Number(south) || DEFAULT_BBOX.south,
    north: Number(north) || DEFAULT_BBOX.north,
    crs: "EPSG:4326",
  };

  async function bindBbox(bbox: Bbox) {
    setWest(String(bbox.west));
    setSouth(String(bbox.south));
    setEast(String(bbox.east));
    setNorth(String(bbox.north));
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await setRegionAoiBbox(bbox.west, bbox.east, bbox.south, bbox.north);
      if (res.ok) {
        setNote(`AOI 已绑定到 ${res.region_name}`);
        await refresh();
      } else setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setError(formatBridgeError(e));
    } finally {
      setBusy(false);
    }
  }

  async function onBindBbox() {
    await bindBbox(previewBbox);
  }

  async function onPolygonDraw(ring: [number, number][]) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await setRegionAoiGeojson({
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [ring] },
      });
      if (res.ok) {
        setNote(`AOI 已绑定到 ${res.region_name}`);
        await refresh();
      } else setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setError(formatBridgeError(e));
    } finally {
      setBusy(false);
    }
  }

  function onPointDraw(lat: number, lng: number) {
    const delta = 0.025;
    void bindBbox({
      west: lng - delta,
      east: lng + delta,
      south: lat - delta,
      north: lat + delta,
      crs: "EPSG:4326",
    });
  }

  async function onBrowseAoi() {
    const pick = await pickOpenFile("选择 AOI 矢量文件", [
      "Vector (*.shp;*.kml;*.kmz;*.geojson;*.json)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) setPath(pick.path);
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
      setFError(formatBridgeError(e));
    } finally {
      setFBusy(false);
    }
  }

  async function onQuickCreateRegion() {
    if (!quickRegion.trim()) return;
    setQuickBusy(true);
    setError(null);
    try {
      const res = await addRegion(quickRegion.trim());
      if (res.ok) await refresh();
      else setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setError(formatBridgeError(e));
    } finally {
      setQuickBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <PageHeader
        title="区域 AOI"
        desc="绘制或导入当前研究区的处理范围，完成后自动绑定到项目。"
        right={<BridgeBadge bridged={bridged} />}
      />
      <RegionBanner ctx={ctx} />

      {!region && ctx?.project && (
        <Card>
          <CardContent className="flex flex-col gap-3 py-4 md:flex-row md:items-end">
            <div className="flex-1">
              <FieldLabel>新建当前研究区</FieldLabel>
              <Input
                value={quickRegion}
                onChange={(e) => setQuickRegion(e.target.value)}
                placeholder="region"
                spellCheck={false}
              />
            </div>
            <Button onClick={onQuickCreateRegion} disabled={quickBusy || !quickRegion.trim()}>
              {quickBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPinned className="h-4 w-4" />}
              创建并开始绘制
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[340px_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">绘制工具</CardTitle>
              <CardDescription>矩形、点选或多边形均会写入当前研究区</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {MODES.map(({ key, label, icon: Icon }) => (
                <Button
                  key={key}
                  size="sm"
                  variant={mode === key ? "default" : "outline"}
                  onClick={() => setMode(key)}
                  disabled={!region}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </Button>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">矩形 bbox</CardTitle>
              <CardDescription>EPSG:4326 十进制度</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
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
              {error && <ErrorNote text={error} />}
              {note && (
                <div className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
                  {note}
                </div>
              )}
              <Button onClick={onBindBbox} disabled={!region || busy} className="w-full">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPinned className="h-4 w-4" />}
                {region?.has_aoi ? "更新处理 AOI" : "绑定为处理 AOI"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">矢量文件</CardTitle>
              <CardDescription>shp / kml / geojson</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <Input
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  placeholder="浏览选择文件"
                  spellCheck={false}
                  className="font-mono text-xs"
                />
                <Button variant="outline" size="icon" onClick={onBrowseAoi} disabled={!region}>
                  <FolderOpen className="h-4 w-4" />
                </Button>
              </div>
              {fError && <ErrorNote text={fError} />}
              <Button
                variant="outline"
                onClick={onImportFile}
                disabled={!region || fBusy || !path.trim()}
                className="w-full"
              >
                {fBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
                从文件导入
              </Button>
            </CardContent>
          </Card>
        </div>

        <Card className="flex min-h-[560px] flex-col">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">AOI 地图</CardTitle>
            <CardDescription>
              {region
                ? region.has_aoi
                  ? `已绑定 · ${region.name}`
                  : `当前区域 · ${region.name}（尚未绑定 AOI）`
                : "先创建或选择研究区；底图未加载时也可以先填写 bbox"}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col pt-0">
            <div className="min-h-[520px] flex-1">
              <AoiDrawMap
                bbox={previewBbox}
                boundBbox={region?.has_aoi ? region.bbox : null}
                mode={mode}
                drawActive={!!region && !busy}
                minHeight={520}
                onRectDraw={(b) => void bindBbox(b)}
                onPolygonDraw={(ring) => void onPolygonDraw(ring)}
                onPointDraw={onPointDraw}
              />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
