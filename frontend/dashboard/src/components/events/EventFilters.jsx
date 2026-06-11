// ═══════════════════════════════════════════════════════════════
// EventFilters — toolbar: month/year/department filters + actions
// ═══════════════════════════════════════════════════════════════

import { Plus, RefreshCw, X } from 'lucide-react';

import { MONTHS } from './constants';

export default function EventFilters({ theme, filters, onChange, onCreate, onRefresh, loading }) {
  const fieldStyle = {
    backgroundColor: theme.bg.input,
    borderColor: theme.border.default,
    color: theme.text.primary,
  };

  const hasFilters =
    filters.month !== '' || filters.year !== '' || filters.department !== '';

  return (
    <div className="mb-5 flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-[11px]" style={{ color: theme.text.muted }}>Месяц</span>
        <select
          value={filters.month}
          onChange={(event) => onChange({ month: event.target.value })}
          className="rounded-lg border px-3 py-1.5 text-sm"
          style={fieldStyle}
        >
          <option value="">Все</option>
          {MONTHS.map((name, index) => (
            <option key={name} value={index + 1}>{name}</option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[11px]" style={{ color: theme.text.muted }}>Год</span>
        <input
          type="number"
          min="2000"
          max="2100"
          placeholder="—"
          value={filters.year}
          onChange={(event) => onChange({ year: event.target.value })}
          className="w-24 rounded-lg border px-3 py-1.5 text-sm"
          style={fieldStyle}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[11px]" style={{ color: theme.text.muted }}>Отдел</span>
        <input
          type="text"
          placeholder="—"
          value={filters.department}
          onChange={(event) => onChange({ department: event.target.value })}
          className="w-36 rounded-lg border px-3 py-1.5 text-sm"
          style={fieldStyle}
        />
      </label>

      {hasFilters && (
        <button
          type="button"
          onClick={() => onChange({ month: '', year: '', department: '' })}
          className="flex items-center gap-1 rounded-lg border px-3 py-1.5 text-sm transition-colors"
          style={{ borderColor: theme.border.default, color: theme.text.secondary }}
        >
          <X size={14} /> Сбросить
        </button>
      )}

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={onRefresh}
          title="Обновить"
          className="rounded-lg border p-2 transition-colors"
          style={{ borderColor: theme.border.default, color: theme.text.muted }}
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
        <button
          type="button"
          onClick={onCreate}
          className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
          style={{ backgroundColor: theme.bg.accent, color: theme.text.inverse }}
        >
          <Plus size={16} /> Добавить событие
        </button>
      </div>
    </div>
  );
}
