"""
UCC Intelligence Platform Server Script

Visible name:
    UCC Analytics - Criterion 3

Script type:
    API

API method:
    ucc_analytics_criterion_3

Purpose:
    Return a permission-aware, evidence-based management analytics catalogue for
    EduTrust Criterion 3. The script separates management questions from raw
    recruitment-agent record counts and does not infer compliance where the
    required relationship, denominator, approval trail, child-table metadata or
    controlled field is unavailable.

Revision:
    Criterion 3 catalogue version 2.0.2
    UCC Intelligence Platform version 1.10.5

Deployment:
    Allow Guest must remain disabled.

Important design rules:
    1. Missing evidence is reported as unavailable, not converted to zero.
    2. Partial proxy calculations are labelled clearly and never presented as
       full compliance conclusions.
    3. Permission-aware frappe.get_list calls are used for all live records.
    4. Drill-down rows are restricted to approved safe fields.
    5. Agent existence, appointment, training, evaluation, performance and
       continued-authorisation decisions are treated as different controls.
    6. IMPORTANT DOCTYPE RULE: Supplier Rating is the actual Frappe DocType.
       Provider Rating is only the translated display label used by the frontend.
       Never query or resolve a server-side DocType named Provider Rating.
    7. API compatibility: resolved_fields must remain a flat list because the
       current dashboard renderer applies JavaScript Array.filter to it.
"""

payload_input = frappe.form_dict.get("payload") or {}
try:
    payload = json.loads(payload_input) if isinstance(payload_input, str) else payload_input
except Exception:
    payload = {}
if not isinstance(payload, dict):
    payload = {}
action = payload.get("action") or "summary"
subcriterion = payload.get("subcriterion") or "3.1.1"
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
    "question_registry", "question_catalogue", "drilldown"
]
if action not in ALLOWED_ACTIONS:
    frappe.throw("Unsupported Criterion 3 action.")

POLICY_REGISTRY = {
    "overview": {
        "title": "Criterion 3 Overview",
        "policy": "Criterion 3 consolidated management view",
        "version": "2.0.0",
        "notes": "The overview combines only known, requirement-scoped exception proxies."
    },
    "3.1.1": {
        "title": "Selection and Appointment of External Recruitment Agents",
        "policy": "PPD-SES-SL-3.1.1",
        "version": "1.2"
    },
    "3.2.1": {
        "title": "Management and Evaluation of Recruitment Agents",
        "policy": "PPD-SES-SL-3.2.1",
        "version": "1.2"
    }
}

SOURCE_CANDIDATES = {
    "agent": ["Agent"],
    "contract": ["Agent Contract"],
    "nda": ["Non Disclosure Agreement", "Non-Disclosure Agreement"],
    "onboarding": ["External Onboarding"],
    "offboarding": ["External Offboarding"],
    "supplier_rating": ["Supplier Rating"],
    "annual_review": ["Agent Annual Performance Review"],
    "claim": ["Agent Claim Form"],
    "applicant": ["Student Applicant"],
    "admission": ["Student Admission UCC"],
    "material_vetting": ["Material Vetting Form"],
    "helpdesk_ticket": ["HD Ticket", "Issue", "Helpdesk Ticket"],
    "quality_action": ["Quality Action"],
    "management_review": ["Management Review"]
}

SAFE_FIELDS = {
    "agent": [
        "name", "agent_or_company_name", "status", "workflow_state",
        "custom_ra_application_form_date", "application_date", "processed_date",
        "approved_date", "approval_date", "activation_date", "date_activated",
        "place_of_registration", "countries_of_recruitment",
        "average_identification_and_selection_score", "overall_selection_score",
        "done_consent_and_onboarding_survey", "onboarding_survey_date",
        "contract", "nda", "agent_search_type", "identification_types",
        "share_values_rating", "legal_rating", "partnership_rating",
        "collaborative_rating", "financial_rating", "communication_rating",
        "cultural_rating", "support_rating", "sustainability_rating",
        "referee_rating", "referee_recommendation_rating", "recommendation_rating",
        "interview_date", "approval_status", "approved_by", "recruitment_target",
        "marketing_plan", "effective_date_of_non_representation",
        "last_evaluation_date", "next_evaluation_date", "modified"
    ],
    "contract": [
        "name", "ac_agent_link_agent_contract", "ac_name_of_agent", "agent",
        "posting_date", "start_date", "end_date", "contract_type", "status",
        "workflow_state", "requires_nda", "nda_acknowledged", "nda_signed_date",
        "signed_date", "ucc_signed_date", "recruitment_target", "target_students",
        "marketing_plan", "commission_rate", "renewal_decision", "decision_status",
        "decision_date", "approved_by", "docstatus", "modified"
    ],
    "nda": [
        "name", "status", "workflow_state", "agent_contract", "agent",
        "posting_date", "start_date", "end_date", "signed_date",
        "ucc_signed_date", "docstatus", "modified"
    ],
    "onboarding": [
        "name", "document_type", "agent_id", "agent_name", "date_of_joining",
        "onboarding_begins_on", "completion_date", "status", "boarding_status",
        "signed_date", "signed_date_and_time", "consent_completed",
        "training_completed", "modified"
    ],
    "offboarding": [
        "name", "document_type", "agent_id", "agent_name",
        "separation_begins_on", "last_working_day", "completion_date", "status",
        "boarding_status", "signed_date", "access_revoked_date",
        "documents_returned_date", "checklist_completed", "modified"
    ],
    "supplier_rating": [
        "name", "posting_date", "year", "status", "workflow_state", "type",
        "document", "supplier", "agent", "evaluation_stage", "rating",
        "rating_likert", "overall_score", "assessment_template", "assessment",
        "recommendation", "note", "modified"
    ],
    "annual_review": [
        "name", "agent_name", "agent_full_name", "year", "date_of_review",
        "next_review_date", "reviewed_by", "status", "recommendation",
        "survey_training", "survey_comm", "survey_marketing",
        "survey_stakeholder", "survey_pdpa", "survey_isms", "survey_overall",
        "rating_recognition", "rating_pro_development", "rating_agent_recommend",
        "rating_policies_clarity", "rating_support_resources",
        "rating_communication", "overall_performance_score", "modified"
    ],
    "claim": [
        "name", "year", "month", "agent", "full_name", "teaching_total",
        "extra_total", "grand_total", "status", "workflow_state", "docstatus",
        "modified"
    ],
    "applicant": [
        "name", "applicant_name", "student_name", "application_status", "status",
        "custom_agent", "agent", "recruitment_agent", "academic_year",
        "program", "modified"
    ],
    "admission": [
        "name", "student", "student_name", "student_applicant", "status",
        "custom_agent", "agent", "recruitment_agent", "academic_year",
        "program", "date_of_commencement", "commencement_date", "modified"
    ],
    "material_vetting": [
        "name", "title", "subject", "status", "approval_status", "workflow_state",
        "reference_doctype", "reference_name", "agent", "recruitment_agent",
        "requester", "submission_date", "approval_date", "publication_date",
        "approved_by", "modified"
    ],
    "helpdesk_ticket": [
        "name", "subject", "description", "status", "priority", "ticket_type",
        "category", "reference_doctype", "reference_name", "agent",
        "recruitment_agent", "agreement_status", "resolution_date", "modified"
    ],
    "quality_action": [
        "name", "title", "subject", "finding_summary", "criterion", "gd4_criterion",
        "status", "workflow_state", "assigned_to", "owner", "due_date",
        "completion_date", "effectiveness_status", "effectiveness_result",
        "reference_doctype", "reference_name", "agent", "modified"
    ],
    "management_review": [
        "name", "title", "subject", "status", "meeting_date", "review_date",
        "criterion", "gd4_criterion", "decision", "action_required", "modified"
    ]
}

