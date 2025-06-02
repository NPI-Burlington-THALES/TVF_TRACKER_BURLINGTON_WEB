# tvf_app/test_requests/views.py
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
from django.contrib import messages
from .forms import CustomUserCreationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required, user_passes_test
from datetime import timedelta
from django.utils import timezone
from django.forms import formset_factory # Not directly used for inlineformset_factory, but good to have if needed for standalone formsets.
from django.db.models import Q # For OR queries in get_filtered_dispatch_methods

# Import your models and forms
from .models import (
    TestRequest, Customer, Project, TVFType, TVFEnvironment, TVFStatus,
    PlasticCodeLookup, DispatchMethod, TestRequestPhaseDefinition,
    TestRequestPlasticCode, TestRequestInputFile, TestRequestPAN,
    TestRequestQuality, TestRequestShipping, TrustportFolder
)
from .forms import (
    TestRequestForm, TestRequestPlasticCodeForm, TestRequestInputFileForm,
    TestRequestPANForm, TestRequestQualityForm, TestRequestShippingForm,
    PlasticCodeFormSet, InputFileFormSet, PanInlineFormSet # Import PanInlineFormSet
)

# For PDF generation
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa

def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    response = HttpResponse(content_type='application/pdf')
    # Use 'attachment' to force download, 'inline' to display in browser
    response['Content-Disposition'] = 'attachment; filename="test_request.pdf"' 
    pisa_status = pisa.CreatePDF(
        html, dest=response)
    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response

class RegisterView(FormView):
    template_name = 'registration/register.html'
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Account created successfully! Please log in.')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'There was an error with your registration. Please check the form.')
        return super().form_invalid(form)

def is_project_manager(user):
    return user.groups.filter(name='Project Managers').exists()

def is_npi_user(user):
    return user.groups.filter(name='NPI Users').exists()

def is_quality_user(user):
    return user.groups.filter(name='Quality Users').exists()

def is_logistics_user(user):
    return user.groups.filter(name='Logistics Users').exists()

def is_coach(user):
    return user.groups.filter(name='Coaches').exists()

def can_view_dashboard(user):
    return is_project_manager(user) or is_npi_user(user) or \
           is_quality_user(user) or is_logistics_user(user) or \
           is_coach(user) or user.is_superuser

# --- AJAX Views for Dynamic Dropdowns ---
from django.http import JsonResponse

@login_required
def get_filtered_projects(request):
    customer_id = request.GET.get('customer_id')
    environment_id = request.GET.get('environment_id')
    projects = []
    if customer_id and environment_id:
        projects = list(Project.objects.filter(
            customer_id=customer_id, tvf_environment_id=environment_id
        ).values('id', 'name').order_by('name'))
    return JsonResponse({'projects': projects})

@login_required
def get_filtered_plastic_codes(request):
    customer_id = request.GET.get('customer_id')
    project_id = request.GET.get('project_id')
    plastic_codes = []
    if customer_id and project_id:
        plastic_codes_query = PlasticCodeLookup.objects.filter(
            customer_id=customer_id, project_id=project_id
        ).values('id', 'code').order_by('code')
        plastic_codes = list(plastic_codes_query)
    return JsonResponse({'plastic_codes': plastic_codes})

@login_required
def get_filtered_trustport_folders(request):
    customer_id = request.GET.get('customer_id')
    project_id = request.GET.get('project_id')
    folders = []
    if customer_id and project_id:
        folders = list(TrustportFolder.objects.filter(
            customer_id=customer_id, project_id=project_id
        ).values('id', 'folder_path').order_by('folder_path'))
    return JsonResponse({'folders': folders})

@login_required
def get_filtered_dispatch_methods(request):
    customer_id = request.GET.get('customer_id')
    project_id = request.GET.get('project_id')
    methods = []
    # Dispatch methods can be global (customer/project is null) or specific
    if customer_id and project_id:
        methods = list(DispatchMethod.objects.filter(
            Q(customer_id=customer_id, project_id=project_id) |
            Q(customer__isnull=True, project__isnull=True) # Allow global methods
        ).values('id', 'name').order_by('name'))
    else: # If no specific customer/project, show only global ones
        methods = list(DispatchMethod.objects.filter(
            customer__isnull=True, project__isnull=True
        ).values('id', 'name').order_by('name'))
    return JsonResponse({'methods': methods})

