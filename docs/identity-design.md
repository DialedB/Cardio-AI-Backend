# Identity and Access Management Design

- **Status:** Accepted
- **Decision owner:** `@DialedB`
- **Related ticket:** `[Auth] Agree the identity design`
- **Last updated:** 2026-10-14

This is the accepted identity architecture for the CardioSmart backend.

## Purpose

This document establishes the identity and access-management approach for the CardioSmart
backend.

It decides:

- who the users are;
- which application roles exist;
- which identity-provider approach will be used;
- how external identities map to backend users;
- how access and refresh tokens are handled;
- where refresh sessions are stored;
- how passwords and multifactor authentication are managed;
- how roles are represented and enforced; and
- which decisions remain open before implementation.

The backend currently reserves authentication and authorization boundaries in:

- `backend/api/auth.py`;
- `backend/auth/authentication.py`; and
- `backend/auth/authorization.py`.

No user model, identity provider, session store, role model, or authentication behavior has
been implemented.

## Product-design inputs

This decision is informed by the **CardioGuard AI Project Proposal, April 2026**.

The proposal identifies:

- patients and members of the general public as the primary product audience;
- clinicians as oversight stakeholders;
- administrators as platform-management users; and
- role-based access control with `patient`, `clinician`, and `administrator` roles.

The proposal describes the platform as supporting users between clinical encounters rather
than replacing clinical care.

Relevant proposal references include:

- Page 2: patient-level support that complements cardiologists and primary-care physicians.
- Page 3: continuous support between clinical encounters.
- Page 4: role-based access control for patient, clinician, and administrator.
- Page 7: separate consideration of patient and clinician users during testing.

The proposal does not fully define clinician-facing workflows. The existence of a `clinician`
role must therefore not be interpreted as approval for unrestricted access to another user's
information or as evidence that the application is a clinician-facing decision-support system.

The source proposal should be linked or added to project documentation so that reviewers can
verify these requirements directly.

The repository is named CardioSmart while the referenced proposal is named CardioGuard AI. The
project owner must confirm whether these names refer to the same project and which name is
canonical.

## Scope

This document defines:

- human application roles;
- the external identity-provider selection;
- identity identifiers;
- registration and privileged role assignment;
- login and server-side session architecture;
- access-token validation;
- refresh-token handling and storage;
- password and MFA policy;
- authentication-related audit requirements;
- baseline authorization rules; and
- requirements for follow-up Auth stories.

Behavior belonging to other project subsystems is outside the scope of this decision.

## Decision summary

CardioSmart will:

1. Recognize three human application roles: `patient`, `clinician`, and `admin`.
2. Treat members of the general public as a product audience rather than a fourth role.
3. Use self-hosted Keycloak as the OAuth 2.0 and OpenID Connect identity provider.
4. Use Authorization Code Flow with PKCE for interactive browser authentication.
5. Identify external users by the combination of the validated `iss` and `sub` claims.
6. Assign every application user a backend-owned UUID.
7. Use RS256 access tokens with a 15-minute lifetime.
8. Use rotating Keycloak refresh tokens with reuse detection.
9. Store backend-managed refresh sessions in PostgreSQL rather than Redis.
10. Store refresh tokens encrypted at rest.
11. Expose only an opaque, secure session cookie to browser clients.
12. Keep authorization enforcement in the backend.
13. Require resource-level authorization in addition to role checks.
14. Deny access by default.
15. Require MFA for clinicians and administrators.
16. Delegate password collection, hashing, recovery, and protection to Keycloak.
17. Use only open-source software with no identity-provider licensing fees.

Keycloak deployment remains subject to:

- security and privacy review;
- infrastructure capacity planning;
- backup and recovery planning;
- monitoring and upgrade ownership;
- confirmation of the production secret-management approach; and
- confirmation of the supported Keycloak and PostgreSQL versions.

This document selects the architecture but does not provision Keycloak, add infrastructure,
change dependencies, or create database schemas.

## Users, audiences, and roles

Product audiences and authorization roles are related but are not identical.

### Product audiences

The primary product audience consists of:

