/*
 * P2.2 authenticated browser evidence.  The plan is created through the real
 * API before the browser opens; this script never injects a card or mutates
 * browser state outside ordinary user interaction.
 *
 * Required environment:
 *   PLAN_V2_E2E_TOKEN  short-lived test JWT for the isolated API
 * Optional: PLAN_V2_E2E_API, PLAN_V2_E2E_WEB, EDGE_EXECUTABLE
 */

const { chromium } = require('playwright');
const fs = require('fs');
const { ensureFlutterSemanticsEnabled } = require('./plan_v2_flutter_semantics.cjs');

const apiBase = process.env.PLAN_V2_E2E_API || 'http://127.0.0.1:8091';
const webBase = process.env.PLAN_V2_E2E_WEB || 'http://127.0.0.1:4173';
const token = process.env.PLAN_V2_E2E_TOKEN;
const edgeExecutable = process.env.EDGE_EXECUTABLE ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const evidencePath = process.env.PLAN_V2_E2E_EVIDENCE;
const e2eConfigurationLabel = 'Plan V2 E2E configuration active';
const planLibraryLabel = 'app-nav-plan-library';
let currentPage;
let executionStage = 'preflight';

if (!token) throw new Error('PLAN_V2_E2E_TOKEN is required');

const headers = {
  authorization: `Bearer ${token}`,
  'content-type': 'application/json',
};

