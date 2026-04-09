✦ What you get at the end vs. just running AI decision:

    Option 1: "Run AI" (Decision Only)
    What you get back:

     1 {
     2   "final_status": "approve|reject|query",
     3   "ai_decision": "approve|reject|query",
     4   "confidence": 0.85,
     5   "risk_score": 0.25,
     6   "route_target": "auto_approve_queue|qc_queue|doctor_review",
     7   "conflicts": [],
     8   "reason": "All checklist items passed..."
     9 }
    No report HTML is generated. Just metadata - decision, risk score, confidence, conflicts.

    ---

    Option 2: "Run AI" with `auto_generate_report=true` (What Auditor/Doctor UI actually uses)
    What you get:
     1. ✅ Everything from Option 1 (decision, risk, conflicts)
     2. ✅ Full HTML Report generated containing:
        - Patient/Hospital information
        - Diagnosis & Treatment details
        - Timeline (admission/discharge dates)
        - Billing breakdown
        - Investigation findings
        - Medicines used + high-end antibiotic flags
        - AI Decision + Risk/Conflicts (the "brain" output)
        - Medico-legal Reasoning
        - Final Conclusion paragraph

     3. ✅ Report saved to DB (report_versions table, report_source="system")

    This IS what happens when you click "Run AI" in the UI - both auditor-qc.js and workspace.js send:

     1 {
     2   auto_generate_report: true,  // ← Report IS generated
     3   auto_advance: true/false
     4 }

    ---

    Option 3: Manual Report Generation
    Doctor can also click "Generate Report" button separately, which calls /reports/ai-generate endpoint directly.

    ---

    Key Difference from "Last AI Run":


    ┌─────────────────┬──────────────────────────┬─────────────────────────────────────────────────────────┐
    │ Aspect          │ Previous Run (Cached)    │ New "Run AI" Click                                      │
    ├─────────────────┼──────────────────────────┼─────────────────────────────────────────────────────────┤
    │ Structured Data │ ✅ Reused from DB        │ Only regenerated if missing                             │
    │ Decision        │ Old decision deactivated │ ✅ New decision computed                                │
    │ Report HTML     │ Old report stays in DB   │ ✅ New AI-generated report (if auto_generate_report=true) │
    │ Checklist       │ Old results exist        │ ✅ Re-evaluated                                         │
    │ Risk/Conflicts  │ Old values               │ ✅ Recalculated                                         │
    └─────────────────┴──────────────────────────┴─────────────────────────────────────────────────────────┘

    ---

    Bottom Line:

    Yes, clicking "Run AI" generates a proper report for you - it's not just raw decision data. The AI creates a full HTML
    report with:
     - ✅ Structured claim data
     - ✅ AI decision + reasoning
     - ✅ Risk assessment
     - ✅ Conflict detection
     - ✅ Medico-legal conclusion
     - ✅ All medical/billing details

    The report is saved to the database and can be viewed/edited in the Report Editor. It's a complete, professional-grade
    claim investigation report suitable for TPA/insurance audit use.
