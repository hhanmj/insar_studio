// Thin wrapper around the pywebview JS<->Python bridge.
//
// In the packaged desktop app the Python side exposes an `Api` object as
// `window.pywebview.api.*` (every method returns a Promise). When the frontend
// runs in a plain browser (vite dev, or the headless screenshot), pywebview is
// absent, so we fall back to mock data so the UI is always previewable. The mock
// keeps a tiny shared "current region" context so the panels feel connected.

import { ADMIN_BOUNDARY_INDEX, type AdminBoundaryLite } from "@/data/adminBoundaries";

type AdminBoundaryIndex = {
  provinces: readonly AdminBoundaryLite[];
  citiesByProvince: Record<string, readonly AdminBoundaryLite[]>;
  districtsByCity: Record<string, readonly AdminBoundaryLite[]>;
};

const ADMIN_INDEX = ADMIN_BOUNDARY_INDEX as unknown as AdminBoundaryIndex;

export type AppInfo = { name: string; version: string; offline: boolean };
export type UpdateInfo = {
  ok: true;
  checked: boolean;
  update_available: boolean;
  current_version: string;
  latest_version: string;
  html_url: string;
  download_url?: string;
  asset_name?: string;
  asset_size?: number;
  online_update_supported?: boolean;
  install_mode?: "manual" | "download" | "installer" | string;
  message?: string;
};
export type ApiError = { ok: false; error: string; code: string | null };
export type Json = Record<string, unknown>;
export type AppUpdateDownloadOk = {
  ok: true;
  path: string;
  folder: string;
  size: number;
  can_run: boolean;
  launched?: boolean;
  install_mode?: "download" | "installer" | string;
  message?: string;
};
export type ComponentSummary = {
  id: string;
  name: string;
  version: string;
  size_mb?: number | null;
  url?: string;
  sha256?: string;
  entry?: string;
  description?: string;
  installed: boolean;
  installed_version?: string;
  installed_path?: string;
  runtime_available: boolean;
  state: "installed" | "bundled" | "available" | "not_configured" | string;
  can_install: boolean;
};
export type ComponentStatusOk = {
  ok: true;
  root: string;
  manifest_url: string;
  manifest_checked_at?: number | null;
  components: ComponentSummary[];
};

export type ProjectOk = {
  ok: true;
  project_id: string;
  name: string;
  safe_name: string;
};
export type RegionOk = {
  ok: true;
  region_id: string;
  name: string;
  safe_name: string;
};
export type WorkspaceOk = {
  ok: true;
  workspace_id: string;
  root: string;
  projects: ProjectOk[];
};

export type Bbox = {
  west: number;
  east: number;
  south: number;
  north: number;
  crs?: string;
};

export type ContextRegion = {
  region_id: string;
  name: string;
  safe_name: string;
  root?: string;
  has_aoi: boolean;
  bbox: Bbox | null;
  aoi_geojson?: Json | null;
  scene_footprint_bbox?: Bbox | null;
  scene_count: number;
};
export type Context = {
  ok: true;
  workspace: { workspace_id: string; root: string; name: string } | null;
  project: { project_id: string; name: string; safe_name: string; root?: string } | null;
  region: ContextRegion | null;
  dem_dataset?: string;
};

export type ConversionAuto = {
  requires_conversion: boolean;
  requires_geoid: boolean;
  source: string;
  target: string;
  geoid_model: string | null;
  message: string;
};

export type SceneRow = {
  scene_id: string;
  platform: string;
  product_type: string;
  beam_mode: string;
  polarization: string;
  acquisition_datetime: string;
  absolute_orbit: number | null;
  relative_orbit: number | null;
  path: number | null;
  frame: number | null;
  orbit_direction: string;
  file_size_remote?: number | null;
  footprint_bbox?: Bbox | null;
  footprint_geojson?: Json | null;
  has_url: boolean;
};

export type TreeRegion = {
  region_id: string;
  name: string;
  safe_name: string;
  root?: string;
  has_aoi: boolean;
  scene_count: number;
};
export type TreeProject = {
  project_id: string;
  name: string;
  safe_name: string;
  root?: string;
  regions: TreeRegion[];
};
export type Tree = {
  ok: true;
  workspace: { workspace_id: string; root: string; name: string } | null;
  projects: TreeProject[];
  current_project_id: string | null;
  current_region_id: string | null;
};
export type PickResult = { ok: boolean; path: string };
export type ActivityEntry = { ts: string; text: string; kind: string };
export type ActivityFeed = { ok: true; activities: ActivityEntry[] };
export type DownloadArchiveItem = {
  id: string;
  name: string;
  status: string;
  detail: string;
  ts: number;
  kind?: "asf" | "orbit" | "dem" | "gacos" | string;
  output_dir?: string;
  total?: number;
  concurrency?: number;
  logs?: string[];
};
export type DownloadArchiveResult = { ok: true; items: DownloadArchiveItem[] };
export type DownloadStatus = {
  ok: true;
  state: string;
  total: number;
  done: number;
  concurrency?: number;
  current_scene: string;
  active_downloads?: {
    scene_id: string;
    bytes: number;
    expected_size?: number | null;
    started_at?: number;
    updated_at?: number;
  }[];
  total_bytes?: number | null;
  done_bytes?: number;
  current_bytes?: number;
  current_expected_size?: number | null;
  bytes_per_second?: number;
  elapsed_seconds?: number;
  paused: boolean;
  cancelled: boolean;
  error: string | null;
  summary_line: string;
  results_path: string;
  output_dir?: string;
  succeeded?: number;
  skipped?: number;
  failed?: number;
  interrupted?: number;
  has_failures?: boolean;
  paused_scene_ids?: string[];
  resume_supported?: boolean;
  resume_hint?: string;
  retry_supported?: boolean;
  retry_hint?: string;
  log: { scene_id: string; outcome: string; bytes_written: number; message?: string; detail: string; ts?: number }[];
};
export type WorkflowStage = {
  id: string;
  label: string;
  nav: string;
  status: "done" | "active" | "blocked" | "running" | string;
  summary: string;
  ready: boolean;
  count: number;
};
export type WorkflowSource = {
  id: string;
  label: string;
  credential: string | null | undefined;
  status: "configured" | "needs_config" | "ready" | "waiting" | string;
  capabilities: string[];
};
export type WorkflowStatus = {
  ok: true;
  context: Context;
  stages: WorkflowStage[];
  sources: WorkflowSource[];
  download: DownloadStatus;
  next_action: { label: string; nav: string };
  counts: { projects: number; regions: number; scenes: number };
  scene_coverage?: { bbox: Bbox | null; count: number };
  dem_dataset: string;
};

export type AoiOk = {
  ok: true;
  aoi: Json;
  aoi_geojson?: Json | null;
  aoi_feature_count?: number | null;
  aoi_total_feature_count?: number | null;
  download_mode?: "merge" | "split" | string;
  region_id: string;
  region_name: string;
};
export type AoiFeaturePreview = {
  id: string;
  index: number;
  source_index?: number;
  name: string;
  area_km2?: number | null;
  bbox?: Bbox | null;
  properties: Json;
};
export type AoiPreviewOk = {
  ok: true;
  path: string;
  file_name: string;
  total_features: number;
  fields: string[];
  display_field?: string;
  features: AoiFeaturePreview[];
};
export type AoiPreviewResult = AoiPreviewOk | ApiError;
export type AdminBoundary = {
  label: string;
  bbox: Bbox;
  geojson?: Json | null;
  source?: string;
  class?: string | null;
  type?: string | null;
  osm_type?: string | null;
  osm_id?: string | number | null;
};
export type AdminBoundaryOk = {
  ok: true;
  query: string;
  results: AdminBoundary[];
  provider?: string;
  warning?: string | null;
};
export type AdminOptionsOk = {
  ok: true;
  provinces: string[];
  cities: string[];
  districts: string[];
};
export type ScenesOk = {
  ok: true;
  scenes: SceneRow[];
  duplicates: string[];
  errors: { line: string; error: string }[];
  queried?: number;
  search?: {
    requested_limit?: number | null;
    query_limit?: number | null;
    total_count?: number | null;
    returned_count?: number | null;
    source?: string | null;
  };
};
export type CheckOk = { ok: true; report: Json };
export type PlanOk = { ok: true; plan: Json };
export type PlanReportOk = { ok: true; plan: Json; report: Json };
export type ConvertOk = {
  ok: true;
  dataset: string;
  auto: ConversionAuto;
  plan: Json;
  report: Json;
};
export type RunSummaryOk = {
  ok: true;
  summary_line: string;
  total: number;
  succeeded?: number;
  copied?: number;
  skipped?: number;
  failed?: number;
  interrupted?: number;
  has_failures: boolean;
  results_path: string;
  output_dir?: string;
  results: Json[];
  download?: Json;
  conversion?: Json | null;
  conversion_results_path?: string;
  raw_dem_path?: string;
  ellipsoid_dem_path?: string;
  sarscape_ready_dem_path?: string;
};
export type OrbitDownloadOk = {
  ok: true;
  orbit_dir: string;
  summary_line: string;
  total: number;
  succeeded: number;
  skipped: number;
  unavailable: number;
  failed: number;
  has_failures: boolean;
  results: Json[];
  report: Json;
};
export type OrbitDownloadStatus = {
  ok: true;
  state: string;
  total: number;
  done: number;
  current_scene: string;
  orbit_dir: string;
  elapsed_seconds?: number;
  paused: boolean;
  cancelled: boolean;
  error: string | null;
  summary_line: string;
  succeeded: number;
  skipped: number;
  unavailable: number;
  failed: number;
  has_failures: boolean;
  results: Json[];
  log: { scene_id: string; outcome: string; detail: string; ts?: number }[];
  report?: Json | null;
  pause_hint?: string;
};
export type OrbitMatchOk = {
  ok: true;
  orbit_dir: string;
  orbit_files: number;
  report: Json;
};
export type ReportOk = {
  ok: true;
  report: Json;
  reports_dir: string;
  included: string[];
  paths: Record<string, string>;
};
export type CredentialStatus = {
  ok: true;
  earthdata: string;
  opentopography: string;
  gacos: string;
};
export type EarthdataAuthCheck = {
  ok: true;
  configured: boolean;
  status: "missing" | "valid" | "expired" | "invalid" | "unknown" | "unavailable";
  message: string;
};
export type NetworkSettings = {
  ok: true;
  proxy_enabled: boolean;
  proxy_url: string;
  cache_enabled: boolean;
  cache_dir: string;
  cache_limit_mb: number;
  tianditu_token: string;
  asf_ssl_verify: boolean;
};
export type NetworkSettingsInput = Omit<NetworkSettings, "ok">;
export type AsfSearchParams = {
  bbox?: Bbox | null;
  aoi_geojson?: Json | null;
  use_current_aoi?: boolean;
  start?: string;
  end?: string;
  product_type?: string;
  beam_mode?: string;
  polarization?: string;
  orbit_direction?: string;
  relative_orbit?: string | number | null;
  frame?: string | number | null;
  max_results?: string | number | null;
};
export type SimpleOk = { ok: true; [key: string]: unknown } | ApiError;
export type NativeWindowSize = {
  ok: true;
  width: number;
  height: number;
  x?: number;
  y?: number;
} | ApiError;
export type MetadataStatus = {
  ok: true;
  state: string;
  done: number;
  total: number;
  percent: number;
  message: string;
};

export type WorkspaceResult = WorkspaceOk | ApiError;
export type ProjectResult = ProjectOk | ApiError;
export type RegionResult = RegionOk | ApiError;
export type AoiResult = AoiOk | ApiError;
export type AdminBoundaryResult = AdminBoundaryOk | ApiError;
export type AdminOptionsResult = AdminOptionsOk | ApiError;
export type ScenesResult = ScenesOk | ApiError;
export type CheckResult = CheckOk | ApiError;
export type PlanResult = PlanOk | ApiError;
export type PlanReportResult = PlanReportOk | ApiError;
export type ConvertResult = ConvertOk | ApiError;
export type RunSummaryResult = RunSummaryOk | ApiError;
export type OrbitDownloadResult = OrbitDownloadOk | ApiError;
export type OrbitMatchResult = OrbitMatchOk | ApiError;
export type ReportResult = ReportOk | ApiError;

