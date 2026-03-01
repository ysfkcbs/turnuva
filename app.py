
import os, random, json

from io import BytesIO
from datetime import datetime, timedelta

from functools import wraps
from flask import session, flash, redirect, url_for

from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, send_file
)
from sqlalchemy import text

from models import (
    db, School, Branch, Tournament, Venue,
    Athlete, TournamentEntry, User, StudentProfile
)

from sqlalchemy import inspect
from flask_migrate import Migrate
from flask import redirect, url_for

migrate = Migrate()

def login_required(fn):
        from functools import wraps
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("logged_in"):
                flash("Lütfen giriş yapın.", "warning")
                return redirect(url_for("login"))
            return fn(*args, **kwargs)
        return wrapper

def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Lütfen giriş yapın.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Bu sayfaya erişim yetkiniz yok.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper

# ======================================================
# helpers / migrations (module level)
# ======================================================
def ensure_tournaments_schema():
    cols = {
        row[1] for row in db.session.execute(
            text("PRAGMA table_info(tournaments)")
        ).fetchall()
    }

    if "is_active" not in cols:
        db.session.execute(text(
            "ALTER TABLE tournaments ADD COLUMN is_active INTEGER DEFAULT 1"
        ))
        db.session.execute(text(
            "UPDATE tournaments SET is_active = 1 WHERE is_active IS NULL"
        ))

    if "created_at" not in cols:
        db.session.execute(text(
            "ALTER TABLE tournaments ADD COLUMN created_at DATETIME"
        ))
        db.session.execute(text(
            "UPDATE tournaments SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
        ))

    if "branch_id" not in cols:
        db.session.execute(text(
            "ALTER TABLE tournaments ADD COLUMN branch_id INTEGER"
        ))

    if "start_date" not in cols:
        db.session.execute(text(
            "ALTER TABLE tournaments ADD COLUMN start_date DATE"
        ))

    # ✅ NEW: profile_id
    if "profile_id" not in cols:
        db.session.execute(text(
            "ALTER TABLE tournaments ADD COLUMN profile_id INTEGER"
        ))

    db.session.commit()


def migrate_existing_payloads():
    """
    Eski turnuvalarda payload farklarını normalize eder.
    """
    changed = 0
    for t in Tournament.query.all():
        try:
            old = json.loads(t.data_json or "{}")
        except Exception:
            old = {}

        if not isinstance(old, dict):
            continue

        if "okullar" in old and "teams" not in old:
            old["teams"] = old.pop("okullar")
            changed += 1

        # yeni alanlar yoksa ekle
        old.setdefault("mode", t.tournament_type or "lig")
        old.setdefault("branch_id", t.branch_id)
        old.setdefault("branch_rules", {})
        old.setdefault("profile_id", t.profile_id)

        if changed:
            t.data_json = json.dumps(old, ensure_ascii=False)

    if changed:
        db.session.commit()
        print(f"[migrate] {changed} turnuva payload normalize edildi.")


def ensure_admin_seed():
    admin = User.query.filter_by(username="dev.yusuf").first()
    if not admin:
        admin = User(username="dev.yusuf", role="admin", is_active=True)
        admin.set_password("Kocabas.01")
        db.session.add(admin)
        db.session.commit()
        print("[seed] dev.yusuf admin oluşturuldu.")


def ensure_branches_seed():
    defaults = [
        ("Futbol", {
            "participant_type": "team",
            "score_type": "goals",
            "allow_draw": True,
            "win_points": 3, "draw_points": 1, "loss_points": 0
        }),
        ("Basketbol", {
            "participant_type": "team",
            "score_type": "points",
            "allow_draw": False,
            "win_points": 2, "loss_points": 1
        }),
        ("Voleybol", {
            "participant_type": "team",
            "score_type": "sets",
            "allow_draw": False,
            "set_count": 3,
            "set_win_points": 2, "set_loss_points": 1
        }),
    ]

    existing = {b.name for b in Branch.query.all()}
    for name, rules in defaults:
        if name not in existing:
            db.session.add(
                Branch(
                    name=name,
                    rules_json=json.dumps(rules, ensure_ascii=False)
                )
            )
    db.session.commit()

    # eski turnuvalara futbol bağla
    futbol = Branch.query.filter_by(name="Futbol").first()
    if futbol:
        updated = 0
        for t in Tournament.query.filter(Tournament.branch_id.is_(None)):
            t.branch_id = futbol.id
            updated += 1
        if updated:
            db.session.commit()
            print(f"[migrate] {updated} turnuva kaydı branch_id ile güncellendi.")


