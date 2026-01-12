# Deployment Guide

## CI/CD Pipeline

Проект использует GitHub Actions для автоматизации CI/CD:

| Workflow | Триггер | Описание |
|----------|---------|----------|
| `lint.yml` | Push/PR to main | Ruff lint + Mypy type check |
| `test.yml` | Push/PR to main | Unit + Integration tests |
| `deploy.yml` | Push to main | Docker build → Push → Deploy |

---

## Required GitHub Secrets

Настройте в **Settings → Secrets and variables → Actions**:

### Docker Registry (автоматически)
- `GITHUB_TOKEN` — автоматически доступен, используется для ghcr.io

### SSH Deployment
| Secret | Описание | Пример |
|--------|----------|--------|
| `SSH_HOST` | IP или домен сервера | `192.168.1.100` |
| `SSH_USER` | Пользователь SSH | `deploy` |
| `SSH_PRIVATE_KEY` | Приватный SSH ключ | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `SSH_PORT` | Порт SSH (опционально) | `22` |
| `DEPLOY_PATH` | Путь к проекту на сервере | `/opt/biotact` |

### Environment Secrets (Production)
| Secret | Описание |
|--------|----------|
| `OPENAI_API_KEY` | OpenAI API ключ |
| `SECRET_KEY` | JWT secret (генерируй: `openssl rand -hex 32`) |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |

---

## Server Setup

### 1. Подготовка сервера

```bash
# Установка Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Создание директории
sudo mkdir -p /opt/biotact
sudo chown $USER:$USER /opt/biotact
cd /opt/biotact

# Клонирование репозитория
git clone https://github.com/temrjan/biotact-core-v2.git .
```

### 2. Настройка environment

```bash
# Создание .env файла
cp .env.example .env.prod

# Редактирование переменных
nano .env.prod
```

Минимальные переменные для production:
```env
APP_ENV=production
DEBUG=false
SECRET_KEY=<generate-with-openssl>
POSTGRES_PASSWORD=<strong-password>
OPENAI_API_KEY=sk-...
CORS_ORIGINS=["https://biotact.uz"]
```

### 3. Первый запуск

```bash
# Запуск сервисов
docker compose -f docker-compose.prod.yml up -d

# Применение миграций
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# Проверка статуса
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8000/api/v1/health
```

---

## Manual Deployment

Если нужен ручной деплой без CI/CD:

```bash
# На сервере
cd /opt/biotact

# Обновление кода
git pull origin main

# Пересборка и перезапуск
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml up -d api

# Миграции
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

---

## Rollback

```bash
# Откат на предыдущую версию
docker compose -f docker-compose.prod.yml pull api
docker compose -f docker-compose.prod.yml up -d api

# Или откат на конкретный тег
docker pull ghcr.io/temrjan/biotact-core-v2:<commit-sha>
```

---

## Monitoring

### Логи
```bash
# Все сервисы
docker compose -f docker-compose.prod.yml logs -f

# Только API
docker compose -f docker-compose.prod.yml logs -f api
```

### Health Check
```bash
curl http://localhost:8000/api/v1/health
```

### Метрики (если включены)
```bash
curl http://localhost:8000/metrics
```

---

## Troubleshooting

### API не запускается
```bash
# Проверить логи
docker compose -f docker-compose.prod.yml logs api

# Проверить переменные окружения
docker compose -f docker-compose.prod.yml exec api env | grep -E "(POSTGRES|OPENAI)"
```

### Ошибки миграций
```bash
# Статус миграций
docker compose -f docker-compose.prod.yml exec api alembic current

# Откат миграции
docker compose -f docker-compose.prod.yml exec api alembic downgrade -1
```

### Проблемы с Docker
```bash
# Очистка
docker system prune -af
docker volume prune -f

# Полный перезапуск
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```
