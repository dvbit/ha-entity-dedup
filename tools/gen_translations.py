"""Generate strings.json and translations/*.json (en, it, fr, de, es).

Single source of truth so the five languages always share the same keys.
Run: python tools/gen_translations.py
"""

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "custom_components" / "entity_dedup"

# Each leaf: {lang: text}
T = {
    "config.step.user.title": {
        "en": "Entity Dedup",
        "it": "Entity Dedup",
        "fr": "Entity Dedup",
        "de": "Entity Dedup",
        "es": "Entity Dedup",
    },
    "config.step.user.description": {
        "en": "After every restart, finds `_N` duplicate entities created because the original entity_id was still held by an orphan registry entry, removes the orphan and renames the live entity back. Default options are applied; change them later from Configure.",
        "it": "Dopo ogni riavvio individua le entità duplicate `_N` create perché l'entity_id originale era ancora occupato da una voce orfana del registro, elimina l'orfana e rinomina l'entità viva. Vengono applicate le opzioni predefinite, modificabili poi da Configura.",
        "fr": "Après chaque redémarrage, détecte les entités dupliquées `_N` créées parce que l'entity_id d'origine était encore occupé par une entrée orpheline du registre, supprime l'orpheline et renomme l'entité active. Les options par défaut sont appliquées ; modifiez-les ensuite via Configurer.",
        "de": "Findet nach jedem Neustart `_N`-Duplikate, die entstanden sind, weil die ursprüngliche entity_id noch von einem verwaisten Registry-Eintrag belegt war, löscht den verwaisten Eintrag und benennt die aktive Entität zurück. Es gelten die Standardoptionen; ändere sie später über Konfigurieren.",
        "es": "Tras cada reinicio detecta las entidades duplicadas `_N` creadas porque el entity_id original seguía ocupado por una entrada huérfana del registro, elimina la huérfana y renombra la entidad activa. Se aplican las opciones predeterminadas; cámbialas después desde Configurar.",
    },
    "config.abort.single_instance_allowed": {
        "en": "Already configured. Only a single configuration is possible.",
        "it": "Già configurato. È possibile una sola configurazione.",
        "fr": "Déjà configuré. Une seule configuration est possible.",
        "de": "Bereits konfiguriert. Nur eine einzige Konfiguration ist möglich.",
        "es": "Ya configurado. Solo es posible una configuración.",
    },
    "options.step.init.title": {
        "en": "Entity Dedup options",
        "it": "Opzioni Entity Dedup",
        "fr": "Options d'Entity Dedup",
        "de": "Entity Dedup Optionen",
        "es": "Opciones de Entity Dedup",
    },
    "options.step.init.description": {
        "en": "Changes apply from the next run; nothing is reloaded or executed now.",
        "it": "Le modifiche valgono dalla prossima esecuzione; nulla viene ricaricato o eseguito ora.",
        "fr": "Les modifications s'appliquent à la prochaine exécution ; rien n'est rechargé ni exécuté maintenant.",
        "de": "Änderungen gelten ab dem nächsten Lauf; jetzt wird nichts neu geladen oder ausgeführt.",
        "es": "Los cambios se aplican desde la próxima ejecución; ahora no se recarga ni se ejecuta nada.",
    },
    "options.step.init.data.delay_minutes": {
        "en": "Delay after startup (minutes)",
        "it": "Ritardo dopo l'avvio (minuti)",
        "fr": "Délai après le démarrage (minutes)",
        "de": "Verzögerung nach dem Start (Minuten)",
        "es": "Retraso tras el arranque (minutos)",
    },
    "options.step.init.data.max_corrections": {
        "en": "Maximum corrections per run",
        "it": "Correzioni massime per esecuzione",
        "fr": "Corrections maximales par exécution",
        "de": "Maximale Korrekturen pro Lauf",
        "es": "Correcciones máximas por ejecución",
    },
    "options.step.init.data.log_max_entries": {
        "en": "Log rows kept",
        "it": "Righe di log conservate",
        "fr": "Lignes de journal conservées",
        "de": "Aufbewahrte Protokollzeilen",
        "es": "Filas de registro conservadas",
    },
    "options.step.init.data.denylist_domains": {
        "en": "Excluded domains",
        "it": "Domini esclusi",
        "fr": "Domaines exclus",
        "de": "Ausgeschlossene Domänen",
        "es": "Dominios excluidos",
    },
    "options.step.init.data.denylist_entities": {
        "en": "Excluded entities",
        "it": "Entità escluse",
        "fr": "Entités exclues",
        "de": "Ausgeschlossene Entitäten",
        "es": "Entidades excluidas",
    },
    "options.step.init.data_description.delay_minutes": {
        "en": "Wait after Home Assistant has started before the automatic run (1–120).",
        "it": "Attesa dopo l'avvio di Home Assistant prima dell'esecuzione automatica (1–120).",
        "fr": "Attente après le démarrage de Home Assistant avant l'exécution automatique (1–120).",
        "de": "Wartezeit nach dem Start von Home Assistant vor dem automatischen Lauf (1–120).",
        "es": "Espera tras el arranque de Home Assistant antes de la ejecución automática (1–120).",
    },
    "options.step.init.data_description.max_corrections": {
        "en": "If more cases are eligible, nothing is corrected and you are notified (1–100). Override once with run_now ignore_limit.",
        "it": "Se i casi idonei sono di più, non si corregge nulla e ricevi una notifica (1–100). Superabile una volta con run_now ignore_limit.",
        "fr": "Si davantage de cas sont éligibles, rien n'est corrigé et vous êtes notifié (1–100). Contournable une fois avec run_now ignore_limit.",
        "de": "Sind mehr Fälle geeignet, wird nichts korrigiert und du wirst benachrichtigt (1–100). Einmalig mit run_now ignore_limit übergehbar.",
        "es": "Si hay más casos aptos, no se corrige nada y recibes una notificación (1–100). Se puede omitir una vez con run_now ignore_limit.",
    },
    "options.step.init.data_description.log_max_entries": {
        "en": "Older rows are dropped after each write (50–5000).",
        "it": "Le righe più vecchie vengono eliminate dopo ogni scrittura (50–5000).",
        "fr": "Les lignes les plus anciennes sont supprimées après chaque écriture (50–5000).",
        "de": "Ältere Zeilen werden nach jedem Schreibvorgang entfernt (50–5000).",
        "es": "Las filas más antiguas se eliminan tras cada escritura (50–5000).",
    },
    "options.step.init.data_description.denylist_domains": {
        "en": "Cases whose entities belong to these domains are ignored silently.",
        "it": "I casi con entità di questi domini vengono ignorati in silenzio.",
        "fr": "Les cas dont les entités appartiennent à ces domaines sont ignorés silencieusement.",
        "de": "Fälle mit Entitäten dieser Domänen werden stillschweigend ignoriert.",
        "es": "Los casos con entidades de estos dominios se ignoran en silencio.",
    },
    "options.step.init.data_description.denylist_entities": {
        "en": "Cases involving these entities (base or `_N`) are ignored silently, also by run_now.",
        "it": "I casi che coinvolgono queste entità (base o `_N`) vengono ignorati in silenzio, anche da run_now.",
        "fr": "Les cas impliquant ces entités (base ou `_N`) sont ignorés silencieusement, y compris par run_now.",
        "de": "Fälle mit diesen Entitäten (Basis oder `_N`) werden stillschweigend ignoriert, auch von run_now.",
        "es": "Los casos con estas entidades (base o `_N`) se ignoran en silencio, también en run_now.",
    },
    "options.error.invalid_domain": {
        "en": "Invalid domain name (lowercase letters, digits, underscore).",
        "it": "Nome di dominio non valido (minuscole, cifre, underscore).",
        "fr": "Nom de domaine invalide (minuscules, chiffres, tiret bas).",
        "de": "Ungültiger Domänenname (Kleinbuchstaben, Ziffern, Unterstrich).",
        "es": "Nombre de dominio no válido (minúsculas, dígitos, guion bajo).",
    },
    "options.error.invalid_entity_id": {
        "en": "Invalid entity_id.",
        "it": "entity_id non valido.",
        "fr": "entity_id invalide.",
        "de": "Ungültige entity_id.",
        "es": "entity_id no válido.",
    },
    "entity.sensor.last_run.name": {
        "en": "Last run",
        "it": "Ultima esecuzione",
        "fr": "Dernière exécution",
        "de": "Letzter Lauf",
        "es": "Última ejecución",
    },
    "entity.sensor.last_fixed.name": {
        "en": "Last run fixed",
        "it": "Corrette nell'ultima esecuzione",
        "fr": "Corrigées à la dernière exécution",
        "de": "Korrigiert im letzten Lauf",
        "es": "Corregidas en la última ejecución",
    },
    "entity.sensor.last_skipped.name": {
        "en": "Last run not fixed",
        "it": "Non corrette nell'ultima esecuzione",
        "fr": "Non corrigées à la dernière exécution",
        "de": "Nicht korrigiert im letzten Lauf",
        "es": "No corregidas en la última ejecución",
    },
    "entity.switch.enabled.name": {
        "en": "Automatic run after restart",
        "it": "Esecuzione automatica dopo il riavvio",
        "fr": "Exécution automatique après redémarrage",
        "de": "Automatischer Lauf nach Neustart",
        "es": "Ejecución automática tras el reinicio",
    },
    "services.run_now.name": {
        "en": "Run now",
        "it": "Esegui ora",
        "fr": "Exécuter maintenant",
        "de": "Jetzt ausführen",
        "es": "Ejecutar ahora",
    },
    "services.run_now.description": {
        "en": "Detects and fixes `_N` duplicate entities now. Works even with the automatic run switched off.",
        "it": "Rileva e corregge ora le entità duplicate `_N`. Funziona anche con l'esecuzione automatica spenta.",
        "fr": "Détecte et corrige maintenant les entités dupliquées `_N`. Fonctionne même avec l'exécution automatique désactivée.",
        "de": "Erkennt und korrigiert jetzt `_N`-Duplikate. Funktioniert auch bei ausgeschaltetem automatischem Lauf.",
        "es": "Detecta y corrige ahora las entidades duplicadas `_N`. Funciona incluso con la ejecución automática desactivada.",
    },
    "services.run_now.fields.dry_run.name": {
        "en": "Dry run",
        "it": "Simulazione",
        "fr": "Simulation",
        "de": "Probelauf",
        "es": "Simulación",
    },
    "services.run_now.fields.dry_run.description": {
        "en": "Only detect, log and notify; the registry is not changed.",
        "it": "Solo rilevazione, log e notifica; il registro non viene modificato.",
        "fr": "Détecter, journaliser et notifier uniquement ; le registre n'est pas modifié.",
        "de": "Nur erkennen, protokollieren und benachrichtigen; die Registry wird nicht geändert.",
        "es": "Solo detectar, registrar y notificar; el registro no se modifica.",
    },
    "services.run_now.fields.ignore_limit.name": {
        "en": "Ignore limit",
        "it": "Ignora limite",
        "fr": "Ignorer la limite",
        "de": "Limit ignorieren",
        "es": "Ignorar límite",
    },
    "services.run_now.fields.ignore_limit.description": {
        "en": "Ignore the maximum number of corrections for this run only.",
        "it": "Ignora il numero massimo di correzioni solo per questa esecuzione.",
        "fr": "Ignorer le nombre maximal de corrections pour cette exécution uniquement.",
        "de": "Die maximale Anzahl an Korrekturen nur für diesen Lauf ignorieren.",
        "es": "Ignorar el número máximo de correcciones solo en esta ejecución.",
    },
    "services.run_now.fields.entity_id.name": {
        "en": "Base entity",
        "it": "Entità base",
        "fr": "Entité de base",
        "de": "Basis-Entität",
        "es": "Entidad base",
    },
    "services.run_now.fields.entity_id.description": {
        "en": "Limit the run to this base entity_id (without `_N`), taken literally.",
        "it": "Limita l'esecuzione a questo entity_id base (senza `_N`), preso alla lettera.",
        "fr": "Limiter l'exécution à cet entity_id de base (sans `_N`), pris tel quel.",
        "de": "Den Lauf auf diese Basis-entity_id (ohne `_N`) beschränken, wörtlich genommen.",
        "es": "Limitar la ejecución a este entity_id base (sin `_N`), tomado literalmente.",
    },
    "services.get_log.name": {
        "en": "Get log",
        "it": "Leggi log",
        "fr": "Lire le journal",
        "de": "Protokoll abrufen",
        "es": "Leer registro",
    },
    "services.get_log.description": {
        "en": "Returns the persistent log rows, newest first.",
        "it": "Restituisce le righe del log persistente, dalla più recente.",
        "fr": "Renvoie les lignes du journal persistant, des plus récentes aux plus anciennes.",
        "de": "Gibt die Zeilen des dauerhaften Protokolls zurück, neueste zuerst.",
        "es": "Devuelve las filas del registro persistente, de la más reciente a la más antigua.",
    },
    "services.get_log.fields.limit.name": {
        "en": "Limit",
        "it": "Limite",
        "fr": "Limite",
        "de": "Limit",
        "es": "Límite",
    },
    "services.get_log.fields.limit.description": {
        "en": "Maximum number of rows (1–500).",
        "it": "Numero massimo di righe (1–500).",
        "fr": "Nombre maximal de lignes (1–500).",
        "de": "Maximale Anzahl an Zeilen (1–500).",
        "es": "Número máximo de filas (1–500).",
    },
    "services.get_log.fields.since.name": {
        "en": "Since",
        "it": "Da",
        "fr": "Depuis",
        "de": "Seit",
        "es": "Desde",
    },
    "services.get_log.fields.since.description": {
        "en": "Only rows written after this moment.",
        "it": "Solo righe scritte dopo questo istante.",
        "fr": "Uniquement les lignes écrites après cet instant.",
        "de": "Nur Zeilen, die nach diesem Zeitpunkt geschrieben wurden.",
        "es": "Solo filas escritas después de este momento.",
    },
    "exceptions.already_running.message": {
        "en": "A run is already in progress, try again later.",
        "it": "Un'esecuzione è già in corso, riprova più tardi.",
        "fr": "Une exécution est déjà en cours, réessayez plus tard.",
        "de": "Ein Lauf ist bereits aktiv, versuche es später erneut.",
        "es": "Ya hay una ejecución en curso, inténtalo más tarde.",
    },
    "exceptions.not_loaded.message": {
        "en": "Entity Dedup is not loaded.",
        "it": "Entity Dedup non è caricato.",
        "fr": "Entity Dedup n'est pas chargé.",
        "de": "Entity Dedup ist nicht geladen.",
        "es": "Entity Dedup no está cargado.",
    },
    "exceptions.notify_title.message": {
        "en": "Entity Dedup report",
        "it": "Report Entity Dedup",
        "fr": "Rapport Entity Dedup",
        "de": "Entity Dedup Bericht",
        "es": "Informe de Entity Dedup",
    },
    "exceptions.notify_title_dry_run.message": {
        "en": "Entity Dedup report (simulation)",
        "it": "Report Entity Dedup (simulazione)",
        "fr": "Rapport Entity Dedup (simulation)",
        "de": "Entity Dedup Bericht (Probelauf)",
        "es": "Informe de Entity Dedup (simulación)",
    },
    "exceptions.notify_summary.message": {
        "en": "Fixed: {fixed} · Skipped: {skipped} · Would fix: {would_fix} · Errors: {errors}",
        "it": "Corrette: {fixed} · Saltate: {skipped} · Da correggere: {would_fix} · Errori: {errors}",
        "fr": "Corrigées : {fixed} · Ignorées : {skipped} · À corriger : {would_fix} · Erreurs : {errors}",
        "de": "Korrigiert: {fixed} · Übersprungen: {skipped} · Würde korrigieren: {would_fix} · Fehler: {errors}",
        "es": "Corregidas: {fixed} · Omitidas: {skipped} · Se corregirían: {would_fix} · Errores: {errors}",
    },
    "exceptions.notify_threshold.message": {
        "en": "Limit exceeded: {count} eligible cases > {max}. Nothing corrected; use run_now with ignore_limit to proceed.",
        "it": "Limite superato: {count} casi idonei > {max}. Nessuna correzione; usa run_now con ignore_limit per procedere.",
        "fr": "Limite dépassée : {count} cas éligibles > {max}. Aucune correction ; utilisez run_now avec ignore_limit pour continuer.",
        "de": "Limit überschritten: {count} geeignete Fälle > {max}. Nichts korrigiert; nutze run_now mit ignore_limit zum Fortfahren.",
        "es": "Límite superado: {count} casos aptos > {max}. No se ha corregido nada; usa run_now con ignore_limit para continuar.",
    },
    "exceptions.notify_extra_orphans.message": {
        "en": "extra orphans: {extras}",
        "it": "orfane extra: {extras}",
        "fr": "orphelines supplémentaires : {extras}",
        "de": "weitere verwaiste: {extras}",
        "es": "huérfanas adicionales: {extras}",
    },
    "exceptions.notify_more_references.message": {
        "en": "… and {count} more references",
        "it": "… e altri {count} riferimenti",
        "fr": "… et {count} autres références",
        "de": "… und {count} weitere Verweise",
        "es": "… y {count} referencias más",
    },
    "exceptions.notify_statistics.message": {
        "en": "long-term statistics of {live} may remain orphaned (Developer tools → Statistics)",
        "it": "le statistiche a lungo termine di {live} possono restare orfane (Strumenti per sviluppatori → Statistiche)",
        "fr": "les statistiques à long terme de {live} peuvent rester orphelines (Outils de développement → Statistiques)",
        "de": "Langzeitstatistiken von {live} können verwaist bleiben (Entwicklerwerkzeuge → Statistiken)",
        "es": "las estadísticas a largo plazo de {live} pueden quedar huérfanas (Herramientas para desarrolladores → Estadísticas)",
    },
    "exceptions.notify_error.message": {
        "en": "error: {error}",
        "it": "errore: {error}",
        "fr": "erreur : {error}",
        "de": "Fehler: {error}",
        "es": "error: {error}",
    },
    "exceptions.notify_aborted.message": {
        "en": "Run stopped: a rollback failed. The snapshot is kept in the log, check the registry manually.",
        "it": "Esecuzione interrotta: un rollback è fallito. Lo snapshot resta nel log, verifica il registro a mano.",
        "fr": "Exécution arrêtée : un rollback a échoué. L'instantané est conservé dans le journal, vérifiez le registre manuellement.",
        "de": "Lauf gestoppt: ein Rollback ist fehlgeschlagen. Der Snapshot bleibt im Protokoll, prüfe die Registry manuell.",
        "es": "Ejecución detenida: un rollback ha fallado. La instantánea se conserva en el registro, revisa el registro de entidades a mano.",
    },
    "exceptions.notify_interrupted_header.message": {
        "en": "Interrupted cases (Home Assistant stopped during a correction; snapshot kept in the log, no automatic restore):",
        "it": "Casi interrotti (Home Assistant fermato durante una correzione; snapshot nel log, nessun ripristino automatico):",
        "fr": "Cas interrompus (Home Assistant arrêté pendant une correction ; instantané conservé dans le journal, pas de restauration automatique) :",
        "de": "Unterbrochene Fälle (Home Assistant wurde während einer Korrektur gestoppt; Snapshot im Protokoll, keine automatische Wiederherstellung):",
        "es": "Casos interrumpidos (Home Assistant se detuvo durante una corrección; instantánea en el registro, sin restauración automática):",
    },
    "exceptions.notify_footer.message": {
        "en": "Full details: action `entity_dedup.get_log`.",
        "it": "Dettagli completi: azione `entity_dedup.get_log`.",
        "fr": "Détails complets : action `entity_dedup.get_log`.",
        "de": "Alle Details: Aktion `entity_dedup.get_log`.",
        "es": "Detalles completos: acción `entity_dedup.get_log`.",
    },
    "exceptions.notify_outcome_fixed.message": {
        "en": "fixed",
        "it": "corretta",
        "fr": "corrigée",
        "de": "korrigiert",
        "es": "corregida",
    },
    "exceptions.notify_outcome_skipped.message": {
        "en": "skipped",
        "it": "saltata",
        "fr": "ignorée",
        "de": "übersprungen",
        "es": "omitida",
    },
    "exceptions.notify_outcome_would_fix.message": {
        "en": "would be fixed",
        "it": "sarebbe corretta",
        "fr": "serait corrigée",
        "de": "würde korrigiert",
        "es": "se corregiría",
    },
    "exceptions.notify_outcome_error_rollback.message": {
        "en": "error, rolled back",
        "it": "errore, ripristinata",
        "fr": "erreur, restaurée",
        "de": "Fehler, zurückgesetzt",
        "es": "error, revertida",
    },
    "exceptions.notify_outcome_error_rollback_failed.message": {
        "en": "error, ROLLBACK FAILED",
        "it": "errore, RIPRISTINO FALLITO",
        "fr": "erreur, RESTAURATION ÉCHOUÉE",
        "de": "Fehler, ROLLBACK FEHLGESCHLAGEN",
        "es": "error, REVERSIÓN FALLIDA",
    },
}


def build(lang):
    out = {}
    for key, texts in T.items():
        node = out
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = texts[lang]
    return out


for lang in ("en", "it", "fr", "de", "es"):
    missing = [k for k, v in T.items() if lang not in v]
    assert not missing, (lang, missing)
    data = json.dumps(build(lang), ensure_ascii=False, indent=2) + "\n"
    (BASE / "translations").mkdir(exist_ok=True)
    (BASE / "translations" / f"{lang}.json").write_text(data, encoding="utf-8")
    if lang == "en":
        (BASE / "strings.json").write_text(data, encoding="utf-8")
print("written", len(T), "keys x 5 languages")
