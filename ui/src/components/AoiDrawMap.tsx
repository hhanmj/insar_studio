import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  LatLng,
  LatLngBoundsExpression,
  LatLngExpression,
  LeafletMouseEvent,
} from "leaflet";
import {
  MapContainer,
  Polyline,
  Rectangle,
  TileLayer,
  useMap,
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

function FitToBbox({ bbox }: { bbox: Bbox }) {
  const map = useMap();

  useEffect(() => {
    map.fitBounds(boundsFromBbox(bbox), {
      animate: false,
      maxZoom: 12,
      padding: [24, 24],
    });
  }, [bbox.east, bbox.north, bbox.south, bbox.west, map]);

  return null;
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
  const map = useMap();
  const [start, setStart] = useState<LatLng | null>(null);
  const [current, setCurrent] = useState<LatLng | null>(null);
  const [sketch, setSketch] = useState<LatLng[]>([]);
  const [hover, setHover] = useState<LatLng | null>(null);

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
      if (mode === "rect") {
        setStart(e.latlng);
        setCurrent(e.latlng);
      }
    },
    mousemove(e) {
      if (!active) return;
      if (mode === "rect" && start) setCurrent(e.latlng);
      if (mode === "polygon" && sketch.length) setHover(e.latlng);
    },
    mouseup() {
      if (!active || mode !== "rect") return;
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
      }
    },
    click(e: LeafletMouseEvent) {
      if (!active) return;
      if (mode === "point") {
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
        pathOptions={{ color: "#2563eb", weight: 2, dashArray: "6 4", fillOpacity: 0.12 }}
      />
    );
  }

  const polygonPreview = hover ? [...sketch, hover] : sketch;
  if (mode === "polygon" && polygonPreview.length > 1) {
    return (
      <Polyline
        positions={polygonPreview.map((p) => [p.lat, p.lng])}
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
  const [tilesReady, setTilesReady] = useState(false);

  const modeHint = useMemo(() => {
    if (mode === "rect") return "拖拽绘制矩形";
    if (mode === "polygon") return "点击加点，双击完成";
    return "单击设置中心点";
  }, [mode]);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border bg-[linear-gradient(0deg,rgba(13,148,136,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(13,148,136,0.08)_1px,transparent_1px)] bg-[size:32px_32px]">
      <MapContainer
        center={center}
        zoom={10}
        scrollWheelZoom
        zoomControl={false}
        preferCanvas
        className={"h-full w-full " + (drawActive ? "cursor-crosshair" : "")}
        style={{ minHeight, background: "transparent" }}
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OSM"
          updateWhenIdle
          keepBuffer={4}
          eventHandlers={{
            load: () => setTilesReady(true),
          }}
        />
        <FitToBbox bbox={display} />
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
      {!tilesReady && (
        <div className="pointer-events-none absolute bottom-3 left-3 z-[500] rounded-md border border-border/60 bg-card/90 px-3 py-2 text-[11px] text-muted-foreground shadow-sm backdrop-blur">
          底图加载中；绘制和 bbox 输入可直接使用
        </div>
      )}
    </div>
  );
}
