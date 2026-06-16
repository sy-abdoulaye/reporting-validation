import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Optional
import os

class EmailService:
    """Service d'envoi d'emails"""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("EMAIL_FROM", "reporting@example.com")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "Reporting App")
        # STARTTLS : "auto" = activé seulement si identifiants ; "true"/"false" pour forcer
        self.use_tls = os.getenv("SMTP_TLS", "auto").lower()

    def _send(self, msg, to_emails: List[str]) -> bool:
        """Logique commune d'envoi SMTP (TLS conditionnel)."""
        try:
            has_creds = bool(self.smtp_user and self.smtp_password)
            want_tls = self.use_tls == "true" or (self.use_tls == "auto" and has_creds)
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20) as server:
                if want_tls:
                    server.starttls()
                if has_creds:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            print(f"✅ Email envoyé à {', '.join(to_emails)} via {self.smtp_host}:{self.smtp_port}")
            return True
        except Exception as e:
            print(f"❌ Erreur email ({self.smtp_host}:{self.smtp_port}): {type(e).__name__}: {e}")
            return False

    async def send_message(self, to_emails: List[str], subject: str, body: str) -> bool:
        """Envoie un email simple (sans pièce jointe)."""
        msg = MIMEMultipart()
        msg['From'] = f"{self.from_name} <{self.from_email}>"
        msg['To'] = ', '.join(to_emails)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        return self._send(msg, to_emails)

    async def send_report(
        self,
        to_emails: List[str],
        subject: str,
        body: str,
        attachment_path: Path,
        attachment_name: Optional[str] = None
    ) -> bool:
        """
        Envoie un email avec pièce jointe
        """
        try:
            # Créer le message
            msg = MIMEMultipart()
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = subject

            # Ajouter le corps
            msg.attach(MIMEText(body, 'plain'))

            # Ajouter la pièce jointe
            with open(attachment_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)

                filename = attachment_name or attachment_path.name
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                msg.attach(part)

            return self._send(msg, to_emails)

        except Exception as e:
            print(f"❌ Erreur email ({self.smtp_host}:{self.smtp_port}): {type(e).__name__}: {e}")
            return False