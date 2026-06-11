// ═══════════════════════════════════════════════════════════════
// EventFormModal — create / edit a calendar event
//
// Mirrors backend EventCreateRequest / EventUpdateRequest
// (src/biotact/modules/hr/events/schemas.py).
// ═══════════════════════════════════════════════════════════════

import { useState } from 'react';
import { X, Loader2 } from 'lucide-react';

import { OCCASION_TYPES } from './constants';

const EMPTY_FORM = {
  date: '',
  employee_name: '',
  department: '',
  occasion_type: 'birthday',
  notes: '',
};

function toForm(event) {
  if (!event) return { ...EMPTY_FORM };
  return {
    date: event.date ?? '',
    employee_name: event.employee_name ?? '',
    department: event.department ?? '',
    occasion_type: event.occasion_type ?? 'birthday',
    notes: event.notes ?? '',
  };
}

function validate(form) {
  const errors = {};
  if (!form.date) errors.date = 'Укажите дату';
  if (!form.employee_name.trim()) errors.employee_name = 'Обязательное поле';
  if (!form.department.trim()) errors.department = 'Обязательное поле';
  return errors;
}

function buildPayload(form) {
  return {
    date: form.date,
    employee_name: form.employee_name.trim(),
    department: form.department.trim(),
    occasion_type: form.occasion_type,
    // null clears notes on PATCH; harmless on create
    notes: form.notes.trim() || null,
  };
}

export default function EventFormModal({ theme, mode, event, onClose, onSubmit }) {
  const [form, setForm] = useState(() => toForm(event));
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [saving, setSaving] = useState(false);

  const setField = (name, value) => setForm((prev) => ({ ...prev, [name]: value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    setSubmitError(null);
    try {
      await onSubmit(buildPayload(form));
    } catch (err) {
      setSubmitError(err.message || 'Не удалось сохранить событие');
      setSaving(false);
    }
  };

  const fieldStyle = {
    backgroundColor: theme.bg.input,
    borderColor: theme.border.default,
    color: theme.text.primary,
  };

  const renderError = (name) =>
    errors[name] && (
      <span className="text-[11px]" style={{ color: theme.text.error }}>{errors[name]}</span>
    );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-2xl border p-6"
        style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold" style={{ color: theme.text.primary }}>
            {mode === 'edit' ? 'Редактировать событие' : 'Новое событие'}
          </h3>
          <button type="button" onClick={onClose} style={{ color: theme.text.muted }}>
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px]" style={{ color: theme.text.muted }}>Дата *</span>
            <input
              type="date"
              value={form.date}
              onChange={(e) => setField('date', e.target.value)}
              className="rounded-lg border px-3 py-1.5 text-sm"
              style={fieldStyle}
            />
            {renderError('date')}
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px]" style={{ color: theme.text.muted }}>Тип события *</span>
            <select
              value={form.occasion_type}
              onChange={(e) => setField('occasion_type', e.target.value)}
              className="rounded-lg border px-3 py-1.5 text-sm"
              style={fieldStyle}
            >
              {OCCASION_TYPES.map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px]" style={{ color: theme.text.muted }}>ФИО сотрудника *</span>
            <input
              type="text"
              value={form.employee_name}
              onChange={(e) => setField('employee_name', e.target.value)}
              className="rounded-lg border px-3 py-1.5 text-sm"
              style={fieldStyle}
            />
            {renderError('employee_name')}
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px]" style={{ color: theme.text.muted }}>Отдел *</span>
            <input
              type="text"
              value={form.department}
              onChange={(e) => setField('department', e.target.value)}
              className="rounded-lg border px-3 py-1.5 text-sm"
              style={fieldStyle}
            />
            {renderError('department')}
          </label>

          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-[11px]" style={{ color: theme.text.muted }}>Заметка</span>
            <textarea
              rows={2}
              value={form.notes}
              onChange={(e) => setField('notes', e.target.value)}
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
            {mode === 'edit' ? 'Сохранить' : 'Добавить'}
          </button>
        </div>
      </form>
    </div>
  );
}