def ensure_profiles_seed():
    defaults = [
        ("İlkokul", "Minik Erkek A"),
        ("İlkokul", "Minik Kız A"),
        ("İlkokul", "Minik Erkek B"),
        ("İlkokul", "Minik Kız B"),
        ("Ortaokul", "Küçük Erkek"),
        ("Ortaokul", "Küçük Kız"),
        ("Ortaokul", "Yıldız Erkek"),
        ("Ortaokul", "Yıldız Kız"),
        ("Lise", "Genç Erkek"),
        ("Lise", "Genç Kız"),
    ]

    existing = {(p.school_type, p.name) for p in StudentProfile.query.all()}
    for stype, name in defaults:
        if (stype, name) not in existing:
            db.session.add(
                StudentProfile(
                    school_type=stype,
                    name=name,
                    is_active=True
                )
            )
    db.session.commit()


def ensure_student_profiles_table():
    """
    DB'yi silmeden, eksikse student_profiles tablosunu oluşturur.
    """
    rows = db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='student_profiles'")
    ).fetchall()

    if not rows:
        print("[migrate] student_profiles tablosu oluşturuluyor...")
        db.session.execute(text("""
            CREATE TABLE student_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                school_type TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME
            );
        """))
        db.session.commit()
        print("[migrate] student_profiles tablosu oluşturuldu.")


def load_payload(tournament: Tournament):
    try:
        data = json.loads(tournament.data_json)
    except Exception:
        data = {}

    if isinstance(data, dict):
        data.setdefault("mode", tournament.tournament_type or "lig")
        data.setdefault("branch_id", tournament.branch_id)
        data.setdefault("profile_id", tournament.profile_id)

        try:
            if tournament.branch and tournament.branch.rules_json:
                data.setdefault(
                    "branch_rules",
                    json.loads(tournament.branch.rules_json)
                )
        except Exception:
            data.setdefault("branch_rules", {})

    return data


def dump_payload(tournament: Tournament, data: dict):
    tournament.data_json = json.dumps(data, ensure_ascii=False)
    db.session.commit()


