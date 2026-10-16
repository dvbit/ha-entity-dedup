# Specifica funzionale: `entity_dedup`

**Versione:** 1.0 | **Data:** 2026-10-16 | **Stato:** in attesa di approvazione

## 1. Scopo

Dopo ogni riavvio di Home Assistant, individuare e correggere in modo automatico e sicuro le entità duplicate con suffisso `_N` (`N ≥ 2`) create perché l'`entity_id` originale `X` era ancora presente nel registro come entità orfana.

Correzione: eliminare le orfane e rinominare l'entità viva `X_N` in `X`, trasferendo le personalizzazioni dell'orfana.

## 2. Vincoli di progetto

| Voce | Valore |
|---|---|
| Forma | Custom component Python, config flow + options flow da UI |
| Dominio | `entity_dedup` |
| Istanze | Una sola (`single_instance_allowed`) |
| Distribuzione | Repository compatibile con HACS (`hacs.json`, release con tag, README) |
| Versione minima HA | 2026.10.0, nessuna compatibilità all'indietro |
| Piattaforme | Tutte le integrazioni (la logica opera solo sul registro entità) |
| Lingue | `it`, `en`, `fr`, `de`, `es` (`translations/*.json`), lingua scelta da HA |
| Dipendenze esterne | Nessuna |

## 3. Definizioni

Dato un `entity_id` nella forma `<dominio>.<object_id>`:

- **Suffisso:** `object_id` che termina con `_N`, `N` intero ≥ 2 senza zeri iniziali (regex `^(.+)_([2-9]|[1-9][0-9]+)$`). Si toglie un solo suffisso finale. Il dominio resta invariato.
- **`X`:** entità con `entity_id` senza suffisso (nome base).
- **`X_N`:** entità con `entity_id` = `X` + `_N`.
- **Viva:** voce di registro con stato presente nella macchina a stati **senza** attributo `restored: true`. Lo stato `unavailable` non esclude. Non disabilitata.
- **Orfana:** voce di registro con stato `unavailable` e attributo `restored: true`.
- **Non viva:** nessuno stato, oppure stato con `restored: true`.
- **Candidata `X`:** `X` è nel registro, è non viva, ed è orfana oppure disabilitata dall'utente (`disabled_by == user`).
- **Orfana extra:** orfana `X_M` (`M ≥ 2`, `M ≠ N`) con stesso dominio e stesso nome base della viva `X_N`.

## 4. Trigger

1. **Automatico:** dopo l'evento `homeassistant_started`, con ritardo configurabile (§6), una sola volta per avvio.
2. **Manuale:** servizio `entity_dedup.run_now` (§7).

Regole:
- Se il componente viene caricato a HA già avviato (installazione, reload della config entry), **non** pianifica alcuna esecuzione. Si usa `run_now`.
- Il timer si annulla allo scarico del componente.
- Alla scadenza del timer, se lo switch `switch.entity_dedup_enabled` è spento, non esegue nulla.
- Le opzioni vengono lette al momento dell'esecuzione. La modifica delle opzioni non ricarica il componente e non avvia esecuzioni.
- Una sola esecuzione alla volta (lock). `run_now` durante un'esecuzione in corso viene rifiutato con `ServiceValidationError`.

## 5. Logica di esecuzione

### 5.1 Rilevazione dei casi

Per ogni voce viva `X_N` nel registro, non esclusa dalla denylist:

1. Ricava `X` (§3). Se `X` non è nel registro, nessun caso (nessuna azione, nessun report).
2. Se `X` non è una candidata (§3), nessun caso (es. `X` viva: nome legittimo come "Lampada 2").
3. Se `X` o la viva rientrano nella denylist (§6), il caso è escluso in silenzio.
4. Conta le vive con lo stesso nome base e dominio:
   - 0 vive: nessun caso.
   - ≥ 2 vive: caso **saltato**, motivo `multiple_live_candidates`.
   - esattamente 1: prosegui con i controlli.

I casi si elaborano in ordine alfabetico per `entity_id` di `X`.

### 5.2 Controlli di sicurezza

