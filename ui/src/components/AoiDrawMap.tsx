import { useMemo, useState } from "react";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";
import {
  MapContainer,
  Polyline,
  Rectangle,
  TileLayer,
  useMapEvents,
  ZoomControl,
} from "react-leaflet";
import type { Bbox } from "@/lib/bridge";

export type DrawMode = "rect" | "polygon" | "point";

const DEFAULT_BBOX: Bbox = {
  west: 110.22,
  east: 110.52,
  south: 30.92,
  north: 31.14,
  crs: "EPSG:4326",
};

function fmt(v: number): string {
  return v.toFixed(4);
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

function DrawLayer({
  mode,
  active,
  onRect,
  onPolygon,
  onPoint,
}: {
  mode: DrawMode;
  active: boolean;
  onRect: (bbox: Bbox) => void;
  onPolygon: (ring: [number, number][]) => void;
  onPoint: (lat: number, lng: number) => void;
}) {
  const [start, setStart] = useState<L.LatLng | null>(null);
  const [current, setCurrent] = useState<L.LatLng | null>(null);
  const [sketch, setSketch] = useState<L.LatLng[]>([]);

  useMapEvents({
    mousedown(e) {
      if (!active) return;
      if (mode === "rect") {
        setStart(e.latlng);
        setCurrent(e.latlng);
      } else if (mode === "point") {
        onPoint(e.latlng.lat, e.latlng.lng);
      } else {
        setSketch([e.latlng]);
      }
    },
    mousemove(e) {
      if (!active) return;
      if (mode === "rect" && start) setCurrent(e.latlng);
      if (mode === "polygon" && sketch.length) {
        const last = sketch[sketch.length - 1];
        if (last.distanceTo(e.latlng) > 25) {
          setSketch((prev) => [...prev, e.latlng]);
        }
      }
    },
    mouseup() {
      if (!active) return;
      if (mode === "rect" && start && current) {
        const south = Math.min(start.lat, current.lat);
        const north = Math.max(start.lat, current.lat);
        const west = Math.min(start.lng, current.lng);
        const east = Math.max(start.lng, current.lng);
        if (Math.abs(east - west) > 1e-5 && Math.abs(north - south) > 1e-5) {
          onRect({ west, east, south, north, crs: "EPSG:4326" });
        }
        setStart(null);
        setCurrent(null);
      } else if (mode === "polygon" && sketch.length >= 3) {
        const ring: [number, number][] = sketch.map((p) => [p.lng, p.lat]);
        if (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1]) {
          ring.push(ring[0]);
        }
        onPolygon(ring);
        setSketch([]);
      } else if (mode === "polygon") {
        setSketch([]);
      }
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
        pathOptions={{ color: "#2563eb", weight: 2, dashArray: "6 4", fillOpacity: 0.12 }}
      />
    );
  }

  if (mode === "polygon" && sketch.length > 1) {
    return (
      <Polyline
        positions={sketch.map((p) => [p.lat, p.lng])}
        pathOptions={{ color: "#2563eb", weight: 2.5 }}
      />
    );
  }

  return null;
}

export function AoiDrawMap({
  bbox = DEFAULT_BBOX,
  boundBbox,
  mode = "rect",
  drawActive = true,
  minHeight = 520,
  onRectDraw,
  onPolygonDraw,
  onPointDraw,
}: {
  bbox?: Bbox;
  boundBbox?: Bbox | null;
  mode?: DrawMode;
  drawActive?: boolean;
  minHeight?: number;
  onRectDraw?: (bbox: Bbox) => void;
  onPolygonDraw?: (ring: [number, number][]) => void;
  onPointDraw?: (lat: number, lng: number) => void;
}) {
  const display = boundBbox ?? bbox;
  const center = centerFromBbox(display);
  const key = `${display.west},${display.south},${display.east},${display.north}`;

  const modeHint = useMemo(() => {
    if (mode === "rect") return "拖拽绘制矩形";
    if (mode === "polygon") return "按住拖动绘制多边形（画笔）";
    return "单击设置中心点（自动生成小范围 bbox）";
  }, [mode]);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border">
      <MapContainer
        key={key}
        center={center}
        zoom={10}
        scrollWheelZoom
        zoomControl={false}
        className="h-full w-full cursor-crosshair"
        style={{ minHeight }}
      >
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OSM" />
        <ZoomControl position="topright" />
        {boundBbox && (
          <Rectangle
            bounds={boundsFromBbox(boundBbox)}
            pathOptions={{ color: "#0d9488", weight: 2.5, fillOpacity: 0.14 }}
          />
        )}
        <DrawLayer
          mode={mode}
          active={drawActive}
          onRect={(b) => onRectDraw?.(b)}
          onPolygon={(ring) => onPolygonDraw?.(ring)}
          onPoint={(lat, lng) => onPointDraw?.(lat, lng)}
        />
      </MapContainer>

      <div className="pointer-events-none absolute left-3 top-3 z-[500] rounded-md border border-border/60 bg-card/90 px-3 py-2 text-xs shadow-sm backdrop-blur">
        <div className="font-medium text-foreground">AOI 地图 · {modeHint}</div>
        <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
          W{fmt(display.west)} · S{fmt(display.south)} · E{fmt(display.east)} · N
          {fmt(display.north)}
        </div>
      </div>
    </div>
  );
}
