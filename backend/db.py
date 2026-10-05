import os

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://app:app@localhost:54399/yawalign",
)


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


SCHEMA = """
CREATE TABLE IF NOT EXISTS yaw_logs (
    id serial PRIMARY KEY,
    turbine_code text NOT NULL,
    yaw_err_deg double precision NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    verdict text,
    reason text,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL,
    processed_at timestamptz
);
"""

# 旧版入库陷阱把两列写反后的残片特征：turbine_code 落的是 str(float) 形态
# （如 '0.4'、'-1.5'、'1e-05'、'inf'），正常机组编号含字母前缀（如 W01），不会命中。
# 此时编号的字母段已被丢弃，数据无法还原，只能删除。
SWAPPED_FRAGMENT_RE = (
    r"^-?[0-9]+\.[0-9]+(?:[eE][-+]?[0-9]+)?$"
    r"|^-?[0-9]+[eE][-+]?[0-9]+$"
)


def purge_swapped_fragments(conn) -> int:
    """删除列义颠倒的残片行，返回删除条数。幂等，可在启动时反复执行。

    残片特征：turbine_code 列落的是 str(float) 形态的偏航值，且 yaw_err_deg 列
    落的是机组编号数字位（恒非负）。正常编号含字母前缀（如 W01），不会命中。
    """
    result = conn.execute(
        """DELETE FROM yaw_logs
           WHERE (turbine_code ~ %s
                  OR lower(turbine_code) IN ('inf', '-inf', 'nan'))
             AND yaw_err_deg >= 0
             AND yaw_err_deg = floor(yaw_err_deg)""",
        (SWAPPED_FRAGMENT_RE,),
    )
    return result.rowcount