@login_required
def get_sla_and_calculate_ship_date(request):
    received_date_str = request.GET.get('received_date')
    customer_id = request.GET.get('customer_id')
    ship_date = None

    if received_date_str and customer_id:
        try:
            received_date = timezone.datetime.fromisoformat(received_date_str)
            customer = Customer.objects.get(pk=customer_id)
            sla_days = customer.sla_days

            calculated_ship_date = received_date + timedelta(days=sla_days)
            ship_date = calculated_ship_date.isoformat(timespec='minutes')
        except (ValueError, Customer.DoesNotExist) as e:
            print(f"Error calculating ship date: {e}")
            pass

    return JsonResponse({'ship_date': ship_date})


# --- Coach View: Dashboard of ALL OPEN TVFs ---
@login_required
@user_passes_test(can_view_dashboard, login_url='test_requests:access_denied')
def coach_dashboard(request):
    open_statuses = TVFStatus.objects.exclude(name__in=['Completed', 'Shipped', 'Rejected']).values_list('name', flat=True) # Exclude 'Shipped' too
    open_tvfs = TestRequest.objects.filter(status__name__in=open_statuses).order_by('-request_received_date')
    
    context = {
        'open_tvfs': open_tvfs,
        'role': 'Coach Dashboard',
        'is_project_manager': is_project_manager(request.user),
        'is_npi_user': is_npi_user(request.user),
        'is_quality_user': is_quality_user(request.user),
        'is_logistics_user': is_logistics_user(request.user),
        'is_coach': is_coach(request.user),
    }
    return render(request, 'test_requests/coach_dashboard.html', context)