FILTER_FIELD_CANDIDATES = {
    "status": ["status", "review_status", "application_status", "workflow_state"],
    "agent": [
        "agent_id", "agent_name", "agent_full_name", "ac_agent_link_agent_contract",
        "document", "supplier", "custom_agent", "agent", "recruitment_agent",
        "reference_name"
    ],
    "year": ["year", "academic_year"],
    "academic_year": ["academic_year", "year"],
    "evaluation_stage": ["evaluation_stage"]
}


def unsupported_metric(metric_id_value, label, message, support_status, requirement_basis, decision_use):
    return {
        "id": metric_id_value,
        "label": label,
        "mode": "unsupported",
        "category": "management",
        "support_status": support_status,
        "message": message,
        "requirement_basis": requirement_basis,
        "decision_use": decision_use
    }


CONFIG = {
    "overview": {
        "sources": ["agent", "contract"],
        "metrics": [
            {
                "id": "ov-under-review",
                "label": "Agents under review",
                "source": "agent",
                "mode": "equals",
                "field": ["status", "workflow_state"],
                "value": "Under Review",
                "category": "supporting",
                "is_exception": True
            },
            {
                "id": "ov-noncontinuing",
                "label": "Inactive, suspended or terminated agents",
                "source": "agent",
                "mode": "in",
                "field": ["status", "workflow_state"],
                "values": ["Inactive", "Suspended", "Terminated"],
                "category": "supporting",
                "is_exception": True
            },
            {
                "id": "ov-expiring-90",
                "label": "Agent contracts expiring within 90 days",
                "source": "contract",
                "mode": "date_next_days",
                "field": ["end_date"],
                "days": 90,
                "category": "supporting",
                "is_exception": True,
                "support_status": "partial",
                "limitations": [
                    "The metric cannot confirm that each record is the current contract of an active agent."
                ]
            },
            {
                "id": "ov-known-attention-total",
                "label": "Known live Criterion 3 exception records",
                "mode": "derived_sum",
                "refs": ["ov-under-review", "ov-noncontinuing", "ov-expiring-90"],
                "category": "management",
                "support_status": "partial",
                "limitations": [
                    "This total combines record counts and may contain the same agent more than once.",
                    "Unsupported complaint, training, background-check and corrective-action gaps are excluded from the number."
                ],
                "requirement_basis": "Criterion 3 management attention queue",
                "decision_use": "Prioritise known agent review, continuation and contract-expiry follow-up.",
                "is_exception": True
            },
            unsupported_metric(
                "ov-requirement-evidence-coverage",
                "Criterion 3 requirement evidence coverage",
                "An approved requirement-to-evidence registry and evidence-state rules are required before requirement coverage can be calculated.",
                "requires_additional_field",
                "Criterion 3 audit readiness",
                "Determine which mandatory requirements have live, document-only or missing evidence."
            )
        ]
    },
    "3.1.1": {
        "sources": [
            "agent", "supplier_rating", "contract", "nda", "onboarding",
            "applicant", "management_review", "quality_action"
        ],
        "metrics": [
            {
                "id": "c311-agents",
                "label": "Recruitment agents in scope",
                "source": "agent",
                "mode": "all",
                "category": "supporting"
            },
            {
                "id": "c311-screening",
                "label": "Agents in screening or approval",
                "source": "agent",
                "mode": "in",
                "field": ["status", "workflow_state"],
                "values": [
                    "Prospective", "Pending Verification", "For Approval",
                    "For Internal Use", "Under Review"
                ],
                "category": "supporting",
                "is_exception": True
            },
            {
                "id": "c311-active",
                "label": "Active appointed agents",
                "source": "agent",
                "mode": "equals",
                "field": ["status", "workflow_state"],
                "value": "Active",
                "category": "supporting"
            },
            {
                "id": "c311-formal-selection-population",
                "label": "Agents with an application date",
                "source": "agent",
                "mode": "truthy",
                "field": ["custom_ra_application_form_date", "application_date"],
                "category": "supporting"
            },
            {
                "id": "c311-identification-complete",
                "label": "Agent records with application date and identification source",
                "source": "agent",
                "mode": "all_required",
                "required_fields": [
                    ["custom_ra_application_form_date", "application_date"],
                    ["agent_search_type", "identification_types"]
                ],
                "category": "supporting"
            },
            {
                "id": "c311-identification-completeness-proxy",
                "label": "Application and identification traceability proxy",
                "mode": "derived_percent",
                "numerator_ref": "c311-identification-complete",
                "denominator_ref": "c311-formal-selection-population",
                "category": "management",
                "support_status": "partial",
                "limitations": [
                    "The proxy does not prove that the strategic need, preliminary discussion or screening decision was documented.",
                    "The denominator is limited to Agent records with an installed application-date field."
                ],
                "requirement_basis": "RA identification and screening process",
                "decision_use": "Follow up Agent records with incomplete entry-route evidence."
            },
            {
                "id": "c311-selection-score",
                "label": "Selection score recorded",
                "source": "agent",
                "mode": "truthy",
                "field": [
                    "average_identification_and_selection_score",
                    "overall_selection_score"
                ],
                "category": "supporting"
            },
            {
                "id": "c311-selection-complete",
                "label": "Selection criteria and passing score completed",
                "source": "agent",
                "mode": "conditions",
                "required_fields": [
                    ["share_values_rating"],
                    ["legal_rating"],
                    ["partnership_rating"],
                    ["collaborative_rating"],
                    ["financial_rating"],
                    ["communication_rating"],
                    ["cultural_rating"],
                    ["support_rating"],
                    ["sustainability_rating"],
                    ["referee_rating", "referee_recommendation_rating", "recommendation_rating"]
                ],
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {
                                "field": [
                                    "average_identification_and_selection_score",
                                    "overall_selection_score"
                                ],
                                "op": "gte",
                                "value": 3.5
                            }
                        ]
                    }
                ],
                "category": "supporting"
            },
            {
                "id": "c311-selection-completion-proxy",
                "label": "Selection criteria and passing-score completion proxy",
                "mode": "derived_percent",
                "numerator_ref": "c311-selection-complete",
                "denominator_ref": "c311-formal-selection-population",
                "category": "management",
                "support_status": "partial",
                "limitations": [
                    "The calculation requires all ten controlled selection criteria, including Referee Recommendation, and a recorded score of at least 3.5.",
                    "It does not prove that criterion notes, interview results, background checks or authorised approval were completed before appointment."
                ],
                "requirement_basis": "RA evaluation and selection criteria",
                "decision_use": "Prevent approval where the installed selection evidence is incomplete or below threshold."
            },
            {
                "id": "c311-screening-ratings",
                "label": "Identification and screening evaluations",
                "source": "supplier_rating",
                "mode": "conditions",
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["type"], "op": "equals", "value": "Agent"},
                            {
                                "field": ["evaluation_stage"],
                                "op": "equals",
                                "value": "Identification and Screening"
                            }
                        ]
                    }
                ],
                "category": "supporting",
                "support_status": "partial",
                "limitations": [
                    "The controlled procedure identifies the Rating section of Agent DocType as the selection record. Supplier Rating is the actual DocType and is treated as supporting evidence only; Provider Rating is only its frontend display label."
                ]
            },
            {
                "id": "c311-first-contracts",
                "label": "First-time agreements",
                "source": "contract",
                "mode": "equals",
                "field": ["contract_type"],
                "value": "First-time Agreement",
                "category": "supporting"
            },
            {
                "id": "c311-signed-contracts",
                "label": "Contracts signed by both parties",
                "source": "contract",
                "mode": "all_required",
                "required_fields": [["signed_date"], ["ucc_signed_date"]],
                "category": "supporting"
            },
            {
                "id": "c311-current-valid-signed-contracts",
                "label": "Currently valid contracts signed by both parties",
                "source": "contract",
                "mode": "conditions",
                "required_fields": [["signed_date"], ["ucc_signed_date"]],
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["start_date"], "op": "date_on_or_before_today"},
                            {"field": ["end_date"], "op": "date_on_or_after_today"}
                        ]
                    }
                ],
                "category": "supporting",
                "support_status": "partial",
                "limitations": [
                    "The metric counts contract records and cannot confirm that each contract is the authoritative current contract of an active Agent record."
                ]
            },
            {
                "id": "c311-nda-required",
                "label": "Contracts requiring NDA",
                "source": "contract",
                "mode": "truthy",
                "field": ["requires_nda"],
                "category": "supporting"
            },
            {
                "id": "c311-nda-acknowledged",
                "label": "NDA acknowledgements completed",
                "source": "contract",
                "mode": "truthy",
                "field": ["nda_acknowledged"],
                "category": "supporting"
            },
            {
                "id": "c311-signed-nda",
                "label": "NDAs signed by both parties",
                "source": "nda",
                "mode": "all_required",
                "required_fields": [["signed_date"], ["ucc_signed_date"]],
                "category": "supporting"
            },
            {
                "id": "c311-onboardings",
                "label": "Agent onboarding records",
                "source": "onboarding",
                "mode": "conditions",
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["document_type"], "op": "equals", "value": "Agent"}
                        ]
                    }
                ],
                "category": "supporting"
            },
            {
                "id": "c311-onboarding-signed",
                "label": "Signed agent onboarding records",
                "source": "onboarding",
                "mode": "conditions",
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["document_type"], "op": "equals", "value": "Agent"},
                            {
                                "field": ["signed_date", "signed_date_and_time"],
                                "op": "truthy"
                            }
                        ]
                    }
                ],
                "category": "supporting"
            },
            {
                "id": "c311-active-readiness-records",
                "label": "Active Agent records with installed contract, NDA and onboarding markers",
                "source": "agent",
                "mode": "conditions",
                "required_fields": [
                    ["contract"],
                    ["nda"],
                    ["done_consent_and_onboarding_survey"],
                    ["onboarding_survey_date"]
                ],
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["status", "workflow_state"], "op": "equals", "value": "Active"}
                        ]
                    }
                ],
                "category": "supporting"
            },
            {
                "id": "c311-active-readiness-proxy",
                "label": "Active Agent readiness-record proxy",
                "mode": "derived_percent",
                "numerator_ref": "c311-active-readiness-records",
                "denominator_ref": "c311-active",
                "category": "supporting",
                "support_status": "partial",
                "limitations": [
                    "References and onboarding markers do not prove that the linked contract and NDA are signed, current or approved, or that onboarding occurred before activation."
                ]
            },
            {
                "id": "c311-linked-applicants",
                "label": "Applicants linked to an agent",
                "source": "applicant",
                "mode": "truthy",
                "field": ["custom_agent", "agent", "recruitment_agent"],
                "category": "supporting"
            },
            unsupported_metric(
                "c311-background-approval-compliance",
                "Background check and authorised approval compliance",
                "A dedicated background-check result and the required final approval authority, decision date and sequence are not confirmed in the supplied fields.",
                "requires_additional_field",
                "Background check and final appointment decision",
                "Approve or reject shortlisted agents only after the required integrity checks and authorised decision."
            ),
            unsupported_metric(
                "c311-valid-appointment-coverage",
                "Valid appointment coverage",
                "A relationship from each active Agent record to its authoritative current signed contract, signed NDA and appointment approval is required.",
                "requires_relationship",
                "Valid contract and NDA before appointment",
                "Prevent an agent from representing UCC without current authority."
            ),
            unsupported_metric(
                "c311-onboarding-before-activation",
                "Onboarding completed before activation",
                "The activation date and complete mandatory onboarding, training, Consent and Agreement evidence must be linked at Agent level.",
                "requires_relationship",
                "Mandatory onboarding before active recruitment",
                "Activate or hold an appointment based on complete readiness evidence."
            ),
            unsupported_metric(
                "c311-agent-list-accuracy",
                "Published Agent List accuracy",
                "A machine-readable website publication or synchronisation result is required to compare SMS countries, current contract dates, status and effective date of non-representation with the public Agent List.",
                "requires_new_source",
                "GD4 Agent List publication and SSOT control",
                "Correct public-list omissions and mismatches."
            ),
            unsupported_metric(
                "c311-process-review-effectiveness",
                "Selection and appointment process review effectiveness",
                "A requirement-scoped APSR review linked to resulting Quality Actions and effectiveness verification is required.",
                "requires_relationship",
                "Review of selection and appointment for continual improvement",
                "Retain or improve the process after reviewing verified outcomes."
            )
        ]
    },
    "3.2.1": {
        "sources": [
            "agent", "supplier_rating", "annual_review", "contract",
            "offboarding", "claim", "applicant", "admission",
            "material_vetting", "helpdesk_ticket", "quality_action",
            "management_review"
        ],
        "metrics": [
            {
                "id": "c321-active",
                "label": "Active recruitment agents",
                "source": "agent",
                "mode": "equals",
                "field": ["status", "workflow_state"],
                "value": "Active",
                "category": "supporting"
            },
            {
                "id": "c321-under-review",
                "label": "Agents under review",
                "source": "agent",
                "mode": "equals",
                "field": ["status", "workflow_state"],
                "value": "Under Review",
                "category": "supporting",
                "is_exception": True
            },
            {
                "id": "c321-suspended-terminated",
                "label": "Inactive, suspended or terminated agents",
                "source": "agent",
                "mode": "in",
                "field": ["status", "workflow_state"],
                "values": ["Inactive", "Suspended", "Terminated"],
                "category": "supporting",
                "is_exception": True
            },
            {
                "id": "c321-annual-reviews",
                "label": "Annual performance review records",
                "source": "annual_review",
                "mode": "all",
                "category": "supporting",
                "support_status": "partial",
                "limitations": [
                    "The controlled procedure identifies Monitor and Review in Agent DocType as the authoritative annual evaluation record."
                ]
            },
            {
                "id": "c321-survey-average",
                "label": "Average annual agent survey score",
                "source": "annual_review",
                "mode": "average_fields",
                "fields": [
                    ["survey_training"], ["survey_comm"], ["survey_marketing"],
                    ["survey_stakeholder"], ["survey_pdpa"], ["survey_isms"],
                    ["survey_overall"]
                ],
                "unit": "rating",
                "category": "supporting",
                "support_status": "partial",
                "limitations": [
                    "This is a survey average only. It is not the approved nine-criterion annual performance score and must not be used as the renewal result."
                ]
            },
            {
                "id": "c321-renewals",
                "label": "Renewal agreements",
                "source": "contract",
                "mode": "equals",
                "field": ["contract_type"],
                "value": "Renewal",
                "category": "supporting"
            },
            {
                "id": "c321-expiring-90",
                "label": "Contracts expiring within 90 days",
                "source": "contract",
                "mode": "date_next_days",
                "field": ["end_date"],
                "days": 90,
                "category": "supporting",
                "is_exception": True,
                "support_status": "partial",
                "limitations": [
                    "The metric cannot confirm that each record is the authoritative current contract of an active agent."
                ]
            },
            {
                "id": "c321-renewal-rule-compliant",
                "label": "Renewal agreements meeting the available checkpoint and duration rules",
                "source": "contract",
                "mode": "renewal_rule_compliant",
                "required_fields": [["start_date"], ["end_date"]],
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["contract_type"], "op": "equals", "value": "Renewal"}
                        ]
                    }
                ],
                "category": "supporting"
            },
            {
                "id": "c321-renewal-rule-proxy",
                "label": "Renewal checkpoint and maximum-duration compliance proxy",
                "mode": "derived_percent",
                "numerator_ref": "c321-renewal-rule-compliant",
                "denominator_ref": "c321-renewals",
                "category": "management",
                "support_status": "partial",
                "limitations": [
                    "The proxy checks that the end month is June or December and that the end date is not later than eighteen months after the start date.",
                    "It does not validate an approved exception, the intended nearest-checkpoint calculation or the authoritative current contract relationship."
                ],
                "requirement_basis": "June and December renewal checkpoints and maximum eighteen-month duration",
                "decision_use": "Correct renewal periods that do not meet the available contract-date rules."
            },
            {
                "id": "c321-regular-evaluations",
                "label": "Renewal and regular evaluation records",
                "source": "supplier_rating",
                "mode": "conditions",
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["type"], "op": "equals", "value": "Agent"},
                            {
                                "field": ["evaluation_stage"],
                                "op": "equals",
                                "value": "Renewal and Regular Review"
                            }
                        ]
                    }
                ],
                "category": "supporting",
                "support_status": "partial",
                "limitations": [
                    "Supplier Rating is the actual DocType and is treated as supporting evidence until the authoritative Monitor and Review source is confirmed. Provider Rating is only the translated frontend display label."
                ]
            },
            {
                "id": "c321-continuation",
                "label": "Approved or conditionally approved continuation decisions",
                "source": "supplier_rating",
                "mode": "conditions",
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["type"], "op": "equals", "value": "Agent"},
                            {
                                "field": ["status", "workflow_state", "recommendation"],
                                "op": "in",
                                "values": [
                                    "Approved", "Approved with Conditions",
                                    "Approved for Continuation"
                                ]
                            }
                        ]
                    }
                ],
                "category": "supporting",
                "support_status": "partial",
                "limitations": [
                    "The controlled recommendation and final approval fields must be confirmed before this count is treated as an authorised continuation decision."
                ]
            },
            {
                "id": "c321-offboardings",
                "label": "Agent offboarding records",
                "source": "offboarding",
                "mode": "conditions",
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["document_type"], "op": "equals", "value": "Agent"}
                        ]
                    }
                ],
                "category": "supporting"
            },
            {
                "id": "c321-submitted-claims",
                "label": "Submitted agent claim forms",
                "source": "claim",
                "mode": "equals",
                "field": ["docstatus"],
                "value": 1,
                "category": "supporting"
            },
            {
                "id": "c321-claim-total",
                "label": "Submitted agent claim amount",
                "source": "claim",
                "mode": "sum",
                "fields": [["grand_total"]],
                "condition_groups": [
                    {
                        "logic": "all",
                        "required": True,
                        "conditions": [
                            {"field": ["docstatus"], "op": "equals", "value": 1}
                        ]
                    }
                ],
                "unit": "SGD",
                "category": "supporting"
            },
            {
                "id": "c321-linked-applicants",
                "label": "Applicants linked to agents",
                "source": "applicant",
                "mode": "truthy",
                "field": ["custom_agent", "agent", "recruitment_agent"],
                "category": "supporting"
            },
            {
                "id": "c321-known-live-exceptions",
                "label": "Known live agent exception records",
                "mode": "derived_sum",
                "refs": [
                    "c321-under-review", "c321-suspended-terminated",
                    "c321-expiring-90"
                ],
                "category": "management",
                "support_status": "partial",
                "limitations": [
                    "The sum is not a unique-agent count and may contain the same agent more than once.",
                    "Complaints, breaches, training failures, missed targets and overdue corrective actions are excluded unless their approved sources are added."
                ],
                "requirement_basis": "Agent risk, continuation and timely action",
                "decision_use": "Prioritise known live exceptions while separately addressing unavailable evidence sources.",
                "is_exception": True
            },
            unsupported_metric(
                "c321-training-current",
                "Agent training and critical-update completion",
                "The Agent Training and Review Log child-table definitions, LMS completion relationship and update-assignment rules were not supplied.",
                "requires_new_source",
                "Continual training and timely critical-information updates",
                "Require retraining or confirm agent readiness."
            ),
            unsupported_metric(
                "c321-service-obligations",
                "Agent service-delivery and communication obligations",
                "Agent Annual Report, regular check-in and agent-linked Material Vetting relationships are required to assess service delivery and promotional-material approval.",
                "requires_new_source",
                "Service delivery, reporting, communication and promotional-material approval",
                "Correct incomplete reporting, communication or advertising controls."
            ),
            unsupported_metric(
                "c321-target-progress",
                "Recruitment and marketing-plan target progress",
                "A confirmed contractual target, performance period and authoritative enrolment outcome linked to each Agent are required.",
                "requires_relationship",
                "Service Performance Indicators and recruitment targets",
                "Intervene, revise the plan, adjust commission or support the renewal decision."
            ),
            unsupported_metric(
                "c321-evaluation-compliance",
                "Annual evaluation completion and performance result",
                "The due Agent population, authoritative Monitor and Review record, approved nine criteria, weighting version, evidence and final approval relationship are required.",
                "requires_relationship",
                "Annual evaluation before contract renewal",
                "Complete overdue evaluations and determine the supported performance result."
            ),
            unsupported_metric(
                "c321-agent-risk-actions",
                "Complaints, breaches, weak performance and corrective actions",
                "Agent-linked complaint, breach, finding, corrective-action, due-date and effectiveness records are required. The known live exception count is provided separately as a partial proxy.",
                "requires_new_source",
                "Timely action for contractual, Code of Conduct and performance failures",
                "Correct, suspend, non-renew or terminate based on verified risk evidence."
            ),
            unsupported_metric(
                "c321-renewal-decision-traceability",
                "Renewal and continuation decision traceability",
                "Each expiring current contract must be linked to its evaluation, target outcome, compliance result, recommendation, authorised approval and decision date.",
                "requires_relationship",
                "Supported renewal, continuation, commission and non-renewal decisions",
                "Approve or reject the contract decision before expiry."
            ),
            unsupported_metric(
                "c321-attribution-claim-validation",
                "Appointed-agent student attribution and commission validation",
                "Student registration must be checked against Agent appointment and contract validity on the registration date, and each claim must be reconciled to eligible enrolment, payment and approved commission terms.",
                "requires_relationship",
                "Appointed-agent enrolment traceability and commission processing",
                "Correct invalid attribution and approve or reject claims."
            ),
            unsupported_metric(
                "c321-offboarding-completeness",
                "Offboarding, access revocation and public-status update completeness",
                "A complete offboarding checklist linked to the contract end date, access revocation, document return, Agent status and website update is required.",
                "requires_relationship",
                "Recruitment Agent offboarding and exit security",
                "Close or escalate incomplete exit controls."
            ),
            unsupported_metric(
                "c321-system-review-effectiveness",
                "Agent-management system review effectiveness",
                "A requirement-scoped APSR review linked to resulting Quality Actions and effectiveness verification is required.",
                "requires_relationship",
                "Review of agent management and evaluation for continual improvement",
                "Retain or improve the management system after reviewing verified outcomes."
            )
        ]
    }
}

