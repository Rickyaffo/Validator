VALIDATR™ v2 - Piattaforma di Analisi per Startup
📝 Descrizione del Progetto
VALIDATR™ v2 è un'evoluzione della piattaforma MVP, progettata per fornire analisi di livello professionale per investitori di startup. Il sistema trasforma i pitch deck e i business plan in un "Investment Memorandum" interattivo, una singola pagina web dinamica che permette di esplorare in profondità tutti gli aspetti di una startup.

Questa nuova versione è costruita su un'architettura serverless e scalabile su Google Cloud Platform (GCP), sfruttando l'intelligenza artificiale di Gemini per generare analisi qualitative e quantitative.

🚀 Architettura e Stack Tecnologico
La piattaforma utilizza un'architettura moderna e serverless per ottimizzare costi e scalabilità.

Frontend:

Framework: HTML5, Tailwind CSS, Vanilla JavaScript

Librerie Grafiche: Chart.js, Plotly.js

Hosting: Google App Engine (Standard Environment)

Backend (API):

Servizio: Google Cloud Functions (2nd Gen)

Linguaggio: Python 3.11

Database:

Servizio: Google Cloud Firestore (NoSQL)

Intelligenza Artificiale:

Modello: Google Gemini (tramite Vertex AI)

Storage:

Servizio: Google Cloud Storage

Autenticazione:

Servizio: Firebase Authentication

🔧 Setup e Installazione Locale
Per contribuire al progetto, segui questi passaggi.

Prerequisiti
Git

Google Cloud SDK

Guida all'Installazione
Clona il repository:

git clone https://github.com/Rickyaffo/Validator.git
cd Validator

Crea un branch per le tue modifiche:

git checkout -b feature/NomeNuovaFunzionalita

Configura la gcloud CLI:
Assicurati di essere autenticato e di aver impostato il progetto GCP corretto.

gcloud auth login
gcloud config set project NOME-DEL-TUO-PROGETTO

☁️ Deploy su Google Cloud Platform
Il deploy è suddiviso in due parti: il frontend su App Engine e il backend su Cloud Functions.

Struttura delle Cartelle
Assicurati che il progetto sia organizzato come segue prima del deploy:

Validator/
├── frontend/
│   ├── index.html
│   └── memorandum.html
├── functions/
│   ├── process-pitch-deck/
│   │   ├── main.py
│   │   └── requirements.txt
│   └── fetch-pitch-data/
│       ├── main.py
│       └── requirements.txt
└── app.yaml

Comandi di Deploy
Esegui questi comandi dalla directory principale del progetto.

Deploy del Frontend su App Engine:

gcloud app deploy app.yaml --quiet

Deploy delle Cloud Functions:

Funzione di Analisi (process-pitch-deck):
Questa funzione (2ª gen) riceve i documenti, li analizza con Gemini e salva i risultati su Firestore. Richiede più memoria a causa delle librerie AI.

gcloud functions deploy process-pitch-deck \
  --gen2 \
  --source=./functions/start_analysis \
  --trigger-http \
  --runtime=python311 \
  --entry-point=start_analysis \
  --region=europe-west1 \
  --memory=512MiB \
  --allow-unauthenticated

Funzione di Lettura Dati (fetchPitchData):
Questa funzione (2ª gen) recupera i dati delle analisi da Firestore per mostrarli nel frontend.

gcloud functions deploy fetchPitchData \
  --gen2 \
  --source=./functions/fetch-pitch-data \
  --trigger-http \
  --runtime=python311 \
  --entry-point=fetchPitchData \
  --region=europe-west1 \
  --allow-unauthenticated

🤖 Automazione (CI/CD) con GitHub Actions
Per automatizzare il processo di deploy, è possibile configurare un workflow di GitHub Actions. Crea un file in .github/workflows/deploy-gcp.yml per eseguire automaticamente i comandi di deploy a ogni push su un branch specifico (es. main o v2-architecture).