import { useEffect } from "react";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Rectangle,
  TileLayer,
  Tooltip,
  useMap,
  ZoomControl,
} from "react-leaflet";
import type { Bbox } from "@/lib/bridge";

const DEFAULT_BBOX: Bbox = {
  west: 110.22,
  east: 110.52,
  south: 30.92,
  north: 31.14,
};

function fmt(v: number): string {
  return v.toFixed(2);
}

function FitBounds({ bounds }: { bounds: LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [28, 28], maxZoom: 11 });
  }, [bounds, map]);
  return null;
}

export function MapCard({
  bbox = DEFAULT_BBOX,
  overlayBbox,
  label = "处理 AOI · 石榴树包",
  overlayLabel = "场景覆盖",
  minHeight = 460,
}: {
  bbox?: Bbox;
  overlayBbox?: Bbox | null;
  label?: string;
  overlayLabel?: string;
  minHeight?: number;
}) {
  const fitBbox = overlayBbox
    ? {
        west: Math.min(bbox.west, overlayBbox.west),
        east: Math.max(bbox.east, overlayBbox.east),
        south: Math.min(bbox.south, overlayBbox.south),
        north: Math.max(bbox.north, overlayBbox.north),
      }
    : bbox;
  const bounds: LatLngBoundsExpression = [
    [bbox.south, bbox.west],
    [bbox.north, bbox.east],
  ];
  const fitBounds: LatLngBoundsExpression = [
    [fitBbox.south, fitBbox.west],
    [fitBbox.north, fitBbox.east],
  ];
  const overlayBounds: LatLngBoundsExpression | null = overlayBbox
    ? [
        [overlayBbox.south, overlayBbox.west],
        [overlayBbox.north, overlayBbox.east],
      ]
    : null;
  const center: LatLngExpression = [
    (fitBbox.south + fitBbox.north) / 2,
    (fitBbox.west + fitBbox.east) / 2,
  ];
  // Remount when the bbox changes so the (initial-only) center/zoom re-fit.
  const key = `${fitBbox.west},${fitBbox.south},${fitBbox.east},${fitBbox.north}`;

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border">
      <MapContainer
        key={key}
        center={center}
        zoom={10}
        scrollWheelZoom={false}
        zoomControl={false}
        className="h-full w-full"
        style={{ minHeight }}
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap"
        />
        <ZoomControl position="topright" />
        <FitBounds bounds={fitBounds} />
        <Rectangle
          bounds={bounds}
          pathOptions={{ color: "#0d9488", weight: 2.5, fillOpacity: 0.14 }}
        />
        {overlayBounds && (
          <Rectangle
            bounds={overlayBounds}
            pathOptions={{ color: "#2563eb", weight: 2, dashArray: "7 5", fillOpacity: 0.08 }}
          >
            <Tooltip>{overlayLabel}</Tooltip>
          </Rectangle>
        )}
        <CircleMarker
          center={center}
          radius={6}
          pathOptions={{
            color: "#0d9488",
            fillColor: "#0d9488",
            fillOpacity: 0.9,
            weight: 2,
          }}
        >
          <Tooltip>区域中心</Tooltip>
        </CircleMarker>
      </MapContainer>

      <div className="pointer-events-none absolute left-3 top-3 z-[500] rounded-md border border-border/60 bg-card/90 px-3 py-2 text-xs shadow-sm backdrop-blur">
        <div className="font-medium text-foreground">{label}</div>
        <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
          W{fmt(bbox.west)} · S{fmt(bbox.south)} · E{fmt(bbox.east)} · N
          {fmt(bbox.north)}
        </div>
      </div>
    </div>
  );
}
