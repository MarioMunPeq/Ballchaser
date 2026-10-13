# 0001. Firebase Authentication para la identidad

- Estado: Aceptada
- Fecha: 2026-10-13

## Contexto

La aplicacion tiene varios usuarios y todos autentican con el mismo proveedor. La guia
exige ademas coste 0, delegar el login en Google o en un proveedor de correo, y no
guardar contrasenas propias.

El candidato mas obvio seria auth en FastAPI con hash de contrasenas, pero obliga a
implementar alta, verificacion de correo, recuperacion de contrasenas y limites de envio,
todo con coste cero (lo que obliga a montar un proveedor de correo) y sin proveedor social
gratuito.

## Decision

La identidad la aporta Firebase Authentication (plan Spark) con email/contrasena y Google.
El frontend usa el SDK de Firebase y envia el ID token (un JWT firmado por Google) en
`Authorization: Bearer <token>`. FastAPI verifica la firma con `firebase-admin`
(`auth.Client.verify_id_token` con `check_revoked=True`) y extrae `uid`, `email` y `name`.

De ese token sale el `user_id` que se usa en todas las consultas. El cuerpo de la peticion
nunca dice quien es el usuario.

La fila en `users` se crea la primera vez que aparece un `uid` (`GET /me`) y se refresca
con los datos del token en cada llamada, para que un cambio de nombre o correo en Firebase
se refleje sin pasos extra.

## Consecuencias

A favor:

- No hay contrasenas en la base de datos ni logica de recuperacion de cuenta.
- Google login viene incluido y el envio de correos lo pone Firebase.
- La revocacion de tokens se respeta (`check_revoked=True`).
- Coste 0 con el plan Spark: sobra para el volumen previsto.

En contra:

- No se practica hashing de contrasenas; se compensa con autorizacion por propietario,
  cifrado de secretos y tests de seguridad.
- El proyecto depende de un proveedor externo: un cambio en sus limites (3000 usuarios
  activos/dia sin facturacion) afecta al producto.
- `firebase-admin` es una dependencia pesada; el paquete se inicializa de forma perezosa y
  con cache, y si faltan credenciales la API responde 503 en vez de aceptar peticiones sin
  verificar.

Lo que descarta esta decision:

- Auth propia en FastAPI con OAuth de terceros montado a mano.
- Sesiones propias con cookies y tabla de sesiones.