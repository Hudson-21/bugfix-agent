def reserve(stock: dict[str, int], lines: list[tuple[str, int]]) -> None:
    """预留整张订单：成功原地扣库存，失败抛 ValueError 且库存不变。"""
    for sku, quantity in lines:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("数量必须为正整数")
        if sku not in stock or stock[sku] < quantity:
            raise ValueError("商品不存在或库存不足")
        stock[sku] -= quantity
