/* Shared Flutter Web semantics activation for Plan V2 browser harnesses. */

async function ensureFlutterSemanticsEnabled(page) {
  const semanticNodes = page.locator('flt-semantics');
  await page
    .locator('flt-semantics-placeholder, flt-semantics')
    .first()
    .waitFor({state: 'attached', timeout: 10000});

  const semanticNodeCountBefore = await semanticNodes.count();
  const placeholder = page.locator('flt-semantics-placeholder');
  const placeholderCount = await placeholder.count();
  if (placeholderCount > 1) {
    throw new Error(`PLAYWRIGHT_HARNESS_PREFLIGHT: expected at most one Flutter semantics placeholder; found ${placeholderCount}`);
  }
  if (semanticNodeCountBefore === 0 && placeholderCount === 1 && await placeholder.isVisible()) {
    await placeholder.focus();
    await page.keyboard.press('Enter');
  }

  await semanticNodes.first().waitFor({state: 'attached', timeout: 10000});
  return {
    semantics_enabled: true,
    placeholder_count: placeholderCount,
    semantic_node_count: await semanticNodes.count(),
  };
}

module.exports = {ensureFlutterSemanticsEnabled};
