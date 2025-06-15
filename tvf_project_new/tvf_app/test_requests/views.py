# tvf_app/test_requests/views.py
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib.auth.decorators import login_required, user_passes_test
from datetime import timedelta
from django.utils import timezone
from django import forms
from django.forms import formset_factory
from django.db.models import Q

# Import your models and forms
from .models import (
    TestRequest, Customer, Project, TVFType, TVFEnvironment, TVFStatus,
    PlasticCodeLookup, DispatchMethod, TestRequestPhaseDefinition,
    TestRequestPlasticCode, TestRequestInputFile, TestRequestPAN,
    TestRequestQuality, TestRequestShipping, TrustportFolder, RejectReason,
    # TestRequestPhaseLog # Uncomment if you plan to use this for detailed comments
)
from .forms import (
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
    # Define common statuses and phases
    # Phases
    pm_draft_phase_name = 'PM_DRAFT'
    project_manager_phase_name = 'PROJECT_MANAGER' # From user's DB dump ID 18
    tvf_released_phase_name = 'TVF_RELEASED'
    tvf_dp_done_phase_name = 'TVF_DP_DONE'
    tvf_processed_at_npi_phase_name = 'TVF_PROCESSED_AT_NPI'
    tvf_open_at_qa_phase_name = 'TVF_OPEN_AT_QA'
    tvf_validated_at_qa_phase_name = 'TVF_VALIDATED_AT_QA'
    tvf_open_at_logistics_phase_name = 'TVF_OPEN_AT_LOGISTICS'
    tvf_shipped_phase_name = 'TVF_SHIPPED' 
    tvf_completed_phase_name = 'TVF_COMPLETED' # Use phase name for completed
    tvf_cancelled_phase_name = 'TVF_CANCELLED' # Use phase name for cancelled

    rework_at_pm_phase_name = 'REWORK_AT_PM'
    rework_at_prod_phase_name = 'REWORK_AT_PROD' 
    rework_at_logistics_phase_name = 'REWORK_AT_LOGISTICS'
    rework_at_qa_phase_name = 'REWORK_AT_QA'

    # Statuses
    status_draft = 'Draft'
    status_submitted = 'TVF_SUBMITTED'
    status_dp_done = 'DP Done'
    status_tvf_processed = 'TVF Processed'
    status_open_at_qa = 'Open at QA'
    status_validated = 'Validated'
    status_open_at_logistics = 'Open at Logistics'
    status_shipped = 'Shipped'
    status_completed = 'Completed'
    status_cancelled = 'Cancelled'
    status_rejected_pm = 'Rejected to PM'
    status_rejected_npi = 'Rejected to NPI'
    status_rejected_quality = 'Rejected to Quality'
    status_rejected_logistics = 'Rejected to Logistics'


    # Initialize all TVF lists as empty
    pm_draft_tvfs = TestRequest.objects.none()
    pm_submitted_tvfs = TestRequest.objects.none()
    npi_released_tvfs = TestRequest.objects.none()
    npi_dp_done_tvfs = TestRequest.objects.none()
    npi_processed_tvfs = TestRequest.objects.none()
    quality_open_tvfs = TestRequest.objects.none()
    quality_validated_tvfs = TestRequest.objects.none()
    logistics_open_tvfs = TestRequest.objects.none()
    
    # For Coach/Superuser only
    all_display_tvfs = TestRequest.objects.none()
    completed_tvfs_list = TestRequest.objects.none()


    # Role-based filtering of TVFs
    if is_project_manager(request.user):
        user_tvfs = TestRequest.objects.filter(tvf_initiator=request.user)
        pm_draft_tvfs = user_tvfs.filter(status__name=status_draft, current_phase__name=pm_draft_phase_name)
        
        pm_submitted_tvfs = TestRequest.objects.filter(
            Q(tvf_initiator=request.user, current_phase__name=tvf_released_phase_name, status__name=status_submitted) | 
            Q(current_phase__name=project_manager_phase_name, status__name=status_rejected_pm, is_rejected=True) | 
            Q(current_phase__name=rework_at_pm_phase_name, status__name=status_rejected_pm, is_rejected=True) 
        ).order_by('-request_received_date')
        
    elif is_npi_user(request.user):
        npi_released_tvfs = TestRequest.objects.filter(
            Q(current_phase__name=tvf_released_phase_name, status__name=status_submitted) |
            Q(current_phase__name=rework_at_prod_phase_name, status__name=status_rejected_npi, is_rejected=True)
        ).order_by('-request_received_date')

        npi_dp_done_tvfs = TestRequest.objects.filter(current_phase__name=tvf_dp_done_phase_name, status__name=status_dp_done).order_by('-request_received_date')
        npi_processed_tvfs = TestRequest.objects.filter(current_phase__name=tvf_processed_at_npi_phase_name, status__name=status_tvf_processed).order_by('-request_received_date')
        
    elif is_quality_user(request.user):
        quality_open_tvfs = TestRequest.objects.filter(
            Q(current_phase__name=tvf_open_at_qa_phase_name, status__name=status_open_at_qa) |
            Q(current_phase__name=rework_at_qa_phase_name, status__name=status_rejected_quality, is_rejected=True)
        ).order_by('-request_received_date')

        quality_validated_tvfs = TestRequest.objects.filter(current_phase__name=tvf_validated_at_qa_phase_name, status__name=status_validated).order_by('-request_received_date')
        
    elif is_logistics_user(request.user):
        logistics_open_tvfs = TestRequest.objects.filter(
            Q(current_phase__name=tvf_open_at_logistics_phase_name, status__name=status_open_at_logistics) |
            Q(current_phase__name=rework_at_logistics_phase_name, status__name=status_rejected_logistics, is_rejected=True)
        ).order_by('-request_received_date')
        
    elif is_coach(request.user) or request.user.is_superuser:
        # Coaches/Superusers main display: All TVFs not yet completed or cancelled
        all_display_tvfs = TestRequest.objects.select_related(
            'customer', 'project', 'tvf_initiator', 'status', 'current_phase'
        ).exclude(
            Q(current_phase__name=tvf_completed_phase_name) | Q(current_phase__name=tvf_cancelled_phase_name)
        ).order_by('-request_received_date')

        # Also get completed TVFs for the separate "View Completed TVFs" list
        completed_tvfs_list = TestRequest.objects.select_related(
            'customer', 'project', 'tvf_initiator', 'status', 'current_phase'
        ).filter(
            Q(current_phase__name=tvf_completed_phase_name) | Q(current_phase__name=tvf_shipped_phase_name) | Q(current_phase__name=tvf_cancelled_phase_name)
        ).order_by('-tvf_completed_date') # Order by completion date

    # Phase lists for general update button conditions (used in tables for coach)
    npi_phases_for_button = [tvf_released_phase_name, tvf_dp_done_phase_name, tvf_processed_at_npi_phase_name, rework_at_prod_phase_name]
    quality_phases_for_button = [tvf_open_at_qa_phase_name, tvf_validated_at_qa_phase_name, rework_at_qa_phase_name]
    logistics_phases_for_button = [tvf_open_at_logistics_phase_name, rework_at_logistics_phase_name]

    context = {
        'role': 'Coach Dashboard',
        'is_project_manager': is_project_manager(request.user),
        'is_npi_user': is_npi_user(request.user),
        'is_quality_user': is_quality_user(request.user),
        'is_logistics_user': is_logistics_user(request.user),
        'is_coach': is_coach(request.user),
        'is_superuser': request.user.is_superuser,

        # For Coach/Superuser: main display list and completed list
        'all_display_tvfs': all_display_tvfs, 
        'completed_tvfs_list': completed_tvfs_list, 

        # PM specific lists (empty if not PM)
        'pm_draft_tvfs': pm_draft_tvfs,
        'pm_submitted_tvfs': pm_submitted_tvfs, 
        
        # NPI specific lists (empty if not NPI)
        'npi_released_tvfs': npi_released_tvfs,
        'npi_dp_done_tvfs': npi_dp_done_tvfs,
        'npi_processed_tvfs': npi_processed_tvfs,
        
        # Quality specific lists (empty if not Quality)
        'quality_open_tvfs': quality_open_tvfs,
        'quality_validated_tvfs': quality_validated_tvfs,

        # Logistics specific lists (empty if not Logistics)
        'logistics_open_tvfs': logistics_open_tvfs,

        # Coach specific lists (empty if not Coach/Superuser)
        'other_open_tvfs': TestRequest.objects.none(), # This will be unused now, handled by all_display_tvfs

        # Phase lists for button conditions (used in tables for coach)
        'npi_phases_for_button': npi_phases_for_button,       
        'quality_phases_for_button': quality_phases_for_button, 
        'logistics_phases_for_button': logistics_phases_for_button,
    }
    return render(request, 'test_requests/coach_dashboard.html', context)


# --- Coach Action: Mark TVF as Completed ---
@login_required
@user_passes_test(lambda u: is_coach(u) or u.is_superuser, login_url='test_requests:access_denied')
def mark_tvf_completed_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    # Only allow marking as completed if it's currently in 'Shipped' status/phase
    if tvf.current_phase.name != 'TVF_SHIPPED' or tvf.status.name != 'Shipped':
        messages.error(request, f"TVF {tvf.tvf_number} cannot be marked as completed unless it is in 'Shipped' status/phase.")
        return redirect('test_requests:coach_dashboard')

    if request.method == 'POST':
        comments_input = request.POST.get('comments', '').strip()
        
        try:
            with transaction.atomic():
                tvf.status, _ = TVFStatus.objects.get_or_create(name='Completed')
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_COMPLETED', defaults={'order': 8})
                tvf.tvf_completed_date = timezone.now()
                # Append completion comments
                current_comments = tvf.comments if tvf.comments else ""
                tvf.comments = f"{current_comments}\n\nCOMPLETED by {request.user.username}: {comments_input}"
                tvf.save()
                messages.success(request, f"TVF {tvf.tvf_number} marked as Completed.")
        except Exception as e:
            messages.error(request, f"Error marking TVF as completed: {e}")
        return redirect('test_requests:coach_dashboard')
    
    # If GET request, show a confirmation page (or just redirect back to dashboard)
    # For simplicity, if it's a GET, just redirect for now. A real app might have a modal.
    messages.info(request, "Please confirm completion via POST action.")
    return redirect('test_requests:coach_dashboard')

# --- Coach Action: Delete TVF ---
@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='test_requests:access_denied') # Only superusers can delete
def delete_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    if request.method == 'POST':
        try:
            tvf_number = tvf.tvf_number
            tvf.delete()
            messages.success(request, f"TVF {tvf_number} permanently deleted.")
        except Exception as e:
            messages.error(request, f"Error deleting TVF {tvf_number}: {e}")
        return redirect('test_requests:coach_dashboard')
    
    # For GET request, render a confirmation page/modal
    return render(request, 'test_requests/confirm_delete_tvf.html', {'tvf': tvf}) # You'll need to create this template


