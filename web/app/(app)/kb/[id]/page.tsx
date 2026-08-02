"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, apiFetch } from "@/lib/api";
import { useStore } from "@/lib/store";
import { ago } from "@/lib/format";
import { tf, useT } from "@/lib/i18n";
import TopBar from "@/components/TopBar";
import { Upload } from "@/components/Icons";
import type { Doc } from "@/lib/types";

export default function KbDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { t } = useT();
  const kbs = useStore((s) => s.kbs);
  const loadKbs = useStore((s) => s.loadKbs);
  const kb = kbs.find((k) => k.id === id);
  // Which pipeline an upload runs is the KB's own setting now, not a
  // hard-coded id — see knowledge_bases.price_extraction (migration 0008).
  const priceMode = !!kb?.price_extraction;

  const STATUS_LABEL: Record<string, string> = {
    pending: t.kb.statusPending,
    processing: t.kb.statusProcessing,
    done: t.kb.statusDone,
    error: t.kb.statusError,
  };

  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Starts empty on purpose: material_prices.region is what every price
  // lookup filters on, so the region must be a deliberate choice, not a
  // default the user never noticed. Upload stays blocked until it is set.
  const [region, setRegion] = useState("");
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

  async function togglePriceExtraction(enabled: boolean) {
    setToggling(true);
    setErr(null);
    try {
      await api.patch(`/api/v1/kb/${id}`, { price_extraction: enabled });
      await loadKbs();
    } catch {
      setErr(t.kb.toggleFailed);
    } finally {
      setToggling(false);
    }
  }

  const uploadBlocked = priceMode && !region;

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    if (uploadBlocked) {
      setErr(t.kb.regionRequired);
      return;
    }
    setUploading(true);
    setErr(null);
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", file);
        // Always the same endpoint — the backend routes to the price pipeline
        // when the KB has the flag on. Region only matters in that case.
        const qs = priceMode
          ? `?region=${encodeURIComponent(region)}&price_period=${encodeURIComponent(pricePeriod)}`
          : "";
        const res = await apiFetch(`/api/v1/documents/upload/${id}${qs}`, {
          method: "POST",
          body: fd,
        });
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          setErr(body?.detail ?? t.kb.createFailed);
          break;
        }
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

          {err && <div className="auth-err" style={{ marginBottom: 16 }}>{err}</div>}

          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt"
            style={{ display: "none" }}
            onChange={(e) => upload(e.target.files)}
          />

          <div className="settings-group" style={{ marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 9, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={priceMode}
                disabled={toggling}
                onChange={(e) => togglePriceExtraction(e.target.checked)}
                style={{ width: 16, height: 16, accentColor: "var(--brand)", cursor: "pointer" }}
              />
              <strong style={{ fontSize: "var(--fs-sm)" }}>{t.kb.priceExtraction}</strong>
              {toggling && <span className="spinner" style={{ width: 13, height: 13 }} />}
            </label>
            <p className="sub" style={{ margin: "8px 0 0 25px" }}>{t.kb.priceExtractionHint}</p>

            {priceMode && (
              <p className="sub" style={{ margin: "14px 0 0 25px" }}>{t.kb.priceUploadNote}</p>
            )}

            {priceMode && (
              <>
                <div className="fb" style={{ padding: 0, margin: "14px 0 0" }}>
                  <div className="field">
                    <label>{t.kb.region} <span className="req">*</span></label>
                    <select
                      className="control select"
                      value={region}
                      onChange={(e) => setRegion(e.target.value)}
                      aria-invalid={!region}
                    >
                      <option value="">{t.kb.regionPlaceholder}</option>
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
              </>
            )}
          </div>

          <div
            className={`dropzone${uploadBlocked ? " disabled" : ""}`}
            onClick={() => !uploadBlocked && fileRef.current?.click()}
            aria-disabled={uploadBlocked}
          >
            <Upload width={20} height={20} style={{ display: "block", margin: "0 auto 8px" }} />
            {uploadBlocked
              ? t.kb.regionRequired
              : uploading
                ? t.kb.uploading
                : priceMode
                  ? t.kb.uploadPriceCta
                  : t.kb.uploadCta}
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
                  {/* null = never went through the price pipeline, so no badge.
                      0 = it did and found nothing readable — worth showing. */}
                  {d.price_row_count !== null && d.price_row_count !== undefined && (
                    <span
                      className={`prices${d.price_row_count === 0 ? " none" : ""}`}
                      title={d.price_row_count === 0 ? t.kb.priceRowNoneHint : undefined}
                    >
                      {tf(t.kb.priceRowCount, { n: d.price_row_count })}
                    </span>
                  )}
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
