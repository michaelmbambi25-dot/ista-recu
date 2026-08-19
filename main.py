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

# Dictionnaire de correspondance Code PIN / ID -> Nom propre de l'agent
DICTIONNAIRE_AGENTS = {
    "1234": "M. KABANGU Alain",
    "5678": "Mme MAVUNGU Clarisse",
    "0101": "M. DINZENZA Geordi",
    "0303": "M. MBAMBI Mike",
}

# Dictionnaire de secours : Matricule -> Nom de l'étudiant
# (Utile si votre formulaire Kobo ne saisit que le matricule)
DICTIONNAIRE_ETUDIANTS = {
    "2026_info_l2_002": "MBAMBI MICHAEL",
    "2026_info_l2_001": "KAPITA Jean",
}

def nettoyer_texte(texte: str) -> str:
    """Nettoie les codes et tirets bas envoyés par KoboToolbox."""
    if not texte:
        return "N/A"
    txt = str(texte)
    
    # Corrections spécifiques des libellés Kobo
    txt = txt.replace("frais_acad_mique___min_ral", "Frais Académiques (Minerval)")
    txt = txt.replace("frais_acad_mique", "Frais Académiques")
    txt = txt.replace("agent_04_malunda_jackson___sci", "M. MALUNDA Jackson")
    
    # Nettoyage général des tirets du bas
    txt = txt.replace("___", " ").replace("__", " ").replace("_", " ")
    txt = " ".join(txt.split()).strip()
    return txt.title()

def extraire_nom_etudiant(data: dict, matricule: str) -> str:
    """Recherche approfondie du nom de l'étudiant."""
    # 1. Vérification par matricule dans le dictionnaire
    if matricule in DICTIONNAIRE_ETUDIANTS:
        return DICTIONNAIRE_ETUDIANTS[matricule]

    # 2. Recherche dans les champs de données envoyés par Kobo
    mots_cles = ["nom_etudiant", "noms_etudiant", "nom_complet", "identite", "student_name", "nom_prenom", "nom_etud", "nom", "noms"]
    exclusions = ["banque", "agent", "motif", "frais", "percepteur", "user", "by", "id", "uuid", "status", "date"]

    for key, val in data.items():
        if key.startswith("_") or not val or str(val).strip() == "":
            continue

        # Extraire le nom du champ même s'il est dans un groupe (ex: groupe1/nom)
        clean_key = key.split("/")[-1].lower()

        if any(ex in clean_key for ex in exclusions):
            continue

        if any(kw in clean_key for kw in mots_cles):
            res = nettoyer_texte(val)
            if res and res.lower() not in ["n/a", "none", "null"]:
                return res

    return "Étudiant"

def extraire_valeur(data: dict, mots_cles: list, defaut: str = "N/A") -> str:
    """Extraction générale des données."""
    exclusions = ["_id", "_uuid", "_submission_time", "_submitted_by"]
    
    for key, val in data.items():
        if key in exclusions or val is None or str(val).strip() == "":
            continue

        clean_key = key.split("/")[-1].lower().replace("_", "").replace("-", "")
        
        for kw in mots_cles:
            kw_clean = kw.lower().replace("_", "").replace("-", "")
            if kw_clean in clean_key:
                return nettoyer_texte(val)
    return defaut

def generer_recu_pdf(nom, matricule, filiere, motif, montant, devise, banque, num_bordereau, date_enregistr, nom_agent):
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

    # Ligne de séparation
    pdf.setLineWidth(1)
    pdf.setStrokeColor(colors.HexColor("#0D3B66"))
    pdf.line(40, height - 95, width - 40, height - 95)

    # Titre
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, height - 130, "REÇU DE PAIEMENT OFFICIEL")

    # Contenu du reçu
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

    # Pied de page
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
    
    print("=== NOUVELLE SOUMISSION KOBO ===")
    print("CLÉS REÇUES :", list(data.keys()))

    # Extraction des champs
    email_destinataire = extraire_valeur(data, ["email", "mail", "courriel"], "")
    
    if not email_destinataire:
        print("❌ ERREUR : Aucun champ e-mail détecté.")
        return {"status": "error", "message": "Adresse e-mail manquante."}

    matricule = extraire_valeur(data, ["matricule", "matr", "code_etudiant"], "Non spécifié")
    nom_etudiant = extraire_nom_etudiant(data, matricule)
    filiere = extraire_valeur(data, ["filiere", "option", "section"], "Non spécifiée")
    motif = extraire_valeur(data, ["motif", "frais", "raison", "paiement"], "Frais d'études")
    montant = extraire_valeur(data, ["montant", "somme", "prix", "valeur"], "0")
    devise = extraire_valeur(data, ["devise", "monnaie", "currency"], "USD")
    banque = extraire_valeur(data, ["banque", "bank", "institution"], "N/A")
    num_bordereau = extraire_valeur(data, ["bordereau", "numero", "ref", "transaction"], "N/A")
    date_enregistr = extraire_valeur(data, ["date", "today"], "N/A")
    
    pin_saisi = extraire_valeur(data, ["pin", "code"], "")
    nom_agent = DICTIONNAIRE_AGENTS.get(pin_saisi, extraire_valeur(data, ["agent", "percepteur"], "Agent Percepteur"))

    # Génération du reçu PDF
    pdf_bytes = generer_recu_pdf(
        nom=nom_etudiant,
        matricule=matricule,
        filiere=filiere,
        motif=motif,
        montant=montant,
        devise=devise,
        banque=banque,
        num_bordereau=num_bordereau,
        date_enregistr=date_enregistr,
        nom_agent=nom_agent
    )

    # Envoi de l'e-mail
    msg = EmailMessage()
    msg["Subject"] = f"Reçu de paiement ISTA-LB - {nom_etudiant} ({matricule})"
    msg["From"] = f"Comptabilité ISTA-LB <{SENDER_EMAIL}>"
    msg["To"] = email_destinataire

    msg.set_content(f"""Bonjour {nom_etudiant},

Veuillez trouver ci-joint votre reçu de paiement officiel délivré par le service de comptabilité de l'ISTA-LB.

RÉCAPITULATIF DU PAIEMENT :
- Nom de l'étudiant : {nom_etudiant}
- Matricule Étudiant : {matricule}
- Filière : {filiere}
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
        filename=f"Recu_ISTA_LB_{matricule}.pdf"
    )

    try:
        with smtplib.SMTP(SMTP_SERVER, 2525, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        print("✅ E-MAIL TRANSMIS AVEC SUCCÈS !")
        return {"status": "success", "message": "Reçu PDF envoyé"}

    except Exception as e:
        print(f"❌ ERREUR ENVOI : {e}")
        return {"status": "failed", "error": str(e)}
