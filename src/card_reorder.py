"""
Card reordering and sequence renumbering logic for PromptLens review margin cards.
Supports list reordering, index shifting, and automatic sequence renumbering.
"""

from typing import Any, List, Optional


def reorder_list(items: List[Any], from_index: int, to_index: int) -> List[Any]:
    """
    Move an item from from_index to to_index within the list.
    Returns a new list with the updated order. Clamps indices safely.
    """
    if not items:
        return []
    n = len(items)
    from_index = max(0, min(from_index, n - 1))
    to_index = max(0, min(to_index, n - 1))
    if from_index == to_index:
        return list(items)

    result = list(items)
    item = result.pop(from_index)
    result.insert(to_index, item)
    return result


def move_item_relative(items: List[Any], item: Any, direction: int) -> List[Any]:
    """
    Move an item up (direction = -1) or down (direction = 1) in the list.
    Returns a new list with the updated order.
    """
    if item not in items:
        return list(items)
    curr_idx = items.index(item)
    target_idx = curr_idx + direction
    return reorder_list(items, curr_idx, target_idx)


def renumber_annotation_sequence(items: List[Any], per_type: bool = True) -> None:
    """
    Renumber the index of annotations to match their sequential order.
    If per_type is True, each item_type ('step', 'box', etc.) is numbered 1..N independently.
    Otherwise, all items are numbered sequentially 1..N.
    """
    if per_type:
        type_counters = {}
        for it in items:
            t = getattr(it, "item_type", "box")
            type_counters[t] = type_counters.get(t, 0) + 1
            it.index = type_counters[t]
    else:
        for idx, it in enumerate(items, start=1):
            it.index = idx
