# tvf_app/test_requests/admin.py
from django.contrib import admin
from django.contrib.auth.models import Group # Import Group model
from .models import (
    Customer, Project, TVFType, TVFEnvironment, PlasticCodeLookup,
    DispatchMethod, TVFStatus, TestRequest, TestRequestPlasticCode,
    TestRequestInputFile, TestRequestPAN, TestRequestQuality,
    TestRequestShipping, TestRequestPhaseDefinition, TestRequestPhaseLog,
    AuditLog, RejectReason, TrustportFolder
)

# Register your models here.

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'sla_days', 'contact_person', 'email')
    search_fields = ('name', 'contact_person', 'email')

@admin.register(TVFEnvironment)
class TVFEnvironmentAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer', 'tvf_environment', 'trustport_folder_base', 'dispatch_method_default')
    list_filter = ('customer', 'tvf_environment')
    search_fields = ('name', 'customer__name', 'tvf_environment__name')
    raw_id_fields = ('customer', 'tvf_environment')

@admin.register(PlasticCodeLookup)
class PlasticCodeLookupAdmin(admin.ModelAdmin):
    list_display = ('code', 'description', 'customer', 'project', 'tvf_environment')
    list_filter = ('customer', 'project', 'tvf_environment')
    search_fields = ('code', 'description', 'customer__name', 'project__name')
    raw_id_fields = ('customer', 'project', 'tvf_environment')

@admin.register(TVFType)
class TVFTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(TVFStatus)
class TVFStatusAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(DispatchMethod)
class DispatchMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer', 'project') # Include new fields
    list_filter = ('customer', 'project')
    search_fields = ('name', 'customer__name', 'project__name')
    raw_id_fields = ('customer', 'project') # Allow searching for customer/project by ID

# --- NEW ADMIN: TrustportFolderAdmin ---
@admin.register(TrustportFolder)
class TrustportFolderAdmin(admin.ModelAdmin):
    list_display = ('folder_path', 'customer', 'project')
    list_filter = ('customer', 'project')
    search_fields = ('folder_path', 'customer__name', 'project__name')
    raw_id_fields = ('customer', 'project')

@admin.register(TestRequestPhaseDefinition)
class TestRequestPhaseDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')
    search_fields = ('name',)
    list_editable = ('order',)

@admin.register(RejectReason) # New Admin for RejectReason
class RejectReasonAdmin(admin.ModelAdmin):
    list_display = ('reason', 'description')
    search_fields = ('reason', 'description')

# Inline for related models within TestRequest admin
class TestRequestPlasticCodeInline(admin.TabularInline):
    model = TestRequestPlasticCode
    extra = 1
    # Specify fields for admin inline as well
    fields = ('plastic_code_lookup', 'manual_plastic_code', 'quantity', 'thermal_colour')
    raw_id_fields = ('plastic_code_lookup',) # Keep this for lookup field

class TestRequestInputFileInline(admin.TabularInline):
    model = TestRequestInputFile
    extra = 1
    # Specify fields for admin inline
    fields = ('file_name', 'date_file_received', 'card_co', 'card_wo', 'card_qty', 'pin_co', 'pin_wo', 'pin_qty')


class TestRequestPANInline(admin.TabularInline):
    model = TestRequestPAN
    extra = 1
    # Specify fields for admin inline
    fields = ('pan_truncated', 'is_available')


class TestRequestPhaseLogInline(admin.TabularInline):
    model = TestRequestPhaseLog
    extra = 1
    raw_id_fields = ('phase_name', 'responsible_user')
    readonly_fields = ('start_time', 'duration_minutes')

