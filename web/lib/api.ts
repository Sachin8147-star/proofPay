import useSWR from "swr";
import { errorText } from "./errors";
import { supabase } from "./supabase";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function token() {
  const { data } = await supabase().auth.getSession();
  return data.session?.access_token;
}

async function parse<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(errorText(j.detail, r.statusText));
  }
  return r.json();
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const t = await token();
  const r = await fetch(API + path, {
    method: opts.method ?? (opts.body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  return parse<T>(r);
}

/** Multipart upload (zip files). The browser sets the content type. */
export async function apiForm<T = any>(path: string, form: FormData): Promise<T> {
  const t = await token();
  const r = await fetch(API + path, { method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: form });
  return parse<T>(r);
}

/** Public endpoint (no sign-in), e.g. the username check on the sign-up form. */
export async function apiPublic<T = any>(path: string): Promise<T> {
  return parse<T>(await fetch(API + path));
}

/** Polls so on-chain changes picked up by the indexer show up without a reload. */
export const useApi = <T = any,>(path: string | null, poll = 0) =>
  useSWR<T>(path, (p: string) => api<T>(p), { refreshInterval: poll, revalidateOnFocus: true });