- patients; and
- members of the general public seeking preventive cardiovascular-health guidance, including
  people without an existing diagnosis.

Clinicians are currently treated as oversight stakeholders.

Administrators manage approved platform and account-management functions.

### Human application roles

The application has three human roles, matching the project proposal:

| Role | Meaning | Baseline authorization |
| --- | --- | --- |
| `patient` | A registered patient or general end user | Own account and explicitly approved end-user features |
| `clinician` | An approved clinician | Only explicitly defined clinician workflows |
| `admin` | An approved administrator | Only explicitly defined administrative workflows |

The role value is `admin`, while documentation and user interfaces may display
“administrator.”

The name `patient` is retained to match the proposal's RBAC terminology. Assignment of this role
does not assert that the user:

- has a diagnosis;
- has a relationship with a clinician;
- is receiving treatment;
- has completed identity proofing; or
- has an associated medical record.

The general public is a product audience, not a fourth RBAC role. A member of the general public
who registers receives the `patient` role unless a future approved decision changes the
end-user role name.

Whether anonymous access is permitted is not decided here. Authentication is required by
default unless a route is explicitly approved as public.

### Multiple roles

A user may hold more than one role.

Roles are additive only where an endpoint explicitly allows them. No role automatically
inherits all permissions from another role.

For example:

- `admin` does not automatically include `clinician`;
- `clinician` does not automatically include `patient`;
- `admin` does not implicitly grant access to another user's content; and
- holding multiple roles does not bypass resource-level authorization.

The authenticated principal must preserve the user's complete set of recognized roles so that
an endpoint can evaluate the applicable role and resource rules.

Unknown or malformed role values must not grant access.

### Service identities

Machine-to-machine identities may be introduced later as separate OAuth clients with explicit
scopes.

Service identities:

- are not human users;
- do not receive human roles for convenience;
- must have narrowly defined audiences and scopes; and
- require a separate approved design before implementation.

Service identities are outside the current implementation scope.

## Identity identifiers

The backend will assign every application user an immutable UUID.

Domain records must refer to the backend UUID rather than:

- an email address;
- a Keycloak subject by itself;
- a username;
- a phone number; or
- another mutable identity attribute.

An external identity is uniquely identified by:

```text
issuer + subject
```

These values correspond to the validated OIDC `iss` and `sub` claims.

Both values are required because a subject is unique only within its issuer. The database must
enforce uniqueness for the combination of issuer and subject.

### Email addresses

Email addresses:

- are contact and login attributes;
- may change;
- must not be used as immutable identifiers;
- must not be used as domain foreign keys;
- must not be used alone to link accounts; and
- are considered verified only when the identity provider supplies a validated
  `email_verified = true` claim.

Automatic account linking based only on matching email addresses is prohibited.

A future account-linking workflow must require proof of control of both identities and a
separate security review.

## Registration and role assignment

### End-user registration

A verified registered end user receives the `patient` role by default.

In this identity model, `patient` is the proposal-defined name for the registered end-user role.
Receiving the role does not establish a diagnosis, clinician relationship, or access to an
external record.

The exact registration flow must be defined in a follow-up story.

The following require separate product decisions before implementation where applicable:

- minimum user age;
- parental or guardian consent;
- anonymous access;
- identity proofing;
- duplicate-account handling;
- account linking;
- collection of health-related information; and
- association with external records.

### Clinician role assignment

Users must not self-assign the `clinician` role.

Clinician access requires a privileged onboarding and verification workflow.

The implementation must record:

- who approved the clinician;
- when approval occurred;
- the verification status;
- the verification method or reference;
- subsequent status changes; and
- revocation or expiration where applicable.

The `clinician` role does not automatically grant access to:

- all end-user accounts;
- another user's conversations;
- documents belonging to another user;
- administrative functions; or
- functionality that has not been explicitly designed.

Initially, clinician permissions must be limited to workflows that have been explicitly
specified and approved.

Before identifiable user information is exposed to clinicians, the project must define:

- the purpose of access;
- the applicable relationship or authorization;
- whether user consent is required;
- the minimum information required;
- retention requirements;
- audit requirements; and
- revocation behavior.

