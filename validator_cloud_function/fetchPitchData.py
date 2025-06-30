import functions_framework
import json
import os
from firebase_admin import credentials, firestore, auth, initialize_app
import firebase_admin

# --- Inizializzazione Firebase Admin SDK ---
if not firebase_admin._apps:
    try:
        cred = credentials.ApplicationDefault()
        initialize_app(cred)
        print("Firebase Admin SDK inizializzato con successo per fetchPitchData.")
    except Exception as e:
        print(f"Errore nell'inizializzazione di Firebase Admin SDK per fetchPitchData: {e}")

db = firestore.client()
APP_ID = os.environ.get('CANVAS_APP_ID', 'validatr-mvp')

@functions_framework.http
def fetchPitchData(request):
    print(f"Richiesta ricevuta: {request.url}, Metodo: {request.method}")

    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': 'https://validatr-mvp.web.app', # Controlla questa origine!
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '3600'
    }

    if request.method == 'OPTIONS':
        print("Richiesta OPTIONS ricevuta, invio risposta pre-flight.")
        return ('', 204, headers)

    auth_header = request.headers.get('Authorization')
    id_token = None
    if auth_header and auth_header.startswith('Bearer '):
        id_token = auth_header.split(' ')[1]

    if not id_token:
        print("Errore: Token di autenticazione mancante nell'header 'Authorization'.")
        return json.dumps({"error": "Unauthorized: No authentication token provided."}), 401, headers

    uid = None
    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        print(f"Utente autenticato: UID={uid}, Email={decoded_token.get('email', 'N/A')}")
    except Exception as e:
        print(f"Errore nella verifica del token Firebase: {e}")
        return json.dumps({"error": f"Unauthorized: Invalid token. {e}"}), 401, headers

    data = {}
    try:
        collection_ref = db.collection('artifacts').document(APP_ID).collection('users').document(uid).collection('pitch_deck_analyses')
        print(f"Recupero pitch dalla collezione dell'utente: {collection_ref.id}")
        
        docs = collection_ref.stream()
        for doc in docs:
            doc_data = doc.to_dict()
            
            transformed_doc_data = {}
            transformed_doc_data['document_name'] = doc.id

            # --- MODIFICA CRUCIALE QUI: Prioritizza 'core_metrics' e gestisci la retrocompatibilità ---
            if 'core_metrics' in doc_data and doc_data['core_metrics']:
                transformed_doc_data['core_metrics'] = {
                    'indice_coerenza': doc_data['core_metrics'].get('indice_coerenza'),
                    'classe_pitch': doc_data['core_metrics'].get('classe_pitch'), # UTILE PER NUOVI DOCUMENTI
                    'z_score': doc_data['core_metrics'].get('z_score'),
                    'final_adjusted_score': doc_data['core_metrics'].get('final_adjusted_score'),
                    'final_score': doc_data['core_metrics'].get('final_score'),
                    'userId': doc_data['core_metrics'].get('userId', uid)
                }
            elif 'calcoli_aggiuntivi' in doc_data and doc_data['calcoli_aggiuntivi']: # Fallback per vecchi documenti
                print(f"DEBUG: Documento '{doc.id}' usa il vecchio formato 'calcoli_aggiuntivi'.")
                transformed_doc_data['core_metrics'] = {
                    'indice_coerenza': doc_data['calcoli_aggiuntivi'].get('indice_coerenza'),
                    'classe_pitch': doc_data['calcoli_aggiuntivi'].get('classe'), # Vecchia chiave 'classe'
                    'z_score': doc_data['calcoli_aggiuntivi'].get('z_score'),
                    'final_adjusted_score': doc_data['calcoli_aggiuntivi'].get('final_adjusted_score'),
                    'final_score': doc_data['calcoli_aggiuntivi'].get('final_score'),
                    'userId': doc_data['calcoli_aggiuntivi'].get('userId', uid)
                }
            else:
                print(f"DEBUG: Documento '{doc.id}' non ha 'core_metrics' né 'calcoli_aggiuntivi'.")
                transformed_doc_data['core_metrics'] = {
                    'indice_coerenza': None, 'classe_pitch': None, 'z_score': None,
                    'final_adjusted_score': None, 'final_score': None, 'userId': uid
                }

            # --- Gestione di 'variabili_valutate' ---
            transformed_doc_data['variables'] = []
            if 'variabili_valutate' in doc_data and doc_data['variabili_valutate']:
                for var in doc_data['variabili_valutate']:
                    motivation = var.get('motivazione')
                    # 'motivation' sarà già un dict se dal nuovo formato, o stringa se dal vecchio.
                    # Non fare json.loads() qui, il dato è già come ci serve per Python
                    transformed_doc_data['variables'].append({
                        'nome_variabile': var.get('nome'),
                        'punteggio_variabile': var.get('punteggio'),
                        'motivazione_variabile': motivation # Passa direttamente l'oggetto/stringa
                    })

            # --- Gestione di 'coerenza_coppie' ---
            transformed_doc_data['coherence_pairs'] = []
            if 'coerenza_coppie' in doc_data and doc_data['coerenza_coppie']:
                for cp in doc_data['coerenza_coppie']:
                    motivation = cp.get('motivazione')
                    # 'motivation' sarà già un dict se dal nuovo formato, o stringa se dal vecchio.
                    transformed_doc_data['coherence_pairs'].append({
                        'nome_coppia': cp.get('coppia'),
                        'punteggio_coppia': cp.get('punteggio'),
                        'motivazione_coppia': motivation # Passa direttamente l'oggetto/stringa
                    })
            
            data[doc.id] = transformed_doc_data
        print(f"Retrieved {len(data)} documents.")

    except Exception as e:
        print(f"Error retrieving data from Firestore: {e}")
        return json.dumps({"error": "Internal server error: Could not retrieve data from Firestore."}), 500, headers
    
    return json.dumps(data), 200, headers