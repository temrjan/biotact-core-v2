// ═══════════════════════════════════════════════════════════════
// Events Calendar — shared constants & formatters
// ═══════════════════════════════════════════════════════════════

// Mirrors backend OccasionType (src/biotact/modules/hr/events/models.py).
export const OCCASION_TYPES = [
  { id: 'birthday', label: 'День рождения', color: '#3b82f6' },
  { id: 'wedding', label: 'Свадьба', color: '#ec4899' },
  { id: 'anniversary', label: 'Юбилей', color: '#7c3aed' },
  { id: 'holiday', label: 'Праздник', color: '#499C75' },
  { id: 'other', label: 'Другое', color: '#78716c' },
];

const TYPE_BY_ID = Object.fromEntries(OCCASION_TYPES.map((t) => [t.id, t]));

export function occasionMeta(id) {
  return TYPE_BY_ID[id] ?? { id, label: id, color: '#78716c' };
}

export const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

// date arrives as an ISO date string ("YYYY-MM-DD"). Format by string
// parts to avoid the UTC-midnight timezone shift of `new Date(...)`.
export function formatEventDate(isoDate) {
  if (!isoDate) return '—';
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) return isoDate;
  const [, year, month, day] = match;
  return `${day}.${month}.${year}`;
}
