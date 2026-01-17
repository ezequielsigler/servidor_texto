from flask import Flask, request, render_template_string, jsonify
from datetime import datetime

app = Flask(__name__)

ARCHIVO = "mensajes.txt"
SEPARADOR = "---FIN-MENSAJE---"

def cargar_mensajes():
    try:
        with open(ARCHIVO, "r", encoding="utf-8") as f:
            contenido = f.read()
            # Limpiamos espacios y evitamos líneas vacías
            return [m.strip() for m in contenido.split(SEPARADOR) if m.strip()]
    except FileNotFoundError:
        return []

def guardar_mensaje(mensaje):
    # Agregamos hora local para mejor contexto
    hora = datetime.now().strftime("%H:%M:%S")
    formato_mensaje = f"[{hora}] {mensaje.strip()}"
    with open(ARCHIVO, "a", encoding="utf-8") as f:
        f.write(formato_mensaje + "\n" + SEPARADOR + "\n")

def reiniciar_chat():
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        f.write("")

HTML = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Chat de Procesos</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 30px; background-color: #f4f7f6; }
        .container { max-width: 700px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        #historial {
            border: 1px solid #ddd;
            padding: 15px;
            height: 450px;
            overflow-y: auto;
            white-space: pre-wrap;
            background-color: #fff;
            border-radius: 4px;
            margin-top: 20px;
        }
        .msg-item {
            padding: 8px 0;
            border-bottom: 1px solid #f0f0f0;
            font-size: 14px;
            color: #333;
        }
        textarea { 
            width: 100%; 
            padding: 10px; 
            border: 1px solid #ccc; 
            border-radius: 4px; 
            resize: vertical;
            box-sizing: border-box;
        }
        .buttons { margin-top: 10px; display: flex; gap: 10px; }
        button { padding: 8px 15px; cursor: pointer; border-radius: 4px; border: none; background: #007bff; color: white; }
        button.reset { background: #dc3545; }
        button:hover { opacity: 0.9; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Control de Chat / Logs</h2>
        
        <form id="chatForm">
            <textarea id="mensajeInput" name="mensaje" rows="3" autofocus placeholder="Escribe un mensaje y presiona Enter..."></textarea>
            <div class="buttons">
                <button type="submit">Enviar</button>
                <button type="button" class="reset" onclick="reiniciarChat()">Reiniciar</button>
            </div>
        </form>

        <div id="historial">
            </div>
    </div>

    <script>
        let ultimoContenido = "";

        async function actualizarMensajes(forzarScroll = false) {
            try {
                const response = await fetch('/mensajes');
                const mensajes = await response.json();
                const contenedor = document.getElementById('historial');
                
                const nuevoContenido = mensajes.map(msg => `<div class="msg-item">${msg}</div>`).join('');
                
                // Solo actualizamos el DOM si hay cambios para evitar parpadeos
                if (nuevoContenido !== ultimoContenido) {
                    
                    // Problema 2: Lógica de Scroll Inteligente
                    const estaAlFinal = contenedor.scrollHeight - contenedor.scrollTop <= contenedor.clientHeight + 50;
                    
                    contenedor.innerHTML = nuevoContenido;
                    ultimoContenido = nuevoContenido;

                    // Solo scrollea si el usuario ya estaba abajo o si acaba de enviar un mensaje
                    if (estaAlFinal || forzarScroll) {
                        contenedor.scrollTop = contenedor.scrollHeight;
                    }
                }
            } catch (e) { console.error("Error:", e); }
        }

        // Enviar con Enter (sin Shift)
        document.getElementById('mensajeInput').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                document.getElementById('chatForm').requestSubmit();
            }
        });

        document.getElementById('chatForm').onsubmit = async (e) => {
            e.preventDefault();
            const input = document.getElementById('mensajeInput');
            const msj = input.value.trim();
            if (!msj) return;

            const formData = new FormData();
            formData.append('accion', 'enviar');
            formData.append('mensaje', msj);

            input.value = ''; 
            await fetch('/', { method: 'POST', body: formData });
            // Forzamos el scroll porque el usuario actual es el que envía
            actualizarMensajes(true); 
        };

        async function reiniciarChat() {
            if(!confirm("¿Limpiar historial?")) return;
            const formData = new FormData();
            formData.append('accion', 'reiniciar');
            await fetch('/', { method: 'POST', body: formData });
            actualizarMensajes();
        }

        setInterval(() => actualizarMensajes(false), 2000);
        actualizarMensajes(true);
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        accion = request.form.get("accion")
        if accion == "enviar":
            mensaje = request.form.get("mensaje", "").strip()
            if mensaje: guardar_mensaje(mensaje)
        elif accion == "reiniciar":
            reiniciar_chat()
        return "OK", 200
    return render_template_string(HTML)

@app.route("/mensajes")
def obtener_mensajes():
    return jsonify(cargar_mensajes())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
