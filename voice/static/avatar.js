// The 3D avatar (S-160): a VRM, or a plain glTF/GLB, from AVATAR_FILE. Mouth from the playback loudness, blinks,
// expressions by name; a body-only rig (Mixamo bone names) gets breathing, nods, glances and a weight shift as
// offsets on the pose the file's first clip gives it. Everything shown is set with textContent.
import * as THREE from "three";
import {GLTFLoader} from "three/examples/jsm/loaders/GLTFLoader.js";
import {VRMLoaderPlugin, VRMUtils} from "/static/vendor/three-vrm/three-vrm.module.min.js";

const MOUTH = /mouth|^aa$|^a$|open|jaw|viseme_aa/i, BLINK = /blink|eye.*clos|clos.*eye|eyes?_?closed/i;
const strip = n => (n || "").replace(/^mixamorig:?/i, "").replace(/_\d+$/, "").toLowerCase();

function creditLine(el, extras) {
  if (!extras || !extras.title) return;
  const split = v => { const m = /^(.*?)\s*\((https?:\/\/[^)\s]+)\)\s*$/.exec(v || ""); return m ? [m[1], m[2]] : [v || "", ""]; };
  const link = (text, href) => {
    if (!href) return document.createTextNode(text);
    const a = document.createElement("a"); a.textContent = text; a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer"; return a;
  };
  const [author, authorUrl] = split(extras.author), [lic, licUrl] = split(extras.license);
  const src = /^https?:\/\//.test(extras.source || "") ? extras.source : "";
  el.replaceChildren(document.createTextNode("This work is based on “"), link(extras.title, src), document.createTextNode("”"));
  if (author) el.append(document.createTextNode(" by "), link(author, authorUrl));
  if (lic) el.append(document.createTextNode(" licensed under "), link(lic.split(" ")[0] || lic, licUrl));
  el.append(document.createTextNode("."));
  el.hidden = false;
}

