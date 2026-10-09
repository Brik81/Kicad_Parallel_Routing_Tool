"""Lettura dalla board KiCad (IPC API / kipy): pad selezionati, regole e ostacoli.

Converte gli oggetti kipy nei tipi semplici di selection.py e router.py.
Le sole funzioni che modificano la board sono apply_routes e remove_routes.
"""
import math

from kipy.board_types import (ArcTrack, BoardArc, BoardCircle, BoardPolygon, BoardRectangle, BoardSegment, Pad,
                              PadStackShape, Track)
from kipy.geometry import Vector2
from kipy.proto.common.commands import editor_commands_pb2
from kipy.proto.common.types.base_types_pb2 import ItemHeader
from kipy.util.board_layer import BoardLayer, canonical_name, is_copper_layer

from follow import chain
from router import Obstacle
from selection import PadInfo

REGION_MARGIN = 10_000_000  # 10 mm attorno ai pad del gruppo: spazio per le deviazioni
ARC_SEGMENT_ANGLE = math.pi / 16


# ---------- selezione ----------

def read_selected_pads(board):
    """Restituisce (lista PadInfo, {nome pad: Pad kipy}, numero di oggetti selezionati che non sono pad)."""
    selection = board.get_selection()
    pads = [item for item in selection if isinstance(item, Pad)]
    others = len(selection) - len(pads)
    if not pads:
        return [], {}, others

    refs = {fp.id.value: fp.reference_field.text.value for fp in board.get_footprints()}
    copper = [layer for layer in board.get_enabled_layers() if is_copper_layer(layer)]
    presence = board.check_padstack_presence_on_layers(pads, copper)
    layers_by_id = {
        item.id.value: frozenset(canonical_name(l) for l, present in by_layer.items() if present)
        for item, by_layer in presence.items()
    }

    infos, by_name = [], {}
    for p in pads:
        ref = refs.get(p.parent.value, "?") if p.parent else "?"
        name = f"{ref}.{p.number}"
        infos.append(PadInfo(name, p.net.name, p.position.x, p.position.y,
                             layers_by_id.get(p.id.value, frozenset())))
        by_name[name] = p
    return infos, by_name, others


def already_connected(board, pad_a, pad_b):
    """True se KiCad considera i due pad già collegati (piste, zone...)."""
    return any(item.id.value == pad_b.id.value for item in board.get_connected_items(pad_a))


# ---------- scrittura ----------

def _with_document(msg, field_number, board):
    """Aggiunge a msg il campo ItemHeader con il documento della board.

    KiCad 10.0.7 lo richiede in BeginCommit (campo 1) ed EndCommit (campo 4) quando sono aperti
    più editor, ma kipy 0.8.0 non ha ancora quei campi: li scriviamo a mano in formato protobuf
    (il messaggio conserva i campi che non conosce e li reinvia).
    ponytail: rimuovere quando kicad-python avrà i campi header nei commit.
    """
    header = ItemHeader()
    header.document.CopyFrom(board._doc)
    raw = header.SerializeToString()

    def varint(n):
        out = bytearray()
        while True:
            out.append((n & 0x7F) | (0x80 if n > 0x7F else 0))
            n >>= 7
            if not n:
                return bytes(out)

    msg.MergeFromString(varint(field_number << 3 | 2) + varint(len(raw)) + raw)
    return msg


def _begin_commit(board):
    cmd = _with_document(editor_commands_pb2.BeginCommit(), 1, board)
    return board._kicad.send(cmd, editor_commands_pb2.BeginCommitResponse).id


def _end_commit(board, commit_id, action, message=""):
    cmd = editor_commands_pb2.EndCommit()
    cmd.id.CopyFrom(commit_id)
    cmd.action = action
    cmd.message = message
    board._kicad.send(_with_document(cmd, 4, board), editor_commands_pb2.EndCommitResponse)

