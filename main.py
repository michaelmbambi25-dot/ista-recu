import io
import os
import smtplib
from email.message import EmailMessage
from fastapi import FastAPI, Request

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = FastAPI()

# Configuration SMTP Brevo
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 2525  # Si le port 2525 bloque, vous pouvez tester 587
SMTP_USERNAME = "b5f05b001@smtp-brevo.com"
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SENDER_EMAIL = "michaelmbambi25@gmail.com"

# E-mail de l'autorité qui recevra les alertes de fraude
AUTHORITY_EMAIL = "stephaniepfiti@gmail.com"  # Modifiez si besoin

# Base des bordereaux déjà enregistrés en mémoire (Anti-fraude)
BORDEREAUX_UTILISES = set()

# Dictionnaire des agents / percepteurs
DICTIONNAIRE_AGENTS = {
    "1234": "M. LAKIA Kaba",
    "5678": "Mme MAVUNGU Clarisse",
    "0101": "M. DINZENZA Geordi",
    "0303": "M. MBAMBI Mike",
}

# Cartographie exacte : (Nom du champ Kobo, Option choisie) -> (Nom de l'étudiant, Libellé promotion)
CARTOGRAPHIE_ETUDIANTS = {
    # Électricité (Etri)
    ("matricule_Etri", "L3"): ("MBAMBI YABU Michael", "L3 Électricité"),
    ("matricule_Etri", "L1"): ("NLEVO MABIALA Jean", "L1 Électricité"),
    ("matricule_Etri", "L1"): ("MBONGO MAMBIMBI  Raphael", "L2 Électricité"),
    
    # Mécanique (meca)
    ("matricule_meca", "L2"): ("DINZENZA DINZENZA Geordi", "L2 Mécanique"),
    ("matricule_meca", "L3"): ("MBADU MBADU Michel", "L3 Mécanique"),
    ("matricule_meca", "L1"): ("MVUMBI PFUTI Glody", "L1 Mécanique"),
    
    # Informatique (info)
    ("matricule_info", "L2"): ("NSAKU MVUBU Dieu", "L2 Informatique"),
    ("matricule_info", "L1"): ("NSASI NIATI Brigitte", "L1 Informatique"),
    ("matricule_info", "L3"): ("NZUZI NZUZI Martin", "L3 Informatique"),
    
    # BTP
    ("matricule_BTP", "L2"): ("SEKE TANGU Juceline", "L2 BTP"),
    ("matricule_BTP", "L1"): ("KASONGO MULUMBA Péter", "L1 BTP"),
    ("matricule_BTP", "L3"): ("LAKIA KABA", "L3 BTP"),
    
    # Prépo
    ("matricule_prepo", "prepo"): ("MANIKA MANIKA Flavien", "Préparatoire"),
    ("matricule_prepo", "prepo"): ("KHASA KHASA Pedro", "Préparatoire"),
    ("matricule_prepo", "prepo"): ("MBONGO MAMBIMBI  Raphael", "Préparatoire"),
}

def nettoyer_texte(texte: str) -> str:
    if not texte:
        return "N/A"
    txt = str(texte)
    txt = txt.replace("frais_acad_mique___min_ral", "Frais Académiques (Minerval)")
    txt = txt.replace("frais_acad_mique", "Frais Académiques")
    txt = txt.replace("___", " ").replace("__", " ").replace("_", " ")
    txt = " ".join(txt.split()).strip()
    return txt.title()

def extraire_valeur(data: dict, mots_cles: list, defaut: str = "N/A") -> str:
    """Parcourt le JSON de Kobo pour trouver le champ correspondant."""
    exclusions = ["_id", "_uuid", "_submission_time", "_submitted_by"]
    
    for key, val in data.items():
        if key in exclusions or val is None or str(val).strip() == "":
            continue

        clean_key = key.split("/")[-1].lower().replace("_", "").replace("-", "")
        
        for kw in mots_cles:
            kw_clean = kw.lower().replace("_", "").replace("-", "")
            if kw_clean in clean_key:
                return str(val).strip()
    return defaut