export async function loadAvatar(url, stage, creditEl) {
  const loader = new GLTFLoader();
  loader.register(p => new VRMLoaderPlugin(p));
  const gltf = await loader.loadAsync(url);
  const vrm = gltf.userData.vrm || null;
  const root = vrm ? vrm.scene : gltf.scene;
  if (vrm) VRMUtils.rotateVRM0(vrm);

  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  stage.hidden = false;
  stage.replaceChildren(renderer.domElement);
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8a96, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(1.5, 2.5, 3); scene.add(key);
  scene.add(root);

  // the file's first clip once, for the rest pose; its bone rotations are the base the motion is added to
  let mixer = null;
  if (!vrm && gltf.animations.length) {
    mixer = new THREE.AnimationMixer(root);
    const a = mixer.clipAction(gltf.animations[0]); a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = true; a.play();
    mixer.update(Math.max(gltf.animations[0].duration, 0));
  }
  root.updateMatrixWorld(true);

  const bones = {};
  root.traverse(o => { const k = strip(o.name); if (k && !(k in bones) && (o.isBone || o.isObject3D)) bones[k] = o; });
  const rig = n => bones[n] && {o: bones[n], q: bones[n].quaternion.clone(), p: bones[n].position.clone()};
  const B = {hips: rig("hips"), spine: rig("spine1") || rig("spine"), chest: rig("spine2"), neck: rig("neck"), head: rig("head")};
  const rigged = !vrm && !!(B.head || B.neck || B.chest);

  // morph targets by lowercase name
  const morphs = {};
  root.traverse(o => {
    if (!o.isMesh || !o.morphTargetDictionary) return;
    for (const [n, i] of Object.entries(o.morphTargetDictionary)) (morphs[n.toLowerCase()] ||= []).push([o, i]);
  });
  const names = Object.keys(morphs);
  const expressions = vrm && vrm.expressionManager ? Object.keys(vrm.expressionManager.expressionMap || {}) : [];
  console.log("avatar:", vrm ? "VRM" : "glTF", "morph targets:", names, "VRM expressions:", expressions, "bones:", Object.keys(bones).filter(k => B.head && /head|neck|spine|hips|arm/.test(k)));
  // a dedicated open-mouth key wins (ARKit's 52 have jawOpen beside ~25 other mouth shapes; driving all of them at once,
  // smile, frown, pucker and mouthClose together, garbles the mouth); otherwise every key that looks like a mouth
  const OPEN = ["jawopen", "mouthopen", "viseme_aa", "aa"].filter(n => n in morphs);
  const mouthKeys = OPEN.length ? OPEN.slice(0, 1) : names.filter(n => MOUTH.test(n)), blinkKeys = names.filter(n => BLINK.test(n));
  const cur = {}, want = {};          // smoothed and wanted weights per morph or VRM expression name
  const setW = (n, w) => { want[n] = w; };
  const apply = (n, w) => {
    if (vrm && vrm.expressionManager && vrm.expressionManager.getExpression(n)) vrm.expressionManager.setValue(n, w);
    for (const [m, i] of morphs[n.toLowerCase()] || []) m.morphTargetInfluences[i] = w;
  };
  const exprNames = new Set();
  function setExpression(name, weight = 1) {
    const lower = String(name).toLowerCase();
    const hit = (vrm && expressions.find(e => e.toLowerCase() === lower)) || names.find(n => n === lower);
    if (!hit) return false;
    exprNames.add(hit);
    setW(hit, weight);
    return true;
  }
  function clearExpressions() { for (const n of exprNames) setW(n, 0); }

  // camera on the head and upper body
  const box = new THREE.Box3().setFromObject(root), size = box.getSize(new THREE.Vector3());
  const head = new THREE.Vector3();
  if (B.head) B.head.o.getWorldPosition(head); else head.set(0, box.max.y - size.y * 0.12, 0);
  const viewH = Math.max(size.y * 0.36, 0.2), cy = head.y + size.y * 0.17 - viewH / 2;    // the head bone sits at the neck: the head is above it
  const cam = new THREE.PerspectiveCamera(30, 1, 0.01, 100);
  const dist = (viewH / 2) / Math.tan(THREE.MathUtils.degToRad(15)) * 1.08;
  cam.position.set(head.x, cy, head.z + dist); cam.lookAt(head.x, cy, head.z);
  const fit = () => {
    const w = stage.clientWidth || 420, h = stage.clientHeight || w;
    renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix();
  };
  fit(); window.addEventListener("resize", fit);
  creditLine(creditEl, gltf.parser.json.asset && gltf.parser.json.asset.extras);

  const off = new THREE.Quaternion(), e = new THREE.Euler();
  const turn = (r, x, y, z) => { if (r) { e.set(x, y, z); off.setFromEuler(e); r.o.quaternion.copy(r.q).multiply(off); } };
  let glance = {x: 0, y: 0, until: 0}, nextBlink = 1500, blinkT = -1, last = 0, forced = null, lvl = 0;

  function update(t, level, state) {
    const dt = Math.min(0.1, (t - last) / 1000 || 0.016); last = t;
    if (forced !== null) level = forced;
    lvl += (level - lvl) * 0.3;
    const s = t / 1000, attentive = state === "hearing" || state === "thinking" ? 1 : 0;
    if (t > glance.until) {
      glance = {x: (Math.random() - 0.5) * 0.08, y: (Math.random() - 0.5) * 0.35 * (attentive ? 0.3 : 1), until: t + 1800 + Math.random() * 3200};
    }
    if (rigged) {
      const gx = (glance.x - attentive * 0.05), gy = glance.y;
      turn(B.chest, Math.sin(s * 1.5) * 0.012, 0, 0);                                        // breathing
      turn(B.spine, 0, 0, Math.sin(s * 0.35) * 0.012);                                       // weight shift
      turn(B.hips, 0, 0, -Math.sin(s * 0.35) * 0.01);
      turn(B.neck, gx * 0.4 + lvl * 0.05 * Math.sin(s * 7), gy * 0.4 + Math.sin(s * 0.6) * 0.02 * lvl, 0);
      turn(B.head, gx * 0.6 + lvl * 0.1 * Math.sin(s * 5.3 + 1), gy * 0.6 + Math.sin(s * 1.1) * 0.03 * lvl, Math.sin(s * 0.8) * 0.015 * (0.4 + lvl));
    }
    // blinking on the same timer as the 2D face's
    if (blinkT < 0 && t > nextBlink) { blinkT = 0; nextBlink = t + 2500 + Math.random() * 3500; }
    let blink = 0;
    if (blinkT >= 0) { blinkT += dt; const p = blinkT / 0.16; blink = p < 1 ? Math.sin(p * Math.PI) : 0; if (p >= 1) blinkT = -1; }
    if (vrm) { setW("aa", Math.min(1, lvl * 1.4)); setW("blink", blink); }
    for (const n of mouthKeys) setW(n, Math.min(1, lvl * 1.4) * (/jaw|open|^aa$/i.test(n) ? 1 : 0.8));
    for (const n of blinkKeys) setW(n, blink);
    for (const n of Object.keys(want)) { cur[n] = (cur[n] || 0) + (want[n] - (cur[n] || 0)) * (/blink/i.test(n) ? 0.8 : 0.35); apply(n, cur[n]); }
    if (vrm) vrm.update(dt);
    renderer.render(scene, cam);
  }
  return {update, setExpression, clearExpressions, names, expressions, forceLevel: v => { forced = v; }};
}