QUESTION_REGISTRY = {
    "overview": [
        {
            "id": "O-01",
            "question": "Which Criterion 3 agents or controls require management attention now?",
            "metric_id": "ov-known-attention-total",
            "requirement_basis": "Criterion 3 management attention queue",
            "decision_use": "Prioritise immediate agent review, continuation and contract-expiry follow-up."
        },
        {
            "id": "O-02",
            "question": "What proportion of Criterion 3 requirements has current live evidence, document-only evidence or no usable evidence?",
            "metric_id": "ov-requirement-evidence-coverage",
            "requirement_basis": "Criterion 3 audit readiness",
            "decision_use": "Determine and close requirement-level evidence gaps."
        }
    ],
    "3.1.1": [
        {
            "id": "S-01",
            "question": "Did every agent entering formal selection have a completed application and documented identification source or strategic need?",
            "metric_id": "c311-identification-completeness-proxy",
            "requirement_basis": "RA identification and screening process",
            "decision_use": "Proceed with or stop formal screening based on traceable entry evidence."
        },
        {
            "id": "S-02",
            "question": "Did every shortlisted agent complete all approved selection criteria, supporting notes, referee assessment and the minimum passing score before approval?",
            "metric_id": "c311-selection-completion-proxy",
            "requirement_basis": "RA evaluation and selection criteria",
            "decision_use": "Prevent approval where selection evidence is incomplete or below threshold."
        },
        {
            "id": "S-03",
            "question": "Did every shortlisted agent complete the required background check and final authorised approval before appointment?",
            "metric_id": "c311-background-approval-compliance",
            "requirement_basis": "Background check and final appointment decision",
            "decision_use": "Approve or reject appointment."
        },
        {
            "id": "S-04",
            "question": "Does every appointed or active agent have a signed, approved and currently valid Agent Contract and NDA?",
            "metric_id": "c311-valid-appointment-coverage",
            "requirement_basis": "Valid contract and NDA before appointment",
            "decision_use": "Confirm or withdraw authority to represent UCC."
        },
        {
            "id": "S-05",
            "question": "Did every appointed agent complete mandatory onboarding, training, Consent and Agreement before activation?",
            "metric_id": "c311-onboarding-before-activation",
            "requirement_basis": "Mandatory onboarding before active recruitment",
            "decision_use": "Activate or hold appointment."
        },
        {
            "id": "S-06",
            "question": "Is the published Agent List accurate and aligned with SMS for countries, current contract dates, status and effective date of non-representation?",
            "metric_id": "c311-agent-list-accuracy",
            "requirement_basis": "GD4 Agent List publication and SSOT control",
            "decision_use": "Correct public-list omissions and mismatches."
        },
        {
            "id": "S-07",
            "question": "Was the selection and appointment process reviewed through APSR, and were resulting actions implemented and verified as effective?",
            "metric_id": "c311-process-review-effectiveness",
            "requirement_basis": "Review of selection and appointment for continual improvement",
            "decision_use": "Improve or retain the selection system."
        }
    ],
    "3.2.1": [
        {
            "id": "M-01",
            "question": "Have all active agents completed required onboarding, annual training and critical course or policy updates?",
            "metric_id": "c321-training-current",
            "requirement_basis": "Continual training and timely critical-information updates",
            "decision_use": "Require retraining or confirm readiness."
        },
        {
            "id": "M-02",
            "question": "Are agents meeting service-delivery and communication obligations, including Annual Reports, regular updates and approved promotional materials?",
            "metric_id": "c321-service-obligations",
            "requirement_basis": "Service delivery, reporting, communication and promotional-material approval",
            "decision_use": "Correct service or advertising non-compliance."
        },
        {
            "id": "M-03",
            "question": "Which agents are on track, below target or cannot be assessed against their agreed recruitment and marketing plans?",
            "metric_id": "c321-target-progress",
            "requirement_basis": "Service Performance Indicators and recruitment targets",
            "decision_use": "Intervene, revise the plan or support the renewal decision."
        },
        {
            "id": "M-04",
            "question": "Were all agents due for evaluation assessed on time using the approved criteria, weighting version, evidence and minimum passing score?",
            "metric_id": "c321-evaluation-compliance",
            "requirement_basis": "Annual evaluation before contract renewal",
            "decision_use": "Complete overdue evaluations and determine the supported performance result."
        },
        {
            "id": "M-05",
            "question": "Which agents have complaints, breaches, compliance failures or weak performance requiring corrective action, suspension, non-renewal or termination?",
            "metric_id": "c321-agent-risk-actions",
            "requirement_basis": "Timely action for contractual, Code of Conduct and performance failures",
            "decision_use": "Determine risk treatment."
        },
        {
            "id": "M-06",
            "question": "Are renewal, continuation, commission-adjustment and non-renewal decisions completed before expiry and supported by evaluation, target and compliance evidence?",
            "metric_id": "c321-renewal-decision-traceability",
            "requirement_basis": "Supported renewal, continuation, commission and non-renewal decisions",
            "decision_use": "Approve or reject the contract decision before expiry."
        },
        {
            "id": "M-07",
            "question": "Do renewal contracts comply with the June and December checkpoint rules and the maximum eighteen-month duration?",
            "metric_id": "c321-renewal-rule-proxy",
            "requirement_basis": "June and December renewal checkpoints and maximum eighteen-month duration",
            "decision_use": "Approve or correct renewal periods."
        },
        {
            "id": "M-08",
            "question": "Are students attributed only to appointed agents, and are commission claims supported by eligible enrolment and payment records?",
            "metric_id": "c321-attribution-claim-validation",
            "requirement_basis": "Appointed-agent enrolment traceability and commission processing",
            "decision_use": "Approve or reject attribution and claims."
        },
        {
            "id": "M-09",
            "question": "Are agent offboarding, access revocation, document return, status update and website update completed within the required timeframe?",
            "metric_id": "c321-offboarding-completeness",
            "requirement_basis": "Recruitment Agent offboarding and exit security",
            "decision_use": "Close or escalate incomplete offboarding."
        },
        {
            "id": "M-10",
            "question": "Was the agent-management and evaluation system reviewed through APSR, and were improvement actions verified as effective?",
            "metric_id": "c321-system-review-effectiveness",
            "requirement_basis": "Review of agent management and evaluation for continual improvement",
            "decision_use": "Improve or retain the management system."
        }
    ]
}

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


