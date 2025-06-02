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
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.utils import timezone
from django.core.exceptions import ValidationError # For custom validation

# Use Django's built-in UserCreationForm for simplicity
class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = UserCreationForm.Meta.fields + ('email',)

class TestRequestForm(forms.ModelForm):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all().order_by('name'),
        empty_label="Select Customer",
        help_text="Select the customer for this TVF."
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(), # Initially empty, populated by JS
        empty_label="Select Project",
        help_text="Select the project for this TVF. (Note: Projects are linked to Customers and Environments)"
    )
    tvf_type = forms.ModelChoiceField(
        queryset=TVFType.objects.all().order_by('name'),
        empty_label="Select TVF Type",
        help_text="Select the type of TVF."
    )
    tvf_environment = forms.ModelChoiceField(
        queryset=TVFEnvironment.objects.all().order_by('name'),
        empty_label="Select TVF Environment",
        help_text="Select the environment for this TVF."
    )
    
    request_received_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text="Date and time when the request was received."
    )
    
    request_ship_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        required=False, 
        help_text="Requested ship date for the TVF (calculated based on SLA)."
    )

    trustport_folder_actual = forms.ModelChoiceField(
        queryset=TrustportFolder.objects.none(), # Initially empty, populated by JS
        empty_label="Select Trustport Folder",
        required=False, 
        help_text="Actual Trustport folder used for this specific TVF."
    )

    class Meta:
        model = TestRequest
        fields = [
            'cr_number', 'customer', 'project', 'tvf_name',
            'tvf_type', 'tvf_environment', 'tvf_pin_mailer', 'run_today',
            'request_received_date', 'request_ship_date', 
            's_code', 'd_code', 'comments',
            'trustport_folder_actual', 'pres_config_version', 'proc_config_version', 'pin_config_version',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply form-control class to all text/select/number/date inputs
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.Select, forms.EmailInput, forms.NumberInput, forms.DateTimeInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            
        # Set request_received_date to current time for new instances
        if not self.instance.pk:
            self.fields['request_received_date'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')

        # --- Dynamic Querysets for Project, Trustport Folder ---
        current_customer_id = None
        current_environment_id = None
        current_project_id = None

        if self.data: # Priority for POST requests (submitted data)
            current_customer_id = self.data.get('customer')
            current_environment_id = self.data.get('tvf_environment')
            current_project_id = self.data.get('project')
        elif self.instance.pk: # For existing instances (update view, pre-filled)
            current_customer_id = self.instance.customer_id
            current_environment_id = self.instance.tvf_environment_id
            current_project_id = self.instance.project_id
        # For initial GET requests, these will remain None, and JS handles initial population

        # Convert IDs to int safely
        try:
            current_customer_id = int(current_customer_id) if current_customer_id else None
            current_environment_id = int(current_environment_id) if current_environment_id else None
            current_project_id = int(current_project_id) if current_project_id else None
        except (ValueError, TypeError):
            current_customer_id = None
            current_environment_id = None
            current_project_id = None

        # Populate Project queryset
        if current_customer_id and current_environment_id:
            self.fields['project'].queryset = Project.objects.filter(
                customer_id=current_customer_id,
                tvf_environment_id=current_environment_id
            ).order_by('name')
        else:
            self.fields['project'].queryset = Project.objects.none()

        # Populate Trustport Folder queryset
        if current_customer_id and current_project_id:
            self.fields['trustport_folder_actual'].queryset = TrustportFolder.objects.filter(
                customer_id=current_customer_id, 
                project_id=current_project_id
            ).order_by('folder_path')
        else:
            self.fields['trustport_folder_actual'].queryset = TrustportFolder.objects.none()

# --- TestRequestPlasticCodeForm (for inline formset) ---
class TestRequestPlasticCodeForm(forms.ModelForm):
    # This field uses the lookup table for dropdown selection
    plastic_code_lookup = forms.ModelChoiceField(
        queryset=PlasticCodeLookup.objects.none(), # Initially empty, populated by JS
        empty_label="Select Plastic Code (if in lookup)",
        required=False, # Make it optional if manual entry is allowed
        help_text="Select a plastic code from the lookup list."
    )
    # This new field allows manual entry
    manual_plastic_code = forms.CharField(
        max_length=255, 
        required=False,
        help_text="Enter a plastic code manually if not in the lookup."
    )

    class Meta:
        model = TestRequestPlasticCode
        fields = ['plastic_code_lookup', 'manual_plastic_code', 'quantity', 'thermal_colour']
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'thermal_colour': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.Select, forms.EmailInput, forms.NumberInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
        
        # Dynamically set plastic_code_lookup queryset based on parent TestRequest's customer and project
        current_customer_id = None
        current_project_id = None

        # This logic needs to get customer/project from the *main* TestRequest form
        # This is usually done by passing it in initial, or accessing self.data (from POST)
        # For inline formsets, the parent form's data is available in self.data
        if self.instance.pk and self.instance.test_request: # For existing plastic code entries
            current_customer_id = self.instance.test_request.customer_id
            current_project_id = self.instance.test_request.project_id
        elif self.data: # For new entries in the formset (on POST request)
            # Access parent form's submitted data for customer and project
            main_form_customer_id = self.data.get('customer')
            main_form_project_id = self.data.get('project')

            if main_form_customer_id and main_form_project_id:
                 current_customer_id = main_form_customer_id
                 current_project_id = main_form_project_id
        
        # Convert IDs to int safely
        try:
            current_customer_id = int(current_customer_id) if current_customer_id else None
            current_project_id = int(current_project_id) if current_project_id else None
        except (ValueError, TypeError):
            current_customer_id = None
            current_project_id = None

        if current_customer_id and current_project_id:
            self.fields['plastic_code_lookup'].queryset = PlasticCodeLookup.objects.filter(
                customer_id=current_customer_id,
                project_id=current_project_id
            ).order_by('code')
        else:
            self.fields['plastic_code_lookup'].queryset = PlasticCodeLookup.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        plastic_code_lookup = cleaned_data.get('plastic_code_lookup')
        manual_plastic_code = cleaned_data.get('manual_plastic_code')

        if not plastic_code_lookup and not manual_plastic_code:
            # Only add error if the form is not being deleted
            if self.cleaned_data.get('DELETE') == True:
                pass # Don't validate if marked for deletion
            else:
                raise ValidationError(
                    "Either select a plastic code from the lookup or enter one manually."
                )
        if plastic_code_lookup and manual_plastic_code:
            raise ValidationError(
                "Cannot select a plastic code from the lookup and enter one manually. Please choose one."
            )
        return cleaned_data


# --- TestRequestPANForm (for nested inline formset under TestRequestInputFile) ---
class TestRequestPANForm(forms.ModelForm):
    class Meta:
        model = TestRequestPAN
        fields = ['pan_truncated', 'is_available']
        widgets = {
            'pan_truncated': forms.TextInput(attrs={'class': 'form-control'}),
            'is_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.Select, forms.EmailInput, forms.NumberInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})


# --- TestRequestInputFileForm (with nested PAN formset) ---
class TestRequestInputFileForm(forms.ModelForm):
    class Meta:
        model = TestRequestInputFile
        fields = ['file_name', 'date_file_received', 'card_co', 'card_wo', 'card_qty', 'pin_co', 'pin_wo', 'pin_qty']
        widgets = {
            'file_name': forms.TextInput(attrs={'class': 'form-control'}),
            'date_file_received': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'card_co': forms.TextInput(attrs={'class': 'form-control'}),
            'card_wo': forms.TextInput(attrs={'class': 'form-control'}),
            'card_qty': forms.NumberInput(attrs={'class': 'form-control'}),
            'pin_co': forms.TextInput(attrs={'class': 'form-control'}),
            'pin_wo': forms.TextInput(attrs={'class': 'form-control'}),
            'pin_qty': forms.NumberInput(attrs={'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.Select, forms.EmailInput, forms.NumberInput, forms.DateTimeInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})


# --- TestRequestQualityForm (no changes needed) ---
class TestRequestQualityForm(forms.ModelForm):
    quality_sign_off_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        empty_label="Select Sign-off User",
        required=False,
        help_text="User who signed off on quality."
    )
    class Meta:
        model = TestRequestQuality
        fields = ['output_accordance_request', 'checked_against_specifications', 'quality_sign_off_by', 'quality_sign_off_date']
        widgets = {
            'output_accordance_request': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'checked_against_specifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'quality_sign_off_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.Select, forms.EmailInput, forms.NumberInput, forms.DateTimeInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})

# --- TestRequestShippingForm (removed tracking_number, added detailed address) ---
class TestRequestShippingForm(forms.ModelForm):
    dispatch_method = forms.ModelChoiceField(
        queryset=DispatchMethod.objects.none(), # Will be filtered dynamically
        empty_label="Select Dispatch Method",
        required=False,
        help_text="Method of dispatch."
    )
    shipping_sign_off_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        empty_label="Select Sign-off User",
        required=False,
        help_text="User who signed off on shipping."
    )
    class Meta:
        model = TestRequestShipping
        fields = [
            'dispatch_method', 'shipping_sign_off_by', 'date_shipped',
            'ship_to_name', 'ship_to_business_name', 'ship_to_address_1',
            'ship_to_address_2', 'ship_to_address_3', 'ship_to_city',
            'ship_to_state_province', 'ship_to_postal_code', 'ship_to_country',
        ]
        widgets = {
            'date_shipped': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'ship_to_name': forms.TextInput(attrs={'class': 'form-control'}),
            'ship_to_business_name': forms.TextInput(attrs={'class': 'form-control'}),
            'ship_to_address_1': forms.TextInput(attrs={'class': 'form-control'}),
            'ship_to_address_2': forms.TextInput(attrs={'class': 'form-control'}),
            'ship_to_address_3': forms.TextInput(attrs={'class': 'form-control'}),
            'ship_to_city': forms.TextInput(attrs={'class': 'form-control'}),
            'ship_to_state_province': forms.TextInput(attrs={'class': 'form-control'}),
            'ship_to_postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'ship_to_country': forms.TextInput(attrs={'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.Select, forms.EmailInput, forms.NumberInput, forms.DateTimeInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})

# --- Inline Formset Factories ---

# For Plastic Codes:
PlasticCodeFormSet = inlineformset_factory(
    TestRequest, TestRequestPlasticCode, form=TestRequestPlasticCodeForm,
    extra=1, 
    can_delete=True, # Keep can_delete=True for actual deletion, but hide UI button via JS if needed
    fields=('plastic_code_lookup', 'manual_plastic_code', 'quantity', 'thermal_colour') 
)

# For PANs (nested under InputFile):
PanInlineFormSet = inlineformset_factory(
    TestRequestInputFile, TestRequestPAN, form=TestRequestPANForm,
    extra=1, can_delete=True,
    fields=('pan_truncated', 'is_available') 
)

# For Input Files:
InputFileFormSet = inlineformset_factory(
    TestRequest, TestRequestInputFile, form=TestRequestInputFileForm,
    extra=1, can_delete=True,
    fields=['file_name', 'date_file_received', 'card_co', 'card_wo', 'card_qty', 'pin_co', 'pin_wo', 'pin_qty'] 
)