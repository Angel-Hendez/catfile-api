import requests

url = "http://127.0.0.1:8000/pdf/add-signature"
with open(r"C:\Users\nomin\Downloads\Presentacion digital fisica 4.pdf", "rb") as f:
    with open(r"C:\Users\nomin\Downloads\cat4.jpg", "rb") as sig:
        response = requests.post(url,
            files={"file": f, "signature_image": sig},
            data={"page_num": 0, "x": 100, "y": 600, "width": 200, "height": 80}
        )
        print("Status:", response.status_code)
        if response.status_code == 200:
            with open("firmado.pdf", "wb") as out:
                out.write(response.content)
            print("PDF guardado!")
        else:
            print("Error:", response.json())
