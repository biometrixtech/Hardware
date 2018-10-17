from fathomapi.api.handler import handler as fathom_handler
from fathomapi.api.flask_app import app

from routes.accessory import app as accessory_routes
from routes.sensor import app as sensor_routes
from routes.firmware import app as firmware_routes
from routes.misc import app as misc_routes
app.register_blueprint(accessory_routes, url_prefix='/accessory')
app.register_blueprint(sensor_routes, url_prefix='/sensor')
app.register_blueprint(firmware_routes, url_prefix='/firmware')
app.register_blueprint(misc_routes, url_prefix='/misc')


def handler(event, context):
    return fathom_handler(event, context)


if __name__ == '__main__':
    app.run(debug=True)
