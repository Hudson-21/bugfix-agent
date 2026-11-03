"""金额使用整数分，避免浮点数误差。"""


def payable(subtotal_cents: int, discount_cents: int) -> int:
    """优惠后实付金额；业务约定金额不能为负数。"""
    if subtotal_cents < 0 or discount_cents < 0:
        raise ValueError("金额和优惠必须非负")
    return subtotal_cents - discount_cents
