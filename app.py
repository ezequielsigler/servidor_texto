"""
Servidor de Archivos Seguro
───────────────────────────
Uso:
  1. cp .env.example .env  y configurá las variables
  2. pip install -r requirements.txt
  3. python app.py
"""

import os
from pathlib import Path
from functools import wraps

from flask import (
    Flask, request, redirect, url_for, session,
    send_from_directory, flash, render_template_string, abort, jsonify,
)
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from dotenv import load_dotenv

load_dotenv()

# ── Configuración ─────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY no configurada. Copiá .env.example a .env y completá las variables."
    )

SERVER_USERNAME = os.environ.get("SERVER_USERNAME", "admin")
PASSWORD_HASH   = os.environ.get("PASSWORD_HASH")
if not PASSWORD_HASH:
    raise RuntimeError("PASSWORD_HASH no configurada.")

MAX_CONTENT_MB = int(os.environ.get("MAX_CONTENT_MB", 500))
UPLOAD_FOLDER  = os.environ.get("UPLOAD_FOLDER", "uploads")
HOST           = os.environ.get("HOST", "0.0.0.0")
PORT           = int(os.environ.get("PORT", 5000))

ALLOWED_EXTENSIONS = {
    "pdf", "docx", "xlsx",
    "jpg", "jpeg", "png", "gif", "webp", "heic",
    "mp3", "wav", "flac", "m4a", "ogg",
    "mp4", "mkv", "mov", "avi", "webm",
    "zip", "tar", "gz", "7z",
    "txt", "csv", "odt", "ods",
}

# ── Flask ─────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"]    = MAX_CONTENT_MB * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["WTF_CSRF_TIME_LIMIT"]   = None  # sin expiración en LAN

csrf    = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])

UPLOAD_PATH = Path(UPLOAD_FOLDER).resolve()
UPLOAD_PATH.mkdir(exist_ok=True)

# ── Utilidades ────────────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lstrip(".").lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def safe_dest(filename: str) -> Path:
    """Devuelve Path destino si es seguro, abort(400) si no."""
    filename = secure_filename(filename)
    if not filename:
        abort(400)
    dest = (UPLOAD_PATH / filename).resolve()
    try:
        dest.relative_to(UPLOAD_PATH)
    except ValueError:
        abort(400)
    return dest

# ── Cabeceras de seguridad ────────────────────────────────────────────────────

@app.after_request
def set_security_headers(response):
    h = response.headers
    h["X-Frame-Options"]         = "DENY"
    h["X-Content-Type-Options"]  = "nosniff"
    h["X-XSS-Protection"]        = "1; mode=block"
    h["Referrer-Policy"]         = "strict-origin-when-cross-origin"
    h["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline';"
    )
    return response

# ── Rutas ─────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == SERVER_USERNAME and check_password_hash(PASSWORD_HASH, password):
            session.clear()
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Credenciales inválidas."
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    files = []
    for f in sorted(UPLOAD_PATH.iterdir()):
        if f.is_file():
            files.append({"name": f.name, "size": human_size(f.stat().st_size)})
    return render_template_string(INDEX_HTML, files=files)


