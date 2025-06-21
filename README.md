VALIDATR™ Project Overview
Questo README riassume l'architettura, le funzionalità chiave e i passaggi di configurazione del progetto VALIDATR™, una piattaforma per l'analisi automatizzata dei pitch deck delle startup.

1. Obiettivo del Progetto
L'obiettivo di VALIDATR™ è fornire un sistema automatizzato per analizzare i pitch deck in formato PDF, estrarre metriche chiave, valutarne la coerenza e generare un ranking. Il sistema è progettato per essere scalabile, sicuro e intuitivo, rivolto sia ai founder che agli investitori.

2. Architettura Tecnologica
Il progetto si basa su un'architettura cloud-native e serverless, sfruttando principalmente Google Cloud Platform (GCP) e le API di OpenAI.



www.youtube.com
Componenti Chiave:

Google Cloud Storage (GCS): Utilizzato per l'ingestione dei file PDF (bucket di input) e per l'archiviazione dei risultati JSON dell'analisi (bucket di output).

Google Cloud Functions:

process_pitch_deck: Funzione Python triggerata dal caricamento di un PDF in GCS, responsabile dell'estrazione del testo, dell'analisi AI e del salvataggio dei risultati.

fetchPitchData: Funzione Python HTTP triggerata dal frontend, responsabile dell'autenticazione, del recupero dati da Firestore e della restituzione al frontend.

OpenAI API (GPT-4.1 Nano): Modello di intelligenza artificiale generativa utilizzato per l'analisi testuale del pitch deck, la valutazione delle variabili e la stima della coerenza.

Firebase Authentication: Gestione degli utenti per l'accesso alla dashboard (Email/Password).

Cloud Firestore: Database NoSQL utilizzato per archiviare i risultati strutturati dell'analisi dei pitch deck, con percorsi differenziati per dati pubblici e dati utente-specifici.

Firebase Hosting: Per ospitare l'applicazione frontend (dashboard HTML).

3. Funzionalità e Flusso di Lavoro
3.1. Ingestione e Analisi del Pitch Deck
Caricamento PDF:

Un file PDF (pitch deck) viene caricato nel bucket GCS di input (validatr-pitch-decks-input).

Il caricamento può avvenire tramite Zapier/Typeform (dove l'email dell'utente finale può essere inclusa come metadato user_email) o manualmente da un amministratore (che include il metadato upload_source: manual_admin).

Trigger Cloud Function process_pitch_deck:

Il caricamento del PDF attiva automaticamente la Cloud Function process_pitch_deck.

Estrazione Testo: La funzione utilizza PyPDF2 per estrarre il testo completo dal PDF.

Analisi AI (OpenAI GPT):

Il testo estratto viene inviato all'API di OpenAI (modello gpt-4.1-nano).

GPT valuta il pitch deck in base a 7 variabili chiave (Problema, Target, Soluzione, Mercato, MVP, Team, Ritorno Atteso), assegnando un punteggio da 0 a 100 e una motivazione dettagliata per ciascuna.

Viene valutata anche la coerenza interna tra 21 coppie specifiche di variabili, con un punteggio di coerenza e una motivazione.

L'output di GPT è un JSON strutturato.

Calcoli Aggiuntivi:

La Cloud Function elabora l'output di GPT per calcolare:

Indice di Coerenza (IC): Media dei punteggi delle 21 coppie di coerenza.

Final Score: Media ponderata dei punteggi delle 7 variabili chiave.

Final Adjusted Score: Media ponderata del Final Score (peso 0.7) e dell'Indice di Coerenza (peso 0.3).

Classe di Valutazione: Assegnazione di una categoria (Rosso, Giallo, Verde, Immunizzato, Zero) in base a soglie predefinite del Final Adjusted Score.

Associazione Utente e Salvataggio Dati:

La funzione tenta di associare l'analisi a un utente Firebase specifico:

Cerca il metadato GCS user_email. Se trovato e corrispondente a un utente Firebase, il pitch è associato a quell'utente.

Se user_email non è presente o non valido, cerca il metadato GCS upload_source. Se è 'manual_admin', il pitch viene associato all'email dell'amministratore specificata nella funzione (ADMIN_EMAIL_FOR_MANUAL_UPLOADS).

Se nessun utente è identificato, l'analisi viene considerata "pubblica".

I risultati JSON completi (inclusi i calcoli aggiuntivi) vengono salvati in Cloud Firestore:

Dati Privati dell'Utente: artifacts/{appId}/users/{userId}/pitch_deck_analyses/{documentId} (per i pitch caricati dall'utente o dall'admin).

Dati Pubblici: artifacts/{appId}/public/data/pitch_deck_analyses/{documentId} (per pitch non associati a un utente specifico).

Una copia del JSON dell'analisi viene salvata anche nel bucket GCS di output (validatr-pitch-decks-output).

3.2. Dashboard Frontend (Visualizzazione Dati)
Autenticazione Utente: Gli utenti accedono alla dashboard tramite Firebase Authentication (Email/Password).

Selezione Filtro: L'utente può scegliere di visualizzare "Tutti i Pitch" o "I Miei Pitch" tramite radio button.

Chiamata Cloud Function fetchPitchData:

Quando l'utente è autenticato e seleziona un filtro, la dashboard frontend chiama la Cloud Function fetchPitchData tramite HTTP.

La richiesta include il token di autenticazione Firebase dell'utente nell'header Authorization e il tipo di filtro (filter=all o filter=my) come parametro di query.

Recupero Dati da Firestore:

