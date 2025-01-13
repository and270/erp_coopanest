from django import template

register = template.Library()

@register.filter
def replace(value, arg):
    """
    Replace comma with dot for Brazilian number format
    """
    return value.replace(arg[0], arg[1])