@app.route("/upload", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def upload():
    is_xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def fail(msg, code=400):
        if is_xhr:
            return jsonify(ok=False, message=msg), code
        flash(msg, "error")
        return redirect(url_for("index"))

    if "file" not in request.files:
        return fail("No se seleccionó ningún archivo.")

    file = request.files["file"]
    if not file.filename:
        return fail("Nombre de archivo vacío.")

    if not allowed_file(file.filename):
        return fail("Tipo de archivo no permitido.")

    dest = safe_dest(file.filename)
    file.save(dest)

    msg = f"'{dest.name}' subido correctamente."
    if is_xhr:
        return jsonify(ok=True, message=msg)
    flash(msg, "success")
    return redirect(url_for("index"))


@app.route("/download/<filename>")
@login_required
def download(filename):
    dest = safe_dest(filename)
    if not dest.is_file():
        abort(404)
    return send_from_directory(UPLOAD_PATH, dest.name, as_attachment=True)


@app.route("/delete/<filename>", methods=["POST"])
@login_required
def delete(filename):
    dest = safe_dest(filename)
    if not dest.is_file():
        abort(404)
    dest.unlink()
    flash(f"'{dest.name}' eliminado.", "success")
    return redirect(url_for("index"))

# ── Manejadores de error ──────────────────────────────────────────────────────

@app.errorhandler(CSRFError)
def handle_csrf_error(_):
    flash("Token de seguridad inválido. Recargá la página e intentá de nuevo.", "error")
    return redirect(url_for("index")), 400


@app.errorhandler(413)
def too_large(_):
    flash(f"Archivo demasiado grande. Máximo permitido: {MAX_CONTENT_MB} MB.", "error")
    return redirect(url_for("index")), 413

# ── Plantillas HTML ───────────────────────────────────────────────────────────

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Iniciar sesión – Servidor de Archivos</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
      background: #0f1117; color: #e2e8f0;
      font-family: system-ui, -apple-system, sans-serif;
    }
    .card {
      background: #1a1f2e; border: 1px solid #2d3748;
      border-radius: 12px; padding: 2.5rem; width: 100%; max-width: 380px;
    }
    h1 { font-size: 1.4rem; margin-bottom: 1.75rem; color: #a78bfa; }
    label { display: block; margin-bottom: .35rem; font-size: .85rem; color: #94a3b8; }
    input[type=text], input[type=password] {
      width: 100%; padding: .65rem .9rem; margin-bottom: 1.1rem;
      background: #0f1117; border: 1px solid #2d3748; border-radius: 8px;
      color: #e2e8f0; font-size: 1rem; outline: none; transition: border-color .2s;
    }
    input:focus { border-color: #7c3aed; }
    button[type=submit] {
      width: 100%; padding: .7rem; background: #7c3aed; color: #fff;
      border: none; border-radius: 8px; font-size: 1rem; cursor: pointer;
      transition: background .2s;
    }
    button[type=submit]:hover { background: #6d28d9; }
    .error {
      background: #3b1c1c; border: 1px solid #7f1d1d; color: #fca5a5;
      border-radius: 8px; padding: .65rem .9rem; margin-bottom: 1rem;
      font-size: .875rem;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>Servidor de Archivos</h1>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <label for="u">Usuario</label>
      <input id="u" name="username" type="text" autocomplete="username" required autofocus>
      <label for="p">Contraseña</label>
      <input id="p" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Entrar</button>
    </form>
  </div>
</body>
</html>"""


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Servidor de Archivos</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh; background: #0f1117; color: #e2e8f0;
      font-family: system-ui, -apple-system, sans-serif;
    }
    header {
      display: flex; align-items: center; justify-content: space-between;
      padding: .85rem 2rem; background: #1a1f2e; border-bottom: 1px solid #2d3748;
    }
    header h1 { font-size: 1.15rem; color: #a78bfa; }
    .btn-logout {
      background: transparent; color: #94a3b8; border: 1px solid #2d3748;
      padding: .35rem .85rem; border-radius: 8px; cursor: pointer; font-size: .85rem;
      transition: border-color .2s, color .2s;
    }
    .btn-logout:hover { border-color: #7c3aed; color: #a78bfa; }

    main { max-width: 900px; margin: 2rem auto; padding: 0 1.25rem; }

    /* Flash */
    .flash { padding: .65rem 1rem; border-radius: 8px; margin-bottom: .6rem; font-size: .875rem; }
    .flash.success { background: #1a2e1a; border: 1px solid #166534; color: #86efac; }
    .flash.error   { background: #3b1c1c; border: 1px solid #7f1d1d; color: #fca5a5; }

    /* Drop zone */
    .dropzone {
      border: 2px dashed #2d3748; border-radius: 12px;
      padding: 2.5rem 1rem; text-align: center; cursor: pointer;
      transition: border-color .2s, background .2s; margin-bottom: 1rem;
      user-select: none;
    }
    .dropzone.over { border-color: #7c3aed; background: #1e1730; }
    .dropzone p { color: #64748b; font-size: .95rem; }
    .dropzone span { color: #a78bfa; text-decoration: underline; }
    #file-input { display: none; }

    /* Progress */
    .progress-wrap {
      display: none; background: #1e2535; border-radius: 99px;
      overflow: hidden; height: 7px; margin-bottom: .4rem;
    }
    .progress-bar { height: 100%; width: 0; background: #7c3aed; transition: width .1s linear; }
    #progress-label { font-size: .78rem; color: #64748b; min-height: 1.1em; margin-bottom: 1.25rem; text-align: right; }

    /* Table */
    .section-title { font-size: .9rem; color: #64748b; margin-bottom: .6rem; font-weight: 500; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: .6rem .75rem; border-bottom: 1px solid #1e2535; font-size: .875rem; }
    th { color: #64748b; font-weight: 500; }
    tr:hover td { background: #141824; }
    .col-size { color: #94a3b8; white-space: nowrap; }
    .col-actions { white-space: nowrap; }
    .btn-dl, .btn-del {
      padding: .28rem .65rem; border-radius: 6px; border: none;
      font-size: .8rem; cursor: pointer; display: inline-block; text-decoration: none;
    }
    .btn-dl  { background: #1e3a5f; color: #93c5fd; margin-right: .35rem; }
    .btn-dl:hover  { background: #1e4a80; }
    .btn-del { background: #3b1c1c; color: #fca5a5; }
    .btn-del:hover { background: #5c2424; }
    .empty { color: #4a5568; text-align: center; padding: 3rem 0; font-size: .9rem; }
  </style>
</head>
<body>
  <header>
    <h1>Servidor de Archivos</h1>
    <form method="POST" action="{{ url_for('logout') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <button type="submit" class="btn-logout">Cerrar sesión</button>
    </form>
  </header>

  <main>
    {% for cat, msg in get_flashed_messages(with_categories=True) %}
      <div class="flash {{ cat }}">{{ msg }}</div>
    {% endfor %}

    <div class="dropzone" id="dropzone">
      <p>Arrastrá archivos aquí o <span id="browse-link">hacé clic para seleccionar</span></p>
      <input type="file" id="file-input" multiple>
    </div>

    <div class="progress-wrap" id="progress-wrap">
      <div class="progress-bar" id="progress-bar"></div>
    </div>
    <div id="progress-label"></div>

    <p class="section-title">Archivos almacenados ({{ files | length }})</p>

    {% if files %}
    <table>
      <thead>
        <tr><th>Nombre</th><th>Tamaño</th><th>Acciones</th></tr>
      </thead>
      <tbody>
        {% for f in files %}
        <tr>
          <td>{{ f.name }}</td>
          <td class="col-size">{{ f.size }}</td>
          <td class="col-actions">
            <a href="{{ url_for('download', filename=f.name) }}" class="btn-dl">Descargar</a>
            <form method="POST" action="{{ url_for('delete', filename=f.name) }}" style="display:inline">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <button type="submit" class="btn-del"
                data-name="{{ f.name }}"
                onclick="return confirm('Eliminar ' + this.dataset.name + '?')">Eliminar</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty">No hay archivos almacenados todavía.</div>
    {% endif %}
  </main>

  <script>
    var dropzone    = document.getElementById('dropzone');
    var fileInput   = document.getElementById('file-input');
    var browseLink  = document.getElementById('browse-link');
    var progressWrap = document.getElementById('progress-wrap');
    var progressBar = document.getElementById('progress-bar');
    var progressLbl = document.getElementById('progress-label');
    var csrfToken   = '{{ csrf_token() }}';

    browseLink.addEventListener('click', function() { fileInput.click(); });
    dropzone.addEventListener('click', function(e) {
      if (e.target !== browseLink) fileInput.click();
    });

    dropzone.addEventListener('dragover', function(e) {
      e.preventDefault(); dropzone.classList.add('over');
    });
    dropzone.addEventListener('dragleave', function() {
      dropzone.classList.remove('over');
    });
    dropzone.addEventListener('drop', function(e) {
      e.preventDefault(); dropzone.classList.remove('over');
      uploadFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', function() {
      if (fileInput.files.length) uploadFiles(fileInput.files);
    });

    function uploadFiles(files) {
      var index = 0;
      function next() {
        if (index >= files.length) { location.reload(); return; }
        uploadOne(files[index++], next);
      }
      next();
    }

    function uploadOne(file, onDone) {
      var fd = new FormData();
      fd.append('file', file);

      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/upload');
      xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
      xhr.setRequestHeader('X-CSRFToken', csrfToken);

      progressWrap.style.display = 'block';
      progressBar.style.width = '0%';
      progressLbl.textContent = 'Subiendo ' + file.name + '\u2026';

      xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
          var pct = Math.round(e.loaded / e.total * 100);
          progressBar.style.width = pct + '%';
          progressLbl.textContent = file.name + ' \u2014 ' + pct + '%';
        }
      };

      xhr.onload = function() {
        try {
          var resp = JSON.parse(xhr.responseText);
          progressLbl.textContent = resp.message;
        } catch (err) {
          progressLbl.textContent = xhr.status === 200 ? 'Completado.' : 'Error al subir.';
        }
        onDone();
      };

      xhr.onerror = function() {
        progressLbl.textContent = 'Error de red.';
        onDone();
      };

      xhr.send(fd);
    }
  </script>
</body>
</html>"""

# ── Inicio ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)
