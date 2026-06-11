// ═══════════════════════════════════════════════════════════════
// EventsPage — HR "События" container: filters + list + form modal
//
// Rendered by BiotactDashboard for section === 'events'. Receives the
// dashboard theme via props; the tree is shallow, so the theme is
// passed down as plain props (no context needed, unlike gifts/).
// ═══════════════════════════════════════════════════════════════

import { useState, useEffect, useCallback } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';

import * as api from '../../api';
import EventFilters from './EventFilters';
import EventsList from './EventsList';
import EventFormModal from './EventFormModal';

const PAGE_SIZE = 20;
const EMPTY_FILTERS = { month: '', year: '', department: '' };

function buildQuery(filters, page) {
  const query = { page, size: PAGE_SIZE };
  if (filters.month) query.month = Number(filters.month);
  if (filters.year) query.year = Number(filters.year);
  if (filters.department.trim()) query.department = filters.department.trim();
  return query;
}

export default function EventsPage({ theme }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState(EMPTY_FILTERS);

  const [modalMode, setModalMode] = useState(null); // 'create' | 'edit'
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listEvents(buildQuery(filters, 1));
      setItems(Array.isArray(res.items) ? res.items : []);
      setTotal(res.total ?? 0);
      setPage(1);
    } catch (err) {
      setError(err.message || 'Не удалось загрузить события');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  const handleLoadMore = async () => {
    setLoadingMore(true);
    setError(null);
    try {
      const res = await api.listEvents(buildQuery(filters, page + 1));
      setItems((prev) => [...prev, ...(Array.isArray(res.items) ? res.items : [])]);
      setTotal(res.total ?? total);
      setPage((prev) => prev + 1);
    } catch (err) {
      setError(err.message || 'Не удалось загрузить события');
    } finally {
      setLoadingMore(false);
    }
  };

  const handleChangeFilters = (patch) => setFilters((prev) => ({ ...prev, ...patch }));

  const handleSubmitForm = async (payload) => {
    if (modalMode === 'edit' && selectedEvent) {
      await api.updateEvent(selectedEvent.id, payload);
    } else {
      await api.createEvent(payload);
    }
    setModalMode(null);
    setSelectedEvent(null);
    await loadEvents();
  };

  const handleConfirmDelete = async (eventId) => {
    setDeletingId(eventId);
    setError(null);
    try {
      await api.deleteEvent(eventId);
      setConfirmDeleteId(null);
      await loadEvents();
    } catch (err) {
      setError(err.message || 'Не удалось удалить событие');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="p-8">
      <EventFilters
        theme={theme}
        filters={filters}
        onChange={handleChangeFilters}
        onCreate={() => {
          setSelectedEvent(null);
          setModalMode('create');
        }}
        onRefresh={loadEvents}
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

      {loading && items.length === 0 ? (
        <div className="flex items-center gap-2 py-16 text-sm" style={{ color: theme.text.muted }}>
          <Loader2 size={18} className="animate-spin" /> Загрузка событий…
        </div>
      ) : (
        <EventsList
          theme={theme}
          items={items}
          total={total}
          onLoadMore={handleLoadMore}
          loadingMore={loadingMore}
          onEdit={(event) => {
            setSelectedEvent(event);
            setModalMode('edit');
          }}
          confirmDeleteId={confirmDeleteId}
          onAskDelete={setConfirmDeleteId}
          onConfirmDelete={handleConfirmDelete}
          onCancelDelete={() => setConfirmDeleteId(null)}
          deletingId={deletingId}
        />
      )}

      {modalMode && (
        <EventFormModal
          theme={theme}
          mode={modalMode}
          event={modalMode === 'edit' ? selectedEvent : null}
          onClose={() => {
            setModalMode(null);
            setSelectedEvent(null);
          }}
          onSubmit={handleSubmitForm}
        />
      )}
    </div>
  );
}
