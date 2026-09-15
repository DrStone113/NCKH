# Firebase architecture

## Scope

This document records the audited Firebase boundary for the existing Health
App. It does not propose a second database for backend-owned domains.

Firebase project target: `healthcare-191d8`.

Actually supported Flutter platforms in this checkout:

- Android: package `com.example.app`.
- Web: an existing web configuration is referenced by `apps/mobile/firebase.json`.
- iOS/macOS: not supported in this checkout because no platform directories
  exist. The hand-written iOS/macOS entries in the current
  `firebase_options.dart` are not evidence of registered apps.

## Runtime audit

### Authentication and identity

Flutter uses `FirebaseAuth` for Email/Password and Google Sign-In. It sends the
Firebase ID token as an HTTP bearer token and as a WebSocket subprotocol.

The backend verifies RS256 Firebase tokens against Google's published signing
keys, with audience `healthcare-191d8` and issuer
`https://securetoken.google.com/healthcare-191d8`. The verified JWT `sub`
becomes `AuthenticatedPrincipal.user_id`. Owner-scoped PostgreSQL rows use this
same value. A `userId` supplied in an ordinary request body is never sufficient
proof of identity. HS256 tokens are limited to development/test mode.

Identity mapping:

```text
Firebase Auth uid
  -> Firebase ID token sub
  -> backend AuthenticatedPrincipal.user_id
  -> PostgreSQL owner/user_id columns
```

### Persistence

Flutter directly persists profiles and lightweight personal logs to Firestore.
The backend persists chat, Plan V2, personalized workout plans/results,
proactive state, RAG and adaptive nutrition state in PostgreSQL. Canonical
nutrition/exercise data is exposed by backend APIs and backed by versioned local
artifacts/materializations.

The mobile app already has domain models with `toMap`/`fromMap` boundaries for
users, body metrics, meals, exercises and lifestyle records. Existing raw maps
remain confined to provider/store persistence code; they must not spread into
UI contracts.

## Final data ownership matrix

| Domain | Primary authority | Notes |
|---|---|---|
| AUTH | FIREBASE_AUTH | Firebase uid is the cross-system principal. |
| PROFILE | FIRESTORE | `nguoi_dung/{uid}`, private and owner-scoped. |
| BODY_METRICS | FIRESTORE | `chi_so_co_the`, private and owner-scoped. |
| FOOD_CATALOG | EXISTING_BACKEND | Canonical/versioned data; never client-writable. |
| MEAL_LOG | FIRESTORE | `nhat_ky_an_uong`, current mobile persistence path. |
| EXERCISE_CATALOG | EXISTING_BACKEND | Wger/backend plus bounded local cache; no Firestore copy. |
| WORKOUT_LOG | FIRESTORE | `nhat_ky_tap_luyen`, current mobile persistence path. |
| PLAN_V2 | POSTGRESQL | Immutable revisions and lifecycle stay authoritative. |
| CHAT | POSTGRESQL | Sessions, messages, memory and tool audit stay backend-owned. |
| RAG | POSTGRESQL | Runtime knowledge chunks/embeddings remain backend-owned. |
| RESEARCH_DATA | IMMUTABLE_LOCAL_ARTIFACT | PostgreSQL research tables are controlled materializations. |
| REFERENCE_KNOWLEDGE | POSTGRESQL | Versioned/provenanced backend knowledge; no Dart copy. |

`lifestyle_logs`, `lifestyle_reminders` and `water_intake` are also private,
owner-scoped Firestore data because current Flutter runtime paths already use
them.

## Proposed Firestore mapping review

| Proposed collection | Decision | Actual boundary |
|---|---|---|
| `users` | MODIFY | Keep existing `nguoi_dung`; document ID must equal Firebase uid. |
| `body_metrics` | MODIFY | Keep existing `chi_so_co_the`; require owned `userId`. |
| `foods` | DO_NOT_CREATE | Backend canonical catalog remains authority. |
| `menus` / `menu_details` | DO_NOT_CREATE | Plan V2 PostgreSQL revisions remain authority. |
| `meal_logs` | MODIFY | Keep existing `nhat_ky_an_uong`; do not create a duplicate name. |
| `exercises` | DO_NOT_CREATE | Backend/local catalog remains authority. |
| `exercise_logs` | MODIFY | Keep existing `nhat_ky_tap_luyen`. |
| `chatbot_knowledge` | DO_NOT_CREATE | Backend RAG/reference architecture remains authority. |

No empty collections or production seed documents are created. Firestore is
schemaless; version-controlled rules, indexes and tests define its usable
contract.

## Firestore collections in scope

