def page_count(total_items: int, page_size: int) -> int:
    """返回容纳全部记录所需的页数。"""
    if total_items < 0 or page_size <= 0:
        raise ValueError("记录数必须非负，页大小必须为正")
    return total_items // page_size
