"use client";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Err } from "./ui";
import { SPEECH_LANGS, useSpeech } from "./useSpeech";

type M = { role: "user" | "assistant"; content: string };
const STARTERS = ["Mera paisa locked kyun hai?", "How do I get paid?", "How do I cancel a contract?", "What is my username for?"];

export default function HelpChat() {
  const path = usePathname();
  const [msgs, setMsgs] = useState<M[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();
  const [lang, setLang] = useState("en-IN");
  const speech = useSpeech((t) => setText((v) => (v ? v + " " : "") + t), lang);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }); }, [msgs, busy]);

  async function send(content: string) {
    const body = content.trim();
    if (!body || busy) return;
    const next: M[] = [...msgs, { role: "user", content: body }];
    setMsgs(next); setText(""); setErr(undefined); setBusy(true);
    try {
      const r = await api("/assistant/chat", { body: { messages: next.slice(-20), page: path } });
      setMsgs([...next, { role: "assistant", content: r.reply }]);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  return (
    <section className="panel" aria-label="Help chat">
      <div ref={box} className="max-h-[28rem] min-h-48 space-y-3 overflow-y-auto px-4 py-3" aria-live="polite">
        {msgs.length === 0 && (
          <div className="space-y-2 text-sm"><p className="text-mute">Ask anything about ProofPay in English, Hindi or Hinglish. Never share your password or wallet seed phrase here.</p>
            <div className="flex flex-wrap gap-2">{STARTERS.map((s) => <button key={s} className="btn-ghost !py-1 text-xs" onClick={() => send(s)}>{s}</button>)}</div></div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <p className={`max-w-[85%] whitespace-pre-wrap break-words rounded px-3 py-2 text-sm ${m.role === "user" ? "bg-brand-soft" : "border border-line bg-white"}`}>{m.content}</p>
          </div>
        ))}
        {busy && <p className="text-sm text-mute">Thinking…</p>}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="space-y-2 border-t border-line p-3">
        <label className="sr-only" htmlFor="help-input">Your question</label>
        <textarea id="help-input" className="input min-h-16" maxLength={2000} placeholder="Type or speak your problem…" value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
        <Err>{err ?? speech.error}</Err>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-primary" disabled={busy || !text.trim()}>Ask</button>
          {speech.supported && <button type="button" className="btn-ghost" onClick={speech.listening ? speech.stop : speech.start} aria-pressed={speech.listening}>{speech.listening ? "Stop listening" : "Speak"}</button>}
          <select aria-label="Speaking language" className="input !w-auto text-xs" value={lang} onChange={(e) => setLang(e.target.value)}>{SPEECH_LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </div>
      </form>
    </section>
  );
}
