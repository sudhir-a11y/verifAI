# Backend Architecture Guide (Agent Instructions)

This document defines the **final backend structure**, **team ownership**, and **rules** for working on the verifAI FastAPI backend.

This is the **source of truth** for how code must be organized.

---

# Goals

- Scalable architecture
- Clear team ownership
- AI / ML separation
- Maintainable FastAPI structure
- Workflow-based system
- Zero spaghetti services
- Easy onboarding for new developers

---

# Final Project Structure

```
backend/
│
├── app/
│
│   ├── main.py
│
│   ├── core/                    # config / settings / security
│   │   ├── config.py
│   │   ├── security.py
│   │   └── logging.py
│
│   ├── api/                     # ROUTES ONLY
│   │   ├── router.py
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── claims.py
│   │       ├── documents.py
│   │       ├── extraction.py
│   │       ├── checklist.py
│   │       ├── decision.py
│   │       └── admin.py
│
│   ├── domain/                  # BUSINESS LOGIC
│   │   ├── claims/
│   │   │   ├── service.py
│   │   │   ├── manager.py
│   │   │   └── validator.py
│   │   │
│   │   ├── documents/
│   │   ├── checklist/
│   │   ├── decision/
│   │   └── workflow/
│
│   ├── ai/                      # LLM / OCR / extraction
│   │   ├── extraction/
│   │   │   ├── engine.py
│   │   │   ├── providers.py
│   │   │   └── parser.py
│   │   │
│   │   ├── summarization/
│   │   ├── structuring/
│   │   └── grammar/
│
│   ├── ml/                      # TRAINING + PREDICTION
│   │   ├── models/
│   │   ├── training/
│   │   ├── inference/
│   │   └── features/
│
│   ├── workflows/               # CLAIM PIPELINE
│   │   ├── claim_pipeline.py
│   │   ├── extraction_flow.py
│   │   ├── checklist_flow.py
│   │   └── decision_flow.py
│
│   ├── repositories/            # DB ACCESS ONLY
│   │   ├── claim_repo.py
│   │   ├── document_repo.py
│   │   └── user_repo.py
│
│   ├── models/                  # ORM
│   ├── schemas/                 # Pydantic
│
│   ├── infrastructure/          # EXTERNAL SERVICES
│   │   ├── storage/
│   │   ├── queue/
│   │   ├── cache/
│   │   └── integrations/
│
│   └── dependencies/            # auth deps
│
├── scripts/
├── tests/
├── db/
└── requirements.txt
```

---

# Layer Responsibilities

## API Layer

Location:

```
app/api/
```

Responsibilities:

- define routes
- validate request
- call domain service
- return response

Rules:

API must NOT contain business logic

Example:

```
@router.post("/claims")
def create_claim():
    return claim_service.create()
```

---

## Domain Layer

Location:

```
app/domain/
```

Responsibilities:

- business logic
- validation
- orchestration
- workflow calls

This is the **heart of application**

---

## AI Layer

Location:

```
app/ai/
```

Responsibilities:

- OCR
- LLM extraction
- summarization
- document parsing
- grammar correction

Rules:

AI layer must NOT:

- access DB
- call repositories
- contain business logic

AI returns structured data only

---

## ML Layer

Location:

```
app/ml/
```

Responsibilities:

- model training
- prediction
- scoring
- feature generation
- model registry

Rules:

ML must be stateless inference

No API calls

No DB logic

---

## Workflow Layer

Location:

```
app/workflows/
```

Responsibilities:

- orchestrate pipeline
- call AI
- call ML
- call domain
- manage flow

Example:

claim pipeline:

```
upload docs
↓
run extraction
↓
run checklist
↓
run decision
↓
store result
```

---

## Repository Layer

Location:

```
app/repositories/
```

Responsibilities:

- database queries
- CRUD
- joins

Rules:

Repository must NOT:

- contain business logic
- call AI
- call ML

---

## Infrastructure Layer

Location:

```
app/infrastructure/
```

Responsibilities:

- S3
- queues
- redis
- integrations
- external APIs

---

# Request Flow

```
API
 ↓
Domain Service
 ↓
Workflow
 ↓
AI / ML
 ↓
Repository
 ↓
Database
```

---

# Team Ownership

## API Team

```
app/api/
app/schemas/
```

---

## Business Team

```
app/domain/
app/workflows/
```

---

## AI Team

```
app/ai/
```

---

## ML Team

```
app/ml/
```

---

## Data Team

```
app/repositories/
app/models/
```

---

## DevOps Team

```
scripts/
infrastructure/
```

---

# Coding Rules

## Rule 1

Routes never contain logic

---

## Rule 2

Domain controls application behavior

---

## Rule 3

AI never touches database

---

## Rule 4

ML only predicts

---

## Rule 5

Repositories only query DB

---

## Rule 6

Workflows orchestrate system

---

# Example Flow

Claim Processing

```
POST /claims/process

API
↓
domain.claims.service
↓
workflow.claim_pipeline
↓
ai.extraction
↓
ml.scoring
↓
decision.service
↓
repository.save
```

---

# Naming Conventions

Services:

```
claims_service.py
documents_service.py
```

Repositories:

```
claim_repo.py
document_repo.py
```

Workflows:

```
claim_pipeline.py
```

AI:

```
extraction_engine.py
```

ML:

```
claim_model.py
```

---

# Forbidden

Do NOT:

- mix AI in services
- put DB queries in API
- put ML in routes
- put business logic in repositories
- create giant services.py

---

# This Architecture Supports

- multiple teams
- large scale
- async workers
- microservices later
- model versioning
- rule engine
- audit logs
- pipeline orchestration

---

# Agent Instructions

When adding new feature:

Step 1

Add schema

```
app/schemas/
```

Step 2

Add API route

```
app/api/v1/
```

Step 3

Add domain service

```
app/domain/
```

Step 4

Add repository

```
app/repositories/
```

Step 5

Add workflow if needed

```
app/workflows/
```

Step 6

Add AI / ML if needed

```
app/ai/
app/ml/
```

---

This is final architecture.
All new code must follow this.
