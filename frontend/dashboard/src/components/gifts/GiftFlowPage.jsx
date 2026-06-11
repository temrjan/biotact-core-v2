// ═══════════════════════════════════════════════════════════════
// GiftFlowPage — HR "Подарки" container: filters + Kanban + modals
//
// Rendered by BiotactDashboard for section === 'gifts'. Receives the
// dashboard theme via props and republishes it through GiftThemeContext
// so this subtree stays decoupled from the monolith.
//
// Each status column is fetched independently (status filter + page).
// A single time-windowed fetch would let in-flight cards vanish once
// the done/cancelled archive outgrows the window — WIP must always be
// fully visible on a Kanban; only terminal columns are paged.
// ═══════════════════════════════════════════════════════════════

import { useState, useEffect, useCallback, useMemo } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';

import * as api from '../../api';
import { GIFT_STATUSES } from './constants';
import { GiftThemeContext } from './GiftThemeContext';
import GiftFilters from './GiftFilters';
import KanbanBoard from './KanbanBoard';
import GiftFormModal from './GiftFormModal';
import GiftDetailModal from './GiftDetailModal';

const PAGE_SIZE = 100;
const EMPTY_FILTERS = { month: '', year: '', responsible: '' };

const EMPTY_COLUMNS = Object.fromEntries(
  GIFT_STATUSES.map((s) => [s.id, { items: [], total: 0, page: 1 }]),
);

function buildQuery(filters, status, page) {
  const query = { status, page, size: PAGE_SIZE };
  if (filters.month) query.month = Number(filters.month);
  if (filters.year) query.year = Number(filters.year);
  if (filters.responsible) query.responsible = Number(filters.responsible);
  return query;
}

export default function GiftFlowPage({ theme, isDark }) {
  const [columns, setColumns] = useState(EMPTY_COLUMNS);
  const [loading, setLoading] = useState(false);
  const [loadingMoreId, setLoadingMoreId] = useState(null);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState(EMPTY_FILTERS);

  const [modalMode, setModalMode] = useState(null); // 'create' | 'edit' | 'detail'
  const [selectedGift, setSelectedGift] = useState(null);
  const [movingId, setMovingId] = useState(null);

  const loadBoard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const responses = await Promise.all(
        GIFT_STATUSES.map((s) => api.listGifts(buildQuery(filters, s.id, 1))),
      );
      const next = {};
      GIFT_STATUSES.forEach((s, index) => {
        next[s.id] = {
          items: Array.isArray(responses[index].items) ? responses[index].items : [],
          total: responses[index].total ?? 0,
          page: 1,
        };
      });
      setColumns(next);
    } catch (err) {
      setError(err.message || 'Не удалось загрузить заявки');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadBoard();
  }, [loadBoard]);

  const handleLoadMore = async (statusId) => {
    const nextPage = columns[statusId].page + 1;
    setLoadingMoreId(statusId);
    setError(null);
    try {
      const res = await api.listGifts(buildQuery(filters, statusId, nextPage));
      setColumns((prev) => ({
        ...prev,
        [statusId]: {
          items: [...prev[statusId].items, ...(Array.isArray(res.items) ? res.items : [])],
          total: res.total ?? prev[statusId].total,
          page: nextPage,
        },
      }));
    } catch (err) {
      setError(err.message || 'Не удалось загрузить заявки');
    } finally {
      setLoadingMoreId(null);
    }
  };

  const boardIsEmpty = useMemo(
    () => GIFT_STATUSES.every((s) => columns[s.id].items.length === 0),
    [columns],
  );

  const handleChangeFilters = (patch) => setFilters((prev) => ({ ...prev, ...patch }));

  const handleSubmitForm = async (payload) => {
    if (modalMode === 'edit' && selectedGift) {
      await api.updateGift(selectedGift.id, payload);
    } else {
      await api.createGift(payload);
    }
    setModalMode(null);
    setSelectedGift(null);
    await loadBoard();
  };

  const handleMoveStatus = async (gift, statusId) => {
    setMovingId(gift.id);
    setError(null);
    try {
      await api.updateGiftStatus(gift.id, { status: statusId });
      await loadBoard();
    } catch (err) {
      setError(err.message || 'Не удалось сменить статус');
    } finally {
      setMovingId(null);
    }
  };

  const handleChangeStatus = async (statusId, comment) => {
    const updated = await api.updateGiftStatus(selectedGift.id, { status: statusId, comment });
    setSelectedGift(updated);
    await loadBoard();
  };

  const handleDelete = async () => {
    await api.deleteGift(selectedGift.id);
    setModalMode(null);
    setSelectedGift(null);
    await loadBoard();
  };

  const themeValue = useMemo(() => ({ theme, isDark }), [theme, isDark]);

  return (
    <GiftThemeContext.Provider value={themeValue}>
      <div className="p-8">
        <GiftFilters
          filters={filters}
          onChange={handleChangeFilters}
          onCreate={() => {
            setSelectedGift(null);
            setModalMode('create');
          }}
          onRefresh={loadBoard}
          loading={loading}
        />

        {error && (
          <div
            className="mb-4 flex items-center gap-2 rounded-xl border px-4 py-3 text-sm"
            style={{ borderColor: theme.text.error, color: theme.text.error }}
          >
            <AlertCircle size={16} /> {error}
          </div>
        )}

        {loading && boardIsEmpty ? (
          <div className="flex items-center gap-2 py-16 text-sm" style={{ color: theme.text.muted }}>
            <Loader2 size={18} className="animate-spin" /> Загрузка заявок…
          </div>
        ) : (
          <KanbanBoard
            columns={columns}
            onOpenGift={(gift) => {
              setSelectedGift(gift);
              setModalMode('detail');
            }}
            onMoveStatus={handleMoveStatus}
            movingId={movingId}
            onLoadMore={handleLoadMore}
            loadingMoreId={loadingMoreId}
          />
        )}
      </div>

      {(modalMode === 'create' || modalMode === 'edit') && (
        <GiftFormModal
          mode={modalMode}
          gift={modalMode === 'edit' ? selectedGift : null}
          onClose={() => {
            setModalMode(null);
            setSelectedGift(null);
          }}
          onSubmit={handleSubmitForm}
        />
      )}

      {modalMode === 'detail' && selectedGift && (
        <GiftDetailModal
          gift={selectedGift}
          onClose={() => {
            setModalMode(null);
            setSelectedGift(null);
          }}
          onEdit={(gift) => {
            setSelectedGift(gift);
            setModalMode('edit');
          }}
          onChangeStatus={handleChangeStatus}
          onDelete={handleDelete}
        />
      )}
    </GiftThemeContext.Provider>
  );
}
