"""Parallel Routing Tool: instrada le altre net del fascio su corsie parallele a una pista
guida tracciata a mano, aggirando gli ostacoli, e solo su conferma le applica.

KiCad lancia questo script in un processo separato e passa KICAD_API_SOCKET /
KICAD_API_TOKEN nell'ambiente; KiCad() li legge da solo.
"""
import math
import time

import wx
from kipy import KiCad
from kipy.util.board_layer import canonical_name

import board_io
from follow import FollowError, assign_lanes
from router import Connection, RoutingError, route_lanes
from selection import pair_by_net


def mm(nm):
    return f"{nm / 1e6:.3f}"


def selection_text(pads, others, pairs, problems):
    lines = [f"Pad selezionati: {len(pads)}"]
    if others:
        lines.append(f"Oggetti ignorati (non pad): {others}")
    for p in sorted(pads, key=lambda p: (p.net, p.name)):
        lines.append(f"  {p.name:<10} net={p.net or '-':<14} ({mm(p.x_nm)}, {mm(p.y_nm)}) mm  "
                     f"{', '.join(sorted(p.layers))}")
    lines.append(f"Connessioni valide: {len(pairs)}")
    if problems:
        lines.append("\nProblemi (selezione non instradabile):")
        lines += [f"  - {p}" for p in problems]
    return lines


def propose(board):
    """Restituisce (testo del riepilogo, piano da applicare oppure None)."""
    pads, by_name, others = board_io.read_selected_pads(board)
    if not pads:
        return "Nessun pad selezionato.\n\nSeleziona i pad da collegare nel PCB Editor e riprova.", None
    pairs, problems = pair_by_net(pads)
    lines = selection_text(pads, others, pairs, problems)
    if problems or not pairs:
        return "\n".join(lines), None

    # La guida è l'unica net del gruppo già collegata: l'utente l'ha tracciata a mano.
    guides = [net for net, (a, b) in pairs.items()
              if board_io.already_connected(board, by_name[a.name], by_name[b.name])]
    if len(guides) != 1:
        lines.append("\nServe esattamente UNA pista guida: traccia a mano una delle connessioni "
                     "(router di KiCad, tratti a 0/45/90°), poi seleziona di nuovo tutti i pad e riprova.")
        if guides:
            lines.append(f"Già collegate: {', '.join(guides)}")
        return "\n".join(lines), None
    guide_net = guides[0]
    ga, _ = pairs[guide_net]
    guide, width, layer = board_io.read_guide(board, guide_net, (ga.x_nm, ga.y_nm))

    rest = {net: pair for net, pair in pairs.items() if net != guide_net}
    if not rest:
        lines.append("\nC'è solo la pista guida: seleziona anche i pad delle altre net.")
        return "\n".join(lines), None
    missing = [p.name for pair in rest.values() for p in pair if canonical_name(layer) not in p.layers]
    if missing:
        lines.append(f"\nPad non presenti sul layer della guida ({canonical_name(layer)}): {', '.join(missing)}")
        return "\n".join(lines), None

    nets = {by_name[p.name].net.name: by_name[p.name].net for pair in pairs.values() for p in pair}
    _, clearance = board_io.group_rules(board, nets.values())
    points = guide + [(p.x_nm, p.y_nm) for pair in pairs.values() for p in pair]
    region = board_io.work_region(board, points)
    obstacles, notes = board_io.read_obstacles(board, layer, region, clearance)

    lines.append(f"\nGuida: {guide_net}   layer {canonical_name(layer)}   pista {mm(width)} mm   "
                 f"clearance {mm(clearance)} mm")
    t0 = time.time()
    try:
        lanes, compacted = assign_lanes(
            guide, [(net, (a.x_nm, a.y_nm), (b.x_nm, b.y_nm)) for net, (a, b) in rest.items()], width + clearance)
        conns = [Connection(*lane) for lane in lanes]
        routes = route_lanes(conns, obstacles, width, clearance, region, origin=guide[0])
    except (FollowError, RoutingError) as e:
        lines.append(f"\nNESSUNA PROPOSTA: {e}\nLa board non è stata modificata.")
        return "\n".join(lines + [""] + notes), None

    guide_len = sum(math.dist(p, q) for p, q in zip(guide, guide[1:]))
    lines.append(f"Calcolo {time.time() - t0:.1f} s")
    lines.append("Fascio stretto sui tratti lunghi della guida, spaziatura dei pad vicino ai connettori.\n"
                 if compacted else "Fascio con la spaziatura dei pad.\n")
    lines.append("Proposta (dall'interno del fascio verso l'esterno):")
    lines.append(f"  {guide_net:<16} {guide_len / 1e6:7.2f} mm   (guida, resta com'è)")
    ideal = {c.net: c.ideal for c in conns}
    for r in routes:
        how = "parallela alla guida" if ideal[r.net] and list(ideal[r.net]) == r.points else "devia attorno a ostacoli"
        lines.append(f"  {r.net:<16} {r.length / 1e6:7.2f} mm   {len(r.points) - 1} segmenti   {how}")
    lines.append("\nTratti solo a 0/45/90°. Clearance verificata sui soli ostacoli considerati: "
                 "esegui comunque il DRC di KiCad.")
    return "\n".join(lines + [""] + notes), (routes, nets, layer, width)


def show(text, ok_label=None, cancel_label="Chiudi"):
    """Finestra con testo scorrevole. Con ok_label restituisce True se l'utente conferma."""
    dlg = wx.Dialog(None, title="Parallel Routing Tool", size=(760, 520),
                    style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.STAY_ON_TOP)
    box = wx.TextCtrl(dlg, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP)
    box.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
    buttons = wx.StdDialogButtonSizer()
    if ok_label:
        buttons.AddButton(wx.Button(dlg, wx.ID_OK, ok_label))
    buttons.AddButton(wx.Button(dlg, wx.ID_CANCEL, cancel_label))
    buttons.Realize()
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(box, 1, wx.EXPAND | wx.ALL, 8)
    sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
    dlg.SetSizer(sizer)
    confirmed = dlg.ShowModal() == wx.ID_OK
    dlg.Destroy()
    return confirmed


def main():
    app = wx.App()
    try:
        board = KiCad().get_board()
        with wx.BusyInfo("Parallel Routing Tool: calcolo in corso..."):
            text, plan = propose(board)
        if plan is None:
            show(text)
        elif show(text + "\n\nNessuna modifica finché non premi Applica.", "Applica", "Annulla"):
            # ponytail: la board non viene riletta tra calcolo e applicazione; se la modifichi
            # mentre la finestra è aperta, il DRC è l'unico controllo.
            created = board_io.apply_routes(board, *plan)
            keep = show(f"Applicati {len(created)} segmenti in un'unica operazione (annullabile con Ctrl+Z).\n\n"
                        "Controllali nel PCB Editor, poi:\n"
                        "  Mantieni  -> restano sulla board\n"
                        "  Rimuovi   -> vengono eliminati solo i segmenti appena creati\n\n"
                        "Dopo: riempi di nuovo le zone (B) ed esegui il DRC di KiCad.",
                        "Mantieni", "Rimuovi")
            if not keep:
                board_io.remove_routes(board, created)
    except Exception as e:  # nessuna board aperta, API disabilitata, guida non valida...
        show(f"Errore: {e}\n\nControlla la board: se il plugin aveva già applicato piste, Ctrl+Z le annulla.")
    app.Destroy()


if __name__ == "__main__":
    main()
