"""Client HTTP pour l'API mailing.weltaare-tech.com.

Envoie des emails via l'API REST avec authentification X-API-Secret.
Documentation: https://mailing.weltaare-tech.com/docs
"""

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def send_email(
    recipient_email: str,
    subject: str,
    body_html: str,
    recipient_name: str = "",
    sender_name: str = "",
) -> bool:
    """Envoie un email via l'API mailing.weltaare-tech.com.

    Args:
        recipient_email: Adresse email du destinataire.
        subject: Sujet de l'email.
        body_html: Corps HTML de l'email.
        recipient_name: Nom du destinataire (optionnel).
        sender_name: Nom de l'expediteur (optionnel, utilise la config sinon).

    Returns:
        True si l'email a ete envoye avec succes, False sinon.
    """
    if not settings.mailer_api_secret:
        logger.error("X-API-Secret non configure - impossible d'envoyer l'email")
        return False

    payload: dict = {
        "recipient_email": recipient_email,
        "subject": subject,
        "body_html": body_html,
    }

    if recipient_name:
        payload["recipient_name"] = recipient_name
    if sender_name:
        payload["sender_name"] = sender_name
    elif settings.report_sender_name:
        payload["sender_name"] = settings.report_sender_name

    logger.info(f"Envoi email a {recipient_email} | Sujet: {subject}")

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                settings.mailer_api_url,
                json=payload,
                headers={
                    "X-API-Secret": settings.mailer_api_secret,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 201:
                data = response.json()
                email_uuid = data.get("uuid", "unknown")
                logger.info(f"Email envoye avec succes - UUID: {email_uuid}")
                return True
            elif response.status_code == 429:
                logger.warning(f"Rate limit atteint pour l'envoi d'email: {response.text}")
                return False
            elif response.status_code == 401:
                logger.error(f"X-API-Secret invalide: {response.text}")
                return False
            else:
                logger.error(f"Echec envoi email ({response.status_code}): {response.text[:300]}")
                return False

    except httpx.TimeoutException:
        logger.error("Timeout lors de l'envoi de l'email")
        return False
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email: {e}")
        return False
