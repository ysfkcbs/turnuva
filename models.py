
import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class School(db.Model):
    __tablename__ = "schools"
    id = db.Column(db.Integer, primary_key=True)
    il_ad = db.Column(db.String)
    ilce_ad = db.Column(db.String)
    okul_turu = db.Column(db.String)
    kurum_ad = db.Column(db.String)
    adres = db.Column(db.String)
    telefon = db.Column(db.String)
    fax = db.Column(db.String)

    def __repr__(self):
        return f"<School {self.id} - {self.kurum_ad}>"

class Branch(db.Model):
    __tablename__ = "branches"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    rules_json = db.Column(db.Text, nullable=False, default="{}")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Branch {self.id} - {self.name}>"

class StudentProfile(db.Model):
    __tablename__ = "student_profiles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    school_type = db.Column(db.String, nullable=False)  # İlkokul / Ortaokul / Lise
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<StudentProfile {self.id} {self.name} ({self.school_type})>"

class Tournament(db.Model):
    __tablename__ = "tournaments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    tournament_type = db.Column(db.String, nullable=False)
    school_type = db.Column(db.String, nullable=False)

    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)
    branch = db.relationship("Branch")

    profile_id = db.Column(db.Integer, db.ForeignKey("student_profiles.id"), nullable=True)
    profile = db.relationship("StudentProfile")

    data_json = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    start_date = db.Column(db.Date)

    def __repr__(self):
        return f"<Tournament {self.id} - {self.name}>"

class Venue(db.Model):
    __tablename__ = "venues"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    address = db.Column(db.String, nullable=True)

    def __repr__(self):
        return f"<Venue {self.id} - {self.name}>"

class Athlete(db.Model):
    __tablename__ = "athletes"
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    full_name = db.Column(db.String, nullable=False)
    gender = db.Column(db.String)
    birth_year = db.Column(db.Integer)
    license_no = db.Column(db.String)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    school = db.relationship("School")

    def __repr__(self):
        return f"<Athlete {self.id} - {self.full_name}>"

class TournamentEntry(db.Model):
    __tablename__ = "tournament_entries"
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id"), nullable=True)
    seed = db.Column(db.Integer)

    tournament = db.relationship("Tournament")
    school = db.relationship("School")
    athlete = db.relationship("Athlete")

    def __repr__(self):
        return f"<Entry t={self.tournament_id} school={self.school_id} athlete={self.athlete_id}>"

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)
    role = db.Column(db.String, default="standard")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.id} {self.username} ({self.role})>"
