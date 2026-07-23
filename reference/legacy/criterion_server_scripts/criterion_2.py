"""
UCC Intelligence Platform Server Script

Visible name:
    UCC Analytics - Criterion 2

Script type:
    API

API method:
    ucc_analytics_criterion_2

Purpose:
    Return permission-aware live analytics foundations for EduTrust Criterion 2.

Current status:
    Live API foundation. The dashboard uses this API. Unsupported fields and
    unavailable sources are reported explicitly instead of being guessed.

Deployment:
    Allow Guest must remain disabled.
"""

payload_input = frappe.form_dict.get("payload") or {}
try:
    payload = json.loads(payload_input) if isinstance(payload_input, str) else payload_input
except Exception:
    payload = {}
if not isinstance(payload, dict):
    payload = {}
action = payload.get("action") or "summary"
subcriterion = payload.get("subcriterion") or "2.1.1"
filters = payload.get("filters") or {}
if not isinstance(filters, dict):
    filters = {}
metric_id = payload.get("metric_id")
page = payload.get("page") or 1
page_size = payload.get("page_size") or 50
row_limit = payload.get("limit") or 2000

try:
    page = max(1, int(page))
except Exception:
    page = 1

try:
    page_size = max(1, min(int(page_size), 200))
except Exception:
    page_size = 50

try:
    row_limit = max(1, min(int(row_limit), 5000))
except Exception:
    row_limit = 2000

ALLOWED_ACTIONS = [
    "summary", "source_status", "policy_registry", "requirement_registry",
    "question_registry", "drilldown"
]
if action not in ALLOWED_ACTIONS:
    frappe.throw("Unsupported Criterion 2 action.")

POLICY_REGISTRY = {'2.1.1': {'title': 'Staff Selection and Management',
           'policy': 'PPD-OEE-HR-2.1.1',
           'version': '2.2'},
 '2.1.2': {'title': 'Staff Training and Development',
           'policy': 'PPD-OEE-HR-2.1.2',
           'version': '1.2'},
 '2.2.1': {'title': 'Internal and External Communication',
           'policy': 'PPD-SES-MG-2.2.1',
           'version': '1.2'},
 '2.3.1': {'title': 'Data and Information Management',
           'policy': 'PPD-OEE-IT-2.3.1',
           'version': '1.2'},
 '2.3.2': {'title': 'Knowledge Management', 'policy': 'PPD-OE-IT-2.3.2', 'version': '1.2'},
 '2.4.1': {'title': 'Feedback Management', 'policy': 'PPD-SGL-SQ-2.4.1', 'version': '2.3'},
 '2.4.2': {'title': 'Student Satisfaction Survey', 'policy': 'PPD-SGL-SQ-2.4.2', 'version': '2.2'},
 '2.4.3': {'title': 'Staff Satisfaction Survey', 'policy': 'PPD-SGL-SQ-2.4.3', 'version': '2.2'}}

SOURCE_CANDIDATES = {'employee': ['Employee'],
 'job_applicant': ['Job Applicant'],
 'job_requisition': ['Job Requisition'],
 'interview_feedback': ['Interview Feedback'],
 'employee_onboarding': ['Employee Onboarding'],
 'employee_separation': ['Employee Separation'],
 'exit_interview': ['Exit Interview', 'Exit Interview Form'],
 'appraisal': ['Appraisal', 'Performance Appraisal'],
 'training_event': ['Training Event'],
 'tna': ['Training Needs Analysis'],
 'training_program': ['Training Program'],
 'training_result': ['Training Result'],
 'training_feedback': ['Training Feedback'],
 'training_sponsorship': ['Training Sponsorship Application'],
 'stakeholder_registry': ['Stakeholder Registry'],
 'stakeholder_engagement': ['Stakeholder Engagement Strategy'],
 'material_vetting': ['Material Vetting Form'],
 'essential_information': ['Essential Information'],
 'document_control': ['Document Control'],
 'quality_performance': ['Quality Performance Outcomes'],
 'quality_meeting': ['Quality Meeting'],
 'quality_action': ['Quality Action'],
 'survey_management': ['Survey Management'],
 'survey_tracking': ['Survey Tracking', 'Survey Response'],
 'helpdesk_ticket': ['HD Ticket', 'Issue', 'Helpdesk Ticket'],
 'employee_grievance': ['Employee Grievance'],
 'manpower_planning': ['Manpower Planning and Deployment'],
 'salary_structure': ['Salary Structure'],
 'salary_component': ['Salary Component'],
 'todo': ['ToDo', 'To Do'],
 'print_format': ['Print Format'],
 'letter_head': ['Letter Head'],
 'student_onboarding_survey': ['Student Onboarding Survey'],
 'end_course_survey': ['End of Course Survey'],
 'staff_onboarding_survey': ['Staff Onboarding Survey'],
 'staff_survey': ['Staff Survey'],
 'exit_interview_survey': ['Exit Interview Survey']}

