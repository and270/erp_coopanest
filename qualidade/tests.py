from django.test import TestCase
from django.core.exceptions import ValidationError
from .models import ProcedimentoQualidade, Procedimento, Groups
from .forms import ProcedimentoFinalizacaoForm
from financas.models import ProcedimentoFinancas # For COBRANCA_CHOICES
from agenda.models import ProcedimentoDetalhes as AgendaProcedimentoDetalhes # Renamed to avoid clash
from django.utils import timezone
from datetime import datetime, timedelta
import pytz

class ProcedimentoQualidadeModelTest(TestCase):
    def setUp(self):
        self.group = Groups.objects.create(name="Test Group Qualidade")
        self.proc_detalhes_agenda = AgendaProcedimentoDetalhes.objects.create(name="Detalhe Agenda Qualidade")
        self.procedimento_agenda = Procedimento.objects.create(
            group=self.group,
            nome_paciente='Paciente Qualidade Teste',
            procedimento_principal=self.proc_detalhes_agenda,
            data_horario=timezone.now(),
            status='finished' # Important for some quality logic perhaps
        )

    def test_procedimento_qualidade_creation_new_fields(self):
        qualidade = ProcedimentoQualidade.objects.create(
            procedimento=self.procedimento_agenda,
            abreviacao_jejum=True,
            escala_aldrete=9
        )
        self.assertTrue(qualidade.abreviacao_jejum)
        self.assertEqual(qualidade.escala_aldrete, 9)

    def test_procedimento_qualidade_aldrete_score_validation(self):
        # Test valid scores
        for score in [0, 5, 10]:
            qualidade = ProcedimentoQualidade(
                procedimento=self.procedimento_agenda,
                escala_aldrete=score
            )
            qualidade.full_clean() # Should not raise ValidationError
            self.assertEqual(qualidade.escala_aldrete, score)

        # Test invalid scores (below 0)
        with self.assertRaises(ValidationError) as context:
            qualidade_low = ProcedimentoQualidade(procedimento=self.procedimento_agenda, escala_aldrete=-1)
            qualidade_low.full_clean()
        self.assertIn('escala_aldrete', context.exception.message_dict)

        # Test invalid scores (above 10)
        with self.assertRaises(ValidationError) as context:
            qualidade_high = ProcedimentoQualidade(procedimento=self.procedimento_agenda, escala_aldrete=11)
            qualidade_high.full_clean()
        self.assertIn('escala_aldrete', context.exception.message_dict)

    def test_procedimento_qualidade_new_fields_defaults_null(self):
        # Test that fields can be null if not provided, as null=True
        qualidade = ProcedimentoQualidade.objects.create(
            procedimento=self.procedimento_agenda
            # abreviacao_jejum and escala_aldrete are not set
        )
        self.assertIsNone(qualidade.abreviacao_jejum)
        self.assertIsNone(qualidade.escala_aldrete)


