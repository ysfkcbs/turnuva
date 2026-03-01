import os
from app import create_app
from models import db, Branch, StudentProfile, User

def upsert_branch(name: str, rules_json: str = "{}"):
    b = Branch.query.filter_by(name=name).first()
    if not b:
        b = Branch(name=name, rules_json=rules_json, is_active=True)
        db.session.add(b)

def upsert_profile(name: str, school_type: str):
    p = StudentProfile.query.filter_by(name=name, school_type=school_type).first()
    if not p:
        p = StudentProfile(name=name, school_type=school_type, is_active=True)
        db.session.add(p)

def upsert_admin(username: str, password: str):
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, role="admin", is_active=True)
        u.set_password(password)
        db.session.add(u)

def main():
    app = create_app()
    with app.app_context():
        # Branch örnekleri (senin gerçek branch listeni buraya koyarız)
        upsert_branch("Futbol")
        upsert_branch("Basketbol")
        upsert_branch("Voleybol")

        # StudentProfile örnekleri (senin gerçek profil listeni buraya koyarız)
        upsert_profile("Standart", "İlkokul")
        upsert_profile("Standart", "Ortaokul")
        upsert_profile("Standart", "Lise")

        # Admin kullanıcı (env’den alalım)
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        upsert_admin(admin_user, admin_pass)

        db.session.commit()
        print("[seed] OK")

if __name__ == "__main__":
    main()