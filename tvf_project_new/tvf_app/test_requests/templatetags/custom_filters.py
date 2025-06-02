# tvf_app/test_requests/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key) if hasattr(dictionary, 'get') else dictionary[key]