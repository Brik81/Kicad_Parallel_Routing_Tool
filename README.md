# 〰️ Parallel Routing Tool per KiCad 10

> Instrada un gruppo di net **vicine e parallele**, lasciando a ogni traccia la libertà di aggirare gli ostacoli da sola.

![KiCad](https://img.shields.io/badge/KiCad-10.0-314cb0)
![API](https://img.shields.io/badge/API-IPC%20(kicad--python)-0a7)
![Stato](https://img.shields.io/badge/stato-Tappa%201%20%E2%80%94%20verifica%20API-orange)

**Non è un autorouter.** È un piccolo strumento mirato: selezioni i pad, lui propone un fascio di piste compatto su un solo layer, tu decidi se applicarlo e poi lanci il DRC di KiCad.

---

## ✨ Cosa farà

| | |
|---|---|
| 🎯 **Selezione esplicita** | Lavora solo sui pad che selezioni, con una regola di accoppiamento documentata (niente connessioni indovinate). |
| 📏 **Fascio parallelo** | Le piste restano vicine e seguono la direzione prevalente del gruppo. |
| 🧭 **Deviazioni indipendenti** | Ogni pista può aggirare un ostacolo senza trascinarsi dietro le altre. |
| ⚖️ **Lunghezze equilibrate** | Forte penalità per piste anomale (es. 82 mm quando le altre sono 42–46 mm). |
| 🛡️ **Sicuro** | Un solo layer, niente via, nessuna pista esistente toccata, nessuna modifica se non c'è una soluzione valida. Un'unica operazione annullabile con `Ctrl+Z`. |

## 🚦 Stato del progetto

| Tappa | Contenuto | Stato |
|---|---|---|
| 1 | Verifica ambiente e API KiCad 10 | ✅ fatta |
| 2 | Plugin minimo installabile | ⏳ |
| 3 | Lettura board e selezione | ⏳ |
| 4 | Proposta di routing | ⏳ |
| 5 | Applicazione e controllo | ⏳ |

> ⚠️ Il plugin **non è ancora stato caricato né provato in KiCad 10**. Questa sezione verrà aggiornata solo dopo la verifica reale nel PCB Editor.

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

## 🧪 Uso (previsto)

1. Nel PCB Editor seleziona i pad da collegare.
2. Avvia **Parallel Routing Tool**.
3. Controlla il riepilogo e la proposta.
4. Applica, oppure annulla senza modifiche.
5. **Esegui sempre il DRC di KiCad**: il router non lo sostituisce.

## 📚 Riferimenti

- [KiCad IPC API — for add-on developers](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- [kicad-python (kipy)](https://gitlab.com/kicad/code/kicad-python)
- [Schema `plugin.json`](https://go.kicad.org/api/schemas/v1)
