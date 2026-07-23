"""
UCC Intelligence Platform Server Script

Visible name:
    UCC Analytics - Criterion 7

Script type:
    API

API method:
    ucc_analytics_criterion_7

Purpose:
    Return permission-aware, policy-aligned Criterion 7 analytics. The API
    separates record existence, data readiness, benchmark validity, target
    validity, measurement, achievement, trend sufficiency, action linkage,
    effectiveness, dissemination and APSR/PDCA closure. Unsupported controls
    are reported honestly instead of being converted into false zeroes.

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
subcriterion = payload.get("subcriterion") or "7.1.1"
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
    frappe.throw("Unsupported Criterion 7 action.")


POLICY_REGISTRY = {'7.1.1': {'title': 'Measurement of Outcomes',
           'policy': 'PPD-SGL-SQ-7.1.1',
           'version': '1.2',
           'effective_date': '15 January 2026',
           'document_note': 'The controlled procedure is consolidated under 7.1.1. Appendix C retains legacy '
                            'domain references 7.2.1 to 7.2.4. The rendered file has 33 pages while the '
                            'footer states 32 pages.'}}

SOURCE_CANDIDATES = {'quality_performance': ['Quality Performance Outcomes'],
 'quality_goal': ['Quality Goal'],
 'quality_action': ['Quality Action'],
 'quality_meeting': ['Quality Meeting'],
 'management_review': ['Management Review'],
 'operational_outcomes': ['Operational Outcomes Cost Time Saving']}

SOURCE_DISPLAY_NAMES = {'Quality Meeting': 'Meeting Minutes'}

SAFE_FIELDS = {'quality_performance': ['name',
                         'outcome',
                         'outcome_title',
                         'outcome_category',
                         'category',
                         'indicator',
                         'kpi',
                         'metric',
                         'status',
                         'benchmark',
                         'benchmark_value',
                         'benchmark_type',
                         'target',
                         'target_value',
                         'actual',
                         'actual_value',
                         'current_value',
                         'measurement_date',
                         'date',
                         'review_date',
                         'frequency',
                         'owner',
                         'department',
                         'trend',
                         'variance',
                         'modified'],
 'quality_goal': ['name', 'modified'],
 'quality_action': ['name',
                    'status',
                    'custom_status_updates',
                    'date',
                    'custom_proposed_date',
                    'custom_completed_date',
                    'custom_type_of_innovation',
                    'custom_innovation_category',
                    'custom_aggregated_performance_index_api',
                    'custom_timeadjusted_cost_efficiency_index_tacei',
                    'custom_cost_efficiency_index_cei',
                    'custom_total_budget_fee',
                    'custom_total_actual_spending',
                    'custom_spending_difference',
                    'goal',
                    'review',
                    'procedure',
                    'modified'],
 'quality_meeting': ['name', 'meeting_date', 'status', 'review', 'procedure', 'modified'],
 'management_review': ['name',
                       'review_date',
                       'review_period',
                       'review_type',
                       'review_status',
                       'chairperson',
                       'next_review_date',
                       'modified'],
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
                          'modified']}

FILTER_FIELD_CANDIDATES = {'quality_performance': {'status': ['status'],
                         'year_date': ['measurement_date', 'date', 'review_date'],
                         'outcome_category': ['outcome_category', 'category'],
                         'department': ['department']},
 'quality_goal': {},
 'quality_action': {'status': ['custom_status_updates', 'status'],
                    'year_date': ['date', 'custom_proposed_date', 'custom_completed_date']},
 'quality_meeting': {'status': ['status'], 'year_date': ['meeting_date']},
 'management_review': {'status': ['review_status'], 'year_date': ['review_date']},
 'operational_outcomes': {'year_value': ['monitoring_year'], 'year_date': ['period_start', 'period_end']}}

CONFIG = {'7.1.1': {'sources': ['quality_performance',
                       'quality_goal',
                       'quality_action',
                       'quality_meeting',
                       'management_review',
                       'operational_outcomes'],
           'metrics': [{'id': 'c711-outcomes',
                        'label': 'Performance outcome records in scope',
                        'source': 'quality_performance',
                        'mode': 'all',
                        'unit': 'records',
                        'evidence_level': 'record_existence'},
                       {'id': 'c711-missing-domain',
                        'label': 'Outcome records missing domain classification',
                        'source': 'quality_performance',
                        'mode': 'falsy',
                        'field': ['outcome_category', 'category'],
                        'unit': 'records',
                        'evidence_level': 'data_completeness'},
                       {'id': 'c711-missing-indicator',
                        'label': 'Outcome records missing KPI or indicator',
                        'source': 'quality_performance',
                        'mode': 'falsy',
                        'field': ['indicator', 'kpi', 'metric'],
                        'unit': 'records',
                        'evidence_level': 'data_completeness'},
                       {'id': 'c711-missing-benchmark',
                        'label': 'Outcome records missing benchmark data',
                        'source': 'quality_performance',
                        'mode': 'falsy',
                        'field': ['benchmark', 'benchmark_value', 'benchmark_type'],
                        'unit': 'records',
                        'evidence_level': 'data_completeness'},
                       {'id': 'c711-missing-target',
                        'label': 'Outcome records missing target data',
                        'source': 'quality_performance',
                        'mode': 'falsy',
                        'field': ['target', 'target_value'],
                        'unit': 'records',
                        'evidence_level': 'data_completeness'},
                       {'id': 'c711-missing-actual',
                        'label': 'Outcome records missing actual result',
                        'source': 'quality_performance',
                        'mode': 'falsy',
                        'field': ['actual', 'actual_value', 'current_value'],
                        'unit': 'records',
                        'evidence_level': 'data_completeness'},
                       {'id': 'c711-missing-measurement-date',
                        'label': 'Outcome records missing measurement date',
                        'source': 'quality_performance',
                        'mode': 'falsy',
                        'field': ['measurement_date', 'date', 'review_date'],
                        'unit': 'records',
                        'evidence_level': 'data_completeness'},
                       {'id': 'c711-missing-owner',
                        'label': 'Outcome records missing assigned owner',
                        'source': 'quality_performance',
                        'mode': 'falsy',
                        'field': ['owner'],
                        'unit': 'records',
                        'evidence_level': 'data_completeness'},
                       {'id': 'c711-core-field-complete',
                        'label': 'Outcome records with all currently mapped core fields',
                        'source': 'quality_performance',
                        'mode': 'all_required',
                        'fields': [['outcome_category', 'category'],
                                   ['indicator', 'kpi', 'metric'],
                                   ['benchmark', 'benchmark_value', 'benchmark_type'],
                                   ['target', 'target_value'],
                                   ['actual', 'actual_value', 'current_value'],
                                   ['measurement_date', 'date', 'review_date'],
                                   ['owner']],
                        'unit': 'records',
                        'evidence_level': 'partial_completeness'},
                       {'id': 'c711-domain-coverage',
                        'label': 'Required outcome-domain coverage',
                        'source': 'quality_performance',
                        'mode': 'required_value_coverage',
                        'field': ['outcome_category', 'category'],
                        'required_values': {'Student and Graduate Outcomes': ['student and graduate',
                                                                              'student & graduate'],
                                            'Service Quality Outcomes': ['service quality'],
                                            'Operational Outcomes': ['operational'],
                                            'People Development Outcomes': ['people development']},
                        'unit': 'domains',
                        'evidence_level': 'coverage'},
                       {'id': 'c711-quality-goals',
                        'label': 'Quality Goal records available',
                        'source': 'quality_goal',
                        'mode': 'all',
                        'unit': 'records',
                        'evidence_level': 'record_existence'},
                       {'id': 'c711-quality-actions',
                        'label': 'Quality Actions in scope',
                        'source': 'quality_action',
                        'mode': 'all',
                        'unit': 'records',
                        'evidence_level': 'record_existence'},
                       {'id': 'c711-open-actions',
                        'label': 'Open Quality Actions in scope',
                        'source': 'quality_action',
                        'mode': 'not_in',
                        'field': ['custom_status_updates', 'status'],
                        'values': ['Completed', 'Closed'],
                        'unit': 'records',
                        'evidence_level': 'process_status'},
                       {'id': 'c711-quality-meetings',
                        'label': 'Quality Meeting records in scope',
                        'source': 'quality_meeting',
                        'mode': 'all',
                        'unit': 'records',
                        'evidence_level': 'record_existence'},
                       {'id': 'c711-management-reviews',
                        'label': 'Management Review records in scope',
                        'source': 'management_review',
                        'mode': 'all',
                        'unit': 'records',
                        'evidence_level': 'record_existence'},
                       {'id': 'c711-net-saving',
                        'label': 'Stored operational net saving',
                        'source': 'operational_outcomes',
                        'mode': 'sum',
                        'field': ['total_net_saving'],
                        'unit': 'SGD',
                        'evidence_level': 'stored_calculation'},
                       {'id': 'c711-benchmark-variance',
                        'label': 'Stored operational benchmark variance',
                        'source': 'operational_outcomes',
                        'mode': 'sum',
                        'field': ['variance_to_benchmark'],
                        'unit': 'SGD',
                        'evidence_level': 'stored_calculation'},
                       {'id': 'c711-indicator-coverage',
                        'label': 'Required named-indicator coverage',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'An approved indicator registry, active status and duplicate-control rule are '
                                   'required.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-artemia-compliance',
                        'label': 'ARTEMIA selection-compliance rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'The supplied metadata does not contain verified fields for all seven ARTEMIA '
                                   'selection criteria.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-benchmark-validation',
                        'label': 'Benchmark validation rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Verified fields for benchmark origin, source evidence, relevance, credibility, '
                                   'currency and applicability were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-proxy-rationale',
                        'label': 'Proxy benchmark substitution rationale',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'A verified proxy-benchmark flag and substitution-rationale field were not '
                                   'supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-target-validity',
                        'label': 'Target establishment validity rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Verified fields for benchmark linkage, calculation method, direction, approval and '
                                   'review cycle were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-target-review',
                        'label': 'Targets due for review or adjustment',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Verified target review history and adjustment-cycle fields were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-measurement-completion',
                        'label': 'Measurement completion rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'A due-measurement population, required frequency and approved '
                                   'calculation/source-evidence fields were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-target-achievement',
                        'label': 'Correct-direction target achievement rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Indicator direction, unit compatibility, period, population and range rules were '
                                   'not supplied. A universal greater-than-or-equal comparison is prohibited.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-below-target',
                        'label': 'Below-target outcome queue',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'The approved direction or range rule is unavailable, so below-target status cannot '
                                   'be calculated defensibly.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-action-linkage',
                        'label': 'Below-target outcomes with linked Quality Actions',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'No verified relationship field linking a Quality Action to a specific outcome gap '
                                   'was supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-root-cause',
                        'label': 'Outcome gaps with completed root cause analysis',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'No verified outcome-gap root-cause field or child table was supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-action-effectiveness',
                        'label': 'Corrective-action effectiveness rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Completed status does not prove effectiveness. Post-action measurement and '
                                   'effectiveness criteria were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-three-year-trend',
                        'label': 'Three-year trend coverage rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'A verified trend-history child table with three consecutive years and '
                                   'interim-treatment evidence was not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-trend-anomaly',
                        'label': 'Trend direction and anomaly queue',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Approved trend direction, method and anomaly thresholds were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-dissemination',
                        'label': 'Outcome dissemination completion rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'A verified dissemination log, stakeholder groups, channel, format and frequency '
                                   'fields were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-apsr-monthly',
                        'label': 'Monthly departmental APSR completion rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'A verified APSR record or Quality Calendar mapping for department-month reviews '
                                   'was not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-apsr-biannual',
                        'label': 'Biannual cross-department APSR completion rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'A verified tactical APSR record and required evidence fields were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-apsr-annual',
                        'label': 'Annual strategic APSR completion rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'A verified annual APSR record linked to Management Review was not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-apsr-components',
                        'label': 'APSR four-component completeness rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Verified Approach, Processes, Systems and Review checklist fields were not '
                                   'supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-pdca-closure',
                        'label': 'Criterion 7 PDCA closure rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Verified linked evidence for Plan, Do, Check, Act and effectiveness was not '
                                   'supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-attrition',
                        'label': 'Student Attrition Rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'An approved cohort denominator, premature-exit rules and student-level source '
                                   'mapping were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-progression',
                        'label': 'Progression Rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Approved horizontal and vertical progression rules, eligible population and source '
                                   'mapping were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-graduation',
                        'label': 'Graduation Rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'The cohort due to complete, adjusted timeframe rules and completion source mapping '
                                   'were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-quality-passes',
                        'label': 'Quality of Passes distribution',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Examination Board-approved grade records, grade-band definitions and comparability '
                                   'rules were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-employment',
                        'label': 'Graduate Employment Rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Graduate survey source, eligible population, response basis and employment '
                                   'classification fields were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-teaching-satisfaction',
                        'label': 'Teaching-quality satisfaction rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Survey question mapping, satisfaction threshold, valid-response denominator and '
                                   'response-coverage source were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-complaint-sla',
                        'label': 'Complaint-resolution SLA compliance rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Complaint source, SLA start/stop events, working-day rule, pause conditions and '
                                   'exclusions were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-overall-satisfaction',
                        'label': 'Overall student-satisfaction rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Approved overall-satisfaction item and valid-response denominator were not '
                                   'supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-liquidity',
                        'label': 'Liquidity Ratio',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Approved finance source fields for current assets and current liabilities at the '
                                   'same reporting date were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-debt-equity',
                        'label': 'Debt-Equity Ratio',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Approved finance source fields for total liabilities and shareholders equity at '
                                   'the same reporting date were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-cost-time-investment',
                        'label': 'Cost savings, time savings and investments',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'The current operational source stores some savings fields but does not provide an '
                                   'approved Criterion 7 population and separate validated units for all three '
                                   'measures.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-staff-satisfaction',
                        'label': 'Overall Staff Satisfaction Rate',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Staff survey source, satisfaction threshold, eligible population and '
                                   'response-coverage fields were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'},
                       {'id': 'c711-training-hours',
                        'label': 'Average Training Hours per Staff',
                        'source': 'quality_performance',
                        'mode': 'unsupported',
                        'message': 'Training records, completed-hour rules and the active staff denominator including '
                                   'part-time and academic staff were not supplied.',
                        'unit': 'records',
                        'evidence_level': 'unsupported'}]}}

QUESTION_REGISTRY = {'7.1.1': [{'id': 'q711-01',
            'question': 'Which performance outcome records are available for Criterion 7 review?',
            'metric_id': 'c711-outcomes',
            'purpose': 'Establish the record population',
            'requirement_reference': '7.1.1.1 and ARTEMIA Assessment',
            'applicable_population': 'All readable Quality Performance Outcomes records within the selected filters',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Confirm the review population and investigate unexpected omissions',
            'support_status': 'Can be implemented now',
            'limitation': '',
            'calculation_note': 'Count of readable outcome records. Record existence does not prove compliance.',
            'source_key': 'quality_performance'},
           {'id': 'q711-02',
            'question': 'Which outcome records lack a defined outcome domain?',
            'metric_id': 'c711-missing-domain',
            'purpose': 'Identify incomplete classification',
            'requirement_reference': '7.1.1.1 and four outcome domains',
            'applicable_population': 'All readable outcome records',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Assign the correct domain or remove an invalid record',
            'support_status': 'Can be implemented now',
            'limitation': '',
            'calculation_note': 'Count records where the mapped category field is blank.',
            'source_key': 'quality_performance'},
           {'id': 'q711-03',
            'question': 'Which outcome records lack a KPI or indicator?',
            'metric_id': 'c711-missing-indicator',
            'purpose': 'Identify outcomes that cannot be measured',
            'requirement_reference': '7.1.1.1 and ARTEMIA measurability',
            'applicable_population': 'All readable outcome records',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Define a valid indicator and approved calculation basis',
            'support_status': 'Can be implemented now',
            'limitation': '',
            'calculation_note': 'Count records where all mapped indicator fields are blank.',
            'source_key': 'quality_performance'},
           {'id': 'q711-04',
            'question': 'Which outcome records lack benchmark information?',
            'metric_id': 'c711-missing-benchmark',
            'purpose': 'Identify missing comparison basis',
            'requirement_reference': '7.1.1.1(b)',
            'applicable_population': 'All readable outcome records requiring a benchmark',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Obtain and validate an internal, external or approved proxy benchmark',
            'support_status': 'Can be implemented now',
            'limitation': '',
            'calculation_note': 'Count records where all currently mapped benchmark fields are blank. Validation is '
                                'assessed separately.',
            'source_key': 'quality_performance'},
           {'id': 'q711-05',
            'question': 'Which outcome records lack a measurable target?',
            'metric_id': 'c711-missing-target',
            'purpose': 'Identify missing target data',
            'requirement_reference': '7.1.1.1(c)',
            'applicable_population': 'All readable active outcome records requiring a target',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Establish a benchmark-based target and approval trail',
            'support_status': 'Can be implemented now',
            'limitation': '',
            'calculation_note': 'Count records where all currently mapped target fields are blank.',
            'source_key': 'quality_performance'},
           {'id': 'q711-06',
            'question': 'Which outcome records lack an actual result?',
            'metric_id': 'c711-missing-actual',
            'purpose': 'Identify missing measurement results',
            'requirement_reference': '7.1.1.1(d)',
            'applicable_population': 'All readable outcome records',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete the required measurement or document why it cannot be assessed',
            'support_status': 'Can be implemented now',
            'limitation': '',
            'calculation_note': 'Count records where all currently mapped actual-value fields are blank.',
            'source_key': 'quality_performance'},
           {'id': 'q711-07',
            'question': 'Which outcome records lack a measurement or review date?',
            'metric_id': 'c711-missing-measurement-date',
            'purpose': 'Identify incomplete reporting-period evidence',
            'requirement_reference': '7.1.1.1(d)',
            'applicable_population': 'All readable outcome records',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Record the applicable measurement date and reporting period',
            'support_status': 'Can be implemented now',
            'limitation': '',
            'calculation_note': 'Count records where all currently mapped measurement-date fields are blank.',
            'source_key': 'quality_performance'},
           {'id': 'q711-08',
            'question': 'Which outcome records lack an accountable owner?',
            'metric_id': 'c711-missing-owner',
            'purpose': 'Identify accountability gaps',
            'requirement_reference': 'Responsibilities and 7.1.1.1',
            'applicable_population': 'All readable outcome records',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Assign an accountable owner',
            'support_status': 'Can be implemented now',
            'limitation': '',
            'calculation_note': 'Count records where the owner field is blank.',
            'source_key': 'quality_performance'},
           {'id': 'q711-09',
            'question': 'How many outcome records contain all currently mapped core fields?',
            'metric_id': 'c711-core-field-complete',
            'purpose': 'Assess current data readiness without overstating compliance',
            'requirement_reference': '7.1.1.1',
            'applicable_population': 'All readable outcome records',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Prioritise incomplete records before management review',
            'support_status': 'Can be implemented now',
            'limitation': 'This is a partial mapped-field check and does not prove ARTEMIA, benchmark or target validity.',
            'calculation_note': 'Count records with category, indicator, benchmark, target, actual, date and owner '
                                'populated.',
            'source_key': 'quality_performance'},
           {'id': 'q711-10',
            'question': 'Are all four required outcome domains represented in the register?',
            'metric_id': 'c711-domain-coverage',
            'purpose': 'Check domain coverage',
            'requirement_reference': '7.1.1.1 and Appendix C',
            'applicable_population': 'The four required domains',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Create or correct outcome records for missing domains',
            'support_status': 'Can be implemented with revised mapping',
            'limitation': 'Coverage depends on consistent category text and does not prove named-indicator coverage.',
            'calculation_note': 'Count distinct required domains represented by the mapped category field. Denominator is '
                                'four domains.',
            'source_key': 'quality_performance'},
           {'id': 'q711-11',
            'question': 'Which required named indicators lack an active approved outcome record?',
            'metric_id': 'c711-indicator-coverage',
            'purpose': 'Check required indicator coverage',
            'requirement_reference': 'Appendix C and Appendix D',
            'applicable_population': 'The 13 named institutional indicators',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Create, approve or correct missing indicator records',
            'support_status': 'Requires an additional field',
            'limitation': 'An approved indicator registry, active status and duplicate-control rule are required.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-12',
            'question': 'Which outcome records satisfy all ARTEMIA selection criteria?',
            'metric_id': 'c711-artemia-compliance',
            'purpose': 'Validate outcome selection governance',
            'requirement_reference': 'ARTEMIA Assessment',
            'applicable_population': 'All active in-scope outcome records',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Approve, revise or retire outcomes based on complete ARTEMIA evidence',
            'support_status': 'Requires an additional field',
            'limitation': 'The supplied metadata does not contain verified fields for all seven ARTEMIA selection criteria.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-13',
            'question': 'Which benchmarks have complete validation evidence?',
            'metric_id': 'c711-benchmark-validation',
            'purpose': 'Validate benchmark quality',
            'requirement_reference': '7.1.1.1(b), Appendix E',
            'applicable_population': 'All outcomes requiring a benchmark',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Approve, replace or revalidate benchmarks',
            'support_status': 'Requires an additional field',
            'limitation': 'Verified fields for benchmark origin, source evidence, relevance, credibility, currency and '
                          'applicability were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-14',
            'question': 'Which internal or proxy benchmarks lack a documented substitution rationale?',
            'metric_id': 'c711-proxy-rationale',
            'purpose': 'Control benchmark substitution',
            'requirement_reference': 'Appendix E benchmark application rules',
            'applicable_population': 'Outcomes using internal or proxy benchmarks because external data is unavailable',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Document the rationale or obtain a suitable external benchmark',
            'support_status': 'Requires an additional field',
            'limitation': 'A verified proxy-benchmark flag and substitution-rationale field were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-15',
            'question': 'Which targets have a valid benchmark, method, direction and review cycle?',
            'metric_id': 'c711-target-validity',
            'purpose': 'Validate target-setting governance',
            'requirement_reference': '7.1.1.1(c), Appendix E',
            'applicable_population': 'All active outcomes requiring a target',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Approve, revise or withdraw invalid targets',
            'support_status': 'Requires an additional field',
            'limitation': 'Verified fields for benchmark linkage, calculation method, direction, approval and review cycle '
                          'were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-16',
            'question': 'Which targets are overdue for review or adjustment?',
            'metric_id': 'c711-target-review',
            'purpose': 'Monitor target review cycles',
            'requirement_reference': 'Appendix E target review requirements',
            'applicable_population': 'All active targets due for quarterly, annual or biennial review under the approved '
                                     'rule',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete review and record approval or justification',
            'support_status': 'Requires an additional field',
            'limitation': 'Verified target review history and adjustment-cycle fields were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-17',
            'question': 'Which due measurements are complete, overdue or cannot be assessed?',
            'metric_id': 'c711-measurement-completion',
            'purpose': 'Monitor measurement completion',
            'requirement_reference': '7.1.1.1(d)',
            'applicable_population': 'Outcomes due for measurement in the selected period',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete overdue measurements and resolve missing source evidence',
            'support_status': 'Requires an additional field',
            'limitation': 'A due-measurement population, required frequency and approved calculation/source-evidence fields '
                          'were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-18',
            'question': 'Which outcomes meet their approved target after applying the correct direction or range rule?',
            'metric_id': 'c711-target-achievement',
            'purpose': 'Assess target achievement defensibly',
            'requirement_reference': '7.1.1.1(d)',
            'applicable_population': 'Outcomes with valid actual, target, unit, period, population and direction',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific higher, lower, range or distribution rule',
            'management_decision': 'Confirm achievement or require action',
            'support_status': 'Requires an additional field',
            'limitation': 'Indicator direction, unit compatibility, period, population and range rules were not supplied. A '
                          'universal greater-than-or-equal comparison is prohibited.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-19',
            'question': 'Which outcomes are below expectation after applying the approved comparison rule?',
            'metric_id': 'c711-below-target',
            'purpose': 'Identify performance gaps',
            'requirement_reference': '7.1.1.1(d)',
            'applicable_population': 'Outcomes with valid comparison data',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Initiate gap analysis and corrective or preventive action',
            'support_status': 'Requires an additional field',
            'limitation': 'The approved direction or range rule is unavailable, so below-target status cannot be calculated '
                          'defensibly.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-20',
            'question': 'Which below-target outcomes lack a linked Quality Action?',
            'metric_id': 'c711-action-linkage',
            'purpose': 'Ensure action linkage',
            'requirement_reference': '7.1.1.1(d) and Appendix A',
            'applicable_population': 'All below-target outcomes requiring action',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Create and approve a linked Quality Action',
            'support_status': 'Requires an additional field',
            'limitation': 'No verified relationship field linking a Quality Action to a specific outcome gap was supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-21',
            'question': 'Which performance gaps lack documented root cause analysis?',
            'metric_id': 'c711-root-cause',
            'purpose': 'Ensure gap investigation',
            'requirement_reference': 'ARTEMIA Execution and Mitigation',
            'applicable_population': 'All confirmed performance gaps requiring investigation',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete root cause analysis before finalising action',
            'support_status': 'Requires an additional field',
            'limitation': 'No verified outcome-gap root-cause field or child table was supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-22',
            'question': 'Which linked corrective actions are completed but not verified effective?',
            'metric_id': 'c711-action-effectiveness',
            'purpose': 'Verify improvement effectiveness',
            'requirement_reference': '7.1.1.1(e), Appendix A',
            'applicable_population': 'Actions linked to outcome gaps and due for effectiveness verification',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Verify, reopen or revise ineffective actions',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Completed status does not prove effectiveness. Post-action measurement and effectiveness '
                          'criteria were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-23',
            'question': 'Which outcomes have a valid three-year trend or an approved interim treatment?',
            'metric_id': 'c711-three-year-trend',
            'purpose': 'Validate trend sufficiency',
            'requirement_reference': '7.1.1.1(e), Appendix D and E',
            'applicable_population': 'All active outcomes requiring trend analysis',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Obtain missing periods or approve and disclose interim treatment',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'A verified trend-history child table with three consecutive years and interim-treatment evidence '
                          'was not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-24',
            'question': 'Which outcome trends are declining, unstable or cannot be assessed?',
            'metric_id': 'c711-trend-anomaly',
            'purpose': 'Direct management attention to adverse patterns',
            'requirement_reference': 'Appendix D trend requirements',
            'applicable_population': 'Outcomes with sufficient validated time-series data',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Investigate causes and adjust strategies',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Approved trend direction, method and anomaly thresholds were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-25',
            'question': 'Which outcomes lack complete stakeholder dissemination evidence?',
            'metric_id': 'c711-dissemination',
            'purpose': 'Verify transparent stakeholder access',
            'requirement_reference': '7.1.1.2',
            'applicable_population': 'Outcomes due for dissemination in the selected period',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete dissemination and capture stakeholder feedback',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'A verified dissemination log, stakeholder groups, channel, format and frequency fields were not '
                          'supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-26',
            'question': 'Which monthly departmental APSR reviews are missing, late or incomplete?',
            'metric_id': 'c711-apsr-monthly',
            'purpose': 'Monitor operational APSR',
            'requirement_reference': '7.1.1.3 APSR Review Requirements',
            'applicable_population': 'Required department-month reviews in the Quality Calendar',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete overdue reviews and raise actions',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'A verified APSR record or Quality Calendar mapping for department-month reviews was not '
                          'supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-27',
            'question': 'Were the required biannual cross-department APSR reviews completed with evidence and actions?',
            'metric_id': 'c711-apsr-biannual',
            'purpose': 'Monitor tactical APSR',
            'requirement_reference': '7.1.1.3 APSR Review Requirements',
            'applicable_population': 'Two required tactical reviews per reporting year',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete the review and record findings and actions',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'A verified tactical APSR record and required evidence fields were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-28',
            'question': 'Was the annual strategic APSR review completed during Management Review?',
            'metric_id': 'c711-apsr-annual',
            'purpose': 'Monitor strategic APSR',
            'requirement_reference': '7.1.1.3 APSR Review Requirements',
            'applicable_population': 'One annual strategic review per reporting year',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete or evidence the strategic review and Principal approval',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'A verified annual APSR record linked to Management Review was not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-29',
            'question': 'Did each APSR review assess Approach, Processes, Systems and Review?',
            'metric_id': 'c711-apsr-components',
            'purpose': 'Verify APSR method completeness',
            'requirement_reference': '7.1.1.3 APSR Method',
            'applicable_population': 'All completed APSR reviews',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete missing components before closure',
            'support_status': 'Requires an additional field',
            'limitation': 'Verified Approach, Processes, Systems and Review checklist fields were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-30',
            'question': 'Which Criterion 7 improvement cycles have not closed the PDCA loop?',
            'metric_id': 'c711-pdca-closure',
            'purpose': 'Verify closed-loop improvement',
            'requirement_reference': '7.1.1.3 and PDCA Alignment',
            'applicable_population': 'Criterion 7 findings and actions due for closure',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Complete Act-stage changes and verify effectiveness',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Verified linked evidence for Plan, Do, Check, Act and effectiveness was not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-31',
            'question': 'What is the Student Attrition Rate by approved programme, cohort and reporting period?',
            'metric_id': 'c711-attrition',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Student and Graduate Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review retention risk and interventions',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'An approved cohort denominator, premature-exit rules and student-level source mapping were not '
                          'supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-32',
            'question': 'What is the Progression Rate by approved programme, cohort and level?',
            'metric_id': 'c711-progression',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Student and Graduate Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review progression barriers and support',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Approved horizontal and vertical progression rules, eligible population and source mapping were '
                          'not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-33',
            'question': 'What is the Graduation Rate for cohorts due to complete?',
            'metric_id': 'c711-graduation',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Student and Graduate Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review completion performance',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'The cohort due to complete, adjusted timeframe rules and completion source mapping were not '
                          'supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-34',
            'question': 'What is the distribution and trend of Quality of Passes?',
            'metric_id': 'c711-quality-passes',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Student and Graduate Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review grade quality and assessment consistency',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Examination Board-approved grade records, grade-band definitions and comparability rules were '
                          'not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-35',
            'question': 'What is the Graduate Employment Rate within the approved post-completion period?',
            'metric_id': 'c711-employment',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Student and Graduate Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review programme relevance and employability',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Graduate survey source, eligible population, response basis and employment classification fields '
                          'were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-36',
            'question': 'What is the Student Satisfaction Rate for teaching quality, with response coverage?',
            'metric_id': 'c711-teaching-satisfaction',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Service Quality Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review teaching quality',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Survey question mapping, satisfaction threshold, valid-response denominator and '
                          'response-coverage source were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-37',
            'question': 'What is the Complaint Resolution SLA compliance rate?',
            'metric_id': 'c711-complaint-sla',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Service Quality Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review complaint-handling timeliness',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Complaint source, SLA start/stop events, working-day rule, pause conditions and exclusions were '
                          'not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-38',
            'question': 'What is the Overall Student Satisfaction Rate, with response coverage?',
            'metric_id': 'c711-overall-satisfaction',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Service Quality Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review the student experience',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Approved overall-satisfaction item and valid-response denominator were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-39',
            'question': 'What is the Liquidity Ratio for the approved reporting date?',
            'metric_id': 'c711-liquidity',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Operational Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review short-term financial resilience',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Approved finance source fields for current assets and current liabilities at the same reporting '
                          'date were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-40',
            'question': 'What is the Debt-Equity Ratio for the approved reporting date?',
            'metric_id': 'c711-debt-equity',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Operational Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review leverage and long-term sustainability',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Approved finance source fields for total liabilities and shareholders equity at the same '
                          'reporting date were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-41',
            'question': 'What cost savings, time savings and resource investments were achieved, reported separately?',
            'metric_id': 'c711-cost-time-investment',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: Operational Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review operational efficiency and investment',
            'support_status': 'Can be implemented with revised mapping',
            'limitation': 'The current operational source stores some savings fields but does not provide an approved '
                          'Criterion 7 population and separate validated units for all three measures.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-42',
            'question': 'What is the Overall Staff Satisfaction Rate, with response coverage?',
            'metric_id': 'c711-staff-satisfaction',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: People Development Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review engagement and workplace conditions',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Staff survey source, satisfaction threshold, eligible population and response-coverage fields '
                          'were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-43',
            'question': 'What are the average completed training hours per in-scope staff member?',
            'metric_id': 'c711-training-hours',
            'purpose': 'Measure the required named institutional indicator',
            'requirement_reference': 'Appendix C and D: People Development Outcomes',
            'applicable_population': 'Approved population defined for the indicator',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Indicator-specific',
            'management_decision': 'Review workforce development',
            'support_status': 'Requires a new DocType or child-table query',
            'limitation': 'Training records, completed-hour rules and the active staff denominator including part-time and '
                          'academic staff were not supplied.',
            'calculation_note': '',
            'source_key': 'quality_performance'},
           {'id': 'q711-44',
            'question': 'Are Quality Goal records available to support KPI and Quality Objective Plan governance?',
            'metric_id': 'c711-quality-goals',
            'purpose': 'Confirm the verified KPI source is accessible',
            'requirement_reference': 'Definitions: KPI and Quality Objective Plan refer to Quality Goal',
            'applicable_population': 'Readable Quality Goal records',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Map verified fields before using Quality Goal data as performance evidence',
            'support_status': 'Can be implemented now',
            'limitation': 'Record existence alone does not prove KPI definition, approval or alignment.',
            'calculation_note': 'Permission-aware count of readable Quality Goal records.',
            'source_key': 'quality_goal'},
           {'id': 'q711-45',
            'question': 'Is Criterion 7 review and dissemination evidence specifically linked in Quality Meeting and '
                        'Management Review records?',
            'metric_id': None,
            'purpose': 'Verify review evidence linkage',
            'requirement_reference': '7.1.1.2 and 7.1.1.3',
            'applicable_population': 'Criterion 7 review and dissemination events',
            'reporting_period': 'Selected reporting period',
            'target_direction': 'Not applicable',
            'management_decision': 'Add or verify Criterion 7 linkage fields before counting meetings as evidence',
            'support_status': 'Requires an additional field',
            'limitation': 'Current meeting and review counts cannot establish Criterion 7 content, period, stakeholders or '
                          'APSR completeness.',
            'calculation_note': '',
            'source_key': None}]}

EXCEPTION_METRIC_IDS = ['c711-missing-domain',
 'c711-missing-indicator',
 'c711-missing-benchmark',
 'c711-missing-target',
 'c711-missing-actual',
 'c711-missing-measurement-date',
 'c711-missing-owner',
 'c711-indicator-coverage',
 'c711-benchmark-validation',
 'c711-target-validity',
 'c711-measurement-completion',
 'c711-below-target',
 'c711-action-linkage',
 'c711-action-effectiveness',
 'c711-three-year-trend',
 'c711-dissemination',
 'c711-apsr-monthly',
 'c711-apsr-biannual',
 'c711-apsr-annual',
 'c711-pdca-closure']

STANDARD_FIELDS = ["name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"]


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
        return float(clean_text(value).replace(",", "").replace("SGD", "").replace("$", ""))
    except Exception:
        return None


def is_permission_error(error):
    text = lower_text(error)
    return "permission" in text or "not permitted" in text or "not allowed" in text or "403" in text


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
    return {"resolved": resolved, "missing": missing}


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
            frappe.get_list(doctype, fields=["name"], limit_start=0, limit_page_length=1, order_by="modified desc")
            attempt["status"] = "available"
            attempt["stage"] = "list"
            attempt["message"] = "Readable by the signed-in user. Source count is not inferred from the probe."
            attempts.append(attempt)
            return {
                "key": alias, "doctype": doctype, "display_doctype": display_doctype(doctype),
                "candidates": candidates, "status": "available", "count": None,
                "count_note": "Availability probe only. Use metrics for filtered counts.",
                "probe": "frappe.get_list", "fallback_used": candidate_index > 0,
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
                    "key": alias, "doctype": doctype, "display_doctype": display_doctype(doctype),
                    "candidates": candidates, "status": "permission_denied", "count": None,
                    "message": message, "probe": "frappe.get_list", "fallback_used": False,
                    "resolution_attempts": attempts,
                }
    expected = candidates[0] if candidates else None
    return {
        "key": alias, "doctype": expected, "display_doctype": display_doctype(expected),
        "candidates": candidates, "status": "unavailable", "count": None,
        "message": "No approved backend DocType could be resolved.",
        "resolution_attempts": attempts, "fallback_used": False,
    }


def source_filter_details(alias, doctype):
    applied = {}
    resolved = []
    unresolved = []
    field_map = FILTER_FIELD_CANDIDATES.get(alias) or {}
    requested_status = filters.get("status")
    if requested_status not in [None, "", "All", "all"]:
        status_field = resolve_field(doctype, field_map.get("status") or [])
        if status_field:
            applied[status_field] = requested_status
            resolved.append({"filter": "status", "field": status_field, "value": requested_status})
        else:
            unresolved.append({"filter": "status", "reason": "No verified status field is mapped for this source."})
    requested_year = filters.get("review_year") or filters.get("year") or filters.get("monitoring_year")
    requested_month = filters.get("month")
    if requested_year:
        year_field = resolve_field(doctype, field_map.get("year_value") or [])
        if year_field:
            applied[year_field] = requested_year
            resolved.append({"filter": "year", "field": year_field, "value": requested_year})
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
                                end_date = frappe.utils.add_days("%s-%02d-01" % (clean_text(requested_year), month_number + 1), -1)
                    except Exception:
                        pass
                applied[date_field] = ["between", [start_date, end_date]]
                resolved.append({"filter": "year", "field": date_field, "value": requested_year})
                if requested_month:
                    resolved.append({"filter": "month", "field": date_field, "value": requested_month})
            else:
                unresolved.append({"filter": "year", "reason": "No verified year or date field is mapped for this source."})
    elif requested_month:
        unresolved.append({"filter": "month", "reason": "A year is required before a month filter can be applied."})
    requested_category = filters.get("outcome_category")
    if requested_category not in [None, "", "All", "all"]:
        category_field = resolve_field(doctype, field_map.get("outcome_category") or [])
        if category_field:
            applied[category_field] = requested_category
            resolved.append({"filter": "outcome_category", "field": category_field, "value": requested_category})
        else:
            unresolved.append({"filter": "outcome_category", "reason": "This source has no verified outcome-category field."})
    requested_department = filters.get("department")
    if requested_department not in [None, "", "All", "all"]:
        department_field = resolve_field(doctype, field_map.get("department") or [])
        if department_field:
            applied[department_field] = requested_department
            resolved.append({"filter": "department", "field": department_field, "value": requested_department})
        else:
            unresolved.append({"filter": "department", "reason": "This source has no verified department field."})
    return {"applied": applied, "resolved": resolved, "unresolved": unresolved}


filter_diagnostics = {}
fetch_diagnostics = {}


def fetch_rows(source, requested_fields=None):
    doctype = source.get("doctype")
    alias = source.get("key")
    if source.get("status") != "available" or not doctype:
        return {"status": source.get("status") or "unavailable", "rows": [], "message": source.get("message") or "Source is unavailable.", "truncated": False}
    fields_to_fetch = safe_fields(doctype, ["name"] + (requested_fields or []))
    filter_result = source_filter_details(alias, doctype)
    filter_diagnostics[alias] = {
        "source": alias, "doctype": doctype, "display_doctype": display_doctype(doctype),
        "applied": filter_result.get("resolved") or [], "unresolved": filter_result.get("unresolved") or [],
    }
    try:
        rows = frappe.get_list(
            doctype, fields=fields_to_fetch, filters=filter_result.get("applied") or {},
            limit_page_length=row_limit + 1, order_by="modified desc"
        ) or []
        truncated = len(rows) > row_limit
        if truncated:
            rows = rows[:row_limit]
        result = {"status": "available", "rows": rows, "message": "", "truncated": truncated}
        fetch_diagnostics[alias] = result
        return result
    except Exception as error:
        status = "permission_denied" if is_permission_error(error) else "query_error"
        result = {"status": status, "rows": [], "message": clean_text(error), "truncated": False}
        fetch_diagnostics[alias] = result
        return result


def compare(row, fieldname, mode, expected=None, values=None):
    value = row.get(fieldname) if fieldname else None
    if mode == "truthy":
        return is_truthy(value)
    if mode == "falsy":
        return not is_truthy(value)
    if mode == "not_in":
        blocked = []
        for item in values or []:
            blocked.append(lower_text(item))
        return lower_text(value) not in blocked
    if mode == "in":
        allowed = []
        for item in values or []:
            allowed.append(lower_text(item))
        return lower_text(value) in allowed
    return False


def base_metric(metric, source=None):
    doctype = source.get("doctype") if source else None
    return {
        "id": metric.get("id"), "label": metric.get("label"), "source": metric.get("source"),
        "doctype": doctype, "display_doctype": display_doctype(doctype),
        "value": None, "record_count": 0, "total": 0, "denominator": None,
        "unit": metric.get("unit") or "records", "status": "unavailable", "message": "",
        "resolved_fields": [], "resolved_field_groups": [], "rows": [], "truncated": False,
        "evidence_level": metric.get("evidence_level") or "unknown",
    }


def evaluate_metric(metric, include_rows=False):
    mode = metric.get("mode")
    if mode in ["unsupported", "document_only"]:
        output = base_metric(metric, None)
        output["status"] = mode
        output["message"] = metric.get("message") or "Structured evidence is not currently available."
        return output
    source = resolved_sources.get(metric.get("source")) or {}
    output = base_metric(metric, source)
    if source.get("status") != "available":
        output["status"] = source.get("status") or "unavailable"
        output["message"] = source.get("message") or "Required source is unavailable."
        return output
    resolved_fields = []
    missing = []
    if metric.get("field"):
        fieldname = resolve_field(source.get("doctype"), metric.get("field") or [])
        if fieldname:
            resolved_fields.append(fieldname)
        else:
            missing.append(metric.get("field") or [])
    group_result = resolve_field_groups(source.get("doctype"), metric.get("fields") or [])
    for fieldname in group_result.get("resolved") or []:
        if fieldname not in resolved_fields:
            resolved_fields.append(fieldname)
    missing.extend(group_result.get("missing") or [])
    if missing:
        output["status"] = "unsupported_field"
        output["message"] = "Required field mapping is not installed or has not been verified."
        output["missing_field_candidates"] = missing
        output["resolved_fields"] = resolved_fields
        return output
    fetch_result = fetch_rows(source, resolved_fields)
    if fetch_result.get("status") != "available":
        output["status"] = fetch_result.get("status")
        output["message"] = fetch_result.get("message") or "The source query failed."
        return output
    rows = fetch_result.get("rows") or []
    matched = []
    value = 0
    denominator = None
    missing_values = []
    covered_values = []
    if mode == "all":
        matched = rows
        value = len(rows)
    elif mode in ["truthy", "falsy", "not_in", "in"]:
        for row in rows:
            if compare(row, resolved_fields[0] if resolved_fields else "", mode, values=metric.get("values")):
                matched.append(row)
        value = len(matched)
    elif mode == "all_required":
        for row in rows:
            accepted = True
            for fieldname in resolved_fields:
                if not is_truthy(row.get(fieldname)):
                    accepted = False
                    break
            if accepted:
                matched.append(row)
        value = len(matched)
        denominator = len(rows)
    elif mode == "sum":
        total_value = 0
        for row in rows:
            number = to_number(row.get(resolved_fields[0])) if resolved_fields else None
            if number is not None:
                total_value = total_value + number
                matched.append(row)
        value = round(total_value, 2)
    elif mode == "required_value_coverage":
        required_values = metric.get("required_values") or {}
        observed = []
        for row in rows:
            text = lower_text(row.get(resolved_fields[0])) if resolved_fields else ""
            if text:
                observed.append(text)
        for label in required_values:
            aliases = required_values.get(label) or []
            found = False
            for observed_value in observed:
                for alias in aliases:
                    if lower_text(alias) in observed_value:
                        found = True
                        break
                if found:
                    break
            if found:
                covered_values.append(label)
            else:
                missing_values.append(label)
        value = len(covered_values)
        denominator = len(required_values)
        matched = rows
    status = "partial_truncated" if fetch_result.get("truncated") else "available"
    output_rows = []
    if include_rows:
        start = (page - 1) * page_size
        end = start + page_size
        allowed = safe_fields(source.get("doctype"), SAFE_FIELDS.get(metric.get("source"), ["name"]))
        for row in matched[start:end]:
            item = {}
            for fieldname in allowed:
                item[fieldname] = row.get(fieldname)
            output_rows.append(item)
    output.update({
        "value": value, "record_count": len(matched), "total": len(matched), "denominator": denominator,
        "status": status, "message": "Result is limited by row_limit." if fetch_result.get("truncated") else "",
        "resolved_fields": resolved_fields, "resolved_field_groups": group_result.get("resolved") or [],
        "rows": output_rows, "truncated": bool(fetch_result.get("truncated")),
        "missing_values": missing_values, "covered_values": covered_values,
    })
    return output


if subcriterion not in CONFIG:
    frappe.throw("Unsupported Criterion 7 subcriterion.")

resolved_sources = {}
for alias in CONFIG[subcriterion]["sources"]:
    resolved_sources[alias] = resolve_source(alias)

metrics = []
for configured_metric in CONFIG[subcriterion]["metrics"]:
    metrics.append(evaluate_metric(configured_metric, False))
metric_by_id = {}
for metric in metrics:
    metric_by_id[metric.get("id")] = metric

approved_metric_ids = []
for definition in QUESTION_REGISTRY.get(subcriterion) or []:
    if definition.get("metric_id") and definition.get("metric_id") not in approved_metric_ids:
        approved_metric_ids.append(definition.get("metric_id"))
supporting_metrics = []
for metric in metrics:
    if metric.get("id") not in approved_metric_ids:
        supporting_metrics.append(metric)


def format_metric_answer(metric):
    if not metric:
        return "Cannot assess from current ERPNext data."
    if metric.get("status") not in ["available", "partial_truncated"]:
        return "Cannot assess from current ERPNext data: " + clean_text(metric.get("message") or metric.get("status"))
    value = metric.get("value")
    unit = metric.get("unit") or "records"
    denominator = metric.get("denominator")
    if unit == "SGD":
        answer = "SGD " + str(value) + " is the stored total for the readable records under the current filters."
    elif denominator is not None:
        answer = str(value) + " of " + str(denominator) + " " + unit + " meet the mapped rule."
    else:
        answer = str(value) + " " + unit + " match the current filters."
    if metric.get("missing_values"):
        answer = answer + " Missing: " + ", ".join(metric.get("missing_values")) + "."
    evidence_level = metric.get("evidence_level")
    if evidence_level == "record_existence":
        answer = answer + " This confirms record existence only, not compliance or effectiveness."
    elif evidence_level == "partial_completeness":
        answer = answer + " This is a partial mapped-field readiness check, not full policy compliance."
    elif evidence_level == "stored_calculation":
        answer = answer + " The stored calculation was not independently recalculated by this API."
    if metric.get("truncated"):
        answer = answer + " The result is truncated at row_limit and must not be treated as the complete population."
    return answer


questions = []
for definition in QUESTION_REGISTRY.get(subcriterion) or []:
    selected_metric = metric_by_id.get(definition.get("metric_id")) if definition.get("metric_id") else None
    if selected_metric:
        answer = format_metric_answer(selected_metric)
        status = selected_metric.get("status")
        if status == "available" and definition.get("support_status") == "Can be implemented now":
            confidence = "Live"
        elif status == "document_only":
            confidence = "Document only"
        elif status in ["available", "partial_truncated"]:
            confidence = "Partial"
        else:
            confidence = "Unavailable"
        doctype = selected_metric.get("doctype")
        display_name = selected_metric.get("display_doctype")
        source_key = selected_metric.get("source")
        record_count = selected_metric.get("record_count") or 0
        resolved_fields = selected_metric.get("resolved_fields") or []
        unit = selected_metric.get("unit")
    else:
        answer = "Cannot assess from current ERPNext data: " + clean_text(definition.get("limitation") or "additional structured evidence is required")
        status = "document_only" if definition.get("support_status") == "Document evidence only" else "unsupported"
        confidence = "Document only" if status == "document_only" else "Unavailable"
        source_key = definition.get("source_key")
        source = resolved_sources.get(source_key) or {}
        candidates = SOURCE_CANDIDATES.get(source_key) or []
        doctype = source.get("doctype") or (candidates[0] if candidates else None)
        display_name = display_doctype(doctype)
        record_count = 0
        resolved_fields = []
        unit = None
    questions.append({
        "id": definition.get("id"), "criterion": subcriterion, "question": definition.get("question"),
        "answer": answer, "metric_id": definition.get("metric_id"), "record_count": record_count,
        "source": source_key, "doctype": doctype, "display_doctype": display_name,
        "resolved_fields": resolved_fields, "status": status, "confidence": confidence, "unit": unit,
        "support_status": definition.get("support_status"),
        "primary_management_purpose": definition.get("purpose"),
        "requirement_reference": definition.get("requirement_reference"),
        "applicable_population": definition.get("applicable_population"),
        "reporting_period": definition.get("reporting_period"),
        "target_direction": definition.get("target_direction"),
        "calculation_note": definition.get("calculation_note"),
        "management_decision": definition.get("management_decision"),
        "limitation": definition.get("limitation") or "",
    })

sources = []
source_mapping = []
for alias in CONFIG[subcriterion]["sources"]:
    source = resolved_sources.get(alias)
    sources.append(source)
    source_mapping.append({
        "key": alias, "backend_doctype": source.get("doctype"), "display_label": source.get("display_doctype"),
        "candidates": source.get("candidates") or [], "status": source.get("status"), "message": source.get("message") or "",
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

requirements = []
for definition in QUESTION_REGISTRY.get(subcriterion) or []:
    requirements.append({
        "id": definition.get("id"), "criterion": subcriterion,
        "requirement_reference": definition.get("requirement_reference"),
        "management_question": definition.get("question"),
        "applicable_population": definition.get("applicable_population"),
        "reporting_period": definition.get("reporting_period"),
        "target_direction": definition.get("target_direction"),
        "calculation_note": definition.get("calculation_note"),
        "management_decision": definition.get("management_decision"),
        "support_status": definition.get("support_status"),
        "source": definition.get("source_key"), "metric_id": definition.get("metric_id"),
        "evidence_gap": definition.get("limitation") or "",
    })

data_quality = []
for source in sources:
    if source.get("status") != "available":
        data_quality.append({
            "criterion": subcriterion, "check": "Source availability", "source": source.get("display_doctype"),
            "backend_doctype": source.get("doctype"), "status": source.get("status"),
            "detail": source.get("message") or "Source is unavailable.",
        })
for metric in metrics:
    if metric.get("status") not in ["available"]:
        data_quality.append({
            "criterion": subcriterion, "check": metric.get("label"),
            "source": metric.get("display_doctype") or metric.get("source"), "backend_doctype": metric.get("doctype"),
            "status": metric.get("status"), "detail": metric.get("message") or "Metric requires attention.",
        })
for item in unresolved_filters:
    data_quality.append({
        "criterion": subcriterion, "check": "Filter mapping", "source": item.get("source"),
        "status": "unsupported_filter", "detail": clean_text(item.get("filter")) + ": " + clean_text(item.get("reason")),
    })

exceptions = []
for metric in metrics:
    if metric.get("id") in EXCEPTION_METRIC_IDS:
        exceptions.append(metric)

readiness = []
for source in sources:
    readiness.append({
        "type": "source", "key": source.get("key"), "label": source.get("display_doctype"),
        "backend_doctype": source.get("doctype"), "status": source.get("status"),
        "message": source.get("message") or source.get("count_note") or "",
    })
for question in questions:
    readiness.append({
        "type": "question", "key": question.get("id"), "label": question.get("question"),
        "status": question.get("status"), "support_status": question.get("support_status"),
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
        "criterion": subcriterion, "metric_id": metric.get("id"), "label": metric.get("label"),
        "value": metric.get("value"), "status": metric.get("status"), "doctype": metric.get("doctype"),
        "display_doctype": metric.get("display_doctype"), "truncated": metric.get("truncated"),
    })
for question in questions:
    if question.get("status") != "available":
        criterion_overview.append({
            "criterion": subcriterion, "question_id": question.get("id"), "label": question.get("question"),
            "value": None, "status": question.get("status"), "support_status": question.get("support_status"),
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
        "api_method": "ucc_analytics_criterion_7", "platform_version": "2.0.0-policy-aligned",
        "status": "policy_aligned_foundation", "generated_at": frappe.utils.now(),
        "action": action, "subcriterion": subcriterion, "row_limit": row_limit,
    },
    "policy": POLICY_REGISTRY.get(subcriterion), "filters": filters,
    "resolved_filters": resolved_filters, "unresolved_filters": unresolved_filters,
    "sources": sources, "source_mapping": source_mapping,
    "metrics": metrics, "supporting_metrics": supporting_metrics,
    "questions": questions, "exceptions": exceptions, "data_quality": data_quality,
    "requirements": requirements, "readiness": readiness, "criterion_overview": criterion_overview,
    "source_summary": {"total": len(sources), "available": available_sources, "issues": len(sources) - available_sources},
    "metric_summary": {"total": len(metrics), "available": available_metrics, "issues": len(metrics) - available_metrics},
    "question_summary": {"total": len(questions), "available": available_questions, "issues": len(questions) - available_questions},
    "data": {
        "sources": sources, "source_mapping": source_mapping, "metrics": metrics,
        "supporting_metrics": supporting_metrics, "questions": questions, "exceptions": exceptions,
        "data_quality": data_quality, "requirements": requirements, "readiness": readiness,
        "criterion_overview": criterion_overview,
    },
    "warnings": [
        "The current controlled procedure is consolidated under 7.1.1. Appendix C references 7.2.1 to 7.2.4 are treated as legacy domain labels, not separate current subcriteria.",
        "The rendered procedure contains 33 pages while its footer states 32 pages. Verify and correct the controlled master.",
        "Only the exact backend DocType Quality Performance Outcomes is queried. The unverified singular candidate is not used.",
        "Quality Goal is treated as the procedure-defined KPI and Quality Objective Plan source, but its detailed field mapping remains unverified.",
        "A populated actual and target are not compared until indicator direction, unit, period, population and comparison rule are verified.",
        "Quality Action, Quality Meeting and Management Review record counts are supporting metrics only and do not prove Criterion 7 linkage, dissemination, APSR completion or effectiveness.",
        "Operational Outcomes Cost Time Saving is retained as a supporting source only. Stored totals are not treated as overall Criterion 7 effectiveness.",
        "Missing data, permission failures, query errors and truncated populations are never converted into a valid zero.",
    ],
}

result = standardise_response_contract(result, "Criterion 7", "ucc_analytics_criterion_7", action, subcriterion, row_limit)

if action == "policy_registry":
    result["registry"] = POLICY_REGISTRY
elif action == "requirement_registry":
    result["registry"] = requirements
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
        frappe.throw("Unknown Criterion 7 metric.")
    result["drilldown"] = evaluate_metric(selected_config, True)

result = standardise_response_contract(result, "Criterion 7", "ucc_analytics_criterion_7", action, subcriterion, row_limit)

frappe.response["message"] = result
