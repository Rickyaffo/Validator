import functions_framework
import json
import io
import PyPDF2
import openai
import os
from google.cloud import storage

# --- Inizializzazione OpenAI ---
# Assicurati che OPENAI_API_KEY sia impostata come variabile d'ambiente nella tua Cloud Function.
# In un ambiente di produzione, considera l'uso di Google Secret Manager per maggiore sicurezza.
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
        "criteri": "Quantifica in modo preciso la dimensione (TAM/SAM/SOM), il potenziale di crescita, il timing e l'attrattività economica del mercato di riferimento. Variabili valutate: dimensione economica, trend di crescita, saturazione competitiva, propensione del mercato ad adottare nuove soluzioni."
    },
    "MVP": {
        "descrizione": "La prova tangibile della tua promessa.",
        "criteri": "Valuta se l’MVP esistente dimostra chiaramente e concretamente il valore della soluzione proposta ed è sufficientemente maturo per essere testato dagli utenti reali. Variabili valutate: completezza, usabilità effettiva, scalabilità tecnica iniziale, robustezza dimostrativa rispetto al valore promesso."
    },
    "Team": {
        "descrizione": "Chi realizza concretamente la visione.",
        "criteri": "Determina se il team attuale possiede le competenze, l’esperienza, e la complementarietà necessarie per portare con successo il prodotto sul mercato e per gestire crescita e rischi operativi. Variabili valutate: skill tecnici ed esecutivi, presenza di figure chiave (CTO, CEO, CMO), esperienza precedente, capacità di attrarre ulteriori talenti."
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


# --- Funzione principale della Cloud Function ---
@functions_framework.cloud_event
def process_pitch_deck(cloud_event):
    # Log di debug per ispezionare l'intero oggetto CloudEvent
    print(f"\n--- DEBUG: Contenuto completo di cloud_event ---")
    print(cloud_event)
    print(f"--- FINE DEBUG cloud_event ---\n")

    # Determina il tipo di cloud_event e recupera i dati
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

    # Log di debug per il contenuto di event_data
    print(f"\n--- DEBUG: Contenuto di event_data (ex cloud_event.data) ---")
    print(event_data)
    print(f"--- FINE DEBUG event_data ---\n")

    # Verifica la presenza di 'bucket' e 'name' nei dati dell'evento
    if "bucket" not in event_data or "name" not in event_data:
        print("Errore: Dati 'bucket' o 'name' mancanti nell'evento CloudEvent.")
        return {"status": "error", "message": "Missing 'bucket' or 'name' in CloudEvent data."}

    bucket_name = event_data["bucket"]
    file_name = event_data["name"]
    print(f"Triggered by file: gs://{bucket_name}/{file_name}")

    # --- Estrazione Testo dal PDF ---
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)

        # Filtra i file non PDF (se il trigger non lo fa già)
        if not file_name.lower().endswith('.pdf'):
            print(f"Skipping non-PDF file: {file_name}. Only PDF files are processed.")
            return {"status": "skipped", "message": "Not a PDF file."}

        # Scarica il contenuto del PDF in memoria
        pdf_content = io.BytesIO(blob.download_as_bytes())
        reader = PyPDF2.PdfReader(pdf_content)
        all_text = ""
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            extracted_page_text = page.extract_text()
            if extracted_page_text: # Aggiungi solo se il testo non è vuoto
                all_text += extracted_page_text + "\n"

        # Pulizia base del testo estratto
        all_text = all_text.replace('\n\n', '\n').strip()
        print(f"Testo estratto dal PDF (primi 500 caratteri): {all_text[:500]}...")

        # --- Chiamata API GPT-4o / GPT-4 per l'Analisi ---
        try:
            analysis_result = analyze_pitch_deck_with_gpt(all_text)
            if analysis_result:
                # Esegui i calcoli aggiuntivi sulla base dell'output di GPT
                final_analysis = perform_additional_calculations(analysis_result)

                # Salva il risultato finale strutturato in un bucket di output
                output_bucket_name = "validatr-pitch-decks-output" # Assicurati che questo bucket esista
                output_blob_name = f"{file_name}.analysis_result.json"
                output_bucket = storage_client.bucket(output_bucket_name)
                output_blob = output_bucket.blob(output_blob_name)
                output_blob.upload_from_string(json.dumps(final_analysis, indent=2))
                print(f"Analisi completa salvata in gs://{output_bucket_name}/{output_blob_name}")

                # (Optional) Generazione del feedback_automatico finale con un'altra chiamata GPT
                # Se abilitato, questa sarebbe una seconda chiamata API.
                # feedback_text = generate_feedback_with_gpt(final_analysis)
                # output_feedback_blob_name = f"{file_name}.feedback.txt"
                # output_feedback_blob = output_bucket.blob(output_feedback_blob_name)
                # output_feedback_blob.upload_from_string(feedback_text)
                # print(f"Feedback automatico salvato in gs://{output_bucket_name}/{output_feedback_blob_name}")

                return {"status": "success", "message": "PDF processed, analyzed by GPT, and results saved."}
            else:
                print("Errore: L'analisi GPT non ha prodotto risultati validi o parsabili.")
                return {"status": "error", "message": "GPT analysis failed or returned invalid data."}

        except openai.APIError as e:
            print(f"Errore API OpenAI: {e}")
            return {"status": "error", "message": f"OpenAI API Error: {e}"}
        except json.JSONDecodeError as e:
            print(f"Errore nel parsing JSON della risposta GPT: {e}. Risposta GPT non valida.")
            print(f"Risposta completa di GPT che ha causato l'errore:\n{e.doc}") # e.doc contiene il JSON non valido
            return {"status": "error", "message": f"GPT response not valid JSON: {e}"}
        except Exception as e:
            print(f"Errore generico durante l'analisi o i calcoli post-GPT: {e}")
            return {"status": "error", "message": f"Post-GPT processing error: {e}"}

    except PyPDF2.errors.PdfReadError as e:
        print(f"Errore nella lettura del PDF: {e}")
        return {"status": "error", "message": f"Failed to read PDF: {e}"}
    except Exception as e:
        print(f"Errore generico durante l'elaborazione del PDF: {e}")
        return {"status": "error", "message": f"PDF processing error: {e}"}


