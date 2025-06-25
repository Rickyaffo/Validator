# main.py della tua Cloud Function 'process-pitch-deck' (trigger Cloud Storage)

import functions_framework
import json
import io
import PyPDF2
import openai
import os
from google.cloud import storage
from google.api_core.exceptions import NotFound # Importa l'eccezione specifica per "Not Found"
from google.cloud import bigquery # Importa il client BigQuery

# --- Inizializzazione Firebase e Firestore ---
# Per l'ambiente Canvas, le variabili __app_id e __firebase_config sono globali.
# In un ambiente standard GCP, dovresti caricare la tua service account key in modo sicuro.
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin import auth # Nuovo import per la gestione utenti Firebase

# Inizializzazione Firebase solo se non è già stata inizializzata
if not firebase_admin._apps:
    try:
        # Usa la configurazione Firebase fornita dall'ambiente Canvas (se disponibile)
        firebase_config_json = os.environ.get('FIREBASE_CONFIG_JSON', None)
        if firebase_config_json:
            cred = credentials.Certificate(json.loads(firebase_config_json))
        else:
            # Fallback per un ambiente senza configurazione esplicita (es. locale per test)
            # In ambiente Cloud Functions, ApplicationDefault() dovrebbe funzionare automaticamente
            cred = credentials.ApplicationDefault()

        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK inizializzato con successo.")
    except Exception as e:
        print(f"Errore nell'inizializzazione di Firebase Admin SDK: {e}")
        # Non bloccare l'esecuzione della funzione, ma logga l'errore grave

db = firestore.client() # Inizializza il client Firestore
bq_client = bigquery.Client() # Inizializza il client BigQuery

# Recupera l'ID dell'app dall'ambiente Canvas o usa un default (il tuo project ID)
APP_ID = os.environ.get('CANVAS_APP_ID', 'validatr-mvp')

# --- Inizializzazione OpenAI ---
# Assicurati che OPENAI_API_KEY sia impostata come variabile d'ambiente nella Cloud Function
openai.api_key = os.environ.get("OPENAI_API_KEY")

# --- Definizione delle Variabili e Rubriche per l'Analisi ---
# Queste rubriche saranno incorporate direttamente nel prompt per GPT.
# Essere il più specifici possibile è cruciale per ottenere risultati accurati.
RUBRICS = {
    "Problema": {
        "descrizione": "La ragione per cui esisti.",
        "criteri": "Misura quanto il problema che la startup intende risolvere sia reale, urgente e rilevante per gli stakeholder. Variabili valutate: concretezza, urgenza percepita, intensità del bisogno nel mercato, verifica empirica attraverso feedback degli utenti target."
    },
    "Target": {
        "descrizione": "Chi ha il problema e chi paga per risolverlo.",
        "criteri": "Determina il grado di definizione, raggiungibilità e predisposizione alla spesa degli utenti destinatari della soluzione. Variabili valutate: precisione segmentale, capacità economica, willingness-to-pay, dimensione quantitativa e qualitativa del pubblico target."
    },
    "Soluzione": {
        "descrizione": "Come risolvi davvero il problema.",
        "criteri": "Analizza l’efficacia pratica della soluzione proposta dalla startup e la sua capacità di essere percepita come valida e superiore rispetto alle alternative esistenti. Variabili valutate: livello di innovazione, fattibilità tecnica, immediatezza di valore percepito, facilità d'uso, posizionamento rispetto ai competitor."
    },
    "Mercato": {
        "descrizione": "Quanto è grande l’opportunità?",
        "criteri": "Quantifica in modo preciso la dimensione (TAM/SAM/SOM), il potenziale di crescita, il timing e l'attrattività economica del mercato di riferimento. Variabili valutate: dimensione economica, trend di crescita, saturazione competitiva, propensione del mercato adotta nuove soluzioni."
    },
    "MVP": {
        "descrizione": "La prova tangibile della tua promessa.",
        "criteri": "Valuta se l’MVP esistente dimostra chiaramente e concretamente il valore della soluzione proposta ed è sufficientemente maturo per essere testato dagli utenti reali. Variabili valutate: completezza, usabilità effettiva, scalabilità tecnica iniziale, robustezza dimostrativa rispetto al valore promesso."
    },
    "Team": {
        "descrizione": "Chi realizza concretamente la visione.",
        "criteri": "Determina se il team attuale possiede le competenze, l'esperienza, e la complementarietà necessarie per portare con successo il prodotto sul mercato e per gestire crescita e rischi operativi. Variabili valutate: skill tecnici ed esecutivi, presenza di figure chiave (CTO, CEO, CMO), esperienza precedente, capacità di attrarre ulteriori talenti."
    },
    "Ritorno Atteso": {
        "descrizione": "Perché dovrebbero finanziarti?",
        "criteri": "Stima numericamente l’attrattività finanziaria della startup dal punto di vista degli investitori professionali, utilizzando modelli predittivi rigorosi come IRR (Internal Rate of Return), moltiplicatori attesi e diluizione equity. Variabili valutate: IRR stimato, multipli di investimento, equity post-diluizione, comparabilità con benchmark di mercato, giustificazione oggettiva della valuation richiesta."
    }
}

