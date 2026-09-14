# Cyberdeck

Набор скриптов для деки. Каждый инструмент — отдельный шаг, который можно
поставить в цепочку: все говорят на одном JSON-диалекте `cyberdeck.v1`.

```
Cyberdeck/
├── cyberdeck/          общая библиотека
│   ├── envelope.py     единый формат ввода/вывода
│   ├── proc.py         запуск внешних тулов с живым выводом
│   └── ui.py           консоль, прогресс, отчёты
├── scripts/
│   ├── portscan.py     masscan (все порты) -> nmap -sV (сервисы)
│   ├── vlessparse.py   разбор VLESS/trojan/vmess/ss в конверт (без сети)
│   ├── ipscan.py       TCP-доступность + geo/ASN, чистый Python (без root)
│   └── adduser.py      завести пользователя на сервере по SSH
├── build.py            сборка самодостаточных версий в dist/
└── dist/               однофайловые сборки (curl | python3 -)
```

## Установка

```bash
pip install -r requirements.txt        # rich, для прогресса и таблиц
sudo apt install masscan nmap          # WSL / Debian / Ubuntu
```

Без `rich` скрипты работают, просто вывод будет обычным текстом.

## Контракт пайпов

Правило одно и жёсткое:

| канал | что там |
|-------|---------|
| **stdout** | только данные: JSON при `--json`, иначе человекочитаемый отчёт |
| **stderr** | логи, прогресс, баннеры, ошибки |

Любой скрипт умеет читать `stdin`: конверт `cyberdeck.v1`, голый JSON-список
или просто список адресов построчно. Поэтому работает и `cat hosts.txt | ...`,
и `./a.py --json | ./b.py --json`.

Конверт:

```jsonc
{
  "schema": "cyberdeck.v1",
  "tool": "portscan",
  "run_id": "a1b2c3d4e5f6",
  "status": "ok",              // ok | partial | error
  "started_at": "...", "finished_at": "...", "duration_sec": 42.1,
  "params": { ... },           // чем запускали
  "targets": ["10.0.0.1"],
  "hosts": [                   // ← главный носитель данных цепочки
    {
      "ip": "10.0.0.1",
      "hostnames": ["srv01.local"],
      "state": "up",
      "ports": [
        { "port": 22, "proto": "tcp", "state": "open", "source": "nmap",
          "service": "ssh", "product": "OpenSSH", "version": "9.6p1",
          "cpe": ["cpe:/a:openbsd:openssh:9.6p1"] }
      ]
    }
  ],
  "stats": { "targets": 1, "hosts_with_ports": 1, "open_ports": 5 },
  "warnings": [], "errors": []
}
```

Следующий инструмент в цепочке читает `hosts`, дописывает свои поля в порты и
отдаёт тот же конверт дальше. Поле `source` показывает, кто добавил данные
(`masscan`, `nmap`, `input`).

Код возврата: `0` — всё хорошо, `1` — `partial`/`error`, `2` — плохие аргументы,
`127` — нет нужного бинаря.

## portscan

Два этапа: masscan прочёсывает весь диапазон портов, найденное уходит в
`nmap -sV` поштучно по хостам.

```bash
# один хост, все 65536 портов
sudo ./scripts/portscan.py 10.0.0.1

# подсеть побыстрее, результат в файл и в stdout
sudo ./scripts/portscan.py 10.0.0.0/24 --rate 5000 --json -o scan.json

# список из файла
cat hosts.txt | sudo ./scripts/portscan.py --sudo --json > scan.json

# только веб-порты, с NSE-скриптами
sudo ./scripts/portscan.py 10.0.0.1 -p 80,443,8000-8100 -sC

# перепроверить сервисы по готовому конверту, без masscan
cat scan.json | ./scripts/portscan.py --skip-discovery --sudo --json
```

Основные флаги:

| флаг | зачем |
|------|-------|
| `-p, --ports` | диапазон для masscan, по умолчанию `0-65535` |
| `--rate` | пакетов/сек, по умолчанию 1000 — поднимай осторожно |
| `-i, --interface` | интерфейс для masscan |
| `--nmap-args` | база для nmap, по умолчанию `-sV -Pn -T4` |
| `-sC, --scripts` | добавить стандартные NSE-скрипты |
| `--masscan-grace` | сколько ждать выхода masscan после 100%, по умолчанию `--wait + 10` |
| `--skip-discovery` | без masscan: порты берутся со stdin или из `--ports` |
| `--skip-nmap` | только быстрый поиск портов |
| `--sudo` | звать masscan/nmap через sudo (сначала прогрей: `sudo -v`) |
| `--json` | конверт в stdout |
| `-o, --out` | сохранить JSON в файл |
| `--raw-dir` | сложить сырые выхлопы masscan/nmap |
| `-v` / `-q` | сырые строки тулов / тишина |

### Если masscan завис

