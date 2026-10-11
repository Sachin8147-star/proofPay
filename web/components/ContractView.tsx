"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useReadContract } from "wagmi";
import { api, useApi } from "@/lib/api";
import { ABI, ESCROW, fmtAmt, mst } from "@/lib/chain";
import { CONTRACT_STATUS, DELIVERY, KIND_LABEL, MILESTONE_STATUS, date, short } from "@/lib/labels";
import Chat from "./Chat";
import Submit from "./Submit";
import Threads from "./Threads";
import { AddrLink, Badge, Err, HashChip, Loading, TxLink } from "./ui";
import { useTx } from "./useTx";

const MAX_RUNS = 5; // matches max_runs_per_milestone on the server
const rd = (fn: string, args: unknown[], enabled: boolean) =>
  useReadContract({ address: ESCROW, abi: ABI, functionName: fn, args, chainId: mst.id, query: { enabled: enabled && !!ESCROW, refetchInterval: 10000 } });
const ZERO = "0x0000000000000000000000000000000000000000";

export default function ContractView({ id, initial }: { id: string; initial?: any }) {
  const router = useRouter();
  const { data: fetched, mutate, error } = useApi<any>(initial ? null : `/contracts/${id}`, 5000);
  const c = initial ?? fetched;
  const tx = useTx();
  const [note, setNote] = useState<string>();
  const [err, setErr] = useState<string>();
  const eid = c?.escrow_id as `0x${string}`;
  const live = c?.status === "active";
  const { data: cms } = rd("getMilestones", [eid], live) as { data?: any[] };
  const { data: grace } = rd("refundGrace", [], live) as { data?: bigint };

  if (error) return <Err>{error.message}</Err>;
  if (!c) return <Loading />;
  const isClient = c.role === "client", isWorker = c.role === "freelancer";
  const clientW = c.client?.wallet, freeW = c.freelancer_wallet;
  const now = Math.floor(Date.now() / 1000);

  async function act(label: string, fn: string, args: unknown[], expect: string | null, value?: bigint, after?: string) {
    setNote(undefined); setErr(undefined);
    const h = await tx.send(label, fn, args, expect, value);
    if (h) { setNote(after ?? "Confirmed on the blockchain. This page updates in a few seconds."); mutate(); }
  }
  const pay = async () => {
    const p = await api<any>(`/contracts/${id}/chain-params`);
    await act("Locking your payment", "createEscrow", [p.escrow_id, p.freelancer, p.contract_hash, p.hidden_tests_hash, p.amounts_wei.map(BigInt), p.deadlines.map(BigInt), p.windows.map(BigInt)], clientW, BigInt(p.total_wei),
      "Payment locked. The worker can see the contract now.");
  };
  const accept = () => act("Accepting the contract", "acceptContract", [eid], c.is_open ? null : freeW, undefined, "You accepted. The money stays locked until you deliver and the work passes.");
  const del = async () => { try { await api(`/contracts/${id}`, { method: "DELETE" }); router.replace("/client"); } catch (e: any) { setErr(e.message); } };

  const banner: Record<string, Record<string, React.ReactNode>> = {
    client: {
      draft: <><p>This contract is saved but <b>not paid yet</b>. Paying locks <b>{fmtAmt(c.total_amount)}</b> in the escrow contract on the blockchain: nobody can take it until the work is delivered and checked. Until someone accepts, you can take it back for free.</p>
        {!ESCROW && <p className="rounded bg-bad-soft px-3 py-2 text-sm text-bad">Payments are not configured yet. Deploy the ProofPay escrow contract, then set <code>NEXT_PUBLIC_ESCROW_ADDRESS</code> in <code>web/.env.local</code> and <code>ESCROW_ADDRESS</code> in the root <code>.env</code>.</p>}
        <div className="flex gap-2"><button className="btn-primary" disabled={!ESCROW} onClick={pay}>Pay and lock {fmtAmt(c.total_amount)}</button><button className="btn-danger" onClick={del}>Delete draft</button></div></>,
      open: <><p>{c.is_open ? "Your money is locked and this job is on the open jobs board. Workers can read it and chat with you before accepting." : <>Your money is locked. Waiting for <b>@{c.freelancer_handle}</b> to accept. Share this page&apos;s link or tell them to open <b>Work</b>.</>} You can take the money back until someone accepts.</p>
        <button className="btn-danger" onClick={() => act("Taking your money back", "revoke", [eid], clientW, undefined, "Contract cancelled and your money was returned.")}>Revoke and get my money back</button></>,
      active: c.cancel_requested
        ? <><p>You asked to cancel. The money returns only if the worker agrees.</p><button className="btn-ghost" onClick={() => act("Withdrawing the request", "withdrawCancel", [eid], clientW)}>Withdraw my request</button></>
        : <><p>Work has started. Each part is paid after its checks pass and the review window ends, or earlier when you approve. Want to stop? The worker has to agree.</p>
          <button className="btn-ghost" onClick={() => act("Sending the request", "requestCancel", [eid], clientW, undefined, "Request sent. Talk it over in the chat.")}>Request cancellation</button></>,
    },
    freelancer: {
      open: <><p>The buyer has already locked <b>{fmtAmt(c.total_amount)}</b> for this contract. Read every part and requirement below, then accept to start. Questions? Use the chat first.</p><button className="btn-primary" onClick={accept}>Accept the contract</button></>,
      active: c.cancel_requested
        ? <><p>The buyer asked to cancel. If you agree, the money that was not paid out yet returns to the buyer.</p><button className="btn-danger" onClick={() => act("Agreeing to cancel", "acceptCancel", [eid], freeW, undefined, "Cancelled by agreement. The unpaid money went back to the buyer.")}>Agree to cancel</button></>
        : <p>Deliver each part below. Use a free practice run first if you want to see how it will be checked.</p>,
    },
  };
  const msg = banner[c.role]?.[c.status];
  const other = isClient ? c.freelancer : c.client;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-3"><h1>{c.title}</h1><Badge map={CONTRACT_STATUS} value={c.status} /></div>
        {c.description && <p className="mt-2 max-w-2xl whitespace-pre-line text-sm text-mute">{c.description}</p>}
        <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-mute">
          <span>Total {fmtAmt(c.total_amount)}</span>
          <span>Buyer {c.client?.handle ? `@${c.client.handle}` : c.client?.name} <AddrLink a={clientW} /></span>
          <span>Worker {c.freelancer?.handle ? `@${c.freelancer.handle}` : c.is_open ? "anyone (open job)" : c.freelancer_handle ? `@${c.freelancer_handle}` : ""} <AddrLink a={freeW && freeW !== ZERO ? freeW : null} /></span>
          {c.contract_hash && <span>Terms <HashChip h={c.contract_hash} /></span>}
        </p>
      </div>

      {(msg || note || tx.busy || tx.error || err) && (
        <div className="panel space-y-3 border-brand/40 p-4">
          {tx.busy ? <p className="font-semibold">{tx.busy}… confirm in your wallet, then wait for the block.</p> : msg}
          {note && <p className="text-sm text-ok">{note}</p>}
          <Err>{tx.error ?? err}</Err>
        </div>
      )}
      {c.status === "completed" && <p className="rounded bg-ok-soft px-3 py-2 text-sm text-ok">Everything is settled. The hidden tests are now public below.</p>}
      {c.status === "cancelled" && <p className="rounded bg-line px-3 py-2 text-sm">This contract was cancelled. Money that was not paid out went back to the buyer.</p>}

      <section className="space-y-4">
        {c.milestones.map((m: any, i: number) => (
          <Milestone key={m.id} c={c} m={m} i={i} cm={cms?.[i]} grace={grace} now={now} isClient={isClient} isWorker={isWorker}
            act={act} eid={eid} clientW={clientW} refresh={mutate} setErr={setErr} />
        ))}
      </section>

      {c.status !== "draft" && (isClient && c.status === "open" && c.is_open ? <Threads id={id} /> : (c.status !== "open" || other) && <Chat id={id} title={other?.handle ? `Chat with @${other.handle}` : "Messages"} />)}

      {c.hidden_reveal && (
        <details className="panel p-4">
          <summary className="cursor-pointer font-semibold">Hidden tests (revealed)</summary>
          <p className="mt-2 text-sm text-mute">sha256(canonical JSON of these tests + salt) equals the commitment recorded when the money was locked: <HashChip h={c.hidden_tests_hash} /></p>
          <pre className="mt-2 overflow-x-auto rounded bg-paper p-3 font-mono text-xs">{JSON.stringify(c.hidden_reveal, null, 2)}</pre>
        </details>
      )}

      <details className="panel p-4">
        <summary className="cursor-pointer font-semibold">Blockchain activity ({c.events.length})</summary>
        <ul className="mt-3 space-y-1 text-sm">
          {c.events.map((e: any) => <li key={e.id} className="flex items-center gap-2"><span className="w-32 font-medium">{e.name}{e.idx != null ? ` #${e.idx + 1}` : ""}</span><TxLink hash={e.tx_hash} /><span className="text-xs text-mute">block {e.block_number}</span></li>)}
          {!c.events.length && <li className="text-mute">Nothing on the blockchain yet.</li>}
        </ul>
      </details>
    </div>
  );
}

