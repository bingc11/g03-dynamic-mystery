// Requires Playwright and a Chromium browser. Run against the loopback offline demo only.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const port = Number(process.env.DEMO_PORT || 5001);

async function main() {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route(/^https?:/, route => {
    const local = ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname);
    return local ? route.continue() : route.abort();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const button = name => page.getByRole('button', { name, exact: true });
  const choose = name => page.locator('.character-card').filter({ hasText: name }).click();
  const chat = async (name, message, reply) => {
    await choose(name);
    const box = page.getByPlaceholder('与' + name + '对话', { exact: true });
    const responses = page.getByText(reply, {exact:false});
    const previous = await responses.count();
    await box.fill(message);
    await box.press('Enter');
    await responses.nth(previous).waitFor();
  };
  try {
    await page.goto('http://127.0.0.1:' + port + '/play/example_4');
    await button('明白了，开始游戏！').click({timeout:60000});
    await chat('御史大夫', '请介绍一下案情。', '【本机模拟对话】');
    await chat('张昌宗', '你当时在哪里？', '【本机模拟对话】');
    await chat('御史大夫', '有人查过秘录登记吗？', '我还没有收到过');
    await choose('太平公主');
    await button('发送证物').click();
    const modal = page.getByRole('dialog');
    await modal.getByText('遗失的宫闱秘录', {exact:true}).first().click();
    await modal.getByRole('button', {name:'发送证物',exact:true}).click();
    await page.getByText('我看过这份记录了', {exact:false}).waitFor();
    await chat('御史大夫', '有人查过秘录登记吗？', '有人托我核对过');
    await chat('御史大夫', '谁来问过秘录登记？', '据我亲历，是太平公主');
    if (process.env.DEMO_SCREENSHOT) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({path:process.env.DEMO_SCREENSHOT});
    }
    console.log('PASS: original witness and assistant chat, evidence disclosure, private contact, player follow-up');
    await page.getByTitle('新建笔记', {exact:true}).click();
    await page.getByPlaceholder('输入笔记标题（可选）').fill('登记来源');
    await page.getByPlaceholder('记录你的推理过程和发现的线索...').fill('御史陈述有人查过登记，不能据此指认。');
    await button('保存笔记').click();
    await page.getByText('登记来源', {exact:true}).waitFor();
    console.log('PASS: created and read back a player note');
    await button('提交推理').click();
    await page.getByRole('radio', {name:'太平公主',exact:true}).check();
    await button('确认选择').click();
    await page.getByText('你冤枉好人了！', {exact:true}).waitFor();
    await button('回到游戏').click();
    await button('提交推理').click();
    await page.getByRole('radio', {name:'武惠妃',exact:true}).check();
    await button('确认选择').click();
    await page.getByText('请选择最符合剧情的作案动机').waitFor();
    await page.getByRole('radio').first().check();
    await button('提交最终推理').click();
    await page.getByPlaceholder('与武惠妃对话').waitFor();
    console.log('PASS: wrong accusation rejected, correct suspect followed by upstream fallback motive and post-game');
    await page.reload();
    await button('明白了，开始游戏！').click({timeout:60000});
    await chat('御史大夫', '有人查过秘录登记吗？', '我还没有收到过');
    console.log('PASS: fresh game starts without earlier private contact');
    await page.getByRole('tab', {name:/证物库/}).click();
    const presentFromLibrary = async name => {
      await choose(name);
      await page.getByText('遗失的宫闱秘录', {exact:true}).first().click();
      await page.getByRole('dialog').getByRole('button', {name:'出示证物'}).click();
      await page.getByText('我看过这份记录了', {exact:false}).waitFor();
    };
    await presentFromLibrary('张昌宗');
    await chat('御史大夫', '有人查过秘录登记吗？', '我还没有收到过');
    await presentFromLibrary('太平公主');
    await chat('御史大夫', '有人查过秘录登记吗？', '有人托我核对过');
    console.log('PASS: evidence-library presentation gives distinct responses for two recipients');
  } catch(error) {
    console.error('Visible page at failure:', (await page.locator('body').innerText()).slice(-2400));
    throw error;
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