I controlli si applicano a `X` e a ogni orfana extra, confrontate con la viva. Al primo controllo fallito, l'**intero caso** è saltato col motivo indicato. Ordine:

| # | Controllo | Motivo se fallisce |
|---|---|---|
| 1 | `X` non disabilitata né nascosta dall'utente (`disabled_by`/`hidden_by` ≠ `user`) | `orphan_disabled_or_hidden` |
| 2 | Orfana ha `config_entry_id` | `orphan_no_config_entry` |
| 3 | Config entry dell'orfana in stato `loaded` | `orphan_config_entry_not_loaded` |
| 4 | Viva ha `config_entry_id` | `live_no_config_entry` |
| 5 | Config entry della viva in stato `loaded` (non in errore, retry o setup in corso) | `live_config_entry_not_loaded` |
| 6 | `device_id` dell'orfana uguale a quello della viva (entrambi nulli = uguali) | `orphan_device_mismatch` |
| 7 | Stessa piattaforma | `platform_mismatch` |
| 8 | Stesso `device_class` effettivo (override utente, altrimenti originale) | `device_class_mismatch` |
| 9 | Stessa `unit_of_measurement` | `unit_mismatch` |
| 10 | Nessun riferimento a `X_N` nei perimetri del §5.3 | `references_found` |

Per i controlli 8 e 9: attributo assente su entrambe = compatibile; assente su una sola = fallisce.

### 5.3 Ricerca dei riferimenti a `X_N`

Ricerca testuale dell'`entity_id` esatto della viva (confini di parola: `sensor.a_2` non trova `sensor.a_20`) in:

- **a)** automazioni, script, scene (UI e YAML, inclusi input delle istanze di blueprint);
- **b)** dashboard Lovelace (modalità UI e YAML);
- **c)** opzioni delle config entry di helper, template e gruppi (es. `template`, `group`, `min_max`, `derivative`, `threshold`) e template/gruppi definiti in YAML;
- **d)** file `*.yaml`/`*.yml` nella directory di configurazione (`configuration.yaml`, `packages/`, file `!include`), esclusi `custom_components/` e `.storage/`;
- **e)** campi `options` e `capabilities` delle altre voci del registro entità.

