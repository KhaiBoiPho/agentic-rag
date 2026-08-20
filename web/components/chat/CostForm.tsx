"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import type { FormField, PendingForm } from "@/lib/types";
import { Check, Sheet } from "../Icons";

export default function CostForm({
  form,
  submittedData,
  disabled,
  onSubmit,
}: {
  form: PendingForm;
  submittedData?: Record<string, unknown>;
  disabled?: boolean;
  onSubmit: (formId: string, data: Record<string, unknown>) => void;
}) {
  const { t } = useT();

  // Fallback schema for the construction_cost form when the backend doesn't
  // send an explicit field list (it may only send form_id + prefill).
  const DEFAULT_FIELDS: FormField[] = [
    {
      name: "foundation_area_m2",
      label: t.costForm.foundationArea,
      type: "number",
      required: true,
    },
    {
      name: "foundation_type",
      label: t.costForm.foundationType,
      type: "select",
      required: true,
      default: "mong_bang",
      options: [
        { value: "mong_don", label: t.costForm.foundationDon },
        { value: "mong_coc", label: t.costForm.foundationCoc },
        { value: "mong_bang", label: t.costForm.foundationBang },
        { value: "mong_be", label: t.costForm.foundationBe },
      ],
    },
    { name: "area_per_floor_m2", label: t.costForm.area, type: "number", required: true },
    { name: "num_floors", label: t.costForm.floors, type: "number", required: true, default: 1 },
    { name: "roof_area_m2", label: t.costForm.roofArea, type: "number", required: true },
    {
      name: "region",
      label: t.costForm.region,
      type: "select",
      required: true,
      options: [
        { value: "HN", label: t.costForm.regionHN },
        { value: "DN", label: t.costForm.regionDN },
        { value: "HCM", label: t.costForm.regionHCM },
      ],
    },
    { name: "target_budget_vnd", label: t.costForm.budget, type: "number", required: false },
  ];

  const fields = form.fields?.length ? form.fields : DEFAULT_FIELDS;
  const prefill = form.prefill ?? {};

  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of fields) {
      const v = prefill[f.name] ?? f.default ?? (f.type === "select" ? f.options?.[0]?.value : "");
      init[f.name] = v === undefined || v === null ? "" : String(v);
    }
    return init;
  });

  function set(name: string, v: string) {
    setValues((s) => ({ ...s, [name]: v }));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const data: Record<string, unknown> = {};
    for (const f of fields) {
      const raw = values[f.name];
      data[f.name] = f.type === "number" ? Number(raw) : raw;
    }
    onSubmit(form.form_id, data);
  }

  // Once submitted, the form locks in place showing what was sent — instead
  // of vanishing (which left an empty husk of a message bubble behind) or
  // staying editable (which allowed accidental re-submission).
  const submitted = !!submittedData;

  function displayValue(f: FormField): string {
    const raw = submittedData?.[f.name];
    // an untouched optional numeric field round-trips as 0, not empty
    const empty = raw === undefined || raw === null || raw === "" || (!f.required && raw === 0);
    if (empty) return "—";
    if (f.type === "select") {
      return f.options?.find((o) => o.value === String(raw))?.label ?? String(raw);
    }
    return String(raw);
  }

  return (
    <form className={`form-card${submitted ? " submitted" : ""}`} onSubmit={submit}>
      <div className="fh">
        <span className="tg">Form</span>
        <h4>{form.title || t.costForm.title}</h4>
        <span className="sub">{form.form_id}</span>
      </div>
      <div className="fb">
        {fields.map((f) => (
          <div className="field" key={f.name}>
            <label>
              {f.label} {f.required && !submitted && <span className="req">*</span>}
            </label>
            {submitted ? (
              <div className="control" aria-readonly="true">
                {displayValue(f)}
              </div>
            ) : f.type === "select" ? (
              <select
                className="control"
                value={values[f.name]}
                required={f.required}
                disabled={disabled}
                onChange={(e) => set(f.name, e.target.value)}
              >
                {f.options?.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className="control"
                type={f.type === "number" ? "number" : "text"}
                value={values[f.name]}
                required={f.required}
                disabled={disabled}
                min={f.type === "number" ? 0 : undefined}
                onChange={(e) => set(f.name, e.target.value)}
              />
            )}
          </div>
        ))}
      </div>
      <div className="ff">
        {submitted ? (
          <span className="form-submitted-tag">
            <Check width={13} height={13} /> {t.costForm.submitted}
          </span>
        ) : (
          <button className="btn btn-primary" type="submit" disabled={disabled}>
            <Sheet /> {t.costForm.submit}
          </button>
        )}
        <span className="hint">{submitted ? t.costForm.submittedHint : t.costForm.hint}</span>
      </div>
    </form>
  );
}