def clone_dict(source):
    output = {}
    for key in source or {}:
        output[key] = source.get(key)
    return output


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
            return {
                "key": alias,
                "doctype": doctype,
                "candidates": candidates,
                "status": "available",
                "sample_count": len(rows),
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
                    "sample_count": 0,
                    "message": message,
                    "probe": "frappe.get_list",
                    "fallback_used": False,
                    "resolution_attempts": attempts
                }

    return {
        "key": alias,
        "doctype": None,
        "candidates": candidates,
        "status": "unavailable",
        "sample_count": 0,
        "message": "No approved candidate DocType could be resolved. Review the candidate-level errors.",
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
    for fieldname in fields or []:
        if fieldname not in output and field_exists(meta, fieldname):
            output.append(fieldname)
    if "name" not in output:
        output.insert(0, "name")
    return output


row_cache = {}


def fetch_rows(source_alias, source, requested_fields=None):
    doctype = source.get("doctype")
    if source.get("status") != "available" or not doctype:
        return []

    fields_to_fetch = safe_fields(doctype, ["name"] + (requested_fields or []))
    cache_key = source_alias + "|" + ",".join(fields_to_fetch)
    if row_cache.get(cache_key) is not None:
        return row_cache.get(cache_key)

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
        row_cache[cache_key] = rows
        source["truncated"] = truncated
        source["count"] = len(rows)
        source.pop("fetch_error", None)
        source.pop("fetch_status", None)
        return rows
    except Exception as error:
        row_cache[cache_key] = []
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
    if op == "contains_any":
        text = lower_text(value)
        for item in values or []:
            if lower_text(item) in text:
                return True
        return False
    if op == "not_contains_any":
        text = lower_text(value)
        for item in values or []:
            if lower_text(item) in text:
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
    if op == "date_next_days":
        if not value:
            return False
        try:
            date_value = frappe.utils.getdate(value)
            today_value = frappe.utils.getdate(frappe.utils.today())
            end_date = frappe.utils.getdate(
                frappe.utils.add_days(today_value, int(days or 0))
            )
            return date_value >= today_value and date_value <= end_date
        except Exception:
            return False
    if op == "date_before_today":
        if not value:
            return False
        try:
            return frappe.utils.getdate(value) < frappe.utils.getdate(frappe.utils.today())
        except Exception:
            return False
    if op == "date_on_or_before_today":
        if not value:
            return False
        try:
            return frappe.utils.getdate(value) <= frappe.utils.getdate(frappe.utils.today())
        except Exception:
            return False
    if op == "date_on_or_after_today":
        if not value:
            return False
        try:
            return frappe.utils.getdate(value) >= frappe.utils.getdate(frappe.utils.today())
        except Exception:
            return False
    return False


def resolve_metric_fields(metric, doctype):
    output = {
        "primary_fields": [],
        "value_fields": [],
        "required_fields": [],
        "condition_groups": [],
        "missing": []
    }

    if metric.get("field"):
        fieldname = resolve_field(doctype, metric.get("field"))
        if fieldname:
            output["primary_fields"].append(fieldname)
        else:
            output["missing"].append(metric.get("field"))

    for candidates in metric.get("fields") or []:
        fieldname = resolve_field(doctype, candidates)
        if fieldname:
            output["value_fields"].append(fieldname)
        else:
            output["missing"].append(candidates)

    for candidates in metric.get("required_fields") or []:
        fieldname = resolve_field(doctype, candidates)
        if fieldname:
            output["required_fields"].append(fieldname)
        else:
            output["missing"].append(candidates)

    condition_groups = metric.get("condition_groups") or []
    if not condition_groups and metric.get("conditions"):
        condition_groups = [{
            "logic": "all",
            "required": True,
            "conditions": metric.get("conditions")
        }]

    for group in condition_groups:
        resolved_group = {
            "logic": group.get("logic") or "all",
            "conditions": []
        }
        unresolved_required = []

        for condition in group.get("conditions") or []:
            fieldname = resolve_field(doctype, condition.get("field") or [])
            if fieldname:
                item = clone_dict(condition)
                item["resolved_field"] = fieldname
                resolved_group["conditions"].append(item)
            elif not condition.get("optional"):
                unresolved_required.append(condition.get("field") or [])

        if unresolved_required:
            output["missing"].extend(unresolved_required)

        if group.get("required") and not resolved_group["conditions"]:
            output["missing"].append({
                "condition_group": group.get("logic") or "all",
                "candidates": [
                    item.get("field") for item in group.get("conditions") or []
                ]
            })

        output["condition_groups"].append(resolved_group)

    return output


def group_matches(row, group):
    conditions = group.get("conditions") or []
    if not conditions:
        return True

    results = []
    for condition in conditions:
        results.append(compare(
            row,
            condition.get("resolved_field"),
            condition.get("op"),
            expected=condition.get("value"),
            values=condition.get("values"),
            days=condition.get("days")
        ))

    if group.get("logic") == "any":
        for result_value in results:
            if result_value:
                return True
        return False

    for result_value in results:
        if not result_value:
            return False
    return True


def row_matches(row, metric, resolved):
    for fieldname in resolved.get("required_fields") or []:
        if not is_truthy(row.get(fieldname)):
            return False

    for group in resolved.get("condition_groups") or []:
        if not group_matches(row, group):
            return False

    mode = metric.get("mode")
    primary_fields = resolved.get("primary_fields") or []

    if mode == "renewal_rule_compliant":
        required_fields = resolved.get("required_fields") or []
        if len(required_fields) < 2:
            return False
        try:
            start_date = frappe.utils.getdate(row.get(required_fields[0]))
            end_date = frappe.utils.getdate(row.get(required_fields[1]))
            maximum_end_date = frappe.utils.getdate(frappe.utils.add_months(start_date, 18))
            return end_date <= maximum_end_date and end_date.month in [6, 12]
        except Exception:
            return False

    if mode in ["all", "all_required", "conditions", "average_fields", "sum"]:
        return True

    if mode in [
        "truthy", "falsy", "equals", "not_equals", "in", "not_in",
        "contains", "contains_any", "not_contains_any", "date_next_days",
        "date_before_today", "date_on_or_before_today", "date_on_or_after_today",
        "gt", "gte", "lt", "lte"
    ]:
        if not primary_fields:
            return False
        return compare(
            row,
            primary_fields[0],
            mode,
            expected=metric.get("value"),
            values=metric.get("values"),
            days=metric.get("days")
        )

    return False


def metric_output_base(metric):
    return {
        "id": metric.get("id"),
        "label": metric.get("label"),
        "category": metric.get("category") or "supporting",
        "support_status": metric.get("support_status") or "live",
        "requirement_basis": metric.get("requirement_basis"),
        "decision_use": metric.get("decision_use"),
        "limitations": metric.get("limitations") or [],
        "is_exception": bool(metric.get("is_exception"))
    }


def evaluate_base_metric(metric, include_rows=False):
    output = metric_output_base(metric)

    if metric.get("mode") == "unsupported":
        output.update({
            "source": metric.get("source"),
            "doctype": None,
            "value": None,
            "unit": metric.get("unit") or "records",
            "record_count": 0,
            "status": "unsupported",
            "message": metric.get("message"),
            "rows": [],
            "total": 0
        })
        return output

    source_alias = metric.get("source")
    source = resolved_sources.get(source_alias) or {}
    output["source"] = source_alias
    output["doctype"] = source.get("doctype")

    if source.get("status") != "available":
        output.update({
            "value": None,
            "unit": metric.get("unit") or "records",
            "record_count": 0,
            "status": source.get("status") or "unavailable",
            "message": source.get("message") or "Required source is unavailable.",
            "rows": [],
            "total": 0
        })
        return output

    doctype = source.get("doctype")
    resolved = resolve_metric_fields(metric, doctype)
    missing = resolved.get("missing") or []

    if metric.get("mode") != "all" and missing:
        output.update({
            "value": None,
            "unit": metric.get("unit") or "records",
            "record_count": 0,
            "status": "unsupported_field",
            "message": "Required field or field group is not installed.",
            "missing_field_candidates": missing,
            "rows": [],
            "total": 0
        })
        return output

    requested = []
    for fieldname in resolved.get("primary_fields") or []:
        if fieldname not in requested:
            requested.append(fieldname)
    for fieldname in resolved.get("value_fields") or []:
        if fieldname not in requested:
            requested.append(fieldname)
    for fieldname in resolved.get("required_fields") or []:
        if fieldname not in requested:
            requested.append(fieldname)
    for group in resolved.get("condition_groups") or []:
        for condition in group.get("conditions") or []:
            fieldname = condition.get("resolved_field")
            if fieldname and fieldname not in requested:
                requested.append(fieldname)

    if include_rows:
        for fieldname in SAFE_FIELDS.get(source_alias) or []:
            if fieldname not in requested:
                requested.append(fieldname)

    rows = fetch_rows(source_alias, source, requested)
    matched = []
    for row in rows:
        if row_matches(row, metric, resolved):
            matched.append(row)

    mode = metric.get("mode")
    value = len(matched)
    record_count = len(matched)

    if mode == "average_fields":
        numbers = []
        for row in matched:
            for fieldname in resolved.get("value_fields") or []:
                number = to_number(row.get(fieldname))
                if number is not None:
                    numbers.append(number)
                    break
        value = round(sum(numbers) / len(numbers), 2) if numbers else 0
        record_count = len(numbers)

    if mode == "sum":
        total_value = 0
        for row in matched:
            for fieldname in resolved.get("value_fields") or []:
                number = to_number(row.get(fieldname))
                if number is not None:
                    total_value = total_value + number
                    break
        value = round(total_value, 2)

    output_rows = []
    if include_rows:
        start = (page - 1) * page_size
        end = start + page_size
        output_fields = safe_fields(
            doctype,
            SAFE_FIELDS.get(source_alias) or ["name"]
        )
        for row in matched[start:end]:
            item = {}
            for fieldname in output_fields:
                item[fieldname] = row.get(fieldname)
            output_rows.append(item)

    output.update({
        "value": value,
        "unit": metric.get("unit") or "records",
        "record_count": record_count,
        "status": "available",
        "resolved_fields": (
            (resolved.get("primary_fields") or []) +
            (resolved.get("value_fields") or []) +
            (resolved.get("required_fields") or [])
        ),
        "resolved_field_groups": {
            "primary": resolved.get("primary_fields") or [],
            "values": resolved.get("value_fields") or [],
            "required": resolved.get("required_fields") or []
        },
        "rows": output_rows,
        "total": len(matched),
        "truncated": len(rows) >= row_limit
    })
    return output


def find_metric(metrics_by_id, selected_id):
    return metrics_by_id.get(selected_id) or {}


def evaluate_derived_metric(metric, metrics_by_id):
    output = metric_output_base(metric)
    output["source"] = "derived"
    output["doctype"] = None

    if metric.get("mode") == "derived_sum":
        total_value = 0
        available_refs = 0
        unavailable_refs = []
        for ref_id in metric.get("refs") or []:
            selected = find_metric(metrics_by_id, ref_id)
            if selected.get("status") == "available":
                total_value = total_value + (to_number(selected.get("value")) or 0)
                available_refs = available_refs + 1
            else:
                unavailable_refs.append(ref_id)

        if available_refs == 0:
            output.update({
                "value": None,
                "unit": metric.get("unit") or "records",
                "record_count": 0,
                "status": "unavailable",
                "message": "None of the referenced live metrics is available.",
                "unavailable_refs": unavailable_refs,
                "rows": [],
                "total": 0
            })
            return output

        output.update({
            "value": round(total_value, 2),
            "unit": metric.get("unit") or "records",
            "record_count": available_refs,
            "status": "available",
            "message": "Some referenced metrics are unavailable." if unavailable_refs else "",
            "unavailable_refs": unavailable_refs,
            "rows": [],
            "total": round(total_value, 2)
        })
        return output

    if metric.get("mode") == "derived_percent":
        numerator = find_metric(metrics_by_id, metric.get("numerator_ref"))
        denominator = find_metric(metrics_by_id, metric.get("denominator_ref"))

        if numerator.get("status") != "available" or denominator.get("status") != "available":
            output.update({
                "value": None,
                "unit": "percent",
                "record_count": 0,
                "status": "unavailable",
                "message": "The numerator or denominator metric is unavailable.",
                "rows": [],
                "total": 0
            })
            return output

        denominator_value = to_number(denominator.get("value"))
        numerator_value = to_number(numerator.get("value"))
        if denominator_value in [None, 0]:
            output.update({
                "value": None,
                "unit": "percent",
                "record_count": 0,
                "status": "not_applicable",
                "message": "No denominator records match the current filters.",
                "rows": [],
                "total": 0
            })
            return output

        percentage = round((numerator_value or 0) * 100.0 / denominator_value, 2)
        output.update({
            "value": percentage,
            "unit": "percent",
            "record_count": int(denominator_value),
            "numerator": numerator_value or 0,
            "denominator": denominator_value,
            "status": "available",
            "rows": [],
            "total": denominator_value
        })
        return output

    output.update({
        "value": None,
        "unit": metric.get("unit") or "records",
        "record_count": 0,
        "status": "unsupported",
        "message": "Unsupported derived metric mode.",
        "rows": [],
        "total": 0
    })
    return output


if subcriterion not in CONFIG:
    frappe.throw("Unsupported Criterion 3 subcriterion.")

resolved_sources = {}
for alias in CONFIG[subcriterion].get("sources") or []:
    resolved_sources[alias] = resolve_source(alias)

metrics = []
metrics_by_id = {}

for configured_metric in CONFIG[subcriterion].get("metrics") or []:
    if configured_metric.get("mode") not in ["derived_sum", "derived_percent"]:
        evaluated = evaluate_base_metric(configured_metric, False)
        metrics.append(evaluated)
        metrics_by_id[evaluated.get("id")] = evaluated

for configured_metric in CONFIG[subcriterion].get("metrics") or []:
    if configured_metric.get("mode") in ["derived_sum", "derived_percent"]:
        evaluated = evaluate_derived_metric(configured_metric, metrics_by_id)
        metrics.append(evaluated)
        metrics_by_id[evaluated.get("id")] = evaluated


def format_limitations(limitations):
    values = []
    for item in limitations or []:
        text = clean_text(item)
        if text:
            values.append(text)
    return " ".join(values)


def answer_for_metric(selected_metric):
    if not selected_metric:
        return {
            "answer": "Unavailable: the linked metric is not configured.",
            "status": "unavailable",
            "confidence": "Unavailable"
        }

    if selected_metric.get("status") == "available":
        unit = selected_metric.get("unit") or "records"
        value = selected_metric.get("value")
        record_count = selected_metric.get("record_count") or 0

        if unit == "rating":
            answer = (
                str(value)
                + " is the live average from "
                + str(record_count)
                + " matching numeric record(s)."
            )
        elif unit == "percent":
            answer = (
                str(value)
                + "% is the available calculation based on "
                + str(record_count)
                + " denominator record(s)."
            )
        elif unit == "SGD":
            answer = "SGD " + str(value) + " matches the current filters."
        else:
            answer = str(value or 0) + " record(s) match the current filters."

        support_status = selected_metric.get("support_status") or "live"
        limitations_text = format_limitations(selected_metric.get("limitations"))
        if support_status == "partial":
            answer = answer + " Partial evidence only."
            if limitations_text:
                answer = answer + " " + limitations_text
            confidence = "Partial"
        else:
            confidence = "Live"

        return {
            "answer": answer,
            "status": "available",
            "confidence": confidence
        }

    return {
        "answer": "Unavailable: " + clean_text(
            selected_metric.get("message")
            or selected_metric.get("status")
            or "required source, field or relationship is unavailable"
        ),
        "status": selected_metric.get("status") or "unavailable",
        "confidence": "Unavailable"
    }


questions = []
for question in QUESTION_REGISTRY.get(subcriterion) or []:
    selected_metric = metrics_by_id.get(question.get("metric_id")) or {}
    answer_result = answer_for_metric(selected_metric)
    questions.append({
        "id": question.get("id"),
        "criterion": subcriterion,
        "question": question.get("question"),
        "answer": answer_result.get("answer"),
        "metric_id": question.get("metric_id"),
        "status": answer_result.get("status"),
        "confidence": answer_result.get("confidence"),
        "support_status": selected_metric.get("support_status") or "unavailable",
        "requirement_basis": question.get("requirement_basis") or selected_metric.get("requirement_basis"),
        "decision_use": question.get("decision_use") or selected_metric.get("decision_use"),
        "limitations": selected_metric.get("limitations") or [],
        "doctype": selected_metric.get("doctype")
    })

sources = []
for alias in CONFIG[subcriterion].get("sources") or []:
    sources.append(resolved_sources.get(alias))

management_metrics = []
supporting_metrics = []
exceptions = []
evidence_gaps = []
data_quality = []

for metric in metrics:
    if metric.get("category") == "management":
        management_metrics.append(metric)
    else:
        supporting_metrics.append(metric)

    if metric.get("is_exception"):
        exceptions.append(metric)

    if metric.get("category") == "management" and metric.get("status") != "available":
        evidence_gaps.append({
            "criterion": subcriterion,
            "metric_id": metric.get("id"),
            "requirement_basis": metric.get("requirement_basis"),
            "support_status": metric.get("support_status"),
            "status": metric.get("status"),
            "detail": metric.get("message") or "Required evidence is unavailable."
        })

for source in sources:
    if source and source.get("status") != "available":
        data_quality.append({
            "criterion": subcriterion,
            "check": "Source availability",
            "source": source.get("doctype") or " / ".join(source.get("candidates") or []),
            "status": source.get("status"),
            "detail": source.get("message") or "Source is unavailable."
        })

for metric in metrics:
    if metric.get("status") in ["unsupported_field", "permission_denied", "unavailable"]:
        data_quality.append({
            "criterion": subcriterion,
            "check": metric.get("label"),
            "source": metric.get("doctype") or metric.get("source"),
            "status": metric.get("status"),
            "detail": metric.get("message") or "Metric is unavailable."
        })

available_sources = 0
for source in sources:
    if source and source.get("status") == "available":
        available_sources = available_sources + 1

available_metrics = 0
partial_metrics = 0
unavailable_metrics = 0
for metric in metrics:
    if metric.get("status") == "available":
        available_metrics = available_metrics + 1
        if metric.get("support_status") == "partial":
            partial_metrics = partial_metrics + 1
    else:
        unavailable_metrics = unavailable_metrics + 1

available_questions = 0
partial_questions = 0
unavailable_questions = 0
for question in questions:
    if question.get("status") == "available":
        available_questions = available_questions + 1
        if question.get("confidence") == "Partial":
            partial_questions = partial_questions + 1
    else:
        unavailable_questions = unavailable_questions + 1

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
        "api_method": "ucc_analytics_criterion_3",
        "platform_version": "1.10.1",
        "catalogue_version": "2.0.1",
        "status": "revised_management_catalogue",
        "generated_at": frappe.utils.now(),
        "action": action,
        "subcriterion": subcriterion,
        "row_limit": row_limit,
        "management_question_count": len(questions)
    },
    "policy": POLICY_REGISTRY.get(subcriterion),
    "filters": filters,
    "sources": sources,
    "metrics": metrics,
    "management_metrics": management_metrics,
    "supporting_metrics": supporting_metrics,
    "questions": questions,
    "exceptions": exceptions,
    "evidence_gaps": evidence_gaps,
    "data_quality": data_quality,
    "source_summary": {
        "total": len(sources),
        "available": available_sources,
        "issues": len(sources) - available_sources
    },
    "metric_summary": {
        "total": len(metrics),
        "available": available_metrics,
        "partial": partial_metrics,
        "unavailable": unavailable_metrics
    },
    "question_summary": {
        "total": len(questions),
        "available": available_questions,
        "partial": partial_questions,
        "unavailable": unavailable_questions
    },
    "data": {
        "sources": sources,
        "metrics": metrics,
        "management_metrics": management_metrics,
        "supporting_metrics": supporting_metrics,
        "questions": questions,
        "exceptions": exceptions,
        "evidence_gaps": evidence_gaps,
        "data_quality": data_quality
    },
    "warnings": [
        "Criterion 3 separates agent selection, appointment, training, evaluation, performance, corrective action and continued-authorisation decisions.",
        "Raw Agent, contract, review, claim and applicant counts are supporting metrics and are not automatically treated as compliance conclusions.",
        "Partial proxy metrics are labelled and retain their stated limitations.",
        "Missing background checks, training logs, authoritative evaluation relationships, complaint records, website-list reconciliation and effectiveness evidence are reported as unavailable rather than zero.",
        "The controlled procedures contain unresolved inconsistencies concerning criterion count, weighting, score calculation, approval authority, activation timing and authoritative evaluation sources.",
        "IMPORTANT: Supplier Rating is the actual server-side DocType. Provider Rating is only the translated display label in the frontend and must never be used in frappe.get_meta or frappe.get_list.",
        "API compatibility note: resolved_fields is intentionally returned as a flat list for the current dashboard renderer; resolved_field_groups contains the structured detail."
    ]
}

result = standardise_response_contract(result, "Criterion 3", "ucc_analytics_criterion_3", action, subcriterion, row_limit)

if action == "policy_registry":
    result["registry"] = POLICY_REGISTRY

if action in ["question_registry", "question_catalogue"]:
    result["registry"] = QUESTION_REGISTRY
    result["catalogue"] = QUESTION_REGISTRY

if action == "requirement_registry":
    result["registry"] = result.get("requirements") or []

if action == "source_status":
    result["source_status"] = sources

if action == "drilldown":
    selected_config = None
    for configured_metric in CONFIG[subcriterion].get("metrics") or []:
        if configured_metric.get("id") == metric_id:
            selected_config = configured_metric
            break

    if not selected_config:
        frappe.throw("Unknown Criterion 3 metric.")

    if selected_config.get("mode") in ["derived_sum", "derived_percent"]:
        result["drilldown"] = metrics_by_id.get(metric_id)
    elif selected_config.get("mode") == "unsupported":
        result["drilldown"] = metrics_by_id.get(metric_id)
    else:
        result["drilldown"] = evaluate_base_metric(selected_config, True)

result = standardise_response_contract(result, "Criterion 3", "ucc_analytics_criterion_3", action, subcriterion, row_limit)

frappe.response["message"] = result
