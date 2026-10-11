"use client";
import Link from "next/link";
import { useState } from "react";
import { Empty, Loading } from "@/components/ui";
import { useApi } from "@/lib/api";
import { fmtAmt } from "@/lib/chain";
import { DELIVERY, date } from "@/lib/labels";

export default function Jobs() {
  const [q, setQ] = useState("");
  const { data, error } = useApi<any[]>(`/jobs?q=${encodeURIComponent(q)}`, 15000);
  return (
    <div className="space-y-5">
      <div><h1>Open jobs</h1><p className="mt-1 text-sm text-mute">Every job here is already paid for: the money is locked in escrow. Open one, read the checks, chat with the poster, then accept.</p></div>
      <div><label className="sr-only" htmlFor="q">Search jobs</label><input id="q" className="input max-w-md" placeholder="Search jobs (website, logo, app…)" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      {error ? <p className="text-bad">{error.message}</p> : !data ? <Loading /> : data.length === 0 ? (
        <Empty title={q ? "No jobs match your search" : "No open jobs right now"}>Check back soon. You can also ask someone to send you their username so they can hire you directly.</Empty>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {data.map((j) => (
            <li key={j.id} className="panel p-4">
              <Link href={`/jobs/${j.id}`} className="block space-y-2">
                <div className="flex items-start justify-between gap-3"><h2 className="min-w-0">{j.title}</h2><span className="shrink-0 font-semibold">{fmtAmt(j.total)}</span></div>
                <p className="line-clamp-3 text-sm text-mute">{j.description}</p>
                <p className="flex flex-wrap items-center gap-2 text-xs text-mute">{j.types.map((t: string) => <span key={t} className="chip">{DELIVERY[t]?.label}</span>)}<span>{j.milestones.length} part(s)</span>{j.earliest_deadline && <span>first due {date(j.earliest_deadline)}</span>}<span>by @{j.poster.handle}</span></p>
                <span className="link text-sm">View and chat →</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
