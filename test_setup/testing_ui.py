from flask import Flask, render_template, request, jsonify
import redis

# --- Redis setup ---
r = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)

app = Flask(__name__)

# --- Serve main interface ---
@app.route('/')
def index():
    return render_template('index.html')  # HTML interface we'll define next

# --- Set pan, tilt, zoom ---
@app.route('/set_angles', methods=['POST'])
def set_angles():
    data = request.json
    if "pan" in data:
        r.set("pan_command", data["pan"])
    if "tilt" in data:
        r.set("tilt_command", data["tilt"])
    if "velocity" in data:
        r.set("velocity_command", data["velocity"])
    if "zoom" in data:
        r.set("zoom_command", data["zoom"])
    return jsonify({"status": "ok"})

# --- Toggle modes ---
@app.route('/set_mode', methods=['POST'])
def set_mode():
    data = request.json
    manual = data.get("manual", 0)
    auto = data.get("auto", 0)
    r.set("manual_mode", str(manual))
    r.set("auto_mode", str(auto))
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
