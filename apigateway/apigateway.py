import json
import sys
import traceback

from exceptions import ApplicationException
from flask import Response, jsonify
from flask_lambda import FlaskLambda
from serialisable import json_serialise

from aws_xray_sdk.core import patch_all
patch_all()


class ApiResponse(Response):
    @classmethod
    def force_type(cls, rv, environ=None):
        if isinstance(rv, dict):
            # Round-trip through our JSON serialiser to make it parseable by AWS's
            rv = json.loads(json.dumps(rv, sort_keys=True, default=json_serialise))
            rv = jsonify(rv)
        return super().force_type(rv, environ)


app = FlaskLambda(__name__)
app.response_class = ApiResponse

from routes.accessory import app as accessory_routes
from routes.sensor import app as sensor_routes
from routes.firmware import app as firmware_routes
from routes.misc import app as misc_routes
app.register_blueprint(accessory_routes, url_prefix='/v1/accessory')
app.register_blueprint(accessory_routes, url_prefix='/hardware/accessory')
app.register_blueprint(sensor_routes, url_prefix='/v1/sensor')
app.register_blueprint(sensor_routes, url_prefix='/hardware/sensor')
app.register_blueprint(firmware_routes, url_prefix='/v1/firmware')
app.register_blueprint(firmware_routes, url_prefix='/hardware/firmware')
app.register_blueprint(misc_routes, url_prefix='/v1/misc')
app.register_blueprint(misc_routes, url_prefix='/hardware/misc')


@app.errorhandler(500)
def handle_server_error(e):
    tb = sys.exc_info()[2]
    return {'message': str(e.with_traceback(tb))}, 500, {'Status': type(e).__name__}


@app.errorhandler(404)
def handle_unrecognised_endpoint(_):
    return {"message": "You must specify an endpoint"}, 404, {'Status': 'UnrecognisedEndpoint'}


@app.errorhandler(ApplicationException)
def handle_application_exception(e):
    traceback.print_exception(*sys.exc_info())
    return {'message': e.message}, e.status_code, {'Status': e.status_code_text}


def handler(event, context):
    print(json.dumps(event))
    ret = app(event, context)

    # Unserialise JSON output so AWS can immediately serialise it again...
    ret['body'] = ret['body'].decode('utf-8')

    if ret['headers']['Content-Type'] == 'application/octet-stream':
        ret['isBase64Encoded'] = True

    print(json.dumps(ret))
    return ret


if __name__ == '__main__':
    app.run(debug=True)
