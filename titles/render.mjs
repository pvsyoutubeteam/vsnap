#!/usr/bin/env node
// Offline renderer for the chrome titles.
//
//   node render.mjs still  --card 4 --t 3.2 [--scale 0.5] [--layer comp|title|bg]
//   node render.mjs sheet  [--scale 0.5]            contact sheet: every card at 3 moments
//   node render.mjs render [--scale 1] [--only title_04,bg] [--config config.json]
//
// "render" writes into out/: one ProRes 4444 clip with alpha per card, a ProRes 422 HQ
// background plate, preview.mp4, and ChromeTitles.fcpxml which lays them out on a
// Final Cut Pro timeline (background in the primary storyline, titles connected above).
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const cmd = args[0] || 'sheet';
const opt = (name, def) => { const i = args.indexOf('--' + name); return i < 0 ? def : args[i + 1]; };
const cfg = JSON.parse(fs.readFileSync(path.resolve(ROOT, opt('config', 'config.json')), 'utf8'));
const scale = parseFloat(opt('scale', '1'));
const OUT = path.resolve(ROOT, opt('out', 'out'));
fs.mkdirSync(path.join(OUT, 'stills'), { recursive: true });

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.ttf': 'font/ttf', '.otf': 'font/otf' };
const server = http.createServer((req, res) => {
  const f = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'] });
async function newPage() {
  const page = await browser.newPage();
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.error('[page]', m.text()); });
  page.on('pageerror', (e) => console.error('[page error]', e.message));
  await page.goto(`http://localhost:${port}/scene.html`);
  await page.waitForFunction(() => typeof window.setup === 'function');
  return { page, size: await page.evaluate(([c, s]) => window.setup(c, s), [cfg, scale]) };
}
const frame = async (page, o) => Buffer.from((await page.evaluate((o) => window.renderFrame(o), o)).split(',')[1], 'base64');

function ffmpeg(a, stdin = 'pipe') {
  const p = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...a], { stdio: [stdin, 'inherit', 'inherit'] });
  p.done = new Promise((ok, no) => p.on('close', (c) => (c ? no(new Error('ffmpeg exit ' + c)) : ok())));
  return p;
}
const write = (s, b) => new Promise((ok) => (s.write(b) ? ok() : s.once('drain', ok)));

