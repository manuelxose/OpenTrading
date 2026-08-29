# Guía definitiva de proyecto

## Autonomous Quantitative Trading & Research Platform

**Versión de arquitectura:** 1.0
**Fecha:** 26 de agosto de 2026
**Objetivo:** construir una firma cuantitativa personal autónoma, auditable y evolutiva capaz de investigar estrategias, validarlas, operar en paper trading y finalmente ejecutar operaciones reales mediante MetaTrader 4 sin conceder a ningún LLM control directo sobre el capital.

---

# 1. Visión final

El sistema deberá funcionar como una pequeña firma cuantitativa institucional:

```text
                         ┌──────────────────────┐
                         │  MARKET / ALT DATA   │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ POINT-IN-TIME DATA   │
                         │      PLATFORM        │
                         └──────────┬───────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
       ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
       │ TradingAgents  │  │ Qlib / Models  │  │ Graphiti       │
       │ qualitative AI │  │ quantitative   │  │ temporal memory│
       └───────┬────────┘  └───────┬────────┘  └───────┬────────┘
               │                   │                   │
               └──────────────┬────┴───────────────────┘
                              ▼
                    ┌────────────────────┐
                    │   SIGNAL FUSION    │
                    └──────────┬─────────┘
                               │
                               ▼
                    ┌────────────────────┐
                    │ DETERMINISTIC RISK │
                    │   + POLICY ENGINE  │
                    └──────────┬─────────┘
                               │
                 APPROVED ONLY │
                               ▼
                      ┌────────────────┐
                      │  ORDER INTENT  │
                      └───────┬────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
       BACKTEST / PAPER                    LIVE
       NautilusTrader                      MT4
                │                           │
                └─────────────┬─────────────┘
                              ▼
                    ┌────────────────────┐
                    │ RECONCILIATION     │
                    │ + POST-TRADE       │
                    └──────────┬─────────┘
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
         Graphiti           PostgreSQL        Obsidian
          memory              truth           journal
```

La arquitectura tiene una regla absoluta:

> **Los LLM investigan, argumentan y proponen. El código determinista decide si una operación puede ejecutarse.**

Esto no se modificará posteriormente.

---

# 2. Qué aprovechamos de cada proyecto

| Proyecto                         | Decisión                              | Papel definitivo                                               |
| -------------------------------- | ------------------------------------- | -------------------------------------------------------------- |
| **TauricResearch/TradingAgents** | **ADOPTAR**                           | Comité de análisis cualitativo/multiagente                     |
| **LangGraph**                    | **ADOPTAR**                           | Orquestación interna de TradingAgents y algunos workflows      |
| **Microsoft Qlib**               | **ADOPTAR**                           | Research cuantitativo, ML, factores, evaluación y experimentos |
| **Microsoft RD-Agent**           | **ADOPTAR OFFLINE**                   | Fábrica autónoma de factores/modelos/hipótesis                 |
| **NautilusTrader**               | **ADOPTAR**                           | Motor event-driven, backtesting y paper trading                |
| **Graphiti**                     | **ADOPTAR**                           | Memoria temporal semántica del sistema                         |
| **FinMem**                       | **EXTRAER IDEAS**                     | Capas de memoria, importancia, reflexión y horizonte cognitivo |
| **Graphify**                     | **ADOPTAR SOLO PARA DESARROLLO**      | Grafo del código y reducción de consumo de contexto            |
| **Obsidian**                     | **ADOPTAR**                           | Base de conocimiento humana y diario de operaciones            |
| **DWX / ZeroMQ MT4 projects**    | **USAR COMO REFERENCIA**              | Diseño del puente MT4                                          |
| **MQL4 WebRequest**              | **NO USAR como transporte principal** | Solo integraciones auxiliares                                  |
| Kafka/Redpanda                   | Más adelante                          | Redis Streams es suficiente inicialmente                       |
| Kubernetes                       | Más adelante                          | Docker Compose primero                                         |

---

# 3. TradingAgents: cerebro cualitativo, no broker

El estado actual de TradingAgents es mucho más completo que sus primeras versiones. Utiliza LangGraph, diferentes proveedores de LLM, analistas especializados, debate bull/bear, risk analysts, Portfolio Manager, checkpoint/resume, structured output y memoria de decisiones.

Su grafo actual incluye herramientas separadas para:

* mercado;
* indicadores;
* snapshot de mercado verificado;
* sentimiento;
* noticias;
* macro;
* insiders;
* prediction markets;
* fundamentales.

La propia implementación central crea clientes LLM, ToolNodes, memoria, reflector, SignalProcessor y grafo LangGraph.

## Decisión arquitectónica

**No debemos reescribir TradingAgents.**

Lo incluiremos detrás de un adapter:

```text
adapters/tradingagents/
    client.py
    mapper.py
    prompts/
    schemas.py
    evaluator.py
```

Nuestro dominio nunca dependerá directamente de sus clases internas.

TradingAgents recibirá:

```python
ResearchRequest(
    instrument=...,
    as_of=...,
    market_snapshot=...,
    portfolio_context=...,
    memory_context=...,
    regime_context=...,
)
```

y devolverá nuestro formato:

