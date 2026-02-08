import requests

def upload_to_imagekit(file):
    url = "https://upload.imagekit.io/api/v1/files/upload"
    headers = {
        "Authorization": "Basic YOUR_IMAGEKIT_AUTH"
    }
    files = {
        'file': file,
        'fileName': file.name
    }
    response = requests.post(url, headers=headers, files=files)
    return response.json()