masscan регулярно доходит до 100%, отдаёт все найденные порты и не завершается —
под WSL особенно. Порты к этому моменту уже собраны, ждать нечего, поэтому за ним
следит сторож: через `--masscan-grace` секунд после 100% (либо после долгой
тишины) процесс снимается, и скан идёт на этап 2 с тем, что нашли.

Запись об этом всегда падает в `warnings`, а `status` зависит от того, успел ли
masscan отчитаться о 100%: успел — диапазон пройден целиком, статус остаётся
`ok`; онемел раньше — часть портов осталась непроверенной, статус `partial`.

`Ctrl+C` во время masscan работает так же — не обрывает всё, а говорит «хватит
искать, показывай сервисы по найденному». Второй `Ctrl+C`, уже на этапе nmap,
завершает скан и печатает то, что успели собрать.

### Про права

masscan работает с raw-сокетами, `nmap -sV`/`-sU` тоже хочет root. Запускай под
`sudo` целиком либо передавай `--sudo`. Во втором случае stdin занят пайпом, и
sudo не сможет спросить пароль — сделай заранее `sudo -v`, скрипт это проверяет
и скажет, если тикета нет.

## vlessparse

Разбирает подписки прокси в конверт `cyberdeck.v1`. Сеть не трогает — только
парсинг. Каждый конфиг это эндпоинт `host:port`, поэтому сервер уходит в `hosts`,
а полный разбор (uuid, sni, security, type, flow, pbk/sid, remark) копится в
`host["configs"]` — дубли на одном адресе не теряются.

Разбор идёт через `urllib.urlsplit`, а не regex по `@host:` — берётся настоящий
порт, IPv6 в скобках, домены и все query-параметры. Кроме `vless://` понимает
`trojan://`, `vmess://` (base64-JSON) и `ss://` (SIP002). Битые строки уходят в
`warnings`, статус остаётся `ok`, пока разобран хоть один конфиг.

```bash
# посмотреть, что внутри подписки
cat sub.txt | ./scripts/vlessparse.py

# конверт дальше по цепочке в сканер
./scripts/vlessparse.py sub.txt --json | ./scripts/ipscan.py --geo --json

# только адреса host:port построчно — для masscan/portscan и прочего
cat sub.txt | ./scripts/vlessparse.py --targets | sudo ./scripts/portscan.py --json

# оставить только vless и схлопнуть дубли эндпоинтов
cat sub.txt | ./scripts/vlessparse.py --scheme vless --unique --json
```

| флаг | зачем |
|------|-------|
| `--scheme NAME` | оставить только эти схемы (повторяемый): `vless/trojan/vmess/ss` |
| `--unique` | схлопнуть эндпоинты `host:port` до уникальных |
| `--json` | конверт в stdout |
| `--targets` | печатать только уникальные `host:port` построчно |
| `-o, --out` | сохранить JSON в файл |
| `-v` / `-q` | причины отбраковки / тишина |

## ipscan

Лёгкий TCP-скан доступности плюс geo/ASN-обогащение. Чистый Python: без root, без
masscan — соединяется с каждым `host:port`, помечает `open`/`closed`/`filtered`,
по флагу `--geo` узнаёт владельца через ip-api.com и группирует по провайдеру и
подсети `/16`.

Порты берутся **из входного конверта** (реальные порты VLESS, а не хардкод `:80`);
для голых адресов — из `-p` (по умолчанию `80,443`). Понимает IP, домены, IPv6 и
`host:port`-токены. Метаданные входа (`configs`, `hostnames`) проносятся в выход,
чтобы цепочка не теряла разбор.

```bash
# один хост
echo 1.1.1.1 | ./scripts/ipscan.py -p 80,443,8443

# полный флоу: подписка -> живые с провайдером
cat sub.txt | ./scripts/vlessparse.py --json | ./scripts/ipscan.py --geo --json > alive.json

# только живые в выходе
./scripts/ipscan.py 8.8.8.8 1.1.1.1 --geo --alive-only
```

| флаг | зачем |
|------|-------|
| `-p, --ports` | порты для голых адресов без порта (по умолчанию `80,443`) |
| `-t, --timeout` | таймаут коннекта в секундах (`3.0`) |
| `-c, --concurrency` | одновременных проб (`100`) |
| `--geo` | узнать владельца/страну через ip-api.com |
| `--alive-only` | оставить в выводе только живые хосты |
| `--json` | конверт в stdout |
| `-o, --out` | сохранить JSON в файл |
| `-v` / `-q` | каждая проба / тишина |

`ipscan` не требует прав и не зависит от внешних бинарей, поэтому едет и на голой
системе, и на Windows. `--geo` бьёт по бесплатному ip-api.com (лимит ~15
батчей/мин) — при офлайне скан не падает, просто без обогащения.

## adduser

