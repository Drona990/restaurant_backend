from rest_framework.response import Response

def success_response(message, data=None, status_code=200):
    return Response(
        {
            "success": True,
            "status": status_code,
            "message": message,
            "data": data
        },
        status=status_code
    )

def error_response(message, errors=None, status_code=400):
    payload = {
        "success": False,
        "status": status_code,
        "message": message,
    }
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=status_code)
