"""Corsie parallele a una pista guida tracciata dall'utente. Nessuna dipendenza da KiCad.

L'utente traccia a mano una pista (la guida) con il router di KiCad. Ogni altra connessione
riceve una corsia: la guida spostata lateralmente di k * spaziatura, dalla parte dei suoi
pad. Il router (router.py) segue la corsia quando può e se ne allontana per aggirare gli
ostacoli.

Unità: nanometri. Coordinate come in KiCad (y verso il basso).
"""
import math

TOL = 2           # nm: tolleranza su arrotondamenti e confronti di punti
FAR = 10**9       # 1 m: prolungamento dei tratti estremi delle corsie oltre i pad
COMPACT_FACTOR = 1.5     # sui tratti lunghi: distanza tra piste = 1.5 x (larghezza + clearance)
COMPACT_MIN_RATIO = 2.0  # un tratto è "lungo" se supera 2 x la larghezza del fascio ai pad


class FollowError(Exception):
    pass


def is_octilinear(a, b):
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    return dx <= TOL or dy <= TOL or abs(dx - dy) <= TOL


def chain(segments, near_start):
    """Ordina i segmenti della guida in una polilinea, partendo dall'estremo più vicino a near_start.
    Errore se non è una sola catena senza diramazioni o interruzioni."""
    error = FollowError("La pista guida deve essere una sola catena di segmenti da pad a pad, "
                        "senza diramazioni o interruzioni.")
    ends = [p for s in segments for p in s]
    tips = [p for p in ends if sum(math.dist(p, q) <= TOL for q in ends) == 1]
    if len(tips) != 2:
        raise error
    left = list(segments)
    pts = [min(tips, key=lambda p: math.dist(p, near_start))]
    while left:
        cur = pts[-1]
        nxt = [s for s in left if math.dist(s[0], cur) <= TOL or math.dist(s[1], cur) <= TOL]
        if len(nxt) != 1:
            raise error
        a, b = nxt[0]
        left.remove(nxt[0])
        pts.append(b if math.dist(a, cur) <= TOL else a)
    return simplify(pts)


def simplify(pts):
    """Toglie punti doppi e punti intermedi su tratti allineati."""
    out = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, out[-1]) <= TOL:
            continue
        if len(out) >= 2:
            (ax, ay), (bx, by) = out[-2], out[-1]
            if abs((bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)) <= TOL * math.dist(out[-2], p):
                out[-1] = p
                continue
        out.append(p)
    return out


def _unit(a, b):
    d = math.dist(a, b)
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def side_offset(pts, p, at_end=False):
    """Distanza con segno di p dalla retta del primo (o ultimo) tratto della guida: >0 a sinistra."""
    a, b = (pts[-2], pts[-1]) if at_end else (pts[0], pts[1])
    ux, uy = _unit(a, b)
    return ux * (p[1] - a[1]) - uy * (p[0] - a[0])


def offset_polyline(pts, offsets):
    """Copia della polilinea spostata lateralmente (>0 a sinistra), un valore per tratto,
    con i tratti estremi prolungati di FAR. Gli spigoli sono le intersezioni delle rette spostate,
    quindi un cambio di spostamento tra due tratti avviene nello spigolo senza angoli nuovi."""
    lines = []
    for d, (a, b) in zip(offsets, zip(pts, pts[1:])):
        ux, uy = _unit(a, b)
        lines.append(((a[0] - d * uy, a[1] + d * ux), (ux, uy)))
    (p0, u0), (pn, un) = lines[0], lines[-1]
    out = [(p0[0] - FAR * u0[0], p0[1] - FAR * u0[1])]
    for (p1, u1), (p2, u2) in zip(lines, lines[1:]):
        den = u1[0] * u2[1] - u1[1] * u2[0]
        if abs(den) < 1e-12:
            raise FollowError("La pista guida ha due tratti consecutivi allineati: semplificala e riprova.")
        t = ((p2[0] - p1[0]) * u2[1] - (p2[1] - p1[1]) * u2[0]) / den
        out.append((p1[0] + t * u1[0], p1[1] + t * u1[1]))
    out.append((pn[0] + (math.dist(pts[-2], pts[-1]) + FAR) * un[0],
                pn[1] + (math.dist(pts[-2], pts[-1]) + FAR) * un[1]))
    return out


