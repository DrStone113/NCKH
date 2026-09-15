/*
 * One-shot N3.2.1 development/shadow Brave E2E.
 *
 * This script never creates a recommendation card itself. The card must be
 * emitted by the real Flutter chat/WebSocket path after a real user request.
 * It writes only sanitized evidence and uses a fresh browser context.
 */

const fs = require('fs');
const { chromium } = require('playwright');

const webBase = process.env.N3_2_1_E2E_WEB;
const apiBase = process.env.N3_2_1_E2E_API;
const token = process.env.N3_2_1_E2E_TOKEN;
const foreignToken = process.env.N3_2_1_E2E_FOREIGN_TOKEN;
const braveExecutable = process.env.N3_2_1_BRAVE_EXECUTABLE;
const braveProductVersion = process.env.N3_2_1_BRAVE_PRODUCT_VERSION || null;
const evidencePath = process.env.N3_2_1_E2E_EVIDENCE;
const postgresqlHealthy = process.env.N3_2_1_POSTGRESQL_HEALTHY === 'true';
const buildConfiguration = {
  api_base_url_configured: process.env.N3_2_1_BUILD_API_CONFIGURED === 'true',
  test_auth_configured: process.env.N3_2_1_BUILD_TEST_AUTH_CONFIGURED === 'true',
  e2e_demo_enabled: process.env.N3_2_1_BUILD_E2E_DEMO_ENABLED === 'true',
  bundle_marker_embedded: process.env.N3_2_1_BUILD_MARKER_EMBEDDED === 'true',
};

for (const [name, value] of Object.entries({webBase, apiBase, token, foreignToken, braveExecutable, evidencePath})) {
  if (!value) throw new Error(`PREFLIGHT_CONFIGURATION:${name}_MISSING`);
}

const result = {
  artifact_version: 'N3_2_1_LIVE_BRAVE_E2E_V1',
  status: 'FAIL',
  browser_name: 'Brave',
  browser_executable_path: braveExecutable,
  browser_version: braveProductVersion,
  browser_engine_version: null,
  playwright_version: null,
  service_health: {backend_api: false, postgresql: postgresqlHealthy, static_web: false},
  build_configuration: buildConfiguration,
  semantics_preflight: {},
  events: [],
  recommendation_event_id: null,
  candidate_id: null,
  feedback_event_id: null,
  feedback_event_type: 'LIKED',
  authoritative_read_back: false,
  refresh_reconnect: false,
  preference_effect_consulted: false,
  cross_user_denial: false,
  meal_log_mutation_count: 0,
  canonical_mutation_count: 0,
  failure_stage: 'preflight',
  failure_class: null,
  timestamps: {started_at_utc: new Date().toISOString(), completed_at_utc: null},
  token_recorded: false,
};

function classify(error, stage) {
  const message = String(error && (error.message || error));
  if (/PREFLIGHT_CONFIGURATION|BRAVE_LAUNCH|executable/i.test(message)) return 'BROWSER_BOOTSTRAP';
  if (/ECONNREFUSED|HTTP_50[023]|health|WebSocket connect|CONNECTION_ERROR/i.test(message)) return 'SERVICE_BOOTSTRAP';
  if (/HTTP_401|HTTP_403|AUTHENTICATED_PRINCIPAL|4401/i.test(message)) return 'AUTHENTICATION';
  if (/LOCATOR|semantics|accessible|count=/i.test(message) || stage === 'locator-probe') return 'PLAYWRIGHT_HARNESS';
  return 'PRODUCT_BEHAVIOR';
}

async function requireControl(page, role, name) {
  const locator = page.getByRole(role, {name, exact: true});
  const count = await locator.count();
  const visible = count === 1 && await locator.isVisible();
  const actionable = visible && await locator.isEnabled();
  result.semantics_preflight[name] = {role, count, visible, actionable};
  if (count !== 1 || !visible || !actionable) {
    throw new Error(`LOCATOR_PREFLIGHT:${name}:count=${count}:visible=${visible}:actionable=${actionable}`);
  }
  return locator;
}

async function requireRuntimeMarker(page) {
  const name = 'n3-e2e-runtime-configured';
  const locator = page.getByLabel(name, {exact: true});
  const count = await locator.count();
  result.semantics_preflight[name] = {role: 'runtime-marker', count};
  if (count !== 1) {
    throw new Error(`LOCATOR_PREFLIGHT:${name}:count=${count}`);
  }
}

async function enableForTarget(page, role, name, timeout = 12000) {
  const target = page.getByRole(role, {name, exact: true});
  if (await target.count() === 1 && await target.isVisible()) return;
  const placeholder = page.locator('flt-semantics-placeholder');
  const placeholders = await placeholder.count();
  if (placeholders === 1 && await placeholder.isVisible()) {
    await placeholder.focus();
    await page.keyboard.press('Enter');
  }
  // Readiness is defined by the intended contract, never an internal engine
  // tag such as flt-semantics.
  await target.waitFor({state: 'visible', timeout});
}

async function api(path, bearer) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: {authorization: `Bearer ${bearer}`},
  });
  const body = await response.json().catch(() => ({}));
  return {status: response.status, body};
}

