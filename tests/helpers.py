import importlib
import sys
import types


def install_import_stubs():
    if "flask" not in sys.modules:
        flask_stub = types.ModuleType("flask")

        class Flask:
            def __init__(self, name):
                self.name = name
                self.view_functions = {}

            def route(self, *_args, **_kwargs):
                def decorator(func):
                    endpoint = _kwargs.get("endpoint", func.__name__)
                    self.view_functions[endpoint] = func
                    return func

                return decorator

            def before_request(self, func):
                return func

        def jsonify(value):
            return value

        def render_template(_name, *_args, **_kwargs):
            return '<a href="/apidocs">/apidocs</a>'

        def url_for(*_args, **_kwargs):
            return ""

        class _Request:
            pass

        flask_stub.Flask = Flask
        flask_stub.jsonify = jsonify
        flask_stub.render_template = render_template
        flask_stub.url_for = url_for
        flask_stub.request = _Request()
        sys.modules["flask"] = flask_stub

    if "flask_restplus" not in sys.modules:
        frp_stub = types.ModuleType("flask_restplus")

        class _Field:
            def __init__(self, *_args, **_kwargs):
                pass

        class _FieldsModule:
            String = _Field
            Float = _Field
            Nested = _Field

        class Resource:
            pass

        class Api:
            def __init__(self, app, **_kwargs):
                self.app = app
                self.__schema__ = {
                    "info": {"title": "Ethiopian Bank Exchange Rates API"},
                    "paths": {
                        "/cbe-exchange-rates": {},
                    },
                }

            class _Parser:
                def add_argument(self, *_args, **_kwargs):
                    return None

            def route(self, *_args, **_kwargs):
                def decorator(cls):
                    return cls

                return decorator

            def parser(self):
                return self._Parser()

            def model(self, _name, model):
                return model

            def expect(self, *_args, **_kwargs):
                def decorator(func):
                    return func

                return decorator

            def response(self, *_args, **_kwargs):
                def decorator(func):
                    return func

                return decorator

            def doc(self, *_args, **_kwargs):
                def decorator(func):
                    return func

                return decorator

        frp_stub.Api = Api
        frp_stub.Resource = Resource
        frp_stub.fields = _FieldsModule()
        sys.modules["flask_restplus"] = frp_stub

    if "bs4" not in sys.modules:
        bs4_stub = types.ModuleType("bs4")

        class BeautifulSoup:
            def __init__(self, *_args, **_kwargs):
                pass

        bs4_stub.BeautifulSoup = BeautifulSoup
        sys.modules["bs4"] = bs4_stub


def import_modules():
    install_import_stubs()

    loaded = {}
    for module_name in [
        "banks.awash",
        "banks.nib",
        "banks.hibret",
        "banks.wegagen",
        "banks.dashen",
        "app",
    ]:
        sys.modules.pop(module_name, None)
        loaded[module_name] = importlib.import_module(module_name)

    return loaded
