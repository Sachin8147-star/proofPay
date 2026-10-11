"use client";
import { useEffect, useRef, useState } from "react";

export const SPEECH_LANGS = [["en-IN", "English"], ["hi-IN", "हिन्दी (Hindi)"], ["en-US", "English (US)"]] as const;

/** Speech-to-text through the browser's built-in recognizer. `supported` is false where the browser has none (e.g. Firefox). */
export function useSpeech(onText: (text: string) => void, lang: string) {
  const [listening, setListening] = useState(false);
  const [supported, setSupported] = useState(false);
  const [error, setError] = useState<string>();
  const rec = useRef<any>(null);
  const cb = useRef(onText);
  cb.current = onText;

  useEffect(() => { setSupported(!!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)); }, []);
  useEffect(() => () => rec.current?.stop?.(), []);

  function start() {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return setError("Your browser can't listen. Type instead, or use Chrome or Edge.");
    setError(undefined);
    const r = new SR();
    r.lang = lang; r.interimResults = false; r.continuous = true;
    r.onresult = (e: any) => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) cb.current(e.results[i][0].transcript.trim()); };
    r.onerror = (e: any) => { setError(e.error === "not-allowed" ? "Microphone is blocked. Allow it in the address bar and try again." : "Could not hear you. Try again."); setListening(false); };
    r.onend = () => setListening(false);
    rec.current = r; r.start(); setListening(true);
  }
  const stop = () => { rec.current?.stop?.(); setListening(false); };
  return { listening, supported, error, start, stop };
}
