from django.test import TestCase
from datetime import datetime, time
from django.utils import timezone
import pytz

# Import the helper function from financas.views
from financas.views import make_aware_sao_paulo, SAO_PAULO_TZ


class TimezoneHelperTest(TestCase):
    """
    Testes para verificar o comportamento correto do helper de timezone.
    Garante que todos os datetimes são convertidos para o fuso de São Paulo.
    """
    
    def test_make_aware_sao_paulo_with_naive_datetime(self):
        """Verifica que datetime naive é convertido para São Paulo."""
        naive_dt = datetime(2025, 1, 15, 10, 30, 0)
        aware_dt = make_aware_sao_paulo(naive_dt)
        
        self.assertFalse(timezone.is_naive(aware_dt))
        self.assertEqual(aware_dt.tzinfo.zone, 'America/Sao_Paulo')
        # O horário deve permanecer o mesmo (10:30) mas agora com timezone
        self.assertEqual(aware_dt.hour, 10)
        self.assertEqual(aware_dt.minute, 30)
    
    def test_make_aware_sao_paulo_with_already_aware_datetime(self):
        """Verifica que datetime já aware não é modificado."""
        utc_dt = datetime(2025, 1, 15, 13, 30, 0, tzinfo=pytz.UTC)
        result = make_aware_sao_paulo(utc_dt)
        
        # Deve retornar o mesmo datetime sem modificação
        self.assertEqual(result, utc_dt)
        self.assertEqual(result.tzinfo, pytz.UTC)
    
    def test_make_aware_sao_paulo_with_none(self):
        """Verifica que None retorna None."""
        result = make_aware_sao_paulo(None)
        self.assertIsNone(result)
    
    def test_sao_paulo_tz_constant(self):
        """Verifica que a constante SAO_PAULO_TZ está configurada corretamente."""
        self.assertEqual(SAO_PAULO_TZ.zone, 'America/Sao_Paulo')
    
    def test_datetime_conversion_consistency(self):
        """
        Verifica que a conversão é consistente independente do timezone do sistema.
        Um datetime 10:30 naive deve sempre se tornar 10:30 em São Paulo.
        """
        # Simula um horário de procedimento às 10:30
        procedure_time = datetime(2025, 6, 15, 10, 30, 0)  # 10:30 naive
        aware_time = make_aware_sao_paulo(procedure_time)
        
        # Quando convertido para UTC, deve considerar o offset de São Paulo
        # São Paulo em junho (horário de verão não ativo) = UTC-3
        utc_time = aware_time.astimezone(pytz.UTC)
        self.assertEqual(utc_time.hour, 13)  # 10:30 - (-3h) = 13:30 UTC
        self.assertEqual(utc_time.minute, 30)
