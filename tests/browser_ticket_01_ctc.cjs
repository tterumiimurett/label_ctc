/*
 * Ticket 1 browser contract test.
 * Run from the repository root with Playwright available, for example:
 *   NODE_PATH=/tmp/ticket1-ctc/node_modules node tests/browser_ticket_01_ctc.cjs
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const PORT = 8791;
const BASE = `http://127.0.0.1:${PORT}`;

function syntheticWav() {
  const sampleRate = 8000;
  const samples = sampleRate / 4;
  const data = Buffer.alloc(samples * 2);
  for (let i = 0; i < samples; i += 1) {
    data.writeInt16LE(Math.round(Math.sin(i * 2 * Math.PI * 440 / sampleRate) * 5000), i * 2);
  }
  const header = Buffer.alloc(44);
  header.write('RIFF', 0); header.writeUInt32LE(36 + data.length, 4); header.write('WAVE', 8);
  header.write('fmt ', 12); header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22); header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * 2, 28); header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34); header.write('data', 36); header.writeUInt32LE(data.length, 40);
  return Buffer.concat([header, data]);
}

function jsonResponse(body, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(body) };
}

async function waitForServer(url) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try { await fetch(url); return; } catch { await new Promise((resolve) => setTimeout(resolve, 100)); }
  }
  throw new Error('local CTC server did not start');
}

async function main() {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ticket1-ctc-browser-'));
  const candidate = {
    candidate_key: 'synthetic|P1|P2|1|2|target',
    pred_is_ctc: true,
    audio_verify: { verify_is_ctc: true },
    tos_audio: { outer_url: 'https://synthetic.test/audio.wav' },
  };
  fs.writeFileSync(path.join(temp, 'candidates.jsonl'), `${JSON.stringify(candidate)}\n`);
  const server = spawn('python3', [
    path.join(ROOT, 'prolific/ctc_verification_app/app.py'),
    '--auto-labels', path.join(temp, 'candidates.jsonl'),
    '--data-dir', path.join(temp, 'data'), '--host', '127.0.0.1',
    '--port', String(PORT), '--bundle-size', '1', '--redundancy', '1',
  ], { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] });
  try {
    await waitForServer(`${BASE}/verify`);
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    const wav = syntheticWav();
    await page.route('https://synthetic.test/audio.wav', (route) => route.fulfill({
      status: 200, contentType: 'audio/wav', body: wav,
    }));

    await page.goto(`${BASE}/verify?PROLIFIC_PID=success-p&STUDY_ID=S1&SESSION_ID=success-s`);
    await page.locator('#verification-form').waitFor({ state: 'visible' });
    await page.locator('summary').first().waitFor({ state: 'visible' });
    await page.waitForFunction(() => document.querySelector('#audio').readyState >= 3);
    const before = await page.locator('#audio').evaluate((audio) => audio.currentTime);
    await page.locator('#audio').evaluate((audio) => audio.play());
    await page.waitForFunction((start) => document.querySelector('#audio').currentTime > start + 0.05, before);
    const success = {
      taskVisible: await page.locator('#task-title').isVisible(),
      instructionVisible: await page.locator('summary').first().isVisible(),
      loadedMetadata: await page.locator('#audio').evaluate((audio) => audio.readyState >= 1),
      canPlay: await page.locator('#audio').evaluate((audio) => audio.readyState >= 3),
      currentTimeAdvanced: await page.locator('#audio').evaluate((audio) => audio.currentTime > 0.05),
    };
    assert.deepEqual(success, { taskVisible: true, instructionVisible: true, loadedMetadata: true, canPlay: true, currentTimeAdvanced: true });

    await page.goto(`${BASE}/verify?PROLIFIC_PID=empty-p&STUDY_ID=S1&SESSION_ID=empty-s`);
    await page.locator('#loading-card.errors').waitFor({ state: 'visible' });
    const noTask = await page.locator('#loading-message').innerText();
    assert.match(noTask, /No unassigned/);

    const scenarios = [
      ['network failure', async (route) => route.abort('failed'), /Unable to load assignment/],
      ['invalid JSON', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{not-json' }), /Unable to load assignment/],
      ['null payload', async (route) => route.fulfill(jsonResponse(null)), /invalid assignment response/],
    ];
    const errors = {};
    for (const [name, handler, expected] of scenarios) {
      await page.route('**/api/assign*', handler, { times: 1 });
      await page.goto(`${BASE}/verify?PROLIFIC_PID=${name.replaceAll(' ', '-')}&STUDY_ID=S1&SESSION_ID=${name.replaceAll(' ', '-')}-s`);
      await page.locator('#loading-card.errors').waitFor({ state: 'visible' });
      const message = await page.locator('#loading-message').innerText();
      assert.match(message, expected);
      errors[name] = message;
    }
    console.log(JSON.stringify({ success, noTask, errors }));
    await browser.close();
  } finally {
    server.kill('SIGINT');
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