type PyApi = {
  get_app_info: () => Promise<AppInfo>;
  check_for_update?: (force?: boolean) => Promise<UpdateInfo | ApiError>;
  download_app_update?: (downloadUrl?: string, assetName?: string) => Promise<AppUpdateDownloadOk | ApiError>;
  get_component_status?: (refresh?: boolean) => Promise<ComponentStatusOk | ApiError>;
  install_component?: (componentId: string) => Promise<ComponentStatusOk | ApiError>;
  remove_component?: (componentId: string) => Promise<ComponentStatusOk | ApiError>;
  get_context: () => Promise<Context>;
  get_tree: () => Promise<Tree>;
  get_workflow_status: () => Promise<WorkflowStatus>;
  get_activity: (limit?: number) => Promise<ActivityFeed>;
  get_network_settings: () => Promise<NetworkSettings>;
  save_network_settings: (settings: NetworkSettingsInput) => Promise<NetworkSettings | ApiError>;
  pick_open_file: (title?: string, filters?: string[]) => Promise<PickResult>;
  pick_directory: (title?: string) => Promise<PickResult>;
  ensure_directory: (path: string) => Promise<SimpleOk>;
  open_external_url: (url: string) => Promise<SimpleOk>;
  open_path: (path: string) => Promise<SimpleOk>;
  window_minimize?: () => Promise<SimpleOk>;
  window_toggle_maximize?: () => Promise<SimpleOk>;
  window_close?: () => Promise<SimpleOk>;
  window_get_size?: () => Promise<NativeWindowSize>;
  window_resize_from_edge?: (
    edge: string,
    startWidth: number,
    startHeight: number,
    deltaX: number,
    deltaY: number,
  ) => Promise<SimpleOk>;
  create_workspace: (root: string, name?: string | null) => Promise<WorkspaceResult>;
  add_project: (name: string) => Promise<ProjectResult>;
  select_project: (projectId: string) => Promise<ProjectResult>;
  add_region: (name: string) => Promise<RegionResult>;
  select_region: (regionId: string) => Promise<RegionResult>;
  set_region_aoi_bbox: (
    west: number,
    east: number,
    south: number,
    north: number,
  ) => Promise<AoiResult>;
  set_region_aoi_file: (path: string) => Promise<AoiResult>;
  preview_aoi_file: (path: string) => Promise<AoiPreviewResult>;
  set_region_aoi_file_features: (
    path: string,
    featureIds?: string[],
    nameField?: string,
    downloadMode?: "merge" | "split",
  ) => Promise<AoiResult>;
  set_region_aoi_geojson: (geojson: Json) => Promise<AoiResult>;
  search_admin_boundaries: (
    query?: string,
    province?: string,
    city?: string,
    district?: string,
    limit?: number,
  ) => Promise<AdminBoundaryResult>;
  get_admin_options: (province?: string, city?: string) => Promise<AdminOptionsResult>;
  import_scenes_text: (text: string) => Promise<ScenesResult>;
  import_scenes_file: (path: string) => Promise<ScenesResult>;
  import_scenes_directory: (path: string) => Promise<ScenesResult>;
  preview_scenes_file?: (path: string) => Promise<ScenesResult>;
  preview_scenes_directory?: (path: string) => Promise<ScenesResult>;
  clear_orbit_candidate_scenes?: () => Promise<SimpleOk>;
  search_asf_scenes: (params: AsfSearchParams) => Promise<ScenesResult>;
  list_scenes: () => Promise<ScenesOk | ApiError>;
  clear_scenes: () => Promise<SimpleOk>;
  clear_map_layers?: () => Promise<SimpleOk>;
  get_metadata_status: () => Promise<MetadataStatus>;
  check_scenes: () => Promise<CheckResult>;
  match_orbits_directory: (orbitDir: string) => Promise<OrbitMatchResult>;
  download_orbits: (outputDir?: string, sceneIds?: string[]) => Promise<OrbitDownloadResult>;
  start_orbit_download: (outputDir?: string, sceneIds?: string[]) => Promise<{ ok: boolean; error?: string; code?: string }>;
  pause_orbit_download: () => Promise<{ ok: boolean; error?: string; code?: string }>;
  resume_orbit_download: () => Promise<{ ok: boolean; error?: string; code?: string }>;
  stop_orbit_download: () => Promise<{ ok: boolean; error?: string; code?: string }>;
  get_orbit_download_status: () => Promise<OrbitDownloadStatus>;
  plan_asf_download: (outputDir?: string, sceneIds?: string[]) => Promise<PlanResult>;
  start_asf_download: (
    outputDir?: string,
    credentialSource?: string,
    maxConcurrent?: number,
    sceneIds?: string[],
  ) => Promise<{ ok: boolean; error?: string; code?: string }>;
  append_asf_download: (
    outputDir?: string,
    maxExtraWorkers?: number,
    sceneIds?: string[],
  ) => Promise<{ ok: boolean; error?: string; code?: string; appended?: number; skipped?: number; concurrency?: number }>;
  pause_asf_scenes: (sceneIds?: string[]) => Promise<{ ok: boolean; error?: string; code?: string; paused?: number }>;
  resume_asf_scenes: (sceneIds?: string[]) => Promise<{ ok: boolean; error?: string; code?: string; resumed?: number }>;
  pause_asf_download: () => Promise<{ ok: boolean; error?: string; code?: string }>;
  resume_asf_download: () => Promise<{ ok: boolean; error?: string; code?: string }>;
  stop_asf_download: () => Promise<{ ok: boolean; error?: string; code?: string }>;
  retry_asf_download: () => Promise<{ ok: boolean; error?: string; code?: string }>;
  get_download_status: () => Promise<DownloadStatus>;
  plan_dem_download: (outputDir?: string, dataset?: string) => Promise<PlanReportResult>;
  plan_dem_download_bbox: (
    west: number,
    east: number,
    south: number,
    north: number,
    outputDir?: string,
    dataset?: string,
  ) => Promise<PlanReportResult>;
  plan_gacos_request: (outputDir?: string) => Promise<PlanReportResult>;
  plan_dem_conversion: (outputDir?: string) => Promise<ConvertResult>;
  plan_local_dem_conversion: (
    inputPath: string,
    outputDir?: string,
    sourceVerticalDatum?: string,
  ) => Promise<ConvertResult>;
  plan_dem_conversion_bbox: (
    west: number,
    east: number,
    south: number,
    north: number,
    outputDir?: string,
    dataset?: string,
  ) => Promise<ConvertResult>;
  run_dem_download: (
    outputDir?: string,
    dataset?: string,
    keySource?: string,
    convert?: boolean,
  ) => Promise<RunSummaryResult>;
  run_dem_download_bbox: (
    west: number,
    east: number,
    south: number,
    north: number,
    outputDir?: string,
    dataset?: string,
    keySource?: string,
    convert?: boolean,
  ) => Promise<RunSummaryResult>;
  run_dem_conversion: (outputDir?: string) => Promise<RunSummaryResult>;
  run_local_dem_conversion: (
    inputPath: string,
    outputDir?: string,
    sourceVerticalDatum?: string,
    outputMode?: "ellipsoid" | "sarscape",
  ) => Promise<RunSummaryResult>;
  run_dem_conversion_bbox: (
    west: number,
    east: number,
    south: number,
    north: number,
    outputDir?: string,
    dataset?: string,
  ) => Promise<RunSummaryResult>;
  set_dem_dataset: (dataset: string) => Promise<{ ok: boolean; dataset?: string; error?: string; code?: string }>;
  get_download_archive: () => Promise<DownloadArchiveResult | ApiError>;
  save_download_archive: (items: DownloadArchiveItem[]) => Promise<DownloadArchiveResult | ApiError>;
  delete_download_archive_item: (item: DownloadArchiveItem) => Promise<DownloadArchiveResult | ApiError>;
  get_credential_status: () => Promise<CredentialStatus>;
  check_earthdata_auth: () => Promise<EarthdataAuthCheck | ApiError>;
  save_earthdata_token: (token: string) => Promise<SimpleOk>;
  save_earthdata_login: (username: string, password: string) => Promise<SimpleOk>;
  clear_earthdata_credentials: () => Promise<SimpleOk>;
  save_opentopography_key: (apiKey: string) => Promise<SimpleOk>;
  clear_opentopography_key: () => Promise<SimpleOk>;
  save_gacos_email: (email: string) => Promise<SimpleOk>;
  clear_gacos_email: () => Promise<SimpleOk>;
  generate_report: (outputDir?: string) => Promise<ReportResult>;
};

declare global {
  interface Window {
    pywebview?: { api: PyApi };
  }
}

export function hasBridge(): boolean {
  return typeof window !== "undefined" && !!window.pywebview?.api;
}

const api = () => window.pywebview!.api;

export function formatBridgeError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error ?? "");
  const text = raw.replace(/^Error:\s*/i, "").trim();
  if (text.includes("NoneType") && text.includes("model_dump")) {
    return "内部状态里暂时没有场景覆盖范围，已改为按空覆盖处理；请重试当前操作。";
  }
  if (text.includes("model_dump")) {
    return "内部数据序列化失败，请重试；如果仍出现，请重新选择当前项目或研究区。";
  }
  return text || "操作失败";
}

function notifyContextChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("insar-context-changed"));
  }
}

let bridgeSeen = false;
export function watchBridgeReady(): () => void {
  if (typeof window === "undefined") return () => undefined;
  if (hasBridge()) {
    bridgeSeen = true;
    notifyContextChanged();
    return () => undefined;
  }
  const id = window.setInterval(() => {
    if (hasBridge() && !bridgeSeen) {
      bridgeSeen = true;
      notifyContextChanged();
      window.clearInterval(id);
    }
  }, 250);
  return () => window.clearInterval(id);
}

