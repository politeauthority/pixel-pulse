"""
    App Entry Point.
    Web application entry point.

"""
import logging
from logging.config import dictConfig
import os

from flask import Flask, request, jsonify
from polite_lib.utils import dict_tools


from modules import glow


CONFIG = glow.load_config()

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'DEBUG',
        'handlers': ['wsgi']
    }
})

MATRIX_ROOM_MEDIA = os.environ.get("MATRIX_ROOM_MEDIA")
MQTT_TOPIC = os.environ.get("MQTT_TOPIC")

logger = logging.getLogger(__name__)
logger.propagate = True

logging.info("Setup to send messages to MQTT Topic: %s" % MQTT_TOPIC)
app = Flask(__name__)



@app.before_request
def before_request():
    """Before we route the request log some info about the request"""
    logging.info(
        "[Start Request] path: %s | method: %s" % (
            request.path,
            request.method))
    return


@app.errorhandler(404)
def page_not_found(e: str):
    """404 Error page."""
    data = {
        "status": "Error",
        "message": "Forbidden"
    }
    return jsonify(data), 403


@app.route('/', methods=["GET"])
@auth.auth_request
def index() -> str:
    """Api Index"""
    data = {"status": "Success"}
    return jsonify(data)


@app.route('/healthz', methods=["GET"])
def healthz() -> str:
    """Helath check"""
    data = {"status": "Success"}
    return jsonify(data)



if __name__ == '__main__':
    port = 80
    app.secret_key = 'super secret key'
    app.config['SESSION_TYPE'] = 'filesystem'
    app.run(host="0.0.0.0", port=port, debug=True)


# End File: politeauthority/pixel-pulse/src/api/app.py
