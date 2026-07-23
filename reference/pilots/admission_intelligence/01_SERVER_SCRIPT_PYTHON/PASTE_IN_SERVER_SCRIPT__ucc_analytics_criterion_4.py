"""
UCC Intelligence Platform Server Script

Visible name:
    UCC Analytics - Criterion 4

Script type:
    API

API method:
    ucc_analytics_criterion_4

Purpose:
    Return permission-aware, decision-useful analytics for EduTrust Criterion 4.

Current status:
    Revised Criterion 4 management-question catalogue. Supported calculations
    remain live. Partial, document-only and unsupported controls are reported
    explicitly and are never converted to a false zero or a compliance conclusion.

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
subcriterion = payload.get("subcriterion") or "4.1.1"
filters = payload.get("filters") or {}
if not isinstance(filters, dict):
    filters = {}
metric_id = payload.get("metric_id")
page = payload.get("page") or 1
page_size = payload.get("page_size") or 50
row_limit = payload.get("limit") or 2000

page = frappe.utils.cint(page)
if page < 1:
    page = 1

page_size = frappe.utils.cint(page_size)
if page_size < 1:
    page_size = 50
if page_size > 200:
    page_size = 200

row_limit = frappe.utils.cint(row_limit)
if row_limit < 1:
    row_limit = 2000
if row_limit > 5000:
    row_limit = 5000

ALLOWED_ACTIONS = [
    "summary", "source_status", "policy_registry", "requirement_registry",
    "question_registry", "drilldown"
]
if action not in ALLOWED_ACTIONS:
    frappe.throw("Unsupported Criterion 4 action.")

POLICY_REGISTRY = {'overview': {'title': 'Criterion 4 Overview',
              'policy': 'PPD-SSO-AD-4.1.1 to PPD-SSO-SS-4.6.1',
              'version': 'Current controlled versions'},
 '4.1.1': {'title': 'Pre-Course Counselling, Selection and Admissions', 'policy': 'PPD-SSO-AD-4.1.1', 'version': '2.2'},
 '4.2.1': {'title': 'Student Contract', 'policy': 'PPD-SSO-AD-4.2.1', 'version': '2.2'},
 '4.2.2': {'title': 'Fee Collection and Fee Protection Scheme', 'policy': 'PPD-SSO-AD-4.2.2', 'version': '2.3'},
 '4.3.1': {'title': 'Course Transfer, Deferment and Withdrawal', 'policy': 'PPD-SSO-SS-4.3.1', 'version': '2.2'},
 '4.4.1': {'title': 'Refund', 'policy': 'PPD-SSO-SS-4.4.1', 'version': '2.2'},
 '4.5.1': {'title': 'Student Support Services', 'policy': 'PPD-SSO-SS-4.5.1', 'version': '2.3'},
 '4.6.1': {'title': 'Student Conduct and Attendance', 'policy': 'PPD-SSO-SS-4.6.1', 'version': '2.2'}}

SOURCE_CANDIDATES = {'applicant': ['Student Applicant'],
 'admission': ['Student Admission UCC'],
 'counselling': ['Pre Course Counselling Declaration'],
 'adjustments': ['Student Log'],
 'contract': ['Student Admission UCC'],
 'invoice': ['Sales Invoice'],
 'payment': ['Payment Entry'],
 'fps': ['FPS Record'],
 'student_log': ['Student Log'],
 'academic_support': ['Intervention Issue Academic Support'],
 'wellness_support': ['Intervention Issue Wellness Services'],
 'integrity_support': ['Intervention Issue Academic Integrity'],
 'support_strategy': ['Student Support Service Strategy Insights'],
 'support_register': ['Student Support Service Register'],
 'attendance': ['Student Attendance'],
 'warning': ['Dismissal Letters due to Attendance Requirements'],
 'leave': ['Student Leave Application'],
 'management_review': ['Management Review'],
 'quality_action': ['Quality Action']}

SAFE_FIELDS = {'applicant': ['name',
               'first_name',
               'middle_name',
               'last_name',
               'student_name',
               'application_status',
               'program',
               'course',
               'course_applying_for',
               'intake',
               'academic_year',
               'application_date',
               'nationality',
               'country',
               'agent',
               'creation',
               'modified'],
 'admission': ['name',
               'student',
               'student_name',
               'student_applicant',
               'program',
               'course',
               'intake',
               'academic_year',
               'application_status',
               'conditional',
               'contract_url',
               'student_contract',
               'contract_sent_date',
               'contract_signed_by_student_date',
               'student_signed_date',
               'pre_course_counseling',
               'docstatus',
               'sales_invoice',
               'creation',
               'modified'],
 'counselling': ['name',
                 'student',
                 'student_name',
                 'student_applicant',
                 'program',
                 'course',
                 'intake',
                 'academic_year',
                 'declaration_check',
                 'pdpa_check',
                 'name_of_staff',
                 'date',
                 'creation',
                 'modified'],
 'adjustments': ['name',
                 'student',
                 'student_name',
                 'program',
                 'course',
                 'academic_year',
                 'status',
                 'workflow_state',
                 'creation',
                 'modified'],
 'contract': ['name',
              'student',
              'student_name',
              'student_applicant',
              'program',
              'course',
              'intake',
              'academic_year',
              'application_status',
              'conditional',
              'contract_url',
              'student_contract',
              'contract_sent_date',
              'contract_signed_by_student_date',
              'student_signed_date',
              'sales_invoice',
              'creation',
              'modified'],
 'invoice': ['name',
             'customer',
             'customer_name',
             'student',
             'student_name',
             'posting_date',
             'due_date',
             'status',
             'grand_total',
             'outstanding_amount',
             'currency',
             'docstatus',
             'creation',
             'modified'],
 'payment': ['name',
             'party_type',
             'party',
             'party_name',
             'payment_type',
             'posting_date',
             'paid_amount',
             'received_amount',
             'reference_no',
             'remarks',
             'docstatus',
             'creation',
             'modified'],
 'fps': ['name',
         'student',
         'student_name',
         'fps_status',
         'status',
         'posting_date',
         'declaration_date',
         'payment_date',
         'coverage_start_date',
         'amount',
         'insured_amount',
         'creation',
         'modified'],
 'student_log': ['name',
                 'student',
                 'student_name',
                 'program',
                 'course',
                 'academic_year',
                 'status',
                 'workflow_state',
                 'subject',
                 'description',
                 'creation',
                 'modified'],
 'academic_support': ['name', 'student', 'student_name', 'status', 'workflow_state', 'owner', 'creation', 'modified'],
 'wellness_support': ['name', 'student', 'student_name', 'status', 'workflow_state', 'owner', 'creation', 'modified'],
 'integrity_support': ['name', 'student', 'student_name', 'status', 'workflow_state', 'owner', 'creation', 'modified'],
 'support_strategy': ['name',
                      'title',
                      'service_category',
                      'delivery_mode',
                      'activity_nature',
                      'operational_status',
                      'status',
                      'review_frequency',
                      'planned_date',
                      'actual_date',
                      'owner',
                      'creation',
                      'modified'],
 'support_register': ['name',
                      'service_name',
                      'service_type',
                      'service_category',
                      'delivery_mode',
                      'responsible_party',
                      'implementation_status',
                      'status',
                      'review_date',
                      'creation',
                      'modified'],
 'attendance': ['name',
                'student',
                'student_name',
                'student_group',
                'course_schedule',
                'attendance_date',
                'date',
                'status',
                'program',
                'course',
                'academic_year',
                'creation',
                'modified'],
 'warning': ['name',
             'student',
             'student_name',
             'warning_type',
             'status',
             'approval_status',
             'approved_by',
             'issue_date',
             'creation',
             'modified'],
 'leave': ['name',
           'student',
           'student_name',
           'from_date',
           'to_date',
           'leave_type',
           'reason',
           'status',
           'workflow_state',
           'approval_status',
           'creation',
           'modified'],
 'management_review': ['name',
                       'review_date',
                       'review_period',
                       'review_type',
                       'review_status',
                       'status',
                       'chairperson',
                       'next_review_date',
                       'creation',
                       'modified'],
 'quality_action': ['name',
                    'goal',
                    'review',
                    'procedure',
                    'status',
                    'custom_status_updates',
                    'date',
                    'custom_proposed_date',
                    'custom_completed_date',
                    'custom_priority_score',
                    'creation',
                    'modified']}

FILTER_FIELD_CANDIDATES = {'academic_year': ['academic_year'],
 'program': ['program', 'course', 'course_applying_for', 'course_type'],
 'intake': ['intake', 'student_admission', 'academic_term', 'intake_applying'],
 'status': ['status', 'workflow_state', 'application_status', 'review_status', 'fps_status'],
 'nationality': ['nationality', 'country'],
 'agent': ['agent', 'custom_agent', 'recruitment_agent'],
 'student': ['student', 'student_id', 'student_applicant']}

CLOSED_VALUES = ['Completed', 'Closed', 'Cancelled', 'Rejected', 'Inactive', 'Archived', 'Done']

CONFIG = {'overview': {'sources': ['counselling',
                          'admission',
                          'contract',
                          'invoice',
                          'payment',
                          'fps',
                          'adjustments',
                          'support_strategy',
                          'support_register',
                          'attendance',
                          'warning',
                          'leave'],
              'metrics': [{'id': 'o-counselling-unacknowledged',
                           'label': 'Counselling acknowledgements missing',
                           'source': 'counselling',
                           'mode': 'falsy',
                           'field': ['declaration_check']},
                          {'id': 'o-conditional-admissions',
                           'label': 'Conditional admissions recorded',
                           'source': 'admission',
                           'mode': 'truthy',
                           'field': ['conditional']},
                          {'id': 'o-contracts-pending',
                           'label': 'Sent contracts without student signature',
                           'source': 'contract',
                           'mode': 'conditions',
                           'conditions': [{'field': ['contract_sent_date'], 'op': 'truthy'},
                                          {'field': ['contract_signed_by_student_date', 'student_signed_date'],
                                           'op': 'falsy'}]},
                          {'id': 'o-overdue-invoices',
                           'label': 'Overdue invoices in readable Sales Invoice data',
                           'source': 'invoice',
                           'mode': 'in',
                           'field': ['status'],
                           'values': ['Overdue']},
                          {'id': 'o-movement-aged-open',
                        'label': 'Open movement requests older than 21 weekdays',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                          {'id': 'o-refund-aged-open',
                        'label': 'Refund requests older than 7 weekdays without approval',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                          {'id': 'o-attendance-risk-records',
                           'label': 'Attendance records marked absent or late',
                           'source': 'attendance',
                           'mode': 'contains_any',
                           'field': ['status'],
                           'values': ['Absent', 'Late']},
                          {'id': 'o-unresolved-support-controls',
                           'label': 'Unresolved student-support controls',
                           'source': 'support_strategy',
                           'mode': 'unsupported',
                           'message': 'Current verified fields do not provide a consistent pending, follow-up, closure '
                                      'and effectiveness rule across all student-support services.'}]},
 '4.1.1': {'sources': ['applicant', 'admission', 'counselling', 'adjustments', 'management_review', 'quality_action'],
           'metrics': [{'id': 'c411-applicants-total',
                        'label': 'No. of Student Applicants',
                        'source': 'applicant',
                        'mode': 'all'},
                       {'id': 'c411-shortlisted-approved',
                        'label': 'No. of Shortlisted',
                        'source': 'applicant',
                        'mode': 'equals',
                        'field': ['application_status'],
                        'value': 'Approved'},
                       {'id': 'c411-enrolled-admitted',
                        'label': 'No. of Enrolled Students',
                        'source': 'applicant',
                        'mode': 'equals',
                        'field': ['application_status'],
                        'value': 'Admitted'},
                       {'id': 'c411-success-rate',
                        'label': 'Success Rate',
                        'source': 'applicant',
                        'mode': 'ratio_status',
                        'field': ['application_status'],
                        'values': ['Admitted'],
                        'unit': 'percent'},
                       {'id': 'c411-counselling',
                        'label': 'Counselling declaration records',
                        'source': 'counselling',
                        'mode': 'all'},
                       {'id': 'c411-acknowledged',
                        'label': 'Counselling acknowledgements recorded',
                        'source': 'counselling',
                        'mode': 'truthy',
                        'field': ['declaration_check']},
                       {'id': 'c411-unacknowledged',
                        'label': 'Counselling acknowledgements missing',
                        'source': 'counselling',
                        'mode': 'falsy',
                        'field': ['declaration_check']},
                       {'id': 'c411-pdpa',
                        'label': 'PDPA consents recorded',
                        'source': 'counselling',
                        'mode': 'truthy',
                        'field': ['pdpa_check']},
                       {'id': 'c411-pdpa-missing',
                        'label': 'PDPA consents missing',
                        'source': 'counselling',
                        'mode': 'falsy',
                        'field': ['pdpa_check']},
                       {'id': 'c411-staff-complete',
                        'label': 'Counselling records with staff representative and date',
                        'source': 'counselling',
                        'mode': 'all_required',
                        'fields': [['name_of_staff'], ['date']]},
                       {'id': 'c411-approved-status',
                        'label': 'Applicant records with approved, admitted or enrolled status',
                        'source': 'applicant',
                        'mode': 'contains_any',
                        'field': ['application_status'],
                        'values': ['Approved', 'Admitted', 'Enrolled']},
                       {'id': 'c411-conditional',
                        'label': 'Conditional admissions recorded',
                        'source': 'admission',
                        'mode': 'truthy',
                        'field': ['conditional']},
                       {'id': 'c411-late',
                        'label': 'Late-admission request rows',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c411-counsellor-readiness',
                        'label': 'Counsellor training and review readiness',
                        'source': 'counselling',
                        'mode': 'unsupported',
                        'message': 'No approved counsellor training, refresher and performance-review source is mapped '
                                   'to this API.'},
                       {'id': 'c411-admission-compliance',
                        'label': 'Admission requirement compliance',
                        'source': 'applicant',
                        'mode': 'unsupported',
                        'message': 'Approved entry requirements, qualification evidence, document-authenticity '
                                   'verification and approval evidence are not available as structured fields.'},
                       {'id': 'c411-conditional-control',
                        'label': 'Conditional-admission control completeness',
                        'source': 'admission',
                        'mode': 'unsupported',
                        'message': 'Condition details, deadline, owner, reminders, evidence and final resolution are '
                                   'not available as verified fields.'},
                       {'id': 'c411-late-joining-control',
                        'label': 'Late-joining approval and integration compliance',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The current mapped fields do not calculate missed-hours limits, capability '
                                   'assessment, approval evidence, orientation or subsequent attendance.'},
                       {'id': 'c411-review-effectiveness',
                        'label': 'Counselling and admissions APSR effectiveness',
                        'source': 'management_review',
                        'mode': 'unsupported',
                        'message': 'Current review fields do not identify Criterion 4.1.1 scope, findings, linked '
                                   'actions and effectiveness verification.'}]},
 '4.2.1': {'sources': ['contract', 'invoice', 'payment', 'management_review', 'quality_action'],
           'metrics': [{'id': 'c421-generated',
                        'label': 'Contracts generated',
                        'source': 'contract',
                        'mode': 'truthy',
                        'field': ['contract_url', 'student_contract']},
                       {'id': 'c421-student-signed',
                        'label': 'Contracts with student signature date',
                        'source': 'contract',
                        'mode': 'truthy',
                        'field': ['contract_signed_by_student_date', 'student_signed_date']},
                       {'id': 'c421-pending',
                        'label': 'Sent contracts without student signature',
                        'source': 'contract',
                        'mode': 'conditions',
                        'conditions': [{'field': ['contract_sent_date'], 'op': 'truthy'},
                                       {'field': ['contract_signed_by_student_date', 'student_signed_date'],
                                        'op': 'falsy'}]},
                       {'id': 'c421-invoiced',
                        'label': 'Admissions linked to a Sales Invoice',
                        'source': 'contract',
                        'mode': 'truthy',
                        'field': ['sales_invoice']},
                       {'id': 'c421-full-execution',
                        'label': 'Fully executed contracts before payment and commencement',
                        'source': 'contract',
                        'mode': 'unsupported',
                        'message': 'Verified UCC signature, guardian applicability, Form 12 acknowledgement, first '
                                   'course-fee payment and commencement timing are not mapped.'},
                       {'id': 'c421-amendment-control',
                        'label': 'Contract amendment and replacement control',
                        'source': 'contract',
                        'mode': 'unsupported',
                        'message': 'Replacement-contract, addendum, mutual acknowledgement and prior-contract '
                                   'termination links are not mapped.'},
                       {'id': 'c421-archive-review',
                        'label': 'Contract access, archive and review evidence',
                        'source': 'contract',
                        'mode': 'unsupported',
                        'message': 'Student copy, Student P-File retention, archive completeness and Criterion 4.2.1 '
                                   'APSR effectiveness are not available as structured fields.'}]},
 '4.2.2': {'sources': ['contract', 'invoice', 'payment', 'fps', 'management_review', 'quality_action'],
           'metrics': [{'id': 'c422-invoiced',
                        'label': 'Admissions linked to a Sales Invoice',
                        'source': 'contract',
                        'mode': 'truthy',
                        'field': ['sales_invoice']},
                       {'id': 'c422-incoming-payments',
                        'label': 'Submitted incoming Payment Entries, not yet scoped to student fees',
                        'source': 'payment',
                        'mode': 'conditions',
                        'conditions': [{'field': ['payment_type'], 'op': 'contains_any', 'values': ['Receive']},
                                       {'field': ['docstatus'], 'op': 'equals', 'value': 1}]},
                       {'id': 'c422-fps-processed',
                        'label': 'FPS records marked processed or approved, not reconciled',
                        'source': 'fps',
                        'mode': 'contains_any',
                        'field': ['fps_status', 'status'],
                        'values': ['Processed', 'Approved']},
                       {'id': 'c422-overdue-invoices',
                        'label': 'Overdue Sales Invoices, not yet scoped to student fees',
                        'source': 'invoice',
                        'mode': 'in',
                        'field': ['status'],
                        'values': ['Overdue']},
                       {'id': 'c422-fee-compliance',
                        'label': 'Fee category, timing and collection-cap compliance',
                        'source': 'invoice',
                        'mode': 'unsupported',
                        'message': 'Schedule B and C line items, executed-contract timing, instalment due dates and '
                                   'the applicable collection cap are not reconciled.'},
                       {'id': 'c422-payment-allocation',
                        'label': 'Student payment allocation and receipt accuracy',
                        'source': 'payment',
                        'mode': 'unsupported',
                        'message': 'The current mapping does not reliably link each Payment Entry to the applicable '
                                   'student, invoice, contract, fee category and official receipt.'},
                       {'id': 'c422-fps-reconciliation',
                        'label': 'Payment-to-FPS coverage reconciliation',
                        'source': 'fps',
                        'mode': 'unsupported',
                        'message': 'Payment amount, covered amount, coverage commencement, declaration period, Nil '
                                   'Declaration and MIL utilisation are not fully mapped.'},
                       {'id': 'c422-revenue-recognition',
                        'label': 'Accrual revenue-recognition compliance',
                        'source': 'invoice',
                        'mode': 'unsupported',
                        'message': 'No approved accounting-ledger and course-delivery allocation source is mapped to '
                                   'this API.'},
                       {'id': 'c422-review-effectiveness',
                        'label': 'Fee, FPS and revenue-control APSR effectiveness',
                        'source': 'management_review',
                        'mode': 'unsupported',
                        'message': 'Current review fields do not identify Criterion 4.2.2 scope, financial findings, '
                                   'linked actions and effectiveness verification.'}]},
 '4.3.1': {'sources': ['adjustments', 'contract', 'fps', 'management_review', 'quality_action'],
           'metrics': [{'id': 'c431-transfer',
                        'label': 'Course transfer request rows',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c431-defer',
                        'label': 'Course deferment request rows',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c431-withdraw',
                        'label': 'Course withdrawal request rows',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c431-open',
                        'label': 'Movement requests without approval date',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c431-aged-open',
                        'label': 'Open movement requests older than 21 weekdays',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c431-eligibility-control',
                        'label': 'Movement request completeness and eligibility',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'Type-specific eligibility, required evidence, outstanding payment and document '
                                   'checks are not available as a complete structured rule.'},
                       {'id': 'c431-downstream-control',
                        'label': 'Movement downstream action completion',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'New contract, FPS, Student Pass, timetable, refund and outcome-communication links '
                                   'are not mapped.'},
                       {'id': 'c431-weekly-review',
                        'label': 'Weekly review of open movement requests',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'No verified last-review date, next-review date, review owner and review outcome '
                                   'fields are mapped.'},
                       {'id': 'c431-review-effectiveness',
                        'label': 'Movement-management APSR effectiveness',
                        'source': 'management_review',
                        'mode': 'unsupported',
                        'message': 'Current review fields do not identify Criterion 4.3.1 scope, recurring delays, '
                                   'linked actions and effectiveness verification.'}]},
 '4.4.1': {'sources': ['adjustments', 'payment', 'contract', 'management_review', 'quality_action'],
           'metrics': [{'id': 'c441-requests',
                        'label': 'Refund request rows',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c441-open',
                        'label': 'Refund requests without approval date',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c441-approved',
                        'label': 'Refund requests with approval date',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c441-aged-open',
                        'label': 'Refund requests older than 7 weekdays without approval',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'The former adjustment child table is no longer an available backend source. Map the replacement Student Log fields before enabling this metric.'},
                       {'id': 'c441-refund-payments',
                        'label': 'Submitted Payment Entries containing refund remarks, not linked to requests',
                        'source': 'payment',
                        'mode': 'conditions',
                        'conditions': [{'field': ['remarks'], 'op': 'contains_any', 'values': ['Refund']},
                                       {'field': ['payment_type'], 'op': 'contains_any', 'values': ['Pay']},
                                       {'field': ['docstatus'], 'op': 'equals', 'value': 1}]},
                       {'id': 'c441-eligibility-control',
                        'label': 'Refund eligibility assessment compliance',
                        'source': 'adjustments',
                        'mode': 'unsupported',
                        'message': 'Verified-complete date, applicable eligibility condition, evidence and appeal '
                                   'outcome are not available as structured fields.'},
                       {'id': 'c441-calculation-control',
                        'label': 'Refund calculation and communication accuracy',
                        'source': 'payment',
                        'mode': 'unsupported',
                        'message': 'Eligible fee base, Schedule D percentage, deductions, calculated amount, approved '
                                   'amount and communicated amount are not mapped.'},
                       {'id': 'c441-timely-completion',
                        'label': 'Refund payment within seven working days from verified completeness',
                        'source': 'payment',
                        'mode': 'unsupported',
                        'message': 'The verified-complete date and request-to-payment linkage are not mapped; '
                                   'posting-date ageing is only an early-warning indicator.'},
                       {'id': 'c441-review-effectiveness',
                        'label': 'Refund APSR effectiveness',
                        'source': 'management_review',
                        'mode': 'unsupported',
                        'message': 'Current review fields do not identify Criterion 4.4.1 scope, fairness, calculation '
                                   'accuracy, timeliness or effectiveness verification.'}]},
 '4.5.1': {'sources': ['support_strategy',
                       'support_register',
                       'academic_support',
                       'wellness_support',
                       'integrity_support',
                       'student_log',
                       'management_review',
                       'quality_action'],
           'metrics': [{'id': 'c451-strategy-records',
                        'label': 'Student Support Service Strategy Insights records',
                        'source': 'support_strategy',
                        'mode': 'all'},
                       {'id': 'c451-register-records',
                        'label': 'Student Support Service Register records',
                        'source': 'support_register',
                        'mode': 'all'},
                       {'id': 'c451-academic-support',
                        'label': 'Academic-support intervention records',
                        'source': 'academic_support',
                        'mode': 'all'},
                       {'id': 'c451-wellness-support',
                        'label': 'Wellness-support intervention records',
                        'source': 'wellness_support',
                        'mode': 'all'},
                       {'id': 'c451-integrity-support',
                        'label': 'Academic-integrity intervention records',
                        'source': 'integrity_support',
                        'mode': 'all'},
                       {'id': 'c451-student-logs',
                        'label': 'Student Log records, not classified as support cases',
                        'source': 'student_log',
                        'mode': 'all'},
                       {'id': 'c451-service-coverage',
                        'label': 'Required service coverage and communication',
                        'source': 'support_register',
                        'mode': 'unsupported',
                        'message': 'The approved required-service denominator, current communication evidence and '
                                   'student-population coverage are not mapped.'},
                       {'id': 'c451-plan-delivery',
                        'label': 'Planned-versus-actual support initiative delivery',
                        'source': 'support_strategy',
                        'mode': 'unsupported',
                        'message': 'Verified planned initiative, due date, actual delivery, participation and '
                                   'applicable student-need fields are not mapped.'},
                       {'id': 'c451-case-control',
                        'label': 'Support case assignment, follow-up and closure compliance',
                        'source': 'student_log',
                        'mode': 'unsupported',
                        'message': 'A consistent need assessment, action plan, owner, milestone, follow-up, referral '
                                   'and closure schema is not mapped.'},
                       {'id': 'c451-outcome-effectiveness',
                        'label': 'Student-support outcome effectiveness',
                        'source': 'support_strategy',
                        'mode': 'unsupported',
                        'message': 'Outcome measures, stakeholder feedback, repeat-case analysis and verified '
                                   'effectiveness are not available as structured fields.'}]},
 '4.6.1': {'sources': ['attendance', 'student_log', 'warning', 'leave', 'management_review', 'quality_action'],
           'metrics': [{'id': 'c461-attendance', 'label': 'Attendance records', 'source': 'attendance', 'mode': 'all'},
                       {'id': 'c461-risk-records',
                        'label': 'Attendance records marked absent or late',
                        'source': 'attendance',
                        'mode': 'contains_any',
                        'field': ['status'],
                        'values': ['Absent', 'Late']},
                       {'id': 'c461-warning',
                        'label': 'Attendance warning or dismissal records',
                        'source': 'warning',
                        'mode': 'all'},
                       {'id': 'c461-leave',
                        'label': 'Student leave application records',
                        'source': 'leave',
                        'mode': 'all'},
                       {'id': 'c461-student-logs',
                        'label': 'Student Log records, not classified as conduct interventions',
                        'source': 'student_log',
                        'mode': 'all'},
                       {'id': 'c461-attendance-completeness',
                        'label': 'Attendance marking completeness by scheduled activity',
                        'source': 'attendance',
                        'mode': 'unsupported',
                        'message': 'No verified timetable or scheduled-learning-activity denominator and cross-mode '
                                   'attendance reconciliation are mapped.'},
                       {'id': 'c461-monthly-threshold',
                        'label': 'Student monthly attendance and punctuality threshold compliance',
                        'source': 'attendance',
                        'mode': 'unsupported',
                        'message': 'Scheduled hours, attended hours, Student Pass status and monthly repeated-lateness '
                                   'aggregation are not mapped.'},
                       {'id': 'c461-intervention-timeliness',
                        'label': 'Threshold-triggered intervention timeliness',
                        'source': 'student_log',
                        'mode': 'unsupported',
                        'message': 'Attendance threshold breach, initial contact, assessment, action plan, warning and '
                                   'escalation are not linked as structured stages.'},
                       {'id': 'c461-leave-validity',
                        'label': 'Leave evidence, approval and attendance integration compliance',
                        'source': 'leave',
                        'mode': 'unsupported',
                        'message': 'Evidence verification, approval date, five-working-day medical-certificate rule '
                                   'and attendance integration are not fully mapped.'},
                       {'id': 'c461-disciplinary-due-process',
                        'label': 'Formal misconduct due process and proportionality',
                        'source': 'student_log',
                        'mode': 'unsupported',
                        'message': 'Assessment, investigation, hearing, committee scoring, authorised outcome and '
                                   'appeal stages are not mapped as structured data.'},
                       {'id': 'c461-effectiveness-review',
                        'label': 'Conduct and attendance intervention effectiveness and APSR review',
                        'source': 'management_review',
                        'mode': 'unsupported',
                        'message': 'Intervention outcome, recurrence, closure evaluation, Criterion 4.6.1 APSR scope '
                                   'and linked action effectiveness are not mapped.'}]}}

REQUIREMENT_REGISTRY = [{'id': '4.1.1.1',
  'subcriterion': '4.1.1',
  'title': 'Train and monitor Course Counsellors and Recruitment Agents',
  'document_reference': 'PPD-SSO-AD-4.1.1 Counsellor Training and Oversight',
  'source_keys': [],
  'manual_gaps': ['initial training',
                  'annual refresher',
                  'biannual Course Counsellor review',
                  'annual Recruitment Agent review']},
 {'id': '4.1.1.2',
  'subcriterion': '4.1.1',
  'title': 'Provide relevant course information during pre-course counselling',
  'document_reference': 'PPD-SSO-AD-4.1.1 Pre-Course Information Delivery',
  'source_keys': ['counselling', 'applicant'],
  'manual_gaps': ['applicant-to-declaration relationship',
                  'course-specific checklist completeness',
                  'counselling-before-application timing']},
 {'id': '4.1.1.3',
  'subcriterion': '4.1.1',
  'title': 'Execute compliant student selection and admissions procedures',
  'document_reference': 'PPD-SSO-AD-4.1.1 Student Selection and Admission',
  'source_keys': ['applicant', 'admission', 'adjustments'],
  'manual_gaps': ['approved entry-requirement denominator',
                  'qualification evidence',
                  'document authenticity',
                  'management and partner approvals',
                  'orientation and Student Pass actions']},
 {'id': '4.1.1.4',
  'subcriterion': '4.1.1',
  'title': 'Monitor staff performing student selection and admissions',
  'document_reference': 'PPD-SSO-AD-4.1.1 Admissions Process Monitoring',
  'source_keys': [],
  'manual_gaps': ['staff monitoring criteria', 'performance review dates', 'findings and corrective actions']},
 {'id': '4.1.1.5',
  'subcriterion': '4.1.1',
  'title': 'Review counselling, selection and admissions for continual improvement',
  'document_reference': 'PPD-SSO-AD-4.1.1 Continuous System Evaluation',
  'source_keys': ['management_review', 'quality_action'],
  'manual_gaps': ['Criterion 4.1.1 APSR scope', 'linked findings', 'implementation and effectiveness verification']},
 {'id': '4.2.1.1',
  'subcriterion': '4.2.1',
  'title': 'Execute one compliant Student Contract for each course admission',
  'document_reference': 'PPD-SSO-AD-4.2.1 Student Contract Execution',
  'source_keys': ['contract', 'invoice', 'payment'],
  'manual_gaps': ['UCC and guardian signatures',
                  'Form 12 acknowledgement',
                  'explanation evidence',
                  'contract-before-payment timing',
                  'amendment and replacement links']},
 {'id': '4.2.1.2',
  'subcriterion': '4.2.1',
  'title': 'Make the Student Contract available to prospective students',
  'document_reference': 'PPD-SSO-AD-4.2.1 Contract Accessibility',
  'source_keys': [],
  'manual_gaps': ['website publication', 'email delivery', 'SMS access', 'Student P-File copy']},
 {'id': '4.2.1.3',
  'subcriterion': '4.2.1',
  'title': 'Review Student Contract execution for continual improvement',
  'document_reference': 'PPD-SSO-AD-4.2.1 Continuous System Evaluation',
  'source_keys': ['management_review', 'quality_action'],
  'manual_gaps': ['Criterion 4.2.1 APSR scope',
                  'accuracy and signing KPIs',
                  'archive completeness',
                  'effectiveness verification']},
 {'id': '4.2.2.1',
  'subcriterion': '4.2.2',
  'title': 'Collect fees only after contract execution and within the collection cap',
  'document_reference': 'PPD-SSO-AD-4.2.2 Fee Collection Compliance',
  'source_keys': ['contract', 'invoice', 'payment'],
  'manual_gaps': ['Schedule B and C line reconciliation',
                  'instalment due date',
                  'collection cap',
                  'course regulatory scope']},
 {'id': '4.2.2.2',
  'subcriterion': '4.2.2',
  'title': 'Issue an original receipt and maintain accurate payment records',
  'document_reference': 'PPD-SSO-AD-4.2.2 Payment Documentation',
  'source_keys': ['payment', 'invoice'],
  'manual_gaps': ['student and contract linkage', 'official receipt verification', 'payment allocation accuracy']},
 {'id': '4.2.2.3',
  'subcriterion': '4.2.2',
  'title': 'Implement FPS Insurance in accordance with the instruction manual',
  'document_reference': 'PPD-SSO-AD-4.2.2 Fee Protection Compliance',
  'source_keys': ['fps', 'payment'],
  'manual_gaps': ['payment-to-coverage amount reconciliation',
                  'coverage commencement',
                  'declaration deadline',
                  'Nil Declaration',
                  'MIL utilisation']},
 {'id': '4.2.2.4',
  'subcriterion': '4.2.2',
  'title': 'Recognise course-fee revenue on an accrual basis over course delivery',
  'document_reference': 'PPD-SSO-AD-4.2.2 Revenue Recognition Policy',
  'source_keys': [],
  'manual_gaps': ['accounting ledger', 'course-delivery period', 'revenue allocation and adjustments']},
 {'id': '4.2.2.5',
  'subcriterion': '4.2.2',
  'title': 'Review fee collection and FPS implementation for continual improvement',
  'document_reference': 'PPD-SSO-AD-4.2.2 Continuous System Evaluation',
  'source_keys': ['management_review', 'quality_action'],
  'manual_gaps': ['Criterion 4.2.2 APSR scope', 'financial findings', 'corrective-action and effectiveness links']},
 {'id': '4.3.1.1',
  'subcriterion': '4.3.1',
  'title': 'Establish and implement transfer, deferment and withdrawal policies',
  'document_reference': 'PPD-SSO-SS-4.3.1 Student Status Policies',
  'source_keys': ['adjustments', 'contract', 'fps'],
  'manual_gaps': ['type-specific eligibility',
                  'complete supporting evidence',
                  'outstanding payment and document checks',
                  'parent consent',
                  'Student Pass actions',
                  'written outcome date']},
 {'id': '4.3.1.2',
  'subcriterion': '4.3.1',
  'title': 'Maintain current transfer, deferment and withdrawal records',
  'document_reference': 'PPD-SSO-SS-4.3.1 Record Keeping',
  'source_keys': ['adjustments'],
  'manual_gaps': ['weekly review evidence', 'current case status', 'downstream completion links']},
 {'id': '4.3.1.3',
  'subcriterion': '4.3.1',
  'title': 'Review movement policies and procedures for continual improvement',
  'document_reference': 'PPD-SSO-SS-4.3.1 Continuous System Evaluation',
  'source_keys': ['management_review', 'quality_action'],
  'manual_gaps': ['Criterion 4.3.1 APSR scope', 'type-specific trends', 'effectiveness verification']},
 {'id': '4.4.1.1',
  'subcriterion': '4.4.1',
  'title': 'Establish and communicate a compliant refund policy and procedure',
  'document_reference': 'PPD-SSO-SS-4.4.1 Refund Processing Timeliness',
  'source_keys': ['adjustments', 'contract', 'payment'],
  'manual_gaps': ['verified-complete date',
                  'eligibility condition',
                  'Schedule D calculation',
                  'seven-working-day payment SLA']},
 {'id': '4.4.1.2',
  'subcriterion': '4.4.1',
  'title': 'Communicate the computation of the refund amount',
  'document_reference': 'PPD-SSO-SS-4.4.1 Refund Computation Communication',
  'source_keys': [],
  'manual_gaps': ['calculation explanation', 'student notification and acknowledgement']},
 {'id': '4.4.1.3',
  'subcriterion': '4.4.1',
  'title': 'Maintain current and accurate refund records',
  'document_reference': 'PPD-SSO-SS-4.4.1 Refund Record Maintenance',
  'source_keys': ['adjustments', 'payment'],
  'manual_gaps': ['request-to-payment link',
                  'approved amount',
                  'payment amount',
                  'audit and acknowledgement evidence']},
 {'id': '4.4.1.4',
  'subcriterion': '4.4.1',
  'title': 'Review the refund policy and procedure for continual improvement',
  'document_reference': 'PPD-SSO-SS-4.4.1 Continuous System Evaluation',
  'source_keys': ['management_review', 'quality_action'],
  'manual_gaps': ['Criterion 4.4.1 APSR scope',
                  'fairness, accuracy and timeliness analysis',
                  'effectiveness verification']},
 {'id': '4.5.1.1',
  'subcriterion': '4.5.1',
  'title': 'Provide a range of Student Support Services',
  'document_reference': 'PPD-SSO-SS-4.5.1 Student Support Services',
  'source_keys': ['support_register', 'support_strategy'],
  'manual_gaps': ['approved required-service denominator',
                  'student population coverage',
                  'current communication evidence']},
 {'id': '4.5.1.2',
  'subcriterion': '4.5.1',
  'title': 'Implement holistic student-development programmes',
  'document_reference': 'PPD-SSO-SS-4.5.1 Holistic Student Development',
  'source_keys': ['support_strategy'],
  'manual_gaps': ['approved plan', 'delivery evidence', 'participation and outcomes']},
 {'id': '4.5.1.3',
  'subcriterion': '4.5.1',
  'title': 'Provide education, career guidance and employability development',
  'document_reference': 'PPD-SSO-SS-4.5.1 Career and Skills Enhancement',
  'source_keys': ['support_strategy', 'support_register'],
  'manual_gaps': ['career initiative scope', 'student participation', 'outcomes and progression evidence']},
 {'id': '4.5.1.4',
  'subcriterion': '4.5.1',
  'title': 'Communicate current support-service information to students',
  'document_reference': 'PPD-SSO-SS-4.5.1 Service Communication Updates',
  'source_keys': [],
  'manual_gaps': ['orientation, portal, Student Handbook, e-Bulletin, email and messaging communication evidence']},
 {'id': '4.5.1.5',
  'subcriterion': '4.5.1',
  'title': 'Evaluate and review Student Support Services for continual improvement',
  'document_reference': 'PPD-SSO-SS-4.5.1 Continuous System Evaluation',
  'source_keys': ['support_strategy', 'student_log', 'management_review', 'quality_action'],
  'manual_gaps': ['case follow-up and closure schema',
                  'outcome effectiveness',
                  'feedback analysis',
                  'APSR and action linkage']},
 {'id': '4.6.1.1',
  'subcriterion': '4.6.1',
  'title': 'Establish and communicate disciplinary policies and procedures',
  'document_reference': 'PPD-SSO-SS-4.6.1 Comprehensive Disciplinary Procedure and Policies',
  'source_keys': ['student_log', 'warning'],
  'manual_gaps': ['communication coverage', 'case classification', 'investigation, hearing and decision stages']},
 {'id': '4.6.1.2',
  'subcriterion': '4.6.1',
  'title': 'Set and communicate attendance policies and procedures',
  'document_reference': 'PPD-SSO-SS-4.6.1 Attendance Policy and System',
  'source_keys': [],
  'manual_gaps': ['orientation, Student Handbook, Lesson Zero and ongoing reminder evidence']},
 {'id': '4.6.1.3',
  'subcriterion': '4.6.1',
  'title': 'Implement attendance taking and monitoring for all learning modes',
  'document_reference': 'PPD-SSO-SS-4.6.1 Attendance Monitoring',
  'source_keys': ['attendance', 'leave'],
  'manual_gaps': ['scheduled activity denominator',
                  'Zoom and LMS reconciliation',
                  'Student Pass status',
                  'monthly attendance calculation']},
 {'id': '4.6.1.4',
  'subcriterion': '4.6.1',
  'title': 'Implement timely interventions for poor conduct or attendance',
  'document_reference': 'PPD-SSO-SS-4.6.1 Timely Interventions',
  'source_keys': ['attendance', 'student_log', 'warning'],
  'manual_gaps': ['threshold-to-intervention link', 'contact, assessment, plan and escalation dates']},
 {'id': '4.6.1.5',
  'subcriterion': '4.6.1',
  'title': 'Evaluate intervention measures for effectiveness',
  'document_reference': 'PPD-SSO-SS-4.6.1 Measure Evaluation',
  'source_keys': ['student_log', 'attendance'],
  'manual_gaps': ['progress, recurrence, closure evaluation and stakeholder feedback']},
 {'id': '4.6.1.6',
  'subcriterion': '4.6.1',
  'title': 'Review disciplinary, attendance and monitoring systems for continual improvement',
  'document_reference': 'PPD-SSO-SS-4.6.1 Continuous System Evaluation',
  'source_keys': ['management_review', 'quality_action'],
  'manual_gaps': ['Criterion 4.6.1 APSR scope', 'trend analysis', 'linked action and effectiveness verification']}]

QUESTION_REGISTRY = {'overview': [{'id': 'O-01',
               'question': 'Which Criterion 4 students, records or controls require management attention now?',
               'requirement_reference': 'Criterion 4 exception management',
               'support_status': 'Can be implemented with revised mapping',
               'answer_mode': 'attention_summary',
               'metric_ids': ['o-counselling-unacknowledged',
                              'o-conditional-admissions',
                              'o-contracts-pending',
                              'o-overdue-invoices',
                              'o-movement-aged-open',
                              'o-refund-aged-open',
                              'o-attendance-risk-records',
                              'o-unresolved-support-controls'],
               'limitations': 'Categories are not summed because records may overlap. Several indicators are partial '
                              'and do not establish formal non-compliance.'},
              {'id': 'O-02',
               'question': 'What proportion of Criterion 4 requirements has current live evidence, partial evidence or '
                           'no usable evidence?',
               'requirement_reference': 'Criterion 4 evidence and audit traceability',
               'support_status': 'Can be implemented now',
               'answer_mode': 'evidence_coverage',
               'metric_ids': [],
               'limitations': 'A readable source or existing record is not proof that the control is complete, current '
                              'or effective.'}],
 '4.1.1': [{'id': 'AI-01',
            'question': 'What is the current conversion from Student Applicant records to admitted students?',
            'requirement_reference': '4.1.1 admissions monitoring',
            'support_status': 'Can be implemented now',
            'answer_mode': 'admission_conversion_summary',
            'metric_ids': ['c411-applicants-total', 'c411-enrolled-admitted', 'c411-success-rate'],
            'limitations': 'This follows the supplied Metabase status-based calculation and does not independently verify admission compliance.'},
           {'id': 'AI-02',
            'question': 'How many Student Applicant records are currently approved and currently admitted?',
            'requirement_reference': '4.1.1 admissions monitoring',
            'support_status': 'Can be implemented now',
            'answer_mode': 'admission_pipeline_summary',
            'metric_ids': ['c411-applicants-total', 'c411-shortlisted-approved', 'c411-enrolled-admitted'],
            'limitations': 'Approved and Admitted are current application statuses, not necessarily sequential lifecycle totals.'},
           {'id': 'A-01',
            'question': 'Were all Course Counsellors and Recruitment Agents trained and currently reviewed before '
                        'providing counselling?',
            'requirement_reference': '4.1.1.1',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'unsupported',
            'metric_ids': ['c411-counsellor-readiness'],
            'limitations': 'Counsellor training and performance-review evidence is not mapped.'},
           {'id': 'A-02',
            'question': 'Did every applicable applicant complete course-specific pre-course counselling before '
                        'application approval or enrolment?',
            'requirement_reference': '4.1.1.2',
            'support_status': 'Requires an additional field',
            'answer_mode': 'counselling_summary',
            'metric_ids': ['c411-counselling', 'c411-acknowledged', 'c411-unacknowledged', 'c411-staff-complete'],
            'limitations': 'Applicant, course and timing relationships are not available, so a completion rate cannot '
                           'be calculated.'},
           {'id': 'A-03',
            'question': 'Did every admitted applicant meet the approved academic, language, age and '
                        'document-verification requirements?',
            'requirement_reference': '4.1.1.3',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'admission_summary',
            'metric_ids': ['c411-approved-status', 'c411-admission-compliance'],
            'limitations': 'Approved/admitted status is only a population indicator and is not evidence of admission '
                           'compliance.'},
           {'id': 'A-04',
            'question': 'Are conditional or special admissions properly approved, monitored and resolved within the '
                        'required period?',
            'requirement_reference': '4.1.1.3',
            'support_status': 'Requires an additional field',
            'answer_mode': 'conditional_summary',
            'metric_ids': ['c411-conditional', 'c411-conditional-control'],
            'limitations': 'The condition, deadline, approval, evidence and final resolution are not mapped.'},
           {'id': 'A-05',
            'question': 'Were late-joining students approved within the permitted missed-hours limits and successfully '
                        'integrated into the course?',
            'requirement_reference': '4.1.1.3',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'late_joining_summary',
            'metric_ids': ['c411-late', 'c411-late-joining-control'],
            'limitations': 'A late-admission row does not prove threshold, approval or integration compliance.'},
           {'id': 'A-06',
            'question': 'Was the counselling and admissions system reviewed, and were identified gaps converted into '
                        'effective improvement actions?',
            'requirement_reference': '4.1.1.4 and 4.1.1.5',
            'support_status': 'Requires an additional field',
            'answer_mode': 'unsupported',
            'metric_ids': ['c411-review-effectiveness'],
            'limitations': 'Criterion-specific APSR scope and action effectiveness are not mapped.'}],
 '4.2.1': [{'id': 'C-01',
            'question': 'Does every applicable enrolment have the correct, accurate and approved Student Contract for '
                        'one course and period?',
            'requirement_reference': '4.2.1.1',
            'support_status': 'Requires an additional field',
            'answer_mode': 'contract_generation_summary',
            'metric_ids': ['c421-generated', 'c421-invoiced', 'c421-full-execution'],
            'limitations': 'Generation and invoice links are population indicators only; accuracy and approval are not '
                           'verified.'},
           {'id': 'C-02',
            'question': 'Were all required explanations, acknowledgements and signatures completed before course-fee '
                        'payment and commencement?',
            'requirement_reference': '4.2.1.1',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'contract_execution_summary',
            'metric_ids': ['c421-student-signed', 'c421-pending', 'c421-full-execution'],
            'limitations': 'Only the student signature date and sent date are currently measurable.'},
           {'id': 'C-03',
            'question': 'Are contract amendments, transfers, deferments, repeats and terminations supported by the '
                        'correct new contract or signed addendum?',
            'requirement_reference': '4.2.1.1',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'unsupported',
            'metric_ids': ['c421-amendment-control'],
            'limitations': 'Contract-change relationships are not mapped.'},
           {'id': 'C-04',
            'question': 'Did students receive and retain access to the executed contract, and was the contract process '
                        'reviewed for improvement?',
            'requirement_reference': '4.2.1.2 and 4.2.1.3',
            'support_status': 'Requires an additional field',
            'answer_mode': 'unsupported',
            'metric_ids': ['c421-archive-review'],
            'limitations': 'Access, archive and APSR effectiveness evidence is not mapped.'}],
 '4.2.2': [{'id': 'F-01',
            'question': 'Were only permitted fees invoiced and collected according to the executed Student Contract, '
                        'instalment schedule and collection cap?',
            'requirement_reference': '4.2.2.1',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'fee_population_summary',
            'metric_ids': ['c422-invoiced', 'c422-incoming-payments', 'c422-fee-compliance'],
            'limitations': 'The current counts are not reconciled to Schedule B or C, contract execution, instalment '
                           'timing or the fee cap.'},
           {'id': 'F-02',
            'question': 'Is every student payment correctly allocated and supported by an accurate official receipt?',
            'requirement_reference': '4.2.2.2',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'payment_summary',
            'metric_ids': ['c422-incoming-payments', 'c422-payment-allocation'],
            'limitations': 'Incoming Payment Entries are not yet scoped or reconciled to the applicable student fee '
                           'transaction.'},
           {'id': 'F-03',
            'question': 'Are all applicable collected fees protected accurately and within the required FPS '
                        'declaration cycle?',
            'requirement_reference': '4.2.2.3',
            'support_status': 'Requires an additional field',
            'answer_mode': 'fps_summary',
            'metric_ids': ['c422-fps-processed', 'c422-fps-reconciliation'],
            'limitations': 'Processed or approved FPS status is not evidence of complete and timely fee protection.'},
           {'id': 'F-04',
            'question': 'Which overdue, overpaid, unmatched, cash-exception or FPS-limit matters require financial or '
                        'management action?',
            'requirement_reference': '4.2.2.1 to 4.2.2.3',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'fee_exception_summary',
            'metric_ids': ['c422-overdue-invoices', 'c422-payment-allocation', 'c422-fps-reconciliation'],
            'limitations': 'Only unscoped overdue invoices are currently countable.'},
           {'id': 'F-05',
            'question': 'Is course-fee revenue recognised on an accrual basis over the approved course duration?',
            'requirement_reference': '4.2.2.4',
            'support_status': 'Requires a new data source',
            'answer_mode': 'unsupported',
            'metric_ids': ['c422-revenue-recognition'],
            'limitations': 'Accounting-ledger and course-delivery allocation data is not mapped.'},
           {'id': 'F-06',
            'question': 'Were the fee-collection, FPS and revenue-recognition controls reviewed, and were corrective '
                        'actions verified as effective?',
            'requirement_reference': '4.2.2.5',
            'support_status': 'Requires an additional field',
            'answer_mode': 'unsupported',
            'metric_ids': ['c422-review-effectiveness'],
            'limitations': 'Criterion-specific APSR and effectiveness evidence is not mapped.'}],
 '4.3.1': [{'id': 'M-01',
            'question': 'Are transfer, deferment and withdrawal requests complete and eligible under their respective '
                        'requirements?',
            'requirement_reference': '4.3.1.1',
            'support_status': 'Requires an additional field',
            'answer_mode': 'movement_summary',
            'metric_ids': ['c431-transfer', 'c431-defer', 'c431-withdraw', 'c431-eligibility-control'],
            'limitations': 'Request counts do not establish completeness or eligibility.'},
           {'id': 'M-02',
            'question': 'Were complete requests decided and communicated within the approved processing standard?',
            'requirement_reference': '4.3.1.1',
            'support_status': 'Requires an additional field',
            'answer_mode': 'movement_ageing_summary',
            'metric_ids': ['c431-aged-open'],
            'limitations': 'The calculation counts weekdays from posting date to today for records without approval '
                           'date. Public holidays, verified completeness and written outcome date are not available.'},
           {'id': 'M-03',
            'question': 'Were all type-specific downstream actions completed after approval?',
            'requirement_reference': '4.3.1.1',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'unsupported',
            'metric_ids': ['c431-downstream-control'],
            'limitations': 'Contract, FPS, Student Pass, timetable, refund and communication actions are not linked.'},
           {'id': 'M-04',
            'question': 'Are open movement requests reviewed weekly and are student-status records current and '
                        'complete?',
            'requirement_reference': '4.3.1.2',
            'support_status': 'Requires an additional field',
            'answer_mode': 'movement_open_summary',
            'metric_ids': ['c431-open', 'c431-weekly-review'],
            'limitations': 'Open request count is available, but weekly review and record-currentness are not '
                           'verified.'},
           {'id': 'M-05',
            'question': 'Was the movement-management system reviewed, and were recurring delays or control failures '
                        'effectively addressed?',
            'requirement_reference': '4.3.1.3',
            'support_status': 'Requires an additional field',
            'answer_mode': 'unsupported',
            'metric_ids': ['c431-review-effectiveness'],
            'limitations': 'Criterion-specific APSR and effectiveness evidence is not mapped.'}],
 '4.4.1': [{'id': 'R-01',
            'question': 'Are refund requests complete and assessed using the correct eligibility condition and '
                        'supporting evidence?',
            'requirement_reference': '4.4.1.1',
            'support_status': 'Requires an additional field',
            'answer_mode': 'refund_request_summary',
            'metric_ids': ['c441-requests', 'c441-open', 'c441-approved', 'c441-eligibility-control'],
            'limitations': 'Approval date does not prove eligibility or completeness.'},
           {'id': 'R-02',
            'question': 'Was each approved refund calculated accurately and was the computation communicated to the '
                        'student?',
            'requirement_reference': '4.4.1.2',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'unsupported',
            'metric_ids': ['c441-calculation-control'],
            'limitations': 'Refund calculation and communication fields are not mapped.'},
           {'id': 'R-03',
            'question': 'Were approved refunds paid and communicated within seven working days from receipt of '
                        'complete and verified information?',
            'requirement_reference': '4.4.1.1 and 4.4.1.3',
            'support_status': 'Requires an additional field',
            'answer_mode': 'refund_completion_summary',
            'metric_ids': ['c441-aged-open', 'c441-refund-payments', 'c441-timely-completion'],
            'limitations': 'The early-warning age and unlinked refund-payment count cannot establish SLA compliance.'},
           {'id': 'R-04',
            'question': 'Which refund appeals, calculation differences, overdue payments or missing acknowledgements '
                        'require management action?',
            'requirement_reference': '4.4.1.1 to 4.4.1.3',
            'support_status': 'Requires an additional field',
            'answer_mode': 'refund_exception_summary',
            'metric_ids': ['c441-open', 'c441-aged-open', 'c441-calculation-control'],
            'limitations': 'Appeal, amount variance and acknowledgement data are not mapped.'},
           {'id': 'R-05',
            'question': 'Was the refund system reviewed for fairness, accuracy and timeliness, and were improvement '
                        'actions effective?',
            'requirement_reference': '4.4.1.4',
            'support_status': 'Requires an additional field',
            'answer_mode': 'unsupported',
            'metric_ids': ['c441-review-effectiveness'],
            'limitations': 'Criterion-specific APSR and effectiveness evidence is not mapped.'}],
 '4.5.1': [{'id': 'S-01',
            'question': 'Are the required Student Support Services current, available, assigned and communicated to '
                        'the applicable student population?',
            'requirement_reference': '4.5.1.1 and 4.5.1.4',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'support_availability_summary',
            'metric_ids': ['c451-strategy-records', 'c451-register-records', 'c451-service-coverage'],
            'limitations': 'Record availability does not establish required service coverage or communication.'},
           {'id': 'S-02',
            'question': 'Were orientation, holistic-development and career initiatives delivered according to the '
                        'approved plan and applicable student needs?',
            'requirement_reference': '4.5.1.2 and 4.5.1.3',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'support_delivery_summary',
            'metric_ids': ['c451-strategy-records', 'c451-plan-delivery'],
            'limitations': 'Planned-versus-actual delivery and participation cannot be calculated.'},
           {'id': 'S-03',
            'question': 'Are identified student-support needs assigned, actioned, followed up and formally closed '
                        'according to defined support protocols?',
            'requirement_reference': '4.5.1.5',
            'support_status': 'Requires an additional field',
            'answer_mode': 'support_case_summary',
            'metric_ids': ['c451-academic-support',
                           'c451-wellness-support',
                           'c451-integrity-support',
                           'c451-case-control'],
            'limitations': 'Intervention record counts do not establish assignment, follow-up or closure.'},
           {'id': 'S-04',
            'question': 'Are support services achieving useful outcomes, and which unmet needs, low-utilisation areas '
                        'or recurring cases require adjustment?',
            'requirement_reference': '4.5.1.5',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'unsupported',
            'metric_ids': ['c451-outcome-effectiveness'],
            'limitations': 'Outcome and effectiveness data is not mapped.'}],
 '4.6.1': [{'id': 'CA-01',
            'question': 'Is attendance completely and accurately recorded for every scheduled learning activity across '
                        'all applicable delivery modes?',
            'requirement_reference': '4.6.1.3',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'attendance_record_summary',
            'metric_ids': ['c461-attendance', 'c461-attendance-completeness'],
            'limitations': 'Attendance record volume is available, but scheduled-session completeness and cross-mode '
                           'accuracy are not.'},
           {'id': 'CA-02',
            'question': 'Which students are below their applicable monthly attendance or punctuality thresholds?',
            'requirement_reference': '4.6.1.3 and 4.6.1.4',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'attendance_risk_summary',
            'metric_ids': ['c461-risk-records', 'c461-monthly-threshold'],
            'limitations': 'Absent or late record count is not a student-month threshold calculation.'},
           {'id': 'CA-03',
            'question': 'Did every student crossing an intervention threshold receive the required contact, '
                        'assessment, action plan, warning or escalation on time?',
            'requirement_reference': '4.6.1.4',
            'support_status': 'Requires an additional field',
            'answer_mode': 'attendance_intervention_summary',
            'metric_ids': ['c461-warning', 'c461-intervention-timeliness'],
            'limitations': 'Warning volume is available, but threshold-to-intervention linkage and timeliness are '
                           'not.'},
           {'id': 'CA-04',
            'question': 'Are leave requests validly supported, approved and correctly integrated without treating '
                        'approved leave as attendance?',
            'requirement_reference': '4.6.1.3',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'leave_summary',
            'metric_ids': ['c461-leave', 'c461-leave-validity'],
            'limitations': 'Leave record volume does not establish evidence validity or correct attendance '
                           'integration.'},
           {'id': 'CA-05',
            'question': 'Did formal misconduct cases follow due process and result in an authorised, '
                        'evidence-supported and proportionate outcome?',
            'requirement_reference': '4.6.1.1',
            'support_status': 'Requires a new DocType or child-table query',
            'answer_mode': 'unsupported',
            'metric_ids': ['c461-disciplinary-due-process'],
            'limitations': 'Structured disciplinary stages and committee scoring are not mapped.'},
           {'id': 'CA-06',
            'question': 'Were attendance and conduct interventions effective, and was the overall system reviewed for '
                        'continual improvement?',
            'requirement_reference': '4.6.1.5 and 4.6.1.6',
            'support_status': 'Requires an additional field',
            'answer_mode': 'unsupported',
            'metric_ids': ['c461-effectiveness-review'],
            'limitations': 'Outcome, recurrence, closure evaluation and Criterion-specific APSR evidence are not '
                           'mapped.'}]}

EXCEPTION_METRIC_IDS = ['o-counselling-unacknowledged',
 'o-conditional-admissions',
 'o-contracts-pending',
 'o-overdue-invoices',
 'o-movement-aged-open',
 'o-refund-aged-open',
 'o-attendance-risk-records',
 'o-unresolved-support-controls',
 'c411-unacknowledged',
 'c411-pdpa-missing',
 'c411-conditional',
 'c411-late',
 'c411-counsellor-readiness',
 'c411-admission-compliance',
 'c411-conditional-control',
 'c411-late-joining-control',
 'c411-review-effectiveness',
 'c421-pending',
 'c421-full-execution',
 'c421-amendment-control',
 'c421-archive-review',
 'c422-overdue-invoices',
 'c422-fee-compliance',
 'c422-payment-allocation',
 'c422-fps-reconciliation',
 'c422-revenue-recognition',
 'c422-review-effectiveness',
 'c431-open',
 'c431-aged-open',
 'c431-eligibility-control',
 'c431-downstream-control',
 'c431-weekly-review',
 'c431-review-effectiveness',
 'c441-open',
 'c441-aged-open',
 'c441-eligibility-control',
 'c441-calculation-control',
 'c441-timely-completion',
 'c441-review-effectiveness',
 'c451-service-coverage',
 'c451-plan-delivery',
 'c451-case-control',
 'c451-outcome-effectiveness',
 'c461-risk-records',
 'c461-warning',
 'c461-attendance-completeness',
 'c461-monthly-threshold',
 'c461-intervention-timeliness',
 'c461-leave-validity',
 'c461-disciplinary-due-process',
 'c461-effectiveness-review']


STANDARD_FIELDS = [
    "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
    "parent", "parenttype", "parentfield"
]

CHILD_SAFE_FIELDS = [
    "name", "parent", "parenttype", "parentfield", "type", "approved_date",
    "student_id", "student_name", "program", "course", "posting_date",
    "academic_year", "reasons_for_request", "parent_consent", "attach_parent",
    "attach_docs", "withdrawal_type", "transferring_to", "start_date_of_deferral",
    "end_date_of_deferral", "expected_date_of_return", "courses_to_be_deferred",
    "creation", "modified"
]


def clean_text(value):
    if value is None:
        return ""
    return frappe.utils.cstr(value).strip()


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
        return frappe.utils.flt(value)
    except Exception:
        return None


def is_permission_error(error):
    text = lower_text(error)
    return (
        "permission" in text
        or "not permitted" in text
        or "not allowed" in text
    )


meta_cache = {}
resolved_field_cache = {}
safe_field_cache = {}
filter_cache = {}
source_resolution_cache = {}
row_cache = {}
row_error_cache = {}
source_field_plan_cache = {}
child_field_plan_cache = {}
child_row_cache = {}
parent_doc_cache = {}
query_stats = {
    "source_probes": 0,
    "row_queries": 0,
    "child_queries": 0,
    "parent_doc_fallbacks": 0,
    "cache_hits": 0
}


def get_meta(doctype):
    if doctype in meta_cache:
        query_stats["cache_hits"] = query_stats["cache_hits"] + 1
        return meta_cache.get(doctype)
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        meta = None
    meta_cache[doctype] = meta
    return meta


def field_exists(meta, fieldname):
    if not fieldname:
        return False
    if fieldname in STANDARD_FIELDS:
        return True
    if not meta:
        return False
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
    cache_key = clean_text(doctype) + "|" + "|".join(candidates or [])
    if cache_key in resolved_field_cache:
        query_stats["cache_hits"] = query_stats["cache_hits"] + 1
        return resolved_field_cache.get(cache_key) or ""
    meta = get_meta(doctype)
    if not meta:
        resolved_field_cache[cache_key] = ""
        return ""
    for fieldname in candidates or []:
        if field_exists(meta, fieldname):
            resolved_field_cache[cache_key] = fieldname
            return fieldname
    resolved_field_cache[cache_key] = ""
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


def applied_filters(doctype, excluded_keys=None):
    excluded = excluded_keys or []
    cache_key = clean_text(doctype) + "|" + "|".join(excluded)
    if cache_key in filter_cache:
        query_stats["cache_hits"] = query_stats["cache_hits"] + 1
        return filter_cache.get(cache_key) or {}
    meta = get_meta(doctype)
    output = {}
    if not meta:
        filter_cache[cache_key] = output
        return output
    for filter_key in FILTER_FIELD_CANDIDATES:
        if filter_key in excluded:
            continue
        requested = filters.get(filter_key)
        if requested in [None, "", "All", "all"]:
            continue
        for candidate in FILTER_FIELD_CANDIDATES.get(filter_key) or []:
            if field_exists(meta, candidate):
                output[candidate] = requested
                break
    filter_cache[cache_key] = output
    return output


def safe_fields(doctype, fields):
    requested = fields or []
    cache_key = clean_text(doctype) + "|" + "|".join(requested)
    if cache_key in safe_field_cache:
        query_stats["cache_hits"] = query_stats["cache_hits"] + 1
        return safe_field_cache.get(cache_key) or []
    meta = get_meta(doctype)
    output = []
    if not meta:
        safe_field_cache[cache_key] = output
        return output
    for fieldname in requested:
        if fieldname not in output and field_exists(meta, fieldname):
            output.append(fieldname)
    if "name" not in output:
        output.insert(0, "name")
    safe_field_cache[cache_key] = output
    return output


def add_candidates(target, candidates):
    for fieldname in candidates or []:
        if fieldname and fieldname not in target:
            target.append(fieldname)


def planned_source_fields(source_alias):
    if source_alias in source_field_plan_cache:
        return source_field_plan_cache.get(source_alias) or ["name"]
    output = ["name"]
    add_candidates(output, SAFE_FIELDS.get(source_alias) or [])
    for filter_key in FILTER_FIELD_CANDIDATES:
        add_candidates(output, FILTER_FIELD_CANDIDATES.get(filter_key) or [])
    for metric in CONFIG.get(subcriterion, {}).get("metrics") or []:
        if metric.get("source") != source_alias or metric.get("child_table_field"):
            continue
        add_candidates(output, metric.get("field") or [])
        for group in metric.get("fields") or []:
            add_candidates(output, group)
        for condition in metric.get("conditions") or []:
            add_candidates(output, condition.get("field") or [])
    source_field_plan_cache[source_alias] = output
    return output


def planned_child_fields(source_alias, table_field, child_doctype):
    cache_key = source_alias + "|" + table_field + "|" + child_doctype
    if cache_key in child_field_plan_cache:
        return child_field_plan_cache.get(cache_key) or CHILD_SAFE_FIELDS
    output = []
    add_candidates(output, CHILD_SAFE_FIELDS)
    for metric in CONFIG.get(subcriterion, {}).get("metrics") or []:
        if (
            metric.get("source") != source_alias
            or metric.get("child_table_field") != table_field
            or metric.get("child_doctype") != child_doctype
        ):
            continue
        add_candidates(output, metric.get("field") or [])
        for group in metric.get("fields") or []:
            add_candidates(output, group)
        for condition in metric.get("conditions") or []:
            add_candidates(output, condition.get("field") or [])
    child_field_plan_cache[cache_key] = output
    return output


def resolve_source(alias):
    if alias in source_resolution_cache:
        query_stats["cache_hits"] = query_stats["cache_hits"] + 1
        return source_resolution_cache.get(alias)

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

        if not get_meta(doctype):
            attempt["status"] = "unavailable"
            attempt["message"] = "DocType metadata is unavailable."
            attempts.append(attempt)
            continue

        try:
            query_stats["source_probes"] = query_stats["source_probes"] + 1
            rows = frappe.get_list(
                doctype,
                fields=["name"],
                limit_start=0,
                limit_page_length=1,
                order_by="modified desc"
            ) or []
            attempt["stage"] = "list"
            attempt["status"] = "available"
            attempt["message"] = "Readable by the signed-in user."
            attempts.append(attempt)
            result = {
                "key": alias,
                "doctype": doctype,
                "candidates": candidates,
                "status": "available",
                "count": len(rows),
                "sample_count": len(rows),
                "count_is_sample": True,
                "truncated": False,
                "probe": "frappe.get_list",
                "fallback_used": candidate_index > 0,
                "resolution_attempts": attempts
            }
            source_resolution_cache[alias] = result
            return result
        except Exception as error:
            message = clean_text(error)
            attempt["stage"] = "list"
            attempt["status"] = "permission_denied" if is_permission_error(error) else "unavailable"
            attempt["message"] = message
            attempts.append(attempt)
            if is_permission_error(error):
                result = {
                    "key": alias,
                    "doctype": doctype,
                    "candidates": candidates,
                    "status": "permission_denied",
                    "count": 0,
                    "sample_count": 0,
                    "count_is_sample": True,
                    "message": message,
                    "probe": "frappe.get_list",
                    "fallback_used": False,
                    "resolution_attempts": attempts
                }
                source_resolution_cache[alias] = result
                return result

    result = {
        "key": alias,
        "doctype": None,
        "candidates": candidates,
        "status": "unavailable",
        "count": 0,
        "sample_count": 0,
        "count_is_sample": True,
        "message": "No approved candidate DocType could be resolved. Open Source Mapping Report for candidate-level errors.",
        "metadata_errors": attempts,
        "resolution_attempts": attempts,
        "fallback_used": False
    }
    source_resolution_cache[alias] = result
    return result


def fetch_rows(source_alias, source, requested_fields=None, excluded_filter_keys=None):
    doctype = source.get("doctype")
    if source.get("status") != "available" or not doctype:
        return []

    planned = list(planned_source_fields(source_alias))
    add_candidates(planned, requested_fields or [])
    fields_to_fetch = safe_fields(doctype, planned)
    active_filters = applied_filters(doctype, excluded_filter_keys)
    filter_parts = []
    for key in sorted(active_filters):
        filter_parts.append(clean_text(key) + "=" + clean_text(active_filters.get(key)))
    cache_key = source_alias + "|" + doctype + "|" + "|".join(fields_to_fetch) + "|" + "|".join(filter_parts)

    if cache_key in row_cache:
        query_stats["cache_hits"] = query_stats["cache_hits"] + 1
        return row_cache.get(cache_key) or []

    try:
        query_stats["row_queries"] = query_stats["row_queries"] + 1
        rows = frappe.get_list(
            doctype,
            fields=fields_to_fetch,
            filters=active_filters,
            limit_page_length=row_limit + 1,
            order_by="modified desc"
        ) or []
        truncated = len(rows) > row_limit
        if truncated:
            rows = rows[:row_limit]
        row_cache[cache_key] = rows
        row_error_cache[cache_key] = None
        source["count"] = len(rows)
        source["count_is_sample"] = False
        source["truncated"] = truncated
        source.pop("fetch_error", None)
        source.pop("fetch_status", None)
        return rows
    except Exception as error:
        message = clean_text(error)
        status = "permission_denied" if is_permission_error(error) else "query_error"
        row_cache[cache_key] = []
        row_error_cache[cache_key] = message
        source["fetch_error"] = message
        source["fetch_status"] = status
        return []


def working_days_elapsed(start_value, end_value=None):
    if not start_value:
        return None
    try:
        start_date = frappe.utils.getdate(start_value)
        end_date = frappe.utils.getdate(end_value or frappe.utils.today())
        if end_date <= start_date:
            return 0
        current = start_date
        count = 0
        guard = 0
        while current < end_date and guard < 5000:
            current = frappe.utils.getdate(frappe.utils.add_days(current, 1))
            if current.weekday() < 5:
                count = count + 1
            guard = guard + 1
        return count
    except Exception:
        return None


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
        allowed = []
        for item in values or []:
            allowed.append(lower_text(item))
        return lower_text(value) in allowed
    if op == "not_in":
        blocked = []
        for item in values or []:
            blocked.append(lower_text(item))
        return lower_text(value) not in blocked
    if op == "contains":
        return lower_text(expected) in lower_text(value)
    if op == "contains_any":
        text_value = lower_text(value)
        for item in values or []:
            if lower_text(item) in text_value:
                return True
        return False
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
    if op == "date_before_today":
        if not value:
            return False
        try:
            return frappe.utils.getdate(value) < frappe.utils.getdate(frappe.utils.today())
        except Exception:
            return False
    if op == "working_days_over":
        elapsed = working_days_elapsed(value)
        if elapsed is None:
            return False
        return elapsed > frappe.utils.cint(days or 0)
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

    resolved_group_result = resolve_field_groups(doctype, metric.get("fields") or [])
    resolved_groups = resolved_group_result[0]
    missing_groups = resolved_group_result[1]
    for fieldname in resolved_groups:
        if fieldname not in fields:
            fields.append(fieldname)
    for group in missing_groups:
        missing.append(group)

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
    if mode in ["truthy", "falsy", "equals", "in", "not_in", "contains_any", "date_before_today", "working_days_over", "gt", "gte", "lt", "lte"]:
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
    return False


def child_row_matches_filters(row):
    academic_year = filters.get("academic_year")
    program = filters.get("program")
    status_filter = filters.get("status")
    student_filter = filters.get("student")

    if academic_year and clean_text(row.get("academic_year")) != clean_text(academic_year):
        return False
    if program and clean_text(row.get("program") or row.get("course")) != clean_text(program):
        return False
    if student_filter and clean_text(row.get("student") or row.get("student_id")) != clean_text(student_filter):
        return False

    if status_filter:
        approved = is_truthy(row.get("approved_date"))
        status_text = lower_text(status_filter)
        if status_text in ["approved", "completed", "closed"] and not approved:
            return False
        if status_text in ["open", "pending"] and approved:
            return False

    return True


def fetch_child_rows(parent_source, source_alias, table_field, child_doctype, requested_fields):
    parent_doctype = parent_source.get("doctype")
    cache_key = source_alias + "|" + parent_doctype + "|" + table_field + "|" + child_doctype
    if cache_key in child_row_cache:
        query_stats["cache_hits"] = query_stats["cache_hits"] + 1
        return child_row_cache.get(cache_key)

    parent_meta = get_meta(parent_doctype)
    try:
        table_meta_field = parent_meta.get_field(table_field) if parent_meta else None
    except Exception:
        table_meta_field = None

    if not table_meta_field or table_meta_field.fieldtype != "Table":
        result = {"status": "unsupported_field", "rows": [], "message": "Child table field is unavailable."}
        child_row_cache[cache_key] = result
        return result

    if table_meta_field.options != child_doctype:
        result = {
            "status": "unsupported_field",
            "rows": [],
            "message": "Child table field does not point to the expected DocType."
        }
        child_row_cache[cache_key] = result
        return result

    child_meta = get_meta(child_doctype)
    if not child_meta:
        result = {"status": "unavailable", "rows": [], "message": "Child DocType metadata is unavailable."}
        child_row_cache[cache_key] = result
        return result

    parent_fields = safe_fields(
        parent_doctype,
        ["name", "student", "student_name", "academic_year", "program", "course", "status", "workflow_state"]
    )
    parent_rows = fetch_rows(source_alias, parent_source, parent_fields, ["status"])
    if parent_source.get("fetch_error"):
        result = {
            "status": parent_source.get("fetch_status") or "unavailable",
            "rows": [],
            "message": parent_source.get("fetch_error")
        }
        child_row_cache[cache_key] = result
        return result

    parent_map = {}
    parent_names = []
    for parent_row in parent_rows:
        parent_name = parent_row.get("name")
        if parent_name:
            parent_map[parent_name] = parent_row
            parent_names.append(parent_name)

    if not parent_names:
        result = {"status": "available", "rows": [], "truncated": False, "query_mode": "no_parent_rows"}
        child_row_cache[cache_key] = result
        return result

    planned = list(planned_child_fields(source_alias, table_field, child_doctype))
    add_candidates(planned, requested_fields or [])
    add_candidates(planned, ["parent", "parenttype", "parentfield"])
    child_fields = safe_fields(child_doctype, planned)

    direct_rows = []
    direct_error = None
    batch_size = 500
    batch_start = 0
    while batch_start < len(parent_names) and len(direct_rows) < row_limit:
        batch_names = parent_names[batch_start:batch_start + batch_size]
        try:
            query_stats["child_queries"] = query_stats["child_queries"] + 1
            remaining = row_limit - len(direct_rows)
            rows = frappe.get_list(
                child_doctype,
                fields=child_fields,
                filters={
                    "parenttype": parent_doctype,
                    "parentfield": table_field,
                    "parent": ["in", batch_names]
                },
                limit_page_length=remaining,
                order_by="modified desc"
            ) or []
            direct_rows.extend(rows)
        except Exception as error:
            direct_error = error
            direct_rows = []
            break
        batch_start = batch_start + batch_size

    output = []
    query_mode = "direct_child_query"

    if direct_error is None:
        for child_row in direct_rows:
            parent_row = parent_map.get(child_row.get("parent")) or {}
            row = {}
            for key in child_row:
                row[key] = child_row.get(key)
            row["student"] = row.get("student") or parent_row.get("student")
            row["student_name"] = row.get("student_name") or parent_row.get("student_name")
            row["academic_year"] = row.get("academic_year") or parent_row.get("academic_year")
            row["program"] = row.get("program") or parent_row.get("program") or parent_row.get("course")
            row["course"] = row.get("course") or parent_row.get("course") or parent_row.get("program")
            if child_row_matches_filters(row):
                output.append(row)
            if len(output) >= row_limit:
                break
    else:
        query_mode = "parent_doc_fallback"
        for parent_row in parent_rows:
            if len(output) >= row_limit:
                break
            parent_name = parent_row.get("name")
            if not parent_name:
                continue
            if parent_name in parent_doc_cache:
                query_stats["cache_hits"] = query_stats["cache_hits"] + 1
                parent_doc = parent_doc_cache.get(parent_name)
            else:
                try:
                    query_stats["parent_doc_fallbacks"] = query_stats["parent_doc_fallbacks"] + 1
                    parent_doc = frappe.get_doc(parent_doctype, parent_name)
                except Exception:
                    parent_doc = None
                parent_doc_cache[parent_name] = parent_doc
            if not parent_doc:
                continue

            children = parent_doc.get(table_field) or []
            for child in children:
                if len(output) >= row_limit:
                    break
                row = {
                    "name": child.get("name"),
                    "parent": parent_doc.name,
                    "parenttype": parent_doctype,
                    "parentfield": table_field,
                    "student": parent_doc.get("student"),
                    "student_name": parent_doc.get("student_name"),
                    "academic_year": parent_doc.get("academic_year"),
                    "program": parent_doc.get("program") or parent_doc.get("course"),
                    "course": parent_doc.get("course") or parent_doc.get("program")
                }
                for fieldname in child_fields:
                    child_value = child.get(fieldname)
                    if child_value not in [None, ""] or fieldname not in row:
                        row[fieldname] = child_value
                if child_row_matches_filters(row):
                    output.append(row)

    result = {
        "status": "available",
        "rows": output,
        "truncated": len(output) >= row_limit or len(direct_rows) >= row_limit,
        "query_mode": query_mode
    }
    if direct_error is not None:
        result["direct_query_error"] = clean_text(direct_error)
    child_row_cache[cache_key] = result
    return result


if subcriterion not in CONFIG:
    frappe.throw("Unsupported Criterion 4 subcriterion.")

resolved_sources = {}
for alias in CONFIG[subcriterion]["sources"]:
    resolved_sources[alias] = resolve_source(alias)


def evaluate_child_metric(metric, source, include_rows=False):
    parent_doctype = source.get("doctype")
    child_doctype = metric.get("child_doctype")
    table_field = metric.get("child_table_field")

    if not child_doctype or not table_field:
        return {
            "id": metric.get("id"), "label": metric.get("label"), "source": metric.get("source"),
            "doctype": parent_doctype, "value": None, "status": "unsupported_field",
            "message": "Child-table configuration is incomplete.", "rows": []
        }

    required_field_result = metric_required_fields(metric, child_doctype)
    required_fields = required_field_result[0]
    missing = required_field_result[1]
    resolved_conditions = required_field_result[2]
    if metric.get("mode") != "all" and missing:
        return {
            "id": metric.get("id"), "label": metric.get("label"), "source": metric.get("source"),
            "doctype": child_doctype, "parent_doctype": parent_doctype,
            "value": None, "status": "unsupported_field",
            "message": "Required child field is not installed.",
            "missing_field_candidates": missing, "rows": []
        }

    fetched = fetch_child_rows(source, metric.get("source"), table_field, child_doctype, required_fields)
    if fetched.get("status") != "available":
        return {
            "id": metric.get("id"), "label": metric.get("label"), "source": metric.get("source"),
            "doctype": child_doctype, "parent_doctype": parent_doctype,
            "value": None, "status": fetched.get("status") or "unavailable",
            "message": fetched.get("message"), "rows": []
        }

    matched = []
    for row in fetched.get("rows") or []:
        if row_matches(row, metric, required_fields, resolved_conditions):
            matched.append(row)

    output_rows = []
    if include_rows:
        start = (page - 1) * page_size
        end = start + page_size
        for row in matched[start:end]:
            item = {}
            for fieldname in CHILD_SAFE_FIELDS:
                if fieldname in row:
                    item[fieldname] = row.get(fieldname)
            for fieldname in ["student", "student_name", "course", "program", "academic_year"]:
                if fieldname in row:
                    item[fieldname] = row.get(fieldname)
            output_rows.append(item)

    return {
        "id": metric.get("id"),
        "label": metric.get("label"),
        "source": metric.get("source"),
        "doctype": child_doctype,
        "parent_doctype": parent_doctype,
        "value": len(matched),
        "unit": metric.get("unit") or "records",
        "record_count": len(matched),
        "status": "available",
        "resolved_fields": required_fields,
        "rows": output_rows,
        "total": len(matched),
        "truncated": fetched.get("truncated") or False
    }


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

    if metric.get("child_table_field"):
        return evaluate_child_metric(metric, source, include_rows)

    doctype = source.get("doctype")
    required_field_result = metric_required_fields(metric, doctype)
    required_fields = required_field_result[0]
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

    requested = list(required_fields)
    for fieldname in SAFE_FIELDS.get(metric.get("source"), []):
        if include_rows and fieldname not in requested:
            requested.append(fieldname)

    rows = fetch_rows(metric.get("source"), source, requested)
    if source.get("fetch_error"):
        return {
            "id": metric.get("id"), "label": metric.get("label"),
            "source": metric.get("source"), "doctype": doctype,
            "value": None, "unit": metric.get("unit") or "records",
            "record_count": 0, "status": source.get("fetch_status") or "query_error",
            "message": source.get("fetch_error"), "resolved_fields": required_fields,
            "rows": [], "total": 0
        }
    if metric.get("mode") == "ratio_status":
        numerator_values = []
        for item in metric.get("values") or []:
            numerator_values.append(lower_text(item))
        numerator_rows = []
        fieldname = required_fields[0] if required_fields else None
        for row in rows:
            if fieldname and lower_text(row.get(fieldname)) in numerator_values:
                numerator_rows.append(row)
        denominator = len(rows)
        value = 0.0
        if denominator:
            value = round((float(len(numerator_rows)) / float(denominator)) * 100.0, 2)
        output_rows = []
        if include_rows:
            start = (page - 1) * page_size
            end = start + page_size
            output_fields = safe_fields(doctype, SAFE_FIELDS.get(metric.get("source"), ["name"]))
            for row in numerator_rows[start:end]:
                item = {}
                for output_field in output_fields:
                    item[output_field] = row.get(output_field)
                output_rows.append(item)
        return {
            "id": metric.get("id"),
            "label": metric.get("label"),
            "source": metric.get("source"),
            "doctype": doctype,
            "value": value,
            "unit": metric.get("unit") or "percent",
            "record_count": len(numerator_rows),
            "denominator": denominator,
            "status": "available",
            "resolved_fields": required_fields,
            "rows": output_rows,
            "total": len(numerator_rows),
            "truncated": len(rows) >= row_limit,
            "calculation_note": "Admitted Student Applicant records divided by all Student Applicant records within the applied filters."
        }

    matched = []
    for row in rows:
        if row_matches(row, metric, required_fields, resolved_conditions):
            matched.append(row)

    output_rows = []
    if include_rows:
        start = (page - 1) * page_size
        end = start + page_size
        output_fields = safe_fields(doctype, SAFE_FIELDS.get(metric.get("source"), ["name"]))
        for row in matched[start:end]:
            item = {}
            for fieldname in output_fields:
                item[fieldname] = row.get(fieldname)
            output_rows.append(item)

    return {
        "id": metric.get("id"),
        "label": metric.get("label"),
        "source": metric.get("source"),
        "doctype": doctype,
        "value": len(matched),
        "unit": metric.get("unit") or "records",
        "record_count": len(matched),
        "status": "available",
        "resolved_fields": required_fields,
        "rows": output_rows,
        "total": len(matched),
        "truncated": len(rows) >= row_limit
    }


metrics = []
for configured_metric in CONFIG[subcriterion]["metrics"]:
    metrics.append(evaluate_metric(configured_metric, False))

metric_lookup = {}
for metric in metrics:
    metric_lookup[metric.get("id")] = metric


def group_count_rows(rows, fieldname, status_value=None):
    grouped = {}
    expected_status = lower_text(status_value) if status_value else ""
    for row in rows or []:
        if expected_status and lower_text(row.get("application_status")) != expected_status:
            continue
        label = clean_text(row.get(fieldname)) or "Not specified"
        grouped[label] = grouped.get(label, 0) + 1
    output = []
    for label in grouped:
        output.append({"label": label, "value": grouped.get(label) or 0})
    return output


def sort_group_rows(rows, year_mode=False):
    output = list(rows or [])
    if year_mode:
        def year_key(item):
            label = clean_text(item.get("label"))
            try:
                return (0, int(label))
            except Exception:
                return (1, label.lower())
        output.sort(key=year_key)
    else:
        output.sort(key=lambda item: lower_text(item.get("label")))
    return output


def build_admission_intelligence():
    if subcriterion != "4.1.1":
        return {}

    applicant_source = resolved_sources.get("applicant") or {}
    if applicant_source.get("status") != "available":
        return {
            "status": applicant_source.get("status") or "unavailable",
            "message": applicant_source.get("message") or "Student Applicant is unavailable.",
            "kpis": [],
            "charts": {}
        }

    applicant_rows = fetch_rows(
        "applicant",
        applicant_source,
        ["application_status", "academic_year", "nationality", "country", "program", "course", "agent", "intake"]
    )

    admitted_rows = []
    approved_rows = []
    applicant_by_name = {}
    for row in applicant_rows:
        applicant_name = row.get("name")
        if applicant_name:
            applicant_by_name[applicant_name] = row
        status_value = lower_text(row.get("application_status"))
        if status_value == "admitted":
            admitted_rows.append(row)
        if status_value == "approved":
            approved_rows.append(row)

    applicant_total = len(applicant_rows)
    admitted_total = len(admitted_rows)
    success_rate = 0.0
    if applicant_total:
        success_rate = round((float(admitted_total) / float(applicant_total)) * 100.0, 2)

    applicants_by_year = sort_group_rows(group_count_rows(applicant_rows, "academic_year"), True)
    enrolled_by_year = sort_group_rows(group_count_rows(applicant_rows, "academic_year", "Admitted"), True)

    nationality_field = resolve_field(applicant_source.get("doctype"), ["nationality", "country"])
    applicants_by_country = []
    if nationality_field:
        applicants_by_country = sort_group_rows(group_count_rows(applicant_rows, nationality_field), False)

    program_field = resolve_field(applicant_source.get("doctype"), ["program", "course", "course_applying_for"])
    programmes = []
    if program_field:
        programmes = sort_group_rows(group_count_rows(applicant_rows, program_field), False)

    agent_field = resolve_field(applicant_source.get("doctype"), ["agent", "custom_agent", "recruitment_agent"])
    agents = []
    if agent_field:
        agents = sort_group_rows(group_count_rows(applicant_rows, agent_field), False)

    duration_by_year = {}
    duration_counts = {}
    duration_status = "available"
    duration_message = "Average calendar days from pre-course counselling to student signature for submitted Student Admission UCC records."
    admission_source = resolved_sources.get("admission") or {}
    if admission_source.get("status") == "available":
        admission_doctype = admission_source.get("doctype")
        counselling_field = resolve_field(admission_doctype, ["pre_course_counseling"])
        signed_field = resolve_field(admission_doctype, ["student_signed_date", "contract_signed_by_student_date"])
        applicant_link_field = resolve_field(admission_doctype, ["student_applicant"])
        docstatus_field = resolve_field(admission_doctype, ["docstatus"])
        if counselling_field and signed_field and applicant_link_field:
            duration_rows = fetch_rows(
                "admission",
                admission_source,
                [counselling_field, signed_field, applicant_link_field, docstatus_field],
                ["academic_year", "nationality", "agent"]
            )
            for row in duration_rows:
                if docstatus_field and frappe.utils.cint(row.get(docstatus_field)) != 1:
                    continue
                applicant_row = applicant_by_name.get(row.get(applicant_link_field)) or {}
                year_label = clean_text(applicant_row.get("academic_year")) or clean_text(row.get("academic_year")) or "Not specified"
                try:
                    duration_days = frappe.utils.date_diff(row.get(signed_field), row.get(counselling_field))
                except Exception:
                    duration_days = None
                if duration_days is None or duration_days < 0:
                    continue
                duration_by_year[year_label] = duration_by_year.get(year_label, 0.0) + float(duration_days)
                duration_counts[year_label] = duration_counts.get(year_label, 0) + 1
        else:
            duration_status = "unsupported_field"
            duration_message = "Student Admission UCC requires pre_course_counseling, student_signed_date and student_applicant fields."
    else:
        duration_status = admission_source.get("status") or "unavailable"
        duration_message = admission_source.get("message") or "Student Admission UCC is unavailable."

    duration_chart = []
    for year_label in duration_by_year:
        count = duration_counts.get(year_label) or 0
        average_days = round(duration_by_year.get(year_label, 0.0) / float(count), 2) if count else 0.0
        duration_chart.append({"label": year_label, "value": average_days, "record_count": count})
    duration_chart = sort_group_rows(duration_chart, True)

    return {
        "status": "available",
        "calculation_basis": "Supplied Metabase SQL, reproduced from Student Applicant and Student Admission UCC.",
        "kpis": [
            {"id": "c411-applicants-total", "label": "No. of Student Applicants", "value": applicant_total, "unit": "records"},
            {"id": "c411-shortlisted-approved", "label": "No. of Shortlisted", "value": len(approved_rows), "unit": "records"},
            {"id": "c411-enrolled-admitted", "label": "No. of Enrolled Students", "value": admitted_total, "unit": "records"},
            {"id": "c411-success-rate", "label": "Success Rate", "value": success_rate, "unit": "percent"}
        ],
        "charts": {
            "applicants_by_year": applicants_by_year,
            "enrolled_by_year": enrolled_by_year,
            "applicants_by_country": applicants_by_country,
            "programmes": programmes,
            "agents": agents,
            "counselling_to_admission": duration_chart
        },
        "chart_status": {
            "applicants_by_country": "available" if nationality_field else "unsupported_field",
            "programmes": "available" if program_field else "unsupported_field",
            "agents": "available" if agent_field else "unsupported_field",
            "counselling_to_admission": duration_status
        },
        "notes": [
            "No. of Shortlisted follows the supplied Metabase rule: application_status equals Approved.",
            "No. of Enrolled Students follows the supplied Metabase rule: application_status equals Admitted.",
            "Number of Students per Agent follows the supplied SQL and counts Student Applicant records, not only admitted students.",
            duration_message
        ]
    }


admission_intelligence = build_admission_intelligence()


def metric_part(metric_id, fallback_label=None):
    item = metric_lookup.get(metric_id) or {}
    label = fallback_label or item.get("label") or metric_id
    if item.get("status") == "available":
        suffix = ""
        if item.get("truncated"):
            suffix = " (source row limit reached)"
        return label + ": " + frappe.utils.cstr(item.get("value") or 0) + suffix
    detail = clean_text(item.get("message") or item.get("status") or "unavailable")
    return label + ": unavailable (" + detail + ")"


def evaluate_requirement(requirement):
    source_keys = requirement.get("source_keys") or []
    manual_gaps = requirement.get("manual_gaps") or []
    source_details = []
    live_count = 0
    readable_empty_count = 0
    unavailable_count = 0

    for source_key in source_keys:
        source = resolved_sources.get(source_key)
        if not source:
            source = resolve_source(source_key)
        item = {
            "source": source_key,
            "doctype": source.get("doctype"),
            "status": source.get("status"),
            "count": source.get("count") or 0,
            "message": source.get("message")
        }
        source_details.append(item)
        if source.get("status") == "available":
            if (source.get("count") or 0) > 0:
                live_count = live_count + 1
            else:
                readable_empty_count = readable_empty_count + 1
        else:
            unavailable_count = unavailable_count + 1

    if not source_keys:
        evidence_status = "no_mapped_live_source"
    elif live_count == len(source_keys) and not manual_gaps:
        evidence_status = "live_source_with_records"
    elif live_count > 0 or readable_empty_count > 0:
        evidence_status = "partial"
    else:
        evidence_status = "no_available_live_source"

    output = {}
    for key in requirement:
        output[key] = requirement.get(key)
    output["evidence_status"] = evidence_status
    output["source_details"] = source_details
    output["live_sources_with_records"] = live_count
    output["readable_empty_sources"] = readable_empty_count
    output["unavailable_sources"] = unavailable_count
    return output


requirement_evidence = []
for requirement in REQUIREMENT_REGISTRY:
    if subcriterion == "overview" or requirement.get("subcriterion") == subcriterion:
        requirement_evidence.append(evaluate_requirement(requirement))


def linked_metric_status(metric_ids):
    available_count = 0
    unavailable_count = 0
    unsupported_messages = []
    for linked_metric_id in metric_ids:
        linked_metric = metric_lookup.get(linked_metric_id) or {}
        if linked_metric.get("status") == "available":
            available_count = available_count + 1
        else:
            unavailable_count = unavailable_count + 1
            if linked_metric.get("message"):
                unsupported_messages.append(clean_text(linked_metric.get("message")))
    return available_count, unavailable_count, unsupported_messages


def build_question_answer(question):
    answer_mode = question.get("answer_mode") or "unsupported"
    metric_ids = question.get("metric_ids") or []
    linked_status_result = linked_metric_status(metric_ids)
    available_count = linked_status_result[0]
    unavailable_count = linked_status_result[1]
    unsupported_messages = linked_status_result[2]

    status = "partial"
    confidence = "Partial"
    answer = ""

    if answer_mode == "unsupported":
        status = "unsupported"
        confidence = "Unavailable"
        detail = unsupported_messages[0] if unsupported_messages else clean_text(question.get("limitations"))
        answer = "Unavailable: " + detail

    elif answer_mode == "attention_summary":
        parts = []
        for linked_metric_id in metric_ids:
            parts.append(metric_part(linked_metric_id))
        if available_count == 0:
            status = "unavailable"
            confidence = "Unavailable"
        else:
            status = "partial" if unavailable_count > 0 else "available"
            confidence = "Partial" if unavailable_count > 0 else "Live"
        answer = "; ".join(parts) + ". Categories are not summed because records may overlap. These are attention indicators, not automatic non-conformities."

    elif answer_mode == "evidence_coverage":
        counts = {
            "live_source_with_records": 0,
            "partial": 0,
            "no_mapped_live_source": 0,
            "no_available_live_source": 0
        }
        for item in requirement_evidence:
            evidence_status = item.get("evidence_status")
            if evidence_status in counts:
                counts[evidence_status] = counts[evidence_status] + 1
        total = len(requirement_evidence)
        status = "available"
        confidence = "Live source status"
        answer = (
            frappe.utils.cstr(total) + " requirements assessed. Live source with records and no declared manual gap: "
            + frappe.utils.cstr(counts.get("live_source_with_records") or 0)
            + "; partial evidence: " + frappe.utils.cstr(counts.get("partial") or 0)
            + "; no mapped live source: " + frappe.utils.cstr(counts.get("no_mapped_live_source") or 0)
            + "; mapped sources unavailable: " + frappe.utils.cstr(counts.get("no_available_live_source") or 0)
            + ". Source availability is not proof of control effectiveness."
        )

    elif answer_mode == "admission_conversion_summary":
        applicant_metric = metric_lookup.get("c411-applicants-total") or {}
        admitted_metric = metric_lookup.get("c411-enrolled-admitted") or {}
        rate_metric = metric_lookup.get("c411-success-rate") or {}
        if applicant_metric.get("status") == "available" and rate_metric.get("status") == "available":
            status = "available"
            confidence = "Live"
            answer = (
                frappe.utils.cstr(admitted_metric.get("value") or 0)
                + " admitted out of " + frappe.utils.cstr(applicant_metric.get("value") or 0)
                + " Student Applicant records, a success rate of "
                + frappe.utils.cstr(rate_metric.get("value") or 0) + "%."
            )
        else:
            status = "unavailable"
            confidence = "Unavailable"
            answer = "Unavailable: Student Applicant status data could not be read."

    elif answer_mode == "admission_pipeline_summary":
        status = "available" if available_count == len(metric_ids) else "partial"
        confidence = "Live" if status == "available" else "Partial"
        answer = (
            metric_part("c411-applicants-total", "Student Applicants") + "; "
            + metric_part("c411-shortlisted-approved", "Approved / shortlisted") + "; "
            + metric_part("c411-enrolled-admitted", "Admitted / enrolled")
            + ". Approved and Admitted are current statuses and should not be interpreted as sequential historical stages without status-history data."
        )

    elif answer_mode == "counselling_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c411-counselling", "Counselling declarations") + "; "
            + metric_part("c411-acknowledged", "Acknowledged declarations") + "; "
            + metric_part("c411-unacknowledged", "Acknowledgement missing") + "; "
            + metric_part("c411-staff-complete", "Records with staff and date")
            + ". Applicant-course coverage and counselling-before-approval timing cannot be calculated."
        )

    elif answer_mode == "admission_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c411-approved-status", "Approved, admitted or enrolled applicant records")
            + ". This is a population indicator only. Approved requirements, qualification evidence, authenticity verification and approval evidence are not mapped."
        )

    elif answer_mode == "conditional_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c411-conditional", "Conditional admissions")
            + ". The condition, three-month deadline, owner, follow-up, evidence and final outcome are not measurable."
        )

    elif answer_mode == "late_joining_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c411-late", "Late-admission request rows")
            + ". Missed-hours limits, capability assessment, approval, orientation and subsequent attendance are not measurable."
        )

    elif answer_mode == "contract_generation_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c421-generated", "Contracts generated") + "; "
            + metric_part("c421-invoiced", "Admissions linked to a Sales Invoice")
            + ". Contract accuracy, approval, one-course validity and applicable enrolment denominator are not verified."
        )

    elif answer_mode == "contract_execution_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c421-student-signed", "Contracts with student signature date") + "; "
            + metric_part("c421-pending", "Sent contracts without student signature")
            + ". UCC signature, guardian applicability, Form 12 and signing-before-payment or commencement are not verified."
        )

    elif answer_mode == "fee_population_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c422-invoiced", "Admissions linked to a Sales Invoice") + "; "
            + metric_part("c422-incoming-payments", "Submitted incoming Payment Entries")
            + ". Neither population is reconciled to approved fee categories, contract execution, instalment timing or collection cap."
        )

    elif answer_mode == "payment_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c422-incoming-payments", "Submitted incoming Payment Entries")
            + ". The count is not yet scoped to student fees and does not prove allocation or receipt accuracy."
        )

    elif answer_mode == "fps_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c422-fps-processed", "FPS records marked processed or approved")
            + ". Payment amount, protected amount, coverage start, declaration cycle, Nil Declaration and MIL are not reconciled."
        )

    elif answer_mode == "fee_exception_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c422-overdue-invoices", "Overdue Sales Invoices")
            + ". The count is not yet scoped to applicable student fees. Overpayment, unmatched payment, cash exception and FPS-limit tests are unavailable."
        )

    elif answer_mode == "movement_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c431-transfer", "Transfer requests") + "; "
            + metric_part("c431-defer", "Deferment requests") + "; "
            + metric_part("c431-withdraw", "Withdrawal requests")
            + ". Type-specific completeness and eligibility are not verified."
        )

    elif answer_mode == "movement_ageing_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c431-aged-open", "Open requests older than 21 weekdays")
            + ". This is an early-warning indicator using posting date and approval date. It excludes public holidays and cannot confirm verified completeness or written outcome communication."
        )

    elif answer_mode == "movement_open_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c431-open", "Movement requests without approval date")
            + ". Weekly review, current status and downstream completion are not verified."
        )

    elif answer_mode == "refund_request_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c441-requests", "Refund requests") + "; "
            + metric_part("c441-open", "Without approval date") + "; "
            + metric_part("c441-approved", "With approval date")
            + ". Approval date is not evidence of completeness, eligibility or correct assessment."
        )

    elif answer_mode == "refund_completion_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c441-aged-open", "Requests older than 7 weekdays without approval") + "; "
            + metric_part("c441-refund-payments", "Submitted refund-related Payment Entries")
            + ". The verified-complete date, request-to-payment link and student communication are unavailable, so SLA compliance cannot be concluded."
        )

    elif answer_mode == "refund_exception_summary":
        status = "partial" if available_count > 0 else "unsupported"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c441-open", "Refund requests without approval date") + "; "
            + metric_part("c441-aged-open", "Older than 7 weekdays without approval")
            + ". Appeals, amount differences, overdue approved payments and missing acknowledgements are not mapped."
        )

    elif answer_mode == "support_availability_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c451-strategy-records", "Strategy Insights records") + "; "
            + metric_part("c451-register-records", "Support Service Register records")
            + ". Required service coverage, current ownership and communication to the applicable student population are not verified."
        )

    elif answer_mode == "support_delivery_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c451-strategy-records", "Strategy Insights records")
            + ". Planned-versus-actual orientation, holistic-development and career initiative delivery cannot be calculated."
        )

    elif answer_mode == "support_case_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c451-academic-support", "Academic-support records") + "; "
            + metric_part("c451-wellness-support", "Wellness-support records") + "; "
            + metric_part("c451-integrity-support", "Academic-integrity records")
            + ". Assignment, action plan, follow-up, referral, closure and effectiveness are not verified."
        )

    elif answer_mode == "attendance_record_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c461-attendance", "Attendance records")
            + ". Scheduled-learning-activity denominator, completeness and cross-mode verification are unavailable."
        )

    elif answer_mode == "attendance_risk_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c461-risk-records", "Attendance records marked absent or late")
            + ". This is not a student-month attendance percentage or repeated-lateness calculation."
        )

    elif answer_mode == "attendance_intervention_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c461-warning", "Attendance warning or dismissal records")
            + ". Threshold breach, contact, assessment, action plan, approval and intervention timing are not linked."
        )

    elif answer_mode == "leave_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c461-leave", "Student leave application records")
            + ". Evidence validity, approval, five-working-day medical-certificate timing and attendance integration are not verified."
        )

    else:
        status = "unsupported"
        confidence = "Unavailable"
        answer = "Unavailable: no approved answer rule is configured."

    doctypes = []
    for linked_metric_id in metric_ids:
        linked_metric = metric_lookup.get(linked_metric_id) or {}
        doctype = linked_metric.get("doctype")
        if doctype and doctype not in doctypes:
            doctypes.append(doctype)

    return {
        "answer": answer,
        "status": status,
        "confidence": confidence,
        "doctypes": doctypes
    }


QUESTION_DRILLDOWN_METRICS = {
    "AI-01": "c411-enrolled-admitted",
    "AI-02": "c411-applicants-total",
    "A-02": "c411-unacknowledged",
    "A-04": "c411-conditional",
    "A-05": "c411-late",
    "C-01": "c421-generated",
    "C-02": "c421-pending",
    "F-01": "c422-invoiced",
    "F-02": "c422-incoming-payments",
    "F-03": "c422-fps-processed",
    "F-04": "c422-overdue-invoices",
    "M-01": "c431-open",
    "M-02": "c431-aged-open",
    "M-04": "c431-open",
    "R-01": "c441-open",
    "R-03": "c441-aged-open",
    "R-04": "c441-aged-open",
    "S-01": "c451-register-records",
    "S-02": "c451-strategy-records",
    "S-03": "c451-academic-support",
    "CA-01": "c461-attendance",
    "CA-02": "c461-risk-records",
    "CA-03": "c461-warning",
    "CA-04": "c461-leave"
}


def question_primary_metric(question):
    configured_id = QUESTION_DRILLDOWN_METRICS.get(question.get("id"))
    if configured_id:
        return metric_lookup.get(configured_id) or {}, configured_id
    for linked_id in question.get("metric_ids") or []:
        linked_metric = metric_lookup.get(linked_id) or {}
        if linked_metric.get("status") == "available":
            return linked_metric, linked_id
    metric_ids = question.get("metric_ids") or []
    if metric_ids:
        return metric_lookup.get(metric_ids[0]) or {}, metric_ids[0]
    return {}, None


questions = []
for question in QUESTION_REGISTRY.get(subcriterion) or []:
    answer_result = build_question_answer(question)
    metric_ids = question.get("metric_ids") or []
    primary_metric_result = question_primary_metric(question)
    primary_metric = primary_metric_result[0]
    primary_metric_id = primary_metric_result[1]
    question_status = answer_result.get("status")
    if question_status == "partial" and primary_metric.get("status") == "available":
        question_status = "available"
    questions.append({
        "id": question.get("id"),
        "criterion": subcriterion,
        "question": question.get("question"),
        "answer": answer_result.get("answer"),
        "metric_id": primary_metric_id,
        "metric_ids": metric_ids,
        "record_count": primary_metric.get("record_count") or 0,
        "status": question_status,
        "confidence": answer_result.get("confidence"),
        "source": primary_metric.get("source"),
        "doctype": primary_metric.get("doctype") or (answer_result.get("doctypes")[0] if answer_result.get("doctypes") else None),
        "doctypes": answer_result.get("doctypes"),
        "resolved_fields": primary_metric.get("resolved_fields") or [],
        "support_status": question.get("support_status"),
        "requirement_reference": question.get("requirement_reference"),
        "limitations": question.get("limitations")
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
    if source.get("truncated"):
        data_quality.append({
            "criterion": subcriterion,
            "check": "Source row limit",
            "source": source.get("doctype") or "",
            "status": "truncated",
            "detail": "Source count reached the configured row limit and may be understated."
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
    if metric.get("truncated"):
        data_quality.append({
            "criterion": subcriterion,
            "check": metric.get("label"),
            "source": metric.get("doctype") or metric.get("source"),
            "status": "truncated",
            "detail": "The metric reached the configured row limit and may be understated."
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
        "api_method": "ucc_analytics_criterion_4",
        "platform_version": "2.1.0-admission-intelligence",
        "status": "decision_useful_catalogue",
        "mapping_basis": "verified_existing_sources_plus_policy_named_sources_without_unverified_field_claims",
        "translation_note": "Student Admission UCC and Student Applicant may both display as Shortlisted Applicants; backend names are preserved.",
        "generated_at": frappe.utils.now(),
        "action": action,
        "subcriterion": subcriterion,
        "row_limit": row_limit,
        "query_stats": query_stats
    },
    "admission_intelligence": admission_intelligence,
    "policy": POLICY_REGISTRY.get(subcriterion),
    "filters": filters,
    "sources": sources,
    "metrics": metrics,
    "questions": questions,
    "requirements": requirement_evidence,
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
        "requirements": requirement_evidence,
        "exceptions": exceptions,
        "data_quality": data_quality,
        "admission_intelligence": admission_intelligence
    },
    "warnings": [
        "Criterion 4 source availability depends on site-installed UCC custom DocTypes and signed-in user permissions.",
        "A readable source or existing record is not proof that a student-protection control is complete, compliant or effective.",
        "Document-only, partial and unsupported controls are returned explicitly and are never converted to zero.",
        "Working-day ageing excludes weekends only because the current API has no approved Singapore public-holiday calendar.",
        "The controlled procedures contain unresolved rule conflicts for cooling-off units, FPS monthly deadlines, movement processing standards, deferment grounds and attendance source-of-truth.",
        "Most Criterion 4 procedures apply only to SSG-registered courses, but no verified regulatory-course scope field is currently mapped.",
        "Student Support Services Version 2.3 is used from the cover and Version Control, although internal page headers still show Version 2.2."
    ]
}

result = standardise_response_contract(result, "Criterion 4", "ucc_analytics_criterion_4", action, subcriterion, row_limit)

if action == "source_status":
    result["source_status"] = sources

if action == "policy_registry":
    result["registry"] = POLICY_REGISTRY

if action == "requirement_registry":
    result["registry"] = REQUIREMENT_REGISTRY
    result["requirement_evidence"] = requirement_evidence

if action == "question_registry":
    result["registry"] = QUESTION_REGISTRY

if action == "drilldown":
    selected_config = None
    for configured_metric in CONFIG[subcriterion]["metrics"]:
        if configured_metric.get("id") == metric_id:
            selected_config = configured_metric
            break
    if not selected_config:
        frappe.throw("Unknown Criterion 4 metric.")
    result["drilldown"] = evaluate_metric(selected_config, True)

result = standardise_response_contract(result, "Criterion 4", "ucc_analytics_criterion_4", action, subcriterion, row_limit)

frappe.response["message"] = result