```python
LLMSignal(
    instrument=...,
    direction=...,
    conviction=...,
    thesis=...,
    risks=...,
    catalysts=...,
    horizon=...,
    evidence=[...],
    model_metadata=...,
)
```

TradingAgents ya genera propuestas estructuradas con entrada, stop-loss y sizing orientativo en el Trader y ratings en el Portfolio Manager.

Pero esos valores siguen procediendo de un LLM.

Por tanto:

```text
LLM position_sizing ≠ executable size
LLM stop_loss       ≠ automatically accepted stop
LLM BUY             ≠ market order
```

El Portfolio Manager actual termina produciendo un `PortfolioDecision`; no es nuestra capa de ejecución.

---

# 4. Qlib + RD-Agent: fábrica cuantitativa autónoma

TradingAgents analiza una oportunidad.

RD-Agent y Qlib deberán descubrir nuevas oportunidades.

Microsoft Qlib proporciona gran parte de la infraestructura que necesitaríamos desarrollar de cero: procesamiento de datos, modelos, backtesting, análisis cuantitativo, portfolio/risk modelling y experiment tracking.

RD-Agent añade encima una auténtica cadena de I+D autónoma.

Su implementación de Quant actualmente sigue aproximadamente:

```text
Generate hypothesis
       ↓
Factor or Model?
       ↓
Generate experiment
       ↓
Write implementation
       ↓
Run experiment
       ↓
Analyze results
       ↓
Feedback
       ↓
New hypothesis
       ↺
```

El código actual separa explícitamente hypothesis generator, factor/model coder, runner y summarizer/feedback.

## Qué podrá hacer nuestro Quant Factory

```text
Research hypothesis
      ↓
Create factor
      ↓
Backtest
      ↓
Measure IC / RankIC
      ↓
Model experiment
      ↓
Walk-forward
      ↓
Robustness tests
      ↓
StrategyCandidate
```

RD-Agent podrá:

* inventar factores;
* implementar factores;
* crear modelos;
* comparar modelos;
* realizar experimentos;
* producir StrategyCandidates;
* detectar degradación de modelos;
* sugerir nuevas hipótesis;
* abrir PRs con mejoras.

No podrá:

* cambiar límites de riesgo;
* modificar producción automáticamente;
* cambiar el bridge MT4;
* activar LIVE_AUTO;
* desplegar estrategias con dinero;
* reemplazar una estrategia aprobada sin promotion gate.

## Entorno separado

RD-Agent indica soporte Linux y utiliza un stack cuya compatibilidad más segura está en Python 3.10/3.11.

Por eso tendremos dos runtimes:

```text
CORE RUNTIME
Python 3.12

TradingAgents
Graphiti adapters
Nautilus
FastAPI
Risk Engine
Workers
Execution Gateway
```

```text
QUANT R&D
Linux
Python 3.11

RD-Agent
Qlib
MLflow
research environments
```

No intentaremos introducirlo todo en un único virtualenv.

---

# 5. NautilusTrader: columna vertebral del trading

Añadimos NautilusTrader como pieza central porque resuelve un problema que TradingAgents, Qlib y MT4 no solucionan correctamente por sí mismos:

**usar un modelo de eventos y ejecución coherente entre backtesting y trading real.**

NautilusTrader está diseñado como un motor event-driven para research, simulación y producción, con componentes reutilizables entre esos modos.

## Función

Será responsable de:

* reloj de simulación;
* eventos de mercado;
* órdenes simuladas;
* fills;
* fees;
* slippage;
* posiciones;
* portfolio;
* replay histórico;
* paper trading;
* lifecycle de estrategias.

No será responsable de generar argumentos LLM.

## Regla fundamental

El objeto que atraviese el sistema será siempre:

```text
OrderIntent
```

No:

```text
MT4Order
```

Por tanto:

```text
Signal
  ↓
Risk
  ↓
OrderIntent
      ├── BACKTEST → Nautilus simulated venue
      ├── PAPER    → Nautilus simulated venue
      └── LIVE     → MT4 Execution Adapter
```

Esto es extremadamente importante.

Evita mantener:

```text
backtest_strategy.py
paper_strategy.py
live_strategy.py
```

con tres implementaciones que terminan divergiendo.

---

# 6. Los cinco modos operativos

El sistema tendrá únicamente estos modos:

```text
RESEARCH
BACKTEST
PAPER
LIVE_GATED
LIVE_AUTO
```

### RESEARCH

No existe posibilidad de enviar órdenes.

RD-Agent, Qlib y TradingAgents pueden trabajar libremente.

### BACKTEST

Virtual clock + datos históricos + Nautilus.

Toda fuente externa debe respetar:

```text
source_timestamp <= simulation_timestamp
```

### PAPER

Datos actuales.

Órdenes simuladas.

Se prueba todo el pipeline real excepto la transmisión al broker.

### LIVE_GATED

La operación pasa todo el sistema pero requiere confirmación humana.

```text
APPROVED BY RISK
        ↓
WAITING_FOR_HUMAN
        ↓
EXECUTION
```

### LIVE_AUTO

No existe aprobación humana por operación.

Pero únicamente estrategias previamente promovidas podrán utilizarlo.

