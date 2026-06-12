// ═══════════════════════════════════════════════════════════════
// KpiSection — "KPI" tab container: list + create/edit modal
//
// Loads up to 100 monthly records in one request (~8 years of
// data); if the archive ever outgrows that, a count note appears
// instead of silent truncation.
// ═══════════════════════════════════════════════════════════════

import { useState, useEffect, useCallback } from 'react';
import { AlertCircle, Loader2, Plus, RefreshCw } from 'lucide-react';

import * as api from '../../../api';
import { useGiftTheme } from '../GiftThemeContext';
import KpiFormModal from './KpiFormModal';
import KpiTable from './KpiTable';
import { kpiPeriodLabel } from './constants';

const PAGE_SIZE = 100;

export default function KpiSection() {
  const { theme } = useGiftTheme();

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [modalMode, setModalMode] = useState(null); // 'create' | 'edit'
  const [selectedKpi, setSelectedKpi] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const loadKpis = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listGiftKpis({ size: PAGE_SIZE });
      setItems(Array.isArray(res.items) ? res.items : []);
      setTotal(res.total ?? 0);
    } catch (err) {
      setError(err.message || 'Не удалось загрузить KPI');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadKpis();
  }, [loadKpis]);

  const handleSubmitForm = async (payload) => {
    if (modalMode === 'edit' && selectedKpi) {
      await api.updateGiftKpi(selectedKpi.id, payload);
    } else {
      await api.createGiftKpi(payload);
    }
    setModalMode(null);
    setSelectedKpi(null);
    await loadKpis();
  };

  const handleDelete = async (kpi) => {
    if (!window.confirm(`Удалить KPI за ${kpiPeriodLabel(kpi)}?`)) return;
    setDeletingId(kpi.id);
    setError(null);
    try {
      await api.deleteGiftKpi(kpi.id);
      await loadKpis();
    } catch (err) {
      setError(err.message || 'Не удалось удалить KPI');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <>
      <div className="mb-5 flex items-center justify-between">
        <span className="text-sm" style={{ color: theme.text.muted }}>
          Ежемесячные показатели модуля «Подарки» — проценты считает сервер
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadKpis}
            title="Обновить"
            className="rounded-lg border p-2 transition-colors"
            style={{ borderColor: theme.border.default, color: theme.text.muted }}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            type="button"
            onClick={() => {
              setSelectedKpi(null);
              setModalMode('create');
            }}
            className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
            style={{ backgroundColor: theme.bg.accent, color: theme.text.inverse }}
          >
            <Plus size={16} /> Добавить KPI
          </button>
        </div>
      </div>

      {error && (
        <div
          className="mb-4 flex items-center gap-2 rounded-xl border px-4 py-3 text-sm"
          style={{ borderColor: theme.text.error, color: theme.text.error }}
        >
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="flex items-center gap-2 py-16 text-sm" style={{ color: theme.text.muted }}>
          <Loader2 size={18} className="animate-spin" /> Загрузка KPI…
        </div>
      ) : items.length === 0 ? (
        <div className="py-16 text-center text-sm" style={{ color: theme.text.muted }}>
          Записей пока нет — добавьте KPI за первый месяц
        </div>
      ) : (
        <>
          <KpiTable
            items={items}
            onEdit={(kpi) => {
              setSelectedKpi(kpi);
              setModalMode('edit');
            }}
            onDelete={handleDelete}
            deletingId={deletingId}
          />
          {total > items.length && (
            <p className="mt-3 text-xs" style={{ color: theme.text.muted }}>
              Показаны первые {items.length} из {total} записей
            </p>
          )}
        </>
      )}

      {(modalMode === 'create' || modalMode === 'edit') && (
        <KpiFormModal
          mode={modalMode}
          kpi={modalMode === 'edit' ? selectedKpi : null}
          onClose={() => {
            setModalMode(null);
            setSelectedKpi(null);
          }}
          onSubmit={handleSubmitForm}
        />
      )}
    </>
  );
}