# --- Project Manager View: Create TVF ---
@login_required
@user_passes_test(is_project_manager, login_url='test_requests:access_denied')
def create_tvf_view(request):
    if request.method == 'POST':
        input_file_form = TestRequestInputFileForm(request.POST, request.FILES)
        plastic_formset = PlasticCodeFormSet(request.POST, prefix='plastic_codes')
        input_file_formset = InputFileFormSet(request.POST, prefix='input_files')
        shipping_form = TestRequestShippingForm(request.POST, prefix='shipping')

        pans_formsets = []
        # Populate pans_formsets based on submitted input_file_formset
        for i, input_file_form in enumerate(input_file_formset.forms):
            # Regardless of validity, if the form is present (not just a placeholder)
            # and not marked for deletion, try to get its nested formset.
            # This is crucial for retaining submitted data for re-rendering on errors.
            if not input_file_form.cleaned_data.get('DELETE', False):
                prefix = f'input_files-{i}-pans'
                # Pass instance=input_file_form.instance if it's an existing object (though for create it's new)
                # For new forms, it will be None.
                pan_formset = PanInlineFormSet(request.POST, instance=input_file_form.instance, prefix=prefix)
                pans_formsets.append(pan_formset)
        
        # Check overall validity of main form and all formsets
        is_valid = form.is_valid() and plastic_formset.is_valid() and input_file_formset.is_valid() and shipping_form.is_valid()
        for pan_fs in pans_formsets:
            is_valid = is_valid and pan_fs.is_valid()

        if is_valid:
            try:
                action = request.POST.get('action') # 'save_draft' or 'submit'
                with transaction.atomic():
                    test_request = form.save(commit=False)
                    test_request.tvf_initiator = request.user
                    test_request.request_received_date = timezone.now() # Set current time as received date

                    if action == 'submit':
                        initial_status, _ = TVFStatus.objects.get_or_create(name='TVF_SUBMITTED')
                        submitted_to_npi_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='NPI Data Processing', order=2) # Ensure order is set
                        test_request.status = initial_status
                        test_request.current_phase = submitted_to_npi_phase
                        messages.success(request, f"TVF {test_request.tvf_number} created and submitted to NPI!")
                    else: # 'save_draft'
                        draft_status, _ = TVFStatus.objects.get_or_create(name='Draft')
                        pm_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='Project Manager', order=1) # Ensure order is set
                        test_request.status = draft_status
                        test_request.current_phase = pm_phase
                        messages.info(request, f"TVF {test_request.tvf_number} saved as draft.")

                    test_request.save()

                    # Save inline formset data (Plastic Codes)
                    plastic_formset.instance = test_request
                    for p_form in plastic_formset.forms:
                        if p_form.instance.pk and p_form.cleaned_data.get('DELETE'): # Existing and marked for deletion
                            p_form.instance.delete()
                            continue
                        if p_form.has_changed() or not p_form.instance.pk: # New or changed form
                            plastic_code_lookup = p_form.cleaned_data.get('plastic_code_lookup')
                            manual_plastic_code = p_form.cleaned_data.get('manual_plastic_code')
                            if plastic_code_lookup:
                                p_form.instance.plastic_code_lookup = plastic_code_lookup
                                p_form.instance.manual_plastic_code = None
                            elif manual_plastic_code:
                                p_form.instance.manual_plastic_code = manual_plastic_code
                                p_form.instance.plastic_code_lookup = None
                            p_form.instance.test_request = test_request
                            p_form.save()
                    # No need for save_m2m for plastic_codes, it's not a M2M relationship here

                    # Save Input Files and nested PANs
                    for i, input_file_form in enumerate(input_file_formset.forms):
                        if input_file_form.instance.pk and input_file_form.cleaned_data.get('DELETE'): # Existing and marked for deletion
                            input_file_form.instance.delete()
                            continue
                        if input_file_form.has_changed() or not input_file_form.instance.pk: # New or changed form
                            input_file = input_file_form.save(commit=False)
                            input_file.test_request = test_request
                            input_file.save() # Save input file first to get its PK

                            # Now save nested PANs (only if corresponding pan_formset exists and is valid)
                            if i < len(pans_formsets): # Ensure the index is valid
                                pan_fs = pans_formsets[i]
                                pan_fs.instance = input_file # Link PAN formset to current input_file
                                for pan_form in pan_fs.forms:
                                    if pan_form.instance.pk and pan_form.cleaned_data.get('DELETE'):
                                        pan_form.instance.delete()
                                        continue
                                    if pan_form.has_changed() or not pan_form.instance.pk:
                                        pan_form.instance.test_request_input_file = input_file
                                        pan_form.save()
                                # No need for pan_fs.save() directly as we iterate and save individual forms
                    # No need for input_file_formset.save_m2m()

                    # Save Shipping details (OneToOne)
                    shipping = shipping_form.save(commit=False)
                    shipping.test_request = test_request
                    shipping.save()

                if action == 'submit':
                    return redirect('test_requests:coach_dashboard')
                else: # 'save_draft'
                    return redirect('test_requests:create_tvf') # Redirect back to the form
            except Exception as e:
                messages.error(request, f"Error creating Test Request: {e}")
                import traceback
                traceback.print_exc()
        else:
            messages.error(request, "Please correct the errors below.")
            # If main form or any formsets are invalid, they will contain errors and be re-rendered.
            # We need to ensure pans_formsets are correctly populated with submitted data and errors
            # for re-rendering.
            re_pans_formsets = []
            for i, input_file_form in enumerate(input_file_formset.forms):
                prefix = f'input_files-{i}-pans'
                # If input_file_form is an existing instance, pass it. Otherwise, None.
                instance = input_file_form.instance if input_file_form.instance.pk else None
                # Pass request.POST data for validation on re-render
                pan_fs = PanInlineFormSet(request.POST, instance=instance, prefix=prefix)
                re_pans_formsets.append(pan_fs)
            pans_formsets = re_pans_formsets # Update pans_formsets with the re-populated ones

    else: # GET request
        form = TestRequestForm(initial={'tvf_initiator': request.user, 'request_received_date': timezone.now().strftime('%Y-%m-%dT%H:%M')})
        plastic_formset = PlasticCodeFormSet(prefix='plastic_codes')
        input_file_formset = InputFileFormSet(prefix='input_files')
        shipping_form = TestRequestShippingForm(prefix='shipping')
        
        # Initialize empty nested PAN formsets for each input file form (for GET)
        pans_formsets = []
        for i in range(input_file_formset.total_form_count()):
            prefix = f'input_files-{i}-pans'
            pans_formsets.append(PanInlineFormSet(prefix=prefix))

    context = {
        'form': form,
        'plastic_formset': plastic_formset,
        'input_file_formset': input_file_formset,
        'pans_formsets': pans_formsets, # Pass the list of PAN formsets
        'shipping_form': shipping_form,
        'role': 'Project Manager - Create TVF'
    }
    return render(request, 'test_requests/pm_create_tvf.html', context)


