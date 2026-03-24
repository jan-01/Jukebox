import os
import logging
import re
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
from functools import wraps
from dotenv import load_dotenv

load_dotenv()  # lädt .env aus dem Repo-Root, falls vorhanden

from flask import Flask, jsonify, redirect, request, render_template, session
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_session import Session  # type: ignore[attr-defined]
import psycopg2
import psycopg2.extras
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import html
from flask_dance.contrib.google import make_google_blueprint, google

# -----------------------------
# APP SETUP
# -----------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(_PROJECT_ROOT, "frontend", "templates"),
    static_folder=os.path.join(_PROJECT_ROOT, "frontend", "static"),
)
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5000").split(",")
CORS(app, resources={
    r"/api/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": True,
    }
})

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# -----------------------------
# Rate Limiter
# -----------------------------
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


# -----------------------------
# Sanitization
# -----------------------------
def sanitize_string(value, max_length=255):
    if not isinstance(value, str):
        return ""
    sanitized = html.escape(value.strip())
    return sanitized[:max_length]

def sanitize_int(value, min_val=None, max_val=None):
    try:
        val = int(value)
        if min_val is not None and val < min_val:
            return min_val
        if max_val is not None and val > max_val:
            return max_val
        return val
    except (ValueError, TypeError):
        return None


# -----------------------------
# SECURITY SETTINGS
# -----------------------------
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-prod")

_is_production = os.environ.get("FLASK_ENV", "development") == "production"

app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_COOKIE_SECURE=_is_production,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

Session(app)
bcrypt = Bcrypt(app)
# -----------------------------
# GOOGLE OAUTH (SSO)
# -----------------------------
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # allows HTTP in local dev

google_bp = make_google_blueprint(
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
    redirect_url="/login/google/callback",
)
app.register_blueprint(google_bp, url_prefix="/login")
# -----------------------------
# DATABASE CONFIG (POSTGRES)
# -----------------------------
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_NAME = os.environ.get("POSTGRES_DB", "jukebox")
DB_USER = os.environ.get("POSTGRES_USER", "jukebox")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "jukebox")
DB_PORT = os.environ.get("DB_PORT", "5432")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Users table with cleaned column
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL DEFAULT 'OAUTH_USER',
        totp_secret TEXT,
        totp_enabled BOOLEAN NOT NULL DEFAULT FALSE
    )
""")
    # Migration: add columns if upgrading an existing database
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret TEXT")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT FALSE")

    # Reviews table
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            userId TEXT NOT NULL,
            appId TEXT NOT NULL,
            title TEXT NOT NULL,
            reviewText TEXT NOT NULL,
            stars INTEGER NOT NULL,
            createdAt TIMESTAMP NOT NULL,
            updatedAt TIMESTAMP
        )
    """)

    conn.commit()
    c.close()
    conn.close()


# Initialize DB at startup
init_db()


# -----------------------------
# SESSION TIMEOUT
# -----------------------------
INACTIVITY_TIMEOUT = 1800  # seconds

@app.before_request
def check_session_timeout():
    if "user" in session:
        last = session.get("last_active")
        if last:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=UTC)
            elapsed = (datetime.now(UTC) - last_dt).total_seconds()
            if elapsed > INACTIVITY_TIMEOUT:
                session.clear()
                return jsonify({"error": "Session expired due to inactivity"}), 401
        session["last_active"] = datetime.now(UTC).isoformat()


# -----------------------------
# SECURITY HEADERS
# -----------------------------
@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    return response


# -----------------------------
# PASSWORD VALIDATION
# -----------------------------
def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Mindestens 8 Zeichen erforderlich"
    if not re.search(r"[A-Z]", password):
        return False, "Mindestens ein Großbuchstabe erforderlich"
    if not re.search(r"[a-z]", password):
        return False, "Mindestens ein Kleinbuchstabe erforderlich"
    if not re.search(r"\d", password):
        return False, "Mindestens eine Ziffer erforderlich"
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", password):
        return False, "Mindestens ein Sonderzeichen erforderlich"
    return True, ""


# -----------------------------
# AUTH DECORATOR
# -----------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
@limiter.limit("5 per minute")
def home():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html")


@app.route("/login")
@limiter.limit("5 per minute")
def login_page():
    return render_template("login.html")


@app.route("/signup")
@limiter.limit("5 per minute")
def signup_page():
    return render_template("signup.html")


# -----------------------------
# AUTH API
# -----------------------------
@app.route("/api/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json(force=True)

    username = sanitize_string(data.get("username"))
    password = data.get("password", "")
    if not isinstance(password, str):
        password = ""

    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user or not bcrypt.check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Ungültige Anmeldedaten"}), 401

    session["user"] = username
    logger.info(f"User '{username}' logged in successfully.")
    return jsonify({"message": "Logged in"}), 200


@app.route("/api/signup", methods=["POST"])
@limiter.limit("3 per minute")
def signup():
    data = request.get_json(force=True)

    username = sanitize_string(data.get("username"))
    password = data.get("password", "")
    if not isinstance(password, str):
        password = ""

    if not username or not password:
        return jsonify({"error": "Benutzername und Passwort erforderlich"}), 400

    if len(username) < 3:
        return jsonify({"error": "Benutzername muss mindestens 3 Zeichen haben"}), 400
    if len(username) > 50:
        return jsonify({"error": "Benutzername darf höchstens 50 Zeichen haben"}), 400

    ok, msg = validate_password(password)
    if not ok:
        return jsonify({"error": msg}), 400

    pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, pw_hash),
        )
        conn.commit()
        cur.close()
        conn.close()
        session["user"] = username
        logger.info(f"User '{username}' registered and logged in.")
        return jsonify({"message": "Konto erstellt"}), 201
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Benutzername bereits vergeben", "exists": True}), 409

