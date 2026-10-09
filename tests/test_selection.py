"""Test simulati (senza KiCad) della regola di selezione. Esegui: python tests/test_selection.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from selection import PadInfo, common_layers, pair_by_net  # noqa: E402

F, B = "F.Cu", "B.Cu"


def pad(name, net, layers=(F,)):
    return PadInfo(name, net, 0, 0, frozenset(layers))


def test_two_pads_per_net():
    pairs, problems = pair_by_net([pad("J1.1", "A"), pad("U1.1", "A"), pad("J1.2", "B"), pad("U1.2", "B")])
    assert set(pairs) == {"A", "B"} and not problems


def test_rejects_bad_counts_and_no_net():
    pairs, problems = pair_by_net([pad("J1.1", "A"), pad("U1.1", "C"), pad("U2.1", "C"), pad("U3.1", "C"), pad("R1.1", "")])
    assert pairs == {}
    assert len(problems) == 3  # A con 1 pad, C con 3 pad, R1.1 senza net


def test_common_layers():
    assert common_layers([pad("J1.1", "A", (F, B)), pad("U1.1", "A", (F,))]) == {F}
    assert common_layers([pad("J1.1", "A", (F,)), pad("U1.1", "A", (B,))]) == frozenset()
    assert common_layers([]) == frozenset()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
