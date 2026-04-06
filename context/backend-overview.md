# Backend Code Overview

## Project Structure

```
backend/
├── app/                      # Main application package
│   ├── main.py               # FastAPI app entry point; mounts routers, static files, serves QC/React UI
│   ├── claim.py              # Legacy claim processing module
│   ├── claims.py             # Additional claim-related logic
│   ├── api/                  # API layer
│   │   ├── router.py         # Aggregates all v1 endpoint routers
│   │   ├── deps/             # FastAPI dependencies
│   │   │   └── auth.py       # Auth deps: get_current_user, require_roles, get_bearer_token
│   │   └── v1/endpoints/     # REST API route definitions
│   │       ├── auth.py       # Login/logout, user CRUD, password reset, IFSC verification, bank details
│   │       ├── claims.py     # Claim CRUD, status updates, assignment, report grammar check, conclusion generation
│   │       ├── documents.py  # Document upload, merge, delete, parse-status update, download URL generation
│   │       ├── extractions.py# Run/list data extraction from documents (OCR/AI providers)
│   │       ├── checklist.py  # Claim checklist evaluation, ML model training, alignment labels
│   │       ├── integrations.py# TeamRightWorks case intake webhook; syncs external claims/reports
│   │       ├── admin_tools.py# Admin: claim rules, diagnosis criteria, medicine catalog, legacy migration, SQL import
│   │       ├── user_tools.py # Completed reports listing, Excel/SQL import, QC status updates, suggestion review
│   │       └── health.py     # Health check endpoint (API + DB ping)
│   ├── core/
│   │   └── config.py         # Pydantic Settings: DB, S3, OpenAI, Razorpay, feature flags
│   ├── db/
│   │   └── session.py        # SQLAlchemy session management, DB engine, ping
│   ├── models/
│   │   ├── base.py           # SQLAlchemy declarative base
│   │   └── entities.py       # ORM entity definitions (minimal; schema managed via SQL migrations)
│   ├── schemas/              # Pydantic request/response models
│   │   ├── auth.py           # User, login, role, bank details schemas
│   │   ├── claim.py          # Claim, checklist, grammar, conclusion schemas
│   │   ├── document.py       # Document CRUD schemas
│   │   ├── extraction.py     # Extraction request/response schemas
│   │   ├── checklist.py      # Checklist run/response schemas
│   │   ├── integration.py    # TeamRightWorks intake payload schema
│   │   └── qc_tools.py       # Admin upsert rules, medicine, diagnosis criteria, suggestion review
│   ├── services/             # Business logic layer
│   │   ├── auth_service.py   # User authentication, session management, password hashing, user CRUD
│   │   ├── claims_service.py # Claim creation, listing, assignment, status updates
│   │   ├── documents_service.py # Document storage, merging, deletion, parse status management
│   │   ├── extractions_service.py # Document data extraction orchestration
│   │   ├── extraction_providers.py # External extraction provider implementations
│   │   ├── checklist_pipeline.py  # Full claim checklist evaluation with AI + rule engine
│   │   ├── legacy_checklist_source.py # Legacy checklist catalog loader
│   │   ├── grammar_service.py     # HTML report grammar checking via OpenAI
│   │   ├── claim_structuring_service.py # AI-powered claim data structuring
│   │   ├── ml_claim_model.py      # ML model for claim recommendation prediction
│   │   ├── medicine_rectify_scheduler.py # Background scheduler for medicine catalog rectification
│   │   ├── analysis_import_service.py # Excel/CSV analysis import handler
│   │   ├── sql_dump_parser.py     # SQL dump table row iterator
│   │   ├── storage_service.py     # S3 upload/download/delete operations
│   │   ├── access_control.py      # Doctor claim/document access control checks
│   │   └── claims_service.py      # (duplicate) Claims business logic
│   └── web/                  # Static HTML/JS/CSS for QC workspace and monitor UI
│       ├── monitor.html
│       └── qc/
│           ├── login.html
│           ├── workspace.html
│           └── public/       # QC app assets (CSS, JS, images)
├── db/
│   ├── schema.sql            # PostgreSQL database schema definition
│   └── seed.sql              # Initial seed data
├── scripts/
│   ├── create_database.py           # Database creation utility
│   ├── import_sql_dump_and_learn_ml.py  # Import SQL dump + train ML model
│   ├── import_sql_reports_for_generation.py # Import SQL reports
│   ├── migrate_qc_kp.py             # QC migration script
│   ├── rectify_medicine_catalog.py  # Medicine catalog rectification
│   ├── sync_legacy_claim_payloads.py # Sync legacy claim data
│   ├── train_claim_ml_model.py      # Train claim ML model
│   └── backfill_clean_provider_registry.py # Clean provider registry backfill
├── requirements.txt          # Python dependencies
├── README.md                 # Backend documentation
└── NO_UI.md                  # Notes on no-UI mode
```

## Summary

**verifAI Backend** is a FastAPI-based medical insurance claim audit and QC platform. It provides:

- **Authentication & User Management** — JWT-based auth with role-based access (super_admin, user, doctor, auditor)
- **Claim Management** — CRUD, assignment, status tracking, workflow events
- **Document Handling** — Upload, merge (PDF/image compression), S3 storage, presigned URLs
- **Data Extraction** — OCR/AI extraction from medical documents via configurable providers
- **Checklist & Rule Engine** — AI-assisted clinical checklist evaluation with configurable rules (R001-R016)
- **ML Prediction** — Lightweight ML model for claim recommendation (approve/reject/query) with auto-retraining
- **QC Tools** — Report review, tagging (Genuine/Fraudulent), QC status tracking, suggestion review
- **Admin Tools** — Claim rules management, diagnosis criteria, medicine catalog, legacy data migration, Excel/SQL import
- **Integrations** — Webhook endpoint for TeamRightWorks external claim/report sync
- **UI Serving** — Serves QC workspace HTML/JS and React app dist files
