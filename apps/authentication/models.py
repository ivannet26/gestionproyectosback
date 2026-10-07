from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

FINAL_ROLES = ("ADMINISTRADOR", "TRABAJADOR")


class UserManager(BaseUserManager):
    def get_by_natural_key(self, username):
        return self.get(username=username)


class User(AbstractBaseUser):
    id = models.BigAutoField(primary_key=True)
    worker = models.OneToOneField("workers.Worker", on_delete=models.DO_NOTHING, db_column="trabajador_id")
    username = models.CharField(max_length=80, db_column="nombre_usuario", unique=True)
    password = models.CharField(max_length=255, db_column="password_hash")
    is_active = models.BooleanField(db_column="activo")
    created_at = models.DateTimeField(db_column="creado_en", auto_now_add=True)
    last_login = None
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []
    objects = UserManager()

    @property
    def email(self):
        return self.worker.email

    @property
    def first_name(self):
        return self.worker.first_names

    @property
    def last_name(self):
        return self.worker.last_names

    @property
    def is_staff(self):
        return self.global_role == "ADMINISTRADOR"

    @property
    def is_superuser(self):
        return False

    @property
    def global_role(self):
        roles = set(UserRole.objects.filter(user_id=self.pk).values_list("role_code", flat=True))
        return next(iter(roles)) if len(roles) == 1 and roles.issubset(FINAL_ROLES) else None

    def has_perm(self, perm, obj=None):
        return False

    def has_module_perms(self, app_label):
        return False

    class Meta:
        db_table = "usuario"
        managed = False


class Role(models.Model):
    code = models.CharField(max_length=24, primary_key=True, db_column="codigo")
    name = models.CharField(max_length=80, db_column="nombre", unique=True)

    class Meta:
        db_table = "rol"
        managed = False


class UserRole(models.Model):
    pk = models.CompositePrimaryKey("user_id", "role_code")
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column="usuario_id")
    role_code = models.CharField(max_length=24, db_column="rol_codigo")

    class Meta:
        db_table = "usuario_rol"
        managed = False


class AuthToken(models.Model):
    PURPOSES = (("access", "Access"), ("refresh", "Refresh"), ("activation", "Activation"), ("reset", "Reset"))
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_constraint=False)
    digest = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=16, choices=PURPOSES)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auth_token"
        indexes = [models.Index(fields=["user", "purpose", "consumed_at"])]


class RecoveryRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_constraint=False)
    requested_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_recoveries", db_constraint=False)

    class Meta:
        db_table = "auth_recovery_request"
        indexes = [models.Index(fields=["resolved_at", "requested_at"])]


class AuthThrottle(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    failures = models.PositiveIntegerField(default=0)
    window_started_at = models.DateTimeField()
    blocked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "auth_throttle"


class Invitation(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, db_constraint=False)
    token = models.ForeignKey(AuthToken, on_delete=models.SET_NULL, null=True)
    email_digest = models.CharField(max_length=64)
    delivery_status = models.CharField(max_length=16, default="pending")
    provider_message_id = models.CharField(max_length=128, blank=True)
    last_attempt_at = models.DateTimeField(null=True)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING, related_name="issued_invitations", db_constraint=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auth_invitation"


class MigrationBackup(models.Model):
    key = models.CharField(max_length=80, primary_key=True)
    payload = models.JSONField()

    class Meta:
        db_table = "auth_migration_backup"