function Milestone({ c, m, i, cm, grace, now, isClient, isWorker, act, eid, clientW, refresh, setErr }: any) {
  const reqs = c.requirements.filter((r: any) => r.milestone_idx === i);
  const runs = c.runs.filter((r: any) => r.milestone_idx === i);
  const last = runs.find((r: any) => r.status === "passed" || r.status === "failed");
  const official = runs.filter((r: any) => !r.dry_run && r.status !== "error" && r.source !== "shipment").length;
  const { data: detail } = useApi<any>(last && last.source !== "shipment" ? `/runs/${last.id}` : null);
  const results: Record<string, any> = Object.fromEntries((detail?.report?.results ?? []).map((x: any) => [x.requirement_id, x]));
  const [reason, setReason] = useState("");
  const [dispOpen, setDispOpen] = useState(false);
  const [ship, setShip] = useState({ carrier: "", tracking: "", note: "" });
  const [busy, setBusy] = useState(false);
  const product = m.delivery_type === "product";

  const st = cm ? Number(cm.status) : null; // on-chain truth: 0 funded, 1 passed, 2 disputed
  const closes = cm ? Number(cm.passedAt) + Number(cm.window) : 0;
  const canFinalize = st === 1 && now >= closes;
  const canDispute = isClient && st === 1 && now < closes;
  const canRefund = isClient && st === 0 && grace !== undefined && now >= Number(cm.deadline) + Number(grace);
  const running = runs.some((r: any) => r.status === "running");
  const active = c.status === "active";
  const canDeliver = isWorker && active && m.status === "funded" && !product;
  const canPractice = isWorker && ["open", "active"].includes(c.status) && m.status === "funded" && !product;
  const canShip = isWorker && active && m.status === "funded" && product && !m.shipment;

  async function download(runId: string) {
    try { const r = await api<any>(`/runs/${runId}/download`); window.open(r.url, "_blank", "noopener"); } catch (x: any) { setErr(x.message); }
  }
  async function markShipped(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(undefined);
    try { await api(`/contracts/${c.id}/milestones/${i}/ship`, { body: ship }); refresh(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }
  async function dispute() {
    setErr(undefined);
    try {
      const { reason_hash } = await api(`/contracts/${c.id}/milestones/${i}/dispute`, { body: { reason } });
      await act("Opening dispute", "dispute", [eid, BigInt(i), reason_hash], clientW, undefined, "Dispute opened. An arbitrator will review the evidence.");
      setDispOpen(false);
    } catch (x: any) { setErr(x.message); }
  }

  return (
    <article className="panel overflow-hidden">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <h2 className="min-w-0 flex-1">{i + 1}. {m.title} <span className="chip align-middle">{DELIVERY[m.delivery_type]?.label}</span></h2>
        <span className="text-sm text-mute">Due {date(m.deadline)}</span>
        <span className="font-semibold">{fmtAmt(m.amount)}</span>
        <Badge map={MILESTONE_STATUS} value={m.status} />
      </header>
      <ul className="divide-y divide-line">
        {reqs.map((r: any) => {
          const res = results[r.id];
          return (
            <li key={r.id} className="flex gap-3 px-4 py-2.5">
              <span aria-label={res ? (res.passed ? "passed" : "failed") : "not run"} className={`mt-0.5 w-5 text-center font-bold ${res ? (res.passed ? "text-ok" : "text-bad") : "text-mute"}`}>{res ? (res.passed ? "✓" : "✕") : "–"}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{r.title}</p>
                <p className="text-xs text-mute">{KIND_LABEL[r.kind] ?? r.kind}{r.criteria ? `. ${r.criteria}` : ""}{r.kind === "ai_review" && r.spec?.claim ? `. Must be true: ${r.spec.claim}` : ""}</p>
                {res?.detail && <pre className={`mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded p-2 font-mono text-xs ${res.passed ? "bg-ok-soft text-ok" : "bg-bad-soft text-bad"}`}>{res.detail}</pre>}
              </div>
            </li>
          );
        })}
      </ul>

      {m.shipment && (
        <p className="border-t border-line bg-paper px-4 py-3 text-sm"><b>Shipped</b> with {m.shipment.carrier}{m.shipment.tracking ? ` (tracking ${m.shipment.tracking})` : ""} on {date(m.shipment.shipped_at)}.{m.shipment.note ? ` ${m.shipment.note}` : ""}</p>
      )}

      {runs.filter((r: any) => r.source !== "shipment").length > 0 && (
        <div className="space-y-2 border-t border-line bg-paper px-4 py-3 text-sm">
          {runs.filter((r: any) => r.source !== "shipment").map((r: any, k: number, arr: any[]) => (
            <div key={r.id} className="space-y-1">
              <p className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{r.dry_run ? "Practice run" : `Submission ${arr.filter((x: any, n: number) => !x.dry_run && n >= k).length}`}</span>
                <span className={r.status === "passed" ? "text-ok" : r.status === "failed" ? "text-bad" : "text-mute"}>{r.status === "running" ? "Checking…" : r.status === "error" ? "Could not run" : `${r.status === "passed" ? "Passed" : "Not passed"} ${r.passed}/${r.total}`}</span>
                <span className="chip">{r.source === "zip" ? `zip: ${r.file_name ?? ""}` : r.source === "site" ? "published site" : "GitHub"}</span>
                {r.commit_sha && <span className="chip">{r.commit_sha.slice(0, 7)}</span>}
                {r.file_path && !r.dry_run && (isClient || isWorker) && <button type="button" className="chip link" onClick={() => download(r.id)}>download zip</button>}
                {r.evidence_hash && !r.dry_run && <Link className="chip link" href={`/verify/${r.evidence_hash}`}>evidence {short(r.evidence_hash, 4)}</Link>}
                <TxLink hash={r.attest_tx} />
                <span className="text-xs text-mute">{date(r.created_at)}</span>
              </p>
              {r.ai_summary && <p className="text-xs text-mute">{r.ai_summary}</p>}
              {r.error && <p className="text-xs text-bad">{r.error}</p>}
            </div>
          ))}
        </div>
      )}
      {st === 1 && <p className="border-t border-line bg-ok-soft px-4 py-2 text-sm text-ok">{now < closes ? `Checked and passed. Review window open until ${date(new Date(closes * 1000).toISOString())}. Payment releases automatically afterward.` : "The review window is over. The payment can be released."}</p>}

      {c.disputes.filter((d: any) => d.milestone_idx === i).map((d: any) => (
        <p key={d.id} className="border-t border-line bg-bad-soft px-4 py-2 text-sm text-bad">Dispute ({d.status}): {d.reason}{d.freelancer_bps != null ? ` Resolved: ${d.freelancer_bps / 100}% to the worker.` : ""}</p>
      ))}

      {canDeliver && <Submit cid={c.id} idx={i} deliveryType={m.delivery_type} dry={false} left={Math.max(0, MAX_RUNS - official)} running={running} onDone={refresh} />}
      {canPractice && !canDeliver && <Submit cid={c.id} idx={i} deliveryType={m.delivery_type} dry running={running} onDone={refresh} />}
      {canDeliver && <details className="border-t border-line px-4 py-3"><summary className="cursor-pointer text-sm font-medium">Try a free practice run first</summary><Submit cid={c.id} idx={i} deliveryType={m.delivery_type} dry running={running} onDone={refresh} /></details>}

      {canShip && (
        <form onSubmit={markShipped} className="space-y-3 border-t border-line px-4 py-4">
          <p className="font-semibold">Mark as shipped</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label className="label" htmlFor={`c${i}`}>Courier / how it was sent</label><input id={`c${i}`} className="input" required minLength={2} value={ship.carrier} onChange={(e) => setShip({ ...ship, carrier: e.target.value })} /></div>
            <div><label className="label" htmlFor={`t${i}`}>Tracking number (optional)</label><input id={`t${i}`} className="input" value={ship.tracking} onChange={(e) => setShip({ ...ship, tracking: e.target.value })} /></div>
            <div className="sm:col-span-2"><label className="label" htmlFor={`n${i}`}>Note for the buyer (optional)</label><input id={`n${i}`} className="input" value={ship.note} onChange={(e) => setShip({ ...ship, note: e.target.value })} /></div>
          </div>
          <button className="btn-primary" disabled={busy}>{busy ? "Saving…" : "I shipped it"}</button>
          <p className="text-xs text-mute">The buyer is told right away. The money is released when they press &quot;I received it&quot;, or after the review window.</p>
        </form>
      )}

      {active && (m.status === "funded" || m.status === "passed") && (isClient || canFinalize || canRefund) && (
        <div className="flex flex-wrap gap-2 border-t border-line px-4 py-3">
          {isClient && (product
            ? <button className="btn-primary" onClick={() => act("Releasing payment", "approve", [eid, BigInt(i)], clientW, undefined, "Thank you. The payment was released to the seller.")}>I received it: release the payment</button>
            : <button className="btn-ghost" onClick={() => act("Approving", "approve", [eid, BigInt(i)], clientW)}>Approve and pay now</button>)}
          {canFinalize && <button className="btn-primary" onClick={() => act("Releasing payment", "finalize", [eid, BigInt(i)], null)}>Release payment</button>}
          {canDispute && <button className="btn-danger" onClick={() => setDispOpen(!dispOpen)}>Dispute this result</button>}
          {canRefund && <button className="btn-ghost" onClick={() => act("Reclaiming", "refundExpired", [eid, BigInt(i)], clientW)}>Reclaim unchecked money (deadline passed)</button>}
        </div>
      )}
      {dispOpen && (
        <div className="space-y-2 border-t border-line px-4 py-3">
          <label className="label" htmlFor={`x${i}`}>Why is the result wrong? (kept as evidence, hashed on the blockchain)</label>
          <textarea id={`x${i}`} className="input min-h-24" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button className="btn-danger" disabled={reason.trim().length < 10} onClick={dispute}>Open dispute</button>
        </div>
      )}
    </article>
  );
}
