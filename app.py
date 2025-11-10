import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# --- App-Konfiguration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dein-sehr-geheimer-schluessel'  # Ändere das!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lernplattform.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' # Wohin wird man bei @login_required umgeleitet?
login_manager.login_message = "Bitte logge dich ein, um diese Seite zu sehen."
login_manager.login_message_category = "info"

QUIZZES_FOLDER = 'quizzes'
EXP_PER_QUESTION = 10  # Wie viel EXP gibt es pro richtiger Antwort

# --- Datenbankmodelle ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student') # 'student' or 'teacher'
    exp = db.Column(db.Integer, default=0)
    
    # Relationen für Schüler
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relationen für Lehrer
    # 'students' wird über 'teacher_id' Backref erstellt
    groups = db.relationship('Group', backref='teacher', lazy=True, foreign_keys='Group.teacher_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    students = db.relationship('User', backref='group', lazy=True, foreign_keys='User.group_id')

class QuizProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    quiz_name = db.Column(db.String(100), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    exp_earned = db.Column(db.Integer, default=0)
    
    user = db.relationship('User', backref='progress')

# --- Hilfsfunktionen ---

@login_manager.user_loader
def load_user(user_id):
    """Lädt den User für Flask-Login."""
    return User.query.get(int(user_id))

def load_quiz(quiz_name):
    """Lädt eine Quiz-Datei (JSON)."""
    file_path = os.path.join(QUIZZES_FOLDER, f"{quiz_name}.json")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def get_all_quizzes():
    """Scannt den quizzes-Ordner und lädt Metadaten."""
    quizzes = []
    if not os.path.exists(QUIZZES_FOLDER):
        os.makedirs(QUIZZES_FOLDER)
        return []
        
    for filename in os.listdir(QUIZZES_FOLDER):
        if filename.endswith('.json'):
            quiz_name = filename.split('.')[0]
            quiz_data = load_quiz(quiz_name)
            if quiz_data:
                quizzes.append({
                    'name': quiz_name,
                    'title': quiz_data.get('title', 'Unbenanntes Quiz')
                })
    return quizzes

# --- Authentifizierungs-Routen ---

@app.route('/')
def index():
    """Startseite, leitet zum Dashboard oder Login weiter."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login-Seite."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Ungültiger Benutzername oder Passwort.', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registrierungsseite (NUR FÜR LEHRER)."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Dieser Benutzername ist bereits vergeben.', 'warning')
            return redirect(url_for('register'))
            
        new_teacher = User(username=username, role='teacher')
        new_teacher.set_password(password)
        db.session.add(new_teacher)
        db.session.commit()
        
        flash('Lehrer-Account erfolgreich erstellt. Bitte einloggen.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    """Logout-Route."""
    logout_user()
    return redirect(url_for('index'))

# --- Kern-Routen (Dashboards & Co.) ---

@app.route('/dashboard')
@login_required
def dashboard():
    """Zeigt das Dashboard je nach Rolle an."""
    if current_user.role == 'teacher':
        # Lehrer-Dashboard: Zeigt Gruppen und Schüler
        groups = Group.query.filter_by(teacher_id=current_user.id).all()
        # Schüler ohne Gruppe, die diesem Lehrer zugeordnet sind
        students_no_group = User.query.filter_by(teacher_id=current_user.id, group_id=None, role='student').all()
        return render_template('dashboard_teacher.html', groups=groups, students_no_group=students_no_group)
        
    else:
        # Schüler-Dashboard: Zeigt verfügbare Quizzes und Fortschritt
        all_quizzes = get_all_quizzes()
        progress = QuizProgress.query.filter_by(user_id=current_user.id).all()
        
        # Erstelle ein Set mit Namen der erledigten Quizzes für schnellen Check im Template
        completed_quizzes = {p.quiz_name for p in progress if p.completed}
        
        return render_template('dashboard_student.html', 
                               all_quizzes=all_quizzes, 
                               completed_quizzes=completed_quizzes)

@app.route('/leaderboard')
@login_required
def leaderboard():
    """Zeigt die Rangliste für die Gruppe des Schülers."""
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
        
    if not current_user.group:
        flash('Du bist in keiner Gruppe, um eine Rangliste anzuzeigen.', 'info')
        return render_template('leaderboard.html', students_ranked=None, group_name=None)
        
    # Hole alle Schüler aus derselben Gruppe, sortiert nach EXP
    students_ranked = User.query.filter_by(group_id=current_user.group_id) \
                                .order_by(User.exp.desc()) \
                                .all()
                                
    return render_template('leaderboard.html', 
                           students_ranked=students_ranked, 
                           group_name=current_user.group.name)

# --- Lehrer-Aktionen (Schüler/Gruppen erstellen) ---

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    if current_user.role != 'teacher':
        abort(403) # Zugriff verweigert
        
    group_name = request.form.get('group_name')
    if group_name:
        new_group = Group(name=group_name, teacher_id=current_user.id)
        db.session.add(new_group)
        db.session.commit()
        flash(f'Gruppe "{group_name}" erstellt.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/create_student', methods=['POST'])
@login_required
def create_student():
    if current_user.role != 'teacher':
        abort(403)
        
    username = request.form.get('username')
    password = request.form.get('password')
    group_id = request.form.get('group_id')
    
    if not username or not password:
        flash('Benutzername und Passwort sind erforderlich.', 'danger')
        return redirect(url_for('dashboard'))
        
    if User.query.filter_by(username=username).first():
        flash('Dieser Benutzername ist bereits vergeben.', 'warning')
        return redirect(url_for('dashboard'))
        
    new_student = User(username=username, role='student', teacher_id=current_user.id)
    new_student.set_password(password)
    
    if group_id:
        # Sicherstellen, dass die Gruppe dem Lehrer gehört
        group = Group.query.filter_by(id=group_id, teacher_id=current_user.id).first()
        if group:
            new_student.group_id = group_id
        else:
            flash('Ungültige Gruppe ausgewählt.', 'warning')
            
    db.session.add(new_student)
    db.session.commit()
    flash(f'Schüler-Account "{username}" erstellt.', 'success')
    return redirect(url_for('dashboard'))

# --- Quiz-Routen ---

@app.route('/quiz/start/<quiz_name>')
@login_required
def start_quiz(quiz_name):
    """Leitet zur ersten Frage weiter und stellt sicher, dass der User Schüler ist."""
    if current_user.role != 'student':
        flash('Nur Schüler können Quizzes bearbeiten.', 'warning')
        return redirect(url_for('dashboard'))
        
    # Erstelle oder hole den Fortschritt-Eintrag
    progress = QuizProgress.query.filter_by(user_id=current_user.id, quiz_name=quiz_name).first()
    if not progress:
        progress = QuizProgress(user_id=current_user.id, quiz_name=quiz_name)
        db.session.add(progress)
        db.session.commit()
    
    # Wenn bereits erledigt, zur Übersichtsseite
    if progress.completed:
        flash('Du hast dieses Quiz bereits abgeschlossen.', 'info')
        return redirect(url_for('quiz_finished', quiz_name=quiz_name))
        
    return redirect(url_for('show_question', quiz_name=quiz_name, question_index=0))

@app.route('/quiz/<quiz_name>/<int:question_index>', methods=['GET', 'POST'])
@login_required
def show_question(quiz_name, question_index):
    """Zeigt eine einzelne Frage an und verarbeitet die Antwort."""
    if current_user.role != 'student':
        abort(403)
        
    quiz_data = load_quiz(quiz_name)
    if not quiz_data:
        abort(404, "Quiz nicht gefunden!")

    questions = quiz_data.get("questions", [])
    if question_index >= len(questions):
        # Sollte nicht passieren, aber sicher ist sicher
        return redirect(url_for('quiz_finished', quiz_name=quiz_name))

    current_question = questions[question_index]
    
    # Hole den Fortschritt-Eintrag (sollte von start_quiz erstellt worden sein)
    progress = QuizProgress.query.filter_by(user_id=current_user.id, quiz_name=quiz_name).first()
    if not progress or progress.completed:
        # Verhindere, dass erledigte Quizzes erneut EXP geben
        flash('Dieses Quiz ist bereits abgeschlossen.', 'info')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        user_answer = request.form.get('answer', '').strip()
        correct_answer = current_question.get('answer')

        if user_answer.lower() == correct_answer.lower():
            flash('Richtig!', 'success')
            # Nur EXP geben, wenn die Antwort korrekt ist
            current_user.exp += EXP_PER_QUESTION
            progress.exp_earned += EXP_PER_QUESTION
            db.session.commit()
        else:
            flash(f'Falsch. Die richtige Antwort war: {correct_answer}', 'danger')
        
        next_question_index = question_index + 1
        if next_question_index < len(questions):
            return redirect(url_for('show_question', quiz_name=quiz_name, question_index=next_question_index))
        else:
            # Quiz ist beendet
            progress.completed = True
            db.session.commit()
            return redirect(url_for('quiz_finished', quiz_name=quiz_name))

    # GET-Request: Frage anzeigen
    return render_template('quiz.html', 
                           quiz_name=quiz_name,
                           question=current_question, 
                           question_index=question_index,
                           total_questions=len(questions))

@app.route('/quiz/finished/<quiz_name>')
@login_required
def quiz_finished(quiz_name):
    """Zeigt die Abschluss-Seite für ein Quiz."""
    quiz_data = load_quiz(quiz_name)
    progress = QuizProgress.query.filter_by(user_id=current_user.id, quiz_name=quiz_name).first()
    
    if not quiz_data or not progress:
        abort(404)
        
    return render_template('quiz_end.html', 
                           quiz_title=quiz_data.get("title"), 
                           exp_earned=progress.exp_earned)

# --- App-Start & DB-Erstellung ---

if __name__ == '__main__':
    # Stellt sicher, dass die Ordner existieren
    if not os.path.exists(QUIZZES_FOLDER):
        os.makedirs(QUIZZES_FOLDER)
    
    # Erstellt die Datenbanktabellen, falls sie nicht existieren
    with app.app_context():
        db.create_all()
        
    app.run(debug=True)