SAFE_FIELDS = {'employee': ['name',
              'employee_name',
              'status',
              'department',
              'designation',
              'date_of_joining',
              'relieving_date',
              'employment_type',
              'company',
              'user_id',
              'modified'],
 'job_applicant': ['name',
                   'applicant_name',
                   'status',
                   'job_title',
                   'job_opening',
                   'email_id',
                   'creation',
                   'modified'],
 'job_requisition': ['name',
                     'designation',
                     'department',
                     'status',
                     'requested_by',
                     'expected_by',
                     'no_of_positions',
                     'modified'],
 'interview_feedback': ['name',
                        'interview',
                        'interviewer',
                        'job_applicant',
                        'result',
                        'average_rating',
                        'modified'],
 'employee_onboarding': ['name',
                         'employee',
                         'employee_name',
                         'job_applicant',
                         'date_of_joining',
                         'boarding_status',
                         'status',
                         'modified'],
 'employee_separation': ['name',
                         'employee',
                         'employee_name',
                         'separation_date',
                         'boarding_status',
                         'status',
                         'modified'],
 'exit_interview': ['name',
                    'employee',
                    'employee_name',
                    'date',
                    'status',
                    'reason_for_leaving',
                    'modified'],
 'appraisal': ['name',
               'employee',
               'employee_name',
               'status',
               'start_date',
               'end_date',
               'appraisal_cycle',
               'final_score',
               'modified'],
 'training_event': ['name',
                    'event_name',
                    'training_program',
                    'status',
                    'start_time',
                    'end_time',
                    'type',
                    'trainer_name',
                    'modified'],
 'tna': ['name',
         'participant_type',
         'participant_doctype',
         'participant',
         'participant_full_name',
         'employee_id',
         'employee_full_name',
         'source_type',
         'department',
         'manpower_planning_and_development',
         'employee_onboarding',
         'appraisal_link',
         'academic_year',
         'assessment_date',
         'assessed_by',
         'assessed_by_full_name',
         'review_date',
         'reviewed_by',
         'reviewed_by_full_name',
         'performance_evaluation',
         'index_value',
         'improvement_average',
         'conclusion',
         'list_of_trainings',
         'total_estimated_cost',
         'appraisal',
         'amended_from',
         'modified'],
 'training_program': ['name',
                      'training_program',
                      'program_name',
                      'status',
                      'start_date',
                      'end_date',
                      'modified'],
 'training_result': ['name', 'employee', 'training_event', 'status', 'result', 'score', 'modified'],
 'training_feedback': ['name', 'employee', 'training_event', 'rating', 'status', 'modified'],
 'training_sponsorship': ['name',
                          'employee',
                          'training_program',
                          'status',
                          'amount',
                          'posting_date',
                          'modified'],
 'stakeholder_registry': ['name',
                          'stakeholder_name',
                          'stakeholder_type',
                          'category',
                          'status',
                          'department',
                          'modified'],
 'stakeholder_engagement': ['name',
                            'stakeholder',
                            'stakeholder_group',
                            'engagement_type',
                            'communication_channel',
                            'frequency',
                            'status',
                            'engagement_date',
                            'next_engagement_date',
                            'modified'],
 'material_vetting': ['name',
                      'naming_series',
                      'material_name',
                      'type',
                      'requestor_name',
                      'full_name',
                      'department',
                      'posting_date',
                      'duration_of_use',
                      'marketing_channel',
                      'target_audience',
                      'geographic_scope',
                      'version_no',
                      'material_attachment',
                      'description_of_request',
                      'reason_for_request',
                      'impact_analysis',
                      'impact_description',
                      'external_parties',
                      'vetter',
                      'vetter_name',
                      'amendments',
                      'vetter_table',
                      'checklist_template',
                      'list',
                      'general_comment',
                      'final_approval_date',
                      'approval_status',
                      'approved_by',
                      'approved_by_full_name',
                      'approval_remarks',
                      'modified'],
 'essential_information': ['name',
                           'title',
                           'information_type',
                           'status',
                           'effective_date',
                           'review_date',
                           'owner',
                           'modified'],
 'document_control': ['name',
                      'document_title',
                      'document_type',
                      'document_code',
                      'version',
                      'status',
                      'effective_date',
                      'review_date',
                      'next_review_date',
                      'department',
                      'owner',
                      'modified'],
 'quality_performance': ['name',
                         'outcome',
                         'outcome_category',
                         'indicator',
                         'status',
                         'target',
                         'actual',
                         'measurement_date',
                         'owner',
                         'modified'],
 'quality_meeting': ['name',
                     'meeting_date',
                     'status',
                     'review',
                     'procedure',
                     'minutes',
                     'modified'],
 'quality_action': ['name',
                    'status',
                    'custom_status_updates',
                    'date',
                    'custom_proposed_date',
                    'custom_completed_date',
                    'feedback',
                    'modified'],
 'survey_management': ['name',
                       'survey_name',
                       'survey_type',
                       'status',
                       'start_date',
                       'end_date',
                       'audience',
                       'modified'],
 'survey_tracking': ['name',
                     'survey',
                     'survey_type',
                     'respondent_type',
                     'status',
                     'response_date',
                     'rating',
                     'score',
                     'modified'],
 'helpdesk_ticket': ['name',
                     'subject',
                     'status',
                     'priority',
                     'ticket_type',
                     'agreement_status',
                     'opening_date',
                     'response_by',
                     'resolution_by',
                     'resolution_date',
                     'feedback_rating',
                     'modified'],
 'employee_grievance': ['name',
                        'employee',
                        'employee_name',
                        'status',
                        'grievance_type',
                        'posting_date',
                        'resolution_date',
                        'modified'],
 'manpower_planning': ['name',
                       'department',
                       'status',
                       'year',
                       'number_of_positions',
                       'required_positions',
                       'current_headcount',
                       'gap',
                       'owner',
                       'review_date',
                       'modified'],
 'salary_structure': ['name', 'is_active', 'company', 'payroll_frequency', 'currency', 'modified'],
 'salary_component': ['name',
                      'type',
                      'depends_on_payment_days',
                      'is_tax_applicable',
                      'disabled',
                      'modified'],
 'todo': ['name',
          'status',
          'priority',
          'date',
          'allocated_to',
          'reference_type',
          'reference_name',
          'description',
          'modified'],
 'print_format': ['name', 'doc_type', 'disabled', 'standard', 'custom_format', 'modified'],
 'letter_head': ['name', 'is_default', 'disabled', 'modified'],
 'student_onboarding_survey': ['name',
                               'student',
                               'status',
                               'survey_date',
                               'rating',
                               'score',
                               'modified'],
 'end_course_survey': ['name',
                       'student',
                       'program',
                       'status',
                       'survey_date',
                       'rating',
                       'score',
                       'modified'],
 'staff_onboarding_survey': ['name',
                             'employee',
                             'status',
                             'survey_date',
                             'rating',
                             'score',
                             'modified'],
 'staff_survey': ['name', 'employee', 'status', 'survey_date', 'rating', 'score', 'modified'],
 'exit_interview_survey': ['name',
                           'employee',
                           'status',
                           'survey_date',
                           'rating',
                           'score',
                           'modified']}

FILTER_FIELD_CANDIDATES = {'status': ['status', 'boarding_status', 'agreement_status'],
 'year': ['year', 'academic_year', 'monitoring_year'],
 'review_year': ['year', 'academic_year', 'monitoring_year'],
 'department': ['department'],
 'employee': ['employee', 'employee_name'],
 'survey_type': ['survey_type', 'type'],
 'month': ['month']}

