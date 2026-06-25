import { Hammer } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { NavKey } from "@/components/Sidebar";

const TITLES: Record<NavKey, { title: string; desc: string }> = {
  overview: { title: "总览", desc: "" },
  workspace: { title: "工作区", desc: "Workspace ▸ Project ▸ Region 层级管理" },
  aoi: { title: "区域 AOI", desc: "矩形/多边形绘制、bbox 输入、shp/kml/geojson 导入" },
  scenes: { title: "影像核查", desc: "ASF 购物车导入与一致性核查" },
  download: { title: "数据下载", desc: "ASF SLC / DEM / GACOS 下载编排" },
  convert: { title: "DEM 转换", desc: "正高 EGM96 → WGS84 椭球高（rasterio/GDAL）" },
  report: { title: "报告", desc: "JSON · Markdown · HTML · manifest · warnings" },
  settings: { title: "设置", desc: "凭据、代理、并发、语言与主题" },
};

export function Placeholder({ navKey }: { navKey: NavKey }) {
  const meta = TITLES[navKey];
  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{meta.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{meta.desc}</p>
      </div>
      <Card>
        <CardContent className="flex flex-col items-center justify-center gap-3 py-20 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Hammer className="h-6 w-6" />
          </div>
          <div className="text-base font-medium">界面骨架就绪，正在接入核心</div>
          <p className="max-w-md text-sm text-muted-foreground">
            该面板将通过 pywebview 桥直接调用现有 Python 核心（{meta.title}）。本页是
            新 UI 的视觉占位，逻辑复用 100% 现有 insar_prep 实现。
          </p>
          <Badge variant="neutral">即将接入</Badge>
        </CardContent>
      </Card>
    </div>
  );
}
