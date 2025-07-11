import functions_framework
import json
import io
import PyPDF2
import openai
import os
from google.cloud import storage
from google.api_core.exceptions import NotFound
from google.cloud import bigquery
import vertexai
from vertexai.generative_models import GenerativeModel
import firebase_admin
from firebase_admin import credentials, firestore, auth

# --- Inizializzazione dei Servizi Google Cloud e Firebase ---
PROJECT_ID = "validatr-mvp"
LOCATION = "us-central1"
vertexai.init(project=PROJECT_ID, location=LOCATION)

if not firebase_admin._apps:
    try:
        # Inizializza l'SDK di Firebase utilizzando le credenziali di default dell'ambiente
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK inizializzato con successo.")
    except Exception as e:
        print(f"Errore nell'inizializzazione di Firebase Admin SDK: {e}")

db = firestore.client()
bq_client = bigquery.Client()
APP_ID = os.environ.get('CANVAS_APP_ID', 'validatr-mvp')
UID_excluded = os.environ.get("UID_excluded")
openai.api_key = os.environ.get("OPENAI_API_KEY")

# --- Definizione delle Rubriche di Valutazione ---
# Contengono i criteri dettagliati per l'analisi di ogni variabile del pitch deck.
RUBRICS = {
    "Problema": {
        "criteri": "Misura quanto il problema che la startup intende risolvere sia reale, urgente e rilevante per gli stakeholder. Variabili valutate: concretezza, urgenza percepita, intensità del bisogno nel mercato, verifica empirica attraverso feedback degli utenti target."
    },
    "Target": {
        "criteri": "Determina il grado di definizione, raggiungibilità e predisposizione alla spesa degli utenti destinatari della soluzione. Variabili valutate: precisione segmentale, capacità economica, willingness-to-pay, facilità di essere identificato e raggiunto, maturità tecnologica o predisposizione all'adottare nuove soluzioni, dimensione quantitativa e qualitativa del pubblico target."
    },
    "Soluzione": {
        "criteri": "Analizza l'efficacia pratica della soluzione proposta dalla startup e la sua capacità di essere percepita come valida e superiore rispetto alle alternative esistenti. Variabili valutate: livello di innovazione, fattibilità tecnica, immediatezza di valore percepito, facilità d'uso, posizionamento rispetto ai competitor, rilevanza rispetto al problema, difficoltà a essere replicata da terzi."
    },
    "Mercato": {
        "criteri": "Quantifica in modo preciso la dimensione (TAM/SAM/SOM), il potenziale di crescita, il timing, l'attrattività economica del mercato di riferimento, la saturazione/competitività, la facilità ad aggredirlo. Variabili valutate: dimensione economica, trend di crescita, competitività (forza dei competitor, saturazione competitiva, capacità/attitudine dei competitor a innovare; considera anche competitor indiretti), facilità di ingresso (valutare eventuali barriere all'entrata e la capacità della startup di superarle), apertura del mercato a nuovi player, presenza di minacce esterne o rischi critici (come forti correlazioni del mercato di riferimento a altri fattori quali altri mercati, normative, politica, e analizza in modo critico possibili rischi derivanti da questa correlazione), presenza di opportunità e sinergie."
    },
    "MVP": {
        "criteri": "Valuta se l'MVP esistente dimostra chiaramente e concretamente il valore della soluzione proposta ed è sufficientemente maturo per essere testato dagli utenti reali. In alcuni casi il servizio/prodotto/piattaforma potrebbe essere già sviluppato e in tal caso verranno riportati dati sull'utilizzo/acquisizione e traction del prodotto/servizio. Variabili valutate: completezza, usabilità effettiva, scalabilità tecnica iniziale, robustezza dimostrativa rispetto al valore promesso."
    },
    "Team": {
        "criteri": "Determina se il team attuale possiede le competenze, l'esperienza, e la complementarietà necessarie per portare con successo il prodotto sul mercato e per gestire crescita e rischi operativi. Verifica che le competenze del team siano coerenti con le esigenze specifiche della startup. Variabili valutate: skill tecniche ed esecutive, presenza di figure chiave (CTO, CEO, CMO), esperienza precedente, capacità di attrarre ulteriori talenti."
    },
    "Ritorno Atteso": {
        "criteri": "Stima numericamente l'attrattività finanziaria della startup dal punto di vista degli investitori professionali, utilizzando modelli predittivi rigorosi come IRR (Internal Rate of Return), moltiplicatori attesi e diluizione equity. Variabili valutate: IRR stimato, multipli di investimento, equity post-diluizione, comparabilità con benchmark di mercato, giustificazione oggettiva della valuation richiesta, capacità del business model di generare revenue e profitti scalabili e sostenibili nel tempo, solidità e affidabilità delle proiezioni finanziarie stimate, prova di avere già generato entrate e avere utenti paganti/clienti."
    }
}