CONFIG = {'2.1.1': {'sources': ['employee',
                       'job_requisition',
                       'job_applicant',
                       'interview_feedback',
                       'employee_onboarding',
                       'appraisal',
                       'employee_separation',
                       'exit_interview',
                       'manpower_planning',
                       'salary_structure',
                       'salary_component'],
           'metrics': [{'id': 'c211-employees',
                        'label': 'Employees in scope',
                        'source': 'employee',
                        'mode': 'all'},
                       {'id': 'c211-active-employees',
                        'label': 'Active employees',
                        'source': 'employee',
                        'mode': 'equals',
                        'field': ['status'],
                        'value': 'Active'},
                       {'id': 'c211-requisitions',
                        'label': 'Job requisitions',
                        'source': 'job_requisition',
                        'mode': 'all'},
                       {'id': 'c211-open-requisitions',
                        'label': 'Open job requisitions',
                        'source': 'job_requisition',
                        'mode': 'in',
                        'field': ['status'],
                        'values': ['Open', 'Pending', 'Approved']},
                       {'id': 'c211-applicants',
                        'label': 'Job applicants',
                        'source': 'job_applicant',
                        'mode': 'all'},
                       {'id': 'c211-selected-applicants',
                        'label': 'Selected or accepted applicants',
                        'source': 'job_applicant',
                        'mode': 'in',
                        'field': ['status'],
                        'values': ['Accepted', 'Selected', 'Offer Accepted', 'Approved']},
                       {'id': 'c211-interviews',
                        'label': 'Interview feedback records',
                        'source': 'interview_feedback',
                        'mode': 'all'},
                       {'id': 'c211-onboardings',
                        'label': 'Employee onboarding records',
                        'source': 'employee_onboarding',
                        'mode': 'all'},
                       {'id': 'c211-completed-onboardings',
                        'label': 'Completed employee onboardings',
                        'source': 'employee_onboarding',
                        'mode': 'in',
                        'field': ['boarding_status', 'status'],
                        'values': ['Completed', 'Closed']},
                       {'id': 'c211-appraisals',
                        'label': 'Performance appraisal records',
                        'source': 'appraisal',
                        'mode': 'all'},
                       {'id': 'c211-separations',
                        'label': 'Employee separation records',
                        'source': 'employee_separation',
                        'mode': 'all'},
                       {'id': 'c211-exit-interviews',
                        'label': 'Exit interview records',
                        'source': 'exit_interview',
                        'mode': 'all'},
                       {'id': 'c211-competency-threshold',
                        'label': 'Competency-based interview threshold compliance',
                        'source': 'interview_feedback',
                        'mode': 'unsupported',
                        'message': 'The approved interview scoring threshold fields were not '
                                   'supplied.'},
                       {'id': 'c211-manpower-plans',
                        'label': 'Manpower planning records',
                        'source': 'manpower_planning',
                        'mode': 'all'},
                       {'id': 'c211-salary-structures',
                        'label': 'Salary structures',
                        'source': 'salary_structure',
                        'mode': 'all'},
                       {'id': 'c211-salary-components',
                        'label': 'Salary components',
                        'source': 'salary_component',
                        'mode': 'all'}]},
 '2.1.2': {'sources': ['employee',
                       'appraisal',
                       'training_event',
                       'tna',
                       'training_program',
                       'training_result',
                       'training_feedback',
                       'training_sponsorship'],
           'metrics': [{'id': 'c212-training-events',
                        'label': 'Training events',
                        'source': 'training_event',
                        'mode': 'all'},
                       {'id': 'c212-completed-events',
                        'label': 'Completed training events',
                        'source': 'training_event',
                        'mode': 'in',
                        'field': ['status'],
                        'values': ['Completed', 'Closed']},
                       {'id': 'c212-tna',
                        'label': 'Training needs assessments',
                        'source': 'tna',
                        'mode': 'all'},
                       {'id': 'c212-approved-tna',
                        'label': 'Reviewed training needs analyses',
                        'source': 'tna',
                        'mode': 'truthy',
                        'field': ['reviewed_by', 'review_date']},
                       {'id': 'c212-programs',
                        'label': 'Training programmes',
                        'source': 'training_program',
                        'mode': 'all'},
                       {'id': 'c212-results',
                        'label': 'Training result records',
                        'source': 'training_result',
                        'mode': 'all'},
                       {'id': 'c212-completed-results',
                        'label': 'Completed or passed training results',
                        'source': 'training_result',
                        'mode': 'in',
                        'field': ['status', 'result'],
                        'values': ['Completed', 'Passed', 'Pass']},
                       {'id': 'c212-feedback',
                        'label': 'Training feedback records',
                        'source': 'training_feedback',
                        'mode': 'all'},
                       {'id': 'c212-feedback-rating',
                        'label': 'Average training feedback rating',
                        'source': 'training_feedback',
                        'mode': 'average_fields',
                        'fields': [['rating', 'score']],
                        'unit': 'rating'},
                       {'id': 'c212-sponsorship',
                        'label': 'Training sponsorship applications',
                        'source': 'training_sponsorship',
                        'mode': 'all'},
                       {'id': 'c212-appraisals',
                        'label': 'Appraisals available for training needs',
                        'source': 'appraisal',
                        'mode': 'all'},
                       {'id': 'c212-training-coverage',
                        'label': 'Employee training completion coverage',
                        'source': 'employee',
                        'mode': 'unsupported',
                        'message': 'Employee-to-training attendance child-table relationships were '
                                   'not supplied.'}]},
 '2.2.1': {'sources': ['stakeholder_registry',
                       'stakeholder_engagement',
                       'material_vetting',
                       'essential_information'],
           'metrics': [{'id': 'c221-stakeholders',
                        'label': 'Stakeholders in the registry',
                        'source': 'stakeholder_registry',
                        'mode': 'all'},
                       {'id': 'c221-engagements',
                        'label': 'Stakeholder engagement records',
                        'source': 'stakeholder_engagement',
                        'mode': 'all'},
                       {'id': 'c221-materials',
                        'label': 'Communication materials submitted',
                        'source': 'material_vetting',
                        'mode': 'all'},
                       {'id': 'c221-approved-materials',
                        'label': 'Approved communication materials',
                        'source': 'material_vetting',
                        'mode': 'in',
                        'field': ['approval_status', 'workflow_state'],
                        'values': ['Approved', 'Final Approval', 'Conditionally Approved']},
                       {'id': 'c221-pending-materials',
                        'label': 'Pending communication approvals',
                        'source': 'material_vetting',
                        'mode': 'in',
                        'field': ['approval_status', 'workflow_state'],
                        'values': ['Pending', 'In Progress', 'Requires Amendments', 'Waiting to Vet', 'Waiting for Approval', 'Draft']},
                       {'id': 'c221-essential-info',
                        'label': 'Essential Information records',
                        'source': 'essential_information',
                        'mode': 'all'},
                       {'id': 'c221-overdue-info-review',
                        'label': 'Essential Information overdue for review',
                        'source': 'essential_information',
                        'mode': 'date_before_today',
                        'field': ['review_date', 'next_review_date']},
                       {'id': 'c221-channel-coverage',
                        'label': 'Approved channel and frequency coverage',
                        'source': 'stakeholder_engagement',
                        'mode': 'all_required',
                        'fields': [['communication_channel', 'channel'],
                                   ['frequency', 'engagement_frequency']]}]},
 '2.3.1': {'sources': ['document_control',
                       'quality_performance',
                       'quality_meeting',
                       'quality_action'],
           'metrics': [{'id': 'c231-documents',
                        'label': 'Controlled documents and records',
                        'source': 'document_control',
                        'mode': 'all'},
                       {'id': 'c231-current-documents',
                        'label': 'Current or approved documents',
                        'source': 'document_control',
                        'mode': 'in',
                        'field': ['status'],
                        'values': ['Current', 'Approved', 'Active']},
                       {'id': 'c231-overdue-reviews',
                        'label': 'Documents overdue for review',
                        'source': 'document_control',
                        'mode': 'date_before_today',
                        'field': ['next_review_date', 'review_date']},
                       {'id': 'c231-performance-outcomes',
                        'label': 'Quality Performance Outcomes',
                        'source': 'quality_performance',
                        'mode': 'all'},
                       {'id': 'c231-quality-meetings',
                        'label': 'Quality Meetings',
                        'source': 'quality_meeting',
                        'mode': 'all'},
                       {'id': 'c231-quality-actions',
                        'label': 'Data and information Quality Actions',
                        'source': 'quality_action',
                        'mode': 'all'},
                       {'id': 'c231-data-quality',
                        'label': 'Automated data-quality exceptions',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'The approved data-quality validation result fields were not '
                                   'supplied.'}]},
 '2.3.2': {'sources': ['document_control',
                       'quality_meeting',
                       'quality_action',
                       'print_format',
                       'letter_head'],
           'metrics': [{'id': 'c232-documents',
                        'label': 'Knowledge documents in scope',
                        'source': 'document_control',
                        'mode': 'all'},
                       {'id': 'c232-approved',
                        'label': 'Approved or current knowledge documents',
                        'source': 'document_control',
                        'mode': 'in',
                        'field': ['status'],
                        'values': ['Approved', 'Current', 'Active']},
                       {'id': 'c232-obsolete',
                        'label': 'Obsolete or archived documents',
                        'source': 'document_control',
                        'mode': 'in',
                        'field': ['status'],
                        'values': ['Obsolete', 'Archived', 'Superseded']},
                       {'id': 'c232-overdue',
                        'label': 'Knowledge documents overdue for review',
                        'source': 'document_control',
                        'mode': 'date_before_today',
                        'field': ['next_review_date', 'review_date']},
                       {'id': 'c232-meetings',
                        'label': 'Quality Meetings recording knowledge updates',
                        'source': 'quality_meeting',
                        'mode': 'all'},
                       {'id': 'c232-actions',
                        'label': 'Knowledge-improvement Quality Actions',
                        'source': 'quality_action',
                        'mode': 'all'},
                       {'id': 'c232-disposal',
                        'label': 'Record disposal completion',
                        'source': 'document_control',
                        'mode': 'unsupported',
                        'message': 'Record disposal and retention fields were not supplied.'},
                       {'id': 'c232-print-formats',
                        'label': 'Controlled print formats',
                        'source': 'print_format',
                        'mode': 'all'},
                       {'id': 'c232-letter-heads',
                        'label': 'Controlled letter heads',
                        'source': 'letter_head',
                        'mode': 'all'}]},
 '2.4.1': {'sources': ['survey_management',
                       'survey_tracking',
                       'helpdesk_ticket',
                       'employee_grievance',
                       'quality_action',
                       'todo'],
           'metrics': [{'id': 'c241-surveys',
                        'label': 'Survey and feedback instruments',
                        'source': 'survey_management',
                        'mode': 'all'},
                       {'id': 'c241-responses',
                        'label': 'Survey tracking records',
                        'source': 'survey_tracking',
                        'mode': 'all'},
                       {'id': 'c241-tickets',
                        'label': 'Feedback tickets',
                        'source': 'helpdesk_ticket',
                        'mode': 'all'},
                       {'id': 'c241-open-tickets',
                        'label': 'Open feedback tickets',
                        'source': 'helpdesk_ticket',
                        'mode': 'not_in',
                        'field': ['status'],
                        'values': ['Closed', 'Resolved']},
                       {'id': 'c241-closed-tickets',
                        'label': 'Closed or resolved feedback tickets',
                        'source': 'helpdesk_ticket',
                        'mode': 'in',
                        'field': ['status'],
                        'values': ['Closed', 'Resolved']},
                       {'id': 'c241-sla-failed',
                        'label': 'Feedback tickets with failed SLA',
                        'source': 'helpdesk_ticket',
                        'mode': 'equals',
                        'field': ['agreement_status'],
                        'value': 'Failed'},
                       {'id': 'c241-grievances',
                        'label': 'Employee grievance records',
                        'source': 'employee_grievance',
                        'mode': 'all'},
                       {'id': 'c241-quality-actions',
                        'label': 'Feedback-related Quality Actions',
                        'source': 'quality_action',
                        'mode': 'truthy',
                        'field': ['feedback']},
                       {'id': 'c241-priority-matrix',
                        'label': 'Feedback priority matrix compliance',
                        'source': 'helpdesk_ticket',
                        'mode': 'unsupported',
                        'message': 'Urgency and impact score fields were not supplied.'},
                       {'id': 'c241-todos',
                        'label': 'Feedback follow-up tasks',
                        'source': 'todo',
                        'mode': 'all'},
                       {'id': 'c241-open-todos',
                        'label': 'Open feedback follow-up tasks',
                        'source': 'todo',
                        'mode': 'not_in',
                        'field': ['status'],
                        'values': ['Closed', 'Cancelled']}]},
 '2.4.2': {'sources': ['survey_management',
                       'survey_tracking',
                       'student_onboarding_survey',
                       'end_course_survey'],
           'metrics': [{'id': 'c242-surveys',
                        'label': 'Student satisfaction survey instruments',
                        'source': 'survey_management',
                        'mode': 'conditions',
                        'conditions': [{'field': ['survey_type', 'type', 'survey_name'],
                                        'op': 'contains',
                                        'value': 'student'}]},
                       {'id': 'c242-responses',
                        'label': 'Student satisfaction responses',
                        'source': 'survey_tracking',
                        'mode': 'conditions',
                        'conditions': [{'field': ['respondent_type', 'survey_type', 'type'],
                                        'op': 'contains',
                                        'value': 'student'}]},
                       {'id': 'c242-completed',
                        'label': 'Completed student survey responses',
                        'source': 'survey_tracking',
                        'mode': 'conditions',
                        'conditions': [{'field': ['respondent_type', 'survey_type', 'type'],
                                        'op': 'contains',
                                        'value': 'student'},
                                       {'field': ['status'],
                                        'op': 'in',
                                        'values': ['Completed', 'Submitted']}]},
                       {'id': 'c242-rating',
                        'label': 'Average student satisfaction score',
                        'source': 'survey_tracking',
                        'mode': 'average_fields',
                        'fields': [['rating', 'score']],
                        'conditions': [{'field': ['respondent_type', 'survey_type', 'type'],
                                        'op': 'contains',
                                        'value': 'student'}],
                        'unit': 'rating'},
                       {'id': 'c242-coverage',
                        'label': 'Student survey coverage rate',
                        'source': 'survey_tracking',
                        'mode': 'unsupported',
                        'message': 'The eligible-population denominator and survey-cycle '
                                   'relationship were not supplied.'},
                       {'id': 'c242-onboarding-surveys',
                        'label': 'Student onboarding survey records',
                        'source': 'student_onboarding_survey',
                        'mode': 'all'},
                       {'id': 'c242-course-surveys',
                        'label': 'End-of-course survey records',
                        'source': 'end_course_survey',
                        'mode': 'all'}]},
 '2.4.3': {'sources': ['survey_management',
                       'survey_tracking',
                       'employee',
                       'staff_onboarding_survey',
                       'staff_survey',
                       'exit_interview_survey'],
           'metrics': [{'id': 'c243-surveys',
                        'label': 'Staff satisfaction survey instruments',
                        'source': 'survey_management',
                        'mode': 'conditions',
                        'conditions': [{'field': ['survey_type', 'type', 'survey_name'],
                                        'op': 'contains',
                                        'value': 'staff'}]},
                       {'id': 'c243-responses',
                        'label': 'Staff satisfaction responses',
                        'source': 'survey_tracking',
                        'mode': 'conditions',
                        'conditions': [{'field': ['respondent_type', 'survey_type', 'type'],
                                        'op': 'contains',
                                        'value': 'staff'}]},
                       {'id': 'c243-completed',
                        'label': 'Completed staff survey responses',
                        'source': 'survey_tracking',
                        'mode': 'conditions',
                        'conditions': [{'field': ['respondent_type', 'survey_type', 'type'],
                                        'op': 'contains',
                                        'value': 'staff'},
                                       {'field': ['status'],
                                        'op': 'in',
                                        'values': ['Completed', 'Submitted']}]},
                       {'id': 'c243-rating',
                        'label': 'Average staff satisfaction score',
                        'source': 'survey_tracking',
                        'mode': 'average_fields',
                        'fields': [['rating', 'score']],
                        'conditions': [{'field': ['respondent_type', 'survey_type', 'type'],
                                        'op': 'contains',
                                        'value': 'staff'}],
                        'unit': 'rating'},
                       {'id': 'c243-active-staff',
                        'label': 'Active staff population',
                        'source': 'employee',
                        'mode': 'equals',
                        'field': ['status'],
                        'value': 'Active'},
                       {'id': 'c243-coverage',
                        'label': 'Staff survey coverage rate',
                        'source': 'survey_tracking',
                        'mode': 'unsupported',
                        'message': 'The approved survey-cycle denominator and respondent matching '
                                   'rules were not supplied.'},
                       {'id': 'c243-onboarding-surveys',
                        'label': 'Staff onboarding survey records',
                        'source': 'staff_onboarding_survey',
                        'mode': 'all'},
                       {'id': 'c243-staff-surveys',
                        'label': 'Staff survey records',
                        'source': 'staff_survey',
                        'mode': 'all'},
                       {'id': 'c243-exit-surveys',
                        'label': 'Exit interview survey records',
                        'source': 'exit_interview_survey',
                        'mode': 'all'}]}}

