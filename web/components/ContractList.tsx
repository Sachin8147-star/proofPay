"use client";
import Link from "next/link";
import { useApi } from "@/lib/api";
import { fmtAmt } from "@/lib/chain";
import { CONTRACT_STATUS } from "@/lib/labels";
import { Badge, Empty, Loading, Stat } from "./ui";

export default function ContractList({ role }: { role: "client" | "freelancer" }) {
  const { data: rows, error } = useApi<any[]>(`/contracts?role=${role}`, 8000);
  const { data: sum } = useApi<any>("/me/summary", 8000);
  const s = sum?.[role];
  const stats = role === "client" ? [["Locked in escrow", s?.locked], ["Paid out", s?.released]] : [["Incoming (locked)", s?.incoming], ["Earned", s?.earned]];
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1>{role === "client" ? "Contracts you created" : "Your work"}</h1>
        {role === "client" ? <Link href="/client/new" className="btn-primary">New contract</Link> : <Link href="/jobs" className="btn-primary">Find open jobs</Link>}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {stats.map(([l, v]) => <Stat key={l} label={l!} value={v ? fmtAmt(v) : "…"} />)}
        <Stat label="Contracts" value={s?.contracts ?? "…"} />
      </div>
      {error ? <p className="text-bad">{String(error.message)}</p> : !rows ? <Loading /> : rows.length === 0 ? (
        <Empty title={role === "client" ? "No contracts yet" : "No work yet"}>
          {role === "client" ? "Describe what you want in your own words. The AI explains it back and builds the checks. You pay, the money is locked, and the worker is paid only when the work passes." : "Share your username with a buyer, or browse open jobs. Contracts that name you appear here once the buyer has paid."}
        </Empty>
      ) : (
        <ul className="panel divide-y divide-line">
          {rows.map((c) => {
            const paid = c.milestones.filter((m: any) => m.status === "released").length;
            return (
              <li key={c.id}>
                <Link href={`/${role}/${c.id}`} className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-paper">
                  <span className="min-w-0 flex-1 truncate font-semibold">{c.title}</span>
                  <span className="text-sm text-mute">{paid} of {c.milestones.length} parts paid</span>
                  <span className="w-32 text-right text-sm font-medium">{fmtAmt(c.total_amount)}</span>
                  <Badge map={CONTRACT_STATUS} value={c.status} />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