# --- NPI View: Update Data Processing Status ---
@login_required
@user_passes_test(is_npi_user, login_url='test_requests:access_denied')
def npi_update_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    if not (tvf.status.name in ['TVF_SUBMITTED', 'Rejected to NPI'] or tvf.current_phase.name == 'NPI Data Processing'):
        messages.warning(request, f"TVF {tvf.tvf_number} is not in your NPI queue for editing.")
        return redirect('test_requests:coach_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', tvf.comments)

        if action == 'process':
            tvf.status, _ = TVFStatus.objects.get_or_create(name='TVF Data Processed')
            tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='Quality Validation', order=3) # Add order
            tvf.comments = comments
            tvf.is_rejected = False
            tvf.save()
            messages.success(request, f"TVF {tvf.tvf_number} processed by NPI and moved to Quality queue!")
            return redirect('test_requests:coach_dashboard')
        
        elif action == 'reject':
            return redirect('test_requests:reject_tvf', tvf_id=tvf.pk)
        
    return render(request, 'test_requests/npi_update_tvf.html', {'tvf': tvf, 'role': 'NPI User'})


# --- Quality View: Update Validation Status ---
@login_required
@user_passes_test(is_quality_user, login_url='test_requests:access_denied')
def quality_update_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    if not (tvf.status.name in ['TVF Data Processed', 'Rejected to Quality'] or tvf.current_phase.name == 'Quality Validation'):
        messages.warning(request, f"TVF {tvf.tvf_number} is not in your Quality queue for editing.")
        return redirect('test_requests:coach_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', tvf.comments)

        if action == 'process':
            tvf.status, _ = TVFStatus.objects.get_or_create(name='Validation Done')
            tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='Logistics Dispatch', order=4) # Add order
            tvf.comments = comments
            tvf.is_rejected = False
            tvf.save()
            messages.success(request, f"TVF {tvf.tvf_number} validated by Quality and moved to Logistics queue!")
            return redirect('test_requests:coach_dashboard')
        
        elif action == 'reject':
            return redirect('test_requests:reject_tvf', tvf_id=tvf.pk)

    return render(request, 'test_requests/quality_update_tvf.html', {'tvf': tvf, 'role': 'Quality User'})

# --- Logistics View: Update Shipping Status ---
@login_required
@user_passes_test(is_logistics_user, login_url='test_requests:access_denied')
def logistics_update_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    if not (tvf.status.name in ['Validation Done', 'Rejected to Logistics'] or tvf.current_phase.name == 'Logistics Dispatch'):
        messages.warning(request, f"TVF {tvf.tvf_number} is not in your Logistics queue for editing.")
        return redirect('test_requests:coach_dashboard')

    shipping_instance, created = TestRequestShipping.objects.get_or_create(test_request=tvf)

    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', tvf.comments)
        shipping_form = TestRequestShippingForm(request.POST, instance=shipping_instance, prefix='shipping')

        if action == 'process':
            if shipping_form.is_valid():
                shipping = shipping_form.save(commit=False)
                shipping.date_shipped = timezone.now()
                shipping.save()

                tvf.status, _ = TVFStatus.objects.get_or_create(name='Shipped')
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_SHIPPED', order=5) # Add order
                tvf.comments = comments
                tvf.is_rejected = False
                tvf.tvf_completed_date = timezone.now()
                tvf.save()
                messages.success(request, f"TVF {tvf.tvf_number} shipped by Logistics!")
                return redirect('test_requests:coach_dashboard')
            else:
                messages.error(request, "Please correct the errors in the shipping details.")
        
        elif action == 'reject':
            return redirect('test_requests:reject_tvf', tvf_id=tvf.pk)

    else: # GET request
        shipping_form = TestRequestShippingForm(instance=shipping_instance, prefix='shipping')

    return render(request, 'test_requests/logistics_update_tvf.html', {
        'tvf': tvf,
        'shipping_form': shipping_form,
        'role': 'Logistics User'
    })

