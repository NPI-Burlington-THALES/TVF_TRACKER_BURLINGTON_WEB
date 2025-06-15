# tvf_app/test_requests/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.db.models import Max
from django.utils import timezone

# --- Lookup / Reference Models ---

class Customer(models.Model):
    """
    Represents a customer.
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the customer")
    sla_days = models.IntegerField(default=0, help_text="Service Level Agreement in days for this customer (for analytics)")
    contact_person = models.CharField(max_length=255, blank=True, null=True, help_text="Primary contact person for the customer")
    email = models.EmailField(blank=True, null=True, help_text="Contact email for the customer")
    phone = models.CharField(max_length=50, blank=True, null=True, help_text="Contact phone number for the customer")

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ['name']

    def __str__(self):
        return self.name

class TVFEnvironment(models.Model):
    """
    Represents the environment for a TVF (e.g., PAT, UAT, PROD).
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the TVF environment (e.g., PAT, UAT, PROD)")

    class Meta:
        verbose_name = "TVF Environment"
        verbose_name_plural = "TVF Environments"
        ordering = ['name']

    def __str__(self):
        return self.name

class Project(models.Model):
    """
    Represents a project associated with a customer and TVF environment.
    """
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, help_text="The customer associated with this project")
    name = models.CharField(max_length=255, help_text="Name of the project")
    tvf_environment = models.ForeignKey(TVFEnvironment, on_delete=models.PROTECT, help_text="The TVF environment for this project")
    trustport_folder_base = models.CharField(max_length=255, blank=True, null=True, help_text="Base Trustport folder for data processing for this project")
    dispatch_method_default = models.CharField(max_length=255, blank=True, null=True, help_text="Default dispatch method for this project")

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        unique_together = ('customer', 'name', 'tvf_environment')
        ordering = ['customer__name', 'name', 'tvf_environment__name']

    def __str__(self):
        return f"{self.customer.name} - {self.name} ({self.tvf_environment.name})"

class PlasticCodeLookup(models.Model):
    """
    Represents a predefined plastic code.
    """
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, help_text="The customer this plastic code belongs to")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, help_text="The project this plastic code is used in")
    tvf_environment = models.ForeignKey(TVFEnvironment, on_delete=models.PROTECT, help_text="The TVF environment for this plastic code")
    code = models.CharField(max_length=155, unique=True, help_text="The unique plastic code (e.g., '01200733')")
    description = models.TextField(blank=True, null=True, help_text="Description of the plastic code")

    class Meta:
        verbose_name = "Plastic Code Lookup"
        verbose_name_plural = "Plastic Code Lookups"
        ordering = ['code']

    def __str__(self):
        return self.code

class TVFType(models.Model):
    """
    Represents a type of TVF (e.g., 'EMV Keys', 'PIN Mailer').
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the TVF type")

    class Meta:
        verbose_name = "TVF Type"
        verbose_name_plural = "TVF Types"
        ordering = ['name']

    def __str__(self):
        return self.name

class TVFStatus(models.Model):
    """
    Represents the status of a TVF (e.g., 'Pending', 'In Progress', 'Completed', 'Rejected').
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the TVF status")

    class Meta:
        verbose_name = "TVF Status"
        verbose_name_plural = "TVF Statuses"
        ordering = ['name']

    def __str__(self):
        return self.name

class DispatchMethod(models.Model):
    """
    Represents available shipping/dispatch methods (e.g., 'XPRESSPOST', 'FEDEX').
    """
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, null=True, blank=True, help_text="The customer this dispatch method is available for")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, null=True, blank=True, help_text="The project this dispatch method is available for")
    name = models.CharField(max_length=255, help_text="Name of the dispatch method")

    class Meta:
        verbose_name = "Dispatch Method"
        verbose_name_plural = "Dispatch Methods"
        unique_together = ('customer', 'project', 'name') # Ensure uniqueness per customer/project
        ordering = ['name']

    def __str__(self):
        customer_name = self.customer.name if self.customer else "Global"
        project_name = self.project.name if self.project else "Global"
        return f"{self.name} ({customer_name}/{project_name})"

