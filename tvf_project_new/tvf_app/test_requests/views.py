# tvf_app/test_requests/views.py
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib.auth.decorators import login_required, user_passes_test
from datetime import timedelta
from django.utils import timezone
from django import forms  # <--- ADD THIS LINE to import the forms module
from django.forms import formset_factory # Not directly used for inlineformset_factory, but good to have if needed for standalone formsets.
from django.db.models import Q # For OR queries in get_filtered_dispatch_methods

# Import your models and forms
from .models import (
    TestRequest, Customer, Project, TVFType, TVFEnvironment, TVFStatus,
    PlasticCodeLookup, DispatchMethod, TestRequestPhaseDefinition,
    TestRequestPlasticCode, TestRequestInputFile, TestRequestPAN,
    TestRequestQuality, TestRequestShipping, TrustportFolder, RejectReason
)
from .forms import ( # This block imports all necessary forms
    CustomUserCreationForm,
    TestRequestForm,
    TestRequestPlasticCodeForm,
    TestRequestInputFileForm,
    TestRequestPANForm,
    TestRequestQualityForm,
    TestRequestShippingForm,
    PlasticCodeFormSet,
    InputFileFormSet,
    PanInlineFormSet
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
    environment_id = request.GET.get('environment_id')
    plastic_codes = []
    if customer_id and project_id and environment_id:
        plastic_codes_query = PlasticCodeLookup.objects.filter(
            customer_id=customer_id,
            project_id=project_id,
            tvf_environment_id=environment_id
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
    if customer_id and project_id:
        methods = list(DispatchMethod.objects.filter(
            Q(customer_id=customer_id, project_id=project_id) |
            Q(customer__isnull=True, project__isnull=True)
        ).values('id', 'name').order_by('name'))
    else:
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


# --- Coach View: Dashboard for all roles ---
@login_required
@user_passes_test(can_view_dashboard, login_url='test_requests:access_denied')
def coach_dashboard(request):
    open_statuses = TVFStatus.objects.exclude(name__in=['Completed', 'Shipped', 'Rejected']).values_list('name', flat=True)
    
    # Define common phase names for filtering
    pm_phase_name = 'Project Manager' # Used for TVFs rejected back to PM
    pm_draft_phase_name = 'PM_DRAFT' # New phase for initial drafts
    tvf_released_phase_name = 'TVF_RELEASED'
    tvf_dp_done_phase_name = 'TVF_DP_DONE'
    tvf_processed_at_npi_phase_name = 'TVF_PROCESSED_AT_NPI'
    tvf_open_at_qa_phase_name = 'TVF_OPEN_AT_QA'
    tvf_validated_at_qa_phase_name = 'TVF_VALIDATED_AT_QA'
    tvf_open_at_logistics_phase_name = 'TVF_OPEN_AT_LOGISTICS'
    
    # Initialize all TVF lists as empty
    pm_draft_tvfs = TestRequest.objects.none()
    pm_submitted_tvfs = TestRequest.objects.none()
    npi_released_tvfs = TestRequest.objects.none()
    npi_dp_done_tvfs = TestRequest.objects.none()
    npi_processed_tvfs = TestRequest.objects.none()
    quality_open_tvfs = TestRequest.objects.none()
    quality_validated_tvfs = TestRequest.objects.none()
    logistics_open_tvfs = TestRequest.objects.none()
    other_open_tvfs = TestRequest.objects.none()
    all_open_tvfs_for_coach = TestRequest.objects.none()

    # Role-based filtering of TVFs
    if is_project_manager(request.user):
        # PMs see their own drafts and submitted TVFs based on current phase AND status
        user_tvfs = TestRequest.objects.filter(tvf_initiator=request.user)
        pm_draft_tvfs = user_tvfs.filter(status__name='Draft', current_phase__name=pm_draft_phase_name)
        pm_submitted_tvfs = user_tvfs.filter(status__name='TVF_SUBMITTED', current_phase__name=tvf_released_phase_name)
        
    elif is_npi_user(request.user):
        # NPI users see TVFs in their specific NPI phases
        npi_released_tvfs = TestRequest.objects.filter(current_phase__name=tvf_released_phase_name)
        npi_dp_done_tvfs = TestRequest.objects.filter(current_phase__name=tvf_dp_done_phase_name)
        npi_processed_tvfs = TestRequest.objects.filter(current_phase__name=tvf_processed_at_npi_phase_name)
        
    elif is_quality_user(request.user):
        # Quality users see TVFs in their specific Quality phases
        quality_open_tvfs = TestRequest.objects.filter(current_phase__name=tvf_open_at_qa_phase_name)
        quality_validated_tvfs = TestRequest.objects.filter(current_phase__name=tvf_validated_at_qa_phase_name)
        
    elif is_logistics_user(request.user):
        # Logistics users see TVFs in their specific Logistics phase
        logistics_open_tvfs = TestRequest.objects.filter(current_phase__name=tvf_open_at_logistics_phase_name)
        
    elif is_coach(request.user) or request.user.is_superuser:
        # Coaches/Superusers see all open TVFs and all categorized sections
        all_open_tvfs_for_coach = TestRequest.objects.filter(status__name__in=open_statuses).order_by('-request_received_date')

        npi_released_tvfs = all_open_tvfs_for_coach.filter(current_phase__name=tvf_released_phase_name)
        npi_dp_done_tvfs = all_open_tvfs_for_coach.filter(current_phase__name=tvf_dp_done_phase_name)
        npi_processed_tvfs = all_open_tvfs_for_coach.filter(current_phase__name=tvf_processed_at_npi_phase_name)

        quality_open_tvfs = all_open_tvfs_for_coach.filter(current_phase__name=tvf_open_at_qa_phase_name)
        quality_validated_tvfs = all_open_tvfs_for_coach.filter(current_phase__name=tvf_validated_at_qa_phase_name)

        logistics_open_tvfs = all_open_tvfs_for_coach.filter(current_phase__name=tvf_open_at_logistics_phase_name)

        # Calculate other_open_tvfs only for Coach/Superuser
        categorized_tvf_ids = list(npi_released_tvfs.values_list('id', flat=True)) + \
                              list(npi_dp_done_tvfs.values_list('id', flat=True)) + \
                              list(npi_processed_tvfs.values_list('id', flat=True)) + \
                              list(quality_open_tvfs.values_list('id', flat=True)) + \
                              list(quality_validated_tvfs.values_list('id', flat=True)) + \
                              list(logistics_open_tvfs.values_list('id', flat=True))
        other_open_tvfs = all_open_tvfs_for_coach.exclude(id__in=categorized_tvf_ids)


    # Phase lists for general update button conditions (if used in 'other_open_tvfs' table)
    npi_phases_for_button = [tvf_released_phase_name, tvf_dp_done_phase_name, tvf_processed_at_npi_phase_name]
    quality_phases_for_button = [tvf_open_at_qa_phase_name, tvf_validated_at_qa_phase_name]
    logistics_phases_for_button = [tvf_open_at_logistics_phase_name]

    context = {
        'role': 'Coach Dashboard',
        'is_project_manager': is_project_manager(request.user),
        'is_npi_user': is_npi_user(request.user),
        'is_quality_user': is_quality_user(request.user),
        'is_logistics_user': is_logistics_user(request.user),
        'is_coach': is_coach(request.user),
        'is_superuser': request.user.is_superuser,

        # PM specific lists
        'pm_draft_tvfs': pm_draft_tvfs,
        'pm_submitted_tvfs': pm_submitted_tvfs,
        
        # NPI specific lists (always passed, but conditionally displayed in HTML)
        'npi_released_tvfs': npi_released_tvfs,
        'npi_dp_done_tvfs': npi_dp_done_tvfs,
        'npi_processed_tvfs': npi_processed_tvfs,
        
        # Quality specific lists (always passed, but conditionally displayed in HTML)
        'quality_open_tvfs': quality_open_tvfs,
        'quality_validated_tvfs': quality_validated_tvfs,

        # Logistics specific lists (always passed, but conditionally displayed in HTML)
        'logistics_open_tvfs': logistics_open_tvfs,

        # Other open TVFs (only calculated for Coach/Superuser, otherwise empty)
        'other_open_tvfs': other_open_tvfs,

        # All open TVFs (only for Coach/Superuser for general table)
        'all_open_tvfs_for_coach': all_open_tvfs_for_coach,

        # Phase lists for button conditions (used in general table for coach)
        'npi_phases_for_button': npi_phases_for_button,       
        'quality_phases_for_button': quality_phases_for_button, 
        'logistics_phases_for_button': logistics_phases_for_button, 
    }
    return render(request, 'test_requests/coach_dashboard.html', context)


# --- Project Manager View: Create TVF ---
@login_required
@user_passes_test(is_project_manager, login_url='test_requests:access_denied')
def create_tvf_view(request):
    if request.method == 'POST':
        form = TestRequestForm(request.POST)
        customer_id = None
        project_id = None
        if form.is_valid():
            customer_obj = form.cleaned_data.get('customer')
            project_obj = form.cleaned_data.get('project')
            customer_id = customer_obj.id if customer_obj else None
            project_id = project_obj.id if project_obj else None
        else:
            try:
                customer_id = int(request.POST.get('customer'))
                project_id = int(request.POST.get('project'))
            except (TypeError, ValueError):
                pass

        # Pass customer_id and project_id to the PlasticCodeFormSet
        plastic_formset = PlasticCodeFormSet(request.POST, prefix='plastic_codes',
                                             form_kwargs={'customer_id': customer_id, 'project_id': project_id})

        # Initialize InputFileFormSet with POST data
        input_file_formset = InputFileFormSet(request.POST, prefix='input_files')
        shipping_form = TestRequestShippingForm(request.POST, prefix='shipping')

        # Validate main form and primary formsets first
        main_form_is_valid = form.is_valid()
        plastic_formset_is_valid = plastic_formset.is_valid()
        input_file_formset_is_valid = input_file_formset.is_valid()
        shipping_form_is_valid = shipping_form.is_valid()

        processed_pans_formsets = []
        all_pan_formsets_valid = True

        if input_file_formset_is_valid:
            for i, iff_form in enumerate(input_file_formset.forms):
                if not iff_form.cleaned_data.get('DELETE', False):
                    prefix = f'input_files-{i}-pans'
                    pan_fs = PanInlineFormSet(request.POST, instance=iff_form.instance, prefix=prefix)
                    if not pan_fs.is_valid():
                        all_pan_formsets_valid = False
                    processed_pans_formsets.append(pan_fs)
                else:
                    prefix = f'input_files-{i}-pans'
                    empty_pan_fs = PanInlineFormSet(prefix=prefix)
                    processed_pans_formsets.append(empty_pan_fs)

        elif request.POST:
            all_pan_formsets_valid = True
            for i, iff_form_unvalidated in enumerate(input_file_formset.forms):
                prefix = f'input_files-{i}-pans'
                instance_for_pan = iff_form_unvalidated.instance if iff_form_unvalidated.instance and iff_form_unvalidated.instance.pk else None
                pan_fs_with_data = PanInlineFormSet(request.POST, instance=instance_for_pan, prefix=prefix)
                if not pan_fs_with_data.is_valid():
                     all_pan_formsets_valid = False
                processed_pans_formsets.append(pan_fs_with_data)
        
        if not processed_pans_formsets:
            all_pan_formsets_valid = True


        is_overall_valid = (main_form_is_valid and
                            plastic_formset_is_valid and
                            input_file_formset_is_valid and
                            shipping_form_is_valid and
                            all_pan_formsets_valid)

        if is_overall_valid:
            try:
                with transaction.atomic():
                    test_request = form.save(commit=False)
                    test_request.tvf_initiator = request.user
                    
                    action = request.POST.get('action')
                    if action == 'submit':
                        initial_status, _ = TVFStatus.objects.get_or_create(name='TVF_SUBMITTED')
                        released_to_npi_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_RELEASED', defaults={'order': 2})
                        test_request.status = initial_status
                        test_request.current_phase = released_to_npi_phase
                    else: # 'save_draft'
                        draft_status, _ = TVFStatus.objects.get_or_create(name='Draft')
                        # New: PM_DRAFT phase for drafts, order 0
                        pm_draft_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='PM_DRAFT', defaults={'order': 0})
                        test_request.status = draft_status
                        test_request.current_phase = pm_draft_phase
                    
                    test_request.save()

                    plastic_formset.instance = test_request
                    plastic_formset.save()

                    for i, input_file_form in enumerate(input_file_formset.forms):
                        if input_file_form.cleaned_data.get('DELETE'):
                            if input_file_form.instance.pk:
                                input_file_form.instance.delete()
                            continue
                        
                        if input_file_form.has_changed() or (not input_file_form.instance.pk and any(input_file_form.cleaned_data.values())):
                            input_file_instance = input_file_form.save(commit=False)
                            input_file_instance.test_request = test_request
                            input_file_instance.save()

                            if i < len(processed_pans_formsets):
                                pan_fs_to_save = processed_pans_formsets[i]
                                for pan_form_instance in pan_fs_to_save.forms:
                                    if pan_form_instance.cleaned_data.get('DELETE'):
                                        if pan_form_instance.instance.pk:
                                            pan_form_instance.instance.delete()
                                        continue
                                    if pan_form_instance.has_changed() or (not pan_form_instance.instance.pk and any(pan_form_instance.cleaned_data.values())):
                                        pan_item = pan_form_instance.save(commit=False)
                                        pan_item.test_request_input_file = input_file_instance
                                        pan_item.save()
                    
                    shipping = shipping_form.save(commit=False)
                    shipping.test_request = test_request
                    shipping.save()
                
                if action == 'submit':
                    messages.success(request, f"TVF {test_request.tvf_number} created and submitted to NPI!")
                    return redirect('test_requests:coach_dashboard')
                else:
                    messages.info(request, f"TVF {test_request.tvf_number} saved as draft.")
                    return redirect('test_requests:detail', pk=test_request.pk)


            except Exception as e:
                messages.error(request, f"Error creating Test Request: {e}")
                import traceback
                traceback.print_exc()
        else:
            messages.error(request, "Please correct the errors below. Check all sections, including PAN entries if applicable.")

    else:
        form = TestRequestForm(initial={'tvf_initiator': request.user, 'request_received_date': timezone.now().strftime('%Y-%m-%dT%H:%M')})
        plastic_formset = PlasticCodeFormSet(prefix='plastic_codes')
        input_file_formset = InputFileFormSet(prefix='input_files')
        shipping_form = TestRequestShippingForm(prefix='shipping')
        
        processed_pans_formsets = []
        for i in range(input_file_formset.initial_form_count() + input_file_formset.extra):
            prefix = f'input_files-{i}-pans'
            processed_pans_formsets.append(PanInlineFormSet(prefix=prefix))

    context = {
        'form': form,
        'plastic_formset': plastic_formset,
        'input_file_formset': input_file_formset,
        'pans_formsets': processed_pans_formsets,
        'shipping_form': shipping_form,
        'role': 'Project Manager - Create TVF'
    }
    return render(request, 'test_requests/pm_create_tvf.html', context)

# --- NPI View: Update Data Processing Status ---
@login_required
@user_passes_test(is_npi_user, login_url='test_requests:access_denied')
def npi_update_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    # NPI relevant phases now start with TVF_RELEASED
    npi_relevant_phases = ['TVF_RELEASED', 'TVF_DP_DONE', 'TVF_PROCESSED_AT_NPI', 'Rejected to NPI']
    if not (tvf.current_phase.name in npi_relevant_phases or tvf.status.name == 'Rejected to NPI'):
        messages.warning(request, f"TVF {tvf.tvf_number} is not in your NPI queue for editing.")
        return redirect('test_requests:coach_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '') 

        if action == 'dp_done':
            if tvf.current_phase.name == 'TVF_RELEASED': # From TVF_RELEASED to TVF_DP_DONE
                tvf.status, _ = TVFStatus.objects.get_or_create(name='DP Done')
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_DP_DONE', defaults={'order': 3})
                tvf.comments = comments
                tvf.save()
                messages.success(request, f"TVF {tvf.tvf_number} marked as DP Done.")
                return redirect('test_requests:coach_dashboard')
            else:
                messages.warning(request, "Cannot mark DP Done in the current phase.")

        elif action == 'tvf_output':
            if tvf.current_phase.name == 'TVF_DP_DONE': # From TVF_DP_DONE to TVF_PROCESSED_AT_NPI
                tvf.status, _ = TVFStatus.objects.get_or_create(name='TVF Processed')
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_PROCESSED_AT_NPI', defaults={'order': 4})
                tvf.comments = comments
                tvf.save()
                messages.success(request, f"TVF {tvf.tvf_number} output processed. Ready for QA.")
                return redirect('test_requests:coach_dashboard')
            else:
                 messages.warning(request, "Cannot process TVF Output in the current phase.")

        elif action == 'push_to_qa':
            if tvf.current_phase.name == 'TVF_PROCESSED_AT_NPI': # From TVF_PROCESSED_AT_NPI to QA
                tvf.status, _ = TVFStatus.objects.get_or_create(name='Open at QA')
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_OPEN_AT_QA', defaults={'order': 5})
                tvf.comments = comments
                tvf.save()
                messages.success(request, f"TVF {tvf.tvf_number} pushed to Quality queue!")
                return redirect('test_requests:coach_dashboard')
            else:
                messages.warning(request, "Cannot push to QA in the current phase.")

        elif action == 'back_to_released': # New action: Back to Released
            if tvf.current_phase.name in ['TVF_DP_DONE', 'TVF_PROCESSED_AT_NPI']:
                tvf.status, _ = TVFStatus.objects.get_or_create(name='TVF_SUBMITTED') # Revert status to submitted
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_RELEASED', defaults={'order': 2})
                tvf.comments = comments
                tvf.save()
                messages.info(request, f"TVF {tvf.tvf_number} moved back to Released state.")
                return redirect('test_requests:coach_dashboard')
            else:
                messages.warning(request, "Cannot move back to Released from current phase.")

        elif action == 'back_to_dp_done': # New action: Back to DP Done (from Processed)
            if tvf.current_phase.name == 'TVF_PROCESSED_AT_NPI':
                tvf.status, _ = TVFStatus.objects.get_or_create(name='DP Done') # Revert status
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_DP_DONE', defaults={'order': 3})
                tvf.comments = comments
                tvf.save()
                messages.info(request, f"TVF {tvf.tvf_number} moved back to DP Done state.")
                return redirect('test_requests:coach_dashboard')
            else:
                messages.warning(request, "Cannot move back to DP Done from current phase.")

        elif action == 'reject':
            return redirect('test_requests:reject_tvf', tvf_id=tvf.pk)

    return render(request, 'test_requests/npi_update_tvf.html', {'tvf': tvf, 'role': 'NPI User'})


# --- Quality View: Update Validation Status ---
@login_required
@user_passes_test(is_quality_user, login_url='test_requests:access_denied')
def quality_update_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    quality_relevant_phases = ['TVF_OPEN_AT_QA', 'TVF_VALIDATED_AT_QA', 'Rejected to Quality']
    if not (tvf.current_phase.name in quality_relevant_phases or tvf.status.name == 'Rejected to Quality'):
        messages.warning(request, f"TVF {tvf.tvf_number} is not in your Quality queue for editing.")
        return redirect('test_requests:coach_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '')

        if action == 'process': # This button will now advance through QA steps
            if tvf.current_phase.name == 'TVF_OPEN_AT_QA': # From TVF_OPEN_AT_QA to TVF_VALIDATED_AT_QA
                tvf.status, _ = TVFStatus.objects.get_or_create(name='Validated')
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_VALIDATED_AT_QA', defaults={'order': 6})
                messages.success(request, f"TVF {tvf.tvf_number} marked as Validated at Quality!")
            elif tvf.current_phase.name == 'TVF_VALIDATED_AT_QA': # From TVF_VALIDATED_AT_QA to Logistics
                tvf.status, _ = TVFStatus.objects.get_or_create(name='Open at Logistics')
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_OPEN_AT_LOGISTICS', defaults={'order': 7})
                messages.success(request, f"TVF {tvf.tvf_number} pushed to Logistics queue!")
            else:
                messages.warning(request, "Invalid Quality process step for this TVF's current phase.")
                return redirect('test_requests:coach_dashboard')
            
            tvf.comments = comments
            tvf.is_rejected = False
            tvf.save()
            return redirect('test_requests:coach_dashboard')
        
        elif action == 'reject':
            return redirect('test_requests:reject_tvf', tvf_id=tvf.pk)

    return render(request, 'test_requests/quality_update_tvf.html', {'tvf': tvf, 'role': 'Quality User'})


# --- Logistics View: Update Shipping Status ---
@login_required
@user_passes_test(is_logistics_user, login_url='test_requests:access_denied')
def logistics_update_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    logistics_relevant_phases = ['TVF_OPEN_AT_LOGISTICS', 'Rejected to Logistics']
    if not (tvf.current_phase.name in logistics_relevant_phases or tvf.status.name == 'Rejected to Logistics'):
        messages.warning(request, f"TVF {tvf.tvf_number} is not in your Logistics queue for editing.")
        return redirect('test_requests:coach_dashboard')

    shipping_instance, created = TestRequestShipping.objects.get_or_create(test_request=tvf)

    # Create a form that only includes the tracking_number field
    class LogisticsShippingForm(forms.ModelForm):
        class Meta:
            model = TestRequestShipping
            fields = ['tracking_number'] # Only tracking_number for this simplified view
            widgets = {
                # Add any specific widgets needed for tracking_number here if necessary
            }

    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '')
        # Use the custom LogisticsShippingForm for validation
        shipping_form = LogisticsShippingForm(request.POST, instance=shipping_instance, prefix='shipping')

        if action == 'process':
            if shipping_form.is_valid():
                shipping = shipping_form.save(commit=False)
                shipping.date_shipped = timezone.now()
                shipping.save()

                tvf.status, _ = TVFStatus.objects.get_or_create(name='Shipped')
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_SHIPPED', defaults={'order': 14})
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

    else:
        # Pass the custom form to the template
        shipping_form = LogisticsShippingForm(instance=shipping_instance, prefix='shipping')

    return render(request, 'test_requests/logistics_update_tvf.html', {
        'tvf': tvf,
        'shipping_form': shipping_form,
        'role': 'Logistics User'
    })

# --- Common Rejection View ---
@login_required
def reject_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    if not (is_project_manager(request.user) or is_npi_user(request.user) or
            is_quality_user(request.user) or is_logistics_user(request.user) or
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

        if not target_phase_name or not rejection_comments or not reject_reason_id:
            messages.error(request, "Please select a target phase, provide rejection comments, AND select a rejection reason.")
            available_phases = TestRequestPhaseDefinition.objects.all().order_by('order')
            reject_reasons = RejectReason.objects.all().order_by('reason')
            return render(request, 'test_requests/reject_tvf.html', {
                'tvf': tvf,
                'available_phases': available_phases,
                'reject_reasons': reject_reasons,
                'role': 'Reject TVF',
                'selected_target_phase': target_phase_name,
                'submitted_comments': rejection_comments,
                'selected_reject_reason_id': reject_reason_id,
            })

        try:
            status_map = {
                'Project Manager': 'Rejected to PM',
                'PM_DRAFT': 'Rejected to PM', # Rejection to draft phase, status still Rejected to PM
                'TVF_RELEASED': 'Rejected to NPI',
                'TVF_DP_DONE': 'Rejected to NPI',
                'TVF_PROCESSED_AT_NPI': 'Rejected to NPI',
                'TVF_OPEN_AT_QA': 'Rejected to Quality',
                'TVF_VALIDATED_AT_QA': 'Rejected to Quality',
                'TVF_OPEN_AT_LOGISTICS': 'Rejected to Logistics',
                'REWORK_AT_PM': 'Rejected',
                'REWORK_AT_PROD': 'Rejected',
                'REWORK_AT_LOGISTICS': 'Rejected',
                'REWORK_AT_QA': 'Rejected',
            }
            new_status_name = status_map.get(target_phase_name, 'Rejected')

            target_status, _ = TVFStatus.objects.get_or_create(name=new_status_name)
            target_phase = TestRequestPhaseDefinition.objects.get(name=target_phase_name)
            reject_reason_obj = RejectReason.objects.get(pk=reject_reason_id)

            current_comments = tvf.comments if tvf.comments else ""
            tvf.comments = f"{current_comments}\n\nREJECTED by {request.user.username} to {target_phase_name} ({reject_reason_obj.reason}): {rejection_comments}"

            tvf.status = target_status
            tvf.current_phase = target_phase
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
    return redirect('test_requests:create_tvf')


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

                    saved_input_files = input_file_formset.save(commit=False)
                    for i, input_file in enumerate(saved_input_file_formset.forms):
                        if input_file.cleaned_data.get('DELETE'):
                            if input_file.instance.pk:
                                input_file.instance.delete()
                            continue
                        
                        if input_file.has_changed() or (not input_file.instance.pk and any(input_file.cleaned_data.values())):
                            input_file_instance = input_file.save(commit=False)
                            input_file_instance.test_request = test_request_saved
                            input_file_instance.save()

                            if i < len(pans_formsets): # Corrected from processed_pans_formsets
                                pan_fs_to_save = pans_formsets[i] # Corrected from processed_pans_formsets
                                for pan_form_instance in pan_fs_to_save.forms:
                                    if pan_form_instance.cleaned_data.get('DELETE'):
                                        if pan_form_instance.instance.pk:
                                            pan_form_instance.instance.delete()
                                        continue
                                    if pan_form_instance.has_changed() or (not pan_form_instance.instance.pk and any(pan_form_instance.cleaned_data.values())):
                                        pan_item = pan_form_instance.save(commit=False)
                                        pan_item.test_request_input_file = input_file_instance
                                        pan_item.save()

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

        'test_request': test_request
    }
    return render_to_pdf('test_requests/test_request_pdf_template.html', context)