### Administrator role assignment

Users must not self-assign the `admin` role.

Admin assignment requires a privileged and audited workflow.

The system must record:

- the actor assigning the role;
- the target user;
- the assignment time;
- the reason or approval reference; and
- subsequent removal of the role.

The `admin` role permits only explicitly approved operational and identity-management
functions.

It does not implicitly grant access to:

- another user's private content;
- clinician-only functionality;
- user documents;
- user conversations; or
- other protected domain resources.

The system must prevent removal or disablement of the last usable administrator unless an
approved recovery process exists.

Any support-access or impersonation feature requires a separate, time-limited, purpose-bound,
and audited design.

## Role representation

Keycloak will place application roles in a namespaced custom access-token claim using a
protocol mapper.

The placeholder claim is:

```text
https://api.cardiosmart.example/roles
```

The production API namespace must replace this placeholder before implementation. It must use a
stable namespace controlled by the project and must not conflict with reserved claims.

An example role claim is:

```json
{
  "https://api.cardiosmart.example/roles": [
    "patient",
    "clinician"
  ]
}
```

The only initially recognized human role values are:

```text
patient
clinician
admin
```

The backend must validate that the role claim has the expected structure.

Missing, unknown, duplicate, or malformed role values must not grant permissions.

Roles provide coarse-grained authorization. Backend-owned resource checks remain authoritative
for deciding whether a user may act on a specific resource.

## Authorization model

Authorization is denied by default.

A protected request is allowed only when all applicable checks succeed:

1. The request is authenticated.
2. The account is active.
3. The session has not expired or been revoked.
4. The user has an explicitly accepted role for the operation.
5. The user is authorized for the requested resource.
6. Any operation-specific requirements are satisfied.

A role check alone is not sufficient where an operation targets a specific user or protected
resource.

### Initial authorization matrix

This matrix defines the safe baseline while detailed workflows remain undecided.

| Capability | Patient | Clinician | Admin | Anonymous |
| --- | --- | --- | --- | --- |
| Read own account | Yes | Yes | Yes | No |
| Update own permitted account fields | Yes | Yes | Yes | No |
| Use approved end-user features | Yes | Only if explicitly allowed | No implicit access | Not yet decided |
| Read another user's private content | No | Not until explicitly designed | No implicit access | No |
| Use approved clinician workflows | No | Yes, when explicitly defined | No implicit access | No |
| Assign clinician role | No | No | Through an audited workflow | No |
| Assign admin role | No | No | Through an audited workflow | No |
| Manage operational account status | No | No | Where explicitly allowed | No |
| Bypass resource checks | No | No | No | No |

Future implementation stories must define resource-level authorization for every protected
operation.

The existence of a role does not by itself authorize access to another user's resources.

## Identity-provider decision

### Selected approach: self-hosted Keycloak

CardioSmart will use a self-hosted Keycloak deployment as its OAuth 2.0 and OpenID Connect
provider.

Interactive browser login will use Authorization Code Flow with PKCE.

The backend must use:

- the configured Keycloak realm's discovery metadata;
- an exact expected issuer;
- an exact expected API audience;
- approved redirect URIs;
- approved post-logout redirect URIs; and
- approved web origins.

Keycloak's hosted login pages will own:

- credential collection;
- password hashing;
- email verification;
- password reset;
- multifactor authentication;
- brute-force protection;
- common-password denylisting; and
- provider-side refresh-token controls.

The backend must not receive, persist, log, or verify user passwords.

### Rationale

Keycloak is preferred because it provides open-source support for:

- OAuth 2.0 and OpenID Connect;
- Authorization Code Flow with PKCE;
- hosted credential entry;
- email verification;
- password recovery;
- multifactor authentication;
- brute-force protection;
- common-password denylisting;
- signing-key rotation through JWKS;
- role and custom-claim integration; and
- rotating refresh tokens with reuse detection.

This avoids implementing credential handling inside the backend while keeping the identity
provider under project control.

Self-hosting Keycloak introduces operational responsibility for:

- deployment and availability;
- security hardening and patching;
- upgrades and compatibility testing;
- PostgreSQL backup and recovery;
- monitoring and alerting;
- signing-key management and rotation; and
- capacity planning.

These responsibilities must have explicit owners before production deployment.

### Open-source and cost requirements

The selected identity design uses software available under open-source licenses and requires no
identity-provider software licensing fees:

- Keycloak is licensed under Apache License 2.0;
- PostgreSQL uses the PostgreSQL License;
- the FastAPI framework is licensed under the MIT License; and
- OAuth 2.0, OpenID Connect, JWT, JWKS, PKCE, TOTP, WebAuthn, and RS256 are open standards.

Keycloak must be self-hosted. No proprietary identity-provider service is required.

“No licensing fee” does not mean “no operating cost.” Compute, storage, email delivery, backups,
monitoring, network traffic, and engineering operations still consume project resources. Any
additional component selected for deployment, secrets, monitoring, email, or backups must also
be available under an approved open-source license.

## Alternatives considered

### Self-built JWT authentication using PyJWT and Argon2

Rejected.

This approach would make the backend responsible for:

- credential storage;
- password hashing parameters and upgrades;
- account recovery;
- email verification;
- multifactor authentication;
- breached-password detection;
- rate limiting;
- bot and brute-force defenses;
- token issuance;
- signing-key generation and rotation;
- session revocation; and
- ongoing authentication security maintenance.

Using established libraries would not remove the architectural and operational responsibility
of building and maintaining an identity provider.

### Auth0

Rejected.

Auth0 provides mature managed identity functionality, but the hosted service is proprietary and
may require paid plans as usage or feature requirements grow. It does not satisfy the project's
requirement to use only free and open-source identity software.

### Amazon Cognito

Rejected for the initial implementation.

Cognito is a proprietary managed service tied to AWS. It does not satisfy the open-source
requirement and would introduce cloud coupling.

### Future provider changes

A future provider change is permitted if it:

- preserves the backend's OAuth 2.0 and OIDC boundary;
- preserves backend-owned user UUIDs;
- includes a migration plan;
- updates this decision document; and
- receives backend CODEOWNER approval.

Domain code must not depend directly on Keycloak SDK objects or Keycloak-specific user
identifiers.

## Authentication flow

The initial browser authentication flow is:

1. The browser starts login through a backend Auth endpoint.
2. The backend creates and stores the required state, nonce, and PKCE values.
3. The user is redirected to the Keycloak-hosted login page.
4. Keycloak authenticates the user.
5. Keycloak redirects to the backend's exact allow-listed callback URI.
6. The backend validates the callback state.
7. The backend exchanges the authorization code using PKCE.
8. The backend validates the returned identity and access-token data.
9. The backend resolves or creates the backend user using validated `iss` and `sub`.
10. The backend creates a server-side session.
11. The backend stores the refresh token encrypted in PostgreSQL.
12. The backend returns an opaque session cookie to the browser.

Authorization codes, access tokens, refresh tokens, and ID tokens must not be placed in browser
URLs after callback processing.

The backend must prevent login CSRF, authorization-code replay, open redirects, and reuse of
state or nonce values.

Native applications and other public clients are outside the initial browser-session decision
and require a separate review before support is added.

## Access-token policy

Access tokens will have a 15-minute lifetime.

The backend will accept identity and role claims only from tokens that pass all required
validation.

Required validation includes:

- cryptographic signature validation;
- an explicitly allowed asymmetric algorithm, initially RS256;
- exact issuer validation;
- exact API audience validation;
- expiration validation;
- not-before validation when present;
- required subject validation;
- expected token type and purpose; and
- expected role-claim structure.

The backend must:

- obtain signing keys from the configured Keycloak realm's JWKS endpoint;
- cache JWKS responses using a bounded policy;
- support normal signing-key rotation;
- refresh JWKS once when an unknown key ID is encountered;
- reject the token if the key remains unknown;
- fail closed when identity configuration or signing keys cannot be validated;
- never use signature-disabled or decode-only token handling;
- never choose an accepted algorithm solely from an untrusted token header;
- never accept an ID token in place of an API access token;
- never accept tokens from arbitrary issuers;
- never accept tokens for a different audience; and
- never log complete tokens or authorization headers.