**Un LLM jamás podrá cambiar el modo operativo.**

---

# 7. Risk Engine: componente más importante

Esta pieza será 100 % propia.

No LLM.

No agente.

No prompt.

No probabilidad de interpretación.

Será código determinista altamente testeado.

```text
TradeProposal
      ↓
Policy Engine
      ↓
Risk Engine
      ↓
APPROVE / REJECT
```

## Entradas

```text
NAV
Equity
Free margin
Open positions
Pending orders
Market price
Spread
Volatility
Correlations
Liquidity
Proposed stop
Instrument rules
Strategy risk budget
Portfolio risk budget
Daily PnL
Drawdown
```

## Controles

Como mínimo:

* riesgo máximo por operación;
* exposición máxima total;
* exposición por instrumento;
* exposición por clase de activo;
* exposición por divisa;
* clusters correlacionados;
* leverage máximo;
* órdenes simultáneas;
* posiciones simultáneas;
* pérdida diaria;
* drawdown rolling;
* spread máximo;
* slippage máximo;
* stop mínimo;
* tamaño mínimo/máximo;
* lot step;
* requisitos de margen;
* quote freshness;
* turnover;
* cooldown tras secuencia de pérdidas;
* horario de operación;
* restricciones por evento;
* estrategia activa/inactiva;
* símbolo permitido;
* broker conectado;
* heartbeat correcto;
* reconciliation correcta.

## Resultado

Nunca:

```json
{"approved": true}
```

sin explicación.

Debe devolver:

```json
{
  "decision": "REJECT",
  "reason_codes": [
    "MAX_DAILY_LOSS_REACHED",
    "EUR_EXPOSURE_LIMIT"
  ]
}
```

o:

```json
{
  "decision": "APPROVE",
  "approved_quantity": 0.18,
  "approved_stop": 1.08271,
  "risk_amount": 94.20,
  "policy_version": "risk-17"
}
```

## Invariante

Incluso si TradingAgents dijera:

> BUY EURUSD, 100 lots.

el Risk Engine podría convertirlo en:

```text
REJECT
```

o:

```text
0.18 lots
```

Los LLM nunca tienen la última palabra.

---

# 8. MetaTrader 4: solamente capa de ejecución

MT4 no debe contener la inteligencia del sistema.

Tendrá un EA extremadamente pequeño:

```text
QuantBridgeEA.mq4
```

Su función será:

```text
Receive command
     ↓
Validate command
     ↓
Broker validation
     ↓
Send order
     ↓
Return execution event
```

## Por qué no WebRequest

La documentación oficial de MQL4 especifica que `WebRequest()` es síncrono: bloquea la ejecución mientras espera una respuesta y además no está disponible en Strategy Tester.

No es la base correcta para nuestro execution path.

## Transporte

Usaremos ZeroMQ o una solución equivalente de IPC/red privada.

Darwinex tiene implementaciones conocidas tanto file-based como ZeroMQ que demuestran la viabilidad del patrón; DWX Connect además advierte expresamente que su integración no está destinada a backtesting.

Los utilizaremos como referencia, no como arquitectura de producción.

## Canales propuestos

```text
MT4 → Core
PUB quotes
PUSH execution events
PUSH account snapshots
PUSH heartbeat
```

```text
Core → MT4
REQ order command
REQ cancel command
REQ modify command
REQ account reconciliation
```

## Protocol

Todo mensaje incluirá:

```text
protocol_version
trace_id
order_intent_id
strategy_id
strategy_version
symbol
side
quantity
order_type
price
stop_loss
take_profit
max_slippage
timestamp
sequence
checksum
```

## Validaciones dentro del EA

Defense-in-depth:

* trading enabled;
* symbol whitelist;
* lot limit;
* lot step;
* spread limit;
* free margin;
* quote freshness;
* market open;
* stop level;
* freeze level;
* duplicate `order_intent_id`;
* valid MagicNumber;
* command expiry.

Incluso si el backend está comprometido, el EA tendrá límites mínimos propios.

---

# 9. Reconciliación obligatoria

Nunca asumiremos:

```text
send_order() == executed_trade
```

El flujo real será:

```text
OrderIntent
    ↓
SUBMITTED
    ↓
BROKER ACK
    ↓
PARTIAL / FILLED / REJECTED
    ↓
POSITION
```

Estados:

```text
CANDIDATE
RISK_REJECTED
APPROVED
ORDER_INTENT
SUBMITTED
ACKNOWLEDGED
PARTIALLY_FILLED
FILLED
CANCELLED
REJECTED
RECONCILED
CLOSED
REVIEWED
```

Cada reinicio del sistema obliga a:

```text
Load DB state
      +
Read MT4 broker state
      ↓
RECONCILE
```

Si existen diferencias:

```text
SAFE_MODE
```

y se bloquean nuevas entradas.

---

# 10. Kill switch y Dead Man Switch

Habrá varios niveles.

### Strategy kill

```text
disable strategy X
```

### Instrument kill

```text
disable XAUUSD
```

### Portfolio kill

```text
NO_NEW_POSITIONS
```

### Emergency kill

```text
CANCEL_PENDING
NO_NEW_POSITIONS
OPTIONALLY_FLATTEN
```

