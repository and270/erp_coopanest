from django import forms
from constants import ANESTESISTA_USER, GESTOR_USER, SECRETARIA_USER
from registration.models import Anesthesiologist, CustomUser, Groups, HospitalClinic, Surgeon
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class CustomUserCreationForm(UserCreationForm):
    group = forms.ModelChoiceField(
        queryset=Groups.objects.all().order_by('name'), 
        required=False, 
        label='Selecione seu Grupo'
    )
    new_group = forms.CharField(required=False, label='Registre o nome do seu Grupo')
    new_group_email = forms.EmailField(required=False, label='E-mail do Grupo')
    create_new_group = forms.BooleanField(
        required=False, 
        label='Criar novo grupo',
        widget=forms.CheckboxInput(attrs={'id': 'id_create_new_group'})
    )
    agree_terms = forms.BooleanField(required=True, label='Concordo com os Termos de Serviço')
    agree_privacy = forms.BooleanField(required=True, label='Concordo com a Política de Privacidade')

    class Meta:
        model = CustomUser
        fields = (
            'email', 'user_type', 'create_new_group', 'group', 
            'new_group', 'new_group_email', 'password1', 'password2', 
            'agree_terms', 'agree_privacy'
        )
        labels = {
            'email': 'E-mail',
            'user_type': 'Tipo de usuário',
            'password1': 'Senha',
            'password2': 'Confirme a senha',
        }

    def clean(self):
        cleaned_data = super().clean()
        user_type = cleaned_data.get("user_type")
        create_new_group = cleaned_data.get("create_new_group")
        group = cleaned_data.get("group")
        new_group = cleaned_data.get("new_group")
        new_group_email = cleaned_data.get("new_group_email")

        # Validation rules for Gestor or other user types
        if user_type == GESTOR_USER:
            if create_new_group and not new_group:
                raise forms.ValidationError("Por favor, insira o nome do novo grupo.")
            elif create_new_group and not new_group_email:
                raise forms.ValidationError("Por favor, insira o e-mail do novo grupo.")
            elif not create_new_group and not group:
                raise forms.ValidationError("Por favor, selecione um grupo.")
        elif user_type != GESTOR_USER and not group:
            raise forms.ValidationError("Por favor, selecione um grupo.")

        return cleaned_data

    def save(self, commit=True):
        """Create the user and also create a Membership record 
           for the chosen/created group.
        """
        user = super().save(commit=False)
        user_type = self.cleaned_data.get("user_type")
        create_new_group = self.cleaned_data.get("create_new_group")
        group = self.cleaned_data.get("group")
        new_group = self.cleaned_data.get("new_group")
        new_group_email = self.cleaned_data.get("new_group_email")

        # Decide which group is "active" for the user
        if user_type == GESTOR_USER:
            if create_new_group:
                # Create new group
                group_obj, created = Groups.objects.get_or_create(
                    name=new_group,
                    defaults={'email': new_group_email}
                )
                user.group = group_obj
            else:
                user.group = group
        else:
            user.group = group

        if commit:
            user.save()  # Save the user first, so we can reference user in the membership

            # Create a membership for the group
            from registration.models import Membership
            Membership.objects.create(
                user=user,
                group=user.group,
                validado=False  # default false; can be changed by an admin later
            )

        return user


class CustomUserLoginForm(AuthenticationForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'password')
        labels = {
            'email': 'E-mail',
            'password': 'Senha',
        }