# --- Coach Action: Cancel TVF ---
@login_required
@user_passes_test(lambda u: is_coach(u) or u.is_superuser, login_url='test_requests:access_denied')
def cancel_tvf_view(request, tvf_id):
    tvf = get_object_or_404(TestRequest, pk=tvf_id)

    # Prevent cancelling already completed/shipped/cancelled TVFs
    if tvf.status.name in ['Completed', 'Shipped', 'Cancelled']: # Check status names
        messages.error(request, f"TVF {tvf.tvf_number} cannot be cancelled as it is already in a final state.")
        return redirect('test_requests:coach_dashboard')

    if request.method == 'POST':
        comments_input = request.POST.get('comments', '').strip()

        try:
            with transaction.atomic():
                tvf.status, _ = TVFStatus.objects.get_or_create(name='Cancelled') # Set status to 'Cancelled'
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_CANCELLED', defaults={'order': 9})
                tvf.is_rejected = False # Clear rejected status if it was
                # Append cancellation comments
                current_comments = tvf.comments if tvf.comments else ""
                tvf.comments = f"{current_comments}\n\nCANCELLED by {request.user.username}: {comments_input}"
                tvf.tvf_completed_date = timezone.now() # Mark as completed for archiving purposes
                tvf.save()
                messages.success(request, f"TVF {tvf.tvf_number} has been cancelled.")
        except Exception as e:
            messages.error(request, f"Error cancelling TVF: {e}")
        return redirect('test_requests:coach_dashboard')
    
    # For GET request, render a confirmation page/modal
    return render(request, 'test_requests/confirm_cancel_tvf.html', {'tvf': tvf}) # You'll need to create this template


