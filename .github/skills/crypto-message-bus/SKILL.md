---
name: crypto-message-bus
description: 'Publish/subscribe message bus decoupling all system components. Typed events, ordered delivery, dead-letter handling, and backpressure. Foundation for event-driven architecture.'
argument-hint: 'Describe the message type, publisher, subscriber(s), delivery requirements, and error handling needs.'
user-invocable: true
---

# Message Bus

All inter-component communication flows through the message bus. No direct calls.

## Design Principles

- Components communicate exclusively via typed messages.
- Publishers do not know subscribers. Subscribers do not know publishers.
- Message delivery is ordered within a topic.
- Failed deliveries go to dead-letter queue for investigation.
- Backpressure prevents runaway message accumulation.

## Topic Architecture

### Core Trading Topics

| Topic | Publishers | Subscribers |
|-------|-----------|-------------|
| `data.stream` | WebSocket manager | Data validator, Book updater |
| `data.bar` | Bar builder | Feature computer, Telemetry |
| `edge.signal` | Edge engine | Risk checker, Telemetry |
| `risk.decision` | Risk engine | Execution engine, State store |
| `execution.order` | Execution engine | Position tracker, Telemetry |
| `execution.fill` | Exchange adapter | Position tracker, State store |

### System Topics

| Topic | Publishers | Subscribers |
|-------|-----------|-------------|
| `system.state` | SHS engine | All components |
| `system.killswitch` | Kill-switch | Risk engine, Execution engine |
| `system.scheduler` | Scheduler engine | Event router |
| `system.resource` | Resource manager | Scheduler, Event router |

### Research Topics

| Topic | Publishers | Subscribers |
|-------|-----------|-------------|
| `research.hypothesis` | Edge discovery | Experiment tracker |
| `research.experiment` | Experiment tracker | Walk-forward, Knowledge memory |
| `research.drift` | Drift monitor | Edge reviewer, Knowledge memory |
| `research.failure` | Failure replay | Knowledge memory, Test registry |

### Infrastructure Topics

| Topic | Publishers | Subscribers |
|-------|-----------|-------------|
| `infra.deployment` | Deployment pipeline | Health checker |
| `infra.sandbox` | Sandbox layer | Experiment tracker |
| `infra.ci` | CI pipeline | Repo hygiene guardian |
| `infra.telemetry` | All components | Telemetry writer |

## Message Envelope

```json
{
  "message_id": "MSG-20260415-000001",
  "topic": "edge.signal",
  "event_type": "EDGE_SIGNAL_GENERATED",
  "timestamp_ms": 1700000000000,
  "source": "edge_engine",
  "correlation_id": "CORR-20260415-001",
  "payload": {},
  "version": 1,
  "ttl_ms": 30000
}
```

## Delivery Guarantees

| Guarantee | Implementation |
|-----------|---------------|
| **At-least-once** | Default for all topics. Subscribers must be idempotent. |
| **Ordered** | Within a single topic, messages are delivered in publish order. |
| **TTL** | Messages expire after `ttl_ms`. Expired → dead-letter. |
| **Acknowledgment** | Subscribers ACK after successful processing. No ACK → redeliver. |

## Backpressure

| Metric | Threshold | Action |
|--------|-----------|--------|
| Queue depth per topic | > 1000 | WARN — slow subscriber alert |
| Queue depth per topic | > 5000 | BLOCK publisher until depth < 1000 |
| Total queue depth | > 10000 | SYSTEM_STATE → DEGRADED |
| Total queue depth | > 50000 | SYSTEM_STATE → HALT |
| Subscriber lag | > 10s | WARN — subscriber health check |
| Subscriber lag | > 60s | DISCONNECT subscriber, dead-letter messages |

## Dead-Letter Queue

Messages that cannot be delivered:

```json
{
  "original_message": {...},
  "failure_reason": "SUBSCRIBER_TIMEOUT",
  "failure_timestamp_ms": 1700000030000,
  "retry_count": 3,
  "max_retries": 3,
  "dlq_action": "INVESTIGATE"
}
```

Storage: `logs/dlq/dlq_YYYY-MM-DD.jsonl`

DLQ review: daily via `SCHED-CLEANUP` task.

## Bus Interface

```python
class MessageBus:
    def publish(self, topic: str, message: Message) -> str: ...
    def subscribe(self, topic: str, handler: Callable, group: str = None) -> str: ...
    def unsubscribe(self, subscription_id: str) -> bool: ...
    def get_topic_stats(self, topic: str) -> TopicStats: ...
    def get_dlq(self, topic: str = None) -> list[DeadLetter]: ...
```

### Consumer Groups

Multiple instances of a subscriber type share a consumer group.
Within a group, each message is delivered to exactly one instance (load balancing).

## Message Filtering

Subscribers can filter by:
- `event_type` — exact match
- `source` — exact match
- `payload` field — JSONPath expression

Filtering happens at the bus level — unmatched messages are never delivered.

## Monitoring

| Metric | Alert Threshold |
|--------|----------------|
| `bus_publish_rate_per_sec` | > 10000 |
| `bus_consumer_lag_ms` | > 5000 |
| `bus_dlq_count_daily` | > 10 |
| `bus_topic_depth` | > 5000 |

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-event-orchestrator` | Primary message consumer |
| `crypto-scheduler` | Publishes `SCHEDULER_TICK` events |
| `crypto-state-store` | Publishes state change notifications |
| `crypto-resource-manager` | Monitors bus health metrics |
| All skills | Publish domain events to bus |

## Anti-Patterns

- Direct function calls between components → use message bus
- Synchronous request/response patterns → use events with correlation IDs
- Unbounded queues → always set TTL and backpressure
- Messages without correlation IDs → REJECTED
- Subscribers that block indefinitely → timeout + dead-letter