# Definisce le 21 coppie di variabili da analizzare per la coerenza.
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

# Fornisce linee guida specifiche per la valutazione di ogni coppia di coerenza.
COHERENCE_GUIDELINES = {
    ("Problema", "Target"): "Elementi utili da considerare: se il target scelto è il principale percettore del problema; se il problema è rilevante e urgente per quel target; se il target è colui che può prendere/influenzare decisioni di acquisto per risolvere quel problema.",
    ("Problema", "Soluzione"): "Elementi utili da considerare: se la soluzione risolve il problema in modo efficace, scalabile, ripetibile, agevole e fruibile.",
    ("Problema", "Mercato"): "Elementi utili da considerare: se il mercato è già in cerca/attivo per risolvere il problema (indicazione di problema realmente percepito); se la concorrenza ha soluzioni per risolvere il problema (valutare se vi sono per dimostrare quanto è pronto il mercato); quanto sono efficaci le attuali soluzioni sul mercato nel risolvere il problema (se sono molto efficaci vi è un impatto negativo sullo score).",
    ("Problema", "MVP"): "Elementi utili da considerare: se l'mvp è capace di risolvere la componente principale del problema; se la fruibilità dell'MVP è conforme con le modalità di risoluzione del problema.",
    ("Problema", "Team"): "Elementi utili da considerare: se il team ha esperienza diretta del problema; se ha le competenze per valutare e comprendere correttamente il problema.",
    ("Problema", "Ritorno Atteso"): "Elementi utili da considerare: se il problema è temporaneo o rimane nel tempo (nel primo caso impatto negativo); se il problema è così impattante da assicurare una willingness to pay per risolverlo stabile o in crescita nei prossimi anni; se il problema può venire meno facilmente per esternalità probabili (politiche, socio-economiche, normative, tecnologiche).",
    ("Target", "Soluzione"): "Elementi utili da considerare: se comportamenti, attitudini, abitudini e maturità digitale del target sono coerenti con la soluzione proposta.",
    ("Target", "Mercato"): "Elementi utili da considerare: se il target scelto è una componente importante del mercato, ben definita, identificabile e raggiungibile; se il target è una componente del mercato propensa ad adottare nuove soluzioni; se il target scelto è già fidalizzato a altre aziende/soluzioni/metodologie (impatto negativo).",
    ("Target", "MVP"): "Elementi utili da considerare: se l'MVP è facilmente fruibile dal target, compatibile con le sue abitudini, comportamenti, bisogni e maturità digitale.",
    ("Target", "Team"): "Elementi utili da considerare: se il team ha le competenze, esperienze e abilità per comprendere il target, raggiungerlo e convincerlo.",
    ("Target", "Ritorno Atteso"): "Elementi utili da considerare: quanto il target è di un numero sufficiente (ora e nei prossimi anni) e ha le disponibilità economiche per generare ritorni; se il target è caratterizzato per possibilità di fidelizzazione e facilità di conversione per genererare ritorni positivi e in crescita; se le abitudini del target lo rendono idonei a generare ricavi crescenti, scalabili e sostenibili nel breve, medio e lungo termine.",
    ("Soluzione", "Mercato"): "Elementi utili da considerare: se la soluzione si differenzia sufficientemente da competitor diretti e indiretti, se i benefici della soluzione possono essere facilmente compresi dal mercato.",
    ("Soluzione", "MVP"): "Elementi utili da considerare: se l'mvp permette di comprendere la soluzione e ne riassume efficacemente i vantaggi chiave; se l'mvp è una soluzione efficace; se l'mvp può essere facilmente scalato in una soluzione più completa e differenziata.",
    ("Soluzione", "Team"): "Elementi utili da considerare: se il team ha le abilità, esperienze e network per sviluppare, presentare e vendere efficacemente la soluzione.",
    ("Soluzione", "Ritorno Atteso"): "Elementi utili da considerare: se la soluzione è scalabile e rimane valida e rilevante nel tempo; se la soluzione è difficilmente replicabile da terzi; se la soluzione è compatibile con il business model previsto per generare alte marginalità; se la soluzione agevola la fidelizzazione con abbonamenti/acquisti ripetuti.",
    ("Mercato", "MVP"): "Elementi utili da considerare: se l'mvp è compatibile con le esigenze del mercato; se è rilevante, differenziato, chiaro e fruibile dato il contesto di mercato in cui è calato.",
    ("Mercato", "Team"): "Elementi utili da considerare: il team ha le abilità, esperienze o connessioni per comprendere il mercato, penetrarlo e superare eventuali barriere all'entrata.",
    ("Mercato", "Ritorno Atteso"): "Elementi utili da considerare: se il mercato (grandezza, crescita, grado di competitività, apertura) è coerente con gli obiettivi di ritorno atteso indicati.",
    ("MVP", "Team"): "Elementi utili da considerare: se il team ha capacità e esperienze coerenti per sviluppare l'mvp indicato.",
    ("MVP", "Ritorno Atteso"): "Elementi utili da considerare: se i dati sullo stato dell'mvp, le sue caratteristiche e la traction generata (utenti, tester, revenue iniziali) sono coerenti con gli obiettivi di ritorno atteso.",
    ("Team", "Ritorno Atteso"): "Elementi utili da considerare: se il team ha le abilità, esperienze e connessioni utili a raggiungere i risultati indicati."
}

