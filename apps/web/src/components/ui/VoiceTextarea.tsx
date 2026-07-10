"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, MicOff } from "lucide-react";

/**
 * Textarea + browser-native SpeechRecognition ("Web Speech API"). Tapping the
 * mic starts continuous recognition; interim results append inline; tapping
 * again stops. If the browser doesn't support the API, the mic is hidden and
 * the textarea behaves normally — no regression.
 *
 * Trades workers often type slowly on phones; voice input is the biggest
 * profile-completion unlock we have.
 */
type Props = React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  value: string;
  onChange: (v: string) => void;
};

// Minimal typing for the Web Speech API (not in lib.dom for all browsers)
interface SR extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((ev: { results: ArrayLike<ArrayLike<{ transcript: string; isFinal: boolean }>> & { length: number }; resultIndex: number }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  onend: (() => void) | null;
}

function getSR(): SR | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { webkitSpeechRecognition?: new () => SR; SpeechRecognition?: new () => SR };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

export function VoiceTextarea({ value, onChange, className = "", ...rest }: Props) {
  const [listening, setListening] = useState(false);
  const [supported, setSupported] = useState(false);
  const srRef = useRef<SR | null>(null);
  const baseRef = useRef<string>(value);
  baseRef.current = value;

  useEffect(() => {
    const sr = getSR();
    if (!sr) return;
    setSupported(true);
    sr.lang = navigator.language || "en-US";
    sr.continuous = true;
    sr.interimResults = true;
    sr.onresult = (ev) => {
      let out = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i][0];
        if (r) out += r.transcript;
      }
      const base = baseRef.current.replace(/\s*$/, "");
      const next = (base ? base + " " : "") + out.trim();
      onChange(next);
    };
    sr.onend = () => setListening(false);
    sr.onerror = () => setListening(false);
    srRef.current = sr;
    return () => { try { sr.stop(); } catch { /* noop */ } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggle() {
    const sr = srRef.current;
    if (!sr) return;
    if (listening) { try { sr.stop(); } catch { /* noop */ } setListening(false); }
    else { try { sr.start(); setListening(true); } catch { /* noop */ } }
  }

  return (
    <div className="relative">
      <textarea
        {...rest}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`input-cohere pr-11 ${className}`}
      />
      {supported && (
        <button
          type="button"
          onClick={toggle}
          aria-label={listening ? "Stop dictation" : "Dictate this field"}
          title={listening ? "Stop dictation" : "Tap to dictate"}
          className={`absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full border transition-colors ${
            listening
              ? "border-studio-maroon bg-cohere-coral text-white animate-pulse"
              : "border-hairline bg-white text-slate-muted hover:border-cohere-ink hover:text-cohere-ink"
          }`}
        >
          {listening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
        </button>
      )}
    </div>
  );
}
