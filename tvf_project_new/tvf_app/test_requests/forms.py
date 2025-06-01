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
    # ... (field definitions like customer, project, tvf_environment, etc.) ...
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all().order_by('name'),
        empty_label="Select Customer",
        help_text="Select the customer for this TVF.",
        widget=forms.Select(attrs={'class': 'form-control'}) # Ensure class is applied
<<<<<<< HEAD
=======
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(), # Initially empty, populated by JS
        empty_label="Select Project",
        help_text="Select the project for this TVF. (Note: Projects are linked to Customers and Environments)",
        widget=forms.Select(attrs={'class': 'form-control'}) # Ensure class is applied
    )
    tvf_type = forms.ModelChoiceField(
        queryset=TVFType.objects.all().order_by('name'),
        empty_label="Select TVF Type",
        help_text="Select the type of TVF."
>>>>>>> parent of adbad03 (c)
    )
    tvf_environment = forms.ModelChoiceField(
        queryset=TVFEnvironment.objects.all().order_by('name'),
        empty_label="Select TVF Environment",
        help_text="Select the environment for this TVF.",
        widget=forms.Select(attrs={'class': 'form-control'}) # Ensure class is applied
<<<<<<< HEAD
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(), 
        empty_label="Select Project",
        help_text="Select the project for this TVF. (Populated after Customer and Environment)",
        required=True, # Assuming project is always required
        widget=forms.Select(attrs={'class': 'form-control'}) # Ensure class is applied
    )
    tvf_type = forms.ModelChoiceField(
        queryset=TVFType.objects.all().order_by('name'),
        empty_label="Select TVF Type",
        help_text="Select the type of TVF.",
        widget=forms.Select(attrs={'class': 'form-control'})
=======
>>>>>>> parent of adbad03 (c)
    )
    
    request_received_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text="Date and time when the request was received."
    )
    
    request_ship_date = forms.DateTimeField(
<<<<<<< HEAD
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        required=False,
        help_text="Requested ship date for the TVF (auto-calculated based on SLA)."
=======
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        required=False, 
        help_text="Requested ship date for the TVF (calculated based on SLA)."
>>>>>>> parent of adbad03 (c)
    )

    trustport_folder_actual = forms.ModelChoiceField(
        queryset=TrustportFolder.objects.none(), # Initially empty, populated by JS
        empty_label="Select Trustport Folder",
        required=False, 
        help_text="Actual Trustport folder used for this specific TVF.",
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
        current_project_id = None # For filtering children of project

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
                    current_project_id = int(project_val)
            except (ValueError, TypeError):
                pass
        elif self.instance and self.instance.pk: # Form is for an existing instance
            current_customer_id = self.instance.customer_id
            current_environment_id = self.instance.tvf_environment_id
            current_project_id = self.instance.project_id
<<<<<<< HEAD
        
=======

        # Convert IDs to int safely
        try:
            current_customer_id = int(current_customer_id) if current_customer_id else None
            current_environment_id = int(current_environment_id) if current_environment_id else None
            current_project_id = int(current_project_id) if current_project_id else None
        except (ValueError, TypeError):
            current_customer_id = None
            current_environment_id = None
            current_project_id = None

>>>>>>> parent of adbad03 (c)
        # Populate Project queryset
        if current_customer_id and current_environment_id:
            self.fields['project'].queryset = Project.objects.filter(
                customer_id=current_customer_id,
                tvf_environment_id=current_environment_id
            ).order_by('name')
        else:
            self.fields['project'].queryset = Project.objects.none()

<<<<<<< HEAD
        # Populate Trustport Folder queryset (dependent on customer and project)
=======
        # Populate Trustport Folder queryset
>>>>>>> parent of adbad03 (c)
        if current_customer_id and current_project_id:
            self.fields['trustport_folder_actual'].queryset = TrustportFolder.objects.filter(
                customer_id=current_customer_id, 
                project_id=current_project_id
            ).order_by('folder_path')
        else:
            self.fields['trustport_folder_actual'].queryset = TrustportFolder.objects.none()

# --- TestRequestPlasticCodeForm (for inline formset) ---
class TestRequestPlasticCodeForm(forms.ModelForm):
    plastic_code_lookup = forms.ModelChoiceField(
        queryset=PlasticCodeLookup.objects.none(),
<<<<<<< HEAD
        empty_label="Select Code (Lookup)",
=======
        empty_label="Select Plastic Code (if in lookup)",
>>>>>>> parent of adbad03 (c)
        required=False,
        help_text="Select a plastic code from the lookup list.",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    manual_plastic_code = forms.CharField(
<<<<<<< HEAD
        max_length=255, required=False,
        help_text="Or enter new code manually.",
=======
        max_length=255,
        required=False,
        help_text="Enter a plastic code manually if not in the lookup.",
>>>>>>> parent of adbad03 (c)
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    quantity = forms.IntegerField(widget=forms.NumberInput(attrs={'class': 'form-control'}))


    class Meta:
        model = TestRequestPlasticCode
<<<<<<< HEAD
        fields = ['plastic_code_lookup', 'manual_plastic_code', 'quantity']

    def __init__(self, *args, **kwargs):
        self.parent_customer = kwargs.pop('parent_customer', None)
        self.parent_project = kwargs.pop('parent_project', None)
        self.parent_environment = kwargs.pop('parent_environment', None) # Added for consistency
=======
        fields = ['plastic_code_lookup', 'manual_plastic_code', 'quantity'] # Removed 'thermal_colour'
        # Widgets defined above or applied in __init__

    def __init__(self, *args, **kwargs):
        # Keep existing __init__ logic for styling and dynamic plastic_code_lookup queryset
>>>>>>> parent of adbad03 (c)
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
<<<<<<< HEAD
            if hasattr(field.widget, 'attrs') and 'form-control' not in field.widget.attrs.get('class', ''):
                field.widget.attrs['class'] = field.widget.attrs.get('class', '') + ' form-control'

        if self.parent_customer and self.parent_project and self.parent_environment:
            self.fields['plastic_code_lookup'].queryset = PlasticCodeLookup.objects.filter(
                customer=self.parent_customer,
                project=self.parent_project,
                tvf_environment=self.parent_environment
            ).order_by('code')
        # If bound with data, self.data will be used by Django's validation against this queryset.
=======
            if hasattr(field.widget, 'attrs'):
                current_classes = field.widget.attrs.get('class', '')
                if 'form-control' not in current_classes and not isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs['class'] = f'{current_classes} form-control'.strip()
        
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
>>>>>>> parent of adbad03 (c)

    def clean(self):
        cleaned_data = super().clean()
        lookup = cleaned_data.get('plastic_code_lookup')
        manual = cleaned_data.get('manual_plastic_code')
        if not cleaned_data.get('DELETE', False):
            if not lookup and not manual:
                raise ValidationError("Either select a plastic code from lookup or enter one manually.")
            if lookup and manual:
<<<<<<< HEAD
                raise ValidationError("Plastic Code: Cannot use both lookup and manual entry. Choose one.")
        return cleaned_data


class TestRequestInputFileForm(forms.ModelForm):
    class Meta:
        model = TestRequestInputFile
        fields = ['file_name', 'date_file_received', 'card_co', 'card_wo', 'pin_co', 'pin_wo']
        widgets = {
            'file_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Input File Name'}),
            'date_file_received': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'card_co': forms.TextInput(attrs={'class': 'form-control'}),
            'card_wo': forms.TextInput(attrs={'class': 'form-control'}),
            'pin_co': forms.TextInput(attrs={'class': 'form-control'}),
            'pin_wo': forms.TextInput(attrs={'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs): # Added for styling consistency
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs') and 'form-control' not in field.widget.attrs.get('class', ''):
                 field.widget.attrs['class'] = field.widget.attrs.get('class', '') + ' form-control'


class TestRequestPANForm(forms.ModelForm):
    plastic_code_lookup = forms.ModelChoiceField(
        queryset=PlasticCodeLookup.objects.none(),
=======
                raise ValidationError("Cannot select from lookup and enter manually. Choose one.")
        return cleaned_data


# --- TestRequestPANForm (for nested inline formset under TestRequestInputFile) ---
class TestRequestPANForm(forms.ModelForm):
    plastic_code_lookup = forms.ModelChoiceField(
        queryset=PlasticCodeLookup.objects.none(), # Dynamically populated by JS
>>>>>>> parent of adbad03 (c)
        empty_label="Select Plastic Code (optional)",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control pan-plastic-code-lookup'}) # Added class for JS targeting
    )
    manual_plastic_code_for_pan = forms.CharField(
<<<<<<< HEAD
        max_length=255, required=False,
        help_text="Or enter manual plastic code for this PAN set",
=======
        max_length=255,
        required=False,
        help_text="Or enter manual plastic code for this PAN",
>>>>>>> parent of adbad03 (c)
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = TestRequestPAN
        fields = ['pan_truncated', 'is_available']
        widgets = {
            'pan_truncated': forms.TextInput(attrs={'class': 'form-control'}),
            'is_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
<<<<<<< HEAD
        self.parent_customer = kwargs.pop('parent_customer', None)
        self.parent_project = kwargs.pop('parent_project', None)
        self.parent_environment = kwargs.pop('parent_environment', None) # Added
=======
        # The main form's customer and project IDs will be needed to populate plastic_code_lookup queryset.
        # This is best handled by JavaScript on the client-side for option loading,
        # and by the view ensuring the queryset is correctly set during POST validation if a value is submitted.
>>>>>>> parent of adbad03 (c)
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
<<<<<<< HEAD
            widget = field.widget
            current_classes = widget.attrs.get('class', '')
            if isinstance(widget, forms.CheckboxInput):
                if 'form-check-input' not in current_classes: widget.attrs['class'] = f'{current_classes} form-check-input'.strip()
            elif not isinstance(widget, forms.HiddenInput) and 'form-control' not in current_classes:
                 widget.attrs['class'] = f'{current_classes} form-control'.strip()

        if self.parent_customer and self.parent_project and self.parent_environment:
            self.fields['plastic_code_lookup'].queryset = PlasticCodeLookup.objects.filter(
                customer=self.parent_customer,
                project=self.parent_project,
                tvf_environment=self.parent_environment
            ).order_by('code')
=======
             if hasattr(field.widget, 'attrs'):
                current_classes = field.widget.attrs.get('class', '')
                if 'form-control' not in current_classes and not isinstance(field.widget, (forms.CheckboxInput, forms.Select)):
                    field.widget.attrs['class'] = f'{current_classes} form-control'.strip()
                elif isinstance(field.widget, forms.Select) and 'form-control' not in current_classes:
                    field.widget.attrs['class'] = f'{current_classes} form-control'.strip()
                elif isinstance(field.widget, forms.CheckboxInput) and 'form-check-input' not in current_classes:
                    field.widget.attrs['class'] = f'{current_classes} form-check-input'.strip()
>>>>>>> parent of adbad03 (c)

    def clean(self):
        cleaned_data = super().clean()
        lookup = cleaned_data.get('plastic_code_lookup')
        manual = cleaned_data.get('manual_plastic_code_for_pan')
<<<<<<< HEAD
        if not cleaned_data.get('DELETE', False):
            if lookup and manual:
                raise ValidationError("PAN's Plastic Code: Cannot use both lookup and manual entry. Choose one or leave both blank.")
=======

        # Allow PANs to not have a plastic code specified if that's desired.
        # If a plastic code *is* specified, then one or the other.
        if lookup and manual:
            raise ValidationError("PAN Plastic Code: Cannot select from lookup and enter manually. Choose one or neither.")
>>>>>>> parent of adbad03 (c)
        return cleaned_data

# --- TestRequestInputFileForm (with nested PAN formset) ---
class TestRequestInputFileForm(forms.ModelForm):
    class Meta:
        model = TestRequestInputFile
        fields = ['file_name', 'date_file_received', 'card_co', 'card_wo', 'pin_co', 'pin_wo'] # Removed card_qty, pin_qty
        widgets = {
            'file_name': forms.TextInput(attrs={'class': 'form-control'}),
            'date_file_received': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.Select, forms.EmailInput, forms.NumberInput, forms.DateTimeInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})

<<<<<<< HEAD
class TestRequestQualityForm(forms.ModelForm):
    # ... (remains as is, ensure styling is applied if needed)
    class Meta:
        model = TestRequestQuality
        fields = ['output_accordance_request', 'checked_against_specifications', 'quality_sign_off_by', 'quality_sign_off_date']
    def __init__(self, *args, **kwargs): # Added for styling consistency
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget
            current_classes = widget.attrs.get('class', '')
            if isinstance(widget, forms.CheckboxInput):
                if 'form-check-input' not in current_classes: widget.attrs['class'] = f'{current_classes} form-check-input'.strip()
            elif not isinstance(widget, forms.HiddenInput) and 'form-control' not in current_classes:
                 widget.attrs['class'] = f'{current_classes} form-control'.strip()

=======

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
>>>>>>> parent of adbad03 (c)

# --- TestRequestShippingForm (removed tracking_number, added detailed address) ---
class TestRequestShippingForm(forms.ModelForm):
    dispatch_method = forms.ModelChoiceField(
        queryset=DispatchMethod.objects.none(), # Will be filtered dynamically
        empty_label="Select Dispatch Method",
<<<<<<< HEAD
        required=False, # As per your model and template
        help_text="Method of dispatch."
    )
    # ... (other fields like ship_to_name etc.)
=======
        required=False,
        help_text="Method of dispatch."
    )
    shipping_sign_off_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        empty_label="Select Sign-off User",
        required=False,
        help_text="User who signed off on shipping."
    )
>>>>>>> parent of adbad03 (c)
    class Meta:
        model = TestRequestShipping
        fields = [
            'dispatch_method', 'shipping_sign_off_by', 'date_shipped',
            'ship_to_name', 'ship_to_business_name', 'ship_to_address_1',
            'ship_to_address_2', 'ship_to_address_3', 'ship_to_city',
            'ship_to_state_province', 'ship_to_postal_code', 'ship_to_country',
        ]
<<<<<<< HEAD

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_customer = kwargs.pop('parent_customer', None)
        self.parent_project = kwargs.pop('parent_project', None)
        super().__init__(*args, **kwargs)
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
        
        if self.parent_customer and self.parent_project:
            self.fields['dispatch_method'].queryset = DispatchMethod.objects.filter(
                Q(customer=self.parent_customer, project=self.parent_project) |
                Q(customer__isnull=True, project__isnull=True) # Also include global methods
            ).order_by('name').distinct()
        else: # Fallback if no customer/project context
            self.fields['dispatch_method'].queryset = DispatchMethod.objects.filter(
                 customer__isnull=True, project__isnull=True
            ).order_by('name').distinct()
=======
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
>>>>>>> parent of adbad03 (c)

# --- Inline Formset Factories ---

# --- Inline Formset Factories ---
PlasticCodeFormSet = inlineformset_factory(
    TestRequest, TestRequestPlasticCode, form=TestRequestPlasticCodeForm,
    fields=('plastic_code_lookup', 'manual_plastic_code', 'quantity'),
    extra=1, can_delete=True
)

InputFileFormSet = inlineformset_factory(
    TestRequest, TestRequestInputFile, form=TestRequestInputFileForm,
    fields=('file_name', 'date_file_received', 'card_co', 'card_wo', 'pin_co', 'pin_wo'),
    extra=1, can_delete=True
)

PanInlineFormSet = inlineformset_factory(
    TestRequestInputFile, TestRequestPAN, form=TestRequestPANForm,
    fields=('pan_truncated', 'is_available', 'plastic_code_lookup', 'manual_plastic_code_for_pan'),
    extra=1, can_delete=True
)