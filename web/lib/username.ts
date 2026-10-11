export const RESERVED = ["admin", "administrator", "support", "proofpay", "root", "system", "api", "help", "staff", "moderator", "null", "undefined"];
export const normalizeUsername = (u: string) => u.trim().toLowerCase().replace(/^@/, "");
/** Returns a message when the username is not allowed, or null when it is fine (availability is checked on the server). */
export function usernameProblem(raw: string): string | null {
  const u = normalizeUsername(raw);
  if (!/^[a-z0-9_-]{3,24}$/.test(u)) return "Use 3-24 letters, numbers, _ or - (no spaces).";
  if (RESERVED.includes(u)) return "That username is reserved.";
  return null;
}
