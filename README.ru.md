# Olympic BOINC

Медальный зачёт команд BOINC по олимпийской системе с веб-интерфейсом и REST API только для чтения. Раз в сутки сервис забирает с [BoincStats](https://www.boincstats.com) завершённые соревнования команд — проектные (`/stats/pchallenge/team/overview`) и командные (`/stats/challenge/team/overview`) — сохраняет призёров и начисляет золото, серебро и бронзу за 1-е, 2-е и 3-е места.

[Веб-интерфейс](#веб-интерфейс) доступен по адресу `/`: фильтры по году и типу соревнования, переключатель английского и русского языков (по умолчанию — английский). [REST API](#rest-api) предоставляет медальный зачёт, результаты соревнований и сведения о командах; интерактивная документация API доступна по адресу `/docs`. Веб-интерфейс и API обслуживает одно приложение, как при локальном запуске, так и в Docker.

## Как это работает

```
BoincStats ──► scraper (Chrome + разбор HTML) ──► sync ──► PostgreSQL ──► REST API
                         ▲
                 scheduler (cron, раз в сутки)

REST API ◄── веб-интерфейс (браузер) / клиенты API
```

- **Загрузка.** BoincStats закрыт Cloudflare, поэтому страницы загружает настоящий Chrome через [nodriver](https://github.com/ultrafunkamsterdam/nodriver). Браузер запускается только на время синхронизации.
- **Синхронизация.** На каждом запуске:
  1. загружаются оба списка соревнований;
  2. отбираются завершённые соревнования, которых ещё нет в базе, свежие первыми;
  3. загружаются их страницы, но не больше `OLYMPIC_SYNC_MAX_CHALLENGES` за запуск;
  4. сохраняются команды, занявшие 1–3 места.
- **Что не загружается повторно.** Уже сохранённые соревнования не загружаются и не меняются. Соревнования без результатов не сохраняются и проверяются снова при следующем запуске.
- **Защита от капчи.** BoincStats показывает капчу при частых запросах, поэтому между запросами выдерживается пауза (`OLYMPIC_REQUEST_DELAY`). Вся история, около 1070 соревнований, догружается за несколько суточных запусков, свежие соревнования идут первыми.
- **Команды.** Команда определяется по имени точно так, как его показывает BoincStats. Ничьи допускаются: две команды на 2-м месте получают по серебру.
- **Веб-интерфейс.** Страница в браузере получает медальный зачёт через REST API и обновляет фильтры года и типа без перезагрузки. HTML, CSS и JavaScript входят в пакет приложения; отдельный frontend-сервер не нужен.
- **Журнал.** Итог каждого запуска пишется в лог приложения, в базе история запусков не хранится.

## Требования

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (переход проверен на 0.13.7); Python 3.13 указан в `.python-version`
- PostgreSQL 18: локально или через `docker compose`
- Chrome или Chromium. Браузер работает с окном, поэтому на сервере без дисплея нужен Xvfb (`xvfb-run`).

## Установка

```bash
uv python install
uv sync --locked
cp .env.example .env    # и заполнить, см. «Настройки»
```

Зависимости зафиксированы в `uv.lock`; `uv sync --locked` устанавливает приложение
и группу `dev`. По умолчанию окружение создаётся в `.venv`, активация не требуется.
Для существующего внешнего окружения задайте переменную **до** всех команд uv и
quality gate в каждом терминале:

```bash
export UV_PROJECT_ENVIRONMENT=<path_to_env>
uv sync --locked
```


### База данных

Вариант 1 — локальный PostgreSQL 18 (порт 5432):

```sql
CREATE ROLE olympic LOGIN PASSWORD '...' CREATEDB;   -- CREATEDB нужен тестам
CREATE DATABASE olympic_boinc OWNER olympic;
```

Вариант 2 — только база в Docker (порт **5433**): создайте `.docker-env` из `.docker-env.example` и задайте в нём `POSTGRES_USER` и `POSTGRES_PASSWORD`, затем

```bash
docker compose up -d db
```

и в `OLYMPIC_DATABASE_URL` в `.env` укажите `localhost:5433` и те же учётные данные. Чтобы запустить в Docker и приложение, см. «Запуск в Docker».

Затем примените миграции:

```bash
uv run --locked alembic upgrade head
```

### Перенос данных через CSV

Собранные соревнования можно выгрузить в CSV-файл и загрузить в другую базу без повторной загрузки с BoincStats. Подключение берётся из `OLYMPIC_DATABASE_URL`.

```bash
uv run --locked python -m olympic_boinc.csv_transfer export                # -> dumps/olympic_boinc_<UTC время>.csv
uv run --locked python -m olympic_boinc.csv_transfer export results.csv    # в указанный файл
uv run --locked python -m olympic_boinc.csv_transfer import dumps/olympic_boinc_20261027_120000.csv
```

Одна строка файла — одно призовое место, внутренних id базы в файле нет. Столбцы:

| Столбец | Значение |
|---|---|
| `challenge_type` | `project` или `team` |
| `challenge_name` | название соревнования |
| `project_name` | проект BOINC, пусто, если неизвестен |
| `start_at`, `end_at` | ISO 8601, при экспорте в UTC; дата без часового пояса при импорте считается UTC |
| `url` | ссылка на соревнование, по ней соревнования считаются одними и теми же |
| `team` | имя команды точно как на BoincStats |
| `place` | 1–3 |
| `score` | очки (целое), пусто, если неизвестны |

Импорт добавляет только соревнования, которых ещё нет в базе. Уже сохранённые пропускаются без изменений, поэтому повторный импорт того же файла ничего не дублирует. Команды сопоставляются по точному имени. Сначала проверяется весь файл: если есть хоть одна ошибка, ничего не загружается, а все ошибки выводятся с номерами строк (код возврата 1). Если файл правили в Excel или LibreOffice, сохраняйте его как «CSV UTF-8» с запятой в качестве разделителя.

## Настройки

Все настройки — переменные окружения с префиксом `OLYMPIC_`, их можно задать в `.env`. Полный список с комментариями — в [`.env.example`](.env.example).

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `OLYMPIC_DATABASE_URL` | — (обязательна) | `postgresql+asyncpg://user:password@host:port/olympic_boinc` |
| `OLYMPIC_SYNC_CRON` | `0 3 * * *` | Расписание синхронизации, cron в UTC |
| `OLYMPIC_SCHEDULER_ENABLED` | `true` | `false` — API работает, синхронизация не запускается |
| `OLYMPIC_SYNC_ON_STARTUP` | `false` | `true` — запустить синхронизацию сразу при старте, дальше по расписанию |
| `OLYMPIC_SYNC_MAX_CHALLENGES` | `100` | Сколько страниц соревнований загружать за запуск |
| `OLYMPIC_SYNC_LOG_FILE` | `logs/sync.log` | Журнал запусков синхронизации, относительно рабочего каталога (см. «Логи») |
| `OLYMPIC_REQUEST_DELAY` | `60` | Пауза между запросами к BoincStats, секунды |
| `OLYMPIC_REQUEST_RETRIES` | `3` | Повторы при сетевых ошибках, 5xx и 429 |
| `OLYMPIC_BROWSER_PATH` | автопоиск | Путь к Chrome/Chromium |
| `OLYMPIC_BROWSER_SANDBOX` | `true` | `false` для Chromium без профиля AppArmor (например, Chromium от Playwright) |
| `OLYMPIC_TEST_DATABASE_URL` | — | Сервер PostgreSQL для тестов (см. «Тесты») |

Не уменьшайте `OLYMPIC_REQUEST_DELAY` для полноценных запусков: при частых запросах BoincStats показывает капчу, и запуск прерывается.

## Запуск

```bash
uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

На сервере без дисплея:

```bash
xvfb-run uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Планировщик стартует вместе с приложением и останавливается вместе с ним. Запуски синхронизации не накладываются друг на друга: если предыдущий ещё идёт, следующий по расписанию пропускается.

По умолчанию синхронизация при старте приложения **не запускается**: первый запуск будет в ближайшее время по `OLYMPIC_SYNC_CRON`. Чтобы запустить её сразу, задайте `OLYMPIC_SYNC_ON_STARTUP=true`. Тогда первый запуск начнётся при старте, а следующие пойдут по расписанию. Запуск при старте подчиняется тем же правилам: не накладывается на запуск по расписанию, пишется в журнал, закрывает браузер. Без включённого планировщика настройка ни на что не влияет.

Включайте её для первого развёртывания или проверки, но не держите постоянно там, где приложение часто перезапускается (отладка, `Restart=on-failure` при нестабильном сервисе). Каждый перезапуск — это ещё один обход сайта, а частые запросы приводят к капче BoincStats.

Если запустить несколько экземпляров приложения, `OLYMPIC_SCHEDULER_ENABLED=true` оставьте только у одного. Данные при одновременных запусках не испортятся, но запросов к сайту будет вдвое больше.

**Быстрая проверка, что всё работает** (синхронизация сразу при старте, по 3 соревнования):

```bash
OLYMPIC_SYNC_ON_STARTUP=true OLYMPIC_SYNC_MAX_CHALLENGES=3 \
  uv run --locked uvicorn olympic_boinc.api.app:create_app --factory
```

Через несколько минут (по паузе между запросами) в логе появится итог:

```
INFO olympic_boinc.sync: sync ok in 13 s: added=2 skipped=1 deferred=1062 errors=0
```

- `added` — сохранено новых соревнований;
- `skipped` — без результатов или с ошибкой, будут проверены в следующий раз;
- `deferred` — не загружены из-за лимита, ждут следующих запусков.

Статусы:
- `ok` — без ошибок;
- `partial` — ошибки на отдельных соревнованиях, или запуск прерван капчей;
- `failed` — не загрузился список соревнований.

Ручного запуска синхронизации (CLI или HTTP) нет, синхронизацию запускает только планировщик: по расписанию и, если включено `OLYMPIC_SYNC_ON_STARTUP`, при старте.

## Логи

Все логи приложения и uvicorn идут в **stderr**.

### Журнал синхронизации

Если планировщик включён, всё, что относится к синхронизации, дополнительно пишется в файл **`logs/sync.log`** в рабочем каталоге, то есть в корне проекта при обычном запуске. Каталог создаётся сам. Путь меняется настройкой `OLYMPIC_SYNC_LOG_FILE`, его можно задать и абсолютным.

В журнале:
- старт и остановка планировщика;
- начало запуска (`sync job started`);
- каждый запрос к BoincStats (`GET <url>`, повторы отдельными строками);
- ошибки по соревнованиям с трейсом;
- итог запуска (`sync ok|partial|failed ...`).

Логов REST API в журнале нет. Файл ротируется при 10 МБ, хранится 5 архивных файлов (`sync.log.1` … `sync.log.5`).

Пример запуска, прерванного капчей:

```
2026-10-27 03:00:00,001 INFO apscheduler.executors.default: Running job "sync (trigger: cron[...], next run at: ...)" (scheduled at 2026-10-27 03:00:00+00:00)
2026-10-27 03:00:00,002 INFO olympic_boinc.scheduler: sync job started
2026-10-27 03:00:00,010 INFO olympic_boinc.scraper.fetcher: GET https://www.boincstats.com/stats/pchallenge/team/overview
2026-10-27 03:02:10,011 INFO olympic_boinc.scraper.fetcher: GET https://www.boincstats.com/stats/challenge/team/overview
...
2026-10-27 03:41:10,415 ERROR olympic_boinc.sync: https://www.boincstats.com/stats/pchallenge/team/list/42080/rank: BlockedError: status=200: BoincStats captcha (too many requests)
2026-10-27 03:41:10,416 WARNING olympic_boinc.sync: sync partial in 2470 s: added=17 skipped=2 deferred=1041 errors=1
```

Число запросов в запуске — это число строк `GET` между `sync job started` и итогом:

```bash
grep -c "GET https://" logs/sync.log            # всего запросов в журнале
grep "olympic_boinc.sync: sync " logs/sync.log  # итоги запусков
```

### Полный вывод приложения

Чтобы сохранить весь вывод при ручном запуске, перенаправьте его:

```bash
# в терминал и в файл
uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000 2>&1 | tee -a app.log

# только в файл, в фоне
nohup uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000 >> app.log 2>&1 &
```

Логгеры:

- `olympic_boinc.sync` — итог каждого запуска и ошибки по отдельным соревнованиям, с трейсом. Уровень итоговой строки: `INFO` при `ok`, `WARNING` при `partial`, `ERROR` при `failed`.
- `olympic_boinc.scraper.fetcher` — каждый запрос к сайту, повторы, клики по проверке Cloudflare.
- `apscheduler` — старт и остановка планировщика, запуск задачи, пропуск запуска, если предыдущий ещё идёт (`maximum number of running instances reached`).

«Job ... executed successfully» от APScheduler значит только то, что задача не упала. Итог синхронизации смотрите в строке `olympic_boinc.sync: sync ...`: запуск, прерванный капчей, тоже завершается «успешно» для планировщика.


## Запуск в Docker

Docker Compose поднимает базу и REST API. Образ собирается uv 0.13.7 из `uv.lock`
с runtime-зависимостями, без dev/load. Контейнер использует `/app/.venv`, локальная
`UV_PROJECT_ENVIRONMENT` ему не передаётся; при старте пакеты не устанавливаются. Python на сервер ставить не нужно. Для сборки и запуска нужен Docker с Compose v2 и доступ к нему: группа `docker` (`sudo usermod -aG docker $USER`, затем перелогиниться) или `sudo`.

**Синхронизации в контейнере нет.** Chromium в контейнере не проходит проверку Cloudflare на BoincStats, поэтому в контейнере планировщик всегда выключен, даже если в настройках стоит `OLYMPIC_SCHEDULER_ENABLED=true`. Данные попадают в контейнер из CSV-файла при старте или из синхронизации, запущенной вне контейнера (см. ниже).

1. Для нового окружения создайте `.docker-env` из готового
   [шаблона `.docker-env.example`](.docker-env.example):

   ```bash
   cp .docker-env.example .docker-env
   ```

   В шаблоне уже заданы имя базы/пользователя, путь CSV и настройки подключения APM
   внутри Docker. Замените заглушки `<...>` собственными значениями:

   - `POSTGRES_USER` и `POSTGRES_PASSWORD` — учётные данные базы в контейнере;
   - `OLYMPIC_DATABASE_URL` — адрес базы для приложения: хост `db`, тот же пользователь и пароль. Спецсимволы пароля в URL кодируются: `@` → `%40`, `/` → `%2F`, `:` → `%3A`, `%` → `%25`, `#` → `%23`.

   Для каждого пароля можно отдельно выполнить `openssl rand -hex 32`.
   Полученные hex-пароли не требуют URL-кодирования. Если запускаете профиль
   `observability`, также замените заглушки `ELASTIC_PASSWORD`,
   `KIBANA_SYSTEM_PASSWORD`, `APM_WRITER_PASSWORD` тремя разными паролями,
   а `KIBANA_ENCRYPTION_KEY` — отдельной строкой не короче 32 символов.
   Для обычного запуска db + app эти четыре настройки не используются.

   При настройке уже работающего окружения редактируйте существующий `.docker-env`,
   сохраняя его пароли и ключ Kibana.

   Если пароль в `POSTGRES_PASSWORD` и в URL разойдётся, приложение не подключится к базе и упадёт на миграциях (`docker compose logs app`).

   Контейнеры (и база, и приложение) читают только `.docker-env`. `.env` для них не используется, он нужен для запуска вне Docker. Без `.docker-env` compose завершится с ошибкой `env file .../.docker-env not found`.
2. Положите выгрузку данных в `dumps/import.csv` (как её получить — ниже).
   В шаблоне явно задано `IMPORT_FILE=dumps/import.csv`; для другой выгрузки
   укажите её путь, например `IMPORT_FILE=dumps/results.csv`. Он задаётся
   относительно `/app` в контейнере; каталог `dumps/` смонтирован с хоста.
3. Соберите и запустите:

   ```bash
   docker compose config --quiet
   docker compose up -d --build
   docker compose ps          # app должен стать healthy
   curl localhost:8000/health
   ```

   Для запуска всего стека с APM установите в `.docker-env`
   `OLYMPIC_APM_ENABLED=true` и используйте:

   ```bash
   docker compose --profile observability config --quiet
   docker compose --profile observability up -d --build
   docker compose --profile observability ps -a
   ```

   В шаблоне APM выключен явно (`false`); один запуск профиля не включает агент
   приложения. Адрес `http://apm-server:8200` и окружение `docker` уже настроены.
   Просмотр событий и вход в Kibana описаны в разделе «Elastic APM».

При каждом старте контейнер:
1. применяет миграции;
2. импортирует `dumps/import.csv`, если файл есть;
3. запускает API.

Импорт добавляет только соревнования, которых ещё нет в базе, поэтому файл можно не удалять: при следующих стартах в логе будет `added 0, skipped N`. Если файла нет, импорт пропускается.

Если в файле ошибка, контейнер не запускает API и завершается. Из-за `restart: unless-stopped` он будет перезапускаться: в `docker compose ps` статус `Restarting`. Ошибки с номерами строк видны в `docker compose logs app`. Исправьте или удалите файл, контейнер поднимется сам при следующем перезапуске. Если миграции не прошли, контейнер ведёт себя так же.

Параметры:
- порт API на хосте — 8000. Другой порт задаётся переменной оболочки при запуске, например `APP_PORT=8080 docker compose up -d`. Это настройка самого Compose, а не контейнера, поэтому в `.docker-env` она не работает;
- `IMPORT_FILE` в `.docker-env` — другой файл для импорта при старте, путь относительно `/app`, например `dumps/2026-10.csv`;
- если UID вашего пользователя не 1000 (`id -u`), соберите образ с `docker compose build --build-arg UID=$(id -u)`, иначе контейнер не сможет писать в `dumps/`;
- данные базы лежат в томе `pgdata` и переживают `docker compose down`. Удаляет их только `docker compose down -v`.

Вывод приложения: `docker compose logs -f app`.

## Elastic APM

APM выключен по умолчанию. Агент фиксирует HTTP-транзакции по шаблонам маршрутов,
необработанные ошибки и фоновые запуски `sync` со статусом и счётчиками.
`/health` и `/static/` исключены. Тела запросов, заголовки и локальные переменные
не отправляются. Отправка идёт в фоне; недоступность APM не останавливает API
или синхронизацию. SQLAlchemy-запросы внутри HTTP-транзакций и `sync` получают
spans типа `db.postgresql.query`: тип операции (например, `SELECT`), длительность
и результат. В деталях span доступен SQL (`db.statement`) с именами таблиц,
столбцов и плейсхолдерами параметров. Строковые и числовые литералы заменяются
на `?`, комментарии удаляются; значения параметров и адрес подключения не отправляются.
Перезапустите приложение и откройте SQL span новой трассировки в Kibana,
чтобы увидеть текст запроса; старые трассировки не изменятся.
Browser spans и центральная конфигурация агента в этой реализации не включены.

Собственный стек запускается профилем `observability`: Elasticsearch, Kibana и
APM Server **9.5.6**, APM integration **9.5.6**, Python-агент **6.26.2** в `uv.lock`.
Нужны Docker Compose v2, около 6 ГБ свободной RAM и место для телеметрии.
Для Elasticsearch на Linux проверьте `sysctl vm.max_map_count` (не ниже 262144).
Первый запуск с установкой integration может занять несколько минут.

В `.docker-env` заполните `ELASTIC_PASSWORD`, `KIBANA_SYSTEM_PASSWORD`,
`APM_WRITER_PASSWORD` разными паролями и `KIBANA_ENCRYPTION_KEY` строкой не короче
32 символов (например, значения можно получить через `openssl rand -hex 32`).
Сохраните ключ между перезапусками. `elastic-setup` подготавливает служебные
аккаунты, затем `apm-setup` устанавливает bundled integration через Kibana API
без внешнего Package Registry. Запросы выполняются по HTTP(S), без автоматических перенаправлений. URL с учётными данными,
query string или fragment отклоняются до подключения. Установка подтверждается
обычной проверкой статуса, работающей и при запуске Python с `-O`.
Оба шага можно безопасно повторять; ошибки дают
ненулевой код завершения. При сохранённом esdata смена `ELASTIC_PASSWORD` в файле
сама по себе не меняет пароль пользователя Elasticsearch.

Для приложения в Docker в `.docker-env` задайте:

```dotenv
OLYMPIC_APM_ENABLED=true
OLYMPIC_APM_SERVER_URL=http://apm-server:8200
OLYMPIC_APM_SERVICE_NAME=olympic-boinc
OLYMPIC_APM_ENVIRONMENT=docker
OLYMPIC_APM_TRANSACTION_SAMPLE_RATE=1.0
```

```bash
docker compose --profile observability up -d --build
docker compose --profile observability ps -a
docker compose --profile observability logs apm-server apm-setup elastic-setup
```

Планировщик в контейнере остаётся выключенным. Приложение зависит только от БД;
обычный `docker compose up -d --build` не запускает Elastic Stack.

Для приложения на хосте запустите только стек (БД приложения остаётся прежней):

```bash
docker compose --profile observability up -d --build elasticsearch kibana apm-setup apm-server
```

В локальном `.env` включите `OLYMPIC_APM_ENABLED=true`, задайте
`OLYMPIC_APM_SERVER_URL=http://127.0.0.1:8200` и `OLYMPIC_APM_ENVIRONMENT=local`.
Запускайте приложение обычной командой:

```bash
uv run --locked uvicorn olympic_boinc.api.app:create_app --factory
```

При необходимости задайте `OLYMPIC_APM_SECRET_TOKEN` в `.docker-env` и **то же
значение** в `.env`. Без токена intake не требует авторизации. Не задавайте
параллельно `ELASTIC_APM_*`: у Python-агента собственный приоритет этих переменных.
Sampling принимает значения от 0 до 1; для проверки оставьте 1.

Откройте `http://127.0.0.1:5601`, войдите как `elastic` с `ELASTIC_PASSWORD`,
перейдите в Observability → APM / Applications и выберите `olympic-boinc` и
окружение `local` или `docker`. Сделайте несколько запросов к `/` и `/api/medals`;
события обычно появляются через несколько секунд. Фоновая транзакция `sync`
появляется после запуска локального планировщика. Kibana и intake опубликованы
только на loopback (5601 и 8200), Elasticsearch наружу не опубликован. Внутри
локальной Docker-сети используется HTTP; для удалённого доступа нужен отдельный
TLS-прокси или туннель.

`docker compose --profile observability down` сохраняет телеметрию в отдельном
томе `esdata`. Для выключения наблюдаемости задайте `OLYMPIC_APM_ENABLED=false`
и остановите сервисы профиля. Для удаления **только телеметрии** сначала остановите
стек, затем найдите точное имя тома и удалите только его:

```bash
docker compose --profile observability down
docker volume ls --filter label=com.docker.compose.volume=esdata
docker volume rm <точное-имя-тома-esdata-этого-проекта>
```

Не используйте `down -v` для этой операции: он удаляет также PostgreSQL `pgdata`.
Quality gate проверяет агент без внешнего Elastic Stack; сценарии реальной
доставки описаны в OpenSpec change `elastic-apm-observability`.

### Как данные попадают в контейнер

Синхронизация работает вне контейнера, там, где Cloudflare её пропускает: на вашей машине или на сервере без Docker (см. «Запуск», «Запуск через systemd»). Есть два способа передать данные в контейнер.

**Через CSV** — подходит, если синхронизация идёт на другой машине:

```bash
uv run --locked python -m olympic_boinc.csv_transfer export dumps/import.csv     # там, где идёт синхронизация
# скопировать файл в dumps/import.csv рядом с docker-compose.yml, затем
docker compose restart app                                        # импорт при старте
# или без перезапуска:
docker compose exec app python -m olympic_boinc.csv_transfer import dumps/import.csv
```

Выгрузка из контейнера: `docker compose exec app python -m olympic_boinc.csv_transfer export`. Файл появится в `dumps/` на хосте.

**Напрямую в базу контейнера** — если синхронизация идёт на той же машине. База контейнера доступна на хосте через порт 5433. Запустите приложение вне контейнера (с планировщиком, как обычно) с адресом этой базы:

```bash
OLYMPIC_DATABASE_URL=postgresql+asyncpg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@localhost:5433/olympic_boinc \
    xvfb-run uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --port 8001
```

Новые соревнования сразу видны в API контейнера. Порт 5433 не должен быть доступен из интернета: закройте его файрволом или публикуйте только на локальном адресе (`"127.0.0.1:5433:5432"` в `docker-compose.yml`).

Обновление: `git pull`, затем `docker compose up -d --build`.

Если раньше `POSTGRES_USER`/`POSTGRES_PASSWORD` были заданы в `.env`, перенесите их в `.docker-env` (с теми же значениями: с ними создан том `pgdata`) и допишите `OLYMPIC_DATABASE_URL`. Из `.env` их можно удалить. Время от времени выполняйте `docker compose build --pull`, чтобы обновить базовый образ.

## Веб-интерфейс

После запуска откройте `http://localhost:8000/` (в Docker — порт `APP_PORT`, по умолчанию 8000).
По умолчанию интерфейс на английском. Переключатель в шапке предлагает English и Русский;
выбранный язык сохраняется в браузере, если доступно локальное хранилище.
Смена языка переводит подписи и сообщения без сброса фильтров и повторной загрузки данных.
Имена команд отображаются точно так, как их передаёт BoincStats.
Страница показывает медальный зачёт команд: золото, серебро, бронзу и общее число медалей.
Два фильтра применяются сразу, без перезагрузки:

- **Год:** «За весь период» или год окончания соревнований в UTC. Список формируется
  из данных при открытии страницы, от новых лет к старым, и общий для обоих типов.
- **Тип соревнования:** «Все типы», «Командные», «Проектные».

Порядок олимпийский: сначала золото, затем серебро и бронза, при равенстве — имя команды.
Если для комбинации нет медалей, страница сообщает об этом; ошибку загрузки можно
повторить кнопкой «Повторить». Для работы нужен JavaScript.

Интерфейс — локальные HTML/CSS/JavaScript в `src/olympic_boinc/web/static/`.
Он включён в Python-пакет и Docker-образ, отдельный frontend-сервер, npm и CDN не нужны.
Python quality gate не измеряет JavaScript: поведение фильтров и адаптивность
нужно дополнительно проверять в браузере при изменении интерфейса.

## REST API

Документация OpenAPI: `http://localhost:8000/docs` (схема — `/openapi.json`). API только для чтения.

| Метод и путь | Что возвращает |
|---|---|
| `GET /api/medals` | Медальный зачёт |
| `GET /api/challenges` | Соревнования с призёрами, постранично |
| `GET /api/challenges/years` | Уникальные годы окончания всех соревнований в UTC, по убыванию; `[]` для пустой БД |
| `GET /api/challenges/{id}` | Одно соревнование с призёрами |
| `GET /api/teams/{id}` | Медали команды и соревнования, где она была призёром |
| `GET /health` | `200 {"status": "ok"}` или `503`, если база недоступна |

### Медальный зачёт

Сортировка: по золоту, затем по серебру, затем по бронзе, всё по убыванию. При полном равенстве — по имени команды.

Параметры:
- `challenge_type` — `project`, `team` или `all` (по умолчанию `all`);
- `from`, `to` — даты `YYYY-MM-DD`, обе включаются. Фильтр смотрит на дату окончания соревнования, в UTC.

Если параметр задан неверно, ответ — 422.

```bash
curl 'localhost:8000/api/medals?challenge_type=project&from=2026-01-01&to=2026-12-31'
```

```json
[
  {"team_id": 1, "team_name": "The FPS Team", "gold": 4, "silver": 0, "bronze": 0, "total": 4},
  {"team_id": 2, "team_name": "Czech National Team", "gold": 0, "silver": 3, "bronze": 1, "total": 4}
]
```

### Соревнования

Параметры:
- `challenge_type` — как у медального зачёта;
- `page` — номер страницы, с 1;
- `size` — размер страницы, по умолчанию 50, максимум 200.

Сортировка — по дате окончания, свежие первыми.

```bash
curl 'localhost:8000/api/challenges?page=1&size=10'
```

```json
{
  "items": [
    {
      "id": 1,
      "challenge_type": "project",
      "name": "Suzuki's Birthday Challenge",
      "project_name": "PrimeGrid",
      "start_at": "2026-10-02T17:00:00Z",
      "end_at": "2026-10-07T17:00:00Z",
      "url": "https://www.boincstats.com/stats/pchallenge/team/list/42109/rank",
      "placements": [
        {"team_id": 1, "team_name": "The FPS Team", "place": 1, "score": 348043392},
        {"team_id": 2, "team_name": "Czech National Team", "place": 2, "score": 334315680},
        {"team_id": 3, "team_name": "SETI.Germany", "place": 3, "score": 284077760}
      ]
    }
  ],
  "total": 4,
  "page": 1,
  "size": 10
}
```

### Команда

```bash
curl localhost:8000/api/teams/1
```

В ответе `id`, `name`, `gold`, `silver`, `bronze`, `total` и `challenges` — соревнования, где команда была призёром, с полем `place`. Если команды нет, ответ — 404.

## Тесты

```bash
uv run --locked pytest                      # все тесты, без обращений к сайту
uv run --locked pytest tests/test_api.py    # один файл
uv run --locked pytest -m live              # смоук-тесты против настоящего BoincStats (нужен браузер)

# Запуск с анализом покрытия кода
uv run --locked pytest \
  --cov=olympic_boinc \
  --cov-report=term-missing \
  --cov-report=html
```

Тестам нужен PostgreSQL:
- если задан `OLYMPIC_TEST_DATABASE_URL`, каждый прогон создаёт на этом сервере свою базу `<имя>_<случайный суффикс>` и удаляет её в конце, поэтому прогоны можно запускать параллельно;
- иначе поднимается контейнер `postgres:18` через testcontainers, нужен Docker.

Полный quality gate: Ruff, mypy, pytest с покрытием строк не ниже **90%**,
Bandit, pip-audit и Semgrep:

```bash
./quality-gate.sh
```

GitHub Actions запускает тот же скрипт при каждом push, в pull request и вручную
через Actions → Quality gate → Run workflow. Workflow находится в
[`.github/workflows/quality-gate.yml`](.github/workflows/quality-gate.yml): Ubuntu 24.04,
Python из `.python-version`, uv 0.13.7 с кешем и отдельный PostgreSQL 18.
Semgrep устанавливается в отдельное окружение через `uv tool install`.
Тесты создают и удаляют свою БД; указанные в workflow учётные данные относятся
только к временному CI-сервису, GitHub Secrets для запуска не нужны.
Live-тесты исключены стандартной конфигурацией pytest. Устаревший запуск той же
ветки или pull request отменяется при поступлении нового. Чтобы запретить слияние
при ошибках, выберите проверку `Quality gate` обязательной в ruleset целевой ветки.

Ruff проверяет lint/import ordering, длину строк (100 символов) и форматирование
через `ruff format --check`. Для применения форматирования используйте
`uv run --locked --no-sync ruff format .`. Логические блоки внутри функций
отделяются пустыми строками согласно `AGENTS.md`; это проверяется при ревью кода.

Скрипт сам устанавливает группы `dev`, `security` и extra `load` из lock-файла
и наследует `UV_PROJECT_ENVIRONMENT`. Bandit и pip-audit запускаются через uv.
Semgrep устанавливается отдельно и должен быть доступен командой `semgrep` в `PATH`
терминала или Run Configuration PyCharm; в зависимости проекта он не входит.
Все шесть проверок запускаются даже при ошибке одной; ошибка подготовки окружения
завершает gate сразу. Отсутствие Semgrep, находки и ошибки сканеров дают ненулевой
итоговый код, проверки не пропускаются молча.

Bandit проверяет Python-код приложения, миграций, скриптов, Docker bootstrap и
нагрузочных сценариев (`src`, `migrations`, `scripts`, `docker`, `load_tests`).
pip-audit проверяет зафиксированные в `uv.lock` runtime/dev/security/load зависимости:
gate временно экспортирует их с хешами без локального пакета проекта и проверяет без повторного
разрешения зависимостей или установки пакетов. Временный файл удаляется при завершении.
Semgrep сканирует те же каталоги, `tests`, `Dockerfile` и quality gate с набором
`p/security-audit`; находки и ошибки считаются провалом (`--error --strict`).
Файл `.semgrepignore` сохраняет тесты в области проверки, исключая только служебные
и сгенерированные файлы; `--no-git-ignore` позволяет проверить и новый код до коммита.
Для pip-audit нужен доступ к базе уязвимостей, для Semgrep — к реестру правил;
состав удалённого набора правил и база уязвимостей могут меняться между запусками.

Тесты загрузки и разбора работают на сохранённых HTML-страницах BoincStats из `tests/fixtures/`. Обновить фикстуры можно скриптом `uv run --locked python scripts/spike_fetch.py --save DIR [URL ...]`.

Нагрузочные тесты REST API на Locust: [подготовка и запуск](load_tests/README.md).

## Частые проблемы

- **`could not find a valid chrome browser binary`** — укажите `OLYMPIC_BROWSER_PATH`. Для Chromium, установленного не из .deb (например, от Playwright), добавьте ещё `OLYMPIC_BROWSER_SANDBOX=false`.
- **В логе `BlockedError` и статус `partial` или `failed`** — BoincStats показал капчу или проверку Cloudflare. Проверьте, что `OLYMPIC_REQUEST_DELAY` не занижен. Следующий запуск продолжит с того же места.
- **`added=0`, а `skipped` растёт от запуска к запуску** — много соревнований без результатов занимают весь лимит запуска. Увеличьте `OLYMPIC_SYNC_MAX_CHALLENGES`.
- **BoincStats исправил результаты уже сохранённого соревнования** — сохранённые соревнования не обновляются. Удалите соревнование из таблицы `challenge`, и следующий запуск загрузит его заново.

## Разработка

Зависимости меняются вместе с `uv.lock`:

```bash
uv add <package>                  # runtime
uv add --dev <package>            # инструменты разработки
uv add --optional load <package>  # нагрузочные инструменты
uv remove <package>
uv lock --check                   # проверить согласованность manifest и lock
```

После изменения manifest запускайте `uv lock`, коммитьте `pyproject.toml` и
`uv.lock` вместе. Для обычной установки и запуска используйте `--locked`, чтобы
устаревший lock приводил к ошибке, а не менялся незаметно.

Миграции:

```bash
uv run --locked alembic revision --autogenerate -m "..."   # новая миграция
uv run --locked alembic check                              # схема моделей совпадает с миграциями
```

Изменения ведутся через [OpenSpec](https://github.com/Fission-AI/OpenSpec):
- `openspec/specs/` — действующие спецификации;
- `openspec/changes/` — изменения в работе;
- `openspec/changes/archive/` — завершённые изменения.

Подробности об устройстве кода — в [`AGENTS.md`](AGENTS.md).
