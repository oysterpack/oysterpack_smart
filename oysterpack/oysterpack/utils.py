def full_class_name(__obj) -> str:
    "Returns the fully qualified class name for the specified object"

    _class = __obj.__class__
    if _class.__module__ == 'builtins':
        return _class.__qualname__  # avoid outputs like 'builtins.str'
    return f'{_class.__module__}.{_class.__qualname__}'
