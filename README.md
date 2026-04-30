# Airdock

Airdock - веб-панель администрирования для управления Docker/automation-инфраструктурой через проекты, курьеров, Ansible playbook, задачи и пайплайны.

Проект построен на FastAPI, Jinja2, SQLAlchemy и SQLite по умолчанию. Интерфейс работает как тёмная SaaS-панель: проекты, задачи, пайплайны, пользователи и журнал срабатываний доступны из единой админки.

## Возможности

- Управление проектами: название, описание, доступ пользователей, привязка курьеров.
- Курьеры/раннеры: SSH-подключение к серверам, статус доступности, сбор метрик.
- Ansible playbook: создание, редактирование YAML, дополнительные файлы рядом с playbook, команда запуска.
- Задачи: ручное создание, запуск, отложенный запуск по времени МСК, остановка, фильтрация по статусу и дате.
- Системные задачи: автоматический сбор метрик от имени `system`.
- Пайплайны: последовательное выполнение нескольких playbook по шагам, выбор от 1 до 5 проектов.
- Журнал срабатываний: события метрик, запусков, ошибок, пайплайнов и задач.
- Контейнеры: просмотр контейнеров проекта и логов контейнеров через привязанных курьеров.
- Авторизация: роли `owner`, `admin`, `user`, HttpOnly cookies, refresh-сессии в базе.

## Технологии

- Python 3.12+
- FastAPI
- Uvicorn
- Jinja2
- SQLAlchemy 2
- SQLite по умолчанию
- Paramiko для SSH
- Docker SDK for Python
- CodeMirror для YAML-редактора

## Структура проекта

```text
.
├── main.py                    # локальная точка входа
├── requirements.txt           # Python-зависимости
├── app/
│   ├── main.py                # создание FastAPI-приложения
│   ├── core/                  # конфиг и безопасность
│   ├── db/                    # модели, сессия, инициализация БД
│   ├── services/              # Docker, Ansible, scheduler, task manager
│   ├── static/                # CSS и JS
│   ├── templates/             # Jinja2-шаблоны
│   └── web/routes/            # маршруты страниц и действий
└── README.md
```

## Быстрый локальный запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Открыть:

```text
http://127.0.0.1:8000
```

При первом старте приложение инициализирует базу и создаёт владельца:

```text
login: owner
password: owner
```

Перед деплоем обязательно смените пароль и задайте собственный `AIRDOCK_SECRET_KEY`.

## Переменные окружения

Пример `.env`:

```env
AIRDOCK_APP_NAME=Airdock
AIRDOCK_DEBUG=false
AIRDOCK_SECRET_KEY=replace-with-a-long-random-secret
AIRDOCK_DATABASE_URL=sqlite:///./airdock.db
AIRDOCK_ACCESS_TOKEN_MINUTES=43200
AIRDOCK_REFRESH_TOKEN_DAYS=90
AIRDOCK_TASK_WORKERS=4
AIRDOCK_DOCKER_BASE_URL=
```

Описание:

| Переменная | Назначение |
| --- | --- |
| `AIRDOCK_APP_NAME` | Название приложения в FastAPI. |
| `AIRDOCK_DEBUG` | Debug-режим. Для production должен быть `false`. |
| `AIRDOCK_SECRET_KEY` | Секрет для подписи токенов и шифрования чувствительных данных. |
| `AIRDOCK_DATABASE_URL` | URL базы данных. По умолчанию `sqlite:///./airdock.db`. |
| `AIRDOCK_ACCESS_TOKEN_MINUTES` | Время жизни access cookie. По умолчанию 30 дней. |
| `AIRDOCK_REFRESH_TOKEN_DAYS` | Время жизни refresh-сессии. По умолчанию 90 дней. |
| `AIRDOCK_TASK_WORKERS` | Количество параллельных воркеров задач, от 2 до 8. |
| `AIRDOCK_DOCKER_BASE_URL` | Опциональный Docker API endpoint для локального Docker SDK. |

## Подготовка сервера к деплою

Минимальный набор на Linux-сервере:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

Если Airdock будет обращаться к локальному Docker на этом же сервере:

```bash
sudo apt install -y docker.io
sudo usermod -aG docker www-data
```

Если Airdock управляет удалёнными серверами через курьеров, на удалённых серверах должны быть:

- доступ по SSH по приватному ключу;
- пользователь, указанный в настройках курьера;
- установленный Ansible, если команда запуска использует `ansible-playbook`;
- доступ к Docker, если playbook или сбор метрик работают с Docker.

## Production-запуск через Uvicorn

```bash
cd /opt/airdock
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export AIRDOCK_DEBUG=false
export AIRDOCK_SECRET_KEY="replace-with-a-long-random-secret"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Для постоянного запуска используйте `systemd`.

## systemd unit

Создайте файл:

```bash
sudo nano /etc/systemd/system/airdock.service
```

Пример:

```ini
[Unit]
Description=Airdock FastAPI service
After=network.target