La Cloud Function fetchPitchData verifica il token di autenticazione Firebase.

In base al filtro richiesto (all o my) e all'UID dell'utente autenticato, recupera i documenti di analisi pitch deck dalla collezione Firestore appropriata (pubblica o privata dell'utente).

Restituisce i dati in formato JSON al frontend.

Visualizzazione Grafica:

La dashboard frontend (HTML/JavaScript) riceve i dati JSON.

Utilizza Chart.js per visualizzare un grafico a barre orizzontali che mostra i pitch deck classificati in base al loro Final Adjusted Score, con colori diversi per indicare la performance (Verde, Giallo, Rosso).

4. Passaggi di Configurazione e Deployment
Per far funzionare il progetto, sono necessari i seguenti passaggi:

4.1. Setup Progetto Firebase/GCP
Crea un Progetto Firebase: Se non l'hai già fatto, crea un nuovo progetto su Firebase Console.

Registra un'App Web: Nella sezione "Project settings" -> "Your apps" di Firebase Console, registra una nuova app web per ottenere l'oggetto firebaseConfig.

Abilita Firebase Authentication: Nella sezione "Authentication" di Firebase Console -> "Sign-in method", abilita il provider "Email/Password". Crea almeno un utente di test e un utente "admin" con cui effettuare i caricamenti manuali e testare la dashboard.

Crea Buckets Cloud Storage:

validatr-pitch-decks-input: Per i PDF in ingresso (trigger della funzione process_pitch_deck).

validatr-pitch-decks-output: Per i risultati JSON dell'analisi.

Configura Cloud Firestore: Nella sezione "Firestore Database" di Firebase Console, crea un nuovo database in Modalità Nativa nella regione europe-west1.

Configura Variabile d'Ambiente OpenAI API Key: Nel deployment della Cloud Function process_pitch_deck, aggiungi la variabile d'ambiente OPENAI_API_KEY con la tua chiave API di OpenAI.

4.2. Deployment delle Cloud Functions
Cloud Function process_pitch_deck:

Carica il codice Python di pitch-deck-analyzer-code (il file main.py e requirements.txt).

Importante: Modifica la riga ADMIN_EMAIL_FOR_MANUAL_UPLOADS = "admin@validatr.com" con l'email del tuo utente admin Firebase.

Trigger: Cloud Storage, su evento Finalize/Create per il bucket validatr-pitch-decks-input.

Runtime: Python 3.9 o superiore.

Entrypoint: process_pitch_deck.

Permessi: Il service account della funzione necessita di: Storage Object Viewer (per leggere PDF), Storage Object Creator (per scrivere JSON di output), Cloud Datastore User (per scrivere su Firestore) e Firebase Authentication Viewer (per auth.get_user_by_email).

Cloud Function fetchPitchData:

Carica il codice Python di fetch-pitch-data-cloud-function (il file main.py e requirements.txt).

Trigger: HTTP.

Authentication: "Require authentication" (fondamentale per la sicurezza).

Runtime: Python 3.9 o superiore.

Entrypoint: fetchPitchData.

CORS: Assicurati che gli header CORS nella funzione siano configurati per permettere al tuo dominio frontend di accedere (es. Access-Control-Allow-Origin: 'https://tuo-dominio.web.app').

Permessi: Il service account della funzione necessita di: Cloud Datastore User (per leggere da Firestore) e Firebase Authentication Viewer (per auth.verify_id_token).

4.3. Deployment della Dashboard Frontend
Aggiorna investor-ranking-dashboard.html:

Popola l'oggetto firebaseConfig con i valori reali della tua app web Firebase.

Sostituisci YOUR_API_ENDPOINT_HERE con l'URL HTTP della tua Cloud Function fetchPitchData (lo trovi nella sezione "Trigger" della funzione in GCP Console).

Firebase Hosting:

Assicurati di aver inizializzato Firebase Hosting nel tuo progetto locale (firebase init hosting).

Esegui il deployment del tuo file HTML e delle sue dipendenze con firebase deploy --only hosting.

4.4. Regole di Sicurezza Firestore
Applica le seguenti regole di sicurezza nel tuo Firestore Database per controllare l'accesso ai dati:

rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /artifacts/{appId} {
      // Regole per i dati pubblici
      match /public/data/{collectionName}/{document=**} {
        allow read: if request.auth != null; // Solo utenti autenticati possono leggere
        // La scrittura è permessa solo dalla Cloud Function (Admin SDK)
      }

      // Regole per i dati utente-specifici
      match /users/{userId}/{collectionName}/{document=**} {
        // L'utente può leggere/scrivere solo i propri dati
        allow read, write: if request.auth != null && request.auth.uid == userId;
      }
    }
  }
}

5. Test e Debugging
Controlla i log di Cloud Functions: Usa Cloud Logging in GCP Console per monitorare l'esecuzione di entrambe le funzioni e diagnosticare errori.

Console del Browser: Apri la console degli sviluppatori (F12) nel tuo browser quando usi la dashboard per verificare errori JavaScript o problemi di rete (specialmente CORS).

Test Metadati GCS: Assicurati che i metadati user_email (da Zapier) o upload_source (per admin manuale) vengano effettivamente allegati al file PDF quando lo carichi in GCS.

Seguendo questi passaggi, avrai un sistema completo e funzionante per l'analisi e la visualizzazione dei pitch deck.


La tua Cloud Function ha una logica per associare i caricamenti a admin@validatr.com se viene rilevato il metadato upload_source: manual_admin.

oppure user_email : riccardo.affolter...