import functions_framework
import json
import io
import PyPDF2
import openai
import os
from google.cloud import storage
from google.api_core.exceptions import NotFound # Importa l'eccezione specifica per "Not Found"

# --- Inizializzazione Firebase e Firestore ---
# Per l'ambiente Canvas, le variabili __app_id e __firebase_config sono globali.
# In un ambiente standard GCP, dovresti caricare la tua service account key in modo sicuro.
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

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
    system_prompt_content = """Sei un analista esperto di pitch deck per startup. Il tuo compito è valutare un pitch deck fornito, identificare 7 variabili chiave, assegnare un punteggio da 0 a 100 a ciascuna variabile basandoti sulle rubriche fornite, fornire una motivazione dettagliata per ogni punteggio, e valutare la coerenza interna tra specifiche coppie di variabili. Restituisci tutte le informazioni in un formato JSON valido.

Le 7 variabili chiave sono: Problema, Target, Soluzione, Mercato, MVP, Team, Ritorno Atteso.

**Rubrica per i punteggi (0-100):**
- 0-20: Mancante o completamente irrilevante.
- 21-40: Presente ma estremamente debole, vago o incoerente.
- 41-60: Accettabile ma con gravi lacune, ambiguità o necessità di maggiori dettagli.
- 61-80: Buono, chiaro e convincente, con piccoli margini di miglioramento.
- 81-100: Eccellente, altamente credibile, ben articolato e supportato da dettagli solidi.

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
        model="gpt-3.5-turbo", # Puoi valutare l'uso di gpt-4o per una maggiore qualità
        messages=messages,
        temperature=0.1,
        max_tokens=2500,
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
    # Definisci i pesi per ogni variabile. Questi sono esempi, personalizzali.
    weights = {
        "Problema": 0.15,
        "Target": 0.10,
        "Soluzione": 0.15,
        "Mercato": 0.15,
        "MVP": 0.15,
        "Team": 0.15,
        "Ritorno Atteso": 0.15
    }

    final_score = sum(variabili_valutate_dict.get(var, 0) * weights.get(var, 0) for var in weights)
    print(f"Final Score: {final_score:.2f}")

    # L'Adjusted Score tiene conto dell'IC
    final_adjusted_score = final_score * (ic / 100)
    print(f"Final Adjusted Score: {final_adjusted_score:.2f}")

    # 3. Calcolo dello Z-score.
    # Questo richiede dati storici (media e deviazione standard di Final_Adjusted_Score).
    # Per l'MVP, lo lasciamo come None.
    z_score = None # Implementare quando avrai un dataset storico

    # 4. Assegnazione della Classe (Rosso, Giallo, Verde, Immunizzato, Zero)
    # Definisci le tue soglie e la logica qui.
    startup_class = "Non Classificato"
    if final_adjusted_score >= 85: # Soglia per "Verde"
        startup_class = "Verde"
    elif final_adjusted_score >= 65: # Soglia per "Giallo"
        startup_class = "Giallo"
    elif final_adjusted_score >= 40: # Soglia per "Rosso"
        startup_class = "Rosso"
    elif final_adjusted_score > 0:
        startup_class = "Zero" # Per punteggi bassi ma non nulli
    # La classe "Immunizzato" potrebbe essere per casi eccezionali, non basati solo sul punteggio.
    # Es: if final_adjusted_score >= 95 and specific_condition_met: startup_class = "Immunizzato"

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
def save_to_firestore(document_id, data):
    try:
        # Percorso della collezione: /artifacts/{appId}/public/data/pitch_deck_analyses
        # Usiamo una collezione 'public' per semplicità, considerando che i dati
        # potrebbero essere condivisi o consultati da diverse UI (es. Looker Studio).
        collection_ref = db.collection('artifacts').document(APP_ID).collection('public').document('data').collection('pitch_deck_analyses')
        
        # Firestore non supporta liste di liste o oggetti troppo complessi direttamente
        # Quindi, se il JSON contiene strutture nidificate problematiche, potrebbe essere necessario serializzarle.
        # Assumiamo che 'data' (final_analysis) sia già compatibile.
        collection_ref.document(document_id).set(data)
        print(f"Dati salvati con successo su Firestore: {collection_ref.document(document_id).path}")
        return True
    except Exception as e:
        print(f"ERRORE nel salvataggio su Firestore per il documento {document_id}: {e}")
        # Non rilanciare l'errore per evitare retry della Cloud Function
        return False

# --- Funzione principale della Cloud Function ---
@functions_framework.cloud_event
def process_pitch_deck(cloud_event):
    print(f"\n--- DEBUG: Contenuto completo di cloud_event ---")
    print(cloud_event)
    print(f"--- FINE DEBUG cloud_event ---\n")

    try:
        event_data = None
        if isinstance(cloud_event, dict):
            event_data = cloud_event.get("data")
            print(f"--- DEBUG: cloud_event è un dict. event_data da .get('data'): {event_data is not None} ---")
        elif hasattr(cloud_event, "data"):
            event_data = cloud_event.data
            print(f"--- DEBUG: cloud_event ha attributo .data. event_data: {event_data is not None} ---")
        else:
            print("Errore: cloud_event non è un dizionario e non ha l'attributo 'data'.")
            return {"status": "error", "message": "CloudEvent is neither a dict nor has a 'data' attribute."}

        if event_data is None:
            print("Errore: Nessun dato 'data' valido nell'evento CloudEvent dopo la verifica.")
            return {"status": "error", "message": "Missing 'data' in CloudEvent after checks."}

        print(f"\n--- DEBUG: Contenuto di event_data (ex cloud_event.data) ---")
        print(event_data)
        print(f"--- FINE DEBUG event_data ---\n")

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

        if output_blob.exists():
            print(f"L'analisi per '{file_name}' esiste già come '{output_blob_name}'. Caricamento del file esistente.")
            try:
                existing_json_content = output_blob.download_as_text()
                final_analysis = json.loads(existing_json_content)
                print(f"File JSON esistente caricato con successo.")
            except Exception as e:
                print(f"ATTENZIONE: Errore durante il caricamento o parsing del file JSON esistente '{output_blob_name}': {e}. Procedo con una nuova analisi.")
                final_analysis = None # Forza la ri-generazione se il caricamento fallisce
        
        # Se final_analysis è ancora None (significa che non esisteva o non è stato caricato correttamente)
        if final_analysis is None:
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
            
            if analysis_result:
                final_analysis = perform_additional_calculations(analysis_result)
            else:
                print("Errore: L'analisi GPT non ha prodotto risultati validi o parsabili.")
                return {"status": "error", "message": "GPT analysis failed or returned invalid data."}

        # A questo punto, final_analysis contiene o il JSON ricaricato o il JSON appena generato
        
        # Usiamo il nome del file (senza estensione) come ID documento Firestore
        document_id = base_file_name 

        # --- SALVA O AGGIORNA SU FIRESTORE ---
        firestore_save_success = save_to_firestore(document_id, final_analysis)
        if not firestore_save_success:
            print(f"AVVERTIMENTO: Il salvataggio/aggiornamento su Firestore per {document_id} è fallito. L'analisi è stata completata ma il dato non è stato persistito in Firestore.")
        
        # --- SALVA O AGGIORNA SU CLOUD STORAGE ---
        try:
            output_blob.upload_from_string(json.dumps(final_analysis, indent=2))
            print(f"Analisi completa salvata/aggiornata in gs://{output_bucket_name}/{output_blob_name}")
            return {"status": "success", "message": "PDF processed, analysis saved/updated to CS and Firestore."}
        except NotFound as e:
            print(f"ERRORE CRITICO: Il bucket di output '{output_bucket_name}' non esiste o la funzione non ha i permessi. Dettaglio: {e}")
            print(f"Impossibile salvare il risultato per il file: {file_name}. L'analisi è stata completata ma il salvataggio su CS è fallito.")
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
        print(f"Si è verificato un errore inatteso durante l'elaborazione del file: {file_name}. L'esecuzione verrà terminata come successo per evitare retry.")
        return {"status": "error", "message": f"An unexpected error occurred: {e}. Execution terminated successfully to prevent retries."}
