// ═══════════════════════════════════════════════════════════════
// KPI tab — metric metadata
//
// The five monthly metrics mirror backend GiftKPI (gifts/models.py).
// Each KPIResponse row carries <key>_planned, <key>_actual and a
// backend-computed <key>_pct — the frontend never recalculates.
// ═══════════════════════════════════════════════════════════════

import { MONTHS } from '../constants';

export const KPI_METRICS = [
  { key: 'employee_congrats', label: 'Поздравления сотрудников' },
  { key: 'partner_congrats', label: 'Поздравления партнёров' },
  { key: 'budget_compliance', label: 'Соблюдение бюджета' },
  { key: 'satisfaction', label: 'Удовлетворённость' },
  { key: 'timely_closure', label: 'Своевременное закрытие' },
];

export function kpiPeriodLabel(kpi) {
  return `${MONTHS[kpi.month - 1] ?? kpi.month} ${kpi.year}`;
}