class AnesthesiologistForm(forms.ModelForm):
    class Meta:
        model = Anesthesiologist
        fields = ['user', 'name', 'date_of_birth', 'cpf', 'function', 'crm', 'phone', 'email', 'role_in_group', 'admission_date', 'responsible_hours']
        labels = {
            'user': 'Usuário',
            'name': 'Nome',
            'date_of_birth': 'Data de Nascimento',
            'cpf': 'CPF',
            'function': 'Função',
            'crm': 'CRM',
            'phone': 'Telefone',
            'email': 'E-mail',
            'role_in_group': 'Cargo no grupo',
            'admission_date': 'Data de Admissão',
            'responsible_hours': 'Horário Responsável',
        }
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'class': 'date-input'}),
            'admission_date': forms.DateInput(attrs={'class': 'date-input'}),
            'phone': forms.TextInput(attrs={'class': 'phone-mask'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            self.fields['user'].queryset = CustomUser.objects.filter(
                user_type=ANESTESISTA_USER, 
                group=user.group
            ).order_by('email')
        
        # Add this line to change the empty label
        self.fields['user'].empty_label = "Selecione se for um Anestesista cadastrado"

        for field in self.fields:
            self.fields[field].initial = None

    def clean_user(self):
        user = self.cleaned_data.get('user')
        if user and user.user_type != ANESTESISTA_USER:
            raise ValidationError(_('O usuário selecionado não é um Anestesista.'))
        return user
    
    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if user:
            instance.group = user.group  # Set the group to the same as the creating user's group
        if commit:
            instance.save()
        return instance

class SurgeonForm(forms.ModelForm):
    class Meta:
        model = Surgeon
        fields = ['name', 'specialty', 'crm', 'phone', 'notes']
        labels = {
            'name': 'Nome',
            'specialty': 'Especialidade',
            'crm': 'CRM',
            'phone': 'Telefone',
            'notes': 'Sugestões de anestesia',
        }
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'phone-mask'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].initial = None

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if user:
            instance.group = user.group  # Set the group to the same as the creating user's group
        if commit:
            instance.save()
        return instance

class HospitalClinicForm(forms.ModelForm):
    class Meta:
        model = HospitalClinic
        fields = ['name', 'address', 'surgery_center_phone', 'hospital_phone']
        labels = {
            'name': 'Nome',
            'address': 'Endereço',
            'surgery_center_phone': 'Telefone do Centro Cirúrgico',
            'hospital_phone': 'Telefone do Hospital',
        }
        widgets = {
            'surgery_center_phone': forms.TextInput(attrs={'class': 'phone-mask'}),
            'hospital_phone': forms.TextInput(attrs={'class': 'phone-mask'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['address'].required = False
        self.fields['surgery_center_phone'].required = False
        self.fields['hospital_phone'].required = False
        for field in self.fields:
            self.fields[field].initial = None

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if user:
            instance.group = user.group  # Set the group to the same as the creating user's group
        if commit:
            instance.save()
        return instance
    
class AddGroupMembershipForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=Groups.objects.all().order_by('name'),
        required=False,
        label='Selecione um grupo existente'
    )
    create_new_group = forms.BooleanField(
        required=False,
        label='Criar novo grupo'
    )
    new_group = forms.CharField(
        required=False,
        label='Nome do novo grupo'
    )
    new_group_email = forms.EmailField(
        required=False,
        label='E-mail do novo grupo'
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # If user is not a Gestor, remove the fields for creating a new group
        if not self.user or self.user.user_type != GESTOR_USER:
            self.fields.pop('create_new_group')
            self.fields.pop('new_group')
            self.fields.pop('new_group_email')

    def clean(self):
        cleaned_data = super().clean()
        # Because for non-gestor, we have already popped the fields out,
        # the code below only applies to a Gestor user.
        create_new_group = cleaned_data.get('create_new_group')
        group = cleaned_data.get('group')
        new_group = cleaned_data.get('new_group')
        new_group_email = cleaned_data.get('new_group_email')

        if self.user and self.user.user_type == GESTOR_USER:
            if create_new_group:
                if not new_group or not new_group_email:
                    raise ValidationError("Por favor, preencha o nome e e-mail do novo grupo.")
            else:
                if not group:
                    raise ValidationError("Por favor, selecione um grupo existente ou crie um novo.")
        else:
            # Non-gestor logic:
            #   - We have removed those fields entirely,
            #     so the only requirement left is that group is selected.
            if not group:
                raise ValidationError("Por favor, selecione um grupo existente.")

        return cleaned_data

    def create_or_get_group(self):
        """Return the group object the user wants to join (or has created).
           For gestor creating a new group, create it. Otherwise, just use `group`.
        """
        create_new_group = self.cleaned_data.get('create_new_group')
        group = self.cleaned_data.get('group')
        new_group = self.cleaned_data.get('new_group')
        new_group_email = self.cleaned_data.get('new_group_email')

        if self.user and self.user.user_type == GESTOR_USER and create_new_group:
            group_obj, created = Groups.objects.get_or_create(
                name=new_group,
                defaults={'email': new_group_email}
            )
            return group_obj
        else:
            return group
