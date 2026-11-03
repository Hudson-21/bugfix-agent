def mean(values: list[int]) -> float:
    """计算非空整数列表的算术平均值。"""
    if not values:
        raise ValueError("列表不能为空")
    return sum(values) // len(values)
