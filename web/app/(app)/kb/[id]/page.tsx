"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useStore } from "@/lib/store";
import { ago } from "@/lib/format";
import { tf, useT } from "@/lib/i18n";
import { KB_PRICING_ID } from "@/lib/constants";
import TopBar from "@/components/TopBar";
import { Upload } from "@/components/Icons";
import type { Doc } from "@/lib/types";

export default function KbDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { t } = useT();
  const kbs = useStore((s) => s.kbs);
  const kb = kbs.find((k) => k.id === id);
  const isPricingKb = id === KB_PRICING_ID;

  const STATUS_LABEL: Record<string, string> = {
    pending: t.kb.statusPending,
    processing: t.kb.statusProcessing,
    done: t.kb.statusDone,
    error: t.kb.statusError,
  };

  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [region, setRegion] = useState("HN");
  const [pricePeriod, setPricePeriod] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    const res = await apiFetch(`/api/v1/documents/${id}?limit=200`);
    if (res.ok) {
      const data = await res.json();
      setDocs(data.documents ?? []);
    }
    setLoading(false);
  }, [id]);

  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [load]);

  // poll while any document is still ingesting
  useEffect(() => {
    const active = docs.some((d) => d.status === "pending" || d.status === "processing");
    if (active) {
      pollRef.current = setTimeout(load, 2500);
      return () => {
        if (pollRef.current) clearTimeout(pollRef.current);
      };
    }
  }, [docs, load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", file);
        const path = isPricingKb
          ? `/api/v1/documents/upload-price/${id}?region=${encodeURIComponent(region)}&price_period=${encodeURIComponent(pricePeriod)}`
          : `/api/v1/documents/upload/${id}`;
        await apiFetch(path, { method: "POST", body: fd });
      }
      await load();
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function remove(docId: string) {
    if (!confirm(t.kb.confirmDeleteDoc)) return;
    await apiFetch(`/api/v1/documents/${docId}`, { method: "DELETE" });
    await load();
  }

  return (
    <>
      <TopBar title={kb?.name ?? t.kb.title} />
      <div className="page">
        <div className="page-inner">
          <div className="page-head">
            <div>
              <h2>{kb?.name ?? t.nav.kb}</h2>
              <p>{kb?.is_system ? t.kb.systemDesc : t.kb.uploadDesc}</p>
            </div>
            <button className="btn btn-ghost" onClick={() => router.push("/kb")}>{t.kb.backAll}</button>
          </div>

          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt"
            style={{ display: "none" }}
            onChange={(e) => upload(e.target.files)}
          />

          {isPricingKb && (
            <div className="settings-group" style={{ marginBottom: 16 }}>
              <p className="sub" style={{ marginBottom: 14 }}>{t.kb.priceUploadNote}</p>
              <div className="fb" style={{ padding: 0, marginBottom: 0 }}>
                <div className="field">
                  <label>{t.kb.region} <span className="req">*</span></label>
                  <select className="control select" value={region} onChange={(e) => setRegion(e.target.value)}>
                    <option value="HN">{t.costForm.regionHN}</option>
                    <option value="DN">{t.costForm.regionDN}</option>
                    <option value="HCM">{t.costForm.regionHCM}</option>
                  </select>
                </div>
                <div className="field">
                  <label>{t.kb.pricePeriod}</label>
                  <input
                    className="control"
                    value={pricePeriod}
                    onChange={(e) => setPricePeriod(e.target.value)}
                    placeholder={t.kb.pricePeriodPh}
                  />
                </div>
              </div>
            </div>
          )}

          <div className="dropzone" onClick={() => fileRef.current?.click()}>
            <Upload width={20} height={20} style={{ display: "block", margin: "0 auto 8px" }} />
            {uploading ? t.kb.uploading : isPricingKb ? t.kb.uploadPriceCta : t.kb.uploadCta}
          </div>

          {loading ? (
            <div className="center-load" style={{ padding: 40 }}>
              <span className="spinner" />
            </div>
          ) : docs.length === 0 ? (
            <div className="empty">{t.kb.emptyDocs}</div>
          ) : (
            <div className="doc-list">
              {docs.map((d) => (
                <div className="doc-row" key={d.id}>
                  <span className={`d ${d.status}`} />
                  <span className="fn">{d.filename}</span>
                  <span className="status" style={{ fontSize: "var(--fs-xs)" }}>
                    {STATUS_LABEL[d.status] ?? d.status}
                  </span>
                  <span className="chunks">{tf(t.kb.chunkCount, { n: d.chunk_count })}</span>
                  <span className="chunks">{ago(d.created_at)}</span>
                  <button className="icon-x" onClick={() => remove(d.id)} aria-label={t.common.delete}>
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
