# 〰️ Parallel Routing Tool per KiCad 10

> Tracci **tu** una pista: il plugin instrada le altre del fascio **parallele e vicine**, solo a 0/45/90°, deviando dove serve per aggirare gli ostacoli.

![KiCad](https://img.shields.io/badge/KiCad-10.0-314cb0)
![API](https://img.shields.io/badge/API-IPC%20(kicad--python)-0a7)
![Versione](https://img.shields.io/badge/versione-V0%20provvisoria-red)

> ⚠️ **V0 provvisoria, non definitiva.** Il tool è ancora in sviluppo: funziona sui casi provati, ma i risultati non sono ancora al livello finale e comportamento, interfaccia e regole possono cambiare. Controlla sempre il risultato ed esegui il DRC di KiCad.

**Non è un autorouter.** Il percorso lo decidi tu, tracciando a mano una pista guida con il router di KiCad. Ogni altra net riceve una corsia parallela alla guida e viene instradata lungo quella corsia, uscendone solo per aggirare gli ostacoli. Tu decidi se applicare il risultato e poi lanci il DRC di KiCad.

---

## ✨ Cosa fa

| | |
|---|---|
| ✋ **Percorso manuale** | Tracci una sola pista (la guida) con il router di KiCad; le altre la seguono. |
| 📏 **Fascio parallelo** | Ogni pista è una copia della guida spostata della distanza del suo pad: il fascio mantiene la spaziatura dei pad e fa le stesse svolte della guida. |
| 🧭 **Flessibile** | Se un ostacolo blocca una corsia, solo quella pista devia (e le vicine la seguono), poi rientra. |
| 📐 **Solo 0/45/90°** | Tratti orizzontali, verticali o a 45°: nessun segmento storto. |
| 🎯 **Selezione esplicita** | Esattamente 2 pad per net, niente connessioni indovinate. |
| 🛡️ **Sicuro** | Un solo layer, niente via, nessuna pista esistente toccata, nessuna modifica senza conferma o se la clearance non è rispettata. Un'unica operazione annullabile con `Ctrl+Z`. |

## 🚦 Stato del progetto

| Tappa | Contenuto | Stato |
|---|---|---|
| 1 | Verifica ambiente e API KiCad 10 | ✅ fatta |
| 2 | Plugin minimo installabile | ✅ caricato in KiCad 10.0.7 (Windows) |
| 3 | Lettura board e selezione | ✅ verificata in KiCad 10.0.7 |
| 4 | Proposta di routing (modalità pista guida) | 🟡 V0: provata in KiCad 10.0.7, risultati da migliorare |
| 5 | Applicazione e controllo | ✅ Applica / Mantieni / Rimuovi provati in KiCad 10.0.7 |

> ℹ️ Verificato nel PCB Editor reale (KiCad 10.0.7, Windows 11): caricamento del plugin, lettura della selezione, creazione e rimozione delle piste, modalità pista guida. Lo stringimento del fascio sui tratti lunghi è nuovo e non ancora provato in KiCad.

## 📦 Requisiti

- **KiCad 10.0** (verificato l'ambiente con 10.0.7, Windows 11)
- **API IPC abilitata**: `Preferenze → Plugin → Abilita server API`
- Connessione internet al primo avvio (KiCad installa `kicad-python` nell'ambiente virtuale del plugin)

Il plugin usa la nuova **IPC API** (`kicad-python` / `kipy`), non la vecchia interfaccia SWIG `pcbnew`, che in KiCad 10 è deprecata.

## 🔧 Installazione

KiCad 10 carica i plugin IPC da una sottocartella di:

| Sistema | Cartella plugin |
|---|---|
| Windows | `%USERPROFILE%\Documents\KiCad\10.0\plugins\` |
| macOS | `~/Documents/KiCad/10.0/plugins/` |
| Linux | `~/.local/share/KiCad/10.0/plugins/` |

### Opzione A — copia

1. Scarica o clona questo repository.
2. Copia la cartella `plugin/` dentro la cartella plugin e rinominala `parallel_routing_tool`.
3. Riavvia KiCad e apri il PCB Editor.
4. Attendi qualche secondo: KiCad crea l'ambiente Python del plugin in background. Poi compare il pulsante **Parallel Routing Tool** nella barra strumenti.

### Opzione B — link per sviluppo (le modifiche sono subito attive)

**Windows (PowerShell):**

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\Documents\KiCad\10.0\plugins\parallel_routing_tool" -Target "$PWD\plugin"
```

**macOS / Linux:**

```bash
ln -s "$PWD/plugin" ~/Documents/KiCad/10.0/plugins/parallel_routing_tool
```

### Se il pulsante non compare

- Verifica che il server API sia abilitato (vedi *Requisiti*).
- `Preferenze → Plugin`: controlla il percorso dell'interprete Python, poi tasto destro sull'azione → **Ricrea ambiente plugin**.
- L'ambiente virtuale si trova in `%LOCALAPPDATA%\KiCad\10.0\python-environments\<id-plugin>` (Windows).

## 🗑️ Disinstallazione

1. Chiudi KiCad.
2. Elimina la cartella `parallel_routing_tool` dalla cartella plugin (con il link dell'opzione B viene rimosso solo il link, non il repository).
3. Opzionale: elimina il relativo ambiente in `python-environments`.

## 🧪 Uso

1. Con il router di KiCad (`X`) traccia **a mano una sola pista**, la *guida*, tra due pad del gruppo. Usa solo tratti orizzontali, verticali o a 45°.
2. Seleziona **tutti i pad** del fascio, compresi i due della guida. **Regola:** esattamente 2 pad per net.
3. Avvia **Parallel Routing Tool**. Le altre piste vengono instradate:
   - lungo corsie parallele alla guida, dalla parte in cui si trovano i loro pad;
   - deviando attorno agli ostacoli quando serve, poi rientrando in corsia;
   - solo con tratti a 0/45/90°, con la stessa larghezza e sullo stesso layer della guida.
4. Finché non premi **Applica** la board non cambia. **Applica** crea tutto in un'unica operazione (un solo `Ctrl+Z`). Poi scegli **Mantieni** oppure **Rimuovi**, che elimina solo i segmenti appena creati.
5. Riempi di nuovo le zone (`B`) ed **esegui sempre il DRC di KiCad**.

Se la proposta viene rifiutata (pad in ordine incrociato, nessun percorso libero, clearance violata), sposta la guida e riprova.

> L'API documenta che le modifiche dentro un commit non sono visibili finché il commit non viene confermato. Per questo l'"anteprima" è: applica, guarda, mantieni o rimuovi.

## ⚙️ Come funziona

```
plugin/
  entrypoint.py   flusso e finestre (wx)
  board_io.py     KiCad: selezione, pista guida, regole, ostacoli, applica/rimuovi
  selection.py    regola "2 pad per net"                         ← senza KiCad, testato
  follow.py       pista guida e corsie parallele                 ← senza KiCad, testato
  router.py       griglia + A* a 8 direzioni + controllo clearance ← senza KiCad, testato
```

- **Guida:** l'unica net del gruppo i cui pad sono già collegati. Deve essere una catena di segmenti dritti, su un solo layer, con una sola larghezza.
- **Corsie:** la guida viene spostata lateralmente della distanza dei pad di ogni net dalla guida, misurata a ciascuno dei due capi. Gli spigoli si calcolano intersecando le rette spostate, quindi i 45° restano 45° e il fascio mantiene la spaziatura dei pad.
- **Copia esatta:** se il percorso pad → corsia → pad non urta nulla, viene usato così com'è: rette perfette, nessuna griglia.
- **Deviazione:** se la copia esatta urta un ostacolo, solo quella pista viene instradata con A* a 8 direzioni (solo 0/45/90°). La griglia ha passo `(larghezza + clearance) / 4` ed è allineata all'inizio della guida. Costo di ogni passo = lunghezza + svolte + distanza dalla propria corsia (oltre 1 passo di tolleranza). Le piste vengono posate dall'interno verso l'esterno e diventano ostacoli per le successive. I pesi si trovano in `WEIGHTS` in [`plugin/router.py`](plugin/router.py).
- **Margine di griglia:** una cella è libera solo se rispetta la clearance più `passo × √2/2`. Questo rende sicuri anche i tratti tra una cella e l'altra.
- **Ordine:** l'ordine laterale dei pad deve essere lo stesso ai due capi. Altrimenti, su un solo layer, le piste si incrocerebbero e la proposta viene rifiutata.
- **Regole:** la clearance è il massimo tra le netclass delle net coinvolte. Per ogni ostacolo vale `max(clearance del gruppo, clearance netclass dell'ostacolo)`.
- **Ostacoli:** pad, fori, piste e archi, via (come passanti), rule area e bordo scheda. Le zone di rame vanno riempite di nuovo dopo l'applicazione.
- **Controllo finale:** ogni segmento nuovo viene verificato con distanze geometriche esatte. Se uno viola la clearance, la proposta viene scartata.

### Limiti noti

- Un solo layer, nessuna via, nessuna modifica delle piste esistenti.
- Piste guida con archi non supportate.
- La spaziatura del fascio è quella dei pad: niente compressione.
- Nelle piste che deviano resta un piccolo aggancio tra il centro del pad e la griglia (< 0,1 mm, dentro il rame del pad).
- I pad a passo fine possono risultare "troppo vicini a un ostacolo per la griglia".
- Non considera regole personalizzate `.kicad_dru`, clearance specifica rame-bordo, grafiche e testi su rame.
- In KiCad 10.0.7 l'API restituisce forme di pad spostate per alcuni footprint ruotati. Per quei pad si usa un ingombro conservativo.
- Il plugin **non sostituisce il DRC** di KiCad.

### Test simulati (senza KiCad)

```bash
python tests/test_selection.py
python tests/test_follow.py
```

## 📚 Riferimenti

- [KiCad IPC API — for add-on developers](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- [kicad-python (kipy)](https://gitlab.com/kicad/code/kicad-python)
- [Schema `plugin.json`](https://go.kicad.org/api/schemas/v1)
