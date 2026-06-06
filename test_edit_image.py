import requests

url = "http://127.0.0.1:8000/pdf/edit-image"
with open(r"C:\Users\nomin\Downloads\QIV _ 3ERA ACTIVIDAD EXTRA _EQUIPO 9.pdf", "rb") as f:
    response = requests.post(url,
        files={"file": f},
        data={
            "page_num": 0,
            "image_index": 0,
            "x": 100,
            "y": 100,
            "width": 300,
            "height": 200,
            "rotation": 0
        }
    )
    print("Status:", response.status_code)
    if response.status_code == 200:
        with open("imagen_editada.pdf", "wb") as out:
            out.write(response.content)
        print("PDF guardado!")
    else:
        print("Error:", response.json())