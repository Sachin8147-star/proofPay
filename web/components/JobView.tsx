"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/api";
import { fmtAmt } from "@/lib/chain";
import { DELIVERY, KIND_LABEL, date } from "@/lib/labels";
import Chat from "./Chat";
import { Badge, Err, Loading } from "./ui";
import { useTx } from "./useTx";

/** What a prospective worker sees: the paid offer, the exact checks, a private chat with the poster, and the Accept button. */
export default function JobView({ id }: { id: string }) {
  const router = useRouter();
  const { data: c, error, mutate } = useApi<any>(`/contracts/${id}`, 8000);
  const { data: me } = useApi<any>("/me");
  const tx = useTx();
  const [note, setNote] = useState<string>();
  useEffect(() => { if (c && c.role !== "viewer") router.replace(`/${c.role}/${id}`); }, [c, id, router]);
  if (error) return <Err>{error.message}</Err>;
  if (!c || c.role !== "viewer") return <Loading />;

  async function accept() {
    setNote(undefined);
    const h = await tx.send("Accepting the job", "acceptContract", [c.escrow_id], me?.wallet ?? null);
    if (h) { setNote("You accepted. Opening your work page…"); mutate(); setTimeout(() => router.replace(`/freelancer/${id}`), 4000); }
  }
  const types = [...new Set<string>(c.milestones.map((m: any) => m.delivery_type))];
  return (
    <div className="space-y-6">
      <div>
        <Link href="/jobs" className="link text-sm">← All open jobs</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3"><h1>{c.title}</h1><span className="rounded bg-ok-soft px-2 py-0.5 text-xs font-semibold text-ok">{fmtAmt(c.total_amount)} already locked</span></div>
        <p className="mt-1 text-sm text-mute">Posted by {c.client?.handle ? `@${c.client.handle}` : c.client?.name} · {types.map((t) => DELIVERY[t]?.label).join(", ")}</p>
        {c.description && <p className="mt-3 max-w-2xl whitespace-pre-line text-sm">{c.description}</p>}
      </div>
      <div className="panel space-y-3 border-brand/40 p-4">
        <p className="text-sm">The buyer has <b>already paid</b>: the money is held by the escrow contract and is released to you when your delivered work passes the checks below. Ask questions in the chat first if anything is unclear, then accept.</p>
        {me && !me.wallet && <p className="rounded bg-warn-soft px-3 py-2 text-sm text-warn">Connect your wallet and link it (sidebar) before accepting.</p>}
        {tx.busy ? <p className="font-semibold">{tx.busy}… confirm in your wallet.</p> : <button className="btn-primary" disabled={!me?.wallet} onClick={accept}>Accept this job</button>}
        {note && <p className="text-sm text-ok">{note}</p>}
        <Err>{tx.error}</Err>
      </div>
      <section className="space-y-4">
        {c.milestones.map((m: any, i: number) => (
          <article key={m.id} className="panel overflow-hidden">
            <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
              <h2 className="min-w-0 flex-1">{i + 1}. {m.title} <span className="chip align-middle">{DELIVERY[m.delivery_type]?.label}</span></h2>
              <span className="text-sm text-mute">Due {date(m.deadline)}</span><span className="font-semibold">{fmtAmt(m.amount)}</span>
              <Badge map={{ funded: ["Money locked", "bg-brand-soft text-brand"] }} value={m.status} />
            </header>
            <ul className="divide-y divide-line">
              {c.requirements.filter((r: any) => r.milestone_idx === i).map((r: any) => (
                <li key={r.id} className="px-4 py-2.5"><p className="text-sm font-medium">{r.title}</p>
                  <p className="text-xs text-mute">{KIND_LABEL[r.kind] ?? r.kind}{r.kind === "ai_review" && r.spec?.claim ? `. Must be true: ${r.spec.claim}` : ""}</p></li>
              ))}
            </ul>
            <p className="border-t border-line bg-paper px-4 py-2 text-xs text-mute">{DELIVERY[m.delivery_type]?.hint} Review window after checking: {Math.round(m.window_secs / 86400)} day(s).</p>
          </article>
        ))}
      </section>
      <Chat id={id} title={`Chat with @${c.client?.handle ?? "the poster"}`} />
    </div>
  );
}