@app.route("/login/google/callback")
def google_callback():
    if not google.authorized:
        return redirect("/login")

    try:
        resp = google.get("/oauth2/v2/userinfo")
        if not resp.ok:
            return redirect("/login")

        info = resp.json()
        google_email = info.get("email")

        if not google_email:
            return redirect("/login")

        # Find or auto-create user based on Google email
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (google_email,))
        user = cur.fetchone()

        if not user:
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (google_email, "GOOGLE_OAUTH_NO_PASSWORD")
            )
            conn.commit()
            logger.info(f"New user created via Google SSO: '{google_email}'")

        cur.close()
        conn.close()

        session["user"] = google_email
        session["last_active"] = datetime.now(UTC).isoformat()
        logger.info(f"User '{google_email}' logged in via Google SSO.")
        return redirect("/")

    except Exception:
        logger.exception("Google OAuth callback failed")
        return redirect("/login")
    
@app.route("/logout")
def logout():
    username = session.get("user")
    session.clear()
    if username:
        logger.info(f"User '{username}' logged out.")
    return redirect("/login")


@app.route("/api/me", methods=["GET"])
@login_required
def me():
    return jsonify({"username": session["user"]}), 200


# -----------------------------
# REVIEWS API
# -----------------------------
@app.route('/api/reviews', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
@login_required
def reviews_handler():
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == 'GET':
        user_id = request.args.get('userId')

        if user_id:
            c.execute(
                "SELECT * FROM reviews WHERE userId=%s ORDER BY id DESC",
                (user_id,)
            )
        else:
            c.execute("SELECT * FROM reviews ORDER BY id DESC")

        reviews = []
        for row in c.fetchall():
            reviews.append({
                "id": row["id"],
                "userId": row["userid"],
                "appId": row["appid"],
                "title": row["title"],
                "reviewText": row["reviewtext"],
                "stars": row["stars"],
                "createdAt": row["createdat"],
                "updatedAt": row["updatedat"],
            })

        c.close()
        conn.close()
        return jsonify(reviews)

    elif request.method == 'POST':
        data = request.get_json(force=True)
        created_at = datetime.now().isoformat()

        user_id = session["user"]
        app_id = sanitize_string(data.get('appId', 'default-app-id'))
        title = sanitize_string(data.get('title', ''))
        review_text = sanitize_string(data.get('reviewText', ''))
        stars = sanitize_int(data.get('stars'))

        if not title or not review_text:
            c.close()
            conn.close()
            return jsonify({"error": "Titel und Reviewtext sind erforderlich"}), 400

        if stars is None or not (1 <= stars <= 5):
            c.close()
            conn.close()
            return jsonify({"error": "Sterne müssen zwischen 1 und 5 liegen"}), 400

        c.execute("""
            INSERT INTO reviews (userId, appId, title, reviewText, stars, createdAt)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, app_id, title, review_text, stars, created_at))

        review_id = c.fetchone()["id"]
        conn.commit()
        c.close()
        conn.close()
        logger.info(f"Review created by user '{user_id}' for '{app_id}' with ID '{review_id}'")
        return jsonify({
            "id": review_id,
            "userId": user_id,
            "appId": app_id,
            "title": title,
            "reviewText": review_text,
            "stars": stars,
            "createdAt": created_at,
            "updatedAt": None
        }), 201


@app.route("/api/reviews/<int:review_id>", methods=["PATCH", "DELETE"])
@limiter.limit("10 per minute")
@login_required
def modify_review(review_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM reviews WHERE id=%s", (review_id,))
    review = cur.fetchone()

    if not review:
        cur.close()
        conn.close()
        return jsonify({"error": "Review nicht gefunden"}), 404

    if review['userid'] != session['user']:
        cur.close()
        conn.close()
        return jsonify({"error": "Forbidden"}), 403

    if request.method == "DELETE":
        cur.execute("DELETE FROM reviews WHERE id=%s", (review_id,))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Review {review_id} deleted by user '{session['user']}'.")
        return jsonify({"message": "Gelöscht"}), 200

    data = request.get_json(force=True)

    title = sanitize_string(data['title']) if 'title' in data else review['title']
    review_text = sanitize_string(data['reviewText']) if 'reviewText' in data else review['reviewtext']

    if 'stars' in data:
        stars = sanitize_int(data['stars'])
        if stars is None or not (1 <= stars <= 5):
            cur.close()
            conn.close()
            return jsonify({"error": "Sterne müssen zwischen 1 und 5 liegen"}), 400
    else:
        stars = review['stars']

    cur.execute(
        """UPDATE reviews
           SET title=%s, reviewText=%s, stars=%s, updatedAt=%s
           WHERE id=%s
           RETURNING *""",
        (title, review_text, stars, datetime.now(UTC), review_id),
    )
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Review {review_id} updated by user '{session['user']}'.")
    return jsonify({
        "id": updated["id"],
        "userId": updated["userid"],
        "appId": updated["appid"],
        "title": updated["title"],
        "reviewText": updated["reviewtext"],
        "stars": updated["stars"],
        "createdAt": updated["createdat"],
        "updatedAt": updated["updatedat"],
    }), 200


# -----------------------------
# ERROR HANDLING
# -----------------------------
@app.errorhandler(Exception)
def handle_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    logger.exception("Unhandled exception")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
