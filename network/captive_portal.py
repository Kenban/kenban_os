import logging
import subprocess

import netman

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

logger = logging.getLogger("wifi_manager")

@app.route('/gen_204')
@app.route('/generate_204')
@app.route('/hotspot-detect.html')
@app.route('/ncsi.txt')
@app.route('/connecttest.txt')
def redirect_gen_204():
    return redirect(url_for("connect"), code=302)



@app.route('/connect')
def connect():
    available_networks = netman.get_available_networks()
    # Build a form with the SSID and password fields

    return render_template('portal.html', networks=available_networks)


@app.route('/submit', methods=['POST'])
def submit():
    ssid = request.form['ssid']
    password = request.form['password']

    # TODO: Use the credentials to connect to the provided WiFi.
    # For now, let's just print them:
    logger.info("SSID:", ssid, "Password:", password)

    flash('WiFi credentials received! Trying to connect...', 'info')

    return jsonify({'status': 'success'})

if __name__ == '__main__':
    # flask_app = subprocess.Popen(["gunicorn", "-w", "1", "captive_portal:app", "--bind", "0.0.0.0:8080", "--log-level", "debug"])
    app.run(host='0.0.0.0', port=8080)
