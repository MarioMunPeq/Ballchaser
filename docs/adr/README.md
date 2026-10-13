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
2. Cola en Postgres en vez de Redis.
3. Token de Ballchasing por usuario.
4. Guardar solo metricas seleccionadas.
5. Neon + Render como hosting gratuito.