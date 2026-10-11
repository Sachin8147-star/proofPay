"use client";
import Link from "next/link";
import { useState } from "react";
import { AddrLink, Empty, Loading, Stat, TxLink } from "@/components/ui";
import { useApi } from "@/lib/api";
import { EXPLORER, fmtAmt, fmtWei } from "@/lib/chain";
import { date } from "@/lib/labels";

export default function Wallet() {
  const { data, error } = useApi<any>("/me/wallet-summary", 15000);
  const [open, setOpen] = useState<string | null>(null);
  const addr: string | null | undefined = data?.address;
  const { data: net } = useApi<any>(addr ? `/wallet/${addr}` : null, 30000);
  const faucet = process.env.NEXT_PUBLIC_MST_FAUCET_URL;
  const bal = data?.balance_wei != null ? BigInt(data.balance_wei) : null;
  const mine = (data?.locked ?? []).filter((x: any) => x.role === "client");
  const incoming = (data?.locked ?? []).filter((x: any) => x.role === "freelancer");

  const LockedTable = ({ rows, title, hint }: { rows: any[]; title: string; hint: string }) => (
    <section className="space-y-2">
      <div><h2>{title}</h2><p className="text-sm text-mute">{hint}</p></div>
      {rows.length === 0 ? <p className="text-sm text-mute">Nothing here.</p> : (
        <ul className="panel divide-y divide-line">
          {rows.map((x) => {
            const k = `${x.contract_id}:${x.milestone_idx}`;
            return (
              <li key={k} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-3">
                  <Link href={`/${x.role}/${x.contract_id}`} className="min-w-0 flex-1 truncate font-medium hover:underline">{x.title} <span className="text-mute">· {x.milestone}</span></Link>
                  <span className="font-semibold">{fmtAmt(x.amount)}</span>
                  <button className="btn-ghost !h-7 !w-7 !rounded-full !p-0 text-xs" aria-label={`Why is this locked? ${x.title}`} aria-expanded={open === k} onClick={() => setOpen(open === k ? null : k)}>i</button>
                </div>
                {open === k && <div className="mt-2 space-y-1 rounded bg-brand-soft px-3 py-2 text-sm"><p><b>Why locked:</b> {x.why}</p><p><b>When it unlocks:</b> {x.unlock}</p></div>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );

  return (
    <div className="space-y-6">
      <h1>Wallet</h1>
      {error ? <p className="text-bad">{error.message}</p> : !data ? <Loading /> : !addr ? <Empty title="No wallet linked yet">Connect your browser wallet in the sidebar, then choose &quot;Link this wallet to your account&quot;.</Empty> : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Available now (unlocked)" value={bal != null ? fmtWei(bal) : "Unavailable"} />
            <Stat label="Locked for your jobs" value={fmtAmt(data.locked_total)} />
            <Stat label="Locked for you (incoming)" value={fmtAmt(data.incoming_total)} />
            <Stat label="Address" value={<AddrLink a={addr} />} />
          </div>
          {bal === 0n && <p className="rounded bg-warn-soft px-3 py-2 text-sm text-warn">This wallet has no testnet balance, so it cannot pay for contracts or gas.{faucet && <> <a className="underline" href={faucet} target="_blank" rel="noreferrer">Get testnet funds</a>.</>}</p>}
          <LockedTable rows={mine} title="Money you locked" hint="Held safely by the escrow contract. It leaves your wallet when you pay and returns if the job is cancelled or fails." />
          <LockedTable rows={incoming} title="Money waiting for you" hint="Already paid in by the buyer. It becomes yours when your delivered work passes." />
          <section className="space-y-2">
            <h2>Activity</h2>
            {data.activity.length === 0 ? <Empty title="No activity yet">Payments, releases, refunds and cancellations on your contracts will show up here.</Empty> : (
              <ul className="panel divide-y divide-line">
                {data.activity.map((a: any, i: number) => (
                  <li key={i} className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm">
                    <span className={`w-6 text-center font-bold ${a.direction === "in" ? "text-ok" : a.direction === "out" ? "text-bad" : "text-mute"}`} aria-label={a.direction ?? "event"}>{a.direction === "in" ? "+" : a.direction === "out" ? "−" : "•"}</span>
                    <span className="min-w-0 flex-1">{a.text}<span className="block text-xs text-mute">{date(a.when)}</span></span>
                    {a.amount && <span className="font-semibold">{fmtAmt(a.amount)}</span>}
                    <TxLink hash={a.tx_hash} />
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="space-y-2">
            <h2>All network transactions</h2>
            {!net ? <Loading /> : !net.explorer_ok ? <p className="text-sm text-mute">The explorer is not answering right now. <a className="link" href={`${EXPLORER}/address/${addr}`} target="_blank" rel="noreferrer">Open it on MSTScan</a>.</p>
              : net.transactions.length === 0 ? <p className="text-sm text-mute">No transactions from this address yet.</p> : (
                <div className="panel overflow-x-auto"><table className="w-full text-left text-sm">
                  <thead className="border-b border-line text-mute"><tr><th className="px-3 py-2">When</th><th className="px-3 py-2">Action</th><th className="px-3 py-2">Direction</th><th className="px-3 py-2">Value</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Hash</th></tr></thead>
                  <tbody className="divide-y divide-line">{net.transactions.map((t: any) => (
                    <tr key={t.hash}><td className="px-3 py-2">{date(t.timestamp)}</td><td className="px-3 py-2">{t.method ?? "Transfer"}</td><td className="px-3 py-2">{t.from?.toLowerCase() === addr.toLowerCase() ? "Out" : "In"}</td>
                      <td className="px-3 py-2">{fmtWei(t.value ?? "0")}</td><td className={`px-3 py-2 ${t.status === "ok" ? "text-ok" : "text-bad"}`}>{t.status === "ok" ? "Success" : t.status ?? ""}</td><td className="px-3 py-2"><TxLink hash={t.hash} /></td></tr>))}</tbody>
                </table></div>
              )}
          </section>
        </>
      )}
    </div>
  );
}