Заводит пользователя на удалённом сервере по SSH одним вызовом. Подключается
системным `ssh` (без зависимостей — работают `~/.ssh/config`, ключи, ssh-agent,
known_hosts), на сервере прогоняет идемпотентный bash. Скрипт уходит по
зашифрованному stdin в `bash -s`, а не через argv, поэтому секреты не светятся в
`ps` на сервере.

```bash
# обычный пользователь, вход по ключу
./scripts/adduser.py root@1.2.3.4 -u deploy --ssh-key-file id.pub

# админ (в группу sudo/wheel) со сгенерированным паролем
./scripts/adduser.py 10.0.0.5 -u ops --admin --random-password

# сервисный пользователь: sudo без пароля, вход по ключу
./scripts/adduser.py root@host -u ci --nopasswd-sudo --ssh-key-file ci.pub

# раскатать сразу по всем живым хостам из цепочки
./scripts/ipscan.py hosts.txt --alive-only --json | ./scripts/adduser.py -u ci --ssh-key-file ci.pub

# показать удалённый скрипт и никуда не подключаться (пароль скрыт)
./scripts/adduser.py root@host -u test --admin --random-password --dry-run
```

Запуск идемпотентный: если пользователь уже есть — не пересоздаётся, но ключ,
группы и sudo доедут, а дубликат ключа в `authorized_keys` не добавится. Пароль
трогается только когда явно задан флаг.

| флаг | зачем |
|------|-------|
| `-u, --user` | имя пользователя (обязательно) |
| `--ssh-user` | логин для SSH (по умолчанию `root`) |
| `-i, --identity` / `-p, --ssh-port` | ключ / порт для SSH |
| `--become` | выполнять на сервере через `sudo -n` (если логин не root) |
| `--admin` | добавить в группу `sudo`/`wheel` (авто-детект) |
| `--nopasswd-sudo` | `sudo` без пароля (drop-in в `sudoers.d`, проверка `visudo`) |
| `--random-password` | сгенерировать пароль и показать (в stderr; в JSON — только с `--show-secrets`) |
| `--ask-password` | спросить пароль скрытым вводом |
| `--password PLAIN` | задать пароль строкой (виден в `ps`/history локально) |
| `--lock` | заблокировать пароль (вход только по ключу) |
| `--ssh-key` / `--ssh-key-file` | публичный ключ строкой или из файла |
| `-G, --groups` `--uid` `--shell` `--gecos` `--home` | параметры useradd |
| `--dry-run` | показать удалённый скрипт, не подключаясь |
| `--json` / `-o` / `-q` / `-v` | конверт / файл / тишина / stderr сервера |

Без флага пароля пользователь создаётся с заблокированным паролем — вход только
по ключу (безопасный дефолт). Каждый сервер в конверте это `host` c полем `user`
(что сделали) и журналом `actions`. На сервере нужны стандартные `useradd`,
`chpasswd`, `getent`, а для `--nopasswd-sudo` — `visudo`.

## Автономный запуск (dist/)

Скрипты в `scripts/` живут в связке с пакетом `cyberdeck`, поэтому вытащить один
файл и запустить его в отрыве нельзя — будет `ModuleNotFoundError`. Для «дёрнул
один файл и запустил» есть сборка:

```bash
python build.py       # -> dist/portscan.py, vlessparse.py, ipscan.py, adduser.py
```

`build.py` вклеивает `cyberdeck` (envelope/ui/proc) прямо внутрь каждого скрипта
(base64 + бутстрап в `sys.modules`). На выходе — один самодостаточный `.py` на
чистом стдлибе, который можно раздавать по одному и лить прямо в интерпретатор:

```bash
# цель в аргументах — тогда stdin свободен под сам скрипт
curl -sSL https://raw.githubusercontent.com/ReSenpai/Cyberdeck/main/dist/ipscan.py \
  | python3 - 1.1.1.1 8.8.8.8 --geo

curl -sSL https://raw.githubusercontent.com/ReSenpai/Cyberdeck/main/dist/adduser.py \
  | python3 - root@10.0.0.5 -u deploy --admin --random-password
```

Нюанс: при `curl … | python3 -` сам скрипт уже занимает stdin, поэтому подавать
ему данные ещё и по пайпу нельзя — цели передавай аргументами. Если нужен именно
пайп с данными (`cat sub.txt | … vlessparse | … ipscan`), сначала скачай файлы, а
потом запускай как `python3 ipscan.py …`:

```bash
curl -sSLO https://raw.githubusercontent.com/ReSenpai/Cyberdeck/main/dist/vlessparse.py
curl -sSLO https://raw.githubusercontent.com/ReSenpai/Cyberdeck/main/dist/ipscan.py
cat sub.txt | python3 vlessparse.py --json | python3 ipscan.py --geo --json
```

Исходники не меняем ради сборки — правим `scripts/` и `cyberdeck/`, потом
пересобираем `build.py`. Файлы `dist/` коммитятся в репозиторий, чтобы `curl` с
GitHub работал.