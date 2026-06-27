import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  ChevronDown,
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
  Sun,
  Trash2,
  UserRound,
  Wifi,
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
import {
  addProject,
  addRegion,
  checkScenes,
  clearScenes,
  clearEarthdataCredentials,
  clearGacosEmail,
  clearOpentopographyKey,
  createWorkspace,
  ensureDirectory,
  formatBridgeError,
  getCredentialStatus,
  getDownloadStatus,
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
  openExternalUrl,
  pauseAsfDownload,
  pauseOrbitDownload,
  pickDirectory,
  pickOpenFile,
  planAsfDownload,
  planGacosRequest,
  resumeAsfDownload,
  resumeOrbitDownload,
  runDemDownload,
  runDemDownloadBbox,
  runLocalDemConversion,
  saveEarthdataLogin,
  saveEarthdataToken,
  saveGacosEmail,
  saveNetworkSettings,
  saveOpentopographyKey,
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
  type Bbox,
  type AdminBoundary,
  type CheckOk,
  type Context,
  type CredentialStatus,
  type DownloadStatus,
  type Json,
  type NetworkSettings,
  type MetadataStatus,
  type OrbitDownloadStatus,
  type OrbitMatchOk,
  type RunSummaryOk,
  type SceneRow,
  type SimpleOk,
  type Tree,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";
import { cn } from "@/lib/utils";

type SourceMode = "sentinel1" | "dem" | "orbit" | "gacos" | "sentinel2";
type PanelTab = "resources" | "downloads" | "settings";

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
const DEFAULT_ROOT = "C:\\InSAR\\projects";
const DEFAULT_BBOX: Bbox = {
  west: 110.22,
  east: 110.52,
  south: 30.92,
  north: 31.14,
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
  { key: "gacos", label: "GACOS", hint: "ZTD 请求", icon: Database },
  { key: "sentinel2", label: "Sentinel-2", hint: "预留", icon: Radar, disabled: true },
];

const PANEL_TABS: { key: PanelTab; label: string; icon: typeof CloudDownload }[] = [
  { key: "resources", label: "资源下载", icon: CloudDownload },
  { key: "downloads", label: "下载中心", icon: Activity },
  { key: "settings", label: "设置", icon: Settings },
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
}: {
  title: string;
  desc?: string;
  icon?: typeof Satellite;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="glass-panel overflow-visible">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
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
  onOpenPage,
}: {
  dark: boolean;
  onToggleDark: () => void;
  onOpenPage?: (key: "report" | "workspace" | "download" | "settings") => void;
}) {
  const { ctx, refresh } = usePrepContext();

  const [source, setSource] = useState<SourceMode>("sentinel1");
  const [panel, setPanel] = useState<PanelTab>("resources");
  const [layerKey, setLayerKey] = useState<MapLayerKey>("cartoLight");
  const [drawMode, setDrawMode] = useState<WorkbenchDrawMode>("rect");
  const [drawActive, setDrawActive] = useState(false);
  const [regionOpen, setRegionOpen] = useState(false);
  const [aoiToolsOpen, setAoiToolsOpen] = useState(false);

  const [tree, setTree] = useState<Tree | null>(null);
  const [root, setRoot] = useState(DEFAULT_ROOT);
  const [projectName, setProjectName] = useState("");
  const [regionName, setRegionName] = useState("");
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [projectNote, setProjectNote] = useState<string | null>(null);

  const [outputDir, setOutputDir] = useState("");
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
  const [adminProvince, setAdminProvince] = useState("湖北省");
  const [adminCity, setAdminCity] = useState("恩施土家族苗族自治州");
  const [adminDistrict, setAdminDistrict] = useState("全部");
  const [adminPickerOpen, setAdminPickerOpen] = useState<"province" | "city" | "district" | null>(null);
  const [adminOptions, setAdminOptions] = useState<{ provinces: string[]; cities: string[]; districts: string[] }>({
    provinces: [],
    cities: [],
    districts: [],
  });
  const [adminResults, setAdminResults] = useState<AdminBoundary[]>([]);
  const [adminBusy, setAdminBusy] = useState(false);
  const [aoiFile, setAoiFile] = useState("");
  const [aoiPreviewGeometry, setAoiPreviewGeometry] = useState<Json | null>(null);
  const [focusBbox, setFocusBbox] = useState<Bbox | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [hoveredSceneId, setHoveredSceneId] = useState<string | null>(null);

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
  const [demWest, setDemWest] = useState(String(DEFAULT_BBOX.west));
  const [demEast, setDemEast] = useState(String(DEFAULT_BBOX.east));
  const [demSouth, setDemSouth] = useState(String(DEFAULT_BBOX.south));
  const [demNorth, setDemNorth] = useState(String(DEFAULT_BBOX.north));
  const [demRun, setDemRun] = useState<RunSummaryOk | null>(null);
  const [demBusy, setDemBusy] = useState(false);
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
  const [opentopoKey, setOpentopoKey] = useState("");
  const [gacosEmail, setGacosEmail] = useState("");
  const [credBusy, setCredBusy] = useState<string | null>(null);
  const [credError, setCredError] = useState<string | null>(null);
  const [credNote, setCredNote] = useState<string | null>(null);
  const [network, setNetwork] = useState<NetworkSettings | null>(null);
  const [networkBusy, setNetworkBusy] = useState(false);
  const [networkError, setNetworkError] = useState<string | null>(null);
  const [networkNote, setNetworkNote] = useState<string | null>(null);
  const [downloadArchive, setDownloadArchive] = useState<
    { id: string; name: string; status: string; detail: string; ts: number }[]
  >([]);

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
    setCreds(await getCredentialStatus());
  }

  async function refreshNetwork() {
    setNetwork(await getNetworkSettings());
  }

  useEffect(() => {
    void refreshTree();
    void refreshScenes();
    void refreshCredentials();
    void refreshNetwork();
  }, []);

  useEffect(() => {
    void refreshScenes();
  }, [ctx?.region?.region_id, ctx?.region?.scene_count]);

  useEffect(() => {
    setAoiPreviewGeometry(null);
    setFocusBbox(null);
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
    const next = activeBbox(ctx);
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

  const resolvedOutputDir = useMemo(
    () => outputDir.trim() || ctx?.region?.root || ctx?.project?.root || ctx?.workspace?.root || "",
    [ctx?.project?.root, ctx?.region?.root, ctx?.workspace?.root, outputDir],
  );

  const mapBbox = focusBbox ?? activeBbox(ctx);
  const manualDemBbox: Bbox = {
    west: asNumber(demWest, DEFAULT_BBOX.west),
    east: asNumber(demEast, DEFAULT_BBOX.east),
    south: asNumber(demSouth, DEFAULT_BBOX.south),
    north: asNumber(demNorth, DEFAULT_BBOX.north),
    crs: "EPSG:4326",
  };
  const asfItems = (asfPlan?.items as Json[] | undefined) ?? [];
  const issues = (checkReport?.issues as Json[] | undefined) ?? [];
  const dlActive = dlStatus?.state === "running" || dlStatus?.state === "paused";
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
  const orbitPct =
    orbitStatus && orbitStatus.total > 0 ? Math.round((orbitStatus.done / orbitStatus.total) * 100) : 0;
  const terminalStates = new Set(["finished", "failed", "cancelled"]);
  const tiandituToken = network?.tianditu_token ?? "";
  const mapAoiGeometry = ctx?.region?.aoi_geojson ?? aoiPreviewGeometry;
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

  function rememberTask(item: { id: string; name: string; status: string; detail: string }) {
    setDownloadArchive((prev) => {
      const next = prev.filter((task) => task.id !== item.id);
      return [{ ...item, ts: Date.now() }, ...next].slice(0, 20);
    });
  }

  useEffect(() => {
    if (!dlStatus || !terminalStates.has(dlStatus.state)) return;
    const detail = dlStatus.error || dlStatus.summary_line || `${dlStatus.done}/${dlStatus.total}`;
    if (!detail) return;
    rememberTask({
      id: `asf:${dlStatus.results_path || detail}:${dlStatus.total}`,
      name: "ASF Sentinel-1 数据下载",
      status: dlStatus.state,
      detail,
    });
  }, [dlStatus?.done, dlStatus?.error, dlStatus?.results_path, dlStatus?.state, dlStatus?.summary_line, dlStatus?.total]);

  useEffect(() => {
    if (!orbitStatus || !terminalStates.has(orbitStatus.state)) return;
    const detail = orbitStatus.error || orbitStatus.summary_line || `${orbitStatus.done}/${orbitStatus.total}`;
    if (!detail) return;
    rememberTask({
      id: `orbit:${orbitStatus.orbit_dir || detail}:${orbitStatus.total}`,
      name: "Sentinel-1 精密轨道下载",
      status: orbitStatus.state,
      detail,
    });
  }, [orbitStatus?.done, orbitStatus?.error, orbitStatus?.orbit_dir, orbitStatus?.state, orbitStatus?.summary_line, orbitStatus?.total]);

  async function onBrowseRoot() {
    const pick = await pickDirectory("选择项目根目录");
    if (pick.ok && pick.path) setRoot(pick.path);
  }

  async function onBrowseOutput() {
    const pick = await pickDirectory("选择本次任务输出目录");
    if (pick.ok && pick.path) setOutputDir(pick.path);
    return pick.ok && pick.path ? pick.path : "";
  }

  async function ensureTaskOutput() {
    if (resolvedOutputDir) return resolvedOutputDir;
    const picked = await onBrowseOutput();
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
    if (!ctx?.region) {
      setAoiError("请先创建或选择研究区；没有 AOI 也可以直接下载 Sentinel-1。");
      return;
    }
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const res = await setRegionAoiBbox(bbox.west, bbox.east, bbox.south, bbox.north);
      if (res.ok) {
        setDrawActive(false);
        setAoiNote(`AOI 已绑定到 ${res.region_name}`);
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
    if (!ctx?.region) {
      setAoiError("请先创建或选择研究区。");
      return;
    }
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
        setAoiNote(`多边形 AOI 已绑定到 ${res.region_name}`);
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
    setFocusBbox(boundary.bbox);
    setAoiPreviewGeometry(boundary.geojson ?? null);
    if (!ctx?.region) {
      setAoiNote("已定位行政边界；创建或选择研究区后可绑定为 AOI。");
      return;
    }
    setAoiBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const res = boundary.geojson
        ? await setRegionAoiGeojson({ type: "Feature", properties: { name: boundary.label }, geometry: boundary.geojson })
        : await setRegionAoiBbox(boundary.bbox.west, boundary.bbox.east, boundary.bbox.south, boundary.bbox.north);
      if (res.ok) {
        setDrawActive(false);
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

  async function onSearchAdminBoundary(bindFirst = false) {
    setAdminBusy(true);
    setAoiError(null);
    setAoiNote(null);
    try {
      const res = await searchAdminBoundaries(
        adminQuery,
        adminProvince,
        adminCity,
        adminDistrict,
        8,
      );
      if (!res.ok) {
        setAoiError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
        return;
      }
      setAdminResults(res.results);
      if (!res.results.length) {
        setAoiError("没有找到可用边界；可以换关键词，或上传 shp/kml/geojson。");
        return;
      }
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
      const res = await searchAsfScenes({
        bbox,
        use_current_aoi: true,
        start: asfSearchStart,
        end: asfSearchEnd,
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
        setSelectedSceneId(null);
        await refresh();
        await refreshTree();
        setMetadataStatus(await getMetadataStatus());
        setAsfSearchNote(`ASF 检索导入 ${res.scenes.length} 景；元数据已补全 path/frame/升降轨/范围。`);
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
      setHoveredSceneId(null);
      setCheckReport(null);
      setAsfPlan(null);
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

  async function onAsfPrecheck() {
    setAsfBusy(true);
    setAsfError(null);
    try {
      const res = await planAsfDownload(resolvedOutputDir);
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
      const out = await ensureTaskOutput();
      if (!out) {
        setAsfError("开始下载前需要确认一个输出目录。");
        return;
      }
      const res = await startAsfDownload(out, "auto", Number(asfConcurrency) || 1);
      if (res.ok) setDlStatus(await getDownloadStatus());
      else setAsfError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      setPanel("downloads");
    } catch (e) {
      setAsfError(formatBridgeError(e));
    } finally {
      setAsfStartBusy(false);
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
      setPanel("downloads");
    } catch (e) {
      setOrbitError(formatBridgeError(e));
    } finally {
      setOrbitStartBusy(false);
    }
  }

  async function onRunDemDownload() {
    setDemBusy(true);
    setDemError(null);
    try {
      const out = await ensureTaskOutput();
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
      if (res.ok) setDemRun(res);
      else setDemError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      setPanel("downloads");
    } catch (e) {
      setDemError(formatBridgeError(e));
    } finally {
      setDemBusy(false);
    }
  }

  async function onBrowseLocalDem() {
    const pick = await pickOpenFile("选择本地 DEM", [
      "DEM (*.tif;*.tiff;*.img;*.vrt)",
      "All files (*.*)",
    ]);
    if (pick.ok && pick.path) setLocalDem(pick.path);
  }

  async function onRunLocalDem() {
    setDemBusy(true);
    setDemError(null);
    try {
      const out = await ensureTaskOutput();
      if (!out) {
        setDemError("转换本地 DEM 前需要确认一个输出目录。");
        return;
      }
      const res = await runLocalDemConversion(localDem, out, localDatum);
      if (res.ok) setDemRun(res);
      else setDemError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      setPanel("downloads");
    } catch (e) {
      setDemError(formatBridgeError(e));
    } finally {
      setDemBusy(false);
    }
  }

  async function onGacosPlan() {
    setGacosBusy(true);
    setGacosError(null);
    try {
      const out = await ensureTaskOutput();
      if (!out) {
        setGacosError("生成 GACOS 请求前需要确认一个输出目录。");
        return;
      }
      const res = await planGacosRequest(out);
      if (res.ok) setGacosPlan(res.plan);
      else setGacosError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      setPanel("downloads");
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

  async function onBrowseCacheDir() {
    const pick = await pickDirectory("选择缓存目录");
    if (pick.ok && pick.path && network) setNetwork({ ...network, cache_dir: pick.path });
  }

  async function onSaveNetwork() {
    if (!network) return;
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
      });
      if (res.ok) {
        setNetwork(res);
        setNetworkNote("网络代理、缓存与图源 Token 已保存。");
      } else {
        setNetworkError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setNetworkError(formatBridgeError(e));
    } finally {
      setNetworkBusy(false);
    }
  }

function renderOutputParameters(desc = "任务开始前确认输出根目录；留空时使用当前项目或研究区目录。") {
    return (
      <div className="space-y-2 rounded-2xl border border-white/45 bg-white/40 p-2.5 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
        <div className="flex items-center gap-2 text-xs font-medium">
          <HardDrive className="h-3.5 w-3.5 text-primary" />
          输出参数
        </div>
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Input
            value={outputDir}
            onChange={(e) => setOutputDir(e.target.value)}
            placeholder={resolvedOutputDir || "开始任务时选择输出目录"}
            className="font-mono text-xs"
            spellCheck={false}
          />
          <Button variant="outline" size="icon" onClick={onBrowseOutput} title="浏览输出目录">
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
        title="项目与任务"
        desc="根目录可浏览或新建；项目名称和研究区名称可留空，系统会自动命名。"
        icon={HardDrive}
      >
        <div className="space-y-3">
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Input
              value={root}
              onChange={(e) => setRoot(e.target.value)}
              placeholder="C:\\InSAR\\projects"
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
            创建 / 切到这个任务
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
        desc="地名 / 行政区划 / 上传边界 / 手动四至；AOI 与 ASF 检索和 DEM 范围共享。"
        icon={MapPinned}
      >
        <div className="space-y-3">
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Input
              value={adminQuery}
              onChange={(e) => setAdminQuery(e.target.value)}
              placeholder="搜索地名（省 / 市 / 区 / POI）..."
              spellCheck={false}
            />
            <Button size="icon" onClick={() => void onSearchAdminBoundary(false)} disabled={adminBusy}>
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
              onClick={() => void onSearchAdminBoundary(true)}
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
                setFocusBbox(null);
                setAoiPreviewGeometry(null);
              }}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
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
                    setFocusBbox(item.bbox);
                    void bindAdminBoundary(item);
                  }}
                  className="block w-full rounded-xl px-2 py-2 text-left transition-colors hover:bg-white/60 dark:hover:bg-white/10"
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

          <div className="flex items-center justify-between gap-2 pt-1">
            <div className="text-xs font-medium">手动四至（WGS-84）</div>
            <Badge variant="neutral">选区面积 {roughBboxAreaKm2(manualDemBbox)} km²</Badge>
          </div>
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
            disabled={!ctx?.region || aoiBusy}
          >
            {aoiBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPinned className="h-4 w-4" />}
            绑定为 AOI
          </Button>
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
        title="ASF 元数据检索"
        desc="按当前 AOI、日期、产品类型和轨道条件查询；没有 AOI 也可检索。"
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
            <Input type="date" value={asfSearchStart} onChange={(e) => setAsfSearchStart(e.target.value)} />
            <Input type="date" value={asfSearchEnd} onChange={(e) => setAsfSearchEnd(e.target.value)} />
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
            {kv("结果", "导入后会自动刷新地图覆盖范围")}
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
          <div className="rounded-2xl border border-white/45 bg-white/35 p-3 text-xs shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
            {kv("当前场景", scenes.length ? `${scenes.length} 景` : "未导入")}
            {kv("元数据", scenes.some((scene) => scene.footprint_bbox) ? "已含 SAR 范围" : "导入后会尝试补全")}
          </div>
          <ErrorLine text={sceneError} />
          <NoteLine text={sceneNote} />
        </div>
      </Section>
    );
  }

  function renderSentinel1Panel() {
    return (
      <div className="space-y-3">
        {renderAsfSearchSection()}
        <Section
          title="影像导入与核查"
          desc="下载任务建议使用 ASF 检索或 ASF 官方 py、metadata、metalink、CSV、GeoJSON。已有本地 SLC/GRD 目录请在 Orbit/GACOS 中用于解析日期和轨道。"
          icon={Satellite}
        >
          <div className="space-y-3">
            <Textarea
              value={sceneText}
              onChange={(e) => setSceneText(e.target.value)}
              placeholder={"粘贴 ASF 场景名、URL 或购物车内容\nS1A_IW_SLC__1SDV_..."}
              className="min-h-[82px] font-mono text-xs"
              spellCheck={false}
            />
            <div className="grid grid-cols-2 gap-2">
              <Button
                onClick={() => void handleSceneImport(() => importScenesText(sceneText))}
                disabled={sceneBusy || !sceneText.trim()}
              >
                {sceneBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardPaste className="h-4 w-4" />}
                粘贴导入
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
            {scenes.length > 0 && (
              <div className="relative rounded-md border bg-muted/30" onMouseLeave={() => setHoveredSceneId(null)}>
                <div className="flex items-center justify-between border-b px-3 py-2 text-xs">
                  <span className="font-medium">{scenes.length} 景已导入 · 点击场景定位边框</span>
                  <Button size="sm" variant="outline" onClick={onRunCheck} disabled={checkBusy}>
                    {checkBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                    核查
                  </Button>
                </div>
                <div className="max-h-44 overflow-y-auto">
                  {scenes.slice(0, 8).map((scene) => (
                    <button
                      key={scene.scene_id}
                      type="button"
                      onClick={() => {
                        setSelectedSceneId(scene.scene_id);
                        if (scene.footprint_bbox) setFocusBbox(scene.footprint_bbox);
                      }}
                      className={cn(
                        "block w-full border-b px-3 py-2 text-left text-xs transition-colors last:border-0 hover:bg-white/45 dark:hover:bg-white/10",
                        selectedSceneId === scene.scene_id && "bg-primary/10",
                      )}
                    >
                      <div className="flex items-center gap-2">
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
                      </div>
                    </button>
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
        <Section
          title="Sentinel-1 下载"
          desc="开始下载时才确认输出目录；支持暂停、继续、结束和 .part 断点续传。"
          icon={CloudDownload}
        >
          <div className="space-y-3">
            {renderOutputParameters("下载前确认输出根目录；同一目录再次开始可利用 .part 断点续传。")}
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
              <Button onClick={onStartAsf} disabled={asfStartBusy || dlActive || scenes.length === 0}>
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

  function renderDemPanel() {
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
            {renderOutputParameters("保存原始 GeoTIFF、椭球高 GeoTIFF 和 SARscape *_dem.tif。")}
            <Button onClick={onRunDemDownload} disabled={demBusy} className="w-full">
              {demBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
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
            {renderOutputParameters("本地 DEM 转换输出到椭球高目录和 SARscape 就绪目录。")}
            <Button variant="outline" onClick={onRunLocalDem} disabled={demBusy || !localDem} className="w-full">
              {demBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              转换为 SARscape DEM
            </Button>
          </div>
        </Section>
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
            <Button onClick={onGacosPlan} disabled={gacosBusy || scenes.length === 0} className="w-full">
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
        <Section title="凭据提醒" desc="GACOS 需要接收邮箱；可在设置中保存。" icon={Mail}>
          <Button variant="outline" onClick={() => setPanel("settings")} className="w-full">
            <Settings className="h-4 w-4" />
            打开设置
          </Button>
        </Section>
      </div>
    );
  }

  function renderResourceScopeBar() {
    const currentSource = SOURCE_TABS.find((item) => item.key === source);
    return (
      <section className="glass-panel px-3 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={ctx?.region?.has_aoi ? "success" : "neutral"}>
                {ctx?.region?.has_aoi ? "AOI 已绑定" : "AOI 可选"}
              </Badge>
              <span className="truncate text-sm font-semibold">{currentSource?.label ?? "资源下载"}</span>
            </div>
            <div className="mt-1 truncate text-xs text-muted-foreground">
              {ctx?.project?.name ?? "未选择项目"} / {ctx?.region?.name ?? "未选择研究区"} · 默认沿用上次选择的范围
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
      dlStatus && dlActive
        ? {
            id: "asf-active",
            name: "ASF Sentinel-1 数据下载",
            status: dlStatus.state,
            progress: dlPct,
            count: `${dlStatus.done}/${dlStatus.total}`,
            detail: dlStatus.current_scene || dlStatus.summary_line || "等待下一个场景",
            metrics: [
              ["已下载", dlStatus.total_bytes ? `${fmtBytes(transferredBytes)} / ${fmtBytes(dlStatus.total_bytes)}` : fmtBytes(transferredBytes)],
              ["速度", fmtRate(dlStatus.bytes_per_second)],
              ["并发", dlStatus.concurrency ?? 1],
              ["断点续传", dlStatus.resume_supported ? "支持 .part" : "未知"],
            ],
            controls: (
              <div className="grid grid-cols-3 gap-2">
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
                  onClick={() => void stopAsfDownload().then(() => getDownloadStatus().then(setDlStatus))}
                >
                  <Square className="h-4 w-4" />
                  结束
                </Button>
              </div>
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
            detail: orbitStatus.current_scene || orbitStatus.summary_line || "等待下一个 EOF",
            metrics: [
              ["成功", orbitStatus.succeeded],
              ["跳过", orbitStatus.skipped],
              ["未发布/不可用", orbitStatus.unavailable],
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
      log: string[];
    }[];

    return (
      <div className="space-y-3">
        <Section title="任务队列" desc="进行中和暂停任务保留在这里，可暂停、继续或结束。" icon={Activity}>
          <div className="space-y-3">
            {activeTasks.length === 0 ? (
              <div className="rounded-md border border-dashed py-8 text-center text-xs text-muted-foreground">
                暂无进行中任务；开始下载后会固定显示在这里。
              </div>
            ) : (
              activeTasks.map((task) => (
                <div key={task.id} className="rounded-lg border bg-card p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold">{task.name}</div>
                      <div className="truncate text-xs text-muted-foreground">{task.detail}</div>
                    </div>
                    <div className="shrink-0 text-right">
                      <Badge variant={task.status === "paused" ? "warning" : "success"}>
                        {statusLabel(task.status)}
                      </Badge>
                      <div className="mt-1 font-mono text-[11px] text-muted-foreground">{task.count}</div>
                    </div>
                  </div>
                  <Progress value={task.progress} className="mt-3" />
                  {task.id === "asf-active" && dlStatus?.current_scene && <Progress value={currentPct} className="mt-1 h-1.5" />}
                  <div className="mt-3 space-y-1">
                    {task.metrics.map(([label, value]) => kv(label, value))}
                  </div>
                  <div className="mt-3">{task.controls}</div>
                  {task.log.length > 0 && (
                    <div className="mt-3 max-h-28 overflow-y-auto rounded-md border bg-muted/20 p-2 font-mono text-[11px]">
                      {task.log.slice(-8).map((line, i) => (
                        <div key={i} className="truncate">
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

        <Section title="历史记录" desc="完成、失败、结束和已删除的任务会归档到这里。" icon={Database}>
          <div className="space-y-2">
            {downloadArchive.length === 0 ? (
              <div className="rounded-md border border-dashed py-8 text-center text-xs text-muted-foreground">
                暂无历史任务。
              </div>
            ) : (
              downloadArchive.map((task) => (
                <div key={task.id} className="flex items-start justify-between gap-3 rounded-lg border bg-card p-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold">{task.name}</div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">{task.detail}</div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      {new Date(task.ts).toLocaleString()}
                    </div>
                  </div>
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
                    {task.status !== "deleted" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={() =>
                          setDownloadArchive((prev) =>
                            prev.map((item) =>
                              item.id === task.id ? { ...item, status: "deleted", detail: "用户已从历史记录删除" } : item,
                            ),
                          )
                        }
                        title="删除历史记录"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </Section>

        <Section title="DEM / GACOS 结果" icon={Database}>
          <div className="space-y-3 text-xs">
            {demRun ? (
              <div className="rounded-md border bg-muted/30 p-3">
                {kv("DEM 结果", demRun.summary_line)}
                {kv("原始 tif", demRun.raw_dem_path || "-")}
                {kv("椭球高 tif", demRun.ellipsoid_dem_path || "-")}
                {kv("SARscape DEM", demRun.sarscape_ready_dem_path || "-")}
              </div>
            ) : (
              <div className="rounded-md border border-dashed py-6 text-center text-muted-foreground">
                暂无 DEM 执行结果
              </div>
            )}
            {gacosPlan && (
              <div className="rounded-md border bg-muted/30 p-3">
                {kv("GACOS 日期数", String((gacosPlan.unique_dates as string[] | undefined)?.length ?? 0))}
                {kv("输出目录", resolvedOutputDir || "-")}
              </div>
            )}
          </div>
        </Section>
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
            <Button variant="outline" size="sm" onClick={() => void refreshCredentials()}>
              <RotateCcw className="h-4 w-4" />
              刷新状态
            </Button>
            <ErrorLine text={credError} />
            <NoteLine text={credNote} />
          </div>
        </Section>

        <Section title="Earthdata / ASF" desc="Sentinel-1 下载使用，优先建议 Token。" icon={Radar}>
          <div className="space-y-3">
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
            <div className="grid grid-cols-2 gap-2">
              <Input value={earthUser} onChange={(e) => setEarthUser(e.target.value)} placeholder="用户名" />
              <Input
                type="password"
                value={earthPassword}
                onChange={(e) => setEarthPassword(e.target.value)}
                placeholder="密码"
              />
            </div>
            <div className="flex flex-wrap gap-2">
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
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.opentopoKey)}>
                <ExternalLink className="h-4 w-4" />
                获取 Key
              </Button>
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.opentopoRegister)}>
                <ExternalLink className="h-4 w-4" />
                注册
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
              <Input
                value={network.proxy_url}
                onChange={(e) => setNetwork({ ...network, proxy_url: e.target.value })}
                placeholder="http://127.0.0.1:10808"
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
                  onChange={(e) => setNetwork({ ...network, cache_enabled: e.target.checked })}
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
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      <header className="z-[520] flex h-16 shrink-0 items-center gap-2 border-b border-white/55 bg-white/62 px-3 shadow-[0_10px_30px_rgba(15,23,42,0.08)] backdrop-blur-2xl dark:border-white/10 dark:bg-[#111827]/68">
        <div className="flex min-w-[170px] max-w-[210px] items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-foreground text-background shadow-sm">
            <Radar className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">InSAR Assistant</div>
            <div className="hidden truncate text-[11px] text-muted-foreground xl:block">地图优先的数据准备工作台</div>
          </div>
        </div>

        <div className="shrink-0">
          <button
            type="button"
            onClick={() => {
              setRegionOpen((value) => !value);
              setPanel("resources");
            }}
            className={cn(
              "flex h-10 w-[230px] max-w-[24vw] items-center justify-between gap-2 overflow-hidden rounded-2xl border border-white/60 bg-white/50 px-3 text-left text-sm shadow-sm backdrop-blur-xl transition-colors hover:bg-white/70 dark:border-white/10 dark:bg-white/10 dark:hover:bg-white/15",
              regionOpen && "ring-2 ring-ring",
            )}
          >
            <span className="flex min-w-0 items-center gap-2">
              <HardDrive className="h-4 w-4 shrink-0 text-primary" />
              <span className="min-w-0">
                <span className="block truncate font-medium">{ctx?.project?.name ?? "项目 / 任务"}</span>
                <span className="block truncate text-[11px] text-muted-foreground">
                  {ctx?.region?.name ?? "未选择研究区"} · {ctx?.workspace?.root ?? "选择或新建工作目录"}
                </span>
              </span>
            </span>
            <ChevronDown className={cn("h-4 w-4 shrink-0 transition-transform", regionOpen && "rotate-180")} />
          </button>
        </div>

        <nav className="flex h-11 min-w-0 flex-1 items-center justify-start overflow-x-auto">
          <div className="flex items-center gap-1 rounded-2xl border border-white/55 bg-white/42 p-1 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/10">
          {SOURCE_TABS.map((item) => {
            const Icon = item.icon;
            const active = source === item.key;
            return (
              <button
                key={item.key}
                type="button"
                disabled={item.disabled}
                onClick={() => {
                  setSource(item.key);
                  setPanel("resources");
                }}
                className={cn(
                  "flex h-9 min-w-[86px] items-center justify-center gap-1.5 rounded-xl px-2.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                  active ? "bg-white/82 text-foreground shadow-sm dark:bg-white/18" : "text-muted-foreground hover:bg-white/55 hover:text-foreground dark:hover:bg-white/12",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate font-medium">{item.label}</span>
              </button>
            );
          })}
          </div>
        </nav>

        <div className="hidden max-w-[320px] items-center gap-1.5 xl:flex">
          <Badge variant={ctx?.region ? "success" : "warning"}>
            {ctx?.region ? ctx.region.name : "未选择研究区"}
          </Badge>
          <Badge variant={scenes.length ? "success" : "neutral"}>{scenes.length} 景</Badge>
          <Badge variant={ctx?.region?.has_aoi ? "success" : "neutral"}>
            {ctx?.region?.has_aoi ? "AOI 已设" : "AOI 可选"}
          </Badge>
        </div>

        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onToggleDark} title="切换主题">
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onOpenPage?.("report")} title="报告">
          <FileText className="h-4 w-4" />
        </Button>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="flex h-full w-[430px] shrink-0 flex-col border-r border-white/55 bg-white/35 backdrop-blur-2xl dark:border-white/10 dark:bg-[#0f172a]/35">
          <div className="grid grid-cols-3 border-b border-white/50 bg-white/45 backdrop-blur-xl dark:border-white/10 dark:bg-white/5">
            {PANEL_TABS.map((item) => {
              const Icon = item.icon;
              const active = panel === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setPanel(item.key)}
                  className={cn(
                    "relative flex h-10 items-center justify-center gap-1.5 text-sm transition-colors",
                    active
                      ? "text-foreground after:absolute after:bottom-0 after:left-0 after:h-0.5 after:w-full after:bg-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {item.label}
                </button>
              );
            })}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {panel === "resources" && (
              <div className="space-y-3">
                {regionOpen && (
                  <>
                    {renderProjectContext()}
                  </>
                )}
                {renderResourcePanel()}
              </div>
            )}
            {panel === "downloads" && renderDownloadCenter()}
            {panel === "settings" && renderSettingsPanel()}
          </div>
        </aside>

        <main className="relative min-w-0 flex-1">
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
            drawActive={drawActive && !!ctx?.region && !aoiBusy}
            onLayerChange={setLayerKey}
            onDrawModeChange={setDrawMode}
            onDrawActiveChange={setDrawActive}
            onRectDraw={(bbox) => void bindBbox(bbox)}
            onPolygonDraw={(ring) => void bindPolygon(ring)}
            onPointDraw={bindPoint}
          />
        </main>
      </div>
    </div>
  );
}
