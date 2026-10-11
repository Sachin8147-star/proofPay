"use client";
import Link from "next/link";
import { ReactNode } from "react";
import { addrUrl, txUrl } from "@/lib/chain";
import { short } from "@/lib/labels";

export const Badge = ({ map, value }: { map: Record<string, [string, string]>; value: string }) => {
  const [text, cls] = map[value] ?? [value, "bg-line"];
  return <span className={`inline-block whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${cls}`}>{text}</span>;
};

export const Empty = ({ title, children }: { title: string; children?: ReactNode }) => (
  <div className="panel p-8 text-center"><p className="font-semibold">{title}</p>{children && <div className="mt-2 text-sm text-mute">{children}</div>}</div>
);

export const Err = ({ children }: { children?: ReactNode }) => (children ? <p role="alert" className="rounded bg-bad-soft px-3 py-2 text-sm text-bad">{children}</p> : null);
export const Loading = () => <p className="py-10 text-center text-sm text-mute">Loading…</p>;

export const TxLink = ({ hash }: { hash?: string | null }) => (hash ? <a className="chip link" href={txUrl(hash)} target="_blank" rel="noreferrer" title={hash}>tx {short(hash, 4)}</a> : null);
export const AddrLink = ({ a }: { a?: string | null }) => (a ? <a className="chip link" href={addrUrl(a)} target="_blank" rel="noreferrer" title={a}>{short(a, 4)}</a> : null);
export const HashChip = ({ h }: { h?: string | null }) => (h ? <span className="chip" title={h}>{short(h, 6)}</span> : null);
export const Stat = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="panel p-4"><p className="text-sm text-mute">{label}</p><p className="mt-1 text-xl font-bold">{value}</p></div>
);
export const NavLink = ({ href, children, active, badge }: { href: string; children: ReactNode; active: boolean; badge?: number }) => (
  <Link href={href} className={`flex items-center justify-between rounded px-3 py-2 text-sm font-medium ${active ? "bg-brand-soft text-brand" : "text-ink hover:bg-paper"}`}>
    {children}{!!badge && <span aria-label={`${badge} unread`} className="rounded-full bg-brand px-2 py-0.5 text-xs font-semibold text-white">{badge > 99 ? "99+" : badge}</span>}
  </Link>
);