Sono ignorati i riferimenti nella config entry e nel log di `entity_dedup`. Per ogni riferimento si registra: tipo (a–e), identificativo (nome/ID dell'oggetto o file e riga). La scansione dei file è eseguita fuori dall'event loop.

### 5.4 Limite di correzioni

Sia *idonei* il numero di casi che superano tutti i controlli.

- Se `idonei > max_corrections` e `ignore_limit` è falso: **nessuna correzione**. Si registra un'unica riga `threshold_exceeded` con l'elenco dei casi idonei e si notifica. Lo stesso vale per `dry_run`.
- Altrimenti si procede con tutti gli idonei.

### 5.5 Esecuzione del caso (non in `dry_run`)

1. **Snapshot** persistito nello Store: tutti i campi della voce di registro di `X` e delle orfane extra, la loro esposizione agli assistenti vocali, e i valori precedenti della viva (`entity_id` e campi trasferibili).
2. Se esistono statistiche a lungo termine sia per `X` sia per `X_N` (recorder presente), imposta il flag `statistics_may_be_orphaned` per il caso. Il componente non tocca le statistiche.
3. Elimina `X` e le orfane extra dal registro.
4. Rinomina la viva da `X_N` a `X` (`new_entity_id`).
5. **Trasferisci da `X`** (non dalle orfane extra) alla viva i campi: nome, icona, area, etichette, categorie, visibilità (`hidden_by`), esposizione agli assistenti vocali. Il valore passa solo se sulla viva il campo è al valore di default (nullo/vuoto/non impostato). Un valore personalizzato sulla viva prevale.
6. Chiudi il caso: rimuovi lo snapshot dal log e scrivi la riga di esito `fixed`.

### 5.6 Errori e rollback

Se un passo tra 3 e 5 fallisce:
- ripristina la viva (`entity_id` originale e campi originali) e ricrea dallo snapshot le voci eliminate;
- esito `error_rollback`, con messaggio d'errore nei dettagli;
- si prosegue con il caso successivo.

Se il rollback stesso fallisce: esito `error_rollback_failed`, lo snapshot resta nella riga di log, l'esecuzione si **interrompe** e si notifica.

Se all'avvio nello Store esiste uno snapshot non chiuso (HA fermato durante un caso), la riga viene marcata `interrupted`, lo snapshot resta, nessun ripristino automatico. Il caso è riportato una volta nella notifica della prima esecuzione successiva.

### 5.7 `dry_run`

Esegue rilevazione, controlli e limite come in esecuzione reale. Non modifica il registro. I casi idonei hanno esito `would_fix`. Non aggiorna i sensori del §8.

## 6. Configurazione (config flow e options flow)

Il config flow crea la voce con i valori predefiniti in un solo passo di conferma. L'options flow modifica:

| Opzione | Tipo | Predefinito | Intervallo |
|---|---|---|---|
| `delay_minutes` | int | 10 | 1–120 |
| `max_corrections` | int | 10 | 1–100 |
| `log_max_entries` | int | 500 | 50–5000 |
| `denylist_domains` | lista di domini | vuota | domini validi |
| `denylist_entities` | lista di `entity_id` | vuota | `entity_id` validi |

La denylist esclude in silenzio i casi in cui `X` o la viva rientrano nell'elenco. Prevale sul parametro `entity_id` di `run_now`.

## 7. Servizi

### `entity_dedup.run_now`

| Parametro | Tipo | Predefinito | Descrizione |
|---|---|---|---|
| `dry_run` | bool | `false` | Solo rilevazione, notifica e log |
| `ignore_limit` | bool | `false` | Ignora una volta `max_corrections` |
| `entity_id` | string, opzionale | nessuno | Limita l'esecuzione al solo nome base `X` indicato, preso alla lettera |

Funziona anche con lo switch di abilitazione spento. Risposta (`SupportsResponse.OPTIONAL`): `{dry_run, fixed, skipped, would_fix, threshold_exceeded, cases: [...]}`.

### `entity_dedup.get_log`

| Parametro | Tipo | Predefinito | Descrizione |
|---|---|---|---|
| `limit` | int 1–500 | 50 | Numero massimo di righe |
| `since` | datetime, opzionale | nessuno | Solo righe successive |

Risposta: `{entries: [...]}`, dalla più recente.

## 8. Entità esposte

Un solo dispositivo "Entity Dedup". I valori persistono ai riavvii.

| Entità | Tipo | Valore |
|---|---|---|
| `sensor.entity_dedup_last_run` | sensor, `device_class: timestamp` | Istante dell'ultima esecuzione reale (esclusi `dry_run`), anche senza casi |
| `sensor.entity_dedup_last_fixed` | sensor, `measurement` | Casi con esito `fixed` nell'ultima esecuzione reale |
| `sensor.entity_dedup_last_skipped` | sensor, `measurement` | Casi non corretti nell'ultima esecuzione reale (saltati, in errore, oltre soglia) |
| `switch.entity_dedup_enabled` | switch, predefinito acceso | Spento: sospende solo l'esecuzione automatica dopo il riavvio |

## 9. Notifica

- Canale: solo `persistent_notification`, ID fisso `entity_dedup_report`. Ogni nuova notifica sostituisce la precedente.
- Emessa a fine esecuzione **solo se c'è qualcosa da riportare**: esiti `fixed`, `skipped`, `error_*`, `threshold_exceeded`, `interrupted`, `would_fix`. Se non c'è nulla, la notifica precedente resta invariata.
- Contenuto: titolo (con indicazione "simulazione" in `dry_run`), riepilogo con conteggi, una riga per caso con `X`, `X_N`, esito e motivo, fino a 5 riferimenti per i casi `references_found`, nota `statistics_may_be_orphaned` dove presente, rimando a `entity_dedup.get_log`.
- Testi localizzati (§2). I codici motivo sono stabili e indipendenti dalla lingua.

## 10. Log persistente

Memorizzato con `Store` di HA. Una riga per caso, più una riga per esecuzione per `threshold_exceeded`.

| Campo | Contenuto |
|---|---|
| `ts` | Timestamp UTC ISO 8601 |
| `run_id` | UUID dell'esecuzione |
| `trigger` | `startup` o `service` |
| `dry_run` | bool |
| `base_entity_id` | `X` (nullo per `threshold_exceeded`) |
| `live_entity_id` | `X_N` (nullo per `threshold_exceeded`) |
| `extra_orphans` | Lista di `entity_id` |
| `outcome` | `fixed`, `skipped`, `would_fix`, `threshold_exceeded`, `error_rollback`, `error_rollback_failed`, `interrupted` |
| `reason` | Codice motivo (§5.2, §5.4, §5.6) o nullo |
| `details` | Oggetto: `references`, `statistics_may_be_orphaned`, `error`, elenco casi per `threshold_exceeded` |
| `snapshot` | Presente solo finché il caso è aperto, o per `interrupted` e `error_rollback_failed` |

Conservazione: dopo ogni scrittura si mantengono le ultime `log_max_entries` righe. Gli snapshot si rimuovono alla chiusura del caso.

## 11. Casi di accettazione

| ID | Scenario | Esito atteso |
|---|---|---|
| T1 | `X` orfana + `X_2` viva, controlli superati | `X` eliminata, `X_2` → `X`, esito `fixed` |
| T2 | `X` orfana, `X_2` orfana, `X_3` viva | `X` e `X_2` eliminate, `X_3` → `X` |
| T3 | `X` orfana, `X_2` e `X_3` vive | Saltato, `multiple_live_candidates` |
| T4 | `X` viva e `X_2` viva ("Lampada 2") | Nessuna azione, nessun report |
| T5 | Solo `X_2` viva, `X` assente | Nessuna azione, nessun report |
| T6 | `X_2` citata in un'automazione | Saltato, `references_found` con posizione |
| T7 | Config entry della viva in retry | Saltato, `live_config_entry_not_loaded` |
| T8 | `X` orfana senza `config_entry_id` | Saltato, `orphan_no_config_entry` |
| T9 | `X` nascosta dall'utente | Saltato, `orphan_disabled_or_hidden` |
| T10 | `X` e `X_2` con `device_id` diversi | Saltato, `orphan_device_mismatch` |
| T11 | `unit_of_measurement` assente solo su una | Saltato, `unit_mismatch` |
| T12 | 11 casi idonei, limite 10 | Nessuna correzione, `threshold_exceeded` con elenco; con `ignore_limit: true` correggi tutti |
| T13 | Eccezione al passo 4 | Rollback completo, `error_rollback`, esecuzione prosegue |
| T14 | `X` con nome personalizzato, viva con nome di default | Nome trasferito; se la viva ha già un nome, resta il suo |
| T15 | Statistiche presenti per `X` e `X_2` | `fixed` con flag `statistics_may_be_orphaned` |
| T16 | `run_now` con `dry_run: true` | Registro invariato, `would_fix`, sensori invariati |
| T17 | Reload del componente a HA avviato | Nessuna esecuzione |
| T18 | Switch spento al riavvio | Nessuna esecuzione automatica; `run_now` funziona |
| T19 | `X` in denylist | Escluso in silenzio |
| T20 | `run_now` durante un'esecuzione | Rifiutato con `ServiceValidationError` |

## 12. Limiti noti

- Il caso con solo `X_N` e `X` assente non è gestito.
- Un re-pairing che crea un nuovo dispositivo (device diverso) viene saltato (`orphan_device_mismatch`).
- Non sono scansionati sistemi esterni a HA (AppDaemon, Node-RED, API REST, YAML di ESPHome, trigger vocali) né file fuori dalla directory di configurazione: l'assenza di riferimenti non è garantita fuori dai perimetri del §5.3.
- Le statistiche a lungo termine non vengono unite: quelle di `X_N` possono restare come orfane, rimovibili a mano da Strumenti per sviluppatori → Statistiche.
- Non esiste undo: il rollback copre solo gli errori durante un caso.
