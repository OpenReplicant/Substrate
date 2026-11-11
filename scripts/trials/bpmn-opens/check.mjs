// Does a BPMN tool open these files? bpmn-moddle (MIT) is the parser bpmn.io's modeler (bpmn-js) reads a file with:
// a file opens when it parses without warnings (unknown elements, unresolved references) and every flow node,
// flow, lane, pool and data object has a shape or edge in the diagram, which is what the modeler draws.
import { readFileSync } from "node:fs";
import { BpmnModdle } from "bpmn-moddle";

const moddle = new BpmnModdle();
let failed = 0;
for (const file of process.argv.slice(2)) {
  const { rootElement, warnings } = await moddle.fromXML(readFileSync(file, "utf8"));
  const drawn = new Set();
  const want = [];
  for (const d of rootElement.diagrams || [])
    for (const el of d.plane.planeElement || []) if (el.bpmnElement) drawn.add(el.bpmnElement.id);
  const walk = (el) => {
    for (const fe of el.flowElements || [])
      if (/^bpmn:(Task|.*Task|.*Event|.*Gateway|SequenceFlow|DataObjectReference|SubProcess|CallActivity)$/.test(fe.$type)) want.push(fe.id);
    for (const ls of el.laneSets || []) for (const l of ls.lanes || []) want.push(l.id);
  };
  for (const root of rootElement.rootElements) {
    if (root.$type === "bpmn:Process") walk(root);
    if (root.$type === "bpmn:Collaboration") for (const p of root.participants || []) want.push(p.id);
  }
  const undrawn = want.filter((id) => !drawn.has(id));
  const { xml } = await moddle.toXML(rootElement);
  const ok = warnings.length === 0 && undrawn.length === 0 && xml.length > 0;
  if (!ok) failed++;
  console.log(JSON.stringify({ file, ok, elements: want.length, drawn: want.length - undrawn.length, undrawn,
                               warnings: warnings.map((w) => w.message) }));
}
process.exit(failed ? 1 : 0);