def ideal_path(lane, a, b):
    """Percorso esatto pad a -> corsia -> pad b, se i pad stanno sui tratti estremi della corsia
    e non si torna indietro. Altrimenti None (servirà il router)."""
    (l0, l1), (lm, ln) = (lane[0], lane[1]), (lane[-2], lane[-1])

    def on_line(p, q, r):  # p sulla retta q-r, prima di r
        ux, uy = _unit(q, r)
        return (abs(ux * (p[1] - q[1]) - uy * (p[0] - q[0])) <= TOL
                and (r[0] - p[0]) * ux + (r[1] - p[1]) * uy >= -TOL)

    if not (on_line(a, l0, l1) and on_line(b, ln, lm)):
        return None
    pts = simplify([a] + [(round(x), round(y)) for x, y in lane[1:-1]] + [b])
    forward = (pts[1][0] - pts[0][0]) * (l1[0] - l0[0]) + (pts[1][1] - pts[0][1]) * (l1[1] - l0[1]) > 0
    # svolte oltre 90°: la copia "si ripiega" (spostamento troppo grande all'interno di una curva)
    folds = any((q[0] - p[0]) * (r[0] - q[0]) + (q[1] - p[1]) * (r[1] - q[1]) < 0
                for p, q, r in zip(pts, pts[1:], pts[2:]))
    ok = forward and not folds and all(is_octilinear(p, q) for p, q in zip(pts, pts[1:]))
    return pts if ok else None


def _long_segments(guide, bus_width):
    """Tratti intermedi della guida su cui conviene stringere il fascio: i più lunghi di
    COMPACT_MIN_RATIO volte la larghezza del fascio (non il primo né l'ultimo, attaccati ai pad)."""
    return [i for i, (a, b) in enumerate(zip(guide, guide[1:]))
            if 0 < i < len(guide) - 2 and math.dist(a, b) >= COMPACT_MIN_RATIO * bus_width]


def _offsets(n, d_start, d_end, compact, long_idx):
    """Spostamento per ciascuno degli n tratti: distanza del pad vicino ai capi, compatto sui tratti
    lunghi (e tra un tratto lungo e l'altro)."""
    if not long_idx:
        return [d_start] * (n - 1) + [d_end]
    first, last = min(long_idx), max(long_idx)
    return [d_start if i < first else d_end if i > last else compact for i in range(n - 1)] + [d_end]


def assign_lanes(guide, connections, pitch):
    """Assegna a ogni connessione la sua corsia parallela alla guida.

    Vicino ai pad la corsia sta alla distanza del pad dalla guida (misurata a ciascuno dei due capi),
    così le piste escono ed entrano dritte. Sui tratti lunghi della guida il fascio si stringe a
    COMPACT_FACTOR * pitch tra le piste, se la geometria lo permette per tutte; altrimenti si
    mantiene la spaziatura dei pad ovunque.

    guide: polilinea della guida (dal pad iniziale al finale).
    connections: [(net, pad_a, pad_b)] per le altre net, pad in ordine qualsiasi.
    pitch: distanza minima tra gli assi di due piste (larghezza + clearance).
    Restituisce ([(net, pad_iniziale, pad_finale, corsia, percorso_ideale_o_None)] dall'interno
    del fascio verso l'esterno, True se il fascio è stato stretto).
    """
    s, e = guide[0], guide[-1]
    items = []
    for net, a, b in connections:
        if math.dist(a, s) + math.dist(b, e) > math.dist(b, s) + math.dist(a, e):
            a, b = b, a  # a = lato iniziale della guida
        items.append((net, a, b, side_offset(guide, a), side_offset(guide, b, at_end=True)))

    # Ordine laterale: deve essere lo stesso ai due capi, altrimenti le piste si incrocerebbero.
    def ranks(col):
        lefts = sorted((it for it in items if it[col] > 0), key=lambda it: it[col])
        rights = sorted((it for it in items if it[col] <= 0), key=lambda it: -it[col])
        return {it[0]: k + 1 for k, it in enumerate(lefts)} | {it[0]: -(k + 1) for k, it in enumerate(rights)}

    at_start, at_end = ranks(3), ranks(4)
    if at_start != at_end:
        raise FollowError("I pad non hanno lo stesso ordine ai due capi rispetto alla guida: "
                          "su un solo layer le piste si incrocerebbero.")
    items.sort(key=lambda it: abs(at_start[it[0]]))

    def build(long_idx):
        result = []
        for net, a, b, d_start, d_end in items:
            compact = at_start[net] * COMPACT_FACTOR * pitch
            lane = tuple(offset_polyline(guide, _offsets(len(guide) - 1, d_start, d_end, compact, long_idx)))
            result.append((net, a, b, lane, ideal_path(lane, a, b)))
        return result

    bus_width = max(max(abs(it[3]), abs(it[4])) for it in items)
    long_idx = _long_segments(guide, bus_width)
    if long_idx:
        compacted = build(long_idx)
        if all(lane[4] for lane in compacted):  # stretto solo se torna per tutte le piste
            return compacted, True
    return build([]), False
