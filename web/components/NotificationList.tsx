"use client";
import { useRouter } from "next/navigation";
import { api, useApi } from "@/lib/api";
import { date } from "@/lib/labels";
import { Empty, Loading } from "./ui";

type N = { id: string; kind: string; title: string; body: string; link: string | null; read_at: string | null; created_at: string };

export default function NotificationList() {
  const router = useRouter();
  const { data, error, mutate } = useApi<{ items: N[]; unread: number }>("/notifications", 10000);
  if (error) return <p className="text-bad">{error.message}</p>;
  if (!data) return <Loading />;
  const open = async (n: N) => {
    if (!n.read_at) { await api("/notifications/read", { body: { ids: [n.id] } }).catch(() => {}); mutate(); }
    if (n.link) router.push(n.link);
  };
  const readAll = async () => { await api("/notifications/read", { body: {} }); mutate(); };
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1>Notifications</h1>{data.unread > 0 && <button className="btn-ghost" onClick={readAll}>Mark all as read</button>}</div>
      {data.items.length === 0 ? <Empty title="Nothing yet">You&apos;ll see updates here when a contract changes, tests finish, or someone writes to you.</Empty> : (
        <ul className="panel divide-y divide-line">
          {data.items.map((n) => (
            <li key={n.id}>
              <button className="flex w-full gap-3 px-4 py-3 text-left hover:bg-paper" onClick={() => open(n)}>
                <span aria-label={n.read_at ? "read" : "unread"} className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-brand"}`} />
                <span className="min-w-0 flex-1"><span className={`block text-sm ${n.read_at ? "" : "font-semibold"}`}>{n.title}</span>{n.body && <span className="block truncate text-sm text-mute">{n.body}</span>}</span>
                <span className="shrink-0 text-xs text-mute">{date(n.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
