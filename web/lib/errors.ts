/** FastAPI returns `detail` as a string (our errors) or a list (validation errors). Turn either into one readable line. */
export function errorText(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((x: any) => `${(x.loc ?? []).slice(1).join(".")}: ${x.msg}`).join("; ");
  return fallback;
}
