import { useEffect, useMemo, useRef, useState, type WheelEvent } from "react";
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
  ExternalLink,
  FileText,
  FileUp,
  FolderOpen,
  FolderPlus,
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
  ShieldCheck,
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
  addProject,
  addRegion,
  checkEarthdataAuth,
  checkScenes,
  closeNativeWindow,
  clearMapLayers,
  clearScenes,
  clearEarthdataCredentials,
  clearGacosEmail,
  clearOpentopographyKey,
  createWorkspace,
  ensureDirectory,
  formatBridgeError,
  getCredentialStatus,
  getDownloadArchive,
  getDownloadStatus,
  getNativeWindowSize,
  hasBridge,
  checkForUpdate,
  getMetadataStatus,
  getAdminOptions,
  getNetworkSettings,
  getOrbitDownloadStatus,
  getTree,
  importScenesDirectory,
  importScenesFile,
  importScenesText,
  listScenes,
  matchOrbitsDirectory,
  minimizeNativeWindow,
  openExternalUrl,
  openPath,
  pauseAsfDownload,
  pauseOrbitDownload,
  pickDirectory,
  pickOpenFile,
  planAsfDownload,
  planGacosRequest,
  retryAsfDownload,
  resumeAsfDownload,
  resumeOrbitDownload,
  runDemDownload,
  runDemDownloadBbox,
  runLocalDemConversion,
  saveEarthdataLogin,
  saveEarthdataToken,
  saveGacosEmail,
  saveDownloadArchive,
  saveNetworkSettings,
  saveOpentopographyKey,
  resizeNativeWindowFromEdge,
  selectProject,
  selectRegion,
  setDemDataset,
  setRegionAoiBbox,
  setRegionAoiFile,
  setRegionAoiGeojson,
  searchAdminBoundaries,
  searchAsfScenes,
  startAsfDownload,
  startOrbitDownload,
  stopAsfDownload,
  stopOrbitDownload,
  toggleNativeWindowMaximize,
  type Bbox,
  type AdminBoundary,
  type CheckOk,
  type Context,
  type CredentialStatus,
  type DownloadArchiveItem,
  type DownloadStatus,
  type EarthdataAuthCheck,
  type Json,
  type NetworkSettings,
  type MetadataStatus,
  type OrbitDownloadStatus,
  type OrbitMatchOk,
  type RunSummaryOk,
  type SceneRow,
  type SimpleOk,
  type Tree,
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

