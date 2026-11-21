// The companion's voice and face (plan step 5): the microphone to the voice head over a WebSocket, its spoken
// replies back as PCM, played in order; the face's mouth follows the loudness of what is playing, its eyes blink
// and it looks attentive while you speak. Everything shown is set with textContent.
const $ = id => document.getElementById(id);
let ctx, ws, analyser, playhead = 0, sources = [], state = "idle", nextAudioRate = null;

function line(cls, who, text) {
  const li = document.createElement("li");
  li.className = cls;
  const s = document.createElement("small"); s.textContent = who;
  li.append(s, document.createTextNode(text));
  $("log").append(li);
  $("log").scrollTop = $("log").scrollHeight;
}

const LABEL = {listening: "Listening", hearing: "Hearing you…", thinking: "Thinking…", speaking: "Speaking"};

function play(buf, rate) {
  const pcm = new Int16Array(buf), f = new Float32Array(pcm.length);
  for (let i = 0; i < pcm.length; i++) f[i] = pcm[i] / 32768;
  const b = ctx.createBuffer(1, f.length, rate);
  b.copyToChannel(f, 0);
  const src = ctx.createBufferSource();
  src.buffer = b;
  src.connect(analyser);
  playhead = Math.max(playhead, ctx.currentTime + 0.03);
  src.start(playhead);
  playhead += b.duration;
  sources.push(src);
  src.onended = () => { sources = sources.filter(s => s !== src); };
}

function stop() { for (const s of sources) { try { s.stop(); } catch {} } sources = []; playhead = 0; }

async function start() {
  $("start").disabled = true;
  ctx = new AudioContext();
  analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.connect(ctx.destination);
  const mic = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1}});
  await ctx.audioWorklet.addModule("/static/mic-worklet.js");
  const node = new AudioWorkletNode(ctx, "mic");
  ctx.createMediaStreamSource(mic).connect(node);
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  node.port.onmessage = e => { if (ws.readyState === 1) ws.send(e.data); };
  ws.onmessage = e => {
    if (typeof e.data !== "string") { play(e.data, nextAudioRate || 24000); return; }
    const m = JSON.parse(e.data);
    if (m.type === "state") { state = m.state; $("state").textContent = LABEL[m.state] || m.state; }
    else if (m.type === "heard") line("you", "you", m.text);
    else if (m.type === "say") line(m.by === "companion" ? "companion" : "", m.by, m.text);
    else if (m.type === "audio") nextAudioRate = m.rate;
    else if (m.type === "stop") stop();
    else if (m.type === "error") line("error", "error", m.text);
  };
  ws.onclose = () => { $("state").textContent = "Disconnected. Reload to reconnect."; $("start").disabled = false; };
  $("start").hidden = true;
}
$("start").onclick = () => start().catch(err => { $("state").textContent = `Could not start: ${err.message}`; $("start").disabled = false; });

// ---------- the face ----------
const cv = $("face"), g = cv.getContext("2d");
let mouth = 0, blink = 0, nextBlink = performance.now() + 2500, look = 0;
const data = new Uint8Array(256);
let avatar = null;
// AVATAR_FILE, when set and present: a 3D avatar replaces the canvas face; any failure keeps the face as it was
fetch("/config.json").then(r => r.json()).then(async c => {
  if (!c.avatar) return;
  const {loadAvatar} = await import("/static/avatar.js");     // loaded only when there is an avatar
  avatar = await loadAvatar(c.avatar, $("stage"), $("credit"));
  window.avatar = avatar;
  cv.hidden = true;
}).catch(err => { console.warn("avatar not loaded:", err); $("stage").hidden = true; $("credit").hidden = true; avatar = null; });
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function frame(t) {
  let level = 0;
  if (analyser) {
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const v of data) sum += ((v - 128) / 128) ** 2;
    level = Math.min(1, Math.sqrt(sum / data.length) * 5);
  }
  if (avatar) { avatar.update(t, level, state); requestAnimationFrame(frame); return; }
  mouth += (level - mouth) * 0.35;
  if (t > nextBlink) { blink = 1; nextBlink = t + 2500 + Math.random() * 3500; }
  blink = Math.max(0, blink - 0.12);
  look += (((state === "hearing" || state === "thinking") ? 1 : 0) - look) * 0.05;
  const W = cv.width, cx = W / 2, cy = W / 2 + 10;
  g.clearRect(0, 0, W, W);
  g.fillStyle = css("--skin");
  g.beginPath(); g.ellipse(cx, cy, 150, 180, 0, 0, Math.PI * 2); g.fill();
  const bob = Math.sin(t / 900) * 3;
  g.fillStyle = css("--ink");
  for (const dx of [-55, 55]) {
    const open = Math.max(0.08, 1 - (blink > 0.5 ? 2 - blink * 2 : blink * 2));
    g.beginPath(); g.ellipse(cx + dx, cy - 40 + bob - look * 4, 16, 20 * open, 0, 0, Math.PI * 2); g.fill();
  }
  g.lineWidth = 6; g.lineCap = "round"; g.strokeStyle = css("--ink");
  for (const dx of [-55, 55]) {
    g.beginPath(); g.moveTo(cx + dx - 24, cy - 78 + bob - look * 8); g.lineTo(cx + dx + 24, cy - 82 + bob - look * 8); g.stroke();
  }
  const mw = 60 - mouth * 10, mh = 4 + mouth * 46;
  g.beginPath(); g.ellipse(cx, cy + 75 + bob, mw, mh, 0, 0, Math.PI * 2); g.fill();
  if (state === "thinking") { g.fillStyle = css("--muted"); for (let i = 0; i < 3; i++) { g.beginPath(); g.arc(cx + 130 + i * 18, cy - 150 - i * 14, 5 + i * 2 + Math.sin(t / 200 + i) * 2, 0, Math.PI * 2); g.fill(); } }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
