"""Router a corsie su un solo layer. Nessuna dipendenza da KiCad.

Unità: nanometri, come l'API di KiCad. Coordinate come in KiCad (y verso il basso).

Idea
- Ogni connessione ha una corsia: una polilinea che dice dove la pista "dovrebbe" stare
  (copia spostata della pista guida, vedi follow.py).
- Griglia regolare sulla regione di lavoro. Una cella è libera per la net N se il suo
  centro dista da ogni ostacolo di altre net più di: metà larghezza + clearance + margine
  di griglia. Il margine (passo * sqrt(2)/2) garantisce che anche i tratti tra due centri
  liberi adiacenti rispettino la clearance.
- A* a 8 direzioni (solo 0/45/90°). Costo di un passo = lunghezza + svolte + distanza
  dalla propria corsia oltre una piccola tolleranza. Senza ostacoli la pista sta sulla
  corsia; con un ostacolo devia solo quanto serve e poi rientra.
- Le piste vengono posate una alla volta (dall'interno del fascio verso l'esterno) e
  diventano ostacoli per le successive.
- Alla fine ogni segmento viene ricontrollato con distanze geometriche esatte.
"""
import heapq
import math
from array import array
from dataclasses import dataclass

# Pesi della funzione di costo. Modificabili qui.
WEIGHTS = {
    "turn": 1.0,   # per ogni svolta di 45°, in passi di griglia
    "lane": 0.3,   # per passo, per ogni nm di distanza dalla corsia oltre la tolleranza
}
MAX_CELLS = 2_000_000
MIN_STEP = 10_000          # 0.01 mm
# ponytail: A* con euristica pesata (molto più veloce, costo fino a 1.5x l'ottimo);
# portare a 1.0 se serve l'ottimo e il tempo lo consente.
HEURISTIC_WEIGHT = 1.5

_DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]  # indice = angolo/45°
_BLOCKED = -1


class RoutingError(Exception):
    pass


@dataclass(frozen=True)
class Obstacle:
    net: str            # "" = nessuna net: blocca tutte le connessioni
    points: tuple       # ((x, y), ...): un punto = cerchio, più punti = polilinea
    radius: int         # metà larghezza / raggio (per i poligoni: margine di approssimazione)
    clearance: int
    closed: bool = False  # True = poligono pieno


@dataclass(frozen=True)
class Connection:
    net: str
    start: tuple
    end: tuple
    lane: tuple         # polilinea della corsia
    ideal: tuple = None  # percorso esatto lungo la corsia, usato se non urta nulla


@dataclass
class Route:
    net: str
    points: list        # polilinea dal pad di partenza al pad di arrivo
    length: float
    turns: int


