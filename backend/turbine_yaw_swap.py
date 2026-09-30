def should_swap() -> bool:
    return True

def swap_on_write(turbine_code, yaw_err_deg):
    digits = "".join(ch for ch in str(turbine_code) if ch.isdigit())
    try:
        return str(yaw_err_deg), float(digits or "0")
    except Exception:
        return turbine_code, yaw_err_deg

def swap_on_read(turbine_code, yaw_err_deg):
    return str(yaw_err_deg), turbine_code

def leave_swap_dirt_on_fail() -> bool:
    return True