QUESTION_REGISTRY = {'2.1.1': [{'id': 'q211-1', 'question': 'How many employees are active?', 'metric_id': 'c211-active-employees'},
           {'id': 'q211-2', 'question': 'How many job requisitions are open?', 'metric_id': 'c211-open-requisitions'},
           {'id': 'q211-3',
            'question': 'How many applicants are selected or accepted?',
            'metric_id': 'c211-selected-applicants'},
           {'id': 'q211-4',
            'question': 'How many employee onboardings are completed?',
            'metric_id': 'c211-completed-onboardings'}],
 '2.1.2': [{'id': 'q212-1',
            'question': 'How many training events are completed?',
            'metric_id': 'c212-completed-events'},
           {'id': 'q212-2',
            'question': 'How many training needs analyses have been reviewed?',
            'metric_id': 'c212-approved-tna'},
           {'id': 'q212-3',
            'question': 'What is the average training feedback rating?',
            'metric_id': 'c212-feedback-rating'},
           {'id': 'q212-4',
            'question': 'How many training results are completed or passed?',
            'metric_id': 'c212-completed-results'}],
 '2.2.1': [{'id': 'q221-1', 'question': 'How many stakeholders are recorded?', 'metric_id': 'c221-stakeholders'},
           {'id': 'q221-2',
            'question': 'How many communication materials are approved?',
            'metric_id': 'c221-approved-materials'},
           {'id': 'q221-3',
            'question': 'How many communication approvals are pending?',
            'metric_id': 'c221-pending-materials'},
           {'id': 'q221-4',
            'question': 'How many Essential Information records are overdue for review?',
            'metric_id': 'c221-overdue-info-review'}],
 '2.3.1': [{'id': 'q231-1',
            'question': 'How many controlled documents are current or approved?',
            'metric_id': 'c231-current-documents'},
           {'id': 'q231-2', 'question': 'How many document reviews are overdue?', 'metric_id': 'c231-overdue-reviews'},
           {'id': 'q231-3',
            'question': 'How many Quality Performance Outcomes are recorded?',
            'metric_id': 'c231-performance-outcomes'},
           {'id': 'q231-4',
            'question': 'How many data-related Quality Actions are in scope?',
            'metric_id': 'c231-quality-actions'}],
 '2.3.2': [{'id': 'q232-1',
            'question': 'How many knowledge documents are approved or current?',
            'metric_id': 'c232-approved'},
           {'id': 'q232-2', 'question': 'How many documents are obsolete or archived?', 'metric_id': 'c232-obsolete'},
           {'id': 'q232-3',
            'question': 'How many knowledge documents are overdue for review?',
            'metric_id': 'c232-overdue'},
           {'id': 'q232-4',
            'question': 'How many knowledge-improvement Quality Actions are in scope?',
            'metric_id': 'c232-actions'}],
 '2.4.1': [{'id': 'q241-1', 'question': 'How many feedback tickets are open?', 'metric_id': 'c241-open-tickets'},
           {'id': 'q241-2',
            'question': 'How many feedback tickets are closed or resolved?',
            'metric_id': 'c241-closed-tickets'},
           {'id': 'q241-3', 'question': 'How many feedback tickets failed SLA?', 'metric_id': 'c241-sla-failed'},
           {'id': 'q241-4',
            'question': 'How many feedback-related Quality Actions are recorded?',
            'metric_id': 'c241-quality-actions'}],
 '2.4.2': [{'id': 'q242-1',
            'question': 'How many student satisfaction responses are recorded?',
            'metric_id': 'c242-responses'},
           {'id': 'q242-2', 'question': 'How many student responses are completed?', 'metric_id': 'c242-completed'},
           {'id': 'q242-3', 'question': 'What is the average student satisfaction score?', 'metric_id': 'c242-rating'}],
 '2.4.3': [{'id': 'q243-1',
            'question': 'How many staff satisfaction responses are recorded?',
            'metric_id': 'c243-responses'},
           {'id': 'q243-2', 'question': 'How many staff responses are completed?', 'metric_id': 'c243-completed'},
           {'id': 'q243-3', 'question': 'What is the average staff satisfaction score?', 'metric_id': 'c243-rating'}]}

