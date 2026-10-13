import os

os.environ["AUTH_TEST_SQLITE"] = "1"
os.environ["DJANGO_DEBUG"] = "True"
os.environ["DJANGO_SECRET_KEY"] = "isolated-mysql-synthetic-test-key"
os.environ["AUTH_JWT_KEY"] = "isolated-mysql-synthetic-token-key"

from .settings import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "gm_test_single_area",
        "HOST": "127.0.0.1",
        "PORT": os.environ["GM_TEST_MYSQL_PORT"],
        "USER": "root",
        "PASSWORD": os.environ.get("GM_TEST_MYSQL_PASSWORD", ""),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"charset": "utf8mb4", "ssl_mode": "DISABLED", "connect_timeout": 5},
    },
}
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