def obtenir_identite_etudiant(data: dict) -> tuple[str, str]:
    """
    Extrait le nom de l'étudiant et son code de promotion.
    1. Vérifie si Kobo a transmis un nom calculé valide.
    2. Sinon, parcourt les champs (matricule_info, matricule_Etri, etc.) pour trouver la correspondance.
    """
    # 1. Vérification si Kobo a réussi le calcul
    nom_kobo = extraire_valeur(data, ["nom_etudiant", "nom_complet", "student_name", "calcul"], "")
    if nom_kobo and nom_kobo.lower() not in ["n/a", "none", "null", "étudiant", "etudiant"]:
        print(f"✅ Nom extrait depuis le calcul Kobo : {nom_kobo}")
        matricule_code = extraire_valeur(data, ["matricule", "matr", "code_etudiant"], "N/A")
        return nettoyer_texte(nom_kobo), matricule_code

    # 2. Identification via la cartographie Python (champ + valeur)
    for key, val in data.items():
        if val is None or str(val).strip() == "":
            continue
        
        clean_key = key.split("/")[-1]  # Ex: "group_1/matricule_info" -> "matricule_info"
        val_str = str(val).strip()

        if (clean_key, val_str) in CARTOGRAPHIE_ETUDIANTS:
            nom_trouve, promo_trouvee = CARTOGRAPHIE_ETUDIANTS[(clean_key, val_str)]
            print(f"✅ Nom identifié via Python pour {clean_key}={val_str} : {nom_trouve}")
            return nom_trouve, val_str

    # 3. Secours : renvoie le code brut trouvé
    code_secours = extraire_valeur(data, ["matricule", "matr", "code_etudiant"], "N/A")
    print(f"⚠️ Aucun nom spécifique trouvé pour le code '{code_secours}'.")
    return "Étudiant", code_secours

def envoyer_alerte_fraude(num_bordereau: str, nom_etudiant: str, nom_agent: str):
    """Envoie un e-mail d'alerte au responsable de la comptabilité."""
    msg = EmailMessage()
    msg["Subject"] = f"🚨 ALERTE FRAUDE : Bordereau réutilisé ({num_bordereau})"
    msg["From"] = f"Système Anti-Fraude ISTA-LB <{SENDER_EMAIL}>"
    msg["To"] = AUTHORITY_EMAIL

    msg.set_content(f"""ATTENTION : Tentative de soumission d'un bordereau en double !

DÉTAILS DU SIGNALEMENT :
- N° Bordereau suspect : {num_bordereau}
- Nom indiqué sur le formulaire : {nom_etudiant}
- Agent qui a saisi le formulaire : {nom_agent}

Ce numéro de bordereau a déjà été utilisé pour générer un reçu auparavant. Aucun reçu officiel n'a été émis pour cette nouvelle tentative.
""")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            if SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"⚠️ Alerte fraude envoyée à {AUTHORITY_EMAIL} pour le bordereau {num_bordereau}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de l'alerte fraude : {e}")

def generer_recu_pdf(nom, matricule, filiere, motif, montant, devise, banque, num_bordereau, date_enregistr, nom_agent):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(colors.HexColor("#0D3B66"))
    pdf.drawString(40, height - 50, "INSTITUT SUPÉRIEUR DES TECHNIQUES APPLIQUÉES DE LUKULA À BOMA")
    pdf.drawString(40, height - 68, "(ISTA-LB)")

    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.black)
    pdf.drawString(40, height - 85, "Service de la Comptabilité et des Finances")

    pdf.setLineWidth(1)
    pdf.setStrokeColor(colors.HexColor("#0D3B66"))
    pdf.line(40, height - 95, width - 40, height - 95)

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, height - 130, "REÇU DE PAIEMENT OFFICIEL")

    pdf.setFont("Helvetica", 10)
    y = height - 165
    interligne = 22

    details = [
        ("Nom de l'étudiant :", nom),
        ("Matricule / Promotion :", matricule),
        ("Filière / Option :", filiere),
        ("Motif du paiement :", motif),
        ("Montant réglé :", f"{montant} {devise.upper()}"),
        ("Nom de la banque :", banque.upper()),
        ("N° de bordereau :", num_bordereau),
        ("Date d'enregistrement :", date_enregistr),
        ("Agent percepteur :", nom_agent),
        ("Statut de la transaction :", "VALIDÉ ET ENREGISTRÉ"),
    ]

    for label, valeur in details:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(40, y, label)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(200, y, str(valeur))
        y -= interligne

    pdf.setLineWidth(0.5)
    pdf.setStrokeColor(colors.gray)
    pdf.line(40, 90, width - 40, 90)

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColor(colors.gray)
    pdf.drawString(40, 75, "Ce document est un reçu électronique officiel délivré par le système automatisé de l'ISTA-LB.")
    pdf.drawString(40, 63, "Toute rature ou falsification rend ce document caduc.")

    pdf.showPage()
    pdf.save()

    buffer.seek(0)
    return buffer.getvalue()

