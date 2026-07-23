"""
UCC Intelligence Platform Server Script

Visible name:
    UCC Analytics - Criterion 6

Script type:
    API

API method:
    ucc_analytics_criterion_6

Purpose:
    Return permission-aware, policy-aligned Criterion 6 analytics. The API
    separates record existence from completeness, timeliness, approval,
    procedural compliance and effectiveness. Unsupported controls are reported
    honestly instead of being converted into false zeroes.

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
subcriterion = payload.get("subcriterion") or "6.1.1"
filters = payload.get("filters") or {}
if not isinstance(filters, dict):
    filters = {}
metric_id = payload.get("metric_id")
page = payload.get("page") or 1
page_size = payload.get("page_size") or 50
row_limit = payload.get("limit") or 1000

try:
    page = max(1, int(page))
except Exception:
    page = 1
try:
    page_size = max(1, min(int(page_size), 200))
except Exception:
    page_size = 50
try:
    row_limit = max(1, min(int(row_limit), 3000))
except Exception:
    row_limit = 1000

ALLOWED_ACTIONS = [
    "summary", "source_status", "policy_registry", "requirement_registry",
    "question_registry", "drilldown"
]
if action not in ALLOWED_ACTIONS:
    frappe.throw("Unsupported Criterion 6 action.")

POLICY_REGISTRY = {'6.1.1': {'title': 'Internal Assessment and Quality Audits',
           'policy': 'PPD-SGL-SQ-6.1.1',
           'version': '1.2',
           'effective_date': '15 January 2026'},
 '6.2.1': {'title': 'Management Review',
           'policy': 'PPD-SGL-SQ-6.2.1',
           'version': '1.3',
           'effective_date': '10 April 2026',
           'version_note': 'The cover page states Version 1.3, while an internal footer still shows Version 1.2. '
                           'Verify the controlled master before audit use.'},
 '6.3.1': {'title': 'Innovation and Continual Improvement',
           'policy': 'PPD-SGL-SQ-6.3.1',
           'version': '1.2',
           'effective_date': '15 January 2026'},
 '6.4.1': {'title': "Provider's Accreditation and Evaluation",
           'policy': 'PPD-OE-FN-6.4.1',
           'version': '1.2',
           'effective_date': '15 January 2026'},
 '6.5.3': {'title': 'Hazard Identification and Risk Assessment',
           'policy': 'PPD-SGL-SQ-6.5.3',
           'version': '1.2',
           'effective_date': '15 January 2026'}}

SOURCE_CANDIDATES = {'oversight_framework': ['Oversight Framework'],
 'quality_action': ['Quality Action'],
 'responsibilities': ['Responsibilities'],
 'management_review': ['Management Review'],
 'quality_meeting': ['Quality Meeting'],
 'operational_outcomes': ['Operational Outcomes Cost Time Saving'],
 'quality_performance_outcomes': ['Quality Performance Outcomes'],
 'provider': ['Supplier'],
 'provider_rating': ['Supplier Rating'],
 'purchase_order': ['Purchase Order'],
 'purchase_receipt': ['Purchase Receipt'],
 'quality_inspection': ['Quality Inspection'],
 'request_for_quotation': ['Request for Quotation'],
 'compliance_tracking': ['Non Conformance'],
 'risk_register': ['Risk Register and Mitigation Plans'],
 'business_continuity': ['Business Continuity and Disaster Recovery'],
 'business_impact_analysis': ['Business Impact Analysis']}

SOURCE_DISPLAY_NAMES = {'Supplier': 'Provider',
 'Supplier Rating': 'Provider Rating',
 'Quality Meeting': 'Meeting Minutes',
 'Non Conformance': 'Compliance Tracking'}

SAFE_FIELDS = {'oversight_framework': ['name', 'modified'],
 'quality_action': ['name',
                    'naming_series',
                    'custom_subject',
                    'custom_status_updates',
                    'status',
                    'corrective_preventive',
                    'date',
                    'custom_proposed_date',
                    'custom_completed_date',
                    'custom_type_of_innovation',
                    'custom_innovation_category',
                    'custom_innovation',
                    'custom_continuous_improvement',
                    'custom_aggregated_performance_index_api',
                    'custom_timeadjusted_cost_efficiency_index_tacei',
                    'custom_cost_efficiency_index_cei',
                    'custom_implementation_duration',
                    'custom_cost_saving_data',
                    'custom_annual_people_savings_ctei',
                    'custom_ctei_savings',
                    'custom_priority_score',
                    'custom_total_budget_fee',
                    'custom_total_actual_spending',
                    'custom_spending_difference',
                    'goal',
                    'review',
                    'procedure',
                    'feedback',
                    'custom_quality_meeting',
                    'custom_risk_and_opportunities_identified',
                    'modified'],
 'responsibilities': ['name', 'modified'],
 'management_review': ['name',
                       'review_date',
                       'review_period',
                       'review_type',
                       'review_status',
                       'chairperson',
                       'chairperson_full_name',
                       'minutes_of_meeting',
                       'next_review_date',
                       'leaderhip_note',
                       'essential_information',
                       'resource_note',
                       'table_bhwb',
                       'process_performance_note',
                       'process_performace_conformity',
                       'risk_note',
                       'risk_opportunities',
                       'bcp__note',
                       'business_continuity',
                       'opportunities_note',
                       'table_qzdd',
                       'modified'],
 'quality_meeting': ['name', 'modified'],
 'operational_outcomes': ['name',
                          'monitoring_year',
                          'period_start',
                          'period_end',
                          'benchmark_type',
                          'benchmark_value',
                          'variance_to_benchmark',
                          'total_people_saving',
                          'total_technology_saving',
                          'total_physical_saving',
                          'total_gross_saving',
                          'total_implementation_cost',
                          'total_maintenance_cost',
                          'total_net_saving',
                          'modified'],
 'quality_performance_outcomes': ['name', 'modified'],
 'provider': ['name', 'modified'],
 'provider_rating': ['name',
                     'posting_date',
                     'year',
                     'status',
                     'type',
                     'document',
                     'supplier',
                     'evaluation_stage',
                     'rating',
                     'rating_likert',
                     'assessment_template',
                     'assessment',
                     'note',
                     'modified'],
 'purchase_order': ['name', 'modified'],
 'purchase_receipt': ['name', 'modified'],
 'quality_inspection': ['name', 'modified'],
 'request_for_quotation': ['name', 'modified'],
 'compliance_tracking': ['name', 'modified'],
 'risk_register': ['name', 'modified'],
 'business_continuity': ['name', 'modified'],
 'business_impact_analysis': ['name', 'modified']}

CHILD_SAFE_FIELDS = {'Quality Action Resolution': ['idx',
                               'finding_type',
                               'status',
                               'responsible',
                               'full_name',
                               'target_date',
                               'completion_by'],
 'Strategic Planning Audit Results': ['idx'],
 'Strategic Planning Nonconformities and Corrective Actions': ['idx'],
 'Management Review Strategic Planning Innovation Childtable': ['idx'],
 'Strategic Planning Performance of External Providers': ['idx'],
 'Strategic Planning Risk and Opportunities': ['idx'],
 'Quality Action Performance Indicators Childtable': ['idx'],
 'Risk Identification Childtable': ['idx'],
 'Risk Justification Childtable': ['idx']}

FILTER_FIELD_CANDIDATES = {'quality_action': {'year_date': ['date', 'custom_proposed_date', 'custom_completed_date'],
                    'status': ['custom_status_updates', 'status']},
 'management_review': {'year_date': ['review_date'], 'status': ['review_status']},
 'operational_outcomes': {'year_value': ['monitoring_year'], 'year_date': ['period_start', 'period_end']},
 'provider_rating': {'year_value': ['year'], 'year_date': ['posting_date'], 'status': ['status']}}

CONFIG = {'6.1.1': {'sources': ['oversight_framework', 'quality_action', 'management_review', 'responsibilities'],
           'metrics': [{'id': 'c611-audit-records',
                        'label': 'Oversight Framework audit records',
                        'source': 'oversight_framework',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c611-actions',
                        'label': 'Quality Actions in scope',
                        'source': 'quality_action',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c611-open-resolutions',
                        'label': 'Open Corrective Action Plan rows',
                        'source': 'quality_action',
                        'mode': 'child_count',
                        'table_field': ['resolutions'],
                        'child_doctype': 'Quality Action Resolution',
                        'conditions': [{'field': ['status'], 'op': 'not_in', 'values': ['Completed', 'Closed']}],
                        'evidence_level': 'process_status'},
                       {'id': 'c611-overdue-resolutions',
                        'label': 'Overdue Corrective Action Plan rows',
                        'source': 'quality_action',
                        'mode': 'child_count',
                        'table_field': ['resolutions'],
                        'child_doctype': 'Quality Action Resolution',
                        'conditions': [{'field': ['target_date'], 'op': 'date_before_today'},
                                       {'field': ['status'], 'op': 'not_in', 'values': ['Completed', 'Closed']}],
                        'evidence_level': 'timeliness'},
                       {'id': 'c611-nonconformities',
                        'label': 'Non-conformity finding rows',
                        'source': 'quality_action',
                        'mode': 'child_count',
                        'table_field': ['resolutions'],
                        'child_doctype': 'Quality Action Resolution',
                        'conditions': [{'field': ['finding_type'],
                                        'op': 'in',
                                        'values': ['NC', 'Min. NC', 'Maj. NC', 'Minor NC', 'Major NC']}],
                        'evidence_level': 'record_existence'},
                       {'id': 'c611-incomplete-cap-control',
                        'label': 'Corrective Action Plan rows missing owner or target date',
                        'source': 'quality_action',
                        'mode': 'child_any_missing',
                        'table_field': ['resolutions'],
                        'child_doctype': 'Quality Action Resolution',
                        'required_fields': [['responsible', 'full_name'], ['target_date']],
                        'evidence_level': 'record_completeness'},
                       {'id': 'c611-review-audit-evidence',
                        'label': 'Management Reviews containing audit-results rows',
                        'source': 'management_review',
                        'mode': 'child_parent_count',
                        'table_field': ['table_efwt'],
                        'child_doctype': 'Strategic Planning Audit Results',
                        'evidence_level': 'record_existence'},
                       {'id': 'c611-review-nc-evidence',
                        'label': 'Management Reviews containing non-conformity action rows',
                        'source': 'management_review',
                        'mode': 'child_parent_count',
                        'table_field': ['nonconformities_corrective_actions'],
                        'child_doctype': 'Strategic Planning Nonconformities and Corrective Actions',
                        'evidence_level': 'record_existence'}]},
 '6.2.1': {'sources': ['management_review', 'quality_action', 'quality_meeting', 'responsibilities'],
           'metrics': [{'id': 'c621-reviews',
                        'label': 'Management Review records in scope',
                        'source': 'management_review',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c621-completed',
                        'label': 'Completed Management Review records',
                        'source': 'management_review',
                        'mode': 'equals',
                        'field': ['review_status'],
                        'value': 'Completed',
                        'evidence_level': 'process_status'},
                       {'id': 'c621-postponed',
                        'label': 'Postponed Management Review records',
                        'source': 'management_review',
                        'mode': 'equals',
                        'field': ['review_status'],
                        'value': 'Postponed',
                        'evidence_level': 'management_attention'},
                       {'id': 'c621-overdue-next-review',
                        'label': 'Overdue Management Review next-review dates',
                        'source': 'management_review',
                        'mode': 'conditions',
                        'conditions': [{'field': ['next_review_date'], 'op': 'date_before_today'},
                                       {'field': ['review_status'], 'op': 'not_in', 'values': ['Completed', 'Closed']}],
                        'evidence_level': 'timeliness'},
                       {'id': 'c621-minutes',
                        'label': 'Management Reviews with minutes',
                        'source': 'management_review',
                        'mode': 'truthy',
                        'field': ['minutes_of_meeting'],
                        'evidence_level': 'record_completeness'},
                       {'id': 'c621-thesis-complete',
                        'label': 'Management Reviews with all THESIS evidence groups',
                        'source': 'management_review',
                        'mode': 'all_required',
                        'fields': [['leaderhip_note', 'essential_information'],
                                   ['resource_note', 'table_bhwb'],
                                   ['process_performance_note', 'process_performace_conformity'],
                                   ['risk_note', 'risk_opportunities'],
                                   ['bcp__note', 'business_continuity'],
                                   ['opportunities_note', 'table_qzdd']],
                        'evidence_level': 'record_completeness'},
                       {'id': 'c621-action-rows',
                        'label': 'Management Review action rows',
                        'source': 'management_review',
                        'mode': 'child_count',
                        'table_field': ['table_qzdd'],
                        'child_doctype': 'Management Review Strategic Planning Innovation Childtable',
                        'evidence_level': 'record_existence'},
                       {'id': 'c621-linked-quality-actions',
                        'label': 'Quality Actions linked to a meeting',
                        'source': 'quality_action',
                        'mode': 'truthy',
                        'field': ['custom_quality_meeting'],
                        'evidence_level': 'source_linkage'}]},
 '6.3.1': {'sources': ['quality_action', 'quality_performance_outcomes', 'operational_outcomes', 'management_review'],
           'metrics': [{'id': 'c631-innovation-actions',
                        'label': 'Innovation Quality Actions',
                        'source': 'quality_action',
                        'mode': 'truthy',
                        'field': ['custom_innovation'],
                        'evidence_level': 'record_classification'},
                       {'id': 'c631-improvement-actions',
                        'label': 'Continual-improvement Quality Actions',
                        'source': 'quality_action',
                        'mode': 'truthy',
                        'field': ['custom_continuous_improvement'],
                        'evidence_level': 'record_classification'},
                       {'id': 'c631-plan-core-complete',
                        'label': 'Quality Actions with core goal, review and procedure fields',
                        'source': 'quality_action',
                        'mode': 'all_required',
                        'fields': [['goal'], ['review'], ['procedure']],
                        'evidence_level': 'record_completeness'},
                       {'id': 'c631-innovation-type',
                        'label': 'Actions with innovation type recorded',
                        'source': 'quality_action',
                        'mode': 'truthy',
                        'field': ['custom_type_of_innovation'],
                        'evidence_level': 'record_completeness'},
                       {'id': 'c631-innovation-category',
                        'label': 'Actions with innovation category recorded',
                        'source': 'quality_action',
                        'mode': 'truthy',
                        'field': ['custom_innovation_category'],
                        'evidence_level': 'record_completeness'},
                       {'id': 'c631-performance-evidence',
                        'label': 'Actions with performance-indicator rows',
                        'source': 'quality_action',
                        'mode': 'child_parent_count',
                        'table_field': ['custom_performance'],
                        'child_doctype': 'Quality Action Performance Indicators Childtable',
                        'evidence_level': 'record_existence'},
                       {'id': 'c631-qipi',
                        'label': 'Average stored QIPI',
                        'source': 'quality_action',
                        'mode': 'average',
                        'field': ['custom_aggregated_performance_index_api'],
                        'unit': 'index',
                        'evidence_level': 'stored_calculation'},
                       {'id': 'c631-tacei',
                        'label': 'Average stored TACEI',
                        'source': 'quality_action',
                        'mode': 'average',
                        'field': ['custom_timeadjusted_cost_efficiency_index_tacei'],
                        'unit': 'index',
                        'evidence_level': 'stored_calculation'},
                       {'id': 'c631-cei',
                        'label': 'Average stored CEI',
                        'source': 'quality_action',
                        'mode': 'average',
                        'field': ['custom_cost_efficiency_index_cei'],
                        'unit': 'index',
                        'evidence_level': 'stored_calculation'},
                       {'id': 'c631-completed',
                        'label': 'Completed Quality Actions',
                        'source': 'quality_action',
                        'mode': 'equals',
                        'field': ['custom_status_updates', 'status'],
                        'value': 'Completed',
                        'evidence_level': 'process_status'},
                       {'id': 'c631-outcome-records',
                        'label': 'Operational outcome monitoring records',
                        'source': 'operational_outcomes',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c631-net-saving',
                        'label': 'Total net operational saving',
                        'source': 'operational_outcomes',
                        'mode': 'sum',
                        'field': ['total_net_saving'],
                        'unit': 'SGD',
                        'evidence_level': 'operational_outcome'},
                       {'id': 'c631-linked-meeting',
                        'label': 'Quality Actions linked to a meeting',
                        'source': 'quality_action',
                        'mode': 'truthy',
                        'field': ['custom_quality_meeting'],
                        'evidence_level': 'source_linkage'}]},
 '6.4.1': {'sources': ['provider',
                       'provider_rating',
                       'purchase_order',
                       'purchase_receipt',
                       'quality_inspection',
                       'request_for_quotation',
                       'compliance_tracking',
                       'management_review'],
           'metrics': [{'id': 'c641-providers',
                        'label': 'Provider master records',
                        'source': 'provider',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c641-ratings',
                        'label': 'Provider Rating records',
                        'source': 'provider_rating',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c641-screening',
                        'label': 'Identification and Screening evaluations',
                        'source': 'provider_rating',
                        'mode': 'equals',
                        'field': ['evaluation_stage'],
                        'value': 'Identification and Screening',
                        'evidence_level': 'process_initiation'},
                       {'id': 'c641-regular-review',
                        'label': 'Renewal and Regular Review evaluations',
                        'source': 'provider_rating',
                        'mode': 'equals',
                        'field': ['evaluation_stage'],
                        'value': 'Renewal and Regular Review',
                        'evidence_level': 'process_initiation'},
                       {'id': 'c641-passing',
                        'label': 'Provider Ratings at or above 3.5',
                        'source': 'provider_rating',
                        'mode': 'number_gte',
                        'field': ['rating', 'rating_likert'],
                        'value': 3.5,
                        'evidence_level': 'performance_threshold'},
                       {'id': 'c641-below-passing',
                        'label': 'Provider Ratings below 3.5',
                        'source': 'provider_rating',
                        'mode': 'number_lt',
                        'field': ['rating', 'rating_likert'],
                        'value': 3.5,
                        'evidence_level': 'management_attention'},
                       {'id': 'c641-critical-failure',
                        'label': 'Provider Ratings below 3.0',
                        'source': 'provider_rating',
                        'mode': 'number_lt',
                        'field': ['rating', 'rating_likert'],
                        'value': 3.0,
                        'evidence_level': 'management_attention'},
                       {'id': 'c641-missing-rating',
                        'label': 'Provider Rating records without a rating',
                        'source': 'provider_rating',
                        'mode': 'falsy',
                        'field': ['rating', 'rating_likert'],
                        'evidence_level': 'record_completeness'},
                       {'id': 'c641-continuation',
                        'label': 'Provider evaluations approved for continuation',
                        'source': 'provider_rating',
                        'mode': 'equals',
                        'field': ['status'],
                        'value': 'Approved for Continuation',
                        'evidence_level': 'decision_status'},
                       {'id': 'c641-terminated',
                        'label': 'Provider evaluations resulting in termination',
                        'source': 'provider_rating',
                        'mode': 'equals',
                        'field': ['status'],
                        'value': 'Terminated',
                        'evidence_level': 'decision_status'},
                       {'id': 'c641-purchase-orders',
                        'label': 'Purchase Order records',
                        'source': 'purchase_order',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c641-purchase-receipts',
                        'label': 'Purchase Receipt records',
                        'source': 'purchase_receipt',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c641-inspections',
                        'label': 'Quality Inspection records',
                        'source': 'quality_inspection',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c641-rfqs',
                        'label': 'Request for Quotation records',
                        'source': 'request_for_quotation',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c641-compliance-tracking',
                        'label': 'Compliance Tracking records',
                        'source': 'compliance_tracking',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c641-review-evidence',
                        'label': 'Management Reviews with provider-performance rows',
                        'source': 'management_review',
                        'mode': 'child_parent_count',
                        'table_field': ['table_kenc'],
                        'child_doctype': 'Strategic Planning Performance of External Providers',
                        'evidence_level': 'record_existence'}]},
 '6.5.3': {'sources': ['risk_register', 'quality_action', 'management_review', 'business_continuity', 'business_impact_analysis'],
           'metrics': [{'id': 'c653-risk-records',
                        'label': 'Risk Register records',
                        'source': 'risk_register',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c653-risk-assessments',
                        'label': 'Quality Actions with risk-identification rows',
                        'source': 'quality_action',
                        'mode': 'child_parent_count',
                        'table_field': ['custom_risk_identification_table'],
                        'child_doctype': 'Risk Identification Childtable',
                        'evidence_level': 'record_existence'},
                       {'id': 'c653-risk-mitigation',
                        'label': 'Quality Actions with mitigation rows',
                        'source': 'quality_action',
                        'mode': 'child_parent_count',
                        'table_field': ['custom_risk_mitigation'],
                        'child_doctype': 'Risk Justification Childtable',
                        'evidence_level': 'record_existence'},
                       {'id': 'c653-risk-notes',
                        'label': 'Quality Actions with risk notes',
                        'source': 'quality_action',
                        'mode': 'truthy',
                        'field': ['custom_risk_and_opportunities_identified'],
                        'evidence_level': 'record_completeness'},
                       {'id': 'c653-priority',
                        'label': 'Quality Actions with priority score',
                        'source': 'quality_action',
                        'mode': 'truthy',
                        'field': ['custom_priority_score'],
                        'evidence_level': 'record_completeness'},
                       {'id': 'c653-review-risk-evidence',
                        'label': 'Management Reviews with risk-and-opportunity rows',
                        'source': 'management_review',
                        'mode': 'child_parent_count',
                        'table_field': ['risk_opportunities'],
                        'child_doctype': 'Strategic Planning Risk and Opportunities',
                        'evidence_level': 'record_existence'},
                       {'id': 'c653-bcdr-records',
                        'label': 'Business Continuity and Disaster Recovery records',
                        'source': 'business_continuity',
                        'mode': 'all',
                        'evidence_level': 'record_existence'},
                       {'id': 'c653-bia-records',
                        'label': 'Business Impact Analysis records',
                        'source': 'business_impact_analysis',
                        'mode': 'all',
                        'evidence_level': 'record_existence'}]}}

QUESTION_REGISTRY = {'6.1.1': [{'id': 'q611-01',
            'question': 'Was the annual audit programme complete and approved by the Principal before implementation?',
            'metric_id': None,
            'purpose': 'Audit programme governance',
            'requirement_reference': '6.1.1 Audit Schedule and Approval',
            'applicable_population': 'Required annual audit programme for the reporting year',
            'management_decision': 'Approve, correct or escalate incomplete audit programmes',
            'support_status': 'Requires additional fields',
            'source_key': 'oversight_framework',
            'limitation': 'The supplied metadata does not confirm scope, auditee-confirmation or Principal-approval fields.'},
           {'id': 'q611-02',
            'question': 'Were audit scope, plan and checklist complete before each audit was conducted?',
            'metric_id': None,
            'purpose': 'Audit readiness',
            'requirement_reference': '6.1.1 Audit Plan and Audit Checklist',
            'applicable_population': 'Audit assignments conducted in the reporting period',
            'management_decision': 'Stop, defer or remediate audits lacking approved readiness evidence',
            'support_status': 'Requires additional fields',
            'source_key': 'oversight_framework',
            'limitation': 'Audit-plan, checklist and execution-date fields were not supplied.'},
           {'id': 'q611-03',
            'question': 'Were all assigned auditors qualified and independent of the audited area?',
            'metric_id': None,
            'purpose': 'Auditor competence and independence',
            'requirement_reference': '6.1.1 Qualified Independent Auditors',
            'applicable_population': 'Audit assignments in the reporting period',
            'management_decision': 'Reassign conflicted auditors or obtain external support',
            'support_status': 'Requires a new DocType or child-table query',
            'source_key': 'responsibilities',
            'limitation': 'Auditor assignment, competence and independence evidence is not mapped.'},
           {'id': 'q611-04',
            'question': 'Did auditees receive notification within the approved lead time?',
            'metric_id': None,
            'purpose': 'Notification timeliness',
            'requirement_reference': '6.1.1 Audit Notification',
            'applicable_population': 'Audits requiring auditee notification',
            'management_decision': 'Escalate late or unverified notifications',
            'support_status': 'Document evidence only',
            'source_key': 'oversight_framework',
            'limitation': 'The procedure contains a 14-day versus 14-working-day conflict that must be resolved before calculation.'},
           {'id': 'q611-05',
            'question': 'Were audit reports issued within thirty working days of the audit date?',
            'metric_id': None,
            'purpose': 'Audit-report timeliness',
            'requirement_reference': '6.1.1 Audit Report',
            'applicable_population': 'Completed audits with report due dates',
            'management_decision': 'Escalate late reports or document approved extensions',
            'support_status': 'Requires additional fields',
            'source_key': 'oversight_framework',
            'limitation': 'Audit date, report date and approved-extension fields were not supplied.'},
           {'id': 'q611-06',
            'question': 'How many non-conformity findings are recorded in Quality Action resolution rows?',
            'metric_id': 'c611-nonconformities',
            'purpose': 'Finding population visibility',
            'requirement_reference': '6.1.1 Findings and Non-conformity Management',
            'applicable_population': 'Quality Action resolution rows classified as non-conformities',
            'management_decision': 'Review the affected findings and confirm root-cause and CAP requirements',
            'support_status': 'Can be implemented now',
            'source_key': 'quality_action',
            'limitation': ''},
           {'id': 'q611-07',
            'question': 'Which Corrective Action Plan rows are missing an owner or target date?',
            'metric_id': 'c611-incomplete-cap-control',
            'purpose': 'CAP completeness',
            'requirement_reference': '6.1.1 Corrective Action Plan',
            'applicable_population': 'Corrective Action Plan rows in Quality Action',
            'management_decision': 'Assign owners and deadlines before implementation',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'quality_action',
            'limitation': ''},
           {'id': 'q611-08',
            'question': 'Which Corrective Action Plan rows are overdue and still open?',
            'metric_id': 'c611-overdue-resolutions',
            'purpose': 'CAP implementation timeliness',
            'requirement_reference': '6.1.1 Corrective Action Plan Monitoring',
            'applicable_population': 'Open CAP rows with target dates already due',
            'management_decision': 'Escalate overdue actions and approve supported revised dates',
            'support_status': 'Can be implemented now',
            'source_key': 'quality_action',
            'limitation': ''},
           {'id': 'q611-09',
            'question': 'Were Corrective Action Reports submitted within fourteen working days of formal report receipt?',
            'metric_id': None,
            'purpose': 'Corrective Action Report timeliness',
            'requirement_reference': '6.1.1 Corrective Action Report',
            'applicable_population': 'Findings requiring a Corrective Action Report and already due',
            'management_decision': 'Escalate late, missing or incomplete reports',
            'support_status': 'Requires additional fields',
            'source_key': 'oversight_framework',
            'limitation': 'Formal-report receipt and CAR submission dates are not mapped.'},
           {'id': 'q611-10',
            'question': 'Were CAPs approved by the Principal before implementation began?',
            'metric_id': None,
            'purpose': 'Approval-before-implementation compliance',
            'requirement_reference': '6.1.1 Corrective Action Plan Approval',
            'applicable_population': 'CAPs implemented or due for implementation',
            'management_decision': 'Stop or investigate unapproved implementation',
            'support_status': 'Requires additional fields',
            'source_key': 'quality_action',
            'limitation': 'Approval role/date and implementation-start fields are not mapped.'},
           {'id': 'q611-11',
            'question': 'Were implemented CAPs independently verified as effective before closure?',
            'metric_id': None,
            'purpose': 'Effectiveness and closure compliance',
            'requirement_reference': '6.1.1 Follow-up and Verification',
            'applicable_population': 'CAPs due for effectiveness review',
            'management_decision': 'Reopen unverified or ineffective CAPs and conduct follow-up or re-audit',
            'support_status': 'Requires additional fields',
            'source_key': 'quality_action',
            'limitation': 'Independent verifier, effectiveness evidence and closure-confirmation fields are not mapped.'}],
 '6.2.1': [{'id': 'q621-01',
            'question': 'Was the required annual Management Review conducted with complete evidence?',
            'metric_id': 'c621-completed',
            'purpose': 'Annual review completion',
            'requirement_reference': '6.2.1 Annual Management Review',
            'applicable_population': 'Reporting years in scope',
            'management_decision': 'Schedule or complete missing annual reviews',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'management_review',
            'limitation': 'A completed record is visible, but annual denominator and completeness evidence require further fields.'},
           {'id': 'q621-02',
            'question': 'Were required participants invited at least one month before the review date?',
            'metric_id': None,
            'purpose': 'Invitation timeliness',
            'requirement_reference': '6.2.1 Review Invitation',
            'applicable_population': 'Management Reviews requiring departmental participation',
            'management_decision': 'Escalate late invitations and obtain missing departmental inputs',
            'support_status': 'Requires additional fields',
            'source_key': 'management_review',
            'limitation': 'Invitation date and participant-list fields are not mapped.'},
           {'id': 'q621-03',
            'question': 'Did each Management Review contain all six THESIS evidence areas?',
            'metric_id': 'c621-thesis-complete',
            'purpose': 'Management Review input completeness',
            'requirement_reference': '6.2.1 THESIS Framework',
            'applicable_population': 'Management Reviews conducted in the reporting period',
            'management_decision': 'Complete missing THESIS inputs before finalising decisions',
            'support_status': 'Can be implemented now',
            'source_key': 'management_review',
            'limitation': ''},
           {'id': 'q621-04',
            'question': 'Did completed Management Reviews include meeting minutes?',
            'metric_id': 'c621-minutes',
            'purpose': 'Meeting evidence completeness',
            'requirement_reference': '6.2.1 Minutes and Decisions',
            'applicable_population': 'Management Reviews conducted in the reporting period',
            'management_decision': 'Complete and distribute missing minutes',
            'support_status': 'Can be implemented now',
            'source_key': 'management_review',
            'limitation': ''},
           {'id': 'q621-05',
            'question': 'How many Management Review action rows were raised?',
            'metric_id': 'c621-action-rows',
            'purpose': 'Action population visibility',
            'requirement_reference': '6.2.1 Outputs and Action Tracking',
            'applicable_population': 'Action rows arising from Management Reviews',
            'management_decision': 'Confirm every action is transferred into controlled tracking',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'management_review',
            'limitation': ''},
           {'id': 'q621-06',
            'question': 'Were Management Review actions assigned an owner, deadline and Principal approval before execution?',
            'metric_id': None,
            'purpose': 'Action-control compliance',
            'requirement_reference': '6.2.1 Action Ownership and Approval',
            'applicable_population': 'Management Review actions raised',
            'management_decision': 'Assign, approve or escalate incomplete actions',
            'support_status': 'Requires a new DocType or child-table query',
            'source_key': 'management_review',
            'limitation': 'The child-table metadata supplied only confirms row existence, not owner, deadline or approval fields.'},
           {'id': 'q621-07',
            'question': 'Were previous Management Review actions completed and verified as effective?',
            'metric_id': None,
            'purpose': 'Action effectiveness',
            'requirement_reference': '6.2.1 Follow-up and Continual Improvement',
            'applicable_population': 'Actions due for effectiveness review',
            'management_decision': 'Reopen ineffective or unverified actions',
            'support_status': 'Requires additional fields',
            'source_key': 'quality_action',
            'limitation': 'Outcome, sustained-effectiveness and review-date fields are not mapped.'},
           {'id': 'q621-08',
            'question': 'Which Management Reviews are postponed or have overdue next-review dates?',
            'metric_id': 'c621-postponed',
            'purpose': 'Management attention and scheduling',
            'requirement_reference': '6.2.1 Annual Review Cycle',
            'applicable_population': 'Management Review records in scope',
            'management_decision': 'Reschedule and escalate postponed reviews',
            'support_status': 'Can be implemented now',
            'source_key': 'management_review',
            'limitation': ''},
           {'id': 'q621-09',
            'question': 'Are Management Review decisions linked to controlled Quality Action records?',
            'metric_id': 'c621-linked-quality-actions',
            'purpose': 'Traceability of decisions',
            'requirement_reference': '6.2.1 Decisions and Action Tracking',
            'applicable_population': 'Quality Actions arising from Management Review',
            'management_decision': 'Create or correct missing source links',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'quality_action',
            'limitation': ''},
           {'id': 'q621-10',
            'question': 'Is the Management Representative appointment, competence and annual evaluation evidenced?',
            'metric_id': None,
            'purpose': 'Management Representative governance',
            'requirement_reference': '6.2.1 MR Appointment and Performance Evaluation',
            'applicable_population': 'Current Management Representative appointment and annual evaluation',
            'management_decision': 'Obtain appointment, competence or evaluation evidence',
            'support_status': 'Document evidence only',
            'source_key': 'responsibilities',
            'limitation': 'No verified structured source links the appointment, training and annual evaluation evidence.'}],
 '6.3.1': [{'id': 'q631-01',
            'question': 'Are improvement opportunities from meetings, audits, course reviews and stakeholder feedback logged in Quality Action?',
            'metric_id': None,
            'purpose': 'Improvement-opportunity logging',
            'requirement_reference': '6.3.1 Opportunity Identification',
            'applicable_population': 'Verified improvement opportunities identified in source records',
            'management_decision': 'Create missing Quality Actions and correct source links',
            'support_status': 'Requires a new DocType or child-table query',
            'source_key': 'quality_action',
            'limitation': 'Cross-source opportunity denominators and linkage fields are not mapped.'},
           {'id': 'q631-02',
            'question': 'How many Quality Actions are classified as innovation or continual improvement?',
            'metric_id': 'c631-innovation-actions',
            'purpose': 'Initiative population visibility',
            'requirement_reference': '6.3.1 Innovation and Continual Improvement Classification',
            'applicable_population': 'Quality Actions in the reporting period',
            'management_decision': 'Confirm correct classification and ownership',
            'support_status': 'Can be implemented now',
            'source_key': 'quality_action',
            'limitation': ''},
           {'id': 'q631-03',
            'question': 'Which Quality Actions have the core goal, review and procedure fields completed?',
            'metric_id': 'c631-plan-core-complete',
            'purpose': 'Improvement-plan completeness',
            'requirement_reference': '6.3.1 Improvement Objectives, Goals and Plans',
            'applicable_population': 'Quality Actions requiring implementation plans',
            'management_decision': 'Complete missing plan components before implementation',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'quality_action',
            'limitation': 'This is a partial completeness check and does not yet cover owner, tasks, resources, budget and expected outcomes.'},
           {'id': 'q631-04',
            'question': 'Were initiative objectives SMART, strategically aligned and supported by stakeholder feedback?',
            'metric_id': None,
            'purpose': 'Objective quality and alignment',
            'requirement_reference': '6.3.1 SMART Goals, Strategic Alignment and Feedback Integration',
            'applicable_population': 'Improvement initiatives requiring approval',
            'management_decision': 'Revise objectives or obtain missing stakeholder evidence',
            'support_status': 'Requires additional fields',
            'source_key': 'quality_action',
            'limitation': 'SMART tests, strategic-goal linkage and feedback evidence are not fully mapped.'},
           {'id': 'q631-05',
            'question': 'Was feasibility analysis completed and authorised approval obtained before implementation?',
            'metric_id': None,
            'purpose': 'Feasibility and approval-before-implementation',
            'requirement_reference': '6.3.1 Feasibility and Approval',
            'applicable_population': 'Initiatives implemented or due for implementation',
            'management_decision': 'Stop, approve or redesign unsupported initiatives',
            'support_status': 'Requires additional fields',
            'source_key': 'quality_action',
            'limitation': 'Feasibility outcome, approval role/date and implementation-start fields are not mapped.'},
           {'id': 'q631-06',
            'question': 'Do initiatives contain performance-indicator rows for before-and-after evaluation?',
            'metric_id': 'c631-performance-evidence',
            'purpose': 'Outcome-measurement readiness',
            'requirement_reference': '6.3.1 Performance Indicators and QIPI',
            'applicable_population': 'Initiatives required to report measurable outcomes',
            'management_decision': 'Add missing indicators before effectiveness review',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'quality_action',
            'limitation': ''},
           {'id': 'q631-07',
            'question': 'Is QIPI calculated correctly from complete and valid indicator data?',
            'metric_id': None,
            'purpose': 'QIPI calculation validity',
            'requirement_reference': '6.3.1 QIPI Data Structure',
            'applicable_population': 'Initiatives required to report QIPI',
            'management_decision': 'Correct invalid calculations or complete missing indicator inputs',
            'support_status': 'Requires a new DocType or child-table query',
            'source_key': 'quality_performance_outcomes',
            'limitation': 'The current API can read a stored QIPI value but cannot validate before, after, min, max and indicator denominator values.'},
           {'id': 'q631-08',
            'question': 'What is the average stored QIPI for records with a numeric value?',
            'metric_id': 'c631-qipi',
            'purpose': 'Stored performance visibility',
            'requirement_reference': '6.3.1 QIPI Monitoring',
            'applicable_population': 'Quality Actions with stored QIPI values in the reporting period',
            'management_decision': 'Investigate low or unsupported values, without treating the stored value as validated',
            'support_status': 'Can be implemented now',
            'source_key': 'quality_action',
            'limitation': ''},
           {'id': 'q631-09',
            'question': 'What measurable net operational saving is recorded?',
            'metric_id': 'c631-net-saving',
            'purpose': 'Operational outcome monitoring',
            'requirement_reference': '6.3.1 Innovation Investment and Performance Governance',
            'applicable_population': 'Operational outcome records in the reporting period',
            'management_decision': 'Validate savings evidence and use results in resource decisions',
            'support_status': 'Can be implemented now',
            'source_key': 'operational_outcomes',
            'limitation': ''},
           {'id': 'q631-10',
            'question': 'Were completed initiatives verified as effective and presented at Management Review?',
            'metric_id': None,
            'purpose': 'Effectiveness and governance closure',
            'requirement_reference': '6.3.1 Monitoring, Validation and Management Review',
            'applicable_population': 'Initiatives due for effectiveness review',
            'management_decision': 'Reopen, adjust or discontinue ineffective or unverified initiatives',
            'support_status': 'Requires additional fields',
            'source_key': 'quality_action',
            'limitation': 'Completion status, outcome evidence, sustained-effectiveness and Management Review decision are not jointly mapped.'}],
 '6.4.1': [{'id': 'q641-01',
            'question': 'Did every in-scope Provider complete the required screening, documents, tier classification, risk assessment and Principal approval '
                        'before accreditation?',
            'metric_id': None,
            'purpose': 'Provider accreditation readiness',
            'requirement_reference': '6.4.1 Provider Accreditation and Screening',
            'applicable_population': 'Providers accredited or used during the period',
            'management_decision': 'Withhold or suspend accreditation until controls are complete',
            'support_status': 'Requires additional fields',
            'source_key': 'provider',
            'limitation': 'Provider master fields for screening, legal documents, tier, risk and approval are not supplied.'},
           {'id': 'q641-02',
            'question': 'How many Provider Rating records are at or above the 3.5 passing threshold?',
            'metric_id': 'c641-passing',
            'purpose': 'Provider performance threshold',
            'requirement_reference': '6.4.1 Performance Evaluation Criteria',
            'applicable_population': 'Provider Rating records with numeric ratings',
            'management_decision': 'Continue, monitor or approve Providers meeting the threshold',
            'support_status': 'Can be implemented now',
            'source_key': 'provider_rating',
            'limitation': ''},
           {'id': 'q641-03',
            'question': 'Which Provider Rating records are below the 3.5 passing threshold?',
            'metric_id': 'c641-below-passing',
            'purpose': 'Provider performance exception',
            'requirement_reference': '6.4.1 Performance Evaluation Criteria',
            'applicable_population': 'Provider Rating records with numeric ratings',
            'management_decision': 'Require improvement, review or contract action',
            'support_status': 'Can be implemented now',
            'source_key': 'provider_rating',
            'limitation': ''},
           {'id': 'q641-04',
            'question': 'Which Provider Rating records are below 3.0 and may require formal review or termination?',
            'metric_id': 'c641-critical-failure',
            'purpose': 'Critical Provider performance exception',
            'requirement_reference': '6.4.1 Performance Evaluation and Compliance',
            'applicable_population': 'Provider Rating records with numeric ratings',
            'management_decision': 'Escalate for formal improvement, contract review or termination',
            'support_status': 'Can be implemented now',
            'source_key': 'provider_rating',
            'limitation': ''},
           {'id': 'q641-05',
            'question': 'Which Provider Rating records are missing a numeric rating?',
            'metric_id': 'c641-missing-rating',
            'purpose': 'Rating completeness',
            'requirement_reference': '6.4.1 Provider Performance Evaluation',
            'applicable_population': 'Provider Rating records in scope',
            'management_decision': 'Complete the evaluation before a continuation decision',
            'support_status': 'Can be implemented now',
            'source_key': 'provider_rating',
            'limitation': ''},
           {'id': 'q641-06',
            'question': 'Did Providers engaged for six months or more receive the required annual evaluation, and were critical Providers evaluated at the '
                        'approved frequency?',
            'metric_id': None,
            'purpose': 'Evaluation-cycle compliance',
            'requirement_reference': '6.4.1 Evaluation Frequency',
            'applicable_population': 'Providers due for evaluation',
            'management_decision': 'Schedule overdue evaluations and escalate critical gaps',
            'support_status': 'Requires a new DocType or child-table query',
            'source_key': 'provider',
            'limitation': 'Engagement start, tier, criticality and evaluation-cycle linkage are not mapped.'},
           {'id': 'q641-07',
            'question': 'Were weighted Provider ratings correct and independently reviewed?',
            'metric_id': None,
            'purpose': 'Rating integrity and independence',
            'requirement_reference': '6.4.1 Performance Evaluation Controls',
            'applicable_population': 'Provider evaluations requiring independent review',
            'management_decision': 'Recalculate or independently review unsupported ratings',
            'support_status': 'Requires additional fields',
            'source_key': 'provider_rating',
            'limitation': 'Weighting inputs, calculation evidence and reviewer independence fields are not mapped.'},
           {'id': 'q641-08',
            'question': 'Did purchases above $500 and $1,000 contain the required price-reasonableness evidence or valid approved exemption?',
            'metric_id': None,
            'purpose': 'Purchase price-reasonableness compliance',
            'requirement_reference': '6.4.1 Purchase Management',
            'applicable_population': 'Purchases above the applicable thresholds',
            'management_decision': 'Obtain comparison evidence or approved emergency justification',
            'support_status': 'Requires additional fields',
            'source_key': 'purchase_order',
            'limitation': 'Purchase amount, evidence-count, exemption and Principal-approval fields are not supplied.'},
           {'id': 'q641-09',
            'question': 'Was delivery, receipt and inspection evidence complete, including discrepancy action within five business days?',
            'metric_id': None,
            'purpose': 'Purchase delivery and inspection control',
            'requirement_reference': '6.4.1 Service Delivery and Purchase Management',
            'applicable_population': 'Purchases requiring receipt or inspection',
            'management_decision': 'Resolve missing receipts, inspections or late discrepancies',
            'support_status': 'Requires a new DocType or child-table query',
            'source_key': 'purchase_receipt',
            'limitation': 'Cross-DocType links and discrepancy dates are not mapped.'},
           {'id': 'q641-10',
            'question': 'How many Provider evaluations resulted in continuation or termination decisions?',
            'metric_id': 'c641-continuation',
            'purpose': 'Provider decision visibility',
            'requirement_reference': '6.4.1 Evaluation Outcomes',
            'applicable_population': 'Provider Rating records in the reporting period',
            'management_decision': 'Review the underlying evaluation evidence before confirming decisions',
            'support_status': 'Can be implemented now',
            'source_key': 'provider_rating',
            'limitation': ''},
           {'id': 'q641-11',
            'question': 'Are Provider performance results reviewed in Management Review?',
            'metric_id': 'c641-review-evidence',
            'purpose': 'Management oversight of Providers',
            'requirement_reference': '6.4.1 Performance Monitoring and Management Review',
            'applicable_population': 'Management Reviews in the reporting period',
            'management_decision': 'Add missing Provider-performance inputs to Management Review',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'management_review',
            'limitation': ''},
           {'id': 'q641-12',
            'question': 'Did Provider offboarding complete Principal approval, data return or deletion, access revocation, final rating and linked Compliance '
                        'Tracking?',
            'metric_id': None,
            'purpose': 'Provider offboarding compliance',
            'requirement_reference': '6.4.1 Offboarding and Exit Management',
            'applicable_population': 'Provider engagements terminated or expired',
            'management_decision': 'Complete missing exit controls before closure',
            'support_status': 'Requires additional fields',
            'source_key': 'provider',
            'limitation': 'Offboarding status, approval, data deletion, access revocation and linked Non Conformance fields are not supplied.'}],
 '6.5.3': [{'id': 'q653-01',
            'question': 'Are reported hazards recorded in the Risk Register and Mitigation Plans DocType?',
            'metric_id': 'c653-risk-records',
            'purpose': 'Hazard-to-risk traceability',
            'requirement_reference': '6.5.3 Risk Register Maintenance',
            'applicable_population': 'Reported hazards or events in scope',
            'management_decision': 'Create missing risk records and source links',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'risk_register',
            'limitation': 'Risk Register record existence can be measured, but the Helpdesk source and one-to-one hazard linkage are not verified.'},
           {'id': 'q653-02',
            'question': 'Do risk records contain all mandatory identification, consequence, mitigation, assignment and review fields?',
            'metric_id': None,
            'purpose': 'Risk-record completeness',
            'requirement_reference': '6.5.3 Essential Risk Register Fields',
            'applicable_population': 'Risk Register records in scope',
            'management_decision': 'Complete missing risk information before treatment decisions',
            'support_status': 'Requires additional fields',
            'source_key': 'risk_register',
            'limitation': 'The Risk Register DocType name is verified by the procedure, but its field metadata was not supplied.'},
           {'id': 'q653-03',
            'question': 'Were likelihood, severity and Risk Index calculated correctly using the 5x5 matrix?',
            'metric_id': None,
            'purpose': 'Risk calculation validity',
            'requirement_reference': '6.5.3 5x5 Risk Matrix',
            'applicable_population': 'Assessed risks in scope',
            'management_decision': 'Correct invalid scores and reclassify affected risks',
            'support_status': 'Requires additional fields',
            'source_key': 'risk_register',
            'limitation': 'Likelihood, severity and calculated-index fields are not mapped.'},
           {'id': 'q653-04',
            'question': 'Were risks correctly classified as Low 1-3, Medium 4-12 or High 15-25?',
            'metric_id': None,
            'purpose': 'Risk classification compliance',
            'requirement_reference': '6.5.3 Risk Classification Thresholds',
            'applicable_population': 'Assessed risks in scope',
            'management_decision': 'Reclassify incorrectly categorised risks and adjust treatment',
            'support_status': 'Requires additional fields',
            'source_key': 'risk_register',
            'limitation': 'Risk index and classification fields are not mapped.'},
           {'id': 'q653-05',
            'question': 'Did medium and high risks receive the required Quality Action, and did high risks trigger the Risk Management Team?',
            'metric_id': None,
            'purpose': 'Risk treatment and escalation compliance',
            'requirement_reference': '6.5.3 Risk Treatment and Escalation',
            'applicable_population': 'Medium and high risks in scope',
            'management_decision': 'Create missing actions or escalate high risks to the Risk Management Team',
            'support_status': 'Requires a new DocType or child-table query',
            'source_key': 'risk_register',
            'limitation': 'Cross-links between Risk Register, Quality Action and RMT activation are not mapped.'},
           {'id': 'q653-06',
            'question': 'How many Quality Actions contain risk-identification and mitigation rows?',
            'metric_id': 'c653-risk-assessments',
            'purpose': 'Risk-treatment evidence visibility',
            'requirement_reference': '6.5.3 Risk Identification and Mitigation',
            'applicable_population': 'Quality Actions with risk-related child tables',
            'management_decision': 'Review records lacking identification or mitigation evidence',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'quality_action',
            'limitation': ''},
           {'id': 'q653-07',
            'question': 'Are risk owners, actions, timelines and next-review dates complete?',
            'metric_id': None,
            'purpose': 'Risk treatment completeness',
            'requirement_reference': '6.5.3 Risk Register Essential Fields and Follow-up',
            'applicable_population': 'Risk records requiring treatment',
            'management_decision': 'Assign owners, deadlines and review dates',
            'support_status': 'Requires additional fields',
            'source_key': 'risk_register',
            'limitation': 'Owner, treatment, deadline and next-review fields are not mapped.'},
           {'id': 'q653-08',
            'question': 'Were residual risk and mitigation effectiveness assessed before closure?',
            'metric_id': None,
            'purpose': 'Risk reduction and closure effectiveness',
            'requirement_reference': '6.5.3 Monitoring, Effectiveness and Closure',
            'applicable_population': 'Risks due for closure or follow-up review',
            'management_decision': 'Reopen prematurely closed or ineffective risks',
            'support_status': 'Requires additional fields',
            'source_key': 'risk_register',
            'limitation': 'Residual-risk, effectiveness-evidence, verifier and closure-confirmation fields are not mapped.'},
           {'id': 'q653-09',
            'question': 'Were annual workplace inspections and required high-risk drills or exercises completed?',
            'metric_id': None,
            'purpose': 'Preventive-control completion',
            'requirement_reference': '6.5.3 Preventive Measures, Drills and Workplace Inspection',
            'applicable_population': 'Annual inspections and risk-triggered drills due in the period',
            'management_decision': 'Schedule missing inspections or drills and review findings',
            'support_status': 'Document evidence only',
            'source_key': 'business_continuity',
            'limitation': 'The procedure names activities and records, but no verified Workplace Inspection DocType or drill fields were supplied.'},
           {'id': 'q653-10',
            'question': 'Were risk and resilience matters reviewed in Management Review with BCDR and BIA evidence?',
            'metric_id': 'c653-review-risk-evidence',
            'purpose': 'Management oversight and operational resilience',
            'requirement_reference': '6.5.3 Annual Reporting and Management Review',
            'applicable_population': 'Management Reviews in the reporting period',
            'management_decision': 'Add missing risk, BCDR or BIA evidence and decisions',
            'support_status': 'Can be implemented with revised mapping',
            'source_key': 'management_review',
            'limitation': ''}]}

EXCEPTION_METRIC_IDS = ['c611-open-resolutions',
 'c611-overdue-resolutions',
 'c611-incomplete-cap-control',
 'c621-postponed',
 'c621-overdue-next-review',
 'c641-below-passing',
 'c641-critical-failure',
 'c641-missing-rating',
 'c641-terminated']


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
        text = clean_text(value).replace(",", "").replace("SGD", "").replace("$", "")
        return float(text)
    except Exception:
        return None


def is_permission_error(error):
    text = lower_text(error)
    return "permission" in text or "not permitted" in text or "not allowed" in text


def display_doctype(doctype):
    return SOURCE_DISPLAY_NAMES.get(doctype) or doctype or "Source"


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


def resolve_source(alias):
    candidates = SOURCE_CANDIDATES.get(alias) or []
    attempts = []
    for candidate_index in range(len(candidates)):
        doctype = candidates[candidate_index]
        attempt = {"doctype": doctype, "display_doctype": display_doctype(doctype), "status": "checking", "stage": "existence", "message": ""}
        try:
            if not frappe.db.exists("DocType", doctype):
                attempt["status"] = "unavailable"
                attempt["message"] = "DocType is not installed on this site."
                attempts.append(attempt)
                continue
        except Exception as error:
            attempt["status"] = "unavailable"
            attempt["message"] = clean_text(error)
            attempts.append(attempt)
            continue
        try:
            frappe.get_meta(doctype)
            attempt["stage"] = "metadata"
        except Exception as error:
            attempt["status"] = "unavailable"
            attempt["stage"] = "metadata"
            attempt["message"] = clean_text(error)
            attempts.append(attempt)
            continue
        try:
            rows = frappe.get_list(
                doctype,
                fields=["name"],
                limit_start=0,
                limit_page_length=row_limit,
                order_by="modified desc"
            ) or []
            attempt["status"] = "available"
            attempt["stage"] = "list"
            attempt["message"] = "Readable by the signed-in user."
            attempts.append(attempt)
            return {
                "key": alias,
                "doctype": doctype,
                "display_doctype": display_doctype(doctype),
                "candidates": candidates,
                "status": "available",
                "count": len(rows),
                "truncated": len(rows) >= row_limit,
                "count_note": "Count is limited by row_limit." if len(rows) >= row_limit else "Permission-aware fetched record count.",
                "probe": "frappe.get_list",
                "fallback_used": candidate_index > 0,
                "resolution_attempts": attempts,
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
                    "display_doctype": display_doctype(doctype),
                    "candidates": candidates,
                    "status": "permission_denied",
                    "count": 0,
                    "message": message,
                    "probe": "frappe.get_list",
                    "fallback_used": False,
                    "resolution_attempts": attempts,
                }
    expected = candidates[0] if candidates else None
    return {
        "key": alias,
        "doctype": expected,
        "display_doctype": display_doctype(expected),
        "candidates": candidates,
        "status": "unavailable",
        "count": 0,
        "message": "No approved backend DocType could be resolved.",
        "resolution_attempts": attempts,
        "fallback_used": False,
    }


def source_filter_details(alias, doctype):
    applied = {}
    resolved = []
    unresolved = []
    field_map = FILTER_FIELD_CANDIDATES.get(alias) or {}
    requested_status = filters.get("status")
    if requested_status:
        status_field = resolve_field(doctype, field_map.get("status") or [])
        if status_field:
            applied[status_field] = requested_status
            resolved.append({"filter": "status", "field": status_field, "value": requested_status})
        else:
            unresolved.append({"filter": "status", "reason": "No verified status field is mapped for this source."})
    requested_year = filters.get("review_year") or filters.get("year") or filters.get("monitoring_year")
    requested_month = filters.get("month")
    year_applied = False
    if requested_year:
        year_field = resolve_field(doctype, field_map.get("year_value") or [])
        if year_field:
            applied[year_field] = requested_year
            resolved.append({"filter": "review_year", "field": year_field, "value": requested_year})
            year_applied = True
        else:
            date_field = resolve_field(doctype, field_map.get("year_date") or [])
            if date_field:
                start_date = clean_text(requested_year) + "-01-01"
                end_date = clean_text(requested_year) + "-12-31"
                if requested_month:
                    try:
                        month_number = int(requested_month)
                        if month_number >= 1 and month_number <= 12:
                            start_date = "%s-%02d-01" % (clean_text(requested_year), month_number)
                            if month_number == 12:
                                end_date = "%s-12-31" % clean_text(requested_year)
                            else:
                                next_month = month_number + 1
                                next_start = "%s-%02d-01" % (clean_text(requested_year), next_month)
                                end_date = frappe.utils.add_days(next_start, -1)
                    except Exception:
                        pass
                applied[date_field] = ["between", [start_date, end_date]]
                resolved.append({"filter": "review_year", "field": date_field, "value": requested_year})
                if requested_month:
                    resolved.append({"filter": "month", "field": date_field, "value": requested_month})
                year_applied = True
            else:
                unresolved.append({"filter": "review_year", "reason": "No verified reporting-year field is mapped for this source."})
    if requested_month and not requested_year:
        unresolved.append({"filter": "month", "reason": "A reporting year is required before a month range can be applied."})
    if requested_month and requested_year and not year_applied:
        unresolved.append({"filter": "month", "reason": "No verified date field is mapped for this source."})
    if filters.get("department"):
        unresolved.append({"filter": "department", "reason": "No verified department field was supplied for this source."})
    if filters.get("quality_area"):
        unresolved.append({"filter": "quality_area", "reason": "No verified quality-area field was supplied for this source."})
    return applied, resolved, unresolved


filter_diagnostics = {}


def fetch_rows(source, requested_fields=None):
    doctype = source.get("doctype")
    alias = source.get("key")
    if source.get("status") != "available" or not doctype:
        return []
    fields_to_fetch = safe_fields(doctype, ["name"] + (requested_fields or []))
    filter_result = source_filter_details(alias, doctype)
    applied = filter_result[0]
    filter_diagnostics[alias] = {
        "source": alias,
        "doctype": doctype,
        "display_doctype": display_doctype(doctype),
        "applied": filter_result[1],
        "unresolved": filter_result[2],
    }
    try:
        rows = frappe.get_list(
            doctype,
            fields=fields_to_fetch,
            filters=applied,
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



def compare(row, fieldname, op, expected=None, values=None):
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
    if op == "date_before_today":
        if not value:
            return False
        try:
            return frappe.utils.getdate(value) < frappe.utils.getdate(frappe.utils.today())
        except Exception:
            return False
    if op == "number_gte":
        number = to_number(value)
        threshold = to_number(expected)
        return number is not None and threshold is not None and number >= threshold
    if op == "number_lt":
        number = to_number(value)
        threshold = to_number(expected)
        return number is not None and threshold is not None and number < threshold
    return False


def resolve_conditions(doctype, conditions):
    resolved = []
    missing = []
    for condition in conditions or []:
        fieldname = resolve_field(doctype, condition.get("field") or [])
        if not fieldname:
            missing.append(condition.get("field") or [])
            continue
        item = {}
        for key in condition:
            item[key] = condition.get(key)
        item["resolved_field"] = fieldname
        resolved.append(item)
    return resolved, missing


def conditions_match(row, conditions):
    for condition in conditions:
        if not compare(row, condition.get("resolved_field"), condition.get("op"), expected=condition.get("value"), values=condition.get("values")):
            return False
    return True


if subcriterion not in CONFIG:
    frappe.throw("Unsupported Criterion 6 subcriterion.")

resolved_sources = {}
for alias in CONFIG[subcriterion]["sources"]:
    resolved_sources[alias] = resolve_source(alias)


def base_metric(metric, source=None):
    doctype = None
    if source:
        doctype = source.get("doctype")
    if not doctype:
        candidates = SOURCE_CANDIDATES.get(metric.get("source")) or []
        doctype = candidates[0] if candidates else None
    return {
        "id": metric.get("id"),
        "label": metric.get("label"),
        "source": metric.get("source"),
        "doctype": doctype,
        "display_doctype": display_doctype(doctype),
        "evidence_level": metric.get("evidence_level") or "unspecified",
        "unit": metric.get("unit") or "records",
        "resolved_fields": [],
        "resolved_field_groups": [],
        "rows": [],
    }


def evaluate_parent_metric(metric, source, include_rows):
    output = base_metric(metric, source)
    doctype = source.get("doctype")
    mode = metric.get("mode")
    fields = []
    field_groups = []
    missing = []
    if metric.get("field"):
        fieldname = resolve_field(doctype, metric.get("field"))
        if fieldname:
            fields.append(fieldname)
            field_groups.append({"candidates": metric.get("field"), "resolved": fieldname})
        else:
            missing.append(metric.get("field"))
    group_result = resolve_field_groups(doctype, metric.get("fields") or [])
    resolved_groups = group_result[0]
    missing_groups = group_result[1]
    fields.extend(resolved_groups)
    for index in range(len(metric.get("fields") or [])):
        candidates = (metric.get("fields") or [])[index]
        resolved_name = ""
        for resolved_candidate in resolved_groups:
            if resolved_candidate in candidates:
                resolved_name = resolved_candidate
                break
        field_groups.append({"candidates": candidates, "resolved": resolved_name})
    missing.extend(missing_groups)
    condition_result = resolve_conditions(doctype, metric.get("conditions") or [])
    resolved_conditions = condition_result[0]
    missing_conditions = condition_result[1]
    missing.extend(missing_conditions)
    for condition in resolved_conditions:
        if condition.get("resolved_field") not in fields:
            fields.append(condition.get("resolved_field"))
    if mode != "all" and missing:
        output.update({"value": None, "record_count": 0, "total": 0, "status": "unsupported_field", "message": "Required field is not installed or was not verified.", "missing_field_candidates": missing, "resolved_fields": fields, "resolved_field_groups": field_groups})
        return output
    requested = []
    for fieldname in fields:
        if fieldname not in requested:
            requested.append(fieldname)
    if include_rows:
        for fieldname in SAFE_FIELDS.get(metric.get("source"), []):
            if fieldname not in requested:
                requested.append(fieldname)
    rows = fetch_rows(source, requested)
    if source.get("fetch_error"):
        output.update({"value": None, "record_count": 0, "total": 0, "status": source.get("fetch_status") or "query_error", "message": source.get("fetch_error"), "resolved_fields": fields, "resolved_field_groups": field_groups, "rows": []})
        return output
    matched = []
    for row in rows:
        accepted = False
        if mode == "all":
            accepted = True
        elif mode in ["truthy", "falsy", "equals", "in", "number_gte", "number_lt"]:
            accepted = compare(row, fields[0] if fields else "", mode, expected=metric.get("value"), values=metric.get("values"))
        elif mode == "conditions":
            accepted = conditions_match(row, resolved_conditions)
        elif mode == "all_required":
            accepted = True
            for fieldname in fields:
                if not is_truthy(row.get(fieldname)):
                    accepted = False
                    break
        elif mode in ["average", "sum"]:
            accepted = conditions_match(row, resolved_conditions)
            if accepted:
                accepted = bool(fields and to_number(row.get(fields[0])) is not None)
        if accepted:
            matched.append(row)
    value = len(matched)
    if mode == "average":
        numbers = []
        for row in matched:
            number = to_number(row.get(fields[0]))
            if number is not None:
                numbers.append(number)
        value = round(sum(numbers) / len(numbers), 2) if numbers else 0
    elif mode == "sum":
        total_value = 0
        for row in matched:
            number = to_number(row.get(fields[0]))
            if number is not None:
                total_value = total_value + number
        value = round(total_value, 2)
    output_rows = []
    if include_rows:
        start = (page - 1) * page_size
        end = start + page_size
        allowed = safe_fields(doctype, SAFE_FIELDS.get(metric.get("source"), ["name"]))
        for row in matched[start:end]:
            item = {}
            for fieldname in allowed:
                item[fieldname] = row.get(fieldname)
            output_rows.append(item)
    output.update({"value": value, "record_count": len(matched), "total": len(matched), "status": "available", "resolved_fields": fields, "resolved_field_groups": field_groups, "rows": output_rows})
    return output


def evaluate_child_metric(metric, source, include_rows):
    output = base_metric(metric, source)
    parent_doctype = source.get("doctype")
    table_field = resolve_field(parent_doctype, metric.get("table_field") or [])
    if not table_field:
        output.update({"value": None, "record_count": 0, "total": 0, "status": "unsupported_field", "message": "Required child-table field is not installed or was not verified.", "missing_field_candidates": [metric.get("table_field") or []]})
        return output
    parent_meta = get_meta(parent_doctype)
    child_doctype = metric.get("child_doctype")
    try:
        table_meta = parent_meta.get_field(table_field)
        if table_meta and table_meta.options:
            child_doctype = table_meta.options
    except Exception:
        pass
    child_meta = get_meta(child_doctype)
    output["doctype"] = child_doctype
    output["display_doctype"] = display_doctype(child_doctype)
    output["parent_doctype"] = parent_doctype
    output["table_field"] = table_field
    if not child_meta:
        output.update({"value": None, "record_count": 0, "total": 0, "status": "unavailable", "message": "Required child DocType is not installed."})
        return output
    condition_result = resolve_conditions(child_doctype, metric.get("conditions") or [])
    resolved_conditions = condition_result[0]
    missing = condition_result[1]
    required_result = resolve_field_groups(child_doctype, metric.get("required_fields") or [])
    required_fields = required_result[0]
    required_missing = required_result[1]
    missing.extend(required_missing)
    if missing:
        output.update({"value": None, "record_count": 0, "total": 0, "status": "unsupported_field", "message": "Required child field is not installed or was not verified.", "missing_field_candidates": missing, "resolved_fields": required_fields})
        return output
    parent_rows = fetch_rows(source, [])
    if source.get("fetch_error"):
        output.update({"value": None, "record_count": 0, "total": 0, "status": source.get("fetch_status") or "query_error", "message": source.get("fetch_error"), "rows": []})
        return output
    matched_rows = []
    matched_parents = []
    for parent in parent_rows:
        try:
            doc = frappe.get_doc(parent_doctype, parent.get("name"))
            child_rows = doc.get(table_field) or []
        except Exception:
            child_rows = []
        parent_has_match = False
        for child in child_rows:
            accepted = True
            if metric.get("mode") == "child_any_missing":
                accepted = False
                for fieldname in required_fields:
                    try:
                        child_value = child.get(fieldname)
                    except Exception:
                        child_value = None
                    if not is_truthy(child_value):
                        accepted = True
                        break
            elif resolved_conditions:
                accepted = conditions_match(child, resolved_conditions)
            if accepted:
                parent_has_match = True
                matched_rows.append({"parent": parent.get("name"), "child": child})
        if parent_has_match:
            matched_parents.append(parent.get("name"))
    count_mode = "parents" if metric.get("mode") == "child_parent_count" else "rows"
    value = len(matched_parents) if count_mode == "parents" else len(matched_rows)
    output_rows = []
    if include_rows:
        start = (page - 1) * page_size
        end = start + page_size
        selected_rows = matched_rows[start:end]
        allowed = safe_fields(child_doctype, CHILD_SAFE_FIELDS.get(child_doctype, ["idx"]))
        for entry in selected_rows:
            item = {"parent_doctype": parent_doctype, "parent": entry.get("parent"), "child_doctype": child_doctype}
            child = entry.get("child")
            for fieldname in allowed:
                try:
                    item[fieldname] = child.get(fieldname)
                except Exception:
                    item[fieldname] = None
            output_rows.append(item)
    output.update({"value": value, "record_count": value, "total": value, "unit": "parents" if count_mode == "parents" else "rows", "status": "available", "resolved_fields": required_fields, "rows": output_rows})
    return output


def evaluate_metric(metric, include_rows=False):
    source = resolved_sources.get(metric.get("source")) or {}
    if source.get("status") != "available":
        output = base_metric(metric, source)
        output.update({"value": None, "record_count": 0, "total": 0, "status": source.get("status") or "unavailable", "message": source.get("message") or "Required source is unavailable."})
        return output
    if metric.get("mode") in ["child_count", "child_parent_count", "child_any_missing"]:
        return evaluate_child_metric(metric, source, include_rows)
    return evaluate_parent_metric(metric, source, include_rows)


metrics = []
for configured_metric in CONFIG[subcriterion]["metrics"]:
    metrics.append(evaluate_metric(configured_metric, False))

metric_by_id = {}
for metric in metrics:
    metric_by_id[metric.get("id")] = metric

approved_metric_ids = []
for question_definition in QUESTION_REGISTRY.get(subcriterion) or []:
    if question_definition.get("metric_id") and question_definition.get("metric_id") not in approved_metric_ids:
        approved_metric_ids.append(question_definition.get("metric_id"))

supporting_metrics = []
for metric in metrics:
    if metric.get("id") not in approved_metric_ids:
        supporting_metrics.append(metric)


def format_metric_answer(metric):
    if not metric:
        return "Cannot assess from current ERPNext data."
    if metric.get("status") != "available":
        return "Cannot assess from current ERPNext data: " + clean_text(metric.get("message") or metric.get("status"))
    unit = metric.get("unit") or "records"
    value = metric.get("value")
    if unit == "SGD":
        answer = "SGD " + str(value) + " is recorded for the current filters."
    elif unit == "index":
        answer = str(value) + " is the stored average for the current filters."
    else:
        answer = str(value or 0) + " " + unit + " match the current filters."
    evidence_level = metric.get("evidence_level")
    if evidence_level == "record_existence":
        answer = answer + " This confirms record existence only, not process compliance or effectiveness."
    elif evidence_level == "process_status":
        answer = answer + " Status alone does not prove approval, implementation or effectiveness."
    elif evidence_level == "stored_calculation":
        answer = answer + " The stored value has not been independently recalculated by this API."
    return answer


questions = []
for definition in QUESTION_REGISTRY.get(subcriterion) or []:
    selected_metric = metric_by_id.get(definition.get("metric_id")) if definition.get("metric_id") else None
    if selected_metric:
        answer = format_metric_answer(selected_metric)
        status = selected_metric.get("status")
        confidence = "Live" if status == "available" and definition.get("support_status") == "Can be implemented now" else "Partial"
        doctype = selected_metric.get("doctype")
        display_name = selected_metric.get("display_doctype")
        source_key = selected_metric.get("source")
        record_count = selected_metric.get("record_count") or 0
        resolved_fields = selected_metric.get("resolved_fields") or []
    else:
        answer = "Cannot assess from current ERPNext data: " + clean_text(definition.get("limitation") or "document or additional structured evidence is required")
        status = "document_only" if definition.get("support_status") == "Document evidence only" else "unsupported"
        confidence = "Document only" if status == "document_only" else "Unavailable"
        source_key = definition.get("source_key")
        source = resolved_sources.get(source_key) or {}
        candidates = SOURCE_CANDIDATES.get(source_key) or []
        doctype = source.get("doctype") or (candidates[0] if candidates else None)
        display_name = display_doctype(doctype)
        record_count = 0
        resolved_fields = []
    questions.append({
        "id": definition.get("id"),
        "criterion": subcriterion,
        "question": definition.get("question"),
        "answer": answer,
        "metric_id": definition.get("metric_id"),
        "record_count": record_count,
        "source": source_key,
        "doctype": doctype,
        "display_doctype": display_name,
        "resolved_fields": resolved_fields,
        "status": status,
        "confidence": confidence,
        "support_status": definition.get("support_status"),
        "primary_management_purpose": definition.get("purpose"),
        "requirement_reference": definition.get("requirement_reference"),
        "applicable_population": definition.get("applicable_population"),
        "management_decision": definition.get("management_decision"),
        "limitation": definition.get("limitation") or "",
    })

sources = []
source_mapping = []
for alias in CONFIG[subcriterion]["sources"]:
    source = resolved_sources.get(alias)
    sources.append(source)
    source_mapping.append({
        "key": alias,
        "backend_doctype": source.get("doctype"),
        "display_label": source.get("display_doctype"),
        "candidates": source.get("candidates") or [],
        "status": source.get("status"),
        "message": source.get("message") or "",
    })

requirements = []
for definition in QUESTION_REGISTRY.get(subcriterion) or []:
    requirements.append({
        "id": definition.get("id"),
        "criterion": subcriterion,
        "requirement_reference": definition.get("requirement_reference"),
        "management_question": definition.get("question"),
        "applicable_population": definition.get("applicable_population"),
        "management_decision": definition.get("management_decision"),
        "support_status": definition.get("support_status"),
        "source": definition.get("source_key"),
        "metric_id": definition.get("metric_id"),
        "evidence_gap": definition.get("limitation") or "",
    })

resolved_filters = []
unresolved_filters = []
for alias in filter_diagnostics:
    diagnostic = filter_diagnostics.get(alias) or {}
    for item in diagnostic.get("applied") or []:
        entry = {"source": alias}
        for key in item:
            entry[key] = item.get(key)
        resolved_filters.append(entry)
    for item in diagnostic.get("unresolved") or []:
        entry = {"source": alias}
        for key in item:
            entry[key] = item.get(key)
        unresolved_filters.append(entry)

data_quality = []
for source in sources:
    if source.get("status") != "available":
        data_quality.append({
            "criterion": subcriterion,
            "check": "Source availability",
            "source": source.get("display_doctype") or " / ".join(source.get("candidates") or []),
            "backend_doctype": source.get("doctype"),
            "status": source.get("status"),
            "detail": source.get("message") or "Source is unavailable.",
        })
for metric in metrics:
    if metric.get("status") != "available":
        data_quality.append({
            "criterion": subcriterion,
            "check": metric.get("label"),
            "source": metric.get("display_doctype") or metric.get("source"),
            "backend_doctype": metric.get("doctype"),
            "status": metric.get("status"),
            "detail": metric.get("message") or "Metric is unavailable.",
        })
for item in unresolved_filters:
    data_quality.append({
        "criterion": subcriterion,
        "check": "Filter mapping",
        "source": item.get("source"),
        "status": "unsupported_filter",
        "detail": item.get("filter") + ": " + item.get("reason"),
    })

exceptions = []
for metric in metrics:
    if metric.get("id") in EXCEPTION_METRIC_IDS:
        exceptions.append(metric)

readiness = []
for source in sources:
    readiness.append({
        "type": "source",
        "key": source.get("key"),
        "label": source.get("display_doctype"),
        "backend_doctype": source.get("doctype"),
        "status": source.get("status"),
        "message": source.get("message") or source.get("count_note") or "",
    })
for question in questions:
    readiness.append({
        "type": "question",
        "key": question.get("id"),
        "label": question.get("question"),
        "status": question.get("status"),
        "support_status": question.get("support_status"),
        "message": question.get("limitation") or "",
    })

available_sources = 0
for source in sources:
    if source.get("status") == "available":
        available_sources = available_sources + 1
available_metrics = 0
for metric in metrics:
    if metric.get("status") == "available":
        available_metrics = available_metrics + 1
available_questions = 0
for question in questions:
    if question.get("status") == "available":
        available_questions = available_questions + 1

criterion_overview = []
for metric in exceptions:
    criterion_overview.append({
        "criterion": subcriterion,
        "metric_id": metric.get("id"),
        "label": metric.get("label"),
        "value": metric.get("value"),
        "status": metric.get("status"),
        "doctype": metric.get("doctype"),
        "display_doctype": metric.get("display_doctype"),
    })
for question in questions:
    if question.get("status") not in ["available"]:
        criterion_overview.append({
            "criterion": subcriterion,
            "question_id": question.get("id"),
            "label": question.get("question"),
            "value": None,
            "status": question.get("status"),
            "support_status": question.get("support_status"),
            "display_doctype": question.get("display_doctype"),
        })

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
        "api_method": "ucc_analytics_criterion_6",
        "platform_version": "2.0.0-policy-aligned",
        "status": "policy_aligned_foundation",
        "generated_at": frappe.utils.now(),
        "action": action,
        "subcriterion": subcriterion,
        "row_limit": row_limit,
    },
    "policy": POLICY_REGISTRY.get(subcriterion),
    "filters": filters,
    "resolved_filters": resolved_filters,
    "unresolved_filters": unresolved_filters,
    "sources": sources,
    "source_mapping": source_mapping,
    "metrics": metrics,
    "supporting_metrics": supporting_metrics,
    "questions": questions,
    "exceptions": exceptions,
    "data_quality": data_quality,
    "requirements": requirements,
    "readiness": readiness,
    "criterion_overview": criterion_overview,
    "source_summary": {"total": len(sources), "available": available_sources, "issues": len(sources) - available_sources},
    "metric_summary": {"total": len(metrics), "available": available_metrics, "issues": len(metrics) - available_metrics},
    "question_summary": {"total": len(questions), "available": available_questions, "issues": len(questions) - available_questions},
    "data": {
        "sources": sources,
        "source_mapping": source_mapping,
        "metrics": metrics,
        "supporting_metrics": supporting_metrics,
        "questions": questions,
        "exceptions": exceptions,
        "data_quality": data_quality,
        "requirements": requirements,
        "readiness": readiness,
        "criterion_overview": criterion_overview,
    },
    "warnings": [
        "Record existence is not treated as proof of completeness, approval, compliance or effectiveness.",
        "Translated labels are used only for display. All server-side queries use exact backend DocType names.",
        "Calendar, checklist, template, report, form and register names are not queried as DocTypes unless exact backend evidence is available.",
        "The 6.2.1 procedure has a Version 1.3 cover but an internal Version 1.2 footer; verify the controlled master.",
        "Audit notification calculation is intentionally withheld until the 14-day versus 14-working-day conflict is resolved.",
    ],
}

result = standardise_response_contract(result, "Criterion 6", "ucc_analytics_criterion_6", action, subcriterion, row_limit)

if action == "policy_registry":
    result["registry"] = POLICY_REGISTRY
elif action == "requirement_registry":
    full_requirements = []
    for criterion_key in QUESTION_REGISTRY:
        for definition in QUESTION_REGISTRY.get(criterion_key) or []:
            full_requirements.append({
                "id": definition.get("id"),
                "criterion": criterion_key,
                "management_question": definition.get("question"),
                "requirement_reference": definition.get("requirement_reference"),
                "applicable_population": definition.get("applicable_population"),
                "management_decision": definition.get("management_decision"),
                "support_status": definition.get("support_status"),
                "source": definition.get("source_key"),
                "metric_id": definition.get("metric_id"),
                "evidence_gap": definition.get("limitation") or "",
            })
    result["registry"] = full_requirements
elif action == "question_registry":
    result["registry"] = QUESTION_REGISTRY
elif action == "source_status":
    result["source_status"] = sources
elif action == "drilldown":
    selected_config = None
    for configured_metric in CONFIG[subcriterion]["metrics"]:
        if configured_metric.get("id") == metric_id:
            selected_config = configured_metric
            break
    if not selected_config:
        frappe.throw("Unknown Criterion 6 metric.")
    result["drilldown"] = evaluate_metric(selected_config, True)

result = standardise_response_contract(result, "Criterion 6", "ucc_analytics_criterion_6", action, subcriterion, row_limit)

frappe.response["message"] = result
