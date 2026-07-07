import { cn } from "@/lib/utils";

const VARIANTES = {
  default: "border-border bg-card text-foreground",
  destructive: "border-destructive/60 bg-destructive/10 text-foreground",
} as const;

type Props = React.HTMLAttributes<HTMLDivElement> & {
  variant?: keyof typeof VARIANTES;
};

export function Alert({ className, variant = "default", ...props }: Props) {
  return (
    <div
      role="alert"
      className={cn("rounded-md border p-4", VARIANTES[variant], className)}
      {...props}
    />
  );
}

export function AlertTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h5
      className={cn("mb-1 font-display font-semibold text-destructive", className)}
      {...props}
    />
  );
}

export function AlertDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm leading-relaxed", className)} {...props} />;
}
