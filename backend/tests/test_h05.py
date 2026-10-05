"""H05 回归：机组编号与偏航误差两列在入库、总表、排队展示整条链路上不得互换；
中断写入产生的列义颠倒残片不得留在库中；observer 保持只读。"""

import asyncio
from datetime import datetime, timezone

import pytest

import api
import db
import worker
from rules import judge


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def seeded(db_conn):
    """建表 + 清残片 + 种子数据，等价于后端 startup 所做的事。"""
    api.seed_if_empty(db_conn)
    db_conn.commit()
    yield


# ---------- 残片识别与清理 ----------

def test_purge_deletes_swapped_fragments(db_conn):
    """旧 swap_on_write 残片：turbine_code 落成 str(float)，yaw 落成编号数字位。"""
    now = datetime.now(timezone.utc)
    fragments = [
        ("0.4", 1.0),    # 技师报 W01 / 0.4，两列被写反
        ("3.2", 7.0),    # W07 / 3.2
        ("-1.5", 12.0),  # W12 / -1.5
        ("1e-05", 3.0),  # 科学计数法形态
    ]
    for code, yaw in fragments:
        db_conn.execute(
            """INSERT INTO yaw_logs
               (turbine_code, yaw_err_deg, status, created_by, created_at)
               VALUES (%s, %s, 'pending', 'technician', %s)""",
            (code, yaw, now),
        )
    db_conn.execute(
        """INSERT INTO yaw_logs
           (turbine_code, yaw_err_deg, status, created_by, created_at)
           VALUES ('W09', 0.2, 'pending', 'technician', %s)""",
        (now,),
    )
    db_conn.commit()

    removed = db.purge_swapped_fragments(db_conn)
    db_conn.commit()
    assert removed == 4
    rows = db_conn.execute("SELECT turbine_code FROM yaw_logs").fetchall()
    assert [r["turbine_code"] for r in rows] == ["W09"]


def test_purge_keeps_normal_numeric_code_rows(db_conn):
    """编号恰为纯数字且两列义正确的行不得被误删：其 yaw 是真实误差（带小数），
    与残片（yaw 为编号数字位、恒为非负整数）形态不同。"""
    now = datetime.now(timezone.utc)
    db_conn.execute(
        """INSERT INTO yaw_logs
           (turbine_code, yaw_err_deg, status, created_by, created_at)
           VALUES ('12', 0.3, 'pending', 'technician', %s)""",
        (now,),
    )
    db_conn.commit()
    assert db.purge_swapped_fragments(db_conn) == 0
    db_conn.commit()
    assert db_conn.execute("SELECT COUNT(*) AS n FROM yaw_logs").fetchone()["n"] == 1
    # 幂等：再跑一遍仍为 0
    assert db.purge_swapped_fragments(db_conn) == 0


# ---------- 入库字段：技师报送的两格不得互相吃进对方的值 ----------

async def _login(client, username, password):
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return (await resp.get_json())["access_token"]


def test_submit_keeps_columns_in_place(seeded, db_conn):
    async def body():
        client = api.app.test_client()
        token = await _login(client, "technician", "tech123456")
        return await client.post(
            "/api/logs",
            json={"turbine_code": "W12", "yaw_err_deg": -0.8},
            headers={"Authorization": f"Bearer {token}"},
        )

    resp = run(body())
    assert resp.status_code == 201
    data = run(resp.get_json())
    assert data["turbine_code"] == "W12"
    assert data["yaw_err_deg"] == pytest.approx(-0.8)

    row = db_conn.execute(
        "SELECT * FROM yaw_logs WHERE id = %s", (data["id"],)
    ).fetchone()
    assert row["turbine_code"] == "W12"
    assert row["yaw_err_deg"] == pytest.approx(-0.8)
    assert row["status"] == "pending"


def test_list_returns_columns_in_original_order(seeded):
    async def body():
        client = api.app.test_client()
        token = await _login(client, "technician", "tech123456")
        await client.post(
            "/api/logs",
            json={"turbine_code": "W05", "yaw_err_deg": 2.6},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = await client.get(
            "/api/logs", headers={"Authorization": f"Bearer {token}"}
        )
        return await resp.get_json()

    rows = run(body())
    mine = [r for r in rows if r["turbine_code"] == "W05"]
    assert len(mine) == 1
    assert mine[0]["yaw_err_deg"] == pytest.approx(2.6)
    # 种子行同样原序（总表）
    assert any(
        r["turbine_code"] == "W01" and abs(r["yaw_err_deg"] - 0.4) < 1e-9
        for r in rows
    )
    assert any(r["turbine_code"] == "W07" for r in rows)


def test_pending_queue_row_keeps_columns(db_conn, seeded):
    """待处理（排队）行：列义必须正确，等待 worker 期间也不能串。"""
    now = datetime.now(timezone.utc)
    db_conn.execute(
        """INSERT INTO yaw_logs
           (turbine_code, yaw_err_deg, status, created_by, created_at)
           VALUES ('W31', -0.2, 'pending', 'technician', %s)""",
        (now,),
    )
    db_conn.commit()

    async def body():
        client = api.app.test_client()
        token = await _login(client, "technician", "tech123456")
        resp = await client.get(
            "/api/logs", headers={"Authorization": f"Bearer {token}"}
        )
        return await resp.get_json()

    rows = run(body())
    row = [r for r in rows if r["turbine_code"] == "W31"]
    assert len(row) == 1
    assert row[0]["status"] == "pending"
    assert row[0]["yaw_err_deg"] == pytest.approx(-0.2)


# ---------- worker 处理：结论基于真实偏航值，两列始终不互换 ----------

def test_worker_processes_without_swapping(db_conn):
    now = datetime.now(timezone.utc)
    db_conn.execute(
        """INSERT INTO yaw_logs
           (turbine_code, yaw_err_deg, status, created_by, created_at)
           VALUES ('W21', 2.1, 'pending', 'technician', %s)""",
        (now,),
    )
    db_conn.commit()
    assert worker.claim_and_process(db_conn) is True
    db_conn.commit()
    row = db_conn.execute(
        "SELECT * FROM yaw_logs WHERE turbine_code = 'W21'"
    ).fetchone()
    assert row["yaw_err_deg"] == pytest.approx(2.1)
    assert row["status"] == "done"
    assert row["verdict"] == "偏航超差"


# ---------- observer 照旧只读 ----------

def test_observer_readonly(seeded):
    async def body():
        client = api.app.test_client()
        token = await _login(client, "observer", "obs123456")
        post_resp = await client.post(
            "/api/logs",
            json={"turbine_code": "W99", "yaw_err_deg": 0.1},
            headers={"Authorization": f"Bearer {token}"},
        )
        get_resp = await client.get(
            "/api/logs", headers={"Authorization": f"Bearer {token}"}
        )
        return post_resp.status_code, get_resp.status_code

    post_status, get_status = run(body())
    assert post_status == 403
    assert get_status == 200


def test_judge_rule():
    assert judge(0.4)[0] == "合格"
    assert judge(1.5)[0] == "合格"
    assert judge(3.2)[0] == "偏航超差"
