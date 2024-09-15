from django import template
from datetime import datetime, time, timedelta

register = template.Library()

@register.simple_tag
def slot_start_time(date_obj, hour):
    return datetime.combine(date_obj, time(hour=int(hour)))

@register.filter
def add_timedelta(value, arg):
    h, m, s = map(int, arg.split(':'))
    return value + timedelta(hours=h, minutes=m, seconds=s)
