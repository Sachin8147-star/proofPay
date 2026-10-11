"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { supabase } from "@/lib/supabase";
import { Err } from "./ui";

export default function LoginForm({ next, title, admin }: { next?: string; title: string; admin?: boolean }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(undefined); setBusy(true);
    try {
      const dest = next ?? new URLSearchParams(window.location.search).get("next") ?? "/client";
      const { data, error } = await supabase().auth.signInWithPassword({ email, password });
      if (error) throw error;
      if (data.session) router.replace(dest);
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-5">
      <h1 className="mb-6">{title}</h1>
      <form onSubmit={submit} className="space-y-4">
        <div><label className="label" htmlFor="email">Email</label><input id="email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></div>
        <div><label className="label" htmlFor="pw">Password</label><input id="pw" className="input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></div>
        <Err>{err}</Err>
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
      {!admin && <Link className="link mt-4 text-sm" href="/register">New here? Create an account</Link>}
    </main>
  );
}
