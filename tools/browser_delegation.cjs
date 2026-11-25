// Run with Playwright and Chromium against tools/round2_runtime.py.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const origin = 'http://127.0.0.1:' + (process.env.DEMO_PORT || '5001');
const apiPort = process.env.DEMO_API_PORT;
const live = process.env.DEMO_LIVE === '1';
const evidenceDir = process.env.DEMO_EVIDENCE_DIR;
const npcDatabase = process.env.DEMO_NPC_DB;

async function main() {
  assert.equal(Boolean(evidenceDir), Boolean(npcDatabase), 'Set both evidence output and fixture database, or neither.');
  if (evidenceDir) await fs.mkdir(evidenceDir, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
  async function isolatedContext() {
    const result = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' });
    await result.route(/^https?:/, route => {
      const url = new URL(route.request().url());
      if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort();
      if (apiPort && url.port === '10000') {
        url.port = apiPort;
        return route.continue({ url: url.href });
      }
      return route.continue();
    });
    return result;
  }
  const context = await isolatedContext();
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const button = name => page.getByRole('button', { name, exact: true });
  const choose = name => page.locator('.character-card').filter({ hasText: name }).click();
  const dialogue = name => page.getByPlaceholder('与' + name + '对话', { exact: true });
  const intro = () => button('明白了，开始游戏！').click({ timeout: 60000 });
  const records = tabPage => tabPage.getByRole('tab', { name: '调查记录', exact: true });
  let capability;

  async function openCase(title, caseId) {
    await page.goto(origin + '/library');
    const heading = page.getByRole('heading', { name: title, exact: true });
    const card = page.locator('.mantine-Card-root').filter({ has: heading });
    await card.getByRole('button', { name: /开始游戏/ }).click();
    await page.waitForURL('**/play/' + caseId);
    await intro();
    capability = undefined;
  }

  function responseAt(route) {
    return page.waitForResponse(response => new URL(response.url()).pathname === '/npc/' + route &&
      response.request().method() === 'POST');
  }

  async function present(name, evidence) {
    await choose(name);
    await button('发送证物').click();
    const picker = page.getByRole('dialog');
    await picker.getByText(evidence, { exact: true }).first().click();
    const showing = responseAt('dialogue');
    await picker.getByRole('button', { name: '发送证物', exact: true }).click();
    const result = await (await showing).json();
    assert.equal(result.handled, true);
    await page.getByText(result.reply, { exact: true }).last().waitFor();
  }

  async function talk(name, message, expectation) {
    await choose(name);
    const box = dialogue(name);
    const replies = page.getByText(expectation.fragment).and(page.locator(':visible'));
    const previous = await replies.count();
    await box.fill(message);
    const initial = responseAt('dialogue');
    const terminal = expectation.status ? responseAt('resume') : undefined;
    let dropped;
    if (expectation.refreshAccepted) {
      let markDropped;
      dropped = new Promise(resolve => { markDropped = resolve; });
      const endpoint = '**/npc/resume';
      const dropResume = async route => {
        if (route.request().method() !== 'POST') return route.fallback();
        await route.abort();
        await page.unroute(endpoint, dropResume);
        markDropped();
      };
      await page.route(endpoint, dropResume);
    }
    await box.press('Enter');
    const response = await initial;
    assert.equal(response.status(), 200);
    capability = (await response.request().headerValue('authorization')).split(' ')[1];
    const first = await response.json();
    assert.equal(first.handled, expectation.handled !== false, message);
    let result = first;
    if (terminal) {
      assert.equal(first.task.status, 'accepted', message);
      if (dropped) {
        await dropped;
        await page.reload();
        await intro();
        await choose(name);
      }
      const resumed = await terminal;
      assert.equal(resumed.status(), 200);
      result = await resumed.json();
      assert.equal(result.task.status, expectation.status, message);
      assert.equal(result.task.id, first.task.id, message);
    }
    await replies.nth(previous).waitFor();
    if (expectation.handled !== false) assert.match(result.reply, expectation.fragment);
    if (expectation.driver) assert.equal(result.driver, expectation.driver, message);
    console.log(`PASS ${name} · ${message} · ${result.task?.status || (result.handled ? 'handled' : 'ordinary chat')}`);
    return result;
  }

  async function capture(caseId, label, screenshotPage = page) {
    if (!evidenceDir) return;
    const screenshot = label + '.png';
    await screenshotPage.evaluate(() => window.scrollTo(0, 0));
    await screenshotPage.screenshot({
      path: path.join(evidenceDir, screenshot),
      mask: [screenshotPage.getByRole('textbox', { name: '邀请链接' })],
      maskColor: '#26303c',
    });
    const exported = spawnSync(process.env.DEMO_PYTHON || 'python3', [
      path.join(__dirname, 'round2_trace.py'), npcDatabase, path.join(evidenceDir, label + '.jsonl'),
      '--screenshot', screenshot, '--case', caseId,
    ], { input: capability, encoding: 'utf8' });
    assert.equal(exported.status, 0, exported.stderr);
  }

  async function closeCase(wrong, right, motive) {
    for (const suspect of [wrong, right]) {
      await button('提交推理').click();
      await page.getByRole('radio', { name: suspect, exact: true }).check();
      await button('确认选择').click();
      await page.getByText('请选择最符合剧情的作案动机').waitFor();
      await page.getByRole('radio', { name: motive, exact: true }).check();
      const verdict = responseAt('verdict');
      await button('提交最终推理').click();
      assert.equal((await (await verdict).json()).correct, suspect === right);
      if (suspect === wrong) {
        await page.getByText(/未能解释全部线索/).waitFor();
        await button('返回').click();
      }
    }
    await page.getByText(/推理成立。你可以在/).waitFor();
    await button('明白了！').click();
    await records(page).click();
    const explanation = responseAt('assist');
    await button('查看结案解释').click();
    const answer = await (await explanation).json();
    assert.equal(answer.level, 'answer');
    assert.match(answer.text, new RegExp(right));
    console.log(`PASS player rejects wrong suspect, submits correct suspect and explicitly views debrief (${right})`);
  }

  async function inviteGuest() {
    await records(page).click();
    await button('邀请玩家').click();
    const link = page.getByRole('textbox', { name: '邀请链接' });
    await link.waitFor();
    const inviteURL = new URL(await link.inputValue());
    assert.ok(inviteURL.searchParams.get('invite'));
    const guestContext = await isolatedContext();
    const guest = await guestContext.newPage();
    guest.setDefaultTimeout(12000);
    await guest.goto(inviteURL.href);
    await guest.getByRole('textbox', { name: '姓名', exact: true }).fill('第二调查席');
    await guest.getByRole('button', { name: '加入调查', exact: true }).click();
    await guest.getByRole('button', { name: '明白了，开始游戏！', exact: true }).click();
    await records(guest).click();
    await guest.getByText('当前席位 第二调查席', { exact: true }).waitFor();
    await page.getByText('第二调查席', { exact: true }).waitFor();
    return guest;
  }

  async function checkShare(guest) {
    assert.equal(await guest.getByText(/二十一点四十六分/).count(), 0);
    await guest.getByText(/目前没有公开线索/).waitFor();
    const shared = responseAt('share');
    await button('公开回报').last().click();
    const result = await (await shared).json();
    assert.equal(result.shared.classification, 'claim');
    await guest.getByText(/二十一点四十六分/).waitFor();
    await guest.getByRole('button', { name: '更新复盘', exact: true }).click();
    await guest.getByText('当时同局公开', { exact: true }).waitFor();
    assert.equal(await guest.getByText(/帮我去问问门卫昨晚谁进过仓库/).count(), 0);
    await capture('harbor_blackout', 'harbor-second-seat', guest);
    console.log('PASS second browser sees only the explicitly shared, attributed witness claim');
  }

  try {
    if (live) {
      await openCase('雾港停电案', 'harbor_blackout');
      const guest = await inviteGuest();
      await talk('宋屿', '帮我去问问门卫昨晚谁进过仓库', {
        status: 'completed', fragment: /二十一点四十六分/, driver: 'llm',
      });
      await page.getByText('模型决策', { exact: true }).last().waitFor();
      await checkShare(guest);
      await talk('阮岑', '是谁来问过西门出入？', {
        fragment: /据我亲历，是宋屿|有人来核对过|有人托我核对过/, driver: 'llm',
      });
      await capture('harbor_blackout', 'live-harbor-follow-up');
      await closeCase('宋屿', '罗钧', '掩盖虚报货重');
      await capture('harbor_blackout', 'live-harbor-closed');
      return;
    }
    await openCase('深宫血色：玉玺谜云', 'example_4');
    await talk('御史大夫', '请介绍一下案情。', { handled: false, fragment: /本机模拟对话/ });
    await talk('张昌宗', '你平日喜欢做什么？', { handled: false, fragment: /本机模拟对话/ });
    await talk('御史大夫', '有人查过秘录登记吗？', { fragment: /没有|还未|还没/ });
    await talk('太平公主', '能不能替我查一件事？', { fragment: /哪|什么|具体/ });
    await talk('太平公主', '劳烦你向御史打听一下宫闱秘录的借阅登记。', {
      status: 'completed', fragment: /未见完整的出库签押/,
    });
    await capture('example_4', 'palace-delegation');
    await talk('御史大夫', '有人查过秘录登记吗？', { fragment: /有人托我核对过/ });
    await talk('御史大夫', '谁来问过秘录登记？', { fragment: /据我亲历，是太平公主/ });
    await capture('example_4', 'palace-follow-up');
    await talk('御史大夫', '请帮我对一对宫闱秘录的借阅登记。', {
      status: 'completed', fragment: /出库栏均无签押/,
    });
    await talk('武惠妃', '劳烦你核查一下封存的内廷名册。', { fragment: /不愿/ });
    await talk('太平公主', '烦请查一查封存的内廷名册。', { fragment: /权限|授权|不能|无法/ });
    await talk('太平公主', '麻烦翻一翻雨夜那份原簿。', { status: 'failed', fragment: /无法调取原件/ });

    await present('张昌宗', '遗失的宫闱秘录');
    await page.getByRole('tab', { name: /证物库/ }).click();
    await choose('太平公主');
    await page.getByText('遗失的宫闱秘录', { exact: true }).first().click();
    const libraryShowing = responseAt('dialogue');
    await page.getByRole('dialog').getByRole('button', { name: '出示证物' }).click();
    assert.equal((await (await libraryShowing).json()).handled, true);
    console.log('PASS original evidence picker and evidence library both present evidence');

    await page.getByRole('tab', { name: '推理笔记' }).click();
    await page.getByTitle('新建笔记', { exact: true }).click();
    await page.getByPlaceholder('输入笔记标题（可选）').fill('登记来源');
    await page.getByPlaceholder('记录你的推理过程和发现的线索...').fill('御史的口述需要与副册核对。');
    await button('保存笔记').click();
    await page.getByText('登记来源', { exact: true }).waitFor();
    await page.reload();
    await intro();
    await choose('太平公主');
    await page.getByText(/未见完整的出库签押/).waitFor();
    assert.equal(await page.getByText(/未见完整的出库签押/).count(), 1);
    await page.getByText('登记来源', { exact: true }).waitFor();
    console.log('PASS browser refresh restores the task report once and preserves the player note');
    await closeCase('太平公主', '武惠妃', '掩盖武氏家族贪墨军饷');
    await capture('example_4', 'palace-closed');

    await openCase('雾港停电案', 'harbor_blackout');
    const guest = await inviteGuest();
    await talk('宋屿', '帮我去问问门卫昨晚谁进过仓库', {
      status: 'completed', fragment: /二十一点四十六分/,
    });
    await checkShare(guest);
    await talk('阮岑', '是谁来问过西门出入？', { fragment: /据我亲历，是宋屿/ });
    await capture('harbor_blackout', 'harbor-follow-up');
    const askTiming = '有人提过监控时间的误差吗？';
    await talk('宋屿', askTiming, { fragment: /还没人来说明/ });
    await present('林遥', '监控校时便条');
    await talk('宋屿', askTiming, { fragment: /去问阮岑/ });
    console.log('PASS autonomous timing tip changes the recipient’s available lead');
    await talk('林遥', '替我核对这两份证词。', {
      status: 'completed', fragment: /快八分钟/, refreshAccepted: true,
    });
    assert.equal(await page.getByText(/快八分钟/).count(), 1);
    console.log('PASS browser refresh after a dropped resume settles the accepted task once');
    const checkVest = '可以帮我翻翻七号背心的领用表吗？';
    await talk('阮岑', checkVest, { fragment: /我还缺核查所需的材料。请先给我看：停电检修工单/ });
    await present('阮岑', '停电检修工单');
    await talk('阮岑', checkVest, { status: 'completed', fragment: /由罗钧领取/ });
    const hidden = '审计组待交件登记副本';
    await page.getByRole('tab', { name: /证物库/ }).click();
    assert.equal(await page.getByText(hidden, { exact: true }).count(), 0);
    await present('宋屿', '半张过磅联');
    await talk('宋屿', '请帮我核查夜航四号的送审底单。', { status: 'completed', fragment: /高于实称重量/ });
    await page.getByRole('tab', { name: /证物库/ }).click();
    await page.getByText(hidden, { exact: true }).waitFor();
    await guest.getByRole('tab', { name: /证物库/ }).click();
    assert.equal(await guest.getByText(hidden, { exact: true }).count(), 0);
    await records(page).click();
    const summary = responseAt('assist');
    await button('总结线索').click();
    assert.match((await (await summary).json()).text, /已核查/);
    await page.getByLabel('想核对的问题').fill('能再核对哪份材料？');
    const hint = responseAt('assist');
    await button('下一步提示').click();
    const suggestion = await (await hint).json();
    assert.equal(suggestion.driver, 'mock');
    assert.match(suggestion.text, /请他核查夜航四号的送审底单/);
    await page.getByText(suggestion.text, { exact: true }).waitFor();
    assert.equal(await button('查看结案解释').count(), 0);
    console.log('PASS browser grants evidence only to the finder, summarizes clues and gives a next step');
    await closeCase('宋屿', '罗钧', '掩盖虚报货重');
    assert.equal(await guest.getByRole('button', { name: '查看结案解释', exact: true }).count(), 0);
    await capture('harbor_blackout', 'harbor-closed');

    await openCase('午夜凶杀案', 'example_1');
    assert.equal(await records(page).count(), 0);
    await choose('张警官');
    await dialogue('张警官').fill('请介绍一下案情。');
    await dialogue('张警官').press('Enter');
    await page.getByText(/本机模拟对话/).waitFor();
    console.log('PASS existing unmanaged case keeps its original dialogue');
  } catch (error) {
    console.error('Visible page at failure:', (await page.locator('body').innerText()).slice(-2600));
    throw error;
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
