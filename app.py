import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.types import Text

# --- App-Konfiguration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dein-sehr-geheimer-schluessel'  # Ändere das!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lernplattform.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Bitte logge dich ein, um diese Seite zu sehen."
login_manager.login_message_category = "info"

QUIZZES_FOLDER = 'quizzes'
EXP_PER_QUESTION = 10  # Wie viel EXP gibt es pro richtiger Antwort

# --- Datenbankmodelle ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')
    exp = db.Column(db.Integer, default=0)
    nemesis_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    nemesis = db.relationship(
        'User',
        foreign_keys=[nemesis_id],
        remote_side=[id]
    )
    
    # Relationen für Schüler
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relationen für Lehrer
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
    results = db.Column(Text, nullable=True) 

    user = db.relationship('User', backref='progress')


# --- Hilfsfunktionen ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def load_quiz(quiz_name):
    file_path = os.path.join(QUIZZES_FOLDER, f"{quiz_name}.json")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def get_all_quizzes():
    quizzes = []
    if not os.path.exists(QUIZZES_FOLDER):
        os.makedirs(QUIZZES_FOLDER)
        return []
        
    for filename in os.listdir(QUIZZES_FOLDER):
        if filename.endswith('.json'):
            quiz_name = filename.split('.')[0]
            quiz_data = load_quiz(quiz_name)
            if quiz_data:
                num_questions = len(quiz_data.get("questions", []))
                quizzes.append({
                    'name': quiz_name,
                    'title': quiz_data.get('title', 'Unbenanntes Quiz'),
                    'max_xp': num_questions * EXP_PER_QUESTION
                })
    return quizzes