# --- Project Manager View: Create TVF ---
@login_required
# Removed @user_passes_test(is_project_manager, login_url='test_requests:access_denied')
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
    npi_relevant_phases = ['TVF_RELEASED', 'TVF_DP_DONE', 'TVF_PROCESSED_AT_NPI', 'REWORK_AT_PROD'] # Include rework phase
    if not (tvf.current_phase.name in npi_relevant_phases or (tvf.is_rejected and tvf.current_phase.name == 'REWORK_AT_PROD')):
        messages.warning(request, f"TVF {tvf.tvf_number} is not in your NPI queue for editing.")
        return redirect('test_requests:coach_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '') 

        if action == 'dp_done':
            if tvf.current_phase.name in ['TVF_RELEASED', 'REWORK_AT_PROD']: # From TVF_RELEASED or REWORK_AT_PROD to TVF_DP_DONE
                tvf.status, _ = TVFStatus.objects.get_or_create(name='DP Done')
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_DP_DONE', defaults={'order': 3})
                tvf.comments = comments
                tvf.is_rejected = False # Clear rejected status
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
                tvf.is_rejected = False # Clear rejected status
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
                tvf.is_rejected = False # Clear rejected status
                tvf.save()
                messages.success(request, f"TVF {tvf.tvf_number} pushed to Quality queue!")
                return redirect('test_requests:coach_dashboard')
            else:
                messages.warning(request, "Cannot push to QA in the current phase.")

        elif action == 'back_to_released': # New action: Back to Released
            if tvf.current_phase.name in ['TVF_DP_DONE', 'TVF_PROCESSED_AT_NPI'] or tvf.current_phase.name == 'REWORK_AT_PROD':
                tvf.status, _ = TVFStatus.objects.get_or_create(name='TVF_SUBMITTED') # Revert status
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_RELEASED', defaults={'order': 2})
                tvf.comments = comments
                tvf.is_rejected = False # Clear rejected status
                tvf.save()
                messages.info(request, f"TVF {tvf.tvf_number} moved back to Released state.")
                return redirect('test_requests:coach_dashboard')
            else:
                messages.warning(request, "Cannot move back to Released from current phase.")

        elif action == 'back_to_dp_done': # New action: Back to DP Done (from Processed)
            if tvf.current_phase.name == 'TVF_PROCESSED_AT_NPI' or tvf.current_phase.name == 'REWORK_AT_PROD':
                tvf.status, _ = TVFStatus.objects.get_or_create(name='DP Done') # Revert status
                tvf.current_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_DP_DONE', defaults={'order': 3})
                tvf.comments = comments
                tvf.is_rejected = False # Clear rejected status
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

    quality_relevant_phases = ['TVF_OPEN_AT_QA', 'TVF_VALIDATED_AT_QA', 'REWORK_AT_QA'] # Include rework phase
    if not (tvf.current_phase.name in quality_relevant_phases or (tvf.is_rejected and tvf.current_phase.name == 'REWORK_AT_QA')):
        messages.warning(request, f"TVF {tvf.tvf_number} is not in your Quality queue for editing.")
        return redirect('test_requests:coach_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '')

        if action == 'process': # This button will now advance through QA steps
            if tvf.current_phase.name in ['TVF_OPEN_AT_QA', 'REWORK_AT_QA']: # From TVF_OPEN_AT_QA or REWORK_AT_QA to TVF_VALIDATED_AT_QA
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

    logistics_relevant_phases = ['TVF_OPEN_AT_LOGISTICS', 'REWORK_AT_LOGISTICS'] # Include rework phase
    if not (tvf.current_phase.name in logistics_relevant_phases or (tvf.is_rejected and tvf.current_phase.name == 'REWORK_AT_LOGISTICS')):
        messages.warning(request, f"TVF {tvf.tvf_number} is not in your Logistics queue for editing.")
        return redirect('test_requests:coach_dashboard')

    shipping_instance, created = TestRequestShipping.objects.get_or_create(test_request=tvf)

    # Create a form that only includes the tracking_number field
    class LogisticsShippingForm(forms.ModelForm):
        class Meta:
            model = TestRequestShipping
            fields = ['tracking_number'] # Only tracking_number for this simplified view
            # No widgets needed here as date_shipped is set programmatically

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

    if tvf.status.name in ['Completed', 'Shipped', 'Cancelled']: # Added Cancelled here
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
                'PM_DRAFT': 'Rejected to PM',
                'PROJECT_MANAGER': 'Rejected to PM', # Rejection to PROJECT_MANAGER phase should also set 'Rejected to PM' status
                'REWORK_AT_PM': 'Rejected to PM', 
                'TVF_RELEASED': 'Rejected to NPI',
                'TVF_DP_DONE': 'Rejected to NPI',
                'TVF_PROCESSED_AT_NPI': 'Rejected to NPI',
                'REWORK_AT_PROD': 'Rejected to NPI', 
                'TVF_OPEN_AT_QA': 'Rejected to Quality',
                'TVF_VALIDATED_AT_QA': 'Rejected to Quality',
                'REWORK_AT_QA': 'Rejected to Quality', 
                'TVF_OPEN_AT_LOGISTICS': 'Rejected to Logistics',
                'REWORK_AT_LOGISTICS': 'Rejected to Logistics', 
            }
            new_status_name = status_map.get(target_phase_name, 'Rejected') # Default to generic 'Rejected' if not mapped

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

    # Ensure to pass the correct target_phase_name based on TVF's current phase for initial selection
    # For now, it will list all available phases for rejection
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
    view_type = request.GET.get('view', 'backlog') # Default to 'backlog'

    if view_type == 'shipped':
        tvfs_to_display = TestRequest.objects.select_related(
            'customer', 'project', 'tvf_initiator', 'status', 'current_phase'
        ).filter(
            status__name='Shipped'
        ).order_by('-tvf_completed_date')
        active_view = 'shipped'
        title = "Shipped TVFs"
    else: # 'backlog' or any other value
        tvfs_to_display = TestRequest.objects.select_related(
            'customer', 'project', 'tvf_initiator', 'status', 'current_phase'
        ).exclude(
            Q(status__name='Shipped') | Q(status__name='Completed') | Q(status__name='Rejected') | Q(current_phase__name='TVF_CANCELLED')
        ).order_by('-request_received_date')
        active_view = 'backlog'
        title = "Backlog TVFs (Open / Pending)"

    context = {
        'tvfs': tvfs_to_display,
        'active_view': active_view,
        'title': title,
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
        'shipping_details__dispatch_method',
        'phase_logs', # Fetch phase logs for detailed comments
    ), pk=pk)

    context = {
        'test_request': test_request,
        'is_coach_or_superuser': is_coach(request.user) or request.user.is_superuser,
        # You can add more context here if certain buttons are only visible based on specific roles
    }
    return render(request, 'test_requests/test_request_detail.html', context)