# ========================= fixture engines =========================
def generate_round_robin(teams):
    n = len(teams)
    if n < 2:
        return []

    teams = teams[:]
    if n % 2 == 1:
        teams.append(None)
        n += 1

    rounds = []
    for r in range(n - 1):
        pairings = []
        for i in range(n // 2):
            t1 = teams[i]
            t2 = teams[n - 1 - i]
            if t1 is not None and t2 is not None:
                pairings.append((t1, t2))
        rounds.append(pairings)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds


def next_bracket_size(n):
    size = 1
    while size < n:
        size *= 2
    return size


def build_elimination_initial_rounds(teams):
    teams = teams[:]
    n = len(teams)
    bracket_size = next_bracket_size(n)
    byes = bracket_size - n

    random.shuffle(teams)

    first_round = []
    idx = 0

    for _ in range(byes):
        first_round.append((teams[idx], None))
        idx += 1

    while idx < n:
        first_round.append((teams[idx], teams[idx + 1]))
        idx += 2

    rounds = [first_round]
    return rounds, bracket_size


def advance_elimination_rounds(rounds, results):
    current_round_idx = len(rounds) - 1
    current_round = rounds[current_round_idx]
    current_results = results[current_round_idx]

    winners = []
    for match, score in zip(current_round, current_results):
        a, b = match
        if b is None:
            winners.append(a)
        else:
            sa, sb = score
            winners.append(a if sa > sb else b)

    if len(winners) == 1:
        return rounds, results

    next_round = []
    for i in range(0, len(winners), 2):
        next_round.append((winners[i], winners[i + 1]))

    rounds.append(next_round)
    results.append([(0, 0) for _ in next_round])
    return rounds, results


# ========================= tables =========================
def calculate_team_table(teams, results, schedule, branch_rules):
    score_type = branch_rules.get("score_type", "goals")
    allow_draw = branch_rules.get("allow_draw", True)

    win_points = branch_rules.get("win_points", 3)
    draw_points = branch_rules.get("draw_points", 1)
    loss_points = branch_rules.get("loss_points", 0)

    set_win_points = branch_rules.get("set_win_points", win_points)
    set_loss_points = branch_rules.get("set_loss_points", loss_points)

    table = {
        t["id"]: {
            "id": t["id"],
            "name": t["name"],
            "school_id": t.get("school_id"),
            "school_name": t.get("school_name", t["name"]),
            "played": 0,
            "won": 0,
            "draw": 0,
            "lost": 0,
            "gf": 0,
            "ga": 0,
            "gd": 0,
            "points": 0
        }
        for t in teams
    }

    for match, score in zip(schedule, results):
        a = match["home_id"]
        b = match["away_id"]
        sa, sb = score

        ta = table[a]
        tb = table[b]

        ta["played"] += 1
        tb["played"] += 1

        ta["gf"] += sa
        ta["ga"] += sb
        tb["gf"] += sb
        tb["ga"] += sa

        if score_type == "sets":
            if sa > sb:
                ta["won"] += 1
                tb["lost"] += 1
                ta["points"] += set_win_points
                tb["points"] += set_loss_points
            else:
                tb["won"] += 1
                ta["lost"] += 1
                tb["points"] += set_win_points
                ta["points"] += set_loss_points
            continue

        if sa > sb:
            ta["won"] += 1
            tb["lost"] += 1
            ta["points"] += win_points
        elif sa < sb:
            tb["won"] += 1
            ta["lost"] += 1
            tb["points"] += win_points
        else:
            if allow_draw:
                ta["draw"] += 1
                tb["draw"] += 1
                ta["points"] += draw_points
                tb["points"] += draw_points
            else:
                ta["lost"] += 1
                tb["lost"] += 1
                ta["points"] += loss_points
                tb["points"] += loss_points

    for t in table.values():
        t["gd"] = t["gf"] - t["ga"]

    return sorted(
        table.values(),
        key=lambda x: (x["points"], x["gd"], x["gf"]),
        reverse=True
    )


def calculate_school_aggregate(individual_table):
    agg = {}
    for row in individual_table:
        sid = row.get("school_id")
        sname = row.get("school_name", "-")
        if sid not in agg:
            agg[sid] = {
                "school_id": sid, "school_name": sname,
                "points": 0, "played": 0,
                "won": 0, "draw": 0, "lost": 0
            }
        agg[sid]["points"] += row["points"]
        agg[sid]["played"] += row["played"]
        agg[sid]["won"] += row["won"]
        agg[sid]["draw"] += row["draw"]
        agg[sid]["lost"] += row["lost"]

    return sorted(agg.values(), key=lambda x: (x["points"], x["won"]), reverse=True)

# ======================================================
# ROUTE REGISTRATION
# ======================================================
def register_routes(app):

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username","").strip()
            password = request.form.get("password","").strip()

            user = User.query.filter_by(username=username, is_active=True).first()
            if user and user.check_password(password):
                session["logged_in"] = True
                session["user_id"] = user.id
                session["username"] = user.username
                session["role"] = user.role
                flash("Giriş başarılı", "success")
                return redirect(url_for("dashboard"))

            flash("Hatalı kullanıcı adı/şifre", "danger")

        return render_template("login.html")
    
    @app.get("/")
    def home():
        return redirect(url_for("login"))

   

# ======================================================
# APP FACTORY
# ======================================================
def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "super_secret_key")

    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    instance_path = os.path.join(BASE_DIR, "instance")
    os.makedirs(instance_path, exist_ok=True)

    db_path = os.path.join(instance_path, "kartal_okul.db")
    sqlite_uri = "sqlite:///" + db_path

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", sqlite_uri)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db_uri = os.getenv("DATABASE_URL", sqlite_uri)
    if db_uri.startswith("postgres://"):
        db_uri = db_uri.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri

    db.init_app(app)

    def run_prod_bootstrap():
    # Sadece Render/Prod’da çalışsın
        if not os.getenv("DATABASE_URL"):
            return
        if os.getenv("RUN_BOOTSTRAP", "1") != "1":
            return

        try:
            from flask_migrate import upgrade
            upgrade()
            print("[bootstrap] db upgrade OK")
        except Exception as e:
            print(f"[bootstrap] db upgrade failed: {e}")

        try:
            from seed import run_seed
            run_seed()
            print("[bootstrap] seed OK")
        except Exception as e:
            print(f"[bootstrap] seed failed: {e}")

    # Route'ları burada kaydet
    register_routes(app)

    def run_prod_bootstrap(app):
        """Prod ortamda (Render) migration + seed çalıştırır."""
        # sadece DATABASE_URL varsa (yani Postgres/prod) çalışsın
        if not os.getenv("DATABASE_URL"):
            return
        # Render gibi prod ortamı işaretlemek için istersen RENDER env varını kullanırız
        # ama şimdilik DB varsa prod sayıyoruz.

        try:
            from flask_migrate import upgrade
            upgrade()  # flask db upgrade eşdeğeri
        except Exception as e:
            print(f"[bootstrap] migrate upgrade skipped/failed: {e}")

        try:
            # seed.py bir dosya, içinde main() yoksa import edip fonksiyon çağırmak zor olabilir.
            # En garantisi: seed.py içinde run() fonksiyonu oluşturmak.
            import seed
            if hasattr(seed, "run"):
                seed.run()
            else:
                # seed.py doğrudan çalışacak şekilde yazıldıysa:
                if hasattr(seed, "main"):
                    seed.main()
                else:
                    print("[bootstrap] seed.py: run/main not found, skip")
        except Exception as e:
            print(f"[bootstrap] seed skipped/failed: {e}")

    def run_sqlite_only_tasks():
        """SQLite'a özel tablo/kolon seed/migration işleri.
        Postgres'te PRAGMA/ALTER farklı olduğu için burada skip ediyoruz.
        """
        dialect = db.engine.dialect.name  # 'sqlite' / 'postgresql' / ...
        if dialect != "sqlite":
            return

        ensure_student_profiles_table()
        ensure_tournaments_schema()
        ensure_branches_seed()
        ensure_profiles_seed()
        ensure_admin_seed()
        migrate_existing_payloads()

    
    # SQLite işleri sadece sqlite'da çalışsın
    with app.app_context():
        run_sqlite_only_tasks()
        run_prod_bootstrap(app)
    

    # ✅ return her zaman create_app'in en sonunda olmalı
    
    # ========================= AUTH =========================
 

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Çıkış yapıldı.", "info")
        return redirect(url_for("index"))

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html")

    # ========================= SCHOOLS =========================
    @app.route("/okullar")
    @login_required
    def okullar():
        page = request.args.get("page", 1, type=int)
        pagination = School.query.order_by(School.kurum_ad).paginate(page=page, per_page=25)
        return render_template("okullar.html", schools=pagination.items, pagination=pagination)

    # ========================= ATHLETES =========================
    @app.route("/athletes", methods=["GET","POST"])
    @login_required
    def athletes():
        schools = School.query.order_by(School.kurum_ad).all()
        if request.method == "POST":
            full_name = request.form.get("full_name","").strip()
            school_id = request.form.get("school_id", type=int)
            gender = request.form.get("gender","").strip()
            birth_year = request.form.get("birth_year", type=int)
            license_no = request.form.get("license_no","").strip()

            if not full_name or not school_id:
                flash("Sporcu adı ve okul zorunlu.", "warning")
                return redirect(url_for("athletes"))

            s = School.query.get(school_id)
            if not s:
                flash("Okul bulunamadı.", "danger")
                return redirect(url_for("athletes"))

            a = Athlete(
                full_name=full_name, school_id=school_id,
                gender=gender, birth_year=birth_year, license_no=license_no
            )
            db.session.add(a)
            db.session.commit()
            flash("Sporcu eklendi.", "success")
            return redirect(url_for("athletes"))

        athletes_ = Athlete.query.order_by(Athlete.full_name).all()
        return render_template("athletes.html", athletes=athletes_, schools=schools)

    @app.route("/athletes/delete/<int:athlete_id>", methods=["POST"])
    @login_required
    def athletes_delete(athlete_id):
        a = Athlete.query.get_or_404(athlete_id)
        db.session.delete(a)
        db.session.commit()
        flash("Sporcu silindi.", "info")
        return redirect(url_for("athletes"))

    # ========================= VENUES =========================
    @app.route("/venues", methods=["GET","POST"])
    @login_required
    def venues():
        if request.method == "POST":
            name = request.form.get("name","").strip()
            address = request.form.get("address","").strip()
            if not name:
                flash("Saha adı zorunlu.", "warning")
            else:
                db.session.add(Venue(name=name, address=address))
                db.session.commit()
                flash("Saha eklendi.", "success")
                return redirect(url_for("venues"))
        venues_ = Venue.query.order_by(Venue.name).all()
        return render_template("venues.html", venues=venues_)

    @app.route("/venues/delete/<int:venue_id>", methods=["POST"])
    @login_required
    def venues_delete(venue_id):
        v = Venue.query.get_or_404(venue_id)
        db.session.delete(v)
        db.session.commit()
        flash("Saha silindi.", "info")
        return redirect(url_for("venues"))

    # ========================= TOURNAMENTS =========================
    @app.route("/tournaments")
    @login_required
    def tournaments_list():
        tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
        return render_template("tournaments_list.html", tournaments=tournaments)

    @app.route("/tournaments/new", methods=["GET","POST"])
    @login_required
    def tournaments_new():
        branches = Branch.query.filter_by(is_active=True).order_by(Branch.name).all()
        profiles = StudentProfile.query.filter_by(is_active=True).order_by(
            StudentProfile.school_type, StudentProfile.name
        ).all()

        if request.method == "POST":
            name = request.form.get("name")
            tournament_type = request.form.get("tournament_type")
            start_date_str = request.form.get("start_date")
            branch_id = request.form.get("branch_id")
            profile_id = request.form.get("profile_id")

            if not name or not tournament_type or not branch_id or not profile_id:
                flash("Tüm alanlar zorunlu (Profil dahil).", "warning")
                return redirect(url_for("tournaments_new"))

            try:
                branch_id = int(branch_id)
            except Exception:
                flash("Geçersiz branş seçimi.", "danger")
                return redirect(url_for("tournaments_new"))

            branch = Branch.query.get(branch_id)
            if not branch:
                flash("Seçilen branş bulunamadı.", "danger")
                return redirect(url_for("tournaments_new"))

            try:
                profile_id = int(profile_id)
            except Exception:
                flash("Geçersiz profil seçimi.", "danger")
                return redirect(url_for("tournaments_new"))

            profile = StudentProfile.query.get(profile_id)
            if not profile:
                flash("Seçilen öğrenci profili bulunamadı.", "danger")
                return redirect(url_for("tournaments_new"))

            session["new_tournament"] = {
                "name": name,
                "tournament_type": tournament_type,
                "start_date": start_date_str,
                "branch_id": branch_id,
                "profile_id": profile.id,
                "school_type": profile.school_type  # ✅ otomatik
            }
            return redirect(url_for("tournaments_select"))

        return render_template(
            "tournaments_new.html",
            branches=branches,
            profiles=profiles
        )

    @app.route("/tournaments/select", methods=["GET","POST"])
    @login_required
    def tournaments_select():
        new_t = session.get("new_tournament")
        if not new_t:
            flash("Önce turnuva bilgilerini girin.", "warning")
            return redirect(url_for("tournaments_new"))

        schools = School.query.filter_by(
            okul_turu=new_t["school_type"]
        ).order_by(School.kurum_ad).all()

        if request.method == "POST":
            selected_ids = request.form.getlist("schools") or request.form.getlist("school_ids")
            selected_ids = [sid for sid in selected_ids if sid]
            if len(selected_ids) < 2:
                flash("En az 2 okul seçmelisiniz.", "warning")
                return redirect(url_for("tournaments_select"))

            session["selected_schools"] = selected_ids

            branch = Branch.query.get(new_t.get("branch_id"))
            rules = json.loads(branch.rules_json or "{}") if branch else {}
            if rules.get("participant_type","team") == "individual":
                return redirect(url_for("tournaments_select_athletes"))

            return redirect(url_for("tournaments_create"))

        branch = Branch.query.get(new_t.get("branch_id")) if new_t.get("branch_id") else None
        profile = StudentProfile.query.get(new_t.get("profile_id")) if new_t.get("profile_id") else None

        return render_template(
            "tournaments_select.html",
            schools=schools,
            tournament_type=new_t["tournament_type"],
            school_type=new_t["school_type"],
            start_date=new_t.get("start_date"),
            branch=branch,
            profile=profile
        )

    @app.route("/tournaments/<int:tournament_id>/delete", methods=["POST"])
    @login_required
    def tournaments_delete(tournament_id):
        t = Tournament.query.get_or_404(tournament_id)
        db.session.delete(t)
        db.session.commit()
        flash("Turnuva silindi.", "info")
        return redirect(url_for("tournaments_list"))

    @app.route("/tournaments/select_athletes", methods=["GET","POST"])
    @login_required
    def tournaments_select_athletes():
        new_t = session.get("new_tournament")
        selected_school_ids = session.get("selected_schools", [])
        if not new_t or not selected_school_ids:
            flash("Önce okul seçimi yapın.", "warning")
            return redirect(url_for("tournaments_new"))

        athletes_q = Athlete.query.filter(
            Athlete.school_id.in_(selected_school_ids),
            Athlete.is_active.is_(True)
        )
        athletes_ = athletes_q.order_by(Athlete.full_name).all()

        if request.method == "POST":
            selected_athletes = request.form.getlist("athlete_ids")
            selected_athletes = [a for a in selected_athletes if a]
            if len(selected_athletes) < 2:
                flash("En az 2 sporcu seçmelisiniz.", "warning")
                return redirect(url_for("tournaments_select_athletes"))
            session["selected_athletes"] = selected_athletes
            return redirect(url_for("tournaments_create"))

        schools = School.query.filter(School.id.in_(selected_school_ids)).all()
        return render_template(
            "tournaments_select_athletes.html",
            athletes=athletes_,
            schools=schools,
            new_t=new_t
        )

    @app.route("/tournaments/create", methods=["GET"])
    @login_required
    def tournaments_create():
        new_t = session.get("new_tournament")
        selected_ids = session.get("selected_schools")
        if not new_t or not selected_ids:
            flash("Eksik seçim.", "warning")
            return redirect(url_for("tournaments_new"))

        branch_id = new_t.get("branch_id")
        branch = Branch.query.get(branch_id) if branch_id else None
        if not branch:
            branch = Branch.query.filter_by(name="Futbol").first()
            branch_id = branch.id if branch else None

        # branş kuralları
        try:
            branch_rules = json.loads(branch.rules_json) if branch and branch.rules_json else {}
        except Exception:
            branch_rules = {}

        participant_type = branch_rules.get("participant_type","team")

        start_date_val = None
        if new_t.get("start_date"):
            try:
                start_date_val = datetime.strptime(new_t["start_date"], "%Y-%m-%d").date()
            except Exception:
                start_date_val = None

        data = {
            "mode": new_t["tournament_type"],
            "branch_id": branch_id,
            "branch_rules": branch_rules,
            "profile_id": new_t.get("profile_id")
        }

        if participant_type == "individual":
            athlete_ids = session.get("selected_athletes") or []
            athletes_ = Athlete.query.filter(Athlete.id.in_(athlete_ids)).all()
            participants = []
            for a in athletes_:
                participants.append({
                    "id": a.id,
                    "name": a.full_name,
                    "school_id": a.school_id,
                    "school_name": a.school.kurum_ad if a.school else "-"
                })
            data["participants"] = participants
        else:
            schools = School.query.filter(School.id.in_(selected_ids)).all()
            participants = [{"id": s.id, "name": s.kurum_ad} for s in schools]
            data["teams"] = participants

        if new_t["tournament_type"] == "lig":
            rounds = generate_round_robin(participants)
            schedule = []
            venues_ = Venue.query.all()
            venues_ = venues_ if venues_ else [{"id": None, "name": "Saha"}]

            for r_idx, rnd in enumerate(rounds, start=1):
                for home, away in rnd:
                    schedule.append({
                        "round": r_idx,
                        "home_id": home["id"],
                        "away_id": away["id"],
                        "home_name": home["name"],
                        "away_name": away["name"],
                        "venue": random.choice(venues_).name if venues_ else None,
                        "date": (start_date_val + timedelta(days=7*(r_idx-1))).isoformat()
                               if start_date_val else None
                    })

            results = [(0, 0) for _ in schedule]
            table = calculate_team_table(participants, results, schedule, branch_rules)

            data.update({
                "schedule": schedule,
                "results": results,
                "table": table
            })

            if participant_type == "individual":
                data["school_table"] = calculate_school_aggregate(table)

        else:
            rounds, bracket_size = build_elimination_initial_rounds(participants)
            results = [[(0, 0) for _ in rnd] for rnd in rounds]
            data.update({
                "rounds": rounds,
                "results": results,
                "bracket_size": bracket_size
            })

        t = Tournament(
            name=new_t["name"],
            tournament_type=new_t["tournament_type"],
            school_type=new_t["school_type"],
            branch_id=branch_id,
            profile_id=new_t.get("profile_id"),
            data_json=json.dumps(data, ensure_ascii=False),
            start_date=start_date_val,
            is_active=True
        )
        db.session.add(t)
        db.session.commit()

        if participant_type == "individual":
            for p in data.get("participants", []):
                db.session.add(TournamentEntry(
                    tournament_id=t.id,
                    school_id=p["school_id"],
                    athlete_id=p["id"]
                ))
            db.session.commit()

        session.pop("new_tournament", None)
        session.pop("selected_schools", None)
        session.pop("selected_athletes", None)

        flash("Turnuva oluşturuldu.", "success")
        return redirect(url_for("tournaments_detail", tournament_id=t.id))

    @app.route("/tournaments/<int:tournament_id>")
    @login_required
    def tournaments_detail(tournament_id):
        t = Tournament.query.get_or_404(tournament_id)
        data = load_payload(t)
        return render_template("tournaments_detail.html", t=t, data=data)

    @app.route("/tournaments/<int:tournament_id>/results", methods=["GET","POST"])
    @login_required
    def results_update(tournament_id):
        t = Tournament.query.get_or_404(tournament_id)
        data = load_payload(t)
        rules = data.get("branch_rules", {})
        participant_type = rules.get("participant_type","team")

        if request.method == "POST":
            if data["mode"] == "lig":
                new_results = []
                for i in range(len(data["schedule"])):
                    sa_raw = request.form.get(f"sa_{i}", "0")
                    sb_raw = request.form.get(f"sb_{i}", "0")
                    try:
                        sa = float(sa_raw) if participant_type=="individual" else int(sa_raw)
                        sb = float(sb_raw) if participant_type=="individual" else int(sb_raw)
                    except Exception:
                        sa, sb = 0, 0
                    new_results.append((sa, sb))

                data["results"] = new_results
                base_list = data.get("participants") or data.get("teams") or []
                data["table"] = calculate_team_table(base_list, data["results"], data["schedule"], rules)
                if participant_type == "individual":
                    data["school_table"] = calculate_school_aggregate(data["table"])
                dump_payload(t, data)
                flash("Sonuçlar güncellendi.", "success")

            else:
                ridx = int(request.form.get("round_idx", 0))
                for midx in range(len(data["rounds"][ridx])):
                    sa_raw = request.form.get(f"sa_{ridx}_{midx}", "0")
                    sb_raw = request.form.get(f"sb_{ridx}_{midx}", "0")
                    try:
                        sa = float(sa_raw) if participant_type=="individual" else int(sa_raw)
                        sb = float(sb_raw) if participant_type=="individual" else int(sb_raw)
                    except Exception:
                        sa, sb = 0, 0
                    data["results"][ridx][midx] = (sa, sb)

                rounds, results_ = advance_elimination_rounds(data["rounds"], data["results"])
                data["rounds"] = rounds
                data["results"] = results_
                dump_payload(t, data)
                flash("Eleme sonuçları güncellendi.", "success")

            return redirect(url_for("tournaments_detail", tournament_id=t.id))

        if data["mode"] == "lig":
            return render_template("results_update_league.html", t=t, data=data)
        else:
            return render_template("results_update_elimination.html", t=t, data=data)

    @app.route("/tournaments/<int:tournament_id>/export_excel")
    @login_required
    def export_excel(tournament_id):
        import pandas as pd
        t = Tournament.query.get_or_404(tournament_id)
        data = load_payload(t)

        output = BytesIO()
        writer = pd.ExcelWriter(output, engine="xlsxwriter")

        if data["mode"] == "lig":
            df_schedule = pd.DataFrame(data.get("schedule", []))
            df_results = pd.DataFrame(data.get("results", []), columns=["home_score", "away_score"])
            df_table = pd.DataFrame(data.get("table", []))
            df_schedule.to_excel(writer, sheet_name="Fikstur", index=False)
            df_results.to_excel(writer, sheet_name="Sonuclar", index=False)
            df_table.to_excel(writer, sheet_name="Tablo", index=False)
            if data.get("school_table"):
                pd.DataFrame(data["school_table"]).to_excel(writer, sheet_name="OkulTablo", index=False)
        else:
            df_rounds = pd.DataFrame({
                "round_idx": [i for i in range(len(data.get("rounds", [])))],
                "matches": [str(rnd) for rnd in data.get("rounds", [])]
            })
            df_rounds.to_excel(writer, sheet_name="Eleme", index=False)

        writer.close()
        output.seek(0)
        filename = f"{t.name}_export.xlsx"
        return send_file(output, as_attachment=True, download_name=filename)

    # ========================= ADMIN BRANCHES =========================
    @app.route("/admin/branches")
    @admin_required
    def admin_branches():
        branches = Branch.query.order_by(Branch.name).all()
        return render_template("admin_branches.html", branches=branches)

    @app.route("/admin/branches/new", methods=["GET","POST"])
    @admin_required
    def admin_branches_new():
        if request.method == "POST":
            name = request.form.get("name","").strip()
            rules_json = request.form.get("rules_json","").strip() or "{}"
            is_active = True if request.form.get("is_active") == "on" else False
            if not name:
                flash("Branş adı zorunlu.", "warning")
                return redirect(url_for("admin_branches_new"))
            try:
                parsed = json.loads(rules_json)
                rules_json = json.dumps(parsed, ensure_ascii=False)
            except Exception:
                flash("Kurallar JSON formatında olmalı.", "danger")
                return redirect(url_for("admin_branches_new"))
            if Branch.query.filter_by(name=name).first():
                flash("Bu branş zaten var.", "warning")
                return redirect(url_for("admin_branches_new"))
            db.session.add(Branch(name=name, rules_json=rules_json, is_active=is_active))
            db.session.commit()
            flash("Branş eklendi.", "success")
            return redirect(url_for("admin_branches"))
        return render_template("admin_branch_form.html", branch=None)

    @app.route("/admin/branches/<int:branch_id>/edit", methods=["GET","POST"])
    @admin_required
    def admin_branches_edit(branch_id):
        branch = Branch.query.get_or_404(branch_id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            rules_json = request.form.get("rules_json", "").strip() or "{}"
            is_active = True if request.form.get("is_active") == "on" else False

            if not name:
                flash("Branş adı zorunlu.", "warning")
                return redirect(url_for("admin_branches_edit", branch_id=branch.id))

            try:
                parsed = json.loads(rules_json)
                rules_json = json.dumps(parsed, ensure_ascii=False)
            except Exception:
                flash("Kurallar JSON formatında olmalı.", "danger")
                return redirect(url_for("admin_branches_edit", branch_id=branch.id))

            existing = Branch.query.filter(Branch.name == name, Branch.id != branch.id).first()
            if existing:
                flash("Bu isimde başka branş var.", "warning")
                return redirect(url_for("admin_branches_edit", branch_id=branch.id))

            branch.name = name
            branch.rules_json = rules_json
            branch.is_active = is_active
            db.session.commit()

            flash("Branş güncellendi.", "success")
            return redirect(url_for("admin_branches"))

        return render_template("admin_branch_form.html", branch=branch)

    @app.route("/admin/branches/<int:branch_id>/delete", methods=["POST"])
    @admin_required
    def admin_branches_delete(branch_id):
        branch = Branch.query.get_or_404(branch_id)
        linked = Tournament.query.filter_by(branch_id=branch.id).first()
        if linked:
            flash("Bu branşa bağlı turnuva var. Silinemez, pasif yapabilirsiniz.", "warning")
            return redirect(url_for("admin_branches"))

        db.session.delete(branch)
        db.session.commit()
        flash("Branş silindi.", "info")
        return redirect(url_for("admin_branches"))

    @app.route("/admin/branches/<int:branch_id>/toggle", methods=["POST"])
    @admin_required
    def admin_branches_toggle(branch_id):
        branch = Branch.query.get_or_404(branch_id)
        branch.is_active = not branch.is_active
        db.session.commit()
        flash("Branş durumu değiştirildi.", "info")
        return redirect(url_for("admin_branches"))

    @app.route("/admin/dashboard")
    @admin_required
    def admin_dashboard():
        return render_template("admin_dashboard.html")

    # ========================= ADMIN USERS =========================
    @app.route("/admin/users")
    @admin_required
    def admin_users():
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template("admin_users.html", users=users)

    @app.route("/admin/users/new", methods=["GET","POST"])
    @admin_required
    def admin_users_new():
        if request.method == "POST":
            username = request.form.get("username","").strip()
            password = request.form.get("password","").strip()
            role = request.form.get("role","standard")
            is_active = True if request.form.get("is_active") == "on" else False

            if not username or not password:
                flash("Kullanıcı adı ve şifre zorunlu.", "warning")
                return redirect(url_for("admin_users_new"))

            if User.query.filter_by(username=username).first():
                flash("Bu kullanıcı adı zaten var.", "warning")
                return redirect(url_for("admin_users_new"))

            u = User(username=username, role=role, is_active=is_active)
            u.set_password(password)

            db.session.add(u)
            db.session.commit()
            flash("Kullanıcı eklendi.", "success")
            return redirect(url_for("admin_users"))

        return render_template("admin_user_form.html", user=None)

    @app.route("/admin/users/<int:user_id>/edit", methods=["GET","POST"])
    @admin_required
    def admin_users_edit(user_id):
        user = User.query.get_or_404(user_id)

        if request.method == "POST":
            username = request.form.get("username","").strip()
            password = request.form.get("password","").strip()
            role = request.form.get("role","standard")
            is_active = True if request.form.get("is_active") == "on" else False

            if not username:
                flash("Kullanıcı adı zorunlu.", "warning")
                return redirect(url_for("admin_users_edit", user_id=user.id))

            existing = User.query.filter(User.username == username, User.id != user.id).first()
            if existing:
                flash("Bu kullanıcı adı başka kullanıcıda var.", "warning")
                return redirect(url_for("admin_users_edit", user_id=user.id))

            user.username = username
            user.role = role
            user.is_active = is_active

            if password:
                user.set_password(password)

            db.session.commit()
            flash("Kullanıcı güncellendi.", "success")
            return redirect(url_for("admin_users"))

        return render_template("admin_user_form.html", user=user)

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    @admin_required
    def admin_users_delete(user_id):
        user = User.query.get_or_404(user_id)

        if user.username == "dev.yusuf":
            flash("Ana admin kullanıcı silinemez.", "warning")
            return redirect(url_for("admin_users"))

        db.session.delete(user)
        db.session.commit()
        flash("Kullanıcı silindi.", "info")
        return redirect(url_for("admin_users"))

    with app.app_context():
        run_sqlite_only_tasks()
        run_prod_bootstrap(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
