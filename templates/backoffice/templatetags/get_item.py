from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def get_item(obj: dict, key: str):
    """Safe dict lookup in templates: {{ mydict|get_item:"key" }}"""
    if obj is None:
        return ""
    try:
        return obj.get(key, "")
    except Exception:
        return ""
