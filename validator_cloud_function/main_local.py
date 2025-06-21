import functions_framework
import json
import io
import PyPDF2
import openai
import os

openai.api_key = os.environ.get("OPEN_API_KEY")

@functions_framework.cloud_event
def process_pitch_deck(cloud_event):
    file_name = "simulated_MagnaEasyPitch.pdf"

    if "data" in cloud_event:
        data = cloud_event.data
        bucket_name = data["bucket"]
        file_name = data["name"]
        print(f"Triggered by file: gs://{bucket_name}/{file_name}")
        pass

    simulated_pdf_text = """
    MAGNA EASY: La tua app di organizzazione alimentare, "SENZA STRESS".

    PROBLEMA:
    - TEMPO: Tra lavoro e studio, il giorno vola e non ci rimane un minuto.
    - GESTIONE CIBO: Scegliere cosa cucinare e ricordare cosa c'è in frigo diventa un peso.

    SOLUZIONE:
    - PLANNER AUTOMATICO: Pasti pianificati in base alle tua routine-esigenza senza sforzo.
    - INVENTARIO VIRTUALE: Controllo della tua credenza.
    - LISTA SPESA SMART: Supportata con AI, Generata in automatico.
    - Alert dei pasti in scadenza.
    - RICETTE PERSONALIZZATE: Adatta le tue esigenze e abitudini alimentari.
    - ACQUISTO DIRETTO: Comparazione prezzi integrata.

    VALIDAZIONE DEL MERCATO / POTENZIALE DI MERCATO:
    - Crescita Mercato Food degli ultimi 10 anni: +69%.
    - 75% usano app food e/o salute alimentare, di cui 40% programmano i pasti settimanali e provano nuove ricette.
    - 20% Giovani lavoratori (25-40 anni) alla ricerca attiva di una soluzione per semplificare la gestione dei pasti.
    - SOM (Mercato iniziale italiano): €10M.
    - SAM (Segmento accessibile europeo): €2 Miliardi.
    - TAM (Mercato totale del food service): €21,05 trilioni.

    ANALISI COMPETITIVA: MagnaEasy si posiziona tra flessibilità e costo rispetto a Justeat, Hellofresh, Samsung food, Mr.cook, Meallime, Yuka, Nowase, To good to go.

    BUSINESS MODEL:
    - Freemium: Gratis con fee sulla spesa, Pubblicità mirata.
    - Premium: 7,99€/mese o 69,99€/anno.
    - Partnership GDO: Promozione prodotti a marchio.

    ROADMAP (Costi e Ricavi):
    - Costi Anno 1-3: Generali (9.6%), Sviluppo (22.6%), Marketing (67.0%).
    - Ricavi Anno 1: 0€, Anno 2: circa 1.5M, Anno 3: circa 2.5M.
    - Fase 1 (2025): MVP base + customer base.
    - Fase 2 (2026): Sviluppo features, aumento customer base + aumento frequenza d'uso.
    - Fase 3 (2027): Partnership supermercati + Ambassador.

    IL NOSTRO TEAM:
    - ELISA MAGNANI: Design Strategist & Co-Fondatore, Design CMF, Lamborghini.
    - RICCARDO AFFOLTER: CTO & Co-Fondatore, Data Engineer, Credem (techstars).
    - FABIO VIRGILIO: CMO & Co-Fondatore, Marketing Strategist.
    - EMANUELE FERRARESI: Business Specialist & Co-Fondatore.
    - MATTEO GRASSELLI: Commercial Director & Co-Fondatore.
    """
    
    max_text_length = 15000 
    if len(simulated_pdf_text) > max_text_length:
        extracted_text = simulated_pdf_text[:max_text_length] + "\n... [Testo troncato per limite di token]"
    else:
        extracted_text = simulated_pdf_text

    extracted_text = extracted_text.replace('\n\n', '\n').strip() 

    print(f"Testo estratto (parziale): {extracted_text[:15000]}...")

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
        print(f"Content-Type: {type(raw_json_output)}") # Verifichiamo che sia una stringa
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