import os
from models import db, Branch, StudentProfile, User

def upsert_branch(name: str, rules_json: str = "{}"):
    b = Branch.query.filter_by(name=name).first()
    if not b:
        db.session.add(Branch(name=name, rules_json=rules_json, is_active=True))

def upsert_profile(name: str, school_type: str):
    p = StudentProfile.query.filter_by(name=name, school_type=school_type).first()
    if not p:
        db.session.add(StudentProfile(name=name, school_type=school_type, is_active=True))

def upsert_admin(username: str, password: str):
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, role="admin", is_active=True)
        u.set_password(password)
        db.session.add(u)

def run_seed():
    # Branch’ler
    upsert_branch("Futbol")
    upsert_branch("Basketbol")
    upsert_branch("Voleybol")

    # Profiller
    upsert_profile("Standart", "İlkokul")
    upsert_profile("Standart", "Ortaokul")
    upsert_profile("Standart", "Lise")

    # Admin
    admin_user = os.getenv("ADMIN_USERNAME", "dev.yusuf")
    admin_pass = os.getenv("ADMIN_PASSWORD", "Kocabas.01")
    upsert_admin(admin_user, admin_pass)

    db.session.commit()
    print("[seed] OK")

if __name__ == "__main__":
    # Lokal çalıştırmak istersen:
    from app import create_app
    app = create_app()
    with app.app_context():
        run_seed()