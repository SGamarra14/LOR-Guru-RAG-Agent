import { cn } from "@/lib/utils";

export function Label({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "font-display text-sm font-semibold tracking-wide text-primary",
        className,
      )}
      {...props}
    />
  );
}
