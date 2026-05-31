"use client";

/**
 * UploadForm — drag-and-drop / click-to-upload for document intake.
 *
 * POSTs to POST /api/v1/documents (multipart/form-data).
 * On success: router.refresh() so the Server Component list re-fetches.
 */

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";

export function UploadForm() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<string | null>(null);
  const router = useRouter();

  async function upload(file: File) {
    setError(null);
    setLastUploaded(null);
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${base}/api/v1/documents`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (res.ok) {
      const data = (await res.json()) as { case_id?: string };
      setLastUploaded(file.name);
      router.refresh();
      return data.case_id;
    } else {
      const body = await res.json().catch(() => null);
      setError(body?.detail ?? `Upload failed (${res.status})`);
    }
  }

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    startTransition(async () => {
      for (const file of Array.from(files)) {
        await upload(file);
      }
    });
  }

  return (
    <div className="space-y-2">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload document"
        aria-busy={pending}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" || e.key === " " ? inputRef.current?.click() : undefined}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={`flex cursor-pointer items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-foreground ${
          dragging
            ? "border-primary bg-primary/10 text-primary"
            : "border-border bg-surface text-muted hover:border-primary hover:text-foreground"
        } ${pending ? "cursor-not-allowed opacity-50" : ""}`}
      >
        <span aria-hidden="true">{pending ? "⟳" : "↑"}</span>
        {pending ? "Uploading…" : "Upload document"}
      </div>
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        accept=".txt,.pdf,.json,.xml,.png,.jpg,.jpeg,.csv"
        multiple
        onChange={(e) => handleFiles(e.target.files)}
        disabled={pending}
      />
      {lastUploaded && !pending && (
        <p className="text-xs text-success">✓ {lastUploaded} uploaded — pipeline processing</p>
      )}
      {error && (
        <p role="alert" className="text-xs text-danger">{error}</p>
      )}
    </div>
  );
}