# --- Common Rejection View ---
@login_required
def reject_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    if not (is_project_manager(request.user) or is_npi_user(request.user) or \
            is_quality_user(request.user) or is_logistics_user(request.user) or \
            is_coach(request.user) or request.user.is_superuser):
        messages.error(request, "You do not have permission to reject TVFs.")
        return redirect('test_requests:coach_dashboard')

    if tvf.status.name in ['Shipped', 'Completed']:
        messages.error(request, f"TVF {tvf.tvf_number} cannot be rejected as it is already {tvf.status.name}.")
        return redirect('test_requests:coach_dashboard')

    if request.method == 'POST':
        target_phase_name = request.POST.get('target_phase')
        rejection_comments = request.POST.get('comments')
        reject_reason_id = request.POST.get('reject_reason')

        if not target_phase_name or not rejection_comments:
            messages.error(request, "Please select a target phase and provide rejection comments.")
            available_phases = TestRequestPhaseDefinition.objects.all().order_by('order')
            reject_reasons = RejectReason.objects.all().order_by('reason')
            return render(request, 'test_requests/reject_tvf.html', {
                'tvf': tvf,
                'available_phases': available_phases,
                'reject_reasons': reject_reasons,
                'role': 'Reject TVF'
            })

        try:
            status_map = {
                'Project Manager': 'Rejected to PM',
                'NPI Data Processing': 'Rejected to NPI',
                'Quality Validation': 'Rejected to Quality',
                'Logistics Dispatch': 'Rejected to Logistics',
            }
            new_status_name = status_map.get(target_phase_name, 'Rejected')

            target_status, _ = TVFStatus.objects.get_or_create(name=new_status_name)
            target_phase = TestRequestPhaseDefinition.objects.get(name=target_phase_name)
            reject_reason_obj = RejectReason.objects.get(pk=reject_reason_id) if reject_reason_id else None
            
            tvf.status = target_status
            tvf.current_phase = target_phase
            tvf.comments = f"REJECTED by {request.user.username} to {target_phase_name}: {rejection_comments}"
            
            tvf.is_rejected = True
            tvf.rejected_by = request.user
            tvf.rejected_reason = reject_reason_obj
            tvf.rejected_comments = rejection_comments
            tvf.rejected_date = timezone.now()
            
            tvf.save()
            messages.success(request, f"TVF {tvf.tvf_number} rejected to {target_phase_name} successfully!")
            return redirect('test_requests:coach_dashboard')
        
        except TestRequestPhaseDefinition.DoesNotExist:
            messages.error(request, "Invalid target phase selected for rejection.")
        except RejectReason.DoesNotExist:
            messages.error(request, "Invalid rejection reason selected.")
        except Exception as e:
            messages.error(request, f"An unexpected error occurred during rejection: {e}")

    available_phases = TestRequestPhaseDefinition.objects.all().order_by('order')
    reject_reasons = RejectReason.objects.all().order_by('reason')

    return render(request, 'test_requests/reject_tvf.html', {
        'tvf': tvf,
        'available_phases': available_phases,
        'reject_reasons': reject_reasons,
        'role': 'Reject TVF'
    })


# --- Access Denied Page ---
def access_denied_view(request):
    return render(request, 'test_requests/access_denied.html')

# --- Existing Test Request Views (No major changes needed based on requirements) ---
@login_required
def test_request_create_view(request):
    messages.info(request, "Please use the 'Create New TVF' link from the dashboard.")
    return redirect('test_requests:create_tvf') # Redirect to the main PM create view


@login_required
def test_request_list_view(request):
    test_requests = TestRequest.objects.all().select_related('customer', 'project', 'tvf_initiator', 'status').order_by('-tvf_number')
    context = {
        'test_requests': test_requests
    }
    return render(request, 'test_requests/test_request_list.html', context)

@login_required
def test_request_detail_view(request, pk):
    test_request = get_object_or_404(TestRequest.objects.select_related(
        'customer', 'project', 'tvf_initiator', 'tvf_type', 'tvf_environment', 'status', 'current_phase', 'trustport_folder_actual'
    ).prefetch_related(
        'plastic_codes_entries__plastic_code_lookup',
        'input_files_entries__pans',
        'quality_details',
        'shipping_details__dispatch_method'
    ), pk=pk)

    context = {
        'test_request': test_request
    }
    return render(request, 'test_requests/test_request_detail.html', context)

