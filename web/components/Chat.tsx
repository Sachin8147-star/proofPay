"use client";
import { useEffect, useRef, useState } from "react";
import { api, useApi } from "@/lib/api";
import { date } from "@/lib/labels";
import { Err } from "./ui";

type Msg = { id: string; mine: boolean; name: string; body: string; created_at: string };

export default function Chat({ id, withUser, title = "Messages" }: { id: string; withUser?: string; title?: string }) {
  const q = withUser ? `?with=${withUser}` : "";
  const { data, mutate } = useApi<Msg[]>(`/contracts/${id}/messages${q}`, 4000);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const seen = useRef(-1);

  useEffect(() => {
    if (!data) return;
    box.current?.scrollTo({ top: box.current.scrollHeight });
    const theirs = data.filter((m) => !m.mine).length;
    if (theirs !== seen.current) { // new messages from the other person are on screen: mark them read
      if (theirs > 0) api(`/contracts/${id}/read`, { method: "POST" }).catch(() => {});
      seen.current = theirs;
    }
  }, [data, id]);

  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    const body = text.trim();
    if (!body || busy) return;
    setBusy(true); setErr(undefined);
    try { await api(`/contracts/${id}/messages`, { body: { body, to: withUser } }); setText(""); await mutate(); }
    catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }

  return (
    <section className="panel" aria-label={title}>
      <h2 className="border-b border-line px-4 py-3">{title}</h2>
      <div ref={box} className="max-h-96 min-h-32 space-y-3 overflow-y-auto px-4 py-3" aria-live="polite">
        {!data ? <p className="text-sm text-mute">Loading…</p> : data.length === 0 ? <p className="text-sm text-mute">No messages yet. Ask a question or share a link here.</p> :
          data.map((m) => (
            <div key={m.id} className={`flex flex-col ${m.mine ? "items-end" : "items-start"}`}>
              <p className="text-xs text-mute">{m.mine ? "You" : m.name} · {date(m.created_at)}</p>
              <p className={`mt-0.5 max-w-[85%] whitespace-pre-wrap break-words rounded px-3 py-2 text-sm ${m.mine ? "bg-brand-soft" : "border border-line bg-white"}`}>{m.body}</p>
            </div>
          ))}
      </div>
      <form onSubmit={send} className="space-y-2 border-t border-line p-3">
        <label className="sr-only" htmlFor="chat-input">Write a message</label>
        <textarea id="chat-input" className="input min-h-16" maxLength={2000} placeholder="Write a message. Enter sends, Shift+Enter adds a line." value={text}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) send(); if (e.key === "Enter" && !e.shiftKey) e.preventDefault(); }} />
        <Err>{err}</Err>
        <button className="btn-primary" disabled={busy || !text.trim()}>{busy ? "Sending…" : "Send"}</button>
      </form>
    </section>
  );
}
