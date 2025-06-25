    import functions_framework
    import json
    import os
    from firebase_admin import credentials, firestore, auth, initialize_app
    import firebase_admin # Aggiunto per accedere a firebase_admin._apps

    # --- Inizializzazione Firebase Admin SDK ---
    # Inizializza Firebase Admin SDK solo se non è già stata inizializzata
    if not firebase_admin._apps:
        try:
            # Per l'ambiente Cloud Functions, ApplicationDefault() dovrebbe funzionare automaticamente
            # Assicurati che l'account di servizio della funzione abbia i ruoli necessari (es. Firestore Viewer, Firebase Auth Viewer)
            cred = credentials.ApplicationDefault()
            initialize_app(cred)
            print("Firebase Admin SDK inizializzato con successo per fetchPitchData.")
        except Exception as e:
            print(f"Errore nell'inizializzazione di Firebase Admin SDK per fetchPitchData: {e}")
            # Questo errore impedirà il funzionamento della funzione, quindi è critico.

    db = firestore.client()
    # Recupera l'ID dell'app dall'ambiente Canvas o usa un default
    APP_ID = os.environ.get('CANVAS_APP_ID', 'validatr-mvp') # Assicurati che questo corrisponda al tuo Project ID

    @functions_framework.http
    def fetchPitchData(request):
        """
        HTTP Cloud Function per recuperare i dati dei pitch deck da Firestore.
        Recupera solo i pitch dell'utente autenticato.
        Richiede un token di autenticazione Firebase nell'header Authorization.
        Include la gestione completa delle richieste CORS.
        """
        print(f"Richiesta ricevuta: {request.url}, Metodo: {request.method}")

        # Imposta gli header CORS comuni per tutte le risposte
        headers = {
            # *** MOLTO IMPORTANTE: Sostituisci '*' con il tuo dominio Firebase Hosting in produzione ***
            # Esempio: 'https://validatr-mvp.web.app'
            # Se stai testando da localhost, potresti aggiungere anche la tua origine locale:
            # 'Access-Control-Allow-Origin': 'https://validatr-mvp.web.app, http://localhost:8000',
            # Ma per produzione, usa solo l'origine HTTPS del tuo dominio.
            'Access-Control-Allow-Origin': 'https://validatr-mvp.web.app', 
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        }

        # Gestisce le richieste OPTIONS pre-flight per CORS
        if request.method == 'OPTIONS':
            print("Richiesta OPTIONS ricevuta, invio risposta pre-flight.")
            return ('', 204, headers) # No content, 204 status

        # 1. Verifica autenticazione Firebase
        auth_header = request.headers.get('Authorization')
        id_token = None
        if auth_header and auth_header.startswith('Bearer '):
            id_token = auth_header.split(' ')[1]

        if not id_token:
            print("Errore: Token di autenticazione mancante nell'header 'Authorization'.")
            # Includi headers nella risposta di errore
            return json.dumps({"error": "Unauthorized: No authentication token provided."}), 401, headers

        uid = None
        try:
            # Verifica il token ID Firebase
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            print(f"Utente autenticato: UID={uid}, Email={decoded_token.get('email', 'N/A')}")
        except Exception as e:
            print(f"Errore nella verifica del token Firebase: {e}")
            # Includi headers nella risposta di errore
            return json.dumps({"error": f"Unauthorized: Invalid token. {e}"}), 401, headers

        # 2. Recupera i dati da Firestore in base all'utente autenticato
        data = {}
        try:
            # La funzione recupererà SEMPRE solo i pitch dell'utente autenticato.
            collection_ref = db.collection('artifacts').document(APP_ID).collection('users').document(uid).collection('pitch_deck_analyses')
            print(f"Recupero pitch dalla collezione dell'utente: {collection_ref.id}")
            
            docs = collection_ref.stream()
            for doc in docs:
                doc_data = doc.to_dict()
                
                # --- Data transformation to match frontend expectations ---
                transformed_doc_data = {}
                transformed_doc_data['document_name'] = doc.id # Always include document_name as the Firestore ID

                # Transform 'calcoli_aggiuntivi' to 'core_metrics' and its nested properties
                if 'calcoli_aggiuntivi' in doc_data and doc_data['calcoli_aggiuntivi']:
                    transformed_doc_data['core_metrics'] = {
                        'indice_coerenza': doc_data['calcoli_aggiuntivi'].get('indice_coerenza'),
                        'classe_pitch': doc_data['calcoli_aggiuntivi'].get('classe'), # Renamed 'classe' to 'classe_pitch'
                        'z_score': doc_data['calcoli_aggiuntivi'].get('z_score'),
                        'final_adjusted_score': doc_data['calcoli_aggiuntivi'].get('final_adjusted_score'),
                        'final_score': doc_data['calcoli_aggiuntivi'].get('final_score'),
                        'userId': doc_data['calcoli_aggiuntivi'].get('userId', uid) # Use existing userId or the current UID
                    }
                else:
                    transformed_doc_data['core_metrics'] = {
                        'indice_coerenza': None, 'classe_pitch': None, 'z_score': None,
                        'final_adjusted_score': None, 'final_score': None, 'userId': uid
                    }


                # Transform 'variabili_valutate' to 'variables' and its nested properties
                transformed_doc_data['variables'] = []
                if 'variabili_valutate' in doc_data and doc_data['variabili_valutate']:
                    for var in doc_data['variabili_valutate']:
                        transformed_doc_data['variables'].append({
                            'nome_variabile': var.get('nome'), # Renamed 'nome' to 'nome_variabile'
                            'punteggio_variabile': var.get('punteggio'), # Renamed 'punteggio' to 'punteggio_variabile'
                            'motivazione_variabile': var.get('motivazione') # Renamed 'motivazione' to 'motivazione_variabile'
                        })

                # Transform 'coerenza_coppie' to 'coherence_pairs' and its nested properties
                transformed_doc_data['coherence_pairs'] = []
                if 'coerenza_coppie' in doc_data and doc_data['coerenza_coppie']:
                    for cp in doc_data['coerenza_coppie']:
                        transformed_doc_data['coherence_pairs'].append({
                            'nome_coppia': cp.get('coppia'), # Renamed 'coppia' to 'nome_coppia'
                            'punteggio_coppia': cp.get('punteggio'), # Renamed 'punteggio' to 'punteggio_coppia'
                            'motivazione_coppia': cp.get('motivazione') # Renamed 'motivazione' to 'motivazione_coppia'
                        })
                
                # Store the transformed data using doc.id as the key
                data[doc.id] = transformed_doc_data
            print(f"Retrieved {len(data)} documents.")

        except Exception as e:
            print(f"Error retrieving data from Firestore: {e}")
            # Include headers in the error response
            return json.dumps({"error": "Internal server error: Could not retrieve data from Firestore."}), 500, headers
        
        # Return the data with CORS headers
        return json.dumps(data), 200, headers
