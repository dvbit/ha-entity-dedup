# Entity Dedup

<img src="icon.png" width="96" align="right" alt="icona">

[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![versione](https://img.shields.io/badge/versione-1.1.0-blue)
![HA](https://img.shields.io/badge/Home%20Assistant-2026.10%2B-03a9f4)

🇬🇧 [Read in English](README.md)

Corregge **in automatico e in sicurezza, dopo ogni riavvio di Home Assistant**, le entità duplicate `_2`, `_3`, …

Quando un'integrazione ricrea un'entità mentre l'`entity_id` originale (`sensor.temperatura`) è ancora occupato da una voce orfana del registro, Home Assistant registra la nuova come `sensor.temperatura_2`. Entity Dedup elimina l'orfana, rinomina l'entità viva in `sensor.temperatura` e trasferisce le personalizzazioni (nome, icona, area, etichette, categorie, visibilità, esposizione agli assistenti vocali).

Specifica di partenza: [docs/specification-v1.1.md](docs/specification-v1.1.md) ([v1.0](docs/specification-v1.0.md)).

## Come funziona

1. Dopo `homeassistant_started` più un ritardo configurabile (predefinito 10 min), una volta per avvio.
2. Per ogni `X_N` viva con `X` orfana (`unavailable` + `restored`) o disabilitata dall'utente, esegue **10 controlli di sicurezza**: disabilitata/nascosta dall'utente, config entry presenti e caricate, stesso dispositivo, piattaforma, device class, unità e **nessun riferimento a `X_N`** in automazioni, script, scene, dashboard, config entry degli helper, file YAML e altre voci del registro.
3. Un controllo fallito → caso **saltato** con codice motivo stabile.
4. Se i casi idonei superano `max_corrections` → **nessuna correzione** e notifica.
5. Ogni caso è eseguito con **snapshot persistito**; in caso di errore si fa **rollback**.
6. La notifica persistente `entity_dedup_report` riassume l'esecuzione; lo storico completo è in `entity_dedup.get_log`.

Usa solo le API pubbliche del registro entità. I file `.storage` non vengono mai modificati.

## Installazione (HACS)

1. HACS → ⋮ → *Repository personalizzati* → `https://github.com/dvbit/ha-entity-dedup`, categoria *Integrazione*.
2. Installa **Entity Dedup** e riavvia Home Assistant.
3. *Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Entity Dedup* → Invia.

> Se installata o ricaricata a HA già avviato **non** esegue nulla in automatico: usa `entity_dedup.run_now` (parti con `dry_run: true`).

## Opzioni

| Opzione | Predefinito | Intervallo | Significato |
|---|---|---|---|
| Ritardo dopo l'avvio | 10 min | 1–120 | Attesa dopo `homeassistant_started` |
| Correzioni massime | 10 | 1–100 | Oltre questa soglia non si corregge nulla |
| Righe di log conservate | 500 | 50–5000 | Conservazione del log persistente |
| Domini esclusi | – | – | es. `light`, `sensor` |
| Entità escluse | – | – | entity_id base o `_N` |
| Correggi i duplicati con originale eliminato | spenta | – | Vedi sotto (v1.1) |

Le opzioni si leggono al momento dell'esecuzione; salvarle non ricarica nulla.

## Originale già eliminato (v1.1, opzionale)

A volte `sensor.temperatura` non c'è più nel registro ma `sensor.temperatura_2` sì. Con **Correggi i duplicati con originale eliminato** attiva, Entity Dedup gestisce questo caso **solo se** Home Assistant ricorda ancora `sensor.temperatura` tra le entità *eliminate*, con **stessa integrazione e stessa config entry** della viva. In quel caso rinomina `_2` e ripristina nome, icona, area, etichette, categorie, visibilità ed esposizione dalla voce eliminata.

Senza questa traccia non fa nulla: nomi come "Zona 2", "SIM 2" o "Porta 5" restano invariati. Le righe hanno `details.case_type: missing_base` e la notifica le indica come *originale eliminato*.

```yaml
# Prima verifica cosa verrebbe corretto
action: entity_dedup.run_now
data:
  dry_run: true
```

## Entità

| Entità | Descrizione |
|---|---|
| `sensor.entity_dedup_last_run` | Istante dell'ultima esecuzione reale |
| `sensor.entity_dedup_last_fixed` | Casi corretti nell'ultima esecuzione reale |
| `sensor.entity_dedup_last_skipped` | Casi non corretti (saltati, errori, oltre soglia) |
| `switch.entity_dedup_enabled` | Spento = sospende solo l'esecuzione automatica dopo il riavvio |

## Azioni

### `entity_dedup.run_now`

| Campo | Predefinito | |
|---|---|---|
| `dry_run` | `false` | Solo rilevazione, log e notifica |
| `ignore_limit` | `false` | Ignora una volta `max_corrections` |
| `entity_id` | – | Solo l'entità base indicata (senza `_N`) |

```yaml
# Prima la simulazione
action: entity_dedup.run_now
data:
  dry_run: true
response_variable: report
```

```yaml
# Correggi una sola entità
action: entity_dedup.run_now
data:
  entity_id: sensor.temperatura_soggiorno
```

```yaml
# Molti casi insieme (dopo aver verificato la simulazione)
action: entity_dedup.run_now
data:
  ignore_limit: true
```

Risposta:

```yaml
dry_run: false
fixed: 1
skipped: 1
would_fix: 0
threshold_exceeded: false
cases:
  - base_entity_id: sensor.temperatura
    live_entity_id: sensor.temperatura_2
    outcome: fixed
    reason: null
    details: {}
  - base_entity_id: sensor.umidita
    live_entity_id: sensor.umidita_2
    outcome: skipped
    reason: references_found
    details:
      references:
        - type: a
          id: "automation.ventola (id: 1700000000)"
```

### `entity_dedup.get_log`

```yaml
action: entity_dedup.get_log
data:
  limit: 20
  since: "2026-10-01 00:00:00"
response_variable: log
```

### Esempio di automazione: avvisami quando corregge qualcosa

```yaml
automation:
  - alias: "Entity Dedup: report"
    triggers:
      - trigger: state
        entity_id: sensor.entity_dedup_last_run
    conditions:
      - condition: numeric_state
        entity_id: sensor.entity_dedup_last_fixed
        above: 0
    actions:
      - action: notify.mobile_app_telefono
        data:
          title: "Entity Dedup"
          message: "Corrette {{ states('sensor.entity_dedup_last_fixed') }} entità duplicate"
```

## Esiti e codici motivo

| Esito | Significato |
|---|---|
| `fixed` | Orfane eliminate, `X_N` rinominata in `X` |
| `skipped` | Un controllo di sicurezza è fallito (vedi motivo) |
| `would_fix` | Simulazione: verrebbe corretta |
| `threshold_exceeded` | Troppi casi idonei, nessuna correzione |
| `error_rollback` | Errore, registro ripristinato |
| `error_rollback_failed` | Ripristino fallito: esecuzione interrotta, snapshot nel log |
| `interrupted` | HA fermato durante un caso: snapshot nel log, nessun ripristino automatico |

Motivi: `multiple_live_candidates`, `orphan_disabled_or_hidden`, `orphan_no_config_entry`, `orphan_config_entry_not_loaded`, `live_no_config_entry`, `live_config_entry_not_loaded`, `orphan_device_mismatch`, `platform_mismatch`, `device_class_mismatch`, `unit_mismatch`, `references_found`, `config_entry_mismatch` (v1.1).

Tipi di riferimento: `a` automazioni/script/scene, `b` dashboard, `c` config entry, `d` file YAML + riga, `e` registro entità. Se una sorgente non è leggibile viene riportata come `scan_error:…` e il caso è saltato (prima la sicurezza).

## Limiti noti

- Il caso con solo `X_N` e `X` assente dal registro è gestito solo se `X` è ancora tra le voci eliminate e l'opzione è attiva.
- Un re-pairing che crea un nuovo dispositivo viene saltato (`orphan_device_mismatch`).
- Non sono analizzati sistemi esterni (AppDaemon, Node-RED, REST, YAML ESPHome, trigger vocali) né file fuori dalla directory di configurazione.
- Le statistiche a lungo termine non vengono unite: quelle di `X_N` possono restare orfane (*Strumenti per sviluppatori → Statistiche*). Segnalato con `statistics_may_be_orphaned`.
- Nessun undo: il rollback copre solo gli errori durante un caso.

## Log di debug

```yaml
logger:
  logs:
    custom_components.entity_dedup: debug
```

## Sviluppo

```bash
pip install -r requirements_test.txt
ruff check . && python tools/check_consistency.py && pytest -q
```

CI: hassfest, validazione HACS e test girano da `.github/workflows/`.
