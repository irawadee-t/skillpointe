"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, CheckCircle2, FileText, FolderOpen, Loader2, ShieldCheck } from "lucide-react";

import { API_BASE } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type Phase = "capture" | "preparing" | "sending" | "done" | "invalid" | "error";

const MAX_BYTES = 10 * 1024 * 1024; // server limit
const MAX_EDGE = 2000; // px — longest edge after client-side downscale
const JPEG_QUALITY = 0.85;

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];

function isPdf(f: File): boolean {
  return f.type === "application/pdf" || /\.pdf$/i.test(f.name);
}

function isImage(f: File): boolean {
  return IMAGE_TYPES.includes(f.type.toLowerCase()) || f.type.startsWith("image/");
}

/** Friendly pre-flight check — runs on pick, before any bytes are spent. */
function preflight(f: File): string | null {
  if (!isPdf(f) && !isImage(f)) {
    return "That file type isn't supported. Take a photo, or pick a JPG, PNG, WebP, HEIC, or PDF.";
  }
  if (isPdf(f) && f.size > MAX_BYTES) {
    return "That PDF is too large. The limit is 10 MB. Try a photo of the document instead.";
  }
  // Oversized images usually shrink well under the limit after downscaling;
  // only reject the truly absurd before decoding.
  if (isImage(f) && f.size > 80 * 1024 * 1024) {
    return "That image is too large to process. Try taking a fresh photo.";
  }
  return null;
}

/**
 * Downscale an image to ~2000px longest edge / 85% JPEG before upload.
 * PDFs are passed through untouched. Any decode failure (e.g. HEIC in a
 * browser that can't render it) falls back to the original file — the server
 * accepts those types anyway.
 */
async function prepareForUpload(f: File): Promise<File> {
  if (!isImage(f)) return f;
  try {
    const bitmap = await decodeImage(f);
    const { width, height } = bitmap;
    const scale = Math.min(1, MAX_EDGE / Math.max(width, height));
    if (scale >= 1 && f.size <= MAX_BYTES && f.type === "image/jpeg") {
      close(bitmap);
      return f; // already small enough — don't recompress for nothing
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) { close(bitmap); return f; }
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    close(bitmap);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
    );
    if (!blob) return f;
    const name = f.name.replace(/\.\w+$/, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg" });
  } catch {
    return f;
  }
}

type Decoded = ImageBitmap | HTMLImageElement;

function close(d: Decoded) {
  if ("close" in d && typeof d.close === "function") d.close();
}