[Service]
WorkingDirectory=/opt/airdock
Environment="AIRDOCK_DEBUG=false"
Environment="AIRDOCK_SECRET_KEY=replace-with-a-long-random-secret"
Environment="AIRDOCK_DATABASE_URL=sqlite:////opt/airdock/airdock.db"
Environment="AIRDOCK_ACCESS_TOKEN_MINUTES=43200"
Environment="AIRDOCK_REFRESH_TOKEN_DAYS=90"
Environment="AIRDOCK_TASK_WORKERS=4"
ExecStart=/opt/airdock/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable airdock
sudo systemctl start airdock
sudo systemctl status airdock
```

Логи:

```bash
journalctl -u airdock -f
```

## Nginx reverse proxy

Пример конфига:

```nginx
server {
    listen 80;
    server_name your-domain.example;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Активировать:

```bash
sudo ln -s /etc/nginx/sites-available/airdock /etc/nginx/sites-enabled/airdock
sudo nginx -t
sudo systemctl reload nginx
```

Для HTTPS подключите сертификат через Certbot или другой reverse proxy.

## Как работает запуск playbook

1. Пользователь создаёт проект.
2. К проекту привязывается один или несколько курьеров.
3. В проекте создаётся Ansible playbook и дополнительные файлы.
4. При запуске Airdock выбирает доступного курьера.
5. Через SSH создаёт директорию:

```text
/home/<server_user>/airdock/<project_name>/
```

6. Загружает туда playbook, `inventory.ini` и дополнительные файлы.
7. Выполняет команду запуска playbook.

Команда запуска поддерживает подстановки:

```text
{inventory}
{playbook}
{playbook_file}
```

Пример:

```text
ansible-playbook -i {inventory} {playbook}
```

## Задачи и пайплайны

Task manager запускается при старте приложения. Он держит очередь задач и несколько воркеров.

Типы задач:

- `playbook` - запуск одного playbook;
- `pipeline` - последовательный запуск шагов пайплайна;
- `metrics` - системный сбор метрик по курьерам.

Статусы:

- `draft` - задача создана, но не поставлена в очередь;
- `scheduled` - ожидает запуска по времени МСК;
- `queued` - стоит в очереди;
- `running` - выполняется;
- `cancel_requested` - запрошена остановка;
- `cancelled` - остановлена;
- `success` - выполнена успешно;
- `failed` - завершилась ошибкой.

Пайплайн выполняет playbook строго по порядку шагов. Если один шаг завершился ошибкой, пайплайн считается ошибочным и следующие шаги не запускаются.

## Scheduler метрик

Отдельный scheduler запускается вместе с приложением и каждые 300 секунд опрашивает проекты и курьеров.

Если у проекта нет курьеров, в журнал пишется предупреждение. Если курьер недоступен, его статус становится `down`, а ошибка попадает в журнал срабатываний.

## База данных

По умолчанию используется SQLite:

```text
airdock.db
```

Для production обязательно настройте регулярный backup этого файла.

Пример backup:

```bash
mkdir -p /opt/backups/airdock
sqlite3 /opt/airdock/airdock.db ".backup '/opt/backups/airdock/airdock-$(date +%F-%H%M).db'"
```

Если проект будет расти, стоит вынести базу на PostgreSQL. Для этого потребуется адаптировать `AIRDOCK_DATABASE_URL` и проверить совместимость схемы.

## Безопасность перед деплоем

Перед публикацией наружу проверьте:

- `AIRDOCK_DEBUG=false`;
- задан длинный случайный `AIRDOCK_SECRET_KEY`;
- пароль `owner` изменён;
- доступ к панели закрыт HTTPS;
- SSH-ключи курьеров имеют минимально нужные права;
- пользователь на удалённом сервере имеет только необходимые sudo/Docker-права;
- файл SQLite доступен только пользователю сервиса;
- reverse proxy ограничивает размер запросов;
- backup базы настроен.

## Обновление проекта

```bash
cd /opt/airdock
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart airdock
sudo systemctl status airdock
```

Если менялась статика, после обновления в браузере можно сделать жёсткую перезагрузку:

```text
Ctrl+F5
```

## Проверка работоспособности

После деплоя:

1. Откройте веб-интерфейс.
2. Войдите под владельцем.
3. Смените пароль владельца.
4. Создайте проект.
5. Добавьте курьера.
6. Проверьте, что статус курьера стал активным.
7. Создайте playbook.
8. Запустите задачу.
9. Проверьте журнал срабатываний и логи задачи.

## Типичные проблемы

### Не открывается панель

Проверьте сервис и порт:

```bash
sudo systemctl status airdock
curl http://127.0.0.1:8000
```

### Курьер недоступен

Проверьте SSH вручную:

```bash
ssh <server_user>@<server_ip>
```

Проверьте, что приватный ключ в Airdock соответствует публичному ключу на сервере.

### Playbook не запускается

Проверьте:

- есть ли у проекта курьер;
- установлен ли Ansible на сервере-курьере;
- корректна ли команда запуска;
- хватает ли прав пользователю;
- что написано в логах задачи и журнале срабатываний.

### Docker-метрики не собираются

Проверьте на сервере-курьере:

```bash
docker ps
```

Если команда требует sudo, настройте права пользователя или sudoers под вашу модель безопасности.

## Лицензия

Лицензия пока не указана. Перед публичным деплоем или публикацией репозитория добавьте файл `LICENSE`.
