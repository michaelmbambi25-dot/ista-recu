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

# ⚠️ Indiquez ici l'adresse e-mail exacte de votre compte Brevo :
SENDER_EMAIL = "michealmbambi25@gmail.com"

# Dictionnaire de sécurité : Code PIN -> Nom de l'agent
DICTIONNAIRE_AGENTS = {
    "1234": "M. KABANGU Alain",
    "5678": "Mme MAVUNGU Clarisse",
    "0101": "M. DINZENZA Geordi",
    "0303": "M. MBAMBI Mike",
}


def generer_recu_pdf(
    nom,
    matricule,
    filiere,
    motif,
    montant,
    devise,
    banque,
    num_bordereau,
    date_enregistr,
    nom_agent,
):
  """Génère un reçu au format PDF officiel dans la mémoire."""
  buffer = io.BytesIO()
  pdf = canvas.Canvas(buffer, pagesize=A4)
  width, height = A4

  # En-tête officiel ISTA-LB
  pdf.setFont("Helvetica-Bold", 12)
  pdf.setFillColor(colors.HexColor("#0D3B66"))
  pdf.drawString(
      40,
      height - 50,
      "INSTITUT SUPÉRIEUR DES TECHNIQUES APPLIQUÉES DE LUKULA À BOMA",
  )

  pdf.setFont("Helvetica-Bold", 11)
  pdf.drawString(40, height - 68, "(ISTA-LB)")

  pdf.setFont("Helvetica", 10)
  pdf.setFillColor(colors.black)
  pdf.drawString(40, height - 85, "Service de la Comptabilité et des Finances")

  # Ligne de séparation
  pdf.setLineWidth(1)
  pdf.setStrokeColor(colors.HexColor("#0D3B66"))
  pdf.line(40, height - 95, width - 40, height - 95)

  # Titre du document
  pdf.setFont("Helvetica-Bold", 14)
  pdf.drawString(40, height - 130, "REÇU DE PAIEMENT OFFICIEL")

  # Détails du paiement
  pdf.setFont("Helvetica", 10)
  y = height - 165
  interligne = 22

  details = [
      ("Nom de l'étudiant :", nom),
      ("Matricule Étudiant :", matricule),
      ("Filière / Option :", filiere),
      ("Motif du paiement :", motif),
      ("Montant réglé :", f"{montant} {devise}"),
      ("Nom de la banque :", banque),
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
  pdf.drawString(
      40,
      75,
      "Ce document est un reçu électronique officiel délivré par le système"
      " automatisé de l'ISTA-LB.",
  )
  pdf.drawString(
      40, 63, "Toute rature ou falsification rend ce document caduc."
  )

  pdf.showPage()
  pdf.save()

  buffer.seek(0)
  return buffer.getvalue()


@app.post("/webhook-kobo")
async def kobo_webhook(request: Request):
  data = await request.json()

  print("=== NOUVELLE SOUMISSION KOBO ===")

  # 1. Recherche de l'e-mail
  email_destinataire = (
      data.get("email_etudiant")
      or data.get("email")
      or data.get("adresse_email")
      or data.get("mail")
      or data.get("courriel")
  )

  if not email_destinataire:
    for key, value in data.items():
      if "email" in key.lower() or "mail" in key.lower():
        email_destinataire = value
        break

  print(f"--> E-mail détecté : {email_destinataire}")

  if not email_destinataire:
    print("❌ ERREUR : Aucun champ e-mail trouvé.")
    return {
        "status": "error",
        "message": "Adresse e-mail manquante dans le formulaire.",
    }

  # 2. Extraction des données
  matricule = (
      data.get("matricule_prepo")
      or data.get("matricule_elec")
      or data.get("matricule_mec")
      or data.get("matricule_btp")
      or data.get("matricule_st")
      or data.get("matricule")
      or "Non spécifié"
  )

  nom_etudiant = (
      data.get("nom_etudiant")
      or data.get("nom_complet")
      or data.get("nom")
      or "Étudiant"
  )
  filiere = data.get("filiere", "N/A")
  montant = data.get("montant", "0")
  devise = data.get("devise", "USD")

  motif = data.get("motif_paiement") or data.get("motif") or "Frais d'études"
  banque = data.get("nom_banque") or data.get("banque") or "N/A"
  num_bordereau = data.get("num_bordereau") or data.get("bordereau") or "N/A"
  date_enregistr = data.get("date_enregistrement") or data.get("date") or "N/A"

  # 3. Nom de l'agent via Code PIN
  pin_saisi = str(data.get("code_pin_agent", ""))
  nom_agent = DICTIONNAIRE_AGENTS.get(pin_saisi, "Agent Percepteur")

  # 4. Génération PDF
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
      nom_agent=nom_agent,
  )

  # 5. Préparation du Mail avec la bonne adresse expéditeur
  msg = EmailMessage()
  msg["Subject"] = (
      f"Reçu de paiement ISTA-LB - {nom_etudiant} ({matricule})"
  )
  msg["From"] = f"Comptabilité ISTA-LB <{SENDER_EMAIL}>"
  msg["To"] = email_destinataire

  msg.set_content(f"""
Bonjour {nom_etudiant},

Nous vous confirmons la bonne réception de votre règlement.

--- RÉCAPITULATIF DU PAIEMENT ---
• Nom de l'étudiant : {nom_etudiant}
• Matricule Étudiant : {matricule}
• Filière : {filiere}
• Motif du paiement : {motif}
• Montant réglé : {montant} {devise}
• Nom de la banque : {banque}
• N° de bordereau : {num_bordereau}
• Date d'enregistrement : {date_enregistr}
• Nom de l'agent percepteur : {nom_agent}

Votre reçu officiel au format PDF est joint à ce message. Veuillez le télécharger et le conserver pour l'accès aux salles de cours et d'examens.

Cordialement,
Le Service de la Comptabilité et des Finances
ISTA-LB (Boma)
""")

  msg.add_attachment(
      pdf_bytes,
      maintype="application",
      subtype="pdf",
      filename=f"Recu_ISTA_LB_{matricule}.pdf",
  )

  # 6. Envoi via Port 2525
  try:
    print("--> Envoi de l'e-mail...")
    with smtplib.SMTP(SMTP_SERVER, 2525, timeout=15) as server:
      server.starttls()
      server.login(SMTP_USERNAME, SMTP_PASSWORD)
      server.send_message(msg)

    print("✅ E-MAIL TRANSMIS À BREVO AVEC SUCCÈS !")
    return {"status": "success", "message": "Reçu PDF envoyé"}

  except Exception as e:
    print(f"❌ ERREUR ENVOI : {e}")
    return {"status": "failed", "error": str(e)}
