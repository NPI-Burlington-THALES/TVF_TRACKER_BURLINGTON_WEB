# tvf_app/test_requests/views.py
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
from django.contrib import messages
from .forms import CustomUserCreationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib.auth.decorators import login_required, user_passes_test
from datetime import timedelta
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q

from .models import (
    TestRequest, Customer, Project, TVFType, TVFEnvironment, TVFStatus,
    PlasticCodeLookup, DispatchMethod, TestRequestPhaseDefinition,
    TestRequestPlasticCode, TestRequestInputFile, TestRequestPAN,
    TestRequestQuality, TestRequestShipping, TrustportFolder, RejectReason
)
from .forms import (
    TestRequestForm,
    PlasticCodeFormSet, InputFileFormSet, PanInlineFormSet,
    TestRequestShippingForm, TestRequestQualityForm # TestRequestQualityForm for other views if needed
)

# PDF Generation and User Group Checks (assumed to be correct from previous versions)
# ... (render_to_pdf, RegisterView, is_project_manager, etc. ... )
def is_project_manager(user): return user.groups.filter(name='Project Managers').exists()
def is_npi_user(user): return user.groups.filter(name='NPI Users').exists()
def is_quality_user(user): return user.groups.filter(name='Quality Users').exists()
def is_logistics_user(user): return user.groups.filter(name='Logistics Users').exists()
def is_coach(user): return user.groups.filter(name='Coaches').exists()
def can_view_dashboard(user):
    return is_project_manager(user) or is_npi_user(user) or \
           is_quality_user(user) or is_logistics_user(user) or \
           is_coach(user) or user.is_superuser


# --- AJAX Views for Dynamic Dropdowns ---
@login_required
def get_filtered_projects(request):
    customer_id = request.GET.get('customer_id')
    environment_id = request.GET.get('environment_id')
    projects = []
    if customer_id and environment_id:
        try:
            projects = list(Project.objects.filter(
                customer_id=int(customer_id),
                tvf_environment_id=int(environment_id)
            ).values('id', 'name').order_by('name'))
        except ValueError: # Handle cases where IDs are not valid integers
            pass
    return JsonResponse({'projects': projects})

@login_required
def get_filtered_plastic_codes(request):
    customer_id = request.GET.get('customer_id')
    project_id = request.GET.get('project_id')
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
    environment_id = request.GET.get('environment_id')
    plastic_codes = []
    if customer_id and project_id and environment_id:
        try:
            plastic_codes = list(PlasticCodeLookup.objects.filter(
                customer_id=int(customer_id),
                project_id=int(project_id),
                tvf_environment_id=int(environment_id)
            ).values('id', 'code').order_by('code'))
        except ValueError:
            pass
=======
    plastic_codes = []
=======
    plastic_codes = []
>>>>>>> parent of 63fccc0 (sdsd)
=======
    plastic_codes = []
>>>>>>> parent of 63fccc0 (sdsd)
    if customer_id and project_id:
        plastic_codes_query = PlasticCodeLookup.objects.filter(
            customer_id=customer_id, project_id=project_id
        ).values('id', 'code').order_by('code')
        plastic_codes = list(plastic_codes_query)
>>>>>>> parent of 63fccc0 (sdsd)
    return JsonResponse({'plastic_codes': plastic_codes})

@login_required
def get_filtered_trustport_folders(request):
    customer_id = request.GET.get('customer_id')
    project_id = request.GET.get('project_id')
    folders = []
    if customer_id and project_id:
        try:
            folders = list(TrustportFolder.objects.filter(
                customer_id=int(customer_id),
                project_id=int(project_id)
            ).values('id', 'folder_path').order_by('folder_path'))
        except ValueError:
            pass
    return JsonResponse({'folders': folders})

@login_required
def get_filtered_dispatch_methods(request):
    customer_id = request.GET.get('customer_id')
    project_id = request.GET.get('project_id')
    methods = []
    try:
        cid = int(customer_id) if customer_id else None
        pid = int(project_id) if project_id else None

        if cid and pid:
            methods = list(DispatchMethod.objects.filter(
                Q(customer_id=cid, project_id=pid) |
                Q(customer__isnull=True, project__isnull=True)
            ).values('id', 'name').order_by('name').distinct())
        else: # Fallback to global if specific customer/project not provided
            methods = list(DispatchMethod.objects.filter(
                customer__isnull=True, project__isnull=True
            ).values('id', 'name').order_by('name').distinct())
    except ValueError:
        pass # Or return error
    return JsonResponse({'methods': methods})


