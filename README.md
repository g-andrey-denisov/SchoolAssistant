# SchoolAssistant — Telegram-бот для родительского комитета

Telegram-бот с поддержкой естественного языка для управления списком учеников, контактами родителей и финансами школьного класса. Данные хранятся в Google Sheets. Команды вводятся произвольным текстом (с опечатками, сокращениями, разговорными оборотами) — LLM распознаёт намерение и выполняет нужную операцию.

---

## Возможности

- Просмотр и редактирование контактов учеников и родителей
- Учёт взносов и трат по классу
- Разделение затрат на всех активных учеников
- Финансовые отчёты: баланс, задолженности, сводки по взносам
- Дни рождения: ближайшие, возраст, сколько дней до праздника
- Нечёткое сопоставление имён (опечатки, инициалы, частичные совпадения)
- Разрешение конфликтов имён (Денисов А. → уточнение: Артемий или Арсений)
- Подтверждение деструктивных операций
- Два взаимозаменяемых LLM-бэкенда: OpenAI и локальный LM Studio
- Whitelist по Telegram user-id
- Авто-перезапуск при изменении исходников (`guard.py`)

---

## Архитектура

```
SchoolAssistant/
├── main.py               # Точка входа, запуск бота
├── guard.py              # Файловый вотчер, авто-перезапуск
├── config.py             # Конфигурация (pydantic-settings)
├── requirements.txt
├── .env.example
├── bot/
│   ├── handlers/         # Обработчики сообщений и колбэков
│   ├── keyboards/        # Инлайн-клавиатуры (подтверждения)
│   ├── middlewares/      # Логирование запросов
│   └── states.py         # FSM-состояния диалогов
├── llm/
│   ├── client.py         # Клиент OpenAI / LM Studio
│   ├── intents.py        # Pydantic-модели интентов
│   └── prompts.py        # Системный промпт для LLM
├── sheets/
│   ├── client.py         # Async-обёртка над gspread
│   └── schema.py         # Константы столбцов и листов
├── services/             # Бизнес-логика
│   ├── students.py
│   ├── contacts.py
│   ├── finance.py
│   ├── birthdays.py
│   └── reports.py
├── utils/
│   ├── dates.py          # Парсинг дат, возраст, дни до ДР
│   ├── fuzzy.py          # Нечёткий поиск (rapidfuzz)
│   └── phones.py         # Форматирование телефонов
├── credentials/
│   └── service_account.json   # (git-ignore) ключ сервисного аккаунта
└── logs/                 # Лог-файлы (создаются автоматически)
```

### Модель данных Google Sheets

**Лист «Контакты»**

| ФИО ученика | День рождения | ФИО родителя | Телефон | Примечание |
|-------------|---------------|--------------|---------|------------|

Ученик помечается как неактивный значением `не ходит` в столбце «Примечание».

**Лист «Финансы»**

| ФИО ученика | Взнос: Подарок к НГ | Трата: Экскурсия | … |
|-------------|---------------------|------------------|---|

Каждый новый взнос или трата — отдельный столбец. Неактивные ученики исключаются из расчётов.

---

## Требования

- Python 3.11+
- Аккаунт Telegram Bot (токен от @BotFather)
- Google Cloud проект с включённым Sheets API и сервисным аккаунтом
- OpenAI API-ключ **или** локальный LM Studio (или оба)
- VPS на Debian/Ubuntu для продакшн-развёртывания

---

## Развёртывание

### 1. Клонирование и виртуальное окружение

```bash
git clone <repo-url> SchoolAssistant
cd SchoolAssistant
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Google Cloud: сервисный аккаунт

1. Откройте [console.cloud.google.com](https://console.cloud.google.com).
2. Создайте или выберите проект.
3. Включите **Google Sheets API** и **Google Drive API** (`API и сервисы → Включить API`).
4. Создайте сервисный аккаунт: `IAM и администрирование → Сервисные аккаунты → Создать`.
5. Сгенерируйте ключ формата JSON, скачайте его.
6. Поместите ключ в `credentials/service_account.json`.
7. Откройте нужную Google-таблицу и **выдайте редактирование** на e-mail сервисного аккаунта (вида `...@...iam.gserviceaccount.com`).

### 3. Google Sheets: структура таблицы

Создайте таблицу с двумя листами.

**Лист «Контакты»** — первая строка (заголовки):
```
ФИО ученика | День рождения | ФИО родителя | Телефон | Примечание
```

**Лист «Финансы»** — первая строка (заголовки):
```
ФИО ученика
```
(остальные столбцы создаются ботом автоматически при добавлении взносов и трат)

Скопируйте ID таблицы из URL:
```
https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
```

### 4. Telegram Bot

1. Напишите @BotFather в Telegram: `/newbot`
2. Следуйте инструкциям, получите токен вида `123456789:AAF...`.

### 5. Конфигурация `.env`

Скопируйте шаблон и заполните:

```bash
cp .env.example .env
nano .env
```

Минимально необходимые переменные:

```dotenv
# Telegram
TELEGRAM_BOT_TOKEN=123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Whitelist Telegram user-id через запятую (пусто = бот закрыт для всех)
ALLOWED_USER_IDS=123456789,987654321

