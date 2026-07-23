# F1 Archive

Archivio analitico personale per esplorare la storia di ogni circuito di
Formula 1.

La descrizione completa di architettura, formule, grafici, interpretazione dei
dati e limiti è disponibile in
[Documentazione tecnica](docs/DOCUMENTAZIONE_TECNICA.md).

Per architettura e container:

- [Architettura runtime](docs/ARCHITECTURE.md)

La struttura rilevante per l'esecuzione è:

```text
backend/                 FastAPI, test, Dockerfile e lock Python
frontend/                React/Vite, Dockerfile e configurazione Nginx
compose.yaml             sviluppo locale con build
scripts/ci/              test, validazione e build portabili
.github/workflows/       test, build e pubblicazione; nessun deploy
```

## Fonti

- [Jolpica F1](https://api.jolpi.ca/ergast/f1/): calendari e risultati del
  mondiale dal 1950.
- [OpenF1](https://openf1.org/): integrazione opzionale per giri, stint, pit
  stop, sorpassi e meteo dal 2023.
- F1 live timing SignalR: adapter sperimentale per uso personale della vista
  Live, senza passare da OpenF1.

Il backend aggrega e mantiene in cache i dati. Per OpenF1 applica il limite
globale del piano gratuito: 3 richieste al secondo e 30 richieste al minuto.
L'arricchimento OpenF1 è disattivato per impostazione predefinita; si abilita
con `ENABLE_OPENF1_HISTORY=true`. Il live usa invece l'adapter F1 SignalR
configurato in `backend/.env`. Un errore OpenF1 non impedisce mai il caricamento
dell'archivio Jolpica.

La dashboard include:

- timing live con classifica, gap, meteo, messaggi FIA, traduzione italiana e
  posizione auto quando il feed fornisce coordinate;
- edizioni disputate, vincitori diversi e affidabilità;
- vittorie, podi e pole di piloti e costruttori;
- record sul giro disponibile nel dataset;
- vittorie dalla pole, griglia media del vincitore e migliori rimonte;
- timeline dei layout recenti con tracciato e curve per anno FastF1;
- albo completo delle edizioni;
- analisi OpenF1 dal 2023 su pit stop, mescole, sorpassi e gare bagnate.

## Live timing

La sezione **Live** usa `/api/f1signal/stream`, uno stream SSE alimentato dal
feed SignalR di F1 live timing. Il backend sottoscrive topic come `DriverList`,
`TimingData`, `WeatherData`, `RaceControlMessages`, `LapCount`, `Position.z` e
`CarData.z`, `TeamRadio`, poi li normalizza in uno snapshot consumabile dal
frontend.

Per autenticare il feed imposta una sola delle due variabili in `backend/.env`:

```bash
F1_SIGNALR_LOGIN_SESSION=...
F1_SIGNALR_AUTH_TOKEN=
```

`F1_SIGNALR_LOGIN_SESSION` è il valore URL-encoded del cookie `login-session`
visibile negli strumenti di sviluppo del browser su `formula1.com`. È il metodo
consigliato: il backend estrae in memoria `data.subscriptionToken`. In
alternativa puoi estrarre manualmente quel JWT e metterlo in
`F1_SIGNALR_AUTH_TOKEN`. I cookie `mk-token` ed `entitlement_token` non sono
necessari per l'adapter corrente.

Il token resta valido fino alla scadenza della sessione F1TV; non serve fare
login a ogni avvio se `backend/.env` contiene ancora un valore valido. Se hai
condiviso o incollato un token in luoghi non fidati, rigenera la sessione con
logout/login e aggiorna `.env`.

Per capire cosa contiene il token configurato, senza ristamparlo, usa:

```bash
cd backend
python -m app.token_tool
```

Il tool legge `backend/.env`, estrae l'eventuale `subscriptionToken` da
`F1_SIGNALR_LOGIN_SESSION`, decodifica header/payload JWT e mostra stato
abbonamento, prodotto, scadenza e se il token sembra utilizzabile per SignalR.
Non verifica la firma crittografica online e non stampa il token completo.

La posizione auto viene mostrata solo quando F1 invia il topic `Position.z`.
Quando arrivano coordinate, il backend accumula una traccia per pilota e la UI
disegna progressivamente la forma della pista usando il pilota con più punti.
Questo fallback funziona anche su piste nuove non ancora coperte da FastF1,
come Madrid. Su sessioni concluse o in finestre non live possono arrivare
classifica, messaggi e meteo, ma non coordinate GPS o telemetria grezza.

La team radio viene mostrata quando F1 invia il topic `TeamRadio`. Di solito il
payload contiene un path relativo come `TeamRadio/LIN_41_20260614_164234.mp3`;
il backend lo completa con la cartella statica della sessione, ad esempio
`/static/2026/2026-06-12_Spanish_Grand_Prix/2026-06-14_Race/`. La UI mostra
solo clip con URL audio ricostruito.

Il testo della team radio non arriva sempre dal feed. Quando arriva una nuova
clip riproducibile, il backend la mette in coda e la trascrive automaticamente
in locale con `faster-whisper`, usando `TEAM_RADIO_TRANSCRIPTION_PROVIDER=local`.
La UI mostra il testo come messaggio principale e un bottone play compatto per
ascoltare l'audio. Il bottone `IT` accanto al play traduce il transcript già
disponibile. Con `TEAM_RADIO_TRANSLATION_PROVIDER=googletrans` usa la libreria
`googletrans`; con `openai` usa OpenAI se `OPENAI_API_KEY` è configurata; con
`none` mostra solo il transcript originale. Di default traduce solo al click;
`TEAM_RADIO_AUTO_TRANSLATE_ENABLED=true` traduce automaticamente appena finisce
la trascrizione.
I transcript vengono salvati in cache per sessione sotto
`backend/.cache/f1signal/<sessione>/team_radio_transcriptions.json`, quindi
restano visibili anche dopo un refresh e diventano uno storico riutilizzabile.

## Analisi post-gara

FastF1 viene usato a sessione conclusa per calcolare:

- passo rappresentativo e miglior giro;
- velocità massima, percentuale full throttle e frenata;
- mappa del tracciato con numeri curva coerente con l'anno/sessione FastF1;
- grafico comparativo sulla distanza per velocità, acceleratore e freno,
  selezionabile tra FP1/FP2/FP3, Sprint, qualifica e gara;
- selezione del giro telemetrico: best lap per pilota oppure giro specifico
  quando disponibile;
- velocità minima media nelle curve lente, medie e veloci;
- stint, mescole e trend grezzo del passo.

La mappa del circuito usa coordinate X/Y FastF1 del weekend selezionato e
numeri curva da `circuit_info`, quindi segue il layout disponibile per quell'
anno. Le curve sono classificate sul giro telemetrico selezionato tramite la
velocità minima attorno alle coordinate fornite da FastF1: lente sotto 140
km/h, medie tra 140 e 209 km/h, veloci da 210 km/h. Passo gara e stint restano
sempre calcolati sulla sessione Race. Il trend stint non è degrado gomme puro:
include anche carburante, evoluzione pista, traffico e meteo.

Il primo caricamento di una gara può richiedere tempo; FastF1 salva poi i dati
in `backend/.cache/fastf1`.

## Predizioni

Il Prediction Center individua la prossima gara e produce un indice comparativo
basato su:

- forma nelle ultime cinque gare;
- forma pulita, che attenua l'effetto di ritiri tecnici o cause non chiare;
- forza recente della vettura/team;
- prestazione su circuiti tecnicamente simili;
- qualifica recente;
- confronto recente con il compagno;
- affidabilità tecnica del team;
- fiducia del pilota, basata su incidenti e penalità sportive osservabili;
- pacchetti upgrade dichiarati dal team, se inseriti nel file locale;
- affinità con temperature ambientali simili, quando disponibile.

Il profilo tecnico considera curve lente, medie e veloci, rettilinei e stress
gomme. Durante il weekend, quando FP2/FP3 sono disponibili, il modello assegna
il 45% del punteggio a giro secco, long run e quantità di giri completati.
Open-Meteo aggiunge temperatura, pioggia e vento nell'orizzonte di 16 giorni.
La temperatura prevista viene confrontata con le condizioni giornaliere delle
gare precedenti. Se previsione o storico non sono disponibili, il relativo
peso viene redistribuito tra forma e circuiti simili.

Gli upgrade tecnici sono opzionali e volutamente manuali: imposta
`PREDICTION_UPGRADES_FILE` e compila un JSON come
`backend/app/data/team_upgrades.example.json`. Il segnale entra solo nella
prediction pre-weekend; quando arrivano FP2/FP3, la prediction post-practice
mostra se il pacchetto sembra confermato dal ritmo in pista.

Il risultato è un ranking spiegabile, non una probabilità di vittoria né una
previsione finanziaria.

Il ranking include solo piloti con risultati stagionali sufficienti nella fonte
Jolpica. Piloti senza storico recente non ricevono ancora uno score inventato:
verranno integrati con entry list FastF1/F1 live quando aggiungeremo il layer
di copertura griglia completa.

Per preparare un eventuale modello ML, il backend espone anche
`/api/predictions/features`: genera esempi supervisionati dalle gare già
concluse usando solo feature disponibili prima della gara target. Il report
include diagnostica delle feature e una valutazione di prontezza ML, così
possiamo decidere se aggiungere un ranker leggero o raccogliere più dati da
FP, qualifica e archivio live.

Gli stati ufficiali distinguono guasti tecnici (`Engine`, `Gearbox`,
`Hydraulics` e simili), incidenti (`Collision`, `Accident`) ed esiti sportivi.
I guasti riducono l'affidabilità di entrambi i piloti del team; gli incidenti
incidono solo sul fattore del pilota coinvolto. Un generico `Retired` resta
neutrale e viene segnalato come causa ignota, perché può indicare sia guasti
sia incidenti non dettagliati dalla fonte risultati. La UI mostra percentuali
e conteggi reali. Affidabilità e incidenti entrano nel ranking come
percentuali reali, non con normalizzazione min-max, per evitare che un singolo
guasto a inizio stagione pesi troppo.

## Stack

- Backend: Python 3.11+, FastAPI, HTTPX
- Frontend: React 19, TypeScript, Vite
- Grafici: componenti React e CSS senza librerie aggiuntive

## Avvio

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# modifica .env e inserisci F1_SIGNALR_LOGIN_SESSION se vuoi il live
./run-dev.sh
```

Frontend, in un altro terminale:

```bash
cd frontend
npm install
npm run dev
```

Apri `http://localhost:5173`. Vite inoltra `/api` al backend.
In alternativa, dalla root del progetto puoi avviare entrambi con:

```bash
./run-dev.sh
```

Con Docker Compose:

```bash
cp .env.example .env
docker compose up --build
```

Apri `http://localhost:5173`. Il frontend Nginx inoltra `/api` al servizio
`api`; l'API non è esposta direttamente sull'host. La cache FastF1, SignalR e
prediction viene salvata nel volume Docker `backend-cache`. Inserire gli
eventuali secret solo nel file `.env` non tracciato.

Build e test senza Docker:

```bash
scripts/ci/test-backend.sh
scripts/ci/test-frontend.sh
scripts/ci/validate-compose.sh
```

Il Compose nella root è esclusivamente locale. Manifest di produzione,
versione distribuita, health check, rollback e dettagli infrastrutturali sono
mantenuti in un repository privato separato. I valori `VITE_*` sono pubblici e
incorporati nella build: l'app attuale non ne richiede perché usa `/api`.

Per costruire e, opzionalmente, pubblicare entrambe le immagini:

```bash
API_IMAGE=ghcr.io/<owner>/f1-companion-api \
FRONTEND_IMAGE=ghcr.io/<owner>/f1-companion-frontend \
IMAGE_TAG=<commit-sha> \
  scripts/ci/build-images.sh

PUSH_IMAGES=true API_IMAGE=ghcr.io/<owner>/f1-companion-api \
  FRONTEND_IMAGE=ghcr.io/<owner>/f1-companion-frontend \
  IMAGE_TAG=<commit-sha> scripts/ci/build-images.sh
```

Il secondo comando è documentale: richiede login e autorizzazioni configurati
manualmente. Codex non ha pubblicato immagini né configurato credenziali.

## API locali

- `GET /api/health`
- `GET /health`
- `GET /api/circuits`
- `GET /api/circuits/{circuit_id}/history`
- `GET /api/circuits/{circuit_id}/layout?year=2025`
- `GET /api/analysis/events?year=2025`
- `GET /api/analysis/post-race?year=2025&round_number=1&telemetry_session=race`
- `GET /api/predictions/next-race?year=2026&include_practice=true`
- `GET /api/seasons`
- `GET /api/meetings?year=2025`
- `GET /api/sessions?meeting_key=1254`
- `GET /api/snapshot?session_key=...&at=...`
- `GET /api/f1signal/status`
- `GET /api/f1signal/snapshot`
- `GET /api/f1signal/stream`

`at` è opzionale e accetta un timestamp ISO 8601. Se omesso viene usata la fine
della sessione per i replay storici oppure l'ora corrente durante una sessione.

Gli endpoint `/api/f1signal/*` usano un adapter sperimentale verso il feed
SignalR di F1 live timing e non passano da OpenF1. L'adapter parte solo quando
viene chiamato uno di questi endpoint. Se disponibile, imposta
`F1_SIGNALR_AUTH_TOKEN` con il `subscriptionToken` F1 valido, oppure
`F1_SIGNALR_LOGIN_SESSION` con il valore URL-encoded del cookie `login-session`
nel file `backend/.env` e il backend estrarrà il token in memoria. Senza token
il feed può essere vuoto o parziale. Gli URL sono configurabili con
`F1_SIGNALR_CONNECTION_URL` e `F1_SIGNALR_NEGOTIATE_URL`.

Quando `F1_SIGNALR_ARCHIVE_ENABLED=true`, ogni snapshot live letto dagli
endpoint F1 SignalR viene salvato in JSONL sotto
`backend/.cache/f1signal/<sessione>/snapshots.jsonl` per replay e prediction.
La frequenza di scrittura è controllata da
`F1_SIGNALR_SNAPSHOT_ARCHIVE_INTERVAL_SECONDS` e il percorso da
`F1_SIGNALR_ARCHIVE_DIR`.

## Limiti dei dati

I risultati sono disponibili dal 1950, ma giro veloce, velocità media e altri
campi non sono presenti con la stessa completezza in ogni epoca. Il record
mostrato è quindi il migliore disponibile nel dataset Jolpica, non
necessariamente il record ufficiale assoluto del tracciato. Le statistiche
OpenF1 riportano separatamente la copertura dal 2023.
