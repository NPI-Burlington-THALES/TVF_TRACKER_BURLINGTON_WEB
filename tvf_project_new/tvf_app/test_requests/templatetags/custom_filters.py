# tvf_app/test_requests/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key) if hasattr(dictionary, 'get') else dictionary[key]

@register.filter
def filter_by_current_phase(queryset, phase_name):
    """
    Filters a queryset of TestRequest objects by their current_phase.name.
    Usage: {{ open_tvfs|filter_by_current_phase:'NPI Data Processing' }}
    """
    return queryset.filter(current_phase__name=phase_name)