Any allowed clock skew must be small and explicitly configured.

## Session and refresh-token policy

### Lifetimes

| Item | Lifetime |
| --- | --- |
| Access token | 15 minutes |
| Server-side session idle lifetime | 30 days |
| Server-side session absolute lifetime | 90 days |
| Refresh token | Rotating and bounded by the session limits |

A session ends when any applicable limit is reached.

Activity must not extend a session beyond its absolute lifetime.

### Refresh-token rotation

Keycloak refresh-token rotation and reuse detection must be enabled by setting refresh-token
revocation on and the permitted refresh-token reuse count to zero.

After a successful refresh:

1. The prior refresh token is invalidated.
2. The newly returned refresh token replaces it transactionally.
3. Rotation metadata is updated.
4. The session's last-used time is updated.
5. Updated identity and role claims are validated before use.

Reuse or replay of an invalidated refresh token must revoke:

- the affected token family where supported; and
- the corresponding backend session.

Concurrent refresh attempts must be serialized or otherwise coordinated so that ordinary
client concurrency does not cause false token-reuse events.

### Storage decision: PostgreSQL

Backend-managed refresh sessions will be stored in PostgreSQL, not Redis.

PostgreSQL is selected because:

- it is already part of the repository architecture;
- session revocation must survive application restarts;
- session and revocation records require durable storage;
- authentication events require durable audit references; and
- introducing Redis solely for authentication would add unapproved infrastructure and
  operational responsibility.

A session record should contain only data required for session management, including:

- a backend session identifier;
- the backend user UUID;
- the external issuer and subject;
- the refresh token encrypted at rest;
- the current role snapshot and its expiration;
- session creation time;
- last-use time;
- idle expiration time;
- absolute expiration time;
- refresh-token rotation metadata;
- revocation time;
- revocation reason; and
- limited client metadata where approved.

The opaque session value sent to the browser must not be stored in plaintext. The database
should store a cryptographic hash or keyed digest so that a database disclosure does not
directly expose usable cookie credentials.

Refresh tokens must:

- be encrypted before persistence;
- never be stored in plaintext logs;
- never be included in exceptions or error responses;
- never be added to metrics or traces;
- never be returned to browser JavaScript;
- never be stored in browser local storage;
- never be stored in browser session storage; and
- be redacted from administrative and support tooling.

The refresh-token encryption key must be supplied through an approved open-source
secret-management system or secure environment injection.

The key must not be stored in:

- PostgreSQL;
- the source repository;
- a committed environment file;
- a container image; or
- application logs.

Key rotation, key versioning, and re-encryption procedures must be defined before production
deployment.

## Browser session cookie

Browser clients will receive an opaque session cookie rather than a refresh token.

The cookie must use:

- `HttpOnly`;
- `Secure`;
- `SameSite=Lax` unless an approved client design requires another setting;
- a narrow domain;
- a narrow path where practical;
- an explicit expiration aligned with session policy; and
- a cryptographically random value with sufficient entropy.

The session identifier must be rotated after successful authentication and after any relevant
privilege change.

Cookie-authenticated state-changing requests require CSRF protection.

CORS configuration does not replace CSRF protection.

The final production cookie name, domain, callback origins, and cross-origin behavior must be
approved before implementation.

## Logout and revocation

Logout must:

1. revoke the backend session;
2. remove the browser session cookie;
3. make the session identifier unusable; and
4. revoke the corresponding Keycloak client session and refresh grant.

The backend must support:

- revoking one session;
- revoking all sessions for a user;
- revoking sessions after credential recovery;
- revoking sessions after MFA recovery;
- disabling a user;
- revoking a token family after refresh-token reuse;
- revoking sessions after a high-risk role change; and
- recording the actor, target, time, and reason for administrative revocation.

Revocation must fail closed. A revoked session must not be silently recreated from a revoked or
superseded refresh grant.