# --- Authentifizierungs-Routen ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            session['daily_bonus_shown'] = False
            return redirect(url_for('dashboard'))
        else:
            flash('Ungültiger Benutzername oder Passwort.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
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
@app.route('/set_nemesis', methods=['POST'])
@login_required
def set_nemesis():
    if current_user.role != 'student':
        abort(403)

    nemesis_id = request.form.get('nemesis_id')

    if not nemesis_id:
        current_user.nemesis_id = None
        db.session.commit()
        flash("Nemesis entfernt.", "info")
        return redirect(url_for('dashboard'))

    nemesis = User.query.filter_by(
        id=nemesis_id,
        group_id=current_user.group_id,
        role='student'
    ).first()

    if not nemesis or nemesis.id == current_user.id:
        flash("Ungültiger Nemesis.", "danger")
        return redirect(url_for('dashboard'))

    current_user.nemesis_id = nemesis.id
    db.session.commit()

    flash(f"🔥 {nemesis.username} ist jetzt dein Nemesis!", "success")
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# --- Kern-Routen (Dashboards & Co.) ---

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'teacher':
        groups = Group.query.filter_by(teacher_id=current_user.id).all()
        students_no_group = User.query.filter_by(teacher_id=current_user.id, group_id=None, role='student').all()
        return render_template('dashboard_teacher.html', groups=groups, students_no_group=students_no_group)
    else:
        all_quizzes = get_all_quizzes()
        progress = QuizProgress.query.filter_by(user_id=current_user.id).all()
        completed_quizzes = {p.quiz_name for p in progress if p.completed}


        daily_bonus = None
        if not session.get('daily_bonus_shown'):
            daily_bonus = 5
            current_user.exp += daily_bonus
            db.session.commit()
            session['daily_bonus_shown'] = True


        earned_xp = {p.quiz_name: p.exp_earned for p in progress}


        xp_delta = None
        xp_target_name = None
        ahead = False

        if current_user.nemesis:
            xp_target_name = current_user.nemesis.username
            xp_delta = abs(current_user.exp - current_user.nemesis.exp)
            ahead = current_user.exp >= current_user.nemesis.exp


        group_students = []
        group = current_user.group
        if group:
            group_students = User.query.filter_by(
                group_id=group.id,
                role='student'
            ).all()


        mini_leaderboard = []
        my_position = None

        if group:
            students = User.query.filter_by(
                group_id=group.id,
                role='student'
            ).order_by(User.exp.desc()).all()

            my_index = None
            for idx, s in enumerate(students):
                if s.id == current_user.id:
                    my_index = idx
                    my_position = idx + 1  # 1-based
                    break

            if my_index is not None:
                wanted_ids = {current_user.id}

                if my_index - 1 >= 0:
                    wanted_ids.add(students[my_index - 1].id)  # above
                if my_index + 1 < len(students):
                    wanted_ids.add(students[my_index + 1].id)  # below

                if current_user.nemesis:
                    wanted_ids.add(current_user.nemesis.id)

                mini_leaderboard = [
                    {'id': s.id, 'name': s.username, 'exp': s.exp}
                    for s in students
                    if s.id in wanted_ids
                ]



        return render_template(
            'dashboard_student.html',
            all_quizzes=all_quizzes,
            completed_quizzes=completed_quizzes,
            earned_xp=earned_xp,
            daily_bonus=daily_bonus,
            xp_delta=xp_delta,
            xp_target_name=xp_target_name,
            ahead=ahead,
            mini_leaderboard=mini_leaderboard,
            my_position=my_position,
            group_students=group_students
        )



@app.route('/leaderboard')
@login_required
def leaderboard():
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
    if not current_user.group:
        flash('Du bist in keiner Gruppe, um eine Rangliste anzuzeigen.', 'info')
        return render_template('leaderboard.html', students_ranked=None, group_name=None)
        
    students_ranked = User.query.filter_by(group_id=current_user.group_id) \
                                .order_by(User.exp.desc()) \
                                .all()
    return render_template('leaderboard.html', 
                           students_ranked=students_ranked, 
                           group_name=current_user.group.name)



@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    if current_user.role != 'teacher':
        abort(403)
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
    if current_user.role != 'student':
        flash('Nur Schüler können Quizzes bearbeiten.', 'warning')
        return redirect(url_for('dashboard'))
    progress = QuizProgress.query.filter_by(user_id=current_user.id, quiz_name=quiz_name).first()
    if not progress:
        progress = QuizProgress(user_id=current_user.id, quiz_name=quiz_name)
        db.session.add(progress)
        db.session.commit()
    practice_mode = request.args.get("practice") == "1"
    if progress.completed and not practice_mode:
        flash('Du hast dieses Quiz bereits abgeschlossen.', 'info')
        return redirect(url_for('quiz_finished', quiz_name=quiz_name))
    session['quiz_answers'] = []
    return redirect(url_for('show_question', 
                        quiz_name=quiz_name, 
                        question_index=0, 
                        practice=1 if practice_mode else None))


@app.route('/quiz/<quiz_name>/<int:question_index>', methods=['GET', 'POST'])
@login_required
def show_question(quiz_name, question_index):
    if current_user.role != 'student':
        abort(403)

    quiz_data = load_quiz(quiz_name)
    if not quiz_data:
        abort(404, "Quiz nicht gefunden!")

    questions = quiz_data.get("questions", [])
    practice_mode = request.args.get("practice") == "1"  # <-- Practice mode flag

    if question_index >= len(questions):
        return redirect(url_for('quiz_finished', quiz_name=quiz_name))

    current_question = questions[question_index]

    # Load progress
    progress = QuizProgress.query.filter_by(
        user_id=current_user.id, 
        quiz_name=quiz_name
    ).first()

    if not progress:
        flash('Quiz konnte nicht geladen werden.', 'danger')
        return redirect(url_for('dashboard'))

    if progress.completed and not practice_mode:
        flash('Dieses Quiz ist bereits abgeschlossen.', 'info')
        return redirect(url_for('quiz_finished', quiz_name=quiz_name))

    if request.method == 'POST':

        user_answer = request.form.get('answer', '').strip()
        correct_answer = current_question.get('answer')
        is_correct = user_answer.lower() == correct_answer.lower()

        if 'quiz_answers' not in session:
            session['quiz_answers'] = []

        session['quiz_answers'].append({
            'question': current_question.get('text'),
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct
        })

        if is_correct:
            flash('Richtig!', 'success')

            # XP ONLY IN REAL MODE
            if not practice_mode:
                current_user.exp += EXP_PER_QUESTION
                progress.exp_earned += EXP_PER_QUESTION
                db.session.commit()

        else:
            flash(f'Falsch. Die richtige Antwort war: {correct_answer}', 'danger')

        next_index = question_index + 1
        if next_index < len(questions):
            return redirect(url_for(
                'show_question',
                quiz_name=quiz_name,
                question_index=next_index,
                practice=1 if practice_mode else None
            ))


        else:
            if not practice_mode:
                progress.completed = True
                progress.results = json.dumps(session.get('quiz_answers', []))
                db.session.commit()

            session.pop('quiz_answers', None)

            return redirect(url_for('quiz_finished', quiz_name=quiz_name))

    # Render question
    return render_template(
        'quiz.html',
        quiz_name=quiz_name,
        question=current_question,
        question_index=question_index,
        total_questions=len(questions),
        max_xp=len(questions) * EXP_PER_QUESTION
    )



@app.route('/quiz/finished/<quiz_name>')
@login_required
def quiz_finished(quiz_name):
    quiz_data = load_quiz(quiz_name)
    progress = QuizProgress.query.filter_by(user_id=current_user.id, quiz_name=quiz_name).first()
    if not quiz_data or not progress:
        abort(404)
    results = []
    if progress.results:
        results = json.loads(progress.results)
    return render_template('quiz_end.html',
                           quiz_title=quiz_data.get("title"),
                           exp_earned=progress.exp_earned,
                           results=results)
@app.route('/change_student_group', methods=['POST'])
@login_required
def change_student_group():
    if current_user.role != 'teacher':
        abort(403)

    student_id = request.form.get('student_id')
    new_group_id = request.form.get('new_group_id')

    student = User.query.filter_by(id=student_id, teacher_id=current_user.id).first()
    group = Group.query.filter_by(id=new_group_id, teacher_id=current_user.id).first()

    if not student:
        flash("Ungültiger Schüler.", "danger")
        return redirect(url_for('dashboard'))

    if not group:
        flash("Ungültige Gruppe.", "danger")
        return redirect(url_for('dashboard'))

    student.group_id = new_group_id
    db.session.commit()

    flash(f'Schüler \"{student.username}\" wurde in die Gruppe \"{group.name}\" verschoben.', "success")
    return redirect(url_for('dashboard'))



# --- App-Start & DB-Erstellung ---

if __name__ == '__main__':
    if not os.path.exists(QUIZZES_FOLDER):
        os.makedirs(QUIZZES_FOLDER)
    with app.app_context():
        db.create_all()
    app.run(debug=True)