async function decodeImage(f: File): Promise<Decoded> {
  if ("createImageBitmap" in window) {
    try {
      return await createImageBitmap(f);
    } catch {
      /* fall through to <img> decode */
    }
  }
  const url = URL.createObjectURL(f);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Upload with real progress (XHR — fetch has no upload progress events). */
function uploadWithProgress(
  url: string,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => resolve({ status: xhr.status, body: xhr.responseText });
    xhr.onerror = () => reject(new Error("network"));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

/**
 * Mobile-first, unauthenticated capture page. The single-use token in the URL
 * (minted on the desktop, delivered by QR code) is the only credential.
 */
export function VerifyDocClient({ token }: { token: string }) {
  const cameraRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("capture");
  const [detail, setDetail] = useState<string>("");
  const [pickError, setPickError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function pick(f: File | undefined | null) {
    if (!f) return;
    const problem = preflight(f);
    if (problem) {
      setPickError(problem);
      return;
    }
    setPickError(null);
    setFile(f);
    setPhase("capture");
    setDetail("");
    if (preview) URL.revokeObjectURL(preview);
    setPreview(isImage(f) ? URL.createObjectURL(f) : null);
  }

  async function submit() {
    if (!file || phase === "sending" || phase === "preparing") return;
    setPhase("preparing");
    setProgress(0);
    try {
      const prepared = await prepareForUpload(file);
      if (prepared.size > MAX_BYTES) {
        setDetail("That file is still over the 10 MB limit after compressing. Try a fresh photo.");
        setPhase("error");
        return;
      }
      setPhase("sending");
      const res = await uploadWithProgress(
        `${API_BASE}/credential-uploads/${token}`,
        prepared,
        setProgress,
      );
      if (res.status === 404) {
        setPhase("invalid");
        return;
      }
      if (res.status < 200 || res.status >= 300) {
        let body: { detail?: string } | null = null;
        try { body = JSON.parse(res.body) as { detail?: string }; } catch { /* raw */ }
        setDetail(
          res.status === 413
            ? "That photo is too large. The limit is 10 MB."
            : res.status === 415
              ? "That file type isn't supported. Take a photo, or pick a JPG, PNG, or PDF."
              : body?.detail || "Something went wrong. Try again.",
        );
        setPhase("error");
        return;
      }
      let data: { detail?: string } = {};
      try { data = JSON.parse(res.body) as { detail?: string }; } catch { /* empty */ }
      setDetail(data.detail ?? "");
      setPhase("done");
    } catch {
      setDetail("Could not reach the server. Check your connection and try again.");
      setPhase("error");
    }
  }

  const busy = phase === "sending" || phase === "preparing";

  return (
    <main className="flex min-h-dvh flex-col items-center bg-stone px-5 py-8">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 text-cohere-ink">
          <ShieldCheck className="h-5 w-5 text-cohere-green" strokeWidth={1.75} />
          <span className="font-display text-feature">SKILLED verification</span>
        </div>

        {phase === "done" ? (
          <div className="mt-6 rounded-[10px] border border-hairline bg-white p-6 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-wash-green">
              <CheckCircle2 className="h-8 w-8 text-cohere-green" strokeWidth={1.75} />
            </div>
            <h1 className="mt-4 font-display text-feature text-cohere-ink">Done</h1>
            <p className="mt-2 text-body text-slate">
              You can close this and go back to your computer.
            </p>
            {detail && <p className="mt-2 text-caption text-slate-muted">{detail}</p>}
          </div>
        ) : phase === "invalid" ? (
          <div className="mt-6 rounded-[10px] border border-hairline bg-white p-6 text-center">
            <h1 className="font-display text-feature text-cohere-ink">This link has expired</h1>
            <p className="mt-2 text-body text-slate">
              Upload links are single-use and last 15 minutes. Go back to your computer and
              generate a new QR code from the credentials page.
            </p>
          </div>
        ) : (
          <div className="mt-6 rounded-[10px] border border-hairline bg-white p-5">
            <h1 className="font-display text-feature text-cohere-ink">
              Add a photo or file of your certificate or license
            </h1>
            <p className="mt-1.5 text-caption text-slate">
              Lay the document flat in good light and make sure the issuer name and your name are
              readable. A photo from your gallery or a PDF works too.
            </p>

            {/* Preview frame — tap to retake with the camera */}
            {(preview || (file && isPdf(file))) && (
              <button
                type="button"
                onClick={() => cameraRef.current?.click()}
                disabled={busy}
                className="mt-4 flex w-full flex-col items-center gap-2 rounded-[10px] border border-dashed border-hairline px-4 py-4"
              >
                {preview ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={preview}
                    alt="Preview of your document photo"
                    className="max-h-56 w-auto rounded-[6px]"
                  />
                ) : (
                  <span className="flex items-center gap-2 text-body text-cohere-ink">
                    <FileText className="h-5 w-5 text-cohere-green" strokeWidth={1.5} /> {file?.name}
                  </span>
                )}
              </button>
            )}
            {file && (
              <p className="mt-2 text-center text-micro text-slate-muted">
                {file.name}. Tap the frame to retake.
              </p>
            )}

            {/* Two honest affordances: live camera capture, or gallery/files (PDF ok). */}
            <div className="mt-4 grid gap-2">
              <button
                type="button"
                onClick={() => cameraRef.current?.click()}
                disabled={busy}
                className={cn(
                  "flex w-full items-center justify-center gap-2 rounded-[10px] border px-4 py-3.5 text-body font-medium transition-colors",
                  file ? "border-hairline text-cohere-ink" : "border-cohere-green/40 bg-wash-green/40 text-cohere-ink",
                )}
              >
                <Camera className="h-5 w-5 text-cohere-green" strokeWidth={1.5} />
                {file ? "Retake photo" : "Take photo"}
              </button>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={busy}
                className="flex w-full items-center justify-center gap-2 rounded-[10px] border border-hairline px-4 py-3.5 text-body font-medium text-cohere-ink transition-colors"
              >
                <FolderOpen className="h-5 w-5 text-slate-muted" strokeWidth={1.5} />
                Choose a photo or PDF
              </button>
            </div>

            {/* Camera: images only, rear camera. */}
            <input
              ref={cameraRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }}
            />
            {/* Gallery / files: images AND PDFs, no capture — matches the copy. */}
            <input
              ref={fileRef}
              type="file"
              accept="image/*,.pdf,application/pdf"
              className="hidden"
              onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }}
            />

            {pickError && (
              <p className="mt-3 rounded-[6px] border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
                {pickError}
              </p>
            )}

            <button
              onClick={submit}
              disabled={!file || busy}
              className="btn-primary mt-4 w-full justify-center"
            >
              {phase === "preparing" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Preparing…
                </>
              ) : phase === "sending" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Sending… {Math.round(progress * 100)}%
                </>
              ) : (
                "Submit"
              )}
            </button>

            {/* Thin linear upload progress (contract: no rings/donuts). */}
            {phase === "sending" && (
              <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-stone">
                <div
                  className="h-full rounded-full bg-cohere-green transition-[width] duration-200"
                  style={{ width: `${Math.max(4, Math.round(progress * 100))}%` }}
                />
              </div>
            )}

            {phase === "error" && (
              <p className="mt-3 rounded-[6px] border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
                {detail}
              </p>
            )}
          </div>
        )}

        <p className="mt-4 text-center text-micro text-slate-muted">
          This link is single-use and expires after 15 minutes.
        </p>
      </div>
    </main>
  );
}
