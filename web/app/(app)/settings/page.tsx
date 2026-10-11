"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import ShareId from "@/components/ShareId";
import { Err } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { HEARD } from "@/lib/labels";
import { normalizeUsername, usernameProblem } from "@/lib/username";

function Form() {
  const welcome = useSearchParams().get("welcome");
  const { data: me, mutate } = useApi<any>("/me");
  const [f, setF] = useState({ first_name: "", last_name: "", phone: "", heard_from: "", heard_other: "", handle: "" });
  const [msg, setMsg] = useState<{ ok?: string; err?: string }>({});
  useEffect(() => { if (me) setF({ first_name: me.first_name ?? "", last_name: me.last_name ?? "", phone: me.phone ?? "", heard_from: me.heard_from ?? "", heard_other: me.heard_other ?? "", handle: me.handle ?? "" }); }, [me]);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: k === "handle" ? e.target.value.toLowerCase() : e.target.value });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const h = normalizeUsername(f.handle);
    if (h && usernameProblem(h)) return setMsg({ err: usernameProblem(h)! });
    try {
      await api("/me", { method: "PUT", body: { first_name: f.first_name, last_name: f.last_name || null, phone: f.phone || null, heard_from: f.heard_from || null, heard_other: f.heard_other || null, handle: h || null } });
      mutate(); setMsg({ ok: "Saved" });
    } catch (x: any) { setMsg({ err: x.message }); }
  }
  return (
    <form onSubmit={save} className="max-w-md space-y-4">
      <h1>Profile</h1>
      {welcome && <p className="rounded bg-ok-soft px-3 py-2 text-sm text-ok">Welcome! Your username is your ID: give it to the person you work with. Next, connect your wallet in the sidebar.</p>}
      <p className="text-sm text-mute">{me?.email}</p>
      {me?.handle && <div className="panel p-3"><ShareId handle={me.handle} /></div>}
      <div className="grid grid-cols-2 gap-3">
        <div><label className="label" htmlFor="fn">First name</label><input id="fn" className="input" required value={f.first_name} onChange={set("first_name")} /></div>
        <div><label className="label" htmlFor="ln">Last name</label><input id="ln" className="input" value={f.last_name} onChange={set("last_name")} /></div>
      </div>
      <div><label className="label" htmlFor="ph">Phone</label><input id="ph" className="input" type="tel" value={f.phone} onChange={set("phone")} /></div>
      <div>
        <label className="label" htmlFor="h">Username</label>
        <input id="h" className="input" value={f.handle} onChange={set("handle")} pattern="[a-z0-9_-]{3,24}" />
        <p className="mt-1 text-xs text-mute">Your public work record lives at /p/{f.handle || "username"}.</p>
      </div>
      <div><label className="label" htmlFor="hf">Where did you hear about us?</label>
        <select id="hf" className="input" value={f.heard_from} onChange={set("heard_from")}><option value="">Not set</option>{HEARD.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
      <Err>{msg.err}</Err>{msg.ok && <p className="text-sm text-ok">{msg.ok}</p>}
      <button className="btn-primary">Save</button>
    </form>
  );
}
export default function Settings() { return <Suspense><Form /></Suspense>; }
