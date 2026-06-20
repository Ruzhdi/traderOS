# TraderOS Roadmap

## Purpose

This document defines the development roadmap for the TraderOS MVP.

The roadmap describes the order in which the backend system should be built, from project foundation to portfolio-ready delivery.

TraderOS is a backend-first trading journal API. The MVP must stay focused on the core product flow:

> A user can register, log in, create trades, organize them by trading context, attach screenshots, and review basic performance statistics through a documented API.

The roadmap is not a strict calendar plan. It is a build-order plan. Each milestone should unlock the next layer of the system.

---

## Roadmap Principles

The project should be built according to the following principles:

1. **Foundation before features**
   The project structure, configuration, dependencies, and development workflow should be stable before product features are added.

2. **Database before business logic**
   Persistent storage, models, and migrations should be introduced before implementing core journal functionality.

3. **Authentication before user data**
   User-specific resources must be protected before trades, screenshots, and statistics are implemented.

4. **Core CRUD before analytics**
   The system must be able to store and manage trades before it can calculate meaningful statistics.

5. **Simple MVP before advanced features**
   Frontend, AI, broker integrations, advanced analytics, and infrastructure complexity are intentionally postponed until after the backend MVP is complete.

6. **Small issues and small pull requests**
   Each milestone should be broken into small, reviewable GitHub issues. One issue should usually map to one branch and one pull request.

---

## Milestone 0 — Foundation Audit

### Objective

Verify that the initial repository foundation is clean, safe, and ready for continued backend development.

This milestone ensures that the project does not continue on top of unclear documentation, accidental files, or a messy repository structure.

### Scope

This milestone includes:

* reviewing the current repository structure;
* confirming that the documentation files exist;
* replacing planning templates with concrete TraderOS documentation;
* confirming that `.env` is not committed;
* confirming that `.gitignore` is reasonable;
* confirming that the project has a clear FastAPI entrypoint;
* confirming that the repository is clean before moving forward.

### Expected Deliverables

* `docs/product.md` contains concrete TraderOS product definition.
* `docs/mvp_scope.md` contains concrete MVP boundaries.
* `docs/roadmap.md` contains the actual build roadmap.
* The repository has no obvious local or secret files committed.
* The project structure is understandable.

### Definition of Done

This milestone is complete when the planning documentation clearly explains what TraderOS is, what belongs in the MVP, what is excluded, and in what order the project will be built.

---

## Milestone 1 — Engineering Foundation

### Objective

Set up the basic backend engineering foundation required for professional development.

This milestone prepares the project so future features can be implemented, tested, formatted, and reviewed consistently.

### Scope

This milestone includes:

* defining the initial FastAPI app structure;
* setting up environment-based configuration;
* creating or refining dependency files;
* configuring Ruff for linting and formatting;
* setting up pytest;
* adding a basic health endpoint if needed;
* adding a basic health endpoint test;
* optionally adding GitHub Actions CI.

### Expected Deliverables

* FastAPI application starts locally.
* `/docs` is available.
* `/openapi.json` is available.
* Project dependencies are clearly defined.
* Ruff can be run locally.
* Pytest can be run locally.
* At least one basic test exists.
* The README contains minimal local setup instructions.

### Definition of Done

This milestone is complete when the project has a clean development workflow and a basic tested FastAPI application that can be run locally.

---

## Milestone 2 — Database Foundation

### Objective

Introduce persistent storage using PostgreSQL and prepare the project for database-backed features.

This milestone creates the foundation for users, trades, screenshots, metadata, and statistics.

### Scope

This milestone includes:

* adding PostgreSQL through Docker Compose;
* configuring database connection settings;
* setting up SQLAlchemy;
* creating the database session layer;
* creating a base model setup;
* configuring Alembic;
* creating and running the first migration workflow.

### Expected Deliverables

* PostgreSQL can be started locally.
* The application can connect to the database.
* SQLAlchemy is configured.
* Alembic is configured.
* A migration can be generated and applied.
* Database configuration uses environment variables.

### Definition of Done

This milestone is complete when the project has a working PostgreSQL database setup, SQLAlchemy integration, and Alembic migration workflow.

---

## Milestone 3 — Auth Foundation

### Objective

Implement user authentication and protected API access.

This milestone ensures that TraderOS can safely store user-specific trading data.

### Scope

This milestone includes:

* creating the User model;
* creating user-related Pydantic schemas;
* hashing passwords securely;
* implementing user registration;
* implementing user login;
* generating JWT access tokens;
* creating a current user dependency;
* protecting endpoints;
* adding `/users/me`;
* adding basic authentication tests.

### Expected Deliverables

* A user can register.
* A user can log in.
* Passwords are stored as hashes.
* The API returns a JWT token after successful login.
* Protected endpoints require authentication.
* `/users/me` returns the authenticated user.
* Auth tests cover the main happy path and basic failure cases.

### Definition of Done

This milestone is complete when authentication works end-to-end and protected endpoints can reliably identify the current user.

---

## Milestone 4 — Trading Metadata

### Objective

Implement the basic metadata needed to classify and organize trades.

Trading metadata makes the journal useful for filtering, reviewing, and later statistics.

### Scope

This milestone includes resources such as:

* instruments;
* trading sessions;
* setups.

The system should allow the authenticated user to create and list these metadata items.

Examples:

* instrument: `NQ`, `ES`, `EURUSD`;
* session: `Asia`, `London`, `New York`;
* setup: `Value Area Breakout`, `VWAP Reclaim`, `Range Breakout`.

### Expected Deliverables

* Instrument model and endpoints.
* Trading session model and endpoints.
* Setup model and endpoints.
* Metadata belongs to the authenticated user where appropriate.
* User cannot access another user’s metadata.
* Basic tests for metadata creation/listing.

### Definition of Done

This milestone is complete when the user can create and list the metadata needed to classify trades.

---

## Milestone 5 — Trade Journal Core

### Objective

Implement the core trade journal functionality.

This is the central milestone of TraderOS. The product becomes useful only when users can create and manage trade records.

### Scope

This milestone includes:

* creating the Trade model;
* creating trade request and response schemas;
* implementing trade creation;
* implementing trade listing;
* implementing trade detail retrieval;
* implementing trade update;
* implementing trade deletion;
* enforcing ownership rules;
* adding basic trade API tests.

A trade should include structured fields such as:

* instrument;
* trading session;
* setup;
* result;
* direction;
* RR;
* PnL;
* notes;
* trade date/time.

The exact field set can be refined during implementation, but the trade model must support future filtering and statistics.

### Expected Deliverables

* A user can create a trade.
* A user can list their own trades.
* A user can view a single trade by ID.
* A user can update their own trade.
* A user can delete their own trade.
* A user cannot access or modify another user’s trades.
* Basic trade tests exist.

### Definition of Done

This milestone is complete when the authenticated user can manage their own trade journal through CRUD API endpoints.

---

## Milestone 6 — Trade Filters

### Objective

Add filtering and pagination so the user can review specific parts of their trading history.

Filtering turns the trade journal from simple storage into a review tool.

### Scope

This milestone includes filtering trades by:

* date range;
* instrument;
* trading session;
* setup;
* result.

This milestone should also include:

* pagination;
* reasonable default ordering;
* tests for filtered trade lists.

### Expected Deliverables

* User can filter trades by date range.
* User can filter trades by instrument.
* User can filter trades by session.
* User can filter trades by setup.
* User can filter trades by result.
* Trade list responses are paginated.
* Filters only apply to the authenticated user’s own trades.

### Definition of Done

This milestone is complete when the user can query and review specific subsets of their trading history through API filters.

---

## Milestone 7 — Stats

### Objective

Implement basic trading performance statistics.

This milestone provides the first analytical layer of TraderOS.

### Scope

This milestone includes:

* creating a stats calculation service;
* calculating performance metrics from stored trades;
* exposing a stats summary endpoint;
* adding unit tests for statistics formulas.

Required statistics:

* trade count;
* winrate;
* average RR;
* expectancy;
* total RR;
* total PnL;
* profit factor;
* max losing streak.

Statistics must be calculated only from the authenticated user’s own trades.

### Expected Deliverables

* Stats service exists outside the route layer.
* Unit tests cover core formulas.
* `/stats/summary` returns structured statistics.
* Stats can optionally respect the same filters used for trades.
* Statistics do not include other users’ data.

### Definition of Done

This milestone is complete when the user can request a performance summary based on their recorded trades.

---

## Milestone 8 — Screenshots

### Objective

Allow users to attach screenshots to trades.

Screenshots provide visual trading context and make the journal more useful for review.

### Scope

This milestone includes:

* creating the Screenshot model;
* implementing screenshot upload;
* storing screenshot metadata;
* linking screenshots to trades;
* listing screenshots for a trade;
* deleting screenshots;
* validating file type;
* validating file size;
* enforcing ownership rules.

The MVP should keep storage simple. Local file storage is acceptable for the first version unless deployment requirements demand a different approach.

### Expected Deliverables

* User can upload a screenshot to their own trade.
* User can list screenshots for their own trade.
* User can delete screenshots from their own trade.
* File type validation exists.
* File size validation exists.
* User cannot upload screenshots to another user’s trade.
* User cannot access screenshots linked to another user’s trade.

### Definition of Done

This milestone is complete when screenshots can be attached, listed, and deleted safely through the API.

---

## Milestone 9 — Portfolio Polish

### Objective

Prepare TraderOS to be shown as a junior Python backend portfolio project.

This milestone focuses on presentation quality, reproducibility, documentation, and final cleanup.

### Scope

This milestone includes:

* improving the README;
* adding complete local setup instructions;
* documenting environment variables;
* adding API usage examples;
* documenting the architecture;
* documenting the database schema;
* adding seed or demo data if useful;
* deploying the API if possible;
* adding the deployment link to the README;
* reviewing the full project for scope creep and technical debt.

### Expected Deliverables

* README explains what TraderOS is.
* README explains how to run the project locally.
* README explains how to run tests.
* API examples are documented.
* Architecture documentation exists.
* Database documentation exists.
* Project can be demonstrated through Swagger/OpenAPI.
* Project is clean enough to show in an interview or job application.

### Definition of Done

This milestone is complete when TraderOS is not only functional, but also understandable, reproducible, and presentable as a backend portfolio project.

---

## MVP Build Order

The milestones should be completed in the following order:

```text
Milestone 0 — Foundation Audit
↓
Milestone 1 — Engineering Foundation
↓
Milestone 2 — Database Foundation
↓
Milestone 3 — Auth Foundation
↓
Milestone 4 — Trading Metadata
↓
Milestone 5 — Trade Journal Core
↓
Milestone 6 — Trade Filters
↓
Milestone 7 — Stats
↓
Milestone 8 — Screenshots
↓
Milestone 9 — Portfolio Polish
```

This order is intentional.

Authentication depends on the database foundation.
Trades depend on authentication and metadata.
Filters depend on trades.
Stats depend on trades and filters.
Screenshots depend on trades and ownership checks.
Portfolio polish depends on the core MVP being stable.

---

## Issue Creation Rule

GitHub issues should be created from the current milestone only.

Do not create a large backlog of detailed issues for every future milestone too early. Future issues may change as the project evolves.

A good issue should have:

* a clear problem;
* a clear scope;
* explicit out-of-scope items;
* acceptance criteria;
* a test plan;
* a suggested branch name;
* a suggested commit message.

One issue should usually produce one focused pull request.

---

## Pull Request Rule

Each pull request should solve one logical task.

A pull request should not mix unrelated changes.

Good examples:

* configure Ruff;
* add health endpoint test;
* add User model;
* implement login endpoint;
* add trade ownership tests.

Bad examples:

* add auth, Docker, trades, stats, and README updates in one PR;
* rewrite project structure while adding a product feature;
* add frontend while working on backend MVP;
* change unrelated files “because they were nearby.”

---

## Scope Control Rule

The roadmap should protect the MVP from unnecessary expansion.

Any new idea must be evaluated against the core MVP goal:

> Does this help the user record trades, organize trading context, attach screenshots, or review basic performance through the backend API?

If the answer is no, the idea should be postponed until after the MVP.