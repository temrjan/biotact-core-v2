// ═══════════════════════════════════════════════════════════════
// GiftFormModal — create / edit a gift request
//
// Mirrors backend GiftCreateRequest (gifts/schemas.py). Optional
// fields are omitted from the payload when empty; on edit (PATCH)
// that means cleared optionals are left unchanged — acceptable for
// the MVP slice.
// ═══════════════════════════════════════════════════════════════

import { useState } from 'react';
import { X, Loader2 } from 'lucide-react';

import * as api from '../../api';
import { useGiftTheme } from './GiftThemeContext';

const LAST_CATEGORY_KEY = 'biotact_gift_last_category';

const EMPTY_FORM = {
  initiator: '',
  recipient: '',
  occasion: '',
  category: '',
  gift_name: '',
  budget: '',
  vendor: '',
  presentation_date: '',
  responsible_person_id: '',
  comment: '',
};

// Create-mode prefills — repeating fields only, all editable. Recipient,
// occasion, gift name, budget and date stay empty on purpose: they are
// unique per request (or money), and a stale default invites mistakes.
function createDefaults() {
  const user = api.getCurrentUser();
  let lastCategory = '';
  try {
    lastCategory = localStorage.getItem(LAST_CATEGORY_KEY) ?? '';
  } catch {
    // storage unavailable — start blank
  }
  return {
    ...EMPTY_FORM,
    initiator: user?.full_name ?? '',
    responsible_person_id: user?.id != null ? String(user.id) : '',
    category: lastCategory,
  };
}

function toForm(gift) {
  if (!gift) return createDefaults();
  return {
    initiator: gift.initiator ?? '',
    recipient: gift.recipient ?? '',
    occasion: gift.occasion ?? '',
    category: gift.category ?? '',
    gift_name: gift.gift_name ?? '',
    budget: gift.budget?.toString() ?? '',
    vendor: gift.vendor ?? '',
    presentation_date: gift.presentation_date ?? '',
    responsible_person_id: gift.responsible_person_id?.toString() ?? '',
    comment: gift.comment ?? '',
  };
}

function validate(form) {
  const errors = {};
  for (const field of ['initiator', 'recipient', 'occasion', 'category']) {
    if (!form[field].trim()) errors[field] = 'Обязательное поле';
  }
  if (form.budget === '' || Number(form.budget) < 0 || !Number.isFinite(Number(form.budget))) {
    errors.budget = 'Укажите бюджет (≥ 0)';
  }
  const responsible = Number(form.responsible_person_id);
  if (!Number.isInteger(responsible) || responsible < 1) {
    errors.responsible_person_id = 'Укажите ID (≥ 1)';
  }
  return errors;
}

function buildPayload(form) {
  const payload = {
    initiator: form.initiator.trim(),
    recipient: form.recipient.trim(),
    occasion: form.occasion.trim(),
    category: form.category.trim(),
    budget: Number(form.budget),
    responsible_person_id: Number(form.responsible_person_id),
  };
  if (form.gift_name.trim()) payload.gift_name = form.gift_name.trim();
  if (form.vendor.trim()) payload.vendor = form.vendor.trim();
  if (form.comment.trim()) payload.comment = form.comment.trim();
  if (form.presentation_date) payload.presentation_date = form.presentation_date;
  return payload;
}

export default function GiftFormModal({ mode, gift, onClose, onSubmit }) {
  const { theme } = useGiftTheme();
  const [form, setForm] = useState(() => toForm(gift));
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [saving, setSaving] = useState(false);

  const setField = (name, value) => setForm((prev) => ({ ...prev, [name]: value }));

  const handleSubmit = async (event) => {
    event.preventDefault();
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    setSubmitError(null);
    try {
      await onSubmit(buildPayload(form));
      try {
        localStorage.setItem(LAST_CATEGORY_KEY, form.category.trim());
      } catch {
        // storage unavailable — skip remembering
      }
    } catch (err) {
      setSubmitError(err.message || 'Не удалось сохранить заявку');
      setSaving(false);
    }
  };

  const fieldStyle = {
    backgroundColor: theme.bg.input,
    borderColor: theme.border.default,
    color: theme.text.primary,
  };

  const renderText = (name, label, { required = false, type = 'text', full = false } = {}) => (
    <label className={`flex flex-col gap-1 ${full ? 'col-span-2' : ''}`}>
      <span className="text-[11px]" style={{ color: theme.text.muted }}>
        {label}{required ? ' *' : ''}
      </span>
      <input
        type={type}
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
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border p-6"
        style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold" style={{ color: theme.text.primary }}>
            {mode === 'edit' ? 'Редактировать заявку' : 'Новая заявка на подарок'}
          </h3>
          <button type="button" onClick={onClose} style={{ color: theme.text.muted }}>
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {renderText('initiator', 'Инициатор', { required: true })}
          {renderText('recipient', 'Получатель', { required: true })}
          {renderText('occasion', 'Повод', { required: true })}
          {renderText('category', 'Категория', { required: true })}
          {renderText('gift_name', 'Название подарка')}
          {renderText('vendor', 'Поставщик')}
          {renderText('budget', 'Бюджет (сум)', { required: true, type: 'number' })}
          {renderText('responsible_person_id', 'ID ответственного', { required: true, type: 'number' })}
          {renderText('presentation_date', 'Дата вручения', { type: 'date' })}

          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-[11px]" style={{ color: theme.text.muted }}>Комментарий</span>
            <textarea
              rows={2}
              value={form.comment}
              onChange={(event) => setField('comment', event.target.value)}
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
            {mode === 'edit' ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </form>
    </div>
  );
}
