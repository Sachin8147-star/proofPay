"use client";
import { AddrLink, Err, Loading, Stat } from "@/components/ui";
import { useApi } from "@/lib/api";
import { fmtAmt, fmtWei } from "@/lib/chain";

export default function Overview() {
  const { data: o } = useApi<any>("/admin/overview", 10000);
  const { data: c, error } = useApi<any>("/admin/chain", 10000);
  if (!o) return <Loading />;
  return (
    <div className="space-y-6">
      <h1>Overview</h1>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Users" value={o.users} /><Stat label="Contracts" value={o.contracts} /><Stat label="In progress" value={o.active} />
        <Stat label="Locked in escrow" value={fmtAmt(o.locked)} /><Stat label="Paid out" value={fmtAmt(o.released)} /><Stat label="Open disputes" value={o.open_disputes} />
        <Stat label="Verification runs" value={o.runs} /><Stat label="Runs that errored" value={o.runs_errored} />
      </div>
      <h2>Chain and services</h2>
      <Err>{error?.message}</Err>
      {c && (
        <dl className="panel grid gap-3 p-4 text-sm sm:grid-cols-2">
          <div><dt className="text-mute">Chain ID</dt><dd>{c.chain_id}</dd></div>
          <div><dt className="text-mute">Latest block / indexed</dt><dd>{c.head} / {c.indexed} <span className={c.lag > 20 ? "text-bad" : "text-ok"}>(lag {c.lag})</span></dd></div>
          <div><dt className="text-mute">Escrow contract</dt><dd><AddrLink a={c.escrow} /> {c.paused ? <span className="font-semibold text-bad">Paused</span> : c.paused === false ? "Active" : ""}</dd></div>
          <div><dt className="text-mute">Verifier wallet</dt><dd><AddrLink a={c.verifier} /> {c.verifier_balance_wei != null && <span className={BigInt(c.verifier_balance_wei) < 10n ** 16n ? "text-bad" : ""}>{fmtWei(c.verifier_balance_wei)}</span>}</dd></div>
        </dl>
      )}
    </div>
  );
}
