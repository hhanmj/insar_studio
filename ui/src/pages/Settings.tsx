import { useEffect, useState } from "react";
import {
  Database,
  ExternalLink,
  KeyRound,
  Loader2,
  Mail,
  Radar,
  RotateCcw,
  Save,
  ShieldCheck,
  UserRound,
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
  clearEarthdataCredentials,
  clearGacosEmail,
  clearOpentopographyKey,
  formatBridgeError,
  getCredentialStatus,
  hasBridge,
  openExternalUrl,
  saveEarthdataLogin,
  saveEarthdataToken,
  saveGacosEmail,
  saveOpentopographyKey,
  type CredentialStatus,
  type SimpleOk,
} from "@/lib/bridge";

const LINKS = {
  earthdataToken: "https://urs.earthdata.nasa.gov/profile",
  earthdataRegister: "https://urs.earthdata.nasa.gov/users/new",
  opentopoKey: "https://portal.opentopography.org/requestService?service=api",
  opentopoRegister: "https://portal.opentopography.org/newUser",
  gacosPortal: "http://www.gacos.net/",
  gacosReadme: "http://www.gacos.net/static/file/ReadMe.pdf",
};

function isConfigured(value: string) {
  return value !== "none" && value !== "unavailable";
}

function ProviderStatus({ value }: { value: string }) {
  if (value === "unavailable") return <Badge variant="warning">凭据服务不可用</Badge>;
  if (!isConfigured(value)) return <Badge variant="warning">待配置</Badge>;
  return <Badge variant="success">{value}</Badge>;
}

function SectionTitle({
  icon: Icon,
  title,
  desc,
  status,
}: {
  icon: typeof Radar;
  title: string;
  desc: string;
  status: string;
}) {
  return (
    <CardHeader className="pb-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <CardTitle className="text-base">{title}</CardTitle>
            <CardDescription className="mt-1">{desc}</CardDescription>
          </div>
        </div>
        <ProviderStatus value={status} />
      </div>
    </CardHeader>
  );
}