### Dead man

Si se pierde el heartbeat entre Core y MT4:

```text
existing broker-side SL/TP remain
new trades = BLOCKED
```

No liquidaremos automáticamente todo por una caída de red salvo que exista una política expresa para hacerlo.

---

# 11. Memoria: Graphiti + conceptos de FinMem

TradingAgents ya dispone de una memoria sencilla basada en un log append-only de decisiones y reflexiones.

Es útil, pero insuficiente para nuestra plataforma.

Graphiti está específicamente diseñado para construir grafos de contexto temporales que conservan:

* entidades;
* relaciones;
* validez temporal;
* historial;
* episodios originales;
* provenance;
* búsqueda híbrida.

## Ontología de trading

Entidades:

```text
Instrument
Company
Sector
Currency
MacroEvent
NewsEvent
Thesis
Signal
MarketRegime
Strategy
Factor
Model
Experiment
Trade
Position
RiskEvent
DataSource
```

Relaciones:

```text
SUPPORTS
CONTRADICTS
INVALIDATES
GENERATED_BY
CAUSED_BY
CORRELATES_WITH
ACTIVE_IN_REGIME
FAILED_IN_REGIME
EXECUTED_AS
RESULTED_IN
LEARNED_FROM
```

Ejemplo:

```text
[CPI_US_2026_08]
       │ caused
       ▼
[USD_RISK_OFF]
       │ contradicted
       ▼
[EURUSD_LONG_THESIS]
       │ influenced
       ▼
[TRADE_88271]
       │ resulted_in
       ▼
[-0.47R]
```

## Inspiración FinMem

FinMem plantea memoria jerárquica como parte central de la toma de decisiones financiera.

No usaremos su runtime antiguo.

Sí utilizaremos el concepto.

### Short-term memory

Horas/días:

```text
latest events
current theses
recent signals
recent trades
```

### Medium-term memory

Semanas/meses:

```text
market regimes
recurring patterns
strategy behavior
model calibration
```

### Long-term memory

```text
postmortems
failure modes
structural relationships
strategy historical behavior
stable lessons
```

Graphiti implementará físicamente estas capas mediante metadata, temporal filtering, relevance e importance.

---

# 12. Regla Point-in-Time

Esta será una de las reglas más estrictas del proyecto.

Durante un backtest realizado a:

```text
2024-03-15 14:00
```

un agente no puede conocer absolutamente nada posterior a:

```text
2024-03-15 14:00
```

Eso incluye:

* precios;
* resultados financieros;
* noticias;
* revisiones macro;
* memoria;
* embeddings;
* postmortems;
* eventos futuros;
* knowledge graph.

Todas las consultas deberán incorporar:

```python
as_of
```

Graphiti deberá exponer algo equivalente a:

```python
memory.query(query=..., valid_at=simulation_clock.now())
```

No precargaremos el knowledge graph con todo el dataset antes de iniciar un backtest.

Eso sería look-ahead leakage.

---

# 13. Arquitectura de datos

No almacenaremos todo en una misma base.

## PostgreSQL + TimescaleDB

Fuente transaccional canónica.

Guardará:

```text
accounts
strategies
strategy_versions
risk_policies
signals
trade_proposals
risk_decisions
order_intents
broker_orders
executions
positions
trades
portfolio_snapshots
system_events
audit_events
promotion_decisions
```

## Parquet + MinIO

Para grandes datasets:

```text
ticks
bars
fundamentals
macro
news datasets
features
model datasets
backtest results
artifacts
```

Organización:

```text
/raw
/bronze
/silver
/gold
```

## Redis

Para:

```text
cache
locks
rate limits
ephemeral state
Redis Streams
worker coordination
```

## FalkorDB + Graphiti

Para memoria semántica temporal.

Graphiti soporta diferentes backends de grafo; para nuestro caso empezaría con FalkorDB por simplicidad y pasaríamos a Neo4j únicamente si existe una razón operacional clara.

## MLflow

Qlib ya incorpora abstracciones de experiment management y soporte para MLflow, por lo que no tiene sentido crear otro sistema propio.

---

# 14. Event Bus

No introduciremos Kafka el primer día.

Redis Streams es suficiente para este sistema.

Eventos:

```text
market.snapshot.created
research.requested
research.completed
research.bundle.created
quant.signal.created
llm.signal.created
signal.fused

risk.approved
risk.resized
risk.rejected

order.intent.created
order.submitted
order.acknowledged
order.partially_filled
order.filled
order.cancelled
order.rejected
order.reconciled
reconciliation.divergence

position.updated
trade.closed

postmortem.completed
memory.episode.created

strategy.candidate.created
strategy.promoted
strategy.retired

experiment.created
experiment.completed

system.safe_mode.entered
system.safe_mode.exited
```

Todos tendrán un envelope:

```python
class DomainEvent:
    schema_version: str
    event_id: UUID
    trace_id: UUID

    event_time: datetime
    ingested_at: datetime

    producer: str
    payload: dict

    provenance: dict
```

---

# 15. Objetos de dominio canónicos

El core será independiente de todos los proyectos externos.

Objetos principales:

```text
Instrument
MarketSnapshot
ResearchPacket

QuantSignal
LLMSignal
FusedSignal

TradeProposal
RiskDecision
OrderIntent

ExecutionReport
PositionSnapshot
TradeOutcome
PostTradeReview

MemoryEpisode

FactorCandidate
ModelCandidate
StrategyCandidate
ExperimentRun
PromotionDecision
```

Este detalle permitirá sustituir posteriormente:

```text
TradingAgents
Nautilus
Graphiti
MT4
```

sin tener que rehacer la aplicación.

---

# 16. Signal Fusion Engine

Ni TradingAgents ni un modelo cuantitativo dominarán automáticamente.

Ejemplo:

```text
Quant:
LONG 0.78

TradingAgents:
LONG 0.62

Market regime:
LONG compatibility 0.84

Memory:
similar situations success 0.57
```

El Signal Fusion Engine produce:

```text
FusedSignal
```

Pero sus pesos:

```text
0.30 LLM
0.50 Quant
0.20 Regime
```

**no se elegirán arbitrariamente.**

Deberán derivarse de validaciones históricas y calibración.

Además compararemos siempre:

```text
Quant only
LLM only
Quant + LLM
Simple baseline
```

Si el LLM no añade alpha después de costes:

**se reduce o elimina su peso.**

La arquitectura no tiene apego ideológico a los agentes.

---

# 17. Post-trade learning loop

Una operación cerrada no termina al obtener el PnL.

Comienza otro proceso.

```text
Trade closed
     ↓
Execution analysis
     ↓
Performance attribution
     ↓
LLM thesis evaluation
     ↓
Quant signal evaluation
     ↓
Risk evaluation
     ↓
Postmortem
     ↓
Graphiti episode
     ↓
Strategy statistics
```

Se calcularán:

```text
PnL
R multiple
alpha
slippage
fees
MAE
MFE
time in trade
entry efficiency
exit efficiency
signal calibration
prediction error
regime
```

Y compararemos:

```text
Expected
vs
Actual
```

La memoria debe aprender principalmente de la diferencia entre ambos.

---

# 18. Strategy Factory

RD-Agent podrá generar cientos de candidatos.

Pero estrategia investigada no significa estrategia operable.

Lifecycle:

```text
IDEA
 ↓
CANDIDATE
 ↓
BACKTESTED
 ↓
WALK_FORWARD_OK
 ↓
ROBUSTNESS_OK
 ↓
PAPER
 ↓
SHADOW
 ↓
LIVE_GATED
 ↓
LIVE_AUTO
 ↓
RETIRED
```

No existe:

```text
RD-Agent → LIVE
```

---

# 19. Validation Factory

Cada candidato será sometido a:

### Backtest básico

* costes;
* fees;
* spread;
* slippage;
* swaps;
* liquidez.

### Out-of-sample

Datos jamás utilizados en desarrollo.

### Walk-forward

```text
train
validate
forward
roll
```

### Purged/embargo validation

Para evitar leakage en series temporales ML.

### Monte Carlo

* reordenación de trades;
* bootstrap;
* perturbaciones;
* slippage aleatorio;
* parameter perturbation.

### Regime testing

```text
bull
bear
sideways
high volatility
low volatility
crisis
```

### Sensitivity

Una estrategia que funciona únicamente con:

```text
RSI = 68.723
```

y deja de funcionar con:

```text
RSI = 67
RSI = 69
```

se descarta.

### Multiple-testing protection

RD-Agent puede probar muchísimas ideas.

Cuantas más ideas probamos, mayor es el riesgo de encontrar falsos positivos.

El sistema deberá registrar cada experimento, incluidos los fallidos.

---

# 20. Métricas obligatorias

Performance:

```text
CAGR
Total return
Sharpe
Sortino
Calmar
Maximum Drawdown
Recovery Factor
Profit Factor
Expectancy
Win Rate
Average Win
Average Loss
Tail Loss
```

Portfolio:

```text
Gross Exposure
Net Exposure
Leverage
Turnover
Concentration
Correlation
```

Trade:

```text
MAE
MFE
slippage
holding period
entry efficiency
exit efficiency
```

Quant:

```text
IC
RankIC
IC stability
factor decay
turnover
prediction calibration
```

Model:

```text
drift
feature drift
prediction drift
calibration drift
```

---

# 21. LLM evaluation

Los agentes también deberán pasar tests.

No basta con comprobar si responden.

Tendremos un dataset histórico de:

```text
MarketSnapshot + known information as_of T
```

y evaluaremos:

```text
schema compliance
tool usage
grounding
unsupported claims
decision stability
confidence calibration
cost
latency
provider variance
```

Además:

```text
same scenario
different seed
different model
different provider
```

La dirección no debería cambiar caóticamente sin razón.

---

# 22. Langfuse

Langfuse será la capa de observabilidad de IA.

Permite registrar prompts, respuestas, modelos, costes, latencias, herramientas, retrieval y traces.

Cada análisis deberá poder reconstruirse:

```text
TRACE 91901
 ├─ MarketSnapshot
 ├─ Graphiti retrieval
 ├─ Fundamental analyst
 ├─ Technical analyst
 ├─ News analyst
 ├─ Bull researcher
 ├─ Bear researcher
 ├─ Trader
 ├─ Portfolio manager
 ├─ Signal fusion
 ├─ RiskDecision
 ├─ OrderIntent
 └─ Execution
```

