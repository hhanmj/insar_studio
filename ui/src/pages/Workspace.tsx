import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  FolderCheck,
  FolderOpen,
  FolderPlus,
  Loader2,
  MapPinned,
  Play,
  Radar,
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
  BridgeBadge,
  ErrorNote,
  FieldLabel,
  PageHeader,
} from "@/components/common";
import {
  addProject,
  addRegion,
  createWorkspace,
  ensureDirectory,
  formatBridgeError,
  getTree,
  hasBridge,
  pickDirectory,
  selectProject,
  selectRegion,
  type Tree,
  type TreeProject,
  type TreeRegion,
} from "@/lib/bridge";
import { usePrepContext } from "@/lib/useContext";

const DEFAULT_ROOT = "C:\\InSAR\\projects";

function formatProjectPath(root: string, project: string, region: string) {
  const cleanRoot = root.trim().replace(/[\\/]+$/, "");
  const cleanProject = project.trim() || "project";
  const cleanRegion = region.trim() || "region";
  return `${cleanRoot}\\${cleanProject}\\${cleanRegion}`;
}

function TreeRegionButton({
  region,
  active,
  onClick,
}: {
  region: TreeRegion;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "flex w-full items-center justify-between rounded-md border px-3 py-2 text-left transition-colors " +
        (active ? "border-primary bg-primary/5" : "bg-card hover:bg-accent")
      }
    >
      <span className="flex min-w-0 items-center gap-2">
        <MapPinned className="h-4 w-4 shrink-0 text-primary" />
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{region.name}</span>
          <span className="block truncate font-mono text-[11px] text-muted-foreground">
            {region.safe_name}
          </span>
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-1.5">
        <Badge variant={region.has_aoi ? "success" : "neutral"}>
          {region.has_aoi ? "AOI" : "待设"}
        </Badge>
        <Badge variant="neutral">{region.scene_count} 景</Badge>
      </span>
    </button>
  );
}

