"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import type { FormField, PendingForm } from "@/lib/types";
import { Sheet } from "../Icons";

export default function CostForm({
  form,
  disabled,
  onSubmit,
}: {
  form: PendingForm;
  disabled?: boolean;
  onSubmit: (formId: string, data: Record<string, unknown>) => void;
}) {
  const { t } = useT();

  // Fallback schema for the construction_cost form when the backend doesn't
  // send an explicit field list (it may only send form_id + prefill).
  const DEFAULT_FIELDS: FormField[] = [
    { name: "area_per_floor_m2", label: t.costForm.area, type: "number", required: true },
    { name: "num_floors", label: t.costForm.floors, type: "number", required: true, default: 1 },
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
    {
      name: "finish_level",
      label: t.costForm.finish,
      type: "select",
      default: "hoan_thien_co_ban",
      options: [
        { value: "tho", label: t.costForm.finishRough },
        { value: "hoan_thien_co_ban", label: t.costForm.finishBasic },
        { value: "hoan_thien_cao_cap", label: t.costForm.finishHigh },
      ],
    },
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

  return (
    <form className="form-card" onSubmit={submit}>
      <div className="fh">
        <span className="tg">Form</span>
        <h4>{form.title || t.costForm.title}</h4>
        <span className="sub">{form.form_id}</span>
      </div>
      <div className="fb">
        {fields.map((f) => (
          <div className="field" key={f.name}>
            <label>
              {f.label} {f.required && <span className="req">*</span>}
            </label>
            {f.type === "select" ? (
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
        <button className="btn btn-primary" type="submit" disabled={disabled}>
          <Sheet /> {t.costForm.submit}
        </button>
        <span className="hint">{t.costForm.hint}</span>
      </div>
    </form>
  );
}
