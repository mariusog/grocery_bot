"""Order-processing utilities for the Grocery Bot."""


def get_needed_items(order):
    """Get dict of {item_type: count_still_needed} for an order."""
    needed = {}
    for item in order["items_required"]:
        needed[item] = needed.get(item, 0) + 1
    for item in order["items_delivered"]:
        needed[item] = needed.get(item, 0) - 1
    return {k: v for k, v in needed.items() if v > 0}
