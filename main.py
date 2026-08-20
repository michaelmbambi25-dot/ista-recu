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
SMTP_USERNAME = "b5f05b001@smtp-brevo.com"
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SENDER_EMAIL = "michaelmbambi25@gmail.com"

DICTIONNAIRE_AGENTS = {
    "1234": "M. LAKIA Kaba",
    "5678": "Mme MAVUNGU Clarisse",
    "0101": "M. DINZENZA Geordi",
    "0303": "M. MBAMBI Mike",
}

# Dictionnaire associant les codes d'options Kobo (m1, m2...) aux noms d'étudiants
DICTIONNAIRE_ETUDIANTS = {
    # Code Kobo (colonne bleue m1, m2...) : Nom de l'étudiant
    "L2": "NSAKU MVUBU Dieu",
    "L1": "NSASI NIATI Brigitte",
    "L3": "NZUZI NZUZI Martin.",
    "L3": "MBAMBI YABU Michael",
    "L2": "MBONGO MAMBIMBI Raphael",
    "L1": "NLEVO MABIALA Jean",
    "L2": "DINZENZA DINZENZA Geordi",
    "L3": "MBADU MBADU Michel",
    "L1": "MVUMBI PFUTI Glody",
    "L1": "KASONGO MULUMBA Péter",
    "L2": "SEKE TANGU Juceline",
    "L3": "LAKIA KABA",
    "prepo": "MANIKA MANIKA Flavien",
    "prepo": "KHASA KHASA Pedro",
    "prepo": "MABIALA PHEMBA Daniel",
    # Ajoutez ici tous vos étudiants selon le même modèle :
    # "m6": "NOM ETUDIANT 6",
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

def obtenir_nom_etudiant(data: dict, matricule_code: str) -> str:
    """1. Vérifie si un champ 'nom_etudiant' ou 'calcul' existe dans Kobo
       2. Sinon, cherche la correspondance dans le dictionnaire Python."""
    
    # Recherche d'un champ nom transmis directement par Kobo
    nom_kobo = extraire_valeur(data, ["nom_etudiant", "nom_complet", "student_name"], "")
    if nom_kobo and nom_kobo.lower() not in ["n/a", "none", "null"]:
        return nettoyer_texte(nom_kobo)

    # Recherche via le code du matricule (ex: m1, m2)
    if matricule_code in DICTIONNAIRE_ETUDIANTS:
        return DICTIONNAIRE_ETUDIANTS[matricule_code]
    
    # Recherche insensible à la casse
    for code, nom in DICTIONNAIRE_ETUDIANTS.items():
        if code.lower() == matricule_code.lower():
            return nom

    return "Étudiant"

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
        ("Matricule Étudiant :", matricule),
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

    email_destinataire = extraire_valeur(data, ["email", "mail", "courriel"], "")
    if not email_destinataire:
        return {"status": "error", "message": "Adresse e-mail manquante."}

    # Extraction du code matricule (ex: m1, m2)
    matricule_code = extraire_valeur(data, ["matricule", "matr", "code_etudiant"], "N/A")
    
    # Obtention du nom via le dictionnaire ou le champ calcul
    nom_etudiant = obtenir_nom_etudiant(data, matricule_code)
    
    filiere = nettoyer_texte(extraire_valeur(data, ["filiere", "option", "section", "promotion"], "Non spécifiée"))
    motif = nettoyer_texte(extraire_valeur(data, ["motif", "frais", "raison", "paiement"], "Frais d'études"))
    montant = extraire_valeur(data, ["montant", "somme", "prix", "valeur"], "0")
    devise = extraire_valeur(data, ["devise", "monnaie", "currency"], "USD")
    banque = extraire_valeur(data, ["banque", "bank", "institution"], "N/A")
    num_bordereau = extraire_valeur(data, ["bordereau", "numero", "ref", "transaction"], "N/A")
    date_enregistr = extraire_valeur(data, ["date", "today"], "N/A")
    
    pin_saisi = extraire_valeur(data, ["pin", "code"], "")
    nom_agent = DICTIONNAIRE_AGENTS.get(pin_saisi, nettoyer_texte(extraire_valeur(data, ["agent", "percepteur"], "Agent Percepteur")))

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

    msg = EmailMessage()
    msg["Subject"] = f"Reçu de paiement ISTA-LB - {nom_etudiant} ({matricule_code})"
    msg["From"] = f"Comptabilité ISTA-LB <{SENDER_EMAIL}>"
    msg["To"] = email_destinataire

    msg.set_content(f"""Bonjour {nom_etudiant},

Veuillez trouver ci-joint votre reçu de paiement officiel délivré par le service de comptabilité de l'ISTA-LB.

RÉCAPITULATIF DU PAIEMENT :
- Nom de l'étudiant : {nom_etudiant}
- Matricule : {matricule_code}
- Option / Promotion : {filiere}
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
        with smtplib.SMTP(SMTP_SERVER, 2525, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"✅ E-mail envoyé avec succès pour {nom_etudiant}")
        return {"status": "success", "message": "Reçu PDF envoyé"}

    except Exception as e:
        print(f"❌ Erreur d'envoi : {e}")
        return {"status": "failed", "error": str(e)}
