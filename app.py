import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
# Ein Secret Key wird für 'flash' Nachrichten benötigt, um Feedback zu geben.
app.secret_key = 'supersecretkey' 

# Pfad zum Ordner, in dem unsere Quiz-Dateien liegen
QUIZZES_FOLDER = 'quizzes'

def load_quiz(quiz_name):
    """Lädt eine Quiz-Datei (JSON) aus dem quizzes-Ordner."""
    file_path = os.path.join(QUIZZES_FOLDER, f"{quiz_name}.json")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None # Quiz nicht gefunden

@app.route('/')
def home():
    """Die Startseite, die eine Liste aller verfügbaren Quizzes anzeigt."""
    # Diese Funktion könnte erweitert werden, um alle .json-Dateien im quizzes-Ordner zu finden
    # Für den Prototyp reicht ein hartcodierter Link.
    return render_template('index.html')

@app.route('/quiz/<quiz_name>')
def start_quiz(quiz_name):
    """Leitet den Benutzer zur ersten Frage des ausgewählten Quizzes weiter."""
    # Dies ist eine saubere Start-URL, bevor man in die Fragen eintaucht.
    return redirect(url_for('show_question', quiz_name=quiz_name, question_index=0))

@app.route('/quiz/<quiz_name>/<int:question_index>', methods=['GET', 'POST'])
def show_question(quiz_name, question_index):
    """Zeigt eine einzelne Frage an und verarbeitet die Antwort."""
    quiz_data = load_quiz(quiz_name)

    if not quiz_data:
        return "Quiz nicht gefunden!", 404

    questions = quiz_data.get("questions", [])
    
    if question_index >= len(questions):
        # Sollte nicht passieren, fängt aber Fehler ab
        return redirect(url_for('home'))

    current_question = questions[question_index]

    if request.method == 'POST':
        user_answer = request.form.get('answer', '').strip()
        correct_answer = current_question.get('answer')

        # Einfache Überprüfung (Groß-/Kleinschreibung wird ignoriert)
        if user_answer.lower() == correct_answer.lower():
            flash('Richtig!', 'success')
        else:
            flash(f'Falsch. Die richtige Antwort war: {correct_answer}', 'danger')
        
        next_question_index = question_index + 1
        if next_question_index < len(questions):
            # Weiter zur nächsten Frage
            return redirect(url_for('show_question', quiz_name=quiz_name, question_index=next_question_index))
        else:
            # Quiz ist beendet
            return render_template('quiz_end.html', quiz_title=quiz_data.get("title"))

    # GET-Request: Frage anzeigen
    return render_template('quiz.html', 
                           quiz_name=quiz_name,
                           question=current_question, 
                           question_index=question_index,
                           total_questions=len(questions))

if __name__ == '__main__':
    # Stellt sicher, dass der 'quizzes'-Ordner existiert
    if not os.path.exists(QUIZZES_FOLDER):
        os.makedirs(QUIZZES_FOLDER)
    app.run(debug=True)