# Tutte le 21 coppie di coerenza
COHERENCE_PAIRS = [
    ("Problema", "Target"), ("Problema", "Soluzione"), ("Problema", "Mercato"),
    ("Problema", "MVP"), ("Problema", "Team"), ("Problema", "Ritorno Atteso"),
    ("Target", "Soluzione"), ("Target", "Mercato"), ("Target", "MVP"),
    ("Target", "Team"), ("Target", "Ritorno Atteso"),
    ("Soluzione", "Mercato"), ("Soluzione", "MVP"), ("Soluzione", "Team"),
    ("Soluzione", "Ritorno Atteso"),
    ("Mercato", "MVP"), ("Mercato", "Team"), ("Mercato", "Ritorno Atteso"),
    ("MVP", "Team"), ("MVP", "Ritorno Atteso"),
    ("Team", "Ritorno Atteso")
]


# --- Funzione per l'Analisi con GPT ---
def analyze_pitch_deck_with_gpt(pitch_text):
    # Rubrica per i punteggi (0-100) aggiornata per il prompt di GPT
    rubrica_prompt = """
**Rubrica per i punteggi (0-100):**
- 0-40: Mancante o completamente irrilevante.
- 40-55: Presente ma estremamente debole, vago o incoerente.
- 55-77: Buono, chiaro e convincente, con piccoli margini di miglioramento.
- 77-100: Eccellente, altamente credibile, ben articolato e supportato da dettagli solidi.
"""

    system_prompt_content = f"""Sei un analista esperto di pitch deck per startup. Il tuo compito è valutare un pitch deck fornito, identificare 7 variabili chiave, assegnare un punteggio da 0 a 100 a ciascuna variabile basandoti sulle rubriche fornite, fornire una motivazione dettagliata per ogni punteggio, e valutare la coerenza interna tra specifiche coppie di variabili. Restituisci tutte le informazioni in un formato JSON valido.

Un pitch deck è un documento che fornisce una panoramica completa del business di una startup. Le 7 variabili chiave vengono tipicamente presentate e approfondite nel PDF con queste modalità:
- **Problema**: Viene individuato e evidenziato tramite analisi o interviste a clienti reali, mostrando la sua urgenza e rilevanza.
- **Soluzione**: Si descrive cosa si offre e il valore unico che si condivide con il cliente, distinguendosi dalle alternative.
- **Mercato**: Si analizza la dimensione del mercato (TAM, SAM, SOM) e si studiano i competitor, evidenziando le loro soluzioni, punti di forza e di debolezza, a volte tramite mappe o matrici di posizionamento.
- **Business Model**: Si spiega in che modo l'azienda genera le proprie entrate.
- **Ritorno Atteso**: Si illustrano i momenti chiave per lanciare il progetto e le proiezioni di crescita nei prossimi anni per gli investitori.
- **Team**: Si presenta chi sono i membri fondatori e del team, per generare fiducia e dimostrare la capacità esecutiva.
- **MVP**: Viene descritto il Minimum Viable Product, la prova tangibile della sua promessa della startup, sufficientemente maturo per i test.

{rubrica_prompt}

Per ogni variabile, valuta il punteggio (0-100) e la motivazione basandoti su questi criteri:
"""
    for var, details in RUBRICS.items():
        system_prompt_content += f"- **{var}**: {details['descrizione']} {details['criteri']}\n"

    system_prompt_content += "\nValuta la coerenza (0-100) delle seguenti coppie di variabili. Un punteggio di 100 indica perfetta coerenza, 0 nessuna coerenza."
    for i, (var1, var2) in enumerate(COHERENCE_PAIRS):
        system_prompt_content += f"\n{i+1}. {var1} - {var2}"

    system_prompt_content += """

Il formato JSON di output deve essere ESATTAMENTE come segue. Non includere alcun testo aggiuntivo prima o dopo il blocco JSON.
```json
{
  "variabili_valutate": [
    {
      "nome": "Problema",
      "punteggio": <int: 0-100>,
      "motivazione": "<string: motivazione dettagliata>"
    },
    {
      "nome": "Target",
      "punteggio": <int: 0-100>,
      "motivazione": "<string: motivazione dettagliata>"
    },
    {
      "nome": "Soluzione",
      "punteggio": <int: 0-100>,
      "motivazione": "<string: motivazione dettagliata>"
    },
    {
      "nome": "Mercato",
      "punteggio": <int: 0-100>,
      "motivazione": "<string: motivazione dettagliata>"
    },
    {
      "nome": "MVP",
      "punteggio": <int: 0-100>,
      "motivazione": "<string: motivazione dettagliata>"
    },
    {
      "nome": "Team",
      "punteggio": <int: 0-100>,
      "motivazione": "<string: motivazione dettagliata>"
    },
    {
      "nome": "Ritorno Atteso",
      "punteggio": <int: 0-100>,
      "motivazione": "<string: motivazione dettagliata>"
    }
  ],
  "coerenza_coppie": [
"""
    # Genera la struttura per le 21 coppie di coerenza nel JSON di output
    for i, (var1, var2) in enumerate(COHERENCE_PAIRS):
        system_prompt_content += f"""    {{
      "coppia": "{var1} - {var2}",
      "punteggio": <int: 0-100>,
      "motivazione": "<string: motivazione dettagliata>"
    }}{',' if i < len(COHERENCE_PAIRS) - 1 else ''}\n"""
    
    system_prompt_content += """  ]
}
```
Testo del pitch deck da analizzare:
"""

    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": pitch_text}
    ]

    response = openai.chat.completions.create(
        model="gpt-4.1-nano", # Modello GPT aggiornato
        messages=messages,
        temperature=0.1,
        max_tokens=3500, # Max tokens aggiornato
        response_format={"type": "json_object"}
    )

    gpt_response_content = response.choices[0].message.content
    print(f"Risposta JSON grezza da OpenAI:\n{gpt_response_content[:1000]}...")

    try:
        parsed_response = json.loads(gpt_response_content)
        return parsed_response
    except json.JSONDecodeError as e:
        print(f"Errore nel parsing JSON della risposta GPT: {e}")
        print(f"Risposta completa di GPT che ha causato l'errore:\n{gpt_response_content}")
        return None