const DOWNLOAD_ARCHIVE_KEY = "insar.downloadArchive.v1";

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
          className={cn("fixed z-[1800] bg-transparent", handle.className)}
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
    label: "已接入：下载后自动转换为 SARscape DEM",
    options: [
      { value: "SRTM_GL3", label: "SRTM 90m", enabled: true, hint: "EGM96" },
      { value: "SRTM_GL1", label: "SRTM 30m", enabled: true, hint: "EGM96" },
      {
        value: "SRTM_GL1_ELLIPSOIDAL",
        label: "SRTM GL1 Ellipsoidal 30m",
        enabled: true,
        hint: "WGS84 椭球高",
      },
      { value: "AW3D30", label: "ALOS World 3D 30m", enabled: true, hint: "EGM96" },
      {
        value: "AW3D30_ELLIPSOIDAL",
        label: "ALOS World 3D Ellipsoidal 30m",
        enabled: true,
        hint: "WGS84 椭球高",
      },
      { value: "COP90", label: "Copernicus Global DSM 90m", enabled: true, hint: "EGM2008" },
      { value: "COP30", label: "Copernicus Global DSM 30m", enabled: true, hint: "EGM2008" },
      { value: "NASADEM", label: "NASADEM Global DEM", enabled: true, hint: "EGM96" },
    ],
  },
  {
    label: "待接入：先列入升级计划",
    options: [
      { value: "SRTM15PLUS", label: "Global Bathymetry SRTM15+ V2.1", enabled: false },
      { value: "EU_DTM", label: "EU DTM 30m", enabled: false },
      { value: "GEDI_L3", label: "GEDI L3 1km", enabled: false },
      { value: "GEBCO_ICE_TOPO", label: "GEBCOIceTopo Bathymetry 500m", enabled: false },
      { value: "GEBCO_SUB_ICE_TOPO", label: "GEBCOSubIceTopo Bathymetry 500m", enabled: false },
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

const DEFAULT_ROOT = "";
const DEFAULT_BBOX: Bbox = {
  west: 73.5,
  east: 135.1,
  south: 18.0,
  north: 53.6,
  crs: "EPSG:4326",
};

const CHINA_PROVINCES = [
  "不限",
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
  { key: "dem", label: "DEM", hint: "下载 + 转换", icon: Mountain },
  { key: "orbit", label: "Orbit", hint: "POEORB", icon: Orbit },
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

const WORKBENCH_TOUR_VERSION = 3;
const WORKBENCH_TOUR_STEPS: TourStep[] = [
  {
    title: "欢迎使用 InSAR Assistant",
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
    target: '[data-tour="resource-panel"]',
    title: "4. 设置 ASF 筛选并检索",
    body: "资源下载面板里完成 ASF 筛选、SAR 文件导入、DEM 下载转换、Orbit/GACOS 日期解析等操作。每个功能都可以收起，避免信息堆在一起。",
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
};

function isConfigured(value: string | undefined) {
  return !!value && value !== "none" && value !== "unavailable";
}

function providerLabel(value: string | undefined) {
  if (!value || value === "none") return "待配置";
  if (value === "unavailable") return "不可用";
  return value;
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

function Section({
  title,
  desc,
  icon: Icon,
  children,
  defaultOpen = true,
  storageKey,
}: {
  title: string;
  desc?: string;
  icon?: typeof Satellite;
  children: React.ReactNode;
  defaultOpen?: boolean;
  storageKey?: string;
}) {
  const [open, setOpen] = useState(() => {
    if (!storageKey || typeof window === "undefined") return defaultOpen;
    const stored = window.localStorage.getItem(`insar.section.${storageKey}`);
    return stored == null ? defaultOpen : stored === "open";
  });
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
        <ChevronDown className={cn("mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="border-t px-3 py-3">{children}</div>}
    </section>
  );
}

function activeBbox(ctx: Context | null): Bbox {
  return ctx?.region?.bbox ?? ctx?.region?.scene_footprint_bbox ?? DEFAULT_BBOX;
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

function dateInputValue(value: string) {
  const normalised = normalizeDateInput(value);
  return /^\d{4}-\d{2}-\d{2}$/.test(normalised) ? normalised : "";
}

function uniqueOptions(options: string[]) {
  return Array.from(
    new Set(options.map((item) => item.trim()).filter((item) => item && item !== "全部" && item !== "不限")),
  );
}

function withAllOption(options: string[]) {
  return ["全部", ...uniqueOptions(options)];
}

function compactStamp() {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}`;
}

function pathBaseName(path: string) {
  return path.trim().replace(/[\\/]+$/, "").split(/[\\/]/).pop()?.trim() || "";
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

function resultLine(value: Json, index: number) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return String(value ?? "");
  const parts = [
    jsonField(value, "outcome") || jsonField(value, "status"),
    jsonField(value, "dataset"),
    jsonField(value, "message") || jsonField(value, "error"),
    jsonField(value, "output_path") || jsonField(value, "path"),
  ].filter(Boolean);
  return parts.length ? `${index + 1}. ${parts.join("；")}` : `${index + 1}. ${JSON.stringify(value)}`;
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
    run.raw_dem_path ? `原始 DEM：${run.raw_dem_path}` : "",
    run.ellipsoid_dem_path ? `椭球高 DEM：${run.ellipsoid_dem_path}` : "",
    run.sarscape_ready_dem_path ? `SARscape DEM：${run.sarscape_ready_dem_path}` : "",
    run.results_path ? `结果表：${run.results_path}` : "",
    run.conversion_results_path ? `转换结果表：${run.conversion_results_path}` : "",
    ...(run.results ?? []).map(resultLine),
    ...(Array.isArray(downloadResults) ? downloadResults.map((item, index) => `下载 ${resultLine(item, index)}`) : []),
    ...(Array.isArray(conversionResults) ? conversionResults.map((item, index) => `转换 ${resultLine(item, index)}`) : []),
  ];
  return Array.from(new Set(lines.filter(Boolean))).slice(-160);
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

  if (!ellipsoid && sarscape) ellipsoid = sarscape.replace(/_dem$/i, "_ellipsoid.tif");
  if (!sarscape && ellipsoid) sarscape = ellipsoid.replace(/_ellipsoid\.(tif|tiff)$/i, "_dem");
  return { raw, ellipsoid, sarscape };
}

function loadDownloadArchive() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(DOWNLOAD_ARCHIVE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return dedupeArchiveItems(parsed
      .filter(
        (item) =>
        item &&
        typeof item.id === "string" &&
        typeof item.name === "string" &&
        typeof item.status === "string" &&
        typeof item.detail === "string",
      )
      .map((item) => normaliseArchiveItemForStartup(item as DownloadArchiveItem)))
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
  const out = archiveTaskOutputDir(item).replace(/[\\/]+$/, "").toLowerCase();
  if (kind && out) return `${kind}:${out}`;
  return item.id;
}

function dedupeArchiveItems(items: DownloadArchiveItem[]) {
  const byKey = new Map<string, DownloadArchiveItem>();
  for (const item of items) {
    const key = archiveTaskKey(item);
    const prev = byKey.get(key);
    if (!prev || Number(item.ts || 0) >= Number(prev.ts || 0)) {
      byKey.set(key, item);
    }
  }
  return Array.from(byKey.values()).sort((a, b) => Number(b.ts || 0) - Number(a.ts || 0));
}

function isRestorableArchiveTask(item: DownloadArchiveItem) {
  const kind = archiveTaskKind(item);
  return (
    (kind === "asf" || kind === "orbit") &&
    ["running", "paused"].includes(item.status) &&
    !!archiveTaskOutputDir(item)
  );
}

function autoProjectName(root: string) {
  const base = pathBaseName(root);
  if (base && !/^projects?$/i.test(base)) return base;
  return `project_${compactStamp()}`;
}

function autoRegionName(project: string) {
  const base = project.trim().replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  return `${base || "region"}_area`;
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
  const [layerKey, setLayerKey] = useState<MapLayerKey>("googleSatellite");
  const [drawMode, setDrawMode] = useState<WorkbenchDrawMode>("rect");
  const [drawActive, setDrawActive] = useState(false);
  const [aoiToolsOpen, setAoiToolsOpen] = useState(false);
  const [manualAoiOpen, setManualAoiOpen] = useState(false);
  const [tourSignal, setTourSignal] = useState(0);
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [communityOpen, setCommunityOpen] = useState(false);

  const [tree, setTree] = useState<Tree | null>(null);
  const [root, setRoot] = useState(DEFAULT_ROOT);
  const [projectName, setProjectName] = useState("");
  const [regionName, setRegionName] = useState("");
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [projectNote, setProjectNote] = useState<string | null>(null);

  const [outputDir, setOutputDir] = useState("");
  const [demDownloadOutputDir, setDemDownloadOutputDir] = useState("");
  const [localDemOutputDir, setLocalDemOutputDir] = useState("");
  const [scenes, setScenes] = useState<SceneRow[]>([]);
  const [sceneText, setSceneText] = useState("");
  const [sceneFile, setSceneFile] = useState("");
  const [sceneDir, setSceneDir] = useState("");
  const [sceneBusy, setSceneBusy] = useState(false);
  const [sceneError, setSceneError] = useState<string | null>(null);
  const [sceneNote, setSceneNote] = useState<string | null>(null);
  const [checkBusy, setCheckBusy] = useState(false);
  const [checkReport, setCheckReport] = useState<CheckOk["report"] | null>(null);

  const [aoiBusy, setAoiBusy] = useState(false);
  const [aoiError, setAoiError] = useState<string | null>(null);
  const [aoiNote, setAoiNote] = useState<string | null>(null);
  const [adminQuery, setAdminQuery] = useState("");
  const [adminProvince, setAdminProvince] = useState("不限");
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
  const [aoiPreviewGeometry, setAoiPreviewGeometry] = useState<Json | null>(null);
  const [focusBbox, setFocusBbox] = useState<Bbox | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [selectedDownloadSceneIds, setSelectedDownloadSceneIds] = useState<Set<string>>(() => new Set());
  const [hoveredSceneId, setHoveredSceneId] = useState<string | null>(null);
  const [sceneWorkspaceOpen, setSceneWorkspaceOpen] = useState(false);

  const [asfPlan, setAsfPlan] = useState<Json | null>(null);
  const [asfBusy, setAsfBusy] = useState(false);
  const [asfStartBusy, setAsfStartBusy] = useState(false);
  const [asfError, setAsfError] = useState<string | null>(null);
  const [asfSearchProduct, setAsfSearchProduct] = useState("SLC");
  const [asfSearchStart, setAsfSearchStart] = useState("");
  const [asfSearchEnd, setAsfSearchEnd] = useState("");
  const [asfSearchOrbit, setAsfSearchOrbit] = useState("");
  const [asfSearchRelativeOrbit, setAsfSearchRelativeOrbit] = useState("");
  const [asfSearchFrame, setAsfSearchFrame] = useState("");
  const [asfSearchMax, setAsfSearchMax] = useState("100");
  const [asfConcurrency, setAsfConcurrency] = useState("2");
  const [asfSearchBusy, setAsfSearchBusy] = useState(false);
  const [asfSearchError, setAsfSearchError] = useState<string | null>(null);
  const [asfSearchNote, setAsfSearchNote] = useState<string | null>(null);
  const [asfSearchSummary, setAsfSearchSummary] = useState<{
    requested_limit?: number | null;
    total_count?: number | null;
    returned_count?: number | null;
    source?: string | null;
  } | null>(null);
  const [metadataStatus, setMetadataStatus] = useState<MetadataStatus | null>(null);
  const [asfSearchBeam, setAsfSearchBeam] = useState("IW");
  const [asfSearchPolarization, setAsfSearchPolarization] = useState("");
  const [dlStatus, setDlStatus] = useState<DownloadStatus | null>(null);

  const [orbitDir, setOrbitDir] = useState("");
  const [orbitMatch, setOrbitMatch] = useState<OrbitMatchOk | null>(null);
  const [orbitBusy, setOrbitBusy] = useState(false);
  const [orbitStartBusy, setOrbitStartBusy] = useState(false);
  const [orbitError, setOrbitError] = useState<string | null>(null);
  const [orbitStatus, setOrbitStatus] = useState<OrbitDownloadStatus | null>(null);

  const [dataset, setDataset] = useState("COP30");
  const [demWest, setDemWest] = useState("");
  const [demEast, setDemEast] = useState("");
  const [demSouth, setDemSouth] = useState("");
  const [demNorth, setDemNorth] = useState("");
  const [demRun, setDemRun] = useState<RunSummaryOk | null>(null);
  const [demRunSource, setDemRunSource] = useState<"download" | "local" | null>(null);
  const [demDownloadBusy, setDemDownloadBusy] = useState(false);
  const [localDemBusy, setLocalDemBusy] = useState(false);
  const [demError, setDemError] = useState<string | null>(null);
  const [localDem, setLocalDem] = useState("");
  const [localDatum, setLocalDatum] = useState("auto");

  const [gacosBusy, setGacosBusy] = useState(false);
  const [gacosPlan, setGacosPlan] = useState<Json | null>(null);
  const [gacosError, setGacosError] = useState<string | null>(null);

  const [creds, setCreds] = useState<CredentialStatus | null>(null);
  const [earthToken, setEarthToken] = useState("");
  const [earthUser, setEarthUser] = useState("");
  const [earthPassword, setEarthPassword] = useState("");
  const [earthCredentialMode, setEarthCredentialMode] = useState<"token" | "login">("token");
  const [opentopoKey, setOpentopoKey] = useState("");
  const [gacosEmail, setGacosEmail] = useState("");
  const [credBusy, setCredBusy] = useState<string | null>(null);
  const [credError, setCredError] = useState<string | null>(null);
  const [credNote, setCredNote] = useState<string | null>(null);
  const [earthdataAuth, setEarthdataAuth] = useState<EarthdataAuthCheck | null>(null);
  const [earthdataAuthChecking, setEarthdataAuthChecking] = useState(false);
  const [network, setNetwork] = useState<NetworkSettings | null>(null);
  const [networkBusy, setNetworkBusy] = useState(false);
  const [networkError, setNetworkError] = useState<string | null>(null);
  const [networkNote, setNetworkNote] = useState<string | null>(null);
  const [downloadArchive, setDownloadArchive] = useState<DownloadArchiveItem[]>(
    () => loadDownloadArchive() as DownloadArchiveItem[],
  );
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
    const next = await getTree();
    setTree(next);
    if (next.workspace?.root) setRoot(next.workspace.root);
    const currentProject = next.projects.find((p) => p.project_id === next.current_project_id);
    if (currentProject) setProjectName(currentProject.name);
    const currentRegion = currentProject?.regions.find((r) => r.region_id === next.current_region_id);
    if (currentRegion) setRegionName(currentRegion.name);
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

  async function refreshEarthdataAuth() {
    setEarthdataAuthChecking(true);
    try {
      const res = await checkEarthdataAuth();
      if (res.ok) setEarthdataAuth(res);
    } catch {
      setEarthdataAuth(null);
    } finally {
      setEarthdataAuthChecking(false);
    }
  }

  useEffect(() => {
    setSelectedDownloadSceneIds((previous) => {
      const ids = scenes.map((scene) => scene.scene_id).filter(Boolean);
      if (!ids.length) return new Set();
      const kept = ids.filter((id) => previous.has(id));
      return new Set(kept.length ? kept : ids);
    });
  }, [scenes]);

  async function refreshNetwork() {
    setNetwork(await getNetworkSettings());
  }

  async function refreshDownloadArchive() {
    const bridged = hasBridge();
    try {
      const res = await getDownloadArchive();
      if (res.ok) {
        if (bridged) archiveLoadedFromBridge.current = true;
        const legacy = loadDownloadArchive() as DownloadArchiveItem[];
        const merged = [...res.items, ...legacy].reduce<DownloadArchiveItem[]>((acc, item) => {
          if (!acc.some((existing) => existing.id === item.id)) acc.push(item);
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

  useEffect(() => {
    void refreshTree();
    void refreshScenes();
    void refreshCredentials().then(() => refreshEarthdataAuth());
    void refreshNetwork();
    void refreshDownloadArchive();
  }, []);

  useEffect(() => {
    const reloadFromBridge = () => {
      void refreshTree();
      void refreshScenes();
      void refreshCredentials().then(() => refreshEarthdataAuth());
      void refreshNetwork();
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
        if (mounted && res.ok && res.update_available) setUpdateInfo(res);
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
    void refreshScenes();
  }, [ctx?.region?.region_id, ctx?.region?.scene_count]);

  useEffect(() => {
    setAoiPreviewGeometry(null);
    setFocusBbox(null);
    setSelectedAdminBoundary(null);
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
      const [download, orbit] = await Promise.all([
        getDownloadStatus(),
        getOrbitDownloadStatus(),
      ]);
      if (!mounted) return;
      setDlStatus(download);
      setOrbitStatus(orbit);
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
  const asfItems = (asfPlan?.items as Json[] | undefined) ?? [];
  const issues = (checkReport?.issues as Json[] | undefined) ?? [];
  const earthdataConfigured = isConfigured(creds?.earthdata);
  const earthdataInvalid =
    earthdataConfigured &&
    (earthdataAuth?.status === "expired" || earthdataAuth?.status === "invalid");
  const earthdataCanDownload = earthdataConfigured && !earthdataInvalid;
  const earthdataStatusLabel =
    !earthdataConfigured
      ? "未配置"
      : earthdataAuth?.status === "valid"
        ? "正常"
        : earthdataInvalid
          ? "已过期或失效"
          : "已保存";
  const opentopoConfigured = isConfigured(creds?.opentopography);
  const gacosConfigured = isConfigured(creds?.gacos);
  const dlActive = dlStatus?.state === "running" || dlStatus?.state === "paused";
  const dlVisible =
    !!dlStatus &&
    dlStatus.state !== "idle" &&
    dlActive;
  const orbitActive = orbitStatus?.state === "running" || orbitStatus?.state === "paused";
  const transferredBytes = (dlStatus?.done_bytes ?? 0) + (dlStatus?.current_bytes ?? 0);
  const dlPct = dlStatus?.total_bytes
    ? Math.round((transferredBytes / dlStatus.total_bytes) * 100)
    : dlStatus && dlStatus.total > 0
      ? Math.round((dlStatus.done / dlStatus.total) * 100)
      : 0;
  const currentPct = dlStatus?.current_expected_size
    ? Math.round(((dlStatus.current_bytes ?? 0) / dlStatus.current_expected_size) * 100)
    : 0;
  const activeAsfDownloads = dlStatus?.active_downloads?.length
    ? dlStatus.active_downloads
    : dlStatus?.current_scene
      ? [
          {
            scene_id: dlStatus.current_scene,
            bytes: dlStatus.current_bytes ?? 0,
            expected_size: dlStatus.current_expected_size,
          },
        ]
      : [];
  const orbitPct =
    orbitStatus && orbitStatus.total > 0 ? Math.round((orbitStatus.done / orbitStatus.total) * 100) : 0;
  const archiveableStates = new Set(["running", "paused", "finished", "failed", "cancelled", "interrupted", "timeout"]);
  const tiandituToken = network?.tianditu_token ?? "";
  const mapAoiGeometry = aoiPreviewGeometry ?? ctx?.region?.aoi_geojson;
  const adminProvinceOptions = useMemo(
    () => uniqueOptions(adminOptions.provinces.length ? adminOptions.provinces : CHINA_PROVINCES),
    [adminOptions.provinces],
  );
  const adminCityOptions = useMemo(() => {
    const preset = ADMIN_PRESETS[adminProvince];
    return withAllOption(adminOptions.cities.length ? adminOptions.cities : (preset?.cities ?? []));
  }, [adminOptions.cities, adminProvince]);
  const adminDistrictOptions = useMemo(() => {
    const preset = ADMIN_PRESETS[adminProvince];
    return withAllOption(adminOptions.districts.length ? adminOptions.districts : ((preset?.districts ?? {})[adminCity] ?? []));
  }, [adminCity, adminOptions.districts, adminProvince]);
  const hoveredScene = useMemo(
    () => scenes.find((scene) => scene.scene_id === hoveredSceneId) ?? null,
    [hoveredSceneId, scenes],
  );
  const selectedDownloadScenes = useMemo(
    () => scenes.filter((scene) => selectedDownloadSceneIds.has(scene.scene_id)),
    [scenes, selectedDownloadSceneIds],
  );
  const selectedDownloadSceneIdList = useMemo(
    () => selectedDownloadScenes.map((scene) => scene.scene_id),
    [selectedDownloadScenes],
  );
  const sceneMetadataStats = useMemo(() => {
    const total = scenes.length;
    const withFootprint = scenes.filter((scene) => scene.footprint_bbox || scene.footprint_geojson).length;
    const withCore = scenes.filter(
      (scene) =>
        (scene.path || scene.relative_orbit) &&
        scene.frame &&
        scene.orbit_direction &&
        scene.polarization,
    ).length;
    return {
      total,
      withFootprint,
      withCore,
      ready: total > 0 && withFootprint === total && withCore === total,
    };
  }, [scenes]);

  function selectAllDownloadScenes() {
    setSelectedDownloadSceneIds(new Set(scenes.map((scene) => scene.scene_id).filter(Boolean)));
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

  function highlightScene(sceneId: string | null) {
    setSelectedSceneId(sceneId);
  }

  function rememberTask(item: Omit<DownloadArchiveItem, "ts"> & { ts?: number }) {
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
    if (!dlStatus || !archiveableStates.has(dlStatus.state)) return;
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
      name: "ASF Sentinel-1 数据下载",
      status: dlStatus.state,
      detail,
      kind: "asf",
      output_dir: dlStatus.output_dir || dlStatus.results_path || "",
      total: dlStatus.total,
      concurrency: dlStatus.concurrency || Number(asfConcurrency) || 1,
      logs: dlStatus.log?.map((line) => line.detail).filter(Boolean) ?? [],
    });
  }, [
    dlStatus?.active_downloads,
    dlStatus?.concurrency,
    dlStatus?.done,
    dlStatus?.error,
    dlStatus?.output_dir,
    dlStatus?.results_path,
    dlStatus?.state,
    dlStatus?.summary_line,
    dlStatus?.total,
  ]);

  useEffect(() => {
    if (!orbitStatus || !archiveableStates.has(orbitStatus.state)) return;
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
      status: orbitStatus.state,
      detail,
      kind: "orbit",
      output_dir: orbitStatus.orbit_dir || "",
      total: orbitStatus.total,
      logs: orbitStatus.log?.map((line) => line.detail).filter(Boolean) ?? [],
    });
  }, [
    orbitStatus?.current_scene,
    orbitStatus?.done,
    orbitStatus?.error,
    orbitStatus?.orbit_dir,
    orbitStatus?.state,
    orbitStatus?.summary_line,
    orbitStatus?.total,
  ]);

  useEffect(() => {
    if (!demRun) return;
    if (demRunSource !== "download") return;
    const outputDir = demRunOutputDir(demRun);
    rememberTask({
      id: `dem:${outputDir || demRun.results_path || demRun.raw_dem_path || demRun.summary_line}:${demRun.total}`,
      name: "DEM 下载与转换",
      status: demRun.has_failures ? "failed" : "finished",
      detail: demRun.summary_line,
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

  async function onBrowseRoot() {
    const pick = await pickDirectory("选择项目根目录");
    if (pick.ok && pick.path) setRoot(pick.path);
  }

  async function onBrowseOutput() {
    const pick = await pickDirectory("选择本次任务输出目录");
    if (pick.ok && pick.path) setOutputDir(pick.path);
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

  async function ensureTaskOutput() {
    if (resolvedOutputDir) return resolvedOutputDir;
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

  async function onCreateProject() {
    if (!root.trim()) {
      setProjectError("请先选择或填写项目根目录。");
      return;
    }
    const finalProjectName = projectName.trim() || autoProjectName(root);
    const finalRegionName = regionName.trim() || autoRegionName(finalProjectName);
    setProjectBusy(true);
    setProjectError(null);
    setProjectNote(null);
    try {
      const dir = await ensureDirectory(root.trim());
      if (!dir.ok) {
        setProjectError(`${dir.error}${dir.code ? ` (${dir.code})` : ""}`);
        return;
      }
      const ws = await createWorkspace(root.trim(), `${finalProjectName} 工作目录`);
      if (!ws.ok) {
        setProjectError(`${ws.error}${ws.code ? ` (${ws.code})` : ""}`);
        return;
      }
      const project = await addProject(finalProjectName);
      if (!project.ok) {
        setProjectError(`${project.error}${project.code ? ` (${project.code})` : ""}`);
        return;
      }
      const region = await addRegion(finalRegionName);
      if (!region.ok) {
        setProjectError(`${region.error}${region.code ? ` (${region.code})` : ""}`);
        return;
      }
      setProjectName(finalProjectName);
      setRegionName(finalRegionName);
      await refresh();
      await refreshTree();
      setProjectNote(
        `已创建：${finalProjectName} / ${finalRegionName}。名称留空时会自动生成，目录仍按 根目录\\项目\\研究区 组织。`,
      );
    } catch (e) {
      setProjectError(formatBridgeError(e));
    } finally {
      setProjectBusy(false);
    }
  }

  async function onSelectProject(projectId: string) {
    const res = await selectProject(projectId);
    if (!res.ok) setProjectError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    await refresh();
    await refreshTree();
  }

  async function onSelectRegion(regionId: string) {
    const res = await selectRegion(regionId);
    if (!res.ok) setProjectError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    await refresh();
    await refreshTree();
  }

  async function bindBbox(bbox: Bbox) {
    setFocusBbox(bbox);
    setAoiPreviewGeometry(null);
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const res = await setRegionAoiBbox(bbox.west, bbox.east, bbox.south, bbox.north);
      if (res.ok) {
        setDrawActive(false);
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
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const res = boundary.geojson
        ? await setRegionAoiGeojson({
            type: "Feature",
            properties: { name: boundary.label },
            geometry: boundary.geojson,
          })
        : await setRegionAoiBbox(boundary.bbox.west, boundary.bbox.east, boundary.bbox.south, boundary.bbox.north);
      if (res.ok) {
        setDrawActive(false);
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

  async function onSearchAdminBoundary({
    bindFirst = false,
    queryOnly = false,
  }: { bindFirst?: boolean; queryOnly?: boolean } = {}) {
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
      if (bindFirst) await bindAdminBoundary(res.results[0]);
    } catch (e) {
      setAoiError(formatBridgeError(e));
    } finally {
      setAdminBusy(false);
    }
  }

  async function onBrowseAoiFile() {
    const pick = await pickOpenFile("选择 AOI 边界文件", [
      "AOI boundary (*.shp;*.kml;*.kmz;*.geojson;*.json)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) setAoiFile(pick.path);
  }

  async function onApplyAoiFile(path = aoiFile) {
    if (!path.trim()) {
      setAoiError("请选择 shp/kml/kmz/geojson 边界文件。");
      return;
    }
    if (!ctx?.region) {
      setAoiError("请先创建或选择研究区，再上传边界作为 AOI。");
      return;
    }
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const res = await setRegionAoiFile(path);
      if (res.ok) {
        setDrawActive(false);
        setAoiPreviewGeometry(res.aoi_geojson ?? null);
        const nextBbox = (res.aoi as { bbox?: Bbox | null }).bbox ?? null;
        if (nextBbox) {
          setFocusBbox(nextBbox);
          setDemWest(String(nextBbox.west));
          setDemEast(String(nextBbox.east));
          setDemSouth(String(nextBbox.south));
          setDemNorth(String(nextBbox.north));
        }
        setAoiNote(`已从边界文件绑定 AOI：${res.region_name}`);
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
        setSelectedSceneId(null);
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

  async function onBrowseSceneFile() {
    const pick = await pickOpenFile("选择 ASF 文件", [
      "ASF cart (*.py;*.metalink;*.csv;*.geojson;*.json;*.txt;*.metadata;*.meta;*.met)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) setSceneFile(pick.path);
  }

  async function onBrowseSceneDir() {
    const pick = await pickDirectory("选择已有 Sentinel-1 数据目录");
    if (pick.ok && pick.path) setSceneDir(pick.path);
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

  async function onAsfSearch() {
    setAsfSearchBusy(true);
    setAsfSearchError(null);
    setAsfSearchNote(null);
    setMetadataStatus({ ok: true, state: "running", done: 0, total: 1, percent: 0, message: "正在准备 ASF 检索" });
    setCheckReport(null);
    try {
      const bbox = ctx?.region?.bbox ?? null;
      const aoiGeojson = ctx?.region?.aoi_geojson ?? aoiPreviewGeometry ?? null;
      const res = await searchAsfScenes({
        bbox,
        aoi_geojson: aoiGeojson,
        use_current_aoi: true,
        start: normalizeDateInput(asfSearchStart),
        end: normalizeDateInput(asfSearchEnd),
        product_type: asfSearchProduct,
        beam_mode: asfSearchBeam,
        polarization: asfSearchPolarization,
        orbit_direction: asfSearchOrbit,
        relative_orbit: asfSearchRelativeOrbit || null,
        frame: asfSearchFrame || null,
        max_results: asfSearchMax || 100,
      });
      if (res.ok) {
        setScenes(res.scenes);
        setAsfSearchSummary(res.search ?? { returned_count: res.scenes.length, total_count: res.queried ?? null });
        setSelectedSceneId(null);
        await refresh();
        await refreshTree();
        setMetadataStatus(await getMetadataStatus());
        const total = res.search?.total_count;
        const returned = res.search?.returned_count ?? res.scenes.length;
        const requested = res.search?.requested_limit;
        const totalText = typeof total === "number" ? `；当前筛选条件总计 ${total} 景` : "";
        const rankText =
          typeof total === "number" && typeof requested === "number" && total > returned
            ? "；已按 AOI 覆盖率优先保留候选影像"
            : "";
        setAsfSearchNote(`ASF 检索导入 ${returned} 景${totalText}${rankText}；元数据已补全 path/frame/升降轨/范围。`);
      } else {
        setAsfSearchError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setAsfSearchError(formatBridgeError(e));
    } finally {
      setAsfSearchBusy(false);
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
      setSelectedSceneId(null);
      setSelectedDownloadSceneIds(new Set());
      setHoveredSceneId(null);
      setSceneWorkspaceOpen(false);
      setCheckReport(null);
      setAsfPlan(null);
      setAsfSearchSummary(null);
      setFocusBbox(null);
      setMetadataStatus(null);
      setSceneNote(null);
      setAsfSearchNote("已清除 ASF 检索/导入结果。");
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
      setSelectedSceneId(null);
      setSelectedDownloadSceneIds(new Set());
      setHoveredSceneId(null);
      setSceneWorkspaceOpen(false);
      setCheckReport(null);
      setAsfPlan(null);
      setAsfSearchSummary(null);
      setFocusBbox(null);
      setAoiPreviewGeometry(null);
      setMetadataStatus(null);
      setSceneNote(null);
      setDrawActive(false);
      setAsfSearchNote("已清空地图上的 AOI、ASF 影像范围和临时高亮。");
      await refresh();
      await refreshTree();
    } catch (e) {
      setAsfSearchError(formatBridgeError(e));
    }
  }

  async function onAsfPrecheck() {
    setAsfBusy(true);
    setAsfError(null);
    try {
      if (selectedDownloadSceneIdList.length === 0) {
        setAsfError("请先在“所选 SAR 数据”中勾选要下载的影像。");
        return;
      }
      const res = await planAsfDownload(resolvedOutputDir, selectedDownloadSceneIdList);
      if (res.ok) setAsfPlan(res.plan);
      else setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setAsfError(formatBridgeError(e));
    } finally {
      setAsfBusy(false);
    }
  }

  async function onStartAsf() {
    setAsfStartBusy(true);
    setAsfError(null);
    try {
      if (!earthdataCanDownload) {
        setAsfError(
          earthdataInvalid
            ? "Earthdata/ASF 凭据已过期或失效，请在设置里重新保存 Token 或账号密码。"
            : "开始 Sentinel-1 下载前，请先在设置里保存 Earthdata Token 或账号密码。",
        );
        setPanel("settings");
        return;
      }
      const out = await ensureTaskOutput();
      if (!out) {
        setAsfError("开始下载前需要确认一个输出目录。");
        return;
      }
      setOutputDir(out);
      if (selectedDownloadSceneIdList.length === 0) {
        setAsfError("请先在“所选 SAR 数据”中勾选要下载的影像。");
        return;
      }
      const res = await startAsfDownload(out, "auto", Number(asfConcurrency) || 1, selectedDownloadSceneIdList);
      if (res.ok) setDlStatus(await getDownloadStatus());
      else setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setAsfError(formatBridgeError(e));
    } finally {
      setAsfStartBusy(false);
    }
  }

  async function onRetryAsf() {
    setAsfError(null);
    try {
      const res = await retryAsfDownload();
      if (!res.ok) {
        setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      setDlStatus(await getDownloadStatus());
      setPanel("downloads");
    } catch (e) {
      setAsfError(formatBridgeError(e));
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

    if (kind === "asf" && !earthdataCanDownload) {
      setAsfError(
        earthdataInvalid
          ? "Earthdata/ASF 凭据已过期或失效，请在设置里重新保存 Token 或账号密码。"
          : "继续 Sentinel-1 下载前，请先在设置里保存 Earthdata Token 或账号密码。",
      );
      setPanel("settings");
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

    setPanel("downloads");
    setOutputDir(out);
    markDetail("正在恢复任务：先进行网络与凭据预检，成功后会回到任务队列。");
    try {
      if (kind === "asf") {
        const workers = Number(task.concurrency) || Number(asfConcurrency) || 1;
        setAsfConcurrency(String(workers));
        const res = await startAsfDownload(out, "auto", workers);
        if (res.ok) {
          setDownloadArchive((prev) => prev.filter((item) => archiveTaskKey(item) !== taskKey));
          setDlStatus(await getDownloadStatus());
          return;
        }
        mark("failed", `${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      if (kind === "orbit") {
        const res = await startOrbitDownload(out);
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

  async function onBrowseOrbitDir() {
    const pick = await pickDirectory("选择 Sentinel-1 精密轨道 EOF 目录");
    if (pick.ok && pick.path) setOrbitDir(pick.path);
  }

  async function onOrbitMatch() {
    setOrbitBusy(true);
    setOrbitError(null);
    try {
      const res = await matchOrbitsDirectory(orbitDir);
      if (res.ok) setOrbitMatch(res);
      else setOrbitError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setOrbitError(formatBridgeError(e));
    } finally {
      setOrbitBusy(false);
    }
  }

  async function onStartOrbit() {
    setOrbitStartBusy(true);
    setOrbitError(null);
    try {
      const out = await ensureTaskOutput();
      if (!out) {
        setOrbitError("开始下载轨道前需要确认一个输出目录。");
        return;
      }
      const res = await startOrbitDownload(out);
      if (res.ok) setOrbitStatus(await getOrbitDownloadStatus());
      else setOrbitError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setOrbitError(formatBridgeError(e));
    } finally {
      setOrbitStartBusy(false);
    }
  }

  async function onRunDemDownload() {
    setDemDownloadBusy(true);
    setDemError(null);
    setDemRun(null);
    setDemRunSource(null);
    try {
      if (!DOWNLOADABLE_DEM_DATASETS.has(dataset)) {
        setDemError("当前选择的是本地或未接入 DEM 来源，不能在线下载；请选择 COP30、SRTM、AW3D30 等在线 DEM，或使用“本地 DEM 转换”。");
        return;
      }
      if (!opentopoConfigured) {
        setDemError("开始下载 DEM 前，请先在设置里保存 OpenTopography API Key。");
        setPanel("settings");
        return;
      }
      const out = await ensureDemDownloadOutput();
      if (!out) {
        setDemError("开始下载 DEM 前需要确认一个输出目录。");
        return;
      }
      const res = ctx?.region?.bbox
        ? await runDemDownload(out, dataset)
        : await runDemDownloadBbox(
            manualDemBbox.west,
            manualDemBbox.east,
            manualDemBbox.south,
            manualDemBbox.north,
            out,
            dataset,
          );
      if (res.ok) {
        setDemRunSource("download");
        setDemRun(res);
      }
      else setDemError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setDemError(formatBridgeError(e));
    } finally {
      setDemDownloadBusy(false);
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

  async function onRunLocalDem() {
    setLocalDemBusy(true);
    setDemError(null);
    setDemRun(null);
    setDemRunSource(null);
    try {
      const out = await ensureLocalDemOutput();
      if (!out) {
        setDemError("转换本地 DEM 前需要确认一个输出目录。");
        return;
      }
      const res = await runLocalDemConversion(localDem, out, localDatum);
      if (res.ok) {
        setDemRunSource("local");
        setDemRun(res);
      }
      else setDemError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setDemError(formatBridgeError(e));
    } finally {
      setLocalDemBusy(false);
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
        await refreshEarthdataAuth();
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
        await refreshEarthdataAuth();
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

function renderOutputParameters(
  desc = "任务开始前确认输出根目录；留空时使用当前项目或研究区目录。",
  options?: {
    value?: string;
    onChange?: (value: string) => void;
    onBrowse?: () => Promise<string>;
    placeholder?: string;
    title?: string;
  },
) {
    const value = options?.value ?? outputDir;
    const onChange = options?.onChange ?? setOutputDir;
    const placeholder = options?.placeholder ?? (value.trim() || "开始任务时选择输出目录");
    return (
      <div className="space-y-2 rounded-2xl border border-white/45 bg-white/40 p-2.5 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
        <div className="flex items-center gap-2 text-xs font-medium">
          <HardDrive className="h-3.5 w-3.5 text-primary" />
          输出参数
        </div>
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            className="font-mono text-xs"
            spellCheck={false}
          />
          <Button
            variant="outline"
            size="icon"
            onClick={() => void (options?.onBrowse ?? onBrowseOutput)()}
            title={options?.title ?? "浏览输出目录"}
          >
            <FolderOpen className="h-4 w-4" />
          </Button>
        </div>
        <div className="text-[11px] leading-4 text-muted-foreground">{desc}</div>
      </div>
    );
  }

  function renderProjectContext() {
    return (
      <Section
        title="高级目录管理"
        desc="一般不用先设置；需要固定根目录、项目名或研究区名时再展开。"
        icon={HardDrive}
        defaultOpen={false}
      >
        <div className="space-y-3">
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Input
              value={root}
              onChange={(e) => setRoot(e.target.value)}
              placeholder="选择或新建工作目录"
              spellCheck={false}
              className="font-mono text-xs"
            />
            <Button variant="outline" size="icon" onClick={onBrowseRoot} title="浏览根目录">
              <FolderOpen className="h-4 w-4" />
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Input
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="项目名称（可选）"
            />
            <Input
              value={regionName}
              onChange={(e) => setRegionName(e.target.value)}
              placeholder="研究区名称（可选）"
            />
          </div>
          <Button
            className="w-full"
            onClick={onCreateProject}
            disabled={projectBusy || !root.trim()}
          >
            {projectBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderPlus className="h-4 w-4" />}
            创建 / 切换目录
          </Button>
          <div className="rounded-md border bg-muted/35 px-3 py-2 text-xs">
            {kv("当前项目", ctx?.project?.name ?? "未选择")}
            {kv("当前研究区", ctx?.region?.name ?? "未选择")}
            {kv("目录结构", "根目录\\项目\\研究区")}
          </div>
          <ErrorLine text={projectError} />
          <NoteLine text={projectNote} />
          {tree?.projects.length ? (
            <div className="max-h-40 space-y-2 overflow-y-auto pr-1">
              {tree.projects.map((project) => (
                <div key={project.project_id} className="rounded-md border bg-card px-2 py-2">
                  <button
                    type="button"
                    onClick={() => void onSelectProject(project.project_id)}
                    className="flex w-full items-center justify-between gap-2 text-left text-xs"
                  >
                    <span className="truncate font-medium">{project.name}</span>
                    {tree.current_project_id === project.project_id && <Badge variant="success">当前</Badge>}
                  </button>
                  {project.regions.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {project.regions.map((region) => (
                        <button
                          key={region.region_id}
                          type="button"
                          onClick={() => void onSelectRegion(region.region_id)}
                          className={cn(
                            "rounded-full border px-2 py-1 text-[11px]",
                            tree.current_region_id === region.region_id
                              ? "border-primary bg-primary/10 text-primary"
                              : "bg-background text-muted-foreground hover:text-foreground",
                          )}
                        >
                          {region.name} · {region.scene_count} 景
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </Section>
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
        <div className="space-y-3">
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
          <div className="grid grid-cols-[1fr_auto_auto] gap-2">
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
              上传
            </Button>
            <Button
              variant="outline"
              size="icon"
              title="清空行政区搜索结果"
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
          <Button
            className="w-full"
            onClick={() => selectedAdminBoundary && void bindAdminBoundary(selectedAdminBoundary)}
            disabled={!selectedAdminBoundary || aoiBusy}
          >
            {aoiBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPinned className="h-4 w-4" />}
            绑定选中边界为 AOI
          </Button>
          {aoiFile && (
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <Input value={aoiFile} readOnly className="font-mono text-xs" />
              <Button variant="outline" onClick={() => void onApplyAoiFile()} disabled={aoiBusy}>
                绑定
              </Button>
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
                    setAoiNote(`已定位行政边界：${item.label}。确认后可绑定为 AOI。`);
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
              <span className="font-medium">经纬度范围（矩形 AOI / WGS-84）</span>
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
          <div className="rounded-2xl border border-white/45 bg-white/35 px-3 py-2 text-[11px] leading-4 text-muted-foreground shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
            优先使用天地图行政区划服务（需在设置中填写 Token）；未配置或接口不可达时会临时使用备用开放地名源。正式项目建议上传本地权威边界文件。
          </div>
          <ErrorLine text={aoiError} />
          <NoteLine text={aoiNote} />
        </div>
      </Section>
    );
  }

  function renderAsfSearchSection() {
    return (
      <Section
        title="ASF 筛选"
        desc="按当前 AOI、日期、产品类型、轨道、束模式和极化筛选；没有 AOI 也可检索。"
        icon={Search}
      >
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <select
              value={asfSearchProduct}
              onChange={(e) => setAsfSearchProduct(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="SLC">SLC</option>
              <option value="GRD">GRD</option>
            </select>
            <select
              value={asfSearchOrbit}
              onChange={(e) => setAsfSearchOrbit(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">升降轨不限</option>
              <option value="ASCENDING">升轨</option>
              <option value="DESCENDING">降轨</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={asfSearchBeam}
              onChange={(e) => setAsfSearchBeam(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">束模式不限</option>
              <option value="IW">IW</option>
              <option value="EW">EW</option>
              <option value="SM">SM</option>
              <option value="WV">WV</option>
            </select>
            <select
              value={asfSearchPolarization}
              onChange={(e) => setAsfSearchPolarization(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">极化不限</option>
              <option value="DV">DV（VV+VH）</option>
              <option value="DH">DH（HH+HV）</option>
              <option value="SV">SV（VV）</option>
              <option value="SH">SH（HH）</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <CalendarDays className="h-3.5 w-3.5" />
                开始日期
              </span>
              <Input
                type="date"
                value={dateInputValue(asfSearchStart)}
                onChange={(e) => setAsfSearchStart(e.target.value)}
                aria-label="开始日期"
              />
            </label>
            <label className="space-y-1">
              <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <CalendarDays className="h-3.5 w-3.5" />
                结束日期
              </span>
              <Input
                type="date"
                value={dateInputValue(asfSearchEnd)}
                onChange={(e) => setAsfSearchEnd(e.target.value)}
                aria-label="结束日期"
              />
            </label>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Input
              value={asfSearchRelativeOrbit}
              onChange={(e) => setAsfSearchRelativeOrbit(e.target.value)}
              placeholder="Path / 相对轨道"
              inputMode="numeric"
            />
            <Input
              value={asfSearchFrame}
              onChange={(e) => setAsfSearchFrame(e.target.value)}
              placeholder="Frame"
              inputMode="numeric"
            />
            <Input
              value={asfSearchMax}
              onChange={(e) => setAsfSearchMax(e.target.value)}
              placeholder="最多条数"
              inputMode="numeric"
            />
          </div>
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Button onClick={onAsfSearch} disabled={asfSearchBusy} className="w-full">
              {asfSearchBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              检索并导入
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => void onClearScenes()}
              disabled={asfSearchBusy || (!scenes.length && !checkReport && !asfPlan)}
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
          <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs">
            {kv("区域", ctx?.region?.bbox ? "使用当前 AOI" : "未设置 AOI，将按日期/条件检索")}
            {kv(
              "候选",
              typeof asfSearchSummary?.total_count === "number"
                ? `${asfSearchSummary.total_count} 景符合当前筛选`
                : "检索后显示当前条件总数",
            )}
            {kv(
              "导入",
              typeof asfSearchSummary?.returned_count === "number"
                ? `${asfSearchSummary.returned_count} 景已进入下载列表`
                : "导入后会自动刷新地图覆盖范围",
            )}
          </div>
          <ErrorLine text={asfSearchError} />
          <NoteLine text={asfSearchNote} />
        </div>
      </Section>
    );
  }

  function renderSceneSourceControls(desc: string) {
    return (
      <Section title="SAR 影像来源" desc={desc} icon={Satellite}>
        <div className="space-y-3">
          <div className="grid grid-cols-[1fr_auto_auto] gap-2">
            <Input
              value={sceneFile}
              onChange={(e) => setSceneFile(e.target.value)}
              placeholder="ASF 官方 py / metalink / metadata / CSV / GeoJSON"
              className="font-mono text-xs"
              spellCheck={false}
            />
            <Button variant="outline" size="icon" onClick={onBrowseSceneFile} title="选择 ASF 官方文件">
              <FolderOpen className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              onClick={() => void handleSceneImport(() => importScenesFile(sceneFile))}
              disabled={sceneBusy || !sceneFile.trim()}
            >
              导入
            </Button>
          </div>
          <div className="grid grid-cols-[1fr_auto_auto] gap-2">
            <Input
              value={sceneDir}
              onChange={(e) => setSceneDir(e.target.value)}
              placeholder="SAR 影像目录（.SAFE / .zip，支持 SLC、GRD、RAW、OCN 文件名识别）"
              className="font-mono text-xs"
              spellCheck={false}
            />
            <Button variant="outline" size="icon" onClick={onBrowseSceneDir} title="选择 SAR 影像目录">
              <FolderOpen className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              onClick={() => void handleSceneImport(() => importScenesDirectory(sceneDir))}
              disabled={sceneBusy || !sceneDir.trim()}
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
              sceneMetadataStats.ready
                ? "border-success/35 bg-success/10"
                : sceneMetadataStats.withFootprint > 0 || sceneMetadataStats.withCore > 0
                  ? "border-primary/30 bg-primary/10"
                  : "border-white/45 bg-white/35 dark:border-white/10 dark:bg-white/10",
            )}
          >
            {kv("当前场景", scenes.length ? `${scenes.length} 景` : "未导入")}
            {kv(
              "元数据",
              sceneMetadataStats.total
                ? sceneMetadataStats.ready
                  ? "已补全 SAR 范围、Path、Frame、升降轨、极化"
                  : `已补全范围 ${sceneMetadataStats.withFootprint}/${sceneMetadataStats.total}，核心字段 ${sceneMetadataStats.withCore}/${sceneMetadataStats.total}`
                : "导入后会尝试补全",
            )}
          </div>
          <ErrorLine text={sceneError} />
          <NoteLine text={sceneNote} />
        </div>
      </Section>
    );
  }

  function renderSceneResultSection() {
    if (scenes.length === 0 && !checkReport) return null;
    return (
      <Section
        title="所选 SAR 数据"
        desc="ASF 筛选、目录识别和手动导入得到的数据统一在这里查看、核查、定位和高亮。"
        icon={Database}
        defaultOpen={false}
        storageKey="sentinel1-scene-results"
      >
        <div className="space-y-3">
          {scenes.length > 0 && (
            <div className="relative rounded-md border bg-muted/30" onMouseLeave={() => setHoveredSceneId(null)}>
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
                  <Button size="sm" variant="outline" onClick={() => setSceneWorkspaceOpen(true)}>
                    <Maximize2 className="h-3.5 w-3.5" />
                    工作台
                  </Button>
                  <Button size="sm" variant="outline" onClick={onRunCheck} disabled={checkBusy}>
                    {checkBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                    核查
                  </Button>
                </div>
              </div>
              <div className="max-h-[34rem] overflow-y-auto">
                {scenes.map((scene) => (
                  <div
                    key={scene.scene_id}
                    onClick={() => {
                      highlightScene(scene.scene_id);
                    }}
                    className={cn(
                      "block w-full cursor-pointer border-b border-l-4 border-l-transparent px-3 py-2 text-left text-xs transition-colors last:border-b-0 hover:bg-white/45 dark:hover:bg-white/10",
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
                        onMouseEnter={() => setHoveredSceneId(scene.scene_id)}
                        onMouseLeave={() => setHoveredSceneId(null)}
                        title="查看元数据"
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
              {hoveredScene && (
                <div className="pointer-events-none absolute right-2 top-12 z-[80]">
                  <SceneMetaCard scene={hoveredScene} />
                </div>
              )}
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

  function renderSentinel1Panel() {
    return (
      <div className="space-y-3">
        {renderAsfSearchSection()}
        {renderSceneResultSection()}
        <Section
          title="ASF 文件 / URL 手动导入"
          desc="已有 ASF 官方 py、metalink、metadata、CSV、GeoJSON、下载 URL 或颗粒名时，从这里导入并补全元数据。"
          icon={Satellite}
          defaultOpen={false}
          storageKey="sentinel1-manual-import"
        >
          <div className="space-y-3">
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
              <Button variant="outline" onClick={onBrowseSceneFile}>
                <FolderOpen className="h-4 w-4" />
                选 ASF 文件
              </Button>
            </div>
            {sceneFile && (
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <Input value={sceneFile} readOnly className="font-mono text-xs" />
                <Button
                  onClick={() => void handleSceneImport(() => importScenesFile(sceneFile))}
                  disabled={sceneBusy}
                >
                  <FileUp className="h-4 w-4" />
                  导入
                </Button>
              </div>
            )}
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
            <NoteLine text={sceneNote} />
          </div>
        </Section>
        <Section
          title="Sentinel-1 下载"
          desc="开始下载时才确认输出目录；支持暂停、继续、结束和 .part 断点续传。"
          icon={CloudDownload}
        >
          <div className="space-y-3">
            {renderOutputParameters("下载前确认输出根目录；同一目录再次开始可利用 .part 断点续传。")}
            {(creds === null || earthdataAuthChecking) && (
              <div className="rounded-2xl border border-primary/25 bg-primary/10 px-3 py-2 text-xs shadow-sm backdrop-blur-xl">
                <div className="flex items-start gap-2">
                  <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary" />
                  <div className="min-w-0 flex-1 leading-5">
                    <div className="font-medium">正在自动检查 Earthdata/ASF 凭据</div>
                    <div className="text-muted-foreground">会读取已保存 Token、账号密码、环境变量或 netrc，完成后自动刷新状态。</div>
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
            <div className="grid grid-cols-[1fr_96px] items-center gap-2 rounded-2xl border border-white/45 bg-white/35 px-3 py-2 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
              <div>
                <div className="font-medium">下载并发</div>
                <div className="text-[11px] text-muted-foreground">
                  建议 1-3；网络或账号限速时调低。
                </div>
              </div>
              <Input
                type="number"
                min={1}
                max={8}
                value={asfConcurrency}
                onChange={(e) => setAsfConcurrency(e.target.value)}
                className="text-center"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={onAsfPrecheck} disabled={asfBusy}>
                {asfBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                下载预检
              </Button>
              <Button
                onClick={onStartAsf}
                disabled={asfStartBusy || dlActive || selectedDownloadSceneIdList.length === 0 || !earthdataCanDownload}
                title={!earthdataCanDownload ? "请先确认 Earthdata/ASF 凭据正常" : undefined}
              >
                {asfStartBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                开始下载
              </Button>
            </div>
            <ErrorLine text={asfError} />
            {asfPlan && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                {kv("预检含义", "离线清单，不替代下载任务")}
                {kv("可下载", `${String(asfPlan.planned_count ?? 0)} / ${String(asfPlan.scene_count ?? 0)} 景`)}
                {kv("缺 URL", String(asfPlan.missing_url_count ?? 0))}
                {asfItems.slice(0, 3).map((item, i) => (
                  <div key={i} className="mt-2 truncate font-mono text-[11px] text-muted-foreground">
                    {String(item.expected_filename ?? item.scene_id)}
                  </div>
                ))}
              </div>
            )}
          </div>
        </Section>
      </div>
    );
  }

  function renderDemResultCard() {
    if (!demRun) return null;
    const logs = demRunLogLines(demRun);
    const title = demRunSource === "local" ? "本地 DEM 转换结果" : "DEM 下载与转换结果";
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
        <Progress value={100} className="mt-3" />
        <div className="mt-3 grid grid-cols-2 gap-2">
          {kv("任务数", demRun.total)}
          {kv("成功", demRun.succeeded ?? demRun.copied ?? 0)}
          {kv("跳过", skipped)}
          {kv("失败", demRun.failed ?? 0)}
          {kv("下载结果", demRun.results_path ? pathBaseName(demRun.results_path) : "-")}
          {kv("转换结果", demRun.conversion_results_path ? pathBaseName(demRun.conversion_results_path) : "-")}
        </div>
        <div className="mt-3 space-y-2">
          {[
            { label: "原始 DEM", path: demPaths.raw },
            { label: "椭球高 DEM", path: demPaths.ellipsoid },
            { label: "SARscape DEM", path: demPaths.sarscape },
          ].map(({ label, path }) => (
            <div key={label} className="rounded-md border bg-muted/20 p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="shrink-0 text-muted-foreground">{label}</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!path}
                  onClick={() => void openLocalPath(pathDirName(String(path || "")))}
                >
                  <FolderOpen className="h-4 w-4" />
                  打开目录
                </Button>
              </div>
              <div className="mt-1 break-all font-mono text-[11px] text-muted-foreground">{path || "-"}</div>
            </div>
          ))}
        </div>
        {logs.length > 0 && (
          <details className="mt-3 rounded-md border bg-muted/20 p-2">
            <summary className="cursor-pointer select-none text-xs font-medium">详细日志</summary>
            <div className="mt-2 max-h-52 overflow-y-auto font-mono text-[11px] leading-5">
              {logs.map((line, i) => (
                <div key={i} className="break-all">
                  {line}
                </div>
              ))}
            </div>
          </details>
        )}
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
          title="DEM 下载并转换"
          desc="下载后自动保留原始 tif，同时输出椭球高 tif 和 SARscape 所需 _dem 后缀文件。"
          icon={Mountain}
        >
          <div className="space-y-3">
            <select
              value={dataset}
              onChange={(e) => {
                setDataset(e.target.value);
                void setDemDataset(e.target.value);
              }}
              className="flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {DEM_DATASET_GROUPS.map((group) => (
                <optgroup key={group.label} label={group.label}>
                  {group.options.map((item) => (
                    <option key={item.value} value={item.value} disabled={!item.enabled}>
                      {item.label}
                      {item.hint ? ` · ${item.hint}` : item.enabled ? "" : " · 待接入"}
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
                {kv("椭球高 tif", `${previewStem}_ellipsoid.tif`)}
                {kv("SARscape 主文件", `${previewStem}_dem`)}
                {kv("SARscape 头文件", `${previewStem}_dem.hdr`)}
              </div>
              <div className="mt-2 text-[11px] leading-5 text-muted-foreground">
                OpenTopography 在线接口返回原始 GeoTIFF；软件会先生成椭球高 GeoTIFF，再导出 SARscape 常用的 ENVI _dem + .hdr。
              </div>
            </div>
            {renderOutputParameters("保存原始 GeoTIFF、椭球高 GeoTIFF 和 SARscape *_dem + *.hdr。", {
              value: demDownloadOutputDir,
              onChange: setDemDownloadOutputDir,
              onBrowse: onBrowseDemDownloadOutput,
              placeholder: resolvedDemDownloadOutputDir || "开始下载时选择 DEM 下载输出目录",
              title: "浏览 DEM 下载输出目录",
            })}
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
            <Button
              onClick={onRunDemDownload}
              disabled={demDownloadBusy || !opentopoConfigured}
              className="w-full"
              title={!opentopoConfigured ? "请先在设置里保存 OpenTopography API Key" : undefined}
            >
              {demDownloadBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
              下载并转换 DEM
            </Button>
            <ErrorLine text={demError} />
          </div>
        </Section>
        <Section
          title="本地 DEM 转换"
          desc="可直接选择用户已有 DEM，并自动识别或手动指定高程基准。"
          icon={FileUp}
        >
          <div className="space-y-3">
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
              <option value="auto">自动识别</option>
              <option value="EGM96">EGM96 正高</option>
              <option value="EGM2008">EGM2008 正高</option>
              <option value="WGS84_ELLIPSOID">WGS84 椭球高</option>
            </select>
            {renderOutputParameters("本地 DEM 转换输出到此目录；留空时默认使用所选 DEM 所在文件夹。", {
              value: localDemOutputDir,
              onChange: setLocalDemOutputDir,
              onBrowse: onBrowseLocalDemOutput,
              placeholder: localPreviewOutputRoot,
              title: "浏览本地 DEM 转换输出目录",
            })}
            <Button variant="outline" onClick={onRunLocalDem} disabled={localDemBusy || !localDem} className="w-full">
              {localDemBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              转换为 SARscape DEM
            </Button>
          </div>
        </Section>
        {renderDemResultCard()}
      </div>
    );
  }

  function renderOrbitPanel() {
    return (
      <div className="space-y-3">
        {renderSceneSourceControls(
          "精密轨道根据 SAR 影像名解析平台、采集日期和轨道号；可导入 ASF 官方 py、metalink、metadata，或扫描本地 SAR 影像目录。",
        )}
        <Section
          title="精密轨道"
          desc="根据已导入的 SAR 影像匹配或下载 POEORB；太新的影像可能因精密轨道尚未发布而显示不可用原因。"
          icon={Orbit}
        >
          <div className="space-y-3">
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <Input
                value={orbitDir}
                onChange={(e) => setOrbitDir(e.target.value)}
                placeholder="已有轨道 EOF 目录（可选，仅用于扫描匹配）"
                className="font-mono text-xs"
                spellCheck={false}
              />
              <Button variant="outline" size="icon" onClick={onBrowseOrbitDir}>
                <FolderOpen className="h-4 w-4" />
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={onOrbitMatch} disabled={orbitBusy || !orbitDir.trim() || scenes.length === 0}>
                {orbitBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                扫描匹配
              </Button>
              <Button onClick={onStartOrbit} disabled={orbitStartBusy || orbitActive || scenes.length === 0}>
                {orbitStartBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
                下载 POEORB
              </Button>
            </div>
            {renderOutputParameters("轨道下载会自动写入 输出根目录\\Sentinel_Orbit\\AUX_POEORB。")}
            <div className="rounded-md border bg-muted/30 p-3 text-xs">
              {kv("自动目录", "Sentinel_Orbit\\AUX_POEORB")}
              {kv("控制说明", "暂停/结束会在当前 EOF 请求结束后生效")}
            </div>
            <ErrorLine text={orbitError} />
            {orbitMatch && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                {kv("EOF 文件", orbitMatch.orbit_files)}
                {kv("匹配", `${String(orbitMatch.report.matched_scenes ?? 0)} / ${String(orbitMatch.report.total_scenes ?? 0)} 景`)}
              </div>
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
    const activeTasks = [
      dlStatus && dlVisible
        ? {
            id: "asf-active",
            name: "ASF Sentinel-1 数据下载",
            status: dlStatus.state,
            progress: dlPct,
            count: `${dlStatus.done}/${dlStatus.total}`,
            detail:
              activeAsfDownloads.length > 0
                ? `正在下载 ${activeAsfDownloads.length} / ${dlStatus.concurrency ?? activeAsfDownloads.length} 景`
                : dlStatus.summary_line || "等待下一个场景",
            activeDownloads: activeAsfDownloads,
            metrics: [
              ["已下载", dlStatus.total_bytes ? `${fmtBytes(transferredBytes)} / ${fmtBytes(dlStatus.total_bytes)}` : fmtBytes(transferredBytes)],
              ["速度", fmtRate(dlStatus.bytes_per_second)],
              ["用时", fmtDuration(dlStatus.elapsed_seconds)],
              ["并发", dlStatus.concurrency ?? 1],
              ["断点续传", dlStatus.resume_supported ? "支持 .part" : "未知"],
              ["失败", (dlStatus.failed ?? 0) + (dlStatus.interrupted ?? 0)],
            ],
            controls: (
              <div className="grid grid-cols-4 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={dlStatus.state !== "running"}
                  onClick={() => void pauseAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}
                >
                  <Pause className="h-4 w-4" />
                  暂停
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={dlStatus.state !== "paused"}
                  onClick={() => void resumeAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}
                >
                  <Play className="h-4 w-4" />
                  继续
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={!dlActive}
                  onClick={() => void stopAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}
                >
                  <Square className="h-4 w-4" />
                  结束
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!dlStatus.retry_supported}
                  onClick={() => void onRetryAsf()}
                  title={dlStatus.retry_hint || "重试失败/中断的 ASF 场景"}
                >
                  <RotateCcw className="h-4 w-4" />
                  重试
                </Button>
              </div>
            ),
            workspaceAction: (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="w-full justify-center"
                disabled={scenes.length === 0}
                title={scenes.length === 0 ? "请先完成 ASF 检索或导入，才能打开每景影像工作台。" : undefined}
                onClick={() => setSceneWorkspaceOpen(true)}
              >
                <Satellite className="h-4 w-4" />
                打开下载工作台
              </Button>
            ),
            log: dlStatus.log?.map((line) => line.detail) ?? [],
          }
        : null,
      orbitStatus && orbitActive
        ? {
            id: "orbit-active",
            name: "Sentinel-1 精密轨道下载",
            status: orbitStatus.state,
            progress: orbitPct,
            count: `${orbitStatus.done}/${orbitStatus.total}`,
            detail: orbitStatus.current_scene ? "正在匹配并下载精密轨道" : orbitStatus.summary_line || "等待下一个 EOF",
            activeDownloads: orbitStatus.current_scene
              ? [
                  {
                    scene_id: orbitStatus.current_scene,
                    bytes: orbitStatus.done,
                    expected_size: orbitStatus.total,
                  },
                ]
              : [],
            metrics: [
              ["轨道目录", orbitStatus.orbit_dir ? pathBaseName(orbitStatus.orbit_dir) : "-"],
              ["用时", fmtDuration(orbitStatus.elapsed_seconds)],
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
            log: orbitStatus.log?.map((line) => line.detail) ?? [],
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
    }[];
    const archiveItems = dedupeArchiveItems(downloadArchive);
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
        activeDownloads: [],
        workspaceAction:
          kind === "asf" ? (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="w-full justify-center"
              disabled={scenes.length === 0}
              title={scenes.length === 0 ? "请先完成 ASF 检索或导入，才能打开每景影像工作台。" : undefined}
              onClick={() => setSceneWorkspaceOpen(true)}
            >
              <Satellite className="h-4 w-4" />
              打开下载工作台
            </Button>
          ) : null,
        metrics: [
          ["类型", kind === "asf" ? "ASF Sentinel-1" : "精密轨道"],
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
                          logs: [...(item.logs ?? []), "用户已结束该保留任务。"].slice(-120),
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
    const queueTasks = [...activeTasks, ...archivedQueueItems];
    const historyTasks = archiveItems.filter((task) => !isRestorableArchiveTask(task));

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
                <div key={task.id} className="rounded-lg border bg-card p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold">{task.name}</div>
                      <div className="truncate text-xs text-muted-foreground">{task.detail}</div>
                    </div>
                    <div className="shrink-0 text-right">
                      <Badge
                        variant={task.status === "paused" || task.status === "failed" || task.status === "cancelled" ? "warning" : "success"}
                      >
                        {statusLabel(task.status)}
                      </Badge>
                      <div className="mt-1 font-mono text-[11px] text-muted-foreground">{task.count}</div>
                    </div>
                  </div>
                  <Progress value={task.progress} className="mt-3" />
                  {task.activeDownloads && task.activeDownloads.length > 0 && (
                    <div className="mt-3 space-y-2 rounded-md border bg-muted/20 p-2">
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
                  <div className="mt-3 space-y-1">
                    {task.metrics.map(([label, value]) => kv(label, value))}
                  </div>
                  {task.workspaceAction && <div className="mt-3">{task.workspaceAction}</div>}
                  <div className="mt-3">{task.controls}</div>
                  {task.log.length > 0 && (
                    <div className="mt-3">
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
                        <div className="mt-2 max-h-52 overflow-y-auto rounded-md border bg-muted/20 p-2 font-mono text-[11px]">
                          {task.log.map((line, i) => (
                            <div key={i} className="break-all leading-5">
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

        <Section title="历史记录" desc="完成、失败、结束和已删除的任务会归档到这里。" icon={Database}>
          <div className="space-y-2">
            {historyTasks.length === 0 ? (
              <div className="rounded-md border border-dashed py-8 text-center text-xs text-muted-foreground">
                暂无历史任务。
              </div>
            ) : (
              historyTasks.map((task) => (
                <div key={task.id} className="rounded-lg border bg-card p-3">
                  <div className="flex items-start justify-between gap-3">
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() =>
                        setExpandedHistoryIds((prev) => {
                          const next = new Set(prev);
                          if (next.has(task.id)) next.delete(task.id);
                          else next.add(task.id);
                          return next;
                        })
                      }
                    >
                      <div className="flex min-w-0 items-center gap-1.5">
                        {expandedHistoryIds.has(task.id) ? (
                          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        )}
                        <div className="truncate text-sm font-semibold">{task.name}</div>
                      </div>
                      <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{task.detail}</div>
                      <div className="mt-1 text-[11px] text-muted-foreground">
                        {new Date(task.ts).toLocaleString()}
                      </div>
                    </button>
                    <div className="flex shrink-0 items-center gap-2">
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
                      {task.status !== "deleted" && ["asf", "orbit"].includes(archiveTaskKind(task)) && archiveTaskOutputDir(task) && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 px-2"
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
                          className="h-8 w-8 text-muted-foreground hover:text-destructive"
                          onClick={() => {
                            const key = archiveTaskKey(task);
                            setDownloadArchive((prev) => prev.filter((item) => archiveTaskKey(item) !== key));
                            setExpandedHistoryIds((prev) => {
                              const next = new Set(prev);
                              next.delete(task.id);
                              return next;
                            });
                          }}
                          title="删除历史记录"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                  {expandedHistoryIds.has(task.id) && (
                    <div className="mt-3 max-h-52 overflow-y-auto rounded-md border bg-muted/20 p-2 font-mono text-[11px] leading-5">
                      {(task.logs?.length ? task.logs : [task.detail]).map((line, i) => (
                        <div key={i} className="break-all">
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

  function renderSceneWorkspaceOverlay() {
    if (!sceneWorkspaceOpen || scenes.length === 0) return null;
    return (
      <div className="absolute inset-4 z-[760] flex min-h-0 flex-col overflow-hidden rounded-[26px] border border-white/65 bg-white/88 shadow-2xl backdrop-blur-2xl dark:border-white/10 dark:bg-zinc-950/88">
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-border/60 px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-base font-semibold">
              <Satellite className="h-4 w-4 text-primary" />
              Sentinel-1 影像下载工作台
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {selectedDownloadSceneIdList.length} / {scenes.length} 景加入下载；点击行只高亮地图边框，不改变地图视图。
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button size="sm" variant="outline" onClick={selectAllDownloadScenes}>
              全选
            </Button>
            <Button size="sm" variant="outline" onClick={clearDownloadSceneSelection}>
              清空
            </Button>
            {dlStatus?.state === "running" && (
              <Button size="sm" variant="outline" onClick={() => void pauseAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}>
                <Pause className="h-4 w-4" />
                暂停任务
              </Button>
            )}
            {dlStatus?.state === "paused" && (
              <Button size="sm" variant="outline" onClick={() => void resumeAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}>
                <Play className="h-4 w-4" />
                继续任务
              </Button>
            )}
            {dlActive && (
              <Button size="sm" variant="destructive" onClick={() => void stopAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}>
                <Square className="h-4 w-4" />
                结束任务
              </Button>
            )}
            <Button size="icon" variant="ghost" className="h-8 w-8 rounded-full" onClick={() => setSceneWorkspaceOpen(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="grid shrink-0 grid-cols-4 gap-2 border-b border-border/60 px-4 py-3 text-xs">
          {kv("候选影像", scenes.length)}
          {kv("加入下载", selectedDownloadSceneIdList.length)}
          {kv("任务状态", dlStatus ? statusLabel(dlStatus.state) : "未开始")}
          {kv("并发", dlStatus?.concurrency ?? asfConcurrency)}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <div className="space-y-2">
            {scenes.map((scene) => {
              const runtime = sceneRuntimeStatus(scene);
              return (
                <div
                  key={scene.scene_id}
                  className={cn(
                    "grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-2xl border bg-white/55 px-3 py-2 text-xs shadow-sm transition-colors hover:bg-white/80 dark:bg-white/5 dark:hover:bg-white/10",
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
                    {runtime.detail && <div className="mt-1 truncate text-[11px] text-muted-foreground">{runtime.detail}</div>}
                  </div>
                  <Badge variant={runtime.variant}>{runtime.label}</Badge>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  function renderSettingsPanel() {
    const earth = creds?.earthdata ?? "none";
    const dem = creds?.opentopography ?? "none";
    const gacos = creds?.gacos ?? "none";
    return (
      <div className="space-y-3">
        <Section
          title="账号与密钥"
          desc="凭据保存在系统凭据管理器，不写入项目目录。没有账号可直接打开注册网站。"
          icon={KeyRound}
        >
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <Badge variant={isConfigured(earth) ? "success" : "warning"}>ASF: {providerLabel(earth)}</Badge>
              <Badge variant={isConfigured(dem) ? "success" : "warning"}>DEM: {providerLabel(dem)}</Badge>
              <Badge variant={isConfigured(gacos) ? "success" : "warning"}>GACOS: {providerLabel(gacos)}</Badge>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refreshCredentials().then(() => refreshEarthdataAuth())}
            >
              <RotateCcw className="h-4 w-4" />
              刷新状态
            </Button>
            {earthdataAuth && earthdataAuth.configured && earthdataAuth.status !== "valid" && (
              <div className="rounded-2xl border border-warning/35 bg-warning/10 px-3 py-2 text-xs leading-5">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                  <div>
                    <div className="font-medium">Earthdata/ASF：{earthdataStatusLabel}</div>
                    <div className="text-muted-foreground">{earthdataAuth.message}</div>
                  </div>
                </div>
              </div>
            )}
            {earthdataAuth && !earthdataAuth.configured && (
              <div className="rounded-2xl border border-warning/35 bg-warning/10 px-3 py-2 text-xs leading-5">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                  <div>
                    <div className="font-medium">Earthdata/ASF 未配置</div>
                    <div className="text-muted-foreground">Sentinel-1 下载前需要先保存 Token 或账号密码。</div>
                  </div>
                </div>
              </div>
            )}
            <ErrorLine text={credError} />
            <NoteLine text={credNote} />
          </div>
        </Section>

        <Section title="Earthdata / ASF" desc="Sentinel-1 下载使用，优先建议 Token。" icon={Radar}>
          <div className="space-y-3">
            {isConfigured(earth) && (
              <div className="rounded-2xl border border-success/25 bg-success/10 px-3 py-2 text-xs leading-5">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  <div>
                    <div className="font-medium">
                      {earthdataAuth?.status === "valid" ? "设置完成，状态正常" : `已设置：${providerLabel(earth)}`}
                    </div>
                    <div className="text-muted-foreground">
                      {earthdataAuth?.status === "valid" ? "启动时已自动检测，无需重复确认。" : "可点“刷新状态”重新检测。"}
                    </div>
                  </div>
                </div>
              </div>
            )}
            <div className="grid grid-cols-2 gap-2 rounded-2xl border border-white/45 bg-white/35 p-1 text-sm dark:border-white/10 dark:bg-white/10">
              {(["token", "login"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setEarthCredentialMode(mode)}
                  className={cn(
                    "h-9 rounded-xl transition-colors",
                    earthCredentialMode === mode ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-white/60",
                  )}
                >
                  {mode === "token" ? "Token" : "账号密码"}
                </button>
              ))}
            </div>
            {earthCredentialMode === "token" ? (
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <Input
                  type="password"
                  value={earthToken}
                  onChange={(e) => setEarthToken(e.target.value)}
                  placeholder="Earthdata Token"
                />
                <Button
                  size="icon"
                  disabled={credBusy === "earth-token" || !earthToken.trim()}
                  onClick={() =>
                    void runCredentialAction(
                      "earth-token",
                      () => saveEarthdataToken(earthToken),
                      "Earthdata Token 已保存",
                    )
                  }
                >
                  {credBusy === "earth-token" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <Input value={earthUser} onChange={(e) => setEarthUser(e.target.value)} placeholder="用户名" />
                <Input
                  type="password"
                  value={earthPassword}
                  onChange={(e) => setEarthPassword(e.target.value)}
                  placeholder="密码"
                />
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {earthCredentialMode === "login" && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={credBusy === "earth-login" || !earthUser.trim() || !earthPassword}
                  onClick={() =>
                    void runCredentialAction(
                      "earth-login",
                      () => saveEarthdataLogin(earthUser, earthPassword),
                      "Earthdata 登录凭据已保存",
                    )
                  }
                >
                  <UserRound className="h-4 w-4" />
                  保存登录
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.earthdataToken)}>
                <ExternalLink className="h-4 w-4" />
                Token
              </Button>
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.earthdataRegister)}>
                <ExternalLink className="h-4 w-4" />
                注册
              </Button>
              <Button
                variant="ghost"
                size="sm"
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

        <Section title="OpenTopography" desc="DEM 下载需要 API Key。" icon={Database}>
          <div className="space-y-3">
            {isConfigured(dem) && (
              <div className="rounded-2xl border border-success/25 bg-success/10 px-3 py-2 text-xs leading-5">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  <div>
                    <div className="font-medium">OpenTopography 已设置</div>
                    <div className="text-muted-foreground">DEM 下载会自动使用已保存的 API Key。</div>
                  </div>
                </div>
              </div>
            )}
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <Input
                type="password"
                value={opentopoKey}
                onChange={(e) => setOpentopoKey(e.target.value)}
                placeholder="OpenTopography API Key"
              />
              <Button
                size="icon"
                disabled={credBusy === "dem-key" || !opentopoKey.trim()}
                onClick={() =>
                  void runCredentialAction(
                    "dem-key",
                    () => saveOpentopographyKey(opentopoKey),
                    "OpenTopography API Key 已保存",
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

        <Section title="GACOS" desc="请求结果会发送到接收邮箱。" icon={Mail}>
          <div className="space-y-3">
            {isConfigured(gacos) && (
              <div className="rounded-2xl border border-success/25 bg-success/10 px-3 py-2 text-xs leading-5">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  <div>
                    <div className="font-medium">GACOS 邮箱已设置</div>
                    <div className="text-muted-foreground">GACOS 请求会自动使用已保存邮箱。</div>
                  </div>
                </div>
              </div>
            )}
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

        {renderProjectContext()}

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
                <Input
                  type="password"
                  value={network.tianditu_token}
                  onChange={(e) => setNetwork({ ...network, tianditu_token: e.target.value })}
                  placeholder="天地图 Key（底图 / 行政边界）"
                />
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

  return (
    <div className="ios-window flex h-screen w-screen flex-col overflow-hidden text-foreground">
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

        {updateInfo && (
          <button
            type="button"
            onMouseDown={stopWindowDrag}
            onClick={() => void openUrl(updateInfo.html_url)}
            className="hidden h-8 shrink-0 items-center gap-1.5 rounded-full border border-primary/20 bg-primary/10 px-2.5 text-xs font-medium text-primary shadow-sm backdrop-blur-xl transition-colors hover:bg-primary/15 lg:flex"
            title={`发现新版 ${updateInfo.latest_version}`}
          >
            <CloudDownload className="h-3.5 w-3.5" />
            <span className="max-w-[120px] truncate">新版 {updateInfo.latest_version}</span>
            <ExternalLink className="h-3 w-3 opacity-70" />
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
                </button>
              );
            })}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-3" data-tour="resource-panel">
            {panel === "resources" && (
              <div className="space-y-3">
                {renderResourcePanel()}
              </div>
            )}
            {panel === "downloads" && renderDownloadCenter()}
            {panel === "settings" && renderSettingsPanel()}
          </div>
        </aside>

        <main className="relative min-w-0 flex-1" data-tour="map-canvas">
          <WorkbenchMap
            bbox={mapBbox}
            aoiBbox={ctx?.region?.bbox ?? null}
            aoiGeometry={mapAoiGeometry}
            sceneBbox={ctx?.region?.scene_footprint_bbox ?? null}
            scenes={scenes}
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
          {renderSceneWorkspaceOverlay()}
        </main>
      </div>
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
        autoStart={false}
      />
    </div>
  );
}