EXCEPTION_METRIC_IDS = ['c211-open-requisitions',
 'c211-competency-threshold',
 'c212-training-coverage',
 'c221-pending-materials',
 'c221-overdue-info-review',
 'c231-overdue-reviews',
 'c231-data-quality',
 'c232-obsolete',
 'c232-overdue',
 'c232-disposal',
 'c241-open-tickets',
 'c241-sla-failed',
 'c241-priority-matrix',
 'c242-coverage',
 'c243-coverage']

STANDARD_FIELDS = [
    "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"
]

def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()

def lower_text(value):
    return clean_text(value).lower()

def is_truthy(value):
    if value in [None, "", 0, "0", False]:
        return False
    if lower_text(value) in ["false", "no", "unchecked", "none", "null"]:
        return False
    return True

def to_number(value):
    try:
        if value in [None, ""]:
            return None
        return float(value)
    except Exception:
        return None

def is_permission_error(error):
    text = lower_text(error)
    return (
        "permission" in text
        or "not permitted" in text
        or "not allowed" in text
    )

def resolve_source(alias):
    candidates = SOURCE_CANDIDATES.get(alias) or []
    attempts = []

    for candidate_index in range(len(candidates)):
        doctype = candidates[candidate_index]
        attempt = {
            "doctype": doctype,
            "status": "checking",
            "stage": "metadata",
            "message": ""
        }

        try:
            frappe.get_meta(doctype)
            attempt["metadata"] = "available"
        except Exception as error:
            attempt["status"] = "unavailable"
            attempt["message"] = clean_text(error)
            attempts.append(attempt)
            continue

        try:
            # A permission-aware get_list is the runtime source probe. If a
            # candidate is stale or its table is unavailable, continue to the
            # next approved candidate instead of stopping the whole section.
            rows = frappe.get_list(
                doctype,
                fields=["name"],
                limit_start=0,
                limit_page_length=row_limit,
                order_by="modified desc"
            ) or []
            attempt["stage"] = "list"
            attempt["status"] = "available"
            attempt["message"] = "Readable by the signed-in user."
            attempts.append(attempt)
            return {
                "key": alias,
                "doctype": doctype,
                "candidates": candidates,
                "status": "available",
                "count": len(rows),
                "truncated": len(rows) >= row_limit,
                "probe": "frappe.get_list",
                "fallback_used": candidate_index > 0,
                "resolution_attempts": attempts
            }
        except Exception as error:
            message = clean_text(error)
            attempt["stage"] = "list"
            attempt["status"] = "permission_denied" if is_permission_error(error) else "unavailable"
            attempt["message"] = message
            attempts.append(attempt)
            if is_permission_error(error):
                return {
                    "key": alias,
                    "doctype": doctype,
                    "candidates": candidates,
                    "status": "permission_denied",
                    "count": 0,
                    "message": message,
                    "probe": "frappe.get_list",
                    "fallback_used": False,
                    "resolution_attempts": attempts
                }
            continue

    return {
        "key": alias,
        "doctype": None,
        "candidates": candidates,
        "status": "unavailable",
        "count": 0,
        "message": "No approved candidate DocType could be resolved. Open Source Mapping Report for the candidate-level errors.",
        "metadata_errors": attempts,
        "resolution_attempts": attempts,
        "fallback_used": False
    }
