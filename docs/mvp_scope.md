# TraderOS MVP Scope

## Purpose

This document defines the scope of the TraderOS MVP.

The goal of the MVP is to build a backend-first trading journal API that allows an individual trader to record trades, organize them by trading context, attach screenshots, and review basic performance statistics.

The MVP must stay focused on one core outcome:

> A trader can use the API to keep a structured trading journal and review performance without relying on spreadsheets or disconnected notes.

The MVP is intentionally limited to backend/API functionality. Frontend, AI, broker integrations, and advanced trading tools are excluded from the first version.

---

## Must-have Features

Must-have features are required for the MVP to be considered functional.

If any of these features are missing, the MVP is not complete.

---

### 1. User Authentication

The system must allow a user to register, log in, and access protected API endpoints.

Required functionality:

* user registration;
* user login;
* password hashing;
* JWT token generation;
* current user dependency;
* protected endpoints;
* `/users/me` endpoint.

Reason:

TraderOS stores personal trading data. Each user must only access their own trades, screenshots, metadata, and statistics.

---

### 2. User Data Ownership

The system must enforce ownership rules across user-specific resources.

Required functionality:

* a user can only see their own trades;
* a user can only update their own trades;
* a user can only delete their own trades;
* a user can only access screenshots linked to their own trades;
* a user can only access their own statistics.

Reason:

Ownership is a core backend security requirement. A trading journal is private user data, so cross-user access must not be possible.

---

### 3. Trading Metadata

The system must support basic metadata used to classify trades.

Required resources:

* instruments;
* trading sessions;
* setups.

Examples:

* instrument: `NQ`, `ES`, `EURUSD`;
* trading session: `London`, `New York`, `Asia`;
* setup: `Value Area Breakout`, `VWAP Reclaim`, `Range Breakout`.

Required functionality:

* create metadata item;
* list metadata items;
* associate metadata with trades.

Reason:

Metadata makes trades searchable, filterable, and useful for later analysis.

---

### 4. Trade Journal CRUD

The system must allow the user to manage trade records.

Required functionality:

* create trade;
* list trades;
* get trade by ID;
* update trade;
* delete trade.

A trade should support structured fields such as:

* instrument;
* trading session;
* setup;
* result;
* direction;
* entry price;
* exit price;
* stop loss;
* take profit;
* RR;
* PnL;
* notes;
* trade date/time.

The exact field set can be refined during implementation, but the trade model must be structured enough to support filtering and statistics.

Reason:

Trade CRUD is the core feature of TraderOS. Without it, the product does not exist.

---

### 5. Trade Filtering

The system must allow the user to filter trades by important review criteria.

Required filters:

* date range;
* instrument;
* trading session;
* setup;
* result.

Should also support:

* pagination;
* reasonable default ordering, such as newest trades first.

Reason:

A journal becomes useful only when the user can review specific parts of trading history instead of manually scanning every trade.

---

### 6. Basic Trading Statistics

The system must provide basic performance statistics based on the user’s recorded trades.

Required statistics:

* trade count;
* winrate;
* average RR;
* expectancy;
* total RR;
* total PnL;
* profit factor;
* max losing streak.

Statistics must be calculated from the authenticated user’s own trades only.

Reason:

The purpose of a trading journal is not just storing trades, but helping the user understand performance.

---

### 7. Screenshot Uploads

The system must allow users to attach screenshots to trades.

Required functionality:

* upload screenshot for a trade;
* list screenshots linked to a trade;
* delete screenshot;
* store screenshot metadata in the database;
* validate file type;
* validate file size;
* enforce ownership rules.

Reason:

Screenshots preserve visual context: chart structure, execution reasoning, trade setup, and market conditions.

---

### 8. PostgreSQL Persistence

The system must use PostgreSQL as the main database.

Required functionality:

* database connection configuration;
* SQLAlchemy models;
* database session management;
* Alembic migrations.

Reason:

The project should demonstrate realistic backend database work, not temporary in-memory storage.

---

### 9. API Documentation

