/*
 * Accessibility-only probe for the existing Plan V2 Flutter web bundle.
 * It deliberately performs no authenticated API calls and no Plan actions.
 */

const { chromium } = require('playwright');
const fs = require('fs');
const { ensureFlutterSemanticsEnabled } = require('./plan_v2_flutter_semantics.cjs');

const webBase = process.env.PLAN_V2_SEMANTICS_WEB || 'http://127.0.0.1:4173';
const edgeExecutable = process.env.EDGE_EXECUTABLE ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const planLibraryLabel = 'app-nav-plan-library';
const configurationLabel = 'Plan V2 E2E configuration active';
const evidencePath = process.env.PLAN_V2_SEMANTICS_EVIDENCE;

const surroundingNavigationLabels = [
  'Main navigation overview',
  'Main navigation nutrition',
  'Main navigation activity',
  'Main navigation settings',
];

async function inspectSemanticButton(page, accessibleName) {
  const locator = page.getByRole('button', {name: accessibleName, exact: true});
  const count = await locator.count();
  return {
    role: 'button',
    accessible_name: accessibleName,
    locator_count: count,
    visible: count === 1 && await locator.isVisible(),
    actionable: count === 1 && await locator.isVisible() && await locator.isEnabled(),
    aria_disabled: count === 1 ? await locator.getAttribute('aria-disabled') : null,
  };
}

async function probe() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: edgeExecutable,
  });
  const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
  try {
    await page.goto(webBase, {waitUntil: 'domcontentloaded'});
    await page.waitForTimeout(3000);
    const semantics = await ensureFlutterSemanticsEnabled(page);
    await page.waitForTimeout(1000);

    const planLibrary = await inspectSemanticButton(page, planLibraryLabel);
    const configurationMarker = page.getByLabel(configurationLabel, {exact: true});
    const configurationMarkerCount = await configurationMarker.count();
    const surroundingNavigation = await Promise.all(
      surroundingNavigationLabels.map((label) => inspectSemanticButton(page, label)),
    );
    const result = {
      artifact_version: 'PLAN_V2_PLAYWRIGHT_SEMANTICS_PROBE_V1',
      status: semantics.semantics_enabled && planLibrary.locator_count === 1 &&
          planLibrary.visible && planLibrary.actionable ? 'PASS' : 'FAIL',
      semantics_enabled: semantics.semantics_enabled,
      semantics_placeholder_count: semantics.placeholder_count,
      semantic_node_count: semantics.semantic_node_count,
      configuration_marker: {
        role: 'group',
        accessible_name: configurationLabel,
        locator_count: configurationMarkerCount,
        aria_disabled: configurationMarkerCount === 1 ?
          await configurationMarker.getAttribute('aria-disabled') : null,
      },
      plan_library_locator: planLibrary,
      surrounding_navigation: surroundingNavigation,
    };
    if (evidencePath) fs.writeFileSync(evidencePath, `${JSON.stringify(result, null, 2)}\n`);
    console.log(JSON.stringify(result, null, 2));
    process.exitCode = result.status === 'PASS' ? 0 : 1;
  } finally {
    await browser.close();
  }
}

if (require.main === module) {
  probe().catch((error) => {
    console.error(error.stack || String(error));
    process.exitCode = 1;
  });
}

module.exports = {ensureFlutterSemanticsEnabled, planLibraryLabel, probe};
