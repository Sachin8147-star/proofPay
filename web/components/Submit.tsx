"use client";
import { useState } from "react";
import { apiForm } from "@/lib/api";
import { Err } from "./ui";

const SOURCES: [string, string][] = [["zip", "Upload a .zip"], ["github", "GitHub link"], ["site", "Published website"]];

/** The worker's delivery form: zip upload, GitHub link or a live website. `dry` makes it a free practice run. */
export default function Submit({ cid, idx, deliveryType, dry, left, running, onDone }: { cid: string; idx: number; deliveryType: string; dry: boolean; left?: number; running: boolean; onDone: () => void }) {
  const live = deliveryType === "live_site";
  const [source, setSource] = useState(live ? "site" : "zip");
  const [f, setF] = useState({ repo_url: "", ref: "", deploy_url: "" });
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);
  const ready = source === "zip" ? !!file : source === "github" ? !!f.repo_url.trim() : !!f.deploy_url.trim();

  async function go(e: React.FormEvent) {
    e.preventDefault();
    setErr(undefined); setBusy(true);
    try {
      const fd = new FormData();
      fd.append("source", source);
      if (source === "zip" && file) fd.append("file", file);
      if (source === "github") { fd.append("repo_url", f.repo_url.trim()); if (f.ref) fd.append("ref", f.ref.trim()); }
      if (source === "site" || live) fd.append("deploy_url", f.deploy_url.trim());
      await apiForm(`/contracts/${cid}/milestones/${idx}/${dry ? "dry-run" : "submit"}`, fd);
      setFile(null);
      onDone();
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }
  const sources = live ? SOURCES.filter(([k]) => k !== "zip") : SOURCES;
  return (
    <form onSubmit={go} className="space-y-3 border-t border-line px-4 py-4">
      <p className="font-semibold">{dry ? "Practice run (free, private)" : "Deliver your work"}</p>
      <div role="tablist" aria-label="How are you delivering?" className="flex flex-wrap gap-2">
        {sources.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={source === k} className={source === k ? "btn-primary !py-1" : "btn-ghost !py-1"} onClick={() => setSource(k)}>{l}</button>)}
      </div>
      {source === "zip" && <div><label className="label" htmlFor={`z${idx}`}>Zip file with everything the buyer asked for</label><input id={`z${idx}`} className="input" type="file" accept=".zip,application/zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></div>}
      {source === "github" && <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><label className="label" htmlFor={`g${idx}`}>GitHub repository</label><input id={`g${idx}`} className="input" placeholder="https://github.com/you/project" value={f.repo_url} onChange={(e) => setF({ ...f, repo_url: e.target.value })} /></div>
        <div><label className="label" htmlFor={`b${idx}`}>Branch or commit (optional)</label><input id={`b${idx}`} className="input" value={f.ref} onChange={(e) => setF({ ...f, ref: e.target.value })} /></div>
      </div>}
      {(source === "site" || live) && <div><label className="label" htmlFor={`u${idx}`}>Published website address</label><input id={`u${idx}`} className="input" placeholder="https://your-site.example.com" value={f.deploy_url} onChange={(e) => setF({ ...f, deploy_url: e.target.value })} /></div>}
      <Err>{err}</Err>
      <div className="flex flex-wrap items-center gap-3">
        <button className={dry ? "btn-ghost" : "btn-primary"} disabled={busy || running || !ready}>{running ? "Checking…" : busy ? "Sending…" : dry ? "Practice run" : `Submit for checking${left != null ? ` (${left} left)` : ""}`}</button>
        {dry && <p className="text-xs text-mute">A practice run checks only the visible requirements. It never goes on-chain and the buyer doesn&apos;t see it.</p>}
      </div>
    </form>
  );
}
