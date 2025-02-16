from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import os
from datetime import datetime
from flask_migrate import Migrate
import random
from flask import session
import sqlite3
from sqlalchemy import event
from sqlalchemy.engine import Engine

import sqlite3
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Replace with a secure key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///treasurehunt.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# ---------------------------
# Models
# ---------------------------
# In main.py (or your models file)
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class Team(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), unique=True, nullable=False)
    assigned_team_id = db.Column(db.String(50), unique=True, nullable=True)
    password_hash = db.Column(db.String(128))
    current_step = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, default=False)
    leader_phone = db.Column(db.String(20), nullable=True)
    security_question = db.Column(db.String(255), nullable=True)
    security_answer = db.Column(db.String(255), nullable=True)
    
    # Define relationship with cascade deletion
    logs = db.relationship('ScanLog', backref='team', lazy=True, cascade="all, delete-orphan")
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    
    # Define the relationship with cascade delete
    logs = db.relationship('ScanLog', backref='team', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)




class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    player_name = db.Column(db.String(100), nullable=True)  # nullable for older records
    roll_no = db.Column(db.String(50), nullable=True)         # nullable for older records

# Create a relationship for easier access:
Team.players = db.relationship('Player', backref='team', lazy=True)


class TeamPath(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_identifier = db.Column(db.String(50))  # e.g., "TeamAlpha", "TeamBeta", etc.
    sequence_number = db.Column(db.Integer)       # order of the clue
    location_code = db.Column(db.String(50))
    riddle = db.Column(db.Text)


class ScanLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id', ondelete='CASCADE'), nullable=False)
    sequence_number = db.Column(db.Integer, nullable=False)
    qr_code = db.Column(db.String(50))
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)


# Optional: Add a relationship to the Team model for easy access
Team.logs = db.relationship('ScanLog', backref='team', lazy=True)




@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Enable foreign key constraints in SQLite
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


# ---------------------------
# User Loader
# ---------------------------
@login_manager.user_loader
def load_user(user_id):
    return Team.query.get(int(user_id))

# ---------------------------
# Create DB tables (if not present)
# ---------------------------
def create_tables():
    db.create_all()

# ---------------------------
# Routes
# ---------------------------
@app.route('/')
def index():
    return redirect(url_for('login'))

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get and normalize form data
        team_name = request.form.get('team_name').strip()
        password = request.form.get('password')
        leader_phone = request.form.get('leader_phone').strip()
        security_question = request.form.get('security_question').strip()
        security_answer = request.form.get('security_answer').strip()
        
        # Ensure the team name is unique.
        if Team.query.filter_by(team_name=team_name).first():
            flash('Team name already exists. Please choose a different name.')
            return redirect(url_for('register'))
        
        # Get all assigned team identifiers from existing teams.
        assigned_ids = {
            team.assigned_team_id 
            for team in Team.query.filter(Team.assigned_team_id != None).all() 
            if team.assigned_team_id is not None
        }
        
        # Get the set of all available team identifiers from the TeamPath table.
        available_ids = {
            row.team_identifier 
            for row in db.session.query(TeamPath.team_identifier).distinct().all()
        }
        
        # Determine which team identifiers have not been allocated yet.
        unused_ids = available_ids - assigned_ids
        
        if not unused_ids:
            flash("No available team identifiers. Registration is closed or please contact the administrator.")
            return redirect(url_for('register'))
        
        # Allocate the first available identifier (you could randomize if desired).
        allocated_id = sorted(unused_ids)[0]
        
        # Create the new team with the allocated team identifier.
        new_team = Team(
            team_name=team_name,
            assigned_team_id=allocated_id,
            leader_phone=leader_phone,
            security_question=security_question,
            security_answer=security_answer,
            is_admin=False,  # Ensure this team is not an admin
            current_step=0   # Starting progress is 0
        )
        new_team.set_password(password)
        db.session.add(new_team)
        db.session.commit()
        
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    # This secret should ideally be stored in an environment variable or secure config
    ADMIN_SECRET_CODE = "MySecretAdminCode123"  
    
    if request.method == 'POST':
        team_name = request.form.get('team_name')
        password = request.form.get('password')
        admin_secret = request.form.get('admin_secret')
        
        if admin_secret != ADMIN_SECRET_CODE:
            flash("Invalid admin secret code.")
            return redirect(url_for('admin_register'))
        
        # Ensure no duplicate team name
        if Team.query.filter_by(team_name=team_name).first():
            flash("Team name already exists. Please choose a different name.")
            return redirect(url_for('admin_register'))
        
        # Create the admin account
        admin = Team(team_name=team_name, is_admin=True)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        
        flash("Admin registered successfully. Please log in.")
        return redirect(url_for('login'))
    
    return render_template('admin_register.html')



# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        team_name = request.form.get('team_name')
        password = request.form.get('password')
        team = Team.query.filter_by(team_name=team_name).first()
        if team and team.check_password(password):
            login_user(team)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid team name or password.')
            return redirect(url_for('login'))
    return render_template('login.html')

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.')
    return redirect(url_for('login'))

# Dashboard – shows current progress and next riddle
@app.route('/dashboard')
@login_required
def dashboard():
    # Prevent admin accounts from playing the game
    if current_user.is_admin:
        flash("Admin accounts do not participate in the game.")
        return redirect(url_for('scoreboard'))
    
    current_step = current_user.current_step
    # Retrieve the next riddle using the dynamic team identifier.
    next_path = TeamPath.query.filter_by(team_identifier=current_user.assigned_team_id, sequence_number=current_step+1).first()
    return render_template('dashboard.html', current_step=current_step, next_path=next_path)


# Scan endpoint – validate QR code submission
@app.route('/scan', methods=['POST'])
@login_required
def scan():
    scanned_code_raw = request.form.get('qr_code')
    # Normalize the scanned code (strip whitespace and convert to uppercase)
    scanned_code = scanned_code_raw.strip().upper() if scanned_code_raw else ""
    
    current_step = current_user.current_step
    expected_path = TeamPath.query.filter_by(
        team_identifier=current_user.assigned_team_id, 
        sequence_number=current_step+1
    ).first()

    if expected_path:
        # Normalize the expected code too
        expected_code = expected_path.location_code.strip().upper() if expected_path.location_code else ""
        if expected_code == scanned_code:
            # Correct scan: update progress
            current_user.current_step += 1
            db.session.commit()

            # Log the correct scan event
            log = ScanLog(
                team_id=current_user.id,
                sequence_number=current_user.current_step,
                qr_code=scanned_code
            )
            db.session.add(log)
            db.session.commit()

            flash('Correct scan! Here is your next clue.')
        else:
            flash('Incorrect QR code scanned. Please try again.')
    else:
        flash("No further clue found. You may have completed all challenges!")
    
    return redirect(url_for('dashboard'))


# Admin route to load CSV data into TeamPath table.
# CSV file format: team_name,sequence_number,location_code,riddle
import csv
import os

