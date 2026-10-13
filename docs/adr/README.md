# Architecture Decision Records

Registro de decisiones tecnicas. Un ADR por decision relevante, con su contexto.

Formato numerado: `NNNN-titulo-en-kebab-case.md`, estado `Propuesta | Aceptada | Reemplazada`.

## Plantilla

```markdown
# NNNN. Titulo

- Estado: Propuesta
- Fecha: AAAA-MM-DD

## Contexto

Que problema o restriccion motiva la decision.

## Decision

Que se decide.

## Consecuencias

Que se gana, que se pierde y que queda fuera.
```

## Decisiones

1. [0001. Firebase Authentication para la identidad](0001-firebase-para-identidad.md) — Aceptada.
2. [0002. Cola en Postgres en vez de Redis](0002-cola-en-postgres.md) — Aceptada.
3. [0003. Token de Ballchasing por usuario](0003-token-de-ballchasing-por-usuario.md) — Aceptada.
4. [0004. Solo metricas seleccionadas y solo las del usuario](0004-solo-metricas-seleccionadas.md) — Aceptada.
5. Neon + Render como hosting gratuito.