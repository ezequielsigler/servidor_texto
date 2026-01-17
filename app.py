from flask import Flask, request, render_template_string

app = Flask(__name__)

texto_guardado = ""  # Aquí guardaremos el texto

HTML = """
<!doctype html>
<title>Servidor de Texto</title>
<h2>Servidor de Texto Compartido</h2>
<form method="POST">
    <textarea name="texto" rows="10" cols="50">{{ texto }}</textarea><br>
    <button type="submit">Guardar</button>
</form>
<h3>Texto guardado:</h3>
<pre>{{ texto }}</pre>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    global texto_guardado
    if request.method == "POST":
        texto_guardado = request.form["texto"]
    return render_template_string(HTML, texto=texto_guardado)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
