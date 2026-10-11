"use client";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Loading, TxLink } from "@/components/ui";
import { useApi } from "@/lib/api";

export default function Verify() {
  const { hash } = useParams<{ hash: string }>();
  const { data, error } = useApi<any>(`/verify/${hash}`);
  const r = data?.report;
  return (
    <main className="mx-auto max-w-3xl space-y-5 px-5 py-8">
      <Link href="/" className="font-bold">ProofPay</Link>
      <h1>Evidence check</h1>
      {error ? <p className="text-bad">{error.message}</p> : !data ? <Loading /> : (
        <>
          <p className={`rounded px-3 py-2 text-sm font-medium ${data.matches ? "bg-ok-soft text-ok" : "bg-bad-soft text-bad"}`}>
            {data.matches ? "The stored report hashes to exactly this value, so it has not been altered." : "The stored report does NOT match this hash."}
          </p>
          <dl className="panel space-y-2 p-4 text-sm">
            <div><dt className="text-mute">Evidence hash (sha256)</dt><dd className="break-all font-mono text-xs">{data.hash}</dd></div>
            <div><dt className="text-mute">Recorded on-chain</dt><dd className="flex flex-wrap gap-2">{data.attestations.length ? data.attestations.map((a: any) => <TxLink key={a.tx_hash} hash={a.tx_hash} />) : "Not yet indexed"}</dd></div>
            <div><dt className="text-mute">Contract</dt><dd>{data.contract.title}</dd></div>
            <div><dt className="text-mute">What was checked</dt><dd className="break-all">{r.source === "zip" ? `Uploaded zip${r.file_name ? `: ${r.file_name}` : ""}` : r.source === "shipment" ? `Shipment declared by the seller${r.shipment?.carrier ? ` (${r.shipment.carrier} ${r.shipment.tracking ?? ""})` : ""}` : r.source === "site" ? `Published site: ${r.deploy_url ?? ""}` : <>{r.repo} @ <span className="font-mono">{String(r.commit_sha ?? "").slice(0, 12)}</span></>}</dd></div>
            <div><dt className="text-mute">Result</dt><dd className="font-semibold">{r.passed ? "Passed" : "Failed"}: {r.summary.passed} of {r.summary.total} tests</dd></div>
          </dl>
          <ul className="panel divide-y divide-line">
            {r.results.map((t: any) => (
              <li key={t.requirement_id ?? t.title} className="flex gap-3 px-4 py-2.5 text-sm">
                <span className={`w-5 font-bold ${t.passed ? "text-ok" : "text-bad"}`}>{t.passed ? "✓" : "✕"}</span>
                <span className="flex-1">{t.title}{t.detail ? <span className="block text-xs text-mute">{String(t.detail).slice(0, 300)}</span> : null}</span>{t.ms != null && <span className="text-xs text-mute">{t.ms} ms</span>}
              </li>
            ))}
          </ul>
          <details className="panel p-4 text-sm"><summary className="cursor-pointer font-semibold">Raw report</summary><pre className="mt-2 overflow-x-auto font-mono text-xs">{JSON.stringify(r, null, 2)}</pre></details>
        </>
      )}
    </main>
  );
}