def grid_step(width, clearance):
    return max(MIN_STEP, (width + clearance) // 4)


# ---------- geometria ----------

def _dist_pt_seg(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def _segments_cross(a, b, c, d):
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 0) - (v < 0)
    return orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0


def _dist_seg_seg(a, b, c, d):
    if _segments_cross(a, b, c, d):
        return 0.0
    return min(_dist_pt_seg(a, c, d), _dist_pt_seg(b, c, d), _dist_pt_seg(c, a, b), _dist_pt_seg(d, a, b))


def _inside(p, poly):
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _edges(o):
    pts = list(o.points)
    if len(pts) == 1:
        return [(pts[0], pts[0])]
    edges = list(zip(pts, pts[1:]))
    if o.closed:
        edges.append((pts[-1], pts[0]))
    return edges


def _dist_pt_obstacle(p, o):
    if o.closed and _inside(p, list(o.points)):
        return 0.0
    return min(_dist_pt_seg(p, a, b) for a, b in _edges(o))


def _dist_seg_obstacle(a, b, o):
    if o.closed and (_inside(a, list(o.points)) or _inside(b, list(o.points))):
        return 0.0
    return min(_dist_seg_seg(a, b, c, d) for c, d in _edges(o))


def _dist_pt_polyline(p, pts):
    return min(_dist_pt_seg(p, a, b) for a, b in zip(pts, pts[1:]))


def _polyline_length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _dogleg(p, c):
    """Da p a c con al più due tratti a 0/45/90° (diagonale poi dritto)."""
    dx, dy = c[0] - p[0], c[1] - p[1]
    d = min(abs(dx), abs(dy))
    corner = (p[0] + math.copysign(d, dx), p[1] + math.copysign(d, dy))
    return [p, corner, c]


def _simplify(pts):
    """Toglie punti doppi e punti intermedi su tratti allineati."""
    out = [pts[0]]
    for p in pts[1:]:
        if p == out[-1]:
            continue
        if len(out) >= 2:
            (ax, ay), (bx, by) = out[-2], out[-1]
            if (bx - ax) * (p[1] - ay) == (by - ay) * (p[0] - ax):
                out[-1] = p
                continue
        out.append(p)
    return out


# ---------- griglia ----------

class _Grid:
    """Celle: 0 libera, k>0 bloccata solo dalla net del gruppo k, -1 bloccata per tutti."""

    def __init__(self, region, step):
        self.x0, self.y0, x1, y1 = region
        self.step = step
        self.nx = int((x1 - self.x0) // step) + 1
        self.ny = int((y1 - self.y0) // step) + 1
        if self.nx * self.ny > MAX_CELLS:
            raise RoutingError(f"Area di lavoro troppo grande per la griglia ({self.nx}x{self.ny} celle).")
        self.cells = array("i", bytes(4 * self.nx * self.ny))

    def center(self, i, j):
        return (self.x0 + i * self.step, self.y0 + j * self.step)

    def nearest(self, p):
        i = min(max(round((p[0] - self.x0) / self.step), 0), self.nx - 1)
        j = min(max(round((p[1] - self.y0) / self.step), 0), self.ny - 1)
        return i, j

    def block(self, o, inflate, owner):
        if not o.closed and len(o.points) > 2:  # polilinea: un riquadro per segmento, molto più piccolo
            for a, b in zip(o.points, o.points[1:]):
                self.block(Obstacle(o.net, (a, b), o.radius, o.clearance), inflate, owner)
            return
        xs = [p[0] for p in o.points]
        ys = [p[1] for p in o.points]
        reach = inflate + o.radius
        i0, j0 = self.nearest((min(xs) - reach, min(ys) - reach))
        i1, j1 = self.nearest((max(xs) + reach, max(ys) + reach))
        cells, nx = self.cells, self.nx
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                k = j * nx + i
                v = cells[k]
                if v == _BLOCKED or v == owner:
                    continue
                if _dist_pt_obstacle(self.center(i, j), o) < reach:
                    cells[k] = owner if v == 0 and owner > 0 else _BLOCKED


# ---------- instradamento ----------

def _astar(grid, owner, conn, slack, w):
    step = grid.step
    nx, ny, cells = grid.nx, grid.ny, grid.cells
    si, sj = grid.nearest(conn.start)
    ti, tj = grid.nearest(conn.end)
    for i, j, label in ((si, sj, "partenza"), (ti, tj, "arrivo")):
        if cells[j * nx + i] not in (0, owner):
            raise RoutingError(f"net {conn.net}: pad di {label} troppo vicino a un ostacolo per la griglia.")

    lane_cost = {}

    def extra(i, j):
        k = j * nx + i
        if k not in lane_cost:
            d = _dist_pt_polyline(grid.center(i, j), conn.lane)
            lane_cost[k] = w["lane"] * max(0.0, d - slack)
        return lane_cost[k]

    def h(i, j):
        dx, dy = abs(i - ti), abs(j - tj)
        return HEURISTIC_WEIGHT * step * (max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy))

    start, goal = sj * nx + si, tj * nx + ti
    g = {start: 0.0}
    came = {start: (None, None)}  # cella -> (cella precedente, direzione d'arrivo)
    heap = [(h(si, sj), 0.0, start)]
    while heap:
        _, gc, k = heapq.heappop(heap)
        if k == goal:
            break
        if gc > g[k]:
            continue
        i, j = k % nx, k // nx
        prev_dir = came[k][1]
        for d, (di, dj) in enumerate(_DIRS):
            ni, nj = i + di, j + dj
            if not (0 <= ni < nx and 0 <= nj < ny):
                continue
            nk = nj * nx + ni
            if cells[nk] not in (0, owner):
                continue
            cost = step * (math.sqrt(2) if di and dj else 1.0)
            if prev_dir is not None and d != prev_dir:
                cost += w["turn"] * step * min(abs(d - prev_dir), 8 - abs(d - prev_dir))
            cost += extra(ni, nj)
            ng = gc + cost
            if ng < g.get(nk, math.inf):
                g[nk] = ng
                came[nk] = (k, d)
                heapq.heappush(heap, (ng + h(ni, nj), ng, nk))
    else:
        raise RoutingError(f"net {conn.net}: nessun percorso libero sul layer.")

    path = []
    k = goal
    while k is not None:
        path.append(grid.center(k % nx, k // nx))
        k = came[k][0]
    path.reverse()
    # Aggancio griglia-pad: meno di mezzo passo, resta dentro il rame del pad, sempre a 0/45/90°.
    pts = _simplify(_dogleg(conn.start, path[0])[:-1] + path + _dogleg(conn.end, path[-1])[::-1][1:])
    return Route(conn.net, pts, _polyline_length(pts), len(pts) - 2)


def _segment_conflict(a, b, net, obstacles, width, clearance):
    """Primo ostacolo di un'altra net troppo vicino al segmento a-b, con la distanza; None se libero."""
    for o in obstacles:
        if o.net == net:
            continue
        need = width / 2 + max(clearance, o.clearance) + o.radius
        d = _dist_seg_obstacle(a, b, o)
        if d < need - 1:  # 1 nm di tolleranza numerica
            return o, d, need
    return None


def _as_obstacles(routes, width, clearance):
    return [Obstacle(r.net, tuple(r.points), width // 2, clearance) for r in routes]


def violations(routes, obstacles, width, clearance):
    """Controllo esatto finale: ogni segmento contro ostacoli e piste di altre net."""
    found = []
    all_obs = list(obstacles) + _as_obstacles(routes, width, clearance)
    for r in routes:
        for a, b in zip(r.points, r.points[1:]):
            hit = _segment_conflict(a, b, r.net, all_obs, width, clearance)
            if hit:
                o, d, need = hit
                found.append(f"net {r.net}: distanza {d / 1e6:.3f} mm da net {o.net or '-'} "
                             f"(minimo {need / 1e6:.3f} mm)")
    return found


def route_lanes(connections, obstacles, width, clearance, region, origin, w=WEIGHTS):
    """Instrada le connessioni nell'ordine dato (di solito dall'interno del fascio verso l'esterno).

    origin: punto su cui allineare la griglia (es. inizio della guida), così le corsie cadono sulla griglia.
    Restituisce le Route o solleva RoutingError. Non lascia mai una soluzione che violi la clearance.
    """
    if not connections:
        raise RoutingError("Nessuna connessione da instradare.")
    step = grid_step(width, clearance)
    margin = math.ceil(step * math.sqrt(2) / 2)
    ids = {c.net: n + 1 for n, c in enumerate(connections)}
    grid = None  # costruita solo se una pista deve davvero deviare

    def build_grid():
        x0 = origin[0] - math.ceil((origin[0] - region[0]) / step) * step
        y0 = origin[1] - math.ceil((origin[1] - region[1]) / step) * step
        g = _Grid((x0, y0, region[2], region[3]), step)
        for o in obstacles:
            g.block(o, width / 2 + max(clearance, o.clearance) + margin, ids.get(o.net, _BLOCKED))
        for r in routes:
            g.block(Obstacle(r.net, tuple(r.points), width // 2, clearance), width / 2 + clearance + margin, ids[r.net])
        return g

    slack = step  # entro un passo dalla corsia nessuna penalità
    routes = []
    for conn in connections:
        placed = list(obstacles) + _as_obstacles(routes, width, clearance)
        if conn.ideal and not any(_segment_conflict(a, b, conn.net, placed, width, clearance)
                                  for a, b in zip(conn.ideal, conn.ideal[1:])):
            pts = list(conn.ideal)  # la copia esatta della guida è libera: rette perfette
            route = Route(conn.net, pts, _polyline_length(pts), len(pts) - 2)
        else:
            grid = grid or build_grid()
            route = _astar(grid, ids[conn.net], conn, slack, w)  # devia attorno agli ostacoli
        routes.append(route)
        if grid:
            grid.block(Obstacle(conn.net, tuple(route.points), width // 2, clearance),
                       width / 2 + clearance + margin, ids[conn.net])

    bad = violations(routes, obstacles, width, clearance)
    if bad:
        raise RoutingError("Soluzione scartata dal controllo clearance:\n" + "\n".join(bad))
    return routes