@login_required
def test_request_update_view(request, pk):
    test_request = get_object_or_404(TestRequest, pk=pk)

    quality_instance, created_quality = TestRequestQuality.objects.get_or_create(test_request=test_request)
    shipping_instance, created_shipping = TestRequestShipping.objects.get_or_create(test_request=test_request)

    if request.method == 'POST':
        form = TestRequestForm(request.POST, instance=test_request)
        plastic_formset = PlasticCodeFormSet(request.POST, instance=test_request, prefix='plastic_codes')
        input_file_formset = InputFileFormSet(request.POST, instance=test_request, prefix='input_files')
        shipping_form = TestRequestShippingForm(request.POST, instance=shipping_instance, prefix='shipping')
        quality_form = TestRequestQualityForm(request.POST, instance=quality_instance, prefix='quality')


        pans_formsets = []
        for i, input_file_form in enumerate(input_file_formset.forms):
            if not input_file_form.cleaned_data.get('DELETE', False):
                prefix = f'input_files-{i}-pans'
                pan_formset = PanInlineFormSet(request.POST, instance=input_file_form.instance, prefix=prefix)
                pans_formsets.append(pan_formset)

        is_valid = form.is_valid() and plastic_formset.is_valid() and input_file_formset.is_valid() \
                   and shipping_form.is_valid() and quality_form.is_valid()
        for pan_fs in pans_formsets:
            is_valid = is_valid and pan_fs.is_valid()

        if is_valid:
            try:
                with transaction.atomic():
                    test_request_saved = form.save()

                    # Save plastic codes (with manual/lookup logic)
                    for p_form in plastic_formset.forms:
                        if p_form.instance.pk: 
                            if p_form.cleaned_data.get('DELETE'): 
                                p_form.instance.delete()
                                continue
                        if p_form.has_changed():
                            plastic_code_lookup = p_form.cleaned_data.get('plastic_code_lookup')
                            manual_plastic_code = p_form.cleaned_data.get('manual_plastic_code')
                            if plastic_code_lookup:
                                p_form.instance.plastic_code_lookup = plastic_code_lookup
                                p_form.instance.manual_plastic_code = None
                            elif manual_plastic_code:
                                p_form.instance.manual_plastic_code = manual_plastic_code
                                p_form.instance.plastic_code_lookup = None
                            p_form.instance.test_request = test_request_saved
                            p_form.save()

                    # Save input files and nested PANs
                    saved_input_files = input_file_formset.save(commit=False)
                    for i, input_file in enumerate(saved_input_files):
                        input_file.test_request = test_request_saved
                        input_file.save()
                        if pans_formsets[i].is_valid():
                            pan_fs = pans_formsets[i]
                            pan_fs.instance = input_file
                            for pan_form in pan_fs.forms:
                                if pan_form.instance.pk and pan_form.cleaned_data.get('DELETE'):
                                    pan_form.instance.delete()
                                    continue
                                if pan_form.has_changed():
                                    pan_form.instance.test_request_input_file = input_file
                                    pan_form.save()

                    shipping_form.save()
                    quality_form.save()

                messages.success(request, f"Test Request {test_request.tvf_number} updated successfully!")
                return redirect('test_requests:detail', pk=test_request.pk)
            except Exception as e:
                messages.error(request, f"Error updating Test Request: {e}")
                import traceback
                traceback.print_exc()
        else:
            messages.error(request, "Please correct the errors below.")
            pans_formsets = []
            for i, input_file_form in enumerate(input_file_formset.forms):
                prefix = f'input_files-{i}-pans'
                instance = input_file_form.instance if input_file_form.instance.pk else None
                pan_formset = PanInlineFormSet(request.POST, instance=instance, prefix=prefix)
                pans_formsets.append(pan_formset)

    else:
        form = TestRequestForm(instance=test_request)
        plastic_formset = PlasticCodeFormSet(instance=test_request, prefix='plastic_codes')
        input_file_formset = InputFileFormSet(instance=test_request, prefix='input_files')
        shipping_form = TestRequestShippingForm(instance=shipping_instance, prefix='shipping')
        quality_form = TestRequestQualityForm(instance=quality_instance, prefix='quality')

        pans_formsets = []
        for i, input_file_form in enumerate(input_file_formset):
            if input_file_form.instance.pk:
                prefix = f'input_files-{i}-pans'
                pans_formsets.append(PanInlineFormSet(instance=input_file_form.instance, prefix=prefix))
            else:
                prefix = f'input_files-{i}-pans'
                pans_formsets.append(PanInlineFormSet(prefix=prefix))


    context = {
        'form': form,
        'plastic_formset': plastic_formset,
        'input_file_formset': input_file_formset,
        'pans_formsets': pans_formsets,
        'quality_form': quality_form,
        'shipping_form': shipping_form,
        'test_request': test_request,
    }
    return render(request, 'test_requests/test_request_form.html', context)


@login_required
def test_request_pdf_view(request, pk):
    test_request = get_object_or_404(TestRequest.objects.select_related(
        'customer', 'project', 'tvf_initiator', 'tvf_type', 'tvf_environment', 'status', 'current_phase', 'trustport_folder_actual'
    ).prefetch_related(
        'plastic_codes_entries__plastic_code_lookup',
        'input_files_entries__pans',
        'quality_details__quality_sign_off_by',
        'shipping_details__dispatch_method',
        'shipping_details__shipping_sign_off_by'
    ), pk=pk)

    context = {
        'test_request': test_request,
        'current_date': timezone.now(),
    }
    return render_to_pdf('test_requests/test_request_pdf_template.html', context)