## Role changes

Role changes must take full effect no later than the 15-minute access-token expiration.

The following changes require immediate revocation of all affected sessions:

- removal of `admin`;
- removal of `clinician`;
- account disablement;
- suspected account compromise;
- confirmed refresh-token reuse; and
- administrative security reset.

After revocation, the user must authenticate again before receiving a new session.

A role claim must not bypass a current backend resource restriction.

## Password policy

Passwords are managed by Keycloak's hosted login and account-recovery flows.

The backend will not:

- collect passwords;
- store password hashes;
- implement password verification;
- send password-reset emails directly; or
- expose password credentials to application code.

The Keycloak realm password and brute-force policies must be configured to:

- require a minimum password length of 12 characters;
- permit long passphrases of at least 64 characters;
- avoid arbitrary composition requirements;
- block common passwords using a locally managed denylist;
- apply login rate limiting;
- enable brute-force protection;
- avoid forced periodic password expiration;
- use expiring, single-use password-reset links; and
- require verified email before normal application access.

Passwords should be changed when compromise is suspected or confirmed, not solely because a
fixed number of days has elapsed.

Password-reset and account-recovery responses must not disclose whether an account exists.

Federated identity, enterprise connections, passkeys, and passwordless authentication may be
evaluated later without changing the backend's OIDC boundary.

## Multifactor authentication

MFA is:

- required for clinicians;
- required for administrators;
- strongly encouraged for patients; and
- required as step-up authentication for sensitive account changes where supported.

Sensitive account changes include:

- changing the primary email address;
- changing MFA settings;
- starting account recovery;
- assigning or removing privileged roles; and
- other operations identified by the security review.

Approved MFA methods and recovery procedures must be decided before production deployment.

Recovery must not allow support staff to bypass identity verification without an approved and
audited process.

## Account status

The backend must maintain an application account status independent of the external identity
provider.

At minimum, the status model must distinguish:

- active;
- disabled; and
- pending any required application approval.

A valid Keycloak session does not override a disabled backend account.

Every authenticated request must resolve to an active backend user before protected access is
granted.

The exact lifecycle for deletion, suspension, reactivation, and retention requires a follow-up
decision.

## Authentication and authorization audit requirements

Security-relevant events must produce structured audit events without including credentials,
tokens, or session-cookie values.

Events include:

- login success;
- login failure;
- invalid callback state;
- authorization-code exchange failure;
- token-validation failure;
- logout;
- token refresh;
- refresh-token reuse detection;
- session creation;
- session revocation;
- account disablement and reactivation;
- email-verification state changes;
- MFA enrollment and recovery;
- role assignment;
- role removal;
- clinician verification;
- password-reset initiation and completion metadata;
- administrative identity actions; and
- denied authorization decisions for sensitive operations.

Audit events should record:

- timestamp;
- event type;
- backend user UUID when known;
- external issuer and subject reference when appropriate;
- session or correlation identifier;
- actor and target for administrative actions;
- outcome;
- reason code; and
- request metadata permitted by the privacy and retention policy.

Audit logs must not contain:

- passwords;
- authorization codes;
- access tokens;
- refresh tokens;
- ID tokens;
- cookie values;
- MFA secrets;
- password-reset tokens; or
- unnecessary private user content.

Audit retention, access control, tamper resistance, and alerting require separate operational
decisions.

## Privacy and identity-service operations review

Before production use, the project must review:

- what identity data Keycloak stores;
- where identity data, logs, and backups are stored;
- retention and deletion behavior;
- realm-administrator access;
- database-administrator access;
- infrastructure and support access;
- backup encryption and restoration testing;
- signing-key generation, storage, and rotation;
- security patch and version-upgrade ownership;
- availability and disaster-recovery requirements;
- monitoring and alerting; and
- export and migration procedures.

Self-hosting keeps identity data within project-controlled infrastructure but does not remove
privacy, security, retention, or access-control responsibilities.

This document does not claim compliance with HIPAA, GDPR, or another regulatory framework.
Compliance and legal review must be performed separately.

## Configuration