# LLM: openai или lmstudio
LLM_BACKEND=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Для LM Studio (если LLM_BACKEND=lmstudio)
# LMSTUDIO_BASE_URL=http://172.16.10.38:1234/v1
# LMSTUDIO_MODEL=qwen3.5-9b-claude-4.6-highiq-instruct

# Google Sheets
GOOGLE_CREDENTIALS_FILE=credentials/service_account.json
GOOGLE_SPREADSHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms

# Названия листов (если отличаются от дефолтных)
# SHEET_CONTACTS=Контакты
# SHEET_FINANCES=Финансы

# Логирование
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_MAX_BYTES=5242880
LOG_BACKUP_COUNT=7
```

Чтобы узнать свой Telegram user-id: напишите @userinfobot.

### 6. Проверка запуска

```bash
source .venv/bin/activate
python main.py
```

Напишите боту `/help` в Telegram — должен прийти ответ. Прервать: `Ctrl+C`.

---

## Развёртывание через systemd (продакшн)

### Структура сервисов

Используются два systemd user-unit:

- `school-assistant.service` — сам бот (запускается через `guard.py`)
- `school-assistant.path` — отслеживает изменения файлов и перезапускает сервис

### 7. Создание unit-файлов

Замените `/home/USER` и `/path/to/SchoolAssistant` на реальные пути.

```bash
mkdir -p ~/.config/systemd/user
```

**`~/.config/systemd/user/school-assistant.service`:**

```ini
[Unit]
Description=SchoolAssistant Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/SchoolAssistant
ExecStart=/path/to/SchoolAssistant/.venv/bin/python guard.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
```

**`~/.config/systemd/user/school-assistant.path`:**

```ini
[Unit]
Description=Watch SchoolAssistant sources and restart on change

[Path]
PathModified=/path/to/SchoolAssistant
Unit=school-assistant.service

[Install]
WantedBy=default.target
```

### 8. Включение и запуск

```bash
# Включить лингерование (сервис стартует без активной SSH-сессии)
loginctl enable-linger $USER

# Перечитать конфиг systemd
systemctl --user daemon-reload

# Включить автозапуск
systemctl --user enable school-assistant.service
systemctl --user enable school-assistant.path

# Запустить
systemctl --user start school-assistant.path
systemctl --user start school-assistant.service
```

### 9. Управление сервисом

```bash
# Статус
systemctl --user status school-assistant.service

# Логи в реальном времени
journalctl --user -u school-assistant.service -f

# Перезапуск вручную
systemctl --user restart school-assistant.service

# Остановка
systemctl --user stop school-assistant.service
```

Файловые логи бота хранятся в `logs/` внутри каталога проекта.

---

## Обновление кода

```bash
cd /path/to/SchoolAssistant
git pull

# Если изменились зависимости
source .venv/bin/activate
pip install -r requirements.txt

# guard.py перезапустит бота автоматически при изменении .py-файлов.
# Если нужно перезапустить вручную:
systemctl --user restart school-assistant.service
```

---

## Использование бота

Бот понимает произвольные фразы на русском языке. Примеры:

```
Покажи список учеников
Телефон родителя Петрова
Кто ещё не сдал на экскурсию?
Добавь взнос 500 руб для Иванова за подарок учителю
Раздели трату 3000 на класс, экскурсия в музей
Ближайшие дни рождения на месяц
Сколько денег в кассе?
Добавь ученика Сидорова Михаила
/reset — очистить контекст диалога
/help — список команд
```

---

## Отладка

**Бот не отвечает**
- Проверьте токен: `echo $TELEGRAM_BOT_TOKEN`
- Проверьте, что ваш user-id есть в `ALLOWED_USER_IDS`
- Смотрите логи: `journalctl --user -u school-assistant.service -n 50`

**Ошибки Google Sheets**
- Убедитесь, что сервисный аккаунт имеет доступ к таблице
- Проверьте `GOOGLE_SPREADSHEET_ID` — он должен совпадать с ID в URL таблицы
- Проверьте, что в таблице есть оба листа с правильными именами

**LLM не понимает запрос**
- Попробуйте сменить бэкенд (`LLM_BACKEND=openai` — более надёжный)
- Проверьте `OPENAI_API_KEY` и баланс аккаунта
- Сложные запросы можно разбить на два простых

**Нечёткое сопоставление имён**
- При неоднозначности бот сам спросит уточнение
- Пишите хотя бы фамилию; инициалы работают, если нет однофамильцев

---

## Лицензия

Для внутреннего использования. Не предназначено для публичного распространения.