def analyze_pitch_deck_with_gpt(pitch_text):
    """
    Costruisce il prompt per l'IA e chiama l'API di OpenAI per l'analisi del pitch.
    """
    system_prompt_content = """Sei un analista esperto nell'analisi e valutazione di pitch deck per startup con background nei principali fondi di investimento per startup come Sequoia Capital, Andreessen Horowitz, P101, 360 capital, Google Ventures, LVenture Group, Y Combinator e CDP Venture Capital SGR di cui utilizzi best practice e approccio.

Il tuo compito è valutare l'opportunità di investimento in startup per determinare quanto è consigliato l'investimento nella startup in esame partendo dal pitch deck fornito. Identifichi 7 variabili chiave, assegnando un punteggio da 0 a 100 a ciascuna variabile basandoti sulle rubriche fornite, fornendo una motivazione dettagliata per ogni punteggio, e valutando la coerenza interna tra specifiche coppie di variabili. Restituisci tutte le informazioni in un formato JSON valido.

Ricorda che dovrai valutare le informazioni ottenute in maniera analitica e critica nella prospettiva di un analista che deve discernere le migliori opportunità di investiemento. Se necessario, includi nel tuo processo di valutazione fonti esterne affidabili per verificare i claim dei pitch deck e fornire una valutazione aggiornata.

### Rubrica per i punteggi (0-100):
* **0-40**: Mancante o completamente irrilevante.
* **40-55**: Presente ma estremamente debole, vago o incoerente.
* **55-77**: Buono, chiaro e convincente, con piccoli margini di miglioramento.
* **77-100**: Eccellente, altamente credibile, ben articolato e supportato da dettagli solidi.

---

### Criteri di Valutazione Dettagliati
Per ogni variabile, valuta il punteggio (0-100) e la motivazione basandoti su questi criteri:
"""

    for var, details in RUBRICS.items():
        system_prompt_content += f"\n* **{var}**: {details['criteri']}"

    system_prompt_content += "\n\n---\n\n### Criteri di Valutazione della Coerenza (0-100)\nValuta la coerenza (0-100) delle seguenti coppie di variabili. Un punteggio di 100 indica perfetta coerenza.\n"

    for i, (var1, var2) in enumerate(COHERENCE_PAIRS):
        pair_tuple = (var1, var2)
        guideline = COHERENCE_GUIDELINES.get(pair_tuple, "Nessuna linea guida specifica.")
        print(guideline)
        system_prompt_content += f"\n{i+1}. **{var1} - {var2}**: {guideline}"

    # --- INIZIO DELLA SEZIONE CORRETTA ---
    system_prompt_content += """

---

### Formato di Output (JSON)
Il formato JSON di output deve essere ESATTAMENTE come segue. Non includere alcun testo aggiuntivo prima o dopo il blocco JSON.
```json
{
  "variabili_valutate": [
    {
      "nome": "Problema",
      "punteggio": 0,
      "motivazione": { "it": "string", "en": "string" }
    },
    {
      "nome": "Target",
      "punteggio": 0,
      "motivazione": { "it": "string", "en": "string" }
    },
    {
      "nome": "Soluzione",
      "punteggio": 0,
      "motivazione": { "it": "string", "en": "string" }
    },
    {
      "nome": "Mercato",
      "punteggio": 0,
      "motivazione": { "it": "string", "en": "string" }
    },
    {
      "nome": "MVP",
      "punteggio": 0,
      "motivazione": { "it": "string", "en": "string" }
    },
    {
      "nome": "Team",
      "punteggio": 0,
      "motivazione": { "it": "string", "en": "string" }
    },
    {
      "nome": "Ritorno Atteso",
      "punteggio": 0,
      "motivazione": { "it": "string", "en": "string" }
    }
  ],
  "coerenza_coppie": [
"""
    # Costruisce dinamicamente l'esempio per tutte le 21 coppie, rendendo le istruzioni inequivocabili.
    for i, (var1, var2) in enumerate(COHERENCE_PAIRS):
        system_prompt_content += f"""    {{
      "coppia": "{var1} - {var2}",
      "punteggio": 0,
      "motivazione": {{ "it": "string", "en": "string" }}
    }}{',' if i < len(COHERENCE_PAIRS) - 1 else ''}
"""

    system_prompt_content += """  ]
}
Testo del pitch deck da analizzare:
"""
    print(system_prompt_content)
    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": pitch_text}
    ]

    response = openai.chat.completions.create(
        model="gpt-4.1-nano", 
        messages=messages,
        temperature=0.1,
        max_tokens=4096,
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

def perform_additional_calculations(gpt_analysis_data):
    """
    Calcola lo score finale, l'indice di coerenza e la classe della startup
    basandosi sui dati analizzati dall'IA.
    """
    variabili_valutate_dict = {v['nome']: v['punteggio'] for v in gpt_analysis_data.get('variabili_valutate', [])}
    coerenza_coppie = gpt_analysis_data.get('coerenza_coppie', [])

    total_coherence_score = sum(item['punteggio'] for item in coerenza_coppie)
    num_coherence_pairs = len(coerenza_coppie) if coerenza_coppie else 0
    ic = (total_coherence_score / num_coherence_pairs) if num_coherence_pairs > 0 else 0

    weights = {
        "Problema": 0.20, "Target": 0.17, "Soluzione": 0.17,
        "Mercato": 0.16, "MVP": 0.08, "Team": 0.08, "Ritorno Atteso": 0.14
    }

    final_score = sum(variabili_valutate_dict.get(var, 0) * weights.get(var, 0) for var in weights)
    
    peso_final_score = 0.7
    peso_indice_coerenza = 0.3
    final_adjusted_score = (final_score * peso_final_score) + (ic * peso_indice_coerenza)

    startup_class = "PASS"
    if final_adjusted_score >= 77:
        startup_class = "INVESTIRE"
    elif final_adjusted_score >= 63:
        startup_class = "MONITORARE"
    elif final_adjusted_score >= 40:
        startup_class = "VERIFICARE"

    gpt_analysis_data["core_metrics"] = {
        "indice_coerenza": round(ic, 2),
        "final_score": round(final_score, 2),
        "final_adjusted_score": round(final_adjusted_score, 2),
        "z_score": None,
        "classe_pitch": startup_class
    }
    
    return gpt_analysis_data

def save_to_firestore(document_id, data, user_id=None):
    """
    Salva i dati dell'analisi su Firestore nel percorso corretto (utente o pubblico).
    """
    try:
        if user_id:
            collection_ref = db.collection('artifacts', APP_ID, 'users', user_id, 'pitch_deck_analyses')
        else:
            collection_ref = db.collection('artifacts', APP_ID, 'public', 'data', 'pitch_deck_analyses')
        
        collection_ref.document(document_id).set(data)
        print(f"Dati salvati con successo su Firestore: {collection_ref.document(document_id).path}")
        return True
    except Exception as e:
        print(f"ERRORE nel salvataggio su Firestore per il documento {document_id} (user_id: {user_id or 'N/A'}): {e}")
        return False

@functions_framework.http
def get_dashboard_data(request):
    """
    Funzione HTTP per recuperare i dati di analisi di un utente da BigQuery
    e restituirli al frontend.
    """
    request_origin = request.headers.get('Origin')
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Methods': 'GET, POST',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '3600'
    }

    if request_origin and ("localhost" in request_origin or "127.0.0.1" in request_origin):
        headers['Access-Control-Allow-Origin'] = request_origin
    else:
        headers['Access-Control-Allow-Origin'] = 'https://validatr-mvp.web.app'

    if request.method == 'OPTIONS':
        return ('', 204, headers)

    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return json.dumps({"error": "Authorization header missing or invalid"}), 401, headers
        
        id_token = auth_header.split('Bearer ')[1]
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        print(f"Richiesta autenticata da UID: {uid}")

        all_grouped_data = {}
        DATASET_ID = "validatr_analyses_dataset"
        
        # Query per recuperare i dati aggregati dell'utente
        query_core = f"SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.calcoli_aggiuntivi_view` WHERE userId = @user_id"
        job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("user_id", "STRING", uid)])
        rows_core = bq_client.query(query_core, job_config=job_config).result()
        
        for row in rows_core:
            doc_id = row.document_id
            if doc_id not in all_grouped_data:
                all_grouped_data[doc_id] = {"document_name": row.document_name, "core_metrics": {}, "variables": [], "coherence_pairs": []}
            all_grouped_data[doc_id]["core_metrics"] = {
                "classe_pitch": row.classe_pitch, "final_score": row.final_score,
                "final_adjusted_score": row.final_adjusted_score, "z_score": row.z_score,
                "indice_coerenza": row.indice_coerenza, "userId": row.userId
            }
        
        # Query per recuperare i dettagli delle variabili
        query_vars = f"SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.valutazione_pitch_view` WHERE document_id IN (SELECT document_id FROM `{PROJECT_ID}.{DATASET_ID}.calcoli_aggiuntivi_view` WHERE userId = @user_id)"
        rows_vars = bq_client.query(query_vars, job_config=job_config).result()
        for row in rows_vars:
            doc_id = row.document_id
            if doc_id in all_grouped_data:
                parsed_motivation = json.loads(row.motivazione_variabile) if isinstance(row.motivazione_variabile, str) else row.motivazione_variabile
                all_grouped_data[doc_id]["variables"].append({"nome_variabile": row.nome_variabile, "punteggio_variabile": row.punteggio_variabile, "motivazione_variabile": parsed_motivation})
        
        # Query per recuperare i dettagli della coerenza
        query_coh = f"SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.pitch_coherence_view` WHERE document_id IN (SELECT document_id FROM `{PROJECT_ID}.{DATASET_ID}.calcoli_aggiuntivi_view` WHERE userId = @user_id)"
        rows_coh = bq_client.query(query_coh, job_config=job_config).result()
        for row in rows_coh:
            doc_id = row.document_id
            if doc_id in all_grouped_data:
                parsed_motivation = json.loads(row.motivazione_coppia) if isinstance(row.motivazione_coppia, str) else row.motivazione_coppia
                all_grouped_data[doc_id]["coherence_pairs"].append({"nome_coppia": row.nome_coppia, "punteggio_coppia": row.punteggio_coppia, "motivazione_coppia": parsed_motivation})
        
        return json.dumps(all_grouped_data), 200, headers

    except Exception as e:
        print(f"Errore nella funzione get_dashboard_data: {e}")
        return json.dumps({"error": str(e)}), 500, headers

