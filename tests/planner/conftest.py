"""Shared fixtures and helpers for planner tests."""


def _active_order(items_required, items_delivered=None):
    return {
        "id": "order_0",
        "items_required": items_required,
        "items_delivered": items_delivered or [],
        "complete": False,
        "status": "active",
    }


def _preview_order(items_required, items_delivered=None):
    return {
        "id": "order_1",
        "items_required": items_required,
        "items_delivered": items_delivered or [],
        "complete": False,
        "status": "preview",
    }