# --- Funzione per Calcoli Aggiuntivi ---
def perform_additional_calculations(gpt_analysis_data):
    # Estrai i dati necessari dall'output di GPT
    variabili_valutate_dict = {v['nome']: v['punteggio'] for v in gpt_analysis_data.get('variabili_valutate', [])}
    coerenza_coppie = gpt_analysis_data.get('coerenza_coppie', [])

    # 1. Calcolo dell'Indice di Coerenza (IC)
    total_coherence_score = sum(item['punteggio'] for item in coerenza_coppie)
    num_coherence_pairs = len(coerenza_coppie)
    ic = total_coherence_score / num_coherence_pairs if num_coherence_pairs > 0 else 0
    print(f"Indice di Coerenza (IC): {ic:.2f}")

    # 2. Calcolo del Final_Score e Final_Adjusted_Score.
    # Definisci i pesi per ogni variabile.
    weights = { # Pesi aggiornati dall'utente
        "Problema": 0.20,
        "Target": 0.17,
        "Soluzione": 0.17,
        "Mercato": 0.16,
        "MVP": 0.08,
        "Team": 0.08,
        "Ritorno Atteso": 0.14
    }

    final_score = sum(variabili_valutate_dict.get(var, 0) * weights.get(var, 0) for var in weights)
    print(f"Final Score: {final_score:.2f}")

    # L'Adjusted Score ora è una media ponderata
    peso_final_score = 0.7
    peso_indice_coerenza = 0.3
    final_adjusted_score = (final_score * peso_final_score + ic * peso_indice_coerenza)
    print(f"Final Adjusted Score (Nuova Logica): {final_adjusted_score:.2f}")

    # 3. Calcolo dello Z-score.
    z_score = None # Implementare quando avrai un dataset storico

    # 4. Assegnazione della Classe (INVESTIRE, MONITORARE, VERIFICARE, PASS)
    startup_class = "NON CLASSIFICATO" # Default
    if final_adjusted_score >= 77:
        startup_class = "INVESTIRE"
    elif final_adjusted_score >= 63:
        startup_class = "MONITORARE"
    elif final_adjusted_score >= 40:
        startup_class = "VERIFICARE"
    else: # Per punteggi inferiori a 40
        startup_class = "PASS" # "Pass" come in "Passare oltre, non investire"

    print(f"Classe Assegnata: {startup_class}")

    # Aggiorna il JSON di output con i calcoli aggiuntivi
    gpt_analysis_data["calcoli_aggiuntivi"] = {
        "indice_coerenza": round(ic, 2),
        "final_score": round(final_score, 2),
        "final_adjusted_score": round(final_adjusted_score, 2),
        "z_score": z_score,
        "classe": startup_class
    }

    return gpt_analysis_data

