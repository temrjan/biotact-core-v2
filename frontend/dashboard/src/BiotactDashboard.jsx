import React, { useState, useRef, useEffect, useCallback, createContext, useContext } from 'react';
import {
  LayoutGrid, Wallet, TrendingUp, Users, Package,
  Settings, Bell, Send, Sparkles, ArrowUpRight,
  ArrowDownRight, ChevronLeft, ChevronRight,
  Server, Megaphone, Briefcase, ShoppingCart, Coffee,
  Moon, Sun, Monitor, Check, AlertCircle, LogOut, Loader2,
  Headphones, Bot, Save, Upload, RotateCcw, RefreshCw, Copy, FileText,
  FolderOpen, FolderPlus, Download, Trash2, Share2, Search, X, ChevronDown,
  Image as ImageIcon, Video, Music, Mic, Volume2
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts';
import * as api from './api';
import { useLocation, useNavigate } from 'react-router-dom';

/*
 * BIOTACT Core Dashboard v3.1
 * With Backend API Integration
 */

// ═══════════════════════════════════════════════════════════════
// THEME SYSTEM
// ═══════════════════════════════════════════════════════════════

const ThemeContext = createContext(null);

const themes = {
  light: {
    name: 'light',
    bg: {
      page: '#fafaf9',
      card: '#ffffff',
      elevated: '#f5f5f4',
      accent: '#499C75',
      accentHover: '#3d8a66',
      input: '#f5f5f4',
      userBubble: '#1c1917',
      aiBubble: '#f5f5f4',
    },
    border: {
      default: '#eeeceb',
      subtle: '#f7f7f6',
    },
    text: {
      primary: '#1c1917',
      secondary: '#57534e',
      muted: '#a8a29e',
      inverse: '#ffffff',
      accent: '#499C75',
      success: '#499C75',
      warning: '#d97706',
      error: '#dc2626',
    },
    chart: {
      grid: '#eeeceb',
      line1: '#499C75',
      line2: '#d6d3d1',
      gradient1: 'rgba(73, 156, 117, 0.12)',
    }
  },
  dark: {
    name: 'dark',
    bg: {
      page: '#0c0a09',
      card: '#1c1917',
      elevated: '#292524',
      accent: '#499C75',
      accentHover: '#5aad86',
      input: '#292524',
      userBubble: '#499C75',
      aiBubble: '#292524',
    },
    border: {
      default: '#353230',
      subtle: '#252220',
    },
    text: {
      primary: '#fafaf9',
      secondary: '#d6d3d1',
      muted: '#78716c',
      inverse: '#0c0a09',
      accent: '#499C75',
      success: '#5aad86',
      warning: '#fbbf24',
      error: '#f87171',
    },
    chart: {
      grid: '#353230',
      line1: '#499C75',
      line2: '#57534e',
      gradient1: 'rgba(73, 156, 117, 0.15)',
    }
  }
};

function ThemeProvider({ children }) {
  const [mode, setMode] = useState('system');
  const [resolved, setResolved] = useState('light');

  useEffect(() => {
    const saved = localStorage.getItem('biotact-theme');
    if (saved) setMode(saved);
  }, []);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => {
      const r = mode === 'system' ? (mq.matches ? 'dark' : 'light') : mode;
      setResolved(r);
    };
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, [mode]);

  const setTheme = (m) => {
    setMode(m);
    localStorage.setItem('biotact-theme', m);
  };

  return (
    <ThemeContext.Provider value={{ theme: themes[resolved], mode, setTheme, isDark: resolved === 'dark' }}>
      {children}
    </ThemeContext.Provider>
  );
}

const useTheme = () => useContext(ThemeContext);

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

const CATEGORIES = {
  hosting: { name: 'Серверы', icon: Server, color: '#2563eb' },
  marketing: { name: 'Маркетинг', icon: Megaphone, color: '#dc2626' },
  salary: { name: 'Команда', icon: Users, color: '#499C75' },
  inventory: { name: 'Закупки', icon: ShoppingCart, color: '#d97706' },
  office: { name: 'Офис', icon: Coffee, color: '#7c3aed' },
  logistics: { name: 'Логистика', icon: Package, color: '#0891b2' },
  other: { name: 'Прочее', icon: Wallet, color: '#6b7280' },
  sales: { name: 'Продажи', icon: TrendingUp, color: '#499C75' }
};

