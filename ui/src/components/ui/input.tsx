import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type, ...props }, ref) => (
  <input
    ref={ref}
    type={type}
    className={cn(
      "flex h-10 w-full rounded-2xl border border-white/58 bg-white/50 px-3 py-1 text-sm shadow-sm backdrop-blur-2xl transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/12 dark:bg-white/10",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";
