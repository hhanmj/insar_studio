import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, ChevronLeft, ChevronRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type TourStep = {
  target?: string;
  title: string;
  body: string;
  hint?: string;
  placement?: "top" | "right" | "bottom" | "left" | "center";
};

type Rect = {
  top: number;
  left: number;
  width: number;
  height: number;
  right: number;
  bottom: number;
};

function visibleRect(selector?: string): Rect | null {
  if (!selector || typeof document === "undefined") return null;
  const el = document.querySelector(selector);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  if (rect.width < 8 || rect.height < 8) return null;
  return {
    top: rect.top,
    left: rect.left,
    width: rect.width,
    height: rect.height,
    right: rect.right,
    bottom: rect.bottom,
  };
}

function readSeenVersion(storageKey: string): number {
  if (typeof window === "undefined") return 0;
  return Number(window.localStorage.getItem(storageKey) || 0);
}

function writeSeenVersion(storageKey: string, version: number) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(storageKey, String(version));
}

export function OnboardingTour({
  steps,
  storageKey,
  version,
  runSignal = 0,
  autoStart = true,
}: {
  steps: TourStep[];
  storageKey: string;
  version: number;
  runSignal?: number;
  autoStart?: boolean;
}) {
  const [index, setIndex] = useState<number | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);
  const step = index === null ? null : steps[index];

  const start = useCallback(() => {
    if (!steps.length) return;
    setIndex(0);
  }, [steps.length]);

  const close = useCallback(
    (remember = true) => {
      if (remember) writeSeenVersion(storageKey, version);
      setIndex(null);
    },
    [storageKey, version],
  );

  useEffect(() => {
    if (!autoStart || readSeenVersion(storageKey) >= version) return;
    const id = window.setTimeout(start, 700);
    return () => window.clearTimeout(id);
  }, [autoStart, start, storageKey, version]);

  useEffect(() => {
    if (runSignal > 0) start();
  }, [runSignal, start]);

  useEffect(() => {
    if (!step) return;
    const update = () => setRect(visibleRect(step.target));
    update();
    const id = window.requestAnimationFrame(update);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.cancelAnimationFrame(id);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [step]);

  const cardStyle = useMemo(() => {
    const width = Math.min(380, Math.max(300, typeof window === "undefined" ? 360 : window.innerWidth - 32));
    const margin = 18;
    if (!rect || !step?.target) {
      return {
        width,
        left: `calc(50vw - ${width / 2}px)`,
        top: "calc(50vh - 150px)",
      };
    }

    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const desired = step.placement ?? (rect.left > vw * 0.55 ? "left" : rect.right < vw * 0.55 ? "right" : "bottom");
    let left = rect.left;
    let top = rect.bottom + margin;

    if (desired === "right") {
      left = rect.right + margin;
      top = rect.top;
    } else if (desired === "left") {
      left = rect.left - width - margin;
      top = rect.top;
    } else if (desired === "top") {
      left = rect.left;
      top = rect.top - 220 - margin;
    } else if (desired === "center") {
      left = vw / 2 - width / 2;
      top = vh / 2 - 150;
    }

    left = Math.min(Math.max(16, left), Math.max(16, vw - width - 16));
    top = Math.min(Math.max(16, top), Math.max(16, vh - 260));
    return { width, left, top };
  }, [rect, step]);

  if (!step || index === null) return null;

  const isLast = index >= steps.length - 1;
  const highlightStyle = rect
    ? {
        top: rect.top - 8,
        left: rect.left - 8,
        width: rect.width + 16,
        height: rect.height + 16,
      }
    : undefined;

  return (
    <div className="fixed inset-0 z-[1200]">
      <div className="absolute inset-0 bg-slate-950/28 backdrop-blur-[2px]" />
      {highlightStyle && (
        <div
          className="pointer-events-none absolute rounded-[24px] border border-white/90 bg-white/12 shadow-[0_0_0_9999px_rgba(2,6,23,0.20),0_24px_80px_rgba(15,23,42,0.28)] ring-4 ring-primary/35"
          style={highlightStyle}
        />
      )}
      <div
        className="absolute rounded-[28px] border border-white/65 bg-white/78 p-4 text-foreground shadow-[0_24px_80px_rgba(15,23,42,0.22)] backdrop-blur-3xl dark:border-white/12 dark:bg-slate-950/78"
        style={cardStyle}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
              <CheckCircle2 className="h-3.5 w-3.5" />
              新手引导 {index + 1}/{steps.length}
            </div>
            <h2 className="mt-3 text-base font-semibold">{step.title}</h2>
          </div>
          <button
            type="button"
            onClick={() => close(true)}
            className="rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-white/70 hover:text-foreground dark:hover:bg-white/10"
            title="关闭引导"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">{step.body}</p>
        {step.hint && (
          <div className="mt-3 rounded-2xl border border-white/50 bg-white/45 px-3 py-2 text-xs leading-5 text-muted-foreground dark:border-white/10 dark:bg-white/10">
            {step.hint}
          </div>
        )}
        <div className="mt-4 flex items-center justify-between gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => close(true)}
          >
            跳过
          </Button>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={index === 0}
              onClick={() => setIndex((value) => Math.max(0, (value ?? 0) - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
              上一步
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => (isLast ? close(true) : setIndex((value) => Math.min(steps.length - 1, (value ?? 0) + 1)))}
              className={cn(isLast && "bg-success text-white hover:bg-success/90")}
            >
              {isLast ? "完成" : "下一步"}
              {!isLast && <ChevronRight className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