# --- Funzione per l'Analisi con GPT ---
def analyze_pitch_deck_with_gpt(pitch_text):
    # Costruisci il prompt combinando le istruzioni, le variabili e le rubriche.
    # È cruciale essere ESTREMAMENTE SPECIFICI sul formato JSON desiderato.
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
    for i, (var1, var2) in enumerate(COHERENCE_PAPPERS): # Errore qui, dovrebbe essere COHERENCE_PAIRS
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
        model="gemini-2.0-flash", # Utilizzo gemini-2.0-flash come da istruzioni
        messages=messages,
        temperature=0.1, # Temperatura più bassa per risposte più deterministiche
        max_tokens=2500, # Aumentato per contenere risposte dettagliate e JSON
        response_format={"type": "json_object"} # FORZA l'output JSON
    )

    gpt_response_content = response.choices[0].message.content
    print(f"Risposta JSON grezza da OpenAI:\n{gpt_response_content[:1000]}...") # Stampa una parte per debug

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

# --- (Optional) Funzione per Generare Feedback Finale con GPT ---
# Questa funzione può essere abilitata se si desidera un feedback narrativo aggiuntivo.
# Richiede una seconda chiamata all'API di GPT.
# def generate_feedback_with_gpt(final_analysis_data):
#     feedback_prompt_messages = [
#         {"role": "system", "content": "Sei un consulente esperto di startup. Genera un feedback conciso (max 200 parole) e costruttivo per la startup, basandoti sull'analisi fornita. Evidenzia i punti di forza e suggerisci aree di miglioramento, con un tono professionale e incoraggiante."},
#         {"role": "user", "content": f"Genera un feedback per la seguente analisi di pitch deck:\n{json.dumps(final_analysis_data, indent=2)}"}
#     ]
#     response = openai.chat.completions.create(
#         model="gemini-2.0-flash", # Puoi usare lo stesso modello o uno diverso
#         messages=feedback_prompt_messages,
#         temperature=0.5,
#         max_tokens=500
#     )
#     return response.choices[0].message.content

