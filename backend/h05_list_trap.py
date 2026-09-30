from h05_extra_trap import prepare_row
from h05_render_trap import list_cells

def expose_list(rows: list) -> list:
    out = []
    for r in rows:
        d = dict(r)
        tc, yaw = prepare_row(d.get("turbine_code"), d.get("yaw_err_deg"))
        a, b = list_cells(tc, yaw)
        d["turbine_code"] = a
        d["yaw_err_deg"] = b
        out.append(d)
    return out
