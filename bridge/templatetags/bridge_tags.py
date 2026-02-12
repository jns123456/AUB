"""
Template tags personalizados para la aplicación Bridge.
"""

import json
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='to_json')
def to_json(value):
    """Convierte un valor Python a JSON para usar en templates."""
    return mark_safe(json.dumps(value))
