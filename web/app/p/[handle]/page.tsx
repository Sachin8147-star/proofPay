"use client";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Loading, Stat, AddrLink } from "@/components/ui";
import { useApi } from "@/lib/api";
import { fmtAmt } from "@/lib/chain";
import { short } from "@/lib/labels";

export default function Passport() {
  const { handle } = useParams<{ handle: string }>();
  const { data, error } = useApi<any>(`/passport/${handle}`);
  return (
    <main className="mx-auto max-w-3xl space-y-5 px-5 py-8">
      <Link href="/" className="font-bold">ProofPay</Link>
      {error ? <p className="text-bad">{error.message}</p> : !data ? <Loading /> : (
        <>
          <div><h1>{data.name ?? data.handle}</h1><p className="mt-1 flex items-center gap-2 text-sm text-mute">Verified work record <AddrLink a={data.wallet} /></p></div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label="Contracts completed" value={data.stats.contracts_completed} />
            <Stat label="Milestones paid" value={data.stats.milestones_released} />
            <Stat label="Earned" value={fmtAmt(data.stats.earned)} />
            <Stat label="Test pass rate" value={data.stats.pass_rate == null ? "No runs yet" : `${data.stats.pass_rate}%`} />
            <Stat label="Verification runs" value={data.stats.verification_runs} />
            <Stat label="Disputes" value={data.stats.disputes} />
          </div>
          <h2>Paid milestones</h2>
          <ul className="panel divide-y divide-line">
            {data.records.length === 0 && <li className="p-4 text-sm text-mute">No paid milestones yet.</li>}
            {data.records.map((r: any, i: number) => (
              <li key={i} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <span className="flex-1"><span className="font-medium">{r.title}</span>, {r.milestone}</span><span>{fmtAmt(r.amount)}</span>
                {r.evidence_hash && <Link className="chip link" href={`/verify/${r.evidence_hash}`}>evidence {short(r.evidence_hash, 4)}</Link>}
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
