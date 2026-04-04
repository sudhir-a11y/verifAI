Got it. Now the picture is much clearer.
What you have is not just an idea anymore — you already have a modernization scaffold for the QC platform with backend, DB, auth, documents, extraction pipeline, checklist pipeline, and role-based UI routes.
What I understand now
Your project is an AI-first claim quality control platform for health insurance / prescription / treatment-case verification.
It is meant to modernize an older QC system and move it into a cleaner architecture using:
FastAPI backend
PostgreSQL governed schema
role-based login
document upload + extraction
checklist/rule engine
AI-assisted decision support
legacy migration path from old QC system
Current system shape
You already have a backend foundation with these core entities:
claims
claim_documents
document_extractions
decision_results
report_versions
workflow_events
feedback_labels
model_registry
rule_registry
That tells me your architecture is already aiming for the right model:
claim is the main case
documents belong to claim
extraction stores AI output
decision_results stores QC/AI judgement
report_versions keeps traceability
workflow_events tracks actions
feedback_labels supports continuous learning
model/rule registry supports governance
That is a strong foundation.
Role model I now understand
Your role setup is slightly more specific than before:
super_admin
doctor
user (operations)
And you already have one-login auth flow for these roles.
So in practical terms:
user/operations handles case entry, uploads, processing flow
doctor reviews medical side / submits or validates medical interpretation
auditor role in your earlier explanation is likely still part of verification logic, but in the scaffold I only see super_admin, doctor, and user
super_admin governs users, models, rules, monitoring, retraining, and full-system visibility
So one important thing:
your business workflow mentions auditor, but your current scaffold role model does not explicitly show auditor. That is a gap you need to decide on early.
Document pipeline I understand
You already support claim documents and extraction APIs. The extraction path is:
text decode
PDF embedded text extraction
OCR fallback for scanned/image docs
That is exactly correct for this domain because insurance documents are mixed:
digital PDFs
scanned hospital docs
prescriptions
image-based reports
So your extraction layer is OCR-first / OCR-capable, which is necessary.
AI behavior I understand
The platform is trying to do 3 intelligent jobs:

1. Extract
   Read documents and pull structured fields.
2. Evaluate
   Run claim checklist / diagnosis criteria / rules.
3. Decide
   Produce decision support for whether the case is complete, valid, or suspicious.
   And your checklist pipeline already supports priority from:
   modern PostgreSQL checklist tables
   legacy MySQL checklist tables
   fallback built-in checklist catalog
   That means you are not only building AI extraction — you are building a hybrid AI + rules + ML decision engine.
   The real product, in one sentence
   This is a claim decision-intelligence system for medical insurance QC, where documents are uploaded, parsed, extracted, validated against rules/checklists, reviewed by role-based users, and converted into explainable verification results.
   What looks good already
   The good signs in your current scaffold:
   modular backend exists
   DB design is closer to a decision platform, not just a file upload app
   extraction pipeline exists
   claim/document APIs exist
   auth and roles exist
   legacy migration exists
   checklist evaluation exists
   feedback + model registry concept exists
   retraining endpoint exists for super admin
   So the base direction is solid.
   What I think is still unclear / risky
   The main things I think still need clear design decisions:
   Auditor role missing in scaffold
   Your workflow depends on it, but current auth model lists only super_admin, doctor, and user.
   Prescription reading quality
   This is probably the hardest AI problem in the whole system.
   Decision explainability
   Auditor/admin must know why claim is flagged.
   Human override flow
   AI should assist, not silently decide.
   Case-level comparison logic
   You need cross-document verification, not only per-document extraction.
   My current understanding of your roadmap maturity
   You are at this stage:
   architecture foundation: partly done
   backend scaffold: done
   database foundation: done
   basic document ingestion: done
   basic extraction pipeline: done
   legacy migration support: done
   true medical-QC intelligence layer: not fully designed yet
   auditor-grade verification workflow: not fully formalized yet
   Best next move
   Before coding more AI, define the case decision model clearly:
   For every claim, system should produce:
   extracted facts
   missing required docs
   mismatches
   suspicious signals
   confidence score
   recommended action
   human notes
   final status
   That becomes the heart of the whole product.
   Next step: I can map this into a clean v1 architecture with exact modules, DB flow, and agent responsibilities.