Implementation will require configuration equivalent to:

- Keycloak base URL;
- Keycloak realm name;
- OIDC issuer;
- API audience;
- client ID;
- client secret for the confidential backend client;
- authorized callback URLs;
- authorized post-logout redirect URLs;
- allowed web origins;
- role-claim namespace;
- allowed signing algorithms;
- JWKS cache limits;
- permitted token clock skew;
- access-token lifetime expectations;
- session idle lifetime;
- session absolute lifetime;
- cookie name;
- cookie domain;
- cookie path;
- cookie security settings;
- refresh-token encryption-key reference;
- Keycloak administrative service-account credentials where an approved workflow requires
  them; and
- Keycloak database connection settings supplied to the Keycloak deployment.

Secrets must not have default values that can accidentally be used in production.

The application must fail closed with an actionable configuration error when required identity
settings are missing or inconsistent.

Environment names and configuration structure will be defined by an implementation story after
this design is accepted.

## Availability and failure behavior

Authentication must fail closed when:

- identity configuration is missing;
- token signature validation fails;
- the issuer is unexpected;
- the audience is unexpected;
- required claims are missing;
- the token has expired;
- signing keys cannot be safely resolved;
- the session has expired;
- the session has been revoked;
- the backend user is missing or disabled; or
- the refresh operation fails.

An identity-provider outage may prevent new logins and token refreshes.

Existing requests may continue only while their current validated authentication state remains
within its approved lifetime. The backend must not extend token or session validity merely
because the provider is unavailable.

Error responses must not expose token contents, provider secrets, signing-key details, or
unnecessary account information.

## Security requirements

The implementation must:

- use TLS in production;
- reject non-HTTPS production callback and logout URLs;
- allow-list exact redirect destinations;
- prevent open redirects;
- use cryptographically secure random state, nonce, PKCE, and session values;
- make state and nonce values single-use and short-lived;
- rotate session identifiers after authentication and privilege changes;
- apply rate limits to authentication-sensitive endpoints;
- avoid account enumeration;
- redact credentials and tokens from logs and traces;
- separate development and production identity tenants or applications;
- use least-privilege Keycloak realm-management permissions;
- document secret and signing-key rotation procedures.

Placeholder configuration or incomplete security controls must not be represented as
production-ready.

## Testing requirements

Implementation stories must add tests appropriate to the behavior they introduce.

The Auth test plan must cover at least:

- successful login;
- invalid callback state;
- replayed callback state;
- authorization-code exchange failure;
- invalid token signature;
- unsupported token algorithm;
- unknown signing key;
- wrong issuer;
- wrong audience;
- expired token;
- missing subject;
- malformed role claim;
- unknown role;
- disabled backend account;
- expired session;
- revoked session;
- idle-session expiration;
- absolute-session expiration;
- successful refresh-token rotation;
- refresh-token reuse;
- concurrent refresh handling;
- logout;
- per-session revocation;
- global user revocation;
- clinician and administrator MFA enforcement;
- denial when a role is absent;
- denial when resource authorization fails;
- CSRF protection;
- secure cookie attributes;
- prevention of account enumeration; and
- redaction of tokens and credentials from logs.

Integration tests must not depend on a production Keycloak realm.

Tests may use a disposable containerized Keycloak instance, test doubles, or a dedicated
non-production realm, subject to the implementation test strategy.

## Non-goals

This decision does not define:

- detailed endpoint request and response contracts;
- anonymous product functionality;
- patient identity proofing;
- clinician credential-verification procedures;
- complete clinician-facing workflows;
- clinician relationships with end users;
- administrator support-access workflows;
- organization or tenant isolation;
- machine-to-machine authorization;
- native application token storage;
- account deletion and retention policy;
- audit-log retention;
- production Keycloak deployment automation;
- production secret-management infrastructure; or
- regulatory compliance status.

These items require follow-up decisions or implementation stories.

## Open items blocking implementation

The following must be resolved before the affected implementation work begins:

- confirmation that CardioGuard AI and CardioSmart refer to the same project;
- the canonical project name;
- the supported Keycloak version and upgrade policy;
- the production Keycloak deployment topology;
- the Keycloak realm name and issuer;
- the final API audience;
- the production role-claim namespace;
- Keycloak database, backup, monitoring, patching, and availability ownership;
- supported client types;
- approved origins;
- approved callback URLs;
- approved logout URLs;
- the production open-source secret-management or secure injection approach;
- refresh-token encryption and key-rotation ownership;
- whether any unauthenticated functionality is permitted;
- whether `patient` remains the role name for registered general-public users;
- the minimum user age and guardian-consent policy;
- clinician verification requirements;
- exact clinician permissions;
- exact administrator permissions;
- account deletion and identity-data retention rules;
- approved MFA and recovery methods;
- last-administrator recovery rules; and
- audit-event retention and access controls.

Implementation stories may resolve these items, but they must not silently invent them.

## Implementation consequences

Under this decision:

- `backend/auth/authentication.py` may implement the OIDC and session behavior.
- `backend/auth/authorization.py` may implement role and resource authorization dependencies.
- Persistence work may add backend user, external identity, and session tables.
- Auth API routes may replace the current HTTP 501 placeholder.
- Configuration may add identity, token, session, cookie, and encryption settings.
- Tests must cover authentication success, validation failures, authorization denial,
  expiration, rotation, revocation, role changes, and browser protections.
- Keycloak-specific behavior should remain isolated behind the backend authentication boundary.
- Domain services should consume a backend principal rather than Keycloak SDK objects.
- Domain records should refer to the backend user UUID rather than Keycloak identifiers.

Implementation of affected areas must wait until the relevant blocking decisions are resolved
or assigned to explicit follow-up stories.

## Requirements for follow-up Auth stories

Every Auth Jira story must:

1. Link to the merged `docs/identity-design.md`.
2. State whether it implements this decision or intentionally deviates from it.
3. Identify the relevant section of this document.
4. Include security-focused acceptance criteria.
5. Include appropriate unit or integration tests.
6. Obtain decision-owner approval for any deviation.
7. Update this document in the same or a preceding approved pull request when the decision
   changes.

Auth stories must not infer a clinician-facing workflow merely from the existence of the
`clinician` role.

A story that grants clinicians access to identifiable end-user information must reference an
approved:

- workflow;
- access purpose;
- resource-authorization rule;
- privacy basis;
- retention requirement; and
- audit requirement.

Expected follow-up stories include:

- Deploy and configure Keycloak using open-source infrastructure components.
- Define Keycloak operations, backups, monitoring, patching, and disaster recovery.
- Add identity-related application configuration.
- Add backend user and external-identity persistence.
- Add authentication-session persistence.
- Implement end-user registration and provisioning.
- Define whether anonymous access is supported.
- Define minimum-age and guardian-consent requirements.
- Implement privileged clinician verification and role assignment.
- Define clinician permissions and workflows.
- Implement privileged administrator role assignment.
- Define administrator permissions.
- Implement Authorization Code Flow with PKCE.
- Implement login callback and server-side sessions.
- Implement refresh-token encryption, rotation, and reuse handling.
- Implement JWT validation and JWKS caching.
- Implement authentication dependencies and backend principals.
- Implement role checks and resource-level authorization.
- Implement logout and per-session revocation.
- Implement global user revocation.
- Implement role synchronization and high-risk role-change revocation.
- Configure password, MFA, and abuse-prevention policies.
- Implement CSRF protection and secure browser cookies.
- Add authentication and authorization audit events.
- Add Auth unit, integration, and end-to-end tests.
- Complete an Auth-specific threat model and security review.
- Define account deletion, retention, and recovery behavior.

Product and engineering owners must update all existing Auth Jira stories with this reference
after the document is merged.

## Definition of done

The `[Auth] Agree the identity design` ticket is complete when:

- this document is merged to `main`;
- open implementation decisions are assigned to explicit follow-up stories;
- every existing Auth Jira story links to this document;
- every existing Auth Jira story states whether it conforms to this decision; and
- deviations require an updated design decision and decision-owner approval.
