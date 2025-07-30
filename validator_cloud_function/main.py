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

storage_client = storage.Client()


FIREBASE_STORAGE_BUCKET_NAME = "validatr-mvp.firebasestorage.app" 

PREDEFINED_SECTORS = [
    "Pubblica Amministrazione",
    "Automotive",
    "Retail",
    "Finanza e Assicurazioni",
    "Salute e Benessere",
    "Educazione",
    "Tecnologia e Software",
    "Industria Manifatturiera",
    "Altro" # Aggiungi "Altro" come fallback se nessuno degli altri si adatta perfettamente
]

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

# --- Funzione di supporto per scaricare e leggere un PDF (spostata fuori da start_analysis) ---
def get_text_from_storage(file_path_within_bucket):
    """
    Scarica un PDF da Google Cloud Storage (gestito da Firebase) e ne estrae il testo.
    Il file_path_within_bucket deve essere il percorso relativo all'interno del bucket,
    senza il nome del bucket stesso.
    Esempio: "validatr-pitch-decks-input-folder/user_uploads/L8u3dXQezmfvO6Qewla7u1pcbQ63/1753220266831_Sunspeker_Pitch-Deck-2025.pdf"
    """
    if not file_path_within_bucket:
        return ""
    try:
        # Usa il bucket client globale e il nome del bucket definito globalmente
        bucket = storage_client.bucket(FIREBASE_STORAGE_BUCKET_NAME)
        blob = bucket.blob(file_path_within_bucket) 

        # Verifica se il blob esiste prima di tentare il download
        if not blob.exists():
            print(f"Errore: Il blob '{file_path_within_bucket}' non esiste nel bucket '{FIREBASE_STORAGE_BUCKET_NAME}'.")
            raise NotFound(f"Blob not found: {file_path_within_bucket}")

        pdf_content = io.BytesIO(blob.download_as_bytes())
        reader = PyPDF2.PdfReader(pdf_content)
        text = "".join(page.extract_text() for page in reader.pages if page.extract_text())

        # Elimina il file dopo averlo letto
        blob.delete()
        print(f"File elaborato ed eliminato: gs://{FIREBASE_STORAGE_BUCKET_NAME}/{file_path_within_bucket}")
        return text.replace('\n\n', '\n').strip()
    except NotFound as e: # Cattura specificamente l'errore 404 per il file
        print(f"Errore (NotFound): {e}")
        return ""
    except Exception as e:
        print(f"Attenzione: impossibile leggere il file. Errore generico: {e}")
        return ""

def analyze_pitch_deck_with_gpt(pitch_text,has_business_plan=False):
    """
    Costruisce il prompt per l'IA e chiama l'API di OpenAI per l'analisi del pitch.
    Include istruzioni per convalidare le variabili con il business plan, se presente,
    e per identificare il settore.
    """
    system_prompt_content = """Sei un analista esperto nell'analisi e valutazione di pitch deck per startup con background nei principali fondi di investimento per startup come Sequoia Capital, Andreessen Horowitz, P101, 360 capital, Google Ventures, LVenture Group, Y Combinator e CDP Venture Capital SGR di cui utilizzi best practice e approccio.

Il tuo compito è valutare l'opportunità di investimento in startup per determinare quanto è consigliato l'investimento nella startup in esame partendo dal pitch deck fornito. Identifichi 7 variabili chiave, assegnando un punteggio da 0 a 100 a ciascuna variabile basandoti sulle rubriche fornite, fornendo una motivazione dettagliata per ogni punteggio, e valutando la coerenza interna tra specifiche coppie di variabili. Restituisci tutte le informazioni in un formato JSON valido.

Ricorda che dovrai valutare le informazioni ottenute in maniera analitica e critica nella prospettiva di un analista che deve discernere le migliori opportunità di investiemento. Se necessario, includi nel tuo processo di valutazione fonti esterne affidabili per verificare i claim dei pitch deck e fornire una valutazione aggiornata.
"""

    if has_business_plan:
    # Aggiungi le istruzioni specifiche per l'analisi combinata
        system_prompt_content += """

### ISTRUZIONI PER ANALISI DI DUE DILIGENCE (PITCH DECK + BUSINESS PLAN)

**Principio Guida Fondamentale:**
Il Business Plan è la **fonte primaria di verità**. Il Pitch Deck fornisce la visione, ma il Business Plan fornisce le prove. Le tue valutazioni e i tuoi punteggi devono basarsi sulle evidenze concrete e sui dati dettagliati del Business Plan.

**Processo di Valutazione Obbligatorio:**

1.  **Lettura Critica:** Analizza il Pitch Deck per capire le affermazioni principali. Successivamente, esamina il Business Plan con scetticismo professionale per trovare i dati che **supportino o smentiscano** tali affermazioni.

2.  **Priorità Assoluta alle Prove:** Per ogni variabile, la tua motivazione e il tuo punteggio devono partire dai dati del Business Plan. Se un'informazione del Pitch Deck non è supportata da evidenze nel Business Plan, considerala **"non verificata"** e assegna un punteggio inferiore.

3.  **Come Gestire le Discrepanze (Regola di Scrittura):**
    Quando noti una discrepanza tra i due documenti, **evidenziala esplicitamente nella motivazione**. Utilizza una struttura simile a questa:
    * *Esempio*: "La proiezione finanziaria nel Business Plan indica un fatturato di €1M al terzo anno. Questo **ridimensiona in modo significativo** l'ottimistica stima di €5M presentata nel Pitch Deck."
    * *Esempio*: "Il Business Plan identifica tre competitor principali. Questo **fornisce un contesto più realistico** rispetto al Pitch Deck, che descriveva il mercato come 'poco affollato'."
"""


    system_prompt_content += """
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

    # --- NUOVA ISTRUZIONE PER L'IA: Identificazione del Settore ---
    system_prompt_content += f"""

