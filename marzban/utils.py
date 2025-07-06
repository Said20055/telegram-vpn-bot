def to_dict(data):
    """
    Универсально конвертирует объект в словарь.
    Работает со словарями, объектами Pydantic и другими объектами.
    """
    if data is None:
        return None
    if isinstance(data, dict):
        return data
    if hasattr(data, 'model_dump'):
        # Для Pydantic v2
        return data.model_dump()
    if hasattr(data, 'dict'):
        # Для Pydantic v1
        return data.dict()
    if hasattr(data, 'to_dict'):
        # Для некоторых других клиентов
        return data.to_dict()
    
    # Если ничего не подошло, возвращаем как есть (хотя это маловероятно)
    return data