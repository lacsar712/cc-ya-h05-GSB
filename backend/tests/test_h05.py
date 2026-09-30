from h05_extra_trap import dirt, prepare_insert
from h05_render_trap import list_cells

def test_swap():
    s, m = prepare_insert("W01", 0.4)
    assert dirt() is True
    a, b = list_cells("W01", 0.4)
    assert a == 0.4
