# BIOTACT Core Dashboard

> AI-powered финансовая панель с управлением через естественный язык

## Обзор

Интерактивный дашборд для управления финансами компании. Пользователь вводит команды обычным текстом в чат — AI распознаёт намерение, извлекает данные и обновляет графики в реальном времени.

```
Пользователь: "Добавь расход 15 млн на хостинг серверов, это на год"
     ↓
AI парсит → { type: "expense", amount: 15000000, category: "hosting", period: "yearly" }
     ↓
Backend обновляет БД → WebSocket → UI перерисовывается
```

---

## Архитектура

### Стек

| Слой | Технологии |
|------|------------|
| Frontend | React 18, Recharts, Tailwind CSS, Lucide Icons |
| AI Parser | GPT-4o-mini + Function Calling |
| Backend | FastAPI / Node.js (планируется) |
| Database | PostgreSQL |
| Real-time | WebSocket / SSE |

### Структура компонентов

```
BiotactCoreDashboard/
├── ThemeProvider          # Контекст темы (light/dark/system)
├── Dashboard/
│   ├── Sidebar            # Навигация (сворачиваемая)
│   ├── Header             # Заголовок + ThemeToggle + уведомления
│   ├── KPICards           # Выручка / Расходы / Прибыль
│   ├── Charts/
│   │   ├── AreaChart      # Динамика за 6 месяцев
│   │   └── BreakdownBars  # Структура расходов (progress bars)
│   └── TransactionsList   # Последние операции
└── ChatSidebar/
    ├── MessageList        # История сообщений
    ├── QuickActions       # Кнопки быстрых команд
    └── InputArea          # Поле ввода + отправка
```

---

## AI Command Parser

### Function Calling Schema

```json
{
  "name": "add_financial_record",
  "description": "Добавить финансовую запись (доход или расход)",
  "parameters": {
    "type": "object",
    "properties": {
      "type": {
        "type": "string",
        "enum": ["expense", "income"],
        "description": "Тип операции"
      },
      "amount": {
        "type": "number",
        "description": "Сумма в сумах"
      },
      "category": {
        "type": "string",
        "enum": ["hosting", "marketing", "salary", "inventory", "office", "logistics", "other", "sales"],
        "description": "Категория"
      },
      "period": {
        "type": "string",
        "enum": ["monthly", "yearly", "quarterly"],
        "description": "Период"
      },
      "description": {
        "type": "string",
        "description": "Описание операции"
      }
    },
    "required": ["type", "amount", "category"]
  }
}
```

### Распознаваемые команды

| Операция | Триггеры | Пример |
|----------|----------|--------|
| Расход | добавь, расход, потратил, оплати, списать | "Расход 5 млн на маркетинг" |
| Доход | доход, получил, заработал, выручка, поступило | "Доход 50 млн с продаж" |
| Отчёт | отчёт, статистика, покажи, итог, сводка | "Покажи отчёт за январь" |

### Категории (auto-detect)

| Категория | Ключевые слова |
|-----------|----------------|
| `hosting` | хостинг, сервер, облако, aws, cloud |
| `marketing` | маркетинг, реклама, smm, продвижение, pr |
| `salary` | зарплата, персонал, команда, сотрудник, оклад |
| `inventory` | закупка, товар, продукция, склад, запас |
| `office` | офис, аренда, помещение |
| `logistics` | доставка, логистика, транспорт |

### Форматы сумм

```
15 млн       → 15,000,000
15 миллионов → 15,000,000
500 тыс      → 500,000
15           → 15,000,000 (авто-определение миллионов)
15.5 млн     → 15,500,000
```

---

## Система тем

### Режимы

- **Light** — светлая тема (тёплые нейтральные Stone)
- **Dark** — тёмная тема (глубокие Stone + Emerald акценты)
- **System** — автоматически по настройкам ОС

### Цветовые токены

```javascript
// Light theme
{
  bg: {
    page: '#fafaf9',      // stone-50
    card: '#ffffff',
    elevated: '#f5f5f4',  // stone-100
    accent: '#059669',    // emerald-600
  },
  text: {
    primary: '#1c1917',   // stone-900
    secondary: '#57534e', // stone-600
    muted: '#a8a29e',     // stone-400
    accent: '#059669',
  }
}

// Dark theme
{
  bg: {
    page: '#0c0a09',      // stone-950
    card: '#1c1917',      // stone-900
    elevated: '#292524',  // stone-800
    accent: '#10b981',    // emerald-500
  },
  text: {
    primary: '#fafaf9',
    secondary: '#d6d3d1',
    muted: '#78716c',
    accent: '#10b981',
  }
}
```

### Переключение

Тема сохраняется в `localStorage` под ключом `biotact-theme`. При значении `system` слушается `prefers-color-scheme` media query.

---

## UI/UX Design

### Концепция: Editorial Swiss

Чистая типографика, щедрые отступы, функциональная эстетика. Сознательно избегаем "AI-шаблонов":