@app.post("/webhook-kobo")
async def kobo_webhook(request: Request):
    data = await request.json()
    
    print("=== DONNÉES REÇUES DE KOBO ===")
    print(data)

    # 1. Extraction de l'e-mail du destinataire
    email_destinataire = extraire_valeur(data, ["email", "mail", "courriel"], "")
    if not email_destinataire or "@" not in email_destinataire:
        print("❌ ERREUR : Adresse e-mail invalide ou introuvable.")
        return {"status": "error", "message": "Adresse e-mail manquante ou invalide."}

    # 2. Identification de l'étudiant (Nom + Promotion)
    nom_etudiant, matricule_code = obtenir_identite_etudiant(data)
    
    # 3. Extractions des autres champs
    filiere = nettoyer_texte(extraire_valeur(data, ["filiere", "option", "section", "promotion"], "Non spécifiée"))
    motif = nettoyer_texte(extraire_valeur(data, ["motif", "frais", "raison", "paiement"], "Frais d'études"))
    montant = extraire_valeur(data, ["montant", "somme", "prix", "valeur"], "0")
    devise = extraire_valeur(data, ["devise", "monnaie", "currency"], "USD")
    banque = extraire_valeur(data, ["banque", "bank", "institution"], "N/A")
    num_bordereau = extraire_valeur(data, ["bordereau", "numero", "ref", "transaction"], "N/A")
    date_enregistr = extraire_valeur(data, ["date", "today"], "N/A")
    
    pin_saisi = extraire_valeur(data, ["pin", "code"], "")
    nom_agent = DICTIONNAIRE_AGENTS.get(pin_saisi, nettoyer_texte(extraire_valeur(data, ["agent", "percepteur"], "Agent Percepteur")))

    # 4. Contrôle Anti-Fraude sur le Bordereau
    if num_bordereau != "N/A" and num_bordereau in BORDEREAUX_UTILISES:
        print(f"🚨 TENTATIVE DE FRAUDE : Bordereau {num_bordereau} réutilisé !")
        envoyer_alerte_fraude(num_bordereau, nom_etudiant, nom_agent)
        return {"status": "rejected", "message": "Bordereau déjà utilisé. Alerte transmise."}

    if num_bordereau != "N/A":
        BORDEREAUX_UTILISES.add(num_bordereau)

    # 5. Génération du Reçu PDF
    pdf_bytes = generer_recu_pdf(
        nom=nom_etudiant,
        matricule=matricule_code,
        filiere=filiere,
        motif=motif,
        montant=montant,
        devise=devise,
        banque=banque,
        num_bordereau=num_bordereau,
        date_enregistr=date_enregistr,
        nom_agent=nom_agent
    )

    # 6. Envoi de l'e-mail avec le reçu PDF
    msg = EmailMessage()
    msg["Subject"] = f"Reçu de paiement ISTA-LB - {nom_etudiant} ({matricule_code})"
    msg["From"] = f"Comptabilité ISTA-LB <{SENDER_EMAIL}>"
    msg["To"] = email_destinataire

    msg.set_content(f"""Bonjour {nom_etudiant},

Veuillez trouver ci-joint votre reçu de paiement officiel délivré par le service de comptabilité de l'ISTA-LB.

RÉCAPITULATIF DU PAIEMENT :
- Nom de l'étudiant : {nom_etudiant}
- Promotion / Matricule : {matricule_code}
- Option : {filiere}
- Montant : {montant} {devise.upper()}
- N° Bordereau : {num_bordereau}

Cordialement,
Le Service de la Comptabilité et des Finances
ISTA-LB (Boma)
""")

    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=f"Recu_ISTA_LB_{matricule_code}.pdf"
    )

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            if SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"✅ E-mail envoyé avec succès à {email_destinataire} pour {nom_etudiant}")
        return {"status": "success", "message": "Reçu PDF envoyé"}

    except Exception as e:
        print(f"❌ Erreur lors de l'envoi SMTP : {e}")
        return {"status": "failed", "error": str(e)}
