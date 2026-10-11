"use client";
import { useState } from "react";

/** Shows the person's username with a copy button: this is the ID they hand to the other party. */
export default function ShareId({ handle }: { handle?: string | null }) {
  const [copied, setCopied] = useState(false);
  if (!handle) return null;
  async function copy() {
    try { await navigator.clipboard.writeText(handle!); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked: the text is still selectable */ }
  }
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <div className="min-w-0"><p className="text-xs text-mute">Your ID (share it)</p><p className="truncate font-semibold">@{handle}</p></div>
      <button className="btn-ghost !px-2 !py-1 text-xs" onClick={copy} aria-label="Copy my username">{copied ? "Copied" : "Copy"}</button>
    </div>
  );
}
