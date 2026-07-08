import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type MouseEvent, type UIEvent, type WheelEvent } from "react";
import {
  Activity,
  AlertCircle,
  BookOpen,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  ClipboardPaste,
  CloudDownload,
  Database,
  Eye,
  EyeOff,
  ExternalLink,
  FileText,
  FileUp,
  FolderOpen,
  HardDrive,
  Info,
  KeyRound,
  Loader2,
  Mail,
  MapPinned,
  Maximize2,
  MessageCircle,
  Minus,
  Moon,
  Mountain,
  Orbit,
  Pause,
  Play,
  Radar,
  RotateCcw,
  Save,
  Satellite,
  Search,
  Settings,
  Square,
  Star,
  Sun,
  Trash2,
  UserRound,
  Wifi,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  WorkbenchMap,
  type MapLayerKey,
  type WorkbenchDrawMode,
} from "@/components/WorkbenchMap";
import { OnboardingTour, type TourStep } from "@/components/OnboardingTour";
import {
  appendAsfDownloadSnapshot,
  cancelAsfSearch,
  checkEarthdataAuth,
  checkScenes,
  closeNativeWindow,
  clearMapLayers,
  clearOrbitCandidateScenes,
  clearScenes,
  clearEarthdataCredentials,
  clearGacosEmail,
  clearOpentopographyKey,
  deleteDownloadArchiveItem,
  downloadAppUpdate,
  formatBridgeError,
  getComponentStatus,
  getCredentialStatus,
  getDownloadArchive,
  getDownloadStatus,
  getDemDownloadStatus,
  getNativeWindowSize,
  hasBridge,
  checkForUpdate,
  getMetadataStatus,
  getAdminOptions,
  getAppInfo,
  getNetworkSettings,
  getOrbitDownloadStatus,
  getTree,
  getUiFlags,
  importScenesDirectory,
  importScenesFile,
  importScenesText,
  installComponent,
  listScenes,
  minimizeNativeWindow,
  openExternalUrl,
  openPath,
  pauseAsfDownload,
  pauseAsfScenes,
  pauseOrbitDownload,
  pickDirectory,
  pickOpenFile,
  planGacosRequest,
  planLocalDemConversion,
  previewScenesDirectory,
  previewScenesFile,
  previewAoiFile,
  previewAoiFileBytes,
  previewAoiFileContent,
  retryAsfDownload,
  resumeAsfDownload,
  resumeAsfScenes,
  resumeOrbitDownload,
  startDemDownload,
  startDemDownloadBbox,
  stopDemDownload,
  runLocalDemConversion,
  saveEarthdataLogin,
  saveEarthdataToken,
  saveGacosEmail,
  saveDownloadArchive,
  saveNetworkSettings,
  saveOpentopographyKey,
  setUiFlag,
  resizeNativeWindowFromEdge,
  removeComponent,
  setDemDataset,
  setRegionAoiBbox,
  setRegionAoiFile,
  setRegionAoiFileFeatures,
  setRegionAoiGeojson,
  setRegionAoiGeojsonFeatures,
  searchAdminBoundaries,
  searchAsfScenes,
  startAsfDownload,
  startAsfDownloadSnapshot,
  startOrbitDownloadSnapshot,
  startOrbitDownload,
  stopAsfDownload,
  stopOrbitDownload,
  toggleNativeWindowMaximize,
  type Bbox,
  type AoiFeaturePreview,
  type AoiPreviewOk,
  type AdminBoundary,
  type AppInfo,
  type CheckOk,
  type ComponentSummary,
  type ComponentStatusOk,
  type Context,
  type ConversionAuto,
  type CredentialStatus,
  type DownloadArchiveItem,
  type DownloadStatus,
  type DemDownloadStatus,
  type EarthdataAuthCheck,
  type Json,
  type NetworkSettings,
  type MetadataStatus,
  type OrbitDownloadStatus,
  type RunSummaryOk,
  type SceneRow,
  type SimpleOk,
  type UpdateInfo,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";
import { cn } from "@/lib/utils";

type SourceMode =
  | "sentinel1"
  | "dem"
  | "orbit"
  | "gacos"
  | "sentinel2"
  | "landsat"
  | "hls";
type PanelTab = "resources" | "downloads" | "settings";
type PendingSceneDownloadTask = {
  id: string;
  name: string;
  title: string;
  aoiName?: string;
  sceneIds: string[];
  snapshot: SceneRow[];
  outputDir: string;
  concurrency: number;
  useProductSubdir: boolean;
  createdAt: number;
  status: "pending" | "starting" | "failed";
  error?: string | null;
};

type SceneTaskSnapshot = {
  title: string;
  aoiName: string;
  outputDir: string;
  scenes: SceneRow[];
};

const DOWNLOAD_ARCHIVE_KEY = "insar.downloadArchive.v1";
const LOCAL_BOUNDARY_EXTENSIONS = new Set([".shp", ".kml", ".kmz", ".geojson", ".json"]);
const TEXT_BOUNDARY_EXTENSIONS = new Set([".kml", ".geojson", ".json"]);
const BINARY_BOUNDARY_EXTENSIONS = new Set([".shp", ".kmz"]);
const MAX_DRAGGED_BINARY_BOUNDARY_BYTES = 50 * 1024 * 1024;

type AoiPreviewSource =
  | { kind: "path"; path: string }
  | { kind: "geojson"; fileName: string; geojson: Json };

function stopWindowDrag(event: { stopPropagation: () => void }) {
  event.stopPropagation();
}

type NativeResizeEdge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

const NATIVE_RESIZE_HANDLES: { edge: NativeResizeEdge; className: string }[] = [
  { edge: "n", className: "left-3 right-3 top-0 h-1.5 cursor-n-resize" },
  { edge: "s", className: "bottom-0 left-3 right-3 h-1.5 cursor-s-resize" },
  { edge: "w", className: "bottom-3 left-0 top-3 w-1.5 cursor-w-resize" },
  { edge: "e", className: "bottom-3 right-0 top-3 w-1.5 cursor-e-resize" },
  { edge: "nw", className: "left-0 top-0 h-3 w-3 cursor-nw-resize" },
  { edge: "ne", className: "right-0 top-0 h-3 w-3 cursor-ne-resize" },
  { edge: "sw", className: "bottom-0 left-0 h-3 w-3 cursor-sw-resize" },
  { edge: "se", className: "bottom-0 right-0 h-3 w-3 cursor-se-resize" },
];

function NativeResizeHandles() {
  const frame = useRef<number | null>(null);
  const last = useRef<{
    edge: NativeResizeEdge;
    startWidth: number;
    startHeight: number;
    startX: number;
    startY: number;
    x: number;
    y: number;
  } | null>(null);

  useEffect(() => {
    return () => {
      if (frame.current !== null) window.cancelAnimationFrame(frame.current);
    };
  }, []);

  function scheduleResize() {
    if (frame.current !== null) return;
    frame.current = window.requestAnimationFrame(() => {
      frame.current = null;
      const item = last.current;
      if (!item) return;
      void resizeNativeWindowFromEdge(
        item.edge,
        item.startWidth,
        item.startHeight,
        item.x - item.startX,
        item.y - item.startY,
      );
    });
  }

  async function beginResize(edge: NativeResizeEdge, event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const size = await getNativeWindowSize();
    if (!size.ok) return;
    last.current = {
      edge,
      startWidth: size.width,
      startHeight: size.height,
      startX: event.screenX,
      startY: event.screenY,
      x: event.screenX,
      y: event.screenY,
    };

    const onMove = (moveEvent: PointerEvent) => {
      if (!last.current) return;
      moveEvent.preventDefault();
      last.current = { ...last.current, x: moveEvent.screenX, y: moveEvent.screenY };
      scheduleResize();
    };
    const onUp = () => {
      last.current = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  return (
    <>
      {NATIVE_RESIZE_HANDLES.map((handle) => (
        <div
          key={handle.edge}
          className={cn("absolute z-[1800] bg-transparent", handle.className)}
          onPointerDown={(event) => void beginResize(handle.edge, event)}
        />
      ))}
    </>
  );
}

const DEM_DATASET_GROUPS: {
  label: string;
  options: { value: string; label: string; enabled: boolean; hint?: string }[];
}[] = [
  {
    label: "OpenTopography 已接入：可下载",
    options: [
      { value: "SRTM_GL3", label: "SRTM 90m", enabled: true, hint: "EGM96 正高" },
      { value: "SRTM_GL1", label: "SRTM 30m", enabled: true, hint: "EGM96 正高" },
      {
        value: "SRTM_GL1_ELLIPSOIDAL",
        label: "SRTM GL1 Ellipsoidal 30m",
        enabled: true,
        hint: "WGS84 椭球高，无需高程转换",
      },
      {
        value: "AW3D30_ELLIPSOIDAL",
        label: "ALOS World 3D Ellipsoidal 30m",
        enabled: true,
        hint: "WGS84 椭球高，无需高程转换",
      },
      { value: "COP90", label: "Copernicus Global DSM 90m", enabled: true, hint: "EGM2008 正高" },
      { value: "COP30", label: "Copernicus Global DSM 30m", enabled: true, hint: "EGM2008 正高" },
    ],
  },
];

const DEM_SOURCE_STEMS: Record<string, string> = {
  SRTM_GL3: "SRTM90m",
  SRTM_GL1: "SRTM30m",
  SRTM_GL1_ELLIPSOIDAL: "SRTM30m",
  AW3D30: "AW3D30m",
  AW3D30_ELLIPSOIDAL: "AW3D30m",
  COP90: "COP90m",
  COP30: "COP30m",
  NASADEM: "NASADEM",
};

const DOWNLOADABLE_DEM_DATASETS = new Set(
  DEM_DATASET_GROUPS.flatMap((group) =>
    group.options.filter((item) => item.enabled).map((item) => item.value),
  ),
);

function demSourceStem(value: string) {
  const fallback = value.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return DEM_SOURCE_STEMS[value.toUpperCase()] ?? (fallback || "DEM");
}

function demDatasetLabel(value: string) {
  for (const group of DEM_DATASET_GROUPS) {
    const found = group.options.find((item) => item.value === value);
    if (found) return found.hint ? `${found.label} · ${found.hint}` : found.label;
  }
  return value;
}

const DEFAULT_BBOX: Bbox = {
  west: 73.5,
  east: 135.1,
  south: 18.0,
  north: 53.6,
  crs: "EPSG:4326",
};
const CHINA_BBOX: Bbox = DEFAULT_BBOX;

const CHINA_PROVINCES = [
  "全部",
  "北京市",
  "天津市",
  "河北省",
  "山西省",
  "内蒙古自治区",
  "辽宁省",
  "吉林省",
  "黑龙江省",
  "上海市",
  "江苏省",
  "浙江省",
  "安徽省",
  "福建省",
  "江西省",
  "山东省",
  "河南省",
  "湖北省",
  "湖南省",
  "广东省",
  "广西壮族自治区",
  "海南省",
  "重庆市",
  "四川省",
  "贵州省",
  "云南省",
  "西藏自治区",
  "陕西省",
  "甘肃省",
  "青海省",
  "宁夏回族自治区",
  "新疆维吾尔自治区",
  "台湾省",
  "香港特别行政区",
  "澳门特别行政区",
];

const ADMIN_PRESETS: Record<string, { cities: string[]; districts: Record<string, string[]> }> = {
  湖北省: {
    cities: [
      "武汉市",
      "黄石市",
      "十堰市",
      "宜昌市",
      "襄阳市",
      "鄂州市",
      "荆门市",
      "孝感市",
      "荆州市",
      "黄冈市",
      "咸宁市",
      "随州市",
      "恩施土家族苗族自治州",
      "仙桃市",
      "潜江市",
      "天门市",
      "神农架林区",
    ],
    districts: {
      恩施土家族苗族自治州: ["恩施市", "利川市", "建始县", "巴东县", "宣恩县", "咸丰县", "来凤县", "鹤峰县"],
      宜昌市: ["西陵区", "伍家岗区", "点军区", "猇亭区", "夷陵区", "远安县", "兴山县", "秭归县", "长阳土家族自治县", "五峰土家族自治县", "宜都市", "当阳市", "枝江市"],
      武汉市: ["江岸区", "江汉区", "硚口区", "汉阳区", "武昌区", "青山区", "洪山区", "东西湖区", "汉南区", "蔡甸区", "江夏区", "黄陂区", "新洲区"],
    },
  },
  重庆市: {
    cities: ["重庆市"],
    districts: {
      重庆市: ["万州区", "涪陵区", "渝中区", "大渡口区", "江北区", "沙坪坝区", "九龙坡区", "南岸区", "北碚区", "綦江区", "大足区", "渝北区", "巴南区", "黔江区", "长寿区", "江津区", "合川区", "永川区", "南川区", "璧山区", "铜梁区", "潼南区", "荣昌区", "开州区", "梁平区", "武隆区"],
    },
  },
  四川省: {
    cities: ["成都市", "自贡市", "攀枝花市", "泸州市", "德阳市", "绵阳市", "广元市", "遂宁市", "内江市", "乐山市", "南充市", "眉山市", "宜宾市", "广安市", "达州市", "雅安市", "巴中市", "资阳市", "阿坝藏族羌族自治州", "甘孜藏族自治州", "凉山彝族自治州"],
    districts: {},
  },
};

const SOURCE_TABS: {
  key: SourceMode;
  label: string;
  hint: string;
  icon: typeof Satellite;
  disabled?: boolean;
}[] = [
  { key: "sentinel1", label: "Sentinel-1", hint: "SLC / GRD", icon: Satellite },
  { key: "orbit", label: "Orbit", hint: "POEORB", icon: Orbit },
  { key: "dem", label: "DEM", hint: "下载 + 转换", icon: Mountain },
  { key: "gacos", label: "GACOS", hint: "暂停", icon: Database, disabled: true },
  { key: "sentinel2", label: "Sentinel-2", hint: "预留", icon: Radar, disabled: true },
  { key: "landsat", label: "Landsat", hint: "预留", icon: Satellite, disabled: true },
  { key: "hls", label: "HLS", hint: "预留", icon: Satellite, disabled: true },
];

const PANEL_TABS: { key: PanelTab; label: string; icon: typeof CloudDownload }[] = [
  { key: "resources", label: "资源下载", icon: CloudDownload },
  { key: "downloads", label: "下载中心", icon: Activity },
  { key: "settings", label: "设置", icon: Settings },
];

const ASF_ORBIT_OPTIONS = [
  { value: "ASCENDING", label: "升轨" },
  { value: "DESCENDING", label: "降轨" },
];

const ASF_BEAM_OPTIONS = [
  { value: "IW", label: "IW" },
  { value: "EW", label: "EW" },
  { value: "SM", label: "SM" },
  { value: "WV", label: "WV" },
];

const ASF_POLARIZATION_OPTIONS = [
  { value: "DV", label: "DV（VV+VH）" },
  { value: "DH", label: "DH（HH+HV）" },
  { value: "SV", label: "SV（VV）" },
  { value: "SH", label: "SH（HH）" },
];

const WORKBENCH_TOUR_VERSION = 4;
const WORKBENCH_TOUR_FLAG = "workbench_tour_seen";
const UPDATE_PROMPT_DISMISSED_KEY = "insar.updatePrompt.dismissedVersion";
const WORKBENCH_TOUR_STEPS: TourStep[] = [
  {
    title: "欢迎使用 InSAR Studio",
    body: "这一版按下载工具的真实流程走：先配置必要账号或密钥，再选择资源、区域和输出，最后进入下载中心看队列。",
    hint: "没有 Earthdata/ASF 凭据时不会允许开始 Sentinel-1 下载，避免任务进入队列后才连续失败。",
    placement: "center",
  },
  {
    target: '[data-tour="settings-tab"]',
    title: "1. 先配置必要密钥",
    body: "第一次使用先到设置里保存 Earthdata Token 或账号密码。DEM 的 OpenTopography Key、GACOS 邮箱、代理和缓存也都在这里维护。",
    placement: "right",
  },
  {
    target: '[data-tour="source-tabs"]',
    title: "2. 选择要处理的数据类型",
    body: "顶部是资源类型入口。Sentinel-1、DEM、精密轨道、GACOS 后续都会共享同一个地图范围和下载中心，减少来回切模块。",
    placement: "bottom",
  },
  {
    target: '[data-tour="scope-panel"]',
    title: "3. 确认区域范围",
    body: "这里显示当前 AOI 状态。你可以加载行政区、上传边界，也可以直接不设 AOI 检索 ASF，后续下载时再确认输出目录。",
    placement: "right",
  },
  {
    target: '[data-tour="asf-filter"]',
    title: "4. 设置在线筛选和本地检索",
    body: "资源下载面板里完成 Sentinel-1 在线筛选、本地文件检索、DEM 下载转换、Orbit/GACOS 日期解析等操作。每个功能都可以收起，避免信息堆在一起。",
    placement: "right",
  },
  {
    target: '[data-tour="map-canvas"]',
    title: "5. 在地图上核对范围",
    body: "右侧地图会显示 AOI、行政边界、SAR 影像框和底图图层。点击列表中的影像可以定位，鼠标停在 i 上查看完整元数据。",
    placement: "left",
  },
  {
    target: '[data-tour="download-center-tab"]',
    title: "6. 下载中心看队列",
    body: "真正开始下载后，进度、速度、暂停、继续、结束和历史记录都集中在下载中心，不再因为切换界面丢失状态。",
    placement: "right",
  },
  {
    target: '[data-tour="settings-tab"]',
    title: "7. 回到设置维护账号、代理与缓存",
    body: "ASF/Earthdata、OpenTopography、GACOS、网络代理、缓存目录都在设置里维护。账号密钥保存在系统凭据里，不写进项目目录。",
    placement: "right",
  },
  {
    target: '[data-tour="help-button"]',
    title: "随时重新打开引导",
    body: "顶部的新手引导入口可以重新播放这个流程。后续还可以继续扩展 Sentinel-2、DEM、Orbit 的专项步骤。",
    placement: "bottom",
  },
];

const LINKS = {
  earthdataToken: "https://urs.earthdata.nasa.gov/profile",
  earthdataRegister: "https://urs.earthdata.nasa.gov/users/new",
  opentopoKey: "https://portal.opentopography.org/requestService?service=api",
  opentopoRegister: "https://portal.opentopography.org/newUser",
  gacosPortal: "http://www.gacos.net/",
  tiandituKey: "https://console.tianditu.gov.cn/api/key",
  github: "https://github.com/hhanmj/insar_studio/releases/latest",
};

const EARTHDATA_AUTH_RETRY_COOLDOWN_MS = 5 * 60 * 1000;
const EARTHDATA_AUTH_TIMER_MS = 6 * 60 * 60 * 1000;

function isConfigured(value: string | undefined) {
  return !!value && value !== "none" && value !== "unavailable";
}

function needsDemGdalComponent(message: string | null | undefined) {
  const text = String(message || "");
  const lowered = text.toLowerCase();
  return Boolean(
    text.includes("DEM/GDAL 高级转换组件") ||
      (text.includes("EGM2008") && text.includes("组件")) ||
      lowered.includes("proj.db") ||
      lowered.includes("proj_create_from_database") ||
      lowered.includes("the epsg code is unknown") ||
      lowered.includes("cannot find proj.db") ||
      lowered.includes("rasterio/gdal"),
  );
}

function earthdataCredentialSourceLabel(value: string | undefined) {
  if (!value || value === "none") return "未保存凭据";
  if (value === "unavailable") return "系统凭据不可用";
  if (value === "token") return "本机已保存 Token";
  if (value.startsWith("login:")) return `本机已保存账号 ${value.slice("login:".length)}`;
  return `本机已保存 ${value}`;
}

function statusLabel(state: string | undefined) {
  if (state === "running") return "运行中";
  if (state === "paused") return "已暂停";
  if (state === "finished") return "已完成";
  if (state === "cancelled") return "已结束";
  if (state === "interrupted") return "上次中断";
  if (state === "failed") return "失败";
  return "空闲";
}

function orbitLabel(value: string) {
  const upper = (value || "").toUpperCase();
  if (upper === "ASCENDING" || upper === "A") return "升轨";
  if (upper === "DESCENDING" || upper === "D") return "降轨";
  return "-";
}

function polarizationLabel(value: string | null | undefined) {
  const upper = (value || "").toUpperCase();
  const labels: Record<string, string> = {
    DV: "VV+VH",
    DH: "HH+HV",
    SV: "VV",
    SH: "HH",
  };
  return labels[upper] ? `${labels[upper]} (${upper})` : upper || "-";
}

function fmtBytes(value: number | null | undefined): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = n;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}

function fmtRate(value: number | null | undefined): string {
  return `${fmtBytes(value)}/s`;
}

function fmtDuration(value: number | null | undefined): string {
  const total = Math.max(0, Math.floor(Number(value ?? 0)));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function roughBboxAreaKm2(bbox: Bbox): string {
  const lat = ((bbox.north + bbox.south) / 2) * (Math.PI / 180);
  const width = Math.abs(bbox.east - bbox.west) * 111.32 * Math.max(0.01, Math.cos(lat));
  const height = Math.abs(bbox.north - bbox.south) * 110.57;
  return (width * height).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function kv(label: string, value: string | number | null | undefined) {
  return (
    <div className="flex min-w-0 justify-between gap-3 text-xs">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="truncate text-right font-mono">{value ?? "-"}</span>
    </div>
  );
}

function metricPill(label: string, value: string | number | null | undefined, tone: "neutral" | "primary" | "success" | "warning" = "neutral") {
  return (
    <div
      className={cn(
        "inline-flex h-9 items-center gap-2 rounded-full border px-3 text-xs shadow-sm backdrop-blur-xl",
        tone === "primary" && "border-primary/25 bg-primary/10",
        tone === "success" && "border-success/25 bg-success/10",
        tone === "warning" && "border-warning/30 bg-warning/10",
        tone === "neutral" && "border-white/45 bg-white/45 dark:border-white/10 dark:bg-white/10",
      )}
    >
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="max-w-[12rem] truncate font-mono text-sm font-semibold tabular-nums text-foreground" title={String(value ?? "-")}>
        {value ?? "-"}
      </span>
    </div>
  );
}

type VirtualRow<T> = {
  item: T;
  index: number;
  top: number;
};

function useVirtualRows<T>(items: T[], rowHeight: number, overscan = 8, restoreScrollTop = 0) {
  const [node, setNode] = useState<HTMLDivElement | null>(null);
  const restoreScrollTopRef = useRef(restoreScrollTop);
  const [viewport, setViewport] = useState({ scrollTop: restoreScrollTop, height: 600 });

  const scrollRef = useCallback((element: HTMLDivElement | null) => {
    setNode(element);
    if (!element) return;
    const top = Math.max(0, restoreScrollTopRef.current);
    element.scrollTop = top;
    setViewport({
      scrollTop: element.scrollTop,
      height: element.clientHeight || 600,
    });
  }, []);

  const updateViewport = useCallback(() => {
    if (!node) return;
    setViewport({
      scrollTop: node.scrollTop,
      height: node.clientHeight || 600,
    });
  }, [node]);

  useEffect(() => {
    restoreScrollTopRef.current = restoreScrollTop;
    if (!node) return;
    const top = Math.max(0, restoreScrollTop);
    if (Math.abs(node.scrollTop - top) > 1) node.scrollTop = top;
    setViewport({
      scrollTop: node.scrollTop,
      height: node.clientHeight || 600,
    });
  }, [node, restoreScrollTop]);

  useEffect(() => {
    updateViewport();
    if (!node) return;
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(updateViewport);
      observer.observe(node);
      return () => observer.disconnect();
    }
    window.addEventListener("resize", updateViewport);
    return () => window.removeEventListener("resize", updateViewport);
  }, [items.length, node, updateViewport]);

  const onScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    setViewport({
      scrollTop: event.currentTarget.scrollTop,
      height: event.currentTarget.clientHeight || 600,
    });
  }, []);

  const totalHeight = items.length * rowHeight;
  const startIndex = Math.max(0, Math.floor(viewport.scrollTop / rowHeight) - overscan);
  const visibleCount = Math.ceil(viewport.height / rowHeight) + overscan * 2;
  const endIndex = Math.min(items.length, startIndex + visibleCount);
  const rows: VirtualRow<T>[] = items.slice(startIndex, endIndex).map((item, offset) => {
    const index = startIndex + offset;
    return { item, index, top: index * rowHeight };
  });

  return { scrollRef, onScroll, totalHeight, rows };
}

function detailMetric(label: string, value: string | number | null | undefined) {
  const display = value ?? "-";
  return (
    <div className="flex min-w-0 items-center justify-between gap-2 rounded-md border border-border/60 bg-muted/20 px-2 py-1 text-[11px]">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="truncate text-right font-mono font-medium tabular-nums" title={String(display)}>
        {display}
      </span>
    </div>
  );
}

function ErrorLine({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{text}</span>
    </div>
  );
}

function NoteLine({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <div className="flex items-start gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{text}</span>
    </div>
  );
}

function SceneMetaCard({ scene }: { scene: SceneRow }) {
  return (
    <div className="w-[360px] rounded-2xl border border-white/70 bg-white/95 p-3 text-xs shadow-2xl backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/95">
      <div className="mb-2 break-all font-mono text-[11px] font-semibold leading-4">{scene.scene_id}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {kv("产品", scene.product_type || "-")}
        {kv("束模式", scene.beam_mode || "-")}
        {kv("极化", polarizationLabel(scene.polarization))}
        {kv("升降轨", orbitLabel(scene.orbit_direction))}
        {kv("Path", scene.path ?? scene.relative_orbit ?? "-")}
        {kv("Frame", scene.frame ?? "-")}
        {kv("绝对轨道", scene.absolute_orbit ?? "-")}
        {kv("采集时间", scene.acquisition_datetime || "-")}
        {kv("远端大小", fmtBytes(scene.file_size_remote))}
        {kv("下载 URL", scene.has_url ? "已提供" : "未提供")}
      </div>
      {scene.footprint_bbox && (
        <div className="mt-2 rounded-xl border border-white/60 bg-white/45 px-2 py-1.5 font-mono text-[11px] text-muted-foreground dark:border-white/10 dark:bg-white/10">
          W{scene.footprint_bbox.west.toFixed(5)} S{scene.footprint_bbox.south.toFixed(5)}
          <br />
          E{scene.footprint_bbox.east.toFixed(5)} N{scene.footprint_bbox.north.toFixed(5)}
        </div>
      )}
    </div>
  );
}

function asfDownloaderUrl(scene: SceneRow) {
  const explicit = String(scene.download_url || "").trim();
  if (explicit) return explicit;
  const sceneId = String(scene.scene_id || "").trim();
  if (!sceneId) return "";
  const platform = sceneId.slice(0, 3).toUpperCase();
  const platformDir =
    platform === "S1A" ? "SA" : platform === "S1B" ? "SB" : platform === "S1C" ? "SC" : platform === "S1D" ? "SD" : platform;
  const product = String(scene.product_type || "").trim().toUpperCase() || "SLC";
  const fileName = sceneId.toUpperCase().endsWith(".ZIP") ? sceneId : `${sceneId}.zip`;
  return `https://datapool.asf.alaska.edu/${product}/${platformDir}/${fileName}`;
}

function sceneMetadataText(scene: SceneRow) {
  const bbox = scene.footprint_bbox
    ? `W${scene.footprint_bbox.west} S${scene.footprint_bbox.south} E${scene.footprint_bbox.east} N${scene.footprint_bbox.north}`
    : "-";
  return [
    `scene_id: ${scene.scene_id}`,
    `product_type: ${scene.product_type || "-"}`,
    `beam_mode: ${scene.beam_mode || "-"}`,
    `polarization: ${polarizationLabel(scene.polarization)}`,
    `orbit_direction: ${orbitLabel(scene.orbit_direction)}`,
    `path: ${scene.path ?? scene.relative_orbit ?? "-"}`,
    `frame: ${scene.frame ?? "-"}`,
    `absolute_orbit: ${scene.absolute_orbit ?? "-"}`,
    `acquisition_datetime: ${scene.acquisition_datetime || "-"}`,
    `remote_size: ${fmtBytes(scene.file_size_remote)}`,
    `download_url: ${asfDownloaderUrl(scene) || "not provided"}`,
    `footprint_bbox: ${bbox}`,
  ].join("\n");
}

function Section({
  title,
  desc,
  icon: Icon,
  headerExtra,
  children,
  defaultOpen = true,
  storageKey,
  forceOpenSignal = 0,
}: {
  title: string;
  desc?: string;
  icon?: typeof Satellite;
  headerExtra?: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  storageKey?: string;
  forceOpenSignal?: number;
}) {
  const [open, setOpen] = useState(() => {
    if (!storageKey || typeof window === "undefined") return defaultOpen;
    const stored = window.localStorage.getItem(`insar.section.${storageKey}`);
    return stored == null ? defaultOpen : stored === "open";
  });
  useEffect(() => {
    if (!forceOpenSignal) return;
    setOpen(true);
    if (storageKey && typeof window !== "undefined") {
      window.localStorage.setItem(`insar.section.${storageKey}`, "open");
    }
  }, [forceOpenSignal, storageKey]);
  function toggleOpen() {
    setOpen((value) => {
      const next = !value;
      if (storageKey && typeof window !== "undefined") {
        window.localStorage.setItem(`insar.section.${storageKey}`, next ? "open" : "closed");
      }
      return next;
    });
  }
  return (
    <section className="glass-panel overflow-visible">
      <button
        type="button"
        onClick={toggleOpen}
        className="flex w-full items-start gap-2 px-3 py-3 text-left transition-colors hover:bg-white/30 dark:hover:bg-white/5"
      >
        {Icon && (
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
            <Icon className="h-3.5 w-3.5" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{title}</div>
          {desc && <div className="mt-0.5 text-xs leading-5 text-muted-foreground">{desc}</div>}
        </div>
        {headerExtra && <div className="mt-0.5 shrink-0">{headerExtra}</div>}
        <ChevronDown className={cn("mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="border-t px-3 py-3">{children}</div>}
    </section>
  );
}

function activeBbox(ctx: Context | null): Bbox {
  return ctx?.region?.bbox ?? ctx?.region?.scene_footprint_bbox ?? DEFAULT_BBOX;
}

function collectGeojsonPositions(value: unknown, points: Array<[number, number]>) {
  if (Array.isArray(value)) {
    if (
      value.length >= 2 &&
      typeof value[0] === "number" &&
      typeof value[1] === "number" &&
      Number.isFinite(value[0]) &&
      Number.isFinite(value[1])
    ) {
      points.push([value[0], value[1]]);
      return;
    }
    value.forEach((item) => collectGeojsonPositions(item, points));
    return;
  }
  if (value && typeof value === "object") {
    Object.values(value).forEach((item) => collectGeojsonPositions(item, points));
    return;
  }
}

function geojsonBbox(value: unknown): Bbox | null {
  if (!value || typeof value !== "object") return null;
  const record = value as { bbox?: unknown; coordinates?: unknown; geometry?: unknown; geometries?: unknown; features?: unknown };
  if (
    Array.isArray(record.bbox) &&
    record.bbox.length >= 4 &&
    record.bbox.slice(0, 4).every((item) => typeof item === "number" && Number.isFinite(item))
  ) {
    const [west, south, east, north] = record.bbox as [number, number, number, number];
    return { west, east, south, north, crs: "EPSG:4326" };
  }
  const points: Array<[number, number]> = [];
  collectGeojsonPositions(record.coordinates, points);
  collectGeojsonPositions(record.geometry, points);
  collectGeojsonPositions(record.geometries, points);
  collectGeojsonPositions(record.features, points);
  if (!points.length) return null;
  return {
    west: Math.min(...points.map(([x]) => x)),
    east: Math.max(...points.map(([x]) => x)),
    south: Math.min(...points.map(([, y]) => y)),
    north: Math.max(...points.map(([, y]) => y)),
    crs: "EPSG:4326",
  };
}

function sceneRowsBbox(rows: SceneRow[]): Bbox | null {
  const boxes = rows
    .map((scene) => scene.footprint_bbox ?? geojsonBbox(scene.footprint_geojson))
    .filter((bbox): bbox is Bbox => !!bbox);
  return unionBboxes(boxes);
}

function updatePromptAlreadyDismissed(version: string) {
  if (typeof window === "undefined" || !version) return false;
  return window.localStorage.getItem(UPDATE_PROMPT_DISMISSED_KEY) === version;
}

function dismissUpdatePromptVersion(version: string) {
  if (typeof window === "undefined" || !version) return;
  window.localStorage.setItem(UPDATE_PROMPT_DISMISSED_KEY, version);
}

function releaseDateLabel(value: string | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
}

function changelogLines(value: string | undefined) {
  return String(value || "")
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.replace(/^#+\s*/, "").replace(/^[-*]\s+/, "").trim())
    .filter(Boolean)
    .slice(0, 12);
}

function unionBboxes(boxes: Array<Bbox | null | undefined>): Bbox | null {
  const valid = boxes.filter((bbox): bbox is Bbox => !!bbox);
  if (!valid.length) return null;
  return {
    west: Math.min(...valid.map((bbox) => bbox.west)),
    east: Math.max(...valid.map((bbox) => bbox.east)),
    south: Math.min(...valid.map((bbox) => bbox.south)),
    north: Math.max(...valid.map((bbox) => bbox.north)),
    crs: "EPSG:4326",
  };
}

function localPathExtension(path: string) {
  const clean = path.trim().split(/[\\/]/).pop() ?? path.trim();
  const dot = clean.lastIndexOf(".");
  return dot >= 0 ? clean.slice(dot).toLowerCase() : "";
}

function isSupportedLocalBoundaryPath(path: string) {
  return LOCAL_BOUNDARY_EXTENSIONS.has(localPathExtension(path));
}

function isFileDrag(event: DragEvent<HTMLElement>) {
  return Array.from(event.dataTransfer.types ?? []).includes("Files");
}

async function fileToBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function sceneBatchKey(rows: SceneRow[]): string {
  return rows
    .map((scene) =>
      [
        scene.scene_id,
        scene.product_type,
        scene.acquisition_datetime,
        scene.path ?? scene.relative_orbit ?? "",
        scene.frame ?? "",
      ].join("|"),
    )
    .sort()
    .join(";");
}

function sceneRowsForIds(rows: SceneRow[], ids: string[]): SceneRow[] {
  const wanted = new Set(ids.filter(Boolean));
  return rows.filter((scene) => wanted.has(scene.scene_id));
}

function mergeSceneRows(...groups: SceneRow[][]): SceneRow[] {
  const byId = new Map<string, SceneRow>();
  for (const group of groups) {
    for (const scene of group) {
      if (scene.scene_id && !byId.has(scene.scene_id)) byId.set(scene.scene_id, scene);
    }
  }
  return Array.from(byId.values());
}

function asNumber(value: string, fallback: number) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeDateInput(value: string) {
  const text = value.trim();
  if (!text) return "";
  const match = /^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/.exec(text);
  if (!match) return text;
  const [, year, month, day] = match;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function isValidSearchDate(value: string) {
  if (!value) return true;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

function dateInputValue(value: string) {
  const normalised = normalizeDateInput(value);
  return /^\d{4}-\d{2}-\d{2}$/.test(normalised) ? normalised : "";
}

function dateDisplayValue(value: string) {
  const normalised = dateInputValue(value);
  return normalised ? normalised.replace(/-/g, "/") : value;
}

function DatePickerInput({
  value,
  onChange,
  ariaLabel,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
  label?: string;
}) {
  const dateValue = dateInputValue(value);
  return (
    <div className="relative">
      {label && (
        <span className="pointer-events-none absolute left-3 top-1/2 z-10 -translate-y-1/2 whitespace-nowrap text-[11px] text-muted-foreground">
          {label}
        </span>
      )}
      <Input
        type="text"
        inputMode="numeric"
        placeholder="yyyy/mm/dd"
        value={dateDisplayValue(value)}
        onChange={(event) => onChange(event.target.value)}
        onBlur={(event) => onChange(normalizeDateInput(event.currentTarget.value))}
        aria-label={ariaLabel}
        className={cn("h-9 pr-10 text-sm placeholder:text-xs", label ? "pl-12" : "")}
      />
      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
        <CalendarDays className="h-3.5 w-3.5" />
      </span>
      <input
        type="date"
        value={dateValue}
        onChange={(event) => onChange(event.target.value)}
        aria-label={`${ariaLabel}选择器`}
        tabIndex={-1}
        className="absolute right-1.5 top-1/2 h-8 w-8 -translate-y-1/2 cursor-pointer opacity-0"
      />
    </div>
  );
}

function uniqueOptions(options: string[]) {
  return Array.from(
    new Set(options.map((item) => item.trim()).filter((item) => item && item !== "全部" && item !== "不限")),
  );
}

function withAllOption(options: string[]) {
  return ["全部", ...uniqueOptions(options)];
}

function formatLogTime(value: number | string | null | undefined) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "";
  const d = new Date(n < 10_000_000_000 ? n * 1000 : n);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (item: number) => String(item).padStart(2, "0");
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function compactDownloadLogText(detail: string, outcome = "") {
  const raw = detail.trim();
  const lower = raw.toLowerCase();
  const outcomeLabel: Record<string, string> = {
    success: "完成",
    skipped: "跳过",
    failed: "失败",
    interrupted: "中断",
    paused: "暂停",
    resumed: "继续",
    verified: "核对",
    unavailable: "不可用",
  };
  let text = raw
    .replace(/cancelled by user; partial \.part kept for resume/gi, "用户取消，已保留 .part")
    .replace(/already complete; skipped/gi, "文件已完整，跳过")
    .replace(/existing \.part matched expected size; finalized/gi, ".part 已完整，已转为正式文件")
    .replace(/download failed after \d+ attempts:?/gi, "多次重试后失败：")
    .replace(/no download URL for scene/gi, "缺少下载链接")
    .replace(/\bsuccess\b/gi, "完成")
    .replace(/\bskipped\b/gi, "跳过")
    .replace(/\bfailed\b/gi, "失败")
    .replace(/\binterrupted\b/gi, "中断")
    .replace(/\bunavailable\b/gi, "不可用");
  if (outcome && outcomeLabel[outcome] && lower === outcome) text = outcomeLabel[outcome];
  if (text.length > 120) text = `${text.slice(0, 117)}...`;
  return text;
}

function formatDownloadLogEntry(entry: { detail?: string; ts?: number | string } | string) {
  if (typeof entry === "string") return compactDownloadLogText(entry);
  const detail = String(entry.detail || "").trim();
  if (!detail) return "";
  const text = compactDownloadLogText(detail, String((entry as { outcome?: string }).outcome || ""));
  const stamp = formatLogTime(entry.ts);
  return stamp ? `[${stamp}] ${text}` : text;
}

function pathBaseName(path: string) {
  return path.trim().replace(/[\\/]+$/, "").split(/[\\/]/).pop()?.trim() || "";
}

function fileStem(path: string) {
  const base = pathBaseName(path);
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

function aoiFeatureDisplayName(feature: AoiFeaturePreview, field: string) {
  const props = feature.properties;
  const fieldValue =
    field && props && typeof props === "object" && !Array.isArray(props)
      ? String((props as Record<string, unknown>)[field] ?? "").trim()
      : "";
  return fieldValue || String(feature.name || "").trim();
}

function localBoundaryAoiName(
  preview: AoiPreviewOk | null,
  selectedIds: Set<string>,
  field: string,
  fallbackPath: string,
) {
  const fallback = fileStem(fallbackPath) || "本地边界";
  const selected = (preview?.features ?? []).filter((feature) => selectedIds.has(feature.id));
  if (selected.length === 1) return aoiFeatureDisplayName(selected[0], field) || fallback;
  const names = selected.map((feature) => aoiFeatureDisplayName(feature, field)).filter(Boolean);
  const uniqueNames = Array.from(new Set(names));
  if (uniqueNames.length === 1) return uniqueNames[0];
  if (selected.length > 1) return `${fallback} (${selected.length} 要素)`;
  return fallback;
}

function pathDirName(path: string) {
  const trimmed = path.trim().replace(/[\\/]+$/, "");
  const parts = trimmed.split(/[\\/]/);
  if (parts.length <= 1) return trimmed;
  return parts.slice(0, -1).join("\\");
}

function jsonField(value: Json | null | undefined, key: string) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  const raw = (value as Record<string, unknown>)[key];
  return raw == null ? "" : String(raw);
}

function compactResultLine(value: Json, index: number, prefix = "") {
  if (!value || typeof value !== "object" || Array.isArray(value)) return `${prefix}${index + 1}. ${String(value ?? "")}`;
  const dataset = jsonField(value, "dataset");
  const outcome = compactDemLogText(jsonField(value, "outcome") || jsonField(value, "status"));
  const message = compactDemLogText(jsonField(value, "message") || jsonField(value, "error"));
  const path = jsonField(value, "output_path") || jsonField(value, "path");
  const parts = [
    dataset,
    outcome,
    message && message !== outcome ? message : "",
    path ? pathBaseName(path) : "",
  ].filter(Boolean);
  return `${prefix}${index + 1}. ${parts.join("；")}`;
}

function compactDemLogText(value: string) {
  let text = String(value || "").trim();
  if (!text) return "";
  text = text
    .replace(/(\d+)\s+downloaded,\s+(\d+)\s+skipped,\s+(\d+)\s+failed,\s+(\d+)\s+interrupted/gi, "下载 $1 成功，$2 跳过，$3 失败，$4 中断")
    .replace(/\bdownloaded\b/gi, "已下载")
    .replace(/\bskipped\b/gi, "已跳过")
    .replace(/\bfailed\b/gi, "失败")
    .replace(/\binterrupted\b/gi, "中断")
    .replace(/\bsuccess\b/gi, "完成")
    .replace(/\bcopied\b/gi, "已复制")
    .replace(/\bconverted\b/gi, "已转换")
    .replace(/dataset is not downloadable from OpenTopography/gi, "该 DEM 来源不能在线下载")
    .replace(/no downloadable DEM datasets in the provided plans \(e\.g\. USER_LOCAL\)/gi, "当前 DEM 来源不能在线下载，请选择在线 DEM 或使用本地 DEM 转换");
  if (text.length > 220) text = `${text.slice(0, 217)}...`;
  return text;
}

function demRunOutputDir(run: RunSummaryOk) {
  if (run.output_dir?.trim()) return run.output_dir.trim();
  const candidate =
    run.results_path ||
    run.conversion_results_path ||
    run.sarscape_ready_dem_path ||
    run.ellipsoid_dem_path ||
    run.raw_dem_path ||
    "";
  return candidate ? pathDirName(candidate) : "";
}

function demRunLogLines(run: RunSummaryOk) {
  const downloadResults = (run.download as { results?: Json[] } | undefined)?.results;
  const conversionResults = (run.conversion as { results?: Json[] } | null | undefined)?.results;
  const lines = [
    run.summary_line,
    run.raw_dem_path ? `原始 DEM：${pathBaseName(run.raw_dem_path)}` : "",
    run.ellipsoid_dem_path ? `椭球高 DEM：${pathBaseName(run.ellipsoid_dem_path)}` : "",
    run.sarscape_ready_dem_path ? `SARscape DEM：${pathBaseName(run.sarscape_ready_dem_path)}` : "",
    run.results_path ? `结果表：${pathBaseName(run.results_path)}` : "",
    run.conversion_results_path ? `转换结果表：${pathBaseName(run.conversion_results_path)}` : "",
    ...(run.results ?? []).map((item, index) => compactResultLine(item, index)),
    ...(Array.isArray(downloadResults) ? downloadResults.map((item, index) => compactResultLine(item, index, "下载 ")) : []),
    ...(Array.isArray(conversionResults) ? conversionResults.map((item, index) => compactResultLine(item, index, "转换 ")) : []),
  ];
  return Array.from(new Set(lines.map(compactDemLogText).filter(Boolean))).slice(-24);
}

function demRunDisplayPaths(run: RunSummaryOk) {
  const conversionResults = (run.conversion as { results?: Json[] } | null | undefined)?.results;
  const candidates = [...(run.results ?? []), ...(Array.isArray(conversionResults) ? conversionResults : [])];
  let raw = run.raw_dem_path || "";
  let ellipsoid = run.ellipsoid_dem_path || "";
  let sarscape = run.sarscape_ready_dem_path || "";

  for (const item of candidates) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const record = item as Record<string, unknown>;
    const inputPath = String(record.input_path ?? record.raw_dem_path ?? "");
    const outputPath = String(record.output_path ?? record.sarscape_ready_dem_path ?? record.path ?? "");
    if (!raw && inputPath) raw = inputPath;
    if (!ellipsoid && /_ellipsoid\.(tif|tiff)$/i.test(outputPath)) ellipsoid = outputPath;
    if (!sarscape && /_dem($|\.hdr$)/i.test(outputPath)) sarscape = outputPath.replace(/\.hdr$/i, "");
  }

  return { raw, ellipsoid, sarscape };
}

function loadDownloadArchive() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(DOWNLOAD_ARCHIVE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    const deletedKeys = new Set(
      parsed
        .filter((item) => item && typeof item === "object" && item.status === "deleted")
        .map((item) => archiveTaskKey({ ...(item as DownloadArchiveItem), status: "cancelled" })),
    );
    return dedupeArchiveItems(parsed
      .filter(
        (item) =>
        item &&
        typeof item.id === "string" &&
        typeof item.name === "string" &&
        typeof item.status === "string" &&
        item.status !== "deleted" &&
        typeof item.detail === "string",
      )
      .map((item) => normaliseArchiveItemForStartup(item as DownloadArchiveItem))
      .filter((item) => !deletedKeys.has(archiveTaskKey(item))))
      .slice(0, 30);
  } catch {
    return [];
  }
}

function normaliseArchiveItemForStartup(item: DownloadArchiveItem): DownloadArchiveItem {
  if (item.status !== "running") return item;
  const detail = item.detail ? `上次关闭时仍在运行：${item.detail}` : "上次关闭软件时任务仍在运行。";
  return {
    ...item,
    status: "interrupted",
    detail: `${detail}；可用同一输出目录重新开始以断点续传。`,
    logs: [
      ...(item.logs ?? []),
      "应用关闭时任务未完成；可重新开始同一输出目录，已完成文件会跳过，.part 文件可断点续传。",
    ].slice(-120),
  };
}

function normaliseArchiveForStartup(items: DownloadArchiveItem[]) {
  return dedupeArchiveItems(items.map(normaliseArchiveItemForStartup));
}

function archiveTaskKind(item: DownloadArchiveItem) {
  if (item.kind) return item.kind;
  if (item.id.startsWith("asf:") || /ASF/i.test(item.name)) return "asf";
  if (item.id.startsWith("orbit:") || /Orbit|轨道|EOF|POEORB/i.test(item.name)) return "orbit";
  if (item.id.startsWith("dem:") || /DEM/i.test(item.name)) return "dem";
  return "";
}

function archiveTaskOutputDir(item: DownloadArchiveItem) {
  if (item.output_dir?.trim()) return item.output_dir.trim();
  const kind = archiveTaskKind(item);
  const prefix = `${kind}:`;
  if (!kind || !item.id.startsWith(prefix)) return "";
  const body = item.id.slice(prefix.length);
  const match = /^(.*):\d+$/.exec(body);
  return (match ? match[1] : body).trim();
}

function archiveTaskKey(item: DownloadArchiveItem) {
  const kind = archiveTaskKind(item);
  if (kind === "dem" && item.id) return item.id;
  const out = archiveTaskOutputDir(item).replace(/[\\/]+$/, "").toLowerCase();
  const layout =
    item.download_layout ||
    (kind === "asf" ? (item.use_product_subdirs ? "product_subdirs" : "flat") : "") ||
    (kind === "orbit" ? (item.use_orbit_subdir ? "orbit_subdir" : "flat") : "");
  if (kind && out) return layout ? `${kind}:${out}:${layout}` : `${kind}:${out}`;
  return item.id;
}

function archiveTaskStatusRank(item: DownloadArchiveItem) {
  if (["finished", "failed", "cancelled", "interrupted", "timeout"].includes(item.status)) return 4;
  if (item.status === "paused") return 3;
  if (item.status === "running") return 2;
  return 1;
}

function dedupeArchiveItems(items: DownloadArchiveItem[]) {
  const byKey = new Map<string, DownloadArchiveItem>();
  for (const item of items) {
    const key = archiveTaskKey(item);
    const prev = byKey.get(key);
    const itemTs = Number(item.ts || 0);
    const prevTs = Number(prev?.ts || 0);
    if (
      !prev ||
      itemTs > prevTs ||
      (itemTs === prevTs && archiveTaskStatusRank(item) > archiveTaskStatusRank(prev))
    ) {
      byKey.set(key, item);
    }
  }
  return Array.from(byKey.values()).sort((a, b) => Number(b.ts || 0) - Number(a.ts || 0));
}

function isRestorableArchiveTask(item: DownloadArchiveItem) {
  const kind = archiveTaskKind(item);
  return (
    (kind === "asf" || kind === "orbit") &&
    item.status === "paused" &&
    !!archiveTaskOutputDir(item)
  );
}

function archiveTaskTimeLabel(item: DownloadArchiveItem) {
  const stamp = formatLogTime(item.ts);
  return stamp ? stamp.slice(5, 16) : "";
}

function archiveTaskDisplayName(item: DownloadArchiveItem) {
  const name = item.name || "";
  if (archiveTaskKind(item) === "asf" || /ASF\s*Sentinel-1/i.test(name)) return "Sentinel-1 下载任务";
  return name || "下载任务";
}

function archiveTaskDisplayTitle(item: DownloadArchiveItem) {
  const time = archiveTaskTimeLabel(item);
  const name = archiveTaskDisplayName(item);
  return time ? `${name} · ${time}` : name;
}

function archiveTaskBadges(item: DownloadArchiveItem) {
  const out = archiveTaskOutputDir(item);
  const parts = [];
  if (out) parts.push(`目录 ${pathBaseName(out) || out}`);
  if (item.total) parts.push(`${item.total}景`);
  if (item.concurrency) parts.push(`并发${item.concurrency}`);
  return parts;
}

function archiveTaskInlineMeta(item: DownloadArchiveItem) {
  return archiveTaskBadges(item).join(" · ");
}

function compactSearchText(value: unknown) {
  return String(value ?? "").replace(/[-_:TZ.\s]/g, "").toLowerCase();
}

function sceneMatchesQuery(scene: SceneRow, query: string) {
  const raw = query.trim();
  if (!raw) return true;
  const q = raw.toLowerCase();
  const compact = compactSearchText(raw);
  const fields = [
    scene.scene_id,
    scene.product_type,
    scene.beam_mode,
    scene.polarization,
    polarizationLabel(scene.polarization),
    scene.orbit_direction,
    orbitLabel(scene.orbit_direction),
    scene.path,
    scene.relative_orbit,
    scene.frame,
    scene.absolute_orbit,
    scene.acquisition_datetime,
  ];
  const text = fields.map((item) => String(item ?? "")).join(" ").toLowerCase();
  const packed = compactSearchText(fields.join(" "));
  return text.includes(q) || (compact.length > 0 && packed.includes(compact));
}

export function Workbench({
  dark,
  onToggleDark,
}: {
  dark: boolean;
  onToggleDark: () => void;
}) {
  const { ctx, refresh } = usePrepContext();

  const [source, setSource] = useState<SourceMode>("sentinel1");
  const [panel, setPanel] = useState<PanelTab>("resources");
  const [layerKey, setLayerKey] = useState<MapLayerKey>("arcgisSatellite");
  const [drawMode, setDrawMode] = useState<WorkbenchDrawMode>("rect");
  const [drawActive, setDrawActive] = useState(false);
  const [aoiToolsOpen, setAoiToolsOpen] = useState(false);
  const [manualAoiOpen, setManualAoiOpen] = useState(false);
  const [tourSignal, setTourSignal] = useState(0);
  const [tourAutoStart, setTourAutoStart] = useState(false);
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateNote, setUpdateNote] = useState<string | null>(null);
  const [downloadedUpdate, setDownloadedUpdate] = useState<{ path: string; folder: string } | null>(null);
  const [componentStatus, setComponentStatus] = useState<ComponentStatusOk | null>(null);
  const [componentBusy, setComponentBusy] = useState<string | null>(null);
  const [componentNote, setComponentNote] = useState<string | null>(null);
  const [settingsComponentsOpenSignal, setSettingsComponentsOpenSignal] = useState(0);
  const [communityOpen, setCommunityOpen] = useState(false);
  const sidebarScrollRef = useRef<HTMLDivElement | null>(null);
  const sidebarScrollPositions = useRef<Record<string, number>>({});
  const sidebarScrollKey = panel === "resources" ? `resources:${source}` : panel;

  const [outputDir, setOutputDir] = useState("");
  const [outputDirSceneKey, setOutputDirSceneKey] = useState("");
  const [demDownloadOutputDir, setDemDownloadOutputDir] = useState("");
  const [localDemOutputDir, setLocalDemOutputDir] = useState("");
  const [scenes, setScenes] = useState<SceneRow[]>([]);
  const [sceneText, setSceneText] = useState("");
  const [sceneFile, setSceneFile] = useState("");
  const [sceneDir, setSceneDir] = useState("");
  const [orbitScenes, setOrbitScenes] = useState<SceneRow[]>([]);
  const [orbitSceneFile, setOrbitSceneFile] = useState("");
  const [orbitSceneDir, setOrbitSceneDir] = useState("");
  const [sceneBusy, setSceneBusy] = useState(false);
  const [sceneError, setSceneError] = useState<string | null>(null);
  const [sceneNote, setSceneNote] = useState<string | null>(null);
  const [checkBusy, setCheckBusy] = useState(false);
  const [checkReport, setCheckReport] = useState<CheckOk["report"] | null>(null);

  const [aoiBusy, setAoiBusy] = useState(false);
  const [aoiError, setAoiError] = useState<string | null>(null);
  const [aoiNote, setAoiNote] = useState<string | null>(null);
  const [adminQuery, setAdminQuery] = useState("");
  const [adminProvince, setAdminProvince] = useState("全部");
  const [adminCity, setAdminCity] = useState("全部");
  const [adminDistrict, setAdminDistrict] = useState("全部");
  const [adminPickerOpen, setAdminPickerOpen] = useState<"province" | "city" | "district" | null>(null);
  const [adminOptions, setAdminOptions] = useState<{ provinces: string[]; cities: string[]; districts: string[] }>({
    provinces: [],
    cities: [],
    districts: [],
  });
  const [adminResults, setAdminResults] = useState<AdminBoundary[]>([]);
  const [selectedAdminBoundary, setSelectedAdminBoundary] = useState<AdminBoundary | null>(null);
  const [adminBusy, setAdminBusy] = useState(false);
  const [aoiFile, setAoiFile] = useState("");
  const [aoiPreviewSource, setAoiPreviewSource] = useState<AoiPreviewSource | null>(null);
  const [aoiDragDepth, setAoiDragDepth] = useState(0);
  const [aoiFeaturePreview, setAoiFeaturePreview] = useState<AoiPreviewOk | null>(null);
  const [aoiFeaturePickerOpen, setAoiFeaturePickerOpen] = useState(false);
  const [aoiFeatureNameField, setAoiFeatureNameField] = useState("");
  const [aoiFeatureFilter, setAoiFeatureFilter] = useState("");
  const [selectedAoiFeatureIds, setSelectedAoiFeatureIds] = useState<Set<string>>(() => new Set());
  const [aoiDownloadMode, setAoiDownloadMode] = useState<"merge" | "split">("merge");
  const [boundAoiName, setBoundAoiName] = useState("");
  const [boundAoiFeatureCount, setBoundAoiFeatureCount] = useState(0);
  const [aoiPreviewGeometry, setAoiPreviewGeometry] = useState<Json | null>(null);
  const [focusBbox, setFocusBbox] = useState<Bbox | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [selectedDownloadSceneIds, setSelectedDownloadSceneIds] = useState<Set<string>>(() => new Set());
  const [selectedOrbitSceneIds, setSelectedOrbitSceneIds] = useState<Set<string>>(() => new Set());
  const [asfTaskScenes, setAsfTaskScenes] = useState<SceneRow[]>([]);
  const [activeAsfTaskScenes, setActiveAsfTaskScenes] = useState<SceneRow[]>([]);
  const [asfTaskSnapshots, setAsfTaskSnapshots] = useState<Record<string, SceneTaskSnapshot>>({});
  const [activeAsfTaskSnapshotId, setActiveAsfTaskSnapshotId] = useState("");
  const [pendingAsfTasks, setPendingAsfTasks] = useState<PendingSceneDownloadTask[]>([]);
  const [orbitTaskScenes, setOrbitTaskScenes] = useState<SceneRow[]>([]);
  const [orbitTaskSnapshots, setOrbitTaskSnapshots] = useState<Record<string, SceneTaskSnapshot>>({});
  const [activeOrbitTaskSnapshotId, setActiveOrbitTaskSnapshotId] = useState("");
  const [hoveredSceneId, setHoveredSceneId] = useState<string | null>(null);
  const [sceneMetaCardPos, setSceneMetaCardPos] = useState<{ x: number; y: number } | null>(null);
  const [sceneWorkspaceOpen, setSceneWorkspaceOpen] = useState(false);
  const [orbitWorkspaceOpen, setOrbitWorkspaceOpen] = useState(false);
  const [sceneWorkspaceScope, setSceneWorkspaceScope] = useState<"current" | "task">("current");
  const [orbitWorkspaceScope, setOrbitWorkspaceScope] = useState<"current" | "task">("current");
  const [workspaceTop, setWorkspaceTop] = useState<"scene" | "orbit">("scene");
  const sceneWorkspaceScrollTop = useRef(0);
  const orbitWorkspaceScrollTop = useRef(0);
  const [sentinelSourceMode, setSentinelSourceMode] = useState<"online" | "local">("online");
  const [demSourceMode, setDemSourceMode] = useState<"online" | "local">("online");
  const [orbitSourceMode, setOrbitSourceMode] = useState<"online" | "local">("online");
  const [sceneWorkspaceQuery, setSceneWorkspaceQuery] = useState("");
  const [orbitWorkspaceQuery, setOrbitWorkspaceQuery] = useState("");

  const [asfStartBusy, setAsfStartBusy] = useState(false);
  const [asfError, setAsfError] = useState<string | null>(null);
  const [asfSearchProduct, setAsfSearchProduct] = useState("SLC");
  const [asfSearchStart, setAsfSearchStart] = useState("");
  const [asfSearchEnd, setAsfSearchEnd] = useState("");
  const [asfSearchOrbit, setAsfSearchOrbit] = useState<string[]>([]);
  const [asfSearchRelativeOrbitStart, setAsfSearchRelativeOrbitStart] = useState("");
  const [asfSearchRelativeOrbitEnd, setAsfSearchRelativeOrbitEnd] = useState("");
  const [asfSearchFrameStart, setAsfSearchFrameStart] = useState("");
  const [asfSearchFrameEnd, setAsfSearchFrameEnd] = useState("");
  const [asfSearchMax, setAsfSearchMax] = useState("");
  const [asfConcurrency, setAsfConcurrency] = useState("2");
  const [orbitConcurrency, setOrbitConcurrency] = useState("10");
  const [asfUseProductSubdir, setAsfUseProductSubdir] = useState(false);
  const [orbitUseSubdir, setOrbitUseSubdir] = useState(false);
  const [asfSearchBusy, setAsfSearchBusy] = useState(false);
  const [asfSearchCancelPending, setAsfSearchCancelPending] = useState(false);
  const [asfSearchError, setAsfSearchError] = useState<string | null>(null);
  const [metadataStatus, setMetadataStatus] = useState<MetadataStatus | null>(null);
  const [asfSearchBeam, setAsfSearchBeam] = useState<string[]>([]);
  const [asfSearchPolarization, setAsfSearchPolarization] = useState<string[]>([]);
  const [asfFilterMenuOpen, setAsfFilterMenuOpen] = useState<"orbit" | "beam" | "polarization" | null>(null);
  const [dlStatus, setDlStatus] = useState<DownloadStatus | null>(null);

  const [orbitStartBusy, setOrbitStartBusy] = useState(false);
  const [orbitError, setOrbitError] = useState<string | null>(null);
  const [orbitStatus, setOrbitStatus] = useState<OrbitDownloadStatus | null>(null);
  const [demStatus, setDemStatus] = useState<DemDownloadStatus | null>(null);
  const [asfStopping, setAsfStopping] = useState(false);
  const [demStopping, setDemStopping] = useState(false);

  const [dataset, setDataset] = useState("COP30");
  const [demWest, setDemWest] = useState("");
  const [demEast, setDemEast] = useState("");
  const [demSouth, setDemSouth] = useState("");
  const [demNorth, setDemNorth] = useState("");
  const [demRun, setDemRun] = useState<RunSummaryOk | null>(null);
  const [demRunSource, setDemRunSource] = useState<"download" | "download-only" | "local-ellipsoid" | "local-sarscape" | null>(null);
  const [demDownloadAction, setDemDownloadAction] = useState<"download-only" | "download-convert" | null>(null);
  const [localDemAction, setLocalDemAction] = useState<"ellipsoid" | "sarscape" | null>(null);
  const [demError, setDemError] = useState<string | null>(null);
  const [localDem, setLocalDem] = useState("");
  const [localDatum, setLocalDatum] = useState("auto");
  const [localDemPreview, setLocalDemPreview] = useState<{ auto: ConversionAuto; plan?: Json; detected?: Json } | null>(null);
  const [localDemPreviewBusy, setLocalDemPreviewBusy] = useState(false);
  const [localDemPreviewError, setLocalDemPreviewError] = useState<string | null>(null);

  const [gacosBusy, setGacosBusy] = useState(false);
  const [gacosPlan, setGacosPlan] = useState<Json | null>(null);
  const [gacosError, setGacosError] = useState<string | null>(null);

  const [creds, setCreds] = useState<CredentialStatus | null>(null);
  const [earthToken, setEarthToken] = useState("");
  const [earthUser, setEarthUser] = useState("");
  const [earthPassword, setEarthPassword] = useState("");
  const [earthCredentialMode, setEarthCredentialMode] = useState<"token" | "login">("token");
  const [showEarthToken, setShowEarthToken] = useState(false);
  const [showEarthPassword, setShowEarthPassword] = useState(false);
  const [showOpentopoKey, setShowOpentopoKey] = useState(false);
  const [showTiandituKey, setShowTiandituKey] = useState(false);
  const [opentopoKey, setOpentopoKey] = useState("");
  const [gacosEmail, setGacosEmail] = useState("");
  const [credBusy, setCredBusy] = useState<string | null>(null);
  const [credError, setCredError] = useState<string | null>(null);
  const [credNote, setCredNote] = useState<string | null>(null);
  const [earthdataAuth, setEarthdataAuth] = useState<EarthdataAuthCheck | null>(null);
  const [earthdataAuthChecking, setEarthdataAuthChecking] = useState(false);
  const earthdataAuthInFlight = useRef(false);
  const earthdataAuthRetryAfter = useRef(0);
  const [network, setNetwork] = useState<NetworkSettings | null>(null);
  const [networkBusy, setNetworkBusy] = useState(false);
  const [networkError, setNetworkError] = useState<string | null>(null);
  const [networkNote, setNetworkNote] = useState<string | null>(null);
  const [downloadArchive, setDownloadArchive] = useState<DownloadArchiveItem[]>(
    () => loadDownloadArchive() as DownloadArchiveItem[],
  );
  const [demQueueTask, setDemQueueTask] = useState<DownloadArchiveItem | null>(null);
  const [archiveLoaded, setArchiveLoaded] = useState(false);
  const archiveLoadedFromBridge = useRef(false);
  const [expandedQueueIds, setExpandedQueueIds] = useState<Set<string>>(() => new Set());
  const [expandedHistoryIds, setExpandedHistoryIds] = useState<Set<string>>(() => new Set());
  const [restoringTaskKeys, setRestoringTaskKeys] = useState<Set<string>>(() => new Set());

  function onSourceTabsWheel(event: WheelEvent<HTMLElement>) {
    const target = event.currentTarget;
    if (target.scrollWidth <= target.clientWidth) return;
    const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    if (!delta) return;
    event.preventDefault();
    target.scrollLeft += delta;
  }

  async function refreshTree() {
    await getTree();
  }

  async function refreshScenes() {
    const res = await listScenes();
    if (res.ok) setScenes(res.scenes);
  }

  async function refreshCredentials() {
    const next = await getCredentialStatus();
    setCreds(next);
    return next;
  }

  async function refreshEarthdataAuth(
    reason: "startup" | "manual" | "timer" | "download" = "manual",
    credentialStatus = creds?.earthdata,
  ): Promise<EarthdataAuthCheck | null> {
    if (reason === "startup" || reason === "manual") {
      setCredError(null);
      setCredNote(null);
    }
    if (!isConfigured(credentialStatus)) {
      const missing: EarthdataAuthCheck = {
        ok: true,
        configured: false,
        status: "missing",
        message: "未保存 Earthdata/ASF 凭据。",
      };
      setEarthdataAuth(missing);
      return missing;
    }
    const now = Date.now();
    if (reason === "manual" && earthdataAuthRetryAfter.current > now) {
      const minutes = Math.ceil((earthdataAuthRetryAfter.current - now) / 60000);
      setCredNote(`上次登录检测未通过，为保护账号已暂停重复检测；请 ${minutes} 分钟后再试，或重新保存正确 Token/密码。`);
      return earthdataAuth;
    }
    if (earthdataAuthInFlight.current) return null;
    earthdataAuthInFlight.current = true;
    setEarthdataAuthChecking(true);
    if (reason !== "timer") {
      setEarthdataAuth({
        ok: true,
        configured: true,
        status: "unknown",
        message: reason === "startup" ? "正在自动检测 Earthdata/ASF 凭据状态..." : "正在检测 Earthdata/ASF 凭据状态...",
      });
    }
    try {
      const res = await checkEarthdataAuth(reason === "manual");
      if (res.ok) {
        setEarthdataAuth(res);
        if (res.configured && res.status !== "valid") {
          earthdataAuthRetryAfter.current = Date.now() + EARTHDATA_AUTH_RETRY_COOLDOWN_MS;
        } else {
          earthdataAuthRetryAfter.current = 0;
        }
        return res;
      }
      setCredError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      return null;
    } catch {
      setEarthdataAuth(null);
      return null;
    } finally {
      earthdataAuthInFlight.current = false;
      setEarthdataAuthChecking(false);
    }
  }

  async function refreshCredentialStatusManually() {
    setCredError(null);
    setCredNote(null);
    const next = await refreshCredentials();
    if (!isConfigured(next.earthdata)) {
      await refreshEarthdataAuth("manual", next.earthdata);
      setCredNote("已刷新本机保存状态；Earthdata/ASF 未保存凭据。");
      return;
    }
    const auth = await refreshEarthdataAuth("manual", next.earthdata);
    if (auth?.status === "valid") {
      setCredNote(`Earthdata/ASF 登录检测通过（${earthdataCredentialSourceLabel(next.earthdata)}）。`);
      return;
    }
    if (auth?.status === "missing") {
      setCredNote("已刷新本机保存状态；Earthdata/ASF 未保存凭据。");
      return;
    }
    if (auth) {
      setCredError(`Earthdata/ASF 登录检测未通过：${auth.message}`);
      return;
    }
    setCredError("Earthdata/ASF 登录检测未完成，请稍后再试。");
  }

  const orbitCandidateScenes = useMemo(
    () => (orbitScenes.length > 0 ? orbitScenes : scenes),
    [orbitScenes, scenes],
  );
  const orbitUsesManualSource = orbitScenes.length > 0;
  const currentSceneBatchKey = useMemo(() => sceneBatchKey(scenes), [scenes]);
  const outputDirBoundToCurrentScenes =
    !!outputDir.trim() && !!currentSceneBatchKey && outputDirSceneKey === currentSceneBatchKey;

  function updateTaskOutputDir(value: string) {
    setOutputDir(value);
    setOutputDirSceneKey(value.trim() && currentSceneBatchKey ? currentSceneBatchKey : "");
  }

  function invalidateTaskOutputForNewScenes() {
    setOutputDirSceneKey("");
  }

  useEffect(() => {
    setSelectedDownloadSceneIds((previous) => {
      const ids = scenes.map((scene) => scene.scene_id).filter(Boolean);
      if (!ids.length) return new Set();
      const kept = ids.filter((id) => previous.has(id));
      return new Set(kept.length ? kept : ids);
    });
  }, [scenes]);

  useEffect(() => {
    setSelectedOrbitSceneIds((previous) => {
      const ids = orbitCandidateScenes.map((scene) => scene.scene_id).filter(Boolean);
      if (!ids.length) return new Set();
      const kept = ids.filter((id) => previous.has(id));
      return new Set(kept.length ? kept : ids);
    });
  }, [orbitCandidateScenes]);

  async function refreshNetwork() {
    setNetwork(await getNetworkSettings());
  }

  async function refreshComponents(refresh = false) {
    const res = await getComponentStatus(refresh);
    if (res.ok) {
      setComponentStatus(res);
      return res;
    }
    setComponentNote(formatBridgeError(res));
    return null;
  }

  function openSettingsComponents() {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("insar.section.settings-updates-components", "open");
    }
    setPanel("settings");
    setSettingsComponentsOpenSignal((value) => value + 1);
    void refreshComponents(true);
  }

  async function refreshDownloadArchive() {
    const bridged = hasBridge();
    try {
      const res = await getDownloadArchive();
      if (res.ok) {
        if (bridged) archiveLoadedFromBridge.current = true;
        const legacy = loadDownloadArchive() as DownloadArchiveItem[];
        const merged = [...res.items, ...legacy].reduce<DownloadArchiveItem[]>((acc, item) => {
          if (!acc.some((existing) => archiveTaskKey(existing) === archiveTaskKey(item))) acc.push(item);
          return acc;
        }, []);
        setDownloadArchive(normaliseArchiveForStartup(merged).slice(0, 40));
      }
    } catch {
      setDownloadArchive(normaliseArchiveForStartup(loadDownloadArchive() as DownloadArchiveItem[]).slice(0, 40));
    } finally {
      setArchiveLoaded(true);
    }
  }

  function startWorkbenchTour() {
    setPanel("settings");
    setAoiToolsOpen(false);
    setTourSignal((value) => value + 1);
  }

  const handleTourStepChange = useCallback((index: number) => {
    setAoiToolsOpen(false);
    if (index === 1 || index === 7) {
      setPanel("settings");
      return;
    }
    if (index === 2 || index === 3 || index === 4 || index === 5) {
      setSource("sentinel1");
      setPanel("resources");
      return;
    }
    if (index === 6) {
      setPanel("downloads");
    }
  }, []);

  useEffect(() => {
    void getAppInfo().then((info) => setAppInfo(info));
    void refreshTree();
    void refreshScenes();
    void refreshCredentials().then((next) => refreshEarthdataAuth("startup", next.earthdata));
    void refreshNetwork();
    void refreshComponents(false);
    void refreshDownloadArchive();
    let disposed = false;
    void getUiFlags().then(async (res) => {
      if (disposed) return;
      if (!res.ok || res.flags[WORKBENCH_TOUR_FLAG]) return;
      const saved = await setUiFlag(WORKBENCH_TOUR_FLAG, true);
      if (disposed || !saved.ok) return;
      setTourAutoStart(true);
    });
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    const reloadFromBridge = () => {
      void refreshTree();
      void refreshScenes();
      void refreshCredentials().then((next) => refreshEarthdataAuth("startup", next.earthdata));
      void refreshNetwork();
      void refreshComponents(false);
      void refreshDownloadArchive();
    };
    window.addEventListener("insar-context-changed", reloadFromBridge);
    return () => window.removeEventListener("insar-context-changed", reloadFromBridge);
  }, []);

  useEffect(() => {
    const status = creds?.earthdata ?? "";
    if (status.startsWith("login:")) setEarthCredentialMode("login");
    else if (status === "token") setEarthCredentialMode("token");
  }, [creds?.earthdata]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const frame = window.requestAnimationFrame(() => {
      const el = sidebarScrollRef.current;
      if (el) el.scrollTop = sidebarScrollPositions.current[sidebarScrollKey] ?? 0;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [sidebarScrollKey]);

  useEffect(() => {
    if (!archiveLoaded) return;
    const cleanedArchive = dedupeArchiveItems(downloadArchive).slice(0, 40);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(DOWNLOAD_ARCHIVE_KEY, JSON.stringify(cleanedArchive));
    }
    if (hasBridge() && archiveLoadedFromBridge.current) {
      void saveDownloadArchive(cleanedArchive);
    }
  }, [archiveLoaded, downloadArchive]);

  useEffect(() => {
    let mounted = true;
    let timer: number | undefined;
    async function checkUpdate() {
      try {
        const res = await checkForUpdate(false);
        if (mounted && res.ok && res.update_available) {
          setUpdateInfo(res);
          if (!updatePromptAlreadyDismissed(res.latest_version)) setUpdateDialogOpen(true);
        }
      } catch {
        // Update checks are best-effort and must never disturb startup.
      }
    }
    void checkUpdate();
    if (typeof window !== "undefined") {
      timer = window.setInterval(() => {
        void checkUpdate();
      }, 60 * 60 * 1000);
    }
    return () => {
      mounted = false;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!isConfigured(creds?.earthdata)) return;
    if (earthdataAuth && earthdataAuth.status !== "valid") return;
    const id = window.setInterval(() => {
      void refreshEarthdataAuth("timer", creds?.earthdata);
    }, EARTHDATA_AUTH_TIMER_MS);
    return () => window.clearInterval(id);
  }, [creds?.earthdata, earthdataAuth?.status]);

  useEffect(() => {
    void refreshScenes();
  }, [ctx?.region?.region_id, ctx?.region?.scene_count]);

  useEffect(() => {
    setAoiPreviewGeometry(null);
    setFocusBbox(null);
    setSelectedAdminBoundary(null);
    setBoundAoiName("");
    setAoiToolsOpen(false);
  }, [ctx?.region?.region_id]);

  useEffect(() => {
    let alive = true;
    async function loadAdminOptions() {
      const res = await getAdminOptions(adminProvince, adminCity);
      if (!alive) return;
      if (res.ok) {
        setAdminOptions({
          provinces: uniqueOptions(res.provinces),
          cities: uniqueOptions(res.cities),
          districts: uniqueOptions(res.districts),
        });
      }
    }
    void loadAdminOptions();
    return () => {
      alive = false;
    };
  }, [adminCity, adminProvince]);

  useEffect(() => {
    const next = ctx?.region?.bbox ?? ctx?.region?.scene_footprint_bbox;
    if (!next) return;
    setDemWest(String(next.west));
    setDemEast(String(next.east));
    setDemSouth(String(next.south));
    setDemNorth(String(next.north));
  }, [
    ctx?.region?.bbox?.east,
    ctx?.region?.bbox?.north,
    ctx?.region?.bbox?.south,
    ctx?.region?.bbox?.west,
    ctx?.region?.scene_footprint_bbox?.east,
    ctx?.region?.scene_footprint_bbox?.north,
    ctx?.region?.scene_footprint_bbox?.south,
    ctx?.region?.scene_footprint_bbox?.west,
  ]);

  useEffect(() => {
    let mounted = true;
    async function poll() {
      const [downloadResult, orbitResult, demResult] = await Promise.allSettled([
        getDownloadStatus(),
        getOrbitDownloadStatus(),
        getDemDownloadStatus(),
      ]);
      if (!mounted) return;
      if (downloadResult.status === "fulfilled") {
        const download = downloadResult.value;
        setDlStatus(download);
        if (download.cancelled || (download.state !== "running" && download.state !== "paused")) setAsfStopping(false);
      }
      if (orbitResult.status === "fulfilled") setOrbitStatus(orbitResult.value);
      if (demResult.status === "fulfilled") {
        const dem = demResult.value;
        setDemStatus(dem);
        if (dem.cancelled || dem.state !== "running") setDemStopping(false);
      }
    }
    void poll();
    const id = window.setInterval(poll, 1000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!asfSearchBusy && !sceneBusy) return;
    let mounted = true;
    async function pollMetadata() {
      try {
        const next = await getMetadataStatus();
        if (mounted) setMetadataStatus(next);
      } catch {
        // Metadata progress is informative; the main search/import call owns errors.
      }
    }
    void pollMetadata();
    const id = window.setInterval(pollMetadata, 350);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, [asfSearchBusy, sceneBusy]);

  const resolvedOutputDir = useMemo(() => outputDir.trim(), [outputDir]);
  const resolvedDemDownloadOutputDir = useMemo(() => demDownloadOutputDir.trim(), [demDownloadOutputDir]);
  const resolvedLocalDemOutputDir = useMemo(() => localDemOutputDir.trim(), [localDemOutputDir]);
  const inferredLocalDemOutputDir = useMemo(() => (localDem.trim() ? pathDirName(localDem) : ""), [localDem]);
  const effectiveLocalDemOutputDir = resolvedLocalDemOutputDir || inferredLocalDemOutputDir;
  const localDemSourceDatum = localDatum === "auto" ? localDemPreview?.auto.source : localDatum;
  const localDemAlreadyEllipsoidal = localDemSourceDatum === "WGS84_ELLIPSOID";
  const localDemSourceUnknown =
    !!localDem.trim() && !localDemPreviewBusy && localDatum === "auto" && localDemSourceDatum === "UNKNOWN";
  const localDemActionBlocked = !!localDemPreviewError || localDemSourceUnknown || localDemPreviewBusy;
  const localDemNeedsConversion = !!localDem && !!localDemPreview?.auto.requires_conversion && !localDemAlreadyEllipsoidal;
  const selectedDemAlreadyEllipsoidal = dataset.toUpperCase().endsWith("_ELLIPSOIDAL");

  const mapBbox = focusBbox ?? activeBbox(ctx);
  const manualDemBbox: Bbox = {
    west: asNumber(demWest, DEFAULT_BBOX.west),
    east: asNumber(demEast, DEFAULT_BBOX.east),
    south: asNumber(demSouth, DEFAULT_BBOX.south),
    north: asNumber(demNorth, DEFAULT_BBOX.north),
    crs: "EPSG:4326",
  };
  const manualBboxReady =
    [demWest, demEast, demSouth, demNorth].every((value) => value.trim()) &&
    asNumber(demWest, Number.NaN) < asNumber(demEast, Number.NaN) &&
    asNumber(demSouth, Number.NaN) < asNumber(demNorth, Number.NaN);
  const issues = (checkReport?.issues as Json[] | undefined) ?? [];
  const earthdataConfigured = isConfigured(creds?.earthdata);
  const earthdataInvalid =
    earthdataConfigured &&
    (earthdataAuth?.status === "expired" || earthdataAuth?.status === "invalid");
  const earthdataAuthValid = earthdataConfigured && earthdataAuth?.status === "valid";
  const earthdataAuthProblem =
    earthdataConfigured &&
    !!earthdataAuth?.configured &&
    !["valid", "unknown"].includes(earthdataAuth.status);
  const earthdataCanDownload = earthdataConfigured && !earthdataInvalid;

  useEffect(() => {
    const input = localDem.trim();
    if (!input) {
      setLocalDemPreview(null);
      setLocalDemPreviewError(null);
      setLocalDemPreviewBusy(false);
      return;
    }
    let cancelled = false;
    setLocalDemPreviewBusy(true);
    setLocalDemPreviewError(null);
    const id = window.setTimeout(() => {
      void planLocalDemConversion(input, effectiveLocalDemOutputDir, localDatum)
        .then((res) => {
          if (cancelled) return;
          if (res.ok) {
            setLocalDemPreview({ auto: res.auto, plan: res.plan, detected: (res as { detected?: Json }).detected });
            setLocalDemPreviewError(null);
          } else {
            setLocalDemPreview(null);
            setLocalDemPreviewError(compactDemLogText(`${res.error}${res.code ? ` (${res.code})` : ""}`));
          }
        })
        .catch((error) => {
          if (!cancelled) {
            setLocalDemPreview(null);
            setLocalDemPreviewError(compactDemLogText(formatBridgeError(error)));
          }
        })
        .finally(() => {
          if (!cancelled) setLocalDemPreviewBusy(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [effectiveLocalDemOutputDir, localDatum, localDem]);
  const opentopoConfigured = isConfigured(creds?.opentopography);
  const gacosConfigured = isConfigured(creds?.gacos);
  const asfDownloadStatuses = useMemo(
    () =>
      dlStatus?.asf_tasks?.length
        ? dlStatus.asf_tasks
        : dlStatus && dlStatus.state !== "idle"
          ? [dlStatus]
          : [],
    [dlStatus],
  );
  const dlBusy = asfDownloadStatuses.some((status) => status.state === "running" || status.state === "paused");
  const dlActive = asfDownloadStatuses.some(
    (status) => !status.cancelled && (status.state === "running" || status.state === "paused"),
  );
  const dlPendingStop = asfDownloadStatuses.some(
    (status) => Boolean(status.cancelled && (status.state === "running" || status.state === "paused")),
  );
  const dlVisible = asfDownloadStatuses.length > 0;
  const orbitActive = !orbitStatus?.cancelled && (orbitStatus?.state === "running" || orbitStatus?.state === "paused");
  const demActive = !demStatus?.cancelled && demStatus?.state === "running";
  const demDownloadBusy = demDownloadAction !== null || demActive;
  const activeDownloadTaskCount =
    asfDownloadStatuses.filter((status) => status.state === "running" || status.state === "paused").length +
    (orbitActive ? 1 : 0) +
    (demActive ? 1 : 0);
  const transferredBytes = (dlStatus?.done_bytes ?? 0) + (dlStatus?.current_bytes ?? 0);
  const dlPct = dlStatus?.total_bytes
    ? Math.round((transferredBytes / dlStatus.total_bytes) * 100)
    : dlStatus && dlStatus.total > 0
      ? Math.round((dlStatus.done / dlStatus.total) * 100)
      : 0;
  const currentPct = dlStatus?.current_expected_size
    ? Math.round(((dlStatus.current_bytes ?? 0) / dlStatus.current_expected_size) * 100)
    : 0;
  const activeAsfDownloads = asfDownloadStatuses.flatMap((status) =>
    status.active_downloads?.length
      ? status.active_downloads
      : status.current_scene
        ? [
            {
              scene_id: status.current_scene,
              bytes: status.current_bytes ?? 0,
              expected_size: status.current_expected_size,
            },
          ]
        : [],
  );
  const activeAsfSceneIds = useMemo(
    () => new Set(activeAsfDownloads.map((item) => item.scene_id).filter(Boolean)),
    [activeAsfDownloads],
  );
  const pausedAsfSceneIds = useMemo(
    () => new Set(asfDownloadStatuses.flatMap((status) => status.paused_scene_ids ?? [])),
    [asfDownloadStatuses],
  );
  useEffect(() => {
    const nextTask = pendingAsfTasks.find((task) => task.status === "pending");
    if (!nextTask || dlPendingStop) return;
    void startQueuedAsfTask(nextTask);
  }, [dlBusy, dlPendingStop, pendingAsfTasks]);
  const orbitPct =
    orbitStatus && orbitStatus.total > 0 ? Math.round((orbitStatus.done / orbitStatus.total) * 100) : 0;
  const activeOrbitDownloads = orbitStatus?.active_scenes?.length
    ? orbitStatus.active_scenes
    : orbitStatus?.current_scene
      ? [{ scene_id: orbitStatus.current_scene }]
      : [];
  const archiveableStates = new Set(["finished", "failed", "cancelled", "interrupted", "timeout"]);
  const tiandituToken = network?.tianditu_token ?? "";
  const mapAoiGeometry = aoiPreviewGeometry ?? ctx?.region?.aoi_geojson;
  const currentAoiName = boundAoiName || selectedAdminBoundary?.label || ctx?.region?.name || "当前 AOI";
  const adminProvinceOptions = useMemo(
    () => withAllOption(adminOptions.provinces.length ? adminOptions.provinces : CHINA_PROVINCES),
    [adminOptions.provinces],
  );
  const adminCityOptions = useMemo(() => {
    if (adminProvince === "全部") return ["全部"];
    const preset = ADMIN_PRESETS[adminProvince];
    return withAllOption(adminOptions.cities.length ? adminOptions.cities : (preset?.cities ?? []));
  }, [adminOptions.cities, adminProvince]);
  const adminDistrictOptions = useMemo(() => {
    if (adminProvince === "全部") return ["全部"];
    const preset = ADMIN_PRESETS[adminProvince];
    return withAllOption(adminOptions.districts.length ? adminOptions.districts : ((preset?.districts ?? {})[adminCity] ?? []));
  }, [adminCity, adminOptions.districts, adminProvince]);
  const displayedAoiFeatureField = aoiFeatureNameField || aoiFeaturePreview?.display_field || "";
  const filteredAoiFeatures = useMemo(() => {
    const features = aoiFeaturePreview?.features ?? [];
    const query = aoiFeatureFilter.trim().toLowerCase();
    if (!query) return features;
    return features.filter((feature) => {
      const fieldValue = displayedAoiFeatureField
        ? String(feature.properties?.[displayedAoiFeatureField] ?? "")
        : "";
      const haystack = [
        feature.name,
        fieldValue,
        feature.index,
        feature.source_index,
        ...Object.values(feature.properties ?? {}),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [aoiFeatureFilter, aoiFeaturePreview?.features, displayedAoiFeatureField]);
  const selectedAoiFeatures = useMemo(
    () => (aoiFeaturePreview?.features ?? []).filter((feature) => selectedAoiFeatureIds.has(feature.id)),
    [aoiFeaturePreview?.features, selectedAoiFeatureIds],
  );
  const selectedAoiAreaKm2 = useMemo(
    () => selectedAoiFeatures.reduce((sum, feature) => sum + Number(feature.area_km2 || 0), 0),
    [selectedAoiFeatures],
  );
  const activeAoiFeatureCount = useMemo(() => {
    if (boundAoiFeatureCount > 1) return boundAoiFeatureCount;
    return 0;
  }, [boundAoiFeatureCount]);
  const hoveredScene = useMemo(
    () =>
      [...scenes, ...orbitCandidateScenes, ...asfTaskScenes, ...orbitTaskScenes].find((scene) => scene.scene_id === hoveredSceneId) ?? null,
    [asfTaskScenes, hoveredSceneId, orbitCandidateScenes, orbitTaskScenes, scenes],
  );
  const sceneWorkspaceSourceScenes =
    sceneWorkspaceScope === "task" && activeAsfTaskSnapshotId && asfTaskSnapshots[activeAsfTaskSnapshotId]
      ? asfTaskSnapshots[activeAsfTaskSnapshotId].scenes
      : sceneWorkspaceScope === "task" && asfTaskScenes.length > 0
        ? asfTaskScenes
        : scenes;
  const activeSceneTaskSnapshot =
    sceneWorkspaceScope === "task" && activeAsfTaskSnapshotId ? asfTaskSnapshots[activeAsfTaskSnapshotId] : null;
  const sceneWorkspaceSnapshotTitle = activeSceneTaskSnapshot?.title || "任务快照";
  const sceneWorkspaceAoiName = activeSceneTaskSnapshot?.aoiName || currentAoiName;
  const activeOrbitTaskSnapshot =
    orbitWorkspaceScope === "task" && activeOrbitTaskSnapshotId ? orbitTaskSnapshots[activeOrbitTaskSnapshotId] : null;
  const orbitWorkspaceSourceScenes =
    activeOrbitTaskSnapshot?.scenes ??
    (orbitWorkspaceScope === "task" && orbitTaskScenes.length > 0 ? orbitTaskScenes : orbitCandidateScenes);
  const orbitWorkspaceSnapshotTitle = activeOrbitTaskSnapshot?.title || "任务快照";
  const orbitWorkspaceAoiName = activeOrbitTaskSnapshot?.aoiName || currentAoiName;
  const visibleMapScenes = source === "orbit" ? orbitWorkspaceSourceScenes : scenes;
  const filteredSceneWorkspaceScenes = useMemo(
    () => sceneWorkspaceSourceScenes.filter((scene) => sceneMatchesQuery(scene, sceneWorkspaceQuery)),
    [sceneWorkspaceQuery, sceneWorkspaceSourceScenes],
  );
  const filteredOrbitWorkspaceScenes = useMemo(
    () => orbitWorkspaceSourceScenes.filter((scene) => sceneMatchesQuery(scene, orbitWorkspaceQuery)),
    [orbitWorkspaceQuery, orbitWorkspaceSourceScenes],
  );
  const sceneResultVirtual = useVirtualRows(scenes, 104);
  const sceneWorkspaceVirtual = useVirtualRows(filteredSceneWorkspaceScenes, 68, 8, sceneWorkspaceScrollTop.current);
  const orbitWorkspaceVirtual = useVirtualRows(filteredOrbitWorkspaceScenes, 68, 8, orbitWorkspaceScrollTop.current);
  const selectedDownloadScenes = useMemo(
    () => sceneWorkspaceSourceScenes.filter((scene) => selectedDownloadSceneIds.has(scene.scene_id)),
    [sceneWorkspaceSourceScenes, selectedDownloadSceneIds],
  );
  const selectedDownloadSceneIdList = useMemo(
    () => selectedDownloadScenes.map((scene) => scene.scene_id),
    [selectedDownloadScenes],
  );
  const selectedOrbitScenes = useMemo(
    () => orbitWorkspaceSourceScenes.filter((scene) => selectedOrbitSceneIds.has(scene.scene_id)),
    [orbitWorkspaceSourceScenes, selectedOrbitSceneIds],
  );
  const selectedOrbitSceneIdList = useMemo(
    () => selectedOrbitScenes.map((scene) => scene.scene_id),
    [selectedOrbitScenes],
  );
  useEffect(() => {
    if (orbitWorkspaceScope !== "task") return;
    const ids = orbitWorkspaceSourceScenes.map((scene) => scene.scene_id).filter(Boolean);
    setSelectedOrbitSceneIds((previous) => {
      const kept = ids.filter((id) => previous.has(id));
      return new Set(kept.length ? kept : ids);
    });
  }, [orbitWorkspaceScope, orbitWorkspaceSourceScenes]);

  function selectAllDownloadScenes() {
    setSelectedDownloadSceneIds(new Set(sceneWorkspaceSourceScenes.map((scene) => scene.scene_id).filter(Boolean)));
  }

  function clearDownloadSceneSelection() {
    setSelectedDownloadSceneIds(new Set());
  }

  function toggleDownloadScene(sceneId: string, checked?: boolean) {
    setSelectedDownloadSceneIds((previous) => {
      const next = new Set(previous);
      const shouldSelect = checked ?? !next.has(sceneId);
      if (shouldSelect) next.add(sceneId);
      else next.delete(sceneId);
      return next;
    });
  }

  function selectAllOrbitScenes() {
    setSelectedOrbitSceneIds(new Set(orbitWorkspaceSourceScenes.map((scene) => scene.scene_id).filter(Boolean)));
  }

  function clearOrbitSceneSelection() {
    setSelectedOrbitSceneIds(new Set());
  }

  function toggleOrbitScene(sceneId: string, checked?: boolean) {
    setSelectedOrbitSceneIds((previous) => {
      const next = new Set(previous);
      const shouldSelect = checked ?? !next.has(sceneId);
      if (shouldSelect) next.add(sceneId);
      else next.delete(sceneId);
      return next;
    });
  }

  function highlightScene(sceneId: string | null) {
    setSelectedSceneId(sceneId);
  }

  function openSceneWorkspace(scope: "current" | "task" = "current") {
    setOrbitWorkspaceOpen(false);
    setSceneWorkspaceScope(scope);
    setSceneWorkspaceOpen(true);
    setWorkspaceTop("scene");
  }

  function closeSceneWorkspace() {
    setSceneWorkspaceOpen(false);
  }

  function openOrbitWorkspace(scope: "current" | "task" = "current") {
    setSceneWorkspaceOpen(false);
    setOrbitWorkspaceScope(scope);
    setOrbitWorkspaceOpen(true);
    setWorkspaceTop("orbit");
  }

  function closeOrbitWorkspace() {
    setOrbitWorkspaceOpen(false);
  }

  function onSceneWorkspaceScroll(event: UIEvent<HTMLDivElement>) {
    sceneWorkspaceScrollTop.current = event.currentTarget.scrollTop;
    sceneWorkspaceVirtual.onScroll(event);
  }

  function onOrbitWorkspaceScroll(event: UIEvent<HTMLDivElement>) {
    orbitWorkspaceScrollTop.current = event.currentTarget.scrollTop;
    orbitWorkspaceVirtual.onScroll(event);
  }

  function showSceneMetaCard(sceneId: string, event: MouseEvent<HTMLElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    setHoveredSceneId(sceneId);
    setSceneMetaCardPos({
      x: Math.max(16, Math.min(rect.right + 10, window.innerWidth - 380)),
      y: Math.max(16, Math.min(rect.top - 8, window.innerHeight - 280)),
    });
  }

  function hideSceneMetaCard() {
    setHoveredSceneId(null);
    setSceneMetaCardPos(null);
  }

  function copySceneMetadata(scene: SceneRow) {
    const done = () => setSceneNote(`已复制元数据：${scene.scene_id}`);
    const writer = navigator.clipboard?.writeText?.(sceneMetadataText(scene));
    if (writer) void writer.then(done).catch(done);
    else done();
  }

  function renderSceneMetaHoverCard() {
    if (!hoveredScene || !sceneMetaCardPos) return null;
    return (
      <div
        className="pointer-events-none fixed z-[900]"
        style={{ left: sceneMetaCardPos.x, top: sceneMetaCardPos.y }}
      >
        <SceneMetaCard scene={hoveredScene} />
      </div>
    );
  }

  function rememberTask(item: Omit<DownloadArchiveItem, "ts"> & { ts?: number }) {
    if (item.status === "running" || item.status === "paused") return;
    setDownloadArchive((prev) => {
      const itemKey = archiveTaskKey(item as DownloadArchiveItem);
      const previous = prev.find((task) => archiveTaskKey(task) === itemKey);
      const logs = (item.logs ?? previous?.logs ?? []).slice(-120);
      const sameLogs = JSON.stringify(previous?.logs ?? []) === JSON.stringify(logs);
      if (previous && previous.status === item.status && previous.detail === item.detail && sameLogs) {
        return dedupeArchiveItems(prev);
      }
      const next = prev.filter((task) => archiveTaskKey(task) !== itemKey);
      const keepPausedTime = previous && previous.status === "paused" && item.status === "paused";
      return dedupeArchiveItems([{ ...item, logs, ts: keepPausedTime ? previous.ts : Date.now() }, ...next]).slice(0, 40);
    });
  }

  useEffect(() => {
    if (!dlStatus) return;
    const archivedState = dlStatus.cancelled ? "cancelled" : dlStatus.state;
    if (!archiveableStates.has(archivedState)) return;
    const activeNames = (dlStatus.active_downloads ?? [])
      .map((item) => item.scene_id)
      .filter(Boolean)
      .slice(0, dlStatus.concurrency || 1)
      .join("；");
    const detail =
      dlStatus.error ||
      dlStatus.summary_line ||
      (activeNames ? `正在下载：${activeNames}` : `${dlStatus.done}/${dlStatus.total}`);
    if (!detail) return;
    rememberTask({
      id: `asf:${dlStatus.results_path || dlStatus.output_dir || "active"}:${dlStatus.total}`,
      name: "Sentinel-1 下载任务",
      status: archivedState,
      detail,
      kind: "asf",
      output_dir: dlStatus.output_dir || dlStatus.results_path || "",
      total: dlStatus.total,
      concurrency: dlStatus.concurrency || Number(asfConcurrency) || 1,
      use_product_subdirs: Boolean(dlStatus.use_product_subdirs),
      download_layout: dlStatus.download_layout || (dlStatus.use_product_subdirs ? "product_subdirs" : "flat"),
      logs: dlStatus.log?.map(formatDownloadLogEntry).filter(Boolean) ?? [],
    });
  }, [
    dlStatus?.active_downloads,
    dlStatus?.cancelled,
    dlStatus?.concurrency,
    dlStatus?.done,
    dlStatus?.error,
    dlStatus?.output_dir,
    dlStatus?.results_path,
    dlStatus?.state,
    dlStatus?.summary_line,
    dlStatus?.total,
    dlStatus?.use_product_subdirs,
    dlStatus?.download_layout,
  ]);

  useEffect(() => {
    if (!orbitStatus) return;
    const archivedState = orbitStatus.cancelled ? "cancelled" : orbitStatus.state;
    if (!archiveableStates.has(archivedState)) return;
    const detail =
      orbitStatus.error ||
      orbitStatus.summary_line ||
      (orbitStatus.current_scene
        ? `正在处理：${orbitStatus.current_scene}`
        : `${orbitStatus.done}/${orbitStatus.total}`);
    if (!detail) return;
    rememberTask({
      id: `orbit:${orbitStatus.orbit_dir || "active"}:${orbitStatus.total}`,
      name: "Sentinel-1 精密轨道下载",
      status: archivedState,
      detail,
      kind: "orbit",
      output_dir: orbitStatus.orbit_dir || "",
      total: orbitStatus.total,
      use_orbit_subdir: Boolean(orbitStatus.use_orbit_subdir),
      download_layout: orbitStatus.download_layout || (orbitStatus.use_orbit_subdir ? "orbit_subdir" : "flat"),
      logs: orbitStatus.log?.map(formatDownloadLogEntry).filter(Boolean) ?? [],
    });
  }, [
    orbitStatus?.current_scene,
    orbitStatus?.cancelled,
    orbitStatus?.done,
    orbitStatus?.error,
    orbitStatus?.orbit_dir,
    orbitStatus?.state,
    orbitStatus?.summary_line,
    orbitStatus?.total,
    orbitStatus?.use_orbit_subdir,
    orbitStatus?.download_layout,
  ]);

  useEffect(() => {
    if (!demStatus) return;
    const archivedState = demStatus.cancelled ? "cancelled" : demStatus.state;
    if (!archiveableStates.has(archivedState)) return;
    const out = demStatus.output_dir || "";
    const detail = demStatus.error || demStatus.summary_line || `${demStatus.done}/${demStatus.total}`;
    if (!detail) return;
    setDemRunSource(demStatus.convert ? "download" : "download-only");
    setDemRun({
      ok: true,
      summary_line: compactDemLogText(detail),
      total: demStatus.total || 1,
      succeeded: demStatus.succeeded,
      skipped: demStatus.skipped,
      failed: demStatus.failed,
      interrupted: demStatus.interrupted,
      has_failures: demStatus.has_failures || archivedState !== "finished",
      results_path: demStatus.results_path || "",
      output_dir: out,
      results: demStatus.results ?? [],
      conversion_results_path: demStatus.conversion_results_path || "",
      raw_dem_path: demStatus.raw_dem_path || "",
      ellipsoid_dem_path: demStatus.convert ? demStatus.ellipsoid_dem_path || "" : "",
      sarscape_ready_dem_path: demStatus.convert ? demStatus.sarscape_ready_dem_path || "" : "",
      logs: demStatus.log?.map(formatDownloadLogEntry).filter(Boolean) ?? [],
      task_id: `dem:${out || demStatus.results_path || demStatus.dataset}:${demStatus.total || 1}:${demStatus.dataset}`,
    });
    rememberTask({
      id: `dem:${out || demStatus.results_path || demStatus.dataset}:${demStatus.total || 1}:${demStatus.dataset}`,
      name: demStatus.convert ? "DEM 下载并转换椭球高" : "DEM 下载",
      status: archivedState,
      detail: compactDemLogText(detail),
      kind: "dem",
      output_dir: out,
      total: demStatus.total || 1,
      concurrency: 1,
      logs: demStatus.log?.map(formatDownloadLogEntry).filter(Boolean) ?? [],
    });
  }, [
    demStatus?.cancelled,
    demStatus?.convert,
    demStatus?.dataset,
    demStatus?.done,
    demStatus?.error,
    demStatus?.output_dir,
    demStatus?.results_path,
    demStatus?.state,
    demStatus?.summary_line,
    demStatus?.total,
  ]);

  useEffect(() => {
    if (!demRun) return;
    if (demRunSource !== "local-ellipsoid" && demRunSource !== "local-sarscape") return;
    const outputDir = demRunOutputDir(demRun);
    rememberTask({
      id:
        demRun.task_id ||
        `dem:${outputDir || demRun.results_path || demRun.raw_dem_path || demRun.summary_line}:${demRun.total}:${demRunSource}`,
      name: demRunSource === "local-ellipsoid" ? "本地 DEM 椭球高转换" : "本地 DEM SARscape 转换",
      status: demRun.has_failures ? "failed" : "finished",
      detail: compactDemLogText(demRun.summary_line),
      kind: "dem",
      output_dir: outputDir,
      total: demRun.total,
      logs: demRunLogLines(demRun),
    });
  }, [
    demRun?.conversion_results_path,
    demRun?.ellipsoid_dem_path,
    demRun?.failed,
    demRun?.has_failures,
    demRun?.output_dir,
    demRun?.raw_dem_path,
    demRun?.results_path,
    demRun?.sarscape_ready_dem_path,
    demRun?.summary_line,
    demRun?.task_id,
    demRun?.total,
    demRunSource,
  ]);

  useEffect(() => {
    if (!gacosPlan) return;
    const dates = String((gacosPlan.unique_dates as string[] | undefined)?.length ?? 0);
    rememberTask({
      id: `gacos:${resolvedOutputDir}:${dates}`,
      name: "GACOS 请求规划",
      status: "finished",
      detail: `${dates} 个日期；输出目录 ${resolvedOutputDir || "-"}`,
      logs: [`规划日期数：${dates}`, `输出目录：${resolvedOutputDir || "-"}`],
    });
  }, [gacosPlan, resolvedOutputDir]);

  async function onBrowseOutput() {
    const pick = await pickDirectory("选择本次任务输出目录");
    if (pick.ok && pick.path) updateTaskOutputDir(pick.path);
    return pick.ok && pick.path ? pick.path : "";
  }

  async function onBrowseDemDownloadOutput() {
    const pick = await pickDirectory("选择 DEM 下载输出目录");
    if (pick.ok && pick.path) setDemDownloadOutputDir(pick.path);
    return pick.ok && pick.path ? pick.path : "";
  }

  async function onBrowseLocalDemOutput() {
    const pick = await pickDirectory("选择本地 DEM 转换输出目录");
    if (pick.ok && pick.path) setLocalDemOutputDir(pick.path);
    return pick.ok && pick.path ? pick.path : "";
  }

  async function ensureTaskOutput(forcePick = false) {
    if (!forcePick && resolvedOutputDir && outputDirBoundToCurrentScenes) return resolvedOutputDir;
    const picked = await onBrowseOutput();
    return picked;
  }

  async function ensureDemDownloadOutput() {
    if (resolvedDemDownloadOutputDir) return resolvedDemDownloadOutputDir;
    const picked = await onBrowseDemDownloadOutput();
    return picked;
  }

  async function ensureLocalDemOutput() {
    if (effectiveLocalDemOutputDir) return effectiveLocalDemOutputDir;
    const picked = await onBrowseLocalDemOutput();
    return picked;
  }

  async function bindBbox(bbox: Bbox) {
    setFocusBbox(bbox);
    setAoiPreviewGeometry(null);
    setBoundAoiFeatureCount(0);
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const res = await setRegionAoiBbox(bbox.west, bbox.east, bbox.south, bbox.north);
      if (res.ok) {
        setDrawActive(false);
        setBoundAoiName("手动范围");
        setAoiNote("AOI 已绑定，可用于 ASF 检索和 DEM 范围。");
        await refresh();
        await refreshTree();
      } else {
        setAoiError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setAoiError(formatBridgeError(e));
    } finally {
      setAoiBusy(false);
    }
  }

  async function bindPolygon(ring: [number, number][]) {
    const geometry: Json = { type: "Polygon", coordinates: [ring] };
    setAoiPreviewGeometry(geometry);
    setBoundAoiFeatureCount(0);
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const res = await setRegionAoiGeojson({
        type: "Feature",
        geometry,
      });
      if (res.ok) {
        setDrawActive(false);
        setBoundAoiName("地图绘制 AOI");
        setAoiNote("多边形 AOI 已绑定，可用于 ASF 检索和 DEM 范围。");
        await refresh();
        await refreshTree();
      } else {
        setAoiError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setAoiError(formatBridgeError(e));
    } finally {
      setAoiBusy(false);
    }
  }

  function bindPoint(lat: number, lng: number) {
    const delta = 0.025;
    void bindBbox({
      west: lng - delta,
      east: lng + delta,
      south: lat - delta,
      north: lat + delta,
      crs: "EPSG:4326",
    });
  }

  async function bindAdminBoundary(boundary: AdminBoundary) {
    setSelectedAdminBoundary(boundary);
    setSelectedSceneId(null);
    setFocusBbox(boundary.bbox);
    setAoiPreviewGeometry(boundary.geojson ?? null);
    setBoundAoiFeatureCount(0);
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      let res;
      if (boundary.geojson) {
        const geojsonType =
          boundary.geojson && typeof boundary.geojson === "object" && !Array.isArray(boundary.geojson)
            ? String((boundary.geojson as Record<string, unknown>).type || "")
            : "";
        res =
          geojsonType === "FeatureCollection" || geojsonType === "Feature"
            ? await setRegionAoiGeojson(boundary.geojson)
            : await setRegionAoiGeojson({
                type: "Feature",
                properties: { name: boundary.label },
                geometry: boundary.geojson,
              });
      } else {
        res = await setRegionAoiBbox(boundary.bbox.west, boundary.bbox.east, boundary.bbox.south, boundary.bbox.north);
      }
      if (res.ok) {
        setDrawActive(false);
        setBoundAoiName(boundary.label);
        setAoiPreviewGeometry(res.aoi_geojson ?? boundary.geojson ?? null);
        setDemWest(String(boundary.bbox.west));
        setDemEast(String(boundary.bbox.east));
        setDemSouth(String(boundary.bbox.south));
        setDemNorth(String(boundary.bbox.north));
        setAoiNote(`行政边界已绑定为 AOI：${boundary.label}`);
        await refresh();
        await refreshTree();
      } else {
        setAoiError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setAoiError(formatBridgeError(e));
    } finally {
      setAoiBusy(false);
    }
  }

  async function bindChinaBoundary() {
    setSelectedAdminBoundary({
      label: "全国",
      bbox: CHINA_BBOX,
      geojson: null,
      source: "内置范围",
      class: "boundary",
      type: "administrative",
    });
    setAdminResults([]);
    setAoiPreviewGeometry(null);
    setFocusBbox(CHINA_BBOX);
    setDemWest(String(CHINA_BBOX.west));
    setDemEast(String(CHINA_BBOX.east));
    setDemSouth(String(CHINA_BBOX.south));
    setDemNorth(String(CHINA_BBOX.north));
    await bindBbox(CHINA_BBOX);
    setBoundAoiName("全国");
    setAoiNote("已绑定全国范围 AOI。全国范围仅作为快速检索/下载范围，正式边界建议上传权威面文件。");
  }

  async function onSearchAdminBoundary({
    queryOnly = false,
  }: { queryOnly?: boolean } = {}) {
    setAdminBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const query = adminQuery.trim();
      const searchGlobally = queryOnly && Boolean(query);
      const res = await searchAdminBoundaries(
        query,
        searchGlobally ? "" : adminProvince,
        searchGlobally ? "" : adminCity,
        searchGlobally ? "" : adminDistrict,
        8,
      );
      if (!res.ok) {
        setAoiError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      setAdminResults(res.results);
      if (!res.results.length) {
        setSelectedAdminBoundary(null);
        setAoiError("没有找到可用边界；可以换关键词，或上传 shp/kml/geojson。");
        return;
      }
      setSelectedAdminBoundary(res.results[0]);
      setSelectedSceneId(null);
      setFocusBbox(res.results[0].bbox);
      setAoiPreviewGeometry(res.results[0].geojson ?? null);
      const provider =
        res.provider === "tianditu"
          ? "天地图"
          : res.results[0].source || "备用地名源";
      setAoiNote(
        `${provider} 找到 ${res.results.length} 条边界结果；已定位到第一条。${
          res.warning ? ` ${res.warning}` : ""
        }`,
      );
      await bindAdminBoundary(res.results[0]);
    } catch (e) {
      setAoiError(formatBridgeError(e));
    } finally {
      setAdminBusy(false);
    }
  }

  async function onBrowseAoiFile() {
    const pick = await pickOpenFile("选择 AOI 边界文件", [
      "AOI boundary (*.shp;*.kml;*.kmz;*.geojson;*.json)",
    ]);
    if (pick.ok && pick.path) {
      await loadAoiFileCandidate(pick.path);
      return;
    }
  }

  async function loadAoiFileCandidate(path: string) {
    const nextPath = path.trim().replace(/^file:\/+/, "");
    if (!nextPath) return;
    if (!isSupportedLocalBoundaryPath(nextPath)) {
      setAoiError("仅支持 .shp、.kml、.kmz、.geojson、.json 边界文件。");
      setAoiNote(null);
      return;
    }
    setAoiFile(nextPath);
    setAoiFeaturePickerOpen(false);
    setAoiFeaturePreview(null);
    setAoiPreviewSource(null);
    setSelectedAoiFeatureIds(new Set());
    setAoiFeatureFilter("");
    setAoiError(null);
    await onPreviewAoiFile(nextPath);
  }

  async function onDropAoiFile(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    event.stopPropagation();
    setAoiDragDepth(0);
    const files = Array.from(event.dataTransfer.files ?? []) as Array<File & { path?: string }>;
    const file = files.find((item) => isSupportedLocalBoundaryPath(item.path || item.name || ""));
    if (!file) {
      setAoiError("仅支持 .shp、.kml、.kmz、.geojson、.json 边界文件。");
      setAoiNote(null);
      return;
    }
    const nativePath = String(file.path || "").trim();
    if (nativePath) {
      await loadAoiFileCandidate(nativePath);
      return;
    }
    const fileName = file.name || "boundary";
    const extension = localPathExtension(fileName);
    if (TEXT_BOUNDARY_EXTENSIONS.has(extension)) {
      setAoiBusy(true);
      setAoiError(null);
      setAoiNote(null);
      try {
        const res = await previewAoiFileContent(fileName, await file.text());
        if (!res.ok) {
          setAoiError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
          return;
        }
        if (!res.geojson) {
          setAoiError("已识别边界，但未生成可绑定的边界快照；请使用上传本地边界按钮选择文件。");
          return;
        }
        applyAoiPreviewResult(res, { kind: "geojson", fileName, geojson: res.geojson });
      } catch (e) {
        setAoiError(formatBridgeError(e));
      } finally {
        setAoiBusy(false);
      }
      return;
    }
    if (BINARY_BOUNDARY_EXTENSIONS.has(extension)) {
      if (file.size > MAX_DRAGGED_BINARY_BOUNDARY_BYTES) {
        setAoiError("拖拽边界文件超过 50 MB，请点击“上传本地边界”选择文件。");
        setAoiNote(null);
        return;
      }
      setAoiBusy(true);
      setAoiError(null);
      setAoiNote(null);
      try {
        const res = await previewAoiFileBytes(fileName, await fileToBase64(file));
        if (!res.ok) {
          setAoiError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
          return;
        }
        if (!res.geojson) {
          setAoiError("已识别边界，但未生成可绑定的边界快照；请使用上传本地边界按钮选择文件。");
          return;
        }
        applyAoiPreviewResult(res, { kind: "geojson", fileName, geojson: res.geojson });
      } catch (e) {
        setAoiError(formatBridgeError(e));
      } finally {
        setAoiBusy(false);
      }
      return;
    }
    setAoiError("仅支持 .shp、.kml、.kmz、.geojson、.json 边界文件。");
    setAoiNote(null);
  }

  function onWorkbenchDragEnter(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    setAoiDragDepth((value) => value + 1);
  }

  function onWorkbenchDragOver(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
  }

  function onWorkbenchDragLeave(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    event.stopPropagation();
    setAoiDragDepth((value) => Math.max(0, value - 1));
  }

  async function onPreviewAoiFile(path = aoiFile) {
    if (!path.trim()) {
      setAoiError("请选择 shp/kml/kmz/geojson 边界文件。");
      return;
    }
    if (!isSupportedLocalBoundaryPath(path)) {
      setAoiError("仅支持 .shp、.kml、.kmz、.geojson、.json 边界文件。");
      return;
    }
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const res = await previewAoiFile(path);
      if (!res.ok) {
        setAoiError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      applyAoiPreviewResult(res, { kind: "path", path });
    } catch (e) {
      setAoiError(formatBridgeError(e));
    } finally {
      setAoiBusy(false);
    }
  }

  function applyAoiPreviewResult(res: AoiPreviewOk, sourceInfo: AoiPreviewSource) {
    setAoiFile(sourceInfo.kind === "path" ? sourceInfo.path : sourceInfo.fileName);
    setAoiPreviewSource(sourceInfo);
    setAoiFeaturePreview(res);
    setAoiFeatureNameField(res.display_field || res.fields[0] || "");
    setSelectedAoiFeatureIds(new Set(res.features.map((feature) => feature.id)));
    setAoiFeatureFilter("");
    setAoiFeaturePickerOpen(true);
    setSelectedSceneId(null);
    const nextBbox = unionBboxes(res.features.map((feature) => feature.bbox));
    if (nextBbox) {
      setFocusBbox(nextBbox);
      setDemWest(String(nextBbox.west));
      setDemEast(String(nextBbox.east));
      setDemSouth(String(nextBbox.south));
      setDemNorth(String(nextBbox.north));
    }
    setAoiNote(`已识别 ${res.total_features} 个边界要素，请选择后再绑定 AOI。`);
  }

  async function onApplyAoiFile(path = aoiFile) {
    const sourceInfo = aoiPreviewSource ?? (path.trim() ? { kind: "path" as const, path } : null);
    if (!sourceInfo) {
      setAoiError("请选择 shp/kml/kmz/geojson 边界文件。");
      return;
    }
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const selectedIds = Array.from(selectedAoiFeatureIds);
      const aoiName = localBoundaryAoiName(
        aoiFeaturePreview,
        selectedAoiFeatureIds,
        displayedAoiFeatureField,
        sourceInfo.kind === "path" ? sourceInfo.path : sourceInfo.fileName,
      );
      const res =
        sourceInfo.kind === "geojson"
          ? await setRegionAoiGeojsonFeatures(sourceInfo.geojson, selectedIds, displayedAoiFeatureField, "merge")
          : aoiFeaturePreview && selectedIds.length > 0
            ? await setRegionAoiFileFeatures(sourceInfo.path, selectedIds, displayedAoiFeatureField, "merge")
            : await setRegionAoiFile(sourceInfo.path);
      if (res.ok) {
        setDrawActive(false);
        setSelectedAdminBoundary(null);
        setBoundAoiName(aoiName);
        setAoiFeaturePickerOpen(false);
        setAoiPreviewSource(null);
        setAoiPreviewGeometry(res.aoi_geojson ?? null);
        const nextBbox = (res.aoi as { bbox?: Bbox | null }).bbox ?? null;
        if (nextBbox) {
          setFocusBbox(nextBbox);
          setDemWest(String(nextBbox.west));
          setDemEast(String(nextBbox.east));
          setDemSouth(String(nextBbox.south));
          setDemNorth(String(nextBbox.north));
        }
        const featureCount = Number(res.aoi_feature_count ?? selectedIds.length ?? 0);
        setBoundAoiFeatureCount(featureCount > 1 ? featureCount : 0);
        setAoiNote(
          typeof res.aoi_feature_count === "number" && res.aoi_feature_count > 1
            ? `已导入 ${res.aoi_feature_count} 个边界要素，已合并绑定为 AOI：${res.region_name}`
            : `已从边界文件绑定 AOI：${res.region_name}`,
        );
        await refresh();
        await refreshTree();
      } else {
        setAoiError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setAoiError(formatBridgeError(e));
    } finally {
      setAoiBusy(false);
    }
  }

  async function handleSceneImport(action: () => Promise<ReturnType<typeof importScenesText> extends Promise<infer T> ? T : never>) {
    setSceneBusy(true);
    setSceneError(null);
    setSceneNote(null);
    setMetadataStatus({ ok: true, state: "running", done: 0, total: 1, percent: 0, message: "正在解析影像名称" });
    setCheckReport(null);
    try {
      const res = await action();
      if (res.ok) {
        setScenes(res.scenes);
        invalidateTaskOutputForNewScenes();
        setSceneWorkspaceScope("current");
        setSelectedDownloadSceneIds(new Set());
        setSceneNote(
          res.cache?.hit
            ? `已使用本地 ASF 检索缓存：${res.scenes.length} 景`
            : res.search?.source === "CMR"
              ? `ASF 检索超时，已使用 CMR 备用结果导入 ${res.scenes.length} 景；下载 URL 可用，升降轨 / Path / Frame 可能不完整。`
            : null,
        );
        setSelectedSceneId(null);
        const nextBbox = sceneRowsBbox(res.scenes);
        if (nextBbox) setFocusBbox(nextBbox);
        await refresh();
        await refreshTree();
        const bits = [`导入 ${res.scenes.length} 景`];
        if (res.duplicates.length) bits.push(`去重 ${res.duplicates.length}`);
        if (res.errors.length) bits.push(`跳过 ${res.errors.length} 行`);
        setSceneNote(bits.join(" / "));
        setMetadataStatus(await getMetadataStatus());
      } else {
        setSceneError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setSceneError(formatBridgeError(e));
    } finally {
      setSceneBusy(false);
    }
  }

  async function handleOrbitSceneImport(action: () => Promise<ReturnType<typeof importScenesText> extends Promise<infer T> ? T : never>) {
    setSceneBusy(true);
    setSceneError(null);
    setSceneNote(null);
    setMetadataStatus({ ok: true, state: "running", done: 0, total: 1, percent: 0, message: "正在解析用于精密轨道下载的 SAR 影像" });
    try {
      const res = await action();
      if (res.ok) {
        setOrbitScenes(res.scenes);
        invalidateTaskOutputForNewScenes();
        setSelectedOrbitSceneIds(new Set(res.scenes.map((scene) => scene.scene_id).filter(Boolean)));
        setOrbitWorkspaceQuery("");
        const nextBbox = sceneRowsBbox(res.scenes);
        if (nextBbox) setFocusBbox(nextBbox);
        setSceneNote(null);
        setMetadataStatus(await getMetadataStatus());
      } else {
        setSceneError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setSceneError(formatBridgeError(e));
    } finally {
      setSceneBusy(false);
    }
  }

  async function onBrowseSceneFile() {
    const pick = await pickOpenFile("选择 ASF 文件", [
      "ASF cart (*.py;*.metalink;*.csv;*.geojson;*.json;*.txt;*.metadata;*.meta;*.met)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) setSceneFile(pick.path);
  }

  async function onBrowseAndImportSceneFile() {
    const pick = await pickOpenFile("选择 ASF 文件", [
      "ASF cart (*.py;*.metalink;*.csv;*.geojson;*.json;*.txt;*.metadata;*.meta;*.met)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) await handleSceneImport(() => importScenesFile(pick.path));
  }

  async function onBrowseOrbitSceneFile() {
    const pick = await pickOpenFile("选择用于轨道匹配的 ASF/SAR 文件", [
      "ASF cart (*.py;*.metalink;*.csv;*.geojson;*.json;*.txt;*.metadata;*.meta;*.met)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) setOrbitSceneFile(pick.path);
  }

  async function onBrowseSceneDir() {
    const pick = await pickDirectory("选择已有 Sentinel-1 数据目录");
    if (pick.ok && pick.path) setSceneDir(pick.path);
  }

  async function onBrowseOrbitSceneDir() {
    const pick = await pickDirectory("选择用于轨道匹配的 SAR 影像目录");
    if (pick.ok && pick.path) setOrbitSceneDir(pick.path);
  }

  async function onRunCheck() {
    setCheckBusy(true);
    setSceneError(null);
    try {
      const res = await checkScenes();
      if (res.ok) setCheckReport(res.report);
      else setSceneError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setSceneError(formatBridgeError(e));
    } finally {
      setCheckBusy(false);
    }
  }

  async function onCancelAsfSearch() {
    if (!asfSearchBusy || asfSearchCancelPending) return;
    setAsfSearchCancelPending(true);
    setAsfSearchError(null);
    setMetadataStatus({ ok: true, state: "cancelled", done: 0, total: 1, percent: 0, message: "正在停止 ASF 检索" });
    try {
      const res = await cancelAsfSearch();
      if (!res.ok) setAsfSearchError(formatBridgeError(res));
    } catch (e) {
      setAsfSearchError(formatBridgeError(e));
      setAsfSearchCancelPending(false);
    }
  }

  async function onAsfSearch() {
    if (asfSearchBusy) {
      await onCancelAsfSearch();
      return;
    }
    setAsfSearchError(null);
    const start = normalizeDateInput(asfSearchStart);
    const end = normalizeDateInput(asfSearchEnd);
    const maxResults = asfSearchMax.trim();
    if (!isValidSearchDate(start)) {
      setAsfSearchError("开始日期格式应为 yyyy/mm/dd，例如 2024/01/31；影像数量请填写到“影像数量”输入框。");
      return;
    }
    if (!isValidSearchDate(end)) {
      setAsfSearchError("结束日期格式应为 yyyy/mm/dd，例如 2024/01/31；影像数量请填写到“影像数量”输入框。");
      return;
    }
    if (maxResults && (!/^\d+$/.test(maxResults) || Number(maxResults) < 1 || Number(maxResults) > 10000)) {
      setAsfSearchError("影像数量必须是 1-10000 的整数；留空时会先读取 ASF 匹配总量。");
      return;
    }
    setAsfSearchBusy(true);
    setAsfSearchCancelPending(false);
    setMetadataStatus({ ok: true, state: "running", done: 0, total: 1, percent: 0, message: "正在准备 ASF 检索" });
    setCheckReport(null);
    try {
      const bbox = ctx?.region?.bbox ?? null;
      const aoiGeojson = ctx?.region?.aoi_geojson ?? aoiPreviewGeometry ?? null;
      const res = await searchAsfScenes({
        bbox,
        aoi_geojson: aoiGeojson,
        use_current_aoi: true,
        start,
        end,
        product_type: asfSearchProduct,
        beam_mode: asfSearchBeam.join(","),
        polarization: asfSearchPolarization.join(","),
        orbit_direction: asfSearchOrbit.join(","),
        relative_orbit_start: asfSearchRelativeOrbitStart || null,
        relative_orbit_end: asfSearchRelativeOrbitEnd || null,
        frame_start: asfSearchFrameStart || null,
        frame_end: asfSearchFrameEnd || null,
        max_results: maxResults || null,
      });
      if (res.ok) {
        setScenes(res.scenes);
        invalidateTaskOutputForNewScenes();
        setSceneWorkspaceScope("current");
        setSelectedDownloadSceneIds(new Set());
        setSelectedSceneId(null);
        const nextBbox = sceneRowsBbox(res.scenes);
        if (nextBbox) setFocusBbox(nextBbox);
        await refresh();
        await refreshTree();
        setMetadataStatus(await getMetadataStatus());
      } else {
        const maybeCancelled = (res as { cancelled?: boolean; code?: string }).cancelled || res.code === "DL001";
        if (maybeCancelled) {
          setMetadataStatus(await getMetadataStatus());
        } else {
          setAsfSearchError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        }
      }
    } catch (e) {
      setAsfSearchError(formatBridgeError(e));
    } finally {
      setAsfSearchBusy(false);
      setAsfSearchCancelPending(false);
    }
  }

  async function onClearScenes() {
    setAsfSearchError(null);
    setSceneError(null);
    try {
      const res = await clearScenes();
      if (!res.ok) {
        setAsfSearchError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      setScenes([]);
      invalidateTaskOutputForNewScenes();
      setSelectedSceneId(null);
      setSelectedDownloadSceneIds(new Set());
      if (!orbitUsesManualSource) {
        setSelectedOrbitSceneIds(new Set());
        closeOrbitWorkspace();
      }
      setHoveredSceneId(null);
      closeSceneWorkspace();
      setCheckReport(null);
      setFocusBbox(null);
      setMetadataStatus(null);
      setSceneNote(null);
      await refresh();
      await refreshTree();
    } catch (e) {
      setAsfSearchError(formatBridgeError(e));
    }
  }

  async function onClearMapLayers() {
    setAsfSearchError(null);
    setSceneError(null);
    try {
      const res = await clearMapLayers();
      if (!res.ok) {
        setAsfSearchError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      setScenes([]);
      setOrbitScenes([]);
      invalidateTaskOutputForNewScenes();
      setSelectedSceneId(null);
      setSelectedDownloadSceneIds(new Set());
      setSelectedOrbitSceneIds(new Set());
      setHoveredSceneId(null);
      closeSceneWorkspace();
      closeOrbitWorkspace();
      setCheckReport(null);
      setFocusBbox(null);
      setAoiPreviewGeometry(null);
      setMetadataStatus(null);
      setSceneNote(null);
      setDrawActive(false);
      await refresh();
      await refreshTree();
    } catch (e) {
      setAsfSearchError(formatBridgeError(e));
    }
  }

  async function onDownloadAsfScenes(sceneIds: string[], workspaceSnapshot = sceneWorkspaceSourceScenes) {
    const ids = sceneIds.filter(Boolean);
    if (ids.length === 0) return;
    setAsfStartBusy(true);
    setAsfError(null);
    try {
      if (!(await ensureEarthdataReadyForDownload("开始 Sentinel-1 下载"))) return;
      const snapshot = workspaceSnapshot.slice();
      const existingSnapshot =
        sceneWorkspaceScope === "task" && activeAsfTaskSnapshotId
          ? asfTaskSnapshots[activeAsfTaskSnapshotId]
          : null;
      const existingTaskStatus = existingSnapshot
        ? asfDownloadStatuses.find((status) => status.task_id === activeAsfTaskSnapshotId)
        : null;
      const out = existingSnapshot?.outputDir || (await ensureTaskOutput(true));
      if (!out) {
        setAsfError("开始下载前需要确认一个输出目录。");
        return;
      }
      if (!existingSnapshot) updateTaskOutputDir(out);
      const workers = Number(asfConcurrency) || 1;
      if (
        existingSnapshot &&
        existingTaskStatus &&
        ["running", "paused"].includes(existingTaskStatus.state) &&
        !existingTaskStatus.cancelled
      ) {
        const res = await appendAsfDownloadSnapshot(out, snapshot, ids, workers, activeAsfTaskSnapshotId);
        if (!res.ok) {
          setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
          return;
        }
        setSceneNote(`已追加 ${res.appended ?? ids.length} 景到任务快照：${existingSnapshot.title}。`);
        setDlStatus(await getDownloadStatus());
        return;
      }
      const title = existingSnapshot?.title || "任务快照";
      const res = await startAsfDownloadSnapshot(out, snapshot, ids, "auto", workers, asfUseProductSubdir);
      if (!res.ok) {
        setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      const taskId = res.task_id || `asf-local-${Date.now()}`;
      const taskSnapshot: SceneTaskSnapshot = {
        title,
        aoiName: currentAoiName,
        outputDir: out,
        scenes: snapshot,
      };
      setAsfTaskSnapshots((prev) => ({ ...prev, [taskId]: taskSnapshot }));
      setActiveAsfTaskSnapshotId(taskId);
      setActiveAsfTaskScenes(snapshot);
      setAsfTaskScenes(snapshot);
      if (dlBusy || dlPendingStop) {
        setAsfTaskScenes(snapshot);
        setSceneWorkspaceScope("task");
        setSceneNote(`已创建独立并行下载任务：${ids.length} 景，目录为 ${pathBaseName(out)}。`);
      } else {
        setSceneNote(`已开始 Sentinel-1 下载任务：${ids.length} 景，目录为 ${pathBaseName(out)}。`);
      }
      setDlStatus(await getDownloadStatus());
    } catch (e) {
      setAsfError(formatBridgeError(e));
    } finally {
      setAsfStartBusy(false);
    }
  }

  async function onPauseAsfScenes(sceneIds: string[], taskId = "") {
    const ids = sceneIds.filter(Boolean);
    if (ids.length === 0) return;
    setAsfError(null);
    try {
      const res = await pauseAsfScenes(ids, taskId);
      if (!res.ok) {
        setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      if ((res.paused ?? 0) === 0) {
        setAsfError("所选影像不在当前下载任务中，或已经完成/暂停。");
      }
      setDlStatus(await getDownloadStatus());
    } catch (e) {
      setAsfError(formatBridgeError(e));
    }
  }

  async function onResumeAsfScenes(sceneIds: string[], taskId = "") {
    const ids = sceneIds.filter(Boolean);
    if (ids.length === 0) return;
    setAsfError(null);
    try {
      const res = await resumeAsfScenes(ids, taskId);
      if (!res.ok) {
        setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      if ((res.resumed ?? 0) === 0) {
        setAsfError("所选影像当前没有处于暂停状态，无法继续。");
      }
      setDlStatus(await getDownloadStatus());
    } catch (e) {
      setAsfError(formatBridgeError(e));
    }
  }

  async function onRetryAsf(taskId = "") {
    setAsfError(null);
    try {
      const res = await retryAsfDownload(taskId);
      if (!res.ok) {
        setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      setDlStatus(await getDownloadStatus());
    } catch (e) {
      setAsfError(formatBridgeError(e));
    }
  }

  async function startQueuedAsfTask(task: PendingSceneDownloadTask) {
    setPendingAsfTasks((prev) =>
      prev.map((item) => (item.id === task.id ? { ...item, status: "starting", error: null } : item)),
    );
    try {
      const res = await startAsfDownloadSnapshot(
        task.outputDir,
        task.snapshot,
        task.sceneIds,
        "auto",
        task.concurrency,
        task.useProductSubdir,
      );
      if (!res.ok) {
        setPendingAsfTasks((prev) =>
          prev.map((item) =>
            item.id === task.id
              ? { ...item, status: "failed", error: `${res.error}${res.code ? ` (${res.code})` : ""}` }
              : item,
          ),
        );
        return;
      }
      const taskId = res.task_id || task.id;
      setAsfTaskSnapshots((prev) => ({
        ...prev,
        [taskId]: {
          title: task.title || "任务快照",
          aoiName: task.aoiName || currentAoiName,
          outputDir: task.outputDir,
          scenes: task.snapshot,
        },
      }));
      setActiveAsfTaskSnapshotId(taskId);
      setActiveAsfTaskScenes(task.snapshot);
      setAsfTaskScenes(task.snapshot);
      setPendingAsfTasks((prev) => prev.filter((item) => item.id !== task.id));
      setDlStatus(await getDownloadStatus());
    } catch (e) {
      setPendingAsfTasks((prev) =>
        prev.map((item) =>
          item.id === task.id ? { ...item, status: "failed", error: formatBridgeError(e) } : item,
        ),
      );
    }
  }

  async function onStopAsfDownload(taskId = "") {
    if (asfStopping) return;
    setAsfStopping(true);
    try {
      const res = await stopAsfDownload(taskId);
      if (!res.ok) {
        setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        setAsfStopping(false);
      }
      setDlStatus(await getDownloadStatus());
    } catch (e) {
      setAsfError(formatBridgeError(e));
      setAsfStopping(false);
    }
  }

  async function onStopDemDownload() {
    if (demStopping) return;
    setDemStopping(true);
    try {
      const res = await stopDemDownload();
      if (!res.ok) setDemError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      if (!res.ok) setDemStopping(false);
      setDemStatus(await getDemDownloadStatus());
    } catch (e) {
      setDemError(formatBridgeError(e));
      setDemStopping(false);
    }
  }

  async function onResumeArchivedTask(task: DownloadArchiveItem) {
    const kind = archiveTaskKind(task);
    const out = archiveTaskOutputDir(task);
    const taskKey = archiveTaskKey(task);
    if (restoringTaskKeys.has(taskKey)) return;
    if (!out) {
      setDownloadArchive((prev) =>
        dedupeArchiveItems(prev.map((item) =>
          archiveTaskKey(item) === taskKey
            ? {
                ...item,
                status: "failed",
                detail: "无法继续：没有保存原输出目录。",
                logs: [...(item.logs ?? []), "无法继续：没有保存原输出目录。"].slice(-120),
              }
            : item,
        )),
      );
      return;
    }

    setRestoringTaskKeys((prev) => new Set(prev).add(taskKey));

    const mark = (status: string, detail: string) =>
      setDownloadArchive((prev) =>
        dedupeArchiveItems(prev.map((item) =>
          archiveTaskKey(item) === taskKey
            ? { ...item, status, detail, logs: [...(item.logs ?? []), detail].slice(-120) }
            : item,
        )),
      );
    const markDetail = (detail: string) =>
      setDownloadArchive((prev) =>
        dedupeArchiveItems(prev.map((item) =>
          archiveTaskKey(item) === taskKey
            ? { ...item, detail, logs: [...(item.logs ?? []), detail].slice(-120) }
            : item,
        )),
      );

    updateTaskOutputDir(out);
    markDetail(kind === "asf" ? "正在恢复任务：直接回到下载队列；凭据只在实际下载请求中使用。" : "正在恢复任务：准备回到任务队列。");
    try {
      if (kind === "asf") {
        const workers = Number(task.concurrency) || Number(asfConcurrency) || 1;
        setAsfConcurrency(String(workers));
        const useSubdirs = Boolean(task.use_product_subdirs || task.download_layout === "product_subdirs");
        setAsfUseProductSubdir(useSubdirs);
        const res = await startAsfDownload(out, "auto", workers, [], useSubdirs);
        if (res.ok) {
          setDownloadArchive((prev) => prev.filter((item) => archiveTaskKey(item) !== taskKey));
          setDlStatus(await getDownloadStatus());
          return;
        }
        mark("failed", `${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      if (kind === "orbit") {
        const workers = Number(task.concurrency) || Number(orbitConcurrency) || 10;
        setOrbitConcurrency(String(workers));
        const useSubdir = Boolean(task.use_orbit_subdir || task.download_layout === "orbit_subdir");
        setOrbitUseSubdir(useSubdir);
        const res = await startOrbitDownload(out, [], workers, useSubdir);
        if (res.ok) {
          setDownloadArchive((prev) => prev.filter((item) => archiveTaskKey(item) !== taskKey));
          setOrbitStatus(await getOrbitDownloadStatus());
          return;
        }
        mark("failed", `${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      mark("failed", formatBridgeError(e));
    } finally {
      setRestoringTaskKeys((prev) => {
        const next = new Set(prev);
        next.delete(taskKey);
        return next;
      });
    }
  }

  async function onDeleteArchivedTask(task: DownloadArchiveItem) {
    const key = archiveTaskKey(task);
    setDownloadArchive((prev) => prev.filter((item) => archiveTaskKey(item) !== key));
    setExpandedHistoryIds((prev) => {
      const next = new Set(prev);
      next.delete(task.id);
      return next;
    });
    try {
      await deleteDownloadArchiveItem(task);
    } catch {
      // Local deletion still prevents the stale row from staying visible.
    }
  }

  async function onStartOrbitScenes(sceneIds: string[]) {
    const ids = sceneIds.filter(Boolean);
    setOrbitStartBusy(true);
    setOrbitError(null);
    try {
      const existingSnapshot =
        orbitWorkspaceScope === "task" && activeOrbitTaskSnapshotId
          ? orbitTaskSnapshots[activeOrbitTaskSnapshotId]
          : null;
      const out = existingSnapshot?.outputDir || (await ensureTaskOutput(true));
      if (!out) {
        setOrbitError("开始下载轨道前需要确认一个输出目录。");
        return;
      }
      if (ids.length === 0) {
        setOrbitError("请先在精密轨道工作台中勾选需要下载轨道的 SAR 影像。");
        return;
      }
      const snapshot = orbitWorkspaceSourceScenes.slice();
      if (!existingSnapshot) updateTaskOutputDir(out);
      const res = await startOrbitDownloadSnapshot(out, snapshot, ids, Number(orbitConcurrency) || 10, orbitUseSubdir);
      if (res.ok) {
        const taskId = res.task_id || activeOrbitTaskSnapshotId || `orbit-local-${Date.now()}`;
        const taskSnapshot: SceneTaskSnapshot = {
          title: existingSnapshot?.title || "任务快照",
          aoiName: existingSnapshot?.aoiName || currentAoiName,
          outputDir: out,
          scenes: snapshot,
        };
        setOrbitTaskSnapshots((prev) => ({ ...prev, [taskId]: taskSnapshot }));
        setActiveOrbitTaskSnapshotId(taskId);
        setOrbitTaskScenes(snapshot);
        setOrbitWorkspaceScope("task");
        setOrbitStatus(await getOrbitDownloadStatus());
      } else setOrbitError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setOrbitError(formatBridgeError(e));
    } finally {
      setOrbitStartBusy(false);
    }
  }

  async function onRunDemDownload(convert = true) {
    setDemDownloadAction(convert ? "download-convert" : "download-only");
    setDemError(null);
    setDemRun(null);
    setDemRunSource(null);
    const taskName = convert ? "DEM 下载并转换椭球高" : "DEM 下载";
    try {
      if (!DOWNLOADABLE_DEM_DATASETS.has(dataset)) {
        setDemError("当前选择的是本地或未接入 DEM 来源，不能在线下载；请选择 COP30、COP90、SRTM 或 AW3D30 椭球版，或使用“本地 DEM 转换”。");
        setDemDownloadAction(null);
        return;
      }
      if (!opentopoConfigured) {
        setDemError("开始下载 DEM 前，请先在设置里保存 OpenTopography API Key。");
        setPanel("settings");
        setDemDownloadAction(null);
        return;
      }
      const out = await ensureDemDownloadOutput();
      if (!out) {
        setDemError("开始下载 DEM 前需要确认一个输出目录。");
        setDemDownloadAction(null);
        return;
      }
      const taskId = `dem:${Date.now()}:${convert ? "convert" : "download"}`;
      const res = ctx?.region?.bbox
        ? await startDemDownload(out, dataset, "auto", convert)
        : await startDemDownloadBbox(
            manualDemBbox.west,
            manualDemBbox.east,
            manualDemBbox.south,
            manualDemBbox.north,
            out,
            dataset,
            "auto",
            convert,
          );
      if (!res.ok) {
        const detail = compactDemLogText(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        rememberTask({
          id: taskId,
          name: taskName,
          status: "failed",
          detail,
          kind: "dem",
          output_dir: out,
          total: 1,
          logs: [detail],
        });
        setDemError(detail);
        setDemDownloadAction(null);
        return;
      }
      setDemStatus(await getDemDownloadStatus());
      setDemDownloadAction(null);
    } catch (e) {
      setDemQueueTask(null);
      setDemError(formatBridgeError(e));
      setDemDownloadAction(null);
    }
  }

  async function onBrowseLocalDem() {
    const pick = await pickOpenFile("选择本地 DEM", [
      "DEM (*.tif;*.tiff;*.img;*.vrt)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) {
      setLocalDem(pick.path);
      setLocalDemOutputDir((current) => current.trim() || pathDirName(pick.path));
    }
  }

  async function onRunLocalDem(outputMode: "ellipsoid" | "sarscape") {
    if (outputMode === "ellipsoid" && localDemAlreadyEllipsoidal) {
      setDemError(null);
      setDemRun(null);
      setDemRunSource(null);
      setLocalDemPreviewError(null);
      return;
    }
    setLocalDemAction(outputMode);
    setDemError(null);
    setDemRun(null);
    setDemRunSource(null);
    try {
      const out = await ensureLocalDemOutput();
      if (!out) {
        setDemError("转换本地 DEM 前需要确认一个输出目录。");
        return;
      }
      const res = await runLocalDemConversion(localDem, out, localDatum, outputMode);
      if (res.ok) {
        setDemRunSource(outputMode === "ellipsoid" ? "local-ellipsoid" : "local-sarscape");
        setDemRun(res);
      }
      else setDemError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setDemError(formatBridgeError(e));
    } finally {
      setLocalDemAction(null);
    }
  }

  async function onGacosPlan() {
    setGacosBusy(true);
    setGacosError(null);
    try {
      if (!gacosConfigured) {
        setGacosError("生成 GACOS 请求前，请先在设置里保存 GACOS 接收邮箱。");
        setPanel("settings");
        return;
      }
      const out = await ensureTaskOutput();
      if (!out) {
        setGacosError("生成 GACOS 请求前需要确认一个输出目录。");
        return;
      }
      const res = await planGacosRequest(out);
      if (res.ok) setGacosPlan(res.plan);
      else setGacosError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setGacosError(formatBridgeError(e));
    } finally {
      setGacosBusy(false);
    }
  }

  async function runCredentialAction(label: string, action: () => Promise<SimpleOk>, success: string) {
    setCredBusy(label);
    setCredError(null);
    setCredNote(null);
    try {
      const res = await action();
      if (res.ok) {
        await refreshCredentials();
        if (label.startsWith("earth-")) {
          earthdataAuthRetryAfter.current = 0;
          const auth = res.auth as EarthdataAuthCheck | undefined;
          if (auth?.ok && typeof auth.configured === "boolean") {
            setEarthdataAuth(auth);
          } else {
            setEarthdataAuth(null);
          }
        }
        setCredNote(success);
      } else {
        setCredError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setCredError(formatBridgeError(e));
    } finally {
      setCredBusy(null);
    }
  }

  async function ensureEarthdataReadyForDownload(actionLabel: string) {
    const latest = await refreshCredentials();
    if (!isConfigured(latest.earthdata)) {
      setAsfError(`${actionLabel}前，请先在设置里保存 Earthdata Token 或账号密码。`);
      setPanel("settings");
      return false;
    }
    if (earthdataAuth?.status === "valid") return true;
    const auth = await refreshEarthdataAuth("download", latest.earthdata);
    if (!auth || auth.status !== "valid") {
      const message =
        auth?.status === "missing"
          ? `${actionLabel}前，请先在设置里保存 Earthdata Token 或账号密码。`
          : auth?.message || "Earthdata/ASF 凭据未通过登录检测，请检查 Token、用户名或密码。";
      setAsfError(message);
      setPanel("settings");
      return false;
    }
    return true;
  }

  async function openUrl(url: string) {
    const res = await openExternalUrl(url);
    if (!res.ok) setCredError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
  }

  async function openLocalPath(path: string) {
    if (!path.trim()) return;
    const res = await openPath(path);
    if (!res.ok) setDemError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
  }

  async function onBrowseCacheDir() {
    const pick = await pickDirectory("选择缓存目录");
    if (pick.ok && pick.path && network) setNetwork({ ...network, cache_dir: pick.path });
  }

  async function onSaveNetwork() {
    if (!network) return;
    const wantsAutoProxy = network.proxy_enabled && !network.proxy_url.trim();
    setNetworkBusy(true);
    setNetworkError(null);
    setNetworkNote(null);
    try {
      const res = await saveNetworkSettings({
        proxy_enabled: network.proxy_enabled,
        proxy_url: network.proxy_url,
        cache_enabled: network.cache_enabled,
        cache_dir: network.cache_dir,
        cache_limit_mb: Number(network.cache_limit_mb) || 0,
        tianditu_token: network.tianditu_token,
        asf_ssl_verify: network.asf_ssl_verify,
      });
      if (res.ok) {
        setNetwork(res);
        setEarthdataAuth(null);
        setNetworkNote(
          wantsAutoProxy && res.proxy_url
            ? `已自动识别系统代理：${res.proxy_url}`
            : wantsAutoProxy
              ? "已保存；未检测到系统代理，请手动填写代理地址后再下载。"
              : "网络代理、缓存与图源 Token 已保存。",
        );
      } else {
        setNetworkError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setNetworkError(formatBridgeError(e));
    } finally {
      setNetworkBusy(false);
    }
  }

  async function onCheckUpdateNow() {
    setUpdateBusy(true);
    setUpdateNote(null);
    setDownloadedUpdate(null);
    try {
      const res = await checkForUpdate(true);
      if (res.ok) {
        setUpdateInfo(res);
        if (res.update_available) setUpdateDialogOpen(true);
        setUpdateNote(res.message ?? "更新检查完成。");
      } else {
        setUpdateNote(formatBridgeError(res));
      }
    } catch (e) {
      setUpdateNote(formatBridgeError(e));
    } finally {
      setUpdateBusy(false);
    }
  }

  async function onDownloadUpdatePackage() {
    if (!updateInfo?.download_url) {
      setUpdateNote("当前没有可直接下载的更新包。");
      return;
    }
    setUpdateBusy(true);
    setUpdateNote(null);
    setDownloadedUpdate(null);
    try {
      const res = await downloadAppUpdate(updateInfo.download_url, updateInfo.asset_name ?? "");
      if (res.ok) {
        setDownloadedUpdate({ path: res.path, folder: res.folder });
        setUpdateNote(res.message ?? "更新包已下载。");
      } else {
        setUpdateNote(formatBridgeError(res));
      }
    } catch (e) {
      setUpdateNote(formatBridgeError(e));
    } finally {
      setUpdateBusy(false);
    }
  }

  function onDismissUpdatePrompt() {
    if (updateInfo?.latest_version) dismissUpdatePromptVersion(updateInfo.latest_version);
    setUpdateDialogOpen(false);
  }

  async function onInstallComponent(componentId: string) {
    setComponentBusy(componentId);
    setComponentNote(null);
    try {
      const res = await installComponent(componentId);
      if (res.ok) {
        setComponentStatus(res);
        setComponentNote("组件安装完成。");
      } else {
        setComponentNote(formatBridgeError(res));
      }
    } catch (e) {
      setComponentNote(formatBridgeError(e));
    } finally {
      setComponentBusy(null);
    }
  }

  async function onRemoveComponent(componentId: string) {
    setComponentBusy(componentId);
    setComponentNote(null);
    try {
      const res = await removeComponent(componentId);
      if (res.ok) {
        setComponentStatus(res);
        setComponentNote("组件已移除。");
      } else {
        setComponentNote(formatBridgeError(res));
      }
    } catch (e) {
      setComponentNote(formatBridgeError(e));
    } finally {
      setComponentBusy(null);
    }
  }

function renderOutputParameters(
  desc = "任务开始前确认输出根目录；留空时使用当前项目或研究区目录。",
  options?: {
    value?: string;
    onChange?: (value: string) => void;
    onBrowse?: () => Promise<string>;
    placeholder?: string;
    title?: string;
    showAoiDownloadMode?: boolean;
  },
) {
    const value = options?.value ?? outputDir;
    const onChange = options?.onChange ?? updateTaskOutputDir;
    const placeholder = options?.placeholder ?? (value.trim() || "开始任务时选择输出目录");
    const showAoiDownloadMode = false;
    return (
      <div className="space-y-2 rounded-2xl border border-white/45 bg-white/40 p-2 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
        <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs font-medium">
            <HardDrive className="h-3.5 w-3.5 text-primary" />
            输出参数
          </div>
          <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            className="h-8 min-w-0 font-mono text-xs"
            spellCheck={false}
          />
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => void (options?.onBrowse ?? onBrowseOutput)()}
            title={options?.title ?? "浏览输出目录"}
          >
            <FolderOpen className="h-4 w-4" />
          </Button>
        </div>
        <div className="text-[11px] leading-4 text-muted-foreground">{desc}</div>
        {showAoiDownloadMode && activeAoiFeatureCount > 1 && (
          <div className="rounded-xl border border-white/55 bg-white/45 px-2 py-1.5 text-xs dark:border-white/10 dark:bg-white/10">
            <div className="mb-1 font-medium">多要素输出（{activeAoiFeatureCount} 个要素）</div>
            <div className="grid gap-1 sm:grid-cols-2">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="radio"
                  checked={aoiDownloadMode === "merge"}
                  onChange={() => setAoiDownloadMode("merge")}
                  className="mt-0.5 h-4 w-4 accent-primary"
                />
                <span>
                  <span className="font-medium">合并下载</span>
                  <span className="ml-1 text-muted-foreground">写入一个目录。</span>
                </span>
              </label>
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="radio"
                  checked={aoiDownloadMode === "split"}
                  onChange={() => setAoiDownloadMode("split")}
                  className="mt-0.5 h-4 w-4 accent-primary"
                />
                <span>
                  <span className="font-medium">拆分下载</span>
                  <span className="ml-1 text-muted-foreground">按要素建目录。</span>
                </span>
              </label>
            </div>
          </div>
        )}
      </div>
    );
  }

  function renderAdminPicker(
    key: "province" | "city" | "district",
    value: string,
    options: string[],
    onChange: (value: string) => void,
  ) {
    const open = adminPickerOpen === key;
    return (
      <div className="relative min-w-0">
        <button
          type="button"
          onClick={() => setAdminPickerOpen(open ? null : key)}
          className={cn(
            "flex h-10 w-full items-center justify-between gap-2 rounded-xl border border-input bg-white/58 px-3 text-left text-sm shadow-sm backdrop-blur-xl transition-colors hover:bg-white/70 dark:bg-white/10 dark:hover:bg-white/15",
            open && "ring-2 ring-ring",
          )}
        >
          <span className="truncate">{value || "全部"}</span>
          <ChevronDown className={cn("h-4 w-4 shrink-0 transition-transform", open && "rotate-180")} />
        </button>
        {open && (
          <div className="absolute left-0 right-0 top-11 z-[80] max-h-60 overflow-y-auto rounded-xl border border-white/70 bg-white/96 p-1.5 text-sm shadow-2xl backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/95">
            {options.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => {
                  onChange(item);
                  setAdminPickerOpen(null);
                }}
                className={cn(
                  "flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-accent",
                  value === item && "bg-foreground text-background hover:bg-foreground",
                )}
              >
                <span className="truncate">{item}</span>
                {value === item && <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  function renderAoiTools() {
    return (
      <Section
        title="区域选择"
        desc="地名 / 行政区划 / 上传边界 / 经纬度范围；AOI 与 ASF 检索和 DEM 范围共享。"
        icon={MapPinned}
      >
        <div
          className="space-y-3"
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }}
          onDrop={(event) => void onDropAoiFile(event)}
        >
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Input
              value={adminQuery}
              onChange={(e) => setAdminQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void onSearchAdminBoundary({ queryOnly: true });
              }}
              placeholder="搜索地名（省 / 市 / 区 / POI）..."
              spellCheck={false}
            />
            <Button
              size="icon"
              onClick={() => void onSearchAdminBoundary({ queryOnly: true })}
              disabled={adminBusy}
            >
              {adminBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            </Button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {renderAdminPicker("province", adminProvince, adminProvinceOptions, (value) => {
              setAdminProvince(value);
              setAdminCity("全部");
              setAdminDistrict("全部");
            })}
            {renderAdminPicker("city", adminCity, adminCityOptions, (value) => {
              setAdminCity(value);
              setAdminDistrict("全部");
            })}
            {renderAdminPicker("district", adminDistrict, adminDistrictOptions, setAdminDistrict)}
          </div>
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Button
              variant="outline"
              onClick={() => void onSearchAdminBoundary()}
              disabled={adminBusy || aoiBusy}
              className="min-w-0"
            >
              {adminBusy || aoiBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPinned className="h-4 w-4" />}
              加载行政边界
            </Button>
            <Button variant="outline" onClick={onBrowseAoiFile}>
              <FileUp className="h-4 w-4" />
              上传本地边界
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="hidden"
              onClick={() => void onPreviewAoiFile()}
              disabled={aoiBusy || !aoiFile.trim()}
              title={aoiFile.trim() ? "选择本地边界要素" : "请先上传本地边界文件"}
            >
              {aoiBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Settings className="h-4 w-4" />}
            </Button>
            <Button
              variant="outline"
              size="icon"
              title="清空行政区搜索结果"
              className="hidden"
              onClick={() => {
                setAdminResults([]);
                setSelectedAdminBoundary(null);
                setFocusBbox(null);
                setAoiPreviewGeometry(null);
              }}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
          {aoiFile && (
            <div className="hidden grid-cols-1 gap-2">
              <Input value={aoiFile} readOnly className="font-mono text-xs" title={aoiFile} />
            </div>
          )}
          {adminResults.length > 0 && (
            <div className="max-h-36 space-y-2 overflow-y-auto rounded-2xl border border-white/45 bg-white/35 p-2 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
              {adminResults.slice(0, 5).map((item, index) => (
                <button
                  key={`${item.label}:${index}`}
                  type="button"
                  onClick={() => {
                    setSelectedAdminBoundary(item);
                    setSelectedSceneId(null);
                    setFocusBbox(item.bbox);
                    setAoiPreviewGeometry(item.geojson ?? null);
                    void bindAdminBoundary(item);
                  }}
                  className={cn(
                    "block w-full rounded-xl px-2 py-2 text-left transition-colors hover:bg-white/60 dark:hover:bg-white/10",
                    selectedAdminBoundary?.label === item.label &&
                      "bg-primary/10 ring-1 ring-primary/25",
                  )}
                >
                  <span className="block truncate font-medium">{item.label}</span>
                  <span className="mt-1 block truncate text-[11px] text-muted-foreground">
                    {item.source || "行政区划服务"} · {item.geojson ? "真实边界" : "矩形范围"}
                  </span>
                  <span className="mt-1 block font-mono text-[11px] text-muted-foreground">
                    W{item.bbox.west.toFixed(4)} S{item.bbox.south.toFixed(4)} E{item.bbox.east.toFixed(4)} N{item.bbox.north.toFixed(4)}
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className="overflow-hidden rounded-2xl border border-white/45 bg-white/28 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/8">
            <button
              type="button"
              onClick={() => setManualAoiOpen((value) => !value)}
              className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-xs"
            >
              <span className="min-w-0 truncate font-medium">经纬度范围</span>
              <span className="flex items-center gap-2">
                <Badge variant="neutral">
                  {manualBboxReady ? `面积 ${roughBboxAreaKm2(manualDemBbox)} km²` : "待输入"}
                </Badge>
                <ChevronDown
                  className={cn(
                    "h-4 w-4 text-muted-foreground transition-transform",
                    manualAoiOpen && "rotate-180",
                  )}
                />
              </span>
            </button>
            {manualAoiOpen && (
              <div className="space-y-2 border-t border-white/45 px-3 py-3 dark:border-white/10">
                <div className="grid grid-cols-2 gap-2">
                  <Input value={demWest} onChange={(e) => setDemWest(e.target.value)} placeholder="West" />
                  <Input value={demEast} onChange={(e) => setDemEast(e.target.value)} placeholder="East" />
                  <Input value={demSouth} onChange={(e) => setDemSouth(e.target.value)} placeholder="South" />
                  <Input value={demNorth} onChange={(e) => setDemNorth(e.target.value)} placeholder="North" />
                </div>
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={() => void bindBbox(manualDemBbox)}
                  disabled={aoiBusy || !manualBboxReady}
                >
                  {aoiBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                  绑定矩形 AOI
                </Button>
              </div>
            )}
          </div>
          <div className="truncate rounded-xl border border-white/45 bg-white/32 px-3 py-1.5 text-[11px] leading-4 text-muted-foreground shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
            正式项目建议上传权威边界文件：内置行政区适合快速筛选和预览。
          </div>
          <ErrorLine text={aoiError} />
          <NoteLine text={aoiNote} />
        </div>
      </Section>
    );
  }

  function renderAoiFeaturePickerOverlay() {
    if (!aoiFeaturePickerOpen || !aoiFeaturePreview) return null;
    const visibleSelected = filteredAoiFeatures.filter((feature) => selectedAoiFeatureIds.has(feature.id)).length;
    const selectionScope = aoiFeatureFilter.trim() ? filteredAoiFeatures : aoiFeaturePreview.features;
    const toggleFeature = (feature: AoiFeaturePreview, checked: boolean) => {
      setSelectedAoiFeatureIds((prev) => {
        const next = new Set(prev);
        if (checked) next.add(feature.id);
        else next.delete(feature.id);
        return next;
      });
    };
    return (
      <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-slate-950/24 p-4 backdrop-blur-sm">
        <div className="flex max-h-[86vh] w-[min(920px,calc(100vw-32px))] flex-col overflow-hidden rounded-[24px] border border-white/70 bg-white/94 shadow-2xl backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/94">
          <div className="flex shrink-0 items-start justify-between gap-4 border-b border-border/60 px-5 py-4">
            <div className="min-w-0">
              <div className="truncate text-lg font-semibold">
                导入区域 - {aoiFeaturePreview.file_name}（{aoiFeaturePreview.total_features} 个要素）
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                已选 {selectedAoiFeatureIds.size} / {aoiFeaturePreview.total_features}
                {selectedAoiAreaKm2 > 0 ? ` · 约 ${selectedAoiAreaKm2.toLocaleString(undefined, { maximumFractionDigits: 2 })} km²` : ""}
              </div>
            </div>
            <Button size="icon" variant="ghost" className="h-8 w-8 rounded-full" onClick={() => setAoiFeaturePickerOpen(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="shrink-0 space-y-3 border-b border-border/60 px-5 py-3">
            <div className="grid gap-2 md:grid-cols-[minmax(180px,260px)_minmax(0,1fr)_auto_auto_auto]">
              <select
                value={displayedAoiFeatureField}
                onChange={(event) => setAoiFeatureNameField(event.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                title="显示名称字段"
              >
                {aoiFeaturePreview.fields.length ? (
                  aoiFeaturePreview.fields.map((field) => (
                    <option key={field} value={field}>
                      {field}
                    </option>
                  ))
                ) : (
                  <option value="">无属性字段</option>
                )}
              </select>
              <Input
                value={aoiFeatureFilter}
                onChange={(event) => setAoiFeatureFilter(event.target.value)}
                placeholder="按名称、编号或字段值筛选要素"
              />
              <Button
                variant="outline"
                title={aoiFeatureFilter.trim() ? "选中当前筛选结果" : "选中全部要素"}
                onClick={() =>
                  setSelectedAoiFeatureIds(new Set(selectionScope.map((feature) => feature.id)))
                }
              >
                全选
              </Button>
              <Button variant="outline" onClick={() => setSelectedAoiFeatureIds(new Set())}>
                清空
              </Button>
              <Button
                variant="outline"
                onClick={() =>
                  setSelectedAoiFeatureIds((prev) => {
                    const next = new Set(prev);
                    selectionScope.forEach((feature) => {
                      if (next.has(feature.id)) next.delete(feature.id);
                      else next.add(feature.id);
                    });
                    return next;
                  })
                }
              >
                反选
              </Button>
            </div>

            <div className="rounded-2xl border border-white/60 bg-white/55 px-3 py-2 text-xs text-muted-foreground dark:border-white/10 dark:bg-white/10">
              选中的边界要素会合并为一个 AOI；下载目录按任务本身设置，不再按要素拆分。
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
            <div className="overflow-hidden rounded-2xl border">
              <div className="grid grid-cols-[42px_64px_minmax(0,1fr)_120px] border-b bg-muted/45 px-3 py-2 text-xs font-medium">
                <span>选</span>
                <span>#</span>
                <span>名称</span>
                <span className="text-right">面积 km²</span>
              </div>
              {filteredAoiFeatures.length ? (
                filteredAoiFeatures.map((feature) => {
                  const fieldValue = displayedAoiFeatureField
                    ? String(feature.properties?.[displayedAoiFeatureField] ?? "")
                    : "";
                  const title = fieldValue && fieldValue !== feature.name ? `${feature.name} · ${fieldValue}` : feature.name;
                  return (
                    <label
                      key={feature.id}
                      className="grid cursor-pointer grid-cols-[42px_64px_minmax(0,1fr)_120px] items-center border-b px-3 py-2 text-xs last:border-b-0 hover:bg-muted/35"
                    >
                      <input
                        type="checkbox"
                        checked={selectedAoiFeatureIds.has(feature.id)}
                        onChange={(event) => toggleFeature(feature, event.currentTarget.checked)}
                        className="h-4 w-4 accent-primary"
                      />
                      <span className="text-muted-foreground">{feature.index}</span>
                      <span className="truncate" title={title}>
                        {fieldValue || feature.name}
                      </span>
                      <span className="text-right font-mono text-muted-foreground">
                        {Number(feature.area_km2 || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </span>
                    </label>
                  );
                })
              ) : (
                <div className="px-3 py-8 text-center text-sm text-muted-foreground">没有匹配的要素。</div>
              )}
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border/60 px-5 py-4">
            <div className="text-xs text-muted-foreground">
              当前筛选 {filteredAoiFeatures.length} 个，已选其中 {visibleSelected} 个。
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={() => setAoiFeaturePickerOpen(false)}>
                取消
              </Button>
              <Button
                onClick={() => void onApplyAoiFile(aoiFeaturePreview.path)}
                disabled={aoiBusy || selectedAoiFeatureIds.size === 0}
              >
                {aoiBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPinned className="h-4 w-4" />}
                导入选中的 {selectedAoiFeatureIds.size} 个要素
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  function renderCardModeSwitch<T extends string>(
    items: { key: T; label: string }[],
    value: T,
    onChange: (key: T) => void,
  ) {
    return (
      <div className="grid grid-cols-2 gap-2 rounded-2xl border border-border/60 bg-white/35 p-1 text-sm shadow-sm dark:bg-white/10">
        {items.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => onChange(item.key)}
            className={cn(
              "h-9 rounded-xl border px-3 font-medium transition-colors",
              value === item.key
                ? "border-primary bg-primary text-primary-foreground shadow-sm"
                : "border-border/70 bg-white/65 text-foreground hover:border-primary/45 hover:bg-white/85 dark:bg-white/5 dark:hover:bg-white/10",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
    );
  }

  function renderAsfMultiSelect(
    key: "orbit" | "beam" | "polarization",
    placeholder: string,
    values: string[],
    setValues: (next: string[]) => void,
    options: { value: string; label: string }[],
  ) {
    const selected = new Set(values);
    const label =
      values.length > 0
        ? options
            .filter((item) => selected.has(item.value))
            .map((item) => item.label)
            .join(" / ")
        : placeholder;
    return (
      <div className="relative">
        <button
          type="button"
          onClick={() => setAsfFilterMenuOpen((open) => (open === key ? null : key))}
          className={cn(
            "flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-card px-3 text-left text-sm shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            values.length > 0 ? "text-foreground" : "text-muted-foreground",
          )}
          aria-haspopup="listbox"
          aria-expanded={asfFilterMenuOpen === key}
        >
          <span className="min-w-0 truncate">{label}</span>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
        {asfFilterMenuOpen === key && (
          <div className="absolute left-0 right-0 top-[calc(100%+0.35rem)] z-[900] overflow-hidden rounded-xl border border-border/80 bg-popover/95 p-1.5 text-sm shadow-xl backdrop-blur-2xl">
            <button
              type="button"
              onClick={() => setValues([])}
              className={cn(
                "flex h-8 w-full items-center justify-between rounded-lg px-2.5 text-left transition hover:bg-muted",
                values.length === 0 ? "text-primary" : "text-muted-foreground",
              )}
            >
              <span>全部</span>
              {values.length === 0 && <CheckCircle2 className="h-3.5 w-3.5" />}
            </button>
            {options.map((item) => {
              const checked = selected.has(item.value);
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => {
                    const next = new Set(values);
                    if (next.has(item.value)) next.delete(item.value);
                    else next.add(item.value);
                    setValues(Array.from(next));
                  }}
                  className={cn(
                    "flex h-8 w-full items-center justify-between rounded-lg px-2.5 text-left transition hover:bg-muted",
                    checked ? "text-primary" : "text-foreground",
                  )}
                  role="option"
                  aria-selected={checked}
                >
                  <span>{item.label}</span>
                  {checked && <CheckCircle2 className="h-3.5 w-3.5" />}
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  function renderAsfSearchSection() {
    return (
      <div data-tour="asf-filter">
        <Section
          title="Sentinel-1 影像来源"
          desc="在同一入口内选择在线检索或本地匹配；结果进入工作台统一核对、筛选和下载。"
          icon={Search}
        >
          <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 rounded-2xl border border-border/60 bg-white/35 p-1 text-sm shadow-sm dark:bg-white/10">
            {[
              { key: "online" as const, label: "在线检索" },
              { key: "local" as const, label: "本地匹配" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setSentinelSourceMode(item.key)}
                className={cn(
                  "h-9 rounded-xl border px-3 font-medium transition-colors",
                  sentinelSourceMode === item.key
                    ? "border-primary bg-primary text-primary-foreground shadow-sm"
                    : "border-border/70 bg-white/65 text-foreground hover:border-primary/45 hover:bg-white/85 dark:bg-white/5 dark:hover:bg-white/10",
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
          {sentinelSourceMode === "online" ? (
            <>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={asfSearchProduct}
              onChange={(e) => setAsfSearchProduct(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="SLC">SLC</option>
              <option value="GRD">GRD</option>
            </select>
            {renderAsfMultiSelect("orbit", "方向", asfSearchOrbit, setAsfSearchOrbit, ASF_ORBIT_OPTIONS)}
          </div>
          <div className="grid grid-cols-2 gap-2">
            {renderAsfMultiSelect("beam", "成像模式", asfSearchBeam, setAsfSearchBeam, ASF_BEAM_OPTIONS)}
            {renderAsfMultiSelect("polarization", "极化", asfSearchPolarization, setAsfSearchPolarization, ASF_POLARIZATION_OPTIONS)}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="sr-only">
                <CalendarDays className="h-3.5 w-3.5" />
                开始日期
              </span>
              <DatePickerInput value={asfSearchStart} onChange={setAsfSearchStart} ariaLabel="开始日期" label="开始" />
            </label>
            <label className="block">
              <span className="sr-only">
                <CalendarDays className="h-3.5 w-3.5" />
                结束日期
              </span>
              <DatePickerInput value={asfSearchEnd} onChange={setAsfSearchEnd} ariaLabel="结束日期" label="结束" />
            </label>
          </div>
          <div className="grid grid-cols-5 gap-2">
            <Input
              value={asfSearchRelativeOrbitStart}
              onChange={(e) => setAsfSearchRelativeOrbitStart(e.target.value)}
              className="h-9 px-2 text-xs placeholder:text-[11px]"
              placeholder="Path 起"
              title="相对轨道 Path 起始值"
              inputMode="numeric"
            />
            <Input
              value={asfSearchRelativeOrbitEnd}
              onChange={(e) => setAsfSearchRelativeOrbitEnd(e.target.value)}
              className="h-9 px-2 text-xs placeholder:text-[11px]"
              placeholder="Path 止"
              title="相对轨道 Path 结束值"
              inputMode="numeric"
            />
            <Input
              value={asfSearchFrameStart}
              onChange={(e) => setAsfSearchFrameStart(e.target.value)}
              className="h-9 px-2 text-xs placeholder:text-[11px]"
              placeholder="Frame 起"
              title="Frame 起始值"
              inputMode="numeric"
            />
            <Input
              value={asfSearchFrameEnd}
              onChange={(e) => setAsfSearchFrameEnd(e.target.value)}
              className="h-9 px-2 text-xs placeholder:text-[11px]"
              placeholder="Frame 止"
              title="Frame 结束值"
              inputMode="numeric"
            />
            <Input
              value={asfSearchMax}
              onChange={(e) => setAsfSearchMax(e.target.value)}
              className="h-9 px-2 text-xs placeholder:text-[11px]"
              placeholder="影像数量"
              inputMode="numeric"
              aria-label="影像数量"
              title="填写要检索的影像数量；留空时先读取 ASF 匹配总量。"
            />
          </div>
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Button
              onClick={onAsfSearch}
              disabled={asfSearchCancelPending}
              variant={asfSearchBusy ? "destructive" : "default"}
              className="w-full"
            >
              {asfSearchBusy ? (
                asfSearchCancelPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Square className="h-4 w-4" />
                )
              ) : (
                <Search className="h-4 w-4" />
              )}
              {asfSearchBusy ? (asfSearchCancelPending ? "正在停止" : "停止检索") : "检索并导入"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => void onClearScenes()}
              disabled={asfSearchBusy || (!scenes.length && !checkReport)}
              title="清除 ASF 检索/导入结果"
            >
              <Trash2 className="h-4 w-4" />
              清除
            </Button>
          </div>
          {asfSearchBusy && metadataStatus && (
            <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="truncate">{metadataStatus.message || "正在检索 ASF 元数据"}</span>
                <span className="font-mono">{metadataStatus.percent}%</span>
              </div>
              <Progress value={metadataStatus.percent} className="h-1.5" />
            </div>
          )}
          <ErrorLine text={asfSearchError} />
            </>
          ) : (
            renderManualSceneImportControls()
          )}
          </div>
        </Section>
      </div>
    );
  }

  function renderSceneSourceControls(desc: string, target: "download" | "orbit" = "download", embedded = false) {
    const isOrbitTarget = target === "orbit";
    const sourceScenes = isOrbitTarget ? orbitCandidateScenes : scenes;
    const sourceFile = isOrbitTarget ? orbitSceneFile : sceneFile;
    const sourceDir = isOrbitTarget ? orbitSceneDir : sceneDir;
    const setSourceFile = isOrbitTarget ? setOrbitSceneFile : setSceneFile;
    const setSourceDir = isOrbitTarget ? setOrbitSceneDir : setSceneDir;
    const sourceStats = {
      total: sourceScenes.length,
      withFootprint: sourceScenes.filter((scene) => scene.footprint_bbox || scene.footprint_geojson).length,
      withCore: sourceScenes.filter(
        (scene) =>
          (scene.path || scene.relative_orbit) &&
          scene.frame &&
          scene.orbit_direction &&
          scene.polarization,
      ).length,
    };
    const sourceReady =
      sourceStats.total > 0 &&
      sourceStats.withFootprint === sourceStats.total &&
      sourceStats.withCore === sourceStats.total;
    const importFile = isOrbitTarget
      ? () => handleOrbitSceneImport(() => previewScenesFile(sourceFile))
      : () => handleSceneImport(() => importScenesFile(sourceFile));
    const importDir = isOrbitTarget
      ? () => handleOrbitSceneImport(() => previewScenesDirectory(sourceDir))
      : () => handleSceneImport(() => importScenesDirectory(sourceDir));
    const content = (
      <div className="space-y-3">
          <div className="grid grid-cols-[1fr_auto_auto] gap-2">
            <Input
              value={sourceFile}
              onChange={(e) => setSourceFile(e.target.value)}
              placeholder="ASF 官方 py / metalink / metadata / CSV / GeoJSON"
              className="font-mono text-xs"
              spellCheck={false}
            />
            <Button
              variant="outline"
              size="icon"
              onClick={isOrbitTarget ? onBrowseOrbitSceneFile : onBrowseSceneFile}
              title={isOrbitTarget ? "选择用于轨道匹配的 ASF 官方文件" : "选择 ASF 官方文件"}
            >
              <FolderOpen className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              onClick={() => void importFile()}
              disabled={sceneBusy || !sourceFile.trim()}
            >
              导入
            </Button>
          </div>
          <div className="grid grid-cols-[1fr_auto_auto] gap-2">
            <Input
              value={sourceDir}
              onChange={(e) => setSourceDir(e.target.value)}
              placeholder={
                isOrbitTarget
                  ? "SAR 影像目录（用于解析采集日期和轨道号，不是 EOF 目录）"
                  : "SAR 影像目录（.SAFE / .zip，支持 SLC、GRD、RAW、OCN 文件名识别）"
              }
              className="font-mono text-xs"
              spellCheck={false}
            />
            <Button
              variant="outline"
              size="icon"
              onClick={isOrbitTarget ? onBrowseOrbitSceneDir : onBrowseSceneDir}
              title={isOrbitTarget ? "选择用于轨道匹配的 SAR 影像目录" : "选择 SAR 影像目录"}
            >
              <FolderOpen className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              onClick={() => void importDir()}
              disabled={sceneBusy || !sourceDir.trim()}
            >
              识别
            </Button>
          </div>
          {sceneBusy && (
            <div className="rounded-2xl border border-primary/30 bg-primary/5 px-3 py-2 text-xs">
              <div className="mb-2 flex items-center justify-between gap-2 font-medium">
                <span className="flex min-w-0 items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                  <span className="truncate">{metadataStatus?.message || "正在解析影像名称并补全 ASF 元数据"}</span>
                </span>
                <span className="font-mono">{metadataStatus?.percent ?? 0}%</span>
              </div>
              <Progress value={metadataStatus?.percent ?? 0} className="h-1.5" />
            </div>
          )}
          <div
            className={cn(
              "rounded-2xl border p-3 text-xs shadow-sm backdrop-blur-xl",
              sourceReady
                ? "border-success/35 bg-success/10"
                : sourceStats.withFootprint > 0 || sourceStats.withCore > 0
                  ? "border-primary/30 bg-primary/10"
                  : "border-white/45 bg-white/35 dark:border-white/10 dark:bg-white/10",
            )}
          >
            {kv(isOrbitTarget ? "轨道候选" : "当前场景", sourceScenes.length ? `${sourceScenes.length} 景` : "未导入")}
          {isOrbitTarget && kv("精密轨道工作台", orbitUsesManualSource ? "本地文件检索结果" : scenes.length ? "Sentinel-1 候选影像" : "等待候选影像")}
          </div>
          {isOrbitTarget && orbitUsesManualSource && (
            <Button
              size="sm"
              variant="outline"
              className="w-full"
              onClick={() => {
                setOrbitScenes([]);
                invalidateTaskOutputForNewScenes();
                setOrbitSceneFile("");
                setOrbitSceneDir("");
                setSceneNote(null);
                const nextBbox = sceneRowsBbox(scenes);
                if (nextBbox) setFocusBbox(nextBbox);
                void clearOrbitCandidateScenes();
              }}
            >
              恢复使用 Sentinel-1 检索结果
            </Button>
          )}
          {sourceScenes.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              <Button size="sm" variant="outline" onClick={isOrbitTarget ? selectAllOrbitScenes : selectAllDownloadScenes}>
                全选
              </Button>
              <Button size="sm" variant="outline" onClick={isOrbitTarget ? clearOrbitSceneSelection : clearDownloadSceneSelection}>
                清空选择
              </Button>
              <Button size="sm" onClick={() => (isOrbitTarget ? openOrbitWorkspace() : openSceneWorkspace())}>
                <Maximize2 className="h-3.5 w-3.5" />
                打开工作台
              </Button>
            </div>
          )}
          <ErrorLine text={sceneError} />
          {!isOrbitTarget && <NoteLine text={sceneNote} />}
      </div>
    );
    if (embedded) return content;
    return (
      <Section title={isOrbitTarget ? "本地文件检索" : "SAR 影像来源"} desc={desc} icon={isOrbitTarget ? Orbit : Satellite}>
        {content}
      </Section>
    );
  }

  function renderSceneResultSection() {
    if (scenes.length === 0 && !checkReport) return null;
    return (
      <Section
        title="所选 SAR 数据"
        desc="在线筛选、本地文件检索和目录识别得到的数据统一在这里查看、核查、定位和高亮。"
        icon={Database}
        defaultOpen={false}
        storageKey="sentinel1-scene-results"
      >
        <div className="space-y-3">
          {scenes.length > 0 && (
            <div className="relative rounded-md border bg-muted/30" onMouseLeave={hideSceneMetaCard}>
              <div className="flex items-center justify-between border-b px-3 py-2 text-xs">
                <span className="font-medium">
                  {selectedDownloadSceneIdList.length} / {scenes.length} 景加入下载 · 点击场景只高亮边框
                </span>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button size="sm" variant="ghost" className="h-7 px-2" onClick={selectAllDownloadScenes}>
                    全选
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7 px-2" onClick={clearDownloadSceneSelection}>
                    清空
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => openSceneWorkspace()}>
                    <Maximize2 className="h-3.5 w-3.5" />
                    工作台
                  </Button>
                  <Button size="sm" variant="outline" onClick={onRunCheck} disabled={checkBusy}>
                    {checkBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                    核查
                  </Button>
                </div>
              </div>
              <div ref={sceneResultVirtual.scrollRef} onScroll={sceneResultVirtual.onScroll} className="max-h-[34rem] overflow-y-auto">
                <div className="relative" style={{ height: sceneResultVirtual.totalHeight }}>
                {sceneResultVirtual.rows.map(({ item: scene, top }) => (
                  <div
                    key={scene.scene_id}
                    style={{ transform: `translateY(${top}px)` }}
                    onClick={() => {
                      highlightScene(scene.scene_id);
                    }}
                    className={cn(
                      "absolute left-0 right-0 h-[96px] w-full cursor-pointer overflow-hidden border-b border-l-4 border-l-transparent px-3 py-2 text-left text-xs transition-colors hover:bg-white/45 dark:hover:bg-white/10",
                      selectedSceneId === scene.scene_id &&
                        "border-l-primary bg-primary/12 ring-1 ring-inset ring-primary/25",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={selectedDownloadSceneIds.has(scene.scene_id)}
                        onChange={(event) => toggleDownloadScene(scene.scene_id, event.currentTarget.checked)}
                        onClick={(event) => event.stopPropagation()}
                        className="h-4 w-4 shrink-0 rounded border-border accent-primary"
                        title="加入本次下载"
                      />
                      <div className="min-w-0 flex-1 truncate font-mono" title={scene.scene_id}>
                        {scene.scene_id}
                      </div>
                      <span
                        className="rounded-full p-1 text-muted-foreground transition-colors hover:bg-white/60 hover:text-foreground dark:hover:bg-white/10"
                        onClick={(event) => {
                          event.stopPropagation();
                          copySceneMetadata(scene);
                        }}
                        onMouseEnter={(event) => showSceneMetaCard(scene.scene_id, event)}
                        onMouseMove={(event) => showSceneMetaCard(scene.scene_id, event)}
                        onMouseLeave={hideSceneMetaCard}
                        title="悬浮查看元数据，点击复制"
                      >
                        <Info className="h-3.5 w-3.5 shrink-0" />
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {selectedSceneId === scene.scene_id && <Badge variant="success">地图高亮</Badge>}
                      {selectedDownloadSceneIds.has(scene.scene_id) && <Badge variant="success">已勾选</Badge>}
                      <Badge variant="neutral">{scene.product_type}</Badge>
                      <Badge variant="neutral">{orbitLabel(scene.orbit_direction)}</Badge>
                      <Badge variant="neutral">{polarizationLabel(scene.polarization)}</Badge>
                      <Badge variant={scene.path || scene.relative_orbit ? "success" : "warning"}>
                        Path {scene.path ?? scene.relative_orbit ?? "-"}
                      </Badge>
                      <Badge variant={scene.frame ? "success" : "warning"}>Frame {scene.frame ?? "-"}</Badge>
                      <Badge variant={scene.footprint_bbox ? "success" : "neutral"}>
                        {scene.footprint_bbox ? "有范围" : "无范围"}
                      </Badge>
                      <Badge
                        className="px-2 py-0.5 text-[11px]"
                        variant={
                          (scene.footprint_bbox || scene.footprint_geojson) &&
                          (scene.path || scene.relative_orbit) &&
                          scene.frame &&
                          scene.orbit_direction
                            ? "success"
                            : "neutral"
                        }
                      >
                        {(scene.footprint_bbox || scene.footprint_geojson) &&
                        (scene.path || scene.relative_orbit) &&
                        scene.frame &&
                        scene.orbit_direction
                          ? "元数据完整"
                          : "部分元数据"}
                      </Badge>
                    </div>
                  </div>
                ))}
                </div>
              </div>
            </div>
          )}
          {checkReport && (
            <div className="rounded-md border bg-muted/30 p-3 text-xs">
              <div className="mb-2 flex items-center justify-between">
                <Badge variant={checkReport.has_errors ? "warning" : "success"}>
                  {checkReport.has_errors ? "存在阻断项" : "核查通过"}
                </Badge>
                <span className="text-muted-foreground">{issues.length} 条问题</span>
              </div>
              {issues.slice(0, 3).map((it, i) => (
                <div key={i} className="truncate text-muted-foreground">
                  {String(it.code)} · {String(it.message)}
                </div>
              ))}
            </div>
          )}
        </div>
      </Section>
    );
  }

  function renderManualSceneImportControls() {
    return (
          <div className="space-y-3">
            <div className="text-xs leading-5 text-muted-foreground">
              从 ASF 官方 py、metalink、metadata、CSV、GeoJSON、下载 URL 或颗粒名识别 Sentinel-1 候选影像。
            </div>
            <Textarea
              value={sceneText}
              onChange={(e) => setSceneText(e.target.value)}
              placeholder={"粘贴 ASF 场景名、下载 URL 或购物车内容\nS1A_IW_SLC__1SDV_..."}
              className="min-h-[82px] font-mono text-xs"
              spellCheck={false}
            />
            <div className="grid grid-cols-2 gap-2">
              <Button
                onClick={() => void handleSceneImport(() => importScenesText(sceneText))}
                disabled={sceneBusy || !sceneText.trim()}
              >
                {sceneBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardPaste className="h-4 w-4" />}
                导入粘贴内容
              </Button>
              <Button variant="outline" onClick={onBrowseAndImportSceneFile} disabled={sceneBusy}>
                <FolderOpen className="h-4 w-4" />
                选 ASF 文件
              </Button>
            </div>
            {sceneBusy && (
              <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-xs">
                <div className="flex items-center gap-2 font-medium">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                  正在解析并补全 ASF 元数据
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-primary/10">
                  <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
                </div>
              </div>
            )}
            <ErrorLine text={sceneError} />
          </div>
    );
  }

  function renderSentinel1Panel() {
    return (
      <div className="space-y-3">
        {renderAsfSearchSection()}
        <Section
          title="Sentinel-1 工作台"
          desc="在线筛选和本地文件检索得到的候选影像统一进入这里；下载时再选择输出目录。"
          icon={CloudDownload}
        >
          <div className="space-y-3">
            {(creds === null || earthdataAuthChecking) && (
              <div className="rounded-2xl border border-primary/25 bg-primary/10 px-3 py-2 text-xs shadow-sm backdrop-blur-xl">
                <div className="flex items-start gap-2">
                  <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary" />
                  <div className="min-w-0 flex-1 leading-5">
                    <div className="font-medium">正在检查 Earthdata/ASF 凭据</div>
                    <div className="text-muted-foreground">会读取已保存 Token、账号密码、环境变量或 netrc；检测失败后不会反复重试。</div>
                  </div>
                </div>
              </div>
            )}
            {creds && !earthdataConfigured && !earthdataAuthChecking && (
              <div className="rounded-2xl border border-warning/35 bg-warning/10 px-3 py-2 text-xs shadow-sm backdrop-blur-xl">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                  <div className="min-w-0 flex-1 leading-5">
                    <div className="font-medium">开始下载前需要先配置 Earthdata/ASF 凭据</div>
                    <div className="text-muted-foreground">
                      请在设置中保存 Earthdata Token 或账号密码；没有凭据时不会启动 Sentinel-1 下载队列。
                    </div>
                  </div>
                  <Button type="button" size="sm" variant="outline" onClick={() => setPanel("settings")}>
                    去设置
                  </Button>
                </div>
              </div>
            )}
            {earthdataInvalid && (
              <div className="rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-2 text-xs shadow-sm backdrop-blur-xl">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                  <div className="min-w-0 flex-1 leading-5">
                    <div className="font-medium">Earthdata/ASF 凭据可能已过期或失效</div>
                    <div className="text-muted-foreground">
                      {earthdataAuth?.message || "请重新保存 Earthdata Token 或账号密码。"}
                    </div>
                  </div>
                  <Button type="button" size="sm" variant="outline" onClick={() => setPanel("settings")}>
                    去设置
                  </Button>
                </div>
              </div>
            )}
            <div className="rounded-2xl border border-white/50 bg-white/45 p-3 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
              {kv("候选影像", scenes.length ? `${scenes.length} 景` : "未导入")}
              {kv("已勾选", selectedDownloadSceneIdList.length)}
              {kv("下载目录", "点击工作台内下载按钮时选择")}
            </div>
            <label className="grid grid-cols-[1fr_92px] items-center gap-2 rounded-2xl border border-white/45 bg-white/35 px-3 py-2 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
              <span>
                <span className="block font-medium">下载并发</span>
                <span className="text-[11px] text-muted-foreground">默认 2；进行中请求不强制中断，后续启动或追加批次生效。</span>
              </span>
              <Input
                type="number"
                min={1}
                max={8}
                value={asfConcurrency}
                onChange={(e) => setAsfConcurrency(e.target.value)}
                className="h-8 text-center"
              />
            </label>
            <label className="flex items-center justify-between gap-3 rounded-2xl border border-white/45 bg-white/35 px-3 py-2 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
              <span>
                <span className="block font-medium">建立 SLC / GRD 子目录</span>
                <span className="text-[11px] text-muted-foreground">
                  未勾选时直接写入所选目录；完整文件会跳过，.part 文件会继续。
                </span>
              </span>
              <input
                type="checkbox"
                checked={asfUseProductSubdir}
                onChange={(event) => setAsfUseProductSubdir(event.target.checked)}
                className="h-4 w-4 shrink-0 accent-primary"
              />
            </label>
            <Button
              onClick={() => openSceneWorkspace()}
              disabled={scenes.length === 0}
              className="w-full"
              title={scenes.length === 0 ? "请先完成在线筛选或本地文件检索。" : undefined}
            >
              <Maximize2 className="h-4 w-4" />
              打开 Sentinel-1 下载工作台
            </Button>
            <ErrorLine text={asfError} />
          </div>
        </Section>
      </div>
    );
  }

  function renderDemResultCard() {
    if (!demRun) return null;
    const logs = demRunLogLines(demRun);
    const demGdalComponent = componentStatus?.components.find((item) => item.id === "dem-gdal");
    const componentFailure = needsDemGdalComponent([demRun.summary_line, ...logs].join("\n"));
    const componentReady = !!demGdalComponent?.runtime_available;
    const needsComponent = componentFailure && !componentReady;
    const previousComponentFailure = componentFailure && componentReady;
      const title =
        demRunSource === "local-ellipsoid"
          ? "本地 DEM 椭球高转换结果"
          : demRunSource === "local-sarscape"
            ? "本地 DEM SARscape 格式转换结果"
        : demRunSource === "download-only"
          ? "DEM 下载结果"
          : "DEM 下载并转换椭球高结果";
    const skipped = Number(demRun.skipped ?? 0);
    const demPaths = demRunDisplayPaths(demRun);
    return (
      <div className="rounded-2xl border border-white/45 bg-white/35 p-3 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold">{title}</div>
            <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{demRun.summary_line}</div>
          </div>
          <Badge variant={demRun.has_failures ? "warning" : skipped > 0 ? "neutral" : "success"}>
            {demRun.has_failures ? "需检查" : skipped > 0 ? "已跳过" : "已完成"}
          </Badge>
        </div>
        {needsComponent && (
          <div className="mt-3 rounded-2xl border border-warning/35 bg-warning/10 px-3 py-2 text-xs leading-5">
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
              <div className="min-w-0 flex-1">
                <div className="font-medium">
                  {demGdalComponent?.state === "partial" ? "DEM/GDAL 组件缺少 EGM2008 网格" : "需要安装或修复 DEM/GDAL 高级转换组件"}
                </div>
                <div className="text-muted-foreground">
                  {demGdalComponent?.state === "partial"
                    ? "已识别 GDAL/PROJ 运行库，但没有 EGM2008 网格；COP30/COP90 转椭球高会被阻止。"
                    : "当前缺少 GDAL/PROJ/EGM2008 所需运行数据，安装或修复组件后再转换。"}
                </div>
              </div>
              <Button size="sm" variant="outline" onClick={openSettingsComponents}>
                去修复组件
              </Button>
            </div>
          </div>
        )}
        {previousComponentFailure && (
          <div className="mt-3 rounded-2xl border border-success/30 bg-success/10 px-3 py-2 text-xs leading-5 text-success">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <div className="font-medium">组件现在已可用</div>
                <div className="text-success/80">这条记录是修复组件前的失败结果，请重新执行 DEM 转换。</div>
              </div>
            </div>
          </div>
        )}
        <Progress value={100} className="mt-2 h-1.5" />
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          {kv("任务数", demRun.total)}
          {kv("成功", demRun.succeeded ?? demRun.copied ?? 0)}
          {kv("跳过", skipped)}
          {kv("失败", demRun.failed ?? 0)}
          {kv("下载结果", demRun.results_path ? pathBaseName(demRun.results_path) : "-")}
          {kv("转换结果", demRun.conversion_results_path ? pathBaseName(demRun.conversion_results_path) : "-")}
        </div>
        <div className="mt-2 space-y-1.5">
          {[
            { label: "原始 DEM", path: demPaths.raw },
            ...(demRunSource === "download-only"
              ? []
              : [
                  { label: "椭球高 DEM", path: demPaths.ellipsoid },
                  ...(demRunSource === "local-ellipsoid" ? [] : [{ label: "SARscape DEM", path: demPaths.sarscape }]),
                ]),
          ].map(({ label, path }) => (
            <div key={label} className="rounded-md border bg-muted/20 px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="shrink-0 text-muted-foreground">{label}</span>
                <span className="min-w-0 flex-1 truncate text-right font-mono text-[11px]" title={String(path || "")}>
                  {path ? pathBaseName(String(path)) : "-"}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 px-2"
                  disabled={!path}
                  onClick={() => void openLocalPath(pathDirName(String(path || "")))}
                >
                  <FolderOpen className="h-3.5 w-3.5" />
                  打开目录
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  function renderLocalDemStatusCard() {
    if (!localDemAction) return null;
    const plan = localDemPreview?.plan;
    const ellipsoid = jsonField(plan, "ellipsoid_dem_path");
    const sarscape = jsonField(plan, "sarscape_ready_dem_path");
    const out = effectiveLocalDemOutputDir || pathDirName(localDem);
    const modeLabel = localDemAction === "ellipsoid" ? "转换椭球高" : "转为 SARscape 格式";
    const lines = [
      `正在执行：${modeLabel}`,
      localDem ? `源 DEM：${pathBaseName(localDem)}` : "",
      ellipsoid ? `椭球高 DEM：${pathBaseName(ellipsoid)}` : "",
      localDemAction === "sarscape" && sarscape ? `SARscape DEM：${pathBaseName(sarscape)}` : "",
    ].filter(Boolean);
    return (
      <div className="rounded-2xl border border-primary/25 bg-primary/10 p-3 text-xs shadow-sm backdrop-blur-xl">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              本地 DEM 转换中
            </div>
            <div className="mt-1 text-muted-foreground">转换完成后会在这里显示结果文件和日志。</div>
          </div>
          <Badge variant="warning">运行中</Badge>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          {kv("任务", modeLabel)}
          {kv("输出目录", out ? pathBaseName(out) : "-")}
        </div>
        <div className="mt-2 space-y-1 rounded-xl border border-white/45 bg-white/45 px-2 py-1.5 font-mono text-[11px] leading-5 dark:border-white/10 dark:bg-white/10">
          {lines.map((line) => (
            <div key={line} className="truncate" title={line}>
              {line}
            </div>
          ))}
        </div>
        <div className="mt-2 flex justify-end">
          <Button variant="outline" size="sm" disabled={!out} onClick={() => void openLocalPath(out)}>
            <FolderOpen className="h-3.5 w-3.5" />
            打开目录
          </Button>
        </div>
      </div>
    );
  }

  function renderDemPanel() {
    const previewStem = demSourceStem(dataset);
    const previewOutputRoot = resolvedDemDownloadOutputDir || "开始下载时选择输出目录";
    const localPreviewOutputRoot = effectiveLocalDemOutputDir || "默认使用所选 DEM 所在目录";
    const previewBbox = manualBboxReady
      ? `W ${manualDemBbox.west.toFixed(5)} / E ${manualDemBbox.east.toFixed(5)} / S ${manualDemBbox.south.toFixed(5)} / N ${manualDemBbox.north.toFixed(5)}`
      : "等待 AOI 或经纬度范围";
    return (
      <div className="space-y-3">
        <Section
          title="DEM"
          desc="在线 DEM 下载和本地 DEM 转换在同一入口中切换，任务结果进入下载中心和历史记录。"
          icon={Mountain}
        >
          <div className="space-y-3">
            {renderCardModeSwitch(
              [
                { key: "online" as const, label: "在线 DEM 下载" },
                { key: "local" as const, label: "本地DEM转换" },
              ],
              demSourceMode,
              setDemSourceMode,
            )}
            {demSourceMode === "online" ? (
              <>
            <select
              value={dataset}
              onChange={(e) => {
                const nextDataset = e.target.value;
                setDataset(nextDataset);
                setDemError(null);
                setDemRun(null);
                setDemRunSource(null);
                void setDemDataset(nextDataset).then((res) => {
                  if (!res.ok) setDemError(compactDemLogText(`${res.error}${res.code ? ` (${res.code})` : ""}`));
                });
              }}
              className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {DEM_DATASET_GROUPS.map((group) => (
                <optgroup key={group.label} label={group.label}>
                  {group.options.map((item) => (
                    <option key={item.value} value={item.value} disabled={!item.enabled}>
                      {item.label}
                      {item.hint ? ` · ${item.hint}` : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <div className="grid grid-cols-2 gap-2">
              <Input value={demWest} onChange={(e) => setDemWest(e.target.value)} placeholder="West" />
              <Input value={demEast} onChange={(e) => setDemEast(e.target.value)} placeholder="East" />
              <Input value={demSouth} onChange={(e) => setDemSouth(e.target.value)} placeholder="South" />
              <Input value={demNorth} onChange={(e) => setDemNorth(e.target.value)} placeholder="North" />
            </div>
            <div className="rounded-2xl border border-white/45 bg-white/35 p-3 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="font-semibold">DEM 输出预览</div>
                <Badge variant={manualBboxReady ? "success" : "neutral"}>
                  {manualBboxReady ? "范围已就绪" : "等待范围"}
                </Badge>
              </div>
              <div className="space-y-1.5">
                {kv("数据源", demDatasetLabel(dataset))}
                {kv("范围", previewBbox)}
                {kv("输出根目录", previewOutputRoot)}
                {kv("原始 tif", `${previewStem}.tif`)}
                {kv("椭球高 tif", selectedDemAlreadyEllipsoidal ? "原始 DEM 已是椭球高" : `${previewStem}_ellipsoid.tif`)}
                {kv("SARscape 主文件", `${previewStem}_dem`)}
                {kv("SARscape 头文件", `${previewStem}_dem.hdr`)}
              </div>
              <div className="mt-2 text-[11px] leading-5 text-muted-foreground">
                {selectedDemAlreadyEllipsoidal
                  ? "当前数据源已经是 WGS84 椭球高，下载后无需高程基准转换；如需 SARscape，可直接导出 ENVI _dem + .hdr + .sml。"
                  : "DEM 下载只保存原始 GeoTIFF；下载并转换时会生成椭球高 GeoTIFF，并导出 SARscape 常用的 ENVI _dem + .hdr + .sml。"}
              </div>
            </div>
            {renderOutputParameters(
              selectedDemAlreadyEllipsoidal
                ? "DEM 下载保存原始 GeoTIFF；SARscape 导出按钮不会执行高程转换。"
                : "DEM 下载保存原始 GeoTIFF；转换按钮会额外生成椭球高 GeoTIFF 和 SARscape 文件。",
              {
              value: demDownloadOutputDir,
              onChange: setDemDownloadOutputDir,
              onBrowse: onBrowseDemDownloadOutput,
              placeholder: resolvedDemDownloadOutputDir || "开始下载时选择 DEM 下载输出目录",
              title: "浏览 DEM 下载输出目录",
              },
            )}
            {!opentopoConfigured && (
              <div className="rounded-2xl border border-warning/35 bg-warning/10 px-3 py-2 text-xs shadow-sm backdrop-blur-xl">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                  <div className="min-w-0 flex-1 leading-5">
                    <div className="font-medium">DEM 在线下载需要 OpenTopography API Key</div>
                    <div className="text-muted-foreground">本地 DEM 转换可以直接使用；在线下载前请先到设置保存 Key。</div>
                  </div>
                  <Button type="button" size="sm" variant="outline" onClick={() => setPanel("settings")}>
                    去设置
                  </Button>
                </div>
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                onClick={() => void onRunDemDownload(false)}
                disabled={demDownloadBusy || !opentopoConfigured}
                className="w-full"
                title={
                  !opentopoConfigured
                    ? "请先在设置里保存 OpenTopography API Key"
                    : demDownloadBusy && demDownloadAction !== "download-only"
                      ? "另一个 DEM 任务正在执行"
                      : "下载原始 GeoTIFF，不执行椭球高/SARscape 转换"
                }
              >
                {demDownloadAction === "download-only" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
                DEM 下载
              </Button>
              <Button
                onClick={() => void onRunDemDownload(true)}
                disabled={demDownloadBusy || !opentopoConfigured}
                className="w-full"
                title={
                  !opentopoConfigured
                    ? "请先在设置里保存 OpenTopography API Key"
                    : demDownloadBusy && demDownloadAction !== "download-convert"
                      ? "另一个 DEM 任务正在执行"
                      : undefined
                }
              >
                {demDownloadAction === "download-convert" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
                {selectedDemAlreadyEllipsoidal ? "下载并导出 SARscape" : "下载并转换椭球高"}
              </Button>
            </div>
            <ErrorLine text={demError} />
            {needsDemGdalComponent(demError) && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full"
                onClick={openSettingsComponents}
              >
                <CloudDownload className="h-4 w-4" />
                去设置安装/修复 DEM/GDAL 组件
              </Button>
            )}
              </>
            ) : (
              <>
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <Input value={localDem} readOnly placeholder="选择本地 DEM" className="font-mono text-xs" />
              <Button variant="outline" size="icon" onClick={onBrowseLocalDem}>
                <FolderOpen className="h-4 w-4" />
              </Button>
            </div>
            <select
              value={localDatum}
              onChange={(e) => setLocalDatum(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="auto">自动识别源高程基准</option>
              <option value="EGM96">EGM96 正高</option>
              <option value="EGM2008">EGM2008 正高</option>
              <option value="WGS84_ELLIPSOID">无需高程转换（WGS84 椭球高）</option>
            </select>
            {localDem && (
              <div
                className={cn(
                  "rounded-md border px-3 py-2 text-[11px] leading-5",
                  localDemPreviewError
                    ? "border-warning/35 bg-warning/10 text-warning"
                    : localDemSourceUnknown
                      ? "border-warning/35 bg-warning/10 text-warning"
                      : localDemAlreadyEllipsoidal
                      ? "border-success/30 bg-success/10 text-success"
                      : "border-primary/25 bg-primary/10 text-muted-foreground",
                )}
              >
                <div className="flex items-start gap-2">
                  {localDemPreviewBusy ? (
                    <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                  ) : localDemSourceUnknown ? (
                    <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                  ) : localDemAlreadyEllipsoidal ? (
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                  ) : (
                    <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                  )}
                  <div className="min-w-0">
                    {localDemPreviewError
                      ? localDemPreviewError
                      : localDemSourceUnknown
                        ? "无法自动识别源高程基准。请手动选择 EGM96、EGM2008 或 WGS84 椭球高；未确认前不执行转换，避免错误高程基准。"
                      : localDemAlreadyEllipsoidal
                        ? "已识别或指定为 WGS84 椭球高，无需执行椭球高转换；可直接导出 SARscape 格式。"
                        : localDemPreview?.auto.message || "正在识别 DEM 高程基准。"}
                  </div>
                </div>
              </div>
            )}
            {renderOutputParameters("本地 DEM 转换输出到此目录；留空时默认使用所选 DEM 所在文件夹。", {
              value: localDemOutputDir,
              onChange: setLocalDemOutputDir,
              onBrowse: onBrowseLocalDemOutput,
              placeholder: localPreviewOutputRoot,
              title: "浏览本地 DEM 转换输出目录",
              showAoiDownloadMode: false,
            })}
            <div className={cn("grid gap-2", localDemAlreadyEllipsoidal ? "grid-cols-1" : "grid-cols-2")}>
              {!localDemAlreadyEllipsoidal && (
                <Button
                  variant="outline"
                  onClick={() => void onRunLocalDem("ellipsoid")}
                  disabled={!!localDemAction || !localDem || localDemActionBlocked}
                  className="w-full"
                >
                  {localDemAction === "ellipsoid" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  转换椭球高
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => void onRunLocalDem("sarscape")}
                disabled={!!localDemAction || !localDem || localDemActionBlocked}
                className="w-full"
              >
                {localDemAction === "sarscape" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                转为SARscape格式
              </Button>
            </div>
            {renderLocalDemStatusCard()}
              </>
            )}
            {renderDemResultCard()}
          </div>
        </Section>
      </div>
    );
  }

  function renderOrbitPanel() {
    return (
      <div className="space-y-3">
        <Section
          title="Orbit"
          desc="在线轨道匹配和本地文件检索在同一入口中切换；识别结果统一进入精密轨道工作台。"
          icon={Orbit}
        >
          <div className="space-y-3">
            {renderCardModeSwitch(
              [
                { key: "online" as const, label: "在线轨道匹配下载" },
                { key: "local" as const, label: "本地文件检索" },
              ],
              orbitSourceMode,
              setOrbitSourceMode,
            )}
            {orbitSourceMode === "local" ? (
              renderSceneSourceControls(
                "用于没有经过 Sentinel-1 在线筛选、但本地已有 SAR 文件或 ASF 官方清单的情况；识别后进入同一个轨道工作台。",
                "orbit",
                true,
              )
            ) : (
              <>
            <div
              className={cn(
                "rounded-2xl border p-3 text-xs shadow-sm backdrop-blur-xl",
                orbitCandidateScenes.length
                  ? "border-success/35 bg-success/10"
                  : "border-white/50 bg-white/45 dark:border-white/10 dark:bg-white/10",
              )}
            >
              {kv("影像源", orbitUsesManualSource ? "本地文件检索" : "Sentinel-1 候选影像")}
              {kv("候选影像", orbitCandidateScenes.length ? `${orbitCandidateScenes.length} 景` : "未导入")}
              {kv("已勾选", selectedOrbitSceneIdList.length)}
              {kv("下载目录", "点击工作台内下载按钮时选择")}
            </div>
            <label className="grid grid-cols-[1fr_92px] items-center gap-2 rounded-2xl border border-white/45 bg-white/35 px-3 py-2 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
              <span>
                <span className="block font-medium">轨道并发</span>
                <span className="text-[11px] text-muted-foreground">默认 10；下一批轨道任务生效。</span>
              </span>
              <Input
                type="number"
                min={1}
                max={10}
                value={orbitConcurrency}
                onChange={(e) => setOrbitConcurrency(e.target.value)}
                className="h-8 text-center"
              />
            </label>
            <label className="flex items-center justify-between gap-3 rounded-2xl border border-white/45 bg-white/35 px-3 py-2 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
              <span>
                <span className="block font-medium">建立 Sentinel_Orbit 子目录</span>
                <span className="text-[11px] text-muted-foreground">
                  未勾选时 EOF 直接写入所选目录；勾选时写入所选目录\Sentinel_Orbit。
                </span>
              </span>
              <input
                type="checkbox"
                checked={orbitUseSubdir}
                onChange={(event) => setOrbitUseSubdir(event.target.checked)}
                className="h-4 w-4 shrink-0 accent-primary"
              />
            </label>
            <Button
              onClick={() => openOrbitWorkspace()}
              disabled={orbitCandidateScenes.length === 0}
              className="w-full"
              title={orbitCandidateScenes.length === 0 ? "请先完成 Sentinel-1 在线筛选，或在上方进行本地文件检索。" : undefined}
            >
              <Maximize2 className="h-4 w-4" />
              打开精密轨道工作台
            </Button>
            <div className="rounded-md border bg-muted/30 p-3 text-xs">
              {kv("保存目录", orbitUseSubdir ? "所选目录\\Sentinel_Orbit" : "所选目录")}
              {kv("控制说明", "暂停/结束会在当前 EOF 请求结束后生效")}
            </div>
            <ErrorLine text={orbitError} />
              </>
            )}
          </div>
        </Section>
      </div>
    );
  }

  function renderGacosPanel() {
    return (
      <div className="space-y-3">
        {renderSceneSourceControls(
          "GACOS 请求日期从 SAR 影像采集日期解析；可直接导入 ASF 官方文件，或扫描本地 SLC/GRD 目录。",
        )}
        <Section
          title="GACOS 请求"
          desc="根据当前场景日期生成 ZTD 请求清单；真正提交仍需按 GACOS 网站要求处理。"
          icon={Database}
        >
          <div className="space-y-3">
            {renderOutputParameters("GACOS 请求清单和后续导入记录会放在该输出目录下。")}
            {!gacosConfigured && (
              <div className="rounded-2xl border border-warning/35 bg-warning/10 px-3 py-2 text-xs shadow-sm backdrop-blur-xl">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                  <div className="min-w-0 flex-1 leading-5">
                    <div className="font-medium">GACOS 请求需要先配置接收邮箱</div>
                    <div className="text-muted-foreground">保存邮箱后再生成请求清单，避免后续提交时信息缺失。</div>
                  </div>
                  <Button type="button" size="sm" variant="outline" onClick={() => setPanel("settings")}>
                    去设置
                  </Button>
                </div>
              </div>
            )}
            <Button
              onClick={onGacosPlan}
              disabled={gacosBusy || scenes.length === 0 || !gacosConfigured}
              className="w-full"
              title={!gacosConfigured ? "请先在设置里保存 GACOS 接收邮箱" : undefined}
            >
              {gacosBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
              生成请求清单
            </Button>
            <ErrorLine text={gacosError} />
            {gacosPlan && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                {kv("日期数", String((gacosPlan.unique_dates as string[] | undefined)?.length ?? 0))}
                {kv("批次", String((gacosPlan.batches as Json[] | undefined)?.length ?? 0))}
              </div>
            )}
          </div>
        </Section>
        <Section title="GACOS 凭据" desc="生成请求前会读取已保存的接收邮箱。" icon={Mail}>
          {gacosConfigured ? (
            <div className="rounded-2xl border border-success/25 bg-success/10 px-3 py-2 text-xs leading-5">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                <div>
                  <div className="font-medium">GACOS 邮箱已设置</div>
                  <div className="text-muted-foreground">生成请求清单时会自动使用，无需重复确认。</div>
                </div>
              </div>
            </div>
          ) : (
            <Button variant="outline" onClick={() => setPanel("settings")} className="w-full">
              <Settings className="h-4 w-4" />
              去设置接收邮箱
            </Button>
          )}
        </Section>
      </div>
    );
  }

  function renderResourceScopeBar() {
    const currentSource = SOURCE_TABS.find((item) => item.key === source);
    return (
      <section className="glass-panel px-3 py-3" data-tour="scope-panel">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={ctx?.region?.has_aoi ? "success" : "neutral"}>
                {ctx?.region?.has_aoi ? "AOI 已绑定" : "AOI 可选"}
              </Badge>
              <span className="truncate text-sm font-semibold">{currentSource?.label ?? "资源下载"}</span>
            </div>
            <div className="mt-1 truncate text-xs text-muted-foreground">
              {ctx?.region?.has_aoi ? "默认沿用已绑定 AOI" : "未绑定 AOI 时也可检索"} · 下载开始前再确认输出目录
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={() => setAoiToolsOpen((value) => !value)}>
            <MapPinned className="h-4 w-4" />
            {aoiToolsOpen ? "收起范围" : "更换范围"}
          </Button>
        </div>
      </section>
    );
  }

  function renderResourcePanel() {
    let content: React.ReactNode;
    if (source === "dem") content = renderDemPanel();
    else if (source === "orbit") content = renderOrbitPanel();
    else if (source === "gacos") content = renderGacosPanel();
    else if (source === "sentinel2") {
      content = (
        <div className="space-y-3">
          <Section
            title="Sentinel-2"
            desc="该入口已预留，后续可以复用同一套地图、AOI、目录和下载中心逻辑扩展。"
            icon={Radar}
          >
            <Badge variant="neutral">即将接入</Badge>
          </Section>
        </div>
      );
    } else {
      content = renderSentinel1Panel();
    }
    return (
      <div className="space-y-3">
        {renderResourceScopeBar()}
        {aoiToolsOpen && renderAoiTools()}
        {content}
      </div>
    );
  }

  function renderDownloadCenter() {
    const asfActiveTaskCards = asfDownloadStatuses.map((status, index) => {
      const taskId = status.task_id || `asf-active-${index}`;
      const taskDownloads = status.active_downloads?.length
        ? status.active_downloads
        : status.current_scene
          ? [
              {
                scene_id: status.current_scene,
                bytes: status.current_bytes ?? 0,
                expected_size: status.current_expected_size,
              },
            ]
          : [];
      const taskTransferredBytes = (status.done_bytes ?? 0) + (status.current_bytes ?? 0);
      const taskPct = status.total_bytes
        ? Math.round((taskTransferredBytes / status.total_bytes) * 100)
        : status.total > 0
          ? Math.round((status.done / status.total) * 100)
          : 0;
      const taskSnapshot = asfTaskSnapshots[taskId];
      return {
            id: taskId,
            name: "Sentinel-1 数据下载",
            status: status.state,
            progress: taskPct,
            count: `${status.done}/${status.total}`,
            detail:
              taskDownloads.length > 0
                ? `正在下载 ${taskDownloads.length} / ${status.concurrency ?? taskDownloads.length} 景`
                : status.summary_line || "等待下一个场景",
            outputDir: status.output_dir || status.results_path || "",
            activeDownloads: taskDownloads,
            metrics: [
              ["已下载", status.total_bytes ? `${fmtBytes(taskTransferredBytes)} / ${fmtBytes(status.total_bytes)}` : fmtBytes(taskTransferredBytes)],
              ["速度", fmtRate(status.bytes_per_second)],
              ["用时", fmtDuration(status.elapsed_seconds)],
              ["并发", status.concurrency ?? 1],
              ["断点续传", status.resume_supported ? "支持 .part" : "未知"],
              ["失败", (status.failed ?? 0) + (status.interrupted ?? 0)],
            ],
            controls: (
              <div className="grid grid-cols-4 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={status.state !== "running"}
                  onClick={() => void pauseAsfDownload(taskId).then(() => getDownloadStatus().then(setDlStatus))}
                >
                  <Pause className="h-4 w-4" />
                  暂停
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={status.state !== "paused"}
                  onClick={() => void resumeAsfDownload(taskId).then(() => getDownloadStatus().then(setDlStatus))}
                >
                  <Play className="h-4 w-4" />
                  继续
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={status.state !== "running" && status.state !== "paused" || asfStopping}
                  onClick={() => void onStopAsfDownload(taskId)}
                >
                  {asfStopping ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                  {asfStopping ? "结束中" : "结束"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!status.retry_supported}
                  onClick={() => void onRetryAsf(taskId)}
                  title={status.retry_hint || "重试失败/中断的 ASF 场景"}
                >
                  <RotateCcw className="h-4 w-4" />
                  重试
                </Button>
              </div>
            ),
            workspaceAction: (
              <Button
                type="button"
                size="sm"
                className="w-full justify-center"
                disabled={!taskSnapshot && activeAsfTaskScenes.length === 0 && asfTaskScenes.length === 0}
                title={!taskSnapshot && activeAsfTaskScenes.length === 0 && asfTaskScenes.length === 0 ? "该下载任务还没有可打开的任务快照。" : undefined}
                onClick={() => {
                  if (taskSnapshot) {
                    setActiveAsfTaskSnapshotId(taskId);
                    setAsfTaskScenes(taskSnapshot.scenes);
                  } else if (activeAsfTaskScenes.length) {
                    setAsfTaskScenes(activeAsfTaskScenes);
                  }
                  openSceneWorkspace("task");
                }}
              >
                <Satellite className="h-4 w-4" />
                打开任务快照
              </Button>
            ),
            log: status.log?.map(formatDownloadLogEntry) ?? [],
          };
    });
    const activeTasks = [
      ...asfActiveTaskCards,
      orbitStatus && orbitActive
        ? {
            id: "orbit-active",
            name: "Sentinel-1 精密轨道下载",
            status: orbitStatus.state,
            progress: orbitPct,
            count: `${orbitStatus.done}/${orbitStatus.total}`,
            detail: activeOrbitDownloads.length ? "正在匹配并下载精密轨道" : orbitStatus.summary_line || "等待下一个 EOF",
            outputDir: orbitStatus.orbit_dir || "",
            activeDownloads: activeOrbitDownloads.map((item) => ({
              scene_id: item.scene_id,
              bytes: orbitStatus.done_bytes ?? orbitStatus.done,
              expected_size: orbitStatus.done_bytes ? undefined : orbitStatus.total,
            })),
            metrics: [
              ["轨道目录", orbitStatus.orbit_dir ? pathBaseName(orbitStatus.orbit_dir) : "-"],
              ["速度", fmtRate(orbitStatus.bytes_per_second)],
              ["用时", fmtDuration(orbitStatus.elapsed_seconds)],
              ["并发", orbitStatus.concurrency ?? 10],
              ["成功", orbitStatus.succeeded],
              ["跳过", orbitStatus.skipped],
              ["未发布/不可用", orbitStatus.unavailable],
              ["失败", orbitStatus.failed ?? 0],
            ],
            controls: (
              <div className="grid grid-cols-3 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={orbitStatus.state !== "running"}
                  onClick={() => void pauseOrbitDownload().then(() => getOrbitDownloadStatus().then(setOrbitStatus))}
                >
                  <Pause className="h-4 w-4" />
                  暂停
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={orbitStatus.state !== "paused"}
                  onClick={() => void resumeOrbitDownload().then(() => getOrbitDownloadStatus().then(setOrbitStatus))}
                >
                  <Play className="h-4 w-4" />
                  继续
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => void stopOrbitDownload().then(() => getOrbitDownloadStatus().then(setOrbitStatus))}
                >
                  <Square className="h-4 w-4" />
                  结束
                </Button>
              </div>
            ),
            workspaceAction: (
              <Button
                type="button"
                size="sm"
                className="w-full justify-center"
                disabled={(orbitTaskScenes.length || orbitCandidateScenes.length) === 0}
                onClick={() => openOrbitWorkspace(orbitTaskScenes.length ? "task" : "current")}
              >
                <Orbit className="h-4 w-4" />
                打开任务快照
              </Button>
            ),
            log: orbitStatus.log?.map(formatDownloadLogEntry) ?? [],
          }
        : null,
      demStatus && demActive
        ? {
            id: "dem-active",
            name: demStatus.convert ? "DEM 下载并转换椭球高" : "DEM 下载",
            status: demStatus.state,
            progress: demStatus.done && demStatus.total ? Math.round((demStatus.done / demStatus.total) * 100) : 18,
            count: `${demStatus.done}/${demStatus.total || 1}`,
            detail: demStatus.current_scene ? `正在下载 ${demStatus.current_scene}` : demStatus.summary_line || "正在执行 DEM 任务",
            outputDir: demStatus.output_dir || "",
            activeDownloads: demStatus.current_scene
              ? [
                  {
                    scene_id: demStatus.current_scene,
                    bytes: demStatus.done_bytes ?? 0,
                  },
                ]
              : [],
            metrics: [
              ["数据源", demStatus.dataset || "-"],
              ["已下载", fmtBytes(demStatus.done_bytes ?? 0)],
              ["速度", fmtRate(demStatus.bytes_per_second)],
              ["用时", fmtDuration(demStatus.elapsed_seconds)],
              ["输出目录", demStatus.output_dir ? pathBaseName(demStatus.output_dir) : "-"],
              ["状态", demStopping ? "结束中" : statusLabel(demStatus.state)],
            ],
            controls: (
              <div className="grid grid-cols-3 gap-2">
                <Button variant="outline" size="sm" disabled title="DEM 下载当前支持结束，不支持暂停队列。">
                  <Pause className="h-4 w-4" />
                  暂停
                </Button>
                <Button variant="outline" size="sm" disabled title="DEM 下载当前支持结束，不支持暂停队列。">
                  <Play className="h-4 w-4" />
                  继续
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={demStopping}
                  onClick={() => void onStopDemDownload()}
                >
                  {demStopping ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                  {demStopping ? "结束中" : "结束"}
                </Button>
              </div>
            ),
            log: demStatus.log?.map(formatDownloadLogEntry) ?? [],
          }
        : null,
    ].filter(Boolean) as {
      id: string;
      name: string;
      status: string;
      progress: number;
      count: string;
      detail: string;
      metrics: [string, string | number | null | undefined][];
      controls: React.ReactNode;
      workspaceAction?: React.ReactNode;
      log: string[];
      activeDownloads?: NonNullable<DownloadStatus["active_downloads"]>;
      outputDir?: string;
    }[];
    const pendingAsfQueueItems = pendingAsfTasks.map((task) => ({
      id: task.id,
      name: `${task.name}（待执行）`,
      status: task.status,
      progress: 0,
      count: `${task.sceneIds.length}/${task.snapshot.length}`,
      detail:
        task.status === "failed"
          ? task.error || "启动失败"
          : task.status === "starting"
            ? "正在启动该任务"
            : "下载器忙，已保留目录和任务快照，等待前序任务结束后自动开始。",
      outputDir: task.outputDir,
      activeDownloads: [],
      workspaceAction: (
        <Button
          type="button"
          size="sm"
          className="w-full justify-center"
          onClick={() => {
            setAsfTaskScenes(task.snapshot);
            openSceneWorkspace("task");
          }}
        >
          <Satellite className="h-4 w-4" />
          打开任务快照
        </Button>
      ),
      metrics: [
        ["类型", "Sentinel-1"],
        ["输出目录", task.outputDir ? pathBaseName(task.outputDir) : "-"],
        ["快照影像", task.snapshot.length],
        ["本次下载", task.sceneIds.length],
        ["并发", task.concurrency],
        ["创建时间", formatLogTime(task.createdAt).slice(11)],
      ] as [string, string | number | null | undefined][],
      controls: (
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={task.status === "starting" || dlBusy || dlPendingStop}
            onClick={() => void startQueuedAsfTask(task)}
            title={dlBusy || dlPendingStop ? "前序 Sentinel-1 下载仍在运行，该任务会自动排队启动" : "立即启动该任务"}
          >
            {task.status === "starting" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {task.status === "starting" ? "启动中" : task.status === "failed" ? "重试" : "启动"}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={task.status === "starting"}
            onClick={() => setPendingAsfTasks((prev) => prev.filter((item) => item.id !== task.id))}
          >
            <Trash2 className="h-4 w-4" />
            移除
          </Button>
        </div>
      ),
      log: [
        `任务快照：${task.snapshot.length} 景；本次下载：${task.sceneIds.length} 景。`,
        `输出目录：${task.outputDir}`,
        task.error ? `错误：${task.error}` : "",
      ].filter(Boolean),
    }));
    const archiveItems = dedupeArchiveItems(downloadArchive);
    const runningDemQueueItems = (demQueueTask ? [demQueueTask] : [])
      .map((task) => {
        const out = archiveTaskOutputDir(task);
        return {
          id: task.id,
          name: task.name || "DEM 下载",
          status: task.status,
          progress: 15,
          count: task.total ? `0/${task.total}` : "运行中",
          detail: task.detail || "正在执行 DEM 任务",
          outputDir: out,
          activeDownloads: [],
          metrics: [
            ["类型", "DEM"],
            ["输出目录", out ? pathBaseName(out) : "-"],
            ["速度", "统计中"],
            ["用时", task.ts ? fmtDuration(Math.max(0, Math.round((Date.now() - task.ts) / 1000))) : "-"],
            ["并发", 1],
            ["状态", statusLabel(task.status)],
            ["开始时间", task.ts ? formatLogTime(task.ts).slice(11) : "-"],
          ] as [string, string | number | null | undefined][],
          controls: (
            <div className="grid grid-cols-3 gap-2">
              <Button variant="outline" size="sm" disabled>
                <Pause className="h-4 w-4" />
                暂停
              </Button>
              <Button variant="outline" size="sm" disabled>
                <Play className="h-4 w-4" />
                继续
              </Button>
              <Button variant="destructive" size="sm" disabled title="DEM 下载当前仍是单次后端调用，需要后台任务化后才能安全结束。">
                <Square className="h-4 w-4" />
                结束
              </Button>
            </div>
          ),
          workspaceAction: null,
          log: task.logs ?? [task.detail],
        };
      });
    const archivedQueueTasks = archiveItems
      .filter(isRestorableArchiveTask)
      .filter((task) => {
        const kind = archiveTaskKind(task);
        if (kind === "asf" && dlVisible) return false;
        if (kind === "orbit" && orbitActive) return false;
        return true;
      });
    const archivedQueueItems = archivedQueueTasks.map((task) => {
      const out = archiveTaskOutputDir(task);
      const kind = archiveTaskKind(task);
      const restoring = restoringTaskKeys.has(archiveTaskKey(task));
      return {
        id: task.id,
        name: task.name,
        status: task.status,
        progress: 0,
        count: task.total ? `0/${task.total}` : "可继续",
        detail:
          task.status === "paused"
            ? "手动暂停的任务已保留；点击继续会回到原输出目录断点续传。"
            : "上次未完成的任务已保留；点击继续会重新进入队列并跳过已完成文件。",
        outputDir: out,
        activeDownloads: [],
        workspaceAction:
          kind === "asf" || kind === "orbit" ? (
            <Button
              type="button"
              size="sm"
              className="w-full justify-center"
              disabled={kind === "orbit" ? (orbitTaskScenes.length || orbitCandidateScenes.length) === 0 : (asfTaskScenes.length || scenes.length) === 0}
              title={
                (kind === "orbit" ? (orbitTaskScenes.length || orbitCandidateScenes.length) === 0 : (asfTaskScenes.length || scenes.length) === 0)
                  ? kind === "orbit"
                    ? "请先完成 Sentinel-1 在线筛选，或在精密轨道中进行本地文件检索。"
                    : "请先完成 ASF 检索或导入，才能打开任务快照。"
                  : undefined
              }
              onClick={() => (kind === "orbit" ? openOrbitWorkspace(orbitTaskScenes.length ? "task" : "current") : openSceneWorkspace(asfTaskScenes.length ? "task" : "current"))}
            >
              {kind === "orbit" ? <Orbit className="h-4 w-4" /> : <Satellite className="h-4 w-4" />}
              打开任务快照
            </Button>
          ) : null,
        metrics: [
          ["类型", kind === "asf" ? "Sentinel-1" : "精密轨道"],
          ["输出目录", out ? pathBaseName(out) : "-"],
          ["上次状态", statusLabel(task.status)],
          ["记录时间", task.ts ? new Date(task.ts).toLocaleString() : "-"],
        ] as [string, string | number | null | undefined][],
        controls: (
          <div className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={task.status === "running" || restoring}
              onClick={() => void onResumeArchivedTask(task)}
            >
              {task.status === "running" || restoring ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {task.status === "running" || restoring ? "恢复中" : task.status === "failed" ? "重试" : "继续"}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() =>
                setDownloadArchive((prev) =>
                  prev.map((item) =>
                    archiveTaskKey(item) === archiveTaskKey(task)
                        ? {
                            ...item,
                            status: "cancelled",
                            detail: "用户已结束该保留任务。",
                            ts: Date.now(),
                            logs: [...(item.logs ?? []), `[${formatLogTime(Date.now())}] 用户已结束该保留任务。`].slice(-120),
                          }
                      : item,
                  ),
                )
              }
            >
              <Square className="h-4 w-4" />
              结束
            </Button>
          </div>
        ),
        log: task.logs ?? [task.detail],
      };
    });
    const queueTasks = [...activeTasks, ...pendingAsfQueueItems, ...runningDemQueueItems, ...archivedQueueItems];
    const historyTasks = archiveItems.filter(
      (task) =>
        task.status !== "deleted" &&
        !["running", "paused"].includes(task.status) &&
        !isRestorableArchiveTask(task) &&
        !(demQueueTask && archiveTaskKey(task) === archiveTaskKey(demQueueTask)),
    );

    return (
      <div className="space-y-3">
        <Section title="任务队列" desc="进行中和手动暂停的任务保留在这里；完成、失败、中断、结束和超时任务进入历史记录。" icon={Activity}>
          <div className="space-y-3">
            {queueTasks.length === 0 ? (
              <div className="rounded-md border border-dashed py-8 text-center text-xs text-muted-foreground">
                暂无进行中或可重试任务；开始下载后会固定显示在这里。
              </div>
            ) : (
              queueTasks.map((task) => (
                <div key={task.id} className="rounded-lg border bg-card p-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold">{task.name}</div>
                      <div className="truncate text-xs text-muted-foreground">{task.detail}</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2 text-right">
                      {task.outputDir && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 px-2 text-xs"
                          onClick={() => void openLocalPath(task.outputDir || "")}
                          title="打开输出目录"
                        >
                          <FolderOpen className="h-3.5 w-3.5" />
                          打开目录
                        </Button>
                      )}
                      <div>
                        <Badge
                          variant={task.status === "paused" || task.status === "failed" || task.status === "cancelled" ? "warning" : "success"}
                        >
                          {statusLabel(task.status)}
                        </Badge>
                        <div className="mt-1 font-mono text-[11px] text-muted-foreground">{task.count}</div>
                      </div>
                    </div>
                  </div>
                  <Progress value={task.progress} className="mt-2 h-1.5" />
                  {task.activeDownloads && task.activeDownloads.length > 0 && (
                    <div className="mt-2 space-y-1.5 rounded-md border bg-muted/20 p-2">
                      {task.activeDownloads
                        .slice(0, task.id === "asf-active" ? (dlStatus?.concurrency ?? task.activeDownloads.length) : task.activeDownloads.length)
                        .map((item, index) => {
                        const pct =
                          task.id === "orbit-active"
                            ? orbitPct
                            : item.expected_size
                              ? Math.round((Number(item.bytes || 0) / Number(item.expected_size)) * 100)
                              : 0;
                        return (
                          <div key={`${item.scene_id}:${index}`} className="space-y-1">
                            <div className="flex items-center justify-between gap-2 text-[11px]">
                              <span className="min-w-0 truncate font-mono" title={item.scene_id}>
                                {item.scene_id}
                              </span>
                              <span className="shrink-0 font-mono text-muted-foreground">
                                {task.id === "orbit-active"
                                  ? `${orbitStatus?.done ?? 0} / ${orbitStatus?.total ?? 0}`
                                  : `${fmtBytes(item.bytes)}${item.expected_size ? ` / ${fmtBytes(item.expected_size)}` : ""}`}
                              </span>
                            </div>
                            <Progress value={pct || currentPct} className="h-1.5" />
                          </div>
                        );
                      })}
                    </div>
                  )}
                  <div className="mt-2 grid grid-cols-2 gap-1.5">
                    {task.metrics.map(([label, value]) => (
                      <Fragment key={label}>{detailMetric(label, value)}</Fragment>
                    ))}
                  </div>
                  {task.workspaceAction && <div className="mt-2">{task.workspaceAction}</div>}
                  <div className="mt-2">{task.controls}</div>
                  {task.log.length > 0 && (
                    <div className="mt-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() =>
                          setExpandedQueueIds((prev) => {
                            const next = new Set(prev);
                            if (next.has(task.id)) next.delete(task.id);
                            else next.add(task.id);
                            return next;
                          })
                        }
                      >
                        {expandedQueueIds.has(task.id) ? (
                          <ChevronDown className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5" />
                        )}
                        详细日志
                      </Button>
                      {expandedQueueIds.has(task.id) && (
                        <div className="mt-1.5 max-h-44 overflow-y-auto rounded-md border bg-muted/20 p-2 font-mono text-[10.5px]">
                          {task.log.map((line, i) => (
                            <div key={i} className="whitespace-pre-wrap break-words leading-4">
                              {line}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </Section>

        <Section title="历史记录" desc="完成、失败和结束的任务会归档到这里；删除后不再显示。" icon={Database}>
          <div className="space-y-2">
            {historyTasks.length === 0 ? (
              <div className="rounded-md border border-dashed py-8 text-center text-xs text-muted-foreground">
                暂无历史任务。
              </div>
            ) : (
              historyTasks.map((task) => (
                <div key={task.id} className="rounded-lg border bg-card px-3 py-2.5">
                  <div className="space-y-2">
                    <button
                      type="button"
                      className="flex w-full min-w-0 items-start gap-1.5 text-left"
                      onClick={() =>
                        setExpandedHistoryIds((prev) => {
                          const next = new Set(prev);
                          if (next.has(task.id)) next.delete(task.id);
                          else next.add(task.id);
                          return next;
                        })
                      }
                    >
                      {expandedHistoryIds.has(task.id) ? (
                        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      )}
                      <span className="min-w-0 whitespace-normal break-words text-sm font-semibold leading-5">{archiveTaskDisplayTitle(task)}</span>
                    </button>
                    <div className="flex flex-wrap items-center gap-1.5 pl-5">
                      <Badge
                        variant={
                          task.status === "finished"
                            ? "success"
                            : task.status === "deleted"
                              ? "neutral"
                              : "warning"
                        }
                      >
                        {task.status === "deleted" ? "已删除" : statusLabel(task.status)}
                      </Badge>
                      {task.status !== "deleted" && archiveTaskOutputDir(task) && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 px-2 text-xs"
                          onClick={() => void openLocalPath(archiveTaskOutputDir(task))}
                          title="打开输出目录"
                        >
                          <FolderOpen className="h-3.5 w-3.5" />
                          打开目录
                        </Button>
                      )}
                      {task.status !== "deleted" && ["asf", "orbit"].includes(archiveTaskKind(task)) && archiveTaskOutputDir(task) && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 px-2 text-xs"
                          disabled={restoringTaskKeys.has(archiveTaskKey(task))}
                          onClick={() => void onResumeArchivedTask(task)}
                          title="使用原输出目录重新进入队列；完整文件会跳过，.part 文件会断点续传"
                        >
                          {restoringTaskKeys.has(archiveTaskKey(task)) ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <RotateCcw className="h-3.5 w-3.5" />
                          )}
                          {restoringTaskKeys.has(archiveTaskKey(task)) ? "恢复中" : "恢复"}
                        </Button>
                      )}
                      {task.status !== "deleted" && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-destructive"
                          onClick={() => void onDeleteArchivedTask(task)}
                          title="删除历史记录"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="mt-1.5 grid w-full grid-cols-[minmax(0,1fr)_auto] gap-2 text-left text-xs text-muted-foreground"
                    onClick={() =>
                      setExpandedHistoryIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(task.id)) next.delete(task.id);
                        else next.add(task.id);
                        return next;
                      })
                    }
                  >
                    <span className="truncate">{task.detail}</span>
                    <span className="shrink-0 font-mono text-[11px]">
                      {formatLogTime(task.ts) || new Date(task.ts).toLocaleString()}
                    </span>
                  </button>
                  <div className="mt-1 truncate text-[11px] text-muted-foreground">
                    {archiveTaskInlineMeta(task)}
                  </div>
                  {expandedHistoryIds.has(task.id) && (
                    <div className="mt-2 max-h-44 overflow-y-auto rounded-md border bg-muted/20 p-2 font-mono text-[10.5px] leading-4">
                      {(task.logs?.length ? task.logs : [task.detail]).map((line, i) => (
                        <div key={i} className="whitespace-pre-wrap break-words">
                          {line}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </Section>

        {gacosPlan && (
          <Section title="GACOS 结果" icon={Database}>
            <div className="space-y-3 text-xs">
              <div className="rounded-md border bg-muted/30 p-3">
                {kv("GACOS 日期数", String((gacosPlan.unique_dates as string[] | undefined)?.length ?? 0))}
                {kv("输出目录", resolvedOutputDir || "-")}
              </div>
            </div>
          </Section>
        )}
      </div>
    );
  }

  function sceneRuntimeStatus(scene: SceneRow) {
    const active = activeAsfDownloads.find((item) => item.scene_id === scene.scene_id);
    if (active) {
      const pct = active.expected_size ? Math.round((Number(active.bytes || 0) / Number(active.expected_size)) * 100) : 0;
      return {
        label: pct ? `下载中 ${pct}%` : "下载中",
        variant: "success" as const,
        detail: `${fmtBytes(active.bytes)}${active.expected_size ? ` / ${fmtBytes(active.expected_size)}` : ""}`,
      };
    }
    if (pausedAsfSceneIds.has(scene.scene_id)) {
      return { label: "已暂停", variant: "warning" as const, detail: "已保留 .part，可继续下载" };
    }
    const lastLog = [...(dlStatus?.log ?? [])].reverse().find((line) => line.scene_id === scene.scene_id);
    const outcome = (lastLog?.outcome || "").toLowerCase();
    if (outcome.includes("success") || outcome.includes("downloaded") || outcome.includes("copied")) {
      return { label: "已完成", variant: "success" as const, detail: lastLog?.detail || "" };
    }
    if (outcome.includes("skip")) return { label: "已跳过", variant: "neutral" as const, detail: lastLog?.detail || "" };
    if (outcome.includes("fail") || outcome.includes("interrupt") || outcome.includes("cancel")) {
      return { label: "未完成", variant: "warning" as const, detail: lastLog?.detail || "" };
    }
    if (selectedDownloadSceneIds.has(scene.scene_id)) {
      return { label: dlActive ? "等待下载" : "已勾选", variant: "success" as const, detail: "" };
    }
    return { label: "未勾选", variant: "neutral" as const, detail: "" };
  }

  function orbitRuntimeStatus(scene: SceneRow) {
    const current = orbitStatus?.current_scene === scene.scene_id;
    if (current) {
      return { label: "正在下载轨道", variant: "success" as const, detail: "正在获取该景对应的 POEORB/EOF 文件" };
    }
    const result = (orbitStatus?.results ?? []).find((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return false;
      return String((item as Record<string, unknown>).scene_id || "") === scene.scene_id;
    }) as Record<string, unknown> | undefined;
    if (result) {
      const outcome = String(result.outcome || "");
      const orbitFile = String(result.orbit_file || "");
      const message = String(result.message || "");
      if (outcome === "success") {
        return { label: "轨道已下载", variant: "success" as const, detail: orbitFile || message };
      }
      if (outcome === "skipped") {
        return { label: "已存在/复用", variant: "neutral" as const, detail: orbitFile || message };
      }
      if (outcome === "unavailable") {
        return { label: "POEORB 未发布", variant: "warning" as const, detail: message || "太新的影像可能暂时没有精密轨道" };
      }
      if (outcome === "failed") {
        return { label: "轨道失败", variant: "warning" as const, detail: message || "轨道文件下载失败" };
      }
    }
    if (selectedOrbitSceneIds.has(scene.scene_id)) {
      return { label: "待下载轨道", variant: "success" as const, detail: "" };
    }
    return { label: "未勾选", variant: "neutral" as const, detail: "" };
  }

  function renderOrbitWorkspaceOverlay() {
    if (!orbitWorkspaceOpen || orbitWorkspaceSourceScenes.length === 0) return null;
    const workspaceScenes = filteredOrbitWorkspaceScenes;
    return (
      <div
        className={cn(
          "absolute inset-4 flex min-h-0 flex-col overflow-hidden rounded-[26px] border border-white/65 bg-white/88 shadow-2xl backdrop-blur-2xl dark:border-white/10 dark:bg-zinc-950/88",
          workspaceTop === "orbit" ? "z-[780]" : "z-[760]",
        )}
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-border/60 px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-base font-semibold">
              <Orbit className="h-4 w-4 text-primary" />
              {orbitWorkspaceScope === "task" ? orbitWorkspaceSnapshotTitle : "精密轨道下载工作台"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              勾选需要配套轨道文件的 SAR 影像；{orbitWorkspaceScope === "task" ? "当前显示任务影像快照。" : orbitUsesManualSource ? "当前来自本地文件检索。" : "当前由 Sentinel-1 传递。"}点击下载时选择目录。
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            <Button
              size="sm"
              variant="outline"
              title={orbitWorkspaceQuery.trim() ? "选中当前筛选结果" : "选中全部候选"}
              onClick={() =>
                setSelectedOrbitSceneIds(new Set(workspaceScenes.map((scene) => scene.scene_id).filter(Boolean)))
              }
            >
              全选
            </Button>
            <Button size="sm" variant="outline" onClick={clearOrbitSceneSelection}>
              清空
            </Button>
            <Button
              size="sm"
              onClick={() => void onStartOrbitScenes(selectedOrbitSceneIdList)}
              disabled={orbitStartBusy || orbitActive || selectedOrbitSceneIdList.length === 0}
            >
              {orbitStartBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
              下载所选轨道
            </Button>
            <Button size="icon" variant="ghost" className="h-8 w-8 rounded-full" onClick={closeOrbitWorkspace}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2 border-b border-border/60 px-4 py-3">
          {orbitWorkspaceScope === "task" && metricPill("AOI", orbitWorkspaceAoiName)}
          {metricPill("候选", orbitWorkspaceSourceScenes.length)}
          {metricPill("显示", workspaceScenes.length)}
          {metricPill("已选", selectedOrbitSceneIdList.length, "primary")}
          {metricPill("轨道", orbitStatus ? `${orbitStatus.done}/${orbitStatus.total}` : "未开始", orbitActive ? "success" : "neutral")}
        </div>

        <div className="shrink-0 border-b border-border/60 px-4 py-3">
          <Input
            value={orbitWorkspaceQuery}
            onChange={(event) => setOrbitWorkspaceQuery(event.target.value)}
            placeholder="搜索日期 / 场景名 / Path / Frame / 极化，例如 0608"
            className="h-9 bg-white/65 text-xs dark:bg-white/10"
          />
        </div>

        <div ref={orbitWorkspaceVirtual.scrollRef} onScroll={onOrbitWorkspaceScroll} className="min-h-0 flex-1 overflow-y-auto p-2.5">
          <div className="relative" style={{ height: orbitWorkspaceVirtual.totalHeight }}>
            {orbitWorkspaceVirtual.rows.map(({ item: scene, top }) => {
              const runtime = orbitRuntimeStatus(scene);
              return (
                <div
                  key={scene.scene_id}
                  style={{ transform: `translateY(${top}px)` }}
                  className={cn(
                    "absolute left-0 right-0 grid h-[60px] cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto_auto_auto] items-center gap-2 overflow-hidden rounded-xl border bg-white/55 px-3 py-1.5 text-xs shadow-sm transition-colors hover:bg-white/80 dark:bg-white/5 dark:hover:bg-white/10",
                    selectedSceneId === scene.scene_id && "border-primary bg-primary/10 ring-1 ring-primary/30",
                  )}
                  onClick={() => highlightScene(scene.scene_id)}
                >
                  <input
                    type="checkbox"
                    checked={selectedOrbitSceneIds.has(scene.scene_id)}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => toggleOrbitScene(scene.scene_id, event.currentTarget.checked)}
                    className="h-4 w-4 rounded border-border accent-primary"
                    title="为该 SAR 影像下载配套轨道"
                  />
                  <div className="min-w-0">
                    <div className="truncate font-mono" title={scene.scene_id}>
                      {scene.scene_id}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <Badge variant="neutral">{scene.platform || "S1"}</Badge>
                      <Badge variant="neutral">{scene.product_type || "-"}</Badge>
                      <Badge variant="neutral">{orbitLabel(scene.orbit_direction)}</Badge>
                      <Badge variant={scene.path || scene.relative_orbit ? "success" : "warning"}>
                        Path {scene.path ?? scene.relative_orbit ?? "-"}
                      </Badge>
                      {selectedSceneId === scene.scene_id && <Badge variant="success">地图高亮</Badge>}
                    </div>
                  </div>
                  <span
                    className="rounded-full p-1 text-muted-foreground transition-colors hover:bg-white/60 hover:text-foreground dark:hover:bg-white/10"
                    onClick={(event) => {
                      event.stopPropagation();
                      copySceneMetadata(scene);
                    }}
                    onMouseEnter={(event) => showSceneMetaCard(scene.scene_id, event)}
                    onMouseMove={(event) => showSceneMetaCard(scene.scene_id, event)}
                    onMouseLeave={hideSceneMetaCard}
                    title="悬浮查看元数据，点击复制"
                  >
                    <Info className="h-3.5 w-3.5 shrink-0" />
                  </span>
                  <Badge variant={runtime.variant} title={runtime.detail || runtime.label}>{runtime.label}</Badge>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 px-2"
                    disabled={orbitStartBusy || orbitActive}
                    onClick={(event) => {
                      event.stopPropagation();
                      void onStartOrbitScenes([scene.scene_id]);
                    }}
                  >
                    <CloudDownload className="h-3.5 w-3.5" />
                    此景轨道
                  </Button>
                </div>
              );
            })}
            {!workspaceScenes.length && (
              <div className="rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                娌℃湁鍖归厤鐨?SAR 褰卞儚銆?              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  /*
            {!workspaceScenes.length && (
              <div className="rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                没有匹配的 SAR 影像。
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  */
  function renderSceneWorkspaceOverlay() {
    if (!sceneWorkspaceOpen || sceneWorkspaceSourceScenes.length === 0) return null;
    const workspaceScenes = filteredSceneWorkspaceScenes;
    const selectedPausableSceneIds = dlActive
      ? selectedDownloadSceneIdList.filter((id) => !pausedAsfSceneIds.has(id))
      : [];
    const selectedPausedSceneIds = selectedDownloadSceneIdList.filter((id) => pausedAsfSceneIds.has(id));
    const selectedDownloadableSceneIds = selectedDownloadSceneIdList.filter(
      (id) => !activeAsfSceneIds.has(id) && !pausedAsfSceneIds.has(id),
    );
    const canPauseSelected = selectedPausableSceneIds.length > 0;
    const canResumeSelected = selectedPausedSceneIds.length > 0;
    return (
      <div
        className={cn(
          "absolute inset-4 flex min-h-0 flex-col overflow-hidden rounded-[26px] border border-white/65 bg-white/88 shadow-2xl backdrop-blur-2xl dark:border-white/10 dark:bg-zinc-950/88",
          workspaceTop === "scene" ? "z-[780]" : "z-[760]",
        )}
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-border/60 px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-base font-semibold">
              <Satellite className="h-4 w-4 text-primary" />
              {sceneWorkspaceScope === "task" ? sceneWorkspaceSnapshotTitle : "Sentinel-1 影像下载工作台"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {selectedDownloadSceneIdList.length} / {sceneWorkspaceSourceScenes.length} 景加入下载；{sceneWorkspaceScope === "task" ? "当前显示任务快照，追加下载会沿用原目录；" : ""}点击下载时选择目录，并按工作台设置的 Sentinel-1 并发启动。
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            <Button
              size="sm"
              variant="outline"
              title={sceneWorkspaceQuery.trim() ? "选中当前筛选结果" : "选中全部候选"}
              onClick={() =>
                setSelectedDownloadSceneIds(new Set(workspaceScenes.map((scene) => scene.scene_id).filter(Boolean)))
              }
            >
              全选
            </Button>
            <Button size="sm" variant="outline" onClick={clearDownloadSceneSelection}>
              清空
            </Button>
            <Button
              size="sm"
              onClick={() => void onDownloadAsfScenes(selectedDownloadableSceneIds, sceneWorkspaceSourceScenes)}
              disabled={
                asfStartBusy ||
                dlPendingStop ||
                selectedDownloadableSceneIds.length === 0 ||
                !earthdataCanDownload
              }
              title={
                !earthdataCanDownload
                  ? "请先确认 Earthdata/ASF 凭据正常"
                  : dlPendingStop
                    ? "当前下载正在结束，请稍后再追加或新建下载"
                    : selectedDownloadableSceneIds.length === 0
                        ? "所选影像已在下载中或已暂停"
                        : dlActive
                          ? "当前已有下载任务运行；会先选择新目录并创建独立排队任务"
                          : "开始下载所选影像"
              }
            >
              {asfStartBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
              {dlActive ? "下载/追加所选" : "下载所选"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void onPauseAsfScenes(selectedPausableSceneIds, activeAsfTaskSnapshotId)}
              disabled={!canPauseSelected}
              title={canPauseSelected ? "暂停勾选的未暂停影像，排队中和下载中都可暂停" : "当前没有可暂停的勾选影像；需要先开始下载任务，并勾选未暂停影像。"}
            >
              <Pause className="h-4 w-4" />
              {canPauseSelected ? `暂停所选(${selectedPausableSceneIds.length})` : "暂停所选"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void onResumeAsfScenes(selectedPausedSceneIds, activeAsfTaskSnapshotId)}
              disabled={!canResumeSelected}
              title={canResumeSelected ? "继续勾选的已暂停影像" : "当前勾选中没有已暂停的影像；只有状态为已暂停的影像可继续。"}
            >
              <Play className="h-4 w-4" />
              {canResumeSelected ? `继续所选(${selectedPausedSceneIds.length})` : "继续所选"}
            </Button>
            <Button size="icon" variant="ghost" className="h-8 w-8 rounded-full" onClick={closeSceneWorkspace}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2 border-b border-border/60 px-4 py-3">
          {sceneWorkspaceScope === "task" && metricPill("AOI", sceneWorkspaceAoiName)}
          {metricPill("候选", sceneWorkspaceSourceScenes.length)}
          {metricPill("显示", workspaceScenes.length)}
          {metricPill("已选", selectedDownloadSceneIdList.length, "primary")}
          {metricPill("下载中", activeAsfDownloads.length, activeAsfDownloads.length > 0 ? "success" : "neutral")}
          {metricPill("已暂停", pausedAsfSceneIds.size, pausedAsfSceneIds.size > 0 ? "warning" : "neutral")}
        </div>

        <div className="shrink-0 border-b border-border/60 px-4 py-3">
          <Input
            value={sceneWorkspaceQuery}
            onChange={(event) => setSceneWorkspaceQuery(event.target.value)}
            placeholder="搜索日期 / 场景名 / Path / Frame / 极化，例如 0608"
            className="h-9 bg-white/65 text-xs dark:bg-white/10"
          />
        </div>

        <div ref={sceneWorkspaceVirtual.scrollRef} onScroll={onSceneWorkspaceScroll} className="min-h-0 flex-1 overflow-y-auto p-2.5">
          <div className="relative" style={{ height: sceneWorkspaceVirtual.totalHeight }}>
            {sceneWorkspaceVirtual.rows.map(({ item: scene, top }) => {
              const runtime = sceneRuntimeStatus(scene);
              const isActive = activeAsfSceneIds.has(scene.scene_id);
              const isPaused = pausedAsfSceneIds.has(scene.scene_id);
              return (
                <div
                  key={scene.scene_id}
                  style={{ transform: `translateY(${top}px)` }}
                  className={cn(
                    "absolute left-0 right-0 grid h-[60px] cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto_auto_auto] items-center gap-2 overflow-hidden rounded-xl border bg-white/55 px-3 py-1.5 text-xs shadow-sm transition-colors hover:bg-white/80 dark:bg-white/5 dark:hover:bg-white/10",
                    selectedSceneId === scene.scene_id && "border-primary bg-primary/10 ring-1 ring-primary/30",
                  )}
                  onClick={() => highlightScene(scene.scene_id)}
                >
                  <input
                    type="checkbox"
                    checked={selectedDownloadSceneIds.has(scene.scene_id)}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => toggleDownloadScene(scene.scene_id, event.currentTarget.checked)}
                    className="h-4 w-4 rounded border-border accent-primary"
                    title="加入本次下载"
                  />
                  <div className="min-w-0">
                    <div className="truncate font-mono" title={scene.scene_id}>
                      {scene.scene_id}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <Badge variant="neutral">{scene.product_type || "-"}</Badge>
                      <Badge variant="neutral">{orbitLabel(scene.orbit_direction)}</Badge>
                      <Badge variant="neutral">{polarizationLabel(scene.polarization)}</Badge>
                      <Badge variant={scene.footprint_bbox ? "success" : "neutral"}>
                        {scene.footprint_bbox ? "有范围" : "无范围"}
                      </Badge>
                      {selectedSceneId === scene.scene_id && <Badge variant="success">地图高亮</Badge>}
                    </div>
                  </div>
                  <span
                    className="rounded-full p-1 text-muted-foreground transition-colors hover:bg-white/60 hover:text-foreground dark:hover:bg-white/10"
                    onClick={(event) => {
                      event.stopPropagation();
                      copySceneMetadata(scene);
                    }}
                    onMouseEnter={(event) => showSceneMetaCard(scene.scene_id, event)}
                    onMouseMove={(event) => showSceneMetaCard(scene.scene_id, event)}
                    onMouseLeave={hideSceneMetaCard}
                    title="悬浮查看元数据，点击复制"
                  >
                    <Info className="h-3.5 w-3.5 shrink-0" />
                  </span>
                  <Badge variant={runtime.variant} title={runtime.detail || runtime.label}>{runtime.label}</Badge>
                  {isActive ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 px-2"
                      onClick={(event) => {
                        event.stopPropagation();
                        void onPauseAsfScenes([scene.scene_id], activeAsfTaskSnapshotId);
                      }}
                    >
                      <Pause className="h-3.5 w-3.5" />
                      暂停
                    </Button>
                  ) : isPaused ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 px-2"
                      onClick={(event) => {
                        event.stopPropagation();
                        void onResumeAsfScenes([scene.scene_id], activeAsfTaskSnapshotId);
                      }}
                    >
                      <Play className="h-3.5 w-3.5" />
                      继续
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 px-2"
                      disabled={asfStartBusy || !earthdataCanDownload}
                      onClick={(event) => {
                        event.stopPropagation();
                        void onDownloadAsfScenes([scene.scene_id], sceneWorkspaceSourceScenes);
                      }}
                    >
                      <CloudDownload className="h-3.5 w-3.5" />
                      下载
                    </Button>
                  )}
                </div>
              );
            })}
            {!workspaceScenes.length && (
              <div className="rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                没有匹配的 SAR 影像。
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  function renderWorkspaceDock() {
    const items = [
      !sceneWorkspaceOpen && scenes.length > 0
        ? {
            key: "scene",
            label: "Sentinel-1",
            count: scenes.length,
            icon: Satellite,
            onClick: openSceneWorkspace,
          }
        : null,
      !orbitWorkspaceOpen && orbitCandidateScenes.length > 0
        ? {
            key: "orbit",
            label: "Orbit",
            count: orbitCandidateScenes.length,
            icon: Orbit,
            onClick: openOrbitWorkspace,
          }
        : null,
    ].filter(Boolean) as {
      key: string;
      label: string;
      count: number;
      icon: typeof Satellite;
      onClick: () => void;
    }[];
    if (!items.length) return null;
    return (
      <div className="absolute right-3 top-20 z-[740] flex flex-col gap-2">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              type="button"
              className="pointer-events-auto inline-flex h-9 items-center gap-2 rounded-full border border-white/65 bg-primary px-3 text-xs font-medium text-primary-foreground shadow-lg shadow-primary/20 backdrop-blur-2xl transition-colors hover:bg-primary/90"
              onClick={item.onClick}
              title={`打开${item.label}工作台`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{item.label}</span>
              <span className="rounded-full bg-white/18 px-1.5 font-mono text-[11px] tabular-nums">
                {item.count}
              </span>
            </button>
          );
        })}
      </div>
    );
  }

  function renderSettingsPanel() {
    const earth = creds?.earthdata ?? "none";
    const dem = creds?.opentopography ?? "none";
    const gacos = creds?.gacos ?? "none";
    const components = componentStatus?.components ?? [];
    const componentLabel = (item: ComponentSummary) => {
      if (item.runtime_available) return "完整可用";
      if (item.state === "partial") return "缺 EGM2008 网格";
      if (item.state === "broken") return "需修复";
      if (item.state === "installed") return "已安装";
      if (item.state === "bundled") return "当前版本内置";
      if (item.state === "available") return "可在线安装";
      return "在线包未发布";
    };
    const componentBadge = (item: ComponentSummary) =>
      item.runtime_available ? "success" : item.state === "partial" || item.state === "broken" || item.can_install ? "warning" : "neutral";
    const componentHint = (item: ComponentSummary) => {
      if (item.runtime_available) return "组件已完整可用，GDAL/rasterio 与 EGM2008 网格均已识别。";
      if (item.state === "partial") {
        const manifestMentionsGrid = String(item.description || "").toLowerCase().includes("egm2008");
        if (!manifestMentionsGrid) {
          return "已识别 GDAL/rasterio 运行库，但当前在线组件包没有声明 EGM2008 网格；重装同一包可能仍无法完成 COP30/COP90 精确椭球高转换，需要发布包含 EGM2008 网格的组件包。";
        }
        return "已识别 GDAL/rasterio 运行库，但缺少 EGM2008 大地水准面网格；COP30/COP90 精确椭球高转换会被阻止，请重新安装包含 EGM2008 网格的组件。";
      }
      if (item.state === "broken") return "组件目录存在，但运行库未能加载；请移除后重新安装组件。";
      if (item.installed) return "组件已安装，但完整运行条件未通过；请刷新组件或重新安装。";
      if (item.can_install) return "可从在线组件库安装；安装后无需重新下载主程序。";
      return "在线组件包尚未发布或当前网络无法读取清单；上传组件清单和压缩包后即可一键安装。";
    };
    const updateAssetSize = updateInfo?.asset_size
      ? `${(updateInfo.asset_size / 1024 / 1024).toFixed(1)} MB`
      : "";
    const renderStatusChip = (kind: "valid" | "invalid" | "pending" | "missing", label: string) => {
      const cls =
        kind === "valid"
          ? "border-success/35 bg-success/10 text-success"
          : kind === "invalid"
            ? "border-destructive/35 bg-destructive/10 text-destructive"
            : "border-warning/35 bg-warning/10 text-warning";
      const icon =
        kind === "valid" ? (
          <CheckCircle2 className="h-3.5 w-3.5" />
        ) : kind === "invalid" ? (
          <X className="h-3.5 w-3.5" />
        ) : kind === "pending" ? (
          <RotateCcw className={cn("h-3.5 w-3.5", earthdataAuthChecking && "animate-spin")} />
        ) : (
          <AlertCircle className="h-3.5 w-3.5" />
        );
      return (
        <span className={cn("inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium", cls)}>
          {icon}
          {label}
        </span>
      );
    };
    return (
      <div className="space-y-3">
        <ErrorLine text={credError} />
        <NoteLine text={credNote} />

        <Section
          title="Earthdata / ASF"
          desc="Sentinel-1 下载使用，优先建议 Token。"
          icon={Radar}
          headerExtra={renderStatusChip(
            earthdataAuthValid ? "valid" : earthdataAuthProblem ? "invalid" : earthdataConfigured ? "pending" : "missing",
            earthdataAuthValid ? "状态正常" : earthdataAuthProblem ? "状态异常" : earthdataConfigured ? "检测中" : "待配置",
          )}
        >
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-1.5 rounded-xl border border-white/45 bg-white/35 p-1 text-sm dark:border-white/10 dark:bg-white/10">
              {(["token", "login"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setEarthCredentialMode(mode)}
                  className={cn(
                    "h-8 rounded-lg transition-colors",
                    earthCredentialMode === mode ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-white/60",
                  )}
                >
                  {mode === "token" ? "Token" : "账号密码"}
                </button>
              ))}
            </div>
            {earthCredentialMode === "token" ? (
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <div className="relative">
                  <Input
                    type={showEarthToken ? "text" : "password"}
                    value={earthToken}
                    onChange={(e) => setEarthToken(e.target.value)}
                    placeholder="Earthdata Token"
                    className="h-9 pr-10"
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    onClick={() => setShowEarthToken((value) => !value)}
                    aria-label={showEarthToken ? "隐藏 Token" : "显示 Token"}
                    title={showEarthToken ? "隐藏 Token" : "显示 Token"}
                  >
                    {showEarthToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <Button
                  size="icon"
                  className="h-9 w-9"
                  disabled={credBusy === "earth-token" || !earthToken.trim()}
                  onClick={() =>
                    void runCredentialAction(
                      "earth-token",
                      () => saveEarthdataToken(earthToken),
                      "Earthdata Token 校验通过并已保存",
                    )
                  }
                >
                  {credBusy === "earth-token" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <Input className="h-9" value={earthUser} onChange={(e) => setEarthUser(e.target.value)} placeholder="用户名" />
                <div className="relative">
                  <Input
                    type={showEarthPassword ? "text" : "password"}
                    value={earthPassword}
                    onChange={(e) => setEarthPassword(e.target.value)}
                    placeholder="密码"
                    className="h-9 pr-10"
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    onClick={() => setShowEarthPassword((value) => !value)}
                    aria-label={showEarthPassword ? "隐藏密码" : "显示密码"}
                    title={showEarthPassword ? "隐藏密码" : "显示密码"}
                  >
                    {showEarthPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            )}
            <div className="flex flex-wrap gap-1.5">
              {earthCredentialMode === "login" && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 px-2.5"
                  disabled={credBusy === "earth-login" || !earthUser.trim() || !earthPassword}
                  onClick={() =>
                    void runCredentialAction(
                      "earth-login",
                      () => saveEarthdataLogin(earthUser, earthPassword),
                      "Earthdata 登录凭据校验通过并已保存",
                    )
                  }
                >
                  <UserRound className="h-4 w-4" />
                  保存登录
                </Button>
              )}
              <Button variant="outline" size="sm" className="h-8 px-2.5" onClick={() => void openUrl(LINKS.earthdataToken)}>
                <ExternalLink className="h-4 w-4" />
                Token
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 px-2.5"
                disabled={!isConfigured(earth) || earthdataAuthChecking}
                onClick={() => void refreshCredentialStatusManually()}
              >
                {earthdataAuthChecking ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                检测登录
              </Button>
              <Button variant="outline" size="sm" className="h-8 px-2.5" onClick={() => void openUrl(LINKS.earthdataRegister)}>
                <ExternalLink className="h-4 w-4" />
                注册
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 px-2.5"
                disabled={!isConfigured(earth)}
                onClick={() =>
                  void runCredentialAction("earth-clear", clearEarthdataCredentials, "Earthdata 凭据已清除")
                }
              >
                清除
              </Button>
            </div>
          </div>
        </Section>

        <Section
          title="OpenTopography"
          desc="DEM 下载需要 API Key。"
          icon={Database}
          headerExtra={renderStatusChip(isConfigured(dem) ? "valid" : "missing", isConfigured(dem) ? "状态正常" : "待配置")}
        >
          <div className="space-y-2.5">
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <div className="relative">
                <Input
                  type={showOpentopoKey ? "text" : "password"}
                  value={opentopoKey}
                  onChange={(e) => setOpentopoKey(e.target.value)}
                  placeholder="OpenTopography API Key"
                  className="pr-10"
                />
                <button
                  type="button"
                  className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
                  onClick={() => setShowOpentopoKey((value) => !value)}
                  aria-label={showOpentopoKey ? "隐藏 Key" : "显示 Key"}
                  title={showOpentopoKey ? "隐藏 Key" : "显示 Key"}
                >
                  {showOpentopoKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <Button
                size="icon"
                disabled={credBusy === "dem-key" || !opentopoKey.trim()}
                onClick={() =>
                  void runCredentialAction(
                    "dem-key",
                    () => saveOpentopographyKey(opentopoKey),
                    "OpenTopography API Key 校验通过并已保存",
                  )
                }
              >
                {credBusy === "dem-key" ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.opentopoRegister)}>
                <ExternalLink className="h-4 w-4" />
                注册
              </Button>
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.opentopoKey)}>
                <ExternalLink className="h-4 w-4" />
                获取 Key
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={!isConfigured(dem)}
                onClick={() =>
                  void runCredentialAction("dem-clear", clearOpentopographyKey, "OpenTopography Key 已清除")
                }
              >
                清除
              </Button>
            </div>
          </div>
        </Section>

        <Section
          title="GACOS"
          desc="请求结果会发送到接收邮箱。"
          icon={Mail}
          headerExtra={renderStatusChip(isConfigured(gacos) ? "valid" : "missing", isConfigured(gacos) ? "状态正常" : "待配置")}
        >
          <div className="space-y-2.5">
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <Input
                value={gacosEmail}
                onChange={(e) => setGacosEmail(e.target.value)}
                placeholder="name@example.com"
                inputMode="email"
              />
              <Button
                size="icon"
                disabled={credBusy === "gacos-email" || !gacosEmail.trim()}
                onClick={() =>
                  void runCredentialAction(
                    "gacos-email",
                    () => saveGacosEmail(gacosEmail),
                    "GACOS 邮箱已保存",
                  )
                }
              >
                {credBusy === "gacos-email" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.gacosPortal)}>
                <ExternalLink className="h-4 w-4" />
                网站
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={!isConfigured(gacos)}
                onClick={() => void runCredentialAction("gacos-clear", clearGacosEmail, "GACOS 邮箱已清除")}
              >
                清除
              </Button>
            </div>
          </div>
        </Section>

        <Section
          title="更新与组件"
          desc="优先打通主程序在线更新；DEM/GDAL 组件作为第二阶段按需安装。"
          icon={HardDrive}
          defaultOpen={false}
          storageKey="settings-updates-components"
          forceOpenSignal={settingsComponentsOpenSignal}
        >
          <div className="space-y-3">
            <div className="rounded-2xl border border-white/45 bg-white/35 p-3 text-xs leading-5 dark:border-white/10 dark:bg-white/10">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold">软件更新</div>
                  <div className="text-muted-foreground">
                    当前版本 {appInfo?.version ?? updateInfo?.current_version ?? "-"}
                    {updateInfo?.checked && `，最新版本 ${updateInfo.latest_version}`}
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    安装版可下载并启动安装器；便携版目前下载更新包后需要关闭软件再替换，后续加入独立更新器实现自动覆盖。
                  </div>
                </div>
                <Badge variant={updateInfo?.update_available ? "warning" : "neutral"}>
                  {updateInfo?.update_available ? "发现新版" : "未发现新版"}
                </Badge>
              </div>
              {updateInfo?.asset_name && (
                <div className="mt-2 rounded-xl border border-white/45 bg-white/35 px-2 py-1.5 font-mono text-[11px] text-muted-foreground dark:border-white/10 dark:bg-white/10">
                  {updateInfo.asset_name}
                  {updateAssetSize && ` · ${updateAssetSize}`}
                </div>
              )}
              {downloadedUpdate && (
                <div className="mt-2 rounded-xl border border-success/30 bg-success/10 px-2 py-1.5 text-[11px] leading-5">
                  <div className="font-medium text-success">更新包已保存</div>
                  <div className="break-all font-mono text-muted-foreground">{downloadedUpdate.path}</div>
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={onCheckUpdateNow} disabled={updateBusy}>
                  {updateBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                  检查更新
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={updateBusy || !updateInfo?.update_available || !updateInfo?.download_url}
                  onClick={onDownloadUpdatePackage}
                >
                  <CloudDownload className="h-4 w-4" />
                  {updateInfo?.install_mode === "installer" ? "下载并启动安装器" : "下载更新包"}
                </Button>
                {downloadedUpdate && (
                  <Button variant="outline" size="sm" onClick={() => void openLocalPath(downloadedUpdate.folder)}>
                    <FolderOpen className="h-4 w-4" />
                    打开更新目录
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => void openUrl(updateInfo?.html_url || LINKS.github)}>
                  <ExternalLink className="h-4 w-4" />
                  Release 页面
                </Button>
              </div>
              <NoteLine text={updateNote || updateInfo?.message || null} />
            </div>

            <div className="rounded-2xl border border-white/45 bg-white/35 p-3 text-xs leading-5 dark:border-white/10 dark:bg-white/10">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold">在线组件（第二阶段）</div>
                  <div className="text-muted-foreground">
                    主程序在线更新闭环优先；DEM/GDAL 运行库与 EGM96、EGM2008 高程基准数据会作为可选组件按需安装。
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={componentBusy === "refresh"}
                  onClick={() => {
                    setComponentBusy("refresh");
                    setComponentNote(null);
                    void refreshComponents(true).finally(() => setComponentBusy(null));
                  }}
                >
                  {componentBusy === "refresh" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                  刷新组件
                </Button>
              </div>
              <div className="mt-2 grid gap-1 rounded-xl border border-white/45 bg-white/35 px-2 py-1.5 font-mono text-[11px] text-muted-foreground dark:border-white/10 dark:bg-white/10">
                <div>组件目录：{componentStatus?.root ?? "正在读取..."}</div>
                <div>清单：{componentStatus?.manifest_url ?? "未读取"}</div>
              </div>
              <div className="mt-3 space-y-2">
                {components.map((item) => (
                  <div key={item.id} className="rounded-xl border border-white/45 bg-white/28 p-2 dark:border-white/10 dark:bg-white/10">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold">{item.name}</span>
                          <Badge variant={componentBadge(item)}>{componentLabel(item)}</Badge>
                        </div>
                        <div className="mt-1 text-[11px] text-muted-foreground">{item.description || componentHint(item)}</div>
                        <div className="mt-1 text-[11px] text-muted-foreground">{componentHint(item)}</div>
                        {item.id === "dem-gdal" && (
                          <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                            <span>运行库：{item.partial_runtime_available || item.runtime_available ? "已识别" : "未识别"}</span>
                            <span>EGM2008 网格：{item.egm2008_grid_available ? "已识别" : "缺失"}</span>
                          </div>
                        )}
                        {item.installed_path && (
                          <div className="mt-1 break-all font-mono text-[11px] text-muted-foreground">已安装：{item.installed_path}</div>
                        )}
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!item.can_install || componentBusy === item.id}
                          onClick={() => void onInstallComponent(item.id)}
                        >
                          {componentBusy === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
                          {item.installed || item.state === "partial" || item.state === "broken" ? "修复" : "安装"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={!item.installed || componentBusy === item.id}
                          onClick={() => void onRemoveComponent(item.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                          移除
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
                {!components.length && (
                  <div className="rounded-xl border border-dashed p-3 text-center text-muted-foreground">
                    暂未读取到组件清单。
                  </div>
                )}
              </div>
              <NoteLine text={componentNote} />
            </div>
          </div>
        </Section>

        <Section
          title="网络代理与缓存"
          desc="代理用于 ASF、DEM、轨道等在线访问；缓存用于地图和检索结果复用。"
          icon={Wifi}
          defaultOpen={false}
        >
          {network ? (
            <div className="space-y-3">
              <label className="flex items-center justify-between rounded-md border bg-muted/25 px-3 py-2 text-sm">
                <span>
                  <span className="block font-medium">启用网络代理</span>
                  <span className="text-xs text-muted-foreground">HTTP / HTTPS / ALL_PROXY</span>
                </span>
                <input
                  type="checkbox"
                  checked={network.proxy_enabled}
                  onChange={(e) => setNetwork({ ...network, proxy_enabled: e.target.checked })}
                  className="h-4 w-4"
                />
              </label>
              <label className="flex items-center justify-between rounded-md border bg-muted/25 px-3 py-2 text-sm">
                <span>
                  <span className="block font-medium">忽略 ASF 证书异常（内部测试）</span>
                  <span className="text-xs text-muted-foreground">
                    默认不启用；仅在代理证书、自签证书或证书过期导致 ASF SSL 失败时临时使用。
                  </span>
                </span>
                <input
                  type="checkbox"
                  checked={network.asf_ssl_verify === false}
                  onChange={(e) => setNetwork({ ...network, asf_ssl_verify: !e.target.checked })}
                  className="h-4 w-4"
                />
              </label>
              <Input
                value={network.proxy_url}
                onChange={(e) => setNetwork({ ...network, proxy_url: e.target.value })}
                placeholder="代理地址（可选，留空自动识别系统代理）"
                className="font-mono text-xs"
                spellCheck={false}
              />
              <label className="flex items-center justify-between rounded-md border bg-muted/25 px-3 py-2 text-sm">
                <span>
                  <span className="block font-medium">启用缓存</span>
                  <span className="text-xs text-muted-foreground">缓存底图瓦片、行政边界和检索结果，减少重复联网。</span>
                </span>
                <input
                  type="checkbox"
                  checked={network.cache_enabled}
                  disabled
                  onChange={() => undefined}
                  className="h-4 w-4"
                />
              </label>
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <Input
                  value={network.cache_dir}
                  onChange={(e) => setNetwork({ ...network, cache_dir: e.target.value })}
                  placeholder="缓存目录"
                  className="font-mono text-xs"
                  spellCheck={false}
                />
                <Button variant="outline" size="icon" onClick={onBrowseCacheDir}>
                  <FolderOpen className="h-4 w-4" />
                </Button>
              </div>
              <div className="grid grid-cols-[1fr_1fr_auto] gap-2">
                <Input
                  type="number"
                  min={0}
                  value={network.cache_limit_mb}
                  onChange={(e) => setNetwork({ ...network, cache_limit_mb: Number(e.target.value) || 0 })}
                  placeholder="缓存上限 MB"
                />
                <div className="relative">
                  <Input
                    type={showTiandituKey ? "text" : "password"}
                    value={network.tianditu_token}
                    onChange={(e) => setNetwork({ ...network, tianditu_token: e.target.value })}
                    placeholder="天地图 Key（底图 / 行政边界）"
                    className="pr-10"
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    onClick={() => setShowTiandituKey((value) => !value)}
                    aria-label={showTiandituKey ? "隐藏 Key" : "显示 Key"}
                    title={showTiandituKey ? "隐藏 Key" : "显示 Key"}
                  >
                    {showTiandituKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <Button variant="outline" size="icon" onClick={() => void openUrl(LINKS.tiandituKey)} title="申请天地图 Key">
                  <ExternalLink className="h-4 w-4" />
                </Button>
              </div>
              <Button onClick={onSaveNetwork} disabled={networkBusy} className="w-full">
                {networkBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                保存网络与缓存设置
              </Button>
              <ErrorLine text={networkError} />
              <NoteLine text={networkNote} />
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-md border bg-muted/25 px-3 py-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              正在读取网络设置
            </div>
          )}
        </Section>
      </div>
    );
  }

  const updateDialogChangelog = changelogLines(updateInfo?.changelog);
  const updateDialogDate = releaseDateLabel(updateInfo?.published_at);
  const updateDialogAssetSize = updateInfo?.asset_size
    ? `${(updateInfo.asset_size / 1024 / 1024).toFixed(1)} MB`
    : "";

  return (
    <div
      className="ios-window relative flex h-[100dvh] w-screen flex-col overflow-hidden text-foreground"
      onDragEnter={onWorkbenchDragEnter}
      onDragOver={onWorkbenchDragOver}
      onDragLeave={onWorkbenchDragLeave}
      onDrop={(event) => void onDropAoiFile(event)}
    >
      <NativeResizeHandles />
      <header
        className="ios-topbar pywebview-drag-region z-[520] flex h-12 shrink-0 items-center gap-2 border-b px-3"
        data-tour="app-header"
      >
        <div className="flex min-w-[150px] items-center gap-2">
          <img src="/app-icon.svg" alt="" className="h-8 w-8 rounded-lg shadow-sm" />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-normal">InSAR Studio</div>
          </div>
        </div>

        <nav
          className="source-tab-strip scrollbar-none relative flex h-11 shrink-0 items-center overflow-x-auto overflow-y-hidden rounded-2xl border border-white/55 bg-white/34 px-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] backdrop-blur-2xl dark:border-white/10 dark:bg-white/8"
          onWheel={onSourceTabsWheel}
        >
          <div
            className="flex min-w-max items-center gap-1"
            data-tour="source-tabs"
          >
          {SOURCE_TABS.map((item) => {
            const Icon = item.icon;
            const active = source === item.key;
            return (
              <button
                key={item.key}
                type="button"
                disabled={item.disabled}
                onMouseDown={stopWindowDrag}
                onClick={() => {
                  setSource(item.key);
                  setPanel("resources");
                }}
                className={cn(
                  "relative flex h-10 min-w-[104px] shrink-0 items-center justify-center gap-1.5 px-3 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-45",
                  active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate font-medium">{item.label}</span>
                {active && (
                  <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-foreground shadow-[0_-6px_18px_rgba(15,23,42,0.18)]" />
                )}
              </button>
            );
          })}
          </div>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-foreground/20 to-transparent" />
        </nav>

        <div className="min-w-0 flex-1" />

        {updateInfo?.update_available && (
          <button
            type="button"
            onMouseDown={stopWindowDrag}
            onClick={() => setUpdateDialogOpen(true)}
            className="hidden h-8 shrink-0 items-center gap-1.5 rounded-full border border-primary/20 bg-primary/10 px-2.5 text-xs font-medium text-primary shadow-sm backdrop-blur-xl transition-colors hover:bg-primary/15 lg:flex"
            title={`发现新版 ${updateInfo.latest_version}，到设置中下载更新包`}
          >
            <CloudDownload className="h-3.5 w-3.5" />
            <span className="max-w-[120px] truncate">下载新版 {updateInfo.latest_version}</span>
          </button>
        )}

        <div className="hidden max-w-[320px] items-center gap-1.5 xl:flex">
          <Badge variant={scenes.length ? "success" : "neutral"}>{scenes.length} 景</Badge>
          <Badge variant={ctx?.region?.has_aoi ? "success" : "neutral"}>
            {ctx?.region?.has_aoi ? "AOI 已设" : "AOI 可选"}
          </Badge>
        </div>

        <Button
          variant="ghost"
          size="icon"
          className="hidden h-8 w-8 shrink-0 rounded-full lg:inline-flex"
          onMouseDown={stopWindowDrag}
          onClick={startWorkbenchTour}
          title="新手引导"
          data-tour="help-button"
        >
          <BookOpen className="h-3.5 w-3.5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="hidden h-8 w-8 shrink-0 rounded-full lg:inline-flex"
          onMouseDown={stopWindowDrag}
          onClick={() => setCommunityOpen(true)}
          title="反馈与社区"
        >
          <MessageCircle className="h-3.5 w-3.5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onMouseDown={stopWindowDrag}
          onClick={onToggleDark}
          title="切换主题"
        >
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <div className="ml-1 flex h-10 shrink-0 items-center gap-1 border-l border-white/55 pl-2 dark:border-white/10">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-full"
            onMouseDown={stopWindowDrag}
            onClick={() => void minimizeNativeWindow()}
            title="最小化"
          >
            <Minus className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-full"
            onMouseDown={stopWindowDrag}
            onClick={() => void toggleNativeWindowMaximize()}
            title="最大化/还原"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-full hover:bg-red-500 hover:text-white dark:hover:bg-red-500 dark:hover:text-white"
            onMouseDown={stopWindowDrag}
            onClick={() => void closeNativeWindow()}
            title="关闭"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </header>

      {updateDialogOpen && updateInfo?.update_available && (
        <div
          className="absolute inset-0 z-[2200] flex items-center justify-center bg-slate-950/34 px-4 backdrop-blur-sm"
          onMouseDown={stopWindowDrag}
        >
          <div className="w-full max-w-[560px] rounded-lg border border-white/65 bg-background/95 p-4 shadow-2xl backdrop-blur-2xl dark:border-white/12">
            <div className="flex items-start gap-3">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary/12 text-primary">
                <CloudDownload className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-semibold tracking-normal">发现新版 {updateInfo.latest_version}</h2>
                  {updateDialogDate && <Badge variant="neutral">{updateDialogDate}</Badge>}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  当前版本 {updateInfo.current_version}
                  {updateInfo.release_name && updateInfo.release_name !== updateInfo.latest_version
                    ? ` · ${updateInfo.release_name}`
                    : ""}
                </div>
              </div>
              <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0 rounded-full" onClick={() => setUpdateDialogOpen(false)} title="关闭">
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="mt-4 max-h-[240px] overflow-auto rounded-md border bg-muted/20 p-3 text-sm">
              {updateDialogChangelog.length ? (
                <ul className="space-y-1.5">
                  {updateDialogChangelog.map((line, index) => (
                    <li key={`${line}-${index}`} className="leading-5 text-foreground/90">
                      {line}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-muted-foreground">本次 Release 暂未填写更新日志，可打开 Release 页面查看详情。</div>
              )}
            </div>

            {updateInfo.asset_name && (
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <FileText className="h-3.5 w-3.5" />
                <span className="break-all">{updateInfo.asset_name}</span>
                {updateDialogAssetSize && <span>{updateDialogAssetSize}</span>}
              </div>
            )}
            {updateNote && <div className="mt-3 text-xs text-muted-foreground">{updateNote}</div>}
            {downloadedUpdate && (
              <div className="mt-3 rounded-md border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                更新包已保存：<span className="break-all font-mono">{downloadedUpdate.path}</span>
              </div>
            )}

            <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={onDismissUpdatePrompt}>
                不再提示此版本
              </Button>
              <Button variant="outline" size="sm" onClick={() => void openUrl(updateInfo.html_url || LINKS.github)}>
                <ExternalLink className="h-4 w-4" />
                Release 页面
              </Button>
              <Button
                size="sm"
                disabled={updateBusy || !updateInfo.download_url}
                onClick={onDownloadUpdatePackage}
                title={updateInfo.download_url ? "在线下载更新包" : "当前 Release 没有可直接下载的更新包"}
              >
                {updateBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
                在线下载更新
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <aside className="ios-sidebar flex h-full w-[430px] shrink-0 flex-col">
          <div
            className="grid h-11 shrink-0 grid-cols-3 border-b border-white/50 bg-white/36 backdrop-blur-2xl dark:border-white/10 dark:bg-white/5"
            data-tour="sidebar-tabs"
          >
            {PANEL_TABS.map((item) => {
              const Icon = item.icon;
              const active = panel === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setPanel(item.key)}
                  data-tour={
                    item.key === "downloads"
                      ? "download-center-tab"
                      : item.key === "settings"
                        ? "settings-tab"
                        : undefined
                  }
                  className={cn(
                    "relative flex h-11 items-center justify-center gap-1.5 text-sm transition-colors",
                    active
                      ? "text-foreground after:absolute after:bottom-0 after:left-0 after:h-0.5 after:w-full after:bg-foreground"
                      : "text-muted-foreground hover:bg-white/45 hover:text-foreground dark:hover:bg-white/10",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span className="font-medium">{item.label}</span>
                  {item.key === "downloads" && activeDownloadTaskCount > 0 && (
                    <span className="absolute right-7 top-1.5 min-w-4 rounded-full bg-primary px-1 text-[10px] font-semibold leading-4 text-primary-foreground shadow-sm">
                      {activeDownloadTaskCount}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          <div
            ref={sidebarScrollRef}
            className="min-h-0 flex-1 overflow-y-auto p-3"
            data-tour="resource-panel"
            onScroll={(event) => {
              sidebarScrollPositions.current[sidebarScrollKey] = event.currentTarget.scrollTop;
            }}
          >
            {panel === "resources" && (
              <div className="space-y-3">
                {renderResourcePanel()}
              </div>
            )}
            {panel === "downloads" && renderDownloadCenter()}
            {panel === "settings" && renderSettingsPanel()}
          </div>
        </aside>

        <main className="relative min-h-0 min-w-0 flex-1 overflow-hidden" data-tour="map-canvas">
          <WorkbenchMap
            bbox={mapBbox}
            aoiBbox={ctx?.region?.bbox ?? null}
            aoiGeometry={mapAoiGeometry}
            sceneBbox={ctx?.region?.scene_footprint_bbox ?? null}
            scenes={visibleMapScenes}
            selectedSceneId={selectedSceneId}
            layerKey={layerKey}
            tiandituToken={tiandituToken}
            drawMode={drawMode}
            drawActive={drawActive && !aoiBusy}
            onLayerChange={setLayerKey}
            onSceneSelect={highlightScene}
            onDrawModeChange={setDrawMode}
            onDrawActiveChange={setDrawActive}
            onClearLayers={() => void onClearMapLayers()}
            onRectDraw={(bbox) => void bindBbox(bbox)}
            onPolygonDraw={(ring) => void bindPolygon(ring)}
            onPointDraw={bindPoint}
          />
          {renderWorkspaceDock()}
          {renderSceneWorkspaceOverlay()}
          {renderOrbitWorkspaceOverlay()}
          {renderSceneMetaHoverCard()}
        </main>
      </div>
      {aoiDragDepth > 0 && (
        <div className="pointer-events-none fixed inset-0 z-[1600] flex items-center justify-center bg-slate-950/28 p-6 backdrop-blur-sm">
          <div className="max-w-[520px] rounded-2xl border border-white/75 bg-white/95 px-6 py-5 text-center shadow-2xl dark:border-white/10 dark:bg-zinc-950/95">
            <div className="mx-auto mb-3 grid h-11 w-11 place-items-center rounded-full bg-primary/12 text-primary">
              <FileUp className="h-5 w-5" />
            </div>
            <div className="text-base font-semibold">释放以识别边界文件</div>
            <div className="mt-1 text-sm text-muted-foreground">
              支持 .shp、.kml、.kmz、.geojson、.json；其他格式不会导入。
            </div>
          </div>
        </div>
      )}
      {renderAoiFeaturePickerOverlay()}
      {communityOpen && (
        <div
          className="fixed inset-0 z-[1300] flex items-center justify-center bg-black/28 p-5 backdrop-blur-sm"
          onMouseDown={() => setCommunityOpen(false)}
        >
          <div
            className="w-full max-w-[760px] rounded-[24px] border border-white/70 bg-white/92 p-6 text-foreground shadow-2xl backdrop-blur-2xl dark:border-white/10 dark:bg-zinc-950/92"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-semibold tracking-normal">反馈与社区</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  内部测试阶段可扫码联系作者反馈问题；交流群二维码提供后会放在右侧。
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0 rounded-full"
                onClick={() => setCommunityOpen(false)}
                title="关闭"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="grid gap-4 sm:grid-cols-[1.15fr_0.85fr]">
              <div className="rounded-2xl border border-border/70 bg-background/80 p-4 text-center shadow-sm">
                <div className="mb-3 flex items-center justify-center gap-2 text-sm font-medium">
                  <UserRound className="h-4 w-4" />
                  微信名片
                </div>
                <div className="mx-auto max-w-[330px] overflow-hidden rounded-2xl border bg-white p-1.5">
                  <img
                    src="/contact/wechat_story.jpg"
                    alt="你一生的故事 微信二维码"
                    className="aspect-square w-full object-contain"
                  />
                </div>
                <div className="mt-3 text-sm font-medium">你一生的故事</div>
                <div className="text-xs text-muted-foreground">扫码添加，反馈测试建议</div>
              </div>

              <div className="rounded-2xl border border-dashed border-border/80 bg-muted/35 p-4 text-center">
                <div className="mb-3 flex items-center justify-center gap-2 text-sm font-medium">
                  <Mail className="h-4 w-4" />
                  技术交流群
                </div>
                <div className="flex aspect-square w-full items-center justify-center rounded-2xl border bg-background/70 p-6 text-sm text-muted-foreground">
                  群聊二维码待提供
                </div>
                <div className="mt-3 text-sm font-medium">后续替换为交流群</div>
                <div className="text-xs text-muted-foreground">可用于版本通知、问题收集和教程同步</div>
                <button
                  type="button"
                  onClick={() => void openExternalUrl("https://github.com/hhanmj/insar_studio")}
                  className="mt-4 inline-flex items-center justify-center gap-1.5 rounded-full border border-amber-300/70 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700 shadow-sm transition-colors hover:bg-amber-100 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-200"
                >
                  <Star className="h-3.5 w-3.5 fill-current" />
                  GitHub Stars
                  <ExternalLink className="h-3 w-3" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      <OnboardingTour
        steps={WORKBENCH_TOUR_STEPS}
        storageKey="insar-assistant:workbench-tour"
        version={WORKBENCH_TOUR_VERSION}
        runSignal={tourSignal}
        autoStart={tourAutoStart}
        onStepChange={handleTourStepChange}
      />
    </div>
  );
}