The system must expose API documentation through FastAPI/OpenAPI.

Required functionality:

* Swagger UI available at `/docs`;
* OpenAPI schema available at `/openapi.json`;
* meaningful request/response schemas.

Reason:

A backend portfolio project must be easy to inspect and test without reading the entire source code first.

---

### 10. Local Development Setup

The project must be runnable locally by another developer.

Required functionality:

* clear README setup instructions;
* environment variable example file;
* dependency installation instructions;
* application startup command;
* Docker Compose setup for PostgreSQL.

Reason:

A portfolio project must be reproducible. If another developer cannot run it locally, the project is not professionally presentable.

---

### 11. Basic Automated Tests

The MVP must include basic automated tests for the most important behavior.

Required test coverage:

* authentication basics;
* trade creation/listing basics;
* ownership checks;
* stats calculation logic;
* screenshot validation basics where applicable.

Reason:

Tests prove that core behavior works and that future changes do not silently break critical functionality.

---

## Should-have Features

Should-have features are important, but they do not block the first usable MVP if time is limited.

These should be added after the must-have features are stable.

---

### 1. GitHub Actions CI

The project should run automated checks on pull requests.

Suggested checks:

* install dependencies;
* run Ruff;
* run pytest.

Reason:

CI demonstrates professional workflow and catches problems before merging.

---

### 2. Deployment

The API should be deployed to a public environment if possible.

Possible platforms:

* Render;
* Railway;
* Fly.io;
* other simple deployment platform.

Reason:

A deployed API is easier to show in a portfolio and during interviews.

---

### 3. Seed or Demo Data

The project should include a way to create demo data.

Possible options:

* seed script;
* demo user;
* example trades;
* documented API examples.

Reason:

Demo data makes the project easier to test and present.

---

### 4. Improved README

The README should explain the project clearly.

Should include:

* project description;
* tech stack;
* local setup;
* environment variables;
* how to run tests;
* API documentation link;
* example API requests;
* demo flow.

Reason:

A good README makes the project understandable to recruiters, engineers, and future maintainers.

---

### 5. Architecture Documentation

The project should include basic architecture documentation.

Suggested file:

* `docs/architecture.md`

Should explain:

* project structure;
* route/service/repository separation;
* database layer;
* auth flow;
* ownership rules.

Reason:

This helps show that the project was designed intentionally, not randomly assembled.

---

### 6. Database Documentation

The project should include basic database documentation.

Suggested file:

* `docs/database.md`

Should explain:

* main tables;
* relationships;
* ownership model;
* migrations;
* important constraints.

Reason:

Database design is a key backend skill, and documenting it improves portfolio quality.

---

## Could-have Features

Could-have features are optional enhancements.

They should only be considered after the must-have and should-have features are complete.

---

### 1. AI Journal Summary

The system may generate a basic AI summary of a trade or a set of trades.

This is optional and must not be started before the core journal, stats, screenshots, and tests are stable.

---

### 2. CSV Export

The system may support exporting trades to CSV.

Possible endpoint:

* `GET /trades/export`

Reason:

Exporting data is useful, but not required for the first backend MVP.

---

### 3. Simple Frontend Page

A very small frontend page may be added later to demonstrate the API.

This should not become a full dashboard.

Reason:

The project is backend-first. Frontend should not distract from backend quality.

---

### 4. Advanced Statistics

The system may later support more advanced analytics.

Possible examples:

* performance by day of week;
* performance by hour;
* session comparison;
* setup comparison;
* average win/loss;
* equity curve.

Reason:

Advanced analytics are valuable, but the MVP only needs basic performance metrics.

---

### 5. Tags

The system may later support flexible tags for trades.

Reason:

Tags are useful, but they can complicate filtering and data modeling. Instruments, sessions, and setups are enough for the MVP.

---

## Won’t-have in MVP

The following features are intentionally excluded from the MVP.

They should not be added during the MVP phase, even if they seem interesting.

---

### 1. Frontend Dashboard

The MVP will not include a React, Next.js, Vue, or full web dashboard.