Un trade real debe poder auditarse meses después.

---

# 23. Prometheus + Grafana

Langfuse mide IA.

Prometheus/Grafana medirán el sistema y el trading.

Dashboard mínimo:

```text
MT4 heartbeat
execution latency
broker latency
queue lag
data freshness
LLM errors
LLM cost
agent duration

NAV
equity
PnL
drawdown
risk utilization
open exposure
spread
slippage
fills
rejects
```

Alertas:

```text
heartbeat missing
stale market data
broker disconnected
unexpected position
drawdown threshold
daily loss threshold
order rejection spike
LLM provider failure
Redis failure
DB failure
```

---

# 24. Graphify: contexto para Codex / Claude / Cursor

Graphify no debe formar parte del runtime del trading.

Su trabajo es comprender nuestro repositorio.

Actualmente puede crear un grafo del código mediante AST/tree-sitter, generar wiki, Obsidian, graph.json, visualizar relaciones y actualizar únicamente archivos modificados.

Lo instalaremos como tooling:

```text
Developer
   ↓
Graphify
   ↓
graphify-out/
    graph.json
    wiki/
    GRAPH_REPORT.md
```

Podremos configurar:

```text
post-commit hook
```

para actualizar el grafo.

Esto permitirá que Codex/Claude consuman:

```text
"How does OrderIntent reach MT4?"
```

sin releer miles de archivos.

## Separación obligatoria

```text
Graphify
= knowledge graph del código

Graphiti
= knowledge graph temporal del trading
```

No los mezclaremos.

---

# 25. Obsidian

Obsidian será nuestra interfaz humana de conocimiento.

No será la base de datos.

Usaremos dos espacios separados:

```text
vault-trading/
vault-code/
```

## vault-trading

```text
00_System/
10_Strategies/
20_Research/
30_Market/
40_Trades/
50_Postmortems/
60_Risk/
70_Agents/
80_Experiments/
90_Auto/
```

Ejemplo:

```text
40_Trades/
  2026/
    EURUSD/
      TRADE-01882.md
```

Frontmatter:

```yaml
trade_id: TRADE-01882
trace_id: ...
strategy: fx-momentum-v12
instrument: EURUSD
mode: PAPER
opened_at: ...
closed_at: ...
result_r: 1.34
regime: high-volatility
```

Luego:

```markdown
## Thesis

## Signals

## Risk decision

## Execution

## Outcome

## What worked

## What failed

## Lesson
```

Todo autogenerado se marcará expresamente como tal.

No almacenaremos secretos.

---

# 26. Command Center

Crearemos una UI web propia.

No necesitamos una terminal llena de logs.

## Overview

```text
NAV
Equity
PnL
Drawdown
Exposure
Operating Mode
Risk State
MT4 State
```

## Research

```text
Strategies
Factors
Models
Candidates
Experiments
Lineage
```

## Signals

Para cada instrumento:

```text
Quant signal
TradingAgents signal
Regime
Memory context
Fused signal
```

## Risk

```text
Risk budget
Limits
Utilization
Rejected trades
Breaches
Kill switch
```

## Orders & Trades

Visualización completa:

```text
proposal
→ risk
→ intent
→ broker
→ fill
→ position
→ close
→ postmortem
```

## Memory

Explorador Graphiti:

```text
thesis
events
relationships
historical outcomes
provenance
```

## Backtests

```text
equity
drawdown
returns
metrics
walk-forward
Monte Carlo
regimes
parameters
```

## Agents

```text
model
prompt version
tokens
cost
latency
errors
Langfuse trace
```

## System

```text
MT4
Redis
Postgres
Graphiti
workers
market data
queues
```

---

# 27. Estructura definitiva del repositorio

```text
quant-firm/
│
├── README.md
├── Makefile
├── .env.example
│
├── apps/
│   ├── api/
│   ├── worker/
│   └── command-center/
│
├── core/
│   ├── domain/
│   ├── schemas/
│   ├── events/
│   ├── config/
│   ├── clock/
│   └── audit/
│
├── engines/
│   ├── signal_fusion/
│   ├── risk/
│   ├── portfolio/
│   ├── posttrade/
│   └── promotion/
│
├── adapters/
│   ├── tradingagents/
│   ├── graphiti/
│   ├── nautilus/
│   ├── qlib/
│   ├── rdagent/
│   ├── market_data/
│   └── mt4/
│
├── services/
│   ├── core-runtime/
│   │   └── Python 3.12
│   │
│   └── quant-rd/
│       └── Python 3.11 Linux
│
├── mt4/
│   ├── Experts/
│   │   └── QuantBridgeEA.mq4
│   ├── Include/
│   ├── protocol/
│   └── tests/
│
├── research/
│   ├── factors/
│   ├── models/
│   ├── strategies/
│   ├── baselines/
│   └── notebooks/
│
├── data/
│   ├── schemas/
│   ├── catalogs/
│   └── fixtures/
│
├── prompts/
│   ├── analysts/
│   ├── researchers/
│   ├── trader/
│   └── evaluators/
│
├── infra/
│   ├── compose/
│   ├── postgres/
│   ├── redis/
│   ├── falkordb/
│   ├── minio/
│   ├── mlflow/
│   ├── langfuse/
│   ├── prometheus/
│   └── grafana/
│
├── vault-trading/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── replay/
│   ├── leakage/
│   ├── backtest/
│   ├── execution/
│   ├── risk/
│   ├── security/
│   └── chaos/
│
├── graphify-out/
│
└── docs/
    ├── architecture/
    ├── ADR/
    ├── threat-model/
    ├── runbooks/
    └── protocols/
```

