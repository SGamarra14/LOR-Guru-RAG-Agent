// Une clases condicionalmente. Versión mínima del `cn` de shadcn (sin
// clsx/tailwind-merge): suficiente porque controlamos todos los usos y no
// mezclamos clases en conflicto.
export function cn(...clases: Array<string | false | null | undefined>): string {
  return clases.filter(Boolean).join(" ");
}
