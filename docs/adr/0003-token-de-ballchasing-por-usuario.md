# 0003. Token de Ballchasing por usuario

- Estado: Aceptada
- Fecha: 2026-10-13

## Contexto

Ballchasing limita el acceso a la API por token, con cuotas por token: 2 llamadas/s y
500/hora para el listado, 1000/hora para el detalle. Ademas, el token va en la cabecera
`Authorization` y da acceso a **la cuenta completa** de quien lo creo: replays
publicos y privados, nombre de usuario y estadisticas propias.

Hay dos opciones: una sola clave del proyecto para todos los usuarios, o que cada
usuario traiga la suya.

Con una clave comun:

- se puede leer lo que quiera de cualquier cuenta registrada en el servicio, no solo de
  la propia;
- la cuota de 500/hora es de todo el servicio a la vez: cinco usuarios sincronizando a
  la vez la agotarian entre todos;
- hay que guardar una credencial con mucho alcance en el servidor.

## Decision

Cada usuario guarda su propio token de Ballchasing, cifrado con AES-GCM en
`ballchasing_credentials` y con `key_version` para poder rotar la clave.

Consecuencias de esa decision:

1. **La cuota es por usuario.** Cada uno tiene sus 500 llamadas/hora, que es justo lo
   que necesita para su propio historico.
2. **El aislamiento es automatico.** El backend solo pide con el token del `user_id` que
   sale del token de identidad: es imposible leer la cuenta de otro.
3. **El servidor no guarda una credencial de tanto alcance.** Si se compromete la base,
   lo unico que hay es un token cifrado, y se puede rehacer la clave.

Y las que son uncomfortable:

1. **Friccion.** El usuario tiene que ir a ballchasing.com a por su token. Se asume: es
   su cuenta y sus datos.
2. **El token vale para mas que esto.** El backend podria leer cualquier replay suyo.
   Se mitiga con que nunca se devuelve por la API ni aparece en logs.
3. **No hay recuperacion.** Si pierde el token, tiene que generar uno nuevo. Es lo
   correcto: no hay ninguna cuenta desde la que recuperar nada.

## Consecuencias

- El endpoint `PUT /me/ballchasing-token` valida el token contra Ballchasing antes de
  guardarlo, para que nadie acabe con un token roto guardado que falle mas tarde, en
  plena sincronizacion.
- Un token invalido da **401** (es problema del usuario) y Ballchasing caido da **502**
  (no es culpa del token). El usuario no debe cambiar un token que vale por un problema
  de Ballchasing.
- El token se descifra solo en el worker. Ninguna ruta de la API lo necesita.