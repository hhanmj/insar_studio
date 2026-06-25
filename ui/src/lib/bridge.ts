// Thin wrapper around the pywebview JS<->Python bridge.
//
// In the packaged desktop app the Python side exposes an `Api` object as
// `window.pywebview.api.*` (every method returns a Promise). When the frontend
// runs in a plain browser (vite dev, or the headless screenshot), pywebview is
// absent, so we fall back to mock data so the UI is always previewable. The mock
// keeps a tiny shared "current region" context so the panels feel connected.

export type AppInfo = { name: string; version: string; offline: boolean };
export type ApiError = { ok: false; error: string; code: string | null };
export type Json = Record<string, unknown>;

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
  has_aoi: boolean;
  bbox: Bbox | null;
  scene_count: number;
};
export type Context = {
  ok: true;
  workspace: { workspace_id: string; root: string; name: string } | null;
  project: { project_id: string; name: string; safe_name: string } | null;
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
  orbit_direction: string;
  has_url: boolean;
};

export type AoiOk = {
  ok: true;
  aoi: Json;
  region_id: string;
  region_name: string;
};
export type ScenesOk = {
  ok: true;
  scenes: SceneRow[];
  duplicates: string[];
  errors: { line: string; error: string }[];
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

export type WorkspaceResult = WorkspaceOk | ApiError;
export type ProjectResult = ProjectOk | ApiError;
export type RegionResult = RegionOk | ApiError;
export type AoiResult = AoiOk | ApiError;
export type ScenesResult = ScenesOk | ApiError;
export type CheckResult = CheckOk | ApiError;
export type PlanResult = PlanOk | ApiError;
export type PlanReportResult = PlanReportOk | ApiError;
export type ConvertResult = ConvertOk | ApiError;
export type ReportResult = ReportOk | ApiError;

type PyApi = {
  get_app_info: () => Promise<AppInfo>;
  get_context: () => Promise<Context>;
  create_workspace: (root: string, name?: string | null) => Promise<WorkspaceResult>;
  add_project: (name: string) => Promise<ProjectResult>;
  select_project: (projectId: string) => Promise<ProjectResult>;
  add_region: (name: string) => Promise<RegionResult>;
  set_region_aoi_bbox: (
    west: number,
    east: number,
    south: number,
    north: number,
  ) => Promise<AoiResult>;
  set_region_aoi_file: (path: string) => Promise<AoiResult>;
  import_scenes_text: (text: string) => Promise<ScenesResult>;
  import_scenes_file: (path: string) => Promise<ScenesResult>;
  check_scenes: () => Promise<CheckResult>;
  plan_asf_download: (outputDir?: string) => Promise<PlanResult>;
  plan_dem_download: (outputDir?: string, dataset?: string) => Promise<PlanReportResult>;
  plan_gacos_request: (outputDir?: string) => Promise<PlanReportResult>;
  plan_dem_conversion: (outputDir?: string) => Promise<ConvertResult>;
  set_dem_dataset: (dataset: string) => Promise<{ ok: boolean; dataset?: string; error?: string; code?: string }>;
  get_credential_status: () => Promise<CredentialStatus>;
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

// --------------------------------------------------------------- mock state
function mockSafeName(value: string): string | null {
  const safe = value
    .trim()
    .replace(/[^A-Za-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return safe || null;
}

const MOCK_BBOX: Bbox = {
  west: 110.22,
  east: 110.52,
  south: 30.92,
  north: 31.14,
  crs: "EPSG:4326",
};

// Browser-preview only: seed a demo region so every panel is self-demoing
// without clicking through. The real pywebview bridge always starts empty.
const mock: {
  workspace: { workspace_id: string; root: string; name: string } | null;
  project: { project_id: string; name: string; safe_name: string } | null;
  region: ContextRegion | null;
} = {
  workspace: {
    workspace_id: "ws_preview",
    root: "C:\\InSAR\\workspaces\\三峡示范",
    name: "三峡示范工作区",
  },
  project: {
    project_id: "proj_badong_2024",
    name: "badong_2024",
    safe_name: "badong_2024",
  },
  region: {
    region_id: "region_shiliushubao",
    name: "shiliushubao",
    safe_name: "shiliushubao",
    has_aoi: true,
    bbox: MOCK_BBOX,
    scene_count: 3,
  },
};

let mockDataset = "COP30";

function mockSourceDatum(ds: string): string {
  if (ds.endsWith("_ELLIPSOIDAL")) return "WGS84_ELLIPSOID";
  if (ds === "COP30" || ds === "COP90") return "EGM2008";
  return "EGM96";
}

function mockReportsDir(): string {
  const root = mock.workspace?.root ?? "C:\\InSAR\\workspaces\\preview";
  const safe = mock.region?.safe_name ?? "region";
  return `${root}\\${safe}\\07_reports`;
}

// ------------------------------------------------------------------- app/ctx
export async function getAppInfo(): Promise<AppInfo> {
  if (hasBridge()) return api().get_app_info();
  return { name: "InSAR Assistant", version: "0.16.0", offline: true };
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
  if (hasBridge()) return api().set_dem_dataset(dataset);
  mockDataset = dataset;
  return { ok: true, dataset };
}

// ------------------------------------------------------------ workspace tree
export async function createWorkspace(
  root: string,
  name?: string,
): Promise<WorkspaceResult> {
  if (hasBridge()) return api().create_workspace(root, name ?? null);
  const trimmed = root.trim();
  if (!trimmed) return { ok: false, error: "工作区根路径不能为空", code: "GUI003" };
  mock.workspace = { workspace_id: "ws_preview", root: trimmed, name: name ?? "" };
  mock.project = null;
  mock.region = null;
  return { ok: true, workspace_id: "ws_preview", root: trimmed, projects: [] };
}

export async function addProject(name: string): Promise<ProjectResult> {
  if (hasBridge()) return api().add_project(name);
  const safe = mockSafeName(name);
  if (!safe) {
    return { ok: false, error: "项目名至少需包含一个字母、数字或下划线", code: "GUI003" };
  }
  mock.project = { project_id: `proj_${safe}`, name, safe_name: safe };
  mock.region = null;
  return { ok: true, project_id: `proj_${safe}`, name, safe_name: safe };
}

export async function selectProject(projectId: string): Promise<ProjectResult> {
  if (hasBridge()) return api().select_project(projectId);
  const safe = projectId.replace(/^proj_/, "");
  mock.project = { project_id: projectId, name: safe, safe_name: safe };
  return { ok: true, project_id: projectId, name: safe, safe_name: safe };
}

export async function addRegion(name: string): Promise<RegionResult> {
  if (hasBridge()) return api().add_region(name);
  const safe = mockSafeName(name);
  if (!safe) {
    return { ok: false, error: "区域名至少需包含一个字母、数字或下划线", code: "GUI003" };
  }
  mock.region = {
    region_id: `region_${safe}`,
    name,
    safe_name: safe,
    has_aoi: false,
    bbox: null,
    scene_count: 0,
  };
  return { ok: true, region_id: `region_${safe}`, name, safe_name: safe };
}

// --------------------------------------------------------------------- AOI
export async function setRegionAoiBbox(
  west: number,
  east: number,
  south: number,
  north: number,
): Promise<AoiResult> {
  if (hasBridge()) return api().set_region_aoi_bbox(west, east, south, north);
  if (!mock.region) return { ok: false, error: "请先创建或选择区域", code: "GUI002" };
  if (!(west < east)) {
    return { ok: false, error: "west must be strictly less than east", code: "AOI001" };
  }
  if (!(south < north)) {
    return { ok: false, error: "south must be strictly less than north", code: "AOI001" };
  }
  const bbox: Bbox = { west, east, south, north, crs: "EPSG:4326" };
  mock.region = { ...mock.region, has_aoi: true, bbox };
  return {
    ok: true,
    aoi: { source: "MANUAL_BBOX", role: "PROCESSING_AOI", bbox },
    region_id: mock.region.region_id,
    region_name: mock.region.name,
  };
}

export async function setRegionAoiFile(path: string): Promise<AoiResult> {
  if (hasBridge()) return api().set_region_aoi_file(path);
  if (!mock.region) return { ok: false, error: "请先创建或选择区域", code: "GUI002" };
  if (!path.trim()) return { ok: false, error: "请提供矢量文件路径", code: "AOI001" };
  mock.region = { ...mock.region, has_aoi: true, bbox: MOCK_BBOX };
  return {
    ok: true,
    aoi: { source: "VECTOR_FILE", role: "PROCESSING_AOI", bbox: MOCK_BBOX, geometry_path: path },
    region_id: mock.region.region_id,
    region_name: mock.region.name,
  };
}

// ------------------------------------------------------------------ SCENES
function mockScene(i: number): SceneRow {
  const day = 12 + i * 12;
  return {
    scene_id: `S1A_IW_SLC__1SDV_202403${day}T223805_202403${day}T223832_0529${14 + i}_0667A5`,
    platform: "S1A",
    product_type: "SLC",
    beam_mode: "IW",
    polarization: "DV",
    acquisition_datetime: `2024-03-${day}T22:38:05Z`,
    absolute_orbit: 52914 + i * 175,
    relative_orbit: null,
    orbit_direction: "UNKNOWN",
    has_url: false,
  };
}

export async function importScenesText(text: string): Promise<ScenesResult> {
  if (hasBridge()) return api().import_scenes_text(text);
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) {
    return { ok: false, error: "请粘贴至少一个 Sentinel-1 IW SLC 颗粒名或下载链接", code: "ASF001" };
  }
  const valid = lines.filter((l) => /S1[ABCD]_IW_SLC/i.test(l));
  const errors = lines
    .filter((l) => !/S1[ABCD]_IW_SLC/i.test(l))
    .map((line) => ({ line, error: "不是 Sentinel-1 IW SLC 颗粒名" }));
  if (!valid.length) {
    return { ok: false, error: "未能解析出任何有效的 Sentinel-1 IW SLC 场景", code: "ASF001" };
  }
  const scenes = valid.map((_, i) => mockScene(i));
  if (mock.region) mock.region = { ...mock.region, scene_count: scenes.length };
  return { ok: true, scenes, duplicates: [], errors };
}

export async function importScenesFile(path: string): Promise<ScenesResult> {
  if (hasBridge()) return api().import_scenes_file(path);
  if (!path.trim()) return { ok: false, error: "请提供购物车文件路径", code: "ASF001" };
  const scenes = [mockScene(0), mockScene(1), mockScene(2)];
  if (mock.region) mock.region = { ...mock.region, scene_count: scenes.length };
  return { ok: true, scenes, duplicates: [], errors: [] };
}

export async function checkScenes(): Promise<CheckResult> {
  if (hasBridge()) return api().check_scenes();
  const n = mock.region?.scene_count ?? 0;
  if (!n) return { ok: false, error: "请先创建或选择区域", code: "GUI002" };
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

// ---------------------------------------------------------------- DOWNLOAD
function mockAsfPlan(): Json {
  const n = mock.region?.scene_count ?? 0;
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
    region_safe_name: mock.region?.safe_name ?? "region",
    scene_count: n,
    planned_count: 0,
    missing_url_count: n,
    credential_required: true,
    slc_directory: `${mock.workspace?.root ?? "C:\\InSAR"}\\02_slc`,
    items,
  };
}

function mockDemPlan(dataset: string): Json {
  const safe = mock.region?.safe_name ?? "region";
  const b = mock.region?.bbox ?? MOCK_BBOX;
  const root = mock.workspace?.root ?? "C:\\InSAR";
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
    raw_dem_path: `${root}\\${safe}\\04_dem\\raw\\${safe}_${dataset.toLowerCase()}_raw.tif`,
    ellipsoid_dem_path: `${root}\\${safe}\\04_dem\\ellipsoid\\${safe}_${dataset.toLowerCase()}_ellipsoid.tif`,
    sarscape_ready_dem_path: `${root}\\${safe}\\06_sarscape_ready\\${safe}_dem.tif`,
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

export async function planAsfDownload(outputDir = ""): Promise<PlanResult> {
  if (hasBridge()) return api().plan_asf_download(outputDir);
  if (!mock.region) return { ok: false, error: "请先创建或选择区域", code: "GUI002" };
  if (!mock.region.scene_count) {
    return { ok: false, error: "请先在『影像核查』导入场景", code: "ASF001" };
  }
  return { ok: true, plan: mockAsfPlan() };
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
        { step_type: "COPY_TO_SARSCAPE_READY", description: "复制到 SARscape 就绪目录（*_dem.tif）" },
      ]
    : [
        {
          step_type: "COPY_TO_SARSCAPE_READY",
          description: "该 DEM 已是椭球高，直接复制为 SARscape 就绪 DEM（*_dem.tif）",
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
      : `该 DEM 高程基准已为 ${source}（椭球高），无需转换，直接复制为 SARscape 就绪 DEM。`,
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
      raw_dem_path: `${root}\\${safe}\\04_dem\\raw\\${safe}_${ds}_raw.tif`,
      ellipsoid_dem_path: `${root}\\${safe}\\04_dem\\ellipsoid\\${safe}_${ds}_ellipsoid.tif`,
      sarscape_ready_dem_path: `${root}\\${safe}\\06_sarscape_ready\\${safe}_dem.tif`,
      steps,
    },
    report: mockReport(),
  };
}

export async function getCredentialStatus(): Promise<CredentialStatus> {
  if (hasBridge()) return api().get_credential_status();
  return { ok: true, earthdata: "none", opentopography: "none", gacos: "none" };
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
