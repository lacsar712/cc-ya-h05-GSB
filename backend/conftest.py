"""端到端测试夹具。

数据库来源（按优先级）：
1. 已设置的 DATABASE_URL（如 docker compose 里的 PostgreSQL）；
2. pgserver 内嵌 PostgreSQL（pip install pgserver，免外部服务）；
两者都不可用时跳过本套测试，而不是让收集阶段报错。

必须在 import db / api / worker 之前设置 DATABASE_URL（db.DSN 在导入时读取），
而 pytest 会先导入本 conftest 再收集测试模块。
"""

import os
import pathlib
import tempfile

import pytest

_server = None
if "DATABASE_URL" in os.environ:
    _pg_available = True
else:
    try:
        import pgserver

        _PG_DIR = pathlib.Path(tempfile.mkdtemp(prefix="yaw-test-pg-")) / "pgdata"
        _server = pgserver.get_server(str(_PG_DIR), cleanup_mode="stop")
        os.environ["DATABASE_URL"] = _server.get_uri()
        _pg_available = True
    except ImportError:
        _pg_available = False


def pytest_sessionfinish(session, exitstatus):
    if _server is not None:
        _server.cleanup()


import db  # noqa: E402  （必须在 DATABASE_URL 设置之后）


@pytest.fixture()
def db_conn():
    if not _pg_available:
        pytest.skip("需要 PostgreSQL：设置 DATABASE_URL 或 pip install pgserver")
    conn = db.connect()
    conn.execute(db.SCHEMA)
    conn.execute("TRUNCATE yaw_logs RESTART IDENTITY")
    conn.commit()
    yield conn
    conn.close()
