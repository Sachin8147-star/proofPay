"use client";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { date } from "@/lib/labels";
import Chat from "./Chat";

/** The poster's inbox for an open job: one private conversation per interested worker. */
export default function Threads({ id }: { id: string }) {
  const { data } = useApi<any[]>(`/contracts/${id}/threads`, 6000);
  const [open, setOpen] = useState<string | null>(null);
  if (!data) return null;
  if (!data.length) return <section className="panel p-4"><h2>Interested workers</h2><p className="mt-1 text-sm text-mute">Nobody has written to you about this job yet. When a worker sends a question, the conversation appears here.</p></section>;
  const cur = data.find((t) => t.user_id === open);
  return (
    <section className="space-y-3">
      <div className="panel"><h2 className="border-b border-line px-4 py-3">Interested workers ({data.length})</h2>
        <ul className="divide-y divide-line">{data.map((t) => (
          <li key={t.user_id}><button className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-paper ${open === t.user_id ? "bg-brand-soft" : ""}`} onClick={() => setOpen(t.user_id)}>
            <span className="min-w-0"><span className="font-medium">{t.name}</span><span className="block truncate text-xs text-mute">{t.last_body} · {date(t.last_at)}</span></span>
            {t.unread > 0 && <span className="rounded-full bg-brand px-2 py-0.5 text-xs font-semibold text-white">{t.unread}</span>}
          </button></li>))}
        </ul>
      </div>
      {cur && <Chat key={cur.user_id} id={id} withUser={cur.user_id} title={`Chat with ${cur.name}`} />}
    </section>
  );
}