# --- Funzione per Salvare i Dati su Firestore ---
def save_to_firestore(document_id, data, user_id=None): # Aggiunto user_id come parametro opzionale
    try:
        if user_id:
            # Salva nel percorso privato dell'utente
            collection_ref = db.collection('artifacts').document(APP_ID).collection('users').document(user_id).collection('pitch_deck_analyses')
            print(f"Saving to user-specific Firestore path: {collection_ref.document(document_id).path}")
        else:
            # Salva nel percorso pubblico di default
            collection_ref = db.collection('artifacts').document(APP_ID).collection('public').document('data').collection('pitch_deck_analyses')
            print(f"Saving to public Firestore path: {collection_ref.document(document_id).path}")
        
        # Firestore non supporta liste di liste o oggetti troppo complessi direttamente
        collection_ref.document(document_id).set(data)
        print(f"Dati salvati con successo su Firestore: {collection_ref.document(document_id).path}")
        return True
    except Exception as e:
        print(f"ERRORE nel salvataggio su Firestore per il documento {document_id} (user_id: {user_id if user_id else 'N/A'}): {e}")
        return False

# --- Nuova funzione per recuperare e aggregare i dati da BigQuery per la dashboard ---
@functions_framework.http
def get_dashboard_data(request):
    # Recupera l'origine della richiesta
    request_origin = request.headers.get('Origin')

    # Configura gli header CORS
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Methods': 'GET, POST', # Aggiungi i metodi permessi
        'Access-Control-Allow-Headers': 'Content-Type, Authorization', # Permetti header Authorization
        'Access-Control-Max-Age': '3600' # Opzionale: cache per pre-flight requests
    }

    # Logica per impostare Access-Control-Allow-Origin
    # In ambiente di sviluppo locale, puoi permettere localhost o altre origini specifiche
    if request_origin and ("localhost" in request_origin or "127.0.0.1" in request_origin):
        headers['Access-Control-Allow-Origin'] = request_origin
        print(f"DEBUG: Impostato Access-Control-Allow-Origin a origine locale: {request_origin}")
    else:
        # In produzione, specifica il dominio della tua app React su Firebase Hosting
        headers['Access-Control-Allow-Origin'] = 'https://validatr-mvp.web.app'
        print(f"DEBUG: Impostato Access-Control-Allow-Origin a dominio di produzione: {headers['Access-Control-Allow-Origin']}")
        # Per test, potresti temporaneamente usare '*' ma NON farlo in produzione per motivi di sicurezza
        # headers['Access-Control-Allow-Origin'] = '*'


    # Gestione delle richieste OPTIONS per CORS pre-flight
    if request.method == 'OPTIONS':
        return ('', 204, headers) # Restituisce una risposta vuota con solo gli header

    # Imposta gli header CORS per le richieste reali (GET/POST)
    # L'header Access-Control-Allow-Origin è già impostato sopra

    try:
        # Autenticazione dell'utente tramite Firebase ID Token
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return json.dumps({"error": "Authorization header missing"}), 401, headers
        
        id_token = auth_header.split('Bearer ')[1]
        
        try:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            print(f"Richiesta autenticata da UID: {uid}")
        except Exception as e:
            print(f"Errore nella verifica del token Firebase: {e}")
            return json.dumps({"error": f"Invalid Firebase ID token: {e}"}), 403, headers

        # Ottieni il parametro di filtro dalla richiesta (rimosso dalla logica precedente)
        # filter_type = request.args.get('filter', 'all') 

        all_grouped_data = {}
    
        # Definisci il tuo ID progetto e dataset BigQuery
        PROJECT_ID = "validatr-mvp" 
        DATASET_ID = "validatr_analyses_dataset"
        
        # --- Recupera e raggruppa i dati da calcoli_aggiuntivi_view ---
        # Poiché l'HTML è stato ripristinato alla versione che usa le chiamate API
        # dobbiamo ripristinare la logica che legge da BigQuery VIEWS.
        # Ho rimosso l'integrazione di Firestore diretta per questa funzione API
        # e aggiunto le query per le viste BigQuery.
        
        # Query per calcoli_aggiuntivi_view
        query_core = f"""
        SELECT
            document_id,
            document_name,
            classe_pitch,
            final_score,
            final_adjusted_score,
            z_score,
            indice_coerenza,
            userId
        FROM
            `{PROJECT_ID}.{DATASET_ID}.calcoli_aggiuntivi_view`
        """
        rows_core = bq_client.query(query_core).result()
        for row in rows_core:
            doc_id = row.document_id
            # Filtra per l'utente autenticato (solo i miei pitch)
            if row.userId != uid:
                continue

            if doc_id not in all_grouped_data:
                all_grouped_data[doc_id] = {
                    "document_name": row.document_name,
                    "core_metrics": {},
                    "variables": [],
                    "coherence_pairs": []
                }
            all_grouped_data[doc_id]["core_metrics"] = {
                "classe_pitch": row.classe_pitch,
                "final_score": row.final_score,
                "final_adjusted_score": row.final_adjusted_score,
                "z_score": row.z_score,
                "indice_coerenza": row.indice_coerenza,
                "userId": row.userId
            }
    
        # Query per valutazione_pitch_view
        query_vars = f"""
        SELECT
            document_id,
            nome_variabile,
            punteggio_variabile,
            motivazione_variabile
        FROM
            `{PROJECT_ID}.{DATASET_ID}.valutazione_pitch_view`
        """
        rows_vars = bq_client.query(query_vars).result()
        for row in rows_vars:
            doc_id = row.document_id
            if doc_id in all_grouped_data: # Includi solo i documenti già filtrati per l'utente
                all_grouped_data[doc_id]["variables"].append({
                    "nome_variabile": row.nome_variabile,
                    "punteggio_variabile": row.punteggio_variabile,
                    "motivazione_variabile": row.motivazione_variabile
                })
    
        # Query per pitch_coherence_view
        query_coh = f"""
        SELECT
            document_id,
            nome_coppia,
            punteggio_coppia,
            motivazione_coppia
        FROM
            `{PROJECT_ID}.{DATASET_ID}.pitch_coherence_view`
        """
        rows_coh = bq_client.query(query_coh).result()
        for row in rows_coh:
            doc_id = row.document_id
            if doc_id in all_grouped_data: # Includi solo i documenti già filtrati per l'utente
                all_grouped_data[doc_id]["coherence_pairs"].append({
                    "nome_coppia": row.nome_coppia,
                    "punteggio_coppia": row.punteggio_coppia,
                    "motivazione_coppia": row.motivazione_coppia
                })
    
        return json.dumps(all_grouped_data), 200, headers

    except Exception as e:
        print(f"Errore nella funzione get_dashboard_data: {e}")
        return json.dumps({"error": str(e)}), 500, headers


