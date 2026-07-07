// Primitivas estilo shadcn/ui escritas a mano (el CLI de shadcn se colgaba
// en este entorno). Mismo API y ubicación que las generadas, para que un
// `npx shadcn add` futuro pueda reemplazarlas sin tocar el resto del código.
import { cn } from "@/lib/utils";

const VARIANTES = {
  default:
    "bg-primary text-primary-foreground hover:bg-primary/85 shadow-[0_0_14px_rgba(200,162,75,0.25)]",
  outline:
    "border border-border bg-transparent text-foreground hover:border-accent hover:text-accent",
} as const;

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof VARIANTES;
};

export function Button({ className, variant = "default", ...props }: Props) {
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold tracking-wide transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "disabled:pointer-events-none disabled:opacity-50",
        VARIANTES[variant],
        className,
      )}
      {...props}
    />
  );
}
