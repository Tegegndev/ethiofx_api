import importlib
import sys
import types


def install_import_stubs():
    if "flask" not in sys.modules:
        flask_stub = types.ModuleType("flask")

        class Flask:
            def __init__(self, name):
                self.name = name

            def route(self, *_args, **_kwargs):
                def decorator(func):
                    return func

                return decorator

        def jsonify(value):
            return value

        flask_stub.Flask = Flask
        flask_stub.jsonify = jsonify
        sys.modules["flask"] = flask_stub

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
