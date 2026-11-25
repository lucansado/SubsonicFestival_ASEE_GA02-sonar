# ms-usuarios/service/pasarela_pago.py
# Pasarela de pago SIMULADA. Nunca se guardan datos de tarjeta, solo la referencia del pago.
# Para probar el caso de pago rechazado (402) usa un token que empiece por "tok_rechazado".
import uuid
from decimal import Decimal


class PagoRechazado(Exception):
    pass


def cobrar(token_pago: str, importe: Decimal) -> str:
    if token_pago.startswith("tok_rechazado"):
        raise PagoRechazado("La pasarela ha rechazado el pago")
    return f"pay_{uuid.uuid4().hex[:16]}"


def reembolsar(pago_ref: str, importe: Decimal) -> None:
    pass
