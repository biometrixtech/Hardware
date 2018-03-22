from flask import Blueprint
from datetime import datetime
import uuid

app = Blueprint('misc', __name__)


@app.route('/uuid', methods=['GET'])
def handle_misc_uuid():
    return {'uuids': [str(uuid.uuid4()) for _ in range(32)]}


@app.route('/time', methods=['GET'])
def handle_misc_time():
    return {'current_date': datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}