@login_required
def get_sla_and_calculate_ship_date(request):
    received_date_str = request.GET.get('received_date')
    customer_id = request.GET.get('customer_id')
    ship_date_iso = None
    if received_date_str and customer_id:
        try:
            received_date = timezone.datetime.fromisoformat(received_date_str.replace(' ', 'T'))
            customer = Customer.objects.get(pk=int(customer_id))
            sla_days = customer.sla_days
            if sla_days is not None:
                calculated_ship_date = received_date + timedelta(days=sla_days)
                ship_date_iso = calculated_ship_date.strftime('%Y-%m-%dT%H:%M')
        except (ValueError, Customer.DoesNotExist):
            pass # Silently fail or log error
    return JsonResponse({'ship_date': ship_date_iso})


# Helper function to save manual plastic codes to PlasticCodeLookup
def get_or_create_plastic_code_lookup(customer, project, environment, code_value):
    if not code_value:
        return None
    # Ensure all parent objects are valid before creating/getting lookup
    if not all([customer, project, environment]):
        # Log this error or handle appropriately
        print(f"Warning: Missing customer, project, or environment when trying to create lookup for code: {code_value}")
        return None
    
    lookup, created = PlasticCodeLookup.objects.get_or_create(
        customer=customer,
        project=project,
        tvf_environment=environment,
        code=code_value.strip() # Ensure no leading/trailing whitespace
        # 'description' can be added to defaults if needed: defaults={'description': 'Manually entered'}
    )
    if created:
        print(f"Created new PlasticCodeLookup: {lookup.code} for C:{customer.id}/P:{project.id}/E:{environment.id}")
    return lookup


