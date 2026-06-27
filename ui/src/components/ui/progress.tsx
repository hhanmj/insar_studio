import { cn } from "@/lib/utils";

export function Progress({
  value = 0,
  className,
}: {
  value?: number;
  className?: string;
}) {
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-white/45 shadow-inner backdrop-blur-xl dark:bg-white/10", className)}>
      <div
        className="h-full rounded-full bg-primary shadow-[0_0_18px_rgba(0,122,255,0.35)] transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
