from flask import Blueprint
from datetime import datetime
import uuid
from fathomapi.api.config import Config

app = Blueprint('misc', __name__)


@app.route('/uuid', methods=['GET'])
def handle_misc_uuid():
    return {'uuids': [str(uuid.uuid4()) for _ in range(32)]}


@app.route('/time', methods=['GET'])
def handle_misc_time():
    current_date_time = datetime.utcfromtimestamp(Config.get('REQUEST_TIME') / 1000).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {'current_date': current_date_time}