def apply_routes(board, routes, nets, layer, width):
    """Crea le piste in un unico commit (un solo passo di annulla). Restituisce gli oggetti creati."""
    tracks = []
    for r in routes:
        for a, b in zip(r.points, r.points[1:]):
            t = Track()
            t.start = Vector2.from_xy(round(a[0]), round(a[1]))
            t.end = Vector2.from_xy(round(b[0]), round(b[1]))
            t.width = width
            t.layer = layer
            t.net = nets[r.net]
            tracks.append(t)
    commit = _begin_commit(board)
    try:
        created = board.create_items(tracks)
        if len(created) != len(tracks):
            raise RuntimeError(f"KiCad ha creato {len(created)} piste su {len(tracks)}.")
    except Exception:
        _end_commit(board, commit, editor_commands_pb2.CMA_DROP)
        raise
    _end_commit(board, commit, editor_commands_pb2.CMA_COMMIT, "Parallel Routing Tool")
    return created


def remove_routes(board, created):
    """Rimuove solo le piste create dal plugin, in un unico commit."""
    commit = _begin_commit(board)
    try:
        board.remove_items(created)
    except Exception:
        _end_commit(board, commit, editor_commands_pb2.CMA_DROP)
        raise
    _end_commit(board, commit, editor_commands_pb2.CMA_COMMIT, "Parallel Routing Tool: rimozione proposta")


# ---------- pista guida ----------

def read_guide(board, net_name, near_start):
    """Segmenti della pista guida (tutte le piste della net): (punti, larghezza, layer).
    Accetta solo segmenti dritti su un unico layer."""
    tracks = [t for t in board.get_tracks() if t.net.name == net_name]
    if any(isinstance(t, ArcTrack) for t in tracks):
        raise ValueError("La pista guida contiene archi: usa solo segmenti dritti.")
    layers = {t.layer for t in tracks}
    widths = {t.width for t in tracks}
    if len(layers) != 1 or len(widths) != 1:
        raise ValueError("La pista guida deve stare su un solo layer e avere una sola larghezza.")
    pts = chain([(_xy(t.start), _xy(t.end)) for t in tracks], near_start)
    return pts, widths.pop(), layers.pop()


# ---------- regole ----------

def group_rules(board, nets):
    """(larghezza, clearance) per il gruppo: il massimo tra le netclass delle net coinvolte."""
    classes = board.get_netclass_for_nets(list(nets))
    widths = [nc.track_width for nc in classes.values()]
    clearances = [nc.clearance for nc in classes.values()]
    if not classes or None in widths or None in clearances:
        raise ValueError("Larghezza pista o clearance non definita nella netclass di qualche net del gruppo.")
    return max(widths), max(clearances)


# ---------- geometria ----------

def _xy(v):
    return (v.x, v.y)


def _arc_points(start, mid, end):
    """Approssima un arco con una polilinea. Restituisce (punti, sagitta massima)."""
    (x1, y1), (x2, y2), (x3, y3) = start, mid, end
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if d == 0:  # punti allineati: è un segmento
        return [start, end], 0
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    cx = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    cy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    r = math.hypot(x1 - cx, y1 - cy)
    a1, a2, a3 = (math.atan2(y - cy, x - cx) for x, y in (start, mid, end))
    sweep = (a3 - a1) % (2 * math.pi)
    if (a2 - a1) % (2 * math.pi) > sweep:  # il punto medio sta dall'altra parte: verso opposto
        sweep -= 2 * math.pi
    n = max(2, math.ceil(abs(sweep) / ARC_SEGMENT_ANGLE))
    pts = [(round(cx + r * math.cos(a1 + sweep * k / n)), round(cy + r * math.sin(a1 + sweep * k / n)))
           for k in range(n + 1)]
    return pts, math.ceil(r * (1 - math.cos(abs(sweep) / n / 2)))


def _circle_points(center, r):
    cx, cy = center
    n = round(2 * math.pi / ARC_SEGMENT_ANGLE)
    pts = [(round(cx + r * math.cos(2 * math.pi * k / n)), round(cy + r * math.sin(2 * math.pi * k / n)))
           for k in range(n + 1)]
    return pts, math.ceil(r * (1 - math.cos(math.pi / n)))


