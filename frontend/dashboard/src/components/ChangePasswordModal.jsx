// ═══════════════════════════════════════════════════════════════
// ChangePasswordModal — self-service password change
//
// Rendered by BiotactDashboard next to the logout button. Receives
// the dashboard theme via props (same decoupling pattern as gifts/).
// ═══════════════════════════════════════════════════════════════

import { useState } from 'react';
import { X, Loader2, Check } from 'lucide-react';

import * as api from '../api';

// Backend detail → human message; anything unknown falls through as-is.
const ERROR_MESSAGES = {
  'Current password is incorrect': 'Текущий пароль неверен',
};

export default function ChangePasswordModal({ theme, onClose }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (next.length < 8) {
      setError('Новый пароль — минимум 8 символов');
      return;
    }
    if (next !== repeat) {
      setError('Пароли не совпадают');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.changePassword(current, next);
      setDone(true);
      setTimeout(onClose, 1500);
    } catch (err) {
      setError(ERROR_MESSAGES[err.message] || err.message || 'Не удалось сменить пароль');
      setSaving(false);
    }
  };

  const fieldStyle = {
    backgroundColor: theme.bg.input,
    borderColor: theme.border.default,
    color: theme.text.primary,
  };

  const renderField = (label, value, setValue, autoComplete) => (
    <label className="flex flex-col gap-1">
      <span className="text-[11px]" style={{ color: theme.text.muted }}>{label}</span>
      <input
        type="password"
        required
        value={value}
        onChange={(event) => setValue(event.target.value)}
        autoComplete={autoComplete}
        className="rounded-lg border px-3 py-2 text-sm"
        style={fieldStyle}
      />
    </label>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <form
        onClick={(event) => event.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl border p-6"
        style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold" style={{ color: theme.text.primary }}>
            Смена пароля
          </h3>
          <button type="button" onClick={onClose} style={{ color: theme.text.muted }}>
            <X size={18} />
          </button>
        </div>

        {done ? (
          <div className="flex items-center gap-2 py-4 text-sm" style={{ color: theme.text.success }}>
            <Check size={18} /> Пароль изменён
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {renderField('Текущий пароль', current, setCurrent, 'current-password')}
              {renderField('Новый пароль (мин. 8 символов)', next, setNext, 'new-password')}
              {renderField('Новый пароль ещё раз', repeat, setRepeat, 'new-password')}
            </div>

            {error && (
              <p className="mt-3 text-sm" style={{ color: theme.text.error }}>{error}</p>
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
                Сменить
              </button>
            </div>
          </>
        )}
      </form>
    </div>
  );
}
