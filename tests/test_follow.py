"""Test simulati (senza KiCad) di corsie + router. Esegui: python tests/test_follow.py"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from follow import FollowError, assign_lanes, chain, is_octilinear  # noqa: E402
from router import Connection, Obstacle, RoutingError, route_lanes, violations  # noqa: E402

MM = 1_000_000
W, C = 200_000, 200_000


def column(x, y0, n, step=-4 * MM):
    return [(x, y0 + k * step) for k in range(n)]


def pads(*cols):
    """Pad tondi da 1.7 mm come ostacoli, net N0, N1... nell'ordine della colonna."""
    return [Obstacle(f"N{k}", (p,), 850_000, C) for col in cols for k, p in enumerate(col)]


def bus(obstacles_extra=()):
    """Come la board di prova: due colonne da 5 pad, guida (N0) già tracciata sul pad più basso."""
    a = column(0, 0, 5)
    b = column(44 * MM, -9 * MM, 5)
    guide = [a[0], (20 * MM, 0), (29 * MM, -9 * MM), b[0]]  # orizzontale, 45°, orizzontale
    lanes, _ = assign_lanes(guide, [(f"N{k}", a[k], b[k]) for k in range(1, 5)], W + C)
    conns = [Connection(*lane) for lane in lanes]
    obstacles = pads(a, b) + [Obstacle("N0", tuple(guide), W // 2, C)] + list(obstacles_extra)
    region = (-12 * MM, -40 * MM, 56 * MM, 12 * MM)
    t = time.time()
    routes = route_lanes(conns, obstacles, W, C, region, origin=guide[0])
    print(f"   {time.time() - t:.1f} s")
    return routes, conns, obstacles


def check_common(routes, obstacles):
    for r in routes:
        assert all(is_octilinear(p, q) for p, q in zip(r.points, r.points[1:])), r.points
    assert not violations(routes, obstacles, W, C)


def test_parallel_bus_without_obstacles():
    # Senza ostacoli: copie esatte della guida, con la spaziatura dei pad (4 mm), solo rette.
    routes, conns, obstacles = bus()
    check_common(routes, obstacles)
    for k, (r, c) in enumerate(zip(routes, conns), start=1):
        assert r.points == list(c.ideal), r.net
        assert len(r.points) == 4  # orizzontale, 45°, orizzontale (come la guida)
        assert r.points[1][1] == -k * 4 * MM  # primo tratto orizzontale all'altezza del suo pad


def test_single_track_detours_around_obstacle():
    blocker = Obstacle("X", ((10 * MM, -8 * MM),), 400_000, C)  # sul tratto orizzontale di N2
    routes, conns, obstacles = bus([blocker])
    check_common(routes, obstacles)
    detoured = [r.net for r, c in zip(routes, conns) if r.points != list(c.ideal)]
    assert detoured == ["N2"], detoured


def test_crossing_order_is_rejected():
    a = column(0, 0, 3)
    b = column(44 * MM, 0, 3)
    try:
        assign_lanes([a[0], b[0]], [("N1", a[1], b[2]), ("N2", a[2], b[1])], W + C)
    except FollowError:
        return
    raise AssertionError("doveva rifiutare l'incrocio")


def test_no_path_means_error():
    wall = Obstacle("", ((10 * MM, -40 * MM), (10 * MM, 12 * MM)), 0, C)
    try:
        bus([wall])
    except RoutingError:
        return
    raise AssertionError("doveva fallire")


def test_chain_orders_segments_and_rejects_branches():
    s, m, e = (0, 0), (10, 0), (20, 10)
    assert chain([(e, m), (s, m)], s) == [s, m, e]
    assert chain([(e, m), (s, m)], e) == [e, m, s]
    try:
        chain([(s, m), (m, e), (m, (10, 50))], s)
    except FollowError:
        return
    raise AssertionError("doveva rifiutare la diramazione")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(name)
            fn()
    print("ok")
