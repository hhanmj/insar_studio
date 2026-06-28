import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type {
  LatLng,
  LatLngBoundsExpression,
  LatLngExpression,
  LeafletMouseEvent,
  Map as LeafletMap,
} from "leaflet";
import { DomEvent } from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Polyline,
  Polygon,
  Popup,
  Rectangle,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import {
  Check,
  Layers,
  LocateFixed,
  MapPinned,
  Minus,
  Pentagon,
  Plus,
  Square,
  Trash2,
} from "lucide-react";
import type { Bbox, Json, SceneRow } from "@/lib/bridge";
import { cn } from "@/lib/utils";

export type WorkbenchDrawMode = "rect" | "polygon" | "point";

export type MapLayerKey =
  | "osm"
  | "cartoLight"
  | "cartoDark"
  | "arcgisSatellite"
  | "arcgisTopo"
  | "arcgisStreet"
  | "openTopoMap"
  | "googleSatellite"
  | "googleMap"
  | "googleHybrid"
  | "gaodeMap"
  | "gaodeSatellite"
  | "tiandituSatellite"
  | "tiandituVector";

const DEFAULT_BBOX: Bbox = {
  west: 73.5,
  east: 135.1,
  south: 18.0,
  north: 53.6,
  crs: "EPSG:4326",
};

const MAP_LAYERS: Record<
  MapLayerKey,
  {
    label: string;
    desc: string;
    url: string;
    attribution: string;
    subdomains?: string;
    maxZoom?: number;
    requiresToken?: boolean;
    category: string;
  }
> = {
  osm: {
    label: "OpenStreetMap",
    desc: "通用街道底图",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap",
    subdomains: "abc",
    maxZoom: 19,
    category: "开放底图",
  },
  cartoLight: {
    label: "Carto Light",
    desc: "浅色制图底图",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 19,
    category: "开放底图",
  },
  cartoDark: {
    label: "Carto Dark",
    desc: "暗色制图底图",
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 19,
    category: "开放底图",
  },
  arcgisSatellite: {
    label: "ArcGIS 卫星",
    desc: "Esri World Imagery",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "&copy; Esri",
    maxZoom: 19,
    category: "ArcGIS",
  },
  arcgisTopo: {
    label: "ArcGIS 地形",
    desc: "Esri World Topo",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    attribution: "&copy; Esri",
    maxZoom: 19,
    category: "ArcGIS",
  },
  arcgisStreet: {
    label: "ArcGIS 街道",
    desc: "Esri World Street",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
    attribution: "&copy; Esri",
    maxZoom: 19,
    category: "ArcGIS",
  },
  openTopoMap: {
    label: "OpenTopoMap",
    desc: "地形与等高线",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenTopoMap",
    subdomains: "abc",
    maxZoom: 17,
    category: "开放底图",
  },
  googleSatellite: {
    label: "Google 卫星",
    desc: "GeoDownloader 同类图源",
    url: "https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    attribution: "&copy; Google",
    subdomains: "0123",
    maxZoom: 20,
    category: "商业图源",
  },
  googleMap: {
    label: "Google 地图",
    desc: "道路底图，部分网络可能不可达",
    url: "https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
    attribution: "&copy; Google",
    subdomains: "0123",
    maxZoom: 20,
    category: "商业图源",
  },
  googleHybrid: {
    label: "Google 混合",
    desc: "卫星 + 注记",
    url: "https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    attribution: "&copy; Google",
    subdomains: "0123",
    maxZoom: 20,
    category: "商业图源",
  },
  gaodeMap: {
    label: "高德地图",
    desc: "GCJ-02 图源，仅作底图参考",
    url: "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
    attribution: "&copy; 高德地图",
    subdomains: "1234",
    maxZoom: 18,
    category: "商业图源",
  },
  gaodeSatellite: {
    label: "高德卫星",
    desc: "GCJ-02 图源，仅作底图参考",
    url: "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
    attribution: "&copy; 高德地图",
    subdomains: "1234",
    maxZoom: 18,
    category: "商业图源",
  },
  tiandituSatellite: {
    label: "天地图卫星",
    desc: "需在设置中填写 Token",
    url: "https://t{s}.tianditu.gov.cn/img_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk={token}",
    attribution: "&copy; 天地图",
    subdomains: "01234567",
    maxZoom: 18,
    requiresToken: true,
    category: "天地图",
  },
  tiandituVector: {
    label: "天地图矢量",
    desc: "需在设置中填写 Token",
    url: "https://t{s}.tianditu.gov.cn/vec_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk={token}",
    attribution: "&copy; 天地图",
    subdomains: "01234567",
    maxZoom: 18,
    requiresToken: true,
    category: "天地图",
  },
};