---

### Identificazione del Settore
Basandoti sul contenuto del pitch deck (e del business plan, se presente), identifica il settore di appartenenza della startup. Devi scegliere **UNO SOLO** tra i seguenti settori predefiniti. Se la startup non rientra chiaramente in nessuno di questi, scegli "Altro".
Settori disponibili: {', '.join(PREDEFINED_SECTORS)}

---

### Criteri di Valutazione della Coerenza (0-100)
Valuta la coerenza (0-100) delle seguenti coppie di variabili. Un punteggio di 100 indica perfetta coerenza.
"""

    for i, (var1, var2) in enumerate(COHERENCE_PAIRS):
        pair_tuple = (var1, var2)
        guideline = COHERENCE_GUIDELINES.get(pair_tuple, "Nessuna linea guida specifica.")
        system_prompt_content += f"\n{i+1}. **{var1} - {var2}**: {guideline}"

    # --- AGGIORNAMENTO DEL FORMATO DI OUTPUT JSON ---
    system_prompt_content += """
---

### Formato di Output (JSON)
Il formato JSON di output deve essere ESATTAMENTE come segue. Non includere alcun testo aggiuntivo prima o dopo il blocco JSON.
```json
{
  "settore": "string",  // Nuovo campo per il settore
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
        max_tokens=3800,
        response_format={"type": "json_object"}
    )

    gpt_response_content = response.choices[0].message.content
    print(f"Risposta JSON grezza da OpenAI:\n{gpt_response_content[:1000]}...")

    try:
        parsed_response = json.loads(gpt_response_content)
        # Validazione del settore: assicurati che sia uno dei predefiniti
        if parsed_response.get("settore") not in PREDEFINED_SECTORS:
            print(f"ATTENZIONE: Settore '{parsed_response.get('settore')}' non riconosciuto. Assegnando 'Altro'.")
            parsed_response["settore"] = "Altro"
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
    
def generate_summary_with_openai(pitch_text):
    """
    Usa OpenAI per generare un riassunto conciso del pitch deck in italiano e inglese,
    restituendo un oggetto JSON.    
    """
    try:
        print("INFO: Inizio generazione riassunto con OpenAI.")
        
        system_prompt = """Sei un analista finanziario esperto. Il tuo compito è analizzare il testo di un pitch deck e creare un riassunto conciso.
Restituisci il riassunto come un oggetto JSON con due chiavi: "it" per la versione italiana e "en" per la versione inglese.
Ogni riassunto deve essere di massimo 3 righe e catturare l'essenza del prodotto, il problema che risolve e il suo target principale."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Basandoti su questo testo, crea il riassunto bilingue in formato JSON:\n\n{pitch_text}"}
        ]

        response = openai.chat.completions.create(
            model="gpt-4.1-nano",
            messages=messages,
            temperature=0.1,
            max_tokens=400, 
            response_format={"type": "json_object"} 
        )

        summary = response.choices[0].message.content
        print("--- RIASSUNTO GENERATO DA OPENAI ---")
        print(summary)
        return summary.strip()
        
    except Exception as e:
        print(f"ERRORE durante la generazione del riassunto con OpenAI: {e}")
        return "Riassunto non disponibile a causa di un errore."

@functions_framework.http
def start_analysis(request):
    """
    Funzione triggerata via HTTP che riceve i percorsi dei file,
    unisce il loro testo e avvia l'analisi completa.
    Utilizza l'UID dal token per identificare l'utente.
    """
    # Gestione CORS
    headers = {
        'Access-Control-Allow-Origin': 'https://validatr-mvp.web.app',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '3600'
    }
    if request.method == 'OPTIONS':
        return ('', 204, headers)

    # --- Autenticazione ---
    try:
        auth_header = request.headers.get('Authorization')
        id_token = auth_header.split('Bearer ')[1]
        decoded_token = auth.verify_id_token(id_token, check_revoked=True)
        # Otteniamo l'UID direttamente dal token, è il modo più sicuro
        user_id_for_firestore = decoded_token['uid'] 
        print(f"Analisi richiesta dall'utente autenticato: UID={user_id_for_firestore}")
    except Exception as e:
        print(f"ERRORE di autenticazione: {e}")
        return json.dumps({"error": f"Unauthorized: {e}"}), 401, headers

     # --- Logga tutti i parametri ricevuti nella richiesta ---
    print("--- Inizio Log Parametri Richiesta HTTP per start_analysis ---")
    print(f"Metodo HTTP: {request.method}")
    print(f"Headers della Richiesta: {request.headers}")

    try:
        request_json = request.get_json(silent=True)
        if request_json:
            print(f"Corpo JSON della Richiesta: {json.dumps(request_json, indent=2)}")
        else:
            print("Nessun corpo JSON nella richiesta.")
    except Exception as e:
        print(f"Errore durante il parsing del corpo JSON: {e}")
        print(f"Corpo raw della richiesta: {request.get_data(as_text=True)}") # Logga il corpo raw per debug

    print("--- Fine Log Parametri Richiesta HTTP per start_analysis ---")

    # --- Logica Principale ---
    try:
        request_json = request.get_json(silent=True)
        pitch_deck_path = request_json.get('pitchDeckPath')
        business_plan_path = request_json.get('businessPlanPath')
        original_file_name = request_json.get('originalFileName')

        if not pitch_deck_path or not original_file_name:
            return json.dumps({"error": "Dati mancanti: pitchDeckPath o originalFileName."}), 400, headers
        
        # Controlla se l'utente è nella lista di esclusione
        if user_id_for_firestore and user_id_for_firestore == UID_excluded:
            print(f"Utente con UID '{user_id_for_firestore}' è nella lista di esclusione. Interruzione.")
            # È buona norma eliminare i file caricati anche se l'analisi non parte
            # (omesso per semplicità, ma da considerare in produzione)
            return {"status": "excluded", "message": "User is on the exclusion list."}

        storage_client = storage.Client()
        all_text = ""

        has_business_plan_flag = False

       
        print(f"Tentativo di leggere Pitch Deck da path GCS: {pitch_deck_path} nel bucket {FIREBASE_STORAGE_BUCKET_NAME}")
        all_text += get_text_from_storage(pitch_deck_path)
        
        # Leggi il Business Plan (opzionale)
        if business_plan_path:
            has_business_plan_flag = True # Setta il flag se il business plan è presente
            print(f"Tentativo di leggere Business Plan da path GCS: {business_plan_path} nel bucket {FIREBASE_STORAGE_BUCKET_NAME}")
            all_text += "\n\n--- CONTENUTO DEL BUSINESS PLAN ---\n\n"
            all_text += get_text_from_storage(business_plan_path)

        print(f"Testo combinato estratto (primi 500 caratteri): {all_text[:500]}...")

        # 1. Genera il riassunto
        executive_summary = generate_summary_with_openai(all_text)

        # 2. Esegui l'analisi principale
        analysis_result = analyze_pitch_deck_with_gpt(all_text)
        if not analysis_result:
            raise Exception("L'analisi GPT principale non ha prodotto risultati validi.")
        
        analysis_result['executive_summary'] = executive_summary

        # 3. Esegui i calcoli aggiuntivi
        final_analysis = perform_additional_calculations(analysis_result)
        
        # 4. Usa la stessa metodologia per creare l'ID del documento e il nome
        document_id = os.path.splitext(original_file_name)[0]
        final_analysis['document_name'] = original_file_name

        # 5. Salva su Firestore usando l'UID del token e l'ID del documento
        if not save_to_firestore(document_id, final_analysis, user_id=user_id_for_firestore):
            raise Exception("Salvataggio su Firestore fallito.")

        return json.dumps({"status": "success", "message": "Analysis completed and saved."}), 200, headers

    except Exception as e:
        print(f"ERRORE GENERALE in start_analysis: {e}")
        return json.dumps({"error": f"Internal server error: {str(e)}"}), 500, headers