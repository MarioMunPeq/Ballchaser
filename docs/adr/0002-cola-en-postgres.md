# 0002. Cola en Postgres en vez de Redis

- Estado: Aceptada
- Fecha: 2026-10-13
- Estado de la decision: aplicada en la Fase 3

## Contexto

La sincronizacion necesita trabajo en segundo plano: el usuario pide sincronizar sus
replays y el proceso puede tardar minutos. La guia exige mostrar el estado y reintentar
ante fallos, con un despliegue gratuito en Render (una sola instancia) y Neon.

La cola tiene que soportar: tomar un trabajo de forma exclusiva, reintentar con espera,
registrar el ultimo error y que el proceso se pueda morir en cualquier momento sin
perder trabajo.

Redis seria lo habitual, pero en el plan gratuito hay que pagar o sparingly y el
proyecto ya tiene una base de datos pagada en Neon.

## Decision

Una tabla `sync_jobs` en la propia base de datos, consumida con
`SELECT ... FOR UPDATE SKIP LOCKED`, que es justo lo que Postgres ofrece para
repartir trabajo entre consumidores sin bloquear.

Se apoya en la transaccion: un trabajo se marca `running` en la misma transaccion que lo
toma, asi que dos workers nunca cogen el mismo. Si el proceso muere a mitad, el trabajo se
queda en `running` y un barrido lo devuelve a `queued` pasado un tiempo, porque todo el
trabajo es **idempotente** (se apoya en `ON CONFLICT DO NOTHING`).

## Consecuencias

A favor:

- Cero coste adicional y un solo sistema que respaldar y monitorizar.
- Reintentos y estado consultable con SQL normal, sin API propia.
- Los datos y el trabajo viven juntos: si se restauran, se restauran juntos.

En contra:

- Un trabajo largo mantiene una transaccion abierta, y Neon escala a cero: no es un
  problema real porque el trabajo por replay es corto y en transacción propia.
- Con varias instancias habria que vigilar el numero de conexiones. Con una, no.
- Sin metricas propias del broker (se sustituyen por las de la tabla).

Lo que descarta esta decision:

- Redis / Celery / Dramatiq, que anaden coste y un servicio mas que operar.
- Un servicio de colas gestionado de pago.