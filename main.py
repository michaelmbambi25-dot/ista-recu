import io
import os
import smtplib
import uuid
from datetime import datetime
from email.message import EmailMessage
from fastapi import FastAPI, Request

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

app = FastAPI()

# Configuration SMTP Brevo
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 2525
SMTP_USERNAME = "b5f05b001@smtp-brevo.com"
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SENDER_EMAIL = "michaelmbambi25@gmail.com"
AUTHORITY_EMAIL = "stephaniepfiti@gmail.com"

# Base des bordereaux enregistrés (Anti-fraude)
BORDEREAUX_UTILISES = set()

# Dictionnaire des agents / percepteurs
DICTIONNAIRE_AGENTS = {
    "1234": "M. LAKIA Kaba",
    "5678": "Mme MAVUNGU Clarisse",
    "0101": "M. DINZENZA Geordi",
    "0303": "M. MBAMBI Mike",
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

def generer_code_transaction() -> str:
    """Génère un identifiant unique type REC-20260821-A1B2C."""
    date_str = datetime.now().strftime("%Y%m%d")
    unique_suffix = uuid.uuid4().hex[:5].upper()
    return f"REC-{date_str}-{unique_suffix}"

def generer_image_qr(contenu: str) -> io.BytesIO:
    """Génère une image PNG en mémoire du QR Code."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(contenu)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0D3B66", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def envoyer_alerte_fraude(num_bordereau: str, matricule: str, nom_agent: str):
    msg = EmailMessage()
    msg["Subject"] = f"🚨 ALERTE FRAUDE : Bordereau réutilisé ({num_bordereau})"
    msg["From"] = f"Système Anti-Fraude ISTA-LB <{SENDER_EMAIL}>"
    msg["To"] = AUTHORITY_EMAIL

    msg.set_content(f"""ATTENTION : Tentative de soumission d'un bordereau en double !

DÉTAILS DU SIGNALEMENT :
- N° Bordereau suspect : {num_bordereau}
- Matricule concerné : {matricule}
- Agent ayant saisi la demande : {nom_agent}

Ce numéro de bordereau a déjà été utilisé pour générer un reçu.
""")
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            if SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"⚠️ Alerte fraude transmise pour le bordereau {num_bordereau}")
    except Exception as e:
        print(f"❌ Erreur envoi alerte : {e}")

def generer_recu_pdf(code_recu, matricule, filiere, motif, montant, devise, banque, num_bordereau, date_enregistr, nom_agent):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # En-tête
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

    # Titre et Code Transaction Unique
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, height - 125, "REÇU DE PAIEMENT OFFICIEL")
    
    # Génération et affichage du QR Code en haut à droite
    texte_qr = f"ISTA-LB | RECU: {code_recu} | MATRICULE: {matricule} | BORDEREAU: {num_bordereau} | MONTANT: {montant} {devise.upper()} | STATUT: VALIDE"
    qr_buffer = generer_image_qr(texte_qr)
    qr_image = ImageReader(qr_buffer)
    pdf.drawImage(qr_image, width - 140, height - 190, width=100, height=100)

    # Détails
    pdf.setFont("Helvetica", 10)
    y = height - 155
    interligne = 22

    details = [
        ("N° Transaction (ID Reçu) :", code_recu),
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

    # Pied de page
    pdf.setLineWidth(0.5)
    pdf.setStrokeColor(colors.gray)
    pdf.line(40, 85, width - 40, 85)

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColor(colors.gray)
    pdf.drawString(40, 70, "Ce document est un reçu électronique officiel délivré par le système automatisé de l'ISTA-LB.")
    pdf.drawString(40, 58, "Scannez le QR Code ci-dessus pour vérifier la validité de ce reçu lors des contrôles aux examens.")

    pdf.showPage()
    pdf.save()

    buffer.seek(0)
    return buffer.getvalue()

@app.post("/webhook-kobo")
async def kobo_webhook(request: Request):
    data = await request.json()

    # 1. Extraction e-mail
    email_destinataire = extraire_valeur(data, ["email", "mail", "courriel"], "")
    if not email_destinataire or "@" not in email_destinataire:
        return {"status": "error", "message": "Adresse e-mail invalide."}

    # 2. Génération du Code de Transaction Unique & extraction du matricule
    code_recu_unique = generer_code_transaction()
    matricule_code = extraire_valeur(data, ["matricule", "matr", "code_etudiant"], "N/A")
    
    # 3. Extraction des autres champs
    filiere = nettoyer_texte(extraire_valeur(data, ["filiere", "option", "section", "promotion"], "Non spécifiée"))
    motif = nettoyer_texte(extraire_valeur(data, ["motif", "frais", "raison", "paiement"], "Frais d'études"))
    montant = extraire_valeur(data, ["montant", "somme", "prix", "valeur"], "0")
    devise = extraire_valeur(data, ["devise", "monnaie", "currency"], "USD")
    banque = extraire_valeur(data, ["banque", "bank", "institution"], "N/A")
    num_bordereau = extraire_valeur(data, ["bordereau", "numero", "ref", "transaction"], "N/A")
    date_enregistr = extraire_valeur(data, ["date", "today"], "N/A")
    
    pin_saisi = extraire_valeur(data, ["pin", "code"], "")
    nom_agent = DICTIONNAIRE_AGENTS.get(pin_saisi, nettoyer_texte(extraire_valeur(data, ["agent", "percepteur"], "Agent Percepteur")))

    # 4. Anti-Fraude
    if num_bordereau != "N/A" and num_bordereau in BORDEREAUX_UTILISES:
        envoyer_alerte_fraude(num_bordereau, matricule_code, nom_agent)
        return {"status": "rejected", "message": "Bordereau déjà utilisé."}

    if num_bordereau != "N/A":
        BORDEREAUX_UTILISES.add(num_bordereau)

    # 5. Génération PDF avec QR Code
    pdf_bytes = generer_recu_pdf(
        code_recu=code_recu_unique,
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

    # 6. Envoi de l'e-mail
    msg = EmailMessage()
    msg["Subject"] = f"Reçu de paiement ISTA-LB [{code_recu_unique}] - Matricule {matricule_code}"
    msg["From"] = f"Comptabilité ISTA-LB <{SENDER_EMAIL}>"
    msg["To"] = email_destinataire

    msg.set_content(f"""Bonjour,

Veuillez trouver ci-joint votre reçu de paiement officiel délivré par le service de comptabilité de l'ISTA-LB.

INFORMATIONS DE LA TRANSACTION :
- N° Reçu Unique : {code_recu_unique}
- Matricule Étudiant : {matricule_code}
- Option / Filière : {filiere}
- Montant : {montant} {devise.upper()}
- N° Bordereau : {num_bordereau}

Note : Ce document contient un QR Code officiel vérifiable lors des examens.

Cordialement,
Le Service de la Comptabilité et des Finances
ISTA-LB (Boma)
""")

    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=f"Recu_{code_recu_unique}_{matricule_code}.pdf"
    )

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            if SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return {"status": "success", "message": "Reçu PDF avec QR Code envoyé", "id_recu": code_recu_unique}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