@app.route('/admin/load_csv')
@login_required
def load_csv():
    # Ensure only admin users can load CSV data
    if not current_user.is_admin:
        flash("Access Denied: Admin privileges required.")
        return redirect(url_for('dashboard'))

    csv_file = 'team_paths.csv'  # Place your CSV file in your project directory.
    if not os.path.exists(csv_file):
        return "CSV file not found.", 404

    # Optional: Clear any existing TeamPath data to avoid duplicates.
    db.session.query(TeamPath).delete()
    db.session.commit()

    count = 0
    with open(csv_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # The CSV must have the following columns: team_identifier, sequence_number, location_code, riddle
        for row in reader:
            new_path = TeamPath(
                team_identifier=row['team_identifier'],
                sequence_number=int(row['sequence_number']),
                location_code=row['location_code'],
                riddle=row['riddle']
            )
            db.session.add(new_path)
            count += 1
        db.session.commit()
    return f"Loaded {count} entries from CSV.", 200



@app.route('/admin/scoreboard')
@login_required
def scoreboard():
    # Only allow admin users to access this page.
    if not current_user.is_admin:
        flash("Access Denied: Admin privileges required.")
        return redirect(url_for('dashboard'))
    
    # Get all distinct team identifiers from the TeamPath table.
    distinct_ids = [row[0] for row in db.session.query(TeamPath.team_identifier).distinct().all()]
    
    scoreboard_data = []
    for tid in distinct_ids:
        # Find a non-admin team that has been allocated this team identifier.
        team = Team.query.filter_by(assigned_team_id=tid, is_admin=False).first()
        if team:
            # Retrieve the most recent scan for this team.
            last_log = ScanLog.query.filter_by(team_id=team.id).order_by(ScanLog.scanned_at.desc()).first()
            last_scan = last_log.scanned_at if last_log else None
            scoreboard_data.append({
                'team_identifier': tid,
                'team_name': team.team_name,
                'score': team.current_step,
                'last_scan': last_scan,
                'team_db_id': team.id  # Include the team record ID for deletion
            })
        else:
            scoreboard_data.append({
                'team_identifier': tid,
                'team_name': 'Not Allocated',
                'score': 0,
                'last_scan': None
            })
    
    # Sorting logic:
    # 1. Allocated teams (team_name != "Not Allocated") come first.
    # 2. Among allocated teams, teams with higher scores come first.
    # 3. If scores are equal, the team that completed its last scan earlier comes first.
    scoreboard_data.sort(key=lambda row: (
        row.get('team_name', 'Not Allocated') == "Not Allocated",
        -row.get('score', 0),
        row.get('last_scan') if row.get('last_scan') is not None else datetime.max
    ))
    
    return render_template('admin_scoreboard.html', scoreboard_data=scoreboard_data)


@app.route('/admin/delete_team/<int:team_id>', methods=['POST'])
@login_required
def delete_team(team_id):
    if not current_user.is_admin:
        flash("Access Denied: Admin privileges required.")
        return redirect(url_for('dashboard'))
    
    team = Team.query.get(team_id)
    if team and not team.is_admin:
        # Manually delete all associated scan logs
        for log in team.logs:
            db.session.delete(log)
        # Then delete the team
        db.session.delete(team)
        db.session.commit()
        flash("Team and its scan logs have been deleted.")
    else:
        flash("Team not found or cannot delete an admin team.")
    return redirect(url_for('scoreboard'))




@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        team_name = request.form.get('team_name')
        team = Team.query.filter_by(team_name=team_name).first()
        if team:
            # Check if the team has set a security question
            if team.security_question:
                # Store the team id in session to use in the next step
                session['reset_team_id'] = team.id
                return redirect(url_for('security_question'))
            else:
                flash("No security question found. Please contact the game operator.")
        else:
            flash("Team not found.")
    return render_template('forgot_password.html')

@app.route('/security-question', methods=['GET', 'POST'])
def security_question():
    team_id = session.get('reset_team_id')
    if not team_id:
        flash("Session expired. Please try again.")
        return redirect(url_for('forgot_password'))
    
    team = Team.query.get(team_id)
    if request.method == 'POST':
        answer = request.form.get('security_answer')
        # Check the answer (for security, consider case-insensitive comparison)
        if answer.strip().lower() == team.security_answer.strip().lower():
            return redirect(url_for('reset_password'))
        else:
            flash("Incorrect answer. Please try again.")
    return render_template('security_question.html', question=team.security_question)


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    team_id = session.get('reset_team_id')
    if not team_id:
        flash("Session expired. Please try again.")
        return redirect(url_for('forgot_password'))
    
    team = Team.query.get(team_id)
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        team.set_password(new_password)
        db.session.commit()
        session.pop('reset_team_id', None)
        flash("Password reset successful. Please log in.")
        return redirect(url_for('login'))
    return render_template('reset_password.html')




@app.route('/camera-test')
def camera_test():
    return render_template('camera-test.html')

if __name__ == '__main__':
    with app.app_context():
        create_tables()
    app.run(debug=True, host='0.0.0.0')


