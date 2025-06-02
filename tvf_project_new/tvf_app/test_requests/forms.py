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
from django.db.models import Q # Import Q for complex lookups


# Use Django's built-in UserCreationForm for simplicity
class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = UserCreationForm.Meta.fields + ('email',)

class TestRequestForm(forms.ModelForm):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all().order_by('name'),
        empty_label="Select Customer",
        help_text="Select the customer for this TVF.",
        widget=forms.Select(attrs={'class': 'form-control'}) # Ensure class is applied
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.all().order_by('name'), # Changed from Project.objects.none() to Project.objects.all()
        empty_label="Select Project",
        help_text="Select the project for this TVF. (Populated after Customer and Environment)",
        required=True, # Assuming project is always required
        widget=forms.Select(attrs={'class': 'form-control'}) # Ensure class is applied
    )
    tvf_type = forms.ModelChoiceField(
        queryset=TVFType.objects.all().order_by('name'),
        empty_label="Select TVF Type",
        help_text="Select the type of TVF."
    )
    tvf_environment = forms.ModelChoiceField(
        queryset=TVFEnvironment.objects.all().order_by('name'),
        empty_label="Select TVF Environment",
        help_text="Select the environment for this TVF.",
        widget=forms.Select(attrs={'class': 'form-control'}) # Ensure class is applied
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
        queryset=TrustportFolder.objects.none(),
        empty_label="Select Trustport Folder",
        required=False,
        help_text="Actual Trustport folder used (Populated after Project selection).",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = TestRequest
        fields = [
            'cr_number', 'customer', 'tvf_environment', 'project', 'tvf_name', # Ensure order allows JS to find customer/env first
            'tvf_type', 'tvf_pin_mailer', 'run_today',
            'request_received_date', 'request_ship_date', 
            's_code', 'd_code', 'comments',
            'trustport_folder_actual', 'pres_config_version', 'proc_config_version', 'pin_config_version',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply form-control class to all visible fields for consistent styling
        for field_name, field in self.fields.items():
            # Check if field has a widget and attrs attribute
            if hasattr(field.widget, 'attrs'):
                # Add or update class attribute
                current_classes = field.widget.attrs.get('class', '')
                if 'form-control' not in current_classes and not isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs['class'] = f'{current_classes} form-control'.strip()
                elif isinstance(field.widget, forms.CheckboxInput) and 'form-check-input' not in current_classes:
                     field.widget.attrs['class'] = f'{current_classes} form-check-input'.strip()
            
        if not self.instance.pk: # For new instances
            self.fields['request_received_date'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')

        current_customer_id = None
        current_environment_id = None
        submitted_project_id = None # Used for filtering trustport folder

        if self.is_bound: # Form is submitted with data
            try:
                customer_val = self.data.get('customer')
                if customer_val and customer_val.isdigit():
                    current_customer_id = int(customer_val)
            except (ValueError, TypeError):
                pass 
            try:
                environment_val = self.data.get('tvf_environment')
                if environment_val and environment_val.isdigit():
                    current_environment_id = int(environment_val)
            except (ValueError, TypeError):
                pass
            try:
                project_val = self.data.get('project')
                if project_val and project_val.isdigit():
                    submitted_project_id = int(project_val)
            except (ValueError, TypeError):
                pass

        elif self.instance and self.instance.pk: # Form is for an existing instance (GET request)
            current_customer_id = self.instance.customer_id
            current_environment_id = self.instance.tvf_environment_id
            submitted_project_id = self.instance.project_id

        # Populate Project queryset (dependent on customer and environment)
        # This part now *filters* the initially broad queryset.
        if current_customer_id and current_environment_id:
            self.fields['project'].queryset = Project.objects.filter(
                customer_id=current_customer_id, tvf_environment_id=current_environment_id
            ).order_by('name')
        # Else: The 'project' queryset remains Project.objects.all() (set in class definition)
        # This allows ModelChoiceField to validate against all projects, and customer/environment
        # fields will show their own errors if invalid.

        # Populate Trustport Folder queryset (dependent on customer and *submitted* project)
        if current_customer_id and submitted_project_id:
            self.fields['trustport_folder_actual'].queryset = TrustportFolder.objects.filter(
                customer_id=current_customer_id, project_id=submitted_project_id
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
        # Extract customer_id and project_id from kwargs, if provided
        self.customer_id = kwargs.pop('customer_id', None)
        self.project_id = kwargs.pop('project_id', None)
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

        # Dynamically set plastic_code_lookup queryset
        # Use self.customer_id and self.project_id from kwargs
        if self.customer_id and self.project_id:
            self.fields['plastic_code_lookup'].queryset = PlasticCodeLookup.objects.filter(
                customer_id=self.customer_id,
                project_id=self.project_id
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
        required=False, # As per your model and template
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
        # ... (styling logic as in TestRequestForm) ...
        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs'):
                current_classes = field.widget.attrs.get('class', '')
                if 'form-control' not in current_classes and not isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs['class'] = f'{current_classes} form-control'.strip()

        current_customer_id = None
        current_project_id = None

        # This form is instantiated with an instance of TestRequestShipping in the update view.
        # In the create_tvf_view, it's instantiated without an instance but with a prefix.
        # To get customer/project, we need to look at the parent TestRequest.
        # If this form is part of a larger POST submission that includes the main TestRequest data:
        if self.data: # If form is bound (e.g. during POST validation)
            # Try to get customer/project from the main form's submitted data if available
            # Note: self.data for a prefixed form only contains its own fields.
            # This means the view needs to handle this linkage or pass initial data.
            # For simplicity, we'll assume the view might pass initial data or rely on instance.
            pass

        if self.instance and self.instance.pk and hasattr(self.instance, 'test_request'):
            parent_test_request = self.instance.test_request
            if parent_test_request:
                current_customer_id = parent_test_request.customer_id
                current_project_id = parent_test_request.project_id
        
        # If this form is part of a larger POST submission, and you need to access main form's data:
        # This is tricky. Usually, you'd pass the parent form's cleaned_data or instance when initializing.
        # For now, the AJAX in pm_create_tvf.html updates shipping_form.dispatch_method directly.
        # Let's assume the JS handles populating it. If validation fails and re-renders,
        # the queryset needs to be set based on the submitted parent form data.
        # The `create_tvf_view` should ideally pass initial data or handle this.

        # Fallback based on what TestRequestForm would have submitted for customer/project:
        if self.is_bound: # If there's POST data for this form
            # This is complex as this form doesn't directly contain customer/project fields
            # The filtering for dispatch_method is handled by JavaScript in your template.
            # For server-side validation on POST, if the JS fails or is bypassed, this queryset needs to be correct.
            # One way is to make the view pass 'customer_id' and 'project_id' as initial data to this form
            # if they are available from the main TestRequestForm.
            pass


        if current_customer_id and current_project_id:
            self.fields['dispatch_method'].queryset = DispatchMethod.objects.filter(
                Q(customer_id=current_customer_id, project_id=current_project_id) |
                Q(customer__isnull=True, project__isnull=True) # Global methods
            ).order_by('name')
        else: # Default to only global methods if customer/project context is missing
            self.fields['dispatch_method'].queryset = DispatchMethod.objects.filter(
                customer__isnull=True, project__isnull=True
            ).order_by('name')

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