import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-2xl text-sm font-medium transition-all duration-200 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-[0_10px_24px_rgba(0,122,255,0.24)] hover:bg-primary/90",
        secondary: "bg-secondary text-secondary-foreground shadow-sm backdrop-blur-xl hover:bg-secondary/80",
        outline:
          "border border-white/60 bg-white/46 shadow-sm backdrop-blur-2xl hover:bg-white/72 hover:text-accent-foreground dark:border-white/12 dark:bg-white/8 dark:hover:bg-white/14",
        ghost: "hover:bg-white/55 hover:text-accent-foreground dark:hover:bg-white/10",
        destructive:
          "bg-destructive text-destructive-foreground shadow-[0_10px_24px_rgba(255,59,48,0.22)] hover:bg-destructive/90",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-2xl px-3 text-xs",
        lg: "h-11 rounded-2xl px-6",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { buttonVariants };