@functions_framework.cloud_event
def process_pitch_deck(cloud_event):
    """
    Funzione principale triggerata dal caricamento di un file su Cloud Storage.
    Orchestra l'intero processo: estrazione testo, analisi, calcoli e salvataggio.
    """
    try:
        event_data = cloud_event.data
        bucket_name = event_data["bucket"]
        file_name = event_data["name"]
        print(f"Triggered by file: gs://{bucket_name}/{file_name}")

        if not file_name.lower().endswith('.pdf'):
            print(f"Skipping non-PDF file: {file_name}.")
            return {"status": "skipped", "message": "Not a PDF file."}

        storage_client = storage.Client()
        input_bucket = storage_client.bucket(bucket_name)
        input_blob = input_bucket.blob(file_name)
        
        # Identifica l'utente tramite i metadati del file
        input_blob.reload()
        user_email_from_metadata = (input_blob.metadata or {}).get('user_email')
        user_id_for_firestore = None

        if user_email_from_metadata:
            try:
                user_record = auth.get_user_by_email(user_email_from_metadata)
                user_id_for_firestore = user_record.uid
                print(f"Associando il pitch all'utente Firebase (email): {user_email_from_metadata} (UID: {user_id_for_firestore})")
            except auth.UserNotFoundError:
                print(f"WARNING: Utente Firebase '{user_email_from_metadata}' non trovato.")
            except Exception as e:
                print(f"ERROR: Errore durante il recupero UID per '{user_email_from_metadata}': {e}.")
        else:
            print("Metadato 'user_email' non presente nel blob.")

        # Controlla se l'utente è nella lista di esclusione
        if user_id_for_firestore and user_id_for_firestore == UID_excluded:
            print(f"Utente con UID '{user_id_for_firestore}' è nella lista di esclusione. Interruzione.")
            return {"status": "excluded", "message": "User is on the exclusion list."}
        
        # Estrae il testo dal PDF
        pdf_content = io.BytesIO(input_blob.download_as_bytes())
        reader = PyPDF2.PdfReader(pdf_content)
        all_text = "".join(page.extract_text() for page in reader.pages if page.extract_text())
        all_text = all_text.replace('\n\n', '\n').strip()
        print(f"Testo estratto dal PDF (primi 500 caratteri): {all_text[:500]}...")

        # --- MODIFICA ARCHITETTURALE: Generazione sommario con Gemini ---
        executive_summary = None  # Inizializza la variabile
        try:
            print("INFO: Inizio della generazione del riassunto con Gemini.")
            gemini_model = GenerativeModel("gemini-pro")
            prompt_summary = f"""Sei un analista finanziario esperto. Il tuo compito è analizzare il testo di un pitch deck e creare un riassunto conciso.
Basandoti sul seguente testo estratto da un pitch deck, genera un riassunto dell'idea di business in un massimo di 3 righe.
Il riassunto deve essere chiaro, diretto e catturare l'essenza del prodotto, il problema che risolve e il suo target principale.

Testo del Pitch Deck:
---
{all_text}
---
"""
            response_summary = gemini_model.generate_content(prompt_summary)
            executive_summary = response_summary.text
            
            print("--- RIASSUNTO GENERATO DA GEMINI ---")
            print(executive_summary)
            print("------------------------------------")
        except Exception as e:
            print(f"ERRORE durante la generazione del riassunto con Gemini: {e}")
            executive_summary = "Riassunto non disponibile a causa di un errore."

        # Esegue l'analisi principale tramite l'IA
        analysis_result = analyze_pitch_deck_with_gpt(all_text)
        
        if not analysis_result:
            print("Errore: L'analisi GPT non ha prodotto risultati validi.")
            return {"status": "error", "message": "Analysis failed or returned invalid data."}

        # Aggiunge il sommario ai dati dell'analisi
        analysis_result['executive_summary'] = executive_summary

        # Esegue i calcoli aggiuntivi e formatta i dati finali
        final_analysis = perform_additional_calculations(analysis_result)
        clean_file_name = os.path.splitext(os.path.basename(file_name))[0]
        final_analysis['document_name'] = os.path.basename(file_name)

        # Salva i risultati su Firestore
        if not save_to_firestore(clean_file_name, final_analysis, user_id=user_id_for_firestore):
            return {"status": "error", "message": "Failed to save analysis to Firestore."}
        
        # Salva una copia dei risultati su un bucket di output e cancella il file di input
        output_folder = f"user_analyses/{user_id_for_firestore}" if user_id_for_firestore else "public_analyses"
        output_blob_name = f"{output_folder}/{clean_file_name}_analysis_result.json"
        output_bucket_name = "validatr-pitch-decks-output"
        output_bucket = storage_client.bucket(output_bucket_name)
        output_blob = output_bucket.blob(output_blob_name)

        output_blob.upload_from_string(json.dumps(final_analysis, indent=2), content_type='application/json')
        print(f"Analisi completa salvata in gs://{output_bucket_name}/{output_blob_name}")
        
        input_blob.delete()
        print(f"File di input {file_name} eliminato.")

        return {"status": "success", "message": "PDF processed, analysis saved."}

    except Exception as e:
        print(f"ERRORE GENERALE NON CATTURATO: {e}")
        return {"status": "error", "message": f"An unexpected error occurred: {e}."}
