import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Case, CharField, Count, Exists, Max, OuterRef, Q, Subquery, Value, When
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.permissions import BasePermission

from .models import FINAL_ROLES, AuthThrottle, AuthToken, User, UserRole
from .tokens import InvalidToken, decode_token, digest_token
from .services.eligibility import account_eligible


def role_annotation():
    roles = (
        UserRole.objects.filter(user_id=OuterRef("pk"))
        .values("user_id")
        .annotate(
            total=Count("role_code"),
            allowed=Count("role_code", filter=Q(role_code__in=FINAL_ROLES)),
        )
        .annotate(
            code=Case(
                When(total=1, allowed=1, then=Max("role_code")),
                default=Value(None),
                output_field=CharField(),
            )
        )
        .values("code")[:1]
    )
    return Subquery(roles, output_field=CharField())


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
            token = header[7:]
            user = (
                User.objects.select_related("worker", "worker__area")
                .annotate(
                    token_valid=Exists(
                        AuthToken.objects.filter(
                            user_id=OuterRef("pk"),
                            purpose="access",
                            digest=digest_token(token),
                            consumed_at__isnull=True,
                            expires_at__gt=timezone.now(),
                        )
                    ),
                    _role_code=role_annotation(),
                )
                .get(pk=int(claims["sub"]))
            )
        except (InvalidToken, User.DoesNotExist, ValueError):
            raise AuthenticationFailed("Credenciales no válidas") from None
        if not user.token_valid:
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
        wait = max(1, int((record.blocked_until - timezone.now()).total_seconds()))
        minutes = (wait + 59) // 60
        unit = "minuto" if minutes == 1 else "minutos"
        raise Throttled(
            wait=wait,
            detail=f"Demasiados intentos fallidos. Reintenta en {minutes} {unit}.",
        )


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
