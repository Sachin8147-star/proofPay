"use client";
import Link from "next/link";
import { useState } from "react";
import { Empty, Err, HashChip, Loading } from "@/components/ui";
import { useTx } from "@/components/useTx";
import { useApi } from "@/lib/api";
import { date } from "@/lib/labels";

export default function Disputes() {
  const { data, mutate } = useApi<any[]>("/admin/disputes", 8000);
  const tx = useTx();
  const [pct, setPct] = useState<Record<string, number>>({});
  if (!data) return <Loading />;
  const resolve = async (d: any) => {
    const h = await tx.send("Resolving", "resolve", [d.contract.escrow_id, BigInt(d.milestone_idx), Math.round((pct[d.id] ?? 50) * 100)], null);
    if (h) mutate();
  };
  return (
    <div className="space-y-4">
      <h1>Disputes</h1>
      <Err>{tx.error}</Err>
      {!data.length && <Empty title="No disputes" />}
      {data.map((d) => (
        <article key={d.id} className="panel space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-3"><h2 className="flex-1">{d.contract?.title} · milestone {d.milestone_idx + 1}</h2><span className="rounded bg-line px-2 py-0.5 text-xs font-semibold">{d.status}</span></div>
          <p className="whitespace-pre-line text-sm">{d.reason}</p>
          <p className="flex flex-wrap items-center gap-3 text-xs text-mute">Opened {date(d.created_at)} {d.evidence_hash && <Link className="link" href={`/verify/${d.evidence_hash}`}>Review evidence <HashChip h={d.evidence_hash} /></Link>}</p>
          {d.status === "open" && (
            <div className="flex flex-wrap items-center gap-4 border-t border-line pt-3">
              <label className="text-sm" htmlFor={`p${d.id}`}>Freelancer receives <strong>{pct[d.id] ?? 50}%</strong>, client gets the rest</label>
              <input id={`p${d.id}`} type="range" min={0} max={100} step={5} value={pct[d.id] ?? 50} onChange={(e) => setPct({ ...pct, [d.id]: Number(e.target.value) })} />
              <button className="btn-primary" disabled={!!tx.busy} onClick={() => resolve(d)}>{tx.busy ? "Confirm in wallet…" : "Resolve on-chain"}</button>
            </div>
          )}
          {d.status === "resolved" && <p className="text-sm text-ok">Resolved: {d.freelancer_bps / 100}% to the freelancer.</p>}
        </article>
      ))}
    </div>
  );
}