async function renderClip(layer, cardIndex, frames, file, label) {
  const { page } = await newPage();
  const { fps } = cfg.output;
  const codec = layer === 'title'
    ? ['-c:v', 'prores_ks', '-profile:v', '4444', '-pix_fmt', 'yuva444p10le', '-alpha_bits', '16']
    : ['-c:v', 'prores_ks', '-profile:v', '3', '-pix_fmt', 'yuv422p10le'];
  const ff = ffmpeg(['-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-', ...codec,
    '-vendor', 'apl0', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-r', String(fps), file]);
  const t0 = Date.now();
  for (let i = 0; i < frames; i++) {
    await write(ff.stdin, await frame(page, { layer, card: cardIndex, t: i / fps }));
    if (i % 25 === 0) console.log(`${label}: ${i}/${frames}  (${((Date.now() - t0) / 1000 / (i + 1)).toFixed(2)} s/frame)`);
  }
  ff.stdin.end(); await ff.done; await page.close();
  console.log(`${label}: done -> ${path.relative(ROOT, file)}`);
}

function writeFcpxml(size) {
  const { fps, duration } = cfg.output;
  const T = (sec) => `${Math.round(sec * fps) * 100}/${fps * 100}s`;
  const std = { '1920x1080': `FFVideoFormat1080p${fps}`, '3840x2160': `FFVideoFormat3840x2160p${fps}` }[`${size.width}x${size.height}`];
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  const asset = (id, name, file, dur, alpha) =>
    `    <asset id="${id}" name="${esc(name)}" start="0s" duration="${T(dur)}" hasVideo="1" format="r1" videoSources="1">\n` +
    `      <media-rep kind="original-media" src="${pathToFileURL(path.join(OUT, file)).href}"/>\n    </asset>`;
  const assets = [asset('r2', 'Background plate', 'background.mov', duration)];
  const clips = [];
  cfg.cards.forEach((c, i) => {
    const name = `${c.id} – ${c.lines.join(' ')}`;
    assets.push(asset(`r${i + 3}`, name, `${c.id}.mov`, c.duration));
    clips.push(`            <asset-clip ref="r${i + 3}" lane="1" offset="${T(c.start)}" name="${esc(name)}" start="0s" duration="${T(c.duration)}" format="r1" tcFormat="NDF"/>`);
  });
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
    <format id="r1"${std ? ` name="${std}"` : ''} frameDuration="${T(1 / fps)}" width="${size.width}" height="${size.height}" colorSpace="1-1-1 (Rec. 709)"/>
${assets.join('\n')}
  </resources>
  <library>
    <event name="Chrome Titles">
      <project name="Chrome Titles">
        <sequence format="r1" duration="${T(duration)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
          <spine>
            <asset-clip ref="r2" offset="0s" name="Background plate" start="0s" duration="${T(duration)}" format="r1" tcFormat="NDF">
${clips.join('\n')}
            </asset-clip>
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
`;
  fs.writeFileSync(path.join(OUT, 'ChromeTitles.fcpxml'), xml);
}

try {
  if (cmd === 'still') {
    const { page } = await newPage();
    const card = parseInt(opt('card', '1')) - 1, t = parseFloat(opt('t', '3')), layer = opt('layer', 'comp');
    const f = path.join(OUT, 'stills', `${cfg.cards[card].id}_${layer}_t${t}.png`);
    fs.writeFileSync(f, await frame(page, { layer, card, t }));
    console.log(f);
  } else if (cmd === 'sheet') {
    const { page } = await newPage();
    const files = [];
    for (let c = 0; c < cfg.cards.length; c++) {
      const d = cfg.cards[c].duration;
      for (const t of [0.7, d * 0.3, d * 0.62]) {
        const f = path.join(OUT, 'stills', `sheet_${c}_${files.length}.png`);
        fs.writeFileSync(f, await frame(page, { layer: 'comp', card: c, t })); files.push(f);
      }
    }
    const sheet = path.join(OUT, 'stills', 'contact_sheet.png');
    execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...files.flatMap((f) => ['-i', f]),
      '-filter_complex', `${files.map((_, i) => `[${i}:v]`).join('')}xstack=grid=3x${cfg.cards.length}`, sheet]);
    files.forEach((f) => fs.unlinkSync(f));
    console.log(sheet);
  } else if (cmd === 'render') {
    const only = opt('only', '').split(',').filter(Boolean);
    const want = (id) => !only.length || only.includes(id);
    const { fps, duration } = cfg.output;
    const jobs = [];
    cfg.cards.forEach((c, i) => { if (want(c.id)) jobs.push(() => renderClip('title', i, Math.round(c.duration * fps), path.join(OUT, `${c.id}.mov`), c.id)); });
    if (want('bg')) jobs.push(() => renderClip('bg', 0, Math.round(duration * fps), path.join(OUT, 'background.mov'), 'background'));
    const workers = Array.from({ length: parseInt(opt('jobs', '2')) }, async () => { while (jobs.length) await jobs.shift()(); });
    await Promise.all(workers);
    const { page, size } = await newPage(); await page.close();
    writeFcpxml(size);
    // flattened preview of the whole timeline
    const have = cfg.cards.filter((c) => fs.existsSync(path.join(OUT, `${c.id}.mov`)));
    if (fs.existsSync(path.join(OUT, 'background.mov')) && have.length) {
      const inputs = ['-i', path.join(OUT, 'background.mov')];
      let chain = '', last = '0:v';
      have.forEach((c, i) => {
        inputs.push('-itsoffset', String(c.start), '-i', path.join(OUT, `${c.id}.mov`));
        chain += `[${last}][${i + 1}:v]overlay=eof_action=pass:enable='between(t,${c.start},${c.start + c.duration})'[v${i}];`;
        last = `v${i}`;
      });
      const p = ffmpeg([...inputs, '-filter_complex', chain.slice(0, -1), '-map', `[${last}]`, '-c:v', 'libx264', '-crf', '17', '-pix_fmt', 'yuv420p', '-t', String(duration), path.join(OUT, 'preview.mp4')], 'ignore');
      await p.done;
      console.log('preview -> out/preview.mp4');
    }
    console.log('timeline -> out/ChromeTitles.fcpxml');
  } else {
    console.error('unknown command: ' + cmd); process.exitCode = 1;
  }
} finally {
  await browser.close(); server.close();
}
