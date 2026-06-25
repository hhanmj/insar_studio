import { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FolderPlus,
  FolderTree,
  Loader2,
  MapPinned,
  Plug,
  PlugZap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  addProject,
  addRegion,
  createWorkspace,
  hasBridge,
  selectProject,
  type ProjectOk,
  type RegionOk,
  type WorkspaceOk,
} from "@/lib/bridge";

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
      {children}
    </label>
  );
}

function ErrorNote({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{text}</span>
    </div>
  );
}

export function Workspace() {
  const bridged = hasBridge();

  const [root, setRoot] = useState("C:\\InSAR\\workspaces\\三峡示范");
  const [wsName, setWsName] = useState("三峡示范工作区");
  const [workspace, setWorkspace] = useState<WorkspaceOk | null>(null);
  const [wsBusy, setWsBusy] = useState(false);
  const [wsError, setWsError] = useState<string | null>(null);

  const [projectName, setProjectName] = useState("");
  const [projects, setProjects] = useState<ProjectOk[]>([]);
  const [pBusy, setPBusy] = useState(false);
  const [pError, setPError] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const [regionName, setRegionName] = useState("");
  const [regionsByProject, setRegionsByProject] = useState<
    Record<string, RegionOk[]>
  >({});
  const [rBusy, setRBusy] = useState(false);
  const [rError, setRError] = useState<string | null>(null);

  const selectedProject =
    projects.find((p) => p.project_id === selectedProjectId) ?? null;
  const regions = selectedProjectId
    ? (regionsByProject[selectedProjectId] ?? [])
    : [];

  async function onCreateWorkspace() {
    setWsBusy(true);
    setWsError(null);
    try {
      const res = await createWorkspace(root, wsName);
      if (res.ok) {
        setWorkspace(res);
        setProjects([]);
        setSelectedProjectId(null);
        setRegionsByProject({});
        setPError(null);
        setRError(null);
      } else {
        setWsError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setWsError(String(e));
    } finally {
      setWsBusy(false);
    }
  }

  async function onAddProject() {
    if (!projectName.trim()) return;
    setPBusy(true);
    setPError(null);
    try {
      const res = await addProject(projectName.trim());
      if (res.ok) {
        setProjects((prev) => [...prev, res]);
        setSelectedProjectId(res.project_id);
        setRegionsByProject((prev) => ({ ...prev, [res.project_id]: [] }));
        setProjectName("");
        setRError(null);
      } else {
        setPError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setPError(String(e));
    } finally {
      setPBusy(false);
    }
  }

  async function onSelectProject(p: ProjectOk) {
    if (p.project_id === selectedProjectId) return;
    setRError(null);
    const res = await selectProject(p.project_id);
    if (res.ok) {
      setSelectedProjectId(p.project_id);
    } else {
      setPError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    }
  }

  async function onAddRegion() {
    if (!selectedProjectId || !regionName.trim()) return;
    setRBusy(true);
    setRError(null);
    try {
      const res = await addRegion(regionName.trim());
      if (res.ok) {
        setRegionsByProject((prev) => ({
          ...prev,
          [selectedProjectId]: [...(prev[selectedProjectId] ?? []), res],
        }));
        setRegionName("");
      } else {
        setRError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setRError(String(e));
    } finally {
      setRBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">工作区</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Workspace ▸ Project ▸ Region 层级管理 · 直连 insar_prep 核心
          </p>
        </div>
        <Badge variant={bridged ? "success" : "warning"}>
          {bridged ? (
            <>
              <PlugZap className="h-3.5 w-3.5" />
              已连接核心
            </>
          ) : (
            <>
              <Plug className="h-3.5 w-3.5" />
              预览模式（mock）
            </>
          )}
        </Badge>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                1
              </span>
              <CardTitle>创建工作区</CardTitle>
            </div>
            <CardDescription>逻辑根路径，不会立即在磁盘创建文件</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <FieldLabel>工作区根路径</FieldLabel>
              <Input
                value={root}
                onChange={(e) => setRoot(e.target.value)}
                placeholder="C:\\InSAR\\workspaces\\my_area"
                spellCheck={false}
              />
            </div>
            <div>
              <FieldLabel>显示名称（可选）</FieldLabel>
              <Input
                value={wsName}
                onChange={(e) => setWsName(e.target.value)}
                placeholder="三峡示范工作区"
              />
            </div>

            {wsError && <ErrorNote text={wsError} />}

            <div className="flex items-center gap-3">
              <Button onClick={onCreateWorkspace} disabled={wsBusy}>
                {wsBusy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <FolderTree className="h-4 w-4" />
                )}
                {workspace ? "重新创建" : "创建工作区"}
              </Button>
              {workspace && (
                <span className="inline-flex items-center gap-1.5 text-sm text-success">
                  <CheckCircle2 className="h-4 w-4" />
                  已创建
                </span>
              )}
            </div>

            {workspace && (
              <div className="rounded-md border bg-muted/40 p-3 text-xs">
                <div className="flex justify-between gap-3">
                  <span className="text-muted-foreground">workspace_id</span>
                  <span className="font-mono text-foreground">
                    {workspace.workspace_id}
                  </span>
                </div>
                <div className="mt-1.5 flex justify-between gap-3">
                  <span className="text-muted-foreground">root</span>
                  <span className="truncate font-mono text-foreground">
                    {workspace.root}
                  </span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className={workspace ? "" : "opacity-60"}>
          <CardHeader>
            <div className="flex items-center gap-2">
              <span
                className={
                  "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold " +
                  (workspace
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground")
                }
              >
                2
              </span>
              <CardTitle>项目</CardTitle>
            </div>
            <CardDescription>
              在当前工作区下创建项目（点击可选中，区域将挂在其下）
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <FieldLabel>项目名称</FieldLabel>
                <Input
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onAddProject();
                  }}
                  placeholder="badong_2024"
                  disabled={!workspace || pBusy}
                  spellCheck={false}
                />
              </div>
              <Button
                onClick={onAddProject}
                disabled={!workspace || pBusy || !projectName.trim()}
              >
                {pBusy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <FolderPlus className="h-4 w-4" />
                )}
                新建项目
              </Button>
            </div>

            {pError && <ErrorNote text={pError} />}

            {projects.length === 0 ? (
              <div className="rounded-md border border-dashed py-8 text-center text-sm text-muted-foreground">
                {workspace ? "尚无项目，添加第一个吧" : "请先创建工作区"}
              </div>
            ) : (
              <div className="space-y-2">
                {projects.map((p) => {
                  const isSel = p.project_id === selectedProjectId;
                  return (
                    <button
                      key={p.project_id}
                      onClick={() => onSelectProject(p)}
                      className={
                        "flex w-full items-center justify-between rounded-md border px-3 py-2 text-left transition-colors " +
                        (isSel
                          ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                          : "bg-card hover:bg-accent")
                      }
                    >
                      <div className="flex items-center gap-2.5">
                        <FolderTree
                          className={
                            "h-4 w-4 " +
                            (isSel ? "text-primary" : "text-muted-foreground")
                          }
                        />
                        <div className="leading-tight">
                          <div className="text-sm font-medium">{p.name}</div>
                          <div className="font-mono text-[11px] text-muted-foreground">
                            {p.safe_name}
                          </div>
                        </div>
                      </div>
                      {isSel ? (
                        <Badge>当前</Badge>
                      ) : (
                        <Badge variant="neutral">
                          {(regionsByProject[p.project_id] ?? []).length} 区域
                        </Badge>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className={selectedProject ? "" : "opacity-60"}>
        <CardHeader>
          <div className="flex items-center gap-2">
            <span
              className={
                "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold " +
                (selectedProject
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground")
              }
            >
              3
            </span>
            <CardTitle>区域</CardTitle>
          </div>
          <CardDescription>
            {selectedProject
              ? `在项目「${selectedProject.name}」下创建区域（区域初始携带占位 AOI，稍后绑定）`
              : "请选择一个项目后再创建区域"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <FieldLabel>区域名称</FieldLabel>
              <Input
                value={regionName}
                onChange={(e) => setRegionName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onAddRegion();
                }}
                placeholder="shiliushubao"
                disabled={!selectedProject || rBusy}
                spellCheck={false}
              />
            </div>
            <Button
              onClick={onAddRegion}
              disabled={!selectedProject || rBusy || !regionName.trim()}
            >
              {rBusy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <MapPinned className="h-4 w-4" />
              )}
              新建区域
            </Button>
          </div>

          {rError && <ErrorNote text={rError} />}

          {regions.length === 0 ? (
            <div className="rounded-md border border-dashed py-8 text-center text-sm text-muted-foreground">
              {selectedProject ? "尚无区域，添加第一个吧" : "请先选择项目"}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {regions.map((r) => (
                <div
                  key={r.region_id}
                  className="flex items-center justify-between rounded-md border bg-card px-3 py-2"
                >
                  <div className="flex items-center gap-2.5">
                    <MapPinned className="h-4 w-4 text-primary" />
                    <div className="leading-tight">
                      <div className="text-sm font-medium">{r.name}</div>
                      <div className="font-mono text-[11px] text-muted-foreground">
                        {r.safe_name}
                      </div>
                    </div>
                  </div>
                  <Badge variant="neutral">区域</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
