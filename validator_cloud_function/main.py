import functions_framework
import json
import io
import PyPDF2 # Per l'estrazione reale da PDF
import openai
import os

# Per i test locali, carica la chiave API da una variabile d'ambiente
# In produzione su Cloud Functions, useremo Google Secret Manager per la sicurezza.
openai.api_key = os.environ.get("OPENAI_API_KEY")

@functions_framework.cloud_event
def process_pitch_deck(cloud_event):
    """
    Cloud Function che si attiva al caricamento di un file PDF in Cloud Storage.
    Estrae il testo (simulato per test), lo invia a GPT-3.5 Turbo per l'analisi e genera un JSON.
    """
    
    # Questo blocco simula l'input di Cloud Storage per i test locali
    # Quando la funzione sarà deployata, `cloud_event.data` conterrà i metadati del file
    file_name = "simulated_MagnaEasyPitch.pdf" # Nome file per log di test

    if "data" in cloud_event:
        # Questo ramo si attiverà quando la funzione sarà deployata su GCP e triggerata da GCS
        # Qui dovrai integrare il codice per scaricare il PDF dal bucket e usare PyPDF2
        data = cloud_event.data
        bucket_name = data["bucket"]
        file_name = data["name"]
        print(f"Triggered by file: gs://{bucket_name}/{file_name}")
        
        # --- LOGICA REALE PER SCARICARE E PARSARE PDF DA GCS (da implementare in futuro) ---
        # from google.cloud import storage
        # storage_client = storage.Client()
        # bucket = storage_client.bucket(bucket_name)
        # blob = bucket.blob(file_name)
        # pdf_bytes = blob.download_as_bytes()
        # pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        # extracted_text = ""
        # for page_num in range(len(pdf_reader.pages)):
        #     page_text = pdf_reader.pages[page_num].extract_text()
        #     if page_text:
        #         extracted_text += page_text.strip() + "\n"
        # -----------------------------------------------------------------------------------
        
        # Per i test locali, continueremo a usare il testo hardcoded sotto,
        # anche se l'evento è simulato.
        # Quando deployerai, questa sezione verrà sostituita dalla logica di download/parsing.
        pass # placeholder

    # --- CONTENUTO DEL PDF DI ESEMPIO "12_MagnaEasyPitch.pdf" ESTRATTO TESTUALMENTE ---
    # Ho estratto manualmente il testo più rilevante dalle pagine del PDF per la simulazione.
    # Questo è l'input che GPT-3.5 Turbo "leggerà".
    simulated_pdf_text = """
    MAGNA EASY: La tua app di organizzazione alimentare, "SENZA STRESS". [cite: 1]

    PROBLEMA:
    - TEMPO: Tra lavoro e studio, il giorno vola e non ci rimane un minuto. [cite: 2]
    - GESTIONE CIBO: Scegliere cosa cucinare e ricordare cosa c'è in frigo diventa un peso. [cite: 3]

    SOLUZIONE:
    - PLANNER AUTOMATICO: Pasti pianificati in base alle tua routine-esigenza senza sforzo. [cite: 4]
    - INVENTARIO VIRTUALE: Controllo della tua credenza. [cite: 4]
    - LISTA SPESA SMART: Supportata con AI, Generata in automatico. [cite: 4]
    - Alert dei pasti in scadenza. [cite: 4]
    - RICETTE PERSONALIZZATE: Adatta le tue esigenze e abitudini alimentari. [cite: 4]
    - ACQUISTO DIRETTO: Comparazione prezzi integrata. [cite: 4]

    VALIDAZIONE DEL MERCATO / POTENZIALE DI MERCATO:
    - Crescita Mercato Food degli ultimi 10 anni: +69%. [cite: 5]
    - 75% usano app food e/o salute alimentare, di cui 40% programmano i pasti settimanali e provano nuove ricette. [cite: 5]
    - 20% Giovani lavoratori (25-40 anni) alla ricerca attiva di una soluzione per semplificare la gestione dei pasti. [cite: 5]
    - SOM (Mercato iniziale italiano): €10M. [cite: 6]
    - SAM (Segmento accessibile europeo): €2 Miliardi. [cite: 6]
    - TAM (Mercato totale del food service): €21,05 trilioni. [cite: 6]

    ANALISI COMPETITIVA: MagnaEasy si posiziona tra flessibilità e costo rispetto a Justeat, Hellofresh, Samsung food, Mr.cook, Meallime, Yuka, Nowase, To good to go. [cite: 7, 8, 9]

    BUSINESS MODEL:
    - Freemium: Gratis con fee sulla spesa, Pubblicità mirata. [cite: 9]
    - Premium: 7,99€/mese o 69,99€/anno. [cite: 9]
    - Partnership GDO: Promozione prodotti a marchio. [cite: 9]

    ROADMAP (Costi e Ricavi):
    - Costi Anno 1-3: Generali (9.6%), Sviluppo (22.6%), Marketing (67.0%). [cite: 10]
    - Ricavi Anno 1: 0€, Anno 2: circa 1.5M, Anno 3: circa 2.5M. [cite: 10]
    - Fase 1 (2025): MVP base + customer base. [cite: 10]
    - Fase 2 (2026): Sviluppo features, aumento customer base + aumento frequenza d'uso. [cite: 10]
    - Fase 3 (2027): Partnership supermercati + Ambassador. [cite: 10]

    IL NOSTRO TEAM:
    - ELISA MAGNANI: Design Strategist & Co-Fondatore, Design CMF, Lamborghini. [cite: 12]
    - RICCARDO AFFOLTER: CTO & Co-Fondatore, Data Engineer, Credem (techstars). [cite: 12]
    - FABIO VIRGILIO: CMO & Co-Fondatore, Marketing Strategist. [cite: 12]
    - EMANUELE FERRARESI: Business Specialist & Co-Fondatore. [cite: 12]
    - MATTEO GRASSELLI: Commercial Director & Co-Fondatore. [cite: 12]
    """
    
    # Limita la lunghezza del testo per non superare il limite di token di GPT
    max_text_length = 15000 
    if len(simulated_pdf_text) > max_text_length:
        extracted_text = simulated_pdf_text[:max_text_length] + "\n... [Testo troncato per limite di token]"
    else:
        extracted_text = simulated_pdf_text

    print(f"Testo estratto (parziale): {extracted_text[:500]}...") # Logga i primi 500 caratteri

    # 2. Prompt Engineering per l'AI (con GPT-3.5 Turbo)
    # Ho reso il prompt ancora più robusto basandomi sulle tue rubriche e sull'output desiderato.
    prompt_template = """
    Analizza il seguente testo estratto da un pitch deck e valuta attentamente le 7 dimensioni chiave: "Problema", "Target", "Soluzione", "Mercato", "MVP", "Team", "Expected Return".

    Per ogni dimensione, assegna un "score" da 0 a 100 basandoti sulla completezza, chiarezza e rilevanza delle informazioni fornite nel pitch. Fornisci una "motivazione" concisa (max 2 frasi) che giustifichi il punteggio assegnato, facendo riferimento a elementi specifici del testo.

    **Rubrica per i punteggi (applica questa logica):**
    - 0-20: Mancante o completamente irrilevante.
    - 21-40: Presente ma estremamente debole, vago o incoerente.
    - 41-60: Accettabile ma con gravi lacune, ambiguità o necessità di maggiori dettagli.
    - 61-80: Buono, chiaro e convincente, con piccoli margini di miglioramento.
    - 81-100: Eccellente, altamente credibile, ben articolato e supportato da dettagli solidi.

    Valuta inoltre la coerenza tra le seguenti 21 coppie di dimensioni. Indica "✅" (coerente), "⛔" (incoerente), o "⬜" (neutrale/non chiaro o non abbastanza informazioni per giudicare). Fornisci una breve "spiegazione" (max 1 frase) per ogni valutazione di coerenza.

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

    **Il formato dell'output deve essere un JSON valido e completo, esattamente come segue:**

    ```json
    {
      "Problema": {
        "score": N,
        "motivazione": "Testo motivazione."
      },
      "Target": {
        "score": N,
        "motivazione": "Testo motivazione."
      },
      "Soluzione": {
        "score": N,
        "motivazione": "Testo motivazione."
      },
      "Mercato": {
        "score": N,
        "motivazione": "Testo motivazione."
      },
      "MVP": {
        "score": N,
        "motivazione": "Testo motivazione."
      },
      "Team": {
        "score": N,
        "motivazione": "Testo motivazione."
      },
      "Expected Return": {
        "score": N,
        "motivazione": "Testo motivazione."
      },
      "coerenza_matrice": {
        "Problema vs Target": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Problema vs Soluzione": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Problema vs Mercato": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Problema vs MVP": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Problema vs Team": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Problema vs Expected Return": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Target vs Soluzione": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Target vs Mercato": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Target vs MVP": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Target vs Team": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Target vs Expected Return": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Soluzione vs Mercato": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Soluzione vs MVP": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Soluzione vs Team": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Soluzione vs Expected Return": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Mercato vs MVP": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Mercato vs Team": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Mercato vs Expected Return": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "MVP vs Team": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "MVP vs Expected Return": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."},
        "Team vs Expected Return": {"status": "SYMBOL", "spiegazione": "Breve spiegazione."}
      }
    }
    ```
    Testo del Pitch Deck da analizzare:
    {pitch_text_content}
    """

    messages = [
        {"role": "system", "content": "Sei un analista di startup esperto nella valutazione di pitch deck. Estrai le informazioni in modo oggettivo e preciso, fornendo score e motivazioni basate su rubriche standard. Valuta la coerenza. L'output deve essere un JSON valido e completo secondo la struttura fornita, con un massimo di 2 frasi per le motivazioni dei punteggi e 1 frase per le spiegazioni di coerenza."},
        {"role": "user", "content": prompt_template.format(pitch_text_content=extracted_text)}
    ]

    # 3. Chiamata API AI (con modello a basso costo per i test)
    try:
        if not openai.api_key:
            raise ValueError("OPENAI_API_KEY non configurata. Impostala come variabile d'ambiente 'OPENAI_API_KEY'.")

        print("Chiamata API OpenAI in corso...")
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo-0125", # Modello economico per i test
            messages=messages,
            response_format={"type": "json_object"}, # Forza l'output JSON
            temperature=0.1 # Valore basso per risposte più consistenti e meno creative
        )

        raw_json_output = response.choices[0].message.content
        print(f"Risposta raw da OpenAI (primi 500 caratteri):\n{raw_json_output[:500]}...")
        
        # Verifica se l'output è JSON valido
        try:
            extracted_data_from_ai = json.loads(raw_json_output)
            print("\n--- Output JSON ricevuto da GPT e validato ---")
            # A questo punto, puoi stampare il JSON formattato per una facile lettura
            print(json.dumps(extracted_data_from_ai, indent=2))
            
            # Qui andrebbe la logica per salvare in Firestore e fare i calcoli finali
            # Per i test locali, ci fermiamo alla visualizzazione del JSON e al return.

            return {
                "status": "success",
                "extracted_data": extracted_data_from_ai,
                "file_processed": file_name
            }
        except json.JSONDecodeError:
            print(f"\n--- Errore nel parsing JSON da GPT ---")
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