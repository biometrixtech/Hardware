from flask import Response, jsonify
from flask_lambda import FlaskLambda
import json
import os
import sys
import traceback


# Break out of Lambda's X-Ray sandbox so we can define our own segments and attach metadata, annotations, etc, to them
lambda_task_root_key = os.getenv('LAMBDA_TASK_ROOT')
del os.environ['LAMBDA_TASK_ROOT']
from aws_xray_sdk.core import patch_all, xray_recorder
from aws_xray_sdk.core.models.trace_header import TraceHeader
patch_all()
os.environ['LAMBDA_TASK_ROOT'] = lambda_task_root_key

from exceptions import ApplicationException
from serialisable import json_serialise


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
app.url_map.strict_slashes = False

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


@app.errorhandler(405)
def handle_unrecognised_method(_):
    return {"message": "The given method is not supported for this endpoint"}, 405, {'Status': 'UnsupportedMethod'}


@app.errorhandler(ApplicationException)
def handle_application_exception(e):
    traceback.print_exception(*sys.exc_info())
    return {'message': e.message}, e.status_code, {'Status': e.status_code_text}


def handler(event, context):
    print(json.dumps(event))

    # Trim trailing slashes from urls
    event['path'] = event['path'].rstrip('/')

    # Trim semantic versioning string from urls, if present
    event['path'] = event['path'].replace('/hardware/latest/', '/hardware/').replace('/hardware/1.0.0/', '/hardware/')

    # Pass tracing info to X-Ray
    if 'X-Amzn-Trace-Id-Safe' in event['headers']:
        xray_trace = TraceHeader.from_header_str(event['headers']['X-Amzn-Trace-Id-Safe'])
        xray_recorder.begin_segment(
            name='hardware.{}.fathomai.com'.format(os.environ['ENVIRONMENT']),
            traceid=xray_trace.root,
            parent_id=xray_trace.parent
        )
    else:
        xray_recorder.begin_segment(name='hardware.{}.fathomai.com'.format(os.environ['ENVIRONMENT']))

    xray_recorder.current_segment().put_http_meta('url', 'https://{}{}'.format(event['headers']['Host'], event['path']))
    xray_recorder.current_segment().put_http_meta('method', event['httpMethod'])
    xray_recorder.current_segment().put_http_meta('user_agent', event['headers']['User-Agent'])
    xray_recorder.current_segment().put_annotation('environment', os.environ['ENVIRONMENT'])

    ret = app(event, context)
    ret['headers'].update({
        'Access-Control-Allow-Methods': 'DELETE,GET,HEAD,OPTIONS,PATCH,POST,PUT',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Origin': '*',
    })

    # Unserialise JSON output so AWS can immediately serialise it again...
    ret['body'] = ret['body'].decode('utf-8')

    if ret['headers']['Content-Type'] == 'application/octet-stream':
        ret['isBase64Encoded'] = True

    # xray_recorder.current_segment().http['response'] = {'status': ret['statusCode']}
    xray_recorder.current_segment().put_http_meta('status', ret['statusCode'])
    xray_recorder.current_segment().apply_status_code(ret['statusCode'])
    xray_recorder.end_segment()

    print(json.dumps(ret))
    return ret


if __name__ == '__main__':
    app.run(debug=True)