def get_meta(doctype):
    try:
        return frappe.get_meta(doctype)
    except Exception:
        return None

def field_exists(meta, fieldname):
    if not fieldname:
        return False
    if fieldname in STANDARD_FIELDS:
        return True
    try:
        for meta_field in meta.fields or []:
            if meta_field.fieldname == fieldname:
                return True
    except Exception:
        pass
    try:
        return bool(meta.has_field(fieldname))
    except Exception:
        return False

def resolve_field(doctype, candidates):
    meta = get_meta(doctype)
    if not meta:
        return ""
    for fieldname in candidates or []:
        if field_exists(meta, fieldname):
            return fieldname
    return ""

def resolve_field_groups(doctype, groups):
    resolved = []
    missing = []
    for candidates in groups or []:
        fieldname = resolve_field(doctype, candidates)
        if fieldname:
            resolved.append(fieldname)
        else:
            missing.append(candidates)
    return resolved, missing

def applied_filters(doctype):
    meta = get_meta(doctype)
    output = {}
    if not meta:
        return output
    for filter_key in FILTER_FIELD_CANDIDATES:
        requested = filters.get(filter_key)
        if requested in [None, "", "All", "all"]:
            continue
        for candidate in FILTER_FIELD_CANDIDATES.get(filter_key) or []:
            if field_exists(meta, candidate):
                output[candidate] = requested
                break
    return output

def safe_fields(doctype, fields):
    meta = get_meta(doctype)
    output = []
    if not meta:
        return output
    for fieldname in fields:
        if fieldname not in output and field_exists(meta, fieldname):
            output.append(fieldname)
    if "name" not in output:
        output.insert(0, "name")
    return output

def fetch_rows(source, requested_fields=None):
    doctype = source.get("doctype")
    if source.get("status") != "available" or not doctype:
        return []
    fields_to_fetch = safe_fields(doctype, ["name"] + (requested_fields or []))
    try:
        rows = frappe.get_list(
            doctype,
            fields=fields_to_fetch,
            filters=applied_filters(doctype),
            limit_page_length=row_limit + 1,
            order_by="modified desc"
        ) or []
        truncated = len(rows) > row_limit
        if truncated:
            rows = rows[:row_limit]
        source["truncated"] = truncated
        source["count"] = len(rows)
        source.pop("fetch_error", None)
        source.pop("fetch_status", None)
        return rows
    except Exception as error:
        source["fetch_error"] = clean_text(error)
        source["fetch_status"] = "permission_denied" if is_permission_error(error) else "query_error"
        return []


def compare(row, fieldname, op, expected=None, values=None, days=None):
    value = row.get(fieldname) if fieldname else None
    if op == "truthy":
        return is_truthy(value)
    if op == "falsy":
        return not is_truthy(value)
    if op == "equals":
        return lower_text(value) == lower_text(expected)
    if op == "not_equals":
        return lower_text(value) != lower_text(expected)
    if op == "in":
        allowed = [lower_text(item) for item in (values or [])]
        return lower_text(value) in allowed
    if op == "not_in":
        blocked = [lower_text(item) for item in (values or [])]
        return lower_text(value) not in blocked
    if op == "contains":
        return lower_text(expected) in lower_text(value)
    if op in ["gt", "gte", "lt", "lte"]:
        left = to_number(value)
        right = to_number(expected)
        if left is None or right is None:
            return False
        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        return left <= right
    if op == "date_next_days":
        if not value:
            return False
        try:
            date_value = frappe.utils.getdate(value)
            today = frappe.utils.getdate(frappe.utils.today())
            end_date = frappe.utils.getdate(
                frappe.utils.add_days(today, int(days or 0))
            )
            return date_value >= today and date_value <= end_date
        except Exception:
            return False
    if op == "date_before_today":
        if not value:
            return False
        try:
            return frappe.utils.getdate(value) < frappe.utils.getdate(frappe.utils.today())
        except Exception:
            return False
    return False

def metric_required_fields(metric, doctype):
    fields = []
    missing = []

    if metric.get("field"):
        fieldname = resolve_field(doctype, metric.get("field"))
        if fieldname:
            fields.append(fieldname)
        else:
            missing.append(metric.get("field"))

    if metric.get("compare_field"):
        fieldname = resolve_field(doctype, metric.get("compare_field"))
        if fieldname:
            fields.append(fieldname)
        else:
            missing.append(metric.get("compare_field"))

    field_group_result = resolve_field_groups(
        doctype,
        metric.get("fields") or []
    )
    resolved_groups = field_group_result[0]
    missing_groups = field_group_result[1]
    fields.extend(resolved_groups)
    missing.extend(missing_groups)

    resolved_conditions = []
    for condition in metric.get("conditions") or []:
        fieldname = resolve_field(doctype, condition.get("field") or [])
        if not fieldname:
            missing.append(condition.get("field") or [])
            continue
        item = {}
        for key in condition:
            item[key] = condition.get(key)
        item["resolved_field"] = fieldname
        resolved_conditions.append(item)
        if fieldname not in fields:
            fields.append(fieldname)

    return fields, missing, resolved_conditions

def row_matches(row, metric, resolved_fields, resolved_conditions):
    mode = metric.get("mode")
    if mode == "all":
        return True
    if mode in ["truthy", "falsy", "equals", "in", "not_in", "date_next_days", "date_before_today", "gt", "gte", "lt", "lte"]:
        if not resolved_fields:
            return False
        return compare(
            row,
            resolved_fields[0],
            mode,
            expected=metric.get("value"),
            values=metric.get("values"),
            days=metric.get("days")
        )
    if mode == "all_required":
        for fieldname in resolved_fields:
            if not is_truthy(row.get(fieldname)):
                return False
        return True
    if mode == "conditions":
        for condition in resolved_conditions:
            if not compare(
                row,
                condition.get("resolved_field"),
                condition.get("op"),
                expected=condition.get("value"),
                values=condition.get("values"),
                days=condition.get("days")
            ):
                return False
        return True
    if mode == "field_compare":
        if len(resolved_fields) < 2:
            return False
        left = to_number(row.get(resolved_fields[0]))
        right = to_number(row.get(resolved_fields[1]))
        if left is None or right is None:
            return False
        operator = metric.get("operator") or "gte"
        if operator == "gt":
            return left > right
        if operator == "gte":
            return left >= right
        if operator == "lt":
            return left < right
        if operator == "lte":
            return left <= right
        return left == right
    if mode in ["average_fields", "sum"]:
        for condition in resolved_conditions:
            if not compare(
                row,
                condition.get("resolved_field"),
                condition.get("op"),
                expected=condition.get("value"),
                values=condition.get("values"),
                days=condition.get("days")
            ):
                return False
        if mode == "sum":
            return bool(resolved_fields and to_number(row.get(resolved_fields[0])) is not None)
        for fieldname in resolved_fields:
            if to_number(row.get(fieldname)) is not None:
                return True
        return False
    return False

if subcriterion not in CONFIG:
    frappe.throw("Unsupported Criterion 2 subcriterion.")

resolved_sources = {}
for alias in CONFIG[subcriterion]["sources"]:
    resolved_sources[alias] = resolve_source(alias)

