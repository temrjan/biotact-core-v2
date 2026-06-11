// ═══════════════════════════════════════════════════════════════
// StatusBadge — colored pill for a gift request status
// ═══════════════════════════════════════════════════════════════

import { statusMeta } from './constants';

export default function StatusBadge({ status }) {
  const meta = statusMeta(status);

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium"
      style={{ backgroundColor: `${meta.color}1a`, color: meta.color }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: meta.color }}
      />
      {meta.label}
    </span>
  );
}
