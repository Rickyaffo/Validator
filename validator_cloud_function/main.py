import functions_framework
import json
import io
import PyPDF2
import openai
import os
from google.cloud import storage # Importa la libreria di Google Cloud Storage

openai.api_key = os.environ.get("OPEN_API_KEY")

@functions_framework.cloud_event
def process_pitch_deck(cloud_event):
    # Logica per l'evento Cloud Storage
    print(cloud_event)
     # Aggiungi questo per ispezionare il tipo di cloud_event
    print(f"--- DEBUG: Tipo di cloud_event: {type(cloud_event)} ---")

    # Controlla se 'data' è un attributo dell'oggetto o una chiave di dizionario
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
    
    # Assicurati che 'bucket' e 'name' siano presenti nell'evento
    if "bucket" not in event_data or "name" not in event_data:
        print("Errore: Dati 'bucket' o 'name' mancanti nell'evento CloudEvent.")
        return {"status": "error", "message": "Missing 'bucket' or 'name' in CloudEvent data."}

    bucket_name = event_data["bucket"]
    file_name = event_data["name"]
    print(f"Triggered by file: gs://{bucket_name}/{file_name}")

    # --- Implementazione lettura PDF da GCS ---
    extracted_text = ""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)

        # Scarica il contenuto del file in memoria
        pdf_content = blob.download_as_bytes()
        
        # Usa io.BytesIO per trattare il contenuto come un file in memoria
        pdf_file_object = io.BytesIO(pdf_content)
        
        pdf_reader = PyPDF2.PdfReader(pdf_file_object)
        
        # Estrai il testo da tutte le pagine
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            extracted_text += page.extract_text() + "\n" # Aggiungi un newline tra le pagine

        # Pulizia base del testo estratto
        extracted_text = extracted_text.replace('\n\n', '\n').strip()
        print(f"Testo estratto (parziale): {extracted_text[:500]}...")

    except Exception as e:
        print(f"Errore durante la lettura o parsing del PDF da GCS: {e}")
        return {"status": "error", "message": f"Error processing PDF from GCS: {e}"}
    # --- Fine Implementazione lettura PDF da GCS ---


    max_text_length = 15000 
    if len(extracted_text) > max_text_length:
        extracted_text = extracted_text[:max_text_length] + "\n... [Testo troncato per limite di token]"
    
    # Il resto del tuo codice per la chiamata OpenAI e il parsing JSON rimane INVARIATO
    # ... (tutto il codice dal prompt_template in giù, inclusi i messaggi e le chiamate OpenAI) ...
    
    # Assicurati che il tuo prompt_template sia quello corretto con le parentesi graffe escapate ({{...}})
    prompt_template = """
    Analizza il seguente testo estratto da un pitch deck e valuta attentamente le 7 dimensioni chiave: "Problema", "Target", "Soluzione", "Mercato", "MVP", "Team", "Expected Return".

    Per ogni dimensione, assegna un "score" da 0 a 100 basandoti sulla completezza, chiarezza e rilevanza delle informazioni fornite nel pitch. Fornisci una breve "motivazione" concisa (massimo 2 frasi) che giustifichi il punteggio assegnato, facendo riferimento a elementi specifici del testo.

    **Rubrica per i punteggi (applica questa logica):**
    - 0-20: Mancante o completamente irrilevante.
    - 21-40: Presente ma estremamente debole, vago o incoerente.
    - 41-60: Accettabile ma con gravi lacune, ambiguità o necessità di maggiori dettagli.
    - 61-80: Buono, chiaro e convincente, con piccoli margini di miglioramento.
    - 81-100: Eccellente, altamente credibile, ben articolato e supportato da dettagli solidi.

    Valuta inoltre la coerenza tra le seguenti 21 coppie di dimensioni. Indica "✅" (coerente), "⛔" (incoerente), o "⬜" (neutrale/non chiaro o non abbastanza informazioni per giudicare). Fornisci una breve "spiegazione" (massimo 1 frase) per ogni valutazione di coerenza.

    **Coppie per la coerenza (chiavi per 'coerenza_matrice'):**
    - Problema vs Target
    - Problema vs Soluzione
    - Problema vs Mercato
    - Problema vs MVP
    - Problema vs Team
    - Problema vs Expected Return
    - Target vs Soluzione
    - Target vs Mercato
    - Target vs MVP
    - Target vs Team
    - Target vs Expected Return
    - Soluzione vs Mercato
    - Soluzione vs MVP
    - Soluzione vs Team
    - Soluzione vs Expected Return
    - Mercato vs MVP
    - Mercato vs Team
    - Mercato vs Expected Return
    - MVP vs Team
    - MVP vs Expected Return
    - Team vs Expected Return

    **L'output DEVE essere un JSON valido e COMPLETO. Non includere alcun testo, commento o carattere aggiuntivo prima o dopo il blocco JSON. Assicurati che TUTTE le chiavi siano stringhe JSON standard, senza caratteri di newline, spazi o virgolette extra al loro interno (es. "Problema" e non "\n \"Problema\"").**

    ```json
    {{
      "Problema": {{
        "score": N,
        "motivazione": "Testo motivazione."
      }},
      "Target": {{
        "score": N,
        "motivazione": "Testo motivazione."
      }},
      "Soluzione": {{
        "score": N,
        "motivazione": "Testo motivazione."
      }},
      "Mercato": {{
        "score": N,
        "motivazione": "Testo motivazione."
      }},
      "MVP": {{
        "score": N,
        "motivazione": "Testo motivazione."
      }},
      "Team": {{
        "score": N,
        "motivazione": "Testo motivazione."
      }},
      "Expected Return": {{
        "score": N,
        "motivazione": "Testo motivazione."
      }},
      "coerenza_matrice": {{
        "Problema vs Target": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Problema vs Soluzione": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Problema vs Mercato": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Problema vs MVP": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Problema vs Team": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Problema vs Expected Return": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Target vs Soluzione": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Target vs Mercato": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Target vs MVP": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Target vs Team": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Target vs Expected Return": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Soluzione vs Mercato": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Soluzione vs MVP": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Soluzione vs Team": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Soluzione vs Expected Return": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Mercato vs MVP": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Mercato vs Team": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Mercato vs Expected Return": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "MVP vs Team": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "MVP vs Expected Return": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}},
        "Team vs Expected Return": {{"status": "SYMBOL", "spiegazione": "Breve spiegazione."}}
      }}
    ```
    Testo del Pitch Deck da analizzare:
    {pitch_text_content}
    """

    messages = [
        {"role": "system", "content": "Sei un analista di startup esperto nella valutazione di pitch deck. Estrai le informazioni in modo oggettivo e preciso, fornendo score e motivazioni basate su rubriche standard. Valuta la coerenza. L'output deve essere un JSON valido e completo secondo la struttura fornita, con un massimo di 2 frasi per le motivazioni dei punteggi e 1 frase per le spiegazioni di coerenza. **Assicurati che tutte le chiavi JSON siano stringhe pulite e semplici, senza caratteri speciali come newline o virgolette aggiuntive, e che l'output sia SOLO il blocco JSON senza testo pre/post o commenti.**"},
        {"role": "user", "content": prompt_template.format(pitch_text_content=extracted_text)}
    ]

    try:
        if not openai.api_key:
            raise ValueError("OPENAI_API_KEY non configurata. Impostala come variabile d'ambiente 'OPENAI_API_KEY'.")

        print("Chiamata API OpenAI in corso...")
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo-0125",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1
        )

        raw_json_output = response.choices[0].message.content
        
        print(f"\n--- DEBUG: Output RAW di GPT prima del parsing ---")
        print(f"Content-Type: {type(raw_json_output)}")
        print(f"Length: {len(raw_json_output)}")
        print(f"Raw Output:\n{raw_json_output}\n--- FINE DEBUG RAW OUTPUT ---\n")

        try:
            extracted_data_from_ai = json.loads(raw_json_output)
            print("\n--- Output JSON ricevuto da GPT e validato ---")
            print(json.dumps(extracted_data_from_ai, indent=2))
            
            return {
                "status": "success",
                "extracted_data": extracted_data_from_ai,
                "file_processed": file_name
            }
        except json.JSONDecodeError as e:
            print(f"\n--- Errore nel parsing JSON da GPT ---")
            print(f"Dettagli errore JSONDecodeError: {e}")
            print(f"Output raw che ha causato l'errore: {raw_json_output}") 
            return {"status": "error", "message": "Invalid JSON from OpenAI", "raw_output": raw_json_output}

    except openai.AuthenticationError as e:
        print(f"\n--- ERRORE AUTENTICAZIONE OpenAI ---")
        print(f"Assicurati che la variabile d'ambiente OPENAI_API_KEY sia impostata correttamente.")
        print(f"Dettagli errore: {e}")
        return {"status": "error", "message": f"Authentication Error: {e}"}
    except Exception as e:
        print(f"\n--- ERRORE GENERICO ---")
        print(f"Errore nella chiamata OpenAI o nell'elaborazione: {e}")
        return {"status": "error", "message": str(e)}