| Collection | Owner rule | Important limits |
|---|---|---|
| `nguoi_dung/{uid}` | path uid equals authenticated uid | identity, email and typed profile envelope validated |
| `chi_so_co_the/{id}` | `userId` equals authenticated uid | bounded weight/BMI; ISO timestamp string |
| `nhat_ky_an_uong/{id}` | `userId` equals authenticated uid | document ID matches payload ID; at most 100 items |
| `nhat_ky_tap_luyen/{id}` | `userId` equals authenticated uid | bounded duration/calories; document ID matches payload ID |
| `lifestyle_logs/{id}` | `userId` equals authenticated uid | bounded observations and notes |
| `lifestyle_reminders/{id}` | `userId` equals authenticated uid | bounded strings; document ID matches payload ID |
| `water_intake/{id}` | `userId` equals authenticated uid | positive bounded amount |

Reads, writes and queries against every other collection are denied to mobile
and web clients. Server/Admin SDK flows use IAM and bypass Firestore Security
Rules; they still require an explicit backend design before being introduced.

## Indexes

Only one composite index is derived from current code:

```text
chi_so_co_the: userId ASC, recordedAt DESC
```

Other current queries use a single `userId` equality filter and rely on normal
single-field indexes. Speculative indexes are not created.

## Offline, pagination and contention

- Critical profile refreshes and several log reads explicitly request the
  server. Other SDK reads may use normal Firestore offline caching.
- Logs are separate documents, avoiding unbounded arrays and single-document
  write contention.
- Meal `items` remains bounded by Rules. Plan revisions are not stored as meal
  arrays in Firestore.
- Existing providers fetch all owned meal/exercise logs then filter dates in
  memory. This is a known scalability debt; a future versioned migration should
  add timestamp-native fields and bounded date queries before changing indexes.
- Current timestamps are ISO strings created by the client. Moving to server
  timestamps requires a backwards-compatible model/data migration and is not
  silently performed by bootstrap.

## Security Rules and test coverage

Files:

- `firebase/firestore.rules`
- `firebase/firestore.indexes.json`
- `firebase/tests/firestore.rules.test.mjs`

The Emulator suite tests unauthenticated denial, own profile access,
cross-owner isolation, identity/shape rejection, body-metric query access,
forged owner rejection, ownership-transfer rejection, canonical catalog write
denial and the rule-bypassing server fixture path.

Run:

```powershell
.\scripts\firebase\run-emulator-tests.ps1
```

## Authentication provider configuration

`firebase/auth.providers.template.json` enables Email/Password and Google and
disables anonymous sign-in. Google requires a human-owned OAuth support email.
The bootstrap script inserts that value into a generated ignored config only
when `-DeployAuth -SupportEmail ...` is explicitly requested.

Provider deployment is scoped to `auth`. Firestore deployment is scoped to
`firestore`. No Hosting, Functions, Storage, user or data deletion operation is
present in the bootstrap.

## Android registration and FlutterFire

The source-of-truth Android package is read from the active Groovy Gradle file:
`com.example.app`. There are no product flavors. The inactive
`build.gradle.kts` contains a different identifier and must not be used for
Firebase registration.

The bootstrap obtains SHA values from the actual Gradle `signingReport`, never
from documentation. It can add missing fingerprints without deleting existing
ones, download the official `google-services.json`, and run FlutterFire against
Android and Web only.

`google-services.json` and generated auth deployment config are ignored by Git.
No OAuth credential is fabricated.

## Emulator integration in Flutter

The app connects to Auth and Firestore emulators only when compiled with:

```text
--dart-define=USE_FIREBASE_EMULATORS=true
```

The default is production connectivity. Android uses host alias `10.0.2.2`;
Web uses `127.0.0.1`.

## Seed and migration strategy

No production seed script is provided because no system/reference dataset is
owned by Firestore. Test documents are isolated Emulator fixtures. Existing
users and logs are not migrated or rewritten.

Any future real migration requires source/destination counts, stable Firebase
uid mapping, dry run, idempotency, rollback and readback validation.

## Environment separation

Only the existing project ID is declared. The bootstrap never creates another
Firebase project. Development/staging aliases may be added later only after the
owner supplies existing project IDs or explicitly authorizes project creation.

## Commands

```powershell
# local rules test; never touches production
.\scripts\firebase\run-emulator-tests.ps1

# cloud read-only audit after firebase login
.\scripts\firebase\bootstrap.ps1

# explicit scoped deployment examples
.\scripts\firebase\bootstrap.ps1 -ApplyCloud -DeployFirestore
.\scripts\firebase\bootstrap.ps1 -ApplyCloud -DeployAuth `
  -SupportEmail 'owner@example.com'
```

See `docs/guides/setup_firebase.md` for Android app/SHA/config provisioning.
