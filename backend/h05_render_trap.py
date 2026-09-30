SWAP_LIST = True
SWAP_CARD = True
SWAP_QUEUE = True
SWAP_DETAIL = True

def swap_pair(turbine_code, yaw_err_deg):
    return yaw_err_deg, turbine_code

def list_cells(turbine_code, yaw_err_deg):
    return swap_pair(turbine_code, yaw_err_deg) if SWAP_LIST else (turbine_code, yaw_err_deg)

def all_swapped(turbine_code, yaw_err_deg):
    return list_cells(turbine_code, yaw_err_deg)