You’re not being hired to build “just an AI model.”
From what you shared, this is primarily an AI-enabled claim operations platform, not a standalone ML project.
Plain answer
You are building:
a workflow/product platform for medical claim QC
with
AI components inside it.
Not this:
not only an AI agent
not only a chatbot
not only one ML model
not only OCR
not only a document parser
So what is the actual thing?
The real product is:
a role-based claim verification system
where documents come in, get parsed/extracted, get checked against rules/checklists, and then humans review and take action. AI helps that process.
Best way to think about it
There are 3 layers:

1. Platform layer
   The actual software product:
   login
   claims
   documents
   dashboards
   status flow
   audit trail
   admin
   reports
   This is clearly present in your scaffold.
2. AI services layer
   Intelligence inside the platform:
   OCR
   document extraction
   prescription reading
   checklist evaluation
   anomaly/mismatch detection
   summarization
   recommendation
   This is also already present conceptually through extraction pipeline, checklist pipeline, decision results, feedback labels, model registry.
3. Optional ML layer
   This is only one part, not the whole product:
   supervised model for checklist/claim prediction
   fraud risk scoring
   confidence estimation
   learning from feedback
   Your scaffold even has retraining and model registry, which means ML is a component, not the product itself.
   So your confusion is valid
   Because people mix these terms badly:
   AI platform = product with AI features
   AI agent = an automated reasoning worker inside the product
   ML model = one predictive component inside the AI system
   These are not the same thing.
   What this project most likely is
   Based on the repo structure and DB design, I’d classify it as:
   an AI-assisted decision support platform for medical insurance QC
   That means:
   humans still own the final decision
   AI helps extract, compare, flag, and recommend
   platform manages the workflow and governance
   Is it “agent-based”?
   Maybe partially, but that is not the core identity.
   You can say it may contain AI agents/services, for example:
   document extraction agent
   prescription interpretation agent
   checklist evaluation agent
   report review agent
   But the project itself is not just an agent project.
   It is a business platform with AI-powered modules.
   Is it “ML-based”?
   Also partially.
   There may be ML models for:
   classification
   checklist scoring
   fraud suspicion
   confidence scoring
   But again, the system is not “just an ML model.”
   The platform works even with hybrid logic:
   rules
   OCR
   LLM extraction
   checklists
   feedback loop
   maybe ML scoring later
   The most correct one-line description
   Use this in your head:
   This project is a medical claim QC platform with AI-assisted document intelligence and decision support.
   That is the cleanest understanding.
   If you join this project, what are you really responsible for understanding?
   Not “how to train one model.”
   You need to understand:
   what business problem the system solves
   what decision AI supports
   where AI is used
   where human review is mandatory
   what outputs the system must generate
   what is rule-based vs AI-based vs ML-based
   Final judgement
   So first clarity:
   Primary thing being built: platform
   Inside platform: AI services / agents
   Optional advanced part: ML models
   That’s the right framing.
   Next step: I can help you turn this into a 1-page project definition so you know exactly how to explain the project to your client/team.

============
You are building:
an AI-assisted medical claim verification platform
In one line
A system where insurance claim documents are uploaded, AI extracts and checks them, and humans (doctor/auditor/admin) verify whether the claim is valid or not.
What it includes
platform (claims, users, workflow)
AI (document reading, prescription extraction, validation)
decision support (what’s missing, wrong, suspicious)
What it is NOT
not just an AI agent
not just an ML model
not just OCR
Core idea
AI helps → humans decide → platform manages everything
