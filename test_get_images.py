import requests

url = "http://127.0.0.1:8000/pdf/delete-image"
with open(r"C:\Users\nomin\Downloads\Presentacion digital fisica 4.pdf", "rb") as f:
    response = requests.post(url,
        files={"file": f},
        data={"page_num": 0, "image_index": 0}
    )
    print("Status:", response.status_code)
    if response.status_code == 200:
        with open("sin_imagen.pdf", "wb") as out:
            out.write(response.content)
        print("PDF guardado!")
    else:
        print("Error:", response.json())