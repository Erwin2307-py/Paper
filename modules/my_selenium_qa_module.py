# Datei: my_selenium_qa_module.py
import streamlit as st
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def accept_cookies(driver):
    """
    Sucht nach einem Cookie-Einwilligungspopup und klickt auf den Zustimmungs-Button.
    """
    try:
        wait = WebDriverWait(driver, 15)
        cookie_button = wait.until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    "button[id='cookie-consent-button'], "
                    "button[class*='cookie'], "
                    "button[class*='consent'], "
                    "button[class*='accept']"
                )
            )
        )
        cookie_button.click()
        st.write("Cookie-Einwilligung wurde akzeptiert.")
    except Exception as e:
        st.write("Kein Cookie-Einwilligungspopup gefunden oder Fehler beim Klicken:", e)

def find_input_field(driver):
    """
    Versucht, das Eingabefeld über mehrere mögliche Selektoren zu finden.
    """
    selectors = ["#prompt-textarea", "textarea", "div[contenteditable='true']"]
    for sel in selectors:
        try:
            field = driver.find_element(By.CSS_SELECTOR, sel)
            if field.is_displayed() and field.is_enabled():
                return field
        except Exception:
            continue
    return None

def wait_for_answer(driver, question_text, timeout=300, poll_frequency=2):
    """
    Wartet bis zum Timeout darauf, dass im DOM die Frage gefunden wird
    und darunter ein nicht-leerer Text erscheint.

    1. Finde ein Element, das den Text von 'question_text' enthält.
    2. Schaue in den folgenden Geschwister-Elementen nach Text.
    3. Sobald eines davon nicht-leeren Text hat, wird dieser zurückgegeben.
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            # Frage-Element im DOM suchen
            question_element = driver.find_element(
                By.XPATH, f"//*[contains(text(), '{question_text}')]"
            )
            # Unmittelbare "folgenden" Geschwister-Elemente holen
            siblings = question_element.find_elements(By.XPATH, "following-sibling::*")

            # Jedes dieser Geschwister auf nicht-leeren Text prüfen
            for sib in siblings:
                text = sib.text.strip()
                if text:
                    return text

        except Exception:
            pass

        time.sleep(poll_frequency)
    return None

def ask_question(url, question):
    """
    Öffnet die gegebene URL in einer eigenen Browserinstanz, versucht,
    das Einwilligungspopup zu schließen, sucht nach einem Eingabefeld,
    sendet die Frage und wartet auf die Antwort.

    Gibt die Antwort als String zurück (oder None, falls keine gefunden).
    """
    # Installiere/aktualisiere ChromeDriver automatisch
    service = Service(ChromeDriverManager().install())

    # Browser-Optionen anpassen: Headless + No-Sandbox + Dev-Shm
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Ohne sichtbare UI
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # ChromeDriver starten
    driver = webdriver.Chrome(service=service, options=options)

    # Seite laden
    driver.get(url)
    time.sleep(3)  # Kurze Pause, damit alles initial laden kann

    # Cookies akzeptieren (falls vorhanden)
    accept_cookies(driver)

    # Eingabefeld suchen
    input_field = find_input_field(driver)
    if not input_field:
        st.write("Kein Eingabefeld gefunden. Bitte prüfe die Selektoren oder Seitenstruktur.")
        driver.quit()
        return None

    # Frage eingeben und abschicken
    input_field.click()
    input_field.send_keys(question)
    input_field.send_keys(Keys.RETURN)
    st.write("Frage wurde gesendet, warte auf die Antwort...")

    # Warten, bis ein Text direkt unter der Frage erscheint
    answer = wait_for_answer(driver, question, timeout=60, poll_frequency=2)
    driver.quit()

    return answer

def main():
    st.title("Selenium-Frage-Antwort mit Streamlit (Headless Chrome)")

    st.write("Dieses Tool nutzt Selenium (Headless Chrome), um eine Seite aufzurufen, eine Frage einzugeben und die Antwort auszulesen.")

    # Benutzer-Eingaben
    url = st.text_input("URL eingeben (z.B. https://chatgpt.ch/):", "https://chatgpt.ch/")
    question = st.text_input("Frage eingeben:", "Was ist die Hauptstadt von Österreich?")

    # Button zum Abschicken der Frage
    if st.button("Frage stellen"):
        st.write(f"Ich stelle folgende Frage an {url}: {question}")
        answer = ask_question(url, question)
        if answer:
            st.write("**Antwort:**", answer)
        else:
            st.write("Keine Antwort gefunden oder Timeout.")