def evaluate_metric(metric, include_rows=False):
    if metric.get("mode") == "unsupported":
        return {
            "id": metric.get("id"),
            "label": metric.get("label"),
            "source": metric.get("source"),
            "doctype": None,
            "value": None,
            "status": "unsupported",
            "message": metric.get("message"),
            "rows": []
        }

    source = resolved_sources.get(metric.get("source")) or {}
    if source.get("status") != "available":
        return {
            "id": metric.get("id"),
            "label": metric.get("label"),
            "source": metric.get("source"),
            "doctype": source.get("doctype"),
            "value": None,
            "status": source.get("status") or "unavailable",
            "message": source.get("message"),
            "rows": []
        }

    doctype = source.get("doctype")
    required_field_result = metric_required_fields(metric, doctype)
    resolved_fields = required_field_result[0]
    missing = required_field_result[1]
    resolved_conditions = required_field_result[2]

    if metric.get("mode") != "all" and missing:
        return {
            "id": metric.get("id"),
            "label": metric.get("label"),
            "source": metric.get("source"),
            "doctype": doctype,
            "value": None,
            "status": "unsupported_field",
            "message": "Required field is not installed.",
            "missing_field_candidates": missing,
            "rows": []
        }

    requested = list(resolved_fields)
    for fieldname in SAFE_FIELDS.get(metric.get("source"), []):
        if include_rows and fieldname not in requested:
            requested.append(fieldname)

    rows = fetch_rows(source, requested)
    if source.get("fetch_error"):
        return {
            "id": metric.get("id"), "label": metric.get("label"),
            "source": metric.get("source"), "doctype": doctype,
            "value": None, "unit": metric.get("unit") or "records",
            "record_count": 0, "status": source.get("fetch_status") or "query_error",
            "message": source.get("fetch_error"), "resolved_fields": resolved_fields,
            "rows": [], "total": 0
        }
    matched = []
    for row in rows:
        if row_matches(row, metric, resolved_fields, resolved_conditions):
            matched.append(row)

    mode = metric.get("mode")
    value = len(matched)
    record_count = len(matched)

    if mode == "average_fields":
        numbers = []
        for row in matched:
            for fieldname in resolved_fields:
                number = to_number(row.get(fieldname))
                if number is not None:
                    numbers.append(number)
        value = round(sum(numbers) / len(numbers), 2) if numbers else 0
        record_count = len(matched)

    if mode == "sum":
        total = 0
        for row in matched:
            number = to_number(row.get(resolved_fields[0]))
            if number is not None:
                total = total + number
        value = round(total, 2)

    output_rows = []
    if include_rows:
        start = (page - 1) * page_size
        end = start + page_size
        safe_output_fields = safe_fields(
            doctype,
            SAFE_FIELDS.get(metric.get("source"), ["name"])
        )
        for row in matched[start:end]:
            item = {}
            for fieldname in safe_output_fields:
                item[fieldname] = row.get(fieldname)
            output_rows.append(item)

    return {
        "id": metric.get("id"),
        "label": metric.get("label"),
        "source": metric.get("source"),
        "doctype": doctype,
        "value": value,
        "unit": metric.get("unit") or "records",
        "record_count": record_count,
        "status": "available",
        "resolved_fields": resolved_fields,
        "rows": output_rows,
        "total": len(matched)
    }

metrics = []
for configured_metric in CONFIG[subcriterion]["metrics"]:
    metrics.append(evaluate_metric(configured_metric, False))

questions = []
for question in QUESTION_REGISTRY.get(subcriterion) or []:
    selected_metric = None
    for metric in metrics:
        if metric.get("id") == question.get("metric_id"):
            selected_metric = metric
            break

    if selected_metric and selected_metric.get("status") == "available":
        unit = selected_metric.get("unit") or "records"
        if unit == "rating":
            answer = (
                str(selected_metric.get("value"))
                + " is the live average rating from "
                + str(selected_metric.get("record_count") or 0)
                + " matching record(s)."
            )
        elif unit == "SGD":
            answer = "SGD " + str(selected_metric.get("value")) + " matches the current filters."
        elif unit == "percent":
            answer = str(selected_metric.get("value")) + "% matches the current filters."
        else:
            answer = str(selected_metric.get("value") or 0) + " record(s) match the current filters."
        status = "available"
        confidence = "Live"
    else:
        answer = "Unavailable: " + clean_text(
            (selected_metric or {}).get("message")
            or (selected_metric or {}).get("status")
            or "required source or field is unavailable"
        )
        status = (selected_metric or {}).get("status") or "unavailable"
        confidence = "Unavailable"

    questions.append({
        "id": question.get("id"),
        "criterion": subcriterion,
        "question": question.get("question"),
        "answer": answer,
        "metric_id": question.get("metric_id"),
        "status": status,
        "confidence": confidence,
        "doctype": (selected_metric or {}).get("doctype")
    })

sources = []
for alias in CONFIG[subcriterion]["sources"]:
    sources.append(resolved_sources.get(alias))

data_quality = []
for source in sources:
    if source.get("status") != "available":
        data_quality.append({
            "criterion": subcriterion,
            "check": "Source availability",
            "source": source.get("doctype") or " / ".join(source.get("candidates") or []),
            "status": source.get("status"),
            "detail": source.get("message") or "Source is unavailable."
        })

for metric in metrics:
    if metric.get("status") != "available":
        data_quality.append({
            "criterion": subcriterion,
            "check": metric.get("label"),
            "source": metric.get("doctype") or metric.get("source"),
            "status": metric.get("status"),
            "detail": metric.get("message") or "Metric is unavailable."
        })

exceptions = []
for metric in metrics:
    if metric.get("id") in EXCEPTION_METRIC_IDS:
        exceptions.append(metric)

available_sources = 0
for source in sources:
    if source.get("status") == "available":
        available_sources = available_sources + 1

available_metrics = 0
for metric in metrics:
    if metric.get("status") == "available":
        available_metrics = available_metrics + 1

