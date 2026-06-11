// ═══════════════════════════════════════════════════════════════
// GiftDetailModal — full gift details, status change, history,
// edit / delete actions
// ═══════════════════════════════════════════════════════════════

import { useState, useEffect, useCallback } from 'react';
import { X, Loader2, Pencil, Trash2 } from 'lucide-react';

import * as api from '../../api';
import { GIFT_STATUSES, formatMoney, formatGiftDate, formatTimestamp, statusMeta } from './constants';
import { useGiftTheme } from './GiftThemeContext';
import StatusBadge from './StatusBadge';

function DetailRow({ label, value, theme }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <span style={{ color: theme.text.muted }}>{label}</span>
      <span className="text-right font-medium" style={{ color: theme.text.primary }}>{value}</span>
    </div>
  );
}

export default function GiftDetailModal({ gift, onClose, onEdit, onChangeStatus, onDelete }) {
  const { theme } = useGiftTheme();
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [newStatus, setNewStatus] = useState('');
  const [statusComment, setStatusComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const items = await api.listGiftHistory(gift.id);
      setHistory(Array.isArray(items) ? items : []);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, [gift.id]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory, gift.status]);

  const handleApplyStatus = async () => {
    if (!newStatus || newStatus === gift.status) return;
    setBusy(true);
    setError(null);
    try {
      await onChangeStatus(newStatus, statusComment.trim() || null);
      setNewStatus('');
      setStatusComment('');
    } catch (err) {
      setError(err.message || 'Не удалось сменить статус');
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    setBusy(true);
    setError(null);
    try {
      await onDelete();
    } catch (err) {
      setError(err.message || 'Не удалось удалить заявку');
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        onClick={(event) => event.stopPropagation()}
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border p-6"
        style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="text-base font-semibold" style={{ color: theme.text.primary }}>
              {gift.recipient}
            </h3>
            <p className="text-xs" style={{ color: theme.text.muted }}>Заявка #{gift.id}</p>
          </div>
          <button type="button" onClick={onClose} style={{ color: theme.text.muted }}>
            <X size={18} />
          </button>
        </div>

        <div className="mb-3"><StatusBadge status={gift.status} /></div>

        <div className="mb-4 divide-y" style={{ borderColor: theme.border.subtle }}>
          <DetailRow label="Повод" value={gift.occasion} theme={theme} />
          <DetailRow label="Категория" value={gift.category} theme={theme} />
          {gift.gift_name && <DetailRow label="Подарок" value={gift.gift_name} theme={theme} />}
          <DetailRow label="Бюджет" value={formatMoney(gift.budget)} theme={theme} />
          {gift.vendor && <DetailRow label="Поставщик" value={gift.vendor} theme={theme} />}
          <DetailRow label="Дата вручения" value={formatGiftDate(gift.presentation_date)} theme={theme} />
          <DetailRow label="Инициатор" value={gift.initiator} theme={theme} />
          <DetailRow label="Ответственный" value={`#${gift.responsible_person_id}`} theme={theme} />
          {gift.comment && <DetailRow label="Комментарий" value={gift.comment} theme={theme} />}
        </div>

        {/* Status change */}
        <div className="mb-4 rounded-xl border p-3" style={{ borderColor: theme.border.default }}>
          <p className="mb-2 text-xs font-medium" style={{ color: theme.text.secondary }}>Сменить статус</p>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={newStatus}
              onChange={(event) => setNewStatus(event.target.value)}
              className="rounded-lg border px-3 py-1.5 text-sm"
              style={{ backgroundColor: theme.bg.input, borderColor: theme.border.default, color: theme.text.primary }}
            >
              <option value="">— выбрать —</option>
              {GIFT_STATUSES.filter((s) => s.id !== gift.status).map((s) => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Комментарий (необязательно)"
              value={statusComment}
              onChange={(event) => setStatusComment(event.target.value)}
              className="flex-1 rounded-lg border px-3 py-1.5 text-sm"
              style={{ backgroundColor: theme.bg.input, borderColor: theme.border.default, color: theme.text.primary }}
            />
            <button
              type="button"
              onClick={handleApplyStatus}
              disabled={busy || !newStatus}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50"
              style={{ backgroundColor: theme.bg.accent, color: theme.text.inverse }}
            >
              {busy && <Loader2 size={14} className="animate-spin" />} Применить
            </button>
          </div>
        </div>

        {/* History */}
        <div className="mb-4">
          <p className="mb-2 text-xs font-medium" style={{ color: theme.text.secondary }}>История статусов</p>
          {historyLoading ? (
            <Loader2 size={16} className="animate-spin" style={{ color: theme.text.muted }} />
          ) : history.length === 0 ? (
            <p className="text-xs" style={{ color: theme.text.muted }}>Изменений пока нет</p>
          ) : (
            <ul className="space-y-1.5">
              {history.map((item) => (
                <li key={item.id} className="text-xs" style={{ color: theme.text.secondary }}>
                  <span style={{ color: statusMeta(item.from_status).color }}>{statusMeta(item.from_status).label}</span>
                  {' → '}
                  <span style={{ color: statusMeta(item.to_status).color }}>{statusMeta(item.to_status).label}</span>
                  <span style={{ color: theme.text.muted }}> · #{item.changed_by} · {formatTimestamp(item.created_at)}</span>
                  {item.comment && <span style={{ color: theme.text.muted }}> — {item.comment}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p className="mb-3 text-sm" style={{ color: theme.text.error }}>{error}</p>}

        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => onEdit(gift)}
            className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors"
            style={{ borderColor: theme.border.default, color: theme.text.secondary }}
          >
            <Pencil size={14} /> Редактировать
          </button>

          {confirmDelete ? (
            <div className="flex items-center gap-2">
              <span className="text-xs" style={{ color: theme.text.secondary }}>Удалить?</span>
              <button
                type="button"
                onClick={handleDelete}
                disabled={busy}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-white transition-colors disabled:opacity-50"
                style={{ backgroundColor: theme.text.error }}
              >
                Да
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="rounded-lg border px-3 py-1.5 text-sm transition-colors"
                style={{ borderColor: theme.border.default, color: theme.text.secondary }}
              >
                Нет
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors"
              style={{ borderColor: theme.border.default, color: theme.text.error }}
            >
              <Trash2 size={14} /> Удалить
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
