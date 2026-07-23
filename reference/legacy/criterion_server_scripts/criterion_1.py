"""
UCC Intelligence Platform Server Script

Visible name:
    UCC Analytics - Criterion 1

Script type:
    API

API method:
    ucc_analytics_criterion_1

Purpose:
    Return permission-aware, decision-useful analytics for EduTrust Criterion 1.

Current status:
    Revised Criterion 1 question catalogue. Supported calculations remain live.
    Document-only and unsupported controls are reported explicitly and never guessed.

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
subcriterion = payload.get("subcriterion") or "1.1.1"
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
    frappe.throw("Unsupported Criterion 1 action.")

POLICY_REGISTRY = {
    "overview": {
        "title": "Criterion 1 Overview",
        "policy": "PPD-SGL-CG-1.1.1 / PPD-SGL-SQ-1.2.1",
        "version": "2.2 / 1.2"
    },
    "1.1.1": {
        "title": "Leadership and Corporate Governance",
        "policy": "PPD-SGL-CG-1.1.1",
        "version": "2.2"
    },
    "1.2.1": {
        "title": "Strategic Planning",
        "policy": "PPD-SGL-SQ-1.2.1",
        "version": "1.2"
    }
}

SOURCE_CANDIDATES = {
    "oversight": ["Oversight Framework"],
    "stakeholder_registry": ["Stakeholder Registry"],
    "stakeholder_engagement": ["Stakeholder Engagement Strategy"],
    "policy_control": ["Policies and Standards Type", "Quality Procedure"],
    "esg_strategy": ["ESG Strategy Insights"],
    "esg_tracker": ["ESG Impact Tracker"],
    "business_impact": ["Business Impact Analysis"],
    "risk_register": ["Risk Register and Mitigation Plans"],
    "quality_goal": ["Quality Goal"],
    "staff_goal": ["Goal"],
    "appraisal": ["Appraisal"],
    "management_review": ["Management Review"],
    "quality_action": ["Quality Action"]
}

SAFE_FIELDS = {
    "oversight": [
        "name", "title", "subject", "status", "review_status", "framework_type",
        "owner", "assigned_to", "review_date", "next_review_date", "approval_date", "modified"
    ],
    "stakeholder_registry": [
        "name", "stakeholder_name", "stakeholder_type", "category", "status",
        "department", "owner", "modified"
    ],
    "stakeholder_engagement": [
        "name", "stakeholder", "stakeholder_group", "engagement_type",
        "communication_channel", "frequency", "status", "engagement_date",
        "next_engagement_date", "modified"
    ],
    "policy_control": [
        "name", "title", "policy_name", "document_code", "version", "status",
        "effective_date", "review_date", "next_review_date", "approval_date",
        "owner", "department", "modified"
    ],
    "esg_strategy": [
        "name", "title", "status", "year", "objective", "target", "actual",
        "progress", "owner", "modified"
    ],
    "esg_tracker": [
        "name", "initiative", "status", "year", "target", "actual", "progress",
        "owner", "modified"
    ],
    "business_impact": [
        "name", "title", "department", "status", "risk_level", "review_date",
        "next_review_date", "owner", "modified"
    ],
    "risk_register": [
        "name", "risk", "risk_title", "status", "risk_level", "likelihood",
        "severity", "risk_score", "residual_risk", "owner", "target_date", "modified"
    ],
    "quality_goal": [
        "name", "goal", "frequency", "procedure", "date", "weekday", "modified"
    ],
    "staff_goal": [
        "name", "goal_name", "is_group", "parent_goal", "progress", "status",
        "custom_type", "employee", "employee_name", "company", "user", "start_date",
        "end_date", "custom_change_department", "custom_department", "appraisal_cycle",
        "kra", "description", "modified"
    ],
    "appraisal": [
        "name", "employee", "employee_name", "status", "start_date", "end_date",
        "appraisal_cycle", "final_score", "modified"
    ],
    "management_review": [
        "name", "review_date", "review_period", "review_type", "review_status",
        "chairperson", "next_review_date", "modified"
    ],
    "quality_action": [
        "name", "goal", "review", "procedure", "status", "custom_status_updates",
        "date", "custom_proposed_date", "custom_completed_date", "custom_priority_score",
        "modified"
    ]
}

FILTER_FIELD_CANDIDATES = {
    "status": ["status", "review_status", "custom_status_updates"],
    "year": ["year", "monitoring_year", "review_year", "academic_year"],
    "review_year": ["year", "monitoring_year", "review_year"],
    "department": ["department", "custom_department", "department_name"],
    "owner": ["owner", "assigned_to", "responsible"]
}

HIGH_RISK_VALUES = ["High", "Critical", "Very High"]
CLOSED_VALUES = ["Completed", "Closed", "Cancelled", "Inactive", "Archived"]

CONFIG = {
    "overview": {
        "sources": [
            "oversight", "stakeholder_registry", "stakeholder_engagement", "policy_control",
            "esg_strategy", "esg_tracker", "business_impact", "risk_register",
            "quality_goal", "staff_goal", "appraisal", "management_review", "quality_action"
        ],
        "metrics": [
            {
                "id": "o-overdue-policy-review",
                "label": "Policies overdue for review",
                "source": "policy_control",
                "mode": "conditions",
                "conditions": [
                    {"field": ["next_review_date"], "op": "date_before_today"},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {
                "id": "o-overdue-oversight-review",
                "label": "Oversight controls overdue for review",
                "source": "oversight",
                "mode": "conditions",
                "conditions": [
                    {"field": ["next_review_date"], "op": "date_before_today"},
                    {"field": ["status", "review_status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {
                "id": "o-open-high-risks",
                "label": "Open high or critical risks",
                "source": "risk_register",
                "mode": "conditions",
                "conditions": [
                    {"field": ["risk_level"], "op": "in", "values": HIGH_RISK_VALUES},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {
                "id": "o-overdue-high-risks",
                "label": "Overdue open high or critical risks",
                "source": "risk_register",
                "mode": "conditions",
                "conditions": [
                    {"field": ["risk_level"], "op": "in", "values": HIGH_RISK_VALUES},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES},
                    {"field": ["target_date"], "op": "date_before_today"}
                ]
            },
            {
                "id": "o-overdue-actions",
                "label": "Overdue Quality Actions",
                "source": "quality_action",
                "mode": "conditions",
                "conditions": [
                    {"field": ["custom_proposed_date", "target_date"], "op": "date_before_today"},
                    {"field": ["custom_status_updates", "status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {
                "id": "o-overdue-staff-goals",
                "label": "Staff Goals past end date and not closed",
                "source": "staff_goal",
                "mode": "conditions",
                "conditions": [
                    {"field": ["end_date"], "op": "date_before_today"},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {
                "id": "o-esg-off-track",
                "label": "ESG initiatives below target",
                "source": "esg_tracker",
                "mode": "field_compare",
                "fields": [["actual"], ["target"]],
                "operator": "lt"
            }
        ]
    },
    "1.1.1": {
        "sources": [
            "oversight", "stakeholder_registry", "stakeholder_engagement", "policy_control",
            "esg_strategy", "esg_tracker", "business_impact", "risk_register",
            "management_review", "quality_action"
        ],
        "metrics": [
            {"id": "c111-oversight", "label": "Oversight records in scope", "source": "oversight", "mode": "all"},
            {
                "id": "c111-active-oversight",
                "label": "Active or approved oversight records",
                "source": "oversight",
                "mode": "in",
                "field": ["status", "review_status"],
                "values": ["Active", "Approved", "Completed"]
            },
            {"id": "c111-stakeholders", "label": "Stakeholders in the registry", "source": "stakeholder_registry", "mode": "all"},
            {"id": "c111-engagements", "label": "Stakeholder engagement records", "source": "stakeholder_engagement", "mode": "all"},
            {
                "id": "c111-overdue-engagements",
                "label": "Stakeholder engagements overdue",
                "source": "stakeholder_engagement",
                "mode": "conditions",
                "conditions": [
                    {"field": ["next_engagement_date"], "op": "date_before_today"},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {"id": "c111-policies", "label": "Controlled policies and standards", "source": "policy_control", "mode": "all"},
            {
                "id": "c111-overdue-policy-review",
                "label": "Policies overdue for review",
                "source": "policy_control",
                "mode": "conditions",
                "conditions": [
                    {"field": ["next_review_date"], "op": "date_before_today"},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {
                "id": "c111-overdue-oversight-review",
                "label": "Oversight controls overdue for review",
                "source": "oversight",
                "mode": "conditions",
                "conditions": [
                    {"field": ["next_review_date"], "op": "date_before_today"},
                    {"field": ["status", "review_status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {"id": "c111-esg-strategies", "label": "ESG strategy records", "source": "esg_strategy", "mode": "all"},
            {"id": "c111-esg-initiatives", "label": "ESG initiatives tracked", "source": "esg_tracker", "mode": "all"},
            {
                "id": "c111-esg-off-track",
                "label": "ESG initiatives below target",
                "source": "esg_tracker",
                "mode": "field_compare",
                "fields": [["actual"], ["target"]],
                "operator": "lt"
            },
            {"id": "c111-business-impact", "label": "Business impact assessments", "source": "business_impact", "mode": "all"},
            {
                "id": "c111-overdue-business-impact-review",
                "label": "Business impact assessments overdue for review",
                "source": "business_impact",
                "mode": "conditions",
                "conditions": [
                    {"field": ["next_review_date"], "op": "date_before_today"},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {"id": "c111-risks", "label": "Risks in scope", "source": "risk_register", "mode": "all"},
            {
                "id": "c111-high-risks",
                "label": "Open high or critical risks",
                "source": "risk_register",
                "mode": "conditions",
                "conditions": [
                    {"field": ["risk_level"], "op": "in", "values": HIGH_RISK_VALUES},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {
                "id": "c111-overdue-high-risks",
                "label": "Overdue open high or critical risks",
                "source": "risk_register",
                "mode": "conditions",
                "conditions": [
                    {"field": ["risk_level"], "op": "in", "values": HIGH_RISK_VALUES},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES},
                    {"field": ["target_date"], "op": "date_before_today"}
                ]
            },
            {"id": "c111-management-reviews", "label": "Management Reviews", "source": "management_review", "mode": "all"},
            {
                "id": "c111-completed-management-reviews",
                "label": "Completed Management Reviews",
                "source": "management_review",
                "mode": "equals",
                "field": ["review_status", "status"],
                "value": "Completed"
            },
            {"id": "c111-quality-actions", "label": "Quality Actions", "source": "quality_action", "mode": "all"},
            {
                "id": "c111-overdue-quality-actions",
                "label": "Overdue Quality Actions",
                "source": "quality_action",
                "mode": "conditions",
                "conditions": [
                    {"field": ["custom_proposed_date", "target_date"], "op": "date_before_today"},
                    {"field": ["custom_status_updates", "status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {
                "id": "c111-vmvq-review",
                "label": "Annual VMVQ review and approval evidence",
                "source": "management_review",
                "mode": "unsupported",
                "message": "The current Management Review fields do not identify the VMVQ agenda item, review inputs, approval decision or resulting revision."
            },
            {
                "id": "c111-stakeholder-coverage",
                "label": "Required stakeholder group and feedback-decision coverage",
                "source": "stakeholder_registry",
                "mode": "unsupported",
                "message": "The required stakeholder-group denominator, influence and interest analysis, feedback decision and action links were not supplied."
            },
            {
                "id": "c111-committee-composition",
                "label": "Governance committee constitution and administrative readiness",
                "source": "oversight",
                "mode": "unsupported",
                "message": "Committee member child-table, appointment, induction, training, conflict declaration and evaluation definitions were not supplied."
            },
            {
                "id": "c111-financial-monitoring",
                "label": "Required financial review completion and control exceptions",
                "source": "oversight",
                "mode": "unsupported",
                "message": "Master Budget, financial statement, audit report and fee-record evidence sources are not mapped in the current Criterion 1 API."
            },
            {
                "id": "c111-governance-apsr-effectiveness",
                "label": "Governance APSR review and action effectiveness",
                "source": "management_review",
                "mode": "unsupported",
                "message": "The current fields do not identify Criterion 1.1.1 APSR elements, linked findings, review decisions or effectiveness verification."
            }
        ]
    },
    "1.2.1": {
        "sources": [
            "quality_goal", "staff_goal", "appraisal", "management_review",
            "quality_action", "risk_register", "business_impact"
        ],
        "metrics": [
            {"id": "c121-quality-goals", "label": "Quality Goals in scope", "source": "quality_goal", "mode": "all"},
            {
                "id": "c121-goals-defined",
                "label": "Quality Goals with a populated goal field",
                "source": "quality_goal",
                "mode": "truthy",
                "field": ["goal"]
            },
            {"id": "c121-staff-goals", "label": "Staff Goals in scope", "source": "staff_goal", "mode": "all"},
            {
                "id": "c121-staff-goals-active-or-completed",
                "label": "Staff Goals in progress, completed or closed",
                "source": "staff_goal",
                "mode": "in",
                "field": ["status"],
                "values": ["In Progress", "Completed", "Closed"]
            },
            {
                "id": "c121-overdue-staff-goals",
                "label": "Staff Goals past end date and not closed",
                "source": "staff_goal",
                "mode": "conditions",
                "conditions": [
                    {"field": ["end_date"], "op": "date_before_today"},
                    {"field": ["status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {"id": "c121-appraisals", "label": "Appraisal records", "source": "appraisal", "mode": "all"},
            {"id": "c121-management-reviews", "label": "Management Reviews", "source": "management_review", "mode": "all"},
            {
                "id": "c121-completed-reviews",
                "label": "Completed Management Reviews",
                "source": "management_review",
                "mode": "equals",
                "field": ["review_status", "status"],
                "value": "Completed"
            },
            {"id": "c121-quality-actions", "label": "Quality Actions", "source": "quality_action", "mode": "all"},
            {
                "id": "c121-overdue-actions",
                "label": "Overdue Quality Actions",
                "source": "quality_action",
                "mode": "conditions",
                "conditions": [
                    {"field": ["custom_proposed_date", "target_date"], "op": "date_before_today"},
                    {"field": ["custom_status_updates", "status"], "op": "not_in", "values": CLOSED_VALUES}
                ]
            },
            {"id": "c121-risks", "label": "Risks and opportunities in scope", "source": "risk_register", "mode": "all"},
            {"id": "c121-business-impact", "label": "Business impact assessments", "source": "business_impact", "mode": "all"},
            {
                "id": "c121-strategic-plan-approval",
                "label": "Current Principal-approved strategic plan completeness",
                "source": "management_review",
                "mode": "unsupported",
                "message": "No structured Strategic Plan source or fields for plan version, Principal decision, actions, owners, resources and implementation timeline were supplied."
            },
            {
                "id": "c121-cascade-alignment",
                "label": "Strategic cascade alignment",
                "source": "quality_goal",
                "mode": "unsupported",
                "message": "Long-term goal, KRA, KPI, departmental target and staff-goal relationship definitions were not supplied."
            },
            {
                "id": "c121-kpi-definition-completeness",
                "label": "KPI definition completeness",
                "source": "quality_goal",
                "mode": "unsupported",
                "message": "Approved baseline, target, actual, direction, tolerance, owner and measurement-method fields were not supplied."
            },
            {
                "id": "c121-kpi-achievement",
                "label": "KPI target achievement and variance",
                "source": "quality_goal",
                "mode": "unsupported",
                "message": "Approved target-versus-actual fields, direction rules and achievement thresholds were not supplied."
            },
            {
                "id": "c121-strategic-alignment",
                "label": "Initiative alignment with risk, continuity, budget and resources",
                "source": "risk_register",
                "mode": "unsupported",
                "message": "Strategic initiative links to risk, continuity, Master Budget and Resource Management Planning were not supplied."
            },
            {
                "id": "c121-departmental-plan-readiness",
                "label": "Departmental work-plan readiness and review",
                "source": "appraisal",
                "mode": "unsupported",
                "message": "The configured Appraisal fields do not expose departmental work-plan content, strategic links, resources, review decisions or biannual review dates."
            },
            {
                "id": "c121-strategic-review-effectiveness",
                "label": "Annual strategic APSR review and improvement effectiveness",
                "source": "management_review",
                "mode": "unsupported",
                "message": "The current fields do not identify strategic-planning APSR inputs, conclusions, plan revisions, benchmarking or effectiveness verification."
            }
        ]
    }
}

REQUIREMENT_REGISTRY = [
    {
        "id": "1.1.1.1",
        "subcriterion": "1.1.1",
        "title": "Set and review Vision, Mission and Values",
        "document_reference": "PPD-SGL-CG-1.1.1 Approach 1 and Appendix B",
        "source_keys": ["policy_control", "management_review"],
        "manual_gaps": ["VMVQ agenda item", "review inputs", "approval decision", "resulting revision"]
    },
    {
        "id": "1.1.1.2",
        "subcriterion": "1.1.1",
        "title": "Engage key stakeholders to support VMVQ",
        "document_reference": "PPD-SGL-CG-1.1.1 Approaches 2 and 3",
        "source_keys": ["stakeholder_registry", "stakeholder_engagement"],
        "manual_gaps": ["required stakeholder-group denominator", "feedback decision and action linkage"]
    },
    {
        "id": "1.1.1.3",
        "subcriterion": "1.1.1",
        "title": "Maintain governance controls, transparency, accountability and community responsibility",
        "document_reference": "PPD-SGL-CG-1.1.1 Approaches 4 to 7",
        "source_keys": ["oversight", "risk_register", "business_impact", "esg_strategy", "esg_tracker"],
        "manual_gaps": ["committee lifecycle", "ethical controls", "financial-control evidence", "committee decisions and minutes"]
    },
    {
        "id": "1.1.1.4",
        "subcriterion": "1.1.1",
        "title": "Monitor financial statements and financial record keeping",
        "document_reference": "PPD-SGL-CG-1.1.1 Approach 8 and Appendix B",
        "source_keys": [],
        "manual_gaps": ["Master Budget", "financial statements", "financial audit report", "fee-payment record evidence"]
    },
    {
        "id": "1.1.1.5",
        "subcriterion": "1.1.1",
        "title": "Review leadership and governance for continual improvement",
        "document_reference": "PPD-SGL-CG-1.1.1 Approach 9",
        "source_keys": ["management_review", "quality_action"],
        "manual_gaps": ["Criterion 1.1.1 APSR scope", "linked findings", "effectiveness verification"]
    },
    {
        "id": "1.2.1.1",
        "subcriterion": "1.2.1",
        "title": "Develop and implement strategies, KPIs and targets",
        "document_reference": "PPD-SGL-SQ-1.2.1 Approaches 1 to 4",
        "source_keys": ["quality_goal", "management_review"],
        "manual_gaps": ["structured Strategic Plan", "Principal approval", "KPI baseline and target fields"]
    },
    {
        "id": "1.2.1.2",
        "subcriterion": "1.2.1",
        "title": "Align strategy with risk, continuity, finance, budget and resources",
        "document_reference": "PPD-SGL-SQ-1.2.1 Approaches 5 to 9",
        "source_keys": ["risk_register", "business_impact"],
        "manual_gaps": ["Master Budget", "Resource Management Planning", "initiative-to-plan links"]
    },
    {
        "id": "1.2.1.3",
        "subcriterion": "1.2.1",
        "title": "Maintain departmental work plans aligned with strategy",
        "document_reference": "PPD-SGL-SQ-1.2.1 Approach 10 and Appendix G",
        "source_keys": ["staff_goal", "appraisal"],
        "manual_gaps": ["departmental work-plan content", "strategic cascade links", "resource requirements"]
    },
    {
        "id": "1.2.1.4",
        "subcriterion": "1.2.1",
        "title": "Review and revise departmental plans",
        "document_reference": "PPD-SGL-SQ-1.2.1 Approach 11 and Appendix G",
        "source_keys": ["appraisal", "management_review"],
        "manual_gaps": ["PDCA-APSR review evidence", "plan revision decision", "biannual review dates"]
    },
    {
        "id": "1.2.1.5",
        "subcriterion": "1.2.1",
        "title": "Identify and track strategic performance outcomes",
        "document_reference": "PPD-SGL-SQ-1.2.1 Approach 12",
        "source_keys": ["quality_goal"],
        "manual_gaps": ["baseline", "target", "actual", "measurement direction", "variance analysis", "benchmarking"]
    },
    {
        "id": "1.2.1.6",
        "subcriterion": "1.2.1",
        "title": "Review strategic planning for continual improvement",
        "document_reference": "PPD-SGL-SQ-1.2.1 Approach 13",
        "source_keys": ["management_review", "quality_action"],
        "manual_gaps": ["strategic APSR scope", "required review inputs", "approved plan revisions", "effectiveness verification"]
    }
]

QUESTION_REGISTRY = {
    "overview": [
        {
            "id": "O-01",
            "question": "Which Criterion 1 controls require management attention now?",
            "requirement_reference": "Criterion 1.1.1.5 and 1.2.1.6",
            "support_status": "Can be implemented with revised mapping",
            "answer_mode": "attention_summary",
            "metric_ids": [
                "o-overdue-policy-review", "o-overdue-oversight-review", "o-open-high-risks",
                "o-overdue-high-risks", "o-overdue-actions", "o-overdue-staff-goals", "o-esg-off-track"
            ],
            "limitations": "Exception categories are not summed because the same record may appear in more than one category. Strategic or governance scoping depends on fields not yet supplied."
        },
        {
            "id": "O-02",
            "question": "What proportion of Criterion 1 requirements has a readable live evidence source, partial evidence or no mapped live source?",
            "requirement_reference": "Criterion 1 evidence and audit traceability",
            "support_status": "Can be implemented now",
            "answer_mode": "evidence_coverage",
            "metric_ids": [],
            "limitations": "A readable source or existing record is not proof that the control is effective or current."
        }
    ],
    "1.1.1": [
        {
            "id": "G-01",
            "question": "Was VMVQ reviewed and approved for the current annual cycle, and did the review consider strategic alignment, stakeholder input and changes in context?",
            "requirement_reference": "1.1.1.1; PPD-SGL-CG-1.1.1 Approach 1 and Appendix B",
            "support_status": "Document evidence only",
            "answer_mode": "document_only",
            "metric_ids": ["c111-vmvq-review"],
            "limitations": "The current fields cannot verify the required agenda, inputs, approval or resulting revision."
        },
        {
            "id": "G-02",
            "question": "Are all required stakeholder groups identified, analysed and covered by a current engagement approach, and what feedback requires a management decision?",
            "requirement_reference": "1.1.1.2; PPD-SGL-CG-1.1.1 Approaches 2 and 3",
            "support_status": "Requires an additional field",
            "answer_mode": "stakeholder_summary",
            "metric_ids": ["c111-stakeholders", "c111-engagements", "c111-overdue-engagements", "c111-stakeholder-coverage"],
            "limitations": "Required-group coverage, influence and interest analysis, and feedback-to-decision linkage cannot be calculated from current fields."
        },
        {
            "id": "G-03",
            "question": "Are all required governance committees validly constituted and administratively current?",
            "requirement_reference": "1.1.1.3; PPD-SGL-CG-1.1.1 Approaches 5 and 6, Appendices C and D",
            "support_status": "Requires a new DocType or child-table query",
            "answer_mode": "unsupported",
            "metric_ids": ["c111-committee-composition"],
            "limitations": "Committee and appointment lifecycle structures are not available to this API."
        },
        {
            "id": "G-04",
            "question": "Which governance policies, oversight controls or regulatory obligations are due or overdue for review or approval?",
            "requirement_reference": "1.1.1.3 and 1.1.1.5",
            "support_status": "Can be implemented with revised mapping",
            "answer_mode": "governance_due",
            "metric_ids": ["c111-overdue-policy-review", "c111-overdue-oversight-review"],
            "limitations": "The calculation uses next review dates only. Approval and regulatory-obligation completeness require additional structured fields."
        },
        {
            "id": "G-05",
            "question": "Which high or critical governance risks, continuity gaps or mitigation actions remain open or overdue?",
            "requirement_reference": "1.1.1.3 and 1.1.1.5",
            "support_status": "Requires an additional field",
            "answer_mode": "risk_summary",
            "metric_ids": ["c111-high-risks", "c111-overdue-high-risks", "c111-overdue-business-impact-review"],
            "limitations": "The current Risk Register fields do not identify whether a risk is specifically governance-related. Continuity test results are not mapped."
        },
        {
            "id": "G-06",
            "question": "Were required financial reviews completed on schedule, and what financial-control or record-keeping issues require action?",
            "requirement_reference": "1.1.1.3 and 1.1.1.4",
            "support_status": "Requires a new DocType or child-table query",
            "answer_mode": "unsupported",
            "metric_ids": ["c111-financial-monitoring"],
            "limitations": "The required review frequency is internally inconsistent in the procedure and the financial evidence sources are not mapped."
        },
        {
            "id": "G-07",
            "question": "Are annual ESG and community plans complete, and which initiatives or targets are off track?",
            "requirement_reference": "1.1.1.3; PPD-SGL-CG-1.1.1 Approach 7 and Appendix B",
            "support_status": "Can be implemented with revised mapping",
            "answer_mode": "esg_summary",
            "metric_ids": ["c111-esg-strategies", "c111-esg-initiatives", "c111-esg-off-track"],
            "limitations": "Off-track means actual is numerically below target. The approved direction and annual plan completeness rule are not supplied."
        },
        {
            "id": "G-08",
            "question": "Was the leadership and corporate-governance system reviewed through APSR, and were resulting improvement actions implemented and verified as effective?",
            "requirement_reference": "1.1.1.5; PPD-SGL-CG-1.1.1 Approach 9",
            "support_status": "Requires an additional field",
            "answer_mode": "governance_review_summary",
            "metric_ids": ["c111-completed-management-reviews", "c111-overdue-quality-actions", "c111-governance-apsr-effectiveness"],
            "limitations": "Current records cannot prove that the review covered Criterion 1.1.1 APSR elements or that actions were verified as effective."
        }
    ],
    "1.2.1": [
        {
            "id": "S-01",
            "question": "Is there a current Principal-approved strategic plan containing actions, owners, resources and implementation timelines?",
            "requirement_reference": "1.2.1.1; PPD-SGL-SQ-1.2.1 Procedure 7.1",
            "support_status": "Requires a new DocType or child-table query",
            "answer_mode": "unsupported",
            "metric_ids": ["c121-strategic-plan-approval"],
            "limitations": "No structured Strategic Plan source is mapped."
        },
        {
            "id": "S-02",
            "question": "Is the strategic cascade complete from long-term goals through KRAs, KPIs, departmental targets and staff goals?",
            "requirement_reference": "1.2.1.1 and 1.2.1.3",
            "support_status": "Requires a new DocType or child-table query",
            "answer_mode": "unsupported",
            "metric_ids": ["c121-cascade-alignment"],
            "limitations": "The required relationship fields and denominator are not supplied."
        },
        {
            "id": "S-03",
            "question": "Do all active KPIs have an approved baseline, target, owner, frequency, deadline and measurement method?",
            "requirement_reference": "1.2.1.1 and 1.2.1.5",
            "support_status": "Requires an additional field",
            "answer_mode": "unsupported",
            "metric_ids": ["c121-kpi-definition-completeness"],
            "limitations": "The current Quality Goal safe fields do not contain the required KPI attributes."
        },
        {
            "id": "S-04",
            "question": "Which strategic KPIs are on track, off track or cannot be assessed, and what variance requires action?",
            "requirement_reference": "1.2.1.1 and 1.2.1.5",
            "support_status": "Requires an additional field",
            "answer_mode": "unsupported",
            "metric_ids": ["c121-kpi-achievement"],
            "limitations": "Target, actual, direction and tolerance rules are not supplied. Missing data must not be treated as zero."
        },
        {
            "id": "S-05",
            "question": "Are strategic initiatives demonstrably aligned with risk, continuity, budget and resource plans?",
            "requirement_reference": "1.2.1.2",
            "support_status": "Requires a new DocType or child-table query",
            "answer_mode": "unsupported",
            "metric_ids": ["c121-strategic-alignment"],
            "limitations": "Initiative-to-plan links and the budget and resource evidence sources are not supplied."
        },
        {
            "id": "S-06",
            "question": "Are departmental work plans current, strategically aligned, adequately resourced and reviewed at the required frequency?",
            "requirement_reference": "1.2.1.3 and 1.2.1.4; PPD-SGL-SQ-1.2.1 Appendix G",
            "support_status": "Requires a new DocType or child-table query",
            "answer_mode": "unsupported",
            "metric_ids": ["c121-departmental-plan-readiness"],
            "limitations": "The configured Appraisal fields do not expose departmental work-plan content or review evidence."
        },
        {
            "id": "S-07",
            "question": "Which strategic or departmental actions and goals are overdue, stalled or awaiting management decision?",
            "requirement_reference": "1.2.1.4 and 1.2.1.6; PPD-SGL-SQ-1.2.1 Procedure 7.2",
            "support_status": "Can be implemented with revised mapping",
            "answer_mode": "strategic_action_summary",
            "metric_ids": ["c121-overdue-actions", "c121-overdue-staff-goals"],
            "limitations": "The current records do not reliably identify whether each action or goal is strategic, departmental or linked to Criterion 1."
        },
        {
            "id": "S-08",
            "question": "Was the strategic-planning process reviewed annually through APSR, and were the plan, priorities or controls updated based on performance, risk, feedback and benchmarking?",
            "requirement_reference": "1.2.1.6; PPD-SGL-SQ-1.2.1 Approach 13",
            "support_status": "Requires an additional field",
            "answer_mode": "strategic_review_summary",
            "metric_ids": ["c121-completed-reviews", "c121-overdue-actions", "c121-strategic-review-effectiveness"],
            "limitations": "A completed Management Review does not prove the required APSR scope, review inputs, approved revisions or effectiveness."
        }
    ]
}

EXCEPTION_METRIC_IDS = [
    "o-overdue-policy-review", "o-overdue-oversight-review", "o-open-high-risks",
    "o-overdue-high-risks", "o-overdue-actions", "o-overdue-staff-goals", "o-esg-off-track",
    "c111-overdue-engagements", "c111-overdue-policy-review", "c111-overdue-oversight-review",
    "c111-esg-off-track", "c111-overdue-business-impact-review", "c111-high-risks",
    "c111-overdue-high-risks", "c111-overdue-quality-actions", "c111-vmvq-review",
    "c111-stakeholder-coverage", "c111-committee-composition", "c111-financial-monitoring",
    "c111-governance-apsr-effectiveness", "c121-overdue-staff-goals", "c121-overdue-actions",
    "c121-strategic-plan-approval", "c121-cascade-alignment", "c121-kpi-definition-completeness",
    "c121-kpi-achievement", "c121-strategic-alignment", "c121-departmental-plan-readiness",
    "c121-strategic-review-effectiveness"
]

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
    frappe.throw("Unsupported Criterion 1 subcriterion.")

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

metric_lookup = {}
for metric in metrics:
    metric_lookup[metric.get("id")] = metric


def metric_value(metric_id):
    item = metric_lookup.get(metric_id) or {}
    if item.get("status") == "available":
        return item.get("value")
    return None


def metric_part(metric_id, fallback_label=None):
    item = metric_lookup.get(metric_id) or {}
    label = fallback_label or item.get("label") or metric_id
    if item.get("status") == "available":
        return label + ": " + str(item.get("value") or 0)
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


def build_question_answer(question):
    answer_mode = question.get("answer_mode") or "unsupported"
    metric_ids = question.get("metric_ids") or []
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

    status = "partial"
    confidence = "Partial"
    answer = ""

    if answer_mode == "document_only":
        status = "document_only"
        confidence = "Document evidence"
        answer = "Document evidence is required. " + clean_text(question.get("limitations"))

    elif answer_mode == "unsupported":
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
        answer = "; ".join(parts) + ". Categories are not summed because records may overlap."

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
            str(total) + " requirements assessed. Live source with records and no declared manual gap: "
            + str(counts.get("live_source_with_records") or 0)
            + "; partial evidence: " + str(counts.get("partial") or 0)
            + "; no mapped live source: " + str(counts.get("no_mapped_live_source") or 0)
            + "; mapped sources unavailable: " + str(counts.get("no_available_live_source") or 0)
            + ". Source availability is not proof of control effectiveness."
        )

    elif answer_mode == "stakeholder_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c111-stakeholders", "Stakeholder registry records") + "; "
            + metric_part("c111-engagements", "Engagement records") + "; "
            + metric_part("c111-overdue-engagements", "Overdue engagements")
            + ". Required-group coverage and feedback-to-decision linkage cannot be calculated from current fields."
        )

    elif answer_mode == "governance_due":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if unavailable_count > 0 else "Live"
        answer = (
            metric_part("c111-overdue-policy-review", "Overdue policy reviews") + "; "
            + metric_part("c111-overdue-oversight-review", "Overdue oversight reviews")
            + ". Only next review dates are used. Approval and regulatory-obligation completeness are not yet measurable."
        )

    elif answer_mode == "risk_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c111-high-risks", "Open high or critical risks") + "; "
            + metric_part("c111-overdue-high-risks", "Overdue open high or critical risks") + "; "
            + metric_part("c111-overdue-business-impact-review", "Overdue business impact reviews")
            + ". Governance-specific risk linkage and continuity test evidence are not available."
        )

    elif answer_mode == "esg_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if unavailable_count > 0 else "Live"
        answer = (
            metric_part("c111-esg-strategies", "ESG strategy records") + "; "
            + metric_part("c111-esg-initiatives", "ESG initiative records") + "; "
            + metric_part("c111-esg-off-track", "Initiatives where actual is below target")
            + ". Annual plan completeness and approved target direction require additional rules."
        )

    elif answer_mode == "governance_review_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c111-completed-management-reviews", "Completed Management Reviews") + "; "
            + metric_part("c111-overdue-quality-actions", "Overdue Quality Actions")
            + ". Current fields cannot confirm Criterion 1.1.1 APSR coverage, linked findings or effectiveness verification."
        )

    elif answer_mode == "strategic_action_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c121-overdue-actions", "Overdue Quality Actions") + "; "
            + metric_part("c121-overdue-staff-goals", "Staff Goals past end date and not closed")
            + ". Strategic and departmental scoping cannot be confirmed without explicit record links."
        )

    elif answer_mode == "strategic_review_summary":
        status = "partial" if available_count > 0 else "unavailable"
        confidence = "Partial" if available_count > 0 else "Unavailable"
        answer = (
            metric_part("c121-completed-reviews", "Completed Management Reviews") + "; "
            + metric_part("c121-overdue-actions", "Overdue Quality Actions")
            + ". Completion does not prove strategic APSR scope, required inputs, approved plan revisions or effectiveness."
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


questions = []
for question in QUESTION_REGISTRY.get(subcriterion) or []:
    answer_result = build_question_answer(question)
    metric_ids = question.get("metric_ids") or []
    questions.append({
        "id": question.get("id"),
        "criterion": subcriterion,
        "question": question.get("question"),
        "answer": answer_result.get("answer"),
        "metric_id": metric_ids[0] if metric_ids else None,
        "metric_ids": metric_ids,
        "status": answer_result.get("status"),
        "confidence": answer_result.get("confidence"),
        "doctype": answer_result.get("doctypes")[0] if answer_result.get("doctypes") else None,
        "doctypes": answer_result.get("doctypes"),
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
        "api_method": "ucc_analytics_criterion_1",
        "platform_version": "2.0.0-criterion-1-redesign",
        "status": "decision_useful_catalogue",
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
        "data_quality": data_quality
    },
    "warnings": [
        "Criterion 1 source availability depends on site-installed UCC custom DocTypes and signed-in user permissions.",
        "A readable source or existing record is not proof that a governance or strategic control is effective.",
        "Document-only and unsupported controls are returned explicitly and are never converted to zero.",
        "Financial review frequency must be clarified before a compliance denominator is coded.",
        "The procedure names Staff Goal DocType while the current approved source candidate is Goal."
    ]
}

result = standardise_response_contract(result, "Criterion 1", "ucc_analytics_criterion_1", action, subcriterion, row_limit)

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
        frappe.throw("Unknown Criterion 1 metric.")
    result["drilldown"] = evaluate_metric(selected_config, True)

result = standardise_response_contract(result, "Criterion 1", "ucc_analytics_criterion_1", action, subcriterion, row_limit)

frappe.response["message"] = result
