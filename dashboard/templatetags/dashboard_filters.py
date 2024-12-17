from django import template

register = template.Library()

@register.filter
def format_currency(value):
    if value is None:
        return "R$ 0"
    try:
        # Convert to float if it's a string
        value = float(value)
        # Format with point as thousands separator and comma as decimal separator
        formatted = "{:,.0f}".format(value).replace(",", ".")
        return formatted
    except (ValueError, TypeError):
        return value
    
@register.filter
def multiply(value, arg):
    """Multiplies the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''
