"""The voice router's scorer for Morphogen (cell voice-route, S-193): reads the workload's lines on stdin and the
answers in $MORPHOGEN_PRIVATE/answers.json ({case id: "talk" | "work"}). The first tool counts as talk when it is
talk or a quick fact on the way to talking (lookup, calculate), as work when it does something (delegate, save_note,
read_notes, remind, search), as the trial did (scripts/trials/voice-route). Prints one JSON line: accuracy, and
talk and work recall, with cases_seen and cases_expected."""
import json, os, sys

TALK, WORK = {"talk", "lookup", "calculate"}, {"delegate", "save_note", "read_notes", "remind", "search"}
answers = json.load(open(os.path.join(os.environ["MORPHOGEN_PRIVATE"], "answers.json")))
got = {}
for line in sys.stdin:
    try:
        r = json.loads(line)
    except ValueError:
        continue
    if isinstance(r, dict) and r.get("case") in answers:
        t = r.get("tool")
        got[r["case"]] = "talk" if t in TALK else "work" if t in WORK else "none"
ok = {k: got.get(k) == v for k, v in answers.items()}
def recall(route):
    ks = [k for k, v in answers.items() if v == route]
    return sum(ok[k] for k in ks) / len(ks) if ks else 1.0
print(json.dumps({"accuracy": sum(ok.values()) / len(answers), "talk_recall": recall("talk"),
                  "work_recall": recall("work"), "cases_seen": len(got), "cases_expected": len(answers)}))
