// Browser driver for the existing real-auth E2E scenarios. No credentials are stored here.
const path = require('path');
const fs = require('fs');
const playwright = require(path.join(process.env.APPDATA, 'npm', 'node_modules', '@playwright', 'cli', 'node_modules', 'playwright-core'));

async function main() {
  const browserRoot = path.join(process.env.LOCALAPPDATA, 'ms-playwright');
  const candidates = fs.readdirSync(browserRoot).filter(name => /^chromium-\d+$/.test(name)).sort().reverse();
  if (candidates.length === 0) throw new Error('CHROMIUM_NOT_INSTALLED');
  const executablePath = path.join(browserRoot, candidates[0], 'chrome-win64', 'chrome.exe');
  const browser = await playwright.chromium.launch({ headless: true, executablePath });
  const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
  await page.goto('http://127.0.0.1:3000', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(10000);
  console.log('TITLE=' + await page.title());
  console.log('BODY_TEXT=' + (await page.locator('body').innerText()).slice(0, 1200).replace(/\s+/g, ' '));
  console.log('SEMANTICS_HOST=' + await page.locator('flt-semantics-host').count());
  console.log('PLACEHOLDER=' + await page.locator('flt-semantics-placeholder').count());
  console.log('PLACEHOLDER_HTML=' + (await page.locator('flt-semantics-placeholder').evaluate(element => element.outerHTML)).slice(0, 1000));
  console.log('SEMANTICS_HTML=' + (await page.locator('flt-semantics-host').evaluate(element => element.outerHTML)).slice(0, 1000));
  await page.locator('flt-semantics-placeholder').evaluate(element => element.click());
  await page.waitForTimeout(1000);
  console.log('SEMANTICS_ENABLED_HTML=' + (await page.locator('flt-semantics-host').evaluate(element => element.outerHTML)).slice(0, 1600));
  console.log('SEMANTICS_TEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(0, 1500).replace(/\s+/g, ' '));
  await page.mouse.click(680, 725);
  await page.waitForTimeout(700);
  console.log('DIALOG_TEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(-1700).replace(/\s+/g, ' '));
  console.log('TEXTBOX_COUNT=' + await page.getByRole('textbox').count());
  console.log('INPUT_COUNT=' + await page.locator('input').count());
  if (process.env.E2E_TEST_EMAIL && process.env.E2E_TEST_PASSWORD) {
    await page.locator('input').nth(0).fill(process.env.E2E_TEST_EMAIL);
    await page.locator('input').nth(1).fill(process.env.E2E_TEST_PASSWORD);
    await page.mouse.click(731, 588);
    await page.waitForTimeout(5000);
    console.log('AFTER_LOGIN_TEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(-2200).replace(/\s+/g, ' '));
    if (await page.getByRole('button', { name: 'Bắt đầu' }).count()) {
      await page.getByRole('button', { name: 'Bắt đầu' }).click();
      await page.waitForTimeout(600);
    }
    console.log('AFTER_START_TEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(-2200).replace(/\s+/g, ' '));
    if (await page.getByRole('textbox', { name: 'Họ và tên' }).count()) {
    const startInputs = await page.locator('input').evaluateAll(elements => elements.map(element => ({ type: element.type, label: element.getAttribute('aria-label'), placeholder: element.getAttribute('placeholder') })));
    console.log('START_INPUTS=' + JSON.stringify(startInputs));
    console.log('COMBOBOX_COUNT=' + await page.getByRole('combobox').count());
    console.log('BUTTON_TEXTS=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(-20)));
    console.log('GENDER_NODES=' + JSON.stringify(await page.locator('flt-semantics').filter({ hasText: 'Giới tính' }).evaluateAll(elements => elements.slice(-5).map(element => ({ id: element.id, role: element.getAttribute('role'), aria: element.getAttribute('aria-label'), text: (element.innerText || '').slice(0, 100), pointer: element.style.pointerEvents })))));
    const isUserB = process.env.E2E_TEST_EMAIL === 'nckh02@test.com';
    await page.getByRole('textbox', { name: 'Họ và tên' }).fill(isUserB ? 'E2E Test B' : 'E2E Test A');
    await page.getByRole('textbox', { name: 'Tuổi' }).fill(isUserB ? '31' : '30');
    await page.getByRole('textbox', { name: /Chiều cao/ }).fill(isUserB ? '168' : '170');
    await page.getByRole('textbox', { name: /Cân nặng/ }).fill(isUserB ? '68' : '70');
    const beforeGender = await page.locator('input').evaluateAll(elements => elements.map(element => ({ label: element.getAttribute('aria-label'), value: element.value })));
    console.log('STEP0_VALUES_BEFORE_GENDER=' + JSON.stringify(beforeGender));
    await page.getByRole('button', { name: 'Giới tính' }).click();
    console.log('GENDER_OPTIONS=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(-12)));
    await page.mouse.click(545, 629);
    await page.getByRole('textbox', { name: /Cân nặng/ }).fill(isUserB ? '68' : '70');
    await page.waitForTimeout(300);
    const afterGender = await page.locator('input').evaluateAll(elements => elements.map(element => ({ label: element.getAttribute('aria-label'), value: element.value })));
    console.log('STEP0_VALUES_AFTER_GENDER=' + JSON.stringify(afterGender));
    await page.getByRole('button', { name: 'Tiếp tục' }).click();
    await page.waitForTimeout(400);
    console.log('STEP1_TEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(-1800).replace(/\s+/g, ' '));
    console.log('STEP1_BUTTONS=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(-20)));
    await page.getByRole('button', { name: 'Duy trì cân nặng' }).click();
    console.log('STEP1_AFTER_GOAL_BUTTONS=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(-20)));
    await page.mouse.click(680, 576);
    await page.waitForTimeout(250);
    console.log('EQUATION_MENU_TEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(-700).replace(/\s+/g, ' '));
    await page.mouse.click(575, 644);
    await page.getByRole('button', { name: 'Hoạt động hằng tuần' }).click();
    await page.waitForTimeout(250);
    console.log('ACTIVITY_MENU_TEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(-800).replace(/\s+/g, ' '));
    await page.mouse.click(650, 668);
    await page.getByRole('button', { name: 'Tiếp tục' }).click();
    await page.waitForTimeout(350);
    console.log('STEP2_TEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(-1500).replace(/\s+/g, ' '));
    console.log('STEP2_BUTTONS=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(-18)));
    await page.getByRole('button', { name: /Trạng thái/ }).first().click();
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(250);
    console.log('STEP2_AFTER_FIRST=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(-10)));
    for (let index = 0; index < 3; index++) {
      await page.getByRole('button', { name: /Trạng thái/ }).filter({ hasText: 'Chưa cung cấp' }).first().click();
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('Enter');
    }
    console.log('STEP2_AFTER_ALL=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(-10)));
    await page.getByRole('button', { name: 'Lưu và tiếp tục' }).click();
    await page.waitForTimeout(1800);
    console.log('AFTER_BASIC_SAVE=' + (await page.locator('flt-semantics-host').innerText()).slice(-1800).replace(/\s+/g, ' '));
    }
    if ((await page.locator('flt-semantics-host').innerText()).includes('Bước 4/6')) {
    await page.getByRole('button', { name: 'Cả ăn uống và tập luyện' }).click();
    await page.getByRole('button', { name: 'Duy trì sức khỏe' }).click();
    await page.getByRole('button', { name: 'Tiếp tục' }).click();
    await page.waitForTimeout(350);
    console.log('STEP5_TEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(-2200).replace(/\s+/g, ' '));
    console.log('STEP5_BUTTONS=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(-35)));
    await page.getByRole('button', { name: /Bạn đã tập luyện có cấu trúc/ }).click();
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowUp');
    await page.keyboard.press('Enter');
    console.log('AFTER_EXPERIENCE=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(0, 7)));
    await page.getByRole('button', { name: /Bạn thường có thể tập mấy ngày/ }).click();
    for (let index = 0; index < 3; index++) await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /Một buổi tập thường kéo dài/ }).click();
    for (let index = 0; index < 3; index++) await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /Bạn muốn tập chủ yếu/ }).click();
    await page.keyboard.press('Enter');
    console.log('WORKOUT_DROPDOWNS=' + JSON.stringify((await page.getByRole('button').allTextContents()).slice(0, 8)));
    console.log('STEP5_CHECKBOXES=' + JSON.stringify((await page.getByRole('checkbox').allTextContents()).slice(-12)));
    await page.mouse.click(602, 700);
    await page.getByRole('button', { name: 'Không', exact: true }).nth(0).click();
    await page.getByRole('button', { name: 'Không / sức khỏe ổn định' }).click();
    await page.getByRole('button', { name: 'Không', exact: true }).nth(1).click();
    await page.getByRole('button', { name: 'Không', exact: true }).nth(2).click();
    await page.getByRole('button', { name: 'Không', exact: true }).nth(3).click();
    console.log('SAFETY_CHECKBOXES=' + JSON.stringify((await page.getByRole('checkbox').allTextContents()).slice(-12)));
    console.log('CHECKBOX_ATTRS=' + JSON.stringify(await page.getByRole('checkbox').evaluateAll(elements => elements.map(element => ({ aria: element.getAttribute('aria-label'), checked: element.getAttribute('aria-checked'), text: (element.innerText || '').slice(0, 90) })))));
    await page.getByRole('checkbox', { name: /Tôi hiểu cần dừng tập/ }).check();
    await page.getByRole('button', { name: 'Tiếp tục' }).click();
    await page.waitForTimeout(450);
    console.log('AFTER_WORKOUT_NEXT=' + (await page.locator('flt-semantics-host').innerText()).slice(-1600).replace(/\s+/g, ' '));
    await page.getByRole('button', { name: 'Hoàn tất' }).click();
    await page.waitForTimeout(2500);
    console.log('AFTER_ONBOARDING=' + (await page.locator('flt-semantics-host').innerText()).slice(-1800).replace(/\s+/g, ' '));
    }
  }
  await page.screenshot({ path: path.join(process.env.TEMP, 'nckh-e2e-auth-screen.png') });
  await browser.close();
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