export function Settings() {
  const bridged = hasBridge();
  const [status, setStatus] = useState<CredentialStatus | null>(null);
  const [earthToken, setEarthToken] = useState("");
  const [earthUser, setEarthUser] = useState("");
  const [earthPassword, setEarthPassword] = useState("");
  const [opentopoKey, setOpentopoKey] = useState("");
  const [gacosEmail, setGacosEmail] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function refresh() {
    setStatus(await getCredentialStatus());
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function run(label: string, action: () => Promise<SimpleOk>, success: string) {
    setBusy(label);
    setError(null);
    setNote(null);
    try {
      const res = await action();
      if (res.ok) {
        await refresh();
        setNote(success);
      } else {
        setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
      }
    } catch (e) {
      setError(formatBridgeError(e));
    } finally {
      setBusy(null);
    }
  }

  async function openUrl(url: string) {
    const res = await openExternalUrl(url);
    if (!res.ok) setError(`${res.error}${res.code ? ` (${res.code})` : ""}`);
  }

  const earthStatus = status?.earthdata ?? "none";
  const demStatus = status?.opentopography ?? "none";
  const gacosStatus = status?.gacos ?? "none";
  const allReady = [earthStatus, demStatus, gacosStatus].every(isConfigured);

  return (
    <div className="mx-auto max-w-[1260px] space-y-5">
      <PageHeader
        title="设置"
        desc="先配置账号、Token 或 API Key，再进入下载和请求规划。"
        right={<BridgeBadge bridged={bridged} />}
      />

      <div
        className={
          "flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 " +
          (allReady ? "bg-success/10" : "bg-warning/10")
        }
      >
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <ShieldCheck className={allReady ? "h-4 w-4 text-success" : "h-4 w-4 text-warning"} />
          <span className="font-medium">
            {allReady ? "下载凭据已就绪" : "请先补齐下载凭据"}
          </span>
          <span className="text-muted-foreground">
            密钥保存到系统凭据管理器，不写入项目目录。
          </span>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refresh()}>
          <RotateCcw className="h-4 w-4" />
          刷新状态
        </Button>
      </div>

      {error && <ErrorNote text={error} />}
      {note && (
        <div className="flex items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
          <ShieldCheck className="h-4 w-4" />
          <span>{note}</span>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card>
          <SectionTitle
            icon={Radar}
            title="Earthdata / ASF"
            desc="Sentinel-1 SLC 下载凭据，优先使用 Token。"
            status={earthStatus}
          />
          <CardContent className="space-y-4">
            <div>
              <FieldLabel>Earthdata Token</FieldLabel>
              <div className="flex gap-2">
                <Input
                  type="password"
                  value={earthToken}
                  onChange={(e) => setEarthToken(e.target.value)}
                  placeholder="粘贴 Bearer Token"
                />
                <Button
                  size="icon"
                  onClick={() =>
                    run("earth-token", () => saveEarthdataToken(earthToken), "Earthdata Token 已保存")
                  }
                  disabled={busy === "earth-token" || !earthToken.trim()}
                  title="保存 Token"
                >
                  {busy === "earth-token" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <div className="grid gap-2">
              <div>
                <FieldLabel>用户名</FieldLabel>
                <Input
                  value={earthUser}
                  onChange={(e) => setEarthUser(e.target.value)}
                  placeholder="Earthdata username"
                  autoComplete="username"
                />
              </div>
              <div>
                <FieldLabel>密码</FieldLabel>
                <Input
                  type="password"
                  value={earthPassword}
                  onChange={(e) => setEarthPassword(e.target.value)}
                  placeholder="Earthdata password"
                  autoComplete="current-password"
                />
              </div>
              <Button
                variant="outline"
                onClick={() =>
                  run(
                    "earth-login",
                    () => saveEarthdataLogin(earthUser, earthPassword),
                    "Earthdata 登录凭据已保存",
                  )
                }
                disabled={busy === "earth-login" || !earthUser.trim() || !earthPassword}
              >
                {busy === "earth-login" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <UserRound className="h-4 w-4" />
                )}
                保存登录凭据
              </Button>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.earthdataToken)}>
                <ExternalLink className="h-4 w-4" />
                Token 页面
              </Button>
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.earthdataRegister)}>
                <ExternalLink className="h-4 w-4" />
                注册
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  run("earth-clear", clearEarthdataCredentials, "Earthdata 凭据已清除")
                }
                disabled={busy === "earth-clear" || !isConfigured(earthStatus)}
              >
                清除
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <SectionTitle
            icon={Database}
            title="OpenTopography"
            desc="DEM 下载需要个人 API Key。"
            status={demStatus}
          />
          <CardContent className="space-y-4">
            <div>
              <FieldLabel>API Key</FieldLabel>
              <div className="flex gap-2">
                <Input
                  type="password"
                  value={opentopoKey}
                  onChange={(e) => setOpentopoKey(e.target.value)}
                  placeholder="OpenTopography API Key"
                />
                <Button
                  size="icon"
                  onClick={() =>
                    run("dem-key", () => saveOpentopographyKey(opentopoKey), "OpenTopography API Key 已保存")
                  }
                  disabled={busy === "dem-key" || !opentopoKey.trim()}
                  title="保存 API Key"
                >
                  {busy === "dem-key" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <KeyRound className="h-4 w-4" />
                  )}
                </Button>
              </div>
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
                onClick={() =>
                  run("dem-clear", clearOpentopographyKey, "OpenTopography API Key 已清除")
                }
                disabled={busy === "dem-clear" || !isConfigured(demStatus)}
              >
                清除
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <SectionTitle
            icon={Mail}
            title="GACOS"
            desc="ZTD 请求结果会发送到该邮箱。"
            status={gacosStatus}
          />
          <CardContent className="space-y-4">
            <div>
              <FieldLabel>接收邮箱</FieldLabel>
              <div className="flex gap-2">
                <Input
                  value={gacosEmail}
                  onChange={(e) => setGacosEmail(e.target.value)}
                  placeholder="name@example.com"
                  inputMode="email"
                />
                <Button
                  size="icon"
                  onClick={() =>
                    run("gacos-email", () => saveGacosEmail(gacosEmail), "GACOS 邮箱已保存")
                  }
                  disabled={busy === "gacos-email" || !gacosEmail.trim()}
                  title="保存邮箱"
                >
                  {busy === "gacos-email" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.gacosPortal)}>
                <ExternalLink className="h-4 w-4" />
                GACOS 网站
              </Button>
              <Button variant="outline" size="sm" onClick={() => void openUrl(LINKS.gacosReadme)}>
                <ExternalLink className="h-4 w-4" />
                ReadMe
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => run("gacos-clear", clearGacosEmail, "GACOS 邮箱已清除")}
                disabled={busy === "gacos-clear" || !isConfigured(gacosStatus)}
              >
                清除
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