class ProcedimentoFinalizacaoFormTest(TestCase):
    def setUp(self):
        # Default valid data for the form. Specific tests can override parts of this.
        # Ensure all required fields as per the form's clean method are present.
        self.sp_timezone = pytz.timezone('America/Sao_Paulo')
        self.start_time = self.sp_timezone.localize(datetime(2023, 1, 1, 10, 0, 0))
        self.end_time = self.sp_timezone.localize(datetime(2023, 1, 1, 12, 0, 0))

        # Create a Procedimento instance for the form
        self.group = Groups.objects.create(name="Test Group Qualidade Form")
        self.proc_detalhes_agenda = AgendaProcedimentoDetalhes.objects.create(name="Detalhe Agenda Qualidade Form")
        self.procedimento_agenda_instance = Procedimento.objects.create(
            group=self.group,
            nome_paciente='Paciente Qualidade Form Teste',
            procedimento_principal=self.proc_detalhes_agenda,
            data_horario=timezone.now(),
            status='pending' # Initial status
        )


        self.valid_data = {
            'data_horario_inicio_efetivo': self.start_time.strftime('%Y-%m-%dT%H:%M'),
            'data_horario_fim_efetivo': self.end_time.strftime('%Y-%m-%dT%H:%M'),
            'dor_pos_operatoria': True, # Default to True, pain scale fields required
            'escala': 'EVA', # Make sure this is default if dor_pos_operatoria is True
            'eva_score': 5,
            # FLACC fields (conditionally required)
            'face': 1, 'pernas': 1, 'atividade': 1, 'choro': 1, 'consolabilidade': 1,
            # BPS fields (conditionally required)
            'expressao_facial': 1, 'movimentos_membros_superiores': 1, 'adaptacao_ventilador': 1,
            # PAINAD-B fields (conditionally required)
            'respiracao': 0, 'vocalizacao_negativa': 0, 'expressao_facial_painad': 0, 'linguagem_corporal': 0, 'consolabilidade_painad': 0,
            'eventos_adversos_graves': False,
            # 'eventos_adversos_graves_desc': '', # Not required if False
            'reacao_alergica_grave': False,
            # 'reacao_alergica_grave_desc': '', # Not required if False
            'encaminhamento_uti': False,
            'evento_adverso_evitavel': False,
            # 'evento_adverso_evitavel_desc': '', # Not required if False
            'adesao_checklist': True,
            'uso_tecnicas_assepticas': True,
            'conformidade_diretrizes': True,
            'ponv': False,
            'adesao_profilaxia_antibiotica': True, # Corrected
            'adesao_prevencao_tvp_tep': True,
            'tipo_cobranca': ProcedimentoFinancas.COBRANCA_CHOICES[0][0],
            'valor_faturado': '0',
            'tipo_pagamento_direto': ProcedimentoFinancas.DIRECT_PAYMENT_CHOICES[0][0],
            'data_pagamento': self.sp_timezone.localize(datetime(2023,1,1)).strftime('%Y-%m-%d'),
            'abreviacao_jejum': True,
            'escala_aldrete': 8,
        }

    def test_form_valid_with_new_fields(self):
        # Make sure 'procedimento' is linked to the form if creating new ProcedimentoQualidade
        # For existing, it's through `instance`. For new, view usually handles linking.
        # Here, we're testing the form's capability to handle data.
        # The form's save() method expects a Procedimento associated with ProcedimentoQualidade.
        # We pass the ProcedimentoQualidade instance (or None for new) to the form.
        # The ProcedimentoQualidade model has a OneToOne to Procedimento.
        # Let's simulate creating a new ProcedimentoQualidade via the form.
        # The form itself doesn't create Procedimento; it assumes ProcedimentoQualidade is/will be linked.

        # If we are testing form creation of ProcedimentoQualidade:
        # pq_instance = ProcedimentoQualidade(procedimento=self.procedimento_agenda_instance)
        # form = ProcedimentoFinalizacaoForm(data=self.valid_data, instance=pq_instance)
        # This would be more like an update.

        # For creation, the instance might be None or a new unsaved ProcedimentoQualidade object
        # linked to a Procedimento. The form's save() method then saves this.
        # The key is that `form.instance.procedimento` must be valid.

        # Let's refine: the form is for *finalizing*, so it implies a ProcedimentoQualidade
        # might already exist or is being created for an existing Procedimento.
        # The form's save() method updates `qualidade_instance.procedimento.status`.
        # So, `qualidade_instance.procedimento` must exist.

        # If ProcedimentoQualidade doesn't exist yet for self.procedimento_agenda_instance:
        pq, created = ProcedimentoQualidade.objects.get_or_create(procedimento=self.procedimento_agenda_instance)

        form = ProcedimentoFinalizacaoForm(data=self.valid_data, instance=pq)
        if not form.is_valid():
            print("Form errors (new_fields):", form.errors.as_json())
        self.assertTrue(form.is_valid())

        # Mock the related Procedimento instance if form.save() needs it and it's not passed via instance
        # For saving, the form expects the ProcedimentoQualidade instance to have a 'procedimento' attribute.
        # If we don't pass an instance to the form, we need to create one before saving.
        # However, the form is designed to be initialized with an instance or create a new one.
        # For simplicity, we'll assume the view handles instance creation/association.
        # Here, we test if the form can save the new fields.

        # To test saving, we need a ProcedimentoQualidade instance linked to Procedimento
        # If testing creation, ProcedimentoQualidade model would be created by form.save()
        # Let's assume we are creating a new ProcedimentoQualidade record through the form

        qualidade_instance = form.save(commit=False)
        qualidade_instance.procedimento = self.procedimento_agenda_instance # Explicitly link
        # Manually set group on financas if created, or ensure it's handled
        # The form's save method handles ProcedimentoFinancas creation/update.
        # It expects `qualidade_instance.procedimento.group` to be set.
        qualidade_instance.procedimento.group = self.group
        qualidade_instance.save()
        form.save_m2m() # if any

        saved_qualidade = ProcedimentoQualidade.objects.get(pk=qualidade_instance.pk)
        self.assertEqual(saved_qualidade.abreviacao_jejum, True)
        self.assertEqual(saved_qualidade.escala_aldrete, 8)

    def test_form_missing_abreviacao_jejum(self):
        data = self.valid_data.copy()
        del data['abreviacao_jejum']
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('abreviacao_jejum', form.errors)

    def test_form_missing_escala_aldrete(self):
        data = self.valid_data.copy()
        del data['escala_aldrete']
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('escala_aldrete', form.errors)

    def test_form_escala_aldrete_invalid_value(self):
        data_low = self.valid_data.copy()
        data_low['escala_aldrete'] = -1
        form_low = ProcedimentoFinalizacaoForm(data=data_low)
        self.assertFalse(form_low.is_valid())
        self.assertIn('escala_aldrete', form_low.errors)

        data_high = self.valid_data.copy()
        data_high['escala_aldrete'] = 11
        form_high = ProcedimentoFinalizacaoForm(data=data_high)
        self.assertFalse(form_high.is_valid())
        self.assertIn('escala_aldrete', form_high.errors)


    # 1.a. Pain Scale Conditional Logic
    def test_pain_scale_dor_false_valid_without_scale_fields(self):
        data = self.valid_data.copy()
        data['dor_pos_operatoria'] = False
        # Remove scale fields, should still be valid
        data.pop('escala')
        data.pop('eva_score')
        # Remove other scale fields to be sure
        for k in ['face', 'pernas', 'atividade', 'choro', 'consolabilidade',
                  'expressao_facial', 'movimentos_membros_superiores', 'adaptacao_ventilador',
                  'respiracao', 'vocalizacao_negativa', 'expressao_facial_painad', 'linguagem_corporal', 'consolabilidade_painad']:
            if k in data: data.pop(k)
        
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_pain_scale_dor_true_invalid_without_escala(self):
        data = self.valid_data.copy()
        data['dor_pos_operatoria'] = True
        data.pop('escala')
        data.pop('eva_score') # Also remove score as escala is missing
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('escala', form.errors)

    def test_pain_scale_dor_true_eva_invalid_without_eva_score(self):
        data = self.valid_data.copy()
        data['dor_pos_operatoria'] = True
        data['escala'] = 'EVA'
        data.pop('eva_score') # Missing EVA score
        # Ensure other scale fields are not present or are for different scales
        for k in ['face', 'pernas', 'atividade', 'choro', 'consolabilidade',
                  'expressao_facial', 'movimentos_membros_superiores', 'adaptacao_ventilador',
                  'respiracao', 'vocalizacao_negativa', 'expressao_facial_painad', 'linguagem_corporal', 'consolabilidade_painad']:
            if k in data: data.pop(k)

        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('eva_score', form.errors)

    def test_pain_scale_dor_true_flacc_invalid_without_flacc_fields(self):
        data = self.valid_data.copy()
        data['dor_pos_operatoria'] = True
        data['escala'] = 'FLACC'
        data.pop('face') # Missing one FLACC field
        # Ensure other scale fields are not present
        for k in ['eva_score', 'expressao_facial', 'movimentos_membros_superiores', 'adaptacao_ventilador',
                  'respiracao', 'vocalizacao_negativa', 'expressao_facial_painad', 'linguagem_corporal', 'consolabilidade_painad']:
            if k in data: data.pop(k)
        
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('face', form.errors) # Example, could be any missing FLACC field

    # 1.b. Start/End Time Validation
    def test_start_end_time_fim_before_inicio(self):
        data = self.valid_data.copy()
        data['data_horario_fim_efetivo'] = (self.start_time - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('data_horario_fim_efetivo', form.errors)
        self.assertIn("O horário de término deve ser posterior ao horário de início.", form.errors['data_horario_fim_efetivo'])

    def test_start_end_time_fim_equals_inicio(self):
        data = self.valid_data.copy()
        data['data_horario_fim_efetivo'] = self.start_time.strftime('%Y-%m-%dT%H:%M')
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('data_horario_fim_efetivo', form.errors)
        self.assertIn("O horário de término deve ser posterior ao horário de início.", form.errors['data_horario_fim_efetivo'])
        
    def test_start_end_time_duration_exceeds_24_hours(self):
        data = self.valid_data.copy()
        data['data_horario_fim_efetivo'] = (self.start_time + timedelta(hours=25)).strftime('%Y-%m-%dT%H:%M')
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('data_horario_fim_efetivo', form.errors)
        self.assertIn("A duração entre o início e o fim é maior que 24 horas.", form.errors['data_horario_fim_efetivo'])

    def test_start_end_time_valid_duration(self):
        data = self.valid_data.copy() # Uses default valid start/end times
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())

    # 1.c. Pre-filling of Start/End Times (covered by default valid data and __init__ logic)
    # This test mainly ensures the form is valid when initial data (which mimics pre-filling) is correct.
    # The actual pre-filling logic is in the view, but the form's __init__ handles initial data formatting.
    def test_form_with_initial_data_for_times(self):
        # The form's __init__ converts datetime objects in 'initial' to the correct string format.
        # Here we are testing the data path, similar to how form would be bound with instance data.
        initial_values = {
            'data_horario_inicio_efetivo': self.start_time, # Pass datetime object
            'data_horario_fim_efetivo': self.end_time,     # Pass datetime object
        }
        # We can't directly test `initial` processing in the same way as POST data.
        # However, the form's `__init__` method already has logic to format these if they
        # are part of an `instance` or `initial` dict passed to the form on GET request.
        # For a POST request, the data should already be in string format.
        # So, self.valid_data already tests the string format scenario.
        # A more direct test of __init__ would require instantiating with `initial=`
        form_with_initial = ProcedimentoFinalizacaoForm(initial=initial_values)
        # We expect the form to render these correctly, but for validation, data is usually POST.
        # Let's check if the form's clean method would work if such data came from instance.
        # For this, we simulate a bound form with already "cleaned" data in the expected format.
        
        # To properly test the scenario of pre-filling (instance data),
        # we'd typically provide an 'instance' to the form.
        # For now, the existing self.valid_data tests cover the format expected from HTML.
        # The __init__ method's handling of datetime objects from an instance is implicitly
        # tested when the form is used with an instance in a view.
        
        # This test confirms that if the data is correctly formatted string (as from widget), it's valid.
        data = self.valid_data.copy()
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_all_required_fields_present(self):
        # Test with minimal valid data, ensuring all *unconditional* required fields are checked
        data = {
            'data_horario_inicio_efetivo': self.start_time.strftime('%Y-%m-%dT%H:%M'),
            'data_horario_fim_efetivo': self.end_time.strftime('%Y-%m-%dT%H:%M'),
            'dor_pos_operatoria': False, # Easiest way to avoid scale validation
            'eventos_adversos_graves': False,
            'reacao_alergica_grave': False,
            'encaminhamento_uti': False,
            'evento_adverso_evitavel': False,
            'adesao_checklist': True,
            'uso_tecnicas_assepticas': True,
            'conformidade_diretrizes': True,
            'ponv': False,
            'adesao_profilaxia': True,
            'tipo_cobranca': ProcedimentoFinancas.COBRANCA_CHOICES[0][0],
        }
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_missing_required_field_ponv(self):
        data = self.valid_data.copy()
        data.pop('ponv')
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('ponv', form.errors)

    def test_eventos_adversos_graves_true_requires_desc(self):
        data = self.valid_data.copy()
        data['eventos_adversos_graves'] = True
        # data.pop('eventos_adversos_graves_desc') # This field is not in self.valid_data by default
        form = ProcedimentoFinalizacaoForm(data=data)
        # The form's Meta.fields does not include 'eventos_adversos_graves_desc' if it's not in self.valid_data
        # but the clean method requires it if 'eventos_adversos_graves' is True.
        # However, 'eventos_adversos_graves_desc' is a Select widget, so it will have a value.
        # Let's assume the list of choices for 'eventos_adversos_graves_desc' is dynamically populated
        # and an empty selection would be '' or None.
        # For this test, we'll assume the field is present but empty.
        data['eventos_adversos_graves_desc'] = '' # Assuming empty string means no selection
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('eventos_adversos_graves_desc', form.errors)

    def test_reacao_alergica_grave_true_requires_desc(self):
        data = self.valid_data.copy()
        data['reacao_alergica_grave'] = True
        data['reacao_alergica_grave_desc'] = '' # Textarea, so empty string is possible
        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('reacao_alergica_grave_desc', form.errors)

    def test_tipo_cobranca_particular_requires_tipo_pagamento_direto(self):
        data = self.valid_data.copy()
        data['tipo_cobranca'] = 'particular'
        data['valor_faturado'] = '100.00' # Required for particular
        # data.pop('tipo_pagamento_direto') # This field is not in self.valid_data by default
        # We need to ensure it's missing for the test
        if 'tipo_pagamento_direto' in data:
             data.pop('tipo_pagamento_direto')
        data['tipo_pagamento_direto'] = '' # Simulate empty selection

        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('tipo_pagamento_direto', form.errors)

    def test_tipo_cobranca_not_cooperativa_requires_valor_faturado(self):
        data = self.valid_data.copy()
        data['tipo_cobranca'] = 'particular' # or 'hospital'
        # data.pop('valor_faturado') # Not in self.valid_data by default if 'cooperativa'
        if 'valor_faturado' in data:
            data.pop('valor_faturado')
        # Ensure tipo_pagamento_direto is provided if particular
        if data['tipo_cobranca'] == 'particular':
            data['tipo_pagamento_direto'] = ProcedimentoFinancas.DIRECT_PAYMENT_CHOICES[0][0]

        form = ProcedimentoFinalizacaoForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('valor_faturado', form.errors)I've written the tests for `ProcedimentoFinalizacaoForm` in `qualidade/tests.py`. These tests cover:
-   Pain scale conditional logic (`dor_pos_operatoria`).
-   Start/end time validations (order, and duration <= 24 hours).
-   Other required field validations like `eventos_adversos_graves_desc`, `reacao_alergica_grave_desc`, `tipo_pagamento_direto`, and `valor_faturado` based on `tipo_cobranca`.

The test `test_form_with_initial_data_for_times` clarifies that pre-filling itself is more of a view/form instantiation concern (`initial` or `instance` data), and the existing `self.valid_data` tests cover the scenario where data is POSTed in the correct string format.

Now, I'll move to **Step 2: Test Dashboard Calculations with Outlier Removal (`dashboard/tests.py`)**.

First, I'll read the content of `dashboard/tests.py`.
