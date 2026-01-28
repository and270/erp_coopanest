from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def split(value, arg):
    return value.split(arg)


@register.filter
def acomodacao_label(value):
    """
    Tradução tolerante para tipo de acomodação.
    Aceita códigos 1/2/3 e também valores textuais.
    """
    if value is None:
        return ''

    raw = str(value).strip()
    if raw == '':
        return ''

    key = raw.lower()
    if key == '1':
        return 'Enfermaria'
    if key == '2':
        return 'Apartamento'
    if key == '3':
        return 'Ambulatório'

    if key in ('enfermaria',):
        return 'Enfermaria'
    if key in ('apartamento',):
        return 'Apartamento'
    if key in ('ambulatorio', 'ambulatório'):
        return 'Ambulatório'

    return raw
