# Documentazione tecnica di F1 Insight

Questo documento descrive lo stato attuale dell'applicazione: quali
funzionalità sono disponibili, da dove arrivano i dati, come vengono
trasformati, come sono implementate le visualizzazioni e come interpretarle.

## 1. Obiettivo e stato del prodotto

F1 Insight è un'applicazione personale per:

1. seguire il timing live tramite un adapter F1 SignalR sperimentale;
2. consultare la storia di un circuito di Formula 1;
3. analizzare una gara conclusa tramite telemetria;
4. produrre un ranking comparativo per la gara successiva;
5. aggiornare il ranking con FP2 e FP3 quando sono disponibili.

La navigazione corrente espone quattro sezioni:

- **Live**
- **Archivio**
- **Post-gara**
- **Predizioni**

## 2. Architettura

```text
Browser
  |
  | /api tramite proxy Vite
  v
FastAPI
  |-- Jolpica F1: calendari e risultati storici
  |-- FastF1: giri, telemetria, stint e sessioni di prove
  |-- Open-Meteo: previsione e temperature storiche
  |-- OpenF1: arricchimento storico opzionale e snapshot/replay
  `-- F1 SignalR: timing live sperimentale per uso personale
```

### Backend

- Python 3.11+
- FastAPI per gli endpoint HTTP
- HTTPX per le chiamate asincrone
- FastF1 per i dati di sessione
- cache TTL in memoria per le API HTTP
- cache FastF1 su disco in `backend/.cache/fastf1`

I moduli principali sono:

- `main.py`: applicazione FastAPI e gestione errori;
- `jolpica.py`: client e paginazione Jolpica;
- `history.py`: aggregazione storica per circuito;
- `telemetry.py`: analisi post-gara e free practice;
- `predictions.py`: ranking pre-gara e aggiornamento post-prove;
- `weather.py`: previsione e archivio Open-Meteo;
- `openf1.py`: client OpenF1 e snapshot temporale;
- `f1signal.py`: adapter SignalR, traduzione topic e snapshot live;
- `cache.py`: cache asincrona TTL;
- `rate_limit.py`: limite globale OpenF1.

### Frontend

- React 19
- TypeScript in modalità `strict`
- Vite
- CSS proprietario
- SVG nativo per il grafico telemetrico

Non viene usato un router: `App.tsx` mantiene nello stato la sezione attiva e
monta uno tra `LiveView`, `ArchiveView`, `PostRaceView` e `PredictionView`.

Il frontend non contiene logica statistica sostanziale. Riceve dal backend
dati già aggregati e li presenta.

## 3. Fonti dati

### Jolpica F1

È la fonte principale per:

- elenco circuiti;
- calendario;
- risultati dal 1950;
- griglia, punti, costruttore e stato finale;
- giro veloce quando presente.

La disponibilità dei singoli campi cambia tra le epoche.

### FastF1

È usato per:

- giri accurati;
- telemetria del giro rappresentativo;
- velocità, acceleratore e freno;
- coordinate delle curve;
- stint e mescole;
- meteo della sessione;
- FP2 e FP3.

Il primo caricamento può essere lento perché FastF1 deve scaricare ed
elaborare la sessione. I caricamenti successivi usano la cache su disco.

### Open-Meteo

È usato senza chiave API per:

- previsione del giorno di gara entro 16 giorni;
- temperatura minima e massima;
- probabilità massima di precipitazione;
- vento massimo;
- temperatura media storica dei GP precedenti.

### OpenF1

L'arricchimento storico è disabilitato per impostazione predefinita:

```bash
ENABLE_OPENF1_HISTORY=false
```

Se abilitato, aggiunge dal 2023:

- giri;
- pit stop;
- stint e mescole;
- sorpassi;
- rilevazione di gare bagnate.

Ogni chiamata passa dal rate limiter globale configurato a 3 richieste al
secondo e 30 al minuto. Un errore OpenF1 non blocca l'archivio Jolpica.

### F1 live timing SignalR

La vista Live usa un adapter sperimentale verso il feed SignalR di F1 live
timing. L'adapter non passa da OpenF1 e viene avviato solo quando il frontend
chiama uno degli endpoint `/api/f1signal/*`.

I topic sottoscritti includono:

- `DriverList`;
- `TimingData`;
- `WeatherData`;
- `RaceControlMessages`;
- `SessionInfo` e `SessionStatus`;
- `TeamRadio`;
- `TrackStatus`;
- `LapCount`;
- `Position.z`;
- `CarData.z`.

I payload `.z` sono compressi con raw deflate codificato base64. Il backend li
decodifica e normalizza in:

- piloti;
- posizioni e distacchi;
- meteo;
- messaggi FIA;
- stato pista;
- conteggio giri;
- clip team radio quando disponibili;
- coordinate auto quando disponibili;
- mini telemetria quando disponibile.

L'autenticazione viene letta da `backend/.env`. Il metodo consigliato è
impostare `F1_SIGNALR_LOGIN_SESSION` con il valore URL-encoded del cookie
`login-session` di `formula1.com`; il backend estrae in memoria
`data.subscriptionToken`. In alternativa si può impostare direttamente
`F1_SIGNALR_AUTH_TOKEN` con quel JWT. `mk-token` ed `entitlement_token` non sono
usati dall'adapter corrente.

Lo status `/api/f1signal/status` espone `token_source` per indicare quale
configurazione è stata usata, senza restituire il token. Il token resta valido
fino alla scadenza della sessione F1TV. Se viene condiviso accidentalmente,
serve rigenerarlo con logout/login.

Il comando locale:

```bash
cd backend
python -m app.token_tool
```

legge `.env`, estrae il `subscriptionToken` da `F1_SIGNALR_LOGIN_SESSION` se
presente e decodifica header/payload JWT senza stampare il token completo. Il
tool mostra algoritmo, `kid`, issuer, stato abbonamento, prodotto, scadenza,
entitlements e un indicatore euristico `usable_for_signalr`. Non effettua una
verifica crittografica online della firma.

## 4. Flusso HTTP e gestione errori

Il frontend usa una sola funzione `request<T>`:

1. esegue `fetch`;
2. controlla `response.ok`;
3. prova a leggere `detail` dalla risposta FastAPI;
4. genera un errore visualizzato nel banner della sezione.

In sviluppo Vite inoltra `/api` a `http://localhost:8000`.

FastAPI traduce gli errori principali in:

- `404`: circuito, sessione o prossima gara non trovati;
- `502`: fonte HTTP esterna non raggiungibile;
- `503`: telemetria FastF1 non disponibile.

Lo stream live usa Server-Sent Events:

- `GET /api/f1signal/status`: stato adapter, connessione, topic ricevuti e fonte
  token, stato archivio locale e directory di scrittura;
- `GET /api/f1signal/snapshot`: avvia l'adapter se necessario e restituisce lo
  stato live corrente;
- `GET /api/f1signal/stream`: invia eventi `snapshot` ogni 1-10 secondi.

La UI usa `EventSource` e aggiorna la dashboard Live a ogni evento. Se lo stream
fallisce, effettua un fallback a snapshot singolo.

Quando `F1_SIGNALR_ARCHIVE_ENABLED=true`, ogni snapshot richiesto dagli
endpoint live viene accodato in formato JSONL. La frequenza minima tra due
scritture è configurata con `F1_SIGNALR_SNAPSHOT_ARCHIVE_INTERVAL_SECONDS`.
Questo evita di salvare ogni frame SignalR grezzo e mantiene un dataset già
normalizzato per analisi e prediction.

## 5. Archivio storico

### 5.1 Selezione circuito

`GET /api/circuits` recupera i circuiti Jolpica. Il frontend:

- li ordina prima per nazione e poi per nome;
- li raggruppa in `<optgroup>`;
- usa Monza come selezione iniziale;
- richiede nuovamente la storia quando cambia `circuitId`.

### 5.2 Caricamento e aggregazione

`GET /api/circuits/{circuit_id}/history` esegue in parallelo:

- elenco circuiti;
- risultati del circuito scelto.

Jolpica può paginare una stessa gara su più risposte. Il client unisce le
pagine usando la coppia `(stagione, round)` per evitare edizioni duplicate.

### 5.3 KPI dell'archivio

#### Edizioni mondiali

Numero di gare con almeno un risultato disponibile per quel `circuitId`.

#### Vincitori diversi

Numero di nomi pilota distinti che hanno vinto almeno una gara. Il dettaglio
mostra il numero di costruttori distinti vincitori.

#### Vittorie dalla pole

Formula:

```text
gare vinte partendo P1 / edizioni disponibili * 100
```

Una partenza dalla pit lane è rappresentata da griglia `0`.

#### Affidabilità storica

Formula:

```text
risultati con positionText numerico / totale partenti * 100
```

Questa metrica significa quindi **percentuale di vetture classificate nel
dataset**, non affidabilità meccanica pura. Incidenti, guasti e altri ritiri
sono tutti fuori dal numeratore.

#### Griglia media vincente

Media aritmetica della posizione di partenza dei vincitori:

```text
somma delle posizioni di griglia dei vincitori / numero di edizioni
```

Un valore vicino a P1 indica un circuito storicamente favorevole a chi parte
davanti. Non misura da solo la difficoltà di sorpasso, perché safety car,
meteo, epoca tecnica e strategie non vengono controllati.

### 5.4 Record sul giro disponibile

Per ogni risultato viene letto `FastestLap.Time.time`, convertito in secondi e
confrontato con tutti gli altri giri veloci disponibili sul circuito.

Viene mostrato il tempo minimo presente nel dataset con:

- pilota;
- costruttore;
- anno;
- numero del giro;
- velocità media, se fornita.

Non è necessariamente il record ufficiale assoluto del tracciato. Può mancare
un'edizione, una configurazione diversa del circuito o un dato storico.

### 5.5 Rimonte vincenti

Per ogni edizione viene identificato il risultato con posizione finale `1`.
Le vittorie vengono ordinate dalla posizione di partenza più arretrata alla
più avanzata.

La statistica è specifica del circuito selezionato. Per questo una rimonta
globale famosa non compare su un circuito diverso.

### 5.6 Classifiche piloti e costruttori

Sono contatori semplici:

- vittorie piloti;
- vittorie costruttori;
- podi, contando i primi tre risultati;
- pole, cercando `grid == 1`.

Il backend restituisce al massimo otto righe; il frontend ne mostra sei.

Le barre sono relative al leader della singola classifica:

```text
larghezza = valore pilota / valore massimo * 100
```

È applicata una larghezza minima del 5% per mantenere visibili anche valori
molto piccoli. La barra non rappresenta una percentuale sul totale.

### 5.7 Grafico "Da dove si vince"

Ogni colonna rappresenta quante vittorie sono arrivate da:

- Pole;
- P2, P3 e così via;
- Pit lane.

L'altezza è normalizzata rispetto alla colonna più alta:

```text
altezza = vittorie da quella griglia / massimo conteggio * 100
```

Il numero sopra la colonna è il dato assoluto. L'altezza serve solo al
confronto visivo.

### 5.8 Tabella delle edizioni

Le edizioni sono mostrate dalla più recente alla più vecchia con:

- anno;
- vincitore;
- costruttore;
- griglia del vincitore;
- poleman;
- giro più veloce dell'edizione;
- ritiri sul totale partenti.

Il numero di ritiri conta i risultati con `positionText` non numerico.

### 5.9 Pannello OpenF1 opzionale

Quando abilitato, il circuito Jolpica viene associato ai meeting OpenF1 tramite
località, nome breve e una tabella di alias.

Per ogni gara conclusa vengono raccolti:

- giri validi non pit-out;
- pit stop con durata numerica;
- stint;
- sorpassi;
- meteo;
- anagrafica piloti.

Il pannello mostra:

- sorpassi medi per GP;
- pit stop medi per GP;
- durata media dei pit;
- numero di gare con almeno un campione `rainfall`;
- giro più rapido dal 2023;
- pit più rapido;
- frequenza delle mescole negli stint.

La copertura è dichiarata separatamente perché non è confrontabile con lo
storico completo dal 1950.

### 5.10 Timeline layout recenti

Nell'Archivio è disponibile un pannello "Evoluzione tracciato" per scorrere
gli anni con copertura FastF1. Il frontend propone le edizioni del circuito dal
2018 in poi, carica un solo anno alla volta e chiama:

```text
GET /api/circuits/{circuit_id}/layout?year=...
```

Il backend usa Jolpica per trovare il round corretto di quel circuito nella
stagione scelta, poi carica la sessione Race FastF1 di quell'edizione e
restituisce la stessa struttura `circuit_map` usata nel Post-gara.

Questa scelta evita di scaricare in blocco molte sessioni FastF1, che sarebbe
lento e pesante. La copertura non è all-time: per i tracciati storici più
vecchi senza FastF1 non viene inventato alcun layout.

## 6. Analisi post-gara

### 6.1 Selezione della gara

`GET /api/analysis/events?year=...` usa il calendario Jolpica e marca come
conclusa una gara quando data e ora risultano precedenti all'istante attuale.

Il frontend:

- propone stagioni dal 2018 a quella corrente;
- mostra solo gare concluse;
- seleziona automaticamente l'ultima disponibile.

`GET /api/analysis/post-race` carica poi la sessione Race tramite FastF1. Il
parametro `telemetry_session` può valere `race` o `qualifying`: cambia il giro
usato per grafico, top speed, full throttle, freno e curve, ma non cambia passo
gara e stint. Lo stesso endpoint restituisce anche una mappa circuito derivata
dalle coordinate FastF1 dell'evento selezionato.

### 6.2 Selezione dei giri

Per ciascun pilota:

```python
driver_laps.pick_accurate().pick_wo_box().pick_quicklaps()
```

Significa:

- solo giri marcati accurati da FastF1;
- esclusione dei giri con ingresso/uscita box;
- esclusione dei giri molto lenti rispetto al ritmo del pilota.

Un pilota senza giri comparabili viene escluso dall'analisi.

### 6.3 Passo gara

Il passo mostrato è la mediana dei tempi dei giri filtrati:

```text
race_pace = mediana(giri accurati, rapidi e senza box)
```

La mediana è meno sensibile della media a traffico, bandiere e singoli giri
anomali. Rimane comunque un indicatore sintetico: non corregge per carburante,
mescola, aria sporca o fase di gara.

Il `Gap passo` nel frontend è:

```text
passo del pilota - miglior passo mediano del gruppo
```

### 6.4 Best lap e giro rappresentativo

Il best lap è il tempo minimo tra i giri filtrati.

Il giro rappresentativo usato per la telemetria dipende dal selettore:

- `race`: best lap gara accurato, rapido e senza box;
- `qualifying`: best lap qualifica accurato, rapido e senza box.

Di conseguenza:

- grafico velocità;
- top speed;
- percentuale full throttle;
- percentuale frenata;
- analisi delle curve

si riferiscono a quel singolo giro, non alla media dell'intera gara. Passo,
gap passo e stint rimangono sempre calcolati sulla sessione Race.

### 6.5 Top speed, acceleratore e freno

Sul giro telemetrico selezionato:

```text
top_speed = massimo del canale Speed
full_throttle_pct = campioni con Throttle >= 98 / campioni totali * 100
braking_pct = campioni con Brake attivo / campioni totali * 100
```

Il freno FastF1 è trattato come segnale booleano e trasformato in `0` o `100`.
Il grafico freno indica quindi **dove il freno risulta attivo**, non pressione
idraulica o intensità della frenata.

### 6.6 Classificazione delle curve

FastF1 fornisce la distanza di ciascuna curva. Sul giro telemetrico selezionato
viene presa una finestra da 80 metri prima a 80 metri dopo il punto indicato.

Nella finestra vengono calcolate:

- velocità minima;
- velocità media.

La classe dipende dalla velocità minima:

```text
lenta   < 140 km/h
media   140-209 km/h
veloce  >= 210 km/h
```

Per ogni pilota e classe il frontend mostra la media delle velocità minime
delle curve appartenenti a quella classe.

Come leggerla:

- valore più alto: il pilota ha mantenuto più velocità minima;
- valore più basso: può indicare minore percorrenza, ma anche linea diversa,
  traffico, correzione o una classificazione imperfetta.

È una proxy automatica, non una segmentazione ingegneristica curva per curva.

### 6.7 Mappa tracciato e curve

La mappa circuito viene costruita nel backend usando due sorgenti dello stesso
evento FastF1:

- coordinate `X`/`Y` del giro telemetrico selezionato;
- tabella `circuit_info.corners`, con numero, eventuale lettera, distanza e
  coordinate curva.

Questo rende il disegno coerente con anno e weekend caricati, nei limiti dei
dati FastF1 disponibili. Non viene usata un'immagine statica del circuito:
il frontend normalizza le coordinate in un `viewBox` SVG 100x100 e disegna:

- una `polyline` per il tracciato;
- un marker rosso per ogni curva;
- l'etichetta numerica della curva.

Prima del disegno il frontend ruota la nuvola di punti attorno al centro del
tracciato per portare curva 1 nella parte bassa del riquadro, quando curva 1 è
presente nei dati FastF1. È una rotazione di visualizzazione: non modifica
distanze, numeri curva o coordinate originali nel payload.

Se FastF1 non fornisce coordinate X/Y o curve per quella sessione, la UI mostra
un pannello di fallback invece di inventare un layout.

### 6.8 Analisi degli stint

I giri accurati vengono raggruppati per numero di stint. Uno stint è mostrato
solo se contiene almeno tre tempi validi.

Per ogni stint vengono calcolati:

- mescola;
- numero di giri validi;
- mediana del tempo;
- pendenza lineare dei tempi sul numero del giro.

La pendenza è una regressione lineare:

```text
trend = covarianza(numero giro, tempo) / varianza(numero giro)
```

Interpretazione:

- valore positivo: i tempi tendevano ad aumentare;
- valore negativo: i tempi tendevano a diminuire;
- valore vicino a zero: andamento mediamente stabile.

Non deve essere chiamato degrado puro. Contiene anche effetto carburante,
evoluzione pista, traffico, gestione, bandiere e meteo.

### 6.9 Implementazione del grafico telemetrico

Il grafico è costruito in `TelemetryChart.tsx` con un elemento SVG nativo.
Non usa D3, Recharts o altre librerie. L'intestazione indica se la traccia è
il best lap gara o il best lap qualifica.

#### Dati inviati al frontend

Ogni punto è una tupla del giro telemetrico scelto:

```text
[distanza, velocità, acceleratore, freno]
```

Per limitare risposta e rendering, il backend riduce ogni traccia a massimo
240 punti. Gli indici vengono distribuiti uniformemente sull'array originale,
preservando primo e ultimo punto.

Non viene effettuata interpolazione su una griglia comune. Le linee sono
confrontate sulla distanza registrata da ciascun giro.

#### Piloti e colori

All'apertura vengono selezionati i primi tre piloti con telemetria valida.
Ogni pulsante pilota:

- attiva o disattiva la linea;
- conserva un colore determinato dalla posizione nell'elenco disponibile;
- riusa ciclicamente una palette di otto colori.

#### Canali

È possibile scegliere:

- velocità;
- acceleratore;
- freno.

L'asse X è sempre la distanza del giro in chilometri.

Per acceleratore e freno l'asse Y è fisso tra 0 e 100%.
Per la velocità il massimo viene arrotondato allo scaglione di 50 km/h
successivo, con 10 km/h di margine.

#### Trasformazione in coordinate SVG

Dimensione logica:

```text
1000 x 360
```

Le coordinate vengono trasformate così:

```text
x = margine_sinistro + distanza / distanza_massima * larghezza_area
y = margine_superiore + altezza_area
    - valore / valore_massimo * altezza_area
```

I punti trasformati vengono concatenati nell'attributo `points` di una
`polyline`.

#### Gara o qualifica?

Il best lap qualifica è di solito il confronto più pulito per la prestazione
pura: poco carburante, gomma preparata e push lap. Il best lap gara è utile
per capire come la vettura si comporta in condizioni di gara, ma può essere
condizionato da carburante, traffico, gestione gomme e fase della corsa.

Per questo la UI permette di scegliere. Il report mantiene comunque nello
stesso schermo passo e stint gara, così si può confrontare prestazione pura e
ritmo reale senza confonderli.

#### Come leggere il grafico velocità

- asse X: posizione lungo il giro;
- asse Y: km/h;
- picchi: rettilinei o accelerazione;
- valli: zone di frenata e percorrenza curva;
- linea più alta nella stessa zona: maggiore velocità in quel tratto.

Il grafico da solo non stabilisce chi guadagna tempo. Una velocità minima più
alta può essere compensata da frenata anticipata, uscita peggiore o linea più
lunga.

#### Come leggere acceleratore

- 100%: pieno acceleratore;
- discese parziali: lift o modulazione;
- 0%: acceleratore chiuso.

Confrontando le linee si osserva chi apre prima o mantiene il gas in un tratto.

#### Come leggere freno

- 100%: freno rilevato come attivo;
- 0%: freno non attivo.

La larghezza del blocco mostra la durata spaziale della fase di frenata. Non
mostra la forza applicata.

#### Limiti del confronto

- ogni pilota usa il proprio giro rapido rappresentativo della modalità scelta;
- i giri possono essere avvenuti in momenti e condizioni diverse;
- non viene allineato il tempo, ma la distanza;
- il downsampling può nascondere variazioni brevissime;
- non sono mostrati delta tempo, marcia o RPM.

## 7. Prediction Center

### 7.1 Natura del risultato

Il ranking mostrato in UI non usa ancora un modello AI o machine learning
addestrato. È un modello deterministico e spiegabile basato su formule e pesi.
Il backend però produce ora anche un dataset diagnostico per valutare se e
quando introdurre un modello ML leggero.

Il valore finale è un **indice comparativo 0-100 all'interno del gruppo
analizzato**, non una probabilità di vittoria.

### 7.2 Individuazione della prossima gara

Il servizio carica in parallelo:

- calendario della stagione;
- risultati della stagione.

La prossima gara è la prima con data e ora successive all'istante corrente.
Sono analizzati solo i round precedenti.

### 7.3 Profilo tecnico del circuito

Ogni circuito conosciuto ha un vettore manuale:

```text
[curve lente, curve medie, curve veloci, rettilinei, stress gomme]
```

Ogni componente è tra `0` e `1`. Per circuiti non presenti viene usato un
profilo generico.

Questi valori sono euristiche curate nel codice, non dati misurati
automaticamente dalla telemetria.

### 7.4 Similarità tra circuiti

Si calcola la distanza euclidea tra i cinque fattori:

```text
distanza = sqrt(somma((profilo_A - profilo_B)^2))
similarità = max(0, 1 - distanza / sqrt(5))
```

Lo stesso circuito ha similarità `1`. Circuiti tecnicamente diversi hanno un
valore progressivamente più basso.

### 7.5 Fattore forma recente

Usa al massimo gli ultimi cinque round completati.

Per ogni gara:

```text
prestazione = max(0, 21 - posizione) + punti * 0.35
```

Il fattore grezzo è la media delle prestazioni recenti.

La posizione valorizza la classifica anche fuori dalla zona punti; i punti
aggiungono peso ai risultati di vertice e agli eventuali bonus.

Il modello calcola anche una **forma pulita**. Per ritiri tecnici o cause non
chiare usa il migliore tra prestazione effettivamente registrata e proxy da
griglia di partenza. Questo evita di trasformare automaticamente un ritiro
meccanico in una perdita di performance pilota.

### 7.5.1 Forza team e confronto compagno

`team_strength` misura la prestazione recente pulita del team corrente. Serve a
distinguere il momento della vettura dal solo andamento del pilota.

`teammate_delta` confronta la forma pulita del pilota con quella del compagno o
dei compagni recenti nello stesso team. È normalizzato come gli altri fattori,
quindi non è un distacco in secondi ma un indice relativo.

### 7.6 Fattore qualifica

Usa la griglia delle ultime cinque gare:

```text
qualifica = media(max(0, 21 - posizione di griglia))
```

La griglia `0`, tipicamente pit lane, viene trattata come P20.

### 7.7 Affinità con circuiti simili

Per ogni gara precedente della stagione:

```text
prestazione pulita = max(prestazione registrata, proxy da griglia se ritiro tecnico/ignoto)
peso = similarità tra circuito precedente e prossimo circuito
```

Il fattore è la media ponderata:

```text
somma(peso * prestazione) / somma(pesi)
```

Tutte le gare precedenti contribuiscono, ma quelle tecnicamente più simili
pesano di più.

### 7.8 Affidabilità tecnica del team

Gli stati Jolpica vengono classificati tramite parole chiave:

- tecnici: `Engine`, `Gearbox`, `Hydraulics`, `Brakes`, ecc.;
- incidenti: `Collision`, `Accident`, `Spun off`;
- sportivi/altri: squalifica, mancata qualifica, ritiro volontario, ecc.;
- finiti: `Finished`, classificazione numerica o giri di distacco classificati;
- ignoti: stati generici non interpretabili, come `Retired`.

Formula:

```text
affidabilità tecnica =
  (1 - guasti tecnici del team / partenze del team) * 100
```

Il valore è condiviso dai piloti che risultano nello stesso team corrente.
Un guasto a una Mercedes, per esempio, riduce il fattore Mercedes di entrambi.

I ritiri con causa ignota sono mostrati nella UI ma non assegnati
arbitrariamente a guasto o incidente. Sono possibili override documentati per
singoli risultati noti: per esempio Piastri e Norris in Cina 2026 vengono
classificati come guasti tecnici perché il non-start McLaren è stato riportato
come problema power-unit/elettrico, anche se la fonte risultati può esporre un
DNS generico. Russell in Canada 2026 è classificato come tecnico per il guasto
alla batteria dichiarato da Mercedes.

Non si assume che `Retired` significhi guasto: Jolpica può usare `Retired`
anche per incidenti noti, come i ritiri causati dal crash al via del GP di
Monaco 2024. In assenza di una causa esplicita o di un override documentato, il
ritiro resta ignoto.

### 7.9 Capacità di evitare incidenti

Formula per pilota:

```text
incident avoidance =
  (1 - incidenti del pilota / partenze del pilota) * 100
```

Una collisione influenza il pilota coinvolto, non il compagno di squadra.
Questo fattore non prova automaticamente la colpa del pilota: lo stato
ufficiale descrive l'esito, non la responsabilità.

`driver_confidence` è un fattore più ampio: conta incidenti e penalità/eventi
sportivi osservabili. In futuro potrà integrare anche incidenti o ritiri in FP
e qualifica quando disponibili da FastF1 o archivi live. Per ora non inventa
eventi non presenti nei dati.

### 7.9.1 Pacchetti upgrade

Gli upgrade tecnici sono una sorgente opzionale e manuale configurata con
`PREDICTION_UPGRADES_FILE`. Il backend non fa scraping automatico di rumor o
articoli: il file va compilato a mano da report FIA, comunicati team o note
verificate.

Schema:

```json
{
  "upgrades": [
    {
      "year": 2026,
      "round": 8,
      "team": "Ferrari",
      "magnitude": 2,
      "confidence": 0.7,
      "areas": ["floor", "front_wing"],
      "source": "FIA show-and-tell / team notes",
      "note": "Descrizione sintetica del pacchetto"
    }
  ]
}
```

`magnitude` va da `1` a `3`; `confidence` va da `0` a `1`. Il segnale grezzo è:

```text
upgrade_signal = clamp((magnitude / 3) * 100 * confidence)
```

Quando almeno un team ha un pacchetto dichiarato per il round target, la
feature entra nel ranking pre-weekend con peso 6%. Gli altri pesi vengono
ridotti proporzionalmente. Dopo FP2/FP3 il modello mostra una validazione
separata basata sul punteggio practice medio del team aggiornato: questo non
prova causalità, ma aiuta a capire se il pacchetto dichiarato è coerente con
il ritmo osservato.

### 7.10 Affinità con la temperatura

Se la gara è nell'orizzonte Open-Meteo:

1. si calcola la media tra minima e massima previste;
2. si recupera la stessa media per ogni GP precedente;
3. si assegna un peso termico a ogni gara:

```text
peso = max(0.05, 1 - abs(temperatura_storica - prevista) / 20)
```

La prestazione usata è la stessa dell'affinità circuito:

```text
max(0, 21 - posizione) + punti * 0.25
```

Il fattore finale è una media ponderata. Il peso minimo `0.05` evita di
eliminare completamente gare con clima molto diverso.

La temperatura è quella ambientale giornaliera, non la temperatura pista
della sessione.

### 7.11 Normalizzazione

Forma, forma pulita, forza team, circuiti simili, qualifica, confronto col
compagno, upgrade e resa con temperatura simile hanno scale grezze diverse.
Prima del punteggio vengono convertiti con min-max:

```text
normalizzato =
  (valore - minimo del gruppo) / (massimo - minimo) * 100
```

Se tutti hanno lo stesso valore, tutti ricevono `50`.

Importante: affidabilità tecnica, incident avoidance e driver confidence non vengono più
normalizzati con min-max. Entrano nel punteggio come percentuali reali, così un
singolo guasto a inizio stagione non viene amplificato artificialmente in una
differenza 0-100.

### 7.12 Pesi pre-weekend

Con temperatura disponibile:

```text
18% forma recente
18% forma pulita
16% forza team
20% circuiti simili
10% qualifica
 6% confronto compagno
 5% affidabilità tecnica
 3% fiducia pilota
 4% temperatura
```

Senza temperatura:

```text
18% forma recente
18% forma pulita
16% forza team
23% circuiti simili
12% qualifica
 5% confronto compagno
 4% affidabilità tecnica
 4% fiducia pilota
```

Il peso meteo viene quindi redistribuito soprattutto tra affinità circuito,
qualifica e fattori di stabilità.

Se esistono upgrade dichiarati per la gara target, `upgrade_signal` entra con
peso 6% e tutti gli altri pesi vengono scalati al 94% del loro valore. Se non
ci sono upgrade, la feature non viene usata e non altera il ranking.

### 7.13 Free practice

L'aggiornamento viene tentato solo da tre giorni prima della gara e usa FP2 e
FP3 disponibili.

Per ogni pilota:

- vengono scelti giri accurati, rapidi e senza box;
- `qualifying_gap` è il distacco del miglior giro dal migliore assoluto;
- i long run includono giri entro il 112% del miglior giro personale;
- un long run richiede almeno quattro giri;
- `long_run_gap` confronta la migliore mediana del pilota con la migliore
  mediana complessiva;
- `laps` è il numero totale di giri rapidi validi.

Gap più piccoli sono migliori. Per questo vengono negati prima della
normalizzazione.

Punteggio prove:

```text
48% prestazione giro secco
42% long run
10% quantità di giri, saturata a 30 giri
```

Punteggio aggiornato:

```text
55% baseline + 45% free practice
```

Un pilota senza dati comparabili mantiene il punteggio baseline e riceve
`practice: null`. Questa è una semplificazione da considerare quando FP2/FP3
sono incomplete o interrotte.

### 7.14 Dataset feature e readiness ML

`GET /api/predictions/features` costruisce un dataset supervisionato dalla
stagione selezionata. Per ogni gara completata dopo almeno `min_prior_races`,
calcola la baseline usando **solo le gare precedenti** e poi collega quelle
feature al risultato reale della gara target.

Ogni riga contiene:

- contesto: anno, round, gara, circuito, pilota, team;
- feature: `score`, `recent_form`, `clean_recent_form`, `team_strength`,
  `track_affinity`, `qualifying`, `teammate_delta`,
  `technical_reliability`, `incident_avoidance`, `driver_confidence`,
  `temperature_match`, `upgrade_signal`;
- target: posizione finale, punti, winner, podium, top6, finished.

Questo evita leakage: il modello non vede dati della gara che sta provando a
predire. Il report include anche diagnostica feature con lift medio dei podi
rispetto ai non podi. Non è causalità, ma aiuta a capire quali segnali stanno
separando meglio i risultati.

`ml_readiness` non addestra ancora un modello: valuta se il campione è
sufficiente per tentare un ranker leggero. Con poche gare conviene continuare
con un modello spiegabile e backtest; con più esempi, FP, qualifica e archivio
live si potrà aggiungere un modello regolarizzato.

### 7.15 Confidenza

La confidenza è un indicatore euristico, non una calibrazione statistica:

```text
base = min(85, 40 + gare completate * 4)
post prove = min(92, base + 12)
pioggia prevista >= 50% = max(25, confidenza - 10)
```

Più gare aumentano il campione; le prove aggiungono informazioni recenti; alta
probabilità di pioggia riduce la stabilità attesa del ranking.

### 7.16 Lettura del frontend predizioni

#### Competitive Index

La barra rappresenta direttamente il punteggio finale del pilota su scala
0-100. La freccia confronta la posizione aggiornata con quella baseline:

- freccia in su: guadagno di posizioni dopo le prove;
- freccia in giù: perdita di posizioni;
- trattino: posizione invariata o nessun aggiornamento.

#### Top 3 fattore per fattore

Le barre di forma, circuiti simili, qualifica e resa con temperatura simile
sono valori normalizzati rispetto agli altri piloti.

Le barre di affidabilità e incidenti mostrano percentuali reali, accompagnate
dai conteggi:

```text
guasti tecnici / partenze team
incidenti / partenze pilota
```

La voce temperatura è intenzionalmente chiamata "resa temp. simile": `100`
significa miglior rendimento relativo tra i piloti nelle gare con temperatura
simile alla previsione. Non è una temperatura in gradi e non è una probabilità.

#### DNA del circuito

Mostra il profilo manuale moltiplicato per 100. Non è una percentuale di curve:
è un indice relativo di presenza o importanza della caratteristica.

#### Meteo

Mostra previsione giornaliera Open-Meteo, non condizioni esatte all'orario
della gara.

#### Pesi del modello

In fase baseline elenca i fattori storici. Dopo le prove mostra invece:

```text
baseline 55%
free practice 45%
```

## 8. Live e snapshot

### 8.1 F1 SignalR esposto nella UI

Gli endpoint live sono:

- `GET /api/f1signal/status`
- `GET /api/f1signal/snapshot`
- `GET /api/f1signal/stream`

`LiveView` usa `EventSource` su `/api/f1signal/stream`. Ogni evento `snapshot`
contiene stato connessione, sessione, piloti, posizioni, distacchi, meteo,
messaggi race control, stato pista, conteggio giri e coordinate auto quando
F1 invia `Position.z`.

La UI mostra:

- classifica e gap;
- stato connessione/sessione;
- meteo e best lap;
- lista completa dei messaggi FIA, scrollabile;
- toggle `IT` con traduzione locale dei messaggi più comuni;
- lista team radio testuale con bottone play quando il payload contiene un URL o
  path;
- pannello GPS auto quando sono presenti coordinate.

La trascrizione delle team radio è automatica in background per le clip nuove e
deduplicate. Con `TEAM_RADIO_TRANSCRIPTION_PROVIDER=local` il backend usa
`faster-whisper` sulla macchina locale e non invia l'audio a servizi esterni.
Il modello è configurato da `TEAM_RADIO_LOCAL_WHISPER_MODEL`,
`TEAM_RADIO_LOCAL_WHISPER_DEVICE` e `TEAM_RADIO_LOCAL_WHISPER_COMPUTE_TYPE`.
`TEAM_RADIO_AUTO_TRANSCRIPTION_ENABLED` abilita la coda automatica e
`TEAM_RADIO_AUTO_TRANSCRIPTION_CONCURRENCY` limita quante clip vengono
trascritte in parallelo. La traduzione in italiano è separata e può essere
richiesta dal tasto `IT` accanto al play audio. Con
`TEAM_RADIO_TRANSLATION_PROVIDER=googletrans` usa la libreria `googletrans`;
con `TEAM_RADIO_TRANSLATION_PROVIDER=openai` e `OPENAI_API_KEY` valorizzata usa
OpenAI; con `TEAM_RADIO_TRANSLATION_PROVIDER=none` viene salvato solo il
transcript originale. `googletrans` è gratuito ma si appoggia a un servizio
Google non ufficiale, quindi può rompersi o rate-limitare.
`TEAM_RADIO_AUTO_TRANSLATE_ENABLED=false` mantiene la traduzione manuale dal
tasto `IT`; impostandolo a `true`, la traduzione parte automaticamente dopo lo
speech-to-text.

La cache delle trascrizioni è abilitata da
`TEAM_RADIO_TRANSCRIPTION_CACHE_ENABLED`. Per ogni sessione viene scritto:

```text
backend/.cache/f1signal/<data>_<meeting>_<sessione>/team_radio_transcriptions.json
```

La chiave primaria è il `path` della clip MP3, con fallback sull'URL. Al refresh
della pagina, lo snapshot live idrata le team radio dalla cache prima di
schedulare nuove trascrizioni. La cache non viene cancellata automaticamente al
cambio GP o al passaggio FP1/FP2/Qualifica/Gara: cambia la cartella sessione e
il dato resta disponibile come storico.

### 8.2 Archivio live per prediction

Gli snapshot F1 SignalR vengono salvati sotto:

```text
backend/.cache/f1signal/<data>_<meeting>_<sessione>/snapshots.jsonl
```

Ogni riga contiene:

- `recorded_at`: timestamp UTC di archiviazione;
- `snapshot`: stato normalizzato usato anche dalla UI.

Il dataset include posizioni, gap, meteo, track status, lap count, race control,
team radio normalizzate, telemetria compatta e coordinate pista disponibili.
Per ora non viene salvato ogni payload grezzo ad alta frequenza, perché
`CarData.z` e `Position.z` possono crescere molto velocemente durante una
sessione. Se servirà per modelli più granulari, si potrà aggiungere un archivio
separato per topic raw con whitelist.

Il topic `TeamRadio` tende a fornire clip audio, non trascrizioni. Quando il
payload contiene un path relativo come `TeamRadio/LIN_41_20260614_164234.mp3`,
il backend ricostruisce l'URL assoluto usando la cartella statica della sessione
derivata da `SessionInfo`, nello stesso schema usato dal live timing storico:

```text
https://livetiming.formula1.com/static/{anno}/{data_evento}_{meeting}/
{data_sessione}_{sessione}/TeamRadio/...
```

La UI mostra solo clip con URL risolto; eventuali metadata non riproducibili
restano nello snapshot ma non vengono presentati come player.

#### Strategia layout pista live

Per le analisi post-gara e l'archivio layout viene preferito FastF1, perché può
fornire una traccia coerente con la sessione e i metadati curva. Per la vista
Live, però, una pista nuova o non ancora presente nei dataset FastF1 può non
avere un layout disponibile. Per questo l'adapter SignalR mantiene in memoria
una traccia progressiva da `Position.z`.

Il backend:

1. decodifica ogni payload `Position.z`;
2. salva per pilota una coda limitata di coordinate X/Y;
3. elimina duplicati consecutivi;
4. sceglie il pilota con più punti come traccia principale;
5. riduce la traccia a un massimo di punti gestibile per il frontend;
6. espone `track_map` nello snapshot live.

Questo approccio permette di far comparire la forma della pista man mano che le
auto girano, anche su circuiti nuovi come Madrid. I limiti sono fisiologici:
nei primi minuti la traccia è incompleta, pit lane/outlier possono sporcarla e
non sono disponibili curva 1, numeri curva o settori finché non esiste una
fonte layout più ricca.

La traduzione non chiama servizi esterni: è una sostituzione locale di frasi
ricorrenti nei messaggi race control. Se un messaggio non corrisponde a una
regola, resta parzialmente o totalmente in inglese.

### 8.2 Snapshot OpenF1 legacy

Gli endpoint OpenF1 ancora disponibili sono:

- `GET /api/meetings?year=...`
- `GET /api/sessions?meeting_key=...`
- `GET /api/snapshot?session_key=...&at=...`

Lo snapshot:

1. carica sessione, piloti, risultati e giri;
2. determina un cursore temporale;
3. usa una finestra di 5 minuti per posizione, intervalli e meteo;
4. usa una finestra di 12 secondi per coordinate e dati vettura;
5. conserva il campione più recente per pilota.

Per sessioni storiche senza parametro `at`, il cursore viene portato alla fine
effettiva ricostruibile della sessione.

Lo snapshot OpenF1 resta utile per replay/storico, ma la sezione Live usa
SignalR direttamente.

## 9. Cache e rate limiting

### Cache HTTP in memoria

`AsyncTTLCache` associa una chiave URL-parametri a:

- valore;
- tempo di scadenza monotono.

Un lock per chiave impedisce che richieste simultanee identiche lancino più
download della stessa risorsa.

La cache vive nel processo: viene persa al riavvio del backend.

TTL principali:

- circuiti Jolpica: 24 ore;
- risultati circuito: 6 ore;
- calendario e risultati stagione: 1 ora;
- previsione meteo: 30 minuti;
- temperature storiche: 30 giorni;
- dati OpenF1 storici: tipicamente 6 ore;
- snapshot OpenF1: 10-300 secondi in base al dato.

### Cache FastF1

È persistente su disco e gestita dalla libreria FastF1. La directory può
essere modificata con `FASTF1_CACHE_DIR`.

### Rate limiter OpenF1

Usa una sliding window con timestamp delle richieste degli ultimi 60 secondi.
Prima di ogni chiamata controlla:

- quante richieste ricadono nell'ultimo secondo;
- quante ricadono nell'ultimo minuto.

Se un limite è raggiunto, attende fino alla scadenza della finestra più
restrittiva. Lo stato è globale per l'istanza backend.

## 10. Configurazione

Variabili supportate:

```text
OPENF1_BASE_URL
JOLPICA_BASE_URL
CACHE_TTL_SECONDS
OPENF1_REQUESTS_PER_SECOND
OPENF1_REQUESTS_PER_MINUTE
ENABLE_OPENF1_HISTORY
FASTF1_CACHE_DIR
OPEN_METEO_BASE_URL
OPEN_METEO_ARCHIVE_URL
```

Il CORS backend consente in sviluppo `http://localhost:5173` e solo metodi
GET.

## 11. Contratti API attivi

### `GET /api/health`

Controllo minimale del processo FastAPI.
La stessa risposta è disponibile su `GET /health` per gli health check interni
dei container.

### `GET /api/seasons`

Restituisce le stagioni dalla corrente al 2023. La UI post-gara genera invece
localmente le stagioni dal 2018.

### `GET /api/circuits`

Elenco sintetico dei circuiti.

### `GET /api/circuits/{circuit_id}/history`

Archivio aggregato, record, classifiche, edizioni e blocco OpenF1 opzionale.

### `GET /api/circuits/{circuit_id}/layout`

Layout Race FastF1 per una specifica edizione del circuito. Richiede
`year=...`, usa Jolpica per risolvere il round e restituisce evento e
`circuit_map`.

### `GET /api/analysis/events`

Calendario della stagione con flag `completed`.

### `GET /api/analysis/post-race`

Analisi FastF1 completa della gara selezionata. Accetta
`telemetry_session=race` o `telemetry_session=qualifying`.

### `GET /api/predictions/next-race`

Prossima gara, meteo, profilo circuito, ranking e possibile aggiornamento
FP2/FP3.

### `GET /api/predictions/features`

Dataset diagnostico per prediction e ML readiness. Parametri:
`year`, `min_prior_races`, `include_rows`, `limit`.

## 12. Test automatici

I test backend verificano:

- normalizzazione di nomi con accenti;
- parsing dei tempi sul giro;
- aggregazione storica;
- rimonta vincente con risultati non ordinati;
- riduzione delle tracce a massimo N punti;
- conservazione degli estremi della telemetria;
- similarità dei circuiti;
- normalizzazione con valori uguali;
- effetto di forma e circuiti simili;
- inclusione della temperatura;
- capacità delle prove di modificare il ranking;
- distinzione tra guasto, incidente, sanzione e causa ignota;
- affidabilità condivisa dal team;
- incidenti attribuiti al singolo pilota;
- override documentato per ritiri ambigui;
- parsing temporale e selezione dell'ultimo dato OpenF1 per pilota.

Comandi:

```bash
cd backend
.venv/bin/pytest -q

cd ../frontend
npm run lint
npm run build
```

La build frontend esegue prima il controllo TypeScript senza emissione e poi
la build Vite.

## 13. Limiti noti

- Il record storico dipende dalla completezza Jolpica.
- L'affidabilità dell'archivio significa classificati/partenti, non guasti.
- I profili circuito delle predizioni sono manuali.
- Il ranking usa solo la stagione corrente, non più stagioni.
- Le percentuali di affidabilità team possono essere poco stabili a inizio
  stagione.
- Gli stati `Retired` generici non consentono una classificazione certa.
- Un incidente non implica responsabilità del pilota.
- La temperatura storica è giornaliera e ambientale.
- Il meteo previsto è giornaliero.
- Il passo gara non corregge carburante, mescola o traffico.
- La telemetria confronta giri diversi e non sincronizzati temporalmente.
- Il freno è un segnale acceso/spento.
- Il trend stint non isola il degrado gomma.
- Il modello non produce probabilità calibrate.
- Strategie, aggiornamenti tecnici e penalità future non sono osservabili.
- Il live SignalR è sperimentale e dipende da token/sessione F1TV validi.
- `Position.z` e `CarData.z` possono non arrivare fuori dalle finestre live o
  su sessioni concluse.
- La traduzione italiana dei messaggi FIA è locale e non garantisce copertura
  completa di tutte le formulazioni.

## 14. Punti di estensione

Le evoluzioni tecnicamente più naturali sono:

- aggiungere delta tempo al grafico telemetrico;
- interpolare le tracce su distanze comuni;
- mostrare marcia, RPM e DRS;
- confrontare giri scelti manualmente invece del solo giro più rapido;
- separare passo per mescola e fase di gara;
- stimare degrado con correzione del carburante;
- derivare automaticamente i profili circuito dalla telemetria;
- conservare più stagioni nel modello predittivo con decadimento temporale;
- aggiungere probabilità calibrate solo dopo aver costruito un dataset di
  backtest sufficientemente ampio;
- persistere snapshot SignalR per replay locali;
- allineare le coordinate `Position.z` a un layout circuito FastF1 quando
  disponibile;
- ampliare il dizionario di traduzione dei messaggi FIA.
