from flask import Response, jsonify
from flask_lambda import FlaskLambda
from werkzeug.routing import BaseConverter
import json
import os
import re
import sys
import traceback


# Break out of Lambda's X-Ray sandbox so we can define our own segments and attach metadata, annotations, etc, to them
lambda_task_root_key = os.getenv('LAMBDA_TASK_ROOT')
del os.environ['LAMBDA_TASK_ROOT']
from aws_xray_sdk.core import patch_all, xray_recorder
from aws_xray_sdk.core.models.trace_header import TraceHeader
patch_all()
os.environ['LAMBDA_TASK_ROOT'] = lambda_task_root_key

from exceptions import ApplicationException, InvalidSchemaException
from serialisable import json_serialise


class ApiResponse(Response):
    @classmethod
    def force_type(cls, rv, environ=None):
        if isinstance(rv, dict):
            # Round-trip through our JSON serialiser to make it parseable by AWS's
            rv = json.loads(json.dumps(rv, sort_keys=True, default=json_serialise))
            rv = jsonify(rv)
        return super().force_type(rv, environ)


class VersionNumberConverter(BaseConverter):
    def to_python(self, value):
        if not re.match('\d+\.\d+(\.\d+)?', value):
            raise InvalidSchemaException('Version number must be in the format NN.NN(.NN)')
        return value

    def to_url(self, value):
        return value


app = FlaskLambda(__name__)
app.response_class = ApiResponse
app.url_map.strict_slashes = False
app.url_map.converters['versionnumber'] = VersionNumberConverter

from routes.accessory import app as accessory_routes
from routes.sensor import app as sensor_routes
from routes.firmware import app as firmware_routes
from routes.misc import app as misc_routes
app.register_blueprint(accessory_routes, url_prefix='/accessory')
app.register_blueprint(sensor_routes, url_prefix='/sensor')
app.register_blueprint(firmware_routes, url_prefix='/firmware')
app.register_blueprint(misc_routes, url_prefix='/misc')


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

    # Strip mount point and version information from the path
    path_match = re.match(f'^/(?P<mount>({os.environ["SERVICE"]}|v1))?(/(?P<version>(\d+([._]\d+([._]\d+(-\w+([._]\d+)?)?)?)?)|latest))?(?P<path>/.+?)/?$', event['path'])
    if path_match is None:
        raise Exception('Invalid path')
    event['path'] = path_match.groupdict()['path']
    api_version = path_match.groupdict()['version']

    # Pass tracing info to X-Ray
    if 'X-Amzn-Trace-Id-Safe' in event['headers']:
        xray_trace = TraceHeader.from_header_str(event['headers']['X-Amzn-Trace-Id-Safe'])
        xray_recorder.begin_segment(
            name='{SERVICE}.{ENVIRONMENT}.fathomai.com'.format(**os.environ),
            traceid=xray_trace.root,
            parent_id=xray_trace.parent
        )
    else:
        xray_recorder.begin_segment(name='{SERVICE}.{ENVIRONMENT}.fathomai.com'.format(**os.environ))

    xray_recorder.current_segment().put_http_meta('url', f"https://{event['headers']['Host']}/{os.environ['SERVICE']}/{api_version}{event['path']}")
    xray_recorder.current_segment().put_http_meta('method', event['httpMethod'])
    xray_recorder.current_segment().put_http_meta('user_agent', event['headers']['User-Agent'])
    xray_recorder.current_segment().put_annotation('environment', os.environ['ENVIRONMENT'])
    xray_recorder.current_segment().put_annotation('version', str(api_version))

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
