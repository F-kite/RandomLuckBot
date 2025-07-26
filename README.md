# RandomLuckBot 🤖

Telegram бот для создания и проведения розыгрышей с автоматическим определением победителей.

## 📋 Описание проекта

RandomLuckBot - это Telegram бот, который позволяет пользователям создавать розыгрыши у себя в каналах, выставлять обязательные подписки для участников и автоматически определять победителей. Бот поддерживает различные типы медиа (фото, видео, GIF) и гибкие настройки розыгрышей.

## 🚀 Функционал

### Основные возможности:

- **Создание розыгрышей** с медиа-контентом (фото, видео, GIF)
- **Настройка обязательных подписок** на каналы/группы
- **Гибкие параметры**: количество победителей, время окончания, текст кнопки
- **Автоматическое определение победителей**
- **Управление каналами** пользователя
- **Система поддержки** для пользователей
- **Веб-интерфейс** для управления базой данных (pgAdmin)

### Команды бота:

- `/start` - приветствие и начало работы
- `/help` - список доступных команд
- `/new_giveaway` - создать новый розыгрыш
- `/my_giveaways` - просмотр созданных розыгрышей
- `/add_channel` - добавить канал для подписки
- `/my_channels` - просмотр добавленных каналов
- `/support` - написать в поддержку

## 🛠 Технологии

- **Backend**: Python 3.11
- **Telegram API**: pyTelegramBotAPI >4.22.0
- **База данных**: PostgreSQL 15
- **ORM**: SQLAlchemy
- **Миграции**: Alembic
- **Контейнеризация**: Docker & Docker Compose
- **Веб-интерфейс БД**: pgAdmin 4
- **Логирование**: встроенная система (с Московским временем : UTC+3:00)

## 📊 Структура базы данных

### Основные таблицы:

- **users** - пользователи бота
- **channels** - каналы для обязательной подписки
- **giveaways** - созданные розыгрыши
- **giveaway_channels** - связь розыгрышей с каналами
- **giveaway_participants** - участники розыгрышей
- **support_requests** - обращения в поддержку

## 🚀 Быстрый старт

### Предварительные требования:

- Docker и Docker Compose
- Telegram Bot Token (получить у [@BotFather](https://t.me/BotFather))

### 1. Клонирование репозитория

```bash
git clone https://github.com/F-kite/RandomLuckBot.git
cd RandomLuckBot
```

### 2. Настройка переменных окружения

Создать файл `.env` в корне проекта:

```env
# Telegram Bot
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Database
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}$@db:5432/${POSTGRES_DB}

# pgAdmin
PGADMIN_DEFAULT_EMAIL=admin@admin.com (пример)
PGADMIN_DEFAULT_PASSWORD=
```

### 3. Запуск проекта

```bash
# Сборка и запуск всех сервисов
docker-compose up --build -d

# Просмотр логов
docker-compose logs -f bot
```

### 4. Применение миграций базы данных

```bash
# Вход в контейнер бота
docker-compose exec bot bash

# Применение миграций
alembic upgrade head


docker-compose run --rm bot alembic revision --autogenerate -m "init"
```

## 🌐 Доступные сервисы

После запуска будут доступны:

- **Telegram Bot**: ваш бот в Telegram
- **PostgreSQL**: `localhost:5432`
- **pgAdmin**: `http://localhost:5050`
  - Email = `PGADMIN_DEFAULT_EMAIL`
  - Password = `PGADMIN_DEFAULT_PASSWORD`

### Настройка pgAdmin:

1. Откройте `http://localhost:5050`
2. Войдите с учетными данными выше
3. Добавьте сервер PostgreSQL:
   - Host: `db`
   - Port: `5432`
   - Username = `POSTGRES_USER`
   - Password = `POSTGRES_PASSWORD`
   - Database = `POSTGRES_DB`

## 📝 Логирование

Бот ведет подробные логи всех действий
Больше про логирование можно узнать в файле `LOGGING.md`

## 🔧 Разработка

### Структура проекта:

```
RandomLuckBot/
├── alembic/              # Миграции базы данных
├── bot/                  # Основной код бота
│   ├── __init__.py
│   ├── main.py          # Точка входа
│   ├── handlers.py      # Обработчики команд
│   ├── models.py        # Модели базы данных
│   ├── db.py           # Настройки БД
│   └── utils.py        # Утилиты и логирование
├── logs/                # Файлы логов
├── docker-compose.yml   # Конфигурация Docker
├── Dockerfile          # Образ бота
├── requirements.txt    # Зависимости Python
└── README.md
```

## 🐛 Отладка

### Частые проблемы:

**Бот не отвечает:**

- Проверьте токен в `.env`
- Убедитесь, что бот не заблокирован
- Проверьте логи: `docker-compose logs bot`

**Ошибки базы данных:**

- Проверьте подключение к PostgreSQL
- Примените миграции: `alembic upgrade head`
- Проверьте переменные окружения

**Проблемы с Docker:**

- Пересоберите образы: `docker-compose build --no-cache`
- Очистите volumes: `docker-compose down -v`

## 🔒 Безопасность

### Рекомендации для продакшена:

- Измените пароли по умолчанию
- Используйте HTTPS для pgAdmin
- Ограничьте доступ к портам
- Настройте бэкапы базы данных
- Добавьте rate limiting для команд

## 📄 Лицензия

Этот проект распространяется под лицензией MIT.

---

**Автор**: [F-kite](https://github.com/F-kite)
**Версия**: 1.0.0  
**Последнее обновление**: 2025
