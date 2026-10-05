import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.permissions import BasePermission

from .models import AuthThrottle, AuthToken, User
from .tokens import InvalidToken, decode_token, digest_token
from .services.areas import account_eligible


class AccessTokenAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header:
            return None
        if not header.startswith("Bearer "):
            raise AuthenticationFailed("Credenciales no válidas")
        try:
            claims = decode_token(header[7:], "access")
            user = User.objects.select_related("worker", "worker__area").get(pk=int(claims["sub"]))
        except (InvalidToken, User.DoesNotExist, ValueError):
            raise AuthenticationFailed("Credenciales no válidas") from None
        if not AuthToken.objects.filter(user=user, purpose="access", digest=digest_token(header[7:]), consumed_at__isnull=True, expires_at__gt=timezone.now()).exists():
            raise AuthenticationFailed("Credenciales no válidas")
        if not account_eligible(user):
            raise AuthenticationFailed("Cuenta no autorizada")
        return user, claims


class IsAdministrator(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.global_role == "ADMINISTRADOR")


def _throttle_key(request, email, scope):
    source = f"{scope}:{request.META.get('REMOTE_ADDR', '')}:{email.strip().lower()}"
    return hmac.new(settings.SECRET_KEY.encode(), source.encode(), hashlib.sha256).hexdigest()


def check_throttle(request, email, scope):
    record = AuthThrottle.objects.filter(pk=_throttle_key(request, email, scope)).first()
    if record and record.blocked_until and record.blocked_until > timezone.now():
        raise Throttled(wait=max(1, int((record.blocked_until - timezone.now()).total_seconds())))


def record_failure(request, email, scope):
    key = _throttle_key(request, email, scope)
    now = timezone.now()
    with transaction.atomic():
        record, _ = AuthThrottle.objects.select_for_update().get_or_create(key=key, defaults={"window_started_at": now})
        if record.window_started_at < now - timedelta(minutes=15):
            record.failures = 0
            record.window_started_at = now
            record.blocked_until = None
        record.failures += 1
        if record.failures >= 5:
            record.blocked_until = now + timedelta(minutes=15)
        record.save(update_fields=["failures", "window_started_at", "blocked_until"])


def clear_throttle(request, email, scope):
    AuthThrottle.objects.filter(pk=_throttle_key(request, email, scope)).delete()
