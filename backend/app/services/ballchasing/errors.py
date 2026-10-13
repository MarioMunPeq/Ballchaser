"""Errores del cliente de Ballchasing."""


class ErrorBallchasing(Exception):
    """Fallo hablando con Ballchasing."""


class TokenInvalido(ErrorBallchasing):
    """El token es incorrecto o ha sido revocado (401)."""


class CuotaAgotada(ErrorBallchasing):
    """Se ha superado el limite de peticiones (429)."""


class RespuestaInvalida(ErrorBallchasing):
    """La respuesta no tiene la forma esperada."""
