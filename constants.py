GESTOR_USER = 'gestor'
ANESTESISTA_USER = 'anestesista'
ADMIN_USER = 'admin'

CONSULTA_PROCEDIMENTO = 'consulta'
CIRURGIA_AMBULATORIAL_PROCEDIMENTO = 'cirurgia_procedimento_ambulatorial'

PLANTONISTA_ESCALA = 'plantonista'
SUBSTITUTO_ESCALA = 'substituto'
FERIAS_ESCALA = 'ferias'

STATUS_PENDING = 'pending'
STATUS_FINISHED = 'finished'

# Clinic types for surgical profile filtering and classification
CLINIC_TYPE_CHOICES = [
    ('aparelho_digestivo', 'Aparelho Digestivo'),
    ('cabeca_pescoco', 'Cabeça e Pescoço'),
    ('cardiovascular', 'Cardiovascular'),
    ('coloproctologia', 'Coloproctologia'),
    ('cranio_maxilo_facial', 'Crânio-Maxilo-Facial'),
    ('dermatologia', 'Dermatologia'),
    ('geral', 'Geral'),
    ('ginecologia', 'Ginecologia'),
    ('neurocirurgia', 'Neurocirurgia'),
    ('mastologia', 'Mastologia'),
    ('obstetricia', 'Obstetrícia'),
    ('oftalmologia', 'Oftalmologia'),
    ('oncologica', 'Oncológica'),
    ('ortopedia_traumatologia', 'Ortopedia e Traumatologia'),
    ('otorrinolaringologia', 'Otorrinolaringologia'),
    ('pediatrica', 'Pediátrica'),
    ('plastica', 'Plástica'),
    ('cirurgia_toracica_obstetricia', 'Cirurgia Torácica Obstetrícia'),
    ('broncoscopia', 'Broncoscopia'),
    ('hemodinamica', 'Hemodinâmica'),
    ('radiologia', 'Radiologia'),
    ('toracica', 'Torácica'),
    ('trauma', 'Trauma'),
    ('urologia', 'Urologia'),
    ('vascular', 'Vascular'),
]

ACOMODACAO_CHOICES = [
    ('apartamento', 'Apartamento'),
    ('enfermaria', 'Enfermaria'),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ACOMODACAO_NUMERIC_LABELS = {
    '1': 'Enfermaria',
    '2': 'Apartamento',
    '3': 'Ambulatório',
}

ACOMODACAO_TEXT_LABELS = {
    'enfermaria': 'Enfermaria',
    'apartamento': 'Apartamento',
    'ambulatorio': 'Ambulatório',
    'ambulatório': 'Ambulatório',
}


def acomodacao_to_label(value) -> str:
    """
    Normaliza a acomodação para um rótulo amigável.

    Aceita tanto códigos numéricos (1/2/3) quanto valores textuais.
    """
    if value is None:
        return ''
    raw = str(value).strip()
    if raw == '':
        return ''

    key = raw.lower()
    if key in ACOMODACAO_NUMERIC_LABELS:
        return ACOMODACAO_NUMERIC_LABELS[key]
    if key in ACOMODACAO_TEXT_LABELS:
        return ACOMODACAO_TEXT_LABELS[key]

    return raw