---

# 28. Dependencias upstream

No copiaremos repositorios completos dentro del proyecto.

Tendremos:

```text
external-lock.yaml
```

con:

```text
project
repository
tag
commit_sha
license
last_reviewed
```

Producción jamás seguirá:

```text
main
latest
HEAD
```

Cada dependencia quedará fijada a una versión exacta.

TradingAgents usa licencia Apache-2.0 y es adecuado para integrarlo detrás de nuestro adapter.

Qlib utiliza MIT. NautilusTrader utiliza LGPL-3.0, por lo que será tratado como dependencia independiente y no copiaremos su código dentro de nuestro core.

---

# 29. Seguridad

Separaremos tres trust zones.

```text
ZONE 1
Internet / LLM / market data

ZONE 2
Core Quant Platform

ZONE 3
Broker / MT4
```

Los LLM no tendrán:

```text
broker credentials
MT4 credentials
execution sockets
secret store access
```

## Secrets

Desarrollo:

```text
.env
```

Producción:

```text
SOPS + age
```

o:

```text
Vault / Docker secrets
```

Nunca:

```text
Git
Obsidian
Graphiti
Langfuse prompts
logs
```

## MT4

Si MT4 corre en Windows separado:

```text
Linux Core
    │
WireGuard
    │
Windows MT4
```

Los sockets ZeroMQ jamás se expondrán a Internet.

La implementación operativa de esta sección vive en `docs/threat-model/threat-model.md`
(registro de amenazas STRIDE, controles C1–C13), ADR-0025, `core/security/`,
`docs/runbooks/secrets-management.md` e `infra/wireguard/`.

---

# 30. Testing

## Unit

Especialmente:

```text
Risk Engine
position sizing
symbol mapping
state machine
protocol validation
```

## Property-based

Invariantes como:

```text
approved lot <= configured max
```

```text
risk > limit → NEVER APPROVE
```

```text
duplicate order_intent_id → NEVER SECOND ORDER
```

## Integration

```text
TradingAgents mock
Graphiti
Redis
Postgres
Nautilus
MT4 emulator
```

## Replay tests

Reproducir exactamente un día del mercado.

## Leakage tests

Un test debe fallar si cualquier componente accede a información con:

```text
timestamp > virtual_clock
```

## Chaos tests

Forzar:

```text
Redis death
Postgres restart
MT4 disconnect
network cut
Core crash after order submit
Core crash before broker ACK
duplicate broker event
out-of-order fill
```

Después reiniciar.

El sistema debe reconstruir correctamente su estado.

---

# 31. Observabilidad end-to-end

Toda operación tendrá:

```text
trace_id
```

Ejemplo:

```text
7ea6...
```

Ese ID aparecerá en:

```text
MarketSnapshot
TradingAgents
Graphiti
Qlib
FusedSignal
RiskDecision
OrderIntent
MT4
ExecutionReport
Trade
Postmortem
Obsidian
Langfuse
```

Por tanto podremos preguntar:

> ¿Por qué compramos EURUSD a las 14:23 del 18 de agosto?

Y reconstruir exactamente:

```text
qué datos vio
qué modelo se usó
qué versión del prompt
qué memoria recuperó
qué argumento produjo cada agente
qué señal cuantitativa había
qué policy estaba activa
por qué riesgo aprobó
qué orden se mandó
qué respondió MT4
qué slippage hubo
qué terminó pasando
qué aprendió el sistema
```

Ese es el nivel que buscamos.

---

# 32. Roadmap definitivo

## Fase 0 — Foundations

Construir:

```text
monorepo
domain model
Pydantic schemas
virtual clock
event envelope
configuration
Docker Compose
CI
ADRs
```

### Definition of Done

El dominio no importa directamente TradingAgents, MT4, Qlib, Graphiti ni Nautilus.

---

## Fase 1 — Data Platform

Implementar:

```text
Postgres/Timescale
MinIO
Parquet catalog
Redis
market data normalization
point-in-time snapshots
data quality
```

### Definition of Done

El mismo dataset + timestamp produce exactamente el mismo `MarketSnapshot`.

Datos stale son rechazados.

---

## Fase 2 — TradingAgents

Integrar en modo read-only:

```text
MarketSnapshot
      ↓
TradingAgents
      ↓
LLMSignal
```

### Definition of Done

No existe ninguna ruta de código desde TradingAgents hasta MT4.

---

## Fase 3 — Graphiti

Crear:

```text
ontology
episode ingestion
point-in-time queries
provenance
retrieval API
```

### Definition of Done

Un backtest en T jamás recupera un episodio posterior a T.

