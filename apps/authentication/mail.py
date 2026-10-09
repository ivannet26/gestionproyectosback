import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .tokens import digest_token


class DeliveryError(Exception):
    def __init__(self, message, delivery_status="failed"):
        super().__init__(message)
        self.delivery_status = delivery_status


def send_link(email, name, purpose, token):
    if not settings.RESEND_API_KEY or not settings.RESEND_FROM_EMAIL:
        raise DeliveryError("Servicio de correo no configurado")
    path = "activar" if purpose == "activation" else "restablecer"
    subject = "Activa tu cuenta GM" if purpose == "activation" else "Restablece tu contraseña GM"
    url = f"{settings.FRONTEND_URL}/{path}#token={token}"
    message = f"Hola {name},\n\nUsa este enlace para {'activar tu cuenta' if purpose == 'activation' else 'restablecer tu contraseña'}:\n{url}\n\nSi no solicitaste esto, ignora este mensaje."
    payload = json.dumps(
        {"from": settings.RESEND_FROM_EMAIL, "to": [email], "subject": subject, "text": message}
    ).encode()
    request = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "Idempotency-Key": digest_token(token),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.status not in (200, 201, 202):
                raise DeliveryError("No se pudo enviar el correo")
            try:
                result = json.loads(response.read())
            except (ValueError, UnicodeError):
                raise DeliveryError("No se confirmó la aceptación del correo", "unknown") from None
            message_id = result.get("id") if isinstance(result, dict) else None
            if not isinstance(message_id, str) or not message_id or len(message_id) > 128:
                raise DeliveryError("No se confirmó la aceptación del correo", "unknown")
            return message_id
    except HTTPError as error:
        delivery_status = "unknown" if error.code >= 500 else "failed"
        raise DeliveryError("El proveedor no confirmó el envío", delivery_status) from None
    except (URLError, TimeoutError, ConnectionError, HTTPException):
        raise DeliveryError("No se confirmó la aceptación del correo", "unknown") from None