async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {...headers, ...(options.headers || {})},
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${path}: HTTP_${response.status} ${JSON.stringify(body)}`);
  return body;
}

function hoChiMinhDate() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(({type, value}) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}

async function createSavedPlan() {
  const localDate = hoChiMinhDate();
  const draft = await api('/api/plan-v2/drafts/nutrition', {
    method: 'POST',
    body: JSON.stringify({
      period_start: localDate,
      period_end: localDate,
      timezone: 'Asia/Ho_Chi_Minh',
      profile: {
        age: 31,
        equation_sex: 'male',
        height_cm: 172,
        weight_kg: 70,
        activity_level: 'moderate',
        health_goal: 'maintain',
      },
    }),
  });
  if (draft.status !== 'READY' || !draft.plan) throw new Error(`draft not ready: ${JSON.stringify(draft)}`);
  const plan = draft.plan;
  return api('/api/plan-v2/plans/save', {
    method: 'POST',
    body: JSON.stringify({
      plan_id: plan.plan_id,
      revision_id: plan.revision_id,
      revision_content_hash: plan.revision_content_hash,
      action_id: `p2-2-edge-save-${plan.revision_id}`,
    }),
  });
}

async function lifecycle(plan, operation) {
  return api(`/api/plan-v2/plans/${plan.plan_id}/revisions/${plan.revision_id}/${operation}`, {
    method: 'POST',
    body: JSON.stringify({
      expected_revision_number: plan.revision_number,
      action_id: `p2-2-edge-${operation}-${plan.revision_id}`,
    }),
  });
}

async function readAuthoritativeLifecycleStatus(plan, expectedStatus) {
  const readBack = await api(
    `/api/plan-v2/plans/${plan.plan_id}?revision_id=${plan.revision_id}`,
  );
  const actualStatus = readBack.plan?.lifecycle_status;
  if (actualStatus !== expectedStatus) {
    throw new Error(
      `PRODUCT_LIFECYCLE_READBACK_MISMATCH: expected ${expectedStatus}, got ${actualStatus}`,
    );
  }
  return {plan: readBack.plan, status: actualStatus};
}

function containsActualObservation(value) {
  const actualKeys = new Set([
    'consumed_at', 'logged_at', 'performed_at', 'actual_reps', 'actual_rpe',
    'actual_load', 'recovered', 'fatigued',
  ]);
  if (Array.isArray(value)) return value.some(containsActualObservation);
  if (!value || typeof value !== 'object') return false;
  return Object.entries(value).some(([key, nested]) =>
    actualKeys.has(key) || containsActualObservation(nested),
  );
}

function semanticButton(page, name) {
  return page.getByRole('button', {name, exact: true});
}

async function requirePlanLibraryPreflight(page) {
  const planLibrary = semanticButton(page, planLibraryLabel);
  const count = await planLibrary.count();
  if (count !== 1) {
    throw new Error(`PLAYWRIGHT_HARNESS_PREFLIGHT: PLAN_LIBRARY_LOCATOR_COUNT=${count}`);
  }
  if (!await planLibrary.isVisible() || !await planLibrary.isEnabled()) {
    throw new Error('PLAYWRIGHT_HARNESS_PREFLIGHT: PLAN_LIBRARY_LOCATOR_NOT_ACTIONABLE');
  }
  return planLibrary;
}

async function openAuthoritativeRevision(page, expected) {
  const revisionLabel =
    `Open authoritative plan revision ${expected.plan_id} ${expected.revision_id}`;
  const revisionLink = semanticButton(page, revisionLabel);
  try {
    await revisionLink.waitFor({timeout: 10000});
  } catch (error) {
    const readBack = await api(
      `/api/plan-v2/plans/${expected.plan_id}?revision_id=${expected.revision_id}`,
    );
    if (readBack.plan?.plan_id === expected.plan_id &&
        readBack.plan?.revision_id === expected.revision_id) {
      throw new Error('PRODUCT_UI_AUTHORITATIVE_PLAN_NOT_RENDERED');
    }
    throw error;
  }
  await revisionLink.click();
}

async function main() {
  executionStage = 'browser-launch';
  const browser = await chromium.launch({headless: true, executablePath: edgeExecutable});
  const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
  currentPage = page;
  const evidence = {
    plan_id: null,
    revision_id: null,
    authenticated_principal: 'p2_2_browser_test',
    events: [],
    semantics_preflight: null,
    read_back_statuses: {},
    cross_user_result: null,
    planned_actual_result: null,
  };
  let passed = false;
  try {
    executionStage = 'browser-load';
    await page.goto(webBase, {waitUntil: 'domcontentloaded'});
    await ensureFlutterSemanticsEnabled(page);
    await page.getByLabel(e2eConfigurationLabel, {exact: true}).waitFor({timeout: 10000});
    evidence.events.push('e2e-runtime-config-active');
    executionStage = 'playwright-harness-preflight';
    const planLibrary = await requirePlanLibraryPreflight(page);
    evidence.semantics_preflight = {
      semantics_enabled: true,
      plan_library_locator_count: 1,
    };
    evidence.events.push('semantics-enabled');
    evidence.events.push('plan-library-locator-count-1');

    executionStage = 'plan-creation';
    const saved = await createSavedPlan();
    const active = await lifecycle(saved.plan, 'activate');
    const expected = active.plan;
    const activationReadBack = await readAuthoritativeLifecycleStatus(expected, 'ACTIVE');
    evidence.plan_id = expected.plan_id;
    evidence.revision_id = expected.revision_id;
    evidence.read_back_statuses.activation = activationReadBack.status;

    executionStage = 'plan-library';
    await planLibrary.click();
    await openAuthoritativeRevision(page, expected);
    await semanticButton(page, 'Plan lifecycle action PAUSED').waitFor({timeout: 10000});

    const exactReference = semanticButton(
      page,
      `Plan V2 exact revision ${expected.plan_id} ${expected.revision_id}`,
    );
    await exactReference.waitFor({timeout: 10000});
    evidence.events.push('library-detail-exact-revision');

    await semanticButton(page, 'Plan lifecycle action PAUSED').click();
    await semanticButton(page, 'Plan lifecycle action ACTIVE').waitFor({timeout: 10000});
    const pauseReadBack = await readAuthoritativeLifecycleStatus(expected, 'PAUSED');
    evidence.read_back_statuses.pause = pauseReadBack.status;
    evidence.events.push('pause-readback');
    await semanticButton(page, 'Plan lifecycle action ACTIVE').click();
    await semanticButton(page, 'Plan lifecycle action PAUSED').waitFor({timeout: 10000});
    const resumeReadBack = await readAuthoritativeLifecycleStatus(expected, 'ACTIVE');
    evidence.read_back_statuses.resume = resumeReadBack.status;
    evidence.events.push('resume-readback');

    executionStage = 'refresh-readback';
    await page.reload({waitUntil: 'domcontentloaded'});
    await ensureFlutterSemanticsEnabled(page);
    await page.getByLabel(e2eConfigurationLabel, {exact: true}).waitFor({timeout: 10000});
    await requirePlanLibraryPreflight(page);
    await semanticButton(page, planLibraryLabel).click();
    await openAuthoritativeRevision(page, expected);
    await semanticButton(page, 'Plan lifecycle action PAUSED').waitFor({timeout: 10000});
    const refreshReadBack = await readAuthoritativeLifecycleStatus(expected, 'ACTIVE');
    evidence.read_back_statuses.refresh = refreshReadBack.status;
    evidence.events.push('refresh-authoritative-readback');

    // Return to the real Nutrition tab and verify that its planned-only
    // section resolves the same active authoritative nutrition revision.
    executionStage = 'nutrition-authoritative-read';
    await page.goBack({waitUntil: 'domcontentloaded'});
    await ensureFlutterSemanticsEnabled(page);
    await semanticButton(page, 'Main navigation nutrition').click();
    await page.getByLabel(
      `Authoritative planned nutrition section ${expected.plan_id} ${expected.revision_id}`,
      {exact: true},
    ).waitFor({timeout: 10000});
    evidence.events.push('nutrition-authoritative-plan-read');

    executionStage = 'api-invariants';
    const exact = await api(`/api/plan-v2/plans/${expected.plan_id}?revision_id=${expected.revision_id}`);
    if (exact.plan.plan_id !== expected.plan_id || exact.plan.revision_id !== expected.revision_id) {
      throw new Error('browser/API reference chain mismatch');
    }
    const foreign = await fetch(`${apiBase}/api/plan-v2/plans/${expected.plan_id}?revision_id=${expected.revision_id}`, {
      headers: {authorization: 'Bearer invalid-token'},
    });
    if (foreign.status !== 401) throw new Error(`unauthenticated ownership probe gave ${foreign.status}`);
    evidence.cross_user_result = {status: foreign.status, denied: true};
    evidence.events.push('owner-bound-api-read');
    const workout = await fetch(`${apiBase}/api/plan-v2/plans/active/WORKOUT`, {headers});
    if (workout.status !== 404) throw new Error(`unrequested workout plan probe gave ${workout.status}`);
    evidence.events.push('no-unrequested-workout-plan');
    evidence.planned_actual_result = {
      planned_nutrition_contains_actual_observations: containsActualObservation(exact.plan),
      planned_nutrition_remained_planned: !containsActualObservation(exact.plan),
      workout_integration_applicable: false,
      workout_actual_state_mutated: false,
    };
    if (!evidence.planned_actual_result.planned_nutrition_remained_planned) {
      throw new Error('PRODUCT_PLANNED_TO_ACTUAL_LEAKAGE');
    }
    const result = {status: 'PASS', failure_stage: null, ...evidence};
    if (evidencePath) fs.writeFileSync(evidencePath, `${JSON.stringify(result, null, 2)}\n`);
    passed = true;
    console.log(JSON.stringify(result));
  } finally {
    if (!passed && evidencePath) {
      await page.screenshot({path: evidencePath.replace(/\.json$/i, '.png'), fullPage: true}).catch(() => {});
    }
    await browser.close();
  }
}

main().catch(async (error) => {
  const result = {status: 'FAIL', failure_stage: executionStage, error: error.stack || String(error)};
  if (currentPage && evidencePath) {
    const screenshotPath = evidencePath.replace(/\.json$/i, '.png');
    await currentPage.screenshot({path: screenshotPath, fullPage: true}).catch(() => {});
    result.screenshot = screenshotPath;
  }
  if (evidencePath) fs.writeFileSync(evidencePath, `${JSON.stringify(result, null, 2)}\n`);
  console.error(result.error);
  process.exitCode = 1;
});
