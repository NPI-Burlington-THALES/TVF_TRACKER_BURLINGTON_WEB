# tvf_app/test_requests/forms.py

from django import forms
from django.forms import inlineformset_factory
from .models import (
    TestRequest, Customer, Project, TVFType, TVFEnvironment, TVFStatus,
    PlasticCodeLookup, DispatchMethod, TestRequestPhaseDefinition,
    TestRequestPlasticCode, TestRequestInputFile, TestRequestPAN,
    TestRequestQuality, TestRequestShipping, RejectReason, TrustportFolder
)
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = UserCreationForm.Meta.fields + ('email',)

class TestRequestForm(forms.ModelForm):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all().order_by('name'),
        empty_label="Select Customer",
        help_text="Select the customer for this TVF.",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    tvf_environment = forms.ModelChoiceField(
        queryset=TVFEnvironment.objects.all().order_by('name'),
        empty_label="Select TVF Environment",
        help_text="Select the environment for this TVF.",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        empty_label="Select Project",
        help_text="Select the project (Populated after Customer and Environment).",
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    tvf_type = forms.ModelChoiceField(
        queryset=TVFType.objects.all().order_by('name'),
        empty_label="Select TVF Type",
        help_text="Select the type of TVF.",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    request_received_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        help_text="Date and time when the request was received."
    )
    request_ship_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        required=False,
        help_text="Requested ship date for the TVF (calculated based on SLA)."
    )
    trustport_folder_actual = forms.ModelChoiceField(
        queryset=TrustportFolder.objects.none(),
        empty_label="Select Trustport Folder",
        required=False,
        help_text="Actual Trustport folder used (Populated after Project selection).",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = TestRequest
        fields = [
            'cr_number', 'customer', 'tvf_environment', 'project', 'tvf_name',
            'tvf_type', 'tvf_pin_mailer', 'run_today',
            'request_received_date', 'request_ship_date',
            's_code', 'd_code', 'comments',
            'trustport_folder_actual', 'pres_config_version', 'proc_config_version', 'pin_config_version',
        ]
        # Removed tvf_initiator, status, current_phase as they are set in the view

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget
            current_classes = widget.attrs.get('class', '')
            if isinstance(widget, forms.CheckboxInput):
                if 'form-check-input' not in current_classes:
                    widget.attrs['class'] = f'{current_classes} form-check-input'.strip()
            elif isinstance(widget, forms.DateTimeInput):
                 # DateTimeInput already has 'form-control' from its definition if type is datetime-local
                if 'form-control' not in current_classes: # Add if not already
                     widget.attrs['class'] = f'{current_classes} form-control'.strip()
            elif isinstance(widget, forms.Select):
                 if 'form-control' not in current_classes: # Add if not already from field def
                    widget.attrs['class'] = f'{current_classes} form-control'.strip()
            elif not isinstance(widget, forms.HiddenInput):
                 if 'form-control' not in current_classes:
                    widget.attrs['class'] = f'{current_classes} form-control'.strip()

        if not self.instance.pk and 'request_received_date' in self.fields:
            self.fields['request_received_date'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')

        current_customer_id = None
        current_environment_id = None
        current_project_id = None

        if self.is_bound:
            try:
                customer_val = self.data.get('customer')
                if customer_val and customer_val.isdigit(): current_customer_id = int(customer_val)
            except (ValueError, TypeError): pass
            try:
                environment_val = self.data.get('tvf_environment')
                if environment_val and environment_val.isdigit(): current_environment_id = int(environment_val)
            except (ValueError, TypeError): pass
            try:
                project_val = self.data.get('project')
                if project_val and project_val.isdigit(): current_project_id = int(project_val)
            except (ValueError, TypeError): pass
        elif self.instance and self.instance.pk:
            current_customer_id = self.instance.customer_id
            current_environment_id = self.instance.tvf_environment_id
            current_project_id = self.instance.project_id

        if current_customer_id and current_environment_id:
            self.fields['project'].queryset = Project.objects.filter(
                customer_id=current_customer_id, tvf_environment_id=current_environment_id
            ).order_by('name')
        else:
            self.fields['project'].queryset = Project.objects.none()

        if current_customer_id and current_project_id:
            self.fields['trustport_folder_actual'].queryset = TrustportFolder.objects.filter(
                customer_id=current_customer_id, project_id=current_project_id
            ).order_by('folder_path')
        else:
            self.fields['trustport_folder_actual'].queryset = TrustportFolder.objects.none()


class TestRequestPlasticCodeForm(forms.ModelForm):
    plastic_code_lookup = forms.ModelChoiceField(
        queryset=PlasticCodeLookup.objects.none(), # Dynamically populated
        empty_label="Select Plastic Code (from lookup)",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    manual_plastic_code = forms.CharField(
        max_length=255,
        required=False,
        help_text="Or enter new plastic code manually.",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Qty'})
    )

    class Meta:
        model = TestRequestPlasticCode
        fields = ['plastic_code_lookup', 'manual_plastic_code', 'quantity'] # thermal_colour removed

    def __init__(self, *args, **kwargs):
        # Capture main form's customer and project if passed for dynamic queryset population
        self.parent_customer = kwargs.pop('parent_customer', None)
        self.parent_project = kwargs.pop('parent_project', None)
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs'):
                current_classes = field.widget.attrs.get('class', '')
                if 'form-control' not in current_classes and not isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs['class'] = f'{current_classes} form-control'.strip()

        if self.parent_customer and self.parent_project:
            self.fields['plastic_code_lookup'].queryset = PlasticCodeLookup.objects.filter(
                customer=self.parent_customer, project=self.parent_project
            ).order_by('code')
        # If data is bound (POST), the view should ideally ensure the queryset is correct for validation.
        # For now, JS will handle populating options. Server-side will validate against this queryset.

    def clean(self):
        cleaned_data = super().clean()
        lookup = cleaned_data.get('plastic_code_lookup')
        manual = cleaned_data.get('manual_plastic_code')

        if not self.cleaned_data.get('DELETE', False): # Only validate if not deleting
            if not lookup and not manual:
                raise ValidationError("Plastic Code: Please select from lookup or enter one manually.")
            if lookup and manual:
                raise ValidationError("Plastic Code: Cannot select from lookup and enter manually. Please choose one.")
        return cleaned_data


class TestRequestInputFileForm(forms.ModelForm):
    class Meta:
        model = TestRequestInputFile
        # card_qty and pin_qty removed
        fields = ['file_name', 'date_file_received', 'card_co', 'card_wo', 'pin_co', 'pin_wo']
        widgets = {
            'file_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Input File Name'}),
            'date_file_received': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'card_co': forms.TextInput(attrs={'class': 'form-control'}),
            'card_wo': forms.TextInput(attrs={'class': 'form-control'}),
            'pin_co': forms.TextInput(attrs={'class': 'form-control'}),
            'pin_wo': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs'):
                current_classes = field.widget.attrs.get('class', '')
                if 'form-control' not in current_classes and not isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs['class'] = f'{current_classes} form-control'.strip()


class TestRequestPANForm(forms.ModelForm):
    # New fields for plastic code context within PAN entry
    plastic_code_lookup = forms.ModelChoiceField(
        queryset=PlasticCodeLookup.objects.none(), # Dynamically populated by JS based on main form's C/P
        empty_label="Select Plastic Code (optional)",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control pan-plastic-code-lookup'})
    )
    manual_plastic_code_for_pan = forms.CharField(
        max_length=255,
        required=False,
        help_text="Or enter manual plastic code for this PAN set",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = TestRequestPAN
        fields = ['pan_truncated', 'is_available', 'plastic_code_lookup', 'manual_plastic_code_for_pan']
        widgets = {
            'pan_truncated': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last 4-8 of PAN'}),
            'is_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.parent_customer = kwargs.pop('parent_customer', None)
        self.parent_project = kwargs.pop('parent_project', None)
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            widget = field.widget
            current_classes = widget.attrs.get('class', '')
            if isinstance(widget, forms.CheckboxInput):
                if 'form-check-input' not in current_classes:
                    widget.attrs['class'] = f'{current_classes} form-check-input'.strip()
            elif isinstance(widget, forms.Select):
                if 'form-control' not in current_classes : # Ensure .pan-plastic-code-lookup isn't overridden if it should stay
                    if 'pan-plastic-code-lookup' in current_classes:
                         widget.attrs['class'] = f'{current_classes} form-control'.strip() # Add form-control
                    else:
                        widget.attrs['class'] = f'{current_classes} form-control'.strip()

            elif not isinstance(widget, forms.HiddenInput):
                if 'form-control' not in current_classes:
                    widget.attrs['class'] = f'{current_classes} form-control'.strip()

        if self.parent_customer and self.parent_project:
            self.fields['plastic_code_lookup'].queryset = PlasticCodeLookup.objects.filter(
                customer=self.parent_customer, project=self.parent_project
            ).order_by('code')


    def clean(self):
        cleaned_data = super().clean()
        lookup = cleaned_data.get('plastic_code_lookup')
        manual = cleaned_data.get('manual_plastic_code_for_pan')

        if not self.cleaned_data.get('DELETE', False):
            # If a plastic code context is intended for this PAN, one or the other.
            # If both are blank, it means no specific plastic code is associated with this PAN.
            if lookup and manual:
                raise ValidationError(
                    "PAN's Plastic Code: Cannot select from lookup and enter manually. Please choose one or leave both blank if not applicable."
                )
        return cleaned_data


# --- Quality and Shipping Forms (no changes from your requirements to these forms themselves) ---
class TestRequestQualityForm(forms.ModelForm):
    quality_sign_off_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        empty_label="Select Sign-off User", required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    quality_sign_off_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        required=False
    )
    output_accordance_request = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class':'form-check-input'}))
    checked_against_specifications = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class':'form-check-input'}))


    class Meta:
        model = TestRequestQuality
        fields = ['output_accordance_request', 'checked_against_specifications', 'quality_sign_off_by', 'quality_sign_off_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items(): # Basic styling
             widget = field.widget
             current_classes = widget.attrs.get('class', '')
             if isinstance(widget, forms.CheckboxInput):
                 if 'form-check-input' not in current_classes: widget.attrs['class'] = f'{current_classes} form-check-input'.strip()
             elif not isinstance(widget, forms.HiddenInput) and 'form-control' not in current_classes:
                 widget.attrs['class'] = f'{current_classes} form-control'.strip()


class TestRequestShippingForm(forms.ModelForm):
    dispatch_method = forms.ModelChoiceField(
        queryset=DispatchMethod.objects.none(), # Dynamically populated by JS / View
        empty_label="Select Dispatch Method", required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    shipping_sign_off_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        empty_label="Select Sign-off User", required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    date_shipped = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        required=False
    )

    class Meta:
        model = TestRequestShipping
        fields = [
            'dispatch_method', 'shipping_sign_off_by', 'date_shipped',
            'ship_to_name', 'ship_to_business_name', 'ship_to_address_1',
            'ship_to_address_2', 'ship_to_address_3', 'ship_to_city',
            'ship_to_state_province', 'ship_to_postal_code', 'ship_to_country',
        ]
    
    def __init__(self, *args, **kwargs):
        self.parent_customer = kwargs.pop('parent_customer', None)
        self.parent_project = kwargs.pop('parent_project', None)
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items(): # Basic styling
             widget = field.widget
             current_classes = widget.attrs.get('class', '')
             if isinstance(widget, forms.CheckboxInput):
                 if 'form-check-input' not in current_classes: widget.attrs['class'] = f'{current_classes} form-check-input'.strip()
             elif not isinstance(widget, forms.HiddenInput) and 'form-control' not in current_classes:
                 widget.attrs['class'] = f'{current_classes} form-control'.strip()
        
        if self.parent_customer and self.parent_project:
            self.fields['dispatch_method'].queryset = DispatchMethod.objects.filter(
                Q(customer=self.parent_customer, project=self.parent_project) |
                Q(customer__isnull=True, project__isnull=True)
            ).order_by('name')
        else:
            self.fields['dispatch_method'].queryset = DispatchMethod.objects.filter(
                 customer__isnull=True, project__isnull=True # Fallback to global
            ).order_by('name')


# --- Updated Inline Formset Factories ---
PlasticCodeFormSet = inlineformset_factory(
    TestRequest,
    TestRequestPlasticCode,
    form=TestRequestPlasticCodeForm,
    fields=('plastic_code_lookup', 'manual_plastic_code', 'quantity'),
    extra=1,
    can_delete=True
)

InputFileFormSet = inlineformset_factory(
    TestRequest,
    TestRequestInputFile,
    form=TestRequestInputFileForm,
    fields=('file_name', 'date_file_received', 'card_co', 'card_wo', 'pin_co', 'pin_wo'),
    extra=1,
    can_delete=True
)

# For PANs (nested under InputFile)
PanInlineFormSet = inlineformset_factory(
    TestRequestInputFile,
    TestRequestPAN,
    form=TestRequestPANForm,
    fields=('pan_truncated', 'is_available', 'plastic_code_lookup', 'manual_plastic_code_for_pan'),
    extra=1,
    can_delete=True
)