import requests

url = "http://127.0.0.1:8000/pdf/add-image"
with open(r"C:\Users\nomin\Downloads\Presentacion digital fisica 4.pdf", "rb") as f:
    with open(r"C:\Users\nomin\Downloads\cat1.jpg", "rb") as img:
        response = requests.post(url,
            files={"file": f, "image": img},
            data={"page_num": 0, "x": 100, "y": 100, "width": 200, "height": 150}
        )
        print("Status:", response.status_code)
        if response.status_code == 200:
            with open("con_imagen.pdf", "wb") as out:
                out.write(response.content)
            print("PDF guardado!")
        else:
            print("Error:", response.json())