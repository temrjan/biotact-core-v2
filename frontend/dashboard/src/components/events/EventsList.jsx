// ═══════════════════════════════════════════════════════════════
// EventsList — calendar events as rows with edit/delete actions
//
// Backend sorts by event date, newest first (events/service.py).
// ═══════════════════════════════════════════════════════════════

import { Pencil, Trash2, Loader2 } from 'lucide-react';

import { occasionMeta, formatEventDate } from './constants';

function TypeBadge({ type }) {
  const meta = occasionMeta(type);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium"
      style={{ backgroundColor: `${meta.color}1a`, color: meta.color }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: meta.color }} />
      {meta.label}
    </span>
  );
}

export default function EventsList({
  theme,
  items,
  total,
  onLoadMore,
  loadingMore,
  onEdit,
  confirmDeleteId,
  onAskDelete,
  onConfirmDelete,
  onCancelDelete,
  deletingId,
}) {
  const remaining = total - items.length;

  if (items.length === 0) {
    return (
      <p className="py-16 text-center text-sm" style={{ color: theme.text.muted }}>
        Событий нет — добавьте первое
      </p>
    );
  }

  return (
    <div className="rounded-2xl border" style={{ borderColor: theme.border.default, backgroundColor: theme.bg.card }}>
      <ul className="divide-y" style={{ borderColor: theme.border.subtle }}>
        {items.map((event) => (
          <li key={event.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <span className="w-24 text-sm font-medium" style={{ color: theme.text.primary }}>
              {formatEventDate(event.date)}
            </span>
            <TypeBadge type={event.occasion_type} />
            <span className="min-w-40 flex-1 text-sm" style={{ color: theme.text.primary }}>
              {event.employee_name}
              <span className="ml-2 text-xs" style={{ color: theme.text.muted }}>
                {event.department}
              </span>
            </span>
            {event.notes && (
              <span className="max-w-xs truncate text-xs" style={{ color: theme.text.muted }}>
                {event.notes}
              </span>
            )}

            <span className="ml-auto flex items-center gap-1.5">
              {confirmDeleteId === event.id ? (
                <>
                  <span className="text-xs" style={{ color: theme.text.secondary }}>Удалить?</span>
                  <button
                    type="button"
                    onClick={() => onConfirmDelete(event.id)}
                    disabled={deletingId === event.id}
                    className="rounded-lg px-2.5 py-1 text-xs font-medium text-white transition-colors disabled:opacity-50"
                    style={{ backgroundColor: theme.text.error }}
                  >
                    {deletingId === event.id ? <Loader2 size={12} className="animate-spin" /> : 'Да'}
                  </button>
                  <button
                    type="button"
                    onClick={onCancelDelete}
                    className="rounded-lg border px-2.5 py-1 text-xs transition-colors"
                    style={{ borderColor: theme.border.default, color: theme.text.secondary }}
                  >
                    Нет
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => onEdit(event)}
                    title="Редактировать"
                    className="rounded-lg border p-1.5 transition-colors"
                    style={{ borderColor: theme.border.default, color: theme.text.secondary }}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onAskDelete(event.id)}
                    title="Удалить"
                    className="rounded-lg border p-1.5 transition-colors"
                    style={{ borderColor: theme.border.default, color: theme.text.error }}
                  >
                    <Trash2 size={14} />
                  </button>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>

      {remaining > 0 && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={loadingMore}
          className="flex w-full items-center justify-center gap-1.5 border-t py-2.5 text-xs font-medium transition-colors disabled:opacity-60"
          style={{ borderColor: theme.border.default, color: theme.text.secondary }}
        >
          {loadingMore ? <Loader2 size={14} className="animate-spin" /> : `Показать ещё (${remaining})`}
        </button>
      )}
    </div>
  );
}
