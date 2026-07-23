# Architettura applicativa

## Distribuzione

```text
Repository applicativo
  -> test e build
  -> immagini backend e frontend con tag SHA immutabile
  -> ambiente container di produzione
```

Il repository applicativo è la fonte autorevole del codice. L'ambiente di
produzione usa le immagini generate dalla CI e una configurazione operativa
separata; non richiede un clone dei sorgenti backend o frontend.

## Runtime

```text
Browser
  -> frontend:8080 (Nginx non-root, SPA)
       -> /api/*
            -> api:8000 (FastAPI non-root)
                 -> /app/.cache
```

Solo il frontend pubblica una porta host. Il backend è raggiungibile mediante
la rete Docker dedicata e Nginx usa il nome servizio `api`. Il browser non
contiene IP interni e usa URL relativi `/api`.

Il backend espone `GET /health` per container e controlli interni e mantiene
`GET /api/health` per il proxy e la compatibilità applicativa. Il frontend
espone `GET /health` direttamente da Nginx.

## Immagini e persistenza

- backend: builder Python 3.12, lock runtime, runtime Debian slim, UID/GID
  `10001`, FFmpeg e health check;
- frontend: build Node 22.14 con `npm ci`, runtime Nginx non privilegiato sulla
  porta 8080;
- immagini: `${API_IMAGE}:${IMAGE_TAG}` e
  `${FRONTEND_IMAGE}:${IMAGE_TAG}`, con SHA Git completo e immutabile;
- cache produzione: `${DATA_PATH}/cache` montata in `/app/.cache`.

Non sono richiesti database o Redis. Nessun manifest o script rimuove volumi o
dati.