TraderOS MVP is backend/API-only.

---

### 2. AI Trading Coach

The MVP will not include:

* AI trading advice;
* AI performance coaching;
* AI screenshot analysis;
* AI-generated strategy recommendations;
* automated decision-making.

AI can be considered later only after the backend is stable.

---

### 3. Broker Integration

The MVP will not connect to:

* futures brokers;
* forex brokers;
* crypto exchanges;
* prop firm APIs;
* execution platforms.

All trades are entered manually through the API.

---

### 4. TradingView Integration

The MVP will not include:

* TradingView alerts;
* TradingView chart embedding;
* automatic screenshot imports;
* TradingView strategy integration.

---

### 5. Backtesting Engine

TraderOS MVP is not a backtesting system.

It will not:

* replay historical data;
* simulate strategies;
* generate trade signals;
* run strategy optimization.

---

### 6. Live Trading or Order Execution

TraderOS will not place trades or manage positions.

It will not connect to live markets or execute orders.

---

### 7. Multi-user Teams or Workspaces

The MVP will not support:

* teams;
* organizations;
* shared workspaces;
* prop firm manager accounts;
* role-based team permissions.

The MVP is for individual users only.

---

### 8. Payments and Subscriptions

The MVP will not include:

* Stripe;
* billing;
* paid plans;
* subscriptions;
* invoices.

---

### 9. Mobile App

The MVP will not include a mobile application.

---

### 10. Advanced Infrastructure

The MVP will not include:

* Kubernetes;
* microservices;
* distributed workers;
* Celery;
* Redis;
* message queues;
* complex cloud infrastructure.

The system should stay simple and appropriate for a junior backend portfolio project.

---

## MVP Definition of Done

The MVP is considered complete when the following checklist is satisfied.

---

### Product Functionality

* A user can register.
* A user can log in.
* A user can access protected endpoints with JWT.
* A user can create trading metadata.
* A user can create a trade.
* A user can list their own trades.
* A user can view a single trade by ID.
* A user can update their own trade.
* A user can delete their own trade.
* A user can filter trades by date, instrument, session, setup, and result.
* A user can upload a screenshot to their own trade.
* A user can list screenshots for their own trade.
* A user can delete screenshots from their own trade.
* A user can view basic trading statistics.

---

### Security and Ownership

* Passwords are hashed.
* JWT authentication works.
* Protected endpoints require authentication.
* Users cannot access other users’ trades.
* Users cannot modify other users’ trades.
* Users cannot access screenshots linked to other users’ trades.
* Statistics are calculated only from the authenticated user’s own trades.
* No real secrets are committed to the repository.

---

### Database

* PostgreSQL is used as the main database.
* SQLAlchemy models exist for core resources.
* Alembic migrations exist.
* Database relationships are clear.
* The project can be started with a clean database.

---

### API Quality

* API routes are organized clearly.
* Request and response schemas are defined with Pydantic.
* Swagger UI works at `/docs`.
* OpenAPI schema works at `/openapi.json`.
* Error responses are reasonably handled.
* Endpoints return appropriate HTTP status codes.

---

### Engineering Quality

* The project has a clear folder structure.
* Business logic is not placed directly inside `main.py`.
* Route, service, repository, model, and schema responsibilities are separated where appropriate.
* Ruff passes.
* Basic pytest tests pass.
* The project can be run locally.
* Docker Compose can start required services.
* The README explains how to set up and run the project.

---

### Portfolio Readiness

* The README explains what TraderOS is.
* The README includes setup instructions.
* The README includes API usage examples.
* The project has clear documentation in the `docs/` directory.
* The project demonstrates backend skills relevant to a junior Python backend developer role.
* The project avoids unnecessary scope creep.
* The project is clean enough to be shown in a job application or interview.

---

## Scope Control Rule

Any new idea must be evaluated against the MVP goal.

A feature should be included in the MVP only if it directly helps the user:

> record trades, organize trading context, attach screenshots, or review basic performance through the backend API.

If a feature does not directly support this goal, it should be postponed until after the MVP.
