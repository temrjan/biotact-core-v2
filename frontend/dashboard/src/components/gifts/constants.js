// ═══════════════════════════════════════════════════════════════
// GiftFlow — shared constants & formatters
// ═══════════════════════════════════════════════════════════════

// Month names shared by the board filters and the KPI tab.
export const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

// Status codes mirror backend GiftStatus (src/biotact/modules/hr/gifts/models.py).
// Colors per design review (2026-06-11). Labels per HR_GIFTS_PHASE2_PLAN §1.3.
export const GIFT_STATUSES = [
  { id: 'new', label: 'Новая заявка', color: '#3b82f6' },
  { id: 'approval', label: 'На согласовании', color: '#d97706' },
  { id: 'purchase', label: 'Закупка', color: '#7c3aed' },
  { id: 'packaging', label: 'Упаковка', color: '#ea580c' },
  { id: 'ready', label: 'Готово к вручению', color: '#0ea5e9' },
  { id: 'done', label: 'Вручено', color: '#499C75' },
  { id: 'cancelled', label: 'Отменено', color: '#78716c' },
];

// Linear progression used by the card "← / →" quick-move buttons.
// `cancelled` is intentionally excluded — it is a side transition,
// handled only via the detail modal.
export const PIPELINE_ORDER = ['new', 'approval', 'purchase', 'packaging', 'ready', 'done'];

const STATUS_BY_ID = Object.fromEntries(GIFT_STATUSES.map((s) => [s.id, s]));

export function statusMeta(id) {
  return STATUS_BY_ID[id] ?? { id, label: id, color: '#78716c' };
}

export function formatMoney(amount) {
  if (amount === null || amount === undefined) return '—';
  return `${new Intl.NumberFormat('ru-RU').format(amount)} сум`;
}

// presentation_date arrives as an ISO date string ("YYYY-MM-DD") or null.
// Format by string parts to avoid the UTC-midnight timezone shift that
// `new Date('2026-06-15')` introduces.
export function formatGiftDate(isoDate) {
  if (!isoDate) return '—';
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) return isoDate;
  const [, year, month, day] = match;
  return `${day}.${month}.${year}`;
}

// created_at is a full ISO timestamp — safe to render via Date.
export function formatTimestamp(isoTimestamp) {
  if (!isoTimestamp) return '—';
  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) return isoTimestamp;
  return date.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
