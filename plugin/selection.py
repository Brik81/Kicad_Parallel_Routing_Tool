"""Regola di accoppiamento dei pad selezionati. Nessuna dipendenza da KiCad.

Regola (v1): ogni net coinvolta deve avere esattamente 2 pad selezionati;
quei due pad formano una connessione da instradare. Tutto il resto viene
segnalato come problema e la selezione non è instradabile.
"""
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class PadInfo:
    name: str            # es. "U1.3"
    net: str             # "" se il pad non ha net
    x_nm: int
    y_nm: int
    layers: frozenset    # nomi dei layer di rame su cui il pad è presente


def pair_by_net(pads):
    """Restituisce (coppie {net: (pad_a, pad_b)}, problemi [str])."""
    by_net = defaultdict(list)
    problems = []
    for p in pads:
        if p.net:
            by_net[p.net].append(p)
        else:
            problems.append(f"{p.name}: pad senza net")

    pairs = {}
    for net, group in sorted(by_net.items()):
        if len(group) == 2:
            pairs[net] = tuple(group)
        else:
            names = ", ".join(p.name for p in group)
            problems.append(f"net {net}: {len(group)} pad selezionati ({names}), servono esattamente 2")
    return pairs, problems


def common_layers(pads):
    """Layer di rame condivisi da tutti i pad: candidati per il routing a layer singolo."""
    pads = list(pads)
    return frozenset.intersection(*(p.layers for p in pads)) if pads else frozenset()
