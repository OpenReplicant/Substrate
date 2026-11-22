"""Checks that need no game: python3 -m envkit.test_envkit (or pytest)."""
from __future__ import annotations

from envkit.core import Environment, Lockstep, Module, Port, World, attach


class W(World):
    outputs = {"frame": Port("grid16"), "ram": Port("json", fair=False), "extra": Port("json"),
               "tick": Port("event")}
    inputs = {"cmd": Port("command")}

    def __init__(self, name, ticks=3):
        super().__init__(name)
        self.ticks, self.got = ticks, []

    def on(self, port, msg):
        self.got.append(msg.data)

    def tick(self, t):
        self.emit("frame", t)
        self.emit("tick", t)
        self.done = t + 1 >= self.ticks


class A(Module):
    kind = "agent"

    def __init__(self, name):
        self.inputs = {"x": Port("json"), "tick": Port("event")}
        self.outputs = {"cmd": Port("command")}
        super().__init__(name)
        self.seen, self.acted = None, []

    def on(self, port, msg):
        if port == "x":
            self.seen = msg.data
        else:
            self.acted.append(self.seen)
            self.emit("cmd", self.seen)


class Double(Module):
    kind = "encoder"
    inputs = {"in": Port("json")}
    outputs = {"out": Port("json")}

    def on(self, port, msg):
        self.emit("out", msg.data * 2)


def env(*extra):
    return Environment("t", [W("game"), *extra],
                       expose={"frame": "game.frame", "ram": "game.ram", "extra": "game.extra", "cmd": "game.cmd",
                               "tick": "game.tick", "double": "enc.out"},
                       profiles={"judged": ["frame", "ram", "tick", "double"], "train": ["frame", "ram", "extra",
                                                                                         "tick", "double"]})


def test_fairness():
    """An agent may read what its profile lists and the world marks fair; anything, with no profile."""
    want = {("frame", "judged"): True, ("ram", "judged"): False, ("extra", "judged"): False,
            ("extra", "train"): True, ("ram", "train"): False, ("ram", None): True}
    for (exposed, profile), ok in want.items():
        try:
            attach(env(), A("a"), {"x": exposed, "cmd": "cmd"}, profile=profile)
            got = True
        except PermissionError:
            got = False
        assert got == ok, (exposed, profile, got)


def test_taps_are_not_judged():
    t = A("t")
    t.kind = "tap"
    attach(env(), t, {"x": "ram"}, profile="judged")


def test_encoder_output_reaches_agent_before_tick():
    """Depth first: the world's frame goes through the encoder and reaches the agent before the world's tick."""
    enc = Double("enc")
    e = env(enc)
    enc.wired_in["in"] = "game.frame"
    a = A("a")
    attach(e, a, {"x": "double", "tick": "tick", "cmd": "cmd"}, profile="judged")
    Lockstep(e.modules + [a]).run()
    assert a.acted == [0, 2, 4], a.acted
    assert e.modules[0].got == [0, 2, 4]


def test_workspace_binds_expires_and_focuses():
    from envkit.core import Msg
    from envkit.workspace import Workspace
    out = []

    class Bus:
        def publish(self, m, ch, data):
            out.append((ch, data))

    w = Workspace("ws", capacity=2)
    w._rt = Bus()
    post = lambda t, es: w.on("post", Msg("ws.post", t, 0, "x", es))  # noqa: E731
    tick = lambda t: w.on("tick", Msg("game.tick", t, 0, "game", {}))  # noqa: E731
    post(0, [{"key": "thing:1", "attrs": {"box": [0, 0, 1, 1]}, "source": "sight", "ttl": 1},
             {"key": "claim:self", "attrs": {"thing": 1}, "source": "mover", "salience": 0.5},
             {"key": "pit", "attrs": {"col": 3}, "source": "mover", "salience": 0.9}])
    post(0, [{"key": "thing:1", "attrs": {"name": "walker"}, "source": "model"}])
    tick(0)
    state = dict(out)["ws.state"]
    th = next(e for e in state["entries"] if e["key"] == "thing:1")
    assert th["attrs"] == {"box": [0, 0, 1, 1], "name": "walker"}  # two sources, one entry
    assert th["by"]["box"][0] == "sight" and th["by"]["name"][0] == "model"
    assert [e["key"] for e in dict(out)["ws.focus"]] == ["pit", "claim:self"]  # capacity 2, by salience
    out.clear()
    tick(1)  # thing:1 not posted again: gone; claims have no ttl and stay
    assert sorted(e["key"] for e in dict(out)["ws.state"]["entries"]) == ["claim:self", "pit"]
    assert dict(out)["ws.changed"]["dropped"] == ["thing:1"]
    out.clear()
    post(2, [{"key": "pit", "retract": True}])
    tick(2)
    assert [e["key"] for e in dict(out)["ws.state"]["entries"]] == ["claim:self"]


def test_cartographer_takes_an_earlier_answer_without_asking_again():
    """An answer given since an earlier run settles its question: a claim, no new interview, budget kept."""
    import pytest
    pytest.importorskip("atlas", reason="the cartographer lives in MetaSoar's atlas, not installed here")
    from atlas.cartographer import Cartographer
    from envkit.org import qid
    c = Cartographer(["wait", "interview", "delegate"], budget=1)
    day = 20000
    commits = [{"repo": "r", "sha": f"s{i}", "t": (day + i) * 86400, "author": who, "coauthors": [], "areas": []}
               for i, who in enumerate(["Ann", "Bot", "Ann"])]
    q = "Which of these identities are you (or act for you): Ann, Bot? The history can't tell an organization's account from a person's."
    entries = [{"key": f"commit:{x['sha']}", "kind": "commit", "attrs": x} for x in commits]
    entries += [{"key": "e", "kind": "event", "attrs": {"kind": "start", "day": day, "until": day + 2}},
                {"key": "reply", "kind": "reply", "attrs": {"id": qid("principal", q), "answer": "I am Ann"}}]
    act, params = c.step({"state": {"t": 3, "entries": entries}})
    assert c.principal == ["Ann"], c.principal
    assert act == "wait" or params["why"] != "principal", params
    f = c.predict(horizon=7)
    assert 0 < f["r"] < 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