const fmt = (v, short = true) => {
  if (v === null || v === undefined) return '0';
  const num = typeof v === 'string' ? parseFloat(v) : v;
  if (short) {
    if (num >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (num >= 1e3) return `${(num / 1e3).toFixed(0)}K`;
  }
  return new Intl.NumberFormat('ru-RU').format(num);
};

// ═══════════════════════════════════════════════════════════════
// LOGIN FORM
// ═══════════════════════════════════════════════════════════════

function LoginForm({ onLogin, theme }) {
  const [email, setEmail] = useState('dashboard@biotact.uz');
  const [password, setPassword] = useState('dashboard123');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await api.login(email, password);
      onLogin();
    } catch (err) {
      setError(err.message || 'Ошибка входа');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: theme.bg.page }}>
      <div className="w-full max-w-sm p-8 rounded-2xl border" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl mx-auto mb-4 flex items-center justify-center" style={{ backgroundColor: theme.bg.accent }}>
            <span className="font-bold text-lg" style={{ color: theme.text.inverse }}>B</span>
          </div>
          <h1 className="text-xl font-semibold" style={{ color: theme.text.primary }}>BIOTACT Dashboard</h1>
          <p className="text-sm mt-1" style={{ color: theme.text.muted }}>Войдите в систему</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: theme.text.secondary }}>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-3 rounded-xl text-sm focus:outline-none focus:ring-2"
              style={{ backgroundColor: theme.bg.input, color: theme.text.primary, '--tw-ring-color': theme.bg.accent }}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: theme.text.secondary }}>Пароль</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 rounded-xl text-sm focus:outline-none focus:ring-2"
              style={{ backgroundColor: theme.bg.input, color: theme.text.primary, '--tw-ring-color': theme.bg.accent }}
              required
            />
          </div>

          {error && (
            <div className="text-sm p-3 rounded-lg" style={{ backgroundColor: `${theme.text.error}15`, color: theme.text.error }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl text-sm font-medium transition-all flex items-center justify-center gap-2"
            style={{ backgroundColor: theme.bg.accent, color: theme.text.inverse, opacity: loading ? 0.7 : 1 }}
          >
            {loading && <Loader2 size={16} className="animate-spin" />}
            {loading ? 'Вход...' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// THEME TOGGLE COMPONENT
// ═══════════════════════════════════════════════════════════════

function ThemeToggle() {
  const { mode, setTheme, theme } = useTheme();
  const [open, setOpen] = useState(false);
  const opts = [
    { v: 'light', icon: Sun, label: 'Светлая' },
    { v: 'dark', icon: Moon, label: 'Тёмная' },
    { v: 'system', icon: Monitor, label: 'Системная' },
  ];
  const cur = opts.find(o => o.v === mode) || opts[0];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="p-2 rounded-lg transition-all duration-200 hover:scale-105"
        style={{ color: theme.text.muted, backgroundColor: open ? theme.bg.elevated : 'transparent' }}
      >
        <cur.icon size={18} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 mt-2 w-44 rounded-xl z-50 border overflow-hidden shadow-2xl"
            style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
          >
            {opts.map(o => (
              <button
                key={o.v}
                onClick={() => { setTheme(o.v); setOpen(false); }}
                className="w-full flex items-center gap-3 px-4 py-3 text-sm transition-colors"
                style={{
                  color: mode === o.v ? theme.text.accent : theme.text.secondary,
                  backgroundColor: mode === o.v ? theme.bg.elevated : 'transparent'
                }}
              >
                <o.icon size={16} />
                <span className="flex-1 text-left">{o.label}</span>
                {mode === o.v && <Check size={14} />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// MAIN DASHBOARD
// ═══════════════════════════════════════════════════════════════

function Dashboard({ onLogout }) {
  const { theme, isDark } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const section = location.pathname === "/" ? "dashboard" : location.pathname.slice(1);
  const setSection = (s) => navigate(s === "dashboard" ? "/" : "/" + s);
  const [sidebar, setSidebar] = useState(true);

  // Chat state
  const [msgs, setMsgs] = useState([
    { id: '0', role: 'ai', text: 'Здравствуйте! Напишите команду — например: «Расход 15 млн на серверы»', ts: new Date() }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  // Data from API
  const [kpi, setKpi] = useState({ revenue: 0, expenses: 0, profit: 0, profit_margin: 0 });
  const [txs, setTxs] = useState([]);
  const [dataLoading, setDataLoading] = useState(true);

  const chartData = [
    { month: 'Авг', income: 120, expenses: 78 },
    { month: 'Сен', income: 135, expenses: 82 },
    { month: 'Окт', income: 148, expenses: 85 },
    { month: 'Ноя', income: 142, expenses: 88 },
    { month: 'Дек', income: 165, expenses: 92 },
    { month: 'Янв', income: 158, expenses: 83 },
  ];

  // Load data from API
  const loadData = useCallback(async () => {
    setDataLoading(true);
    try {
      const [kpiData, txsData] = await Promise.all([
        api.getKPI(),
        api.getTransactions({ limit: 50 })
      ]);
      setKpi(kpiData);
      setTxs(txsData.map(tx => ({
        ...tx,
        date: new Date(tx.transaction_date || tx.created_at)
      })));
    } catch (err) {
      console.error('Failed to load data:', err);
      if (err.message === 'Unauthorized') {
        onLogout();
      }
    } finally {
      setDataLoading(false);
    }
  }, [onLogout]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const totalExp = parseFloat(kpi.expenses) || 0;
  const totalInc = parseFloat(kpi.revenue) || 0;
  const profit = parseFloat(kpi.profit) || 0;
  const margin = kpi.profit_margin?.toFixed(1) || '0.0';

  const breakdown = Object.entries(CATEGORIES)
    .map(([k, c]) => ({
      key: k, name: c.name, color: c.color, icon: c.icon,
      amount: txs.filter(t => t.type === 'expense' && t.category === k).reduce((s, t) => s + parseFloat(t.amount || 0), 0)
    }))
    .filter(i => i.amount > 0)
    .sort((a, b) => b.amount - a.amount);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);

  const send = useCallback(async () => {
    if (!input.trim() || loading) return;
    const userMsg = { id: Date.now().toString(), role: 'user', text: input.trim(), ts: new Date() };
    setMsgs(p => [...p, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const response = await api.sendChatMessage(userMsg.text, sessionId);

      // Save session ID for conversation continuity
      if (response.session_id) {
        setSessionId(response.session_id);
      }

      const aiMsg = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        text: response.answer,
        ts: new Date(),
        status: response.action_result?.success ? 'success' : undefined
      };

      setMsgs(prev => [...prev, aiMsg]);

      // If action was successful, reload data
      if (response.action_result?.success) {
        await loadData();
      }
    } catch (err) {
      const errorMsg = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        text: `Ошибка: ${err.message}`,
        ts: new Date(),
        status: 'warning'
      };
      setMsgs(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, sessionId, loadData]);

  const nav = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutGrid },
    { id: 'askbiotact', label: 'AskBiotact', icon: Bot },
    { id: 'marketing', label: 'Marketing', icon: Megaphone },
    { id: 'documents', label: 'Документы', icon: FolderOpen },
    { id: 'hr', label: 'HR', icon: Briefcase },
    { id: 'media', label: 'Медиа', icon: ImageIcon },
  ];

  // AskBiotact state
  const [prompt, setPrompt] = useState('Загрузка...');
  const [savedPrompt, setSavedPrompt] = useState('');
  const [promptLoading, setPromptLoading] = useState(true);
  const [botRestarting, setBotRestarting] = useState(false);
  const [askMsgs, setAskMsgs] = useState([
    { id: '0', role: 'ai', text: 'Здравствуйте! 💚 Я консультант Biotact. Чем могу помочь?', ts: new Date() }
  ]);
  const [askInput, setAskInput] = useState('');
  const [askLoading, setAskLoading] = useState(false);

  // Media — Image / Video / Audio (today: audio only)
  const [mediaTab, setMediaTab] = useState('audio'); // 'image' | 'video' | 'audio'
  const [audioMode, setAudioMode] = useState('stt'); // 'stt' | 'tts'
  const [sttFile, setSttFile] = useState(null);
  const [sttFileUrl, setSttFileUrl] = useState(null);
  const [sttText, setSttText] = useState('');
  const [sttLoading, setSttLoading] = useState(false);
  const [sttError, setSttError] = useState('');
  const [sttCopied, setSttCopied] = useState(false);
  const [ttsText, setTtsText] = useState('');
  const [ttsVoice, setTtsVoice] = useState('nova');
  const [ttsLoading, setTtsLoading] = useState(false);
  const [ttsError, setTtsError] = useState('');
  const [ttsAudioUrl, setTtsAudioUrl] = useState(null);
  const [mediaDragOver, setMediaDragOver] = useState(false);
  const sttFileInputRef = useRef(null);
  const ttsFileInputRef = useRef(null);
  // STT history
  const [sttHistory, setSttHistory] = useState([]);
  const [sttHistoryTotal, setSttHistoryTotal] = useState(0);
  const [sttHistoryPage, setSttHistoryPage] = useState(1);
  const [sttHistoryPages, setSttHistoryPages] = useState(0);
  const [sttHistoryLoading, setSttHistoryLoading] = useState(false);
  const [sttHistoryError, setSttHistoryError] = useState('');
  const [sttSelectedId, setSttSelectedId] = useState(null);
  const SST_PAGE_SIZE = 20;

  // Marketing — Content Generator
  const [mktTab, setMktTab] = useState('generate'); // 'generate' | 'history'
  const [mktProduct, setMktProduct] = useState('');
  const [mktContext, setMktContext] = useState('');
  const [mktVariants, setMktVariants] = useState([]);
  const [mktLoading, setMktLoading] = useState(false);
  const [mktError, setMktError] = useState(null);
  const [mktModel, setMktModel] = useState('');
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [mktHistory, setMktHistory] = useState([]);
  const [mktHistoryLoading, setMktHistoryLoading] = useState(false);
  const [mktHistoryFilter, setMktHistoryFilter] = useState('');
  const [mktExpandedId, setMktExpandedId] = useState(null);

  // Marketing Chat
  const [mktChatMsgs, setMktChatMsgs] = useState([
    { id: 1, role: 'assistant', text: 'Привет! Я помогу с контентом. Спросите что угодно: найти пост, сгенерировать новый, показать статистику.' },
  ]);
  const [mktChatInput, setMktChatInput] = useState('');
  const [mktChatLoading, setMktChatLoading] = useState(false);
  const mktChatEndRef = useRef(null);
  const mktChatInputRef = useRef(null);

  // ═══════════════════════════════════════════════════════════════
  // Documents module state
  // ═══════════════════════════════════════════════════════════════
  const [docFolders, setDocFolders] = useState([]);
  const [docFiles, setDocFiles] = useState([]);
  const [docCurrentFolder, setDocCurrentFolder] = useState(null); // folder_id or null (root)
  const [docBreadcrumbs, setDocBreadcrumbs] = useState([{ folder_id: null, name: 'Все документы' }]);
  const [docStats, setDocStats] = useState({ total_files: 0, total_folders: 0, total_size: 0, indexed_files: 0 });
  const [docUploading, setDocUploading] = useState(false);
  const [docDragOver, setDocDragOver] = useState(false);
  const [docShowNewFolder, setDocShowNewFolder] = useState(false);
  const [docNewFolderName, setDocNewFolderName] = useState('');
  const [docLoading, setDocLoading] = useState(false);
  const [docUploadMsg, setDocUploadMsg] = useState(null);
  const docFileInputRef = useRef(null);

  // Documents Chat
  const [docChatMsgs, setDocChatMsgs] = useState([
    { id: '0', role: 'ai', text: 'Здравствуйте! Я могу искать информацию по всем загруженным документам, сопоставлять данные и помогать с анализом. Спрашивайте!' },
  ]);
  const [docChatInput, setDocChatInput] = useState('');
  const [docChatLoading, setDocChatLoading] = useState(false);
  const docChatEndRef = useRef(null);
  const docChatInputRef = useRef(null);

  // ═══════════════════════════════════════════════════════════════
  // HR module state
  // ═══════════════════════════════════════════════════════════════
  const [hrTemplates, setHrTemplates] = useState([]);
  const [hrUploading, setHrUploading] = useState(false);
  const [hrDocResult, setHrDocResult] = useState(null); // generated document text
  const hrFileInputRef = useRef(null);

  // HR Document History
  const [hrDocHistory, setHrDocHistory] = useState([]);
  const [hrDocHistoryTotal, setHrDocHistoryTotal] = useState(0);
  const [hrDocHistoryPage, setHrDocHistoryPage] = useState(1);
  const [hrDocHistoryLoading, setHrDocHistoryLoading] = useState(false);
  const [hrActiveTab, setHrActiveTab] = useState('library'); // 'library' | 'history'

  // HR Chat
  const [hrChatMsgs, setHrChatMsgs] = useState([
    { id: 1, role: 'assistant', text: 'Здравствуйте! Я HR-ассистент. Напишите какой документ нужно создать — я найду образец и заполню данными.' },
  ]);
  const [hrChatInput, setHrChatInput] = useState('');
  const [hrChatLoading, setHrChatLoading] = useState(false);
  const hrChatEndRef = useRef(null);
  const hrChatInputRef = useRef(null);

  // Load documents data
  const loadDocuments = useCallback(async () => {
    setDocLoading(true);
    try {
      const [folders, files, stats] = await Promise.all([
        api.listFolders(docCurrentFolder),
        api.listFiles(docCurrentFolder),
        api.getFileStats(),
      ]);
      setDocFolders(folders);
      setDocFiles(files);
      setDocStats(stats);

      // Update breadcrumbs
      if (docCurrentFolder) {
        const crumbs = await api.getBreadcrumbs(docCurrentFolder);
        setDocBreadcrumbs(crumbs);
      } else {
        setDocBreadcrumbs([{ folder_id: null, name: 'Все документы' }]);
      }
    } catch (err) {
      console.error('Failed to load documents:', err);
    } finally {
      setDocLoading(false);
    }
  }, [docCurrentFolder]);

  useEffect(() => {
    if (section === 'documents') loadDocuments();
  }, [section, docCurrentFolder, loadDocuments]);

  const navigateToFolder = useCallback((folderId) => {
    setDocCurrentFolder(folderId);
  }, []);

  const handleCreateFolder = useCallback(async () => {
    if (!docNewFolderName.trim()) return;
    try {
      await api.createFolder(docNewFolderName.trim(), docCurrentFolder);
      setDocNewFolderName('');
      setDocShowNewFolder(false);
      await loadDocuments();
    } catch (err) {
      console.error('Failed to create folder:', err);
    }
  }, [docNewFolderName, docCurrentFolder, loadDocuments]);

  const handleUploadFiles = useCallback(async (fileList) => {
    if (!fileList || fileList.length === 0) return;
    setDocUploading(true);
    try {
      let uploaded = 0;
      for (const file of fileList) {
        await api.uploadFile(file, docCurrentFolder);
        uploaded++;
      }
      // Force reload current folder contents
      const [folders, files, stats] = await Promise.all([
        api.listFolders(docCurrentFolder),
        api.listFiles(docCurrentFolder),
        api.getFileStats(),
      ]);
      setDocFolders(folders);
      setDocFiles(files);
      setDocStats(stats);
      setDocUploadMsg({ type: 'success', text: `Загружено: ${uploaded} файл(ов)` });
      setTimeout(() => setDocUploadMsg(null), 4000);
    } catch (err) {
      console.error('Upload failed:', err);
      setDocUploadMsg({ type: 'error', text: 'Ошибка загрузки файла' });
      setTimeout(() => setDocUploadMsg(null), 4000);
    } finally {
      setDocUploading(false);
    }
  }, [docCurrentFolder]);

  const handleDeleteFile = useCallback(async (fileId) => {
    if (!confirm('Удалить файл?')) return;
    try {
      await api.deleteFile(fileId);
      await loadDocuments();
    } catch (err) {
      console.error('Delete failed:', err);
      alert('Ошибка удаления файла. Удалять может только создатель.');
    }
  }, [loadDocuments]);

  const handleDeleteFolder = useCallback(async (folderId) => {
    if (!confirm('Удалить папку и всё содержимое?')) return;
    try {
      await api.deleteFolder(folderId);
      await loadDocuments();
    } catch (err) {
      console.error('Delete folder failed:', err);
      alert('Ошибка удаления папки. Удалять может только создатель.');
    }
  }, [loadDocuments]);

  const sendDocChat = useCallback(async () => {
    if (!docChatInput.trim() || docChatLoading) return;
    const msg = docChatInput.trim();
    setDocChatInput('');
    setDocChatMsgs(prev => [...prev, { id: Date.now(), role: 'user', text: msg }]);
    setDocChatLoading(true);
    try {
      const history = docChatMsgs.filter(m => m.role !== 'ai' || m.id !== '0').map(m => ({
        role: m.role === 'ai' ? 'assistant' : m.role,
        content: m.text,
      }));
      const data = await api.filesChat(msg, history.length > 0 ? history : null);
      const sources = data.sources && data.sources.length > 0
        ? '\n\n' + data.sources.map(s => `📄 ${s.file_name}`).join('\n')
        : '';
      setDocChatMsgs(prev => [...prev, { id: Date.now() + 1, role: 'ai', text: data.answer + sources }]);
    } catch (err) {
      setDocChatMsgs(prev => [...prev, { id: Date.now() + 1, role: 'ai', text: `Ошибка: ${err.message}`, status: 'warning' }]);
    } finally {
      setDocChatLoading(false);
    }
  }, [docChatInput, docChatLoading, docChatMsgs]);

  // ── Media: Audio handlers ──────────────────────────────────────
  const acceptSttFile = useCallback((file) => {
    if (!file) return;
    setSttError('');
    setSttText('');
    setSttCopied(false);
    if (sttFileUrl) URL.revokeObjectURL(sttFileUrl);
    setSttFile(file);
    setSttFileUrl(URL.createObjectURL(file));
  }, [sttFileUrl]);

  const loadTranscriptions = useCallback(async (page = 1) => {
    setSttHistoryLoading(true);
    setSttHistoryError('');
    try {
      const data = await api.listTranscriptions({
        limit: SST_PAGE_SIZE,
        offset: (page - 1) * SST_PAGE_SIZE,
      });
      setSttHistory(data.items || []);
      setSttHistoryTotal(data.total || 0);
      setSttHistoryPage(data.page || page);
      setSttHistoryPages(data.pages || 0);
    } catch (err) {
      setSttHistoryError(err.message || 'Не удалось загрузить историю');
    } finally {
      setSttHistoryLoading(false);
    }
  }, []);

  const handleTranscribe = useCallback(async () => {
    if (!sttFile || sttLoading) return;
    setSttLoading(true);
    setSttError('');
    setSttText('');
    setSttCopied(false);
    try {
      const data = await api.transcribeAudio(sttFile);
      setSttText(data.text || '');
      setSttSelectedId(data.transcription_id || null);
      await loadTranscriptions(1);
    } catch (err) {
      setSttError(err.message || 'Не удалось транскрибировать');
    } finally {
      setSttLoading(false);
    }
  }, [sttFile, sttLoading, loadTranscriptions]);

  const handleSelectTranscription = useCallback(async (transcriptionId) => {
    setSttError('');
    setSttCopied(false);
    try {
      const data = await api.getTranscription(transcriptionId);
      setSttText(data.text || '');
      setSttSelectedId(data.transcription_id);
      if (sttFileUrl) URL.revokeObjectURL(sttFileUrl);
      setSttFileUrl(null);
      setSttFile(null);
    } catch (err) {
      setSttError(err.message || 'Не удалось загрузить транскрипт');
    }
  }, [sttFileUrl]);

  const handleDeleteTranscription = useCallback(async (transcriptionId) => {
    if (!window.confirm('Удалить эту запись? Отмена невозможна.')) return;
    try {
      await api.deleteTranscription(transcriptionId);
      if (sttSelectedId === transcriptionId) {
        setSttSelectedId(null);
        setSttText('');
      }
      await loadTranscriptions(sttHistoryPage);
    } catch (err) {
      setSttHistoryError(err.message || 'Не удалось удалить');
    }
  }, [sttSelectedId, sttHistoryPage, loadTranscriptions]);

  const handleCopyTranscript = useCallback(async () => {
    if (!sttText) return;
    await navigator.clipboard.writeText(sttText);
    setSttCopied(true);
    setTimeout(() => setSttCopied(false), 2000);
  }, [sttText]);

  const handleDownloadTranscript = useCallback(() => {
    if (!sttText) return;
    const blob = new Blob([sttText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const baseName = (sttFile?.name || 'transcript').replace(/\.[^.]+$/, '');
    a.href = url;
    a.download = `${baseName}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }, [sttText, sttFile]);

  const handleLoadTxtForTts = useCallback(async (file) => {
    if (!file) return;
    setTtsError('');
    try {
      const text = await file.text();
      if (text.length > 4096) {
        setTtsError('Файл больше 4096 символов — обрежьте текст');
      }
      setTtsText(text.slice(0, 4096));
    } catch (err) {
      setTtsError(err.message || 'Не удалось прочитать файл');
    }
  }, []);

  const handleSynthesize = useCallback(async () => {
    const text = ttsText.trim();
    if (!text || ttsLoading) return;
    setTtsLoading(true);
    setTtsError('');
    if (ttsAudioUrl) URL.revokeObjectURL(ttsAudioUrl);
    setTtsAudioUrl(null);
    try {
      const blob = await api.synthesizeAudio(text, ttsVoice);
      setTtsAudioUrl(URL.createObjectURL(blob));
    } catch (err) {
      setTtsError(err.message || 'Не удалось синтезировать');
    } finally {
      setTtsLoading(false);
    }
  }, [ttsText, ttsVoice, ttsLoading, ttsAudioUrl]);

  const handleDownloadTtsAudio = useCallback(() => {
    if (!ttsAudioUrl) return;
    const a = document.createElement('a');
    a.href = ttsAudioUrl;
    a.download = 'speech.mp3';
    a.click();
  }, [ttsAudioUrl]);

  const handleGenerate = useCallback(async () => {
    if (!mktProduct.trim()) return;
    setMktLoading(true);
    setMktError(null);
    setMktVariants([]);
    setCopiedIdx(null);
    try {
      const data = await api.generateContent(mktProduct.trim(), mktContext.trim() || null);
      if (data.error) {
        setMktError(data.error);
      } else {
        setMktVariants(data.variants);
        setMktModel(data.model_used);
      }
    } catch (e) {
      setMktError(e.message || 'Error');
    } finally {
      setMktLoading(false);
    }
  }, [mktProduct, mktContext]);

  const handleCopy = useCallback(async (text, idx) => {
    await navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  }, []);

  const loadHistory = useCallback(async () => {
    setMktHistoryLoading(true);
    try {
      const data = await api.getContentHistory({
        product: mktHistoryFilter || undefined,
      });
      setMktHistory(data);
    } catch (e) {
      console.error('Failed to load history:', e);
    } finally {
      setMktHistoryLoading(false);
    }
  }, [mktHistoryFilter]);

  // Load history when switching to history tab
  useEffect(() => {
    if (section === 'marketing' && mktTab === 'history') {
      loadHistory();
    }
  }, [section, mktTab, loadHistory]);

  // Reload history after generation
  const handleGenerateAndSave = useCallback(async () => {
    await handleGenerate();
    if (mktTab === 'history') loadHistory();
  }, [handleGenerate, mktTab, loadHistory]);

  const sendMktChat = useCallback(async () => {
    const text = mktChatInput.trim();
    if (!text || mktChatLoading) return;
    setMktChatInput('');
    const userMsg = { id: Date.now(), role: 'user', text };
    setMktChatMsgs(prev => [...prev, userMsg]);
    setMktChatLoading(true);

    try {
      const chatHistory = mktChatMsgs.filter(m => m.role !== 'system').map(m => ({ role: m.role, content: m.text }));
      const data = await api.marketingChat(text, chatHistory.length > 1 ? chatHistory.slice(-10) : null);

      const aiMsg = { id: Date.now() + 1, role: 'assistant', text: data.message };
      setMktChatMsgs(prev => [...prev, aiMsg]);

      // Apply action to central area
      if (data.action) {
        if (data.action.type === 'filter_history') {
          setMktTab('history');
          if (data.action.params?.product) setMktHistoryFilter(data.action.params.product);
          loadHistory();
        } else if (data.action.type === 'show_generation') {
          setMktTab('generate');
          if (data.action.data?.variants) {
            setMktVariants(data.action.data.variants.map(v => ({
              text: v.text, is_blocked: false, stop_words_found: [], warnings: v.warnings || [], replacements_made: [],
            })));
            setMktModel(data.action.data.model_used || '');
          }
        }
      }
    } catch (e) {
      setMktChatMsgs(prev => [...prev, { id: Date.now() + 1, role: 'assistant', text: 'Ошибка: ' + (e.message || 'попробуйте позже') }]);
    } finally {
      setMktChatLoading(false);
    }
  }, [mktChatInput, mktChatLoading, mktChatMsgs, loadHistory]);

  // ═══════════════════════════════════════════════════════════════
  // HR module handlers
  // ═══════════════════════════════════════════════════════════════

  const loadHrTemplates = useCallback(async () => {
    try {
      const data = await api.hrListTemplates();
      setHrTemplates(data.items || []);
    } catch (e) {
      console.error('Failed to load HR templates:', e);
    }
  }, []);

  useEffect(() => {
    if (section === 'hr') loadHrTemplates();
  }, [section, loadHrTemplates]);

  useEffect(() => {
    if (section === 'media' && mediaTab === 'audio' && audioMode === 'stt') {
      loadTranscriptions(1);
    }
  }, [section, mediaTab, audioMode, loadTranscriptions]);

  const [hrUploadMsg, setHrUploadMsg] = useState(null); // {type: 'success'|'error', text}
  const [hrSelectedCategory, setHrSelectedCategory] = useState('td_osnovnoy');

  const handleHrUpload = useCallback(async (files) => {
    if (!files || files.length === 0) return;
    setHrUploading(true);
    setHrUploadMsg(null);
    try {
      for (const file of files) {
        await api.hrUploadTemplate(file, hrSelectedCategory);
      }
      await loadHrTemplates();
      setHrUploadMsg({ type: 'success', text: `Загружено: ${files.length} файл(ов) в категорию "${hrSelectedCategory}"` });
      setTimeout(() => setHrUploadMsg(null), 5000);
    } catch (e) {
      setHrUploadMsg({ type: 'error', text: 'Ошибка загрузки: ' + (e.message || 'попробуйте позже') });
    } finally {
      setHrUploading(false);
      if (hrFileInputRef.current) hrFileInputRef.current.value = '';
    }
  }, [loadHrTemplates, hrSelectedCategory]);

  const handleHrDeleteTemplate = useCallback(async (id) => {
    if (!confirm('Удалить образец?')) return;
    try {
      await api.hrDeleteTemplate(id);
      await loadHrTemplates();
    } catch (e) {
      console.error('HR delete failed:', e);
    }
  }, [loadHrTemplates]);

  // HR Document History
  const loadHrDocHistory = useCallback(async (page = 1) => {
    setHrDocHistoryLoading(true);
    try {
      const data = await api.hrListDocuments(page);
      setHrDocHistory(data.items || []);
      setHrDocHistoryTotal(data.total || 0);
      setHrDocHistoryPage(page);
    } catch (e) {
      console.error('Failed to load HR doc history:', e);
    } finally {
      setHrDocHistoryLoading(false);
    }
  }, []);

  const handleHrDeleteDocument = useCallback(async (id) => {
    if (!confirm('Удалить документ? Файл будет удалён безвозвратно.')) return;
    try {
      await api.hrDeleteDocument(id);
      await loadHrDocHistory(hrDocHistoryPage);
    } catch (e) {
      console.error('HR doc delete failed:', e);
    }
  }, [loadHrDocHistory, hrDocHistoryPage]);

  useEffect(() => {
    if (section === 'hr') loadHrDocHistory();
  }, [section, loadHrDocHistory]);

  const sendHrChat = useCallback(async () => {
    const text = hrChatInput.trim();
    if (!text || hrChatLoading) return;
    setHrChatInput('');
    const userMsg = { id: Date.now(), role: 'user', text };
    setHrChatMsgs(prev => [...prev, userMsg]);
    setHrChatLoading(true);
    setHrDocResult(null);

    try {
      const chatHistory = hrChatMsgs.filter(m => m.role !== 'system').map(m => ({ role: m.role, content: m.text }));
      const data = await api.hrChat(text, chatHistory.length > 1 ? chatHistory.slice(-10) : null);

      const aiMsg = { id: Date.now() + 1, role: 'assistant', text: data.message };
      setHrChatMsgs(prev => [...prev, aiMsg]);

      if (data.document_url) {
        setHrDocResult(data.document_url);
        loadHrDocHistory();
      }
    } catch (e) {
      setHrChatMsgs(prev => [...prev, { id: Date.now() + 1, role: 'assistant', text: 'Ошибка: ' + (e.message || 'попробуйте позже') }]);
    } finally {
      setHrChatLoading(false);
    }
  }, [hrChatInput, hrChatLoading, hrChatMsgs]);

  const askEndRef = useRef(null);
  const askInputRef = useRef(null);

  // Load prompt from server
  useEffect(() => {
    const loadPrompt = async () => {
      try {
        const data = await api.getPrompt('askbiotact');
        setPrompt(data.content);
        setSavedPrompt(data.content);
      } catch (err) {
        console.error('Failed to load prompt:', err);
        setPrompt('// Ошибка загрузки промпта');
      } finally {
        setPromptLoading(false);
      }
    };
    loadPrompt();
  }, []);

  const handleSavePrompt = async () => {
    try {
      await api.updatePrompt('askbiotact', prompt);
      setSavedPrompt(prompt);
    } catch (err) {
      console.error('Failed to save prompt:', err);
    }
  };

  const handleResetPrompt = () => {
    setPrompt(savedPrompt);
  };
const handleRestartBot = async () => {    setBotRestarting(true);    try {      await api.restartBot();      alert("Бот перезапущен!");    } catch (err) {      console.error("Failed to restart bot:", err);      alert("Ошибка перезапуска бота: " + err.message);    } finally {      setBotRestarting(false);    }  };

  const handleCopyPrompt = () => {
    navigator.clipboard.writeText(prompt);
  };

  useEffect(() => {
    askEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [askMsgs]);

  const sendAskMessage = useCallback(async () => {
    if (!askInput.trim() || askLoading) return;
    const userMsg = { id: Date.now().toString(), role: 'user', text: askInput.trim(), ts: new Date() };
    setAskMsgs(p => [...p, userMsg]);
    setAskInput('');
    setAskLoading(true);

    // Simulate AI response (TODO: integrate with backend)
    setTimeout(() => {
      const aiMsg = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        text: 'Понимаю вашу заботу! 💚 Расскажите подробнее — для кого ищете продукт и какие симптомы беспокоят?',
        ts: new Date()
      };
      setAskMsgs(prev => [...prev, aiMsg]);
      setAskLoading(false);
    }, 1500);
  }, [askInput, askLoading]);

  if (dataLoading) {
    return (
      <div className="h-screen flex items-center justify-center" style={{ backgroundColor: theme.bg.page }}>
        <div className="text-center">
          <Loader2 size={32} className="animate-spin mx-auto mb-4" style={{ color: theme.bg.accent }} />
          <p style={{ color: theme.text.muted }}>Загрузка данных...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex transition-colors duration-300" style={{ backgroundColor: theme.bg.page, fontFamily: "'DM Sans', system-ui, sans-serif" }}>

      {/* ══════════ SIDEBAR ══════════ */}
      <aside
        className="flex flex-col border-r transition-all duration-300"
        style={{ width: sidebar ? 224 : 64, backgroundColor: theme.bg.card, borderColor: theme.border.default }}
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b" style={{ borderColor: theme.border.subtle }}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: theme.bg.accent }}>
              <span className="font-bold text-sm" style={{ color: theme.text.inverse }}>B</span>
            </div>
            {sidebar && (
              <div className="overflow-hidden">
                <div className="text-sm font-semibold" style={{ color: theme.text.primary }}>BIOTACT</div>
                <div className="text-[10px] uppercase tracking-widest" style={{ color: theme.text.muted }}>Core</div>
              </div>
            )}
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-2">
          {nav.map(item => {
            const active = section === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setSection(item.id)}
                className="w-full flex items-center gap-3 px-3 py-2.5 mb-1 rounded-lg transition-all duration-200"
                style={{
                  backgroundColor: active ? 'rgba(73, 156, 117, 0.1)' : 'transparent',
                  color: active ? theme.text.accent : theme.text.secondary
                }}
              >
                <item.icon size={18} strokeWidth={active ? 2 : 1.5} />
                {sidebar && <span className="text-sm font-medium">{item.label}</span>}
              </button>
            );
          })}
        </nav>

        {/* Toggle */}
        <div className="p-3 border-t" style={{ borderColor: theme.border.subtle }}>
          <button
            onClick={() => setSidebar(!sidebar)}
            className="w-full flex items-center justify-center p-2 rounded-lg transition-colors"
            style={{ color: theme.text.muted }}
          >
            {sidebar ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
          </button>
        </div>

        {/* Logout */}
        <div className="p-3 border-t" style={{ borderColor: theme.border.subtle }}>
          <button
            onClick={onLogout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-red-500/10"
            style={{ color: theme.text.muted }}
          >
            <LogOut size={18} strokeWidth={1.5} />
            {sidebar && <span className="text-sm">Выйти</span>}
          </button>
        </div>
      </aside>

      {/* ══════════ MAIN CONTENT ══════════ */}
      <main className="flex-1 overflow-auto">
        {/* Header */}
        <header
          className="sticky top-0 z-20 backdrop-blur-sm border-b"
          style={{ backgroundColor: isDark ? 'rgba(12,10,9,0.9)' : 'rgba(250,250,249,0.9)', borderColor: theme.border.default }}
        >
          <div className="h-16 px-8 flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold" style={{ color: theme.text.primary }}>
                {section === 'dashboard' && 'Главная панель'}
                {section === 'askbiotact' && 'AskBiotact'}
                {section === 'marketing' && 'Маркетинг'}
                {section === 'documents' && 'Документы'}
                {section === 'hr' && 'HR / Кадры'}
                {section === 'media' && 'Медиа'}
              </h1>
              <p className="text-xs" style={{ color: theme.text.muted }}>
                {section === 'askbiotact' ? 'AI Консультант' : section === 'marketing' ? 'Генератор контента' : section === 'documents' ? 'Общая площадка обмена документами' : section === 'media' ? 'Изображения, видео и аудио' : new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={loadData}
                className="p-2 rounded-lg transition-colors"
                style={{ color: theme.text.muted }}
                title="Обновить данные"
              >
                <Loader2 size={18} strokeWidth={1.5} className={dataLoading ? 'animate-spin' : ''} />
              </button>
              <ThemeToggle />
              <button
                className="relative p-2 rounded-lg transition-colors"
                style={{ color: theme.text.muted }}
              >
                <Bell size={18} strokeWidth={1.5} />
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-red-500 rounded-full" />
              </button>
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium"
                style={{ backgroundColor: theme.bg.elevated, color: theme.text.secondary }}
              >
                АД
              </div>
            </div>
          </div>
        </header>

        {/* Dashboard Grid */}
        {section === 'dashboard' && (
        <div className="p-8 max-w-6xl">
          {/* KPIs */}
          <div className="grid grid-cols-3 gap-6 mb-8">
            {/* Revenue */}
            <div
              className="rounded-xl p-6 border transition-shadow duration-300 hover:shadow-lg"
              style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
            >
              <div className="flex items-start justify-between mb-4">
                <span className="text-xs font-medium uppercase tracking-wider" style={{ color: theme.text.muted }}>Выручка</span>
                <span className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full" style={{ backgroundColor: isDark ? 'rgba(16,185,129,0.15)' : 'rgba(5,150,105,0.1)', color: theme.text.success }}>
                  <ArrowUpRight size={12} />12%
                </span>
              </div>
              <div className="text-3xl font-semibold tracking-tight" style={{ color: theme.text.primary }}>{fmt(totalInc)}</div>
              <div className="text-xs mt-1" style={{ color: theme.text.muted }}>сум / месяц</div>
            </div>

            {/* Expenses */}
            <div
              className="rounded-xl p-6 border transition-shadow duration-300 hover:shadow-lg"
              style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
            >
              <div className="flex items-start justify-between mb-4">
                <span className="text-xs font-medium uppercase tracking-wider" style={{ color: theme.text.muted }}>Расходы</span>
                <span className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full" style={{ backgroundColor: isDark ? 'rgba(251,191,36,0.15)' : 'rgba(217,119,6,0.1)', color: theme.text.warning }}>
                  <ArrowUpRight size={12} />8%
                </span>
              </div>
              <div className="text-3xl font-semibold tracking-tight" style={{ color: theme.text.primary }}>{fmt(totalExp)}</div>
              <div className="text-xs mt-1" style={{ color: theme.text.muted }}>сум / месяц</div>
            </div>

            {/* Profit */}
            <div
              className="rounded-xl p-6 transition-all duration-300 hover:scale-[1.02]"
              style={{ backgroundColor: theme.bg.accent }}
            >
              <div className="flex items-start justify-between mb-4">
                <span className="text-xs font-medium uppercase tracking-wider" style={{ color: isDark ? 'rgba(0,0,0,0.5)' : 'rgba(255,255,255,0.7)' }}>Прибыль</span>
                <span className="text-xs font-medium px-2 py-0.5 rounded-full" style={{ backgroundColor: 'rgba(255,255,255,0.2)', color: theme.text.inverse }}>{margin}%</span>
              </div>
              <div className="text-3xl font-semibold tracking-tight" style={{ color: theme.text.inverse }}>{fmt(profit)}</div>
              <div className="text-xs mt-1" style={{ color: isDark ? 'rgba(0,0,0,0.4)' : 'rgba(255,255,255,0.6)' }}>чистая / месяц</div>
            </div>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-5 gap-6 mb-8">
            {/* Area Chart */}
            <div
              className="col-span-3 rounded-xl p-6 border"
              style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-sm font-semibold" style={{ color: theme.text.primary }}>Динамика за 6 месяцев</h2>
                <div className="flex items-center gap-4 text-xs">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: theme.chart.line1 }} />
                    <span style={{ color: theme.text.muted }}>Доходы</span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: theme.chart.line2 }} />
                    <span style={{ color: theme.text.muted }}>Расходы</span>
                  </span>
                </div>
              </div>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="incGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={theme.chart.line1} stopOpacity={0.15} />
                        <stop offset="100%" stopColor={theme.chart.line1} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.chart.grid} vertical={false} />
                    <XAxis dataKey="month" stroke={theme.text.muted} fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke={theme.text.muted} fontSize={11} tickLine={false} axisLine={false} tickFormatter={v => `${v}M`} />
                    <Tooltip
                      contentStyle={{ backgroundColor: theme.bg.card, border: `1px solid ${theme.border.default}`, borderRadius: 8, fontSize: 12 }}
                      labelStyle={{ color: theme.text.primary }}
                      formatter={(v) => [`${v} млн сум`]}
                    />
                    <Area type="monotone" dataKey="income" stroke={theme.chart.line1} strokeWidth={2} fill="url(#incGrad)" />
                    <Area type="monotone" dataKey="expenses" stroke={theme.chart.line2} strokeWidth={2} fill="transparent" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Breakdown */}
            <div
              className="col-span-2 rounded-xl p-6 border"
              style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
            >
              <h2 className="text-sm font-semibold mb-6" style={{ color: theme.text.primary }}>Структура расходов</h2>
              <div className="space-y-4">
                {breakdown.length === 0 ? (
                  <p className="text-sm" style={{ color: theme.text.muted }}>Нет данных о расходах</p>
                ) : breakdown.map(item => {
                  const pct = totalExp > 0 ? (item.amount / totalExp * 100).toFixed(0) : 0;
                  const Icon = item.icon;
                  return (
                    <div key={item.key} className="group">
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          <div
                            className="w-7 h-7 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110"
                            style={{ backgroundColor: `${item.color}15` }}
                          >
                            <Icon size={14} style={{ color: item.color }} />
                          </div>
                          <span className="text-sm" style={{ color: theme.text.secondary }}>{item.name}</span>
                        </div>
                        <span className="text-sm font-medium" style={{ color: theme.text.primary }}>{fmt(item.amount)}</span>
                      </div>
                      <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: theme.bg.elevated }}>
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{ width: `${pct}%`, backgroundColor: item.color }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Transactions */}
          <div className="rounded-xl border overflow-hidden" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
            <div className="px-6 py-4 border-b flex items-center justify-between" style={{ borderColor: theme.border.subtle }}>
              <h2 className="text-sm font-semibold" style={{ color: theme.text.primary }}>Последние операции</h2>
              <button className="text-xs transition-colors" style={{ color: theme.text.muted }}>Все операции →</button>
            </div>
            <div>
              {txs.length === 0 ? (
                <div className="px-6 py-8 text-center">
                  <p className="text-sm" style={{ color: theme.text.muted }}>Нет операций. Добавьте через чат!</p>
                </div>
              ) : txs.slice(0, 5).map((tx, i) => {
                const cat = CATEGORIES[tx.category];
                const Icon = cat?.icon || Wallet;
                return (
                  <div
                    key={tx.id || tx.transaction_id}
                    className="px-6 py-4 flex items-center justify-between transition-colors"
                    style={{ borderTop: i > 0 ? `1px solid ${theme.border.subtle}` : 'none' }}
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${cat?.color || '#6b7280'}10` }}>
                        <Icon size={18} style={{ color: cat?.color || '#6b7280' }} />
                      </div>
                      <div>
                        <div className="text-sm font-medium" style={{ color: theme.text.primary }}>{cat?.name || 'Прочее'}</div>
                        <div className="text-xs" style={{ color: theme.text.muted }}>
                          {tx.date?.toLocaleDateString?.('ru-RU', { day: 'numeric', month: 'short' }) || tx.transaction_date}
                          {tx.period === 'yearly' && ' • Годовой'}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold" style={{ color: tx.type === 'expense' ? theme.text.primary : theme.text.success }}>
                      {tx.type === 'expense' ? '−' : '+'}{fmt(tx.amount, false)} <span style={{ color: theme.text.muted, fontWeight: 400 }}>сум</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        )}

        {/* AskBiotact Section */}
        {section === 'askbiotact' && (
        <div className="flex-1 flex flex-col p-6 overflow-hidden">
          {/* Prompt Editor */}
          <div className="flex-1 flex flex-col rounded-xl border overflow-hidden" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
            {/* Prompt Header */}
            <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: theme.border.subtle }}>
              <div className="flex items-center gap-2">
                <FileText size={16} style={{ color: theme.text.muted }} />
                <span className="text-sm font-medium" style={{ color: theme.text.primary }}>System Prompt</span>
                {prompt !== savedPrompt && (
                  <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: theme.text.warning + '20', color: theme.text.warning }}>
                    Изменено
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleCopyPrompt}
                  className="p-2 rounded-lg transition-colors hover:opacity-80"
                  style={{ color: theme.text.muted }}
                  title="Копировать"
                >
                  <Copy size={16} />
                </button>
                <button
                  onClick={handleResetPrompt}
                  className="p-2 rounded-lg transition-colors hover:opacity-80"
                  style={{ color: theme.text.muted }}
                  title="Сбросить"
                  disabled={prompt === savedPrompt}
                >
                  <RotateCcw size={16} />
                </button>
                <button
                  onClick={handleSavePrompt}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                  style={{
                    backgroundColor: prompt !== savedPrompt ? theme.bg.accent : theme.bg.elevated,
                    color: prompt !== savedPrompt ? theme.text.inverse : theme.text.muted
                  }}
                  disabled={prompt === savedPrompt}
                >
                  <Save size={14} />
                  Сохранить
                </button>
                <button
                  onClick={handleRestartBot}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                  style={{
                    backgroundColor: theme.bg.elevated,
                    color: theme.text.warning
                  }}
                  disabled={botRestarting}
                >
                  <RefreshCw size={14} className={botRestarting ? "animate-spin" : ""} />
                  {botRestarting ? "Перезапуск..." : "Перезапустить бота"}
                </button>
              </div>
            </div>

            {/* Prompt Textarea */}
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="flex-1 p-4 text-sm focus:outline-none font-mono"
              style={{
                backgroundColor: theme.bg.card,
                color: theme.text.primary,
                lineHeight: 1.7,
                minHeight: '400px',
                resize: 'vertical'
              }}
              placeholder="Введите системный промпт..."
            />

            {/* Prompt Footer */}
            <div className="px-4 py-3 border-t flex items-center justify-between" style={{ borderColor: theme.border.subtle }}>
              <div className="flex items-center gap-4 text-xs" style={{ color: theme.text.muted }}>
                <span>{prompt.length} символов</span>
                <span>{prompt.split('\n').length} строк</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
                  style={{ backgroundColor: theme.bg.elevated, color: theme.text.secondary }}
                >
                  <Upload size={14} />
                  Загрузить
                </button>
              </div>
            </div>
          </div>
        </div>
        )}

        {/* Marketing — Content Generator + History */}
        {section === 'marketing' && (
        <div className="flex-1 overflow-auto p-8">
          <div className="max-w-3xl mx-auto space-y-6">
            {/* Tabs */}
            <div className="flex gap-1 p-1 rounded-xl" style={{ backgroundColor: theme.bg.elevated }}>
              {[
                { id: 'generate', label: 'Генератор', icon: Sparkles },
                { id: 'history', label: 'История', icon: FileText },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setMktTab(tab.id)}
                  className="flex-1 py-2.5 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all"
                  style={{
                    backgroundColor: mktTab === tab.id ? theme.bg.card : 'transparent',
                    color: mktTab === tab.id ? theme.text.primary : theme.text.muted,
                    boxShadow: mktTab === tab.id ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                  }}
                >
                  <tab.icon size={14} /> {tab.label}
                </button>
              ))}
            </div>

            {/* ── Generate Tab ── */}
            {mktTab === 'generate' && (<>
            <div className="rounded-2xl p-6 border" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: theme.text.primary }}>Продукт</label>
                  <input
                    type="text"
                    value={mktProduct}
                    onChange={e => setMktProduct(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !mktLoading && handleGenerate()}
                    placeholder="Иммунокомплекс, Бифолак Нео, Кальций Триактив Д3..."
                    className="w-full px-4 py-3 rounded-xl text-sm border outline-none transition-colors"
                    style={{ backgroundColor: theme.bg.elevated, borderColor: theme.border.default, color: theme.text.primary }}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2" style={{ color: theme.text.muted }}>
                    Контекст <span className="font-normal">(опционально)</span>
                  </label>
                  <input
                    type="text"
                    value={mktContext}
                    onChange={e => setMktContext(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !mktLoading && handleGenerate()}
                    placeholder="для мам, осень, тренд — иммунитет детей"
                    className="w-full px-4 py-3 rounded-xl text-sm border outline-none transition-colors"
                    style={{ backgroundColor: theme.bg.elevated, borderColor: theme.border.default, color: theme.text.primary }}
                  />
                </div>
                <button
                  onClick={handleGenerate}
                  disabled={mktLoading || !mktProduct.trim()}
                  className="w-full py-3 rounded-xl text-sm font-medium transition-all flex items-center justify-center gap-2"
                  style={{
                    backgroundColor: mktLoading || !mktProduct.trim() ? theme.bg.elevated : theme.bg.accent,
                    color: mktLoading || !mktProduct.trim() ? theme.text.muted : '#fff',
                    cursor: mktLoading || !mktProduct.trim() ? 'not-allowed' : 'pointer',
                  }}
                >
                  {mktLoading ? <><Loader2 size={16} className="animate-spin" /> Генерирую...</> : <><Sparkles size={16} /> Сгенерировать посты</>}
                </button>
              </div>
            </div>

            {mktError && (
              <div className="rounded-xl p-4 flex items-center gap-3" style={{ backgroundColor: theme.bg.elevated }}>
                <AlertCircle size={18} style={{ color: '#ef4444' }} />
                <span className="text-sm" style={{ color: '#ef4444' }}>{mktError}</span>
              </div>
            )}

            {mktVariants.map((v, idx) => (
              <div key={idx} className="rounded-2xl p-6 border space-y-4" style={{ backgroundColor: theme.bg.card, borderColor: v.is_blocked ? '#ef4444' : theme.border.default }}>
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold" style={{ color: theme.text.primary }}>Вариант {idx + 1}</h3>
                  <button
                    onClick={() => handleCopy(v.text, idx)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors"
                    style={{ backgroundColor: theme.bg.elevated, color: copiedIdx === idx ? theme.text.success : theme.text.muted }}
                  >
                    {copiedIdx === idx ? <><Check size={12} /> Скопировано</> : <><Copy size={12} /> Копировать</>}
                  </button>
                </div>
                <div className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: theme.text.secondary }}>{v.text}</div>
                {v.is_blocked && (
                  <div className="rounded-lg p-3 text-xs flex items-center gap-2" style={{ backgroundColor: '#fef2f2', color: '#ef4444' }}>
                    <AlertCircle size={14} /> Заблокировано: {v.stop_words_found.join(', ')}
                  </div>
                )}
                {v.warnings.length > 0 && (
                  <div className="rounded-lg p-3 text-xs" style={{ backgroundColor: theme.bg.elevated, color: theme.text.muted }}>
                    Проверьте: {v.warnings.join(', ')}
                  </div>
                )}
                {v.replacements_made.length > 0 && (
                  <div className="rounded-lg p-3 text-xs" style={{ backgroundColor: theme.bg.elevated, color: theme.text.muted }}>
                    Автозамены: {v.replacements_made.join(', ')}
                  </div>
                )}
              </div>
            ))}

            {mktVariants.length > 0 && (
              <div className="flex gap-3">
                <button onClick={handleGenerate} disabled={mktLoading}
                  className="flex-1 py-3 rounded-xl text-sm font-medium flex items-center justify-center gap-2 border transition-colors"
                  style={{ borderColor: theme.border.default, color: theme.text.primary, backgroundColor: theme.bg.card }}>
                  <RefreshCw size={14} /> Переделать
                </button>
              </div>
            )}

            {mktModel && mktVariants.length > 0 && (
              <p className="text-center text-xs" style={{ color: theme.text.muted }}>Модель: {mktModel}</p>
            )}
            </>)}

            {/* ── History Tab ── */}
            {mktTab === 'history' && (<>
            {/* Filter */}
            <div className="flex gap-3">
              <input
                type="text"
                value={mktHistoryFilter}
                onChange={e => setMktHistoryFilter(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && loadHistory()}
                placeholder="Фильтр по продукту..."
                className="flex-1 px-4 py-2.5 rounded-xl text-sm border outline-none"
                style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default, color: theme.text.primary }}
              />
              <button onClick={loadHistory} className="px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 border"
                style={{ borderColor: theme.border.default, color: theme.text.primary, backgroundColor: theme.bg.card }}>
                {mktHistoryLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Обновить
              </button>
            </div>

            {/* History List */}
            {mktHistory.length === 0 && !mktHistoryLoading && (
              <div className="text-center py-12">
                <FileText size={32} style={{ color: theme.text.muted }} className="mx-auto mb-3" />
                <p className="text-sm" style={{ color: theme.text.muted }}>История пуста</p>
              </div>
            )}

            {mktHistory.map(item => (
              <div key={item.id} className="rounded-2xl border overflow-hidden" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
                {/* Header — always visible */}
                <button
                  onClick={() => setMktExpandedId(mktExpandedId === item.id ? null : item.id)}
                  className="w-full px-5 py-4 flex items-center justify-between text-left"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold" style={{ color: theme.text.primary }}>{item.product}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full" style={{
                        backgroundColor: item.channel === 'telegram' ? '#e0f2fe' : theme.bg.elevated,
                        color: item.channel === 'telegram' ? '#0284c7' : theme.text.muted,
                      }}>{item.channel}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-xs" style={{ color: theme.text.muted }}>
                        {new Date(item.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </span>
                      {item.context && <span className="text-xs" style={{ color: theme.text.muted }}>{item.context}</span>}
                    </div>
                  </div>
                  <ChevronRight size={16} style={{ color: theme.text.muted, transform: mktExpandedId === item.id ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s' }} />
                </button>

                {/* Expanded content */}
                {mktExpandedId === item.id && (
                  <div className="px-5 pb-5 space-y-4 border-t" style={{ borderColor: theme.border.default }}>
                    <div className="pt-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium" style={{ color: theme.text.muted }}>Вариант 1</span>
                        <button onClick={() => handleCopy(item.variant_1, `h1-${item.id}`)}
                          className="text-xs flex items-center gap-1" style={{ color: theme.text.muted }}>
                          {copiedIdx === `h1-${item.id}` ? <><Check size={10} /> Скопировано</> : <><Copy size={10} /> Копировать</>}
                        </button>
                      </div>
                      <div className="text-sm leading-relaxed whitespace-pre-wrap p-3 rounded-lg" style={{ backgroundColor: theme.bg.elevated, color: theme.text.secondary }}>{item.variant_1}</div>
                    </div>
                    {item.variant_2 && (
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-medium" style={{ color: theme.text.muted }}>Вариант 2</span>
                          <button onClick={() => handleCopy(item.variant_2, `h2-${item.id}`)}
                            className="text-xs flex items-center gap-1" style={{ color: theme.text.muted }}>
                            {copiedIdx === `h2-${item.id}` ? <><Check size={10} /> Скопировано</> : <><Copy size={10} /> Копировать</>}
                          </button>
                        </div>
                        <div className="text-sm leading-relaxed whitespace-pre-wrap p-3 rounded-lg" style={{ backgroundColor: theme.bg.elevated, color: theme.text.secondary }}>{item.variant_2}</div>
                      </div>
                    )}
                    {item.model_used && <p className="text-xs" style={{ color: theme.text.muted }}>Модель: {item.model_used}</p>}
                  </div>
                )}
              </div>
            ))}
            </>)}
          </div>
        </div>
        )}

        {/* ══════════ DOCUMENTS ══════════ */}
        {section === 'documents' && (
        <div className="flex-1 overflow-y-auto">
          {/* Toolbar */}
          <div className="px-8 py-4 flex items-center gap-3 border-b" style={{ borderColor: theme.border.subtle }}>
            <button
              onClick={() => docFileInputRef.current?.click()}
              disabled={docUploading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-all hover:shadow-lg"
              style={{ backgroundColor: '#3584e4' }}
            >
              {docUploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
              {docUploading ? 'Загрузка...' : 'Загрузить'}
            </button>
            <input
              ref={docFileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.txt,.md,.csv,.json,.xlsx,.xls"
              className="hidden"
              onChange={(e) => handleUploadFiles(e.target.files)}
            />
            <button
              onClick={() => setDocShowNewFolder(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-all"
              style={{ borderColor: theme.border.default, color: theme.text.primary, backgroundColor: theme.bg.card }}
            >
              <FolderPlus size={15} /> Папка
            </button>

            {/* Back button + Breadcrumbs */}
            <div className="flex items-center gap-1 ml-4 text-sm">
              {docCurrentFolder && (
                <button
                  onClick={() => {
                    const parentCrumb = docBreadcrumbs.length >= 2 ? docBreadcrumbs[docBreadcrumbs.length - 2] : { folder_id: null };
                    navigateToFolder(parentCrumb.folder_id);
                  }}
                  className="p-1.5 rounded-md transition-colors mr-1"
                  style={{ color: theme.text.muted }}
                  title="Назад"
                >
                  <ChevronLeft size={16} />
                </button>
              )}
              {docBreadcrumbs.map((crumb, i) => (
                <React.Fragment key={crumb.folder_id || 'root'}>
                  {i > 0 && <span style={{ color: theme.text.muted }}>›</span>}
                  <button
                    onClick={() => navigateToFolder(crumb.folder_id)}
                    className="px-2 py-1 rounded-md transition-colors"
                    style={{
                      color: i === docBreadcrumbs.length - 1 ? theme.text.primary : theme.text.muted,
                      fontWeight: i === docBreadcrumbs.length - 1 ? 500 : 400,
                    }}
                  >
                    {crumb.name}
                  </button>
                </React.Fragment>
              ))}
            </div>

            {/* Stats */}
            <div className="ml-auto flex items-center gap-4 text-xs" style={{ color: theme.text.muted }}>
              <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: theme.text.accent }}></span> {docStats.indexed_files} проиндексировано</span>
              <span>{docStats.total_files} файлов • {(docStats.total_size / 1024 / 1024).toFixed(1)} MB</span>
            </div>
          </div>

          {/* Create folder modal */}
          {docShowNewFolder && (
            <form onSubmit={(e) => { e.preventDefault(); handleCreateFolder(); }} className="px-8 py-3 flex items-center gap-2 border-b" style={{ borderColor: theme.border.subtle, backgroundColor: theme.bg.elevated }}>
              <FolderPlus size={16} style={{ color: '#3584e4' }} />
              <input
                autoFocus
                value={docNewFolderName}
                onChange={(e) => setDocNewFolderName(e.target.value)}
                placeholder="Имя папки..."
                className="flex-1 px-3 py-1.5 rounded-lg text-sm border outline-none"
                style={{ borderColor: theme.border.default, backgroundColor: theme.bg.card, color: theme.text.primary }}
              />
              <button type="submit" className="px-3 py-1.5 rounded-lg text-sm font-medium text-white" style={{ backgroundColor: '#3584e4' }}>Создать</button>
              <button type="button" onClick={() => { setDocShowNewFolder(false); setDocNewFolderName(''); }} className="p-1.5 rounded-lg" style={{ color: theme.text.muted }}><X size={16} /></button>
            </form>
          )}

          {/* Upload notification */}
          {docUploadMsg && (
            <div className="mx-8 mt-2 rounded-xl p-3 flex items-center gap-2" style={{
              backgroundColor: docUploadMsg.type === 'success' ? 'rgba(73,156,117,0.1)' : 'rgba(239,68,68,0.1)',
            }}>
              {docUploadMsg.type === 'success' ? <Check size={16} style={{ color: theme.text.success }} /> : <AlertCircle size={16} style={{ color: '#ef4444' }} />}
              <span className="text-sm" style={{ color: docUploadMsg.type === 'success' ? theme.text.success : '#ef4444' }}>{docUploadMsg.text}</span>
            </div>
          )}

          {/* Drag & drop overlay */}
          <div
            className="relative px-8 py-6"
            onDragOver={(e) => { e.preventDefault(); setDocDragOver(true); }}
            onDragLeave={() => setDocDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDocDragOver(false); handleUploadFiles(e.dataTransfer.files); }}
          >
            {docDragOver && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed" style={{ borderColor: '#3584e4', backgroundColor: 'rgba(53,132,228,0.06)' }}>
                <Upload size={40} style={{ color: '#3584e4', opacity: 0.5 }} />
                <span className="mt-2 text-sm font-medium" style={{ color: '#3584e4' }}>Перетащите файлы сюда</span>
              </div>
            )}

            {docLoading ? (
              <div className="flex items-center justify-center py-20"><Loader2 size={24} className="animate-spin" style={{ color: theme.text.muted }} /></div>
            ) : (
              <>
                {/* Folders */}
                {docFolders.length > 0 && (
                  <>
                    <div className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: theme.text.muted }}>Папки</div>
                    <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3 mb-8">
                      {docFolders.map(folder => (
                        <div
                          key={folder.folder_id}
                          onClick={() => navigateToFolder(folder.folder_id)}
                          className="group relative flex flex-col items-center p-4 rounded-2xl cursor-pointer transition-all hover:-translate-y-0.5"
                          style={{ ':hover': { backgroundColor: theme.bg.elevated } }}
                          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = theme.bg.elevated; e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.06)'; }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.boxShadow = 'none'; }}
                        >
                          {/* GNOME-style folder SVG */}
                          <svg width="56" height="46" viewBox="0 0 72 60" fill="none" style={{ filter: 'drop-shadow(0 4px 8px rgba(53,132,228,0.15))', marginBottom: 8 }}>
                            <rect x="4" y="4" width="64" height="52" rx="2" fill={isDark ? '#3584e4' : '#1c71d8'} />
                            <path d="M4 6C4 4.895 4.895 4 6 4H25.17c.53 0 1.04.21 1.41.59l2.83 2.83c.38.37.89.58 1.41.58H66c1.1 0 2 .9 2 2v2H4V6Z" fill={isDark ? '#3584e4' : '#1c71d8'} />
                            <rect x="2" y="14" width="68" height="42" rx="2" fill={isDark ? '#62a0ea' : '#3584e4'} />
                            <rect x="2" y="14" width="68" height="3" rx="1" fill="rgba(255,255,255,0.15)" />
                          </svg>
                          <div className="text-xs font-medium text-center truncate w-full" style={{ color: theme.text.primary }}>{folder.name}</div>
                          <div className="text-[10px] mt-0.5" style={{ color: theme.text.muted }}>{folder.file_count || 0} файлов</div>
                          {/* Delete button — only for owner */}
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDeleteFolder(folder.folder_id); }}
                            className="absolute top-2 right-2 p-1 rounded-md opacity-0 group-hover:opacity-100 transition-opacity"
                            style={{ color: theme.text.muted }}
                            title="Удалить"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {/* Files */}
                {docFiles.length > 0 && (
                  <>
                    <div className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: theme.text.muted }}>Файлы</div>
                    <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
                      {docFiles.map(file => {
                        const ext = file.name.split('.').pop()?.toLowerCase() || '';
                        const typeColors = { pdf: '#e74c3c', docx: '#3498db', doc: '#3498db', xlsx: '#27ae60', xls: '#27ae60', txt: '#95a5a6', csv: '#f39c12', md: '#8e44ad', json: '#95a5a6' };
                        const bgColor = typeColors[ext] || '#95a5a6';
                        return (
                          <div
                            key={file.file_id}
                            className="group relative flex items-center gap-3 p-3.5 rounded-xl border transition-all hover:-translate-y-0.5"
                            style={{ borderColor: theme.border.default, backgroundColor: theme.bg.card }}
                            onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#3584e4'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(53,132,228,0.15)'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.borderColor = theme.border.default; e.currentTarget.style.boxShadow = 'none'; }}
                          >
                            {/* Type badge */}
                            <div className="w-9 h-9 rounded-lg flex items-center justify-center text-[10px] font-bold text-white flex-shrink-0" style={{ background: `linear-gradient(135deg, ${bgColor}, ${bgColor}dd)` }}>
                              {ext.toUpperCase().slice(0, 3)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium truncate" style={{ color: theme.text.primary }}>{file.name}</div>
                              <div className="flex items-center gap-2 mt-0.5 text-[11px]" style={{ color: theme.text.muted }}>
                                <span>{(file.size / 1024 / 1024).toFixed(1)} MB</span>
                                <span>•</span>
                                {file.is_indexed
                                  ? <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: 'rgba(73,156,117,0.1)', color: theme.text.accent }}>✓ indexed</span>
                                  : <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold animate-pulse" style={{ backgroundColor: 'rgba(53,132,228,0.1)', color: '#3584e4' }}>⏳ indexing</span>
                                }
                              </div>
                              <div className="text-[10px] mt-0.5" style={{ color: theme.text.muted }}>{file.uploaded_by_name}</div>
                            </div>
                            {/* Actions */}
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button onClick={() => api.downloadFile(file.file_id, file.original_name)} className="p-1.5 rounded-md transition-colors" style={{ color: theme.text.muted }} title="Скачать"><Download size={14} /></button>
                              <button onClick={() => handleDeleteFile(file.file_id)} className="p-1.5 rounded-md transition-colors hover:text-red-500" style={{ color: theme.text.muted }} title="Удалить"><Trash2 size={14} /></button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}

                {/* Empty state */}
                {docFolders.length === 0 && docFiles.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-20 text-center">
                    <FolderOpen size={48} strokeWidth={1} style={{ color: theme.text.muted, opacity: 0.3 }} />
                    <div className="text-sm font-medium mt-4" style={{ color: theme.text.secondary }}>Пока нет документов</div>
                    <div className="text-xs mt-1" style={{ color: theme.text.muted }}>Загрузите файлы или создайте папку</div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
        )}

        {/* ══════════ HR MODULE ══════════ */}
        {section === 'hr' && (
        <div className="flex-1 overflow-auto p-8">
          <div className="max-w-4xl mx-auto space-y-6">

            {/* Document ready for download */}
            {hrDocResult && (
              <div className="rounded-2xl p-6 border space-y-4" style={{ backgroundColor: theme.bg.card, borderColor: theme.bg.accent }}>
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: theme.text.success }}>
                    <Check size={16} /> Документ готов
                  </h3>
                  <button
                    onClick={() => api.hrDownloadRendered(hrDocResult)}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium text-white transition-all hover:shadow-lg"
                    style={{ backgroundColor: theme.bg.accent }}
                  >
                    <Download size={16} /> Скачать DOCX
                  </button>
                </div>
                <p className="text-sm" style={{ color: theme.text.muted }}>
                  Документ создан по шаблону с подставленными данными. Форматирование сохранено.
                </p>
              </div>
            )}

            {/* Upload notification */}
            {hrUploadMsg && (
              <div className="rounded-xl p-4 flex items-center gap-3" style={{
                backgroundColor: hrUploadMsg.type === 'success' ? 'rgba(73,156,117,0.1)' : 'rgba(239,68,68,0.1)',
              }}>
                {hrUploadMsg.type === 'success' ? <Check size={18} style={{ color: theme.text.success }} /> : <AlertCircle size={18} style={{ color: '#ef4444' }} />}
                <span className="text-sm" style={{ color: hrUploadMsg.type === 'success' ? theme.text.success : '#ef4444' }}>{hrUploadMsg.text}</span>
              </div>
            )}

            {/* Tabs: Библиотека / История */}
            <div className="flex gap-1 p-1 rounded-xl" style={{ backgroundColor: theme.bg.elevated }}>
              {[
                { id: 'library', label: 'Библиотека', count: hrTemplates.length },
                { id: 'history', label: 'История', count: hrDocHistoryTotal },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => { setHrActiveTab(tab.id); if (tab.id === 'history') loadHrDocHistory(); }}
                  className="flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-all"
                  style={{
                    backgroundColor: hrActiveTab === tab.id ? theme.bg.card : 'transparent',
                    color: hrActiveTab === tab.id ? theme.text.primary : theme.text.muted,
                    boxShadow: hrActiveTab === tab.id ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                  }}
                >
                  {tab.label} {tab.count > 0 && <span className="ml-1 opacity-60">({tab.count})</span>}
                </button>
              ))}
            </div>

            {/* Library — uploaded templates */}
            {hrActiveTab === 'library' && (
            <div className="rounded-2xl p-6 border" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold" style={{ color: theme.text.primary }}>Библиотека образцов</h3>
                <div className="flex items-center gap-2">
                  <select
                    value={hrSelectedCategory}
                    onChange={(e) => setHrSelectedCategory(e.target.value)}
                    className="px-3 py-2 rounded-lg text-sm border outline-none"
                    style={{ backgroundColor: theme.bg.elevated, borderColor: theme.border.default, color: theme.text.primary }}
                  >
                    <option value="td_osnovnoy">ТД (основное место)</option>
                    <option value="td_sovmestitelstvo">ТД (совместительство)</option>
                    <option value="гпд">ГПД</option>
                    <option value="приказ">Приказ</option>
                    <option value="должностная_инструкция">Должностная инструкция</option>
                    <option value="мат_ответственность">Мат. ответственность</option>
                    <option value="соглашение_конфиденциальности">NDA / Конфиденциальность</option>
                    <option value="соглашение_персданные">Обработка перс. данных</option>
                    <option value="соглашение_возмещение">Возмещение</option>
                    <option value="другое">Другое</option>
                  </select>
                  <button
                    onClick={() => hrFileInputRef.current?.click()}
                    disabled={hrUploading}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-all"
                    style={{ backgroundColor: theme.bg.accent }}
                  >
                    {hrUploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
                    {hrUploading ? 'Загрузка...' : 'Загрузить'}
                  </button>
                </div>
                <input
                  ref={hrFileInputRef}
                  type="file"
                  accept=".docx,.pdf,.txt,.md"
                  multiple
                  className="hidden"
                  onChange={(e) => handleHrUpload(e.target.files)}
                />
              </div>

              {hrTemplates.length === 0 ? (
                <div className="text-center py-8">
                  <Briefcase size={32} style={{ color: theme.text.muted }} className="mx-auto mb-3" />
                  <p className="text-sm" style={{ color: theme.text.muted }}>Загрузите образцы документов (DOCX, PDF, TXT, MD)</p>
                  <p className="text-xs mt-1" style={{ color: theme.text.muted }}>Выберите категорию, затем нажмите "Загрузить"</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {hrTemplates.map(t => (
                    <div key={t.id} className="flex items-center justify-between p-3 rounded-lg border transition-all" style={{ borderColor: theme.border.default }}>
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center text-[10px] font-bold text-white" style={{ backgroundColor: t.file_type === 'docx' ? '#3498db' : t.file_type === 'pdf' ? '#e74c3c' : '#95a5a6' }}>
                          {t.file_type.toUpperCase()}
                        </div>
                        <div>
                          <div className="text-sm font-medium" style={{ color: theme.text.primary }}>{t.name}</div>
                          <div className="text-xs" style={{ color: theme.text.muted }}>{t.category} · {(t.file_size / 1024).toFixed(0)} KB</div>
                        </div>
                      </div>
                      <button onClick={() => handleHrDeleteTemplate(t.id)} className="p-1.5 rounded-md transition-colors hover:text-red-500" style={{ color: theme.text.muted }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            )}

            {/* History — generated documents */}
            {hrActiveTab === 'history' && (
            <div className="rounded-2xl p-6 border" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
              <h3 className="text-sm font-semibold mb-4" style={{ color: theme.text.primary }}>Созданные документы</h3>

              {hrDocHistoryLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 size={24} className="animate-spin" style={{ color: theme.text.muted }} />
                </div>
              ) : hrDocHistory.length === 0 ? (
                <div className="text-center py-8">
                  <FileText size={32} style={{ color: theme.text.muted }} className="mx-auto mb-3" />
                  <p className="text-sm" style={{ color: theme.text.muted }}>Документы ещё не создавались</p>
                  <p className="text-xs mt-1" style={{ color: theme.text.muted }}>Напишите в чат запрос на создание документа</p>
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    {hrDocHistory.map(doc => (
                      <div key={doc.id} className="flex items-center justify-between p-3 rounded-lg border transition-all" style={{ borderColor: theme.border.default }}>
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-[10px] font-bold text-white" style={{ backgroundColor: '#3498db' }}>
                            DOCX
                          </div>
                          <div>
                            <div className="text-sm font-medium" style={{ color: theme.text.primary }}>{doc.employee_name}</div>
                            <div className="text-xs" style={{ color: theme.text.muted }}>
                              {doc.template_name} · {(doc.file_size / 1024).toFixed(0)} KB · {new Date(doc.created_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => api.hrDownloadRendered(`/api/v1/hr/documents/download/${doc.file_id}`)}
                            className="p-1.5 rounded-md transition-colors hover:text-blue-500"
                            style={{ color: theme.text.muted }}
                            title="Скачать"
                          >
                            <Download size={14} />
                          </button>
                          <button
                            onClick={() => handleHrDeleteDocument(doc.id)}
                            className="p-1.5 rounded-md transition-colors hover:text-red-500"
                            style={{ color: theme.text.muted }}
                            title="Удалить"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Pagination */}
                  {hrDocHistoryTotal > 20 && (
                    <div className="flex items-center justify-center gap-2 mt-4">
                      <button
                        onClick={() => loadHrDocHistory(hrDocHistoryPage - 1)}
                        disabled={hrDocHistoryPage <= 1}
                        className="px-3 py-1 rounded-md text-sm border transition-all disabled:opacity-30"
                        style={{ borderColor: theme.border.default, color: theme.text.primary }}
                      >
                        &larr;
                      </button>
                      <span className="text-sm" style={{ color: theme.text.muted }}>
                        {hrDocHistoryPage} / {Math.ceil(hrDocHistoryTotal / 20)}
                      </span>
                      <button
                        onClick={() => loadHrDocHistory(hrDocHistoryPage + 1)}
                        disabled={hrDocHistoryPage >= Math.ceil(hrDocHistoryTotal / 20)}
                        className="px-3 py-1 rounded-md text-sm border transition-all disabled:opacity-30"
                        style={{ borderColor: theme.border.default, color: theme.text.primary }}
                      >
                        &rarr;
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
            )}

          </div>
        </div>
        )}

        {section === 'media' && (
        <div className="flex-1 overflow-auto p-8">
          <div className="max-w-3xl mx-auto space-y-6">
            {/* Tabs: Image / Video / Audio */}
            <div className="flex gap-1 p-1 rounded-xl" style={{ backgroundColor: theme.bg.elevated }}>
              {[
                { id: 'image', label: 'Изображение', icon: ImageIcon },
                { id: 'video', label: 'Видео', icon: Video },
                { id: 'audio', label: 'Аудио', icon: Music },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setMediaTab(tab.id)}
                  className="flex-1 py-2.5 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all"
                  style={{
                    backgroundColor: mediaTab === tab.id ? theme.bg.card : 'transparent',
                    color: mediaTab === tab.id ? theme.text.primary : theme.text.muted,
                    boxShadow: mediaTab === tab.id ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                  }}
                >
                  <tab.icon size={14} /> {tab.label}
                </button>
              ))}
            </div>

            {/* ── Image / Video placeholders ── */}
            {(mediaTab === 'image' || mediaTab === 'video') && (
              <div className="rounded-2xl p-12 border text-center" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
                {mediaTab === 'image'
                  ? <ImageIcon size={40} className="mx-auto mb-3" style={{ color: theme.text.muted }} />
                  : <Video size={40} className="mx-auto mb-3" style={{ color: theme.text.muted }} />}
                <p className="text-sm font-medium" style={{ color: theme.text.primary }}>Скоро</p>
                <p className="text-xs mt-1" style={{ color: theme.text.muted }}>Раздел в разработке</p>
              </div>
            )}

            {/* ── Audio tab ── */}
            {mediaTab === 'audio' && (<>
              {/* Mode switch: STT / TTS */}
              <div className="flex gap-1 p-1 rounded-xl" style={{ backgroundColor: theme.bg.elevated }}>
                {[
                  { id: 'stt', label: 'Аудио → Текст', icon: Mic },
                  { id: 'tts', label: 'Текст → Аудио', icon: Volume2 },
                ].map(m => (
                  <button
                    key={m.id}
                    onClick={() => setAudioMode(m.id)}
                    className="flex-1 py-2.5 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all"
                    style={{
                      backgroundColor: audioMode === m.id ? theme.bg.card : 'transparent',
                      color: audioMode === m.id ? theme.text.primary : theme.text.muted,
                      boxShadow: audioMode === m.id ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                    }}
                  >
                    <m.icon size={14} /> {m.label}
                  </button>
                ))}
              </div>

              {/* ── STT: Audio → Text ── */}
              {audioMode === 'stt' && (<>
                <div className="rounded-2xl p-6 border space-y-4" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
                  <input
                    ref={sttFileInputRef}
                    type="file"
                    accept=".mp3,.m4a,.wav,.ogg,.oga,.webm,.mp4,.mpeg,.mpga,audio/*"
                    className="hidden"
                    onChange={e => acceptSttFile(e.target.files?.[0])}
                  />
                  <div
                    onClick={() => sttFileInputRef.current?.click()}
                    onDragOver={e => { e.preventDefault(); setMediaDragOver(true); }}
                    onDragLeave={() => setMediaDragOver(false)}
                    onDrop={e => { e.preventDefault(); setMediaDragOver(false); acceptSttFile(e.dataTransfer.files?.[0]); }}
                    className="rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors"
                    style={{
                      borderColor: mediaDragOver ? theme.text.accent : theme.border.default,
                      backgroundColor: mediaDragOver ? theme.bg.elevated : 'transparent',
                    }}
                  >
                    <Upload size={28} className="mx-auto mb-2" style={{ color: theme.text.muted }} />
                    <p className="text-sm font-medium" style={{ color: theme.text.primary }}>
                      {sttFile ? sttFile.name : 'Перетащите аудио или выберите файл'}
                    </p>
                    <p className="text-xs mt-1" style={{ color: theme.text.muted }}>
                      MP3 · M4A · WAV · OGG · WebM · до 300 МБ · длинные файлы режутся автоматически
                    </p>
                  </div>

                  {sttFileUrl && (
                    <audio controls src={sttFileUrl} className="w-full" />
                  )}

                  <button
                    onClick={handleTranscribe}
                    disabled={!sttFile || sttLoading}
                    className="w-full py-3 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all"
                    style={{
                      backgroundColor: !sttFile || sttLoading ? theme.bg.elevated : theme.bg.accent,
                      color: !sttFile || sttLoading ? theme.text.muted : '#fff',
                      cursor: !sttFile || sttLoading ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {sttLoading
                      ? <><Loader2 size={16} className="animate-spin" /> Транскрибирую...</>
                      : <><Mic size={16} /> Транскрибировать</>}
                  </button>

                  {sttLoading && sttFile && sttFile.size > 20_000_000 && (
                    <p className="text-xs text-center" style={{ color: theme.text.muted }}>
                      Длинная запись режется на куски и обрабатывается параллельно — это может занять несколько минут.
                    </p>
                  )}

                  {sttError && (
                    <div className="rounded-xl p-4 flex items-center gap-3" style={{ backgroundColor: theme.bg.elevated }}>
                      <AlertCircle size={18} style={{ color: '#ef4444' }} />
                      <span className="text-sm" style={{ color: '#ef4444' }}>{sttError}</span>
                    </div>
                  )}

                  {sttText && (
                    <div className="space-y-3">
                      <textarea
                        value={sttText}
                        onChange={e => setSttText(e.target.value)}
                        rows={10}
                        className="w-full px-4 py-3 rounded-xl text-sm border outline-none resize-y"
                        style={{ backgroundColor: theme.bg.elevated, borderColor: theme.border.default, color: theme.text.primary }}
                      />
                      <div className="flex gap-3">
                        <button
                          onClick={handleCopyTranscript}
                          className="flex-1 py-2.5 rounded-xl text-sm font-medium flex items-center justify-center gap-2 border transition-colors"
                          style={{ borderColor: theme.border.default, color: sttCopied ? theme.text.success : theme.text.primary, backgroundColor: theme.bg.card }}
                        >
                          {sttCopied ? <><Check size={14} /> Скопировано</> : <><Copy size={14} /> Копировать</>}
                        </button>
                        <button
                          onClick={handleDownloadTranscript}
                          className="flex-1 py-2.5 rounded-xl text-sm font-medium flex items-center justify-center gap-2 border transition-colors"
                          style={{ borderColor: theme.border.default, color: theme.text.primary, backgroundColor: theme.bg.card }}
                        >
                          <Download size={14} /> Скачать .txt
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* История транскрипций */}
                <div className="rounded-2xl p-6 border space-y-3" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold" style={{ color: theme.text.primary }}>
                      История
                      {sttHistoryTotal > 0 && <span className="font-normal ml-2" style={{ color: theme.text.muted }}>· {sttHistoryTotal}</span>}
                    </h3>
                    <button
                      onClick={() => loadTranscriptions(sttHistoryPage)}
                      disabled={sttHistoryLoading}
                      className="p-1.5 rounded-lg transition-colors"
                      style={{ color: theme.text.muted }}
                      title="Обновить"
                    >
                      <RefreshCw size={14} className={sttHistoryLoading ? 'animate-spin' : ''} />
                    </button>
                  </div>

                  {sttHistoryError && (
                    <div className="rounded-xl p-3 flex items-center gap-2 text-xs" style={{ backgroundColor: theme.bg.elevated, color: '#ef4444' }}>
                      <AlertCircle size={14} /> {sttHistoryError}
                    </div>
                  )}

                  {!sttHistoryLoading && sttHistory.length === 0 && !sttHistoryError && (
                    <p className="text-sm text-center py-6" style={{ color: theme.text.muted }}>
                      Пока нет записей. Транскрибируй первое аудио — оно появится здесь.
                    </p>
                  )}

                  {sttHistory.length > 0 && (
                    <div className="space-y-2">
                      {sttHistory.map(item => {
                        const isSelected = sttSelectedId === item.transcription_id;
                        const dateStr = new Date(item.created_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
                        return (
                          <div
                            key={item.transcription_id}
                            className="rounded-xl p-3 border cursor-pointer transition-colors"
                            style={{
                              backgroundColor: isSelected ? theme.bg.elevated : 'transparent',
                              borderColor: isSelected ? theme.text.accent : theme.border.default,
                            }}
                            onClick={() => handleSelectTranscription(item.transcription_id)}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 text-xs mb-1" style={{ color: theme.text.muted }}>
                                  <span>{dateStr}</span>
                                  <span>·</span>
                                  <span className="truncate">{item.uploaded_by_name || 'Без имени'}</span>
                                </div>
                                <div className="text-sm font-medium mb-1 truncate" style={{ color: theme.text.primary }}>
                                  {item.title}
                                </div>
                                <div className="text-xs line-clamp-2" style={{ color: theme.text.secondary }}>
                                  {item.preview}
                                </div>
                              </div>
                              {item.is_owner && (
                                <button
                                  onClick={e => { e.stopPropagation(); handleDeleteTranscription(item.transcription_id); }}
                                  className="p-1.5 rounded-lg transition-colors flex-shrink-0"
                                  style={{ color: theme.text.muted }}
                                  title="Удалить"
                                >
                                  <Trash2 size={14} />
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {sttHistoryPages > 1 && (
                    <div className="flex items-center justify-between pt-2">
                      <button
                        onClick={() => loadTranscriptions(sttHistoryPage - 1)}
                        disabled={sttHistoryPage <= 1 || sttHistoryLoading}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1 border transition-colors disabled:opacity-40"
                        style={{ borderColor: theme.border.default, color: theme.text.primary, backgroundColor: theme.bg.card }}
                      >
                        <ChevronLeft size={14} /> Назад
                      </button>
                      <span className="text-xs" style={{ color: theme.text.muted }}>
                        {sttHistoryPage} / {sttHistoryPages}
                      </span>
                      <button
                        onClick={() => loadTranscriptions(sttHistoryPage + 1)}
                        disabled={sttHistoryPage >= sttHistoryPages || sttHistoryLoading}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1 border transition-colors disabled:opacity-40"
                        style={{ borderColor: theme.border.default, color: theme.text.primary, backgroundColor: theme.bg.card }}
                      >
                        Вперёд <ChevronRight size={14} />
                      </button>
                    </div>
                  )}
                </div>
              </>)}

              {/* ── TTS: Text → Audio ── */}
              {audioMode === 'tts' && (
                <div className="rounded-2xl p-6 border space-y-4" style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}>
                  <input
                    ref={ttsFileInputRef}
                    type="file"
                    accept=".txt,text/plain"
                    className="hidden"
                    onChange={e => handleLoadTxtForTts(e.target.files?.[0])}
                  />
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium" style={{ color: theme.text.primary }}>
                      Текст <span className="font-normal" style={{ color: theme.text.muted }}>({ttsText.length} / 4096)</span>
                    </label>
                    <button
                      onClick={() => ttsFileInputRef.current?.click()}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 border transition-colors"
                      style={{ borderColor: theme.border.default, color: theme.text.muted, backgroundColor: theme.bg.card }}
                    >
                      <Upload size={12} /> Загрузить .txt
                    </button>
                  </div>

                  <textarea
                    value={ttsText}
                    onChange={e => setTtsText(e.target.value.slice(0, 4096))}
                    rows={8}
                    placeholder="Введите текст на русском..."
                    className="w-full px-4 py-3 rounded-xl text-sm border outline-none resize-y"
                    style={{ backgroundColor: theme.bg.elevated, borderColor: theme.border.default, color: theme.text.primary }}
                  />

                  <div>
                    <label className="block text-sm font-medium mb-2" style={{ color: theme.text.primary }}>Голос</label>
                    <select
                      value={ttsVoice}
                      onChange={e => setTtsVoice(e.target.value)}
                      className="w-full px-4 py-3 rounded-xl text-sm border outline-none"
                      style={{ backgroundColor: theme.bg.elevated, borderColor: theme.border.default, color: theme.text.primary }}
                    >
                      <option value="nova">Nova (женский, тёплый)</option>
                      <option value="shimmer">Shimmer (женский, мягкий)</option>
                      <option value="alloy">Alloy (нейтральный)</option>
                      <option value="echo">Echo (мужской)</option>
                      <option value="fable">Fable (мужской, британский)</option>
                      <option value="onyx">Onyx (мужской, глубокий)</option>
                    </select>
                  </div>

                  <button
                    onClick={handleSynthesize}
                    disabled={!ttsText.trim() || ttsLoading}
                    className="w-full py-3 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all"
                    style={{
                      backgroundColor: !ttsText.trim() || ttsLoading ? theme.bg.elevated : theme.bg.accent,
                      color: !ttsText.trim() || ttsLoading ? theme.text.muted : '#fff',
                      cursor: !ttsText.trim() || ttsLoading ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {ttsLoading
                      ? <><Loader2 size={16} className="animate-spin" /> Синтезирую...</>
                      : <><Volume2 size={16} /> Синтезировать</>}
                  </button>

                  {ttsError && (
                    <div className="rounded-xl p-4 flex items-center gap-3" style={{ backgroundColor: theme.bg.elevated }}>
                      <AlertCircle size={18} style={{ color: '#ef4444' }} />
                      <span className="text-sm" style={{ color: '#ef4444' }}>{ttsError}</span>
                    </div>
                  )}

                  {ttsAudioUrl && (
                    <div className="space-y-3">
                      <audio controls src={ttsAudioUrl} className="w-full" />
                      <button
                        onClick={handleDownloadTtsAudio}
                        className="w-full py-2.5 rounded-xl text-sm font-medium flex items-center justify-center gap-2 border transition-colors"
                        style={{ borderColor: theme.border.default, color: theme.text.primary, backgroundColor: theme.bg.card }}
                      >
                        <Download size={14} /> Скачать .mp3
                      </button>
                    </div>
                  )}
                </div>
              )}
            </>)}
          </div>
        </div>
        )}
      </main>

      {/* ══════════ CHAT SIDEBAR ══════════ */}
      {section !== 'media' && (
      <aside
        className="w-96 flex flex-col border-l"
        style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
      >
        {/* Header */}
        <div className="h-16 px-5 flex items-center gap-3 border-b" style={{ borderColor: theme.border.default }}>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ backgroundColor: section === 'documents' ? '#3584e4' : isDark ? theme.bg.accent : theme.text.primary }}>
            {section === 'askbiotact' ? <Bot size={16} style={{ color: theme.text.inverse }} /> : section === 'documents' ? <FileText size={16} style={{ color: '#fff' }} /> : <Sparkles size={16} style={{ color: theme.text.inverse }} />}
          </div>
          <div className="flex-1">
            <div className="text-sm font-semibold" style={{ color: theme.text.primary }}>
              {section === 'askbiotact' ? 'Тест консультанта' : section === 'marketing' ? 'Контент-ассистент' : section === 'documents' ? 'Документы AI' : section === 'hr' ? 'HR Ассистент' : 'AI Ассистент'}
            </div>
            <div className="text-[11px] flex items-center gap-1" style={{ color: theme.text.success }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: theme.text.success }} />
              {section === 'askbiotact' ? 'Промпт загружен' : section === 'marketing' ? 'Поиск + генерация' : section === 'documents' ? `${docStats.indexed_files} документов проиндексировано` : section === 'hr' ? `${hrTemplates.length} образцов загружено` : 'Подключён к API'}
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {(section === 'askbiotact' ? askMsgs : section === 'marketing' ? mktChatMsgs : section === 'documents' ? docChatMsgs : section === 'hr' ? hrChatMsgs : msgs).map(m => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className="max-w-[85%] px-4 py-3 text-sm leading-relaxed"
                style={{
                  backgroundColor: m.role === 'user' ? theme.bg.userBubble : theme.bg.aiBubble,
                  color: m.role === 'user' ? theme.text.inverse : theme.text.primary,
                  borderRadius: m.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px'
                }}
              >
                {m.status === 'success' && (
                  <div className="flex items-center gap-1.5 text-xs font-medium mb-2" style={{ color: theme.text.success }}>
                    <Check size={12} /><span>Готово</span>
                  </div>
                )}
                {m.status === 'warning' && (
                  <div className="flex items-center gap-1.5 text-xs font-medium mb-2" style={{ color: theme.text.warning }}>
                    <AlertCircle size={12} /><span>Внимание</span>
                  </div>
                )}
                <p className="whitespace-pre-line">{m.text}</p>
              </div>
            </div>
          ))}
          {(section === 'askbiotact' ? askLoading : section === 'marketing' ? mktChatLoading : section === 'documents' ? docChatLoading : section === 'hr' ? hrChatLoading : loading) && (
            <div className="flex justify-start">
              <div className="px-4 py-3 rounded-2xl" style={{ backgroundColor: theme.bg.aiBubble }}>
                <div className="flex items-center gap-1">
                  {[0, 150, 300].map(d => (
                    <span key={d} className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ backgroundColor: theme.text.muted, animationDelay: `${d}ms` }} />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={section === 'askbiotact' ? askEndRef : section === 'marketing' ? mktChatEndRef : section === 'documents' ? docChatEndRef : section === 'hr' ? hrChatEndRef : endRef} />
        </div>

        {/* Quick Actions */}
        <div className="px-4 py-3 border-t" style={{ borderColor: theme.border.subtle }}>
          <div className="flex gap-2 flex-wrap">
            {(section === 'askbiotact'
              ? ['У ребенка живот болит', 'После антибиотиков', 'Сколько стоит?']
              : section === 'marketing'
              ? ['Сгенерируй пост про Иммунокомплекс', 'Найди посты за эту неделю', 'Покажи статистику']
              : section === 'documents'
              ? ['Найди в документах...', 'Сравни два файла', 'Что нового загружено?']
              : section === 'hr'
              ? ['Составь трудовой договор', 'Приказ о приёме', 'Какие образцы есть?']
              : ['Расход 5 млн на маркетинг', 'Доход 10 млн', 'Покажи отчёт']
            ).map(a => (
              <button
                key={a}
                onClick={() => {
                  if (section === 'askbiotact') {
                    setAskInput(a);
                    askInputRef.current?.focus();
                  } else if (section === 'marketing') {
                    setMktChatInput(a);
                    mktChatInputRef.current?.focus();
                  } else if (section === 'documents') {
                    setDocChatInput(a);
                    docChatInputRef.current?.focus();
                  } else if (section === 'hr') {
                    setHrChatInput(a);
                    hrChatInputRef.current?.focus();
                  } else {
                    setInput(a);
                    inputRef.current?.focus();
                  }
                }}
                className="px-3 py-1.5 text-xs font-medium rounded-full transition-colors"
                style={{ backgroundColor: theme.bg.elevated, color: theme.text.secondary }}
              >
                {a.length > 18 ? a.slice(0, 18) + '...' : a}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="p-4 border-t" style={{ borderColor: theme.border.default }}>
          <div className="flex gap-2">
            <input
              ref={section === 'askbiotact' ? askInputRef : section === 'marketing' ? mktChatInputRef : section === 'documents' ? docChatInputRef : section === 'hr' ? hrChatInputRef : inputRef}
              type="text"
              value={section === 'askbiotact' ? askInput : section === 'marketing' ? mktChatInput : section === 'documents' ? docChatInput : section === 'hr' ? hrChatInput : input}
              onChange={e => section === 'askbiotact' ? setAskInput(e.target.value) : section === 'marketing' ? setMktChatInput(e.target.value) : section === 'documents' ? setDocChatInput(e.target.value) : section === 'hr' ? setHrChatInput(e.target.value) : setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (section === 'askbiotact' ? sendAskMessage() : section === 'marketing' ? sendMktChat() : section === 'documents' ? sendDocChat() : section === 'hr' ? sendHrChat() : send())}
              placeholder={section === 'askbiotact' ? 'Напишите как клиент...' : section === 'marketing' ? 'Спросите про контент...' : section === 'documents' ? 'Спросите о документах...' : section === 'hr' ? 'Какой документ создать?' : 'Напишите команду...'}
              disabled={section === 'askbiotact' ? askLoading : section === 'marketing' ? mktChatLoading : section === 'documents' ? docChatLoading : section === 'hr' ? hrChatLoading : loading}
              className="flex-1 border-0 rounded-xl px-4 py-3 text-sm transition-all focus:outline-none focus:ring-2"
              style={{
                backgroundColor: theme.bg.input,
                color: theme.text.primary,
                '--tw-ring-color': theme.bg.accent
              }}
            />
            <button
              onClick={section === 'askbiotact' ? sendAskMessage : section === 'marketing' ? sendMktChat : section === 'documents' ? sendDocChat : section === 'hr' ? sendHrChat : send}
              disabled={section === 'askbiotact' ? (!askInput.trim() || askLoading) : section === 'marketing' ? (!mktChatInput.trim() || mktChatLoading) : section === 'documents' ? (!docChatInput.trim() || docChatLoading) : section === 'hr' ? (!hrChatInput.trim() || hrChatLoading) : (!input.trim() || loading)}
              className="w-11 h-11 rounded-xl flex items-center justify-center transition-all disabled:opacity-40"
              style={{ backgroundColor: theme.bg.accent }}
            >
              <Send size={16} style={{ color: theme.text.inverse }} />
            </button>
          </div>
        </div>
      </aside>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// APP WRAPPER
// ═══════════════════════════════════════════════════════════════

export default function BiotactCoreDashboard() {
  const [isAuthenticated, setIsAuthenticated] = useState(api.isAuthenticated());

  const handleLogin = () => {
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    api.clearAuth();
    setIsAuthenticated(false);
  };

  return (
    <ThemeProvider>
      {isAuthenticated ? (
        <Dashboard onLogout={handleLogout} />
      ) : (
        <LoginFormWrapper onLogin={handleLogin} />
      )}
    </ThemeProvider>
  );
}

function LoginFormWrapper({ onLogin }) {
  const { theme } = useTheme();
  return <LoginForm onLogin={onLogin} theme={theme} />;
}
