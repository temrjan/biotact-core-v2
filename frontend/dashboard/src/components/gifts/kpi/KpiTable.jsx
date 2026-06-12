// ═══════════════════════════════════════════════════════════════
// KpiTable — monthly KPI records: plan / actual / % per metric
//
// Percentages come computed from the backend (<key>_pct,
// gifts/schemas.py KPIResponse) — never recalculated here.
// ═══════════════════════════════════════════════════════════════

import { Pencil, Trash2, StickyNote } from 'lucide-react';

import { statusMeta } from '../constants';
import { useGiftTheme } from '../GiftThemeContext';
import { KPI_METRICS, kpiPeriodLabel } from './constants';

// 100%-выполнение подсвечиваем зелёным статуса «Вручено» — палитра
// статусов в gifts/constants.js, не тема (там семантического success нет).
const PCT_DONE = statusMeta('done').color;

export default function KpiTable({ items, onEdit, onDelete, deletingId }) {
  const { theme } = useGiftTheme();

  return (
    <div
      className="overflow-x-auto rounded-xl border"
      style={{ borderColor: theme.border.default }}
    >
      <table className="w-full min-w-[860px] text-sm">
        <caption className="sr-only">Ежемесячные KPI модуля «Подарки»</caption>
        <thead>
          <tr style={{ color: theme.text.muted }}>
            <th className="px-3 py-2 text-left font-medium">Месяц</th>
            {KPI_METRICS.map(({ key, label }) => (
              <th key={key} className="px-3 py-2 text-center font-medium">
                {label}
                <div className="text-[10px] font-normal">план / факт / %</div>
              </th>
            ))}
            <th className="px-3 py-2 text-center font-medium">Заметки</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {items.map((kpi) => (
            <tr
              key={kpi.id}
              className="border-t"
              style={{ borderColor: theme.border.default, color: theme.text.primary }}
            >
              <td className="whitespace-nowrap px-3 py-2 font-medium">{kpiPeriodLabel(kpi)}</td>
              {KPI_METRICS.map(({ key }) => {
                const pct = kpi[`${key}_pct`];
                return (
                  <td key={key} className="whitespace-nowrap px-3 py-2 text-center">
                    {kpi[`${key}_planned`]} / {kpi[`${key}_actual`]} /{' '}
                    <span
                      className="font-semibold"
                      style={{ color: pct >= 100 ? PCT_DONE : theme.text.secondary }}
                    >
                      {pct}%
                    </span>
                  </td>
                );
              })}
              <td className="px-3 py-2 text-center">
                {kpi.notes ? (
                  <span title={kpi.notes} style={{ color: theme.text.muted }}>
                    <StickyNote size={15} className="inline" />
                  </span>
                ) : (
                  <span style={{ color: theme.text.muted }}>—</span>
                )}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right">
                <button
                  type="button"
                  onClick={() => onEdit(kpi)}
                  title="Редактировать"
                  className="mr-1 rounded-lg border p-1.5 transition-colors"
                  style={{ borderColor: theme.border.default, color: theme.text.muted }}
                >
                  <Pencil size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(kpi)}
                  disabled={deletingId === kpi.id}
                  title="Удалить"
                  className="rounded-lg border p-1.5 transition-colors disabled:opacity-60"
                  style={{ borderColor: theme.border.default, color: theme.text.error }}
                >
                  <Trash2 size={14} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
