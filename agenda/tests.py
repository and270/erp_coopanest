from django.test import TestCase
from django.urls import reverse
from .models import Procedimento, Groups, Convenios, ProcedimentoDetalhes, HospitalClinic, Surgeon
from .forms import ProcedimentoForm
from registration.models import CustomUser, Anesthesiologist
from django.utils import timezone
import datetime

class ProcedimentoModelTest(TestCase):
    def setUp(self):
        self.group = Groups.objects.create(name="Test Group Agenda")
        self.convenio = Convenios.objects.create(name="Test Convenio")
        self.proc_detalhes = ProcedimentoDetalhes.objects.create(name="Test Proc Detalhes")
        self.hospital = HospitalClinic.objects.create(name="Test Hospital", group=self.group)
        self.cirurgiao = Surgeon.objects.create(name="Test Surgeon", group=self.group)


    def test_procedimento_creation_with_tipo(self):
        procedimento = Procedimento.objects.create(
            group=self.group,
            nome_paciente='Paciente Teste',
            procedimento_principal=self.proc_detalhes,
            data_horario=timezone.now(),
            hospital=self.hospital,
            tipo_procedimento='urgencia'
        )
        self.assertEqual(procedimento.tipo_procedimento, 'urgencia')
        self.assertEqual(str(procedimento), f'{self.proc_detalhes} - Paciente Teste')

    def test_procedimento_default_tipo(self):
        procedimento = Procedimento.objects.create(
            group=self.group,
            nome_paciente='Paciente Default',
            procedimento_principal=self.proc_detalhes,
            hospital=self.hospital,
            data_horario=timezone.now()
            # tipo_procedimento is not set, should use default 'eletiva'
        )
        self.assertEqual(procedimento.tipo_procedimento, 'eletiva')


class ProcedimentoFormTest(TestCase):
    def setUp(self):
        self.group = Groups.objects.create(name="Test Group Form Agenda")
        self.user = CustomUser.objects.create_user(username='testuseragenda', password='password', group=self.group, user_type=1, validado=True) # Gestor
        self.proc_detalhes = ProcedimentoDetalhes.objects.create(name="Detalhe Teste Form")
        self.hospital = HospitalClinic.objects.create(name="Hospital Test Form", group=self.group)
        self.surgeon = Surgeon.objects.create(name="Surgeon Test Form", group=self.group)
        Anesthesiologist.objects.create(name="Anes Test Form", user=self.user, group=self.group)


        self.form_data = {
            'nome_paciente': 'Paciente Form Teste',
            'email_paciente': 'paciente@teste.com',
            'cpf_paciente': '12345678900',
            'convenio_nome_novo': 'Novo Convenio Form', # Testing new convenio creation
            'procedimento_principal': self.proc_detalhes.id,
            'hospital': self.hospital.id,
            'cirurgiao': self.surgeon.id,
            'data': '01/01/2025',
            'time': '10:00',
            'end_time': '12:00',
            'visita_pre_anestesica': True,
            'data_visita_pre_anestesica': '31/12/2024',
            'nome_responsavel_visita': 'Dr. Visita',
            'tipo_procedimento': 'eletiva', # New field
        }

    def test_procedimento_form_valid_with_tipo_procedimento(self):
        form = ProcedimentoForm(data=self.form_data, user=self.user)
        if not form.is_valid():
            print("Form errors:", form.errors.as_json())
        self.assertTrue(form.is_valid())

        procedimento = form.save(commit=False)
        procedimento.group = self.group # Group might need to be set explicitly if not handled by form's user logic fully for test
        procedimento.save()
        form.save_m2m()

        self.assertEqual(procedimento.tipo_procedimento, 'eletiva')
        self.assertEqual(procedimento.nome_paciente, 'Paciente Form Teste')
        self.assertIsNotNone(procedimento.convenio)
        self.assertEqual(procedimento.convenio.name, 'Novo Convenio Form')


    def test_procedimento_form_tipo_procedimento_choices(self):
        form = ProcedimentoForm(user=self.user)
        self.assertIn('tipo_procedimento', form.fields)
        choices = form.fields['tipo_procedimento'].widget.choices
        # First choice is often empty_label if not overridden
        # Actual choices from model are ('urgencia', 'Urgência'), ('eletiva', 'Eletiva')
        # The widget might reformat them slightly, e.g. if using Select widget
        # Let's check the values
        choice_values = [choice[0] for choice in choices if choice[0]] # Exclude empty label
        self.assertIn('urgencia', choice_values)
        self.assertIn('eletiva', choice_values)

    def test_procedimento_form_missing_tipo_procedimento(self):
        # Default is 'eletiva' in model, so form should be valid if not provided,
        # and the model's default will be used.
        # However, if the field is explicitly made required in the form without a default, this would fail.
        # Current model has default='eletiva', null=True, blank=True.
        # Form field by default will be required if model field is not blank=True.
        # Let's check if the model's blank=True makes the form field not required.
        data = self.form_data.copy()
        del data['tipo_procedimento']
        form = ProcedimentoForm(data=data, user=self.user)

        # If model field has blank=True, form field should have required=False
        # If model field has default, form field might not need it if required=False
        self.assertTrue(form.fields['tipo_procedimento'].required is False or form.fields['tipo_procedimento'].initial is not None)

        if not form.is_valid():
            print("Form errors (missing tipo_procedimento):", form.errors.as_json())
        self.assertTrue(form.is_valid()) # Should be valid due to model's default and blank=True

        procedimento = form.save(commit=False)
        procedimento.group = self.group
        procedimento.save()
        self.assertEqual(procedimento.tipo_procedimento, 'eletiva') # Model default
