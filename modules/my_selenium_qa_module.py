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
        wait = WebDriverWait(driver, 15)  # Warte bis zu 15 Sekunden auf das Popup
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

    Geht dabei so vor:
    1. Finde ein Element, das den Text der 'question_text' enthält.
    2. Schaue in den Folgesiblings (folgenden Elementen) nach Text.
    3. Sobald eines der folgenden Elemente nicht-leeren Text hat, wird dieser zurückgegeben.
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            # 1) Finde die Frage im DOM:
            question_element = driver.find_element(
                By.XPATH, f"//*[contains(text(), '{question_text}')]"
            )
            # 2) Nimm sämtliche unmittelbar folgenden Geschwister-Elemente
            siblings = question_element.find_elements(By.XPATH, "following-sibling::*")

            # 3) Prüfe jedes dieser folgenden Elemente auf nicht-leeren Text
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
    Öffnet die gegebene URL in einer eigenen Browserinstanz, versucht, das Einwilligungspopup zu schließen,
    sucht nach einem Eingabefeld, sendet die Frage und wartet auf die Antwort.
    
    Gibt die gefundene Antwort als String zurück (oder None, falls keine Antwort).
    """
    service = Service(ChromeDriverManager().install())

    # Optional: Headless-Chrome verwenden, damit kein Fenster aufspringt
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # auskommentieren, wenn du GUI-Fenster sehen willst
    
    driver = webdriver.Chrome(service=service, options=options)
    
    # Seite aufrufen
    driver.get(url)
    time.sleep(3)  # Kurze Wartezeit für initiales Laden
    
    # Cookies akzeptieren (falls möglich)
    accept_cookies(driver)
    
    # Eingabefeld suchen
    input_field = find_input_field(driver)
    if not input_field:
        st.write("Kein Eingabefeld gefunden. Bitte prüfe die Selektoren oder Seitenstruktur.")
        driver.quit()
        return None

    # Frage senden
    input_field.click()
    input_field.send_keys(question)
    input_field.send_keys(Keys.RETURN)
    st.write("Frage wurde gesendet, warte auf die Antwort...")

    # Warten, bis ein Text unter der Frage erscheint
    answer = wait_for_answer(driver, question, timeout=60, poll_frequency=2)
    
    driver.quit()
    
    return answer

def main():
    st.title("Selenium-Frage-Antwort mit Streamlit")
    
    st.write("Dieses kleine Tool nutzt Selenium, um auf eine Seite zu gehen, eine Frage einzugeben und die Antwort auszulesen.")

    # Eingabe für URL und Frage
    url = st.text_input("URL eingeben (z.B. https://chatgpt.ch/):", "https://chatgpt.ch/")
    question = st.text_input("Frage eingeben:", "Was ist die Hauptstadt von Österreich?")

    if st.button("Frage stellen"):
        st.write(f"Ich stelle nun folgende Frage: '{question}' an '{url}' ...")
        answer = ask_question(url, question)

        if answer:
            st.write("**Antwort:**", answer)
        else:
            st.write("Keine Antwort gefunden oder Timeout erreicht.")


if __name__ == "__main__":
    main()