@admin.register(TestRequest)
class TestRequestAdmin(admin.ModelAdmin):
    list_display = ('tvf_number', 'tvf_name', 'customer', 'project', 'tvf_initiator', 'status', 'current_phase', 'is_rejected', 'request_received_date', 'request_ship_date', 'tvf_completed_date', 'run_today')
    list_filter = ('customer', 'project', 'tvf_type', 'tvf_environment', 'status', 'current_phase', 'tvf_pin_mailer', 'is_rejected', 'run_today')
    search_fields = ('tvf_number__iexact', 'tvf_name__icontains', 'cr_number__iexact', 'customer__name__icontains', 'project__name__icontains', 'tvf_initiator__username__icontains')
    raw_id_fields = ('customer', 'project', 'tvf_initiator', 'tvf_type', 'tvf_environment', 'status', 'current_phase', 'rejected_by', 'rejected_reason', 'trustport_folder_actual')
    readonly_fields = ('tvf_number', 'last_status_update')

    fieldsets = (
        (None, {
            'fields': ('cr_number', 'customer', 'project', 'tvf_name', 'tvf_initiator', 'tvf_type', 'tvf_environment', 'tvf_pin_mailer', 'status', 'current_phase', 'run_today')
        }),
        ('Dates', {
            'fields': ('request_received_date', 'request_ship_date', 'tvf_completed_date', 'last_status_update')
        }),
        ('Codes & Comments', {
            'fields': ('s_code', 'd_code', 'comments')
        }),
        ('Configuration Versions', {
            'fields': ('trustport_folder_actual', 'pres_config_version', 'proc_config_version', 'pin_config_version')
        }),
        ('Rejection Details', {
            'fields': ('is_rejected', 'rejected_by', 'rejected_reason', 'rejected_comments', 'rejected_date'),
            'classes': ('collapse',), # Makes this section collapsible
        }),
    )
    # inlines = [] # If you want to use the inlines defined above in the admin for TestRequest itself, uncomment and add them
    # Example: inlines = [TestRequestPlasticCodeInline, TestRequestInputFileInline, TestRequestPhaseLogInline]


@admin.register(TestRequestInputFile)
class TestRequestInputFileAdmin(admin.ModelAdmin):
    list_display = ('test_request', 'file_name', 'card_qty', 'pin_qty', 'date_file_received')
    list_filter = ('test_request__customer', 'test_request__project', 'test_request')
    search_fields = ('file_name__icontains', 'test_request__tvf_number__iexact')
    raw_id_fields = ('test_request',)
    inlines = [TestRequestPANInline] # Add PAN inline here for nested management in admin

@admin.register(TestRequestPAN)
class TestRequestPANAdmin(admin.ModelAdmin):
    list_display = ('test_request_input_file', 'pan_truncated', 'is_available')
    search_fields = ('pan_truncated', 'test_request_input_file__file_name')
    raw_id_fields = ('test_request_input_file',)
    list_filter = ('is_available',)

@admin.register(TestRequestQuality)
class TestRequestQualityAdmin(admin.ModelAdmin):
    list_display = ('test_request', 'output_accordance_request', 'checked_against_specifications', 'quality_sign_off_by', 'quality_sign_off_date')
    raw_id_fields = ('test_request', 'quality_sign_off_by')
    search_fields = ('test_request__tvf_number__iexact', 'quality_sign_off_by__username__icontains')

@admin.register(TestRequestShipping)
class TestRequestShippingAdmin(admin.ModelAdmin):
    list_display = ('test_request', 'dispatch_method', 'shipping_sign_off_by', 'date_shipped', 'ship_to_name', 'ship_to_city')
    raw_id_fields = ('test_request', 'dispatch_method', 'shipping_sign_off_by')
    search_fields = ('test_request__tvf_number__iexact', 'shipping_sign_off_by__username__icontains', 'ship_to_name__icontains', 'ship_to_city__icontains')
    fieldsets = (
        (None, {
            'fields': ('test_request', 'dispatch_method', 'shipping_sign_off_by', 'date_shipped')
        }),
        ('Shipping Address', {
            'fields': ('ship_to_name', 'ship_to_business_name', 'ship_to_address_1', 'ship_to_address_2', 'ship_to_address_3', 'ship_to_city', 'ship_to_state_province', 'ship_to_postal_code', 'ship_to_country')
        }),
    )


@admin.register(TestRequestPhaseLog)
class TestRequestPhaseLogAdmin(admin.ModelAdmin):
    list_display = ('test_request', 'phase_name', 'start_time', 'end_time', 'duration_minutes', 'responsible_user')
    list_filter = ('phase_name', 'responsible_user', 'test_request__customer', 'test_request__project')
    search_fields = ('test_request__tvf_number__iexact', 'phase_name__name__icontains', 'responsible_user__username__icontains')
    raw_id_fields = ('test_request', 'phase_name', 'responsible_user')
    readonly_fields = ('duration_minutes',)

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'model_name', 'record_id', 'field_name', 'new_value')
    list_filter = ('action', 'model_name', 'user')
    search_fields = ('model_name', 'record_id', 'field_name', 'old_value', 'new_value', 'user__username')
    readonly_fields = ('timestamp', 'user', 'action', 'model_name', 'record_id', 'field_name', 'old_value', 'new_value', 'change_details')