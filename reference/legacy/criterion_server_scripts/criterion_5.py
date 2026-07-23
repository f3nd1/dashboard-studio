"""
UCC Intelligence Platform Server Script

Visible name:
    UCC Analytics - Criterion 5

Script type:
    API

API method:
    ucc_analytics_criterion_5

Purpose:
    Return permission-aware, policy-aligned analytics for EduTrust Criterion 5
    without treating record existence, status completion or source availability
    as proof of compliance or effectiveness.

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
requested_subcriterion = payload.get("subcriterion") or "5.1.1"
filters = payload.get("filters") or {}
if not isinstance(filters, dict):
    filters = {}
metric_id = payload.get("metric_id")
question_id = payload.get("question_id")
page = payload.get("page") or 1
page_size = payload.get("page_size") or 50
row_limit = payload.get("limit") or 500

try:
    page = max(1, int(page))
except Exception:
    page = 1
try:
    page_size = max(1, min(int(page_size), 200))
except Exception:
    page_size = 50
try:
    row_limit = max(1, min(int(row_limit), 2000))
except Exception:
    row_limit = 500

ALLOWED_ACTIONS = [
    "summary", "source_status", "policy_registry", "requirement_registry",
    "question_registry", "drilldown"
]
if action not in ALLOWED_ACTIONS:
    frappe.throw("Unsupported Criterion 5 action.")

SUBCRITERION_ALIASES = {"5.4": "5.4.1", "5.5": "5.5.1"}
canonical_subcriterion = SUBCRITERION_ALIASES.get(requested_subcriterion) or requested_subcriterion

POLICY_REGISTRY = {'overview': {'title': 'Criterion 5 Overview',
              'policy': 'PPD-ALI Criterion 5 controlled procedure set',
              'version': 'Mixed controlled versions',
              'criterion': '5'},
 '5.1.1': {'title': 'Course Design and Development',
           'policy': 'PPD-ALI-CD-5.1.1',
           'version': '2.2',
           'last_updated': '15 January 2026',
           'criterion': '5.1.1'},
 '5.1.2': {'title': 'Course Review',
           'policy': 'PPD-ALI-CD-5.1.2',
           'version': '2.2',
           'last_updated': '15 January 2026',
           'criterion': '5.1.2'},
 '5.2.1': {'title': 'Course Planning',
           'policy': 'PPD-ALI-CM-5.2.1',
           'version': '2.2',
           'last_updated': '15 January 2026',
           'criterion': '5.2.1'},
 '5.2.2': {'title': 'Course Delivery',
           'policy': 'PPD-ALI-CM-5.2.2',
           'version': '2.2',
           'last_updated': '15 January 2026',
           'criterion': '5.2.2'},
 '5.3.1': {'title': 'Partnerships',
           'policy': 'PPD-ALI-CD-5.3.1',
           'version': '1.2',
           'last_updated': '15 January 2026',
           'criterion': '5.3.1'},
 '5.4.1': {'title': 'Student Learning',
           'policy': 'PPD-ALI-CM-5.4.1',
           'version': '2.2',
           'last_updated': '15 January 2026',
           'criterion': '5.4.1'},
 '5.5.1': {'title': 'Student Assessment',
           'policy': 'PPD-ALI-CM-5.5.1',
           'version': '2.2',
           'last_updated': '15 January 2026',
           'criterion': '5.5.1'}}
SOURCE_CANDIDATES = {'course_proposal': ['Course Proposal'],
 'course': ['Program'],
 'module': ['Course'],
 'course_review': ['Course Review'],
 'module_review': ['Module Review'],
 'student_intake': ['Student Batch Name'],
 'module_schedule': ['Course Schedule'],
 'student_admission': ['Student Admission UCC'],
 'module_class': ['Student Group'],
 'classroom_observation': ['Classroom Observation'],
 'student_attendance': ['Student Attendance'],
 'partnership_management': ['Partnerships Agreement Management'],
 'student_log': ['Student Log'],
 'assessment_plan': ['Assessment Plan'],
 'assessment_result': ['Assessment Result'],
 'assessment_verification': ['Assessment Verification'],
 'assessment_failure_notification': ['Assessment Failure Notification'],
 'assessment_email_sender': ['Assessment Email Sender'],
 'quality_meeting': ['Quality Meeting'],
 'quality_action': ['Quality Action'],
 'management_review': ['Management Review']}
SOURCE_DISPLAY_NAMES = {'course_proposal': 'Course Proposal',
 'course': 'Course',
 'module': 'Module',
 'course_review': 'Course Review',
 'module_review': 'Module Review',
 'student_intake': 'Student Intake No',
 'module_schedule': 'Module Schedule',
 'student_admission': 'Shortlisted Applicants',
 'module_class': 'Module Class Details',
 'classroom_observation': 'Classroom Observation',
 'student_attendance': 'Student Attendance',
 'partnership_management': 'Partnerships Agreement Management',
 'student_log': 'Student Log',
 'assessment_plan': 'Assessment Plan',
 'assessment_result': 'Assessment Result',
 'assessment_verification': 'Assessment Verification',
 'assessment_failure_notification': 'Assessment Failure Notification',
 'assessment_email_sender': 'Assessment Email Sender',
 'quality_meeting': 'Meeting Minutes',
 'quality_action': 'Quality Action',
 'management_review': 'Management Review'}
SAFE_FIELDS = {'course_proposal': ['name',
                     'course_title',
                     'approval_status',
                     'proposed_date',
                     'decision_date',
                     'ssg_approval_date',
                     'docstatus',
                     'modified'],
 'course': ['name', 'program_name', 'department', 'modified'],
 'module': ['name', 'course_name', 'department', 'topics', 'assessment_criteria', 'modified'],
 'course_review': ['name',
                   'course',
                   'review_date',
                   'next_review_date',
                   'review_type',
                   'review_status',
                   'recommendation_implementation_status',
                   'modified'],
 'module_review': ['name',
                   'course',
                   'module',
                   'module_class_details',
                   'date_of_review',
                   'status',
                   'type_of_review',
                   'recommendation_implementation_status',
                   'modified'],
 'student_intake': ['name', 'batch_name', 'modified'],
 'module_schedule': ['name',
                     'student_group',
                     'instructor',
                     'instructor_name',
                     'naming_series',
                     'program',
                     'course',
                     'color',
                     'schedule_date',
                     'room',
                     'from_time',
                     'to_time',
                     'title',
                     'modified'],
 'student_admission': ['name', 'modified'],
 'module_class': ['name',
                  'student_group_name',
                  'academic_year',
                  'program',
                  'course',
                  'disabled',
                  'max_strength',
                  'custom_module_status',
                  'custom_instructor',
                  'custom_instructor_full_name',
                  'modified'],
 'classroom_observation': ['name',
                           'date_of_observation',
                           'type_of_observation',
                           'module_class_details',
                           'course',
                           'module_name',
                           'name_of_teacher',
                           'platform_delivery',
                           'prior_notice',
                           'observers_signature',
                           'teachers_signature',
                           'areas_text',
                           'modified'],
 'student_attendance': ['name',
                        'student',
                        'course_schedule',
                        'date',
                        'student_group',
                        'status',
                        'duration_attended',
                        'expected_duration',
                        'modified'],
 'partnership_management': ['name',
                            'agreement_title',
                            'party_name',
                            'type',
                            'status',
                            'agreement_date',
                            'expiry_date',
                            'average_identification_and_selection_score',
                            'modified'],
 'student_log': ['name', 'modified'],
 'assessment_plan': ['name',
                     'assessment_name',
                     'student_group',
                     'course',
                     'program',
                     'academic_year',
                     'schedule_date',
                     'room',
                     'examiner',
                     'supervisor',
                     'maximum_assessment_score',
                     'modified'],
 'assessment_result': ['name',
                       'assessment_plan',
                       'program',
                       'course',
                       'academic_year',
                       'student',
                       'student_name',
                       'student_group',
                       'maximum_score',
                       'total_score',
                       'grade',
                       'modified'],
 'assessment_verification': ['name', 'modified'],
 'assessment_failure_notification': ['name', 'modified'],
 'assessment_email_sender': ['name', 'modified'],
 'quality_meeting': ['name', 'modified'],
 'quality_action': ['name', 'modified'],
 'management_review': ['name', 'modified']}
SOURCES_BY_SECTION = {'overview': ['course_proposal',
              'course',
              'module',
              'course_review',
              'module_review',
              'student_intake',
              'module_schedule',
              'student_admission',
              'module_class',
              'classroom_observation',
              'student_attendance',
              'partnership_management',
              'student_log',
              'assessment_plan',
              'assessment_result',
              'assessment_verification',
              'assessment_failure_notification',
              'assessment_email_sender',
              'quality_meeting',
              'quality_action',
              'management_review'],
 '5.1.1': ['course_proposal', 'course', 'module', 'course_review'],
 '5.1.2': ['module_review', 'course_review', 'course', 'module'],
 '5.2.1': ['student_intake',
           'module_schedule',
           'student_admission',
           'module_class'],
 '5.2.2': ['module_schedule', 'module_class', 'classroom_observation', 'student_attendance'],
 '5.3.1': ['partnership_management'],
 '5.4.1': ['student_log', 'student_attendance', 'assessment_result'],
 '5.5.1': ['assessment_plan',
           'assessment_result',
           'assessment_verification',
           'assessment_failure_notification',
           'assessment_email_sender',
           'quality_meeting',
           'student_log',
           'student_attendance',
           'module_review',
           'course_review']}
METRIC_CONFIG = {'overview': [{'id': 'o-current-attention',
               'label': 'Current verified attention indicators',
               'mode': 'attention_count',
               'source': None},
              {'id': 'o-pending-approvals',
               'label': 'Pending governance approvals and registrations',
               'mode': 'unsupported',
               'source': None,
               'message': 'Approval authority, due date and registration evidence are not available as one verified '
                          'cross-Criterion 5 structure.'},
              {'id': 'o-overdue-controls',
               'label': 'Overdue verified control timelines',
               'mode': 'unsupported',
               'source': None,
               'message': 'Population-specific due dates are not consistently linked across the current Criterion 5 '
                          'sources. The timetable standard also conflicts between one week and three calendar days.'},
              {'id': 'o-evidence-gaps',
               'label': 'Mandatory requirements without usable live evidence',
               'mode': 'requirement_gap_count',
               'source': None},
              {'id': 'o-effectiveness-pending',
               'label': 'Completed actions awaiting effectiveness verification',
               'mode': 'unsupported',
               'source': None,
               'message': 'Implementation evidence and post-action effectiveness fields are not consistently mapped '
                          'across the Criterion 5 action records.'}],
 '5.1.1': [{'id': 'd511-proposal-population',
            'label': 'Course Proposal records in scope',
            'source': 'course_proposal',
            'mode': 'all'},
           {'id': 'd511-approved-without-ssg-date',
            'label': 'Approved-status proposals without an SSG approval date',
            'source': 'course_proposal',
            'mode': 'conditions',
            'conditions': [{'field': ['approval_status'], 'op': 'in', 'values': ['Approved', 'Accepted', 'Endorsed']},
                           {'field': ['ssg_approval_date'], 'op': 'falsy'}]},
           {'id': 'd511-artifact-readiness',
            'label': 'Course and module artefact development readiness',
            'source': 'course_proposal',
            'mode': 'unsupported',
            'message': 'Course Proposal, Course, Module and controlled artefact records are not linked through a '
                       'verified completeness, approval and version-control schema.'},
           {'id': 'd511-design-effectiveness',
            'label': 'Design validation and revision effectiveness',
            'source': 'course_review',
            'mode': 'unsupported',
            'message': 'Validation findings, assigned actions, implementation evidence and post-change effectiveness '
                       'are not linked as structured fields.'}],
 '5.1.2': [{'id': 'r512-overdue-review-records',
            'label': 'Course Review records with a past next-review date',
            'source': 'course_review',
            'mode': 'date_before_today',
            'field': ['next_review_date']},
           {'id': 'r512-review-input-completeness',
            'label': 'Completed reviews with all required inputs and approvals',
            'source': 'course_review',
            'mode': 'unsupported',
            'message': 'The required review-input checklist, applicable partner input and Academic Board decision are '
                       'not mapped as a complete structured rule.'},
           {'id': 'r512-pending-module-recommendations',
            'label': 'Module Review recommendations with a pending implementation status',
            'source': 'module_review',
            'mode': 'in',
            'field': ['recommendation_implementation_status'],
            'values': ['Not Implemented', 'Pending', 'Open']},
           {'id': 'r512-review-effectiveness',
            'label': 'Implemented review actions awaiting effectiveness verification',
            'source': 'course_review',
            'mode': 'unsupported',
            'message': 'Review-action implementation evidence and subsequent academic or operational outcome evidence '
                       'are not mapped.'}],
 '5.2.1': [{'id': 'p521-intake-readiness',
            'label': 'Planned intake academic and operational readiness',
            'source': 'student_intake',
            'mode': 'unsupported',
            'message': 'No verified cross-source rule links the intake, approved modules, schedule, venue or platform, '
                       'instructional resources, LMS, assessment and student communication evidence.'},
           {'id': 'p521-teacher-deployment-compliance',
            'label': 'Teacher deployment approval and registration compliance',
            'source': 'module_class',
            'mode': 'unsupported',
            'message': 'Teacher assignment is not linked to competence evidence, Academic Board approval and dated SSG '
                       'registration at least seven days before deployment.'},
           {'id': 'p521-planning-record-consistency',
            'label': 'Module class, schedule, admission, contract and timetable consistency',
            'source': 'module_class',
            'mode': 'unsupported',
            'message': 'Exact relationships and required fields across Module Class Details, Module Schedule, Student '
                       'Admission UCC and communication evidence are not mapped.'},
           {'id': 'p521-transition-risk-control',
            'label': 'Transition risks and planning exceptions under control',
            'source': 'quality_action',
            'mode': 'unsupported',
            'message': 'Transition-risk assessment, approved transition plan, exception owner, communication and '
                       'closure evidence are not available as a verified structured source.'}],
 '5.2.2': [{'id': 'l522-delivery-adherence',
            'label': 'Delivery adherence to approved academic artefacts',
            'source': 'module_schedule',
            'mode': 'unsupported',
            'message': 'Delivered content, approved learning outcomes, assessment alignment, authorised deviations and '
                       'corrective actions are not linked as structured evidence.'},
           {'id': 'l522-observation-records',
            'label': 'Classroom Observation records',
            'source': 'classroom_observation',
            'mode': 'all'},
           {'id': 'l522-observations-with-findings',
            'label': 'Classroom observations recording improvement areas',
            'source': 'classroom_observation',
            'mode': 'truthy',
            'field': ['areas_text', 'areas_for_improvement']},
           {'id': 'l522-intervention-effectiveness',
            'label': 'Teaching intervention effectiveness',
            'source': 'classroom_observation',
            'mode': 'unsupported',
            'message': 'Teaching intervention, follow-up, subsequent observation or feedback result, recurrence and '
                       'effectiveness decision are not linked.'}],
 '5.3.1': [{'id': 'pa531-below-selection-threshold',
            'label': 'In-scope partnership records below the 3.5 selection threshold',
            'source': 'partnership_management',
            'mode': 'conditions',
            'conditions': [{'field': ['type'],
                            'op': 'not_contains_any',
                            'values': ['Provider', 'Recruitment Agent', 'External Recruitment Agent']},
                           {'field': ['average_identification_and_selection_score'], 'op': 'lt', 'value': 3.5}],
            'unit': 'records'},
           {'id': 'pa531-expired-agreement-records',
            'label': 'Partnership management records with a past expiry date',
            'source': 'partnership_management',
            'mode': 'date_before_today',
            'field': ['expiry_date']},
           {'id': 'pa531-annual-evaluation-compliance',
            'label': 'Annual partnership evaluation compliance',
            'source': 'partnership_management',
            'mode': 'unsupported',
            'message': 'Annual evaluation date, evidence, performance score, action and management decision are not '
                       'mapped as a complete rule.'},
           {'id': 'pa531-value-effectiveness',
            'label': 'Partnership value and continuation decision effectiveness',
            'source': 'partnership_management',
            'mode': 'unsupported',
            'message': 'Verified student benefit, institutional benefit, issue action, renewal or termination decision '
                       'and post-action effectiveness are not mapped.'}],
 '5.4.1': [{'id': 'sl541-attendance-risk-records',
            'label': 'Attendance records marked absent or late',
            'source': 'student_attendance',
            'mode': 'in',
            'field': ['status'],
            'values': ['Absent', 'Late']},
           {'id': 'sl541-intervention-plan-completeness',
            'label': 'Complete and approved student intervention plans',
            'source': 'student_log',
            'mode': 'unsupported',
            'message': 'Case category, urgency, impact, priority, owner, target outcome, approval, communication and '
                       'implementation are not mapped as a complete intervention plan.'},
           {'id': 'sl541-follow-up-compliance',
            'label': 'Student intervention follow-up and closure compliance',
            'source': 'student_log',
            'mode': 'unsupported',
            'message': 'Required follow-up date, progress, next step, closure date and closure authority are not '
                       'mapped as a consistent rule.'},
           {'id': 'sl541-intervention-effectiveness',
            'label': 'Student intervention effectiveness and recurrence',
            'source': 'student_log',
            'mode': 'unsupported',
            'message': 'Defined intended outcome, post-intervention result, effectiveness decision, recurrence and '
                       'escalation are not mapped.'}],
 '5.5.1': [{'id': 'a551-assessment-plan-records',
            'label': 'Assessment Plan records in scope',
            'source': 'assessment_plan',
            'mode': 'all'},
           {'id': 'a551-assessment-verification-records',
            'label': 'Assessment Verification records in scope',
            'source': 'assessment_verification',
            'mode': 'all'},
           {'id': 'a551-major-assessment-security',
            'label': 'Major assessment approval and security compliance',
            'source': 'quality_meeting',
            'mode': 'unsupported',
            'message': 'Major-assessment classification, Examination Board approval, version, access, handover, '
                       'reproduction and release evidence are not linked.'},
           {'id': 'a551-score-errors',
            'label': 'Assessment Result records above the recorded maximum score',
            'source': 'assessment_result',
            'mode': 'field_compare',
            'fields': [['total_score'], ['maximum_score']],
            'operator': 'gt'},
           {'id': 'a551-failure-notification-records',
            'label': 'Assessment Failure Notification records in scope',
            'source': 'assessment_failure_notification',
            'mode': 'all'},
           {'id': 'a551-result-approval-release',
            'label': 'Examination Board-approved results released through an authorised channel',
            'source': 'assessment_result',
            'mode': 'unsupported',
            'message': 'Assessment Verification, moderation, Examination Board decision and Assessment Email Sender '
                       'release evidence are not linked to each final result set.'},
           {'id': 'a551-award-approval',
            'label': 'Award eligibility and Examination Board approval compliance',
            'source': 'assessment_result',
            'mode': 'unsupported',
            'message': 'Course-specific module passes, STP status, module attendance thresholds, awarding authority, '
                       'Examination Board decision and issue date are not linked.'},
           {'id': 'a551-appeal-compliance',
            'label': 'Grade and dismissal appeal due-process and timeliness compliance',
            'source': 'student_log',
            'mode': 'unsupported',
            'message': 'Appeal type, submission date, course administration type, evidence, recommendation, '
                       'Examination Board decision, communication and follow-up are not linked.'},
           {'id': 'a551-post-assessment-effectiveness',
            'label': 'Post-assessment improvement effectiveness',
            'source': 'assessment_result',
            'mode': 'unsupported',
            'message': 'Post-assessment finding, linked Module Review or Course Review action, implementation and '
                       'later-cycle effectiveness result are not linked.'}]}
SUPPORTING_CONFIG = {'overview': [],
 '5.1.1': [{'id': 's511-proposals', 'label': 'Course Proposal records', 'source': 'course_proposal', 'mode': 'all'},
           {'id': 's511-approved-status',
            'label': 'Course Proposal records with an approved-like status',
            'source': 'course_proposal',
            'mode': 'in',
            'field': ['approval_status'],
            'values': ['Approved', 'Accepted', 'Endorsed']},
           {'id': 's511-ssg-date',
            'label': 'Course Proposal records with an SSG approval date',
            'source': 'course_proposal',
            'mode': 'truthy',
            'field': ['ssg_approval_date']},
           {'id': 's511-course-records', 'label': 'Course records', 'source': 'course', 'mode': 'all'},
           {'id': 's511-module-records', 'label': 'Module records', 'source': 'module', 'mode': 'all'},
           {'id': 's511-course-topics',
            'label': 'Module records with curriculum topics',
            'source': 'module',
            'mode': 'truthy',
            'field': ['topics', 'custom_list_of_learning_objective']},
           {'id': 's511-course-assessment-criteria',
            'label': 'Module records with assessment criteria',
            'source': 'module',
            'mode': 'truthy',
            'field': ['assessment_criteria']}],
 '5.1.2': [{'id': 's512-module-reviews', 'label': 'Module Review records', 'source': 'module_review', 'mode': 'all'},
           {'id': 's512-closed-module-reviews',
            'label': 'Module Review records with approved, completed or closed status',
            'source': 'module_review',
            'mode': 'in',
            'field': ['status'],
            'values': ['Approved', 'Completed', 'Closed']},
           {'id': 's512-course-reviews', 'label': 'Course Review records', 'source': 'course_review', 'mode': 'all'},
           {'id': 's512-closed-course-reviews',
            'label': 'Course Review records with approved, completed or closed status',
            'source': 'course_review',
            'mode': 'in',
            'field': ['review_status', 'status'],
            'values': ['Approved', 'Completed', 'Closed']},
           {'id': 's512-pending-course-recommendations',
            'label': 'Course Review recommendations with a pending implementation status',
            'source': 'course_review',
            'mode': 'in',
            'field': ['recommendation_implementation_status'],
            'values': ['Not Implemented', 'Pending', 'Open']}],
 '5.2.1': [{'id': 's521-student-intake-records',
            'label': 'Student Intake No records',
            'source': 'student_intake',
            'mode': 'all'},
           {'id': 's521-module-schedule-records',
            'label': 'Module Schedule records',
            'source': 'module_schedule',
            'mode': 'all'},
           {'id': 's521-student-admission-records',
            'label': 'Shortlisted Applicants records',
            'source': 'student_admission',
            'mode': 'all'},
           {'id': 's521-module-class-records',
            'label': 'Module Class Details records',
            'source': 'module_class',
            'mode': 'all'}],
 '5.2.2': [{'id': 's522-module-schedule-records',
            'label': 'Module Schedule records',
            'source': 'module_schedule',
            'mode': 'all'},
           {'id': 's522-module-class-records',
            'label': 'Module Class Details records',
            'source': 'module_class',
            'mode': 'all'},
           {'id': 's522-attendance-records',
            'label': 'Student Attendance records',
            'source': 'student_attendance',
            'mode': 'all'},
           {'id': 's522-observations-with-signatures',
            'label': 'Classroom observations with observer and teacher signatures',
            'source': 'classroom_observation',
            'mode': 'all_required',
            'fields': [['observers_signature'], ['teachers_signature']]}],
 '5.3.1': [{'id': 's531-partnership-records',
            'label': 'Partnerships Agreement Management records',
            'source': 'partnership_management',
            'mode': 'all'},
           {'id': 's531-expiring-90-days',
            'label': 'Partnership records expiring within 90 days',
            'source': 'partnership_management',
            'mode': 'date_next_days',
            'field': ['expiry_date'],
            'days': 90}],
 '5.4.1': [{'id': 's541-student-log-records', 'label': 'Student Log records', 'source': 'student_log', 'mode': 'all'},
           {'id': 's541-assessment-result-records',
            'label': 'Assessment Result records',
            'source': 'assessment_result',
            'mode': 'all'}],
 '5.5.1': [{'id': 's551-assessment-result-records',
            'label': 'Assessment Result records',
            'source': 'assessment_result',
            'mode': 'all'},
           {'id': 's551-graded-results',
            'label': 'Assessment Result records with a grade',
            'source': 'assessment_result',
            'mode': 'truthy',
            'field': ['grade']},
           {'id': 's551-assessment-email-records',
            'label': 'Assessment Email Sender records',
            'source': 'assessment_email_sender',
            'mode': 'all'},
           {'id': 's551-quality-meeting-records',
            'label': 'Meeting Minutes records',
            'source': 'quality_meeting',
            'mode': 'all'},
           {'id': 's551-student-log-records', 'label': 'Student Log records', 'source': 'student_log', 'mode': 'all'},
           {'id': 's551-attendance-records',
            'label': 'Student Attendance records',
            'source': 'student_attendance',
            'mode': 'all'},
           {'id': 's551-module-review-records',
            'label': 'Module Review records',
            'source': 'module_review',
            'mode': 'all'},
           {'id': 's551-course-review-records',
            'label': 'Course Review records',
            'source': 'course_review',
            'mode': 'all'}]}

# v2.0.2: additional management-question metrics
METRIC_CONFIG['overview'].extend([{'id': 'o-assessment-score-errors',
  'label': 'Assessment Result records above maximum score',
  'source': 'assessment_result',
  'mode': 'field_compare',
  'fields': [['total_score'], ['maximum_score']],
  'operator': 'gt'},
 {'id': 'o-schedules-missing-teacher',
  'label': 'Module Schedule records without a teacher',
  'source': 'module_schedule',
  'mode': 'falsy',
  'field': ['instructor']},
 {'id': 'o-proposals-missing-decision-date',
  'label': 'Course Proposal records without a decision date',
  'source': 'course_proposal',
  'mode': 'falsy',
  'field': ['decision_date']},
 {'id': 'o-partnerships-expiring-90-days',
  'label': 'Partnership records expiring within 90 days',
  'source': 'partnership_management',
  'mode': 'date_next_days',
  'field': ['expiry_date'],
  'days': 90},
 {'id': 'o-results-missing-grade',
  'label': 'Assessment Result records without a grade',
  'source': 'assessment_result',
  'mode': 'falsy',
  'field': ['grade']}])
METRIC_CONFIG['5.1.1'].extend([{'id': 'd511-stakeholder-input-completeness',
  'label': 'Proposal stakeholder-input completeness',
  'source': 'course_proposal',
  'mode': 'unsupported',
  'message': 'Required learner, employer, industry, academic and regulatory stakeholder inputs are not mapped as '
             'structured proposal evidence.'},
 {'id': 'd511-proposals-missing-proposed-date',
  'label': 'Course Proposal records without a proposed date',
  'source': 'course_proposal',
  'mode': 'falsy',
  'field': ['proposed_date']},
 {'id': 'd511-proposals-missing-decision-date',
  'label': 'Course Proposal records without a decision date',
  'source': 'course_proposal',
  'mode': 'falsy',
  'field': ['decision_date']},
 {'id': 'd511-modules-missing-topics',
  'label': 'Module records without curriculum topics',
  'source': 'module',
  'mode': 'falsy',
  'field': ['topics']},
 {'id': 'd511-modules-missing-assessment-criteria',
  'label': 'Module records without assessment criteria',
  'source': 'module',
  'mode': 'falsy',
  'field': ['assessment_criteria']}])
METRIC_CONFIG['5.1.2'].extend([{'id': 'r512-module-review-records',
  'label': 'Module Review records in scope',
  'source': 'module_review',
  'mode': 'all'},
 {'id': 'r512-reviews-missing-next-review-date',
  'label': 'Course Review records without a next review date',
  'source': 'course_review',
  'mode': 'falsy',
  'field': ['next_review_date']},
 {'id': 'r512-first-run-review-compliance',
  'label': 'New-course first-run review compliance',
  'source': 'course_review',
  'mode': 'unsupported',
  'message': 'Course launch date, first-run completion and the linked first post-hoc Course Review are not mapped.'},
 {'id': 'r512-lapsed-course-ab-decision',
  'label': 'Lapsed or materially changed course Academic Board decisions',
  'source': 'course_review',
  'mode': 'unsupported',
  'message': 'Last delivery, material-change classification, lapse duration and Academic Board maintain, deregister or '
             'reactivate decision are not linked.'},
 {'id': 'r512-stakeholder-input-coverage',
  'label': 'Course and Module Review stakeholder-input coverage',
  'source': 'course_review',
  'mode': 'unsupported',
  'message': 'Required student, teacher, employer, partner, performance and regulatory review inputs are not mapped as '
             'a complete checklist.'}])
METRIC_CONFIG['5.2.1'].extend([{'id': 'p521-student-intake-records', 'label': 'Student Intake No records', 'source': 'student_intake', 'mode': 'all'},
 {'id': 'p521-schedules-missing-teacher',
  'label': 'Module Schedule records without a teacher',
  'source': 'module_schedule',
  'mode': 'falsy',
  'field': ['instructor']},
 {'id': 'p521-schedules-missing-room',
  'label': 'Module Schedule records without a room',
  'source': 'module_schedule',
  'mode': 'falsy',
  'field': ['room']},
 {'id': 'p521-module-classes-missing-teacher',
  'label': 'Module Class Details records without an assigned teacher',
  'source': 'module_class',
  'mode': 'falsy',
  'field': ['custom_instructor']},
 {'id': 'p521-timetable-communication-compliance',
  'label': 'Timetable communication compliance',
  'source': 'module_schedule',
  'mode': 'unsupported',
  'message': 'Final timetable communication date, recipients and the approved one-week versus three-calendar-day '
             'standard are not consistently mapped.'}])
METRIC_CONFIG['5.2.2'].extend([{'id': 'l522-schedules-missing-teacher',
  'label': 'Delivered Module Schedule records without a teacher',
  'source': 'module_schedule',
  'mode': 'falsy',
  'field': ['instructor']},
 {'id': 'l522-schedules-missing-room',
  'label': 'Delivered Module Schedule records without a room',
  'source': 'module_schedule',
  'mode': 'falsy',
  'field': ['room']},
 {'id': 'l522-observations-missing-observer-signature',
  'label': 'Classroom observations without observer signature',
  'source': 'classroom_observation',
  'mode': 'falsy',
  'field': ['observers_signature']},
 {'id': 'l522-attendance-risk-records',
  'label': 'Attendance records marked absent or late',
  'source': 'student_attendance',
  'mode': 'in',
  'field': ['status'],
  'values': ['Absent', 'Late']},
 {'id': 'l522-feedback-delivery-risk-linkage',
  'label': 'Student feedback linked to delivery-risk follow-up',
  'source': 'classroom_observation',
  'mode': 'unsupported',
  'message': 'Student feedback results, affected teacher or class, assigned action and later effectiveness evidence '
             'are not linked.'}])
METRIC_CONFIG['5.3.1'].extend([{'id': 'pa531-expiring-90-days',
  'label': 'Partnership records expiring within 90 days',
  'source': 'partnership_management',
  'mode': 'date_next_days',
  'field': ['expiry_date'],
  'days': 90},
 {'id': 'pa531-missing-agreement-date',
  'label': 'Partnership records without an agreement date',
  'source': 'partnership_management',
  'mode': 'falsy',
  'field': ['agreement_date']},
 {'id': 'pa531-missing-expiry-date',
  'label': 'Partnership records without an expiry date',
  'source': 'partnership_management',
  'mode': 'falsy',
  'field': ['expiry_date']},
 {'id': 'pa531-missing-selection-score',
  'label': 'Partnership records without a selection score',
  'source': 'partnership_management',
  'mode': 'falsy',
  'field': ['average_identification_and_selection_score']},
 {'id': 'pa531-out-of-scope-records',
  'label': 'Partnership records identified as Provider or Recruitment Agent',
  'source': 'partnership_management',
  'mode': 'contains_any',
  'field': ['type'],
  'values': ['Provider', 'Recruitment Agent']}])
METRIC_CONFIG['5.4.1'].extend([{'id': 'sl541-student-log-records', 'label': 'Student Log records in scope', 'source': 'student_log', 'mode': 'all'},
 {'id': 'sl541-results-missing-grade',
  'label': 'Assessment Result records without a grade',
  'source': 'assessment_result',
  'mode': 'falsy',
  'field': ['grade']},
 {'id': 'sl541-communication-completeness',
  'label': 'Student intervention communication completeness',
  'source': 'student_log',
  'mode': 'unsupported',
  'message': 'Required communication to the student, teacher and parent or guardian, where applicable, is not mapped '
             'as structured evidence.'},
 {'id': 'sl541-recurring-support-needs',
  'label': 'Recurring learning-support needs after intervention',
  'source': 'student_log',
  'mode': 'unsupported',
  'message': 'Student, intervention category, prior closure, recurrence date and escalation decision are not linked.'},
 {'id': 'sl541-achievement-recognition',
  'label': 'Student achievement and recognition evidence',
  'source': 'assessment_result',
  'mode': 'unsupported',
  'message': 'Academic and non-academic achievement, recognition decision and certificate or award evidence are not '
             'mapped as one verified source.'}])
METRIC_CONFIG['5.5.1'].extend([{'id': 'a551-complete-plan-administration-fields',
  'label': 'Assessment Plan records with schedule, room, examiner and supervisor',
  'source': 'assessment_plan',
  'mode': 'all_required',
  'fields': [['schedule_date'], ['room'], ['examiner'], ['supervisor']]},
 {'id': 'a551-results-missing-grade',
  'label': 'Assessment Result records without a grade',
  'source': 'assessment_result',
  'mode': 'falsy',
  'field': ['grade']},
 {'id': 'a551-result-release-communications',
  'label': 'Assessment Email Sender records in scope',
  'source': 'assessment_email_sender',
  'mode': 'all'},
 {'id': 'a551-eb-meeting-records',
  'label': 'Meeting Minutes records available for Examination Board evidence',
  'source': 'quality_meeting',
  'mode': 'all'},
 {'id': 'a551-results-missing-plan-link',
  'label': 'Assessment Result records without an Assessment Plan link',
  'source': 'assessment_result',
  'mode': 'falsy',
  'field': ['assessment_plan']}])

QUESTION_REGISTRY = {'overview': [{'id': 'O-01',
               'criterion': '5',
               'question': 'Which Criterion 5 controls require management attention now, and which courses, modules, '
                           'intakes, teachers, partners, students or assessments are affected?',
               'management_purpose': 'Prioritise current exceptions',
               'why_useful': 'Aggregates only verified breach/overdue rules; groups by affected entity; no summing '
                             'overlapping records.',
               'requirement_reference': 'All seven procedures; exception management',
               'calculation': 'Requires a cross-section exception registry. Return verified exceptions separately from '
                              'data gaps.',
               'primary_source': 'All verified C5 sources',
               'required_fields': 'exception type; entity; owner; due date; status; evidence',
               'drilldown_records': 'Affected records filtered to each exception',
               'support_status': 'Requires a new DocType or child-table query',
               'metric_id': 'o-current-attention',
               'answer_mode': 'attention_summary',
               'source_keys': []},
              {'id': 'O-02',
               'criterion': '5',
               'question': 'Which Academic Board, Examination Board, Principal, HOD-ALI or SSG approvals or '
                           'registrations are pending or overdue?',
               'management_purpose': 'Escalate governance decisions',
               'why_useful': 'Separates approval authorities and prevents status labels being mistaken for approval.',
               'requirement_reference': '5.1.1, 5.1.2, 5.2.1, 5.5.1',
               'calculation': 'Count approvals due in period; exception where required approval/registration is '
                              'missing after control point.',
               'primary_source': 'Approval and registration evidence',
               'required_fields': 'authority; decision date; due date; linked record',
               'drilldown_records': 'Records with missing/pending approval',
               'support_status': 'Requires a new DocType or child-table query',
               'metric_id': 'o-pending-approvals',
               'answer_mode': 'unsupported',
               'source_keys': ['course_proposal', 'quality_meeting']},
              {'id': 'O-03',
               'criterion': '5',
               'question': 'Which verified review cycles, service standards or communication timelines have been '
                           'missed?',
               'management_purpose': 'Manage overdue controls',
               'why_useful': 'Provides an auditable overdue queue using only clarified timelines.',
               'requirement_reference': '5.1.2; 5.2.1; 5.3.1; 5.5.1',
               'calculation': 'Apply population-specific due dates; do not calculate where standards conflict or are '
                              'unspecified.',
               'primary_source': 'Review, planning, partnership and assessment records',
               'required_fields': 'population type; due date; completion date; timeline basis',
               'drilldown_records': 'Overdue records with days overdue',
               'support_status': 'Can be implemented with revised mapping',
               'metric_id': 'o-overdue-controls',
               'answer_mode': 'unsupported',
               'source_keys': ['course_review', 'partnership_management']},
              {'id': 'O-04',
               'criterion': '5',
               'question': 'Which mandatory Criterion 5 requirements have no usable live evidence or have incompatible '
                           'source mappings?',
               'management_purpose': 'Direct data remediation',
               'why_useful': 'Separates evidence gaps from operational non-compliance.',
               'requirement_reference': 'All procedures',
               'calculation': 'Requirement registry: live, partial, document-only, missing source, permission denied.',
               'primary_source': 'Requirement registry and source mapping',
               'required_fields': 'requirement; source; field; status; limitation',
               'drilldown_records': 'Requirement-to-source detail',
               'support_status': 'Requires a new DocType or child-table query',
               'metric_id': 'o-evidence-gaps',
               'answer_mode': 'evidence_gap_summary',
               'source_keys': []},
              {'id': 'O-05',
               'criterion': '5',
               'question': 'Which completed academic actions still require implementation confirmation or '
                           'effectiveness verification?',
               'management_purpose': 'Close the improvement loop',
               'why_useful': 'Prevents Completed/Closed from being treated as effective.',
               'requirement_reference': '5.1.2; 5.2.2; 5.3.1; 5.4.1; 5.5.1',
               'calculation': 'Denominator: completed actions in scope. Exception: no implementation evidence or no '
                              'post-action effectiveness result.',
               'primary_source': 'Review/action/intervention records',
               'required_fields': 'action; owner; completion; implementation; effectiveness',
               'drilldown_records': 'Actions awaiting verification',
               'support_status': 'Requires an additional field',
               'metric_id': 'o-effectiveness-pending',
               'answer_mode': 'unsupported',
               'source_keys': ['course_review', 'module_review', 'student_log', 'quality_action']}],
 '5.1.1': [{'id': 'D511-01',
            'criterion': '5.1.1',
            'question': 'Did every new course or module proposal due for decision contain all required learner, '
                        'curriculum, pedagogy, assessment, resource, risk and stakeholder design inputs?',
            'management_purpose': 'Decide proposal readiness',
            'why_useful': 'Tests design completeness rather than proposal existence.',
            'requirement_reference': 'PPD-ALI-CD-5.1.1, Approach and 7.1',
            'calculation': 'Numerator: proposals with all verified required inputs. Denominator: all new course/module '
                           'proposals due for decision in period. Missing inputs remain exceptions.',
            'primary_source': 'Course Proposal',
            'required_fields': 'proposal type; required design fields/children; decision due date',
            'drilldown_records': 'Incomplete proposals and missing inputs',
            'support_status': 'Requires an additional field',
            'metric_id': 'd511-proposal-population',
            'answer_mode': 'proposal_scope_summary',
            'source_keys': ['course_proposal']},
           {'id': 'D511-02',
            'criterion': '5.1.1',
            'question': 'Were required HOD-ALI, Principal and Academic Board approvals completed, and was SSG '
                        'registration obtained before implementation where applicable?',
            'management_purpose': 'Authorise implementation',
            'why_useful': 'Distinguishes internal review, AB approval and regulatory registration.',
            'requirement_reference': 'PPD-ALI-CD-5.1.1, 7.1',
            'calculation': 'For each proposal in scope, compare approval/registration dates with implementation date. '
                           'Cannot assess without dated evidence.',
            'primary_source': 'Course Proposal plus approval/SSG evidence',
            'required_fields': 'reviewer; authority; decision; decision date; registration date; implementation date',
            'drilldown_records': 'Proposals missing or late approvals/registration',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'd511-approved-without-ssg-date',
            'answer_mode': 'proposal_approval_summary',
            'source_keys': ['course_proposal']},
           {'id': 'D511-03',
            'criterion': '5.1.1',
            'question': 'Were all required course and module artefacts developed, approved and version-controlled '
                        'before delivery?',
            'management_purpose': 'Confirm development readiness',
            'why_useful': 'Ensures approved proposals were translated into controlled delivery artefacts.',
            'requirement_reference': 'PPD-ALI-CD-5.1.1, 7.1 / Quality Records',
            'calculation': 'Numerator: approved proposals with complete required artefact set before first delivery. '
                           'Denominator: approved proposals entering implementation.',
            'primary_source': 'Course Proposal, Course, Module and controlled artefact evidence',
            'required_fields': 'artefact type; version; approval; effective date; first delivery',
            'drilldown_records': 'Courses/modules with missing or late artefacts',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'd511-artifact-readiness',
            'answer_mode': 'unsupported',
            'source_keys': ['course_proposal', 'course', 'module']},
           {'id': 'D511-04',
            'criterion': '5.1.1',
            'question': 'Did validation and post-implementation review identify, assign and close design gaps, and was '
                        'the effect of revisions verified?',
            'management_purpose': 'Approve or escalate design changes',
            'why_useful': 'Connects validation, action and effectiveness.',
            'requirement_reference': 'PPD-ALI-CD-5.1.1, validation and continual improvement',
            'calculation': 'Track validation findings to approved action, implementation and post-change result. '
                           'Completed without effectiveness is pending verification.',
            'primary_source': 'Course Review / validation and action evidence',
            'required_fields': 'finding; action; owner; due date; implementation; effectiveness',
            'drilldown_records': 'Open design gaps and actions awaiting verification',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'd511-design-effectiveness',
            'answer_mode': 'unsupported',
            'source_keys': ['course_review', 'quality_action']}],
 '5.1.2': [{'id': 'R512-01',
            'criterion': '5.1.2',
            'question': 'Which modules and courses are due or overdue for review under the applicable midpoint, '
                        'end-of-module, first-run, biennial or ad-hoc rule?',
            'management_purpose': 'Schedule reviews',
            'why_useful': 'Applies the correct population-specific review rule.',
            'requirement_reference': 'PPD-ALI-CD-5.1.2, review scope/frequency',
            'calculation': 'Build applicable population first; due date by verified rule; exception includes missing '
                           'review record.',
            'primary_source': 'Module Review, Course Review and delivery history',
            'required_fields': 'course type; module end/midpoint; first run; last review; material change',
            'drilldown_records': 'Due/overdue courses and modules',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'r512-overdue-review-records',
            'answer_mode': 'review_due_summary',
            'source_keys': ['module_review', 'course_review', 'course', 'module']},
           {'id': 'R512-02',
            'criterion': '5.1.2',
            'question': 'Did each completed Module Review or Course Review include all required inputs and required '
                        'Academic Board or external-partner involvement?',
            'management_purpose': 'Validate review completeness',
            'why_useful': 'A review record or completed status alone is insufficient.',
            'requirement_reference': 'PPD-ALI-CD-5.1.2, review inputs and governance',
            'calculation': 'Numerator: reviews with every applicable input and approval. Denominator: reviews '
                           'completed in period.',
            'primary_source': 'Module Review, Course Review and evidence children',
            'required_fields': 'input checklist; participant; AB decision; partner feedback',
            'drilldown_records': 'Incomplete reviews and missing approvals/inputs',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'r512-review-input-completeness',
            'answer_mode': 'unsupported',
            'source_keys': ['module_review', 'course_review']},
           {'id': 'R512-03',
            'criterion': '5.1.2',
            'question': 'Were approved review recommendations assigned, implemented by the due date and supported by '
                        'evidence?',
            'management_purpose': 'Manage implementation',
            'why_useful': 'Creates a true action-implementation queue.',
            'requirement_reference': 'PPD-ALI-CD-5.1.2, 7.1/7.2',
            'calculation': 'Numerator: approved recommendations implemented on time. Denominator: approved '
                           'recommendations due in period.',
            'primary_source': 'Module Review / Course Review action plan',
            'required_fields': 'recommendation; approval; owner; due date; implementation evidence',
            'drilldown_records': 'Overdue/unimplemented recommendations',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'r512-pending-module-recommendations',
            'answer_mode': 'review_action_summary',
            'source_keys': ['module_review', 'course_review']},
           {'id': 'R512-04',
            'criterion': '5.1.2',
            'question': 'Did implemented review changes achieve the intended academic or operational result?',
            'management_purpose': 'Verify effectiveness',
            'why_useful': 'Separates implementation from effectiveness.',
            'requirement_reference': 'PPD-ALI-CD-5.1.2, continual improvement',
            'calculation': 'For implemented changes with review date reached, compare defined '
                           'baseline/target/post-change evidence; missing review is pending.',
            'primary_source': 'Review action and effectiveness evidence',
            'required_fields': 'measure; baseline; target; post-result; review date; conclusion',
            'drilldown_records': 'Implemented actions awaiting/failed effectiveness',
            'support_status': 'Requires an additional field',
            'metric_id': 'r512-review-effectiveness',
            'answer_mode': 'unsupported',
            'source_keys': ['module_review', 'course_review', 'quality_action']}],
 '5.2.1': [{'id': 'P521-01',
            'criterion': '5.2.1',
            'question': 'Was each planned intake academically and operationally ready before commencement, including '
                        'approved modules, schedules, venue/platform, instructional and support resources?',
            'management_purpose': 'Approve intake readiness',
            'why_useful': 'Provides one intake-level readiness decision with evidence.',
            'requirement_reference': 'PPD-ALI-CM-5.2.1, Approach / Appendix C',
            'calculation': 'Numerator: planned intakes with every applicable readiness control completed by '
                           'commencement. Denominator: intakes commencing in period.',
            'primary_source': 'Student Intake No, Module Schedule, Module Class Details and readiness evidence',
            'required_fields': 'intake; start date; module; schedule; resource checklist; approval',
            'drilldown_records': 'Intakes with missing/late readiness controls',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'p521-intake-readiness',
            'answer_mode': 'unsupported',
            'source_keys': ['student_intake', 'module_schedule', 'module_class']},
           {'id': 'P521-02',
            'criterion': '5.2.1',
            'question': 'Were all deployed teachers suitably qualified, Academic Board-approved and registered with '
                        'SSG at least seven days before deployment?',
            'management_purpose': 'Prevent non-compliant deployment',
            'why_useful': 'Assignment alone is not compliant deployment.',
            'requirement_reference': 'PPD-ALI-CM-5.2.1, Approach',
            'calculation': 'Numerator: teacher-module deployments meeting all three controls by T-7 days. Denominator: '
                           'all deployments in period.',
            'primary_source': 'Module Class Details plus teacher approval/registration evidence',
            'required_fields': 'teacher; module; deployment date; AB decision; SSG registration date',
            'drilldown_records': 'Non-compliant teacher deployments',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'p521-teacher-deployment-compliance',
            'answer_mode': 'unsupported',
            'source_keys': ['module_class']},
           {'id': 'P521-03',
            'criterion': '5.2.1',
            'question': 'Were Module Class Details, schedules, admission/contract dates and timetable communications '
                        'complete and consistent before the applicable start date?',
            'management_purpose': 'Resolve planning exceptions',
            'why_useful': 'Tests linked-record consistency and communication, not record volume.',
            'requirement_reference': 'PPD-ALI-CM-5.2.1, 7.1 / Quality Records',
            'calculation': 'Linked-record completeness by intake/class. Timetable timeliness remains cannot-assess '
                           'until one-week versus three-day conflict is resolved.',
            'primary_source': 'Student Intake No, Module Schedule, Module Class Details, Shortlisted Applicants',
            'required_fields': 'linked IDs; dates; communication timestamp; recipient groups',
            'drilldown_records': 'Classes with missing/inconsistent records or late communication',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'p521-planning-record-consistency',
            'answer_mode': 'unsupported',
            'source_keys': ['module_class', 'module_schedule', 'student_admission']},
           {'id': 'P521-04',
            'criterion': '5.2.1',
            'question': 'Were transition risks, timetable changes and resource exceptions assessed, approved, '
                        'communicated and closed before they affected delivery?',
            'management_purpose': 'Escalate planning risk',
            'why_useful': 'Makes transition and change controls operational.',
            'requirement_reference': 'PPD-ALI-CM-5.2.1, Appendices G/H',
            'calculation': 'Exception where identified risk/change lacks assessment, authority, communication or '
                           'closure by control date.',
            'primary_source': 'Transition-risk/change evidence',
            'required_fields': 'risk/change; impact; owner; approval; communication; closure',
            'drilldown_records': 'Open or late planning risks/changes',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'p521-transition-risk-control',
            'answer_mode': 'unsupported',
            'source_keys': ['quality_action']}],
 '5.2.2': [{'id': 'L522-01',
            'criterion': '5.2.2',
            'question': 'Did each delivered class follow the approved learning outcomes, content, assessment alignment '
                        'and delivery artefacts, and were deviations authorised before use?',
            'management_purpose': 'Control delivery adherence',
            'why_useful': 'Directly tests approved delivery rather than attendance volume.',
            'requirement_reference': 'PPD-ALI-CM-5.2.2, Approach',
            'calculation': 'Sample/monitor delivered classes against approved artefact version. Exception for '
                           'unauthorised omission/substitution/deviation.',
            'primary_source': 'Module Class Details, approved artefacts and deviation evidence',
            'required_fields': 'class; artefact version; deviation; approval; date',
            'drilldown_records': 'Classes with unauthorised or unsupported deviations',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'l522-delivery-adherence',
            'answer_mode': 'unsupported',
            'source_keys': ['module_schedule', 'module_class']},
           {'id': 'L522-02',
            'criterion': '5.2.2',
            'question': 'Were required classroom observations completed for every applicable new teacher, new-module '
                        'teacher, poor-feedback case and annual teacher population?',
            'management_purpose': 'Ensure observation coverage',
            'why_useful': 'Uses the documented observation population.',
            'requirement_reference': 'PPD-ALI-CM-5.2.2, Approach',
            'calculation': 'Numerator: applicable teacher-module cases observed in required period. Denominator: all '
                           'applicable cases.',
            'primary_source': 'Classroom Observation and teacher/class population',
            'required_fields': 'teacher; module; trigger; due date; observation date',
            'drilldown_records': 'Missing/overdue observations',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'l522-observation-records',
            'answer_mode': 'observation_coverage_summary',
            'source_keys': ['classroom_observation', 'module_class']},
           {'id': 'L522-03',
            'criterion': '5.2.2',
            'question': 'Did observation or feedback findings result in an assigned, timely and completed follow-up '
                        'action?',
            'management_purpose': 'Close teaching-quality findings',
            'why_useful': 'Signatures do not prove corrective follow-up.',
            'requirement_reference': 'PPD-ALI-CM-5.2.2, 7.1',
            'calculation': 'Numerator: findings with approved action completed by due date. Denominator: findings '
                           'requiring action.',
            'primary_source': 'Classroom Observation, feedback and action evidence',
            'required_fields': 'finding; severity; action; owner; due date; completion',
            'drilldown_records': 'Open/overdue teaching actions',
            'support_status': 'Requires an additional field',
            'metric_id': 'l522-observations-with-findings',
            'answer_mode': 'observation_followup_summary',
            'source_keys': ['classroom_observation', 'quality_action']},
           {'id': 'L522-04',
            'criterion': '5.2.2',
            'question': 'Were teaching interventions effective, and which teachers or classes still require management '
                        'attention?',
            'management_purpose': 'Evaluate teaching support',
            'why_useful': 'Links intervention to a defined post-action result.',
            'requirement_reference': 'PPD-ALI-CM-5.2.2, continual improvement',
            'calculation': 'Compare pre/post observation, feedback or performance measure against intended result. '
                           'Missing follow-up is pending.',
            'primary_source': 'Observation, survey/performance and intervention evidence',
            'required_fields': 'teacher/class; intervention; baseline; target; post-result; decision',
            'drilldown_records': 'Failed/pending effectiveness cases',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'l522-intervention-effectiveness',
            'answer_mode': 'unsupported',
            'source_keys': ['classroom_observation', 'quality_action']}],
 '5.3.1': [{'id': 'PA531-01',
            'criterion': '5.3.1',
            'question': 'Did every in-scope partnership complete the approved selection rubric and achieve the minimum '
                        'overall score of 3.5 before appointment?',
            'management_purpose': 'Approve partner selection',
            'why_useful': 'Applies correct scope and threshold.',
            'requirement_reference': 'PPD-ALI-CD-5.3.1, Scope / Appendix D',
            'calculation': 'Numerator: appointed in-scope partners with complete rubric and score ≥3.5. Denominator: '
                           'appointed partners in period.',
            'primary_source': 'Partnerships Agreement Management and selection rubric',
            'required_fields': 'partner category; rubric items; overall score; appointment date',
            'drilldown_records': 'Partners appointed without compliant selection',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'pa531-below-selection-threshold',
            'answer_mode': 'partnership_selection_summary',
            'source_keys': ['partnership_management']},
           {'id': 'PA531-02',
            'criterion': '5.3.1',
            'question': 'Does every active in-scope partner have a current signed renewable agreement containing the '
                        'required duration, terms, responsibilities and expectations?',
            'management_purpose': 'Control agreement validity',
            'why_useful': 'Agreement count/expiry alone is insufficient.',
            'requirement_reference': 'PPD-ALI-CD-5.3.1, Approach/7.1',
            'calculation': 'Numerator: active partners with complete current signed renewable agreement. Denominator: '
                           'active in-scope partners.',
            'primary_source': 'Partnerships Agreement Management and signed agreement',
            'required_fields': 'start/end; signatures; renewable; required terms checklist',
            'drilldown_records': 'Active partners with missing/incomplete/expired agreement',
            'support_status': 'Requires an additional field',
            'metric_id': 'pa531-expired-agreement-records',
            'answer_mode': 'partnership_agreement_summary',
            'source_keys': ['partnership_management']},
           {'id': 'PA531-03',
            'criterion': '5.3.1',
            'question': 'Was each active partnership evaluated annually, did it meet the approved performance '
                        'threshold, and were issues assigned for action?',
            'management_purpose': 'Manage partner performance',
            'why_useful': 'Uses partnership evaluation, not Provider Rating.',
            'requirement_reference': 'PPD-ALI-CD-5.3.1, 7.1 / Appendix E',
            'calculation': 'Annual denominator: active in-scope partners due for evaluation. Flag missing evaluation, '
                           'score below approved threshold or unresolved findings.',
            'primary_source': 'Partnerships Agreement Management and evaluation rubric',
            'required_fields': 'evaluation date; score; findings; owner; due date',
            'drilldown_records': 'Overdue/below-threshold/unresolved partners',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'pa531-annual-evaluation-compliance',
            'answer_mode': 'unsupported',
            'source_keys': ['partnership_management']},
           {'id': 'PA531-04',
            'criterion': '5.3.1',
            'question': 'Were renewal, adjustment or termination decisions supported by performance evidence, and did '
                        'the partnership produce measurable value to UCC and students?',
            'management_purpose': 'Decide partnership continuation',
            'why_useful': 'Connects annual review to outcome and decision.',
            'requirement_reference': 'PPD-ALI-CD-5.3.1, purpose/7.1',
            'calculation': 'For decisions in period, require evaluation evidence, outcome measures and authorised '
                           'decision. Effectiveness cannot be inferred from active status.',
            'primary_source': 'Partnerships Agreement Management and outcome evidence',
            'required_fields': 'benefits; KPI/result; decision; authority; date; follow-up',
            'drilldown_records': 'Decisions without evidence or value assessment',
            'support_status': 'Requires an additional field',
            'metric_id': 'pa531-value-effectiveness',
            'answer_mode': 'unsupported',
            'source_keys': ['partnership_management', 'quality_action']}],
 '5.4.1': [{'id': 'SL541-01',
            'criterion': '5.4.1',
            'question': 'Which students in SSG-approved courses met defined academic, attendance, participation or '
                        'teacher-observation indicators, and were their support needs assessed promptly?',
            'management_purpose': 'Identify students needing support',
            'why_useful': 'Creates a student-level early-warning queue.',
            'requirement_reference': 'PPD-ALI-CM-5.4.1, Scope/Approach',
            'calculation': 'Applicable population: students in SSG-approved courses. Flag indicator breach without '
                           'Helpdesk assessment/referral by defined control date; no invented timeline.',
            'primary_source': 'Assessment, attendance, teacher observation and Student Log',
            'required_fields': 'student; course; indicator; trigger date; assessment/referral date',
            'drilldown_records': 'Students with unassessed support indicators',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'sl541-attendance-risk-records',
            'answer_mode': 'student_learning_indicator_summary',
            'source_keys': ['student_attendance', 'assessment_result', 'student_log']},
           {'id': 'SL541-02',
            'criterion': '5.4.1',
            'question': 'Did each assessed support case have a complete prioritised intervention plan, responsible '
                        'owner, approval, communication and implemented action?',
            'management_purpose': 'Ensure appropriate intervention',
            'why_useful': 'Tests the intervention plan and implementation stages.',
            'requirement_reference': 'PPD-ALI-CM-5.4.1, 7.1 / Appendix D',
            'calculation': 'Numerator: cases with required plan fields and implemented action. Denominator: cases '
                           'assessed as requiring intervention.',
            'primary_source': 'Student Log and intervention evidence',
            'required_fields': 'urgency; impact; category; plan; owner; approval; communication; implementation',
            'drilldown_records': 'Incomplete or unimplemented intervention cases',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'sl541-intervention-plan-completeness',
            'answer_mode': 'unsupported',
            'source_keys': ['student_log']},
           {'id': 'SL541-03',
            'criterion': '5.4.1',
            'question': 'Were follow-up reviews and progress updates completed and documented until formal closure?',
            'management_purpose': 'Manage open cases',
            'why_useful': 'Prevents tickets or logs from being treated as completed support.',
            'requirement_reference': 'PPD-ALI-CM-5.4.1, 7.1',
            'calculation': 'Flag open cases without required follow-up/milestone or closed cases without closure '
                           'evidence.',
            'primary_source': 'Student Log / intervention follow-up',
            'required_fields': 'follow-up date; progress; next step; closure date; closure authority',
            'drilldown_records': 'Cases overdue for follow-up or unsupported closure',
            'support_status': 'Requires an additional field',
            'metric_id': 'sl541-follow-up-compliance',
            'answer_mode': 'unsupported',
            'source_keys': ['student_log']},
           {'id': 'SL541-04',
            'criterion': '5.4.1',
            'question': 'Did closed interventions achieve the intended result, and which recurring or unresolved needs '
                        'require revised action or management escalation?',
            'management_purpose': 'Verify intervention effectiveness',
            'why_useful': 'Separates closure from effectiveness and recurrence.',
            'requirement_reference': 'PPD-ALI-CM-5.4.1, effectiveness/continual improvement',
            'calculation': 'Denominator: closed cases due for effectiveness review. Success requires defined intended '
                           'outcome and verified post-result; recurrence/failed result is exception.',
            'primary_source': 'Student Log and outcome evidence',
            'required_fields': 'intended outcome; post-result; effectiveness decision; recurrence; escalation',
            'drilldown_records': 'Closed cases awaiting/failed effectiveness',
            'support_status': 'Requires an additional field',
            'metric_id': 'sl541-intervention-effectiveness',
            'answer_mode': 'unsupported',
            'source_keys': ['student_log', 'quality_action']}],
 '5.5.1': [{'id': 'A551-01',
            'criterion': '5.5.1',
            'question': 'Did every applicable module have a complete approved Assessment Plan, and were assessment '
                        'types, weightings, schedule, venue, criteria, result-release and appeal information '
                        'communicated before assessment?',
            'management_purpose': 'Approve assessment planning and communication',
            'why_useful': 'Plan existence alone is insufficient.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, Approach/7.1',
            'calculation': 'Numerator: module offerings with complete plan and dated communication before control '
                           'point. Denominator: module offerings with assessment in period.',
            'primary_source': 'Assessment Plan, Module Class Details and LMS/communication evidence',
            'required_fields': 'module/class; plan fields; approval; communication date; recipients',
            'drilldown_records': 'Modules with missing/incomplete/late assessment information',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-assessment-plan-records',
            'answer_mode': 'assessment_plan_summary',
            'source_keys': ['assessment_plan', 'module_class']},
           {'id': 'A551-02',
            'criterion': '5.5.1',
            'question': 'Were assessment instruments aligned with approved learning outcomes and internally verified, '
                        'with required revisions closed before administration?',
            'management_purpose': 'Authorise assessment instruments',
            'why_useful': 'Tests validity and verification, not examiner presence.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, Setting/Vetting and 7.2',
            'calculation': 'Numerator: instruments with completed IV and closed revisions before assessment date. '
                           'Denominator: instruments administered in period.',
            'primary_source': 'Assessment instrument and Assessment Verification',
            'required_fields': 'learning outcomes; verifier; checks; findings; revision closure; administration date',
            'drilldown_records': 'Unverified or unresolved instruments',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-assessment-verification-records',
            'answer_mode': 'assessment_verification_summary',
            'source_keys': ['assessment_verification', 'assessment_plan']},
           {'id': 'A551-03',
            'criterion': '5.5.1',
            'question': 'Did major assessments receive Examination Board approval, and were assessment materials '
                        'stored, reproduced, transferred and released under approved security controls?',
            'management_purpose': 'Protect major-assessment integrity',
            'why_useful': 'Combines major approval and material security control point.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, EB Oversight and Secure Storage',
            'calculation': 'Flag major assessment without EB decision before use or without required security/handover '
                           'evidence.',
            'primary_source': 'Meeting Minutes/EB evidence and assessment security record',
            'required_fields': 'major flag; EB decision; version; access; handover; release time',
            'drilldown_records': 'Major/security exceptions',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-major-assessment-security',
            'answer_mode': 'unsupported',
            'source_keys': ['quality_meeting', 'assessment_plan']},
           {'id': 'A551-04',
            'criterion': '5.5.1',
            'question': 'Were assessment administration, code-of-conduct briefings and integrity incidents managed and '
                        'documented according to the approved controls?',
            'management_purpose': 'Manage assessment administration risk',
            'why_useful': 'Supports immediate operational exception management.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, Code of Conduct / 7.1',
            'calculation': 'For scheduled assessments, require applicable briefing/admin evidence; integrity incidents '
                           'require report, decision and follow-up. Score-above-maximum remains data-quality '
                           'exception.',
            'primary_source': 'Assessment Plan, incident/Student Log and data-quality checks',
            'required_fields': 'assessment; invigilator; briefing; incident; action; result error',
            'drilldown_records': 'Administration/integrity/data-quality exceptions',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-score-errors',
            'answer_mode': 'assessment_admin_summary',
            'source_keys': ['assessment_plan', 'assessment_result', 'student_log']},
           {'id': 'A551-05',
            'criterion': '5.5.1',
            'question': 'Were marking, moderation and Internal Verifier sampling completed using approved rubrics, and '
                        'were marker variances resolved and documented?',
            'management_purpose': 'Confirm result reliability',
            'why_useful': 'Grade presence does not prove moderated marking.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, 7.2 / Appendix E',
            'calculation': 'Numerator: assessment result sets with required marking/IV/moderation and resolved '
                           'variance. Denominator: result sets due for finalisation.',
            'primary_source': 'Assessment Verification and Assessment Result',
            'required_fields': 'marker; rubric; sample; IV; variance; decision; grade change',
            'drilldown_records': 'Unverified/unmoderated/unresolved result sets',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-assessment-verification-records',
            'answer_mode': 'assessment_marking_summary',
            'source_keys': ['assessment_verification', 'assessment_result']},
           {'id': 'A551-06',
            'criterion': '5.5.1',
            'question': 'Did failure notifications, resubmissions, resits, deferrals, extensions and late penalties '
                        'follow the applicable evidence, approval, timing and communication rules?',
            'management_purpose': 'Ensure fair follow-up',
            'why_useful': 'Provides traceable case controls for failed or adjusted assessments.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, 7.2 / Resitting / Appendix F',
            'calculation': 'Case-specific rules: appeal/resit request within 7 working days after event where stated; '
                           'extensions ≥5 working days before deadline; no invented decision SLA.',
            'primary_source': 'Assessment Failure Notification, Student Log and request evidence',
            'required_fields': 'case type; event date; request date; evidence; decision; communication; new '
                               'date/penalty',
            'drilldown_records': 'Cases breaching applicable controls or cannot-assess',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-failure-notification-records',
            'answer_mode': 'assessment_failure_summary',
            'source_keys': ['assessment_failure_notification', 'student_log']},
           {'id': 'A551-07',
            'criterion': '5.5.1',
            'question': 'Were final results internally verified, moderated and approved by the Examination Board '
                        'before release through the authorised channel?',
            'management_purpose': 'Authorise result release',
            'why_useful': 'Separates grade entry from governance and communication.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, 7.3',
            'calculation': 'Numerator: released result sets with IV/moderation and EB approval dated before release. '
                           'Denominator: result sets released in period.',
            'primary_source': 'Assessment Verification, Meeting Minutes, Assessment Result, Assessment Email Sender',
            'required_fields': 'verification; EB decision/date; result update; release date/channel',
            'drilldown_records': 'Results pending approval or released prematurely',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-result-approval-release',
            'answer_mode': 'unsupported',
            'source_keys': ['assessment_verification',
                            'quality_meeting',
                            'assessment_result',
                            'assessment_email_sender']},
           {'id': 'A551-08',
            'criterion': '5.5.1',
            'question': 'Did every proposed award meet the applicable module-pass and attendance requirements and '
                        'receive Examination Board approval before issuance?',
            'management_purpose': 'Approve awards',
            'why_useful': 'Academic results alone do not establish award eligibility.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, Course Completion / Appendix G',
            'calculation': 'For each award candidate, evaluate course-specific module passes plus 75% non-STP or 90% '
                           'STP attendance per module, then EB approval before issue.',
            'primary_source': 'Assessment Result, attendance, award and Meeting Minutes evidence',
            'required_fields': 'student; course; module passes; STP status; attendance; EB decision; issue date',
            'drilldown_records': 'Ineligible/unapproved/premature awards',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-award-approval',
            'answer_mode': 'unsupported',
            'source_keys': ['assessment_result', 'student_attendance', 'quality_meeting']},
           {'id': 'A551-09',
            'criterion': '5.5.1',
            'question': 'Were grade and dismissal appeals submitted, reviewed and decided by the Examination Board '
                        'fairly and within the applicable timelines, with final communication and follow-up recorded?',
            'management_purpose': 'Control appeal due process',
            'why_useful': 'Creates an auditable appeal queue.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, Grade/Dismissal Appeal and 7.4',
            'calculation': 'Submission exception after 7 working days; outcome overdue after 4 weeks internal or 8 '
                           'weeks external. Require EB decision and communication.',
            'primary_source': 'Assessment Verification, Meeting Minutes, Assessment Email Sender and Student Log',
            'required_fields': 'appeal type; dates; evidence; recommendation; EB decision; communication; follow-up',
            'drilldown_records': 'Late/incomplete appeals and missing decisions',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-appeal-compliance',
            'answer_mode': 'unsupported',
            'source_keys': ['assessment_verification',
                            'quality_meeting',
                            'assessment_email_sender',
                            'student_log']},
           {'id': 'A551-10',
            'criterion': '5.5.1',
            'question': 'Did post-assessment analysis identify performance, alignment or fairness issues, link them to '
                        'Module Review or Course Review actions, and verify improvement in a later cycle?',
            'management_purpose': 'Improve assessment system',
            'why_useful': 'Closes the assessment-review-effectiveness loop.',
            'requirement_reference': 'PPD-ALI-CM-5.5.1, Post-Assessment Review',
            'calculation': 'For result sets due for analysis, require documented findings, approved linked action, '
                           'implementation and subsequent effectiveness result.',
            'primary_source': 'Assessment Result, Module Review, Course Review and action evidence',
            'required_fields': 'distribution/trend; finding; linked action; owner; post-result; conclusion',
            'drilldown_records': 'Missing analysis, unlinked actions or failed effectiveness',
            'support_status': 'Requires a new DocType or child-table query',
            'metric_id': 'a551-post-assessment-effectiveness',
            'answer_mode': 'unsupported',
            'source_keys': ['assessment_result', 'module_review', 'course_review', 'quality_action']}]}

# v2.0.2: five additional management questions per dashboard section
QUESTION_REGISTRY['overview'].extend([{'id': 'O-06',
  'criterion': '5',
  'question': 'Which assessment-result records contain scores above the recorded maximum and therefore require '
              'correction before management reporting?',
  'management_purpose': 'Prevent decisions based on invalid assessment data',
  'why_useful': 'Identifies a verified data-quality exception rather than treating an impossible score as academic '
                'performance.',
  'requirement_reference': 'PPD-ALI-CM-5.5.1; assessment accuracy and result management',
  'calculation': 'Numerator: Assessment Result records where total_score exceeds maximum_score. Denominator: all '
                 'readable Assessment Result records in the selected scope. Missing scores are cannot-assess, not '
                 'compliant.',
  'primary_source': 'Assessment Result',
  'required_fields': 'assessment_plan; student; total_score; maximum_score',
  'drilldown_records': 'Result records where total_score is greater than maximum_score',
  'support_status': 'Can be implemented now',
  'metric_id': 'o-assessment-score-errors',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'These records require correction before result, award or performance analysis is relied '
                             'upon.',
  'source_keys': ['assessment_result']},
 {'id': 'O-07',
  'criterion': '5',
  'question': 'Which scheduled classes have no teacher recorded and therefore require immediate planning verification?',
  'management_purpose': 'Prevent unstaffed course delivery',
  'why_useful': 'Provides a direct staffing-data exception queue without claiming that an assigned teacher is approved '
                'or registered.',
  'requirement_reference': 'PPD-ALI-CM-5.2.1; staff deployment and operational readiness',
  'calculation': 'Numerator: Module Schedule records with no instructor. Denominator: all readable Module Schedule '
                 'records in scope. Drill down to the affected schedule and class.',
  'primary_source': 'Module Schedule',
  'required_fields': 'student_group; program; course; schedule_date; instructor',
  'drilldown_records': 'Module Schedule records with blank instructor',
  'support_status': 'Can be implemented now',
  'metric_id': 'o-schedules-missing-teacher',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'A blank teacher field is a planning-data exception; teacher competence, Academic Board '
                             'approval and SSG registration remain separate controls.',
  'source_keys': ['module_schedule']},
 {'id': 'O-08',
  'criterion': '5',
  'question': 'Which Course Proposal records have no decision date and therefore lack decision traceability?',
  'management_purpose': 'Improve proposal governance traceability',
  'why_useful': 'Separates missing decision evidence from proposal approval status.',
  'requirement_reference': 'PPD-ALI-CD-5.1.1; Course Proposal and development governance',
  'calculation': 'Numerator: Course Proposal records with blank decision_date. Denominator: all readable Course '
                 'Proposal records in scope.',
  'primary_source': 'Course Proposal',
  'required_fields': 'name; approval_status; proposed_date; decision_date',
  'drilldown_records': 'Course Proposal records with no decision date',
  'support_status': 'Can be implemented now',
  'metric_id': 'o-proposals-missing-decision-date',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should confirm whether a decision was never made or was made but not '
                             'recorded.',
  'source_keys': ['course_proposal']},
 {'id': 'O-09',
  'criterion': '5',
  'question': 'Which partnership records expire within the next 90 days and require renewal, adjustment or termination '
              'planning?',
  'management_purpose': 'Avoid partnership agreement lapses',
  'why_useful': 'Creates a forward-looking renewal queue while leaving the final decision to management.',
  'requirement_reference': 'PPD-ALI-CD-5.3.1; partnership maintenance and evaluation',
  'calculation': 'Numerator: in-scope readable partnership records with expiry_date from today through the next 90 '
                 'days. Denominator: readable partnership records with an expiry date.',
  'primary_source': 'Partnerships Agreement Management',
  'required_fields': 'party_name; type; status; expiry_date',
  'drilldown_records': 'Partnership records expiring within 90 days',
  'support_status': 'Can be implemented now',
  'metric_id': 'o-partnerships-expiring-90-days',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'The queue supports timely review but does not by itself prove that an agreement is in '
                             'scope, signed, renewable or effective.',
  'source_keys': ['partnership_management']},
 {'id': 'O-10',
  'criterion': '5',
  'question': 'Which Assessment Result records have no grade and may obstruct result approval, release or '
              'student-learning analysis?',
  'management_purpose': 'Resolve incomplete result records',
  'why_useful': 'Identifies incomplete result data without assuming that a missing grade means failure.',
  'requirement_reference': 'PPD-ALI-CM-5.5.1; result management and Examination Board oversight',
  'calculation': 'Numerator: Assessment Result records with blank grade. Denominator: all readable Assessment Result '
                 'records in scope.',
  'primary_source': 'Assessment Result',
  'required_fields': 'assessment_plan; student; total_score; grade',
  'drilldown_records': 'Assessment Result records with no grade',
  'support_status': 'Can be implemented now',
  'metric_id': 'o-results-missing-grade',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should determine whether grading is pending, not applicable or incompletely '
                             'recorded.',
  'source_keys': ['assessment_result']}])
QUESTION_REGISTRY['5.1.1'].extend([{'id': 'D511-05',
  'criterion': '5.1.1',
  'question': 'Did each proposal contain the required learner, employer, industry, academic and regulatory stakeholder '
              'input before approval?',
  'management_purpose': 'Confirm evidence-based course design',
  'why_useful': 'Prevents an approved status from being treated as proof that stakeholder evidence was considered.',
  'requirement_reference': 'PPD-ALI-CD-5.1.1; analysis and Course Proposal design inputs',
  'calculation': 'Numerator: proposals with every required stakeholder input documented before approval. Denominator: '
                 'proposals due for decision. Missing input is incomplete.',
  'primary_source': 'Course Proposal and stakeholder evidence',
  'required_fields': 'stakeholder type; input date; finding; response; approval linkage',
  'drilldown_records': 'Proposals with missing stakeholder-input categories',
  'support_status': 'Requires an additional field',
  'metric_id': 'd511-stakeholder-input-completeness',
  'answer_mode': 'unsupported',
  'source_keys': ['course_proposal']},
 {'id': 'D511-06',
  'criterion': '5.1.1',
  'question': 'Which Course Proposal records lack a proposed date and therefore cannot support reliable design-cycle '
              'timeliness analysis?',
  'management_purpose': 'Improve proposal timeline evidence',
  'why_useful': 'Creates a precise evidence-completeness queue.',
  'requirement_reference': 'PPD-ALI-CD-5.1.1; Course Proposal initiation and development',
  'calculation': 'Numerator: proposals with blank proposed_date. Denominator: all readable proposals in scope.',
  'primary_source': 'Course Proposal',
  'required_fields': 'name; proposed_date; approval_status',
  'drilldown_records': 'Course Proposal records with blank proposed_date',
  'support_status': 'Can be implemented now',
  'metric_id': 'd511-proposals-missing-proposed-date',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Without the initiation date, management cannot assess proposal ageing or development '
                             'timeliness.',
  'source_keys': ['course_proposal']},
 {'id': 'D511-07',
  'criterion': '5.1.1',
  'question': 'Which Course Proposal records lack a decision date and therefore require governance-record completion?',
  'management_purpose': 'Complete proposal decision records',
  'why_useful': 'Provides a direct record-level follow-up queue.',
  'requirement_reference': 'PPD-ALI-CD-5.1.1; approval and governance evidence',
  'calculation': 'Numerator: proposals with blank decision_date. Denominator: all readable proposals in scope.',
  'primary_source': 'Course Proposal',
  'required_fields': 'name; approval_status; decision_date',
  'drilldown_records': 'Course Proposal records with blank decision_date',
  'support_status': 'Can be implemented now',
  'metric_id': 'd511-proposals-missing-decision-date',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'A blank date does not prove that no decision occurred; it shows that the current record '
                             'does not evidence it.',
  'source_keys': ['course_proposal']},
 {'id': 'D511-08',
  'criterion': '5.1.1',
  'question': 'Which Module records have no curriculum topics recorded and require curriculum-documentation review?',
  'management_purpose': 'Identify incomplete module curriculum records',
  'why_useful': 'Supports artefact-readiness follow-up while avoiding a conclusion on curriculum quality.',
  'requirement_reference': 'PPD-ALI-CD-5.1.1; module design and development artefacts',
  'calculation': 'Numerator: readable Module records with blank topics. Denominator: readable Module records in scope.',
  'primary_source': 'Module',
  'required_fields': 'name; course_name; topics',
  'drilldown_records': 'Module records with blank topics',
  'support_status': 'Can be implemented now',
  'metric_id': 'd511-modules-missing-topics',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Blank topics indicate incomplete structured data; the approved curriculum may still '
                             'exist in another controlled artefact.',
  'source_keys': ['module']},
 {'id': 'D511-09',
  'criterion': '5.1.1',
  'question': 'Which Module records have no assessment criteria recorded and require assessment-design review?',
  'management_purpose': 'Identify incomplete assessment-design records',
  'why_useful': 'Highlights missing structured criteria without claiming that no approved assessment artefact exists '
                'elsewhere.',
  'requirement_reference': 'PPD-ALI-CD-5.1.1; assessment design and module development',
  'calculation': 'Numerator: readable Module records with blank assessment_criteria. Denominator: readable Module '
                 'records in scope.',
  'primary_source': 'Module',
  'required_fields': 'name; course_name; assessment_criteria',
  'drilldown_records': 'Module records with blank assessment_criteria',
  'support_status': 'Can be implemented now',
  'metric_id': 'd511-modules-missing-assessment-criteria',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should verify the approved assessment artefact and update the structured '
                             'record where applicable.',
  'source_keys': ['module']}])
QUESTION_REGISTRY['5.1.2'].extend([{'id': 'R512-05',
  'criterion': '5.1.2',
  'question': 'How many Module Review records are available for the selected scope, and can they be matched to the '
              'required midpoint or end-of-module review population?',
  'management_purpose': 'Establish the review population before calculating compliance',
  'why_useful': 'Separates record volume from review-cycle compliance.',
  'requirement_reference': 'PPD-ALI-CD-5.1.2; module-review timing and frequency',
  'calculation': 'Count readable Module Review records. Do not calculate a completion rate until the applicable module '
                 'population and timing rule are linked.',
  'primary_source': 'Module Review',
  'required_fields': 'course; module; module class; date; review type; status',
  'drilldown_records': 'Readable Module Review records',
  'support_status': 'Can be implemented with revised mapping',
  'metric_id': 'r512-module-review-records',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'The count is a population indicator only and does not prove that all due reviews were '
                             'completed.',
  'source_keys': ['module_review']},
 {'id': 'R512-06',
  'criterion': '5.1.2',
  'question': 'Which Course Review records have no next review date and therefore cannot support future-cycle '
              'monitoring?',
  'management_purpose': 'Complete review scheduling evidence',
  'why_useful': 'Creates a specific review-calendar data-quality queue.',
  'requirement_reference': 'PPD-ALI-CD-5.1.2; scheduled review cycle',
  'calculation': 'Numerator: Course Review records with blank next_review_date. Denominator: readable Course Review '
                 'records in scope.',
  'primary_source': 'Course Review',
  'required_fields': 'course; review_date; next_review_date; review_type; status',
  'drilldown_records': 'Course Review records with blank next_review_date',
  'support_status': 'Can be implemented now',
  'metric_id': 'r512-reviews-missing-next-review-date',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should confirm the applicable rule before setting the next review date.',
  'source_keys': ['course_review']},
 {'id': 'R512-07',
  'criterion': '5.1.2',
  'question': 'Were new courses reviewed after their first completed run, with the required inputs and decision '
              'recorded?',
  'management_purpose': 'Confirm first-run course evaluation',
  'why_useful': 'Targets the specific new-course post-hoc review requirement.',
  'requirement_reference': 'PPD-ALI-CD-5.1.2; new-course review after first run',
  'calculation': 'Numerator: new courses completing their first run with a complete linked Course Review and decision. '
                 'Denominator: new courses whose first run ended in the period.',
  'primary_source': 'Course, delivery history and Course Review',
  'required_fields': 'course status; first-run completion date; linked review; decision',
  'drilldown_records': 'New courses missing or late first-run review',
  'support_status': 'Requires a new DocType or child-table query',
  'metric_id': 'r512-first-run-review-compliance',
  'answer_mode': 'unsupported',
  'source_keys': ['course_review', 'course']},
 {'id': 'R512-08',
  'criterion': '5.1.2',
  'question': 'Did lapsed, materially changed or reactivated courses receive the required Academic Board decision '
              'before continuation or reactivation?',
  'management_purpose': 'Control lapsed and changed course decisions',
  'why_useful': 'Prevents a generic review status from replacing the required population-specific decision.',
  'requirement_reference': 'PPD-ALI-CD-5.1.2; review schedule, lapse and reactivation rules',
  'calculation': 'Separate populations by last delivery and material change. Require the applicable Academic Board '
                 'maintain, deregister or reactivation decision.',
  'primary_source': 'Course history, Course Review and Academic Board evidence',
  'required_fields': 'last run; change type; lapse duration; AB decision/date',
  'drilldown_records': 'Courses missing the applicable Academic Board decision',
  'support_status': 'Requires a new DocType or child-table query',
  'metric_id': 'r512-lapsed-course-ab-decision',
  'answer_mode': 'unsupported',
  'source_keys': ['course_review', 'course']},
 {'id': 'R512-09',
  'criterion': '5.1.2',
  'question': 'Did each Course Review and Module Review include the required student, teacher, performance, industry, '
              'partner and regulatory inputs applicable to that review?',
  'management_purpose': 'Confirm review-input completeness',
  'why_useful': 'Distinguishes a review record from a complete evidence-based review.',
  'requirement_reference': 'PPD-ALI-CD-5.1.2; review-input requirements and appendices',
  'calculation': 'Numerator: reviews containing every applicable required input. Denominator: reviews completed in the '
                 'period. Missing applicable input is incomplete.',
  'primary_source': 'Course Review, Module Review and linked evidence',
  'required_fields': 'input category; source; date; finding; review linkage',
  'drilldown_records': 'Reviews with missing input categories',
  'support_status': 'Requires an additional field',
  'metric_id': 'r512-stakeholder-input-coverage',
  'answer_mode': 'unsupported',
  'source_keys': ['course_review', 'module_review']}])
QUESTION_REGISTRY['5.2.1'].extend([{'id': 'P521-05',
  'criterion': '5.2.1',
  'question': 'How many Student Intake No records are available for planning reconciliation in the selected scope?',
  'management_purpose': 'Establish the intake planning population',
  'why_useful': 'Uses the actual backend Student Batch Name DocType while displaying the approved translated label.',
  'requirement_reference': 'PPD-ALI-CM-5.2.1; intake and course-planning records',
  'calculation': 'Count readable Student Batch Name records displayed as Student Intake No. The count alone does not '
                 'prove readiness.',
  'primary_source': 'Student Intake No',
  'required_fields': 'batch_name',
  'drilldown_records': 'Readable Student Intake No records',
  'support_status': 'Can be implemented now',
  'metric_id': 'p521-student-intake-records',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Use this population for reconciliation with Module Schedule, Module Class Details and '
                             'student-admission records.',
  'source_keys': ['student_intake']},
 {'id': 'P521-06',
  'criterion': '5.2.1',
  'question': 'Which Module Schedule records have no teacher recorded and require staffing follow-up?',
  'management_purpose': 'Resolve unstaffed schedule records',
  'why_useful': 'Provides a direct operational planning queue.',
  'requirement_reference': 'PPD-ALI-CM-5.2.1; staff deployment and scheduling',
  'calculation': 'Numerator: Module Schedule records with blank instructor. Denominator: readable Module Schedule '
                 'records in scope.',
  'primary_source': 'Module Schedule',
  'required_fields': 'student_group; program; course; schedule_date; instructor',
  'drilldown_records': 'Module Schedule records with blank instructor',
  'support_status': 'Can be implemented now',
  'metric_id': 'p521-schedules-missing-teacher',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Teacher approval, competence and SSG registration must still be verified separately.',
  'source_keys': ['module_schedule']},
 {'id': 'P521-07',
  'criterion': '5.2.1',
  'question': 'Which Module Schedule records have no room recorded and require venue or platform readiness '
              'verification?',
  'management_purpose': 'Resolve missing delivery-location planning',
  'why_useful': 'Identifies incomplete schedule records before commencement.',
  'requirement_reference': 'PPD-ALI-CM-5.2.1; venue and platform readiness',
  'calculation': 'Numerator: Module Schedule records with blank room. Denominator: readable Module Schedule records in '
                 'scope.',
  'primary_source': 'Module Schedule',
  'required_fields': 'student_group; course; schedule_date; room',
  'drilldown_records': 'Module Schedule records with blank room',
  'support_status': 'Can be implemented now',
  'metric_id': 'p521-schedules-missing-room',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'A blank room requires verification of physical venue or approved online-platform '
                             'arrangements.',
  'source_keys': ['module_schedule']},
 {'id': 'P521-08',
  'criterion': '5.2.1',
  'question': 'Which Module Class Details records have no assigned teacher and require deployment reconciliation?',
  'management_purpose': 'Complete module-class staffing records',
  'why_useful': 'Finds inconsistencies between class setup and schedule deployment.',
  'requirement_reference': 'PPD-ALI-CM-5.2.1; teacher assignment and resource allocation',
  'calculation': 'Numerator: Module Class Details records with blank custom_instructor. Denominator: readable Module '
                 'Class Details records in scope.',
  'primary_source': 'Module Class Details',
  'required_fields': 'name; program; course; custom_instructor',
  'drilldown_records': 'Module Class Details records with no assigned teacher',
  'support_status': 'Can be implemented now',
  'metric_id': 'p521-module-classes-missing-teacher',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should reconcile the class record with the Module Schedule and approved '
                             'deployment evidence.',
  'source_keys': ['module_class']},
 {'id': 'P521-09',
  'criterion': '5.2.1',
  'question': 'Were final timetables communicated to students and teachers within the approved standard before '
              'commencement?',
  'management_purpose': 'Confirm timely timetable communication',
  'why_useful': 'Addresses a key readiness and student-information control.',
  'requirement_reference': 'PPD-ALI-CM-5.2.1; timetable communication',
  'calculation': 'Do not calculate until the one-week versus three-calendar-day standard is formally clarified. '
                 'Thereafter compare final communication date with commencement for every applicable class.',
  'primary_source': 'Module Schedule and communication evidence',
  'required_fields': 'final timetable date; communication date; recipient coverage; commencement date',
  'drilldown_records': 'Late, incomplete or unsupported timetable communications',
  'support_status': 'Requires an additional field',
  'metric_id': 'p521-timetable-communication-compliance',
  'answer_mode': 'unsupported',
  'source_keys': ['module_schedule']}])
QUESTION_REGISTRY['5.2.2'].extend([{'id': 'L522-05',
  'criterion': '5.2.2',
  'question': 'Which delivered Module Schedule records have no teacher recorded and require delivery-record correction '
              'or escalation?',
  'management_purpose': 'Identify potentially unstaffed delivered sessions',
  'why_useful': 'Supports immediate exception follow-up without assuming whether delivery occurred.',
  'requirement_reference': 'PPD-ALI-CM-5.2.2; course delivery and resource management',
  'calculation': 'Numerator: Module Schedule records in scope with blank instructor. Denominator: readable schedule '
                 'records.',
  'primary_source': 'Module Schedule',
  'required_fields': 'student_group; course; schedule_date; instructor',
  'drilldown_records': 'Module Schedule records with blank instructor',
  'support_status': 'Can be implemented now',
  'metric_id': 'l522-schedules-missing-teacher',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should verify actual delivery, substitution approval and record correction.',
  'source_keys': ['module_schedule']},
 {'id': 'L522-06',
  'criterion': '5.2.2',
  'question': 'Which delivered Module Schedule records have no room recorded and require delivery-location '
              'verification?',
  'management_purpose': 'Confirm delivery-location evidence',
  'why_useful': 'Identifies incomplete delivery records affecting audit traceability.',
  'requirement_reference': 'PPD-ALI-CM-5.2.2; delivery resources and monitoring',
  'calculation': 'Numerator: Module Schedule records with blank room. Denominator: readable schedule records in scope.',
  'primary_source': 'Module Schedule',
  'required_fields': 'student_group; schedule_date; room',
  'drilldown_records': 'Module Schedule records with blank room',
  'support_status': 'Can be implemented now',
  'metric_id': 'l522-schedules-missing-room',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Verify whether the session used an approved physical room or online platform and update '
                             'the record.',
  'source_keys': ['module_schedule']},
 {'id': 'L522-07',
  'criterion': '5.2.2',
  'question': 'Which Classroom Observation records lack the observer signature and therefore require evidence '
              'completion?',
  'management_purpose': 'Complete observation evidence',
  'why_useful': 'Creates a precise observation-record follow-up queue.',
  'requirement_reference': 'PPD-ALI-CM-5.2.2; classroom observation and teaching monitoring',
  'calculation': 'Numerator: Classroom Observation records with blank observers_signature. Denominator: readable '
                 'observations in scope.',
  'primary_source': 'Classroom Observation',
  'required_fields': 'date; teacher; observer signature; teacher signature',
  'drilldown_records': 'Classroom Observation records with no observer signature',
  'support_status': 'Can be implemented now',
  'metric_id': 'l522-observations-missing-observer-signature',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'The missing signature affects evidence completeness but does not determine the '
                             'observation outcome.',
  'source_keys': ['classroom_observation']},
 {'id': 'L522-08',
  'criterion': '5.2.2',
  'question': 'Which attendance records are marked absent or late and may indicate class-level delivery or engagement '
              'risks requiring review?',
  'management_purpose': 'Identify delivery-related engagement signals',
  'why_useful': 'Uses attendance only as an indicator, not as proof of teaching effectiveness.',
  'requirement_reference': 'PPD-ALI-CM-5.2.2; monitoring delivery effectiveness',
  'calculation': 'Numerator: attendance records with status Absent or Late. Denominator: readable attendance records '
                 'in scope. Analyse by class and student before action.',
  'primary_source': 'Student Attendance',
  'required_fields': 'student; course schedule; date; status',
  'drilldown_records': 'Absent or late attendance records grouped by class and student',
  'support_status': 'Can be implemented now',
  'metric_id': 'l522-attendance-risk-records',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should look for concentration, recurrence and linkage to feedback or '
                             'observation findings.',
  'source_keys': ['student_attendance']},
 {'id': 'L522-09',
  'criterion': '5.2.2',
  'question': 'Were student-feedback delivery risks linked to the affected teacher or class, assigned for follow-up '
              'and subsequently verified as resolved?',
  'management_purpose': 'Close student-feedback delivery issues',
  'why_useful': 'Connects feedback to accountable improvement rather than reporting survey volume.',
  'requirement_reference': 'PPD-ALI-CM-5.2.2; student feedback, performance appraisal and follow-up',
  'calculation': 'Numerator: applicable feedback findings linked to teacher or class with completed action and later '
                 'verification. Denominator: feedback findings requiring action.',
  'primary_source': 'Student feedback, Classroom Observation and action evidence',
  'required_fields': 'feedback finding; teacher/class; owner; due date; action; post-review',
  'drilldown_records': 'Unlinked, overdue or ineffective feedback actions',
  'support_status': 'Requires a new DocType or child-table query',
  'metric_id': 'l522-feedback-delivery-risk-linkage',
  'answer_mode': 'unsupported',
  'source_keys': ['classroom_observation']}])
QUESTION_REGISTRY['5.3.1'].extend([{'id': 'PA531-05',
  'criterion': '5.3.1',
  'question': 'Which in-scope partnership records expire within the next 90 days and require a documented continuation '
              'decision?',
  'management_purpose': 'Prepare timely partnership renewal decisions',
  'why_useful': 'Provides a forward-looking expiry queue.',
  'requirement_reference': 'PPD-ALI-CD-5.3.1; partnership maintenance and renewal',
  'calculation': 'Numerator: partnership records with expiry_date from today through 90 days. Denominator: readable '
                 'records with expiry dates. Confirm scope before decision.',
  'primary_source': 'Partnerships Agreement Management',
  'required_fields': 'party; type; status; expiry_date',
  'drilldown_records': 'Records expiring within 90 days',
  'support_status': 'Can be implemented now',
  'metric_id': 'pa531-expiring-90-days',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should combine the expiry queue with evaluation results and agreement '
                             'evidence.',
  'source_keys': ['partnership_management']},
 {'id': 'PA531-06',
  'criterion': '5.3.1',
  'question': 'Which partnership records have no agreement date and require agreement-evidence completion?',
  'management_purpose': 'Complete agreement commencement evidence',
  'why_useful': 'Identifies a clear agreement-record gap.',
  'requirement_reference': 'PPD-ALI-CD-5.3.1; signed agreement and record maintenance',
  'calculation': 'Numerator: readable partnership records with blank agreement_date. Denominator: readable partnership '
                 'records in scope.',
  'primary_source': 'Partnerships Agreement Management',
  'required_fields': 'party; agreement_date; status',
  'drilldown_records': 'Partnership records with blank agreement_date',
  'support_status': 'Can be implemented now',
  'metric_id': 'pa531-missing-agreement-date',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'A blank date requires verification against the signed agreement; it does not by itself '
                             'prove no agreement exists.',
  'source_keys': ['partnership_management']},
 {'id': 'PA531-07',
  'criterion': '5.3.1',
  'question': 'Which active partnership records have no expiry date and cannot support renewal-cycle monitoring?',
  'management_purpose': 'Complete agreement expiry evidence',
  'why_useful': 'Prevents open-ended or incomplete records from escaping review.',
  'requirement_reference': 'PPD-ALI-CD-5.3.1; renewable agreement and ongoing oversight',
  'calculation': 'Numerator: partnership records with blank expiry_date. Denominator: readable partnership records in '
                 'scope. Active status must be confirmed in drill-down.',
  'primary_source': 'Partnerships Agreement Management',
  'required_fields': 'party; type; status; expiry_date',
  'drilldown_records': 'Partnership records with blank expiry_date',
  'support_status': 'Can be implemented now',
  'metric_id': 'pa531-missing-expiry-date',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should verify whether the agreement is renewable, perpetual or incompletely '
                             'recorded.',
  'source_keys': ['partnership_management']},
 {'id': 'PA531-08',
  'criterion': '5.3.1',
  'question': 'Which partnership records have no documented selection score and require selection-evidence review?',
  'management_purpose': 'Complete partner-selection evidence',
  'why_useful': 'Separates missing selection evidence from failing the 3.5 threshold.',
  'requirement_reference': 'PPD-ALI-CD-5.3.1; Partnership Selection Rubric',
  'calculation': 'Numerator: records with blank average_identification_and_selection_score. Denominator: readable '
                 'in-scope partnership records.',
  'primary_source': 'Partnerships Agreement Management',
  'required_fields': 'party; type; selection score',
  'drilldown_records': 'Records with blank selection score',
  'support_status': 'Can be implemented now',
  'metric_id': 'pa531-missing-selection-score',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should confirm whether selection occurred and whether the result was recorded '
                             'in the correct field.',
  'source_keys': ['partnership_management']},
 {'id': 'PA531-09',
  'criterion': '5.3.1',
  'question': 'Which records are identified as Providers or Recruitment Agents and should be excluded from Criterion '
              '5.3.1 partnership performance reporting?',
  'management_purpose': 'Maintain correct Criterion 5.3.1 scope',
  'why_useful': 'Prevents supplier or recruitment-agent records from distorting partnership results.',
  'requirement_reference': 'PPD-ALI-CD-5.3.1; Scope exclusions',
  'calculation': 'Count records whose type contains Provider or Recruitment Agent. Verify and route them to the '
                 'applicable provider or Criterion 3 control.',
  'primary_source': 'Partnerships Agreement Management',
  'required_fields': 'party; type; status',
  'drilldown_records': 'Records classified as Provider or Recruitment Agent',
  'support_status': 'Can be implemented now',
  'metric_id': 'pa531-out-of-scope-records',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'These records should not be included in the in-scope partnership denominator unless '
                             'their classification is corrected.',
  'source_keys': ['partnership_management']}])
QUESTION_REGISTRY['5.4.1'].extend([{'id': 'SL541-05',
  'criterion': '5.4.1',
  'question': 'How many Student Log records are available for student-learning review, and which cannot be reliably '
              'classified as learning-support interventions?',
  'management_purpose': 'Establish the intervention evidence population',
  'why_useful': 'Prevents every Student Log entry from being treated as a support case.',
  'requirement_reference': 'PPD-ALI-CM-5.4.1; intervention cycle and record traceability',
  'calculation': 'Count readable Student Log records. Classification as an intervention requires category, trigger, '
                 'student, owner, action and outcome fields.',
  'primary_source': 'Student Log',
  'required_fields': 'student; category; trigger; owner; action; status; outcome',
  'drilldown_records': 'Readable Student Log records with classification status',
  'support_status': 'Can be implemented with revised mapping',
  'metric_id': 'sl541-student-log-records',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'The count is evidence volume only and does not prove intervention coverage or '
                             'effectiveness.',
  'source_keys': ['student_log']},
 {'id': 'SL541-06',
  'criterion': '5.4.1',
  'question': 'Which Assessment Result records have no grade and may prevent timely identification of students '
              'requiring learning support?',
  'management_purpose': 'Resolve missing academic indicators',
  'why_useful': 'Identifies incomplete result data relevant to support identification.',
  'requirement_reference': 'PPD-ALI-CM-5.4.1; academic monitoring and support identification',
  'calculation': 'Numerator: Assessment Result records with blank grade. Denominator: readable Assessment Result '
                 'records in scope.',
  'primary_source': 'Assessment Result',
  'required_fields': 'student; course; assessment_plan; total_score; grade',
  'drilldown_records': 'Assessment Result records with no grade',
  'support_status': 'Can be implemented now',
  'metric_id': 'sl541-results-missing-grade',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'A missing grade is a data-completeness issue, not proof that the student failed or '
                             'requires intervention.',
  'source_keys': ['assessment_result']},
 {'id': 'SL541-07',
  'criterion': '5.4.1',
  'question': 'Were students, teachers and parents or guardians, where applicable, informed of the intervention plan, '
              'responsibilities and follow-up expectations?',
  'management_purpose': 'Confirm intervention communication',
  'why_useful': 'Ensures support actions are understood and traceable.',
  'requirement_reference': 'PPD-ALI-CM-5.4.1; intervention actions, communication and follow-up',
  'calculation': 'Numerator: applicable intervention cases with all required communication and acknowledgement '
                 'evidence. Denominator: cases requiring communication.',
  'primary_source': 'Student Log and communication evidence',
  'required_fields': 'recipient; date; channel; acknowledgement; linked plan',
  'drilldown_records': 'Cases with missing required communication or acknowledgement',
  'support_status': 'Requires an additional field',
  'metric_id': 'sl541-communication-completeness',
  'answer_mode': 'unsupported',
  'source_keys': ['student_log']},
 {'id': 'SL541-08',
  'criterion': '5.4.1',
  'question': 'Which students show recurring learning-support indicators after a prior intervention and require '
              'revised action or escalation?',
  'management_purpose': 'Escalate recurring support needs',
  'why_useful': 'Focuses management on recurrence rather than closure status alone.',
  'requirement_reference': 'PPD-ALI-CM-5.4.1; follow-up, evaluation and escalation',
  'calculation': 'Identify the same student and support category recurring after prior intervention closure within the '
                 'verified review period.',
  'primary_source': 'Student Log, results and attendance',
  'required_fields': 'student; category; prior action; closure; recurrence; escalation',
  'drilldown_records': 'Students with recurring indicators after intervention',
  'support_status': 'Requires a new DocType or child-table query',
  'metric_id': 'sl541-recurring-support-needs',
  'answer_mode': 'unsupported',
  'source_keys': ['student_log', 'assessment_result', 'student_attendance']},
 {'id': 'SL541-09',
  'criterion': '5.4.1',
  'question': 'Were academic and other student achievements appropriately recorded, recognised and supported by '
              'evidence?',
  'management_purpose': 'Confirm achievement recognition',
  'why_useful': 'Covers the procedure requirement beyond deficit-based intervention monitoring.',
  'requirement_reference': 'PPD-ALI-CM-5.4.1; recognition of academic and other achievements',
  'calculation': 'Numerator: eligible achievements with documented recognition and evidence. Denominator: achievements '
                 'due for recognition under the approved mechanism.',
  'primary_source': 'Assessment Result and recognition evidence',
  'required_fields': 'student; achievement type; eligibility; recognition decision; evidence',
  'drilldown_records': 'Eligible achievements lacking recognition evidence',
  'support_status': 'Requires a new DocType or child-table query',
  'metric_id': 'sl541-achievement-recognition',
  'answer_mode': 'unsupported',
  'source_keys': ['assessment_result']}])
QUESTION_REGISTRY['5.5.1'].extend([{'id': 'A551-11',
  'criterion': '5.5.1',
  'question': 'How many Assessment Plan records contain schedule, room, examiner and supervisor information, and which '
              'plans require administrative completion?',
  'management_purpose': 'Complete assessment administration planning',
  'why_useful': 'Identifies basic administration readiness without treating those fields as full assessment approval.',
  'requirement_reference': 'PPD-ALI-CM-5.5.1; assessment planning and administration',
  'calculation': 'Numerator: readable Assessment Plan records with all four mapped fields. Denominator: all readable '
                 'Assessment Plan records in scope.',
  'primary_source': 'Assessment Plan',
  'required_fields': 'schedule_date; room; examiner; supervisor',
  'drilldown_records': 'Plans missing one or more administration fields',
  'support_status': 'Can be implemented now',
  'metric_id': 'a551-complete-plan-administration-fields',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'The count confirms mapped administration fields only; approval, verification and '
                             'communication remain separate controls.',
  'source_keys': ['assessment_plan']},
 {'id': 'A551-12',
  'criterion': '5.5.1',
  'question': 'Which Assessment Result records have no grade and require result-completion review before approval or '
              'release?',
  'management_purpose': 'Resolve incomplete result records',
  'why_useful': 'Creates a direct result-data follow-up queue.',
  'requirement_reference': 'PPD-ALI-CM-5.5.1; result management and Examination Board approval',
  'calculation': 'Numerator: Assessment Result records with blank grade. Denominator: readable results in scope.',
  'primary_source': 'Assessment Result',
  'required_fields': 'assessment_plan; student; total_score; grade',
  'drilldown_records': 'Assessment Result records with blank grade',
  'support_status': 'Can be implemented now',
  'metric_id': 'a551-results-missing-grade',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Management should determine whether grading is pending, not applicable or incompletely '
                             'recorded before release.',
  'source_keys': ['assessment_result']},
 {'id': 'A551-13',
  'criterion': '5.5.1',
  'question': 'How many Assessment Email Sender records are available as result-release communication evidence, and '
              'can each be linked to an approved result set?',
  'management_purpose': 'Verify authorised result communication',
  'why_useful': 'Separates communication-record existence from approved release compliance.',
  'requirement_reference': 'PPD-ALI-CM-5.5.1; result communication and release',
  'calculation': 'Count readable Assessment Email Sender records. Full compliance requires linkage to the result set, '
                 'Examination Board approval and release date.',
  'primary_source': 'Assessment Email Sender',
  'required_fields': 'result set; recipient; sent date; approval linkage',
  'drilldown_records': 'Communication records and unmatched result sets',
  'support_status': 'Can be implemented with revised mapping',
  'metric_id': 'a551-result-release-communications',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'The count is communication evidence volume only and does not prove that release was '
                             'authorised or complete.',
  'source_keys': ['assessment_email_sender']},
 {'id': 'A551-14',
  'criterion': '5.5.1',
  'question': 'How many Meeting Minutes records are available as Examination Board evidence, and can the required '
              'assessment, result, award and appeal decisions be identified within them?',
  'management_purpose': 'Verify Examination Board decision evidence',
  'why_useful': 'Distinguishes meeting-record existence from criterion-specific approval evidence.',
  'requirement_reference': 'PPD-ALI-CM-5.5.1; Examination Board oversight',
  'calculation': 'Count readable Quality Meeting records displayed as Meeting Minutes. Decision compliance requires '
                 'criterion, agenda item, decision, date and linked record.',
  'primary_source': 'Meeting Minutes',
  'required_fields': 'meeting type; date; agenda; decision; linked record',
  'drilldown_records': 'Meeting Minutes with identified or missing assessment decisions',
  'support_status': 'Can be implemented with revised mapping',
  'metric_id': 'a551-eb-meeting-records',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'The count does not prove that the Examination Board approved any specific assessment, '
                             'result, award or appeal.',
  'source_keys': ['quality_meeting']},
 {'id': 'A551-15',
  'criterion': '5.5.1',
  'question': 'Which Assessment Result records are not linked to an Assessment Plan and therefore require '
              'reconciliation before approval, analysis or release?',
  'management_purpose': 'Maintain assessment-to-result traceability',
  'why_useful': 'Identifies a direct relationship gap affecting verification and audit trail.',
  'requirement_reference': 'PPD-ALI-CM-5.5.1; assessment lifecycle and result management',
  'calculation': 'Numerator: Assessment Result records with blank assessment_plan. Denominator: readable result '
                 'records in scope.',
  'primary_source': 'Assessment Result',
  'required_fields': 'assessment_plan; student; course; score; grade',
  'drilldown_records': 'Assessment Result records with no Assessment Plan link',
  'support_status': 'Can be implemented now',
  'metric_id': 'a551-results-missing-plan-link',
  'answer_mode': 'metric_context_summary',
  'evidence_interpretation': 'Unlinked results should be reconciled before moderation, Examination Board approval or '
                             'student communication.',
  'source_keys': ['assessment_result']}])

DOCUMENT_ISSUES = [{'id': 'DOC-01',
  'subcriterion': '5.1.2',
  'status': 'document_conflict',
  'issue': 'Course Review GD4 mapping contains 5.12.3 instead of 5.1.2.3.',
  'treatment': 'Do not silently normalise the controlled-document reference.'},
 {'id': 'DOC-02',
  'subcriterion': '5.2.1',
  'status': 'document_conflict',
  'issue': 'The main procedure requires timetable communication at least one week before course start, while Appendix '
           'B uses at least three calendar days.',
  'treatment': 'Do not calculate timetable communication compliance until management approves one standard.'},
 {'id': 'DOC-03',
  'subcriterion': '5.3.1',
  'status': 'resolved_in_mapping',
  'issue': 'The procedure uses a 1-5 partnership selection scale with a minimum overall score of 3.5; the old Python '
           'used 70.',
  'treatment': 'The revised metric uses 3.5 and excludes Provider and recruitment-agent labels when the type field is '
               'available.'},
 {'id': 'DOC-04',
  'subcriterion': '5.5.1',
  'status': 'document_conflict',
  'issue': 'The supplied Student Assessment filename states 1.2, while the cover, headers and Version Control state '
           '2.2 dated 15 January 2026.',
  'treatment': 'The API registry uses the controlled-document internal version 2.2 and reports the filename '
               'inconsistency.'},
 {'id': 'DOC-05',
  'subcriterion': '5.5.1',
  'status': 'document_conflict',
  'issue': 'The rendered Student Assessment file has 52 pages while the footer states 51; some Quality Record '
           'descriptions are copied from unrelated records.',
  'treatment': 'Do not use those descriptions as proof of system behaviour; verify actual DocType schema at runtime.'},
 {'id': 'DOC-06',
  'subcriterion': '5.1.2',
  'status': 'document_conflict',
  'issue': 'The rendered Course Review file has 22 pages while its footer and contents state 21.',
  'treatment': 'Report as a document-control issue; it does not change the review-cycle calculation.'}]

if canonical_subcriterion not in POLICY_REGISTRY:
    frappe.throw("Unsupported Criterion 5 subcriterion.")

STANDARD_FIELDS = [
    "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"
]
FILTER_FIELD_CANDIDATES = {
    "year": ["academic_year", "year", "review_year"],
    "academic_year": ["academic_year", "year"],
    "student_group": ["student_group", "module_class_details"],
    "program": ["program", "course"],
    "course": ["course", "program"],
    "status": ["status", "review_status", "application_status", "approval_status"]
}

SOURCE_CACHE = {}
META_CACHE = {}
FIELD_CACHE = {}
ROW_CACHE = {}
ROW_ERROR_CACHE = {}


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
    return "permission" in text or "not permitted" in text or "not allowed" in text


def get_meta(doctype):
    if doctype in META_CACHE:
        return META_CACHE.get(doctype)
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        meta = None
    META_CACHE[doctype] = meta
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
    if cache_key in FIELD_CACHE:
        return FIELD_CACHE.get(cache_key) or ""
    meta = get_meta(doctype)
    if not meta:
        FIELD_CACHE[cache_key] = ""
        return ""
    for fieldname in candidates or []:
        if field_exists(meta, fieldname):
            FIELD_CACHE[cache_key] = fieldname
            return fieldname
    FIELD_CACHE[cache_key] = ""
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
    return [resolved, missing]


def safe_fields(doctype, fields):
    meta = get_meta(doctype)
    output = []
    if not meta:
        return output
    for fieldname in fields or []:
        if fieldname not in output and field_exists(meta, fieldname):
            output.append(fieldname)
    if "name" not in output:
        output.insert(0, "name")
    return output


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


def resolve_source(alias):
    if alias in SOURCE_CACHE:
        return SOURCE_CACHE.get(alias)
    candidates = SOURCE_CANDIDATES.get(alias) or []
    attempts = []
    for candidate_index in range(len(candidates)):
        doctype = candidates[candidate_index]
        attempt = {"doctype": doctype, "status": "checking", "stage": "metadata", "message": ""}
        meta = get_meta(doctype)
        if not meta:
            attempt["status"] = "unavailable"
            attempt["message"] = "DocType metadata is unavailable."
            attempts.append(attempt)
            continue
        try:
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
                "display_name": SOURCE_DISPLAY_NAMES.get(alias) or doctype,
                "candidates": candidates,
                "status": "available",
                "count": len(rows),
                "count_is_sample": True,
                "truncated": False,
                "probe": "frappe.get_list",
                "fallback_used": candidate_index > 0,
                "resolution_attempts": attempts
            }
            SOURCE_CACHE[alias] = result
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
                    "display_name": SOURCE_DISPLAY_NAMES.get(alias) or doctype,
                    "candidates": candidates,
                    "status": "permission_denied",
                    "count": 0,
                    "count_is_sample": True,
                    "message": message,
                    "probe": "frappe.get_list",
                    "fallback_used": False,
                    "resolution_attempts": attempts
                }
                SOURCE_CACHE[alias] = result
                return result
    result = {
        "key": alias,
        "doctype": None,
        "display_name": SOURCE_DISPLAY_NAMES.get(alias) or alias,
        "candidates": candidates,
        "status": "unavailable",
        "count": 0,
        "count_is_sample": True,
        "message": "No verified candidate DocType could be resolved.",
        "resolution_attempts": attempts,
        "fallback_used": False
    }
    SOURCE_CACHE[alias] = result
    return result


def add_candidates(target, candidates):
    for fieldname in candidates or []:
        if fieldname and fieldname not in target:
            target.append(fieldname)


def metric_required_fields(metric, doctype):
    fields = []
    missing = []
    if metric.get("field"):
        fieldname = resolve_field(doctype, metric.get("field"))
        if fieldname:
            fields.append(fieldname)
        else:
            missing.append(metric.get("field"))
    groups_result = resolve_field_groups(doctype, metric.get("fields") or [])
    resolved_groups = groups_result[0]
    missing_groups = groups_result[1]
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
    return [fields, missing, resolved_conditions]


def fetch_rows(source_alias, source, requested_fields=None):
    doctype = source.get("doctype")
    if source.get("status") != "available" or not doctype:
        return []
    planned = []
    add_candidates(planned, SAFE_FIELDS.get(source_alias) or ["name"])
    add_candidates(planned, requested_fields or [])
    fields_to_fetch = safe_fields(doctype, planned)
    active_filters = applied_filters(doctype)
    filter_parts = []
    for key in sorted(active_filters):
        filter_parts.append(clean_text(key) + "=" + clean_text(active_filters.get(key)))
    cache_key = source_alias + "|" + doctype + "|" + "|".join(fields_to_fetch) + "|" + "|".join(filter_parts)
    if cache_key in ROW_CACHE:
        return ROW_CACHE.get(cache_key) or []
    try:
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
        ROW_CACHE[cache_key] = rows
        ROW_ERROR_CACHE[cache_key] = None
        source["count"] = len(rows)
        source["count_is_sample"] = False
        source["truncated"] = truncated
        source.pop("fetch_error", None)
        source.pop("fetch_status", None)
        return rows
    except Exception as error:
        message = clean_text(error)
        status = "permission_denied" if is_permission_error(error) else "query_error"
        ROW_CACHE[cache_key] = []
        ROW_ERROR_CACHE[cache_key] = message
        source["fetch_error"] = message
        source["fetch_status"] = status
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
    if op == "not_contains_any":
        text_value = lower_text(value)
        for item in values or []:
            if lower_text(item) in text_value:
                return False
        return True
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
    if op == "date_next_days":
        if not value:
            return False
        try:
            date_value = frappe.utils.getdate(value)
            today = frappe.utils.getdate(frappe.utils.today())
            end_date = frappe.utils.getdate(frappe.utils.add_days(today, int(days or 0)))
            return date_value >= today and date_value <= end_date
        except Exception:
            return False
    return False


def row_matches(row, metric, resolved_fields, resolved_conditions):
    mode = metric.get("mode")
    if mode == "all":
        return True
    if mode in ["truthy", "falsy", "equals", "in", "not_in", "contains", "contains_any", "not_contains_any", "date_before_today", "date_next_days", "gt", "gte", "lt", "lte"]:
        if not resolved_fields:
            return False
        return compare(
            row, resolved_fields[0], mode,
            expected=metric.get("value"), values=metric.get("values"), days=metric.get("days")
        )
    if mode == "all_required":
        for fieldname in resolved_fields:
            if not is_truthy(row.get(fieldname)):
                return False
        return True
    if mode == "conditions":
        for condition in resolved_conditions:
            if not compare(
                row, condition.get("resolved_field"), condition.get("op"),
                expected=condition.get("value"), values=condition.get("values"), days=condition.get("days")
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
    return False


def evaluate_direct_metric(metric, source_map, include_rows=False):
    source_alias = metric.get("source")
    if metric.get("mode") == "unsupported":
        source = source_map.get(source_alias) or {}
        return {
            "id": metric.get("id"), "label": metric.get("label"),
            "source": source_alias, "doctype": source.get("doctype"),
            "value": None, "unit": metric.get("unit") or "records",
            "record_count": 0, "status": "unsupported",
            "message": metric.get("message"), "resolved_fields": [],
            "resolved_field_groups": [], "rows": [], "total": 0
        }
    source = source_map.get(source_alias) or resolve_source(source_alias)
    if source.get("status") != "available":
        return {
            "id": metric.get("id"), "label": metric.get("label"),
            "source": source_alias, "doctype": source.get("doctype"),
            "value": None, "unit": metric.get("unit") or "records",
            "record_count": 0, "status": source.get("status") or "unavailable",
            "message": source.get("message"), "resolved_fields": [],
            "resolved_field_groups": [], "rows": [], "total": 0
        }
    doctype = source.get("doctype")
    required_result = metric_required_fields(metric, doctype)
    resolved_fields = required_result[0]
    missing = required_result[1]
    resolved_conditions = required_result[2]
    if metric.get("mode") != "all" and missing:
        return {
            "id": metric.get("id"), "label": metric.get("label"),
            "source": source_alias, "doctype": doctype,
            "value": None, "unit": metric.get("unit") or "records",
            "record_count": 0, "status": "unsupported_field",
            "message": "Required field is not installed or has not been verified.",
            "missing_field_candidates": missing,
            "resolved_fields": resolved_fields,
            "resolved_field_groups": resolved_conditions,
            "rows": [], "total": 0
        }
    rows = fetch_rows(source_alias, source, resolved_fields)
    if source.get("fetch_error"):
        return {
            "id": metric.get("id"), "label": metric.get("label"),
            "source": source_alias, "doctype": doctype,
            "value": None, "unit": metric.get("unit") or "records",
            "record_count": 0, "status": source.get("fetch_status") or "unavailable",
            "message": source.get("fetch_error"),
            "resolved_fields": resolved_fields,
            "resolved_field_groups": resolved_conditions,
            "rows": [], "total": 0
        }
    matched = []
    for row in rows:
        if row_matches(row, metric, resolved_fields, resolved_conditions):
            matched.append(row)
    output_rows = []
    if include_rows:
        start = (page - 1) * page_size
        end = start + page_size
        output_fields = safe_fields(doctype, SAFE_FIELDS.get(source_alias) or ["name"])
        for row in matched[start:end]:
            item = {}
            for fieldname in output_fields:
                item[fieldname] = row.get(fieldname)
            item["requirement_indicator"] = metric.get("label")
            output_rows.append(item)
    return {
        "id": metric.get("id"), "label": metric.get("label"),
        "source": source_alias, "doctype": doctype,
        "value": len(matched), "unit": metric.get("unit") or "records",
        "record_count": len(matched), "status": "available",
        "resolved_fields": resolved_fields,
        "resolved_field_groups": resolved_conditions,
        "rows": output_rows, "total": len(matched),
        "truncated": source.get("truncated") or False
    }


def metric_by_id(rows, target_id):
    for row in rows or []:
        if row.get("id") == target_id:
            return row
    return None


def count_available(rows):
    count = 0
    for row in rows or []:
        if row.get("status") == "available":
            count = count + 1
    return count


def build_requirement_rows(section, source_map):
    output = []
    for question in QUESTION_REGISTRY.get(section) or []:
        source_details = []
        available_count = 0
        issue_count = 0
        for source_key in question.get("source_keys") or []:
            source = source_map.get(source_key)
            if not source:
                source = resolve_source(source_key)
            detail = {
                "source": source_key,
                "doctype": source.get("doctype"),
                "status": source.get("status"),
                "count": source.get("count") or 0,
                "message": source.get("message")
            }
            source_details.append(detail)
            if source.get("status") == "available":
                available_count = available_count + 1
            else:
                issue_count = issue_count + 1
        if not question.get("source_keys"):
            evidence_status = "no_mapped_live_source"
        elif available_count == len(question.get("source_keys") or []) and question.get("support_status") == "Can be implemented now":
            evidence_status = "live_source_available"
        elif available_count > 0:
            evidence_status = "partial"
        else:
            evidence_status = "no_available_live_source"
        output.append({
            "id": question.get("id"),
            "subcriterion": question.get("criterion"),
            "requirement": question.get("question"),
            "requirement_reference": question.get("requirement_reference"),
            "management_purpose": question.get("management_purpose"),
            "calculation": question.get("calculation"),
            "required_fields": question.get("required_fields"),
            "support_status": question.get("support_status"),
            "source_keys": question.get("source_keys") or [],
            "source_details": source_details,
            "evidence_status": evidence_status,
            "available_sources": available_count,
            "source_issues": issue_count
        })
    return output


def build_custom_metric(metric, primary_metrics, supporting_metrics, requirements, include_rows=False):
    mode = metric.get("mode")
    if mode == "requirement_gap_count":
        rows = []
        for item in requirements:
            if item.get("evidence_status") != "live_source_available":
                rows.append({
                    "requirement_id": item.get("id"),
                    "subcriterion": item.get("subcriterion"),
                    "requirement": item.get("requirement"),
                    "support_status": item.get("support_status"),
                    "evidence_status": item.get("evidence_status")
                })
        return {
            "id": metric.get("id"), "label": metric.get("label"),
            "source": "requirement_registry", "doctype": None,
            "value": len(rows), "unit": "requirements",
            "record_count": len(rows), "status": "available",
            "resolved_fields": [], "resolved_field_groups": [],
            "rows": rows[(page - 1) * page_size:((page - 1) * page_size) + page_size] if include_rows else [],
            "total": len(rows)
        }
    if mode == "attention_count":
        rows = []
        combined = []
        for item in primary_metrics:
            combined.append(item)
        for item in supporting_metrics:
            combined.append(item)
        for item in combined:
            value = to_number(item.get("value"))
            if item.get("status") == "available" and value is not None and value > 0 and item.get("id") in [
                "d511-approved-without-ssg-date", "r512-overdue-review-records",
                "r512-pending-module-recommendations", "l522-observations-with-findings",
                "pa531-below-selection-threshold", "pa531-expired-agreement-records",
                "sl541-attendance-risk-records", "a551-score-errors"
            ]:
                rows.append({
                    "metric_id": item.get("id"), "indicator": item.get("label"),
                    "count": value, "source": item.get("doctype") or item.get("source")
                })
        return {
            "id": metric.get("id"), "label": metric.get("label"),
            "source": "verified_exception_registry", "doctype": None,
            "value": len(rows), "unit": "indicators",
            "record_count": len(rows), "status": "available",
            "resolved_fields": [], "resolved_field_groups": [],
            "rows": rows[(page - 1) * page_size:((page - 1) * page_size) + page_size] if include_rows else [],
            "total": len(rows)
        }
    return {
        "id": metric.get("id"), "label": metric.get("label"),
        "source": metric.get("source"), "doctype": None,
        "value": None, "unit": metric.get("unit") or "records",
        "record_count": 0, "status": "unsupported",
        "message": metric.get("message") or "The calculation is not implemented.",
        "resolved_fields": [], "resolved_field_groups": [], "rows": [], "total": 0
    }


def metric_value_text(metric):
    if not metric or metric.get("status") != "available":
        return "unavailable"
    value = metric.get("value")
    if value is None:
        value = 0
    unit = metric.get("unit") or "records"
    if unit == "requirements":
        return clean_text(value) + " requirement(s)"
    if unit == "indicators":
        return clean_text(value) + " indicator(s)"
    return clean_text(value) + " record(s)"


def unavailable_answer(question, metric):
    detail = clean_text((metric or {}).get("message") or (metric or {}).get("status") or question.get("support_status"))
    return "Cannot assess from the current verified mapping: " + detail


def build_question_answer(question, primary_metric, all_metrics, source_map):
    answer_mode = question.get("answer_mode") or "unsupported"
    support_status = question.get("support_status") or "Document evidence only"
    limitation = question.get("calculation") or ""
    status = "unsupported"
    confidence = "Unavailable"
    answer = ""

    if answer_mode == "unsupported":
        answer = unavailable_answer(question, primary_metric)
    elif not primary_metric or primary_metric.get("status") != "available":
        status = primary_metric.get("status") if primary_metric else "unavailable"
        confidence = "Unavailable"
        answer = unavailable_answer(question, primary_metric)
    elif answer_mode == "proposal_scope_summary":
        approved = metric_by_id(all_metrics, "s511-approved-status")
        ssg = metric_by_id(all_metrics, "s511-ssg-date")
        answer = (
            metric_value_text(primary_metric) + " are in the current filter scope. "
            + metric_value_text(approved) + " have an approved-like status and "
            + metric_value_text(ssg) + " have an SSG approval date. "
            + "The required learner, curriculum, pedagogy, assessment, resource, risk and stakeholder inputs are not mapped as a complete checklist."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "proposal_approval_summary":
        answer = (
            metric_value_text(primary_metric) + " have an approved-like status but no SSG approval date in the mapped field. "
            + "HOD-ALI, Principal and Academic Board approval evidence and implementation timing are not mapped, so full approval and registration compliance cannot be concluded."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "review_due_summary":
        answer = (
            metric_value_text(primary_metric) + " have a past next-review date. "
            + "This does not identify courses or modules with no review record and does not apply the midpoint, end-of-module, first-run, biennial, lapse or material-change population rules."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "review_action_summary":
        course_pending = metric_by_id(all_metrics, "s512-pending-course-recommendations")
        answer = (
            metric_value_text(primary_metric) + " in Module Review and "
            + metric_value_text(course_pending) + " in Course Review have a pending implementation status. "
            + "Owner, due date, approval, implementation evidence and effectiveness are not confirmed."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "observation_coverage_summary":
        answer = (
            metric_value_text(primary_metric) + " are readable. "
            + "The required teacher population for new teachers, new-module teachers, poor-feedback triggers and annual routine observation is not mapped, so coverage cannot be calculated."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "observation_followup_summary":
        answer = (
            metric_value_text(primary_metric) + " record improvement areas. "
            + "Assigned action, due date, follow-up, escalation, closure and effectiveness evidence are not mapped."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "partnership_selection_summary":
        answer = (
            metric_value_text(primary_metric) + " are below the documented 3.5 out of 5 selection threshold after excluding records whose type contains Provider or Recruitment Agent. "
            + "The stored type and scale must still be verified against the live DocType schema, and a passing score alone does not prove appointment or benefit."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "partnership_agreement_summary":
        answer = (
            metric_value_text(primary_metric) + " have a past expiry date. "
            + "The current mapping does not prove that every active in-scope partner has a signed renewable agreement with all required terms and authorised signatories."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "student_learning_indicator_summary":
        answer = (
            metric_value_text(primary_metric) + " are marked absent or late. "
            + "This is only one possible support indicator and does not identify unique students in SSG-approved courses or prove assessment, assignment, intervention, follow-up or effectiveness."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "assessment_plan_summary":
        answer = (
            metric_value_text(primary_metric) + " are readable. "
            + "Record existence does not prove a complete approved module-level plan, learning-outcome alignment, weighting, criteria, result-release information, appeal information or timely LMS communication."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "assessment_verification_summary":
        answer = (
            metric_value_text(primary_metric) + " are readable. "
            + "The mapping does not yet prove instrument linkage, validity/fairness/reliability/authenticity checks, revision closure or completion before administration."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "assessment_marking_summary":
        answer = (
            metric_value_text(primary_metric) + " are readable. "
            + "The required rubric, marker, Internal Verifier sample, moderation, variance resolution and documented grade-change relationship to result sets are not mapped."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "assessment_admin_summary":
        answer = (
            metric_value_text(primary_metric) + " have a total score above the recorded maximum score and require data correction. "
            + "Other administration, briefing and academic-integrity controls remain unmapped."
        )
        status = "available"
        confidence = "Live data-quality exception"
    elif answer_mode == "assessment_failure_summary":
        answer = (
            metric_value_text(primary_metric) + " are readable. "
            + "The mapping does not confirm failure explanation, student decision, evidence, resubmission/resit/deferral timing, approval, communication or updated result."
        )
        status = "partial"
        confidence = "Partial live evidence"
    elif answer_mode == "metric_context_summary":
        answer = (
            metric_value_text(primary_metric) + ". "
            + clean_text(question.get("evidence_interpretation") or "This is a live record indicator and does not by itself prove procedural compliance or effectiveness.")
        )
        status = clean_text(question.get("answer_status") or "partial")
        confidence = clean_text(question.get("answer_confidence") or "Partial live evidence")
    elif answer_mode == "evidence_gap_summary":
        answer = (
            metric_value_text(primary_metric) + " do not have a fully usable live evidence mapping. "
            + "These are evidence and data-model gaps, not automatic operational non-conformities."
        )
        status = "available"
        confidence = "Live source-mapping status"
    elif answer_mode == "attention_summary":
        answer = (
            metric_value_text(primary_metric) + " currently have a positive verified exception indicator. "
            + "Overlapping affected records are not summed, and evidence gaps are reported separately."
        )
        status = "available"
        confidence = "Live exception indicators"
    else:
        answer = unavailable_answer(question, primary_metric)

    source_key = primary_metric.get("source") if primary_metric else None
    source = source_map.get(source_key) or {}
    return {
        "id": question.get("id"),
        "criterion": question.get("criterion"),
        "question": question.get("question"),
        "answer": answer,
        "metric_id": question.get("metric_id"),
        "record_count": primary_metric.get("record_count") if primary_metric else 0,
        "source": source_key,
        "doctype": primary_metric.get("doctype") if primary_metric else source.get("doctype"),
        "resolved_fields": primary_metric.get("resolved_fields") if primary_metric else [],
        "status": status,
        "confidence": confidence,
        "support_status": support_status,
        "management_purpose": question.get("management_purpose"),
        "decision_required": question.get("management_purpose"),
        "requirement_reference": question.get("requirement_reference"),
        "calculation": question.get("calculation"),
        "required_fields": question.get("required_fields"),
        "drilldown_records": question.get("drilldown_records"),
        "source_logic": clean_text(primary_metric.get("label") if primary_metric else question.get("primary_source")),
        "limitation": limitation
    }


section_sources = SOURCES_BY_SECTION.get(canonical_subcriterion) or []
resolved_sources = {}
for alias in section_sources:
    resolved_sources[alias] = resolve_source(alias)

primary_metrics = []
for configured_metric in METRIC_CONFIG.get(canonical_subcriterion) or []:
    if configured_metric.get("mode") in ["attention_count", "requirement_gap_count"]:
        continue
    primary_metrics.append(evaluate_direct_metric(configured_metric, resolved_sources, False))

supporting_metrics = []
for configured_metric in SUPPORTING_CONFIG.get(canonical_subcriterion) or []:
    supporting_metrics.append(evaluate_direct_metric(configured_metric, resolved_sources, False))

requirements = build_requirement_rows(canonical_subcriterion, resolved_sources)

for configured_metric in METRIC_CONFIG.get(canonical_subcriterion) or []:
    if configured_metric.get("mode") in ["attention_count", "requirement_gap_count"]:
        primary_metrics.append(build_custom_metric(configured_metric, primary_metrics, supporting_metrics, requirements, False))

all_metrics = []
for item in primary_metrics:
    all_metrics.append(item)
for item in supporting_metrics:
    all_metrics.append(item)

questions = []
for question in QUESTION_REGISTRY.get(canonical_subcriterion) or []:
    primary_metric = metric_by_id(all_metrics, question.get("metric_id"))
    questions.append(build_question_answer(question, primary_metric, all_metrics, resolved_sources))

sources = []
for alias in section_sources:
    sources.append(resolved_sources.get(alias))

operational_exception_ids = [
    "d511-approved-without-ssg-date", "r512-overdue-review-records",
    "r512-pending-module-recommendations", "l522-observations-with-findings",
    "pa531-below-selection-threshold", "pa531-expired-agreement-records",
    "sl541-attendance-risk-records", "a551-score-errors"
]
exceptions = []
for metric in primary_metrics:
    if metric.get("id") in operational_exception_ids and metric.get("status") == "available":
        value = to_number(metric.get("value"))
        if value is not None and value > 0:
            exceptions.append(metric)

evidence_gaps = []
for requirement in requirements:
    if requirement.get("evidence_status") != "live_source_available":
        evidence_gaps.append(requirement)

data_quality = []
for source in sources:
    if source.get("status") != "available":
        data_quality.append({
            "criterion": canonical_subcriterion,
            "check": "Source availability",
            "source": source.get("doctype") or " / ".join(source.get("candidates") or []),
            "status": source.get("status"),
            "detail": source.get("message") or "Source is unavailable."
        })
for metric in primary_metrics:
    if metric.get("status") != "available":
        data_quality.append({
            "criterion": canonical_subcriterion,
            "check": metric.get("label"),
            "source": metric.get("doctype") or metric.get("source") or "Requirement mapping",
            "status": metric.get("status"),
            "detail": metric.get("message") or "Metric is unavailable."
        })
for issue in DOCUMENT_ISSUES:
    if issue.get("subcriterion") == canonical_subcriterion:
        data_quality.append({
            "criterion": canonical_subcriterion,
            "check": "Controlled-document consistency",
            "source": issue.get("id"),
            "status": issue.get("status"),
            "detail": issue.get("issue") + " Treatment: " + issue.get("treatment")
        })

available_sources = count_available(sources)
available_metrics = count_available(primary_metrics)
available_supporting_metrics = count_available(supporting_metrics)

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
        "api_method": "ucc_analytics_criterion_5",
        "platform_version": "2.0.2-intake-expanded-questions",
        "status": "translation_aligned_foundation",
        "generated_at": frappe.utils.now(),
        "action": action,
        "subcriterion": requested_subcriterion,
        "canonical_subcriterion": canonical_subcriterion,
        "row_limit": row_limit,
        "legacy_alias_used": requested_subcriterion != canonical_subcriterion
    },
    "policy": POLICY_REGISTRY.get(canonical_subcriterion),
    "filters": filters,
    "sources": sources,
    "metrics": primary_metrics,
    "supporting_metrics": supporting_metrics,
    "questions": questions,
    "requirements": requirements,
    "exceptions": exceptions,
    "evidence_gaps": evidence_gaps,
    "data_quality": data_quality,
    "document_issues": DOCUMENT_ISSUES,
    "source_summary": {
        "total": len(sources),
        "available": available_sources,
        "issues": len(sources) - available_sources
    },
    "metric_summary": {
        "total": len(primary_metrics),
        "available": available_metrics,
        "issues": len(primary_metrics) - available_metrics
    },
    "supporting_metric_summary": {
        "total": len(supporting_metrics),
        "available": available_supporting_metrics,
        "issues": len(supporting_metrics) - available_supporting_metrics
    },
    "readiness": {
        "type": "technical_data_readiness",
        "label": "Source and field availability only",
        "not_operational_compliance": True,
        "available_sources": available_sources,
        "total_sources": len(sources),
        "available_management_metrics": available_metrics,
        "total_management_metrics": len(primary_metrics),
        "evidence_gap_count": len(evidence_gaps)
    },
    "data": {
        "sources": sources,
        "metrics": primary_metrics,
        "supporting_metrics": supporting_metrics,
        "questions": questions,
        "requirements": requirements,
        "exceptions": exceptions,
        "evidence_gaps": evidence_gaps,
        "data_quality": data_quality
    },
    "warnings": [
        "Source and metric availability is technical data readiness, not proof of compliance or effectiveness.",
        "Raw record counts are returned as supporting_metrics and are not automatically converted into management questions.",
        "Legacy frontend subcriterion codes 5.4 and 5.5 are accepted and mapped to controlled procedure codes 5.4.1 and 5.5.1.",
        "The Course Planning timetable threshold conflict remains unresolved; no timetable compliance rate is calculated.",
        "Provider and external recruitment-agent populations are excluded from the partnership rule when the stored type field supports that classification.",
        "Backend DocType names use the untranslated Frappe names; display_name contains the UCC translated label."
    ]
}

result = standardise_response_contract(result, "Criterion 5", "ucc_analytics_criterion_5", action, canonical_subcriterion, row_limit)

if action == "policy_registry":
    result["registry"] = POLICY_REGISTRY
    result["aliases"] = SUBCRITERION_ALIASES
elif action == "source_status":
    result["source_status"] = sources
elif action == "requirement_registry":
    result["registry"] = requirements
elif action == "question_registry":
    result["registry"] = QUESTION_REGISTRY.get(canonical_subcriterion) or []
elif action == "drilldown":
    selected_config = None
    for configured_metric in METRIC_CONFIG.get(canonical_subcriterion) or []:
        if configured_metric.get("id") == metric_id:
            selected_config = configured_metric
            break
    if not selected_config and question_id:
        for question in QUESTION_REGISTRY.get(canonical_subcriterion) or []:
            if question.get("id") == question_id:
                metric_id = question.get("metric_id")
                break
        for configured_metric in METRIC_CONFIG.get(canonical_subcriterion) or []:
            if configured_metric.get("id") == metric_id:
                selected_config = configured_metric
                break
    if not selected_config:
        frappe.throw("Unknown Criterion 5 management metric.")
    if selected_config.get("mode") in ["attention_count", "requirement_gap_count"]:
        result["drilldown"] = build_custom_metric(selected_config, primary_metrics, supporting_metrics, requirements, True)
    else:
        result["drilldown"] = evaluate_direct_metric(selected_config, resolved_sources, True)

result = standardise_response_contract(result, "Criterion 5", "ucc_analytics_criterion_5", action, canonical_subcriterion, row_limit)

frappe.response["message"] = result
