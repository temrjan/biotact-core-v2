import React, { useState, useRef, useEffect, useCallback, createContext, useContext } from 'react';
import { 
  LayoutGrid, Wallet, TrendingUp, Users, Package, 
  Settings, Bell, Send, Sparkles, ArrowUpRight, 
  ArrowDownRight, ChevronLeft, ChevronRight,
  Server, Megaphone, Briefcase, ShoppingCart, Coffee,
  Moon, Sun, Monitor, Check, AlertCircle
} from 'lucide-react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer
} from 'recharts';

/* 
 * BIOTACT Core Dashboard v3.0
 * Light/Dark/System theme support
 * Editorial Swiss design language
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
      accent: '#059669',
      accentHover: '#047857',
      input: '#f5f5f4',
      userBubble: '#1c1917',
      aiBubble: '#f5f5f4',
    },
    border: {
      default: '#e7e5e4',
      subtle: '#f5f5f4',
    },
    text: {
      primary: '#1c1917',
      secondary: '#57534e',
      muted: '#a8a29e',
      inverse: '#ffffff',
      accent: '#059669',
      success: '#059669',
      warning: '#d97706',
    },
    chart: {
      grid: '#e7e5e4',
      line1: '#059669',
      line2: '#d6d3d1',
      gradient1: 'rgba(5, 150, 105, 0.12)',
    }
  },
  dark: {
    name: 'dark',
    bg: {
      page: '#0c0a09',
      card: '#1c1917',
      elevated: '#292524',
      accent: '#10b981',
      accentHover: '#34d399',
      input: '#292524',
      userBubble: '#10b981',
      aiBubble: '#292524',
    },
    border: {
      default: '#292524',
      subtle: '#1c1917',
    },
    text: {
      primary: '#fafaf9',
      secondary: '#d6d3d1',
      muted: '#78716c',
      inverse: '#0c0a09',
      accent: '#10b981',
      success: '#34d399',
      warning: '#fbbf24',
    },
    chart: {
      grid: '#292524',
      line1: '#10b981',
      line2: '#57534e',
      gradient1: 'rgba(16, 185, 129, 0.15)',
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
// AI COMMAND PARSER
// ═══════════════════════════════════════════════════════════════

const parseCommand = (text) => {
  const lower = text.toLowerCase();
  
  // Amount extraction
  let amount = null;
  const match = text.match(/(\d+(?:[.,]\d+)?)\s*(?:млн|миллион|тыс|тысяч)?/i);
  if (match) {
    amount = parseFloat(match[1].replace(',', '.'));
    if (/млн|миллион/i.test(lower)) amount *= 1e6;
    else if (/тыс|тысяч/i.test(lower)) amount *= 1e3;
    else if (amount < 1e4) amount *= 1e6;
  }

  // Operation type
  const isExpense = /добав|расход|потрат|оплат|списа/i.test(lower);
  const isIncome = /доход|получ|заработ|выручк|поступ/i.test(lower);
  const isReport = /отчет|статистик|покаж|итог|сводк/i.test(lower);

  // Category
  const cats = {
    hosting: ['хостинг', 'сервер', 'облак', 'aws'],
    marketing: ['маркетинг', 'реклам', 'smm', 'pr'],
    salary: ['зарплат', 'персонал', 'команд', 'сотрудник'],
    inventory: ['закуп', 'товар', 'продукц', 'склад'],
    office: ['офис', 'аренд', 'помещ'],
    logistics: ['доставк', 'логист', 'транспорт'],
  };
  let category = 'other';
  for (const [cat, kws] of Object.entries(cats)) {
    if (kws.some(k => lower.includes(k))) { category = cat; break; }
  }

  // Period
  let period = 'monthly';
  if (/год|annual/i.test(lower)) period = 'yearly';
  else if (/квартал/i.test(lower)) period = 'quarterly';

  if (isExpense && amount) return { type: 'expense', amount, category, period, ok: true };
  if (isIncome && amount) return { type: 'income', amount, category: 'sales', period, ok: true };
  if (isReport) return { type: 'report', ok: true };
  return { type: 'unknown', ok: false };
};

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

const CATEGORIES = {
  hosting: { name: 'Серверы', icon: Server, color: '#2563eb' },
  marketing: { name: 'Маркетинг', icon: Megaphone, color: '#dc2626' },
  salary: { name: 'Команда', icon: Users, color: '#059669' },
  inventory: { name: 'Закупки', icon: ShoppingCart, color: '#d97706' },
  office: { name: 'Офис', icon: Coffee, color: '#7c3aed' },
  logistics: { name: 'Логистика', icon: Package, color: '#0891b2' },
  other: { name: 'Прочее', icon: Wallet, color: '#6b7280' },
  sales: { name: 'Продажи', icon: TrendingUp, color: '#059669' }
};

const fmt = (v, short = true) => {
  if (short) {
    if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  }
  return new Intl.NumberFormat('ru-RU').format(v);
};

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

function Dashboard() {
  const { theme, isDark } = useTheme();
  const [section, setSection] = useState('overview');
  const [sidebar, setSidebar] = useState(true);
  
  // Chat state
  const [msgs, setMsgs] = useState([
    { id: '0', role: 'ai', text: 'Здравствуйте! Напишите команду — например: «Расход 15 млн на серверы»', ts: new Date() }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  // Data
  const [txs, setTxs] = useState([
    { id: '1', type: 'expense', category: 'marketing', amount: 8e6, period: 'monthly', date: new Date('2025-01-10') },
    { id: '2', type: 'expense', category: 'salary', amount: 25e6, period: 'monthly', date: new Date('2025-01-05') },
    { id: '3', type: 'expense', category: 'inventory', amount: 45e6, period: 'monthly', date: new Date('2025-01-03') },
    { id: '4', type: 'expense', category: 'office', amount: 5e6, period: 'monthly', date: new Date('2025-01-01') },
  ]);

  const chartData = [
    { month: 'Авг', income: 120, expenses: 78 },
    { month: 'Сен', income: 135, expenses: 82 },
    { month: 'Окт', income: 148, expenses: 85 },
    { month: 'Ноя', income: 142, expenses: 88 },
    { month: 'Дек', income: 165, expenses: 92 },
    { month: 'Янв', income: 158, expenses: 83 },
  ];

  const totalExp = txs.filter(t => t.type === 'expense').reduce((s, t) => s + (t.period === 'yearly' ? t.amount / 12 : t.amount), 0);
  const totalInc = 158e6;
  const profit = totalInc - totalExp;
  const margin = ((profit / totalInc) * 100).toFixed(1);

  const breakdown = Object.entries(CATEGORIES)
    .map(([k, c]) => ({
      key: k, name: c.name, color: c.color, icon: c.icon,
      amount: txs.filter(t => t.type === 'expense' && t.category === k).reduce((s, t) => s + t.amount, 0)
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

    await new Promise(r => setTimeout(r, 600 + Math.random() * 400));
    const p = parseCommand(userMsg.text);
    let res = { id: (Date.now() + 1).toString(), role: 'ai', ts: new Date() };

    if (p.type === 'expense' && p.ok) {
      setTxs(prev => [{ id: Date.now().toString(), type: 'expense', category: p.category, amount: p.amount, period: p.period, date: new Date() }, ...prev]);
      const cat = CATEGORIES[p.category];
      res.text = `Готово. ${cat.name}: ${fmt(p.amount, false)} сум${p.period === 'yearly' ? ' (год)' : ''}`;
      res.status = 'success';
    } else if (p.type === 'income' && p.ok) {
      res.text = `Доход: ${fmt(p.amount, false)} сум`;
      res.status = 'success';
    } else if (p.type === 'report') {
      res.text = `Январь 2026\n\nДоходы: ${fmt(totalInc, false)}\nРасходы: ${fmt(totalExp, false)}\nПрибыль: ${fmt(profit, false)} (${margin}%)`;
      res.status = 'info';
    } else {
      res.text = `Попробуйте:\n• Расход 5 млн на маркетинг\n• Доход 50 млн\n• Покажи отчёт`;
      res.status = 'warning';
    }

    setMsgs(prev => [...prev, res]);
    setLoading(false);
  }, [input, loading, totalExp, totalInc, profit, margin]);

  const nav = [
    { id: 'overview', label: 'Обзор', icon: LayoutGrid },
    { id: 'finance', label: 'Финансы', icon: Wallet },
    { id: 'analytics', label: 'Аналитика', icon: TrendingUp },
    { id: 'products', label: 'Продукты', icon: Package },
    { id: 'team', label: 'Команда', icon: Users },
  ];

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
                  backgroundColor: active ? theme.bg.accent : 'transparent',
                  color: active ? theme.text.inverse : theme.text.secondary
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

        {/* Settings */}
        <div className="p-3 border-t" style={{ borderColor: theme.border.subtle }}>
          <button 
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors"
            style={{ color: theme.text.muted }}
          >
            <Settings size={18} strokeWidth={1.5} />
            {sidebar && <span className="text-sm">Настройки</span>}
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
              <h1 className="text-lg font-semibold" style={{ color: theme.text.primary }}>Главная панель</h1>
              <p className="text-xs" style={{ color: theme.text.muted }}>
                {new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}
              </p>
            </div>
            <div className="flex items-center gap-2">
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
                {breakdown.map(item => {
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
              {txs.slice(0, 5).map((tx, i) => {
                const cat = CATEGORIES[tx.category];
                const Icon = cat?.icon || Wallet;
                return (
                  <div 
                    key={tx.id}
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
                          {tx.date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
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
      </main>

      {/* ══════════ CHAT SIDEBAR ══════════ */}
      <aside 
        className="w-96 flex flex-col border-l"
        style={{ backgroundColor: theme.bg.card, borderColor: theme.border.default }}
      >
        {/* Header */}
        <div className="h-16 px-5 flex items-center gap-3 border-b" style={{ borderColor: theme.border.default }}>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ backgroundColor: isDark ? theme.bg.accent : theme.text.primary }}>
            <Sparkles size={16} style={{ color: theme.text.inverse }} />
          </div>
          <div className="flex-1">
            <div className="text-sm font-semibold" style={{ color: theme.text.primary }}>Ассистент</div>
            <div className="text-[11px] flex items-center gap-1" style={{ color: theme.text.success }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: theme.text.success }} />
              Готов
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {msgs.map(m => (
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
                    <AlertCircle size={12} /><span>Подсказка</span>
                  </div>
                )}
                <p className="whitespace-pre-line">{m.text}</p>
              </div>
            </div>
          ))}
          {loading && (
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
          <div ref={endRef} />
        </div>

        {/* Quick Actions */}
        <div className="px-4 py-3 border-t" style={{ borderColor: theme.border.subtle }}>
          <div className="flex gap-2 flex-wrap">
            {['Расход', 'Доход', 'Отчёт'].map(a => (
              <button
                key={a}
                onClick={() => { setInput(a === 'Отчёт' ? 'Покажи отчёт' : `${a} `); inputRef.current?.focus(); }}
                className="px-3 py-1.5 text-xs font-medium rounded-full transition-colors"
                style={{ backgroundColor: theme.bg.elevated, color: theme.text.secondary }}
              >
                {a}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="p-4 border-t" style={{ borderColor: theme.border.default }}>
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
              placeholder="Напишите команду..."
              disabled={loading}
              className="flex-1 border-0 rounded-xl px-4 py-3 text-sm transition-all focus:outline-none focus:ring-2"
              style={{ 
                backgroundColor: theme.bg.input, 
                color: theme.text.primary,
                '--tw-ring-color': theme.bg.accent
              }}
            />
            <button
              onClick={send}
              disabled={!input.trim() || loading}
              className="w-11 h-11 rounded-xl flex items-center justify-center transition-all disabled:opacity-40"
              style={{ backgroundColor: theme.bg.accent }}
            >
              <Send size={16} style={{ color: theme.text.inverse }} />
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// APP WRAPPER
// ═══════════════════════════════════════════════════════════════

export default function BiotactCoreDashboard() {
  return (
    <ThemeProvider>
      <Dashboard />
    </ThemeProvider>
  );
}
