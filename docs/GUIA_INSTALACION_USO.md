# Guía Completa de Instalación y Uso — OpenTrading

> **Idioma:** español · **Fecha:** 2026-08-29 · **Audiencia:** cualquier persona que
> instale y use la plataforma desde cero (operadores, investigadores cuantitativos,
> propietarios del riesgo).
>
> **Regla de oro (INV-1):** los LLM investigan, argumentan y proponen; el **código
> determinista decide** si una operación puede ejecutarse. Ninguna guía, comando o
> configuración de esta página otorga a un LLM autoridad sobre el capital.

---

## Índice

1. [Qué es OpenTrading](#1-qué-es-opentrading)
2. [Requisitos previos](#2-requisitos-previos)
3. [Instalación desde cero](#3-instalación-desde-cero)
4. [Verificación de la instalación](#4-verificación-de-la-instalación)
5. [Uso desde cero — primeros pasos](#5-uso-desde-cero--primeros-pasos)
6. [Pipeline PAPER autónomo (simulación)](#6-pipeline-paper-autónomo-simulación)
7. [Backtests deterministas](#7-backtests-deterministas)
8. [Protocolo MT4 y emulador](#8-protocolo-mt4-y-emulador)
9. [Command Center (interfaz web)](#9-command-center-interfaz-web)
10. [Modos LIVE_GATED y LIVE_AUTO (cuenta demo)](#10-modos-live_gated-y-live_auto-cuenta-demo)
11. [Quant R&D (fábrica de estrategias)](#11-quant-rd-fábrica-de-estrategias)
12. [Observabilidad: métricas, trazas y paneles](#12-observabilidad-métricas-trazas-y-paneles)
13. [Operación diaria y recuperación](#13-operación-diaria-y-recuperación)
14. [Configuración de referencia](#14-configuración-de-referencia)
15. [Seguridad: qué hacer y qué no hacer jamás](#15-seguridad-qué-hacer-y-qué-no-hacer-jamás)
16. [Solución de problemas](#16-solución-de-problemas)
17. [Documentación de referencia](#17-documentación-de-referencia)

---

## 1. Qué es OpenTrading

Plataforma autónoma de trading cuantitativo: investiga estrategias, las valida,
las negocia en papel (PAPER) y finalmente ejecuta vía MetaTrader 4, **sin que
ningún LLM controle el dinero**.

Los cinco modos de operación (INV-8, nunca cambiables en caliente):

| Modo | Qué hace | ¿Dinero real? |
|---|---|---|
| `RESEARCH` | datos + análisis | No |
| `BACKTEST` | backtests deterministas (Nautilus) | No |
| `PAPER` | pipeline autónomo sobre un simulador | No (cuenta de papel) |
| `LIVE_GATED` | MT4 real, **cada orden requiere aprobación humana** | Sí (cuenta demo primero) |
| `LIVE_AUTO` | MT4 real sin aprobación por operación, gobernado por el registro determinista | Sí (solo estrategias promovidas) |

**Estado actual (auditoría 2026-08-29, `docs/PRODUCTION_READINESS.md`):** todo el
núcleo determinista está implementado y probado (1185+ tests verdes), pero **la
plataforma no está declarada lista para capital real**: el bridge EA aún no está
construido y nunca se ha conectado un broker real. Esta guía cubre instalación y
uso **hasta demo/emulador**, que es lo que hoy puede ejecutarse.

---

## 2. Requisitos previos

| Herramienta | Versión mínima | Verificación |
|---|---|---|
| Linux (recomendado) o macOS | — | `uname -a` |
| Git | 2.x | `git --version` |
| Docker + Compose v2 | ≥ 2.24 (soporta `!reset`) | `docker compose version` |
| uv | ≥ 0.5 | `uv --version` |
| Python | 3.12 (lo gestiona uv automáticamente) | `uv run python --version` |
| Node.js (solo Command Center) | ≥ 20 | `node --version` |
| `gitleaks` + `pip-audit` (solo CI/auditoría) | — | opcional |
| SOPS + age (solo producción) | — | `scripts/secrets/setup-age.sh` |

> En una máquina **sin Docker** (como algunos VPS de desarrollo) no podrás
> levantar la infraestructura local, pero sí ejecutar todo el ciclo PAPER en
> memoria (`run-once`, §5) y toda la suite de tests unitarios.

> **¿Instalando en Windows con un cliente MT4 real?** Esta guía asume
> Linux/macOS. Usa `docs/runbooks/local-development-windows.md` (inglés): Core
> Platform dentro de WSL2 + terminal MT4 nativo en Windows — la topología real
> del proyecto (Core en Linux, MT4 en Windows). Nota importante que esa página
> explica en detalle: `QuantBridgeEA.mq4` todavía no existe (§8 de esta guía),
> así que "instalar MT4" hoy te deja el terminal listo pero sin conectar; el
> ciclo completo se prueba contra el emulador Python (§8).

---

## 3. Instalación desde cero

```bash
# 1. Clonar el repositorio
git clone <url-del-repo> OpenTrading
cd OpenTrading

# 2. Crear .env desde la plantilla (valores de desarrollo, no son secretos)
make env-file          # equivalente a: cp .env.example .env

# 3. Instalar el entorno Python 3.12 con todas las dependencias
make setup             # equivalente a: uv sync --all-groups

# 4. Levantar TODA la infraestructura local (PostgreSQL/TimescaleDB, Redis,
#    MinIO, FalkorDB, ClickHouse, Langfuse, MLflow, Prometheus, Grafana),
#    crear los buckets de MinIO y aplicar las migraciones de base de datos.
make up                # bloquea hasta que todos los servicios estén sanos
```

`make up` hace tres cosas, en orden:

1. `docker compose up -d --build --wait` — arranca todos los servicios y espera
   a que **todas** las comprobaciones de salud estén verdes.
2. Crea los buckets MinIO (`raw`, `bronze`, `silver`, `gold`, `mlflow-artifacts`,
   `langfuse`, `posttrade-artifacts`).
3. `alembic upgrade head` — aplica las 9 migraciones (la última, `0009`, hace la
   pista de auditoría inmutable a nivel de base de datos).

La primera ejecución descarga imágenes pinned y construye la imagen de MLflow:
puede tardar unos minutos. Es idempotente: puedes repetirla.

### Endpoints locales (solo accesibles desde 127.0.0.1)

| Servicio | URL | Usuario / contraseña (dev) |
|---|---|---|
| PostgreSQL (TimescaleDB) | `127.0.0.1:5432` · BD `opentrading` | `opentrading` / `opentrading-dev` |
| Redis | `127.0.0.1:6379` | password `opentrading-dev` |
| MinIO S3 / Consola | `:9000` / `:9001` | `opentrading` / `opentrading-dev` |
| FalkorDB | `127.0.0.1:6380` | `falkordb-dev` |
| ClickHouse | `127.0.0.1:8123` | `clickhouse` / `clickhouse-dev` |
| Langfuse | `http://127.0.0.1:3000` | `admin@opentrading.local` / `opentrading-dev` |
| MLflow | `http://127.0.0.1:5000` | — |
| Prometheus | `http://127.0.0.1:9090` | — |
| Grafana | `http://127.0.0.1:3001` | `admin` / `admin-dev` |

Si algún puerto local está ocupado, cambia `OT_*_HOST_PORT` en `.env` y actualiza
el DSN/URL correspondiente.

---

## 4. Verificación de la instalación

```bash
make health     # tabla OK/FAIL de todos los servicios
make test       # suite completa de tests (1185+; los de integración se saltan
                # automáticamente si la pila no está levantada)
make lint       # ruff
make typecheck  # mypy estricto
```

```bash
# Inspección SQL de la pista de auditoría y del estado
docker compose --project-name opentrading-dev -f infra/compose/docker-compose.yml exec postgres \
  psql -U opentrading -d opentrading -c "SELECT count(*) FROM audit_events;"
```

---

## 5. Uso desde cero — primeros pasos

### 5.1 Levantar la API

```bash
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

| Endpoint | Qué devuelve |
|---|---|
| `GET /healthz` | liveness (siempre 200 con el proceso vivo) |
| `GET /readyz` | readiness: sondea Postgres, Redis, MinIO, FalkorDB… 200 si todo OK, 503 con detalle por dependencia |
| `GET /api/v1/contracts` | catálogo de contratos canónicos del dominio |
| `GET /api/v1/market-data/instruments` | registro normalizado de instrumentos |
| `GET /api/v1/market-data/bars?instrument_id=&timeframe=&as_of=&dataset_version=` | barras **point-in-time** (INV-3): `as_of` y `dataset_version` obligatorios |
| `GET /api/v1/market-data/snapshots/{instrument_id}?timeframe=&as_of=&dataset_version=` | `MarketSnapshot` con su hash determinista |

### 5.2 Primer ciclo PAPER (sin infraestructura, todo en memoria)

El pipeline completo — investigación → fusión de señales → propuesta → motor de
riesgo → intención de orden → ejecución simulada → posiciones → post-trade —
en un solo comando determinista:

```bash
uv run python -m apps.worker run-once --llm mock
```

Salida esperada (resumida):

```
run-once complete: 14 events produced
pipeline runs recorded: 9
  lifecycle EURUSD: POSITION_OPEN
  account: balance=100000 equity=99998.00000 realized=0
```

Opciones útiles:

```bash
--llm mock|live|off     # mock = LLM simulado determinista; live = TradingAgents real
--cycles N              # cuántos ciclos encadenados (p. ej. 3 → apertura, cierre, revisión)
--seed N                # semilla (mismo seed ⇒ mismo resultado)
--store memory|postgres # persistencia en memoria o PostgreSQL
--bus memory|redis      # bus de eventos en memoria o Redis Streams
```

Ejemplo: tres ciclos completos con cierre y revisión post-trade:

```bash
uv run python -m apps.worker run-once --llm mock --cycles 3 --seed 42
# → lifecycle EURUSD: POSITION_OPEN → … → REVIEWED
# → post-trade reviews recorded: 1  (con artefacto en MinIO y nota en la bóveda)
```

### 5.3 Prueba de la suite de caos (escenarios de fallo)

```bash
uv run pytest tests/chaos
# → caídas de Redis/Postgres/MinIO/FalkorDB/LLM, caída del worker a mitad de
#   etapa, partición de red, rellenos parciales del broker… (25 escenarios)
```

---

## 6. Pipeline PAPER autónomo (simulación)

Modo no atendido sobre la pila real (Redis Streams + PostgreSQL, recuperable tras
caídas):

```bash
OT_PAPER_MODE_ENABLED=true uv run python -m apps.worker run \
    --store postgres --bus redis --llm mock
```

- `--llm live` usa el adaptador TradingAgents real (pinned, con timeouts y
  reintentos). `OT_PAPER_LLM_REQUIRED=true` salta ciclos cuando el LLM no está
  disponible (por defecto el ciclo continúa con la política de señal ausente).
- Los workers usan grupos de consumidores de Redis (`opentrading-workers:<etapa>`)
  y al arrancar recuperan sus mensajes pendientes (`XAUTOCLAIM`) procesándolos de
  forma idempotente. Mensajes envenenados → `opentrading:events:dead:<grupo>` tras
  `OT_PAPER_MAX_DELIVERIES` (5 por defecto).
- Inspección del estado:

```sql
SELECT * FROM pipeline_runs      ORDER BY started_at DESC LIMIT 20;
SELECT * FROM trade_lifecycles   ORDER BY updated_at DESC LIMIT 20;
SELECT * FROM paper_accounts;
SELECT * FROM execution_orders   ORDER BY created_at DESC LIMIT 20;
SELECT * FROM execution_positions;
```

- Parada segura: `Ctrl-C`. Nunca hace falta un apagado limpio.

Detalle completo: `docs/runbooks/paper-pipeline.md`.

---

## 7. Backtests deterministas

```bash
uv run python -m adapters.nautilus.cli --seed 42
```

Imprime huellas de reproducibilidad (`input_hash`, `output_hash`). **Ejecuta el
mismo comando dos veces: los hashes deben ser idénticos** — esa es la Definición
de Hecho del backtest. La suite `tests/backtest/` cubre determinismo entre
procesos, costes (comisión/slippage), contabilidad de posiciones a doble libro
(ledger propio = venue) y rechazos.

Límites conocidos (documentados en `docs/KNOWN_LIMITATIONS.md`): solo FX, cuentas
en la divisa cotizada/base del par; el backtest de línea base emite intenciones
con `risk_decision_id` sintético (no pasa por el Motor de Riesgo, por diseño de
simulación).

---

## 8. Protocolo MT4 y emulador

El puente MT4 es un protocolo versionado (ADR-0020) sobre ZeroMQ privado. Puedes
practicar el ciclo de vida completo **sin MetaTrader instalado**:

```bash
# Smoke test: suscribe/rellena/cancela/modifica/rechaza/reconcilia/latido
# sobre sockets ZeroMQ reales de loopback. Exit 0 = todo correcto.
uv run python -m adapters.mt4.cli smoke

# Emulador persistente (sustituto de QuantBridgeEA.mq4 durante el desarrollo):
uv run python -m adapters.mt4.cli run
#   command: tcp://127.0.0.1:5555   events: tcp://127.0.0.1:5556   quotes: tcp://127.0.0.1:5557
```

Garantía clave (INV-6): el mismo `order_intent_id` enviado 100 veces genera como
máximo **una** operación. La reconciliación obligatoria de arranque
(`reconcile-once`, §13) compara órdenes/posiciones/cantidades/identificadores con
el broker y entra en SAFE_MODE ante divergencia material.

---

## 9. Command Center (interfaz web)

Panel de monitorización en TypeScript/React. **Sin lógica de trading en el
cliente** — consume proyecciones de solo lectura de la API.

```bash
cd apps/command-center
npm install
npm run dev          # proxy de /api → http://127.0.0.1:8000
```

- Con la API en otro sitio: `VITE_API_ROOT=<url> npm run build` y sirve `dist/`.
- Secciones: Overview, Research, Signals, Risk, Orders & Trades, Memory,
  Backtests, Agents, System. Las capacidades no disponibles se muestran
  honestamente (nunca datos sintéticos).
- Arranca primero la API (`uv run uvicorn apps.api.main:app --reload`).

---

## 10. Modos LIVE_GATED y LIVE_AUTO (cuenta demo)

> ⚠️ Estos modos existen y están probados contra el emulador, pero **la plataforma
> no está declarada lista para capital real** (sin EA, sin broker conectado).
> Úsalos solo contra el emulador o una cuenta demo, nunca con dinero real sin
> completar las puertas de `docs/PRODUCTION_READINESS.md`.

### 10.1 LIVE_GATED — aprobación humana por operación

1. Añade al entorno los secretos (mínimo 32 caracteres, si no la configuración
   **falla al arrancar**):

```bash
export OT_OPERATING_MODE=LIVE_GATED
export OT_LIVE_OPERATOR_TOKEN="<token-de-operador-≥32-caracteres>"
export OT_LIVE_APPROVAL_SIGNING_KEY="<clave-de-firma-≥32-caracteres>"
```

2. Levanta la API: `uv run uvicorn apps.api.main:app --port 8000`. Las rutas de
   mutación solo se montan si los secretos existen.

3. Flujo: la intención de orden entra en `WAITING_FOR_HUMAN` con el contexto de
   precio (cotización) hasheado en la aprobación. El operador decide:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/live-gated/approvals/<order_intent_id>/approve \
     -H "Authorization: Bearer $OT_LIVE_OPERATOR_TOKEN"
curl -X POST http://127.0.0.1:8000/api/v1/live-gated/approvals/<order_intent_id>/reject \
     -H "Authorization: Bearer $OT_LIVE_OPERATOR_TOKEN"
```

La aprobación es HMAC-vinculada a la intención, expira según
`OT_LIVE_APPROVAL_TTL_SECONDS` (30 s por defecto) y **solo puede consumirse una
vez**. Un movimiento material del mercado obliga a revalidar y a una **nueva**
decisión humana. La firma manipulada o caducada nunca llega al broker.

4. Kill switches:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/live-gated/kill-switches \
     -H "Authorization: Bearer $OT_LIVE_OPERATOR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"scope":"EMERGENCY","reason":"incidente"}'
```

### 10.2 LIVE_AUTO — gobernanza determinista sin aprobación por operación

1. `OT_OPERATING_MODE=LIVE_AUTO`, `OT_LIVE_AUTO_ENABLED=true`,
   `OT_LIVE_AUTO_MAX_STRATEGIES=1`, `OT_LIVE_AUTO_MAX_CAPITAL>0`,
   `OT_LIVE_AUTO_MAX_LOSS>0` y `OT_LIVE_OPERATOR_TOKEN` (≥32 caracteres).
2. **Promover** una estrategia (solo desde `LIVE_GATED`, solo con token de
   operador; escribe un evento de auditoría inmutable):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/live-auto/promotions \
     -H "Authorization: Bearer $OT_LIVE_OPERATOR_TOKEN" -H "Content-Type: application/json" \
     -d '{"strategy_id":"strategy-a","strategy_version":"1.0.0","from_state":"LIVE_GATED",
          "risk_budget":500,"capital_allocation":5000,"evidence":["walk-forward-ok"]}'
```

3. Cada orden automatizada sigue pasando por: Motor de Riesgo obligatorio
   (APPROVE/RESIZE con cantidades exactas), límite de pérdidas global (ledger
   de PnL de solo anexado), presupuesto por estrategia, frescura de cotización y
   controles de seguridad locales de MT4. El modo **nunca** puede cambiarse en
   caliente (ni por API, ni por LLM).

### 10.3 Controles de emergencia y dead man switch (INV-7)

Cuatro niveles: `STRATEGY_KILL` / `INSTRUMENT_KILL` (dirigidos),
`NO_NEW_POSITIONS`, `EMERGENCY_KILL` (cancela pendientes + bloquea entradas; el
cierre forzoso solo si `OT_EMERGENCY_FLATTEN_ON_KILL=true`).

- Pérdida de latido Core↔MT4 → se bloquean nuevas entradas, los SL/TP del broker
  quedan intactos, alerta CRÍTICA y estado seguro persistido. **La pérdida de
  conectividad jamás cierra posiciones automáticamente** salvo que la política lo
  pida explícitamente.
- Monitor apto para cron: `uv run python -m engines.execution.cli check-emergency`
  (exit 2 = estado seguro activo → alerta).

---

## 11. Quant R&D (fábrica de estrategias)

Runtime separado Python 3.11 (INV-13) con RD-Agent + Qlib + MLflow, **confinado**:
contenedor sin root, solo lectura, sin capacidades, en red interna de
investigación, sin acceso a broker/MT4 ni credenciales, y sin poder modificar
producción. Solo escribe en `/workspace` y `/outputs`.

```bash
docker compose -f services/quant-rd/compose.yml run --rm quant-rd fin_quant
# workflows disponibles: fin_factor | fin_model | fin_quant
```

Configuración de experimento: `services/quant-rd/config.example.json`
(`OT_RESEARCH_CONFIG`). Los candidatos (`StrategyCandidate`) se escriben en
`/outputs` y **ningún componente de producción los lee automáticamente**: la
promoción a PAPER/LIVE exige la fábrica de validación determinista
(`engines/promotion`, 14 etapas: walk-forward, purga, embargo, Monte Carlo,
controles de testeo múltiple…) y una acción administrativa registrada.

---

## 12. Observabilidad: métricas, trazas y paneles

- **Métricas Prometheus:** `GET http://127.0.0.1:8000/metrics` — duración/errores
  por etapa del pipeline, latencia de ejecución, edad del latido MT4
  (`mt4_heartbeat_age_seconds`), posiciones inesperadas del broker, retraso Redis
  por grupo de consumidores. Paneles: Grafana `http://127.0.0.1:3001`.
- **Langfuse:** `http://127.0.0.1:3000` — una traza por etapa del pipeline; el id
  W3C deriva del `trace_id` del dominio; metadatos filtrados por lista blanca;
  degrada a no-op ante fallo. **Nunca** pongas secretos, credenciales ni material
  del broker en prompts/trazas de Langfuse.
- **Logs:** filtro de redacción instalado en API, worker y ejecución — los
  secretos quedan enmascarados aunque un handler esté mal configurado.
- **Readiness:** `GET /readyz` con desglose por dependencia (útil para
  balanceadores y health checks de orquestadores).

---

## 13. Operación diaria y recuperación

```bash
# Reconciliación obligatoria (INV-6): 7 pasos contra el broker.
# exit 0 = limpia; exit 2 = broker inalcanzable o SAFE_MODE → avisar.
uv run python -m engines.execution.cli reconcile-once

# Dead man switch apto para cron/systemd-timer (exit 2 = alerta)
uv run python -m engines.execution.cli check-emergency

# Copias de seguridad (PostgreSQL + MinIO) — ver docs/DISASTER_RECOVERY.md
OT_BACKUP_DIR=/var/backups/opentrading ./scripts/backup.sh

# Restauración (rechaza sobrescribir una BD no vacía sin OT_RESTORE_FORCE=1)
OT_RESTORE_DUMP=<ruta.dump> OT_RESTORE_MINIO_SRC=<ruta/buckets> \
  OT_RESTORE_FORCE=1 ./scripts/restore.sh

# Migraciones
uv run alembic upgrade head      # como rol ot_migrator en producción
uv run alembic history           # ver la cadena (head = 0009)
```

Parada de la pila: `make down` (los volúmenes sobreviven) · Reinicio destructivo
solo dev: `make reset-dev` (⚠️ destruye todos los volúmenes).

Recuperación de workers PAPER: al rearrancar, cada grupo reclama su PEL y
reprocesa de forma idempotente; los mensajes envenenados quedan en
`opentrading:events:dead:<grupo>` (revisar con `XRANGE … - +` y reenviar con
`XADD` tras corregir la causa). Ver `docs/DISASTER_RECOVERY.md` para los 8
escenarios de incidente.

---

## 14. Configuración de referencia

Todo se configura con variables `OT_*` (fichero `.env`). Resumen de las más
usadas (completas en `.env.example`):

| Variable | Default | Significado |
|---|---|---|
| `OT_OPERATING_MODE` | `RESEARCH` | Modo: RESEARCH/BACKTEST/PAPER/LIVE_GATED/LIVE_AUTO |
| `OT_POSTGRES_DSN` | dev local | DSN de aplicación (rol `ot_app` en prod) |
| `OT_POSTGRES_MIGRATOR_DSN` | — | DSN con DDL para Alembic (`ot_migrator` en prod) |
| `OT_REDIS_URL` | dev local | Redis (usuario ACL en prod) |
| `OT_FALKORDB_URL` | dev local | FalkorDB (memoria temporal) |
| `OT_MINIO_*` | dev local | endpoint + credenciales scoped en prod |
| `OT_PAPER_MODE_ENABLED` | `false` | Habilita el pipeline PAPER |
| `OT_PAPER_CYCLE_INTERVAL_SECONDS` | `300` | Cadencia de investigación |
| `OT_PAPER_STARTING_BALANCE` | `100000` | Semilla de la cuenta de papel |
| `OT_PAPER_LLM_REQUIRED` | `false` | `true` salta ciclos si el LLM falla |
| `OT_PAPER_MAX_DELIVERIES` | `5` | Umbral de dead-letter |
| `OT_MT4_COMMAND_ADDR` / `_EVENTS_` / `_QUOTES_` | loopback | Canales ZeroMQ privados (WireGuard hacia MT4 remoto) |
| `OT_LIVE_AUTO_*` | deshabilitado | Límites duros del modo automático |
| `OT_EMERGENCY_*` | dead man activado | Timeout de latido, cancelación y flattening opcional |
| `OT_MT4_HEARTBEAT_INTERVAL_SECONDS` | `1.0` | Latido Core↔MT4 |

---

## 15. Seguridad: qué hacer y qué no hacer jamás

- ✅ Los secretos de producción viven solo en `secrets/*.env` cifrados con
  SOPS+age (`scripts/secrets/{setup-age,encrypt,decrypt,verify}.sh`); `.env`,
  `secrets/`, `*.key`, `*.pem` están en `.gitignore`.
- ✅ Producción: `make up-prod` con `.env.prod` — red interna, **sin puertos
  publicados**; falla cerrado si falta un secreto. Roles de Postgres de mínimo
  privilegio (`ot_migrator` DDL / `ot_app` DML / `ot_readonly` SELECT), Redis con
  ACL, MinIO con políticas por bucket, FalkorDB con contraseña.
- ✅ La pista de auditoría (`audit_events`, `system_events`) es **inmutable a
  nivel de base de datos** (migración 0009): ni el dueño de la tabla puede
  modificarla.
- ✅ CI: gitleaks + pip-audit en cada push; dependencias pinned en `uv.lock` y
  `external-lock.yaml`.
- ❌ **Jamás** des credenciales del broker/MT4, sockets de ejecución o secretos a
  un proceso LLM, un prompt, Langfuse u Obsidian.
- ❌ **Jamás** expongas la API ni los canales ZeroMQ a internet (solo red privada
  / WireGuard).
- ❌ **Jamás** cambies `OT_OPERATING_MODE` en caliente: un cambio de modo es un
  redespliegue con registro de auditoría.
- ❌ **Jamás** calcules el tamaño de una orden a partir de salida de LLM: las
  cantidades las calcula solo el Motor de Riesgo (INV-1).

---

## 16. Solución de problemas

| Síntoma | Causa probable / solución |
|---|---|
| `make up` expira la primera vez | Descarga inicial de imágenes lenta; repite (es idempotente) |
| Langfuse unhealthy mucho rato | Mira `make logs SERVICE=langfuse-worker`; aplica sus migraciones al primer arranque |
| Conflicto de puerto 5432/6379/… | Otro servicio local lo usa; páralo o cambia `OT_*_HOST_PORT` + el DSN/URL |
| API 401 en endpoints live | Token ≥32 caracteres y cabecera `Authorization: Bearer <token>` exacta |
| El worker se niega a arrancar en LIVE_* | Es **correcto**: guardián de zona de confianza (ADR-0025); los modos live corren en el servicio de ejecución, no en el worker LLM |
| Inundación de `pipeline.stage.failed` | Mira `pipeline_runs.error`, pendientes del PEL y `opentrading:events:dead:*` |
| SAFE_MODE activo | Mira `reconciliation_runs` (códigos de discrepancia), `check-emergency` y `mt4_heartbeat_age_seconds` |
| Desviación de la cuenta de papel | Compara `execution_orders` vs `execution_positions` vs `trade_lifecycles`; rearranca (los niveles SL/TP se reenganchan al cargar) |
| Búsqueda de Graphiti vacía tras reinicio | Limitación conocida (índice en memoria): re-ingesta los episodios |
| Quant R&D falla al arrancar | Guardián de entorno o de versión Python (requiere 3.11) — lee el mensaje |
| `init_id` / error UUID4 en Nautilus | No reemplaces el `init_id` aleatorio por un UUID no-v4: Nautilus exige versión 4 |

---

## 17. Documentación de referencia

| Documento | Contenido |
|---|---|
| `docs/PRODUCTION_READINESS.md` | Auditoría de producción, veredicto y puertas abiertas |
| `docs/KNOWN_LIMITATIONS.md` | Limitaciones clasificadas (BLOQUEO/MAYOR/MENOR/INFO) |
| `docs/OPERATIONS_MANUAL.md` | Manual de operación completo (inglés) |
| `docs/DISASTER_RECOVERY.md` | RPO/RTO, backups, restauración y playbooks de incidente |
| `docs/runbooks/local-development.md` | Entorno de desarrollo (inglés) |
| `docs/runbooks/local-development-windows.md` | Entorno de desarrollo en Windows + terminal MT4 real (inglés) |
| `docs/runbooks/paper-pipeline.md` | Pipeline PAPER en detalle (inglés) |
| `docs/runbooks/infrastructure.md` | Infraestructura compose y producción (inglés) |
| `docs/runbooks/observability-alerts.md` | Alertas y paneles (inglés) |
| `docs/runbooks/secrets-management.md` | Gestión de secretos SOPS+age (inglés) |
| `docs/architecture.md` | Arquitectura canónica (español, autoritativa) |
| `docs/ADR/` | 26 decisiones congeladas |
| `.ai/rules/architecture-invariants.md` | Invariantes INV-1…INV-16 (no negociables) |

**Camino de aprendizaje sugerido:** §3 instalación → §5 primer ciclo PAPER →
§7 backtest determinista → §8 emulador MT4 → §6 pipeline PAPER completo → §10
demo LIVE_GATED → §13 operación diaria.