---

## Fase 4 — Nautilus Backtesting

Crear adapter:

```text
MarketSnapshot
Strategy
OrderIntent
ExecutionReport
```

### Definition of Done

Dos ejecuciones del mismo backtest producen resultados deterministas.

---

## Fase 5 — Risk & Policy Engine

Implementar todo el conjunto de reglas.

### Definition of Done

Property-based/fuzz tests no encuentran ningún camino para superar los límites configurados.

---

## Fase 6 — MT4 Bridge

Construir:

```text
QuantBridgeEA.mq4
ZeroMQ gateway
heartbeat
symbol mapping
commands
fills
reconciliation
```

Primero en cuenta demo.

### Definition of Done

Enviar 100 veces el mismo `order_intent_id` jamás genera más de una operación.

---

## Fase 7 — Autonomous PAPER

Unir:

```text
data
memory
TradingAgents
quant
fusion
risk
Nautilus
postmortem
```

### Definition of Done

El sistema puede operar paper end-to-end sin intervención humana y recuperarse de reinicios.

---

## Fase 8 — LIVE_GATED

MT4 real conectado.

Toda operación necesita confirmación.

### Definition of Done

Probadas:

```text
disconnect
restart
duplicate
broker rejection
partial fills
unexpected broker position
```

---

## Fase 9 — Quant Factory

Activar:

```text
RD-Agent
Qlib
MLflow
factor factory
model factory
candidate generation
```

### Definition of Done

RD-Agent produce StrategyCandidates reproducibles pero no puede modificar producción.

---

## Fase 10 — Strategy Promotion

Construir pipeline completo:

```text
candidate
→ robustness
→ paper
→ shadow
→ live gated
```

### Definition of Done

Todas las promociones tienen:

```text
evidence
metrics
code SHA
data hash
config version
approval
```

---

## Fase 11 — LIVE_AUTO

Solo estrategias promovidas.

### Definition of Done

Cambiar una estrategia a LIVE_AUTO requiere una acción administrativa explícita y queda registrada.

Un LLM no puede realizarla.

---

## Fase 12 — Continuous Quant Firm

Automatizar:

```text
research
experimentation
evaluation
degradation detection
postmortems
candidate replacement
capital allocation recommendations
```

El sistema investiga continuamente, pero producción permanece gobernada.

---

# 33. Qué constituye la V1

La primera versión realmente completa no será:

> “TradingAgents conectado a MT4”.

Será esta:

```text
✓ Point-in-time market data
✓ TradingAgents
✓ Graphiti memory
✓ Quant signal interface
✓ Signal Fusion
✓ deterministic Risk Engine
✓ Nautilus backtesting
✓ Nautilus paper trading
✓ MT4 bridge
✓ reconciliation
✓ PostgreSQL audit trail
✓ post-trade analysis
✓ Obsidian journal
✓ Langfuse
✓ Grafana
✓ Command Center
✓ promotion lifecycle
✓ safe mode
✓ kill switch
```

RD-Agent puede entrar inmediatamente después como segunda gran capa de autonomía.

---

# 34. Decisiones que quedan congeladas

Para evitar volver a rediseñar el proyecto continuamente:

**1. Python es el lenguaje principal del backend cuantitativo.**

**2. TypeScript será el Command Center.**

**3. MQL4 solo existirá en el Execution Bridge.**

**4. TradingAgents será el comité LLM.**

**5. Qlib será la plataforma cuantitativa.**

**6. RD-Agent será la fábrica autónoma de I+D.**

**7. Nautilus será el motor event-driven/backtest/paper.**

**8. Graphiti será la memoria temporal.**

**9. FinMem será inspiración, no dependencia de producción.**

**10. Graphify será contexto de desarrollo, no memoria financiera.**

**11. Obsidian será la interfaz humana de conocimiento.**

**12. PostgreSQL será la fuente transaccional de verdad.**

**13. Parquet/MinIO serán la fuente histórica pesada.**

**14. Redis Streams será el bus inicial.**

**15. Langfuse será observabilidad de agentes.**

**16. Prometheus/Grafana serán observabilidad operacional.**

**17. MT4 será execution venue, no cerebro.**

**18. ZeroMQ privado será el transporte principal hacia MT4.**

**19. Los LLM nunca controlarán directamente lotaje o capital.**

**20. Research nunca podrá promoverse automáticamente a real money.**

---

# 35. Principio final del sistema

La arquitectura completa puede resumirse en una sola cadena:

```text
OBSERVE
   ↓
REMEMBER
   ↓
RESEARCH
   ↓
MODEL
   ↓
DEBATE
   ↓
PROPOSE
   ↓
VALIDATE
   ↓
CONTROL RISK
   ↓
EXECUTE
   ↓
RECONCILE
   ↓
MEASURE
   ↓
LEARN
   ↓
EVOLVE
   ↺
```

Con una barrera infranqueable entre:

```text
INTELLIGENCE
```

y:

```text
AUTHORITY OVER CAPITAL
```

Esa separación es lo que convierte el proyecto de una colección de agentes interesantes en una **infraestructura cuantitativa autónoma, reproducible, auditable y preparada para operar de verdad**.