@login_required
def test_request_update_view(request, pk):
    tvf = get_object_or_404(TestRequest, pk=pk)

    quality_instance, created_quality = TestRequestQuality.objects.get_or_create(test_request=tvf)
    shipping_instance, created_shipping = TestRequestShipping.objects.get_or_create(test_request=tvf)

    # Determine if the current user has permission to edit this TVF
    can_edit = False
    
    # Initiator can edit drafts
    if request.user == tvf.tvf_initiator and tvf.status.name == 'Draft':
        can_edit = True
    # NPI users can always edit TVFs in their workflow (including rejected ones for NPI)
    elif is_npi_user(request.user) and tvf.current_phase.name in ['TVF_RELEASED', 'TVF_DP_DONE', 'TVF_PROCESSED_AT_NPI', 'REWORK_AT_NPI',]:
        can_edit = True
    # Project Managers can edit if rejected back to PM and they initiated it
    elif is_project_manager(request.user) and tvf.current_phase.name == 'REWORK_AT_PM' and request.user == tvf.tvf_initiator:
        can_edit = True
    # Quality users can edit if rejected back to QA
    elif is_quality_user(request.user) and tvf.current_phase.name == 'REWORK_AT_QA':
        can_edit = True
    # Logistics users can edit if rejected back to Logistics
    elif is_logistics_user(request.user) and tvf.current_phase.name == 'REWORK_AT_LOGISTICS':
        can_edit = True
    # Coaches and Superusers always have edit access
    elif is_coach(request.user) or request.user.is_superuser:
        can_edit = True

    if not can_edit:
        messages.error(request, f"You do not have permission to edit TVF {tvf.tvf_number} at its current stage ({tvf.status.name}, {tvf.current_phase.name}).")
        return redirect('test_requests:coach_dashboard') # Or detail view of the TVF

    if request.method == 'POST':
        form = TestRequestForm(request.POST, instance=tvf)
        plastic_formset = PlasticCodeFormSet(request.POST, instance=tvf, prefix='plastic_codes')
        input_file_formset = InputFileFormSet(request.POST, instance=tvf, prefix='input_files')
        shipping_form = TestRequestShippingForm(request.POST, instance=shipping_instance, prefix='shipping')
        quality_form = TestRequestQualityForm(request.POST, instance=quality_instance, prefix='quality')

        # First, validate all primary forms/formsets
        main_forms_valid = (form.is_valid() and
                            plastic_formset.is_valid() and
                            input_file_formset.is_valid() and
                            shipping_form.is_valid() and
                            quality_form.is_valid())

        pans_formsets = []
        all_pan_formsets_valid = True

        # Now, handle PAN formsets based on the validity of input_file_formset
        if main_forms_valid:
            for i, input_file_form_validated in enumerate(input_file_formset.forms):
                if not input_file_form_validated.cleaned_data.get('DELETE', False):
                    prefix = f'input_files-{i}-pans'
                    pan_fs = PanInlineFormSet(request.POST, instance=input_file_form_validated.instance, prefix=prefix)
                    if not pan_fs.is_valid():
                        all_pan_formsets_valid = False
                    pans_formsets.append(pan_fs)
                else:
                    prefix = f'input_files-{i}-pans'
                    pans_formsets.append(PanInlineFormSet(prefix=prefix)) # Append empty formset for deleted files
        else:
            # If main forms are not valid, re-instantiate PAN formsets with POST data for error display
            for i, input_file_form_unvalidated in enumerate(input_file_formset.forms):
                prefix = f'input_files-{i}-pans'
                instance_for_pan = input_file_form_unvalidated.instance if input_file_form_unvalidated.instance and input_file_form_unvalidated.instance.pk else None
                pan_fs_with_data = PanInlineFormSet(request.POST, instance=instance_for_pan, prefix=prefix)
                pans_formsets.append(pan_fs_with_data)
            all_pan_formsets_valid = False # Assume false if primary forms are invalid for overall check

        is_overall_valid = main_forms_valid and all_pan_formsets_valid

        if is_overall_valid:
            try:
                with transaction.atomic():
                    tvf_saved = form.save(commit=False)

                    action = request.POST.get('action')
                    if action == 'submit' and tvf_saved.status.name == 'Rejected to PM' and tvf_saved.tvf_initiator == request.user:
                        # If a PM is submitting a TVF rejected to them, change status back to submitted
                        new_status, _ = TVFStatus.objects.get_or_create(name='TVF_SUBMITTED')
                        new_phase, _ = TestRequestPhaseDefinition.objects.get_or_create(name='TVF_RELEASED', defaults={'order': 2})
                        tvf_saved.status = new_status
                        tvf_saved.current_phase = new_phase
                        tvf_saved.is_rejected = False # Clear rejected flag upon successful resubmission
                        messages.success(request, f"TVF {tvf_saved.tvf_number} updated and re-submitted to NPI!")
                    else:
                        messages.info(request, f"TVF {tvf_saved.tvf_number} updated successfully!")

                    tvf_saved.save()

                    plastic_formset.instance = tvf_saved
                    plastic_formset.save()

                    # Save input files and their PANs
                    for i, input_file_form in enumerate(input_file_formset.forms): # Iterate over forms (now validated if is_overall_valid is true)
                        if input_file_form.cleaned_data.get('DELETE'):
                            if input_file_form.instance.pk:
                                input_file_form.instance.delete()
                            continue
                        
                        if input_file_form.has_changed() or (not input_file_form.instance.pk and any(input_file_form.cleaned_data.values())):
                            input_file_instance = input_file_form.save(commit=False)
                            input_file_instance.test_request = tvf_saved
                            input_file_instance.save()

                            if i < len(pans_formsets):
                                pan_fs_to_save = pans_formsets[i] # This pan_fs_to_save is already validated
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
                
                return redirect('test_requests:detail', pk=tvf_saved.pk)
            except Exception as e:
                messages.error(request, f"Error updating Test Request: {e}")
                import traceback
                traceback.print_exc()
        else:
            messages.error(request, "Please correct the errors below.")
            # Formsets are already re-instantiated with POST data and errors if not valid
            # so no need to repeat them here.

    else: # GET request
        form = TestRequestForm(instance=tvf)
        plastic_formset = PlasticCodeFormSet(instance=tvf, prefix='plastic_codes')
        input_file_formset = InputFileFormSet(instance=tvf, prefix='input_files')
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
        'test_request': tvf, # Pass tvf object to template
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
        'shipping_details__shipping_sign_off_by'
    ), pk=pk)

    context = {

        'test_request': test_request
    }
    return render_to_pdf('test_requests/test_request_pdf_template.html', context)