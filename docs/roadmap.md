#### Milestone 0 — Foundation Audit

Verify that the current project foundation is clean and ready for further development.

This milestone should include:

* checking the current file structure;
* verifying that `.env` is not committed;
* confirming that `.gitignore` is correct;
* confirming that the FastAPI app runs locally;
* confirming that `/health` and `/docs` work;
* checking that the Git repository is clean.

#### Milestone 1 — Engineering Foundation

Set up the basic engineering tools and structure required for professional development.

This milestone should include:

* environment-based configuration;
* dependency files;
* Ruff configuration;
* basic pytest setup;
* initial health endpoint test;
* optional GitHub Actions CI.

#### Milestone 2 — Database Foundation

Prepare the project for persistent data storage with PostgreSQL.

This milestone should include:

* Docker Compose setup for PostgreSQL;
* SQLAlchemy database session configuration;
* base database model setup;
* Alembic migration configuration;
* first migration workflow.

#### Milestone 3 — Auth Foundation

Implement user authentication and protected API access.

This milestone should include:

* User model;
* password hashing;
* user registration;
* user login;
* JWT token generation;
* current user dependency;
* protected `/users/me` endpoint;
* authentication tests.

#### Milestone 4 — Trading Metadata

Implement the core metadata needed to classify trades.

This milestone should include:

* instruments;
* trading sessions;
* setups;
* create/list endpoints for metadata;
* ownership rules for user-specific metadata.

#### Milestone 5 — Trade Journal Core

Implement the core trade journal functionality.

This milestone should include:

* Trade model;
* trade creation;
* trade listing;
* trade detail endpoint;
* trade update;
* trade deletion;
* ownership checks;
* basic trade API tests.

#### Milestone 6 — Trade Filters

Add filtering and pagination for reviewing trades.

This milestone should include:

* filtering by date range;
* filtering by instrument;
* filtering by trading session;
* filtering by setup;
* filtering by result;
* pagination;
* tests for filtered trade lists.

#### Milestone 7 — Stats

Implement trading performance statistics.

This milestone should include:

* stats calculation service;
* winrate;
* average RR;
* expectancy;
* total RR;
* total PnL;
* profit factor;
* max losing streak;
* unit tests for stats formulas;
* `/stats/summary` endpoint.

#### Milestone 8 — Screenshots

Allow users to attach screenshots to trades.

This milestone should include:

* Screenshot model;
* screenshot upload endpoint;
* screenshot list endpoint;
* screenshot delete endpoint;
* file type validation;
* file size validation;
* ownership checks;
* upload tests.

#### Milestone 9 — Portfolio Polish

Prepare the project to be shown as a junior backend portfolio project.

This milestone should include:

* improved README;
* local setup instructions;
* API examples;
* architecture documentation;
* database documentation;
* demo data or seed script;
* deployment;
* deployment link in README;
* final project review.
