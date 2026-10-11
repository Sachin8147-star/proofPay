"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Err } from "@/components/ui";
import { SPEECH_LANGS, useSpeech } from "@/components/useSpeech";
import { api, useApi } from "@/lib/api";
import { SYMBOL } from "@/lib/chain";
import { DELIVERY, KIND_LABEL } from "@/lib/labels";
import { normalizeUsername, usernameProblem } from "@/lib/username";

type Req = { title: string; criteria: string; kind: string; spec: any; hidden: boolean };
type Ms = { title: string; amount: string; deadline: string; delivery_type: string; review_days: number; requirements: Req[] };
const AUTO_KINDS: Record<string, string[]> = { software: ["ai_review", "command", "file_exists", "file_contains", "manual"], live_site: ["ai_review", "http", "manual"], product: ["manual"] };
const blank = (kind: string): any => ({
  file_exists: { path: "README.md" }, file_contains: { path: "", pattern: "" }, http: { method: "GET", path: "/", expect_status: 200, expect_contains: "" },
  command: { cmd: "pytest -q", image: "python:3.12-slim", setup: "pip install -r requirements.txt", timeout: 120 }, ai_review: { claim: "" }, manual: { note: "" },
}[kind]);
const inDays = (d: number) => { const t = new Date(Date.now() + d * 864e5); t.setMinutes(t.getMinutes() - t.getTimezoneOffset()); return t.toISOString().slice(0, 16); };
const newReq = (type: string): Req => (type === "product"
  ? { title: "I received the item as described", criteria: "", kind: "manual", spec: blank("manual"), hidden: false }
  : { title: "", criteria: "", kind: "ai_review", spec: blank("ai_review"), hidden: false });
const newMs = (n: number, type = "software"): Ms => ({ title: "", amount: "", deadline: inDays(7 * (n + 1)), delivery_type: type, review_days: type === "product" ? 7 : 3, requirements: [newReq(type)] });

function Spec({ kind, spec, set }: { kind: string; spec: any; set: (s: any) => void }) {
  const f = (k: string, label: string, ph = "", type = "text") => (
    <label className="block"><span className="label">{label}</span><input className="input" type={type} placeholder={ph} value={spec[k] ?? ""} onChange={(e) => set({ ...spec, [k]: type === "number" ? Number(e.target.value) : e.target.value })} /></label>
  );
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {kind === "ai_review" && <div className="sm:col-span-2">{f("claim", "What must be true? (the AI has to quote proof from the delivered work)", "The site has a contact form with name, email and message")}</div>}
      {kind === "manual" && <div className="sm:col-span-2">{f("note", "What will you confirm? (optional)", "Item arrives as described")}</div>}
      {kind === "file_exists" && f("path", "File path", "README.md")}
      {kind === "file_contains" && <>{f("path", "File path", "src/auth.py")}{f("pattern", "Must match (regex)", "def login")}</>}
      {kind === "http" && <>
        <label className="block"><span className="label">Method</span><select className="input" value={spec.method} onChange={(e) => set({ ...spec, method: e.target.value })}>{["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => <option key={m}>{m}</option>)}</select></label>
        {f("path", "Page or path on the published site", "/pricing")}{f("expect_status", "Expected status", "200", "number")}{f("expect_contains", "Page contains (optional)")}
      </>}
      {kind === "command" && <>
        <div className="sm:col-span-2">{f("cmd", "Command (the files are at /work)", "pytest -q")}</div>
        <div className="sm:col-span-2">{f("setup", "Install step (optional)", "pip install -r requirements.txt")}</div>
        <label className="block"><span className="label">Environment</span><select className="input" value={spec.image} onChange={(e) => set({ ...spec, image: e.target.value })}><option>python:3.12-slim</option><option>node:20-slim</option></select></label>
        {f("timeout", "Timeout (seconds, max 300)", "120", "number")}
      </>}
    </div>
  );
}

export default function NewContract() {
  const router = useRouter();
  const { data: me } = useApi<any>("/me");
  const [step, setStep] = useState<"brief" | "edit">("brief");
  const [idea, setIdea] = useState("");
  const [budget, setBudget] = useState("");
  const [worker, setWorker] = useState("");
  const [workerInfo, setWorkerInfo] = useState<{ ok: boolean; msg: string }>();
  const [lang, setLang] = useState("en-IN");
  const [analysis, setAnalysis] = useState<any>(null);
  const [title, setTitle] = useState("");
  const [ms, setMs] = useState<Ms[]>([]);
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState<"" | "explain" | "draft" | "save">("");
  const [issues, setIssues] = useState<any[] | null>(null);
  const [checking, setChecking] = useState(false);
  const speech = useSpeech((t) => setIdea((v) => (v ? v + " " : "") + t), lang);

  const w = normalizeUsername(worker);
  useEffect(() => {
    setWorkerInfo(undefined);
    if (!w || usernameProblem(w)) return;
    const t = setTimeout(async () => {
      try {
        const u = await api(`/users/${w}`);
        setWorkerInfo(u.is_you ? { ok: false, msg: "That is your own username." } : !u.has_wallet ? { ok: false, msg: `@${u.handle} (${u.name || "user"}) has not connected a wallet yet. Ask them to open Settings first.` } : { ok: true, msg: `Found @${u.handle}${u.name ? ` (${u.name})` : ""}.` });
      } catch (e: any) { setWorkerInfo({ ok: false, msg: e.message }); }
    }, 400);
    return () => clearTimeout(t);
  }, [w]);

  const total = ms.reduce((s, m) => s + (Number(m.amount) || 0), 0);
  const saveIssue = !title.trim() ? "Add a contract title." : ms.length === 0 ? "Add at least one delivery part." : ms.some((m) => !m.title.trim()) ? "Name every delivery part." : ms.some((m) => !(Number(m.amount) > 0)) ? "Every delivery part needs a positive amount." : ms.some((m) => !m.deadline || new Date(m.deadline).getTime() <= Date.now()) ? "Every deadline must be in the future." : ms.some((m) => m.requirements.length === 0 || m.requirements.some((r) => !r.title.trim())) ? "Name every requirement so both sides know what will be checked." : null;
  const patchMs = (i: number, p: Partial<Ms>) => setMs(ms.map((m, k) => (k === i ? { ...m, ...p } : m)));
  const patchReq = (i: number, j: number, p: Partial<Req>) => patchMs(i, { requirements: ms[i].requirements.map((r, k) => (k === j ? { ...r, ...p } : r)) });
  const changeType = (i: number, t: string) => patchMs(i, { delivery_type: t, review_days: t === "product" ? 7 : ms[i].review_days, requirements: [newReq(t)] });

  async function explain() {
    setErr(undefined); setBusy("explain");
    try { setAnalysis(await api("/ai/idea", { body: { text: idea, budget: budget || null } })); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  }
  async function draft() {
    setErr(undefined); setBusy("draft");
    try {
      const d = await api("/compile", { body: { description: idea, budget: budget || null } });
      setTitle(d.title || analysis?.title || "");
      const b = Number(budget) || 0;
      setMs(d.milestones.map((m: any, i: number) => ({
        title: m.title, amount: b ? ((b * (m.share_pct ?? 100 / d.milestones.length)) / 100).toFixed(4).replace(/\.?0+$/, "") : "", deadline: inDays(7 * (i + 1)),
        delivery_type: m.delivery_type, review_days: m.review_days ?? 3,
        requirements: m.requirements.map((r: any) => ({ title: r.title, criteria: r.criteria ?? "", kind: r.kind, spec: r.spec, hidden: !!r.hidden })),
      })));
      setStep("edit");
    } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  }
  const scratch = () => { setMs([newMs(0)]); setStep("edit"); };

  async function check() {
    setErr(undefined); setChecking(true);
    try {
      const r = await api("/compile/review", { body: { description: idea, milestones: ms.map((m) => ({ title: m.title, requirements: m.requirements.map((q) => ({ ...q, title: q.title || "Untitled requirement" })) })) } });
      setIssues(r.issues);
    } catch (e: any) { setErr(e.message); } finally { setChecking(false); }
  }

  async function save() {
    setErr(undefined); setBusy("save");
    try {
      const { id } = await api("/contracts", { body: {
        title, description: idea, idea, freelancer_username: w || null, ai_notes: analysis,
        milestones: ms.map((m) => ({ ...m, deadline: new Date(m.deadline).toISOString() })) } });
      router.push(`/client/${id}`);
    } catch (e: any) { setErr(e.message); setBusy(""); }
  }

  if (step === "brief")
    return (
      <div className="max-w-2xl space-y-5">
        <h1>New contract</h1>
        {me && !me.wallet && <p className="rounded bg-warn-soft px-3 py-2 text-sm text-warn">Connect your wallet first: use the sidebar, then choose &quot;Link this wallet to your account&quot;. You need it to lock the payment.</p>}
        <div>
          <div className="flex items-end justify-between gap-2">
            <label className="label" htmlFor="idea">Describe what you want</label>
            <div className="mb-1 flex items-center gap-2">
              <select aria-label="Speaking language" className="input !w-auto !py-1 text-xs" value={lang} onChange={(e) => setLang(e.target.value)}>{SPEECH_LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              {speech.supported && <button type="button" className={speech.listening ? "btn-danger !py-1 text-xs" : "btn-ghost !py-1 text-xs"} onClick={speech.listening ? speech.stop : speech.start} aria-pressed={speech.listening}>{speech.listening ? "Stop listening" : "Speak"}</button>}
            </div>
          </div>
          <textarea id="idea" className="input min-h-40" placeholder="Write or speak in English, Hindi or Hinglish. Example: Mujhe apni bakery ke liye ek website chahiye jisme menu, order form aur contact page ho. Saath mein 20 gift boxes bhi chahiye." value={idea} onChange={(e) => setIdea(e.target.value)} />
          <Err>{speech.error}</Err>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div><label className="label" htmlFor="bu">Total budget ({SYMBOL}, optional)</label><input id="bu" className="input" inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} /></div>
          <div>
            <label className="label" htmlFor="wk">Worker&apos;s username</label>
            <input id="wk" className="input" placeholder="e.g. @sachin_web" value={worker} onChange={(e) => setWorker(e.target.value.toLowerCase())} />
            <p className={`mt-1 text-xs ${workerInfo ? (workerInfo.ok ? "text-ok" : "text-bad") : "text-mute"}`}>{workerInfo?.msg ?? "Leave empty to post an open job that anyone can accept."}</p>
          </div>
        </div>
        <Err>{err}</Err>
        {analysis && (
          <section className="panel space-y-3 p-4" aria-label="What the AI understood">
            <h2>{analysis.title || "Your idea"}</h2>
            <p className="text-sm">{analysis.understood}</p>
            {analysis.deliverables?.length > 0 && <ul className="space-y-1 text-sm">{analysis.deliverables.map((d: any, i: number) => <li key={i}><b>{d.title}</b> <span className="chip">{DELIVERY[d.type]?.label}</span> <span className="text-mute">{d.detail}</span></li>)}</ul>}
            {analysis.suggestions?.length > 0 && <div><p className="text-sm font-semibold">Suggestions</p><ul className="list-disc pl-5 text-sm">{analysis.suggestions.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul></div>}
            {analysis.questions?.length > 0 && <div><p className="text-sm font-semibold">Please add these details to your description</p><ul className="list-disc pl-5 text-sm">{analysis.questions.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul></div>}
            {analysis.how_checked?.length > 0 && <div><p className="text-sm font-semibold">How the work will be checked</p><ul className="list-disc pl-5 text-sm">{analysis.how_checked.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul></div>}
          </section>
        )}
        <div className="flex flex-wrap gap-3">
          <button className="btn-ghost" disabled={!!busy || idea.trim().length < 10} onClick={explain}>{busy === "explain" ? "Thinking…" : analysis ? "Explain again" : "Explain my idea"}</button>
          <button className="btn-primary" disabled={!!busy || idea.trim().length < 10 || (!!worker && workerInfo?.ok === false)} onClick={draft}>{busy === "draft" ? "Building checks…" : "Build the checks"}</button>
          <button className="btn-ghost" disabled={!!busy} onClick={scratch}>Start blank</button>
        </div>
      </div>
    );

  return (
    <div className="max-w-3xl space-y-6">
      <div><h1>Review the contract</h1><p className="mt-1 text-sm text-mute">These checks decide when payment is released. {w ? `Only @${w} can accept this contract.` : "This is an open job: any worker can read it and accept."} After you pay, the terms cannot be changed.</p></div>
      <div><label className="label" htmlFor="t">Title</label><input id="t" className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
      {ms.map((m, i) => (
        <section key={i} className="panel space-y-4 p-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
            <label className="block"><span className="label">Part {i + 1}: what is delivered</span><input className="input" value={m.title} onChange={(e) => patchMs(i, { title: e.target.value })} /></label>
            <label className="block"><span className="label">Type</span><select className="input" value={m.delivery_type} onChange={(e) => changeType(i, e.target.value)}>{Object.entries(DELIVERY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></label>
          </div>
          <p className="text-xs text-mute">{DELIVERY[m.delivery_type]?.hint}</p>
          <div className="grid gap-3 sm:grid-cols-[8rem_12rem_10rem_auto]">
            <label className="block"><span className="label">Amount ({SYMBOL})</span><input className="input" inputMode="decimal" value={m.amount} onChange={(e) => patchMs(i, { amount: e.target.value })} /></label>
            <label className="block"><span className="label">Deadline</span><input className="input" type="datetime-local" value={m.deadline} onChange={(e) => patchMs(i, { deadline: e.target.value })} /></label>
            <label className="block"><span className="label">Review days</span><input className="input" type="number" min={1} max={30} value={m.review_days} onChange={(e) => patchMs(i, { review_days: Math.min(30, Math.max(1, Number(e.target.value) || 1)) })} /></label>
            {ms.length > 1 && <button className="link self-end pb-2 text-sm text-bad" onClick={() => setMs(ms.filter((_, k) => k !== i))}>Remove part</button>}
          </div>
          {m.requirements.map((r, j) => (
            <div key={j} className="space-y-3 rounded border border-line p-3">
              <div className="grid gap-3 sm:grid-cols-[1fr_15rem]">
                <label className="block"><span className="label">Requirement</span><input className="input" value={r.title} onChange={(e) => patchReq(i, j, { title: e.target.value })} /></label>
                <label className="block"><span className="label">Checked by</span><select className="input" value={r.kind} disabled={m.delivery_type === "product"} onChange={(e) => patchReq(i, j, { kind: e.target.value, spec: blank(e.target.value) })}>{AUTO_KINDS[m.delivery_type].map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}</select></label>
              </div>
              <Spec kind={r.kind} spec={r.spec} set={(spec) => patchReq(i, j, { spec })} />
              {m.delivery_type !== "product" && (
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={r.hidden} onChange={(e) => patchReq(i, j, { hidden: e.target.checked })} />Hidden from the worker until the contract completes</label>
                  {m.requirements.length > 1 && <button className="link text-sm text-bad" onClick={() => patchMs(i, { requirements: m.requirements.filter((_, k) => k !== j) })}>Remove</button>}
                </div>
              )}
            </div>
          ))}
          {m.delivery_type !== "product" && <button className="btn-ghost" onClick={() => patchMs(i, { requirements: [...m.requirements, newReq(m.delivery_type)] })}>Add requirement</button>}
        </section>
      ))}
      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost" onClick={() => setMs([...ms, newMs(ms.length)])}>Add website / software part</button>
        <button className="btn-ghost" onClick={() => setMs([...ms, newMs(ms.length, "product")])}>Add physical product</button>
      </div>
      <section className="panel space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex-1"><h2>Check for vague requirements</h2><p className="text-sm text-mute">Finds checks that can&apos;t prove anything or wording two people could read differently. Fixing these now prevents disputes later.</p></div>
          <button className="btn-ghost" onClick={check} disabled={checking}>{checking ? "Checking…" : "Check my requirements"}</button>
        </div>
        {issues && (issues.length === 0 ? <p className="text-sm text-ok">No problems found. Every requirement can be checked objectively.</p> : (
          <ul className="divide-y divide-line">
            {issues.map((x, k) => (
              <li key={k} className="flex gap-3 py-2 text-sm">
                <span className={`mt-0.5 h-fit shrink-0 rounded px-1.5 py-0.5 text-xs font-semibold ${x.severity === "warn" ? "bg-warn-soft text-warn" : "bg-brand-soft text-brand"}`}>{x.severity === "warn" ? "Fix" : "Tip"}</span>
                <span><span className="font-medium">Part {x.milestone + 1}{x.requirement != null ? `, ${ms[x.milestone]?.requirements[x.requirement]?.title || `requirement ${x.requirement + 1}`}` : ""}.</span> {x.issue} <span className="text-mute">{x.suggestion}</span></span>
              </li>
            ))}
          </ul>
        ))}
      </section>
      <Err>{err}</Err>
      <div className="flex flex-wrap items-center gap-4 border-t border-line pt-4">
        <p className="font-semibold">Total {total.toLocaleString(undefined, { maximumFractionDigits: 6 })} {SYMBOL}</p>
        <button className="btn-primary" disabled={!!busy || !!saveIssue || total <= 0} onClick={save}>{busy === "save" ? "Saving…" : "Save and go to payment"}</button>
        <button className="link text-sm" onClick={() => setStep("brief")}>Back</button>
        <Link href="/client" className="link text-sm">Cancel</Link>
      </div>
      {saveIssue && <p className="text-sm text-warn">{saveIssue}</p>}
    </div>
  );
}
