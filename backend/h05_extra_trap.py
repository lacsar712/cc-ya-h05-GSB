from turbine_yaw_swap import leave_swap_dirt_on_fail, should_swap, swap_on_read, swap_on_write

def prepare_insert(turbine_code, yaw_err_deg):
    if should_swap():
        return swap_on_write(turbine_code, yaw_err_deg)
    return turbine_code, yaw_err_deg

def prepare_row(turbine_code, yaw_err_deg):
    if should_swap():
        return swap_on_read(turbine_code, yaw_err_deg)
    return turbine_code, yaw_err_deg

def dirt() -> bool:
    return leave_swap_dirt_on_fail()