def _polyline(polyline):
    """PolyLine kipy -> (punti, sagitta)."""
    pts, sag = [], 0
    for node in polyline.nodes:
        if node.has_arc:
            arc_pts, s = _arc_points(_xy(node.arc.start), _xy(node.arc.mid), _xy(node.arc.end))
            pts += arc_pts
            sag = max(sag, s)
        else:
            pts.append(_xy(node.point))
    return pts, sag


# ---------- ostacoli ----------

def _bbox(points, pad):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _overlaps(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _pad_fallback_shape(pad, layer):
    """Forma conservativa che contiene il pad, dalla dimensione del padstack: (punti, raggio, chiuso)."""
    ps = pad.padstack
    cl = ps.copper_layer(layer) or ps.copper_layers[0]
    if cl.shape not in (PadStackShape.PSS_CIRCLE, PadStackShape.PSS_RECTANGLE, PadStackShape.PSS_OVAL,
                        PadStackShape.PSS_ROUNDRECT, PadStackShape.PSS_CHAMFEREDRECT):
        raise ValueError(f"Forma del pad {pad.number} non disponibile in modo affidabile: "
                         "impossibile garantire la clearance.")
    sx, sy = cl.size.x, cl.size.y
    ox, oy = cl.offset.x, cl.offset.y
    cx, cy = _xy(pad.position)
    if ox or oy:  # con offset il verso di rotazione conta: cerchio che contiene tutto
        return [(cx, cy)], math.ceil(math.hypot(ox, oy) + math.hypot(sx, sy) / 2), False
    a = math.radians(ps.angle.degrees)
    hx = (abs(sx * math.cos(a)) + abs(sy * math.sin(a))) / 2  # riquadro del rettangolo ruotato
    hy = (abs(sx * math.sin(a)) + abs(sy * math.cos(a))) / 2
    hx, hy = math.ceil(hx), math.ceil(hy)
    return [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)], 0, True


def _plausible(pts, pad, layer):
    """Il poligono restituito dall'API sta davvero attorno al pad? (in KiCad 10.0.7 non sempre)"""
    cl = pad.padstack.copper_layer(layer) or pad.padstack.copper_layers[0]
    reach = math.hypot(cl.size.x, cl.size.y) / 2 + math.hypot(cl.offset.x, cl.offset.y)
    x0, y0, x1, y1 = _bbox(pts, 0)
    return math.dist(((x0 + x1) / 2, (y0 + y1) / 2), _xy(pad.position)) <= reach


def _pad_polygons(board, pads, layer):
    polys = board.get_pad_shapes_as_polygons(pads, layer)
    if len(polys) == len(pads):
        return polys
    # kipy scarta i pad senza poligono e la lista perde l'allineamento: richiesta pad per pad.
    return [board.get_pad_shapes_as_polygons(p, layer) for p in pads]


def work_region(board, group_points):
    """Regione di lavoro: pad del gruppo + margine, ritagliata sul bordo scheda (Edge.Cuts)."""
    x0, y0, x1, y1 = _bbox(group_points, REGION_MARGIN)
    edge = [s for s in board.get_shapes() if s.layer == BoardLayer.BL_Edge_Cuts]
    boxes = [s.bounding_box() for s in edge if hasattr(s, "bounding_box")]
    if boxes:
        x0 = max(x0, min(b.pos.x for b in boxes))
        y0 = max(y0, min(b.pos.y for b in boxes))
        x1 = min(x1, max(b.pos.x + b.size.x for b in boxes))
        y1 = min(y1, max(b.pos.y + b.size.y for b in boxes))
    return x0, y0, x1, y1