// --------------------------------------------------------------- mock state
function mockSafeName(value: string): string | null {
  const safe = value
    .trim()
    .replace(/[^A-Za-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return safe || null;
}

const MOCK_BBOX: Bbox = {
  west: 73.5,
  east: 135.1,
  south: 18.0,
  north: 53.6,
  crs: "EPSG:4326",
};

const MOCK_SCENE_DATES = ["20240312", "20240324", "20240405", "20240417", "20240429", "20240511"];

function mockFootprintBbox(i: number, base: Bbox = MOCK_BBOX): Bbox {
  const width = Math.max(0.02, base.east - base.west);
  const height = Math.max(0.02, base.north - base.south);
  const step = Math.min(width, height) * 0.12;
  return {
    west: base.west + step * i,
    east: base.east + step * i,
    south: base.south + step * (i % 3) * 0.45,
    north: base.north + step * (i % 3) * 0.45,
    crs: "EPSG:4326",
  };
}

function polygonFromBbox(bbox: Bbox): Json {
  return {
    type: "Polygon",
    coordinates: [
      [
        [bbox.west, bbox.south],
        [bbox.east, bbox.south],
        [bbox.east, bbox.north],
        [bbox.west, bbox.north],
        [bbox.west, bbox.south],
      ],
    ],
  };
}

function bboxFromGeojson(geojson: Json): Bbox {
  const coords: [number, number][] = [];
  function walk(value: unknown) {
    if (!Array.isArray(value)) return;
    if (
      value.length >= 2 &&
      typeof value[0] === "number" &&
      typeof value[1] === "number"
    ) {
      coords.push([value[0], value[1]]);
      return;
    }
    value.forEach(walk);
  }
  walk((geojson.geometry as Json | undefined)?.coordinates ?? geojson.coordinates);
  if (!coords.length) return MOCK_BBOX;
  const lngs = coords.map((p) => p[0]);
  const lats = coords.map((p) => p[1]);
  return {
    west: Math.min(...lngs),
    east: Math.max(...lngs),
    south: Math.min(...lats),
    north: Math.max(...lats),
    crs: "EPSG:4326",
  };
}

// Browser-preview state starts empty so a delayed pywebview bridge never flashes
// stale demo data into the packaged desktop app.
const mock: {
  workspace: { workspace_id: string; root: string; name: string } | null;
  project: { project_id: string; name: string; safe_name: string; root?: string } | null;
  region: ContextRegion | null;
  standaloneSceneCount: number;
} = {
  workspace: null,
  project: null,
  region: null,
  standaloneSceneCount: 0,
};

let mockDataset = "COP30";
let mockCredentials: CredentialStatus = {
  ok: true,
  earthdata: "none",
  opentopography: "none",
  gacos: "none",
};
let mockNetworkSettings: NetworkSettings = {
  ok: true,
  proxy_enabled: false,
  proxy_url: "",
  cache_enabled: true,
  cache_dir: "C:\\Users\\<user>\\AppData\\Local\\InSAR Assistant\\cache",
  cache_limit_mb: 10240,
  tianditu_token: "",
  asf_ssl_verify: true,
};

function mockSourceDatum(ds: string): string {
  if (ds.endsWith("_ELLIPSOIDAL")) return "WGS84_ELLIPSOID";
  if (ds === "COP30" || ds === "COP90") return "EGM2008";
  return "EGM96";
}

function demSourceStem(ds: string): string {
  const key = ds.toUpperCase();
  const stems: Record<string, string> = {
    SRTM_GL3: "SRTM90m",
    SRTM_GL1: "SRTM30m",
    SRTM_GL1_ELLIPSOIDAL: "SRTM30m",
    AW3D30: "AW3D30m",
    AW3D30_ELLIPSOIDAL: "AW3D30m",
    COP90: "COP90m",
    COP30: "COP30m",
    NASADEM: "NASADEM",
  };
  return stems[key] ?? key.replace(/[^A-Za-z0-9]+/g, "_");
}

function mockReportsDir(): string {
  const root = mock.workspace?.root ?? "workspace_preview";
  const safe = mock.region?.safe_name ?? "region";
  return `${root}\\${safe}\\07_reports`;
}

function mockActiveSceneCount(): number {
  return mock.region?.scene_count ?? mock.standaloneSceneCount;
}

function mockActiveSafeName(): string {
  return mock.region?.safe_name ?? "standalone_download";
}

function ensureMockRegion(): ContextRegion {
  if (!mock.workspace) {
    mock.workspace = {
      workspace_id: "ws_preview",
      root: "workspace_preview",
      name: "预览工作区",
    };
  }
  if (!mock.project) {
    mock.project = {
      project_id: "proj_default_task",
      name: "默认任务",
      safe_name: "default_task",
      root: `${mock.workspace.root}\\default_task`,
    };
  }
  if (!mock.region) {
    mock.region = {
      region_id: "region_default_area",
      name: "默认区域",
      safe_name: "default_area",
      root: `${mock.project.root}\\default_area`,
      has_aoi: false,
      bbox: null,
      scene_count: 0,
    };
  }
  return mock.region;
}

function liteToBbox(item: AdminBoundaryLite): Bbox {
  return {
    west: item[2],
    east: item[3],
    south: item[4],
    north: item[5],
    crs: "EPSG:4326",
  };
}

function allPreviewDistricts(province: string): AdminBoundaryLite[] {
  const cityRows = ADMIN_INDEX.citiesByProvince[province] ?? [];
  return cityRows.flatMap((city) => ADMIN_INDEX.districtsByCity[`${province}|${city[0]}`] ?? []);
}

function previewBoundaryCandidates(province = "", city = "", district = "", query = ""): AdminBoundary[] {
  const clean = (value: string) => value.trim();
  const provinceName = clean(province);
  const cityName = clean(city);
  const districtName = clean(district);
  const queryName = clean(query);
  const provinceRows = [...ADMIN_INDEX.provinces];
  const allCityRows = Object.values(ADMIN_INDEX.citiesByProvince).flatMap((items) => [...items]);
  const allDistrictRows = Object.values(ADMIN_INDEX.districtsByCity).flatMap((items) => [...items]);
  const toBoundary = (item: AdminBoundaryLite, parts: string[]): AdminBoundary => {
    const label = [...parts, item[0]].filter(Boolean).join(" / ");
    const bbox = liteToBbox(item);
    return {
      label,
      bbox,
      geojson: polygonFromBbox(bbox),
      source: "Browser preview boundary index",
      class: "boundary",
      type: "administrative",
      osm_id: item[1],
    };
  };

  if (queryName) {
    const all = [...provinceRows, ...allCityRows, ...allDistrictRows];
    const matches = all
      .filter((item) => item[0] === queryName || item[0].includes(queryName) || queryName.includes(item[0]))
      .slice(0, 30)
      .map((item) => toBoundary(item, []));
    if (matches.length) return matches;
  }

  const selectedProvince = provinceRows.find((item) => item[0] === provinceName || item[0].includes(provinceName));
  const cityRows = selectedProvince
    ? [...(ADMIN_INDEX.citiesByProvince[selectedProvince[0]] ?? [])]
    : allCityRows;
  const selectedCity = cityRows.find((item) => item[0] === cityName || item[0].includes(cityName));
  const districtRows = selectedProvince
    ? selectedCity
      ? [...(ADMIN_INDEX.districtsByCity[`${selectedProvince[0]}|${selectedCity[0]}`] ?? [])]
      : allPreviewDistricts(selectedProvince[0])
    : allDistrictRows;

  if (districtName && districtName !== "全部" && districtName !== "不限") {
    return districtRows
      .filter((item) => item[0] === districtName || item[0].includes(districtName) || districtName.includes(item[0]))
      .map((item) => toBoundary(item, [selectedProvince?.[0] ?? provinceName, selectedCity?.[0] ?? cityName]));
  }
  if (cityName && cityName !== "全部" && cityName !== "不限") {
    const rows: AdminBoundary[] = [];
    if (selectedCity) rows.push(toBoundary(selectedCity, [selectedProvince?.[0] ?? provinceName]));
    rows.push(
      ...districtRows
        .slice(0, 30)
        .map((item) => toBoundary(item, [selectedProvince?.[0] ?? provinceName, selectedCity?.[0] ?? cityName])),
    );
    return rows;
  }
  if (provinceName && provinceName !== "全部" && provinceName !== "不限") {
    const rows: AdminBoundary[] = [];
    if (selectedProvince) rows.push(toBoundary(selectedProvince, []));
    rows.push(...cityRows.slice(0, 30).map((item) => toBoundary(item, [selectedProvince?.[0] ?? provinceName])));
    return rows;
  }
  return [];
}

// ------------------------------------------------------------------- app/ctx
export async function getAppInfo(): Promise<AppInfo> {
  if (hasBridge()) return api().get_app_info();
  return { name: "InSAR Studio", version: "2.0.1", offline: true };
}

export async function checkForUpdate(force = false): Promise<UpdateInfo | ApiError> {
  if (hasBridge()) {
    const checker = api().check_for_update;
    if (typeof checker === "function") return checker(force);
  }
  return {
    ok: true,
    checked: false,
    update_available: false,
    current_version: "2.0.1",
    latest_version: "2.0.1",
    html_url: "https://github.com/hhanmj/insar_studio/releases/latest",
    message: "Update checks run only in the packaged desktop app.",
  };
}

export async function downloadAppUpdate(
  downloadUrl = "",
  assetName = "",
): Promise<AppUpdateDownloadOk | ApiError> {
  if (hasBridge()) {
    const downloader = api().download_app_update;
    if (typeof downloader === "function") return downloader(downloadUrl, assetName);
  }
  return {
    ok: false,
    error: "在线下载更新包只在桌面版中可用。",
    code: "GUI003",
  };
}

export async function getComponentStatus(refresh = false): Promise<ComponentStatusOk | ApiError> {
  if (hasBridge()) {
    const getter = api().get_component_status;
    if (typeof getter === "function") return getter(refresh);
  }
  return {
    ok: true,
    root: "C:\\Users\\You\\AppData\\Local\\InSAR Assistant\\components",
    manifest_url: "https://github.com/hhanmj/insar_studio/releases/latest/download/components-manifest.json",
    components: [
      {
        id: "dem-gdal",
        name: "DEM 高级转换组件",
        version: "2.1",
        size_mb: 180,
        description: "GDAL/rasterio 等 DEM 椭球高转换运行库。",
        installed: false,
        runtime_available: true,
        state: "bundled",
        can_install: false,
      },
    ],
  };
}

export async function installComponent(componentId: string): Promise<ComponentStatusOk | ApiError> {
  if (hasBridge()) {
    const installer = api().install_component;
    if (typeof installer === "function") return installer(componentId);
  }
  return { ok: false, error: "组件安装只在桌面版中可用。", code: "GUI003" };
}

export async function removeComponent(componentId: string): Promise<ComponentStatusOk | ApiError> {
  if (hasBridge()) {
    const remover = api().remove_component;
    if (typeof remover === "function") return remover(componentId);
  }
  return { ok: false, error: "组件移除只在桌面版中可用。", code: "GUI003" };
}

export async function getContext(): Promise<Context> {
  if (hasBridge()) return api().get_context();
  return {
    ok: true,
    workspace: mock.workspace,
    project: mock.project,
    region: mock.region,
    dem_dataset: mockDataset,
  };
}

export async function setDemDataset(
  dataset: string,
): Promise<{ ok: boolean; dataset?: string; error?: string; code?: string }> {
  if (hasBridge()) {
    const res = await api().set_dem_dataset(dataset);
    if (res.ok) notifyContextChanged();
    return res;
  }
  mockDataset = dataset;
  notifyContextChanged();
  return { ok: true, dataset };
}

export async function getTree(): Promise<Tree> {
  if (hasBridge()) return api().get_tree();
  const projects: TreeProject[] = [];
  if (mock.project) {
    projects.push({
      ...mock.project,
      regions: mock.region
        ? [
            {
              region_id: mock.region.region_id,
              name: mock.region.name,
              safe_name: mock.region.safe_name,
              has_aoi: mock.region.has_aoi,
              scene_count: mock.region.scene_count,
            },
          ]
        : [],
    });
  }
  return {
    ok: true,
    workspace: mock.workspace,
    projects,
    current_project_id: mock.project?.project_id ?? null,
    current_region_id: mock.region?.region_id ?? null,
  };
}

export async function getWorkflowStatus(): Promise<WorkflowStatus> {
  if (hasBridge()) return api().get_workflow_status();
  const context = await getContext();
  const tree = await getTree();
  const download = await getDownloadStatus();
  const workspaceReady = !!context.workspace && !!context.project && !!context.region;
  const aoiReady = workspaceReady && !!context.region?.has_aoi;
  const sceneCount = context.region?.scene_count ?? mock.standaloneSceneCount;
  const scenesReady = sceneCount > 0;
  const dlActive = download.state === "running" || download.state === "paused";
  const creds = await getCredentialStatus();
  const credentialsReady = [creds.earthdata, creds.opentopography, creds.gacos].every(
    (v) => v !== "none" && v !== "unavailable",
  );
  const stages: WorkflowStage[] = [
    {
      id: "settings",
      label: "设置",
      nav: "settings",
      status: credentialsReady ? "done" : "active",
      summary: "配置 Earthdata、OpenTopography 和 GACOS。",
      ready: credentialsReady,
      count: credentialsReady ? 1 : 0,
    },
    {
      id: "workspace",
      label: "项目",
      nav: "workspace",
      status: workspaceReady ? "done" : "active",
      summary: "创建或选择当前项目和研究区。",
      ready: workspaceReady,
      count: workspaceReady ? 1 : 0,
    },
    {
      id: "aoi",
      label: "AOI",
      nav: "aoi",
      status: aoiReady ? "done" : workspaceReady ? "active" : "blocked",
      summary: "绘制或导入处理范围。",
      ready: aoiReady,
      count: aoiReady ? 1 : 0,
    },
    {
      id: "scenes",
      label: "影像",
      nav: "download",
      status: scenesReady ? "done" : "active",
      summary: "导入 ASF 购物车或本地目录；AOI 可选绑定。",
      ready: scenesReady,
      count: sceneCount,
    },
    {
      id: "downloads",
      label: "下载",
      nav: "download",
      status: dlActive ? "running" : download.state === "finished" ? "done" : scenesReady ? "active" : "blocked",
      summary: "规划并执行 SLC、DEM 和 GACOS。",
      ready: scenesReady,
      count: download.done,
    },
    {
      id: "convert",
      label: "DEM 转换",
      nav: "convert",
      status: aoiReady ? "active" : "blocked",
      summary: "生成 SARscape 可用的椭球高 DEM。",
      ready: aoiReady,
      count: 0,
    },
    {
      id: "report",
      label: "报告",
      nav: "report",
      status: scenesReady ? "active" : "blocked",
      summary: "生成报告、清单和警告表。",
      ready: scenesReady,
      count: 0,
    },
  ];
  const next_action = !credentialsReady
    ? { label: "配置下载凭据", nav: "settings" }
    : !workspaceReady
      ? { label: "创建项目", nav: "workspace" }
      : !scenesReady
        ? { label: "导入影像", nav: "download" }
        : !aoiReady
          ? { label: "可选绑定 AOI", nav: "aoi" }
          : dlActive
            ? { label: "查看下载", nav: "download" }
            : { label: "生成报告", nav: "report" };
  return {
    ok: true,
    context,
    stages,
    sources: [
      {
        id: "asf",
        label: "Sentinel-1",
        credential: creds.earthdata,
        status: ["none", "unavailable"].includes(creds.earthdata) ? "needs_config" : "configured",
        capabilities: ["cart import", "consistency check", "real download"],
      },
      {
        id: "dem",
        label: "OpenTopography DEM",
        credential: creds.opentopography,
        status: ["none", "unavailable"].includes(creds.opentopography) ? "needs_config" : "configured",
        capabilities: ["request plan", "real download", "vertical conversion"],
      },
      {
        id: "gacos",
        label: "GACOS",
        credential: creds.gacos,
        status: ["none", "unavailable"].includes(creds.gacos) ? "needs_config" : "configured",
        capabilities: ["request plan", "email result import"],
      },
      {
        id: "report",
        label: "Preparation report",
        credential: "local",
        status: scenesReady ? "ready" : "waiting",
        capabilities: ["html", "markdown", "manifest", "warnings"],
      },
    ],
    download,
    next_action,
    counts: {
      projects: tree.projects.length,
      regions: tree.projects.reduce((n, p) => n + p.regions.length, 0),
      scenes: sceneCount,
    },
    scene_coverage: {
      bbox: context.region?.scene_footprint_bbox ?? null,
      count: context.region?.scene_footprint_bbox ? context.region.scene_count : 0,
    },
    dem_dataset: mockDataset,
  };
}

export async function getActivity(limit = 12): Promise<ActivityFeed> {
  if (hasBridge()) return api().get_activity(limit);
  return { ok: true, activities: [] };
}

let mockDownloadArchive: DownloadArchiveItem[] = [];

export async function getDownloadArchive(): Promise<DownloadArchiveResult | ApiError> {
  if (hasBridge()) return api().get_download_archive();
  return { ok: true, items: mockDownloadArchive };
}

export async function saveDownloadArchive(
  items: DownloadArchiveItem[],
): Promise<DownloadArchiveResult | ApiError> {
  if (hasBridge()) return api().save_download_archive(items);
  mockDownloadArchive = items.slice(0, 40);
  return { ok: true, items: mockDownloadArchive };
}

export async function deleteDownloadArchiveItem(
  item: DownloadArchiveItem,
): Promise<DownloadArchiveResult | ApiError> {
  if (hasBridge()) return api().delete_download_archive_item(item);
  const key = `${item.kind || ""}:${(item.output_dir || item.id).replace(/[\\/]+$/, "").toLowerCase()}`;
  mockDownloadArchive = mockDownloadArchive.filter((row) => {
    const rowKey = `${row.kind || ""}:${(row.output_dir || row.id).replace(/[\\/]+$/, "").toLowerCase()}`;
    return row.id !== item.id && rowKey !== key;
  });
  return { ok: true, items: mockDownloadArchive };
}

export async function getNetworkSettings(): Promise<NetworkSettings> {
  if (hasBridge()) return api().get_network_settings();
  return mockNetworkSettings;
}

export async function saveNetworkSettings(
  settings: NetworkSettingsInput,
): Promise<NetworkSettings | ApiError> {
  if (hasBridge()) return api().save_network_settings(settings);
  mockNetworkSettings = {
    ok: true,
    proxy_enabled: !!settings.proxy_enabled,
    proxy_url: settings.proxy_url || "",
    cache_enabled: true,
    cache_dir: settings.cache_dir || "",
    cache_limit_mb: Number(settings.cache_limit_mb) || 0,
    tianditu_token: settings.tianditu_token || "",
    asf_ssl_verify: settings.asf_ssl_verify !== false,
  };
  return mockNetworkSettings;
}

export async function pickOpenFile(
  title = "",
  filters: string[] = [],
): Promise<PickResult> {
  if (hasBridge()) return api().pick_open_file(title, filters);
  return { ok: true, path: "" };
}

export async function pickDirectory(title = ""): Promise<PickResult> {
  if (hasBridge()) return api().pick_directory(title);
  return { ok: true, path: "" };
}

export async function ensureDirectory(path: string): Promise<SimpleOk> {
  if (hasBridge()) return api().ensure_directory(path);
  const trimmed = path.trim();
  if (!trimmed) return { ok: false, error: "目录路径不能为空", code: "GUI003" };
  return { ok: true, path: trimmed };
}

export async function openExternalUrl(url: string): Promise<SimpleOk> {
  if (hasBridge()) return api().open_external_url(url);
  if (typeof window !== "undefined") window.open(url, "_blank", "noopener,noreferrer");
  return { ok: true, url };
}

export async function openPath(path: string): Promise<SimpleOk> {
  if (hasBridge()) return api().open_path(path);
  return { ok: true, path };
}

export async function minimizeNativeWindow(): Promise<SimpleOk> {
  if (hasBridge() && typeof api().window_minimize === "function") {
    return api().window_minimize!();
  }
  return { ok: true };
}

export async function toggleNativeWindowMaximize(): Promise<SimpleOk> {
  if (hasBridge() && typeof api().window_toggle_maximize === "function") {
    return api().window_toggle_maximize!();
  }
  return { ok: true };
}

export async function closeNativeWindow(): Promise<SimpleOk> {
  if (hasBridge() && typeof api().window_close === "function") {
    return api().window_close!();
  }
  if (typeof window !== "undefined") window.close();
  return { ok: true };
}

export async function getNativeWindowSize(): Promise<NativeWindowSize> {
  if (hasBridge() && typeof api().window_get_size === "function") {
    return api().window_get_size!();
  }
  return {
    ok: true,
    width: typeof window !== "undefined" ? window.innerWidth : 1320,
    height: typeof window !== "undefined" ? window.innerHeight : 880,
  };
}

export async function resizeNativeWindowFromEdge(
  edge: string,
  startWidth: number,
  startHeight: number,
  deltaX: number,
  deltaY: number,
): Promise<SimpleOk> {
  if (hasBridge() && typeof api().window_resize_from_edge === "function") {
    return api().window_resize_from_edge!(edge, startWidth, startHeight, deltaX, deltaY);
  }
  return { ok: true };
}

// ------------------------------------------------------------ workspace tree
export async function createWorkspace(
  root: string,
  name?: string,
): Promise<WorkspaceResult> {
  if (hasBridge()) {
    const res = await api().create_workspace(root, name ?? null);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const trimmed = root.trim();
  if (!trimmed) return { ok: false, error: "工作区根路径不能为空", code: "GUI003" };
  if (mock.workspace?.root === trimmed) {
    if (name) mock.workspace = { ...mock.workspace, name };
    notifyContextChanged();
    return { ok: true, workspace_id: mock.workspace.workspace_id, root: trimmed, projects: [] };
  }
  mock.workspace = { workspace_id: "ws_preview", root: trimmed, name: name ?? "" };
  mock.project = null;
  mock.region = null;
  notifyContextChanged();
  return { ok: true, workspace_id: "ws_preview", root: trimmed, projects: [] };
}

export async function addProject(name: string): Promise<ProjectResult> {
  if (hasBridge()) {
    const res = await api().add_project(name);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const safe = mockSafeName(name);
  if (!safe) {
    return { ok: false, error: "项目名至少需包含一个字母、数字或下划线", code: "GUI003" };
  }
  const root = `${mock.workspace?.root ?? "C:\\InSAR"}\\${safe}`;
  mock.project = { project_id: `proj_${safe}`, name, safe_name: safe, root };
  mock.region = null;
  notifyContextChanged();
  return { ok: true, project_id: `proj_${safe}`, name, safe_name: safe };
}

export async function selectProject(projectId: string): Promise<ProjectResult> {
  if (hasBridge()) {
    const res = await api().select_project(projectId);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const safe = projectId.replace(/^proj_/, "");
  mock.project = {
    project_id: projectId,
    name: safe,
    safe_name: safe,
    root: `${mock.workspace?.root ?? "C:\\InSAR"}\\${safe}`,
  };
  notifyContextChanged();
  return { ok: true, project_id: projectId, name: safe, safe_name: safe };
}

export async function addRegion(name: string): Promise<RegionResult> {
  if (hasBridge()) {
    const res = await api().add_region(name);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const safe = mockSafeName(name);
  if (!safe) {
    return { ok: false, error: "区域名至少需包含一个字母、数字或下划线", code: "GUI003" };
  }
  mock.region = {
    region_id: `region_${safe}`,
    name,
    safe_name: safe,
    root: `${mock.project?.root ?? mock.workspace?.root ?? "C:\\InSAR"}\\${safe}`,
    has_aoi: false,
    bbox: null,
    scene_count: 0,
  };
  notifyContextChanged();
  return { ok: true, region_id: `region_${safe}`, name, safe_name: safe };
}

export async function selectRegion(regionId: string): Promise<RegionResult> {
  if (hasBridge()) {
    const res = await api().select_region(regionId);
    if (res.ok) notifyContextChanged();
    return res;
  }
  if (!mock.region || mock.region.region_id !== regionId) {
    return { ok: false, error: "未知区域", code: "GUI002" };
  }
  notifyContextChanged();
  return {
    ok: true,
    region_id: mock.region.region_id,
    name: mock.region.name,
    safe_name: mock.region.safe_name,
  };
}

// --------------------------------------------------------------------- AOI
export async function setRegionAoiBbox(
  west: number,
  east: number,
  south: number,
  north: number,
): Promise<AoiResult> {
  if (hasBridge()) {
    const res = await api().set_region_aoi_bbox(west, east, south, north);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const region = ensureMockRegion();
  if (!(west < east)) {
    return { ok: false, error: "west must be strictly less than east", code: "AOI001" };
  }
  if (!(south < north)) {
    return { ok: false, error: "south must be strictly less than north", code: "AOI001" };
  }
  const bbox: Bbox = { west, east, south, north, crs: "EPSG:4326" };
  mock.region = { ...region, has_aoi: true, bbox, aoi_geojson: null };
  notifyContextChanged();
  return {
    ok: true,
    aoi: { source: "MANUAL_BBOX", role: "PROCESSING_AOI", bbox },
    region_id: mock.region.region_id,
    region_name: mock.region.name,
  };
}

export async function setRegionAoiFile(path: string): Promise<AoiResult> {
  if (hasBridge()) {
    const res = await api().set_region_aoi_file(path);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const region = ensureMockRegion();
  if (!path.trim()) return { ok: false, error: "请提供矢量文件路径", code: "AOI001" };
  mock.region = { ...region, has_aoi: true, bbox: MOCK_BBOX, aoi_geojson: null };
  notifyContextChanged();
  return {
    ok: true,
    aoi: { source: "VECTOR_FILE", role: "PROCESSING_AOI", bbox: MOCK_BBOX, geometry_path: path },
    aoi_geojson: polygonFromBbox(MOCK_BBOX),
    aoi_feature_count: 1,
    region_id: mock.region.region_id,
    region_name: mock.region.name,
  };
}

export async function previewAoiFile(path: string): Promise<AoiPreviewResult> {
  if (hasBridge()) return api().preview_aoi_file(path);
  if (!path.trim()) return { ok: false, error: "请提供矢量文件路径", code: "AOI001" };
  return {
    ok: true,
    path,
    file_name: path.split(/[\\/]/).pop() || "boundary.geojson",
    total_features: 3,
    fields: ["name", "type"],
    display_field: "name",
    features: [
      { id: "0", index: 1, name: "示例边界 A", area_km2: 120.5, bbox: MOCK_BBOX, properties: { name: "示例边界 A", type: "county" } },
      { id: "1", index: 2, name: "示例边界 B", area_km2: 86.2, bbox: MOCK_BBOX, properties: { name: "示例边界 B", type: "county" } },
      { id: "2", index: 3, name: "示例边界 C", area_km2: 214.8, bbox: MOCK_BBOX, properties: { name: "示例边界 C", type: "county" } },
    ],
  };
}

export async function setRegionAoiFileFeatures(
  path: string,
  featureIds: string[],
  nameField = "",
  downloadMode: "merge" | "split" = "merge",
): Promise<AoiResult> {
  if (hasBridge()) {
    const res = await api().set_region_aoi_file_features(path, featureIds, nameField, downloadMode);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const region = ensureMockRegion();
  mock.region = { ...region, has_aoi: true, bbox: MOCK_BBOX, aoi_geojson: polygonFromBbox(MOCK_BBOX) };
  notifyContextChanged();
  return {
    ok: true,
    aoi: { source: "VECTOR_FILE", role: "PROCESSING_AOI", bbox: MOCK_BBOX, geometry_path: path },
    aoi_geojson: polygonFromBbox(MOCK_BBOX),
    aoi_feature_count: featureIds.length || 3,
    aoi_total_feature_count: 3,
    download_mode: downloadMode,
    region_id: mock.region.region_id,
    region_name: mock.region.name,
  };
}

export async function setRegionAoiGeojson(geojson: Json): Promise<AoiResult> {
  if (hasBridge()) {
    const res = await api().set_region_aoi_geojson(geojson);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const region = ensureMockRegion();
  const bbox = bboxFromGeojson(geojson);
  mock.region = { ...region, has_aoi: true, bbox, aoi_geojson: geojson };
  notifyContextChanged();
  return {
    ok: true,
    aoi: { source: "MANUAL_BBOX", role: "PROCESSING_AOI", bbox },
    aoi_geojson: geojson,
    region_id: mock.region.region_id,
    region_name: mock.region.name,
  };
}

export async function searchAdminBoundaries(
  query = "",
  province = "",
  city = "",
  district = "",
  limit = 8,
): Promise<AdminBoundaryResult> {
  if (hasBridge()) {
    return api().search_admin_boundaries(query, province, city, district, limit);
  }
  const parts = [district, city, province, query]
    .map((item) => item.trim())
    .filter((item) => item && item !== "全部" && item !== "不限");
  const label = parts.length ? parts.join(" / ") : "预览行政区";
  const results = previewBoundaryCandidates(province, city, district, query).slice(0, Math.max(1, limit));
  if (results.length) {
    return {
      ok: true,
      query: label,
      provider: "preview-local-index",
      warning: "网页预览只内置行政区 bbox；exe 内使用完整不规则边界。",
      results,
    };
  }
  const bbox = MOCK_BBOX;
  return {
    ok: true,
    query: label,
    provider: "preview-fallback",
    warning: "未在预览索引中找到匹配行政区，已返回示例范围。",
    results: [
      {
        label,
        bbox,
        geojson: polygonFromBbox(bbox),
        source: "Mock boundary",
        class: "boundary",
        type: "administrative",
      },
    ],
  };
}

export async function getAdminOptions(province = "", city = ""): Promise<AdminOptionsResult> {
  if (hasBridge()) return api().get_admin_options(province, city);
  const clean = (value: string) => value.trim();
  const provinceName = clean(province);
  const cityName = clean(city);
  const provinces = ADMIN_INDEX.provinces.map((item) => item[0]);
  const provinceKey =
    provinces.find((item) => item === provinceName) ??
    provinces.find((item) => provinceName && (item.includes(provinceName) || provinceName.includes(item))) ??
    "";
  const cityRows = provinceKey
    ? [...(ADMIN_INDEX.citiesByProvince[provinceKey] ?? [])]
    : Object.values(ADMIN_INDEX.citiesByProvince).flatMap((items) => [...items]);
  const cityNames = Array.from(new Set(cityRows.map((item) => item[0]))).sort();
  const cityKey =
    cityNames.find((item) => item === cityName) ??
    cityNames.find((item) => cityName && (item.includes(cityName) || cityName.includes(item))) ??
    "";
  const districtRows =
    provinceKey && cityKey
      ? [...(ADMIN_INDEX.districtsByCity[`${provinceKey}|${cityKey}`] ?? [])]
      : provinceKey
        ? allPreviewDistricts(provinceKey)
        : Object.values(ADMIN_INDEX.districtsByCity).flatMap((items) => [...items]);
  const districts = Array.from(new Set(districtRows.map((item) => item[0]))).sort();
  return {
    ok: true,
    provinces,
    cities: cityNames,
    districts,
  };
}

// ------------------------------------------------------------------ SCENES
function mockScene(i: number): SceneRow {
  const date = MOCK_SCENE_DATES[i % MOCK_SCENE_DATES.length];
  const footprint = mockFootprintBbox(i);
  return {
    scene_id: `S1A_IW_SLC__1SDV_${date}T223805_${date}T223832_0529${14 + i}_0667A5`,
    platform: "S1A",
    product_type: "SLC",
    beam_mode: "IW",
    polarization: "DV",
    acquisition_datetime: `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}T22:38:05Z`,
    absolute_orbit: 52914 + i * 175,
    relative_orbit: 11,
    path: 11,
    frame: 468,
    orbit_direction: i % 2 === 0 ? "DESCENDING" : "ASCENDING",
    file_size_remote: 7_800_000_000 + i * 210_000_000,
    footprint_bbox: footprint,
    footprint_geojson: polygonFromBbox(footprint),
    has_url: false,
  };
}

export async function importScenesText(text: string): Promise<ScenesResult> {
  if (hasBridge()) {
    const res = await api().import_scenes_text(text);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) {
    return { ok: false, error: "请粘贴至少一个 Sentinel-1 颗粒名或下载链接", code: "ASF001" };
  }
  const valid = lines.filter((l) => /S1[ABCD]_(SM|IW|EW|WV)_(SLC|GRD|RAW|OCN)/i.test(l));
  const errors = lines
    .filter((l) => !/S1[ABCD]_(SM|IW|EW|WV)_(SLC|GRD|RAW|OCN)/i.test(l))
    .map((line) => ({ line, error: "不是 Sentinel-1 颗粒名" }));
  if (!valid.length) {
    return { ok: false, error: "未能解析出任何有效的 Sentinel-1 场景", code: "ASF001" };
  }
  const scenes = valid.map((_, i) => mockScene(i));
  if (mock.region) mock.region = { ...mock.region, scene_count: scenes.length };
  else mock.standaloneSceneCount = scenes.length;
  notifyContextChanged();
  return { ok: true, scenes, duplicates: [], errors };
}

export async function importScenesFile(path: string): Promise<ScenesResult> {
  if (hasBridge()) {
    const res = await api().import_scenes_file(path);
    if (res.ok) notifyContextChanged();
    return res;
  }
  if (!path.trim()) return { ok: false, error: "请提供购物车文件路径", code: "ASF001" };
  const scenes = [mockScene(0), mockScene(1), mockScene(2)];
  if (mock.region) mock.region = { ...mock.region, scene_count: scenes.length };
  else mock.standaloneSceneCount = scenes.length;
  notifyContextChanged();
  return {
    ok: true,
    scenes,
    duplicates: [],
    errors: [],
    queried: scenes.length,
    search: {
      requested_limit: n,
      query_limit: n,
      total_count: Math.max(n, scenes.length),
      returned_count: scenes.length,
      source: "mock",
    },
  };
}

export async function previewScenesFile(path: string): Promise<ScenesResult> {
  if (hasBridge()) {
    const previewer = api().preview_scenes_file;
    if (typeof previewer === "function") return previewer(path);
    return api().import_scenes_file(path);
  }
  if (!path.trim()) return { ok: false, error: "请提供购物车文件路径", code: "ASF001" };
  const scenes = [mockScene(0), mockScene(1), mockScene(2)];
  return { ok: true, scenes, duplicates: [], errors: [] };
}

export async function importScenesDirectory(path: string): Promise<ScenesResult> {
  if (hasBridge()) {
    const res = await api().import_scenes_directory(path);
    if (res.ok) notifyContextChanged();
    return res;
  }
  if (!path.trim()) return { ok: false, error: "请提供 Sentinel-1 数据目录", code: "ASF001" };
  const scenes = [mockScene(0), mockScene(1)];
  if (mock.region) mock.region = { ...mock.region, scene_count: scenes.length };
  else mock.standaloneSceneCount = scenes.length;
  notifyContextChanged();
  return { ok: true, scenes, duplicates: [], errors: [] };
}

export async function previewScenesDirectory(path: string): Promise<ScenesResult> {
  if (hasBridge()) {
    const previewer = api().preview_scenes_directory;
    if (typeof previewer === "function") return previewer(path);
    return api().import_scenes_directory(path);
  }
  if (!path.trim()) return { ok: false, error: "请提供 Sentinel-1 数据目录", code: "ASF001" };
  const scenes = [mockScene(0), mockScene(1)];
  return { ok: true, scenes, duplicates: [], errors: [] };
}

export async function clearOrbitCandidateScenes(): Promise<SimpleOk> {
  if (hasBridge()) {
    const clearer = api().clear_orbit_candidate_scenes;
    if (typeof clearer === "function") return clearer();
  }
  return { ok: true };
}

export async function searchAsfScenes(params: AsfSearchParams): Promise<ScenesResult> {
  if (hasBridge()) {
    const res = await api().search_asf_scenes(params);
    if (res.ok) notifyContextChanged();
    return res;
  }
  const n = Math.min(Number(params.max_results || 12) || 12, 50);
  const product = String(params.product_type || "SLC").toUpperCase();
  const beam = String(params.beam_mode || "IW").toUpperCase();
  const polarization = String(params.polarization || "DV").toUpperCase();
  const orbitDirection = String(params.orbit_direction || "").toUpperCase();
  const scenes = Array.from({ length: Math.min(n, 6) }, (_, i) => ({
    ...mockScene(i),
    product_type: product,
    beam_mode: beam,
    polarization,
    has_url: true,
    orbit_direction:
      orbitDirection === "ASCENDING" || orbitDirection === "DESCENDING"
        ? orbitDirection
        : i % 2 === 0
          ? "DESCENDING"
          : "ASCENDING",
    path: params.relative_orbit ? Number(params.relative_orbit) : 11 + i,
    relative_orbit: params.relative_orbit ? Number(params.relative_orbit) : 11 + i,
    frame: params.frame ? Number(params.frame) : 468 + i,
    footprint_bbox: mockFootprintBbox(i, params.bbox ?? mock.region?.bbox ?? MOCK_BBOX),
    footprint_geojson: polygonFromBbox(mockFootprintBbox(i, params.bbox ?? mock.region?.bbox ?? MOCK_BBOX)),
  }));
  if (mock.region) {
    const footprint = scenes[0]?.footprint_bbox ?? mock.region.scene_footprint_bbox;
    mock.region = { ...mock.region, scene_count: scenes.length, scene_footprint_bbox: footprint };
  } else {
    mock.standaloneSceneCount = scenes.length;
  }
  notifyContextChanged();
  return { ok: true, scenes, duplicates: [], errors: [] };
}

export async function listScenes(): Promise<ScenesResult> {
  if (hasBridge()) return api().list_scenes();
  const n = mockActiveSceneCount();
  return { ok: true, scenes: Array.from({ length: n }, (_, i) => mockScene(i)), duplicates: [], errors: [] };
}

export async function clearScenes(): Promise<SimpleOk> {
  if (hasBridge()) {
    const res = await api().clear_scenes();
    if (res.ok) notifyContextChanged();
    return res;
  }
  const cleared = mockActiveSceneCount();
  if (mock.region) mock.region = { ...mock.region, scene_count: 0, scene_footprint_bbox: null };
  mock.standaloneSceneCount = 0;
  notifyContextChanged();
  return { ok: true, cleared };
}

export async function clearMapLayers(): Promise<SimpleOk> {
  if (hasBridge()) {
    const clearAll = api().clear_map_layers;
    if (typeof clearAll === "function") return clearAll();
    return api().clear_scenes();
  }
  const cleared = mockActiveSceneCount();
  mock.standaloneScenes = [];
  if (mock.region) {
    mock.region = { ...mock.region, has_aoi: false, bbox: null, aoi_geojson: null, scene_count: 0 };
  }
  notifyContextChanged();
  return { ok: true, cleared_scenes: cleared, cleared_aoi: true };
}

export async function getMetadataStatus(): Promise<MetadataStatus> {
  if (hasBridge()) return api().get_metadata_status();
  return {
    ok: true,
    state: "idle",
    done: 0,
    total: 0,
    percent: 0,
    message: "",
  };
}

export async function checkScenes(): Promise<CheckResult> {
  if (hasBridge()) return api().check_scenes();
  const n = mockActiveSceneCount();
  if (!n) return { ok: false, error: "请先导入场景", code: "ASF001" };
  return {
    ok: true,
    report: {
      total_scenes: n,
      valid_scenes: n,
      has_errors: false,
      has_warnings: true,
      issues: [
        {
          code: "SCENE_URL_MISSING",
          severity: "WARNING",
          message: "scene has no download URL",
          scene_id: mockScene(0).scene_id,
        },
      ],
      summary: { scene_count: n },
    },
  };
}

function mockOrbitReport(sceneCount: number, matched = sceneCount): Json {
  return {
    total_scenes: sceneCount,
    matched_scenes: matched,
    unmatched_scenes: Math.max(0, sceneCount - matched),
    results: Array.from({ length: sceneCount }, (_, i) => ({
      scene_id: mockScene(i).scene_id,
      is_matched: i < matched,
      matched_orbit:
        i < matched
          ? {
              file_name:
                "S1A_OPER_AUX_POEORB_OPOD_20240313T120000_V20240312T000000_20240313T000000.EOF",
              orbit_type: "POEORB",
            }
          : null,
    })),
    issues: [],
    summary: {
      orbit_files: matched,
      scenes: sceneCount,
      matched,
      unmatched: Math.max(0, sceneCount - matched),
      orbit_types: ["POEORB"],
    },
  };
}

export async function matchOrbitsDirectory(orbitDir: string): Promise<OrbitMatchResult> {
  if (hasBridge()) return api().match_orbits_directory(orbitDir);
  const n = mockActiveSceneCount();
  if (!n) return { ok: false, error: "请先导入 ASF 场景或本地 SLC 目录", code: "ASF001" };
  if (!orbitDir.trim()) return { ok: false, error: "请提供精密轨道目录", code: "ORB001" };
  return {
    ok: true,
    orbit_dir: orbitDir,
    orbit_files: n,
    report: mockOrbitReport(n),
  };
}

export async function downloadOrbits(outputDir = "", sceneIds: string[] = []): Promise<OrbitDownloadResult> {
  if (hasBridge()) return api().download_orbits(outputDir, sceneIds);
  const selectedIds = sceneIds.filter(Boolean);
  const n = selectedIds.length || mockActiveSceneCount();
  if (!n) return { ok: false, error: "请先导入 ASF 场景或本地 SLC 目录", code: "ASF001" };
  const root = outputDir || mock.workspace?.root || "C:\\InSAR";
  return {
    ok: true,
    orbit_dir: `${root}\\Sentinel_Orbit\\AUX_POEORB`,
    summary_line: `${n} downloaded, 0 skipped, 0 unavailable, 0 failed`,
    total: n,
    succeeded: n,
    skipped: 0,
    unavailable: 0,
    failed: 0,
    has_failures: false,
    results: Array.from({ length: n }, (_, i) => ({
      scene_id: selectedIds[i] ?? mockScene(i).scene_id,
      outcome: "success",
      orbit_file: `S1A_OPER_AUX_POEORB_OPOD_202403${13 + i}T120000_V202403${12 + i}T000000_202403${13 + i}T000000.EOF`,
      orbit_type: "POEORB",
      path: `${root}\\Sentinel_Orbit\\AUX_POEORB\\orbit.EOF`,
      bytes_written: 1024,
      message: "已从 ASF 下载 POEORB 精密轨道文件。",
    })),
    report: mockOrbitReport(n),
  };
}

let mockOrbitState: OrbitDownloadStatus = {
  ok: true,
  state: "idle",
  total: 0,
  done: 0,
  current_scene: "",
  orbit_dir: "",
  elapsed_seconds: 0,
  paused: false,
  cancelled: false,
  error: null,
  summary_line: "",
  succeeded: 0,
  skipped: 0,
  unavailable: 0,
  failed: 0,
  has_failures: false,
  results: [],
  log: [],
  report: null,
  pause_hint: "轨道文件较小，暂停/结束会在当前 EOF 请求结束后生效。",
};

export async function startOrbitDownload(
  outputDir = "",
  sceneIds: string[] = [],
): Promise<{ ok: boolean; error?: string; code?: string }> {
  if (hasBridge()) return api().start_orbit_download(outputDir, sceneIds);
  const selectedIds = sceneIds.filter(Boolean);
  const n = selectedIds.length || mockActiveSceneCount();
  if (!n) return { ok: false, error: "请先导入 ASF 场景或本地 SLC 目录", code: "ASF001" };
  const root = outputDir || mock.region?.root || mock.project?.root || mock.workspace?.root || "C:\\InSAR";
  const results = Array.from({ length: n }, (_, i) => ({
    scene_id: selectedIds[i] ?? mockScene(i).scene_id,
    outcome: "success",
    orbit_file: `S1A_OPER_AUX_POEORB_OPOD_202403${13 + i}T120000_V202403${12 + i}T000000_202403${13 + i}T000000.EOF`,
    orbit_type: "POEORB",
    path: `${root}\\Sentinel_Orbit\\AUX_POEORB\\orbit.EOF`,
    bytes_written: 1024,
    message: "mock POEORB ok",
  }));
  mockOrbitState = {
    ...mockOrbitState,
    state: "finished",
    total: n,
    done: n,
    current_scene: "",
    orbit_dir: `${root}\\Sentinel_Orbit\\AUX_POEORB`,
    paused: false,
    cancelled: false,
    error: null,
    summary_line: `${n} downloaded, 0 skipped, 0 unavailable, 0 failed`,
    succeeded: n,
    skipped: 0,
    unavailable: 0,
    failed: 0,
    has_failures: false,
    results,
    log: results.map((r) => ({
      scene_id: String(r.scene_id),
      outcome: String(r.outcome),
      detail: `${r.outcome}: ${r.message}`,
    })),
    report: mockOrbitReport(n),
  };
  return { ok: true };
}

export async function pauseOrbitDownload(): Promise<{ ok: boolean; error?: string; code?: string }> {
  if (hasBridge()) return api().pause_orbit_download();
  mockOrbitState = { ...mockOrbitState, state: "paused", paused: true };
  return { ok: true };
}

export async function resumeOrbitDownload(): Promise<{ ok: boolean; error?: string; code?: string }> {
  if (hasBridge()) return api().resume_orbit_download();
  mockOrbitState = { ...mockOrbitState, state: "running", paused: false };
  return { ok: true };
}

export async function stopOrbitDownload(): Promise<{ ok: boolean; error?: string; code?: string }> {
  if (hasBridge()) return api().stop_orbit_download();
  mockOrbitState = { ...mockOrbitState, state: "cancelled", cancelled: true, paused: false };
  return { ok: true };
}

export async function getOrbitDownloadStatus(): Promise<OrbitDownloadStatus> {
  if (hasBridge()) return api().get_orbit_download_status();
  return mockOrbitState;
}

// ---------------------------------------------------------------- DOWNLOAD
function mockAsfPlan(): Json {
  const n = mockActiveSceneCount();
  const items = Array.from({ length: n }, (_, i) => {
    const s = mockScene(i);
    return {
      scene_id: s.scene_id,
      platform: "S1A",
      acquisition_datetime: s.acquisition_datetime,
      product: "SLC",
      beam: "IW",
      polarization: "DV",
      url_status: "missing",
      status: "MISSING_URL",
      expected_filename: `${s.scene_id}.zip`,
    };
  });
  return {
    region_safe_name: mockActiveSafeName(),
    scene_count: n,
    planned_count: 0,
    missing_url_count: n,
    credential_required: true,
    slc_directory: `${mock.workspace?.root ?? "C:\\InSAR"}\\SAR_Data\\SLC`,
    items,
  };
}

function mockDemPlan(
  dataset: string,
  bbox: Bbox = mock.region?.bbox ?? MOCK_BBOX,
  safe = mock.region?.safe_name ?? "standalone_dem",
  root = mock.workspace?.root ?? "C:\\InSAR",
): Json {
  const b = bbox;
  return {
    dataset,
    provider: "OPENTOPOGRAPHY",
    request_bbox: {
      west: b.west - 0.05,
      east: b.east + 0.05,
      south: b.south - 0.05,
      north: b.north + 0.05,
    },
    processing_bbox: b,
    buffer_degrees: 0.05,
    source_vertical_datum: "EGM2008",
    target_vertical_datum: "WGS84_ELLIPSOID",
    raw_dem_path: `${root}\\${demSourceStem(dataset)}.tif`,
    ellipsoid_dem_path: `${root}\\${demSourceStem(dataset)}_ellipsoid.tif`,
    sarscape_ready_dem_path: `${root}\\${demSourceStem(dataset)}_dem`,
  };
}

function mockReport(hasErrors = false): Json {
  return {
    has_errors: hasErrors,
    has_warnings: false,
    issues: [],
    summary: { overall_status: hasErrors ? "blocked" : "ready" },
  };
}

export async function planAsfDownload(outputDir = "", sceneIds: string[] = []): Promise<PlanResult> {
  if (hasBridge()) return api().plan_asf_download(outputDir, sceneIds);
  if (!(sceneIds.length || mockActiveSceneCount())) {
    return { ok: false, error: "请先在『影像核查』导入场景", code: "ASF001" };
  }
  return { ok: true, plan: mockAsfPlan() };
}

let mockDlState: DownloadStatus = {
  ok: true,
    state: "idle",
    total: 0,
    done: 0,
    current_scene: "",
    total_bytes: null,
    done_bytes: 0,
    current_bytes: 0,
    current_expected_size: null,
    bytes_per_second: 0,
    elapsed_seconds: 0,
    concurrency: 1,
    paused: false,
  cancelled: false,
    error: null,
    summary_line: "",
    results_path: "",
    succeeded: 0,
    skipped: 0,
    failed: 0,
    interrupted: 0,
    has_failures: false,
    paused_scene_ids: [],
    resume_supported: true,
    resume_hint: "暂停或强制结束会保留 .part；再次开始同一输出目录会断点续传。",
    retry_supported: false,
    retry_hint: "只重试失败/中断的场景；已完成文件会跳过，.part 文件会继续续传。",
    log: [],
};

export async function startAsfDownload(
  outputDir = "",
  credentialSource = "auto",
  maxConcurrent = 1,
  sceneIds: string[] = [],
): Promise<{ ok: boolean; error?: string; code?: string }> {
  if (hasBridge()) return api().start_asf_download(outputDir, credentialSource, maxConcurrent, sceneIds);
  const n = sceneIds.length || mockActiveSceneCount();
  if (!n) return { ok: false, error: "请先导入场景", code: "ASF001" };
  if (mockCredentials.earthdata === "none" || mockCredentials.earthdata === "unavailable") {
    return {
      ok: false,
      error: "开始 Sentinel-1 下载前，请先在设置中保存 Earthdata Token 或账号密码。",
      code: "DL004",
    };
  }
  mockDlState = {
    ok: true,
    state: "finished",
    total: n,
    done: n,
    current_scene: "",
    total_bytes: n * 1024,
    done_bytes: n * 1024,
    current_bytes: 0,
    current_expected_size: null,
    bytes_per_second: 1024,
    elapsed_seconds: 1,
    concurrency: maxConcurrent,
    paused: false,
    cancelled: false,
    error: null,
    summary_line: `${n} 已下载, 0 跳过, 0 失败, 0 中断`,
    results_path: "",
    succeeded: n,
    skipped: 0,
    failed: 0,
    interrupted: 0,
    has_failures: false,
    resume_supported: true,
    resume_hint: "暂停或强制结束会保留 .part；再次开始同一输出目录会断点续传。",
    retry_supported: false,
    retry_hint: "只重试失败/中断的场景；已完成文件会跳过，.part 文件会继续续传。",
    log: [],
  };
  return { ok: true };
}

export async function appendAsfDownload(
  outputDir = "",
  maxExtraWorkers = 1,
  sceneIds: string[] = [],
): Promise<{ ok: boolean; error?: string; code?: string; appended?: number; skipped?: number; concurrency?: number }> {
  if (hasBridge()) return api().append_asf_download(outputDir, maxExtraWorkers, sceneIds);
  const n = sceneIds.length || 0;
  if (!n) return { ok: false, error: "请先勾选要追加下载的 SAR 影像", code: "ASF001" };
  mockDlState = {
    ...mockDlState,
    state: mockDlState.state === "idle" ? "running" : mockDlState.state,
    total: mockDlState.total + n,
    concurrency: Math.max(mockDlState.concurrency ?? 1, (mockDlState.concurrency ?? 1) + Math.min(n, maxExtraWorkers)),
  };
  return { ok: true, appended: n, skipped: 0, concurrency: mockDlState.concurrency };
}

export async function pauseAsfScenes(sceneIds: string[] = []): Promise<{ ok: boolean; error?: string; code?: string; paused?: number }> {
  if (hasBridge()) return api().pause_asf_scenes(sceneIds);
  const paused = new Set([...(mockDlState.paused_scene_ids ?? []), ...sceneIds]);
  mockDlState = { ...mockDlState, paused_scene_ids: Array.from(paused), state: "paused", paused: true };
  return { ok: true, paused: sceneIds.length };
}

export async function resumeAsfScenes(sceneIds: string[] = []): Promise<{ ok: boolean; error?: string; code?: string; resumed?: number }> {
  if (hasBridge()) return api().resume_asf_scenes(sceneIds);
  const targets = new Set(sceneIds);
  mockDlState = {
    ...mockDlState,
    paused_scene_ids: (mockDlState.paused_scene_ids ?? []).filter((id) => !targets.has(id)),
    state: "running",
    paused: false,
  };
  return { ok: true, resumed: sceneIds.length };
}

export async function pauseAsfDownload(): Promise<{ ok: boolean; error?: string; code?: string }> {
  if (hasBridge()) return api().pause_asf_download();
  if (mockDlState.state !== "running") return { ok: false, error: "当前没有进行中的下载", code: "GUI004" };
  mockDlState = { ...mockDlState, state: "paused", paused: true };
  return { ok: true };
}

export async function resumeAsfDownload(): Promise<{ ok: boolean; error?: string; code?: string }> {
  if (hasBridge()) return api().resume_asf_download();
  if (mockDlState.state !== "paused") return { ok: false, error: "下载未处于暂停状态", code: "GUI004" };
  mockDlState = { ...mockDlState, state: "running", paused: false };
  return { ok: true };
}

export async function stopAsfDownload(): Promise<{ ok: boolean; error?: string; code?: string }> {
  if (hasBridge()) return api().stop_asf_download();
  mockDlState = { ...mockDlState, state: "cancelled", cancelled: true };
  return { ok: true };
}

export async function retryAsfDownload(): Promise<{ ok: boolean; error?: string; code?: string }> {
  if (hasBridge()) return api().retry_asf_download();
  if (!mockDlState.has_failures) return { ok: false, error: "当前没有失败或中断的 ASF 场景可重试", code: "GUI004" };
  mockDlState = { ...mockDlState, state: "running", paused: false, cancelled: false };
  return { ok: true };
}

export async function getDownloadStatus(): Promise<DownloadStatus> {
  if (hasBridge()) return api().get_download_status();
  return mockDlState;
}

export async function planDemDownload(
  outputDir = "",
  dataset = "COP30",
): Promise<PlanReportResult> {
  if (hasBridge()) return api().plan_dem_download(outputDir, dataset);
  if (!mock.region?.has_aoi) {
    return { ok: false, error: "请先在『区域 AOI』设置处理范围（bbox）", code: "AOI001" };
  }
  mockDataset = dataset;
  return { ok: true, plan: mockDemPlan(dataset), report: mockReport() };
}

export async function planDemDownloadBbox(
  west: number,
  east: number,
  south: number,
  north: number,
  outputDir = "",
  dataset = "COP30",
): Promise<PlanReportResult> {
  if (hasBridge()) {
    return api().plan_dem_download_bbox(west, east, south, north, outputDir, dataset);
  }
  if (!(west < east) || !(south < north)) {
    return { ok: false, error: "bbox 范围无效，请检查 west/east/south/north", code: "AOI001" };
  }
  mockDataset = dataset;
  const bbox: Bbox = { west, east, south, north, crs: "EPSG:4326" };
  return {
    ok: true,
    plan: mockDemPlan(dataset, bbox, "standalone_dem", outputDir || mock.workspace?.root || "C:\\InSAR"),
    report: mockReport(),
  };
}

export async function runDemDownload(
  outputDir = "",
  dataset = "COP30",
  keySource = "auto",
  convert = true,
): Promise<RunSummaryResult> {
  if (hasBridge()) return api().run_dem_download(outputDir, dataset, keySource, convert);
  const plan = await planDemDownload(outputDir, dataset);
  if (!plan.ok) return plan;
  if (!convert) {
    return {
      ok: true,
      summary_line: "1 downloaded, 0 skipped, 0 failed, 0 interrupted",
      total: 1,
      succeeded: 1,
      skipped: 0,
      failed: 0,
      interrupted: 0,
      has_failures: false,
      results_path: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\dem_download_results.csv`,
      results: [
        {
          region_safe_name: mock.region?.safe_name ?? "region",
          dataset,
          outcome: "success",
          bytes_written: 1024,
          message: "mock DEM ok",
        },
      ],
      raw_dem_path: String(plan.plan.raw_dem_path ?? ""),
      ellipsoid_dem_path: "",
      sarscape_ready_dem_path: "",
    };
  }
  const conversion = await runDemConversion(outputDir);
  return {
    ok: true,
    summary_line: `下载：1 downloaded, 0 skipped, 0 failed, 0 interrupted；转换：${
      conversion.ok ? conversion.summary_line : "未执行"
    }`,
    total: 1,
    succeeded: 1,
    skipped: 0,
    failed: 0,
    interrupted: 0,
    has_failures: conversion.ok ? conversion.has_failures : true,
    results_path: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\dem_download_results.csv`,
    results: [
      {
        region_safe_name: mock.region?.safe_name ?? "region",
        dataset,
        outcome: "success",
        bytes_written: 1024,
        message: "mock DEM ok",
      },
    ],
    download: {
      summary_line: "1 downloaded, 0 skipped, 0 failed, 0 interrupted",
      results_path: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\dem_download_results.csv`,
    },
    conversion: conversion.ok ? conversion : null,
    conversion_results_path: conversion.ok ? conversion.results_path : "",
    raw_dem_path: String(plan.plan.raw_dem_path ?? ""),
    ellipsoid_dem_path: String(plan.plan.ellipsoid_dem_path ?? ""),
    sarscape_ready_dem_path: String(plan.plan.sarscape_ready_dem_path ?? ""),
  };
}

export async function runDemDownloadBbox(
  west: number,
  east: number,
  south: number,
  north: number,
  outputDir = "",
  dataset = "COP30",
  keySource = "auto",
  convert = true,
): Promise<RunSummaryResult> {
  if (hasBridge()) {
    return api().run_dem_download_bbox(west, east, south, north, outputDir, dataset, keySource, convert);
  }
  const plan = await planDemDownloadBbox(west, east, south, north, outputDir, dataset);
  if (!plan.ok) return plan;
  if (!convert) {
    return {
      ok: true,
      summary_line: "1 downloaded, 0 skipped, 0 failed, 0 interrupted",
      total: 1,
      succeeded: 1,
      skipped: 0,
      failed: 0,
      interrupted: 0,
      has_failures: false,
      results_path: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\dem_download_results.csv`,
      results: [
        {
          region_safe_name: "standalone_dem",
          dataset,
          outcome: "success",
          bytes_written: 1024,
          message: "mock DEM ok",
        },
      ],
      raw_dem_path: String(plan.plan.raw_dem_path ?? ""),
      ellipsoid_dem_path: "",
      sarscape_ready_dem_path: "",
    };
  }
  const conversion = await runDemConversionBbox(west, east, south, north, outputDir, dataset);
  return {
    ok: true,
    summary_line: `下载：1 downloaded, 0 skipped, 0 failed, 0 interrupted；转换：${
      conversion.ok ? conversion.summary_line : "未执行"
    }`,
    total: 1,
    succeeded: 1,
    skipped: 0,
    failed: 0,
    interrupted: 0,
    has_failures: conversion.ok ? conversion.has_failures : true,
    results_path: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\dem_download_results.csv`,
    results: [
      {
        region_safe_name: "standalone_dem",
        dataset,
        outcome: "success",
        bytes_written: 1024,
        message: "mock DEM ok",
      },
    ],
    download: {
      summary_line: "1 downloaded, 0 skipped, 0 failed, 0 interrupted",
      results_path: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\dem_download_results.csv`,
    },
    conversion: conversion.ok ? conversion : null,
    conversion_results_path: conversion.ok ? conversion.results_path : "",
    raw_dem_path: String(plan.plan.raw_dem_path ?? ""),
    ellipsoid_dem_path: String(plan.plan.ellipsoid_dem_path ?? ""),
    sarscape_ready_dem_path: String(plan.plan.sarscape_ready_dem_path ?? ""),
  };
}

export async function planGacosRequest(outputDir = ""): Promise<PlanReportResult> {
  if (hasBridge()) return api().plan_gacos_request(outputDir);
  if (!mock.region?.has_aoi) {
    return { ok: false, error: "请先在『区域 AOI』设置处理范围（bbox）", code: "AOI001" };
  }
  if (!mock.region.scene_count) {
    return { ok: false, error: "GACOS 需要场景日期，请先导入影像", code: "GAC001" };
  }
  return {
    ok: true,
    plan: {
      region_safe_name: mock.region.safe_name,
      unique_dates: ["2024-03-12", "2024-03-24"],
      processing_bbox: mock.region.bbox,
      buffer_degrees: 0.05,
      batches: [{ dates: ["2024-03-12", "2024-03-24"] }],
      output_directory: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\${mock.region.safe_name}\\GACOS\\requests`,
    },
    report: mockReport(),
  };
}

export async function planDemConversion(outputDir = ""): Promise<ConvertResult> {
  if (hasBridge()) return api().plan_dem_conversion(outputDir);
  if (!mock.region?.has_aoi) {
    return { ok: false, error: "请先在『区域 AOI』设置处理范围（bbox）", code: "AOI001" };
  }
  const dataset = mockDataset;
  const safe = mock.region.safe_name;
  const root = mock.workspace?.root ?? "C:\\InSAR";
  const source = mockSourceDatum(dataset);
  const requires = source !== "WGS84_ELLIPSOID";
  const geoid = !requires ? null : source === "EGM96" ? "EGM96" : "EGM2008";
  const ds = dataset.toLowerCase();

  const steps = requires
    ? [
        {
          step_type: "VERTICAL_DATUM_CONVERSION",
          description: `${source} 正高 → WGS84 椭球高（geoid: ${geoid}）`,
          requires_geoid: true,
          geoid_model: geoid,
        },
        { step_type: "COPY_TO_SARSCAPE_READY", description: "导出 SARscape ENVI _dem + .hdr" },
      ]
    : [
        {
          step_type: "COPY_TO_SARSCAPE_READY",
          description: "该 DEM 已是椭球高，直接导出 SARscape ENVI _dem + .hdr",
        },
      ];

  const auto: ConversionAuto = {
    requires_conversion: requires,
    requires_geoid: requires,
    source,
    target: "WGS84_ELLIPSOID",
    geoid_model: geoid,
    message: requires
      ? `检测到高程基准为 ${source}（正高），将自动转换为 WGS84_ELLIPSOID，采用大地水准面模型 ${geoid}（系统自动选择）。`
      : `该 DEM 高程基准已为 ${source}（椭球高），无需垂直基准转换，将导出 SARscape ENVI _dem + .hdr。`,
  };

  return {
    ok: true,
    dataset,
    auto,
    plan: {
      dataset,
      source_vertical_datum: source,
      target_vertical_datum: "WGS84_ELLIPSOID",
      requires_conversion: requires,
      requires_geoid: requires,
      raw_dem_path: `${root}\\${demSourceStem(dataset)}.tif`,
      ellipsoid_dem_path: `${root}\\${demSourceStem(dataset)}_ellipsoid.tif`,
      sarscape_ready_dem_path: `${root}\\${demSourceStem(dataset)}_dem`,
      steps,
    },
    report: mockReport(),
  };
}

export async function planLocalDemConversion(
  inputPath: string,
  outputDir = "",
  sourceVerticalDatum = "auto",
): Promise<ConvertResult> {
  if (hasBridge()) {
    return api().plan_local_dem_conversion(inputPath, outputDir, sourceVerticalDatum);
  }
  if (!inputPath.trim()) return { ok: false, error: "请选择本地 DEM 文件", code: "DEM004" };
  const safe = inputPath
    .split(/[\\/]/)
    .pop()
    ?.replace(/\.[^.]+$/, "")
    .replace(/[^A-Za-z0-9_]+/g, "_")
    .toLowerCase() || "local_dem";
  const source =
    sourceVerticalDatum === "auto"
      ? inputPath.toLowerCase().includes("ellipsoid")
        ? "WGS84_ELLIPSOID"
        : inputPath.toLowerCase().includes("egm2008")
          ? "EGM2008"
          : "EGM96"
      : sourceVerticalDatum;
  const requires = source !== "WGS84_ELLIPSOID";
  const geoid = !requires ? null : source === "EGM96" ? "EGM96" : "EGM2008";
  const root = outputDir || mock.region?.root || mock.project?.root || mock.workspace?.root || "C:\\InSAR";
  return {
    ok: true,
    dataset: "USER_LOCAL",
    auto: {
      requires_conversion: requires,
      requires_geoid: requires,
      source,
      target: "WGS84_ELLIPSOID",
      geoid_model: geoid,
      message: requires
        ? `检测到或选择高程基准为 ${source}，将转换为 WGS84_ELLIPSOID。`
        : "该 DEM 已按椭球高处理，将导出 SARscape ENVI _dem + .hdr。",
    },
    plan: {
      dataset: "USER_LOCAL",
      raw_dem_path: inputPath,
      ellipsoid_dem_path: `${root}\\${safe}_ellipsoid.tif`,
      sarscape_ready_dem_path: `${root}\\${safe}_dem`,
      steps: requires
        ? [
            {
              step_type: "VERTICAL_DATUM_CONVERSION",
              description: `${source} → WGS84_ELLIPSOID`,
              requires_geoid: true,
              geoid_model: geoid,
            },
            { step_type: "COPY_TO_SARSCAPE_READY", description: "导出 SARscape ENVI _dem + .hdr" },
          ]
        : [{ step_type: "COPY_TO_SARSCAPE_READY", description: "导出 SARscape ENVI _dem + .hdr" }],
    },
    report: mockReport(),
  };
}

export async function planDemConversionBbox(
  west: number,
  east: number,
  south: number,
  north: number,
  outputDir = "",
  dataset = "COP30",
): Promise<ConvertResult> {
  if (hasBridge()) {
    return api().plan_dem_conversion_bbox(west, east, south, north, outputDir, dataset);
  }
  const dem = await planDemDownloadBbox(west, east, south, north, outputDir, dataset);
  if (!dem.ok) return dem;
  const source = mockSourceDatum(dataset);
  const requires = source !== "WGS84_ELLIPSOID";
  const geoid = !requires ? null : source === "EGM96" ? "EGM96" : "EGM2008";
  return {
    ok: true,
    dataset,
    auto: {
      requires_conversion: requires,
      requires_geoid: requires,
      source,
      target: "WGS84_ELLIPSOID",
      geoid_model: geoid,
      message: requires
        ? `检测到高程基准为 ${source}（正高），将自动转换为 WGS84_ELLIPSOID，采用大地水准面模型 ${geoid}（系统自动选择）。`
        : `该 DEM 高程基准已为 ${source}（椭球高），无需垂直基准转换，将导出 SARscape ENVI _dem + .hdr。`,
    },
    plan: {
      ...mockDemPlan(
        dataset,
        { west, east, south, north, crs: "EPSG:4326" },
        "standalone_dem",
        outputDir || mock.workspace?.root || "C:\\InSAR",
      ),
      requires_conversion: requires,
      requires_geoid: requires,
      steps: requires
        ? [
            {
              step_type: "VERTICAL_DATUM_CONVERSION",
              description: `${source} 正高 → WGS84 椭球高（geoid: ${geoid}）`,
              requires_geoid: true,
              geoid_model: geoid,
            },
            { step_type: "COPY_TO_SARSCAPE_READY", description: "导出 SARscape ENVI _dem + .hdr" },
          ]
        : [
            {
              step_type: "COPY_TO_SARSCAPE_READY",
              description: "该 DEM 已是椭球高，直接导出 SARscape ENVI _dem + .hdr",
            },
          ],
    },
    report: mockReport(),
  };
}

export async function runDemConversion(outputDir = ""): Promise<RunSummaryResult> {
  if (hasBridge()) return api().run_dem_conversion(outputDir);
  const plan = await planDemConversion(outputDir);
  if (!plan.ok) return plan;
  return {
    ok: true,
    summary_line: plan.auto.requires_conversion
      ? "1 converted, 0 copied, 0 skipped, 0 failed"
      : "0 converted, 1 copied, 0 skipped, 0 failed",
    total: 1,
    succeeded: plan.auto.requires_conversion ? 1 : 0,
    copied: plan.auto.requires_conversion ? 0 : 1,
    skipped: 0,
    failed: 0,
    has_failures: false,
    results_path: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\dem_convert_results.csv`,
    results: [
      {
        region_safe_name: mock.region?.safe_name ?? "region",
        dataset: plan.dataset,
        outcome: plan.auto.requires_conversion ? "success" : "copied",
        output_path: String(plan.plan.sarscape_ready_dem_path ?? ""),
        message: "mock conversion ok",
      },
    ],
  };
}

export async function runLocalDemConversion(
  inputPath: string,
  outputDir = "",
  sourceVerticalDatum = "auto",
  outputMode: "ellipsoid" | "sarscape" = "sarscape",
): Promise<RunSummaryResult> {
  if (hasBridge()) {
    return api().run_local_dem_conversion(inputPath, outputDir, sourceVerticalDatum, outputMode);
  }
  const plan = await planLocalDemConversion(inputPath, outputDir, sourceVerticalDatum);
  if (!plan.ok) return plan;
  return {
    ok: true,
    summary_line: plan.auto.requires_conversion
      ? "1 converted, 0 copied, 0 skipped, 0 failed"
      : "0 converted, 1 copied, 0 skipped, 0 failed",
    total: 1,
    succeeded: plan.auto.requires_conversion ? 1 : 0,
    copied: plan.auto.requires_conversion ? 0 : 1,
    skipped: 0,
    failed: 0,
    has_failures: false,
    results_path: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\dem_convert_results.csv`,
    raw_dem_path: String(plan.plan.raw_dem_path ?? inputPath),
    ellipsoid_dem_path: String(plan.plan.ellipsoid_dem_path ?? ""),
    sarscape_ready_dem_path: outputMode === "ellipsoid" ? "" : String(plan.plan.sarscape_ready_dem_path ?? ""),
    results: [
      {
        region_safe_name: mock.region?.safe_name ?? "local_dem",
        dataset: "USER_LOCAL",
        outcome: plan.auto.requires_conversion ? "success" : "copied",
        output_path:
          outputMode === "ellipsoid"
            ? String(plan.plan.ellipsoid_dem_path ?? "")
            : String(plan.plan.sarscape_ready_dem_path ?? ""),
        message: "mock local DEM conversion ok",
      },
    ],
  };
}

export async function runDemConversionBbox(
  west: number,
  east: number,
  south: number,
  north: number,
  outputDir = "",
  dataset = "COP30",
): Promise<RunSummaryResult> {
  if (hasBridge()) {
    return api().run_dem_conversion_bbox(west, east, south, north, outputDir, dataset);
  }
  const plan = await planDemConversionBbox(west, east, south, north, outputDir, dataset);
  if (!plan.ok) return plan;
  return {
    ok: true,
    summary_line: plan.auto.requires_conversion
      ? "1 converted, 0 copied, 0 skipped, 0 failed"
      : "0 converted, 1 copied, 0 skipped, 0 failed",
    total: 1,
    succeeded: plan.auto.requires_conversion ? 1 : 0,
    copied: plan.auto.requires_conversion ? 0 : 1,
    skipped: 0,
    failed: 0,
    has_failures: false,
    results_path: `${outputDir || mock.workspace?.root || "C:\\InSAR"}\\dem_convert_results.csv`,
    results: [
      {
        region_safe_name: "standalone_dem",
        dataset,
        outcome: plan.auto.requires_conversion ? "success" : "copied",
        output_path: String(plan.plan.sarscape_ready_dem_path ?? ""),
        message: "mock conversion ok",
      },
    ],
  };
}

export async function getCredentialStatus(): Promise<CredentialStatus> {
  if (hasBridge()) return api().get_credential_status();
  return mockCredentials;
}

export async function checkEarthdataAuth(): Promise<EarthdataAuthCheck | ApiError> {
  if (hasBridge()) return api().check_earthdata_auth();
  const configured = !["none", "unavailable"].includes(mockCredentials.earthdata);
  return {
    ok: true,
    configured,
    status: configured ? "valid" : "missing",
    message: configured ? "Earthdata/ASF 凭据正常。" : "未保存 Earthdata/ASF 凭据。",
  };
}

export async function saveEarthdataToken(token: string): Promise<SimpleOk> {
  if (hasBridge()) {
    const res = await api().save_earthdata_token(token);
    if (res.ok) notifyContextChanged();
    return res;
  }
  if (!token.trim()) return { ok: false, error: "Token 不能为空", code: "DL004" };
  mockCredentials = { ...mockCredentials, earthdata: "token" };
  notifyContextChanged();
  return { ok: true, status: mockCredentials };
}

export async function saveEarthdataLogin(username: string, password: string): Promise<SimpleOk> {
  if (hasBridge()) {
    const res = await api().save_earthdata_login(username, password);
    if (res.ok) notifyContextChanged();
    return res;
  }
  if (!username.trim() || !password) {
    return { ok: false, error: "用户名和密码都不能为空", code: "DL004" };
  }
  mockCredentials = { ...mockCredentials, earthdata: `login:${username.trim()[0] ?? "*"}***` };
  notifyContextChanged();
  return { ok: true, status: mockCredentials };
}

export async function clearEarthdataCredentials(): Promise<SimpleOk> {
  if (hasBridge()) {
    const res = await api().clear_earthdata_credentials();
    if (res.ok) notifyContextChanged();
    return res;
  }
  mockCredentials = { ...mockCredentials, earthdata: "none" };
  notifyContextChanged();
  return { ok: true, removed: true, status: mockCredentials };
}

export async function saveOpentopographyKey(apiKey: string): Promise<SimpleOk> {
  if (hasBridge()) {
    const res = await api().save_opentopography_key(apiKey);
    if (res.ok) notifyContextChanged();
    return res;
  }
  if (!apiKey.trim()) return { ok: false, error: "API Key 不能为空", code: "DEM005" };
  mockCredentials = { ...mockCredentials, opentopography: "set" };
  notifyContextChanged();
  return { ok: true, status: mockCredentials };
}

export async function clearOpentopographyKey(): Promise<SimpleOk> {
  if (hasBridge()) {
    const res = await api().clear_opentopography_key();
    if (res.ok) notifyContextChanged();
    return res;
  }
  mockCredentials = { ...mockCredentials, opentopography: "none" };
  notifyContextChanged();
  return { ok: true, removed: true, status: mockCredentials };
}

export async function saveGacosEmail(email: string): Promise<SimpleOk> {
  if (hasBridge()) {
    const res = await api().save_gacos_email(email);
    if (res.ok) notifyContextChanged();
    return res;
  }
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
    return { ok: false, error: "邮箱格式不正确", code: "GAC003" };
  }
  const [local, domain] = email.trim().split("@");
  mockCredentials = { ...mockCredentials, gacos: `${local[0] ?? "*"}***@${domain}` };
  notifyContextChanged();
  return { ok: true, status: mockCredentials };
}

export async function clearGacosEmail(): Promise<SimpleOk> {
  if (hasBridge()) {
    const res = await api().clear_gacos_email();
    if (res.ok) notifyContextChanged();
    return res;
  }
  mockCredentials = { ...mockCredentials, gacos: "none" };
  notifyContextChanged();
  return { ok: true, removed: true, status: mockCredentials };
}

export async function generateReport(outputDir = ""): Promise<ReportResult> {
  if (hasBridge()) return api().generate_report(outputDir);
  if (!mock.region) return { ok: false, error: "请先创建或选择区域", code: "GUI002" };
  const dir = mockReportsDir();
  const safe = mock.region.safe_name;
  const included: string[] = [];
  if (mock.region.scene_count > 0) included.push("scene_check");
  if (mock.region.has_aoi) included.push("dem_planning", "dem_conversion");
  if (mock.region.has_aoi && mock.region.scene_count > 0) included.push("gacos_planning");
  return {
    ok: true,
    included,
    report: {
      title: `InSAR data preparation report: ${safe}`,
      created_at: new Date().toISOString(),
      ...(mockReport() as object),
    },
    reports_dir: dir,
    paths: {
      json: `${dir}\\${safe}_data_preparation_report.json`,
      markdown: `${dir}\\${safe}_data_preparation_report.md`,
      html: `${dir}\\${safe}_data_preparation_report.html`,
      manifest: `${dir}\\${safe}_manifest.csv`,
      warnings: `${dir}\\${safe}_warnings.csv`,
    },
  };
}