@login_required
@user_passes_test(is_project_manager, login_url='test_requests:access_denied')
def create_tvf_view(request):
    form_kwargs_for_dependents = {}

    if request.method == 'POST':
        form = TestRequestForm(request.POST)

        if form.is_valid():
            # If main form is valid, extract customer, project, environment for dependent formsets
            valid_customer = form.cleaned_data['customer']
            valid_project = form.cleaned_data['project']
            valid_environment = form.cleaned_data['tvf_environment']
            form_kwargs_for_dependents = {
                'parent_customer': valid_customer,
                'parent_project': valid_project,
                'parent_environment': valid_environment
            }
        # Initialize formsets with POST data and potentially parent context for validation
        plastic_formset = PlasticCodeFormSet(request.POST, prefix='plastic_codes', form_kwargs=form_kwargs_for_dependents)
        input_file_formset = InputFileFormSet(request.POST, prefix='input_files') # No direct parent_kwargs needed for its own fields
        shipping_form = TestRequestShippingForm(request.POST, prefix='shipping', **form_kwargs_for_dependents)


        # Prepare PanInlineFormSets
        processed_pans_formsets = []
        all_pan_formsets_valid = True # Assume true initially

        # Iterate based on the number of input file forms submitted
        for i in range(input_file_formset.total_form_count()):
            pan_prefix = f'{input_file_formset.prefix}-{i}-pans'
            # For PAN formset, pass parent context if available (from main form)
            # The instance for PanInlineFormSet will be set later if input_file_form is valid and saved
            pan_fs = PanInlineFormSet(request.POST, prefix=pan_prefix, form_kwargs=form_kwargs_for_dependents)
            processed_pans_formsets.append(pan_fs)
            # Defer PAN formset validation until after its parent input_file_form is validated


        # Overall validation check
        is_valid_main_form = form.is_valid() # Already checked, but good for clarity
        is_valid_plastic = plastic_formset.is_valid()
        is_valid_input_files = input_file_formset.is_valid()
        is_valid_shipping = shipping_form.is_valid()

        # Now validate PAN formsets, only if their parent input_file_form was valid
        if is_valid_input_files:
            for i, iff_form in enumerate(input_file_formset.forms):
                if i < len(processed_pans_formsets): # Ensure index exists
                    pan_fs_to_validate = processed_pans_formsets[i]
                    if not iff_form.cleaned_data.get('DELETE', False): # Don't validate PANs for deleted input file
                        if not pan_fs_to_validate.is_valid():
                            all_pan_formsets_valid = False
                    # If iff_form is to be deleted, its PANs don't need to be "valid" for submission
                    # but they should not block if they contain errors but parent is deleted.
                    # For simplicity, if input_file_formset is valid, we proceed to check PANs unless parent is deleted.
        else: # If input_file_formset itself is invalid, then PANs cannot be meaningfully validated in context
            all_pan_formsets_valid = False


        if is_valid_main_form and is_valid_plastic and is_valid_input_files and is_valid_shipping and all_pan_formsets_valid:
            try:
                with transaction.atomic():
                    test_request = form.save(commit=False)
                    test_request.tvf_initiator = request.user
                    
                    action = request.POST.get('action')
                    if action == 'submit':
                        status_name, phase_name, phase_order = 'TVF_SUBMITTED', 'NPI Data Processing', 2
                    else: # 'save_draft'
                        status_name, phase_name, phase_order = 'Draft', 'Project Manager', 1
                    
                    test_request.status, _ = TVFStatus.objects.get_or_create(name=status_name)
                    test_request.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(
                        name=phase_name, defaults={'order': phase_order}
                    )
                    test_request.save() # Save main TestRequest

                    # Save Plastic Codes
                    plastic_formset.instance = test_request
                    saved_plastic_codes = plastic_formset.save(commit=False)
                    for pc_instance in saved_plastic_codes:
                        if pc_instance.manual_plastic_code and not pc_instance.plastic_code_lookup:
                            lookup = get_or_create_plastic_code_lookup(
                                test_request.customer, test_request.project,
                                test_request.tvf_environment, pc_instance.manual_plastic_code
                            )
                            if lookup:
                                pc_instance.plastic_code_lookup = lookup
                                pc_instance.manual_plastic_code = None
                        pc_instance.save()
                    plastic_formset.save_m2m()

                    # Save Input Files and their nested PANs
                    for i, iff_form in enumerate(input_file_formset.forms):
                        if iff_form.cleaned_data.get('DELETE'):
                            if iff_form.instance.pk: iff_form.instance.delete()
                            continue
                        
                        # Only save if form has data or is an initial form that's not empty and not deleted
                        if iff_form.has_changed() or (not iff_form.instance.pk and any(val for name, val in iff_form.cleaned_data.items() if name != 'DELETE')):
                            input_file_instance = iff_form.save(commit=False)
                            input_file_instance.test_request = test_request
                            input_file_instance.save()

                            if i < len(processed_pans_formsets):
                                pan_fs_to_save = processed_pans_formsets[i]
                                pan_fs_to_save.instance = input_file_instance
                                saved_pans = pan_fs_to_save.save(commit=False)
                                for pan_instance in saved_pans:
                                    if pan_instance.manual_plastic_code_for_pan and not pan_instance.plastic_code_lookup:
                                        pan_lookup = get_or_create_plastic_code_lookup(
                                            test_request.customer, test_request.project,
                                            test_request.tvf_environment, pan_instance.manual_plastic_code_for_pan
                                        )
                                        if pan_lookup:
                                            pan_instance.plastic_code_lookup = pan_lookup
                                            pan_instance.manual_plastic_code_for_pan = None
                                    # pan_instance.test_request_input_file is set by formset
                                    pan_instance.save()
                                pan_fs_to_save.save_m2m()
                    
                    # Save Shipping Details
                    shipping_instance = shipping_form.save(commit=False)
                    shipping_instance.test_request = test_request
                    shipping_instance.save()

                messages.success(request, f"TVF {test_request.tvf_number} ({status_name}) processed successfully!")
                return redirect('test_requests:detail', pk=test_request.pk)

            except Exception as e:
                messages.error(request, f"Error processing Test Request: {e}")
                import traceback
                traceback.print_exc()
        else:
            error_messages = ["Please correct the errors below."]
            if not is_valid_main_form: error_messages.append("Main form has errors.")
            if not is_valid_plastic: error_messages.append("Plastic Codes section has errors.")
            if not is_valid_input_files: error_messages.append("Input Files section has errors.")
            if not is_valid_shipping: error_messages.append("Shipping Details section has errors.")
            if not all_pan_formsets_valid: error_messages.append("PANs section has errors.")
            messages.error(request, " ".join(error_messages))
            # Fall through to render, processed_pans_formsets will be used

    else: # GET request
        form = TestRequestForm(initial={'tvf_initiator': request.user, 'request_received_date': timezone.now().strftime('%Y-%m-%dT%H:%M')})
        plastic_formset = PlasticCodeFormSet(prefix='plastic_codes', form_kwargs=form_kwargs_for_dependents)
        input_file_formset = InputFileFormSet(prefix='input_files')
        shipping_form = TestRequestShippingForm(prefix='shipping', **form_kwargs_for_dependents)
        
        processed_pans_formsets = []
        for i in range(input_file_formset.initial_form_count() + input_file_formset.extra):
            pan_prefix = f'{input_file_formset.prefix}-{i}-pans'
            processed_pans_formsets.append(PanInlineFormSet(prefix=pan_prefix, form_kwargs=form_kwargs_for_dependents))

    context = {
        'form': form,
        'plastic_formset': plastic_formset,
        'input_file_formset': input_file_formset,
        'pans_formsets': processed_pans_formsets, # This is a list of PanInlineFormSet instances
        'shipping_form': shipping_form,
        'role': 'Project Manager - Create TVF' # Assuming 'role' is for display
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