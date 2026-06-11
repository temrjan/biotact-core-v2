// ═══════════════════════════════════════════════════════════════
// KanbanBoard — gift requests laid out in 7 status columns
// ═══════════════════════════════════════════════════════════════

import { GIFT_STATUSES } from './constants';
import { useGiftTheme } from './GiftThemeContext';
import GiftCard from './GiftCard';

export default function KanbanBoard({ giftsByStatus, onOpenGift, onMoveStatus, movingId }) {
  const { theme } = useGiftTheme();

  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {GIFT_STATUSES.map((column) => {
        const cards = giftsByStatus[column.id] ?? [];
        return (
          <section
            key={column.id}
            className="flex w-72 flex-shrink-0 flex-col rounded-2xl border"
            style={{ backgroundColor: theme.bg.elevated, borderColor: theme.border.default }}
          >
            <header
              className="flex items-center justify-between border-b px-3 py-2.5"
              style={{ borderColor: theme.border.default }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: column.color }}
                />
                <span className="text-sm font-medium" style={{ color: theme.text.primary }}>
                  {column.label}
                </span>
              </div>
              <span
                className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                style={{ backgroundColor: theme.bg.card, color: theme.text.muted }}
              >
                {cards.length}
              </span>
            </header>

            <div className="flex flex-col gap-2.5 p-2.5">
              {cards.length === 0 ? (
                <p className="px-1 py-6 text-center text-xs" style={{ color: theme.text.muted }}>
                  Нет заявок
                </p>
              ) : (
                cards.map((gift) => (
                  <GiftCard
                    key={gift.id}
                    gift={gift}
                    onOpen={onOpenGift}
                    onMoveStatus={onMoveStatus}
                    isMoving={movingId === gift.id}
                  />
                ))
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