class TrustportFolder(models.Model):
    """
    Stores predefined Trustport folder paths, linked to Customer and Project.
    """
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, help_text="The customer this Trustport folder belongs to")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, help_text="The project this Trustport folder belongs to")
    folder_path = models.CharField(max_length=500, help_text="The actual Trustport folder path")
    
    class Meta:
        verbose_name = "Trustport Folder"
        verbose_name_plural = "Trustport Folders"
        unique_together = ('customer', 'project', 'folder_path')
        ordering = ['folder_path']

    def __str__(self):
        return f"{self.folder_path} ({self.customer.name} - {self.project.name})"

class TestRequestPhaseDefinition(models.Model):
    """
    Defines the different phases/departments a Test Request goes through.
    Crucial for tracking time spent in each phase for analytics.
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the phase (e.g., Data Entry, Personalization, Quality, Shipping)")
    order = models.IntegerField(unique=True, help_text="Order in which phases typically occur")

    class Meta:
        verbose_name = "TVF Phase Definition"
        verbose_name_plural = "TVF Phase Definitions"
        ordering = ['order']

    def __str__(self):
        return f"{self.order}. {self.name}"

class RejectReason(models.Model):
    """
    Defines predefined reasons for rejecting a TVF.
    """
    reason = models.CharField(max_length=255, unique=True, help_text="Reason for rejecting a TVF")
    description = models.TextField(blank=True, null=True, help_text="Detailed description of the reason")

    class Meta:
        verbose_name = "Reject Reason"
        verbose_name_plural = "Reject Reasons"
        ordering = ['reason']

    def __str__(self):
        return self.reason

# --- Main Test Request Model ---

class TestRequest(models.Model):
    """
    The central model for each Test Validation Form.
    """
    # General Info
    tvf_number = models.IntegerField(unique=True, editable=False, db_index=True, help_text="Unique auto-incrementing TVF Number")
    cr_number = models.CharField(max_length=255, blank=True, null=True, help_text="Change Request Number from requestor")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='test_requests', help_text="The customer for this TVF")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name='test_requests', help_text="The project for this TVF")
    tvf_name = models.CharField(max_length=255, help_text="Name of the TVF")
    tvf_initiator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='initiated_tvfs', help_text="The user who initiated this TVF")
    tvf_type = models.ForeignKey(TVFType, on_delete=models.PROTECT, related_name='test_requests', help_text="The type of TVF")
    tvf_environment = models.ForeignKey(TVFEnvironment, on_delete=models.PROTECT, related_name='test_requests', help_text="The environment for this TVF (e.g., PAT)")
    tvf_pin_mailer = models.BooleanField(default=False, help_text="Indicates if this TVF is for a PIN mailer")
    run_today = models.BooleanField(default=False, help_text="Indicates if this TVF is scheduled to run today.")
    
    # Dates
    request_received_date = models.DateTimeField(help_text="Date and time when the request was received/submitted")
    request_ship_date = models.DateTimeField(blank=True, null=True, help_text="Requested ship date for the TVF (for SLA tracking)")
    tvf_completed_date = models.DateTimeField(blank=True, null=True, help_text="Actual date and time when the TVF was completed")

    # Codes & Comments
    s_code = models.CharField(max_length=255, blank=True, null=True, help_text="S-Code for the TVF")
    d_code = models.CharField(max_length=255, blank=True, null=True, help_text="D-Code for the TVF")
    comments = models.TextField(blank=True, null=True, help_text="General comments for the TVF")

    # Configuration Versions
    trustport_folder_actual = models.ForeignKey(TrustportFolder, on_delete=models.PROTECT, blank=True, null=True, help_text="Actual Trustport folder used for this specific TVF") 
    pres_config_version = models.CharField(max_length=255, blank=True, null=True, help_text="Personalization Configuration Version")
    proc_config_version = models.CharField(max_length=255, blank=True, null=True, help_text="Processing Configuration Version")
    pin_config_version = models.CharField(max_length=255, blank=True, null=True, help_text="PIN Configuration Version")

    # Status and Phase Tracking (for analytics)
    status = models.ForeignKey(TVFStatus, on_delete=models.PROTECT, related_name='test_requests_by_status', help_text="Current status of the TVF")
    current_phase = models.ForeignKey(TestRequestPhaseDefinition, on_delete=models.PROTECT, blank=True, null=True, related_name='current_tvfs', help_text="Current phase of the TVF lifecycle")
    last_status_update = models.DateTimeField(auto_now=True, help_text="Automatically updated timestamp of the last status change")

    # Rejection Fields
    is_rejected = models.BooleanField(default=False, help_text="Indicates if the TVF has been rejected")
    rejected_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='rejected_tvfs', help_text="User who rejected the TVF")
    rejected_reason = models.ForeignKey(RejectReason, on_delete=models.PROTECT, null=True, blank=True, help_text="Reason for rejection")
    rejected_comments = models.TextField(blank=True, null=True, help_text="Additional comments for rejection")
    rejected_date = models.DateTimeField(blank=True, null=True, help_text="Date and time of rejection")
    
    # Custom permissions for role-based access
    class Meta:
        verbose_name = "Test Request (TVF)"
        verbose_name_plural = "Test Requests (TVFs)"
        ordering = ['-tvf_number']
        permissions = []

    def __str__(self):
        return f"TVF {self.tvf_number}: {self.tvf_name} ({self.customer.name})"

    def save(self, *args, **kwargs):
        # Set initial status if not already set (e.g., 'Pending' or 'New')
        if not self.status_id:
            self.status, created = TVFStatus.objects.get_or_create(name='Pending')
        # Set initial phase if not already set
        if not self.current_phase_id:
            self.current_phase, created = TestRequestPhaseDefinition.objects.get_or_create(name='Data Entry', order=1)
        super().save(*args, **kwargs)

# Signal to auto-increment tvf_number
@receiver(pre_save, sender=TestRequest)
def set_tvf_number(sender, instance, **kwargs):
    if not instance.tvf_number:
        max_tvf_number = sender.objects.all().aggregate(Max('tvf_number'))['tvf_number__max']
        instance.tvf_number = (max_tvf_number or 7554) + 1 # Start from 7555 if no existing TVFs

# --- Related Models (One-to-Many) ---

class TestRequestPlasticCode(models.Model):
    """
    Stores plastic codes and quantities for a specific TestRequest.
    """
    test_request = models.ForeignKey(TestRequest, on_delete=models.CASCADE, related_name='plastic_codes_entries', help_text="The TVF this plastic code entry belongs to")
    plastic_code_lookup = models.ForeignKey(PlasticCodeLookup, on_delete=models.PROTECT, null=True, blank=True, help_text="The specific plastic code used") # Made nullable for manual input
    manual_plastic_code = models.CharField(max_length=255, blank=True, null=True, help_text="Manually entered plastic code if not in lookup.") # New field for manual entry
    quantity = models.IntegerField(help_text="Quantity for this plastic code")
    thermal_colour = models.CharField(max_length=255, blank=True, null=True, help_text="Thermal color associated with this plastic code")

    class Meta:
        verbose_name = "Plastic Code Entry"
        verbose_name_plural = "Plastic Code Entries"
        # unique_together = ('test_request', 'plastic_code_lookup') # Remove unique_together to allow nulls
        ordering = ['plastic_code_lookup__code', 'manual_plastic_code']

    def __str__(self):
        code_display = self.plastic_code_lookup.code if self.plastic_code_lookup else self.manual_plastic_code
        return f"{self.test_request.tvf_number} - {code_display} ({self.quantity})"

class TestRequestInputFile(models.Model):
    """
    Stores details about input files, including card and PIN workorder quantities.
    """
    test_request = models.ForeignKey(TestRequest, on_delete=models.CASCADE, related_name='input_files_entries', help_text="The TVF this input file entry belongs to")
    file_name = models.CharField(max_length=255, help_text="Name of the input file")
    date_file_received = models.DateTimeField(blank=True, null=True, help_text="Date and time when this input file was received")

    # Workorders - Cards section
    card_co = models.CharField(max_length=255, blank=True, null=True, help_text="Card Control Order")
    card_wo = models.CharField(max_length=255, blank=True, null=True, help_text="Card Work Order")
    card_qty = models.IntegerField(default=0, help_text="Quantity of cards in this input file")

    # Workorders - PINS section
    pin_co = models.CharField(max_length=255, blank=True, null=True, help_text="PIN Control Order")
    pin_wo = models.CharField(max_length=255, blank=True, null=True, help_text="PIN Work Order")
    pin_qty = models.IntegerField(default=0, help_text="Quantity of PINs expected in this input file")

    class Meta:
        verbose_name = "Input File Entry"
        verbose_name_plural = "Input File Entries"
        unique_together = ('test_request', 'file_name')
        ordering = ['file_name']

    def __str__(self):
        return f"{self.test_request.tvf_number} - {self.file_name}"

class TestRequestPAN(models.Model):
    """
    Stores truncated PANs associated with each input file within a test request.
    """
    test_request_input_file = models.ForeignKey(TestRequestInputFile, on_delete=models.CASCADE, related_name='pans', help_text="The specific input file this PAN belongs to")
    pan_truncated = models.CharField(max_length=255, help_text="Truncated Primary Account Number (e.g., XXXXXXXXXXXX7067)")
    is_available = models.BooleanField(default=False, help_text="Indicates if the PAN is available (from 'Avble' in zc_tvfpans)")

    class Meta:
        verbose_name = "TVF PAN"
        verbose_name_plural = "TVF PANs"
        unique_together = ('test_request_input_file', 'pan_truncated')
        ordering = ['pan_truncated']

    def __str__(self):
        return f"{self.test_request_input_file.file_name} - {self.pan_truncated}"

# --- Quality and Shipping Models (One-to-One) ---

class TestRequestQuality(models.Model):
    """
    Stores quality assurance details for a TestRequest.
    """
    test_request = models.OneToOneField(TestRequest, on_delete=models.CASCADE, related_name='quality_details', help_text="The TVF this quality check is for")
    output_accordance_request = models.BooleanField(default=False, help_text="Output in accordance with request")
    checked_against_specifications = models.BooleanField(default=False, help_text="Checked against specifications being tested")
    quality_sign_off_by = models.ForeignKey(User, on_delete=models.PROTECT, blank=True, null=True, related_name='quality_signed_off_tvfs', help_text="User who signed off on quality")
    quality_sign_off_date = models.DateTimeField(blank=True, null=True, help_text="Date and time of quality sign off")

    class Meta:
        verbose_name = "Quality Check"
        verbose_name_plural = "Quality Checks"
        ordering = ['test_request__tvf_number']

    def __str__(self):
        return f"Quality for TVF {self.test_request.tvf_number}"

class TestRequestShipping(models.Model):
    """
    Stores shipping details for a TestRequest.
    """
    test_request = models.OneToOneField(TestRequest, on_delete=models.CASCADE, related_name='shipping_details', help_text="The TVF this shipping info is for")
    dispatch_method = models.ForeignKey(DispatchMethod, on_delete=models.PROTECT, null=True, blank=True, help_text="Method of dispatch (e.g., XPRESSPOST)")
    shipping_sign_off_by = models.ForeignKey(User, on_delete=models.PROTECT, blank=True, null=True, related_name='shipping_signed_off_tvfs', help_text="User who signed off on shipping")
    date_shipped = models.DateTimeField(blank=True, null=True, help_text="Date and time when the TVF was shipped")
    ship_to_name = models.CharField(max_length=255, blank=True, null=True, help_text="Recipient Name")
    ship_to_business_name = models.CharField(max_length=255, blank=True, null=True, help_text="Business Name")
    ship_to_address_1 = models.CharField(max_length=255, blank=True, null=True, help_text="Address Line 1")
    ship_to_address_2 = models.CharField(max_length=255, blank=True, null=True, help_text="Address Line 2")
    ship_to_address_3 = models.CharField(max_length=255, blank=True, null=True, help_text="Address Line 3")
    ship_to_city = models.CharField(max_length=255, blank=True, null=True, help_text="City")
    ship_to_state_province = models.CharField(max_length=255, blank=True, null=True, help_text="State/Province")
    ship_to_postal_code = models.CharField(max_length=20, blank=True, null=True, help_text="Postal Code")
    ship_to_country = models.CharField(max_length=255, blank=True, null=True, help_text="Country")
    # Removed tracking_number field
    tracking_number = models.CharField(max_length=255, blank=True, null=True, help_text="Tracking number for the shipment") # <--- ADDED THIS LINE
    
    class Meta:
        verbose_name = "Shipping Information"
        verbose_name_plural = "Shipping Information"
        ordering = ['dispatch_method__name']

    def __str__(self):
        return f"Shipping for TVF {self.test_request.tvf_number}"

# --- Analytics and Audit Models ---

class TestRequestPhaseLog(models.Model):
    """
    Logs the entry and exit times for a TVF in different phases/departments.
    Crucial for calculating time spent in each phase.
    """
    test_request = models.ForeignKey(TestRequest, on_delete=models.CASCADE, related_name='phase_logs', help_text="The TVF for this phase log")
    phase_name = models.ForeignKey(TestRequestPhaseDefinition, on_delete=models.PROTECT, help_text="The phase/department name")
    start_time = models.DateTimeField(default=timezone.now, help_text="When the TVF entered this phase")
    end_time = models.DateTimeField(blank=True, null=True, help_text="When the TVF exited this phase")
    responsible_user = models.ForeignKey(User, on_delete=models.PROTECT, blank=True, null=True, help_text="User responsible during this phase")
    comments = models.TextField(blank=True, null=True, help_text="Comments on this phase transition")

    class Meta:
        verbose_name = "TVF Phase Log"
        verbose_name_plural = "TVF Phase Logs"
        ordering = ['start_time']

    def __str__(self):
        return f"TVF {self.test_request.tvf_number} - Phase: {self.phase_name.name} ({self.start_time.strftime('%Y-%m-%d %H:%M')})"

    @property
    def duration_minutes(self):
        """Calculates the duration in minutes for this phase log entry."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() / 60
        return None

class AuditLog(models.Model):
    """
    A generic audit log to track changes to any model instance.
    This model will be managed by Django's migrations.
    """
    timestamp = models.DateTimeField(auto_now_add=True, help_text="When the change occurred")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, help_text="User who made the change")
    action = models.CharField(max_length=255, help_text="Type of action (e.g., 'created', 'updated', 'deleted')")
    model_name = models.CharField(max_length=255, help_text="Name of the model that was changed")
    record_id = models.CharField(max_length=255, help_text="ID of the record that was changed")
    field_name = models.CharField(max_length=255, blank=True, null=True, help_text="Specific field that was changed (if applicable)")
    old_value = models.TextField(blank=True, null=True, help_text="Old value of the field (if applicable)")
    new_value = models.TextField(blank=True, null=True, help_text="New value of the field (if applicable)")
    change_details = models.TextField(blank=True, null=True, help_text="JSON or text details of the change")

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.user or 'System'} - {self.action} {self.model_name} (ID: {self.record_id})"