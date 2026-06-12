// ═══════════════════════════════════════════════════════════════
// KpiFormModal — create / edit a monthly KPI record
//
// Mirrors backend KPICreateRequest / KPIUpdateRequest
// (gifts/schemas.py). month + year are immutable on the backend, so
// in edit mode both selects are disabled and excluded from the
// payload. PATCH sends changed fields only. A duplicate month
// answers 409 — shown inline, the form stays open with the data.
// ═══════════════════════════════════════════════════════════════

import { useState } from 'react';
import { X, Loader2 } from 'lucide-react';

import { MONTHS } from '../constants';
import { useGiftTheme } from '../GiftThemeContext';
import { KPI_METRICS } from './constants';

const METRIC_FIELDS = KPI_METRICS.flatMap(({ key }) => [`${key}_planned`, `${key}_actual`]);

function createDefaults() {
  const now = new Date();
  const form = {
    month: String(now.getMonth() + 1),
    year: String(now.getFullYear()),
    notes: '',
  };
  for (const field of METRIC_FIELDS) form[field] = '0';
  form.budget_compliance_planned = '100';
  return form;
}

function toForm(kpi) {
  if (!kpi) return createDefaults();
  const form = {
    month: String(kpi.month),
    year: String(kpi.year),
    notes: kpi.notes ?? '',
  };
  for (const field of METRIC_FIELDS) form[field] = String(kpi[field] ?? 0);
  return form;
}

function validate(form) {
  const errors = {};
  for (const field of METRIC_FIELDS) {
    if (!/^\d+$/.test(form[field].trim())) errors[field] = 'Целое число ≥ 0';
  }
  return errors;
}

// Create sends the full record; edit sends changed fields only
// (month/year are immutable and never included on PATCH).
function buildPayload(form, initial) {
  const payload = {};
  for (const field of METRIC_FIELDS) {
    const value = Number(form[field]);
    if (!initial || value !== Number(initial[field])) payload[field] = value;
  }
  const notes = form.notes.trim();
  if (!initial) {
    payload.month = Number(form.month);
    payload.year = Number(form.year);
    if (notes) payload.notes = notes;
  } else if (notes !== (initial.notes ?? '')) {
    payload.notes = notes || null;
  }
  return payload;
}

export default function KpiFormModal({ mode, kpi, onClose, onSubmit }) {
  const { theme } = useGiftTheme();
  const isEdit = mode === 'edit';
  const [form, setForm] = useState(() => toForm(kpi));
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [saving, setSaving] = useState(false);

  const setField = (name, value) => setForm((prev) => ({ ...prev, [name]: value }));

  const handleSubmit = async (event) => {
    event.preventDefault();
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const payload = buildPayload(form, isEdit ? toForm(kpi) : null);
    if (isEdit && Object.keys(payload).length === 0) {
      onClose();
      return;
    }

    setSaving(true);
    setSubmitError(null);
    try {
      await onSubmit(payload);
    } catch (err) {
      setSubmitError(
        err.status === 409
          ? 'KPI за этот месяц уже существует — откройте его на редактирование'
          : err.message || 'Не удалось сохранить KPI',
      );
      setSaving(false);
    }
  };

  const fieldStyle = {
    backgroundColor: theme.bg.input,
    borderColor: theme.border.default,
    color: theme.text.primary,
  };

  const renderNumber = (name, label) => (
    <label className="flex flex-col gap-1">
      <span className="text-[11px]" style={{ color: theme.text.muted }}>{label}</span>
      <input
        type="number"
        min="0"
        step="1"
        value={form[name]}
        onChange={(event) => setField(name, event.target.value)}
        className="rounded-lg border px-3 py-1.5 text-sm"
        style={fieldStyle}
      />
      {errors[name] && (
        <span className="text-[11px]" style={{ color: theme.text.error }}>{errors[name]}</span>
      )}
    </label>
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <form
        onClick={(event) => event.stopPropagation()}
        onSubmit={handleSubmit}
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl border p-6"
        style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold" style={{ color: theme.text.primary }}>
            {isEdit ? 'Редактировать KPI' : 'Новый KPI за месяц'}
          </h3>
          <button type="button" onClick={onClose} style={{ color: theme.text.muted }}>
            <X size={18} />
          </button>
        </div>

        <div className="mb-3 grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px]" style={{ color: theme.text.muted }}>
              Месяц{isEdit ? ' (нельзя изменить)' : ''}
            </span>
            <select
              value={form.month}
              onChange={(event) => setField('month', event.target.value)}
              disabled={isEdit}
              className="rounded-lg border px-3 py-1.5 text-sm disabled:opacity-60"
              style={fieldStyle}
            >
              {MONTHS.map((name, index) => (
                <option key={name} value={index + 1}>{name}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px]" style={{ color: theme.text.muted }}>
              Год{isEdit ? ' (нельзя изменить)' : ''}
            </span>
            <input
              type="number"
              min="2000"
              max="2100"
              value={form.year}
              onChange={(event) => setField('year', event.target.value)}
              disabled={isEdit}
              className="rounded-lg border px-3 py-1.5 text-sm disabled:opacity-60"
              style={fieldStyle}
            />
          </label>
        </div>

        <div className="flex flex-col gap-3">
          {KPI_METRICS.map(({ key, label }) => (
            <div key={key} className="grid grid-cols-2 gap-3">
              {renderNumber(`${key}_planned`, `${label} — план`)}
              {renderNumber(`${key}_actual`, `${label} — факт`)}
            </div>
          ))}

          <label className="flex flex-col gap-1">
            <span className="text-[11px]" style={{ color: theme.text.muted }}>Заметки</span>
            <textarea
              rows={2}
              maxLength={2000}
              value={form.notes}
              onChange={(event) => setField('notes', event.target.value)}
              className="resize-none rounded-lg border px-3 py-1.5 text-sm"
              style={fieldStyle}
            />
          </label>
        </div>

        {submitError && (
          <p className="mt-3 text-sm" style={{ color: theme.text.error }}>{submitError}</p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border px-4 py-2 text-sm transition-colors"
            style={{ borderColor: theme.border.default, color: theme.text.secondary }}
          >
            Отмена
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-60"
            style={{ backgroundColor: theme.bg.accent, color: theme.text.inverse }}
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            {isEdit ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </form>
    </div>
  );
}
