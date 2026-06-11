// ═══════════════════════════════════════════════════════════════
// GiftCard — single gift request card inside a Kanban column
// ═══════════════════════════════════════════════════════════════

import { ChevronLeft, ChevronRight, Calendar, User, Wallet, Loader2 } from 'lucide-react';

import { PIPELINE_ORDER, formatMoney, formatGiftDate } from './constants';
import { useGiftTheme } from './GiftThemeContext';

export default function GiftCard({ gift, onOpen, onMoveStatus, isMoving }) {
  const { theme } = useGiftTheme();

  const pipelineIndex = PIPELINE_ORDER.indexOf(gift.status);
  const prevStatus = pipelineIndex > 0 ? PIPELINE_ORDER[pipelineIndex - 1] : null;
  const nextStatus =
    pipelineIndex >= 0 && pipelineIndex < PIPELINE_ORDER.length - 1
      ? PIPELINE_ORDER[pipelineIndex + 1]
      : null;

  const handleMove = (event, target) => {
    event.stopPropagation();
    if (target) onMoveStatus(gift, target);
  };

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(gift)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen(gift);
        }
      }}
      className="cursor-pointer rounded-xl border p-3 transition-all hover:shadow-md focus:outline-none focus:ring-2"
      style={{
        backgroundColor: theme.bg.card,
        borderColor: theme.border.default,
        opacity: isMoving ? 0.6 : 1,
        pointerEvents: isMoving ? 'none' : 'auto',
      }}
    >
      <h4 className="mb-1 text-sm font-semibold" style={{ color: theme.text.primary }}>
        {gift.recipient}
      </h4>
      <p className="mb-2 text-xs" style={{ color: theme.text.secondary }}>
        {gift.occasion}
        {gift.category ? ` · ${gift.category}` : ''}
      </p>

      <div className="space-y-1 text-[11px]" style={{ color: theme.text.muted }}>
        <div className="flex items-center gap-1.5">
          <Wallet size={12} /> {formatMoney(gift.budget)}
        </div>
        <div className="flex items-center gap-1.5">
          <Calendar size={12} /> {formatGiftDate(gift.presentation_date)}
        </div>
        <div className="flex items-center gap-1.5">
          <User size={12} /> Инициатор: {gift.initiator}
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between">
        <button
          type="button"
          disabled={!prevStatus || isMoving}
          onClick={(event) => handleMove(event, prevStatus)}
          title="Предыдущий статус"
          className="rounded-lg border p-1 transition-colors disabled:opacity-30"
          style={{ borderColor: theme.border.default, color: theme.text.secondary }}
        >
          <ChevronLeft size={14} />
        </button>
        {isMoving ? (
          <Loader2 size={12} className="animate-spin" style={{ color: theme.text.muted }} />
        ) : (
          <span className="text-[10px]" style={{ color: theme.text.muted }}>
            #{gift.id}
          </span>
        )}
        <button
          type="button"
          disabled={!nextStatus || isMoving}
          onClick={(event) => handleMove(event, nextStatus)}
          title="Следующий статус"
          className="rounded-lg border p-1 transition-colors disabled:opacity-30"
          style={{ borderColor: theme.border.default, color: theme.text.secondary }}
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </article>
  );
}