def standardise_response_contract(result, criterion_name, api_method, action_name, subcriterion_name, row_limit_value):
    """Normalise every Criterion API to the shared frontend contract."""
    if not isinstance(result, dict):
        result = {}

    result["ok"] = bool(result.get("ok", True))

    meta = result.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    meta["api_method"] = api_method
    meta["criterion"] = criterion_name
    meta["contract_version"] = "2.1.0"
    meta["action"] = action_name
    meta["subcriterion"] = subcriterion_name
    meta["row_limit"] = row_limit_value
    result["meta"] = meta

    filter_values = result.get("filters")
    if not isinstance(filter_values, dict):
        filter_values = {}
    result["filters"] = filter_values

    array_keys = [
        "resolved_filters", "unresolved_filters", "sources", "source_mapping",
        "metrics", "supporting_metrics", "questions", "requirements",
        "exceptions", "evidence_gaps", "data_quality", "warnings"
    ]
    for key in array_keys:
        value = result.get(key)
        if not isinstance(value, list):
            result[key] = []

    if not result.get("requirements"):
        requirement_evidence = result.get("requirement_evidence")
        if isinstance(requirement_evidence, list):
            result["requirements"] = requirement_evidence

    if not result.get("supporting_metrics"):
        supporting = []
        for metric in result.get("metrics") or []:
            if isinstance(metric, dict) and metric.get("category") == "supporting":
                supporting.append(metric)
        result["supporting_metrics"] = supporting

    if not result.get("source_mapping"):
        mappings = []
        for source in result.get("sources") or []:
            if not isinstance(source, dict):
                continue
            display_name = (
                source.get("display_doctype") or source.get("display_name")
                or source.get("doctype") or source.get("key") or ""
            )
            mappings.append({
                "key": source.get("key"),
                "doctype": source.get("doctype"),
                "display_doctype": display_name,
                "status": source.get("status") or "unavailable",
                "count": source.get("count"),
                "count_is_sample": bool(source.get("count_is_sample")),
                "truncated": bool(source.get("truncated")),
                "candidates": source.get("candidates") or [],
                "resolution_attempts": source.get("resolution_attempts") or []
            })
        result["source_mapping"] = mappings

    metric_lookup = {}
    for metric in result.get("metrics") or []:
        if isinstance(metric, dict) and metric.get("id"):
            metric_lookup[metric.get("id")] = metric

    normalised_questions = []
    for question in result.get("questions") or []:
        if not isinstance(question, dict):
            continue
        primary_metric = {}
        primary_metric_id = question.get("metric_id")
        if not primary_metric_id:
            metric_ids = question.get("metric_ids") or []
            if metric_ids:
                primary_metric_id = metric_ids[0]
        if primary_metric_id:
            primary_metric = metric_lookup.get(primary_metric_id) or {}
        if question.get("metric_id") is None:
            question["metric_id"] = primary_metric_id
        if question.get("source") is None:
            question["source"] = primary_metric.get("source")
        if question.get("doctype") is None:
            question["doctype"] = primary_metric.get("doctype")
        if not isinstance(question.get("resolved_fields"), list):
            question["resolved_fields"] = primary_metric.get("resolved_fields") or []
        if question.get("record_count") is None:
            question["record_count"] = primary_metric.get("record_count")
        if question.get("unit") is None:
            question["unit"] = primary_metric.get("unit")
        if not question.get("status"):
            question["status"] = primary_metric.get("status") or "unsupported"
        if not question.get("confidence"):
            if question.get("status") == "available":
                question["confidence"] = "Live"
            elif question.get("status") in ["partial", "partial_truncated"]:
                question["confidence"] = "Partial"
            else:
                question["confidence"] = "Unavailable"
        if not question.get("applicable_population"):
            question["applicable_population"] = primary_metric.get("applicable_population") or "Records within the applied filters."
        if not question.get("reporting_period"):
            question["reporting_period"] = primary_metric.get("reporting_period") or "Applied dashboard period, subject to source-field support."
        if not question.get("calculation_note"):
            question["calculation_note"] = primary_metric.get("calculation_note") or primary_metric.get("label") or "Configured management-answer rule."
        normalised_questions.append(question)
    result["questions"] = normalised_questions

    sources = result.get("sources") or []
    metrics = result.get("metrics") or []
    questions = result.get("questions") or []

    source_available = 0
    source_issues = 0
    source_truncated = 0
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("status") == "available":
            source_available = source_available + 1
        else:
            source_issues = source_issues + 1
        if source.get("truncated"):
            source_truncated = source_truncated + 1

    metric_available = 0
    metric_partial = 0
    metric_issues = 0
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        status = metric.get("status")
        if status == "available":
            metric_available = metric_available + 1
        elif status in ["partial", "partial_truncated"]:
            metric_partial = metric_partial + 1
        else:
            metric_issues = metric_issues + 1

    question_available = 0
    question_partial = 0
    question_issues = 0
    for question in questions:
        if not isinstance(question, dict):
            continue
        status = question.get("status")
        if status == "available":
            question_available = question_available + 1
        elif status in ["partial", "partial_truncated"]:
            question_partial = question_partial + 1
        else:
            question_issues = question_issues + 1

    result["source_summary"] = {
        "total": len(sources), "available": source_available,
        "issues": source_issues, "truncated": source_truncated
    }
    result["metric_summary"] = {
        "total": len(metrics), "available": metric_available,
        "partial": metric_partial, "issues": metric_issues
    }
    result["question_summary"] = {
        "total": len(questions), "available": question_available,
        "partial": question_partial, "issues": question_issues
    }

    readiness = result.get("readiness")
    if not isinstance(readiness, dict):
        readiness = {}
    readiness["status"] = "active_with_limitations" if (
        source_issues or source_truncated or metric_partial or metric_issues
        or question_partial or question_issues or result.get("data_quality")
        or result.get("evidence_gaps")
    ) else "active"
    readiness["source_total"] = len(sources)
    readiness["source_available"] = source_available
    readiness["source_truncated"] = source_truncated
    readiness["metric_total"] = len(metrics)
    readiness["metric_available"] = metric_available
    readiness["metric_partial"] = metric_partial
    readiness["question_total"] = len(questions)
    readiness["question_available"] = question_available
    readiness["question_partial"] = question_partial
    readiness["items_need_review"] = len(result.get("data_quality") or []) + len(result.get("evidence_gaps") or [])
    result["readiness"] = readiness

    data = result.get("data")
    if not isinstance(data, dict):
        data = {}
    mirror_keys = [
        "sources", "source_mapping", "metrics", "supporting_metrics", "questions",
        "requirements", "exceptions", "evidence_gaps", "data_quality", "readiness"
    ]
    for key in mirror_keys:
        data[key] = result.get(key)
    result["data"] = data

    return result

result = {
    "ok": True,
    "meta": {
        "api_method": "ucc_analytics_criterion_2",
        "platform_version": "1.9.5",
        "status": "live_foundation",
        "generated_at": frappe.utils.now(),
        "action": action,
        "subcriterion": subcriterion,
        "row_limit": row_limit
    },
    "policy": POLICY_REGISTRY.get(subcriterion),
    "filters": filters,
    "sources": sources,
    "metrics": metrics,
    "questions": questions,
    "exceptions": exceptions,
    "data_quality": data_quality,
    "source_summary": {
        "total": len(sources),
        "available": available_sources,
        "issues": len(sources) - available_sources
    },
    "metric_summary": {
        "total": len(metrics),
        "available": available_metrics,
        "issues": len(metrics) - available_metrics
    },
    "data": {
        "sources": sources,
        "metrics": metrics,
        "questions": questions,
        "exceptions": exceptions,
        "data_quality": data_quality
    },
    "warnings": ['Criterion 2 spans HR, communication, information, knowledge and feedback sources.',
 'Custom DocTypes are resolved only from approved policy-referenced candidates.',
 'Survey coverage and HR competency metrics remain unsupported until denominator and child-table '
 'rules are supplied.']
}

result = standardise_response_contract(result, "Criterion 2", "ucc_analytics_criterion_2", action, subcriterion, row_limit)

if action == "policy_registry":
    result["registry"] = POLICY_REGISTRY

if action == "source_status":
    result["source_status"] = sources

if action == "requirement_registry":
    result["registry"] = result.get("requirements") or []

if action == "question_registry":
    result["registry"] = QUESTION_REGISTRY

if action == "drilldown":
    selected_config = None
    for configured_metric in CONFIG[subcriterion]["metrics"]:
        if configured_metric.get("id") == metric_id:
            selected_config = configured_metric
            break
    if not selected_config:
        frappe.throw("Unknown Criterion 2 metric.")
    result["drilldown"] = evaluate_metric(selected_config, True)

result = standardise_response_contract(result, "Criterion 2", "ucc_analytics_criterion_2", action, subcriterion, row_limit)

frappe.response["message"] = result
