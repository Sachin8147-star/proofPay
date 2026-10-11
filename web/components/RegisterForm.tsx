"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiPublic } from "@/lib/api";
import { HEARD } from "@/lib/labels";
import { supabase } from "@/lib/supabase";
import { normalizeUsername, usernameProblem } from "@/lib/username";
import { Err } from "./ui";

type Check = { state: "idle" | "checking" | "ok" | "bad"; msg?: string };

export default function RegisterForm() {
  const [f, setF] = useState({ first_name: "", last_name: "", email: "", phone: "", heard_from: "", heard_other: "", handle: "", password: "", password2: "" });
  const [check, setCheck] = useState<Check>({ state: "idle" });
  const [err, setErr] = useState<string>();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: k === "handle" ? e.target.value.toLowerCase() : e.target.value });
  const u = normalizeUsername(f.handle);

  useEffect(() => {
    if (!u) return setCheck({ state: "idle" });
    const bad = usernameProblem(u);
    if (bad) return setCheck({ state: "bad", msg: bad });
    setCheck({ state: "checking" });
    const t = setTimeout(async () => {
      try {
        const r = await apiPublic(`/username-available?u=${encodeURIComponent(u)}`);
        setCheck(r.available ? { state: "ok", msg: "Username is available" } : { state: "bad", msg: r.reason || "Username already exists. Pick another." });
      } catch { setCheck({ state: "idle" }); }
    }, 400);
    return () => clearTimeout(t);
  }, [u]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(undefined);
    if (check.state !== "ok") return setErr(check.state === "bad" ? check.msg : "Wait for username availability to be confirmed.");
    if (check.state === "bad") return setErr(check.msg);
    if (f.password !== f.password2) return setErr("The two passwords do not match.");
    if (f.heard_from === "other" && !f.heard_other.trim()) return setErr("Tell us where you heard about ProofPay.");
    setBusy(true);
    try {
      const { data, error } = await supabase().auth.signUp({
        email: f.email.trim(), password: f.password,
        options: { data: { first_name: f.first_name.trim(), last_name: f.last_name.trim(), phone: f.phone.trim(), heard_from: f.heard_from, heard_other: f.heard_other.trim(), handle: u } },
      });
      if (error) throw error;
      // Supabase hides "already registered" behind an empty identities list.
      if (data.user && data.user.identities?.length === 0) throw new Error("This email already has an account. Sign in instead.");
      if (data.session) window.location.replace("/settings?welcome=1"); else setDone(true);
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }

  if (done)
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-5">
        <h1>Check your email</h1>
        <p className="mt-3 text-mute">We sent a confirmation link to <b>{f.email}</b>. Open it, then <Link className="link" href="/login?next=/settings%3Fwelcome%3D1">sign in</Link>. Your username is <b>@{u}</b>: share it with the person you work with.</p>
      </main>
    );
  const hint = check.state === "checking" ? "Checking…" : check.msg;
  return (
    <main className="mx-auto max-w-md px-5 py-10">
      <h1>Create your ProofPay account</h1>
      <p className="mt-1 text-sm text-mute">One account works for hiring and for doing work.</p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div><label className="label" htmlFor="fn">First name</label><input id="fn" className="input" required maxLength={60} value={f.first_name} onChange={set("first_name")} autoComplete="given-name" /></div>
          <div><label className="label" htmlFor="ln">Last name <span className="font-normal text-mute">(optional)</span></label><input id="ln" className="input" maxLength={60} value={f.last_name} onChange={set("last_name")} autoComplete="family-name" /></div>
        </div>
        <div><label className="label" htmlFor="em">Gmail / email</label><input id="em" className="input" type="email" required value={f.email} onChange={set("email")} autoComplete="email" /></div>
        <div><label className="label" htmlFor="ph">Phone number</label><input id="ph" className="input" type="tel" required pattern="\+?[0-9 ()\-]{7,20}" placeholder="+91 98765 43210" value={f.phone} onChange={set("phone")} autoComplete="tel" /></div>
        <div>
          <label className="label" htmlFor="hf">Where did you hear about us?</label>
          <select id="hf" className="input" required value={f.heard_from} onChange={set("heard_from")}>
            <option value="">Choose one</option>{HEARD.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        {f.heard_from === "other" && <div><label className="label" htmlFor="ho">Please tell us where</label><input id="ho" className="input" maxLength={120} value={f.heard_other} onChange={set("heard_other")} /></div>}
        <div>
          <label className="label" htmlFor="un">Username</label>
          <input id="un" className="input" required value={f.handle} onChange={set("handle")} placeholder="e.g. sachin_web" aria-describedby="un-hint" autoComplete="username" />
          <p id="un-hint" role="status" className={`mt-1 text-xs ${check.state === "ok" ? "text-ok" : check.state === "bad" ? "text-bad" : "text-mute"}`}>{hint || "This is your ID. The other person types it to hire you or to find you."}</p>
        </div>
        <div><label className="label" htmlFor="pw">Password</label><input id="pw" className="input" type="password" required minLength={8} value={f.password} onChange={set("password")} autoComplete="new-password" /></div>
        <div><label className="label" htmlFor="pw2">Repeat password</label><input id="pw2" className="input" type="password" required minLength={8} value={f.password2} onChange={set("password2")} autoComplete="new-password" /></div>
        <Err>{err}</Err>
        <button className="btn-primary w-full" disabled={busy || check.state !== "ok"}>{busy ? "Creating…" : "Create account"}</button>
      </form>
      <p className="mt-4 text-sm text-mute">Already have an account? <Link className="link" href="/login">Sign in</Link></p>
    </main>
  );
}
