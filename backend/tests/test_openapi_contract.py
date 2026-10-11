"""Contract smoke test for the deployed FastAPI documentation surface."""

import main


def main_test():
    app = main.app
    assert app.openapi_url == "/openapi.json", app.openapi_url
    assert app.docs_url == "/docs", app.docs_url
    assert app.redoc_url == "/redoc", app.redoc_url

    schema = app.openapi()
    assert schema["info"]["title"] == "KAIZO Core Engine API"
    assert schema["info"]["version"] == "2.0.0"
    assert "/api/v1/health" in schema["paths"]
    assert schema["paths"], "OpenAPI schema must expose registered API paths"
    print("OPENAPI CONTRACT PASS: /openapi.json /docs /redoc")


if __name__ == "__main__":
    main_test()