function fmt(v: number): string {
  return Number.isFinite(v) ? v.toFixed(4) : "-";
}

function boundsFromBbox(bbox: Bbox): LatLngBoundsExpression {
  return [
    [bbox.south, bbox.west],
    [bbox.north, bbox.east],
  ];
}

function centerFromBbox(bbox: Bbox): LatLngExpression {
  return [(bbox.south + bbox.north) / 2, (bbox.west + bbox.east) / 2];
}

function isValidBbox(bbox: Bbox | null | undefined): bbox is Bbox {
  return !!bbox && bbox.west < bbox.east && bbox.south < bbox.north;
}

function fmtBytes(value: number | null | undefined): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n) || n <= 0) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = n;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}

function polarizationLabel(value: string | null | undefined): string {
  const upper = (value || "").toUpperCase();
  const labels: Record<string, string> = {
    DV: "VV+VH",
    DH: "HH+HV",
    SV: "VV",
    SH: "HH",
  };
  return labels[upper] ? `${labels[upper]} (${upper})` : upper || "-";
}

function unionBbox(boxes: (Bbox | null | undefined)[]): Bbox | null {
  const valid = boxes.filter(isValidBbox);
  if (!valid.length) return null;
  return {
    west: Math.min(...valid.map((box) => box.west)),
    east: Math.max(...valid.map((box) => box.east)),
    south: Math.min(...valid.map((box) => box.south)),
    north: Math.max(...valid.map((box) => box.north)),
    crs: "EPSG:4326",
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function ringToLatLngs(value: unknown): LatLngExpression[] | null {
  if (!Array.isArray(value)) return null;
  const ring: LatLngExpression[] = [];
  for (const item of value) {
    if (
      Array.isArray(item) &&
      item.length >= 2 &&
      typeof item[0] === "number" &&
      typeof item[1] === "number"
    ) {
      ring.push([item[1], item[0]]);
    }
  }
  return ring.length >= 3 ? ring : null;
}

function polygonFromCoordinates(value: unknown): LatLngExpression[][] | null {
  if (!Array.isArray(value)) return null;
  const rings = value.map(ringToLatLngs).filter((ring): ring is LatLngExpression[] => !!ring);
  return rings.length ? rings : null;
}

function geometryPolygons(value: unknown): LatLngExpression[][][] {
  const geometry = asRecord(value);
  if (!geometry) return [];
  const type = String(geometry.type || "");
  const coordinates = geometry.coordinates;
  if (type === "Polygon") {
    const polygon = polygonFromCoordinates(coordinates);
    return polygon ? [polygon] : [];
  }
  if (type === "MultiPolygon" && Array.isArray(coordinates)) {
    return coordinates
      .map(polygonFromCoordinates)
      .filter((polygon): polygon is LatLngExpression[][] => !!polygon);
  }
  if (type === "Feature") {
    return geometryPolygons(geometry.geometry);
  }
  if (type === "FeatureCollection" && Array.isArray(geometry.features)) {
    return geometry.features.flatMap((feature) => geometryPolygons(feature));
  }
  return [];
}

function scenePolygons(scene: SceneRow): LatLngExpression[][][] {
  return geometryPolygons(scene.footprint_geojson);
}

function ScenePopup({ scene, index }: { scene: SceneRow; index: number }) {
  return (
    <div className="min-w-[230px] max-w-[300px] text-xs">
      <div className="mb-2 flex items-start gap-2">
        <span className="mt-0.5 rounded-full bg-primary/10 px-2 py-0.5 font-mono text-[11px] text-primary">
          #{index + 1}
        </span>
        <div className="min-w-0">
          <div className="break-all font-mono text-[11px] font-semibold leading-4">
            {scene.scene_id}
          </div>
          <div className="mt-1 text-muted-foreground">
            {scene.product_type || "-"} · {scene.beam_mode || "-"} · {polarizationLabel(scene.polarization)}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
        <span className="text-muted-foreground">升降轨</span>
        <span className="text-right">{scene.orbit_direction || "-"}</span>
        <span className="text-muted-foreground">Path</span>
        <span className="text-right">{scene.path ?? scene.relative_orbit ?? "-"}</span>
        <span className="text-muted-foreground">Frame</span>
        <span className="text-right">{scene.frame ?? "-"}</span>
        <span className="text-muted-foreground">绝对轨道</span>
        <span className="text-right">{scene.absolute_orbit ?? "-"}</span>
        <span className="text-muted-foreground">时间</span>
        <span className="text-right">{scene.acquisition_datetime || "-"}</span>
        <span className="text-muted-foreground">大小</span>
        <span className="text-right">{fmtBytes(scene.file_size_remote)}</span>
        <span className="text-muted-foreground">下载 URL</span>
        <span className="text-right">{scene.has_url ? "已提供" : "未提供"}</span>
        {scene.footprint_bbox && (
          <>
            <span className="text-muted-foreground">影像框</span>
            <span className="text-right font-mono">
              W{fmt(scene.footprint_bbox.west)} S{fmt(scene.footprint_bbox.south)}
              <br />
              E{fmt(scene.footprint_bbox.east)} N{fmt(scene.footprint_bbox.north)}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

function FitToData({ bbox }: { bbox: Bbox }) {
  const map = useMap();

  useEffect(() => {
    map.fitBounds(boundsFromBbox(bbox), {
      animate: false,
      maxZoom: 12,
      padding: [36, 36],
    });
  }, [bbox.east, bbox.north, bbox.south, bbox.west, map]);

  return null;
}

function MapApiBridge({ onReady }: { onReady: (map: LeafletMap | null) => void }) {
  const map = useMap();

  useEffect(() => {
    onReady(map);
    return () => onReady(null);
  }, [map, onReady]);

  return null;
}

function MapToolButton({
  active,
  children,
  onClick,
  title,
}: {
  active?: boolean;
  children: ReactNode;
  onClick?: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onPointerDown={(event) => event.stopPropagation()}
      onPointerUp={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
      onMouseUp={(event) => event.stopPropagation()}
      onDoubleClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onClick?.();
      }}
      className={cn(
        "flex h-10 w-10 items-center justify-center border-b border-white/40 bg-white/56 text-foreground shadow-sm backdrop-blur-2xl transition-all last:border-b-0 hover:bg-white/76 active:scale-[0.98] dark:border-white/10 dark:bg-slate-950/48 dark:hover:bg-white/12",
        active && "bg-primary text-primary-foreground hover:bg-primary dark:bg-primary",
      )}
    >
      {children}
    </button>
  );
}

function MapToolbar({
  map,
  drawMode,
  drawActive,
  layersOpen,
  onDrawModeChange,
  onDrawActiveChange,
  onClearLayers,
  onToggleLayers,
}: {
  map: LeafletMap | null;
  drawMode: WorkbenchDrawMode;
  drawActive: boolean;
  layersOpen: boolean;
  onDrawModeChange: (mode: WorkbenchDrawMode) => void;
  onDrawActiveChange: (active: boolean) => void;
  onClearLayers: () => void;
  onToggleLayers: () => void;
}) {
  const toolbarRef = useRef<HTMLDivElement | null>(null);

  const activate = (mode: WorkbenchDrawMode) => {
    if (drawActive && drawMode === mode) {
      onDrawActiveChange(false);
      return;
    }
    onDrawModeChange(mode);
    onDrawActiveChange(true);
  };

  useEffect(() => {
    if (!toolbarRef.current) return;
    DomEvent.disableClickPropagation(toolbarRef.current);
    DomEvent.disableScrollPropagation(toolbarRef.current);
  }, []);

  return (
    <div
      ref={toolbarRef}
      className="pointer-events-auto absolute left-4 top-4 z-[760] flex flex-col gap-3"
      onPointerDown={(event) => event.stopPropagation()}
      onPointerUp={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
      onMouseUp={(event) => event.stopPropagation()}
      onMouseMove={(event) => event.stopPropagation()}
      onClick={(event) => event.stopPropagation()}
      onDoubleClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <div className="overflow-hidden rounded-2xl border border-white/55 bg-white/42 shadow-lg backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/38">
        <MapToolButton title="放大" onClick={() => map?.zoomIn()}>
          <Plus className="h-5 w-5" />
        </MapToolButton>
        <MapToolButton title="缩小" onClick={() => map?.zoomOut()}>
          <Minus className="h-5 w-5" />
        </MapToolButton>
      </div>
      <div className="overflow-hidden rounded-2xl border border-white/55 bg-white/42 shadow-lg backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/38">
        <MapToolButton
          title="绘制多边形"
          active={drawActive && drawMode === "polygon"}
          onClick={() => activate("polygon")}
        >
          <Pentagon className="h-4 w-4" />
        </MapToolButton>
        <MapToolButton
          title="框选矩形"
          active={drawActive && drawMode === "rect"}
          onClick={() => activate("rect")}
        >
          <Square className="h-4 w-4" />
        </MapToolButton>
      </div>
      <div className="overflow-hidden rounded-2xl border border-white/55 bg-white/42 shadow-lg backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/38">
        <MapToolButton title="清空地图图层" onClick={onClearLayers}>
          <Trash2 className="h-4 w-4" />
        </MapToolButton>
      </div>
      <div className="overflow-hidden rounded-2xl border border-white/55 bg-white/42 shadow-lg backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/38">
        <MapToolButton title="切换底图" active={layersOpen} onClick={onToggleLayers}>
          <Layers className="h-5 w-5" />
        </MapToolButton>
      </div>
    </div>
  );
}

function DrawLayer({
  mode,
  active,
  onRect,
  onPolygon,
  onPoint,
}: {
  mode: WorkbenchDrawMode;
  active: boolean;
  onRect: (bbox: Bbox) => void;
  onPolygon: (ring: [number, number][]) => void;
  onPoint: (lat: number, lng: number) => void;
}) {
  const map = useMap();
  const [start, setStart] = useState<LatLng | null>(null);
  const [current, setCurrent] = useState<LatLng | null>(null);
  const [sketch, setSketch] = useState<LatLng[]>([]);
  const [hover, setHover] = useState<LatLng | null>(null);
  const [lastPoint, setLastPoint] = useState<LatLng | null>(null);

  const appendUniquePoint = useCallback((points: LatLng[], point: LatLng) => {
    const last = points[points.length - 1];
    if (last && last.distanceTo(point) < 0.5) return points;
    return [...points, point];
  }, []);

  const finishPolygon = useCallback(
    (extra?: LatLng) => {
      const points = extra ? appendUniquePoint(sketch, extra) : sketch;
      if (points.length < 3) {
        setSketch([]);
        setHover(null);
        return;
      }
      const ring: [number, number][] = points.map((p) => [p.lng, p.lat]);
      const first = ring[0];
      const last = ring[ring.length - 1];
      if (first[0] !== last[0] || first[1] !== last[1]) ring.push(first);
      onPolygon(ring);
      setSketch([]);
      setHover(null);
    },
    [appendUniquePoint, onPolygon, sketch],
  );

  useEffect(() => {
    if (!active) return;
    const dragWasEnabled = map.dragging.enabled();
    const dblClickWasEnabled = map.doubleClickZoom.enabled();
    if (mode === "rect" || mode === "polygon") map.dragging.disable();
    if (mode === "polygon") map.doubleClickZoom.disable();
    return () => {
      if (dragWasEnabled) map.dragging.enable();
      else map.dragging.disable();
      if (dblClickWasEnabled) map.doubleClickZoom.enable();
      else map.doubleClickZoom.disable();
    };
  }, [active, map, mode]);

  useEffect(() => {
    setStart(null);
    setCurrent(null);
    setSketch([]);
    setHover(null);
  }, [mode]);

  useEffect(() => {
    if (!active || mode !== "polygon") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Enter") finishPolygon();
      if (event.key === "Escape") {
        setSketch([]);
        setHover(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active, finishPolygon, mode]);

  useMapEvents({
    mousedown(e) {
      if (!active || mode !== "rect") return;
      e.originalEvent.preventDefault();
      setStart(e.latlng);
      setCurrent(e.latlng);
    },
    mousemove(e) {
      if (!active) return;
      if (mode === "rect" && start) setCurrent(e.latlng);
      if (mode === "polygon" && sketch.length) setHover(e.latlng);
    },
    mouseup() {
      if (!active || mode !== "rect") return;
      if (start && current) {
        const south = Math.min(start.lat, current.lat);
        const north = Math.max(start.lat, current.lat);
        const west = Math.min(start.lng, current.lng);
        const east = Math.max(start.lng, current.lng);
        if (Math.abs(east - west) > 1e-5 && Math.abs(north - south) > 1e-5) {
          onRect({ west, east, south, north, crs: "EPSG:4326" });
        }
        setStart(null);
        setCurrent(null);
      }
    },
    click(e: LeafletMouseEvent) {
      if (!active) return;
      if (mode === "point") {
        setLastPoint(e.latlng);
        onPoint(e.latlng.lat, e.latlng.lng);
      }
      if (mode === "polygon") {
        setSketch((prev) => appendUniquePoint(prev, e.latlng));
        setHover(null);
      }
    },
    dblclick(e: LeafletMouseEvent) {
      if (!active || mode !== "polygon") return;
      e.originalEvent.preventDefault();
      finishPolygon(e.latlng);
    },
  });

  if (mode === "rect" && start && current) {
    const south = Math.min(start.lat, current.lat);
    const north = Math.max(start.lat, current.lat);
    const west = Math.min(start.lng, current.lng);
    const east = Math.max(start.lng, current.lng);
    return (
      <Rectangle
        bounds={[
          [south, west],
          [north, east],
        ]}
        pathOptions={{ color: "#22c55e", weight: 2, dashArray: "6 4", fillOpacity: 0.12 }}
      />
    );
  }

  const polygonPreview = hover ? [...sketch, hover] : sketch;
  return (
    <>
      {mode === "polygon" && polygonPreview.length > 1 && (
        <Polyline
          positions={polygonPreview.map((p) => [p.lat, p.lng])}
          pathOptions={{ color: "#22c55e", weight: 2.5 }}
        />
      )}
      {lastPoint && (
        <CircleMarker
          center={[lastPoint.lat, lastPoint.lng]}
          radius={6}
          pathOptions={{ color: "#22c55e", fillColor: "#22c55e", fillOpacity: 0.85 }}
        />
      )}
    </>
  );
}

function MapStatusOverlay() {
  const map = useMap();
  const [status, setStatus] = useState(() => {
    const center = map.getCenter();
    return { lat: center.lat, lng: center.lng, zoom: map.getZoom(), label: "中心" };
  });

  const updateFromCenter = useCallback(
    (label = "中心") => {
      const center = map.getCenter();
      setStatus({ lat: center.lat, lng: center.lng, zoom: map.getZoom(), label });
    },
    [map],
  );

  useEffect(() => {
    updateFromCenter();
  }, [updateFromCenter]);

  useMapEvents({
    mousemove(e) {
      setStatus({ lat: e.latlng.lat, lng: e.latlng.lng, zoom: map.getZoom(), label: "鼠标" });
    },
    mouseout() {
      updateFromCenter();
    },
    moveend() {
      updateFromCenter(status.label === "鼠标" ? "中心" : status.label);
    },
    zoomend() {
      updateFromCenter(status.label === "鼠标" ? "中心" : status.label);
    },
  });

  return (
    <div className="pointer-events-none absolute bottom-4 left-4 z-[520] rounded-2xl border border-white/55 bg-white/62 px-3 py-1.5 text-xs shadow-lg backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/62">
      <span className="text-muted-foreground">{status.label}</span>
      <span className="ml-2 font-mono">
        经度: {fmt(status.lng)}　纬度: {fmt(status.lat)}　|　缩放: {status.zoom}
      </span>
    </div>
  );
}

export function WorkbenchMap({
  bbox,
  aoiBbox,
  aoiGeometry,
  sceneBbox,
  scenes = [],
  selectedSceneId = null,
  layerKey,
  tiandituToken = "",
  drawMode,
  drawActive,
  onLayerChange,
  onDrawModeChange,
  onDrawActiveChange,
  onClearLayers,
  onRectDraw,
  onPolygonDraw,
  onPointDraw,
}: {
  bbox?: Bbox | null;
  aoiBbox?: Bbox | null;
  aoiGeometry?: Json | null;
  sceneBbox?: Bbox | null;
  scenes?: SceneRow[];
  selectedSceneId?: string | null;
  layerKey: MapLayerKey;
  tiandituToken?: string;
  drawMode: WorkbenchDrawMode;
  drawActive: boolean;
  onLayerChange: (key: MapLayerKey) => void;
  onDrawModeChange: (mode: WorkbenchDrawMode) => void;
  onDrawActiveChange: (active: boolean) => void;
  onClearLayers: () => void;
  onRectDraw: (bbox: Bbox) => void;
  onPolygonDraw: (ring: [number, number][]) => void;
  onPointDraw: (lat: number, lng: number) => void;
}) {
  const sceneUnion = useMemo(
    () => unionBbox(scenes.map((scene) => scene.footprint_bbox)),
    [scenes],
  );
  const selectedSceneBbox = useMemo(
    () => scenes.find((scene) => scene.scene_id === selectedSceneId)?.footprint_bbox ?? null,
    [scenes, selectedSceneId],
  );
  const fitBbox = useMemo(() => {
    if (isValidBbox(selectedSceneBbox)) return selectedSceneBbox;
    if (isValidBbox(bbox)) return bbox;
    if (isValidBbox(aoiBbox)) return aoiBbox;
    if (isValidBbox(sceneBbox)) return sceneBbox;
    if (isValidBbox(sceneUnion)) return sceneUnion;
    return DEFAULT_BBOX;
  }, [aoiBbox, bbox, sceneBbox, sceneUnion, selectedSceneBbox]);
  const [tilesReady, setTilesReady] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [mapApi, setMapApi] = useState<LeafletMap | null>(null);
  const layerBackdropRef = useRef<HTMLDivElement | null>(null);
  const layerPanelRef = useRef<HTMLDivElement | null>(null);
  const visibleScenes = useMemo(
    () => scenes.filter((scene) => isValidBbox(scene.footprint_bbox)).slice(0, 300),
    [scenes],
  );
  const orderedSceneEntries = useMemo(() => {
    const entries = visibleScenes.map((scene, index) => ({ scene, index }));
    if (!selectedSceneId) return entries;
    return [
      ...entries.filter((entry) => entry.scene.scene_id !== selectedSceneId),
      ...entries.filter((entry) => entry.scene.scene_id === selectedSceneId),
    ];
  }, [selectedSceneId, visibleScenes]);
  const aoiPolygons = useMemo(() => geometryPolygons(aoiGeometry), [aoiGeometry]);
  const footprintCount = visibleScenes.length;
  const token = tiandituToken.trim();
  const layer = MAP_LAYERS[layerKey].requiresToken && !token ? MAP_LAYERS.cartoLight : MAP_LAYERS[layerKey];
  const layerUrl = layer.url.replace("{token}", encodeURIComponent(token));

  useEffect(() => setTilesReady(false), [layerKey]);

  useEffect(() => {
    if (!layersOpen) return;
    for (const element of [layerBackdropRef.current, layerPanelRef.current]) {
      if (!element) continue;
      DomEvent.disableClickPropagation(element);
      DomEvent.disableScrollPropagation(element);
    }
  }, [layersOpen]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#d9e6e2]">
      <MapContainer
        center={centerFromBbox(fitBbox)}
        zoom={10}
        scrollWheelZoom
        zoomControl={false}
        className={cn("h-full w-full", drawActive && "cursor-crosshair")}
      >
        <TileLayer
          key={`${layerKey}:${token ? "token" : "none"}`}
          url={layerUrl}
          subdomains={layer.subdomains ?? "abc"}
          attribution={layer.attribution}
          maxNativeZoom={layer.maxZoom}
          updateWhenIdle
          updateWhenZooming={false}
          keepBuffer={1}
          detectRetina={false}
          eventHandlers={{ load: () => setTilesReady(true) }}
        />
        <MapApiBridge onReady={setMapApi} />
        <FitToData bbox={fitBbox} />
        {isValidBbox(sceneBbox) && (
          <Rectangle
            bounds={boundsFromBbox(sceneBbox)}
            pathOptions={{ color: "#f59e0b", weight: 2, dashArray: "8 5", fillOpacity: 0.08 }}
            interactive={false}
          />
        )}
        {aoiPolygons.length > 0
          ? aoiPolygons.map((positions, index) => (
              <Polygon
                key={`aoi:${index}`}
                positions={positions}
                pathOptions={{ color: "#0f766e", weight: 3, fillColor: "#14b8a6", fillOpacity: 0.18 }}
                interactive={false}
              />
            ))
          : isValidBbox(aoiBbox) && (
              <Rectangle
                bounds={boundsFromBbox(aoiBbox)}
                pathOptions={{ color: "#0f766e", weight: 2.5, fillOpacity: 0.16 }}
                interactive={false}
              />
            )}
        {orderedSceneEntries.map(({ scene, index }) => {
          const polygons = scenePolygons(scene);
          const selected = scene.scene_id === selectedSceneId;
          const options = {
            color: selected ? "#ff2d55" : index % 2 ? "#2563eb" : "#f97316",
            weight: selected ? 4.8 : 1.8,
            opacity: selected ? 1 : 0.78,
            fillColor: selected ? "#ff2d55" : index % 2 ? "#2563eb" : "#f97316",
            fillOpacity: selected ? 0.24 : 0.12,
          };
          const haloOptions = {
            color: "#ffffff",
            weight: 9,
            opacity: 0.92,
            fillOpacity: 0,
          };
          if (polygons.length) {
            return polygons.map((positions, part) => (
              <Fragment key={`${scene.scene_id}:poly:${part}`}>
                {selected && <Polygon positions={positions} pathOptions={haloOptions} interactive={false} />}
                <Polygon
                  positions={positions}
                  pathOptions={options}
                  interactive={!drawActive}
                >
                  <Popup>
                    <ScenePopup scene={scene} index={index} />
                  </Popup>
                </Polygon>
              </Fragment>
            ));
          }
          return (
            <Fragment key={`${scene.scene_id}:bbox`}>
              {selected && (
                <Rectangle
                  bounds={boundsFromBbox(scene.footprint_bbox!)}
                  pathOptions={haloOptions}
                  interactive={false}
                />
              )}
              <Rectangle
                bounds={boundsFromBbox(scene.footprint_bbox!)}
                pathOptions={options}
                interactive={!drawActive}
              >
                <Popup>
                  <ScenePopup scene={scene} index={index} />
                </Popup>
              </Rectangle>
            </Fragment>
          );
        })}
        <DrawLayer
          mode={drawMode}
          active={drawActive}
          onRect={onRectDraw}
          onPolygon={onPolygonDraw}
          onPoint={onPointDraw}
        />
        <MapStatusOverlay />
      </MapContainer>

      <MapToolbar
        map={mapApi}
        drawMode={drawMode}
        drawActive={drawActive}
        layersOpen={layersOpen}
        onDrawModeChange={onDrawModeChange}
        onDrawActiveChange={onDrawActiveChange}
        onClearLayers={onClearLayers}
        onToggleLayers={() => setLayersOpen((value) => !value)}
      />

      <div className="pointer-events-none absolute bottom-14 left-4 z-[500] max-w-[460px] rounded-2xl border border-white/55 bg-white/62 px-3 py-2 text-xs shadow-lg backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/62">
        <div className="flex items-center gap-2 font-medium">
          <MapPinned className="h-3.5 w-3.5 text-primary" />
          {drawActive ? "正在绘制 AOI" : "地图工作区"}
        </div>
        <div className="mt-1 font-mono text-[11px] text-muted-foreground">
          W{fmt(fitBbox.west)} S{fmt(fitBbox.south)} E{fmt(fitBbox.east)} N{fmt(fitBbox.north)}
        </div>
        {footprintCount > 0 && (
          <div className="mt-1 text-[11px] text-muted-foreground">
            已显示 {footprintCount} 个 SAR 影像范围，点击范围或左侧列表可查看/定位
          </div>
        )}
      </div>

      {layersOpen && (
        <div
          ref={layerBackdropRef}
          className="pointer-events-auto absolute inset-0 z-[640]"
          style={{ zIndex: 640 }}
          onPointerDown={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setLayersOpen(false);
          }}
          onPointerUp={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
          onMouseUp={(event) => event.stopPropagation()}
          onMouseMove={(event) => event.stopPropagation()}
          onWheel={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
          onDoubleClick={(event) => event.stopPropagation()}
          onContextMenu={(event) => event.stopPropagation()}
        />
      )}

      {layersOpen && (
        <div
          ref={layerPanelRef}
          className="pointer-events-auto absolute left-16 top-4 z-[790] max-h-[calc(100%-2rem)] w-[290px] overflow-y-auto rounded-[24px] border border-white/60 bg-white/74 p-2 shadow-2xl backdrop-blur-3xl dark:border-white/10 dark:bg-slate-950/78"
          style={{ zIndex: 790 }}
          onPointerDown={(event) => event.stopPropagation()}
          onPointerUp={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
          onMouseUp={(event) => event.stopPropagation()}
          onMouseMove={(event) => event.stopPropagation()}
          onWheel={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
          onDoubleClick={(event) => event.stopPropagation()}
          onContextMenu={(event) => event.stopPropagation()}
        >
          <div className="flex items-center gap-2 px-1.5 pb-2 text-xs font-semibold">
            <Layers className="h-3.5 w-3.5 text-primary" />
            多图层底图
          </div>
          <div className="space-y-1">
            {(Object.keys(MAP_LAYERS) as MapLayerKey[]).map((key) => {
              const item = MAP_LAYERS[key];
              const active = key === layerKey;
              const locked = !!item.requiresToken && !token;
              return (
                <button
                  key={key}
                  type="button"
                  disabled={locked}
                  onPointerDown={(event) => event.stopPropagation()}
                  onPointerUp={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    if (locked) return;
                    if (active) {
                      setLayersOpen(false);
                      return;
                    }
                    window.requestAnimationFrame(() => onLayerChange(key));
                  }}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-xs transition-colors disabled:cursor-default",
                    active ? "bg-foreground text-background" : "hover:bg-accent",
                    locked && "opacity-50",
                  )}
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                      active ? "border-background" : "border-muted-foreground/50",
                    )}
                  >
                    {active && <Check className="h-3 w-3" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{item.label}</span>
                    <span
                      className={cn(
                        "block truncate text-[11px]",
                        active ? "text-background/80" : "text-muted-foreground",
                      )}
                    >
                      {item.category} · {locked ? "设置 Token 后启用" : item.desc}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {!tilesReady && (
        <div className="pointer-events-none absolute bottom-16 left-4 z-[500] rounded-2xl border border-white/55 bg-white/62 px-3 py-2 text-xs shadow-lg backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/62">
          <div className="flex items-center gap-2">
            <LocateFixed className="h-3.5 w-3.5 animate-pulse text-primary" />
            底图加载中，AOI 坐标输入和任务控制仍可使用
          </div>
        </div>
      )}

    </div>
  );
}
