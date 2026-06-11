// ═══════════════════════════════════════════════════════════════
// GiftFlowPage — HR "Подарки" container: filters + Kanban + modals
//
// Rendered by BiotactDashboard for section === 'gifts'. Receives the
// dashboard theme via props and republishes it through GiftThemeContext
// so this subtree stays decoupled from the monolith.
// ═══════════════════════════════════════════════════════════════

import { useState, useEffect, useCallback, useMemo } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';

import * as api from '../../api';
import { GiftThemeContext } from './GiftThemeContext';
import GiftFilters from './GiftFilters';
import KanbanBoard from './KanbanBoard';
import GiftFormModal from './GiftFormModal';
import GiftDetailModal from './GiftDetailModal';

const PAGE_SIZE = 100;
const EMPTY_FILTERS = { month: '', year: '', responsible: '' };

function buildQuery(filters) {
  const query = { page: 1, size: PAGE_SIZE };
  if (filters.month) query.month = Number(filters.month);
  if (filters.year) query.year = Number(filters.year);
  if (filters.responsible) query.responsible = Number(filters.responsible);
  return query;
}

export default function GiftFlowPage({ theme, isDark }) {
  const [gifts, setGifts] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState(EMPTY_FILTERS);

  const [modalMode, setModalMode] = useState(null); // 'create' | 'edit' | 'detail'
  const [selectedGift, setSelectedGift] = useState(null);
  const [movingId, setMovingId] = useState(null);

  const loadGifts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listGifts(buildQuery(filters));
      setGifts(Array.isArray(res.items) ? res.items : []);
      setTotal(res.total ?? 0);
    } catch (err) {
      setError(err.message || 'Не удалось загрузить заявки');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadGifts();
  }, [loadGifts]);

  const giftsByStatus = useMemo(() => {
    const grouped = {};
    for (const gift of gifts) {
      (grouped[gift.status] ??= []).push(gift);
    }
    return grouped;
  }, [gifts]);

  const handleChangeFilters = (patch) => setFilters((prev) => ({ ...prev, ...patch }));

  const handleSubmitForm = async (payload) => {
    if (modalMode === 'edit' && selectedGift) {
      await api.updateGift(selectedGift.id, payload);
    } else {
      await api.createGift(payload);
    }
    setModalMode(null);
    setSelectedGift(null);
    await loadGifts();
  };

  const handleMoveStatus = async (gift, statusId) => {
    setMovingId(gift.id);
    setError(null);
    try {
      await api.updateGiftStatus(gift.id, { status: statusId });
      await loadGifts();
    } catch (err) {
      setError(err.message || 'Не удалось сменить статус');
    } finally {
      setMovingId(null);
    }
  };

  const handleChangeStatus = async (statusId, comment) => {
    const updated = await api.updateGiftStatus(selectedGift.id, { status: statusId, comment });
    setSelectedGift(updated);
    await loadGifts();
  };

  const handleDelete = async () => {
    await api.deleteGift(selectedGift.id);
    setModalMode(null);
    setSelectedGift(null);
    await loadGifts();
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
          onRefresh={loadGifts}
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

        {total > gifts.length && (
          <p className="mb-3 text-xs" style={{ color: theme.text.muted }}>
            Показаны первые {gifts.length} из {total} заявок. Уточните фильтры, чтобы увидеть остальные.
          </p>
        )}

        {loading && gifts.length === 0 ? (
          <div className="flex items-center gap-2 py-16 text-sm" style={{ color: theme.text.muted }}>
            <Loader2 size={18} className="animate-spin" /> Загрузка заявок…
          </div>
        ) : (
          <KanbanBoard
            giftsByStatus={giftsByStatus}
            onOpenGift={(gift) => {
              setSelectedGift(gift);
              setModalMode('detail');
            }}
            onMoveStatus={handleMoveStatus}
            movingId={movingId}
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