function ProjectBlock({
  project,
  tree,
  onSelectProject,
  onSelectRegion,
}: {
  project: TreeProject;
  tree: Tree | null;
  onSelectProject: (projectId: string) => void;
  onSelectRegion: (regionId: string) => void;
}) {
  const activeProject = tree?.current_project_id === project.project_id;
  return (
    <div className="rounded-lg border bg-card p-3">
      <button
        type="button"
        onClick={() => onSelectProject(project.project_id)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="flex min-w-0 items-center gap-2">
          <FolderCheck
            className={
              "h-4 w-4 shrink-0 " +
              (activeProject ? "text-primary" : "text-muted-foreground")
            }
          />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">{project.name}</span>
            <span className="block truncate font-mono text-[11px] text-muted-foreground">
              {project.safe_name}
            </span>
          </span>
        </span>
        {activeProject && <Badge>当前项目</Badge>}
      </button>
      {project.regions.length > 0 && (
        <div className="mt-3 space-y-2">
          {project.regions.map((region) => (
            <TreeRegionButton
              key={region.region_id}
              region={region}
              active={tree?.current_region_id === region.region_id}
              onClick={() => onSelectRegion(region.region_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function Workspace() {
  const bridged = hasBridge();
  const { refresh: refreshContext } = usePrepContext();
  const [tree, setTree] = useState<Tree | null>(null);
  const [root, setRoot] = useState(DEFAULT_ROOT);
  const [projectName, setProjectName] = useState("badong_2024");
  const [regionName, setRegionName] = useState("shiliushubao");
  const [busy, setBusy] = useState(false);
  const [dirBusy, setDirBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function refreshTree() {
    const next = await getTree();
    setTree(next);
    if (next.workspace?.root) setRoot(next.workspace.root);
    const currentProject = next.projects.find((p) => p.project_id === next.current_project_id);
    if (currentProject) setProjectName(currentProject.name);
    const currentRegion = currentProject?.regions.find(
      (r) => r.region_id === next.current_region_id,
    );
    if (currentRegion) setRegionName(currentRegion.name);
  }

  useEffect(() => {
    void refreshTree();
  }, []);

  const previewPath = useMemo(
    () => formatProjectPath(root, projectName, regionName),
    [root, projectName, regionName],
  );

  async function onBrowseRoot() {
    const pick = await pickDirectory("选择项目根目录");
    if (pick.ok && pick.path) setRoot(pick.path);
  }

  async function onEnsureRoot() {
    setDirBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await ensureDirectory(root);
      if (res.ok) setNote("目录已准备好");
      else setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    } catch (e) {
      setError(formatBridgeError(e));
    } finally {
      setDirBusy(false);
    }
  }

  async function onStartProject() {
    if (!root.trim() || !projectName.trim() || !regionName.trim()) {
      setError("根目录、项目名和研究区名称都需要填写");
      return;
    }
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const folder = await ensureDirectory(root.trim());
      if (!folder.ok) {
        setError(`${folder.error}${folder.code ? ` (${folder.code})` : ""}`);
        return;
      }
      const ws = await createWorkspace(root.trim(), `${projectName.trim()} 工作目录`);
      if (!ws.ok) {
        setError(`${ws.error}${ws.code ? ` (${ws.code})` : ""}`);
        return;
      }
      const project = await addProject(projectName.trim());
      if (!project.ok) {
        setError(`${project.error}${project.code ? ` (${project.code})` : ""}`);
        return;
      }
      const region = await addRegion(regionName.trim());
      if (!region.ok) {
        setError(`${region.error}${region.code ? ` (${region.code})` : ""}`);
        return;
      }
      await refreshTree();
      await refreshContext();
      setNote("项目已就绪，可以进入 AOI 绘制");
    } catch (e) {
      setError(formatBridgeError(e));
    } finally {
      setBusy(false);
    }
  }

  async function onSelectProject(projectId: string) {
    const res = await selectProject(projectId);
    if (!res.ok) setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    await refreshTree();
    await refreshContext();
  }

  async function onSelectRegion(regionId: string) {
    const res = await selectRegion(regionId);
    if (!res.ok) setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
    await refreshTree();
    await refreshContext();
  }

  return (
    <div className="mx-auto max-w-[1260px] space-y-5">
      <PageHeader
        title="项目设置"
        desc="选择一个磁盘根目录，创建当前 InSAR 项目和研究区。"
        right={<BridgeBadge bridged={bridged} />}
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Radar className="h-4 w-4 text-primary" />
              新建当前项目
            </CardTitle>
            <CardDescription>
              根目录会用于 ASF、DEM、GACOS、报告等输出，目录不存在时可直接创建。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <FieldLabel>项目根目录</FieldLabel>
              <div className="flex gap-2">
                <Input
                  value={root}
                  onChange={(e) => setRoot(e.target.value)}
                  placeholder="C:\\InSAR\\projects"
                  spellCheck={false}
                  className="font-mono text-xs"
                />
                <Button variant="outline" size="icon" onClick={onBrowseRoot} title="浏览目录">
                  <FolderOpen className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={onEnsureRoot}
                  disabled={dirBusy || !root.trim()}
                  title="创建目录"
                >
                  {dirBusy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <FolderPlus className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <FieldLabel>项目名称</FieldLabel>
                <Input
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="badong_2024"
                  spellCheck={false}
                />
              </div>
              <div>
                <FieldLabel>研究区名称</FieldLabel>
                <Input
                  value={regionName}
                  onChange={(e) => setRegionName(e.target.value)}
                  placeholder="shiliushubao"
                  spellCheck={false}
                />
              </div>
            </div>

            <div className="rounded-lg border bg-muted/40 px-3 py-2">
              <div className="text-xs text-muted-foreground">预计工作目录</div>
              <div className="mt-1 truncate font-mono text-xs">{previewPath}</div>
            </div>

            {error && <ErrorNote text={error} />}
            {note && (
              <div className="flex items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
                <CheckCircle2 className="h-4 w-4" />
                <span>{note}</span>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={onStartProject}
                disabled={busy || !root.trim() || !projectName.trim() || !regionName.trim()}
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                开始这个项目
              </Button>
              <span className="text-xs text-muted-foreground">
                完成后会自动选中该研究区。
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">当前会话</CardTitle>
            <CardDescription>
              {tree?.workspace
                ? tree.workspace.name || tree.workspace.root
                : "尚未创建项目上下文"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!tree?.workspace || tree.projects.length === 0 ? (
              <div className="rounded-lg border border-dashed py-12 text-center text-sm text-muted-foreground">
                创建项目后会显示当前项目和研究区。
              </div>
            ) : (
              <div className="space-y-3">
                {tree.projects.map((project) => (
                  <ProjectBlock
                    key={project.project_id}
                    project={project}
                    tree={tree}
                    onSelectProject={onSelectProject}
                    onSelectRegion={onSelectRegion}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