def read_obstacles(board, layer, region, group_clearance):
    """Ostacoli sul layer dentro la regione. Restituisce (ostacoli, note sui limiti)."""
    raw = []  # (net, punti, raggio, chiuso)
    notes = []

    pads = list(board.get_pads())
    presence = board.check_padstack_presence_on_layers(pads, [layer])
    present_ids = {item.id.value for item, by_layer in presence.items() if by_layer.get(layer)}
    present = [p for p in pads if p.id.value in present_ids]
    fallback = 0
    for p, poly in zip(present, _pad_polygons(board, present, layer)):
        pts, sag = _polyline(poly.outline) if poly is not None else ([], 0)
        if pts and _plausible(pts, p, layer):
            raw.append((p.net.name, pts, sag, True))
        else:
            pts, radius, closed = _pad_fallback_shape(p, layer)
            raw.append((p.net.name, pts, radius, closed))
            fallback += 1
    if fallback:
        notes.append(f"{fallback} pad con forma non attendibile dall'API: usato un ingombro conservativo "
                     "(rettangolo o cerchio che contiene il pad).")
    for p in pads:  # fori dei pad senza rame su questo layer (NPTH e simili)
        if p.id.value in present_ids:
            continue
        drill = p.padstack.drill.diameter
        if max(drill.x, drill.y) > 0:
            raw.append((p.net.name, [_xy(p.position)], max(drill.x, drill.y) // 2, False))

    for t in board.get_tracks():
        if t.layer != layer:
            continue
        if isinstance(t, ArcTrack):
            pts, sag = _arc_points(_xy(t.start), _xy(t.mid), _xy(t.end))
            raw.append((t.net.name, pts, t.width // 2 + sag, False))
        else:
            raw.append((t.net.name, [_xy(t.start), _xy(t.end)], t.width // 2, False))

    for v in board.get_vias():  # ponytail: ogni via è trattata come passante (presente su tutti i layer)
        size = max(max(cl.size.x, cl.size.y) for cl in v.padstack.copper_layers)
        raw.append((v.net.name, [_xy(v.position)], size // 2, False))

    for z in board.get_zones():
        if z.is_rule_area() and layer in z.layers:
            pts, sag = _polyline(z.outline.outline)
            raw.append(("", pts, sag, True))
    if any(not z.is_rule_area() and layer in z.layers for z in board.get_zones()):
        notes.append("Zone di rame sul layer ignorate: vanno riempite di nuovo (tasto B) dopo l'applicazione.")

    for s in board.get_shapes():
        if s.layer != BoardLayer.BL_Edge_Cuts:
            continue
        if isinstance(s, BoardSegment):
            raw.append(("", [_xy(s.start), _xy(s.end)], 0, False))
        elif isinstance(s, BoardRectangle):
            (ax, ay), (bx, by) = _xy(s.top_left), _xy(s.bottom_right)
            raw.append(("", [(ax, ay), (bx, ay), (bx, by), (ax, by), (ax, ay)], 0, False))
        elif isinstance(s, BoardArc):
            pts, sag = _arc_points(_xy(s.start), _xy(s.mid), _xy(s.end))
            raw.append(("", pts, sag, False))
        elif isinstance(s, BoardCircle):
            r = math.dist(_xy(s.center), _xy(s.radius_point))
            pts, sag = _circle_points(_xy(s.center), r)
            raw.append(("", pts, sag, False))
        elif isinstance(s, BoardPolygon):
            for poly in s.polygons:
                pts, sag = _polyline(poly.outline)
                raw.append(("", pts + pts[:1], sag, False))
        else:
            notes.append(f"Forma del bordo scheda non gestita: {type(s).__name__}.")

    nets = {}
    for item in list(pads) + list(board.get_tracks()) + list(board.get_vias()):
        if item.net.name:
            nets.setdefault(item.net.name, item.net)
    classes = board.get_netclass_for_nets(list(nets.values())) if nets else {}

    obstacles = []
    for net, pts, radius, closed in raw:
        if not _overlaps(_bbox(pts, radius + 2 * group_clearance), region):
            continue
        nc = classes.get(net)
        # Il router usa sempre max(clearance del gruppo, clearance dell'ostacolo).
        obstacles.append(Obstacle(net, tuple(pts), int(radius), (nc.clearance or 0) if nc else 0, closed))
    notes.append("Non considerati: regole personalizzate (.kicad_dru), clearance rame-bordo specifica, "
                 "grafiche e testi su rame, keepout dei footprint.")
    return obstacles, notes