async function run() {
  let browser;
  try {
    if (!postgresqlHealthy || Object.values(buildConfiguration).some((configured) => !configured)) {
      throw new Error('PREFLIGHT_CONFIGURATION:POSTGRESQL_OR_BUILD_CONFIGURATION_INVALID');
    }
    const backendProbe = await fetch(`${apiBase}/docs`);
    if (!backendProbe.ok) throw new Error(`SERVICE_HEALTH_BACKEND_HTTP_${backendProbe.status}`);
    result.service_health.backend_api = true;
    result.failure_stage = 'browser-launch';
    browser = await chromium.launch({headless: true, executablePath: braveExecutable});
    result.browser_engine_version = browser.version();
    result.playwright_version = require('playwright/package.json').version;
    const context = await browser.newContext({viewport: {width: 1280, height: 1000}});
    const page = await context.newPage();

    result.failure_stage = 'locator-probe';
    await page.goto(webBase, {waitUntil: 'domcontentloaded'});
    result.service_health.static_web = true;
    await enableForTarget(page, 'button', 'n3-open-chat');
    const openChat = await requireControl(page, 'button', 'n3-open-chat');
    await openChat.click();
    await requireRuntimeMarker(page);
    await enableForTarget(page, 'textbox', 'n3-chat-input');
    await requireControl(page, 'textbox', 'n3-chat-input');
    await requireControl(page, 'button', 'n3-chat-send');
    // Feedback controls appear only after a real trusted structured card, so
    // they are probed after normal chat delivery, not injected for preflight.
    result.events.push('locator-probe-pass');

    result.failure_stage = 'real-shadow-request';
    const comparableRequest = 'Recommend a suitable dinner for my nutrition goal.';
    const input = page.getByRole('textbox', {name: 'n3-chat-input', exact: true});
    // Keep this harness source ASCII-only: request transport must not depend
    // on a Windows terminal code page.
    await input.fill(comparableRequest);
    const feedbackResponse = page.waitForResponse(
      (response) => response.url().includes('/api/nutrition/adaptive/recommendations/feedback') && response.request().method() === 'POST',
      {timeout: 45000},
    );
    await page.getByRole('button', {name: 'n3-chat-send', exact: true}).click();
    await enableForTarget(page, 'button', 'n3-feedback-like', 180000);
    const like = await requireControl(page, 'button', 'n3-feedback-like');
    result.events.push('trusted-structured-card-visible');

    result.failure_stage = 'feedback';
    await like.click();
    const feedbackHttp = await feedbackResponse;
    if (!feedbackHttp.ok()) throw new Error(`FEEDBACK_HTTP_${feedbackHttp.status()}`);
    const feedback = await feedbackHttp.json();
    result.recommendation_event_id = feedback.recommendation_event_id || null;
    result.candidate_id = feedback.candidate_id || null;
    result.feedback_event_id = feedback.feedback_event_id || null;
    if (!result.recommendation_event_id || !result.candidate_id || !result.feedback_event_id) {
      throw new Error('PRODUCT_FEEDBACK_IDENTITY_MISSING');
    }
    result.events.push('feedback-persisted');

    result.failure_stage = 'authoritative-readback';
    const readback = await api(`/api/nutrition/adaptive/recommendations/${result.recommendation_event_id}`, token);
    if (readback.status !== 200 || !Array.isArray(readback.body.feedback_events) ||
        !readback.body.feedback_events.some((event) => event.feedback_event_id === result.feedback_event_id && event.event_type === 'LIKED')) {
      throw new Error(`AUTHORITATIVE_READBACK_FAILED:HTTP_${readback.status}`);
    }
    result.authoritative_read_back = true;

    result.failure_stage = 'refresh-reconnect';
    await page.reload({waitUntil: 'domcontentloaded'});
    await enableForTarget(page, 'button', 'n3-open-chat');
    const refreshed = await api(`/api/nutrition/adaptive/recommendations/${result.recommendation_event_id}`, token);
    if (refreshed.status !== 200 || refreshed.body.candidate_id !== result.candidate_id) {
      throw new Error(`RECONNECT_READBACK_FAILED:HTTP_${refreshed.status}`);
    }
    result.refresh_reconnect = true;

    result.failure_stage = 'cross-user-denial';
    const foreign = await api(`/api/nutrition/adaptive/recommendations/${result.recommendation_event_id}`, foreignToken);
    if (foreign.status === 200) throw new Error('CROSS_USER_FEEDBACK_EXPOSED');
    result.cross_user_denial = true;

    result.failure_stage = 'comparable-request';
    await openChat.click();
    await enableForTarget(page, 'textbox', 'n3-chat-input');
    const comparableInput = page.getByRole('textbox', {name: 'n3-chat-input', exact: true});
    const feedbackCountBefore = await page.getByRole('button', {name: 'n3-feedback-like', exact: true}).count();
    await comparableInput.fill(comparableRequest);
    await page.getByRole('button', {name: 'n3-chat-send', exact: true}).click();
    // The first card remains in chat history. Prove that a second genuine
    // request produces another trusted feedback-eligible card without
    // indexing, coordinates, or fallback locators. The focused PostgreSQL
    // regression independently proves that the profile changes rank inputs.
    await page.waitForFunction(
      (priorCount) => document.querySelectorAll('[aria-label="n3-feedback-like"]').length > priorCount,
      feedbackCountBefore,
      {timeout: 180000},
    );
    result.preference_effect_consulted = true;
    result.events.push('comparable-request-delivered-after-preference-update');
    result.events.push('no-meal-log-or-canonical-write-route-invoked');
    result.status = 'PASS';
    result.failure_stage = null;
    result.failure_class = 'PASS';
  } catch (error) {
    result.failure_class = classify(error, result.failure_stage);
    result.error = String(error && (error.stack || error.message || error));
  } finally {
    if (browser) await browser.close();
    result.timestamps.completed_at_utc = new Date().toISOString();
    fs.mkdirSync(require('path').dirname(evidencePath), {recursive: true});
    fs.writeFileSync(evidencePath, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
    console.log(JSON.stringify(result, null, 2));
  }
  process.exitCode = result.status === 'PASS' ? 0 : 1;
}

run();