**Не используем:**
- Фиолетовые/индиго градиенты
- Neon-свечения и глянец
- Bot-иконки в чате
- Избыточное скругление (rounded-2xl везде)

**Используем:**
- Тёплые нейтральные (Stone palette)
- Emerald акценты (отсылка к health/wellness)
- Чёткие границы вместо теней
- Progress bars вместо pie chart

### Layout

```
┌─────────┬────────────────────────────────┬──────────────┐
│         │                                │              │
│  Nav    │         Main Content           │   AI Chat    │
│  56-224 │           flex-1               │     384px    │
│         │                                │              │
│ [icons] │  ┌─────┐ ┌─────┐ ┌─────┐      │  [messages]  │
│         │  │ KPI │ │ KPI │ │ KPI │      │              │
│ Обзор   │  └─────┘ └─────┘ └─────┘      │              │
│ Финансы │                                │              │
│ ...     │  ┌──────────────┐ ┌────────┐  │  [quick]     │
│         │  │    Chart     │ │Breakdn │  │  [input]     │
│         │  └──────────────┘ └────────┘  │              │
└─────────┴────────────────────────────────┴──────────────┘
```

### Типографика

- **Шрифт:** DM Sans (Google Fonts)
- **Fallback:** system-ui, sans-serif
- **Заголовки:** Semibold, tracking-tight
- **Метки:** Uppercase, letter-spacing: 0.05em
- **Числа:** Tabular figures

### Анимации

- Hover на карточках: `shadow-lg` + `scale-[1.02]`
- Progress bars: `transition-all duration-500`
- Typing indicator: `animate-bounce` с delay
- Theme toggle: `transition-colors duration-300`

---

## Интеграция с BIOTACT Core

### Текущая экосистема

```
                    ┌─────────────────┐
                    │   Qdrant        │
                    │ (Vector Store)  │
                    └────────┬────────┘
                             │
┌─────────────┐    ┌────────┴────────┐    ┌─────────────┐
│  Telegram   │───▶│    LlamaIndex   │◀───│  Dashboard  │
│    Bot      │    │  + GPT-4o-mini  │    │   (React)   │
└─────────────┘    └────────┬────────┘    └─────────────┘
                             │
                    ┌────────┴────────┐
                    │    amoCRM       │
                    │  (OAuth 2.0)    │
                    └─────────────────┘
```

### Точки интеграции

1. **Shared AI Stack** — использует тот же GPT-4o-mini что и Telegram-консультант
2. **Qdrant** — может хранить историю операций для контекстного поиска
3. **amoCRM** — синхронизация финансовых данных из сделок
4. **Auth** — общая система авторизации с Telegram Web App

### Деплой

- **URL:** `biotact.uz/core` или `app.biotact.uz/dashboard`
- **Standalone:** может работать как отдельное React-приложение

---

## Разработка

### Запуск

```bash
# Установка зависимостей
npm install react recharts lucide-react

# Запуск (в составе существующего проекта)
# Импортировать компонент BiotactCoreDashboard
```

### Зависимости

```json
{
  "react": "^18.0.0",
  "recharts": "^2.12.0",
  "lucide-react": "^0.263.1"
}
```

### Структура файлов

```
/components
  /dashboard
    BiotactCoreDashboard.jsx   # Главный компонент
    /hooks
      useTheme.js              # Хук темы
    /components
      ThemeToggle.jsx
      KPICard.jsx
      Chart.jsx
      ChatSidebar.jsx
    /utils
      parseCommand.js          # AI-парсер (локальный fallback)
      formatters.js
```

---

## TODO / Roadmap

### MVP (текущий статус)

- [x] Трёхколоночный layout
- [x] KPI-карточки с динамикой
- [x] Area chart (доходы/расходы)
- [x] Breakdown bars (структура расходов)
- [x] AI-чат с парсером команд
- [x] Light/Dark/System темы
- [x] Локальное сохранение темы

### Phase 2

- [ ] Backend API (FastAPI)
- [ ] PostgreSQL схема
- [ ] GPT-4o-mini Function Calling интеграция
- [ ] WebSocket real-time updates
- [ ] Auth интеграция

### Phase 3

- [ ] Дополнительные секции (Продукты, Команда, Аналитика)
- [ ] amoCRM синхронизация
- [ ] Мобильная адаптация
- [ ] Export (PDF/Excel)
- [ ] Уведомления

---

## Примеры использования

### Добавление расхода

```
Пользователь: Добавь расход 15 млн на хостинг серверов, это на год

AI Response:
✓ Готово. Серверы: 15 000 000 сум (год)
[Графики обновляются автоматически]
```

### Генерация отчёта

```
Пользователь: Покажи отчёт

AI Response:
Январь 2026

Доходы: 158 000 000
Расходы: 83 000 000
Прибыль: 75 000 000 (47.5%)
```

### Неизвестная команда

```
Пользователь: Привет

AI Response:
⚠ Подсказка
Попробуйте:
• Расход 5 млн на маркетинг
• Доход 50 млн
• Покажи отчёт
```
