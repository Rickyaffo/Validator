# VALIDATR™ OS MVP Development

Questo repository contiene lo sviluppo del **Minimum Viable Product (MVP) di VALIDATR™ OS**, un sistema innovativo per la valutazione oggettiva dei pitch deck delle startup, basato su intelligenza artificiale e metriche di business chiare.

L'obiettivo dell'MVP è dimostrare il core value proposition del sistema, automatizzando l'estrazione dati, lo scoring, l'analisi di coerenza e la generazione di feedback basati su un pitch deck PDF.

---

## 🚀 Visione del Progetto (VALIDATR™ OS Completo)

VALIDATR™ OS è un sistema modulare progettato per fornire una valutazione completa e oggettiva della bancabilità di una startup. La sua architettura è pensata per essere scalabile e integrare diverse fonti di dati e analisi avanzate.

**Moduli Chiave:**
* **Data Capture:** Raccolta semi-automatica di informazioni tramite form e upload di pitch deck PDF.
* **AI Scoring Engine:** Assegnazione di punteggi oggettivi (0-100) a dimensioni chiave (Problema, Target, Soluzione, Mercato, MVP, Team, Expected Return) con motivazioni generate da AI.
* **Coherence Engine:** Valutazione della coerenza logica tra le diverse dimensioni del pitch deck (matrice 21 coppie).
* **Signal Tracker (Futuro):** Integrazione di dati reali (es. waitlist, visite sito, ricavi) per un "reality boost" nello score.
* **Explainability & Feedback:** Generazione di un audit dettagliato e suggerimenti mirati per migliorare il pitch.
* **Live Validation Tracker (Futuro):** Monitoraggio delle startup valutate per verificare l'accuratezza predittiva del sistema nel tempo.
* **Return Engine:** Calcolo di metriche finanziarie (IRR, ritorno cash, diluizione) per stimare la bancabilità.
* **Moduli Avanzati (Futuri):** Bias Index, Exit Viability Map, Cross Source Validator, Kill-Test Simulator, Vanity Filter, Semantic Entropy Analyzer, Public Trust Tracker.

Per una descrizione dettagliata del sistema completo, fare riferimento al documento: `GUIDA COMPLETA – COME APPLICARE VALIDATR™ OS .docx`.

---

## 🛠️ Struttura del Repository

Questo repository è organizzato per supportare lo sviluppo dell'MVP e la futura espansione.

## ⚙️ Configurazione e Test Locale della Cloud Function

Questa sezione descrive come configurare l'ambiente di sviluppo e testare la Cloud Function principale (`process_pitch_deck`) sul tuo computer, senza sostenere costi di Cloud GCP in questa fase.

### Prerequisiti:
* Python 3.8+ installato.
* `pip` (gestore pacchetti Python).
* Un account OpenAI e una chiave API (`OPENAI_API_KEY`).
* `curl` (già presente sulla maggior parte dei sistemi, o scaricabile per Windows).

### 1. Clonare il Repository
Se non l'hai già fatto, clona questo repository:
```bash
git clone [https://github.com/tuo-username/validatr-os-mvp.git](https://github.com/tuo-username/validatr-os-mvp.git)
cd validatr-os-mvp
```

### 1. Configurare l'Ambiente della Cloud Function
Naviga nella directory della Cloud Function e configura l'ambiente virtuale:

```bash
cd functions/process_pitch_deck
python -m venv venv
```

### 3. Installare le Dipendenze
```bash
pip install -r requirements.txt
```
### 4. Configurare la Chiave API di OpenAI
```bash
# macOS/Linux:
export OPENAI_API_KEY="la_tua_chiave_api_openai_qui"
```

### 5. Eseguire la Cloud Function in Locale
functions-framework --target=process_pitch_deck --signature-type=cloudevent --port=8080