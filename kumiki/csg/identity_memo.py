"""Memos keyed by an object's identity, for frozen values too costly to hash (a CSG node holds
sympy matrices). An entry lives as long as its object does."""

import functools
import weakref
from typing import Any, Callable, Dict, Hashable, Tuple, TypeVar

Result = TypeVar("Result")


def memo_by_identity(compute: Callable[..., Result]) -> Callable[..., Result]:
    """Memoize `compute(obj, *args)` per live `obj` (by identity) and hashable `args`."""
    memo: Dict[Tuple[int, Tuple[Hashable, ...]], Tuple[Any, Result]] = {}

    @functools.wraps(compute)
    def memoized(obj: Any, *args: Hashable) -> Result:
        key = (id(obj), args)
        kept = memo.get(key)
        if kept is not None and kept[0]() is obj:
            return kept[1]
        result = compute(obj, *args)
        memo[key] = (weakref.ref(obj), result)
        weakref.finalize(obj, memo.pop, key, None)
        return result

    return memoized