# --- Funzione principale della Cloud Function (attivata da Cloud Storage) ---
@functions_framework.cloud_event
def process_pitch_deck(cloud_event):
    print(f"\n--- DEBUG: Contenuto completo di cloud_event ---")
    print(cloud_event)
    print(f"--- FINE DEBUG cloud_event ---\n")

    # IMPORANTE: MODIFICA CON L'EMAIL DEL TUO ADMIN FIREBASE
    # Questa email verr\u00E0 usata per associare i caricamenti manuali a un utente admin specifico.
    # In un ambiente di produzione, considera di usare Google Secret Manager per questo valore.
    ADMIN_EMAIL_FOR_MANUAL_UPLOADS = "admin@validatr.com" # <--- MODIFICA QUI

    try:
        event_data = None
        if isinstance(cloud_event, dict):
            event_data = cloud_event.get("data")
        elif hasattr(cloud_event, "data"):
            event_data = cloud_event.data
        else:
            print("Errore: cloud_event non \u00E8 un dizionario e non ha l'attributo 'data'.")
            return {"status": "error", "message": "CloudEvent is neither a dict nor has a 'data' attribute."}

        if event_data is None:
            print("Errore: Nessun dato 'data' valido nell'evento CloudEvent dopo la verifica.")
            return {"status": "error", "message": "Missing 'data' in CloudEvent after checks."}

        if "bucket" not in event_data or "name" not in event_data:
            print("Errore: Dati 'bucket' o 'name' mancanti nell'evento CloudEvent.")
            return {"status": "error", "message": "Missing 'bucket' or 'name' in CloudEvent data."}

        bucket_name = event_data["bucket"]
        file_name = event_data["name"]
        print(f"Triggered by file: gs://{bucket_name}/{file_name}")

        storage_client = storage.Client()
        input_bucket = storage_client.bucket(bucket_name)
        input_blob = input_bucket.blob(file_name)

        if not file_name.lower().endswith('.pdf'):
            print(f"Skipping non-PDF file: {file_name}. Only PDF files are processed.")
            return {"status": "skipped", "message": "Not a PDF file."}
        
        base_file_name = os.path.splitext(file_name)[0]
        output_blob_name = f"{base_file_name}.analysis_result.json"

        output_bucket_name = "validatr-pitch-decks-output" # Assicurati che questo bucket esista
        output_bucket = storage_client.bucket(output_bucket_name)
        output_blob = output_bucket.blob(output_blob_name)

        final_analysis = None # Inizializza final_analysis

        # --- RECUPERO USER_ID PER FIRESTORE ---
        user_id_for_firestore = None
        blob_metadata = None # Inizializza per sicurezza

        if input_blob.exists():
            input_blob.reload() # Assicurati di avere i metadati pi\u00F9 recenti
            blob_metadata = input_blob.metadata if input_blob.metadata is not None else {} # Inizializza a dict vuoto se None

            if blob_metadata: # Verifica se i metadati sono presenti e non None
                # 1. Tenta di ottenere l'email dell'utente finale dai metadati di Zapier/Typeform
                user_email_from_metadata = blob_metadata.get('user_email')
                if user_email_from_metadata:
                    try:
                        user_record = auth.get_user_by_email(user_email_from_metadata)
                        user_id_for_firestore = user_record.uid
                        print(f"Associando il pitch all'utente Firebase (email): {user_email_from_metadata} (UID: {user_id_for_firestore})")
                    except auth.UserNotFoundError:
                        print(f"WARNING: Utente Firebase '{user_email_from_metadata}' (da metadati 'user_email') non trovato. Cerco altre fonti o salvo pubblicamente.")
                    except Exception as e:
                        print(f"ERROR: Errore durante il recupero UID per '{user_email_from_metadata}': {e}. Cerco altre fonti o salvo pubblicamente.")
                else:
                    print("Metadato 'user_email' non presente nel blob.")

                # 2. Se l'utente finale non \u00E8 stato identificato, controlla se \u00E8 un caricamento manuale dell'admin
                if not user_id_for_firestore:
                    upload_source_metadata = blob_metadata.get('upload_source')
                    if upload_source_metadata == 'manual_admin':
                        # Se \u00E8 un caricamento manuale dell'admin, salva SEMPRE nel percorso pubblico.
                        # Non associarlo a un UID specifico in Firestore per questo tipo di upload.
                        user_id_for_firestore = None 
                        print(f"Associando il pitch come pubblico a causa di 'manual_admin' source.")
                        # Potresti voler loggare l'email admin qui per tracciabilit\u00E0 nei log
                        # try:
                        #     admin_user_record = auth.get_user_by_email(ADMIN_EMAIL_FOR_MANUAL_UPLOADS)
                        #     print(f"Caricamento manuale dell'Admin (Email: {ADMIN_EMAIL_FOR_MANUAL_UPLOADS}, UID: {admin_user_record.uid}) salvato pubblicamente.")
                        # except Exception as e:
                        #     print(f"Impossibile risolvere UID Admin per logging: {e}")
                    else:
                        print("Metadato 'upload_source' non presente o non 'manual_admin'.")
            else:
                print("WARNING: Blob esiste ma non ha metadati personalizzati. Il pitch sar\u00E0 salvato pubblicamente.")
        else:
            print("WARNING: Blob non trovato per la lettura dei metadati. Il pitch sar\u00E0 salvato pubblicamente.")


        # Scarica il contenuto del PDF in memoria per la nuova analisi
        pdf_content = io.BytesIO(input_blob.download_as_bytes())
        reader = PyPDF2.PdfReader(pdf_content)
        all_text = ""
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            extracted_page_text = page.extract_text()
            if extracted_page_text:
                all_text += extracted_page_text + "\n"

        all_text = all_text.replace('\n\n', '\n').strip()
        print(f"Testo estratto dal PDF (primi 500 caratteri): {all_text[:500]}...")

        # --- Chiamata API GPT per l'Analisi REALE ---
        analysis_result = analyze_pitch_deck_with_gpt(all_text) 
        
        # --- RISULTATO MOCK PER IL TEST SE GPT E' DISABILITATO ---
        if analysis_result is None:
            print("Utilizzando risultati di analisi mock per testing. ABILITA LA CHIAMATA GPT PER L'ANALISI REALE.")
            analysis_result = {
                "variabili_valutate": [
                    {"nome": "Problema", "punteggio": 70, "motivazione": "Mock: Il problema \u00E8 ben compreso."},
                    {"nome": "Target", "punteggio": 65, "motivazione": "Mock: Target definito."},
                    {"nome": "Soluzione", "punteggio": 75, "motivazione": "Mock: Soluzione chiara."},
                    {"nome": "Mercato", "punteggio": 60, "motivazione": "Mock: Mercato ampio."},
                    {"nome": "MVP", "punteggio": 55, "motivazione": "Mock: MVP migliorabile."},
                    {"nome": "Team", "punteggio": 80, "motivazione": "Mock: Team forte."},
                    {"nome": "Ritorno Atteso", "punteggio": 40, "motivazione": "Mock: Ritorno poco chiaro."}
                ],
                "coerenza_coppie": [
                    {"coppia": "Problema - Soluzione", "punteggio": 70, "motivazione": "Mock: Coerenza Problema-Soluzione buona."},
                    {"coppia": "Target - Mercato", "punteggio": 65, "motivazione": "Mock: Coerenza Target-Mercato media."},
                    {"coppia": "Soluzione - MVP", "punteggio": 50, "motivazione": "Mock: Coerenza Soluzione-MVP debole."},
                    {"coppia": "Team - Ritorno Atteso", "punteggio": 45, "motivazione": "Mock: Coerenza Team-Ritorno Atteso bassa."},
                    {"coppia": "Problema - Target", "punteggio": 70, "motivazione": "Il problema \u00E8 rilevante per il target definito, ma la connessione tra le esigenze specifiche di questo segmento e la soluzione proposta potrebbe essere pi\u00F9 esplicita e approfondita."},
                    {"coppia": "Problema - Mercato", "punteggio": 80, "motivazione": "Il mercato \u00E8 ampio e in crescita, coerente con il problema e la soluzione, anche se sarebbe utile un collegamento pi\u00F9 diretto tra la dimensione del mercato e la reale domanda del target."},
                    {"coppia": "Problema - MVP", "punteggio": 50, "motivazione": "L'MVP \u00E8 menzionato ma non dettagliato, quindi la coerenza tra problema e MVP \u00E8 debole. \u00C8 difficile valutare se l'MVP possa effettivamente validare il problema senza ulteriori informazioni."},
                    {"coppia": "Problema - Team", "punteggio": 65, "motivazione": "Il team ha competenze rilevanti, ma non \u00E8 chiaro se abbia le capacit\u00E0 specifiche per risolvere il problema in modo efficace, specialmente in relazione alle sfide tecniche e di mercato."},
                    {"coppia": "Problema - Ritorno Atteso", "punteggio": 40, "motivazione": "L'assenza di stime di ritorno rende poco coerente la relazione tra il problema e le aspettative di ritorno economico, creando una disconnessione tra la necessit\u00E0 di risolvere il problema e i benefici attesi."},
                    {"coppia": "Target - Soluzione", "punteggio": 75, "motivazione": "La soluzione \u00E8 pensata per il target, ma potrebbe essere pi\u00F9 personalizzata o adattata alle esigenze specifiche di questo segmento, migliorando la coerenza."},
                    {"coppia": "Target - MVP", "punteggio": 55, "motivazione": "L'MVP non \u00E8 descritto in modo dettagliato, quindi la coerenza tra target e MVP \u00E8 limitata. \u00C8 difficile capire se l'MVP sia tarato sulle esigenze specifiche del target."},
                    {"coppia": "Target - Team", "punteggio": 70, "motivazione": "Il team ha competenze adeguate per il target, ma non sono evidenziate esperienze specifiche nel segmento di mercato o nelle esigenze di questo pubblico."},
                    {"coppia": "Target - Ritorno Atteso", "punteggio": 45, "motivazione": "L'assenza di stime di ritorno rende poco coerente la relazione tra il target e le aspettative di ritorno economico, creando un gap tra le esigenze del segmento e i benefici attesi."},
                    {"coppia": "Soluzione - Mercato", "punteggio": 80, "motivazione": "La soluzione si inserisce in un mercato in crescita e con ampio potenziale, coerente con le dimensioni e le tendenze del settore."},
                    {"coppia": "Soluzione - Team", "punteggio": 70, "motivazione": "Il team ha competenze tecniche e di marketing, coerenti con lo sviluppo e il lancio della soluzione, anche se mancano dettagli sulla capacit\u00E0 di innovare o differenziarsi."},
                    {"coppia": "Soluzione - Ritorno Atteso", "punteggio": 45, "motivazione": "L'assenza di proiezioni di ritorno rende debole la coerenza tra la soluzione proposta e le aspettative di ritorno economico."},
                    {"coppia": "Mercato - MVP", "punteggio": 55, "motivazione": "L'MVP non \u00E8 descritto in modo dettagliato, quindi la coerenza tra mercato e MVP \u00E8 limitata. Non si pu\u00F2 valutare se l'MVP possa validare il mercato."},
                    {"coppia": "Mercato - Team", "punteggio": 75, "motivazione": "Il mercato ampio e in crescita richiede un team con competenze specifiche, che il team sembra possedere, anche se non sono dettagliate le esperienze nel settore."},
                    {"coppia": "Mercato - Ritorno Atteso", "punteggio": 50, "motivazione": "L'assenza di stime di ritorno rende poco coerente la relazione tra dimensione di mercato e aspettative di ritorno economico."},
                    {"coppia": "MVP - Team", "punteggio": 50, "motivazione": "L'MVP non \u00E8 dettagliato, quindi la coerenza con il team \u00E8 limitata. Non si pu\u00F2 valutare se il team abbia le competenze per sviluppare e validare l'MVP."},
                    {"coppia": "MVP - Ritorno Atteso", "punteggio": 40, "motivazione": "L'assenza di stime di ritorno rende debole la coerenza tra MVP e ritorno atteso, creando un gap tra la validazione del prodotto e i benefici economici."},
                    {"coppia": "Team - Ritorno Atteso", "punteggio": 55, "motivazione": "Il team ha competenze adeguate, ma senza proiezioni di ritorno, la relazione tra capacit\u00E0 esecutiva e benefici economici attesi \u00E8 poco supportata."}
                ]
            }
        # --- FINE RISULTATO MOCK ---

        if analysis_result:
            final_analysis = perform_additional_calculations(analysis_result)
        else:
            print("Errore: L'analisi non ha prodotto risultati validi o parsabili (probabilmente mock non attivo o errore GPT).")
            return {"status": "error", "message": "Analysis failed or returned invalid data."}

        # Usiamo il nome del file (senza estensione) come ID documento Firestore
        document_id = base_file_name 

        # --- SALVA O AGGIORNA SU FIRESTORE (con user_id) ---
        # user_id_for_firestore sar\u00E0 l'UID dell'utente finale, dell'admin, o None per il pubblico
        firestore_save_success = save_to_firestore(document_id, final_analysis, user_id=user_id_for_firestore)
        if not firestore_save_success:
            print(f"AVVERTIMENTO: Il salvataggio/aggiornamento su Firestore per {document_id} (user_id: {user_id_for_firestore if user_id_for_firestore else 'N/A'}) \u00E8 fallito. L'analisi \u00E8 stata completata ma il dato non \u00E8 stato persistito in Firestore.")
        
        # --- SALVA O AGGIORNA SU CLOUD STORAGE ---
        try:
            output_blob.upload_from_string(json.dumps(final_analysis, indent=2))
            print(f"Analisi completa salvata/aggiornata in gs://{output_bucket_name}/{output_blob_name}")
            
            backup_bucket_name = "validatr-pitch-decks-input-backup" # Definisci il nome del bucket di backup
            backup_bucket = storage_client.bucket(backup_bucket_name)
            backup_blob = backup_bucket.blob(file_name) # Mantieni lo stesso nome file

            # Sposta il blob
            new_blob = input_bucket.copy_blob(input_blob, backup_bucket, file_name)
            input_blob.delete()
            print(f"File '{file_name}' spostato con successo da '{bucket_name}' a '{backup_bucket_name}'.")
            # --- FINE NUOVA LOGICA ---
            return {"status": "success", "message": "PDF processed, analysis saved/updated to CS and Firestore."}
        except NotFound as e:
            print(f"ERRORE CRITICO: Il bucket di output '{output_bucket_name}' non esiste o la funzione non ha i permessi. Dettaglio: {e}")
            print(f"Impossibile salvare il risultato per il file: {file_name}. L'analisi \u00E8 stata completata ma il salvataggio su CS \u00E8 fallito.")
            return {"status": "error", "message": f"Output bucket '{output_bucket_name}' not found or no permissions. Analysis completed but result not saved to CS."}

    except openai.APIError as e:
        print(f"Errore API OpenAI: {e}")
        return {"status": "error", "message": f"OpenAI API Error: {e}"}
    except json.JSONDecodeError as e:
        print(f"Errore nel parsing JSON della risposta GPT: {e}. Risposta GPT non valida.")
        print(f"Risposta completa di GPT che ha causato l'errore:\n{e.doc}")
        return {"status": "error", "message": f"GPT response not valid JSON: {e}"}
    except PyPDF2.errors.PdfReadError as e:
        print(f"Errore nella lettura del PDF: {e}")
        return {"status": "error", "message": f"Failed to read PDF: {e}"}
    except Exception as e:
        print(f"ERRORE GENERALE NON CATTURATO: {e}")
        print(f"Si \u00E8 verificato un errore inatteso durante l'elaborazione del file: {file_name}. L'esecuzione verr\u00E0 terminata come successo per evitare retry.")
        return {"status": "error", "message": f"An unexpected error occurred: {e}. Execution terminated successfully to prevent retries."}
