import functions_framework
import json
import os
from firebase_admin import credentials, firestore, auth, initialize_app
import firebase_admin

@functions_framework.http
def replicate_analyses(request):
    """
    Funzione HTTP per replicare le analisi dei pitch deck da un utente sorgente a uno destinazione.
    Richiede un body JSON con "source_uid" e "destination_uid".
    """
    # Gestione CORS
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': 'https://validatr-mvp.web.app',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    }
    if request.method == 'OPTIONS':
        return ('', 204, headers)

    # --- Autenticazione e Autorizzazione (SOLO ADMIN) ---
    try:
        auth_header = request.headers.get('Authorization')
        id_token = auth_header.split('Bearer ')[1]
        decoded_token = auth.verify_id_token(id_token)
        caller_uid = decoded_token['uid']
        """
        await firebaseAuth.currentUser.getIdToken()
         curl -m 70 -X POST "https://europe-west1-validatr-mvp.cloudfunctions.net/replicate_documents_pitch"  \
        -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6Ijk1MWRkZTkzMmViYWNkODhhZmIwMDM3YmZlZDhmNjJiMDdmMDg2NmIiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vdmFsaWRhdHItbXZwIiwiYXVkIjoidmFsaWRhdHItbXZwIiwiYXV0aF90aW1lIjoxNzUzODg0ODIzLCJ1c2VyX2lkIjoiTDh1M2RYUWV6bWZ2TzZRZXdsYTd1MXBjYlE2MyIsInN1YiI6Ikw4dTNkWFFlem1mdk82UWV3bGE3dTFwY2JRNjMiLCJpYXQiOjE3NTM4ODQ4MjMsImV4cCI6MTc1Mzg4ODQyMywiZW1haWwiOiJyaWNjYXJkby5hZmZvbHRlckBnbWFpbC5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZmlyZWJhc2UiOnsiaWRlbnRpdGllcyI6eyJlbWFpbCI6WyJyaWNjYXJkby5hZmZvbHRlckBnbWFpbC5jb20iXX0sInNpZ25faW5fcHJvdmlkZXIiOiJwYXNzd29yZCJ9fQ.RYsQwlbAEfVkNmOQivrxvt0HNmDfa4sw7xDcrV3c9fAZnl-B91ZWjIkayybsVLUShPGDBzZF2oJNnJ4BXt5giTY3hAILxfkpU5kmzpSD6dykkgI_gkq-Y-L1nTj2awV3g8k_WO8HiebeAC23GtP7geDgeRL2AWO5YQMyP7Ydn2sfDDt4j4h4Ds1pwS_PIV70afQfDR0zRTW7uIB-e27BnBPU4prOwaK0B2xmYngo8ECJ7O_ceu4miqKZyguOWVqt_nwJgj4woOGZ6YcnKvD2MhMC9V56XCiB48VF1HiCGuAu7qlN9_Ex_-uQ0AhLaPxpBSHUs5XHVAyFFL5SSNBKtQ"  \
        -H "Content-Type: application/json" \
          -d '{     "source_uid": "L8u3dXQezmfvO6Qewla7u1pcbQ63",     "destination_uid": "ekDXJbgPf5gMDEf1WIdrpsifS7F3"}'
          """
        # IMPORTANTE: Inserisci qui l'UID del tuo account admin.
        # Solo questo utente potrà eseguire la copia.
        ADMIN_UID = "L8u3dXQezmfvO6Qewla7u1pcbQ63" 
        if caller_uid != ADMIN_UID:
            print(f"ERRORE: Tentativo di replica non autorizzato da UID {caller_uid}")
            return json.dumps({"error": "Forbidden: Only admins can perform this action."}), 403, headers
        
        print(f"Azione di replica autorizzata per l'admin UID: {caller_uid}")

    except Exception as e:
        print(f"Errore di autenticazione durante la replica: {e}")
        return json.dumps({"error": f"Unauthorized: Invalid token. {e}"}), 401, headers

    # --- Logica di Copia ---
    try:
        request_json = request.get_json(silent=True)
        if not request_json or 'source_uid' not in request_json or 'destination_uid' not in request_json:
            return json.dumps({"error": "Missing 'source_uid' or 'destination_uid' in request body."}), 400, headers

        source_uid = request_json['source_uid']
        destination_uid = request_json['destination_uid']

        print(f"Inizio replica da {source_uid} a {destination_uid}")

        # Riferimento alla collezione sorgente
        source_ref = db.collection('artifacts', APP_ID, 'users', source_uid, 'pitch_deck_analyses')
        
        # Riferimento alla collezione destinazione
        destination_ref = db.collection('artifacts', APP_ID, 'users', destination_uid, 'pitch_deck_analyses')

        docs_to_copy = source_ref.stream()
        copied_count = 0

        for doc in docs_to_copy:
            # Scrive ogni documento nella collezione di destinazione con lo stesso ID e contenuto
            destination_ref.document(doc.id).set(doc.to_dict())
            copied_count += 1
            print(f"Copiato documento: {doc.id}")

        success_message = f"Replica completata con successo. Copiati {copied_count} documenti da {source_uid} a {destination_uid}."
        print(success_message)
        return json.dumps({"status": "success", "message": success_message, "copied_docs": copied_count}), 200, headers

    except Exception as e:
        print(f"ERRORE durante il processo di replica: {e}")
        return json.dumps({"error": "Internal server error during replication